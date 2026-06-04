from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

import agent.trace as trace_module
from agent import (
    TraceWriteError,
    append_trace_event,
    load_checkpoint_for_layout,
    load_process_lease,
    load_process_leases,
    load_trace_events,
    trace_event_payload,
)
from agent.skills.compile import compile_candidate
from agent.skills.fake_gbs import FakeGbsHarness
from tests.fixtures.fake_workspace import create_fake_workspace


pytestmark = pytest.mark.skipif(os.name != "posix", reason="compile skill uses fake_gbs")

SESSION_ID = "sess_compile_skill"
TRIAL_ID = "trial_compile_1"
NOW = datetime(2026, 6, 4, 13, 0, tzinfo=UTC)


def test_compile_skill_success_records_trace_checkpoint_and_restores_spec(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=101,
    )

    result = compile_candidate(
        fake.config,
        fake.layout,
        checkpoint,
        combo=["-O3", "-funroll-loops"],
        trial_id=TRIAL_ID,
        harness=harness,
        now=NOW,
    )

    assert result.success is True
    assert result.artifact_ref is not None
    assert result.artifact_hash is not None
    assert result.failure_classification is None
    assert "{{AGENT_COMBO}}" in fake.spec_path.read_text(encoding="utf-8")
    assert result.workspace_verify.ok is True

    trace_payloads = [trace_event_payload(event) for event in load_trace_events(fake.layout.trace_path)]
    assert [payload["kind"] for payload in trace_payloads] == [
        "trial_start",
        "process_started",
        "compile_result",
    ]
    process_started = trace_payloads[1]
    assert process_started["trial_id"] == TRIAL_ID
    assert process_started["operation"] == "compile"
    assert process_started["lease_ref"] == result.lease_ref
    assert process_started["process_record"]["lease_id"]
    assert process_started["process_record"]["trial_id"] == TRIAL_ID
    assert process_started["process_lease"]["record"]["pgid"] == (
        process_started["process_lease"]["record"]["pid"]
    )

    checkpoint_after = load_checkpoint_for_layout(fake.layout)
    assert checkpoint_after.trace_line_count == 3
    assert checkpoint_after.current_trial is not None
    assert checkpoint_after.current_trial.process is None
    assert checkpoint_after.current_trial.operations[-1].op == "compile"
    assert checkpoint_after.current_trial.operations[-1].status == "completed"
    assert checkpoint_after.current_trial.operations[-1].process_refs == (result.lease_ref,)
    assert checkpoint_after.current_trial.operations[-1].output_ref == result.artifact_ref

    lease = load_process_lease(fake.layout.namespace_dir / result.lease_ref)
    assert lease.status == "exited"
    assert lease.lease_id == lease.record.lease_id


def test_compile_skill_trace_failure_kills_process_and_terminalizes_lease(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=102,
    )
    original_append = trace_module.append_trace_event

    def fail_process_started(layout, event, *, expected_line_number=None):
        payload = trace_event_payload(event)
        if payload["kind"] == "process_started":
            raise TraceWriteError("injected process_started failure")
        return original_append(
            layout,
            event,
            expected_line_number=expected_line_number,
        )

    monkeypatch.setattr(trace_module, "append_trace_event", fail_process_started)

    with pytest.raises(TraceWriteError, match="process_started"):
        compile_candidate(
            fake.config,
            fake.layout,
            checkpoint,
            combo=["-O3"],
            trial_id=TRIAL_ID,
            harness=harness,
            failure_mode="timeout",
            timeout_seconds=0.1,
            now=NOW,
        )

    leases = load_process_leases(fake.layout)
    assert len(leases) == 1
    assert leases[0].status == "killed"
    assert not _pgid_has_members(leases[0].record.pgid)
    assert "{{AGENT_COMBO}}" in fake.spec_path.read_text(encoding="utf-8")
    assert [event.kind for event in load_trace_events(fake.layout.trace_path)] == [
        "trial_start",
    ]
    assert not fake.layout.checkpoint_path.exists()


def test_compile_skill_failure_uses_result_schema_and_operation_ledger(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    checkpoint = _checkpoint(fake)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=fake.layout.namespace_dir / "fake_gbs",
        session_id=SESSION_ID,
        seed=103,
    )

    result = compile_candidate(
        fake.config,
        fake.layout,
        checkpoint,
        combo=["-finvalid-option"],
        trial_id=TRIAL_ID,
        harness=harness,
        failure_mode="invalid_option",
        now=NOW,
    )

    assert result.success is False
    assert result.failure_classification is not None
    assert result.failure_classification.category == "invalid_option"
    assert result.failure_classification.route == "option_related"
    assert result.failure_classification.confidence == "HIGH"
    assert result.failure_classification.write_failed_combos is True
    assert result.failure_classification.affected_options == ("-finvalid-option",)
    assert result.failure_classification.matched_rule_id == "gcc_unknown_option_v1"

    checkpoint_after = load_checkpoint_for_layout(fake.layout)
    assert checkpoint_after.current_trial is not None
    assert checkpoint_after.current_trial.process is None
    operation = checkpoint_after.current_trial.operations[-1]
    assert operation.op == "compile"
    assert operation.status == "failed"
    assert operation.output_ref is None
    assert operation.details["failure_classification"]["category"] == "invalid_option"
    assert operation.details["failure_classification"]["write_failed_combos"] is True


def _checkpoint(fake) -> dict[str, object]:
    append_trace_event(
        fake.layout,
        {
            "ts": NOW,
            "kind": "trial_start",
            "session_id": SESSION_ID,
            "namespace": str(fake.layout.namespace),
            "trial_id": TRIAL_ID,
            "combo": ["-O3"],
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
            "current_stage": "compiling",
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
