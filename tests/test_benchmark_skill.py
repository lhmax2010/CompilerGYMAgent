from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

import agent.trace as trace_module
from agent import (
    RunLevelRecord,
    TraceWriteError,
    append_trace_event,
    compute_result_combo_hash,
    load_checkpoint_for_layout,
    load_process_leases,
    load_trace_events,
    trace_event_payload,
)
from agent.skills.benchmark import _summary_hint, benchmark_candidate
from agent.skills.fake_gbs import FakeGbsHarness
from tests.fixtures.fake_workspace import create_fake_workspace


pytestmark = pytest.mark.skipif(os.name != "posix", reason="benchmark skill uses fake_gbs")

SESSION_ID = "sess_benchmark_skill"
TRIAL_ID = "trial_benchmark_1"
NOW = datetime(2026, 6, 4, 14, 0, tzinfo=UTC)


def test_benchmark_skill_returns_run_level_records_and_checkpoint_refs(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=201,
    )
    compile_result = harness.compile(["-O3"], trial_id=TRIAL_ID)
    assert compile_result.artifact_path is not None
    assert compile_result.artifact_hash is not None

    result = benchmark_candidate(
        fake.layout,
        checkpoint,
        artifact_path=compile_result.artifact_path,
        artifact_hash=compile_result.artifact_hash,
        combo=["-O3"],
        trial_id=TRIAL_ID,
        harness=harness,
        objective_direction="higher_is_better",
        warmup_runs=1,
        measured_runs=2,
        noise_profile="gaussian",
        now=NOW,
    )

    assert result.status == "success"
    assert len(result.records) == 3
    assert [record.phase for record in result.records] == ["warmup", "measured", "measured"]
    assert [record.run_index for record in result.records] == [0, 0, 1]
    assert all(record.valid_for_scoring for record in result.records)
    assert all(record.objective_direction == "higher_is_better" for record in result.records)
    assert all(record.artifact_hash == compile_result.artifact_hash for record in result.records)
    assert all(record.artifact_hash_verified is True for record in result.records)
    assert all(record.failure_classification is None for record in result.records)
    assert result.summary_hint is not None
    assert result.summary_hint.mean is not None
    assert result.summary_hint.n_measured == 2
    assert result.summary_hint.n_valid == 2
    assert result.summary_hint.n_invalid == 0
    assert result.summary_hint.effective_sample_size == 2.0
    assert result.summary_hint.ess_preliminary is True
    assert result.records[-1].summary_hint == result.summary_hint

    payloads = [trace_event_payload(event) for event in load_trace_events(fake.layout.trace_path)]
    assert [payload["kind"] for payload in payloads] == [
        "trial_start",
        "process_started",
        "benchmark_run_result",
        "process_started",
        "benchmark_run_result",
        "process_started",
        "benchmark_run_result",
    ]
    assert all(payload.get("operation") == "benchmark" for payload in payloads if payload["kind"] == "process_started")
    assert len(result.process_started_trace_ids) == 3
    assert len(result.run_result_trace_ids) == 3
    assert len(result.lease_refs) == 3

    checkpoint_after = load_checkpoint_for_layout(fake.layout)
    assert checkpoint_after.trace_line_count == 7
    assert checkpoint_after.current_trial is not None
    assert checkpoint_after.current_trial.process is None
    operation = checkpoint_after.current_trial.operations[-1]
    assert operation.op == "benchmark"
    assert operation.status == "completed"
    assert operation.process_refs == result.lease_refs

    benchmark_leases = [
        lease for lease in load_process_leases(fake.layout) if lease.role == "benchmark"
    ]
    assert len(benchmark_leases) == 3
    assert {lease.status for lease in benchmark_leases} == {"exited"}


def test_benchmark_skill_score_parse_failed_is_hard_failure_record(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=202,
    )
    compile_result = harness.compile(["-O2"], trial_id=TRIAL_ID)
    assert compile_result.artifact_path is not None
    assert compile_result.artifact_hash is not None

    result = benchmark_candidate(
        fake.layout,
        checkpoint,
        artifact_path=compile_result.artifact_path,
        artifact_hash=compile_result.artifact_hash,
        combo=["-O2"],
        trial_id=TRIAL_ID,
        harness=harness,
        objective_direction="lower_is_better",
        measured_runs=1,
        failure_mode="score_parse_failed",
        now=NOW,
    )

    assert result.status == "failed"
    assert len(result.records) == 1
    record = result.records[0]
    assert record.valid_for_scoring is False
    assert record.score is None
    assert record.invalid_reason == "score_parse_failed"
    assert record.score_source_ref is not None
    assert record.failure_classification is not None
    assert record.failure_classification.category == "score_parse_failed"
    assert record.failure_classification.write_failed_combos is False

    checkpoint_after = load_checkpoint_for_layout(fake.layout)
    assert checkpoint_after.current_trial is not None
    assert checkpoint_after.current_trial.operations[-1].status == "failed"


def test_benchmark_skill_artifact_hash_mismatch_does_not_spawn(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=203,
    )
    compile_result = harness.compile(["-O2"], trial_id=TRIAL_ID)
    assert compile_result.artifact_path is not None
    assert compile_result.artifact_hash is not None

    result = benchmark_candidate(
        fake.layout,
        checkpoint,
        artifact_path=compile_result.artifact_path,
        artifact_hash="sha256:" + ("0" * 64),
        combo=["-O2"],
        trial_id=TRIAL_ID,
        harness=harness,
        objective_direction="higher_is_better",
        measured_runs=1,
        now=NOW,
    )

    assert result.status == "failed"
    assert result.process_started_trace_ids == ()
    assert result.lease_refs == ()
    assert len(result.records) == 1
    record = result.records[0]
    assert record.valid_for_scoring is False
    assert record.invalid_reason == "artifact_invalid"
    assert record.artifact_hash_verified is False
    assert record.failure_classification is not None
    assert record.failure_classification.category == "artifact_invalid"
    payloads = [trace_event_payload(event) for event in load_trace_events(fake.layout.trace_path)]
    assert [payload["kind"] for payload in payloads] == [
        "trial_start",
        "benchmark_run_result",
    ]
    benchmark_leases = [
        lease for lease in load_process_leases(fake.layout) if lease.role == "benchmark"
    ]
    assert benchmark_leases == []


def test_summary_hint_uses_none_cv_when_mean_is_near_zero() -> None:
    records = (
        _run_record(score=-1.0, run_index=0),
        _run_record(score=1.0, run_index=1),
    )

    summary = _summary_hint(records)

    assert summary is not None
    assert summary.mean == 0.0
    assert summary.cv is None
    assert summary.n_measured == 2
    assert summary.n_valid == 2
    assert summary.n_invalid == 0


def test_benchmark_skill_trace_failure_kills_process_and_terminalizes_lease(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=204,
    )
    compile_result = harness.compile(["-O2"], trial_id=TRIAL_ID)
    assert compile_result.artifact_path is not None
    assert compile_result.artifact_hash is not None
    original_append = trace_module.append_trace_event

    def fail_process_started(layout, event, *, expected_line_number=None):
        payload = trace_event_payload(event)
        if payload["kind"] == "process_started":
            raise TraceWriteError("injected benchmark process_started failure")
        return original_append(
            layout,
            event,
            expected_line_number=expected_line_number,
        )

    monkeypatch.setattr(trace_module, "append_trace_event", fail_process_started)

    with pytest.raises(TraceWriteError, match="process_started"):
        benchmark_candidate(
            fake.layout,
            checkpoint,
            artifact_path=compile_result.artifact_path,
            artifact_hash=compile_result.artifact_hash,
            combo=["-O2"],
            trial_id=TRIAL_ID,
            harness=harness,
            objective_direction="higher_is_better",
            measured_runs=1,
            failure_mode="timeout",
            timeout_seconds=0.1,
            now=NOW,
        )

    benchmark_leases = [
        lease for lease in load_process_leases(fake.layout) if lease.role == "benchmark"
    ]
    assert len(benchmark_leases) == 1
    assert benchmark_leases[0].status == "killed"
    assert not _pgid_has_members(benchmark_leases[0].record.pgid)
    assert [event.kind for event in load_trace_events(fake.layout.trace_path)] == [
        "trial_start",
    ]
    assert not fake.layout.checkpoint_path.exists()


def _checkpoint(fake) -> dict[str, object]:
    append_trace_event(
        fake.layout,
        {
            "ts": NOW,
            "kind": "trial_start",
            "session_id": SESSION_ID,
            "namespace": str(fake.layout.namespace),
            "trial_id": TRIAL_ID,
            "combo": ["-O2"],
            "mode": "test",
        },
        expected_line_number=1,
    )
    return {
        "session_id": SESSION_ID,
        "namespace": str(fake.layout.namespace),
        "last_completed_trial": None,
        "current_trial": {
            "trial_id": TRIAL_ID,
            "started_at": NOW,
            "current_stage": "benchmarking",
            "stage_started_at": NOW,
            "spec_backup_path": None,
            "workspace_snapshot_pre": None,
            "build_dir": str(
                Path(fake.config.workspace_protection.build_dir_root) / TRIAL_ID
            ),
            "artifact_staging": str(
                Path(fake.config.workspace_protection.artifact_staging_dir) / TRIAL_ID
            ),
            "process": None,
            "operations": [],
            "current_trial_start_line": 1,
        },
        "current_best": None,
        "explorer_state": {},
        "random_seed": 1,
        "total_tokens_consumed": 0,
        "trace_line_count": 1,
        "last_updated": NOW,
    }


def _run_record(*, score: float, run_index: int) -> RunLevelRecord:
    return RunLevelRecord(
        run_id=f"run_{run_index}",
        run_index=run_index,
        combo_hash=compute_result_combo_hash(["-O2"]),
        score=score,
        phase="measured",
        metric_name="throughput",
        metric_unit="items/sec",
        objective_direction="higher_is_better",
        duration_sec=0.1,
        started_at=NOW,
        ended_at=NOW,
        exit_code=0,
        stdout_ref="logs/bench.stdout#L1",
        stderr_ref="logs/bench.stderr#L1",
        valid_for_scoring=True,
        benchmark_cmd=("fake-gbs", "benchmark"),
        artifact_ref="artifacts/fake/run.artifact",
        artifact_hash="sha256:" + "a" * 64,
        artifact_hash_verified=True,
        score_source_ref="logs/bench.stdout#L1",
    )


def _pgid_has_members(pgid: int) -> bool:
    for proc in psutil.process_iter(["pid", "status"]):
        try:
            if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                continue
            if os.getpgid(proc.info["pid"]) == pgid:
                return True
        except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False
