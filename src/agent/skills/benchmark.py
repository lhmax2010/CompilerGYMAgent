"""Benchmark skill orchestration and run-level record production."""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Literal

import psutil

from agent.errors import AgentError, EXIT_EXECUTION_REFUSED
from agent.fs_memory import (
    CheckpointState,
    CheckpointTrialOperation,
    NamespaceLayout,
    checkpoint_payload,
)
from agent.process_registry import process_lease_path, process_lease_payload
from agent.process_runner import ProcessSpawnResult
from agent.trace import TraceCheckpointWriter

from .error_analyzer import LogContent, classify_benchmark_failure
from .fake_gbs import (
    FakeGbsBenchmarkResult,
    FakeGbsFailureMode,
    FakeGbsHarness,
    FakeGbsNoiseProfile,
)
from .result_schema import (
    FailureClassification,
    ObjectiveDirection,
    RunEnvironmentSnapshot,
    RunLevelRecord,
    RunPhase,
    RunSummaryHint,
    compute_combo_hash,
)


class BenchmarkSkillError(AgentError):
    """Raised when benchmark orchestration cannot preserve recovery semantics."""

    exit_code = EXIT_EXECUTION_REFUSED


@dataclass(frozen=True)
class BenchmarkSkillResult:
    """Result of one benchmark skill invocation."""

    trial_id: str
    combo: tuple[str, ...]
    records: tuple[RunLevelRecord, ...]
    summary_hint: RunSummaryHint | None
    status: Literal["success", "failed"]
    checkpoint: CheckpointState
    process_started_trace_ids: tuple[str, ...]
    run_result_trace_ids: tuple[str, ...]
    lease_refs: tuple[str, ...]
    fake_gbs_results: tuple[FakeGbsBenchmarkResult, ...]

    @property
    def measured_records(self) -> tuple[RunLevelRecord, ...]:
        return tuple(record for record in self.records if record.phase == "measured")


def benchmark_candidate(
    layout: NamespaceLayout,
    checkpoint: CheckpointState | dict[str, Any],
    *,
    artifact_path: Path,
    artifact_hash: str,
    combo: Sequence[str],
    trial_id: str,
    harness: FakeGbsHarness,
    objective_direction: ObjectiveDirection,
    metric_name: str = "score",
    metric_unit: str = "points",
    warmup_runs: int = 0,
    measured_runs: int = 1,
    noise_profile: FakeGbsNoiseProfile = "gaussian",
    failure_mode: FakeGbsFailureMode | None = None,
    timeout_seconds: float = 2.0,
    now: datetime | None = None,
) -> BenchmarkSkillResult:
    """Run benchmark measurements and return Phase 08-ready run records."""

    safe_combo = _validate_combo(combo)
    if warmup_runs < 0 or measured_runs <= 0:
        raise BenchmarkSkillError("warmup_runs must be >= 0 and measured_runs must be > 0")
    state = CheckpointState.model_validate(checkpoint)
    _validate_checkpoint_for_trial(state, trial_id)
    expected_artifact_hash = _validate_sha256(artifact_hash, "artifact_hash")
    artifact = Path(artifact_path)
    combo_hash = compute_combo_hash(list(safe_combo))
    trace_checkpoint = TraceCheckpointWriter.for_checkpoint(layout, state)
    process_started_trace_ids: list[str] = []
    run_result_trace_ids: list[str] = []
    lease_refs: list[str] = []
    records: list[RunLevelRecord] = []
    fake_results: list[FakeGbsBenchmarkResult] = []

    actual_artifact_hash = _sha256_file(artifact) if artifact.exists() else None
    if actual_artifact_hash != expected_artifact_hash:
        record = _artifact_invalid_record(
            layout=layout,
            harness=harness,
            trial_id=trial_id,
            combo_hash=combo_hash,
            artifact=artifact,
            expected_hash=expected_artifact_hash,
            actual_hash=actual_artifact_hash,
            objective_direction=objective_direction,
            metric_name=metric_name,
            metric_unit=metric_unit,
            now=_normalize_now(now),
        )
        final_checkpoint = _checkpoint_with_benchmark_operation(
            trace_checkpoint.checkpoint,
            lease_refs=(),
            status="failed",
            output_ref=None,
            details={"records": [record.model_dump(mode="json", exclude_none=True)]},
        )
        trace_result = trace_checkpoint.append_and_checkpoint(
            "benchmark_run_result",
            checkpoint=final_checkpoint,
            trial_id=trial_id,
            run_id=record.run_id,
            run_index=record.run_index,
            phase=record.phase,
            valid_for_scoring=False,
            failure_classification=record.failure_classification.model_dump(
                mode="json",
                exclude_none=True,
            )
            if record.failure_classification is not None
            else None,
            artifact_ref=record.artifact_ref,
            artifact_hash=record.artifact_hash,
            artifact_hash_verified=False,
        )
        return BenchmarkSkillResult(
            trial_id=trial_id,
            combo=safe_combo,
            records=(record,),
            summary_hint=None,
            status="failed",
            checkpoint=trace_result.checkpoint,
            process_started_trace_ids=(),
            run_result_trace_ids=(trace_result.trace.trace_id,),
            lease_refs=(),
            fake_gbs_results=(),
        )

    run_plan = _run_plan(warmup_runs=warmup_runs, measured_runs=measured_runs)
    for plan_index, (phase, run_index) in enumerate(run_plan):
        run_id = _run_id(trial_id, phase=phase, run_index=run_index)
        current_run_started = _normalize_now(now) if now is not None else datetime.now(UTC)
        current_lease_ref: str | None = None

        def on_spawn(spawn: ProcessSpawnResult) -> None:
            nonlocal current_lease_ref, trace_checkpoint
            lease = spawn.lease
            current_lease_ref = _lease_ref(layout, lease)
            if current_lease_ref not in lease_refs:
                lease_refs.append(current_lease_ref)
            running_checkpoint = _checkpoint_with_benchmark_operation(
                trace_checkpoint.checkpoint,
                lease_refs=tuple(lease_refs),
                status="running",
                output_ref=None,
                details={
                    "active_run_id": run_id,
                    "active_run_index": run_index,
                    "phase": phase,
                    "artifact_hash": expected_artifact_hash,
                },
            )
            result = trace_checkpoint.append_and_checkpoint(
                "process_started",
                checkpoint=running_checkpoint,
                trial_id=trial_id,
                operation="benchmark",
                run_id=run_id,
                run_index=run_index,
                phase=phase,
                lease_ref=current_lease_ref,
                process_record=spawn.record.model_dump(mode="json"),
                process_lease=process_lease_payload(lease),
            )
            process_started_trace_ids.append(result.trace.trace_id)
            trace_checkpoint.checkpoint = result.checkpoint

        fake_result = harness.benchmark(
            artifact,
            trial_id=trial_id,
            run_index=run_index,
            noise_profile=noise_profile,
            failure_mode=failure_mode,
            timeout_seconds=timeout_seconds,
            on_spawn=on_spawn,
        )
        if current_lease_ref is None:
            raise BenchmarkSkillError("benchmark process did not emit process_started trace")
        current_run_ended = datetime.now(UTC)
        record = _run_record_from_fake_result(
            layout=layout,
            result=fake_result,
            run_id=run_id,
            run_index=run_index,
            phase=phase,
            combo_hash=combo_hash,
            objective_direction=objective_direction,
            metric_name=metric_name,
            metric_unit=metric_unit,
            benchmark_cmd=("fake_gbs", "benchmark"),
            started_at=current_run_started,
            ended_at=current_run_ended,
            expected_artifact_hash=expected_artifact_hash,
        )
        records.append(record)
        fake_results.append(fake_result)
        is_last_run = plan_index == len(run_plan) - 1
        terminal_status = (
            "failed"
            if not record.valid_for_scoring
            else "completed"
            if is_last_run
            else "running"
        )
        checkpoint_for_result = _checkpoint_with_benchmark_operation(
            trace_checkpoint.checkpoint,
            lease_refs=tuple(lease_refs),
            status=terminal_status,
            output_ref=record.artifact_ref,
            details={
                "last_run_id": run_id,
                "last_run_index": run_index,
                "last_phase": phase,
                "records_count": len(records),
                "last_record": record.model_dump(mode="json", exclude_none=True),
            },
        )
        trace_result = trace_checkpoint.append_and_checkpoint(
            "benchmark_run_result",
            checkpoint=checkpoint_for_result,
            trial_id=trial_id,
            run_id=run_id,
            run_index=run_index,
            phase=phase,
            score=record.score,
            valid_for_scoring=record.valid_for_scoring,
            invalid_reason=record.invalid_reason,
            failure_classification=(
                None
                if record.failure_classification is None
                else record.failure_classification.model_dump(mode="json", exclude_none=True)
            ),
            artifact_ref=record.artifact_ref,
            artifact_hash=record.artifact_hash,
            artifact_hash_verified=record.artifact_hash_verified,
            lease_ref=current_lease_ref,
        )
        run_result_trace_ids.append(trace_result.trace.trace_id)
        trace_checkpoint.checkpoint = trace_result.checkpoint
        if not record.valid_for_scoring:
            break

    summary_hint = _summary_hint(records)
    records_with_summary = tuple(
        record.model_copy(update={"summary_hint": summary_hint}) for record in records
    )

    return BenchmarkSkillResult(
        trial_id=trial_id,
        combo=safe_combo,
        records=records_with_summary,
        summary_hint=summary_hint,
        status="failed"
        if any(not record.valid_for_scoring for record in records_with_summary)
        else "success",
        checkpoint=trace_checkpoint.checkpoint,
        process_started_trace_ids=tuple(process_started_trace_ids),
        run_result_trace_ids=tuple(run_result_trace_ids),
        lease_refs=tuple(lease_refs),
        fake_gbs_results=tuple(fake_results),
    )


def _run_record_from_fake_result(
    *,
    layout: NamespaceLayout,
    result: FakeGbsBenchmarkResult,
    run_id: str,
    run_index: int,
    phase: RunPhase,
    combo_hash: str,
    objective_direction: ObjectiveDirection,
    metric_name: str,
    metric_unit: str,
    benchmark_cmd: tuple[str, ...],
    started_at: datetime,
    ended_at: datetime,
    expected_artifact_hash: str,
) -> RunLevelRecord:
    artifact_ref = _namespace_ref(layout, result.artifact_path)
    stdout_ref = _namespace_ref(layout, result.stdout_path)
    stderr_ref = _namespace_ref(layout, result.stderr_path)
    score_source_ref = f"{stdout_ref}#L1"
    classification = _failure_classification_for_benchmark(
        result,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        result_ref=_namespace_ref(layout, result.result_json_path)
        if result.result_json_path.exists()
        else None,
    )
    valid = result.status == "success" and result.score is not None
    return RunLevelRecord(
        run_id=run_id,
        run_index=run_index,
        combo_hash=combo_hash,
        score=result.score if valid else None,
        phase=phase,
        metric_name=metric_name,
        metric_unit=metric_unit,
        objective_direction=objective_direction,
        duration_sec=max((ended_at - started_at).total_seconds(), 0.0),
        started_at=started_at,
        ended_at=ended_at,
        exit_code=result.exit_code,
        signal=result.signal,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        env_snapshot=_environment_snapshot(),
        valid_for_scoring=valid,
        invalid_reason=None if valid else result.status,
        benchmark_cmd=benchmark_cmd,
        artifact_ref=artifact_ref,
        artifact_hash=expected_artifact_hash,
        artifact_hash_verified=result.artifact_hash_verified
        and result.artifact_hash == expected_artifact_hash,
        score_source_ref=score_source_ref,
        pair_key=None,
        failure_classification=classification,
    )


def _failure_classification_for_benchmark(
    result: FakeGbsBenchmarkResult,
    *,
    stdout_ref: str,
    stderr_ref: str,
    result_ref: str | None,
) -> FailureClassification | None:
    return classify_benchmark_failure(
        result.status,
        stdout=LogContent(ref=stdout_ref, text=_read_text(result.stdout_path)),
        stderr=LogContent(ref=stderr_ref, text=_read_text(result.stderr_path)),
        result_json_ref=result_ref,
    )


def _artifact_invalid_record(
    *,
    layout: NamespaceLayout,
    harness: FakeGbsHarness,
    trial_id: str,
    combo_hash: str,
    artifact: Path,
    expected_hash: str,
    actual_hash: str | None,
    objective_direction: ObjectiveDirection,
    metric_name: str,
    metric_unit: str,
    now: datetime,
) -> RunLevelRecord:
    logs_dir = harness.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_id = _run_id(trial_id, phase="measured", run_index=0)
    stdout_path = logs_dir / f"{run_id}.stdout.log"
    stderr_path = logs_dir / f"{run_id}.stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text(
        "artifact hash mismatch before benchmark "
        f"(expected={expected_hash}, actual={actual_hash})\n",
        encoding="utf-8",
    )
    return RunLevelRecord(
        run_id=run_id,
        run_index=0,
        combo_hash=combo_hash,
        score=None,
        phase="measured",
        metric_name=metric_name,
        metric_unit=metric_unit,
        objective_direction=objective_direction,
        duration_sec=0.0,
        started_at=now,
        ended_at=now,
        exit_code=None,
        signal=None,
        stdout_ref=_namespace_ref(layout, stdout_path),
        stderr_ref=_namespace_ref(layout, stderr_path),
        env_snapshot=_environment_snapshot(),
        valid_for_scoring=False,
        invalid_reason="artifact_invalid",
        benchmark_cmd=("fake_gbs", "benchmark"),
        artifact_ref=_namespace_ref(layout, artifact),
        artifact_hash=actual_hash,
        artifact_hash_verified=False,
        score_source_ref=None,
        pair_key=None,
        failure_classification=FailureClassification(
            category="artifact_invalid",
            route="unknown",
            confidence="LOW",
            retryable=False,
            write_failed_combos=False,
        ),
    )


def _checkpoint_with_benchmark_operation(
    checkpoint: CheckpointState,
    *,
    lease_refs: tuple[str, ...],
    status: str,
    output_ref: str | None,
    details: dict[str, Any],
) -> CheckpointState:
    payload = checkpoint_payload(checkpoint)
    current_trial = payload.get("current_trial")
    if not isinstance(current_trial, dict):
        raise BenchmarkSkillError("checkpoint.current_trial is required for benchmark")
    operations = [
        dict(operation) for operation in (current_trial.get("operations") or [])
    ]
    operation_payload = CheckpointTrialOperation(
        op="benchmark",
        status=status,  # type: ignore[arg-type]
        process_refs=lease_refs,
        output_ref=output_ref,
        details=details,
    ).model_dump(mode="json", exclude_none=True)
    for index, operation in enumerate(operations):
        if operation.get("op") == "benchmark":
            operations[index] = operation_payload
            break
    else:
        operations.append(operation_payload)
    current_trial["operations"] = operations
    current_trial["current_stage"] = "benchmarking"
    current_trial["process"] = None
    current_trial["stage_started_at"] = datetime.now(UTC).isoformat()
    payload["last_updated"] = datetime.now(UTC).isoformat()
    return CheckpointState.model_validate(payload)


def _summary_hint(records: Sequence[RunLevelRecord]) -> RunSummaryHint | None:
    scores = [
        record.score
        for record in records
        if record.phase == "measured" and record.valid_for_scoring and record.score is not None
    ]
    if not scores:
        return None
    average = mean(scores)
    stddev = stdev(scores) if len(scores) > 1 else 0.0
    cv = None if math.isclose(average, 0.0, abs_tol=1e-12) else abs(stddev / average)
    return RunSummaryHint(
        mean=average,
        median=median(scores),
        stddev=stddev,
        cv=cv,
    )


def _run_plan(
    *,
    warmup_runs: int,
    measured_runs: int,
) -> tuple[tuple[RunPhase, int], ...]:
    plan: list[tuple[RunPhase, int]] = []
    for index in range(warmup_runs):
        plan.append(("warmup", index))
    for index in range(measured_runs):
        plan.append(("measured", index))
    return tuple(plan)


def _environment_snapshot() -> RunEnvironmentSnapshot:
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = None
    try:
        mem_available = int(psutil.virtual_memory().available)
    except (psutil.Error, OSError):
        mem_available = None
    return RunEnvironmentSnapshot(
        loadavg_1m=load1,
        loadavg_5m=load5,
        loadavg_15m=load15,
        mem_available_bytes=mem_available,
    )


def _validate_checkpoint_for_trial(checkpoint: CheckpointState, trial_id: str) -> None:
    current_trial = checkpoint.current_trial
    if current_trial is None:
        raise BenchmarkSkillError("checkpoint.current_trial is required for benchmark")
    if current_trial.trial_id != trial_id:
        raise BenchmarkSkillError(
            "checkpoint.current_trial.trial_id must match benchmark trial_id"
        )
    if current_trial.current_trial_start_line is None:
        raise BenchmarkSkillError(
            "current_trial_start_line is required before benchmark operation ledger writes"
        )


def _validate_combo(combo: Sequence[str]) -> tuple[str, ...]:
    if isinstance(combo, str):
        raise BenchmarkSkillError("combo must be a sequence of option strings")
    values = tuple(str(option).strip() for option in combo)
    if not values:
        raise BenchmarkSkillError("combo must contain at least one option")
    for option in values:
        if not option:
            raise BenchmarkSkillError("combo options must be non-empty")
        if "\x00" in option or "\n" in option or "\r" in option:
            raise BenchmarkSkillError("combo options must not contain NUL or newline")
    return values


def _validate_sha256(value: str, label: str) -> str:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise BenchmarkSkillError(f"{label} must start with 'sha256:'")
    digest = value[len(prefix) :]
    if len(digest) != 64:
        raise BenchmarkSkillError(f"{label} must contain a 64-character digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise BenchmarkSkillError(f"{label} must be hexadecimal") from exc
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _lease_ref(layout: NamespaceLayout, lease: Any) -> str:
    path = process_lease_path(
        layout,
        session_id=lease.session_id,
        trial_id=lease.trial_id,
        role=lease.role,
        pid=lease.record.pid,
    )
    return _namespace_ref(layout, path)


def _namespace_ref(layout: NamespaceLayout, path: Path) -> str:
    try:
        return path.relative_to(layout.namespace_dir).as_posix()
    except ValueError as exc:
        raise BenchmarkSkillError(f"path is outside namespace: {path}") from exc


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _run_id(trial_id: str, *, phase: str, run_index: int) -> str:
    safe_trial = "".join(char if char.isalnum() or char in "_-" else "_" for char in trial_id)
    return f"benchmark_{safe_trial}_{phase}_{run_index}"


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise BenchmarkSkillError("now must be timezone-aware")
    return value.astimezone(UTC)
