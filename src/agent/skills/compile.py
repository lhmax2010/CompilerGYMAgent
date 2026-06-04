"""Compile skill orchestration for Phase 05 fake_gbs-backed runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.config import AgentConfig
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

from .error_analyzer import LogContent, classify_compile_failure
from .fake_gbs import FakeGbsCompileResult, FakeGbsFailureMode, FakeGbsHarness
from .result_schema import FailureClassification
from .spec_backup import SpecBackupResult, spec_backup
from .spec_injector import SpecInjectResult, spec_injector
from .spec_restore import SpecRestoreResult, spec_restore
from .workspace_snapshot import WorkspaceSnapshotResult, workspace_snapshot
from .workspace_verify import WorkspaceVerifyResult, workspace_verify


class CompileSkillError(AgentError):
    """Raised when the compile skill cannot preserve recovery semantics."""

    exit_code = EXIT_EXECUTION_REFUSED


@dataclass(frozen=True)
class CompileSkillResult:
    """Result of one protected compile skill invocation."""

    trial_id: str
    combo: tuple[str, ...]
    status: str
    artifact_ref: str | None
    artifact_hash: str | None
    failure_classification: FailureClassification | None
    stdout_ref: str
    stderr_ref: str
    result_ref: str
    lease_ref: str
    process_started_trace_id: str
    compile_result_trace_id: str
    checkpoint: CheckpointState
    workspace_snapshot_pre: WorkspaceSnapshotResult
    spec_backup: SpecBackupResult
    spec_inject: SpecInjectResult
    spec_restore: SpecRestoreResult
    workspace_verify: WorkspaceVerifyResult
    fake_gbs_result: FakeGbsCompileResult

    @property
    def success(self) -> bool:
        return self.status == "success"


def compile_candidate(
    config: AgentConfig,
    layout: NamespaceLayout,
    checkpoint: CheckpointState | dict[str, Any],
    *,
    combo: Sequence[str],
    trial_id: str,
    harness: FakeGbsHarness,
    failure_mode: FakeGbsFailureMode | None = None,
    timeout_seconds: float = 2.0,
    now: datetime | None = None,
) -> CompileSkillResult:
    """Compile one candidate combo through fake_gbs and canonical recovery state."""

    safe_combo = _validate_combo(combo)
    state = CheckpointState.model_validate(checkpoint)
    _validate_checkpoint_for_trial(state, trial_id)
    timestamp = _normalize_now(now)

    pre_snapshot = workspace_snapshot(
        config,
        layout,
        trial_id=trial_id,
        phase="pre",
        now=timestamp,
    )
    backup = spec_backup(config, layout, trial_id=trial_id, now=timestamp)
    injected: SpecInjectResult | None = None
    restored: SpecRestoreResult | None = None
    verified: WorkspaceVerifyResult | None = None
    started_trace_id: str | None = None
    lease_ref: str | None = None
    trace_checkpoint = TraceCheckpointWriter.for_checkpoint(layout, state)

    def on_spawn(spawn: ProcessSpawnResult) -> None:
        nonlocal started_trace_id, lease_ref, trace_checkpoint
        lease = spawn.lease
        lease_ref = _lease_ref(layout, lease)
        process_record = spawn.record.model_dump(mode="json")
        running_checkpoint = _checkpoint_with_compile_operation(
            trace_checkpoint.checkpoint,
            lease_ref=lease_ref,
            status="running",
            output_ref=None,
            details={
                "combo": list(safe_combo),
                "lease_id": lease.lease_id,
            },
        )
        result = trace_checkpoint.append_and_checkpoint(
            "process_started",
            checkpoint=running_checkpoint,
            trial_id=trial_id,
            operation="compile",
            lease_ref=lease_ref,
            process_record=process_record,
            process_lease=process_lease_payload(lease),
        )
        started_trace_id = result.trace.trace_id
        trace_checkpoint.checkpoint = result.checkpoint

    try:
        injected = spec_injector(
            config,
            layout,
            trial_id=trial_id,
            combo=safe_combo,
            now=timestamp,
        )
        fake_result = harness.compile(
            safe_combo,
            trial_id=trial_id,
            failure_mode=failure_mode,
            timeout_seconds=timeout_seconds,
            on_spawn=on_spawn,
        )
    finally:
        restored = spec_restore(
            config,
            layout,
            backup=backup,
            trial_id=trial_id,
            expected_hash=backup.original_hash,
            now=timestamp,
        )
        verified = workspace_verify(
            config,
            layout,
            trial_id=trial_id,
            pre_snapshot=pre_snapshot,
            now=timestamp,
        )

    if injected is None or restored is None or verified is None:
        raise CompileSkillError("compile workspace protection did not complete")
    if started_trace_id is None or lease_ref is None:
        raise CompileSkillError("compile process did not emit process_started trace")

    artifact_ref = _optional_namespace_ref(layout, fake_result.artifact_path)
    stdout_ref = _namespace_ref(layout, fake_result.stdout_path)
    stderr_ref = _namespace_ref(layout, fake_result.stderr_path)
    result_ref = _namespace_ref(layout, fake_result.result_json_path)
    classification = _failure_classification_for_compile(
        fake_result,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        result_ref=result_ref,
    )
    terminal_status = "completed" if fake_result.status == "success" else "failed"
    final_checkpoint = _checkpoint_with_compile_operation(
        trace_checkpoint.checkpoint,
        lease_ref=lease_ref,
        status=terminal_status,
        output_ref=artifact_ref,
        details={
            "status": fake_result.status,
            "artifact_hash": fake_result.artifact_hash,
            "stdout_ref": stdout_ref,
            "stderr_ref": stderr_ref,
            "result_ref": result_ref,
            "exit_code": fake_result.exit_code,
            "signal": fake_result.signal,
            "failure_classification": (
                None
                if classification is None
                else classification.model_dump(mode="json", exclude_none=True)
            ),
        },
    )
    trace_result = trace_checkpoint.append_and_checkpoint(
        "compile_result",
        checkpoint=final_checkpoint,
        trial_id=trial_id,
        status=fake_result.status,
        artifact_ref=artifact_ref,
        artifact_hash=fake_result.artifact_hash,
        failure_classification=(
            None
            if classification is None
            else classification.model_dump(mode="json", exclude_none=True)
        ),
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        result_ref=result_ref,
        lease_ref=lease_ref,
    )

    return CompileSkillResult(
        trial_id=trial_id,
        combo=safe_combo,
        status=fake_result.status,
        artifact_ref=artifact_ref,
        artifact_hash=fake_result.artifact_hash,
        failure_classification=classification,
        stdout_ref=stdout_ref,
        stderr_ref=stderr_ref,
        result_ref=result_ref,
        lease_ref=lease_ref,
        process_started_trace_id=started_trace_id,
        compile_result_trace_id=trace_result.trace.trace_id,
        checkpoint=trace_result.checkpoint,
        workspace_snapshot_pre=pre_snapshot,
        spec_backup=backup,
        spec_inject=injected,
        spec_restore=restored,
        workspace_verify=verified,
        fake_gbs_result=fake_result,
    )


def _checkpoint_with_compile_operation(
    checkpoint: CheckpointState,
    *,
    lease_ref: str,
    status: str,
    output_ref: str | None,
    details: dict[str, Any],
) -> CheckpointState:
    payload = checkpoint_payload(checkpoint)
    current_trial = payload.get("current_trial")
    if not isinstance(current_trial, dict):
        raise CompileSkillError("checkpoint.current_trial is required for compile")
    operations = [
        dict(operation) for operation in (current_trial.get("operations") or [])
    ]
    replaced = False
    for index, operation in enumerate(operations):
        if (
            operation.get("op") == "compile"
            and lease_ref in tuple(operation.get("process_refs") or ())
        ):
            operations[index] = _compile_operation_payload(
                status=status,
                process_refs=(lease_ref,),
                output_ref=output_ref,
                details=details,
            )
            replaced = True
            break
    if not replaced:
        operations.append(
            _compile_operation_payload(
                status=status,
                process_refs=(lease_ref,),
                output_ref=output_ref,
                details=details,
            )
        )
    current_trial["operations"] = operations
    current_trial["current_stage"] = "compiling"
    current_trial["process"] = None
    current_trial["stage_started_at"] = datetime.now(UTC).isoformat()
    payload["last_updated"] = datetime.now(UTC).isoformat()
    return CheckpointState.model_validate(payload)


def _compile_operation_payload(
    *,
    status: str,
    process_refs: tuple[str, ...],
    output_ref: str | None,
    details: dict[str, Any],
) -> dict[str, Any]:
    operation = CheckpointTrialOperation(
        op="compile",
        status=status,  # type: ignore[arg-type]
        process_refs=process_refs,
        output_ref=output_ref,
        details=details,
    )
    return operation.model_dump(mode="json", exclude_none=True)


def _failure_classification_for_compile(
    result: FakeGbsCompileResult,
    *,
    stdout_ref: str,
    stderr_ref: str,
    result_ref: str,
) -> FailureClassification | None:
    return classify_compile_failure(
        result.status,
        combo=result.combo,
        stdout=LogContent(ref=stdout_ref, text=_read_text(result.stdout_path)),
        stderr=LogContent(ref=stderr_ref, text=_read_text(result.stderr_path)),
        result_json_ref=result_ref if result.result_json_path.exists() else None,
    )


def _validate_checkpoint_for_trial(checkpoint: CheckpointState, trial_id: str) -> None:
    current_trial = checkpoint.current_trial
    if current_trial is None:
        raise CompileSkillError("checkpoint.current_trial is required for compile")
    if current_trial.trial_id != trial_id:
        raise CompileSkillError(
            "checkpoint.current_trial.trial_id must match compile trial_id"
        )
    if current_trial.current_trial_start_line is None:
        raise CompileSkillError(
            "current_trial_start_line is required before compile operation ledger writes"
        )


def _validate_combo(combo: Sequence[str]) -> tuple[str, ...]:
    if isinstance(combo, str):
        raise CompileSkillError("combo must be a sequence of option strings")
    values = tuple(str(option).strip() for option in combo)
    if not values:
        raise CompileSkillError("combo must contain at least one option")
    for option in values:
        if not option:
            raise CompileSkillError("combo options must be non-empty")
        if "\x00" in option or "\n" in option or "\r" in option:
            raise CompileSkillError("combo options must not contain NUL or newline")
    return values


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
        raise CompileSkillError(f"path is outside namespace: {path}") from exc


def _optional_namespace_ref(layout: NamespaceLayout, path: Path | None) -> str | None:
    if path is None:
        return None
    return _namespace_ref(layout, path)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise CompileSkillError("now must be timezone-aware")
    return value.astimezone(UTC)
