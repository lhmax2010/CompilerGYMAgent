from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent import (
    ProcessRecord,
    StateConsistencyReport,
    append_trace_event,
    compute_cmdline_hash,
    inspect_state_consistency,
    mark_process_exited,
    mark_process_killed,
    process_lease_path,
    register_process_lease,
    write_checkpoint_state,
)
from tests.fixtures.fake_workspace import create_fake_workspace


SESSION_ID = "sess_state_consistency"
TRIAL_ID = "trial_1"


def test_state_consistency_reports_healthy_checkpoint_trace_and_lease(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    append_trial_trace(fake.layout, trial_id=TRIAL_ID)
    lease = register_process_lease(
        fake.layout,
        record=record(pid=1234),
        trial_id=TRIAL_ID,
        role="compile",
        now=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
    )
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(
            fake.layout,
            trace_line_count=2,
            current_trial=running_trial(
                process_refs=[lease_ref(fake.layout, lease)],
            ),
        ),
    )

    report = inspect_state_consistency(fake.layout)

    assert isinstance(report, StateConsistencyReport)
    assert report.ok is True
    assert report.trace_alignment is not None
    assert report.trace_alignment.status == "aligned"
    assert tuple(span.session_id for span in report.session_spans) == (SESSION_ID,)
    assert tuple(lease.status for lease in report.process_leases) == ("running",)


def test_state_consistency_reports_trace_alignment_issues(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    append_trial_trace(fake.layout, trial_id=TRIAL_ID)

    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(fake.layout, trace_line_count=1, current_trial=None),
    )
    trace_ahead = inspect_state_consistency(fake.layout)
    assert issue_codes(trace_ahead) == ("trace_ahead",)
    assert trace_ahead.issues[0].severity == "warning"

    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(fake.layout, trace_line_count=3, current_trial=None),
    )
    checkpoint_ahead = inspect_state_consistency(fake.layout)
    assert "checkpoint_ahead" in issue_codes(checkpoint_ahead)
    assert checkpoint_ahead.has_errors is True


def test_state_consistency_reports_missing_process_ref(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    append_trial_trace(fake.layout, trial_id=TRIAL_ID)
    missing_ref = f"state/processes/{SESSION_ID}/{TRIAL_ID}/compile-404.yaml"
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(
            fake.layout,
            trace_line_count=2,
            current_trial=running_trial(process_refs=[missing_ref]),
        ),
    )

    report = inspect_state_consistency(fake.layout)

    assert "process_ref_missing" in issue_codes(report)
    issue = only_issue(report, "process_ref_missing")
    assert issue.severity == "error"
    assert issue.details["process_ref"] == missing_ref


def test_state_consistency_reports_operation_and_lease_status_mismatch(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    append_trial_trace(fake.layout, trial_id=TRIAL_ID)
    lease = register_process_lease(
        fake.layout,
        record=record(pid=2345),
        trial_id=TRIAL_ID,
        role="compile",
    )
    killed = mark_process_killed(fake.layout, lease, signal=9)
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(
            fake.layout,
            trace_line_count=2,
            current_trial=running_trial(
                process_refs=[lease_ref(fake.layout, killed)],
            ),
        ),
    )

    report = inspect_state_consistency(fake.layout)

    issue = only_issue(report, "running_operation_terminal_lease")
    assert issue.severity == "warning"
    assert issue.details["lease_status"] == "killed"


def test_state_consistency_reports_orphan_process_leases(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    running = register_process_lease(
        fake.layout,
        record=record(pid=3456),
        trial_id="trial_orphan_running",
        role="compile",
    )
    exited = mark_process_exited(
        fake.layout,
        register_process_lease(
            fake.layout,
            record=record(pid=3457),
            trial_id="trial_orphan_exited",
            role="benchmark",
        ),
        exit_code=0,
        now=datetime.now(UTC) + timedelta(seconds=1),
    )
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(fake.layout, trace_line_count=0, current_trial=None),
    )

    report = inspect_state_consistency(fake.layout)

    orphan_issues = tuple(
        issue for issue in report.issues if issue.code == "orphan_process_lease"
    )
    assert len(orphan_issues) == 2
    severities = {issue.details["process_ref"]: issue.severity for issue in orphan_issues}
    assert severities[lease_ref(fake.layout, running)] == "warning"
    assert severities[lease_ref(fake.layout, exited)] == "info"


def test_state_consistency_reports_current_trial_trace_mismatch(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    append_trial_trace(fake.layout, trial_id="other_trial")
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(
            fake.layout,
            trace_line_count=2,
            current_trial=idle_trial(trial_id=TRIAL_ID, current_trial_start_line=2),
        ),
    )

    report = inspect_state_consistency(fake.layout)

    issue = only_issue(report, "current_trial_start_line_mismatch")
    assert issue.severity == "error"
    assert issue.details["expected_trial_id"] == TRIAL_ID
    assert issue.details["actual_trial_id"] == "other_trial"


def test_state_consistency_reports_invalid_process_lease(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    bad_path = (
        fake.layout.state_dir
        / "processes"
        / SESSION_ID
        / TRIAL_ID
        / "compile-999.yaml"
    )
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("a: &a 1\nb: *a\n", encoding="utf-8")
    write_checkpoint_state(
        fake.layout,
        checkpoint_payload(fake.layout, trace_line_count=0, current_trial=None),
    )

    report = inspect_state_consistency(fake.layout)

    issue = only_issue(report, "process_lease_invalid")
    assert issue.severity == "error"
    assert "aliases" in issue.message


def append_trial_trace(layout, *, trial_id: str) -> None:
    append_trace_event(
        layout,
        {
            "ts": "2026-06-01T08:00:00Z",
            "kind": "round_start",
            "session_id": SESSION_ID,
            "namespace": str(layout.namespace),
        },
        expected_line_number=1,
    )
    append_trace_event(
        layout,
        {
            "ts": "2026-06-01T08:00:01Z",
            "kind": "trial_start",
            "session_id": SESSION_ID,
            "namespace": str(layout.namespace),
            "trial_id": trial_id,
            "combo": ["-O3"],
            "mode": "exploit",
            "candidate_source": "llm_proposal",
        },
        expected_line_number=2,
    )


def checkpoint_payload(layout, *, trace_line_count: int, current_trial):
    return {
        "session_id": SESSION_ID,
        "namespace": str(layout.namespace),
        "last_completed_trial": None,
        "current_trial": current_trial,
        "current_best": None,
        "explorer_state": {},
        "random_seed": 42,
        "total_tokens_consumed": 0,
        "trace_line_count": trace_line_count,
        "last_updated": "2026-06-01T08:00:00Z",
    }


def running_trial(*, process_refs: list[str]) -> dict:
    return {
        **idle_trial(trial_id=TRIAL_ID, current_trial_start_line=2),
        "current_stage": "compiling",
        "process": {
            "pid": 1234,
            "pgid": 1234,
            "create_time": 1730000000.0,
            "cmdline_hash": "sha256:" + ("d" * 64),
            "session_marker": f"AGENT_SESSION_ID={SESSION_ID}",
        },
        "operations": [
            {
                "op": "compile",
                "status": "running",
                "process_refs": process_refs,
                "details": {"attempt": 1},
            }
        ],
    }


def idle_trial(*, trial_id: str, current_trial_start_line: int) -> dict:
    return {
        "trial_id": trial_id,
        "started_at": "2026-06-01T08:00:01Z",
        "current_stage": "spec_inject",
        "stage_started_at": "2026-06-01T08:00:02Z",
        "spec_backup_path": "spec_backups/pre_trial.spec.bak",
        "workspace_snapshot_pre": "workspace_snapshots/pre.yaml",
        "build_dir": "build_dirs/trial_1",
        "artifact_staging": "artifacts/staging/trial_1",
        "current_trial_start_line": current_trial_start_line,
        "operations": [],
    }


def record(*, pid: int) -> ProcessRecord:
    return ProcessRecord(
        pid=pid,
        pgid=pid,
        create_time=1730000000.0 + pid,
        session_id=SESSION_ID,
        cmdline_hash=compute_cmdline_hash(["python", str(pid)]),
        env_marker_visible_at_spawn=True,
        cgroup_path=None,
    )


def lease_ref(layout, lease) -> str:
    path = process_lease_path(
        layout,
        session_id=lease.session_id,
        trial_id=lease.trial_id,
        role=lease.role,
        pid=lease.record.pid,
    )
    return path.relative_to(layout.namespace_dir).as_posix()


def issue_codes(report: StateConsistencyReport) -> tuple[str, ...]:
    return tuple(issue.code for issue in report.issues)


def only_issue(report: StateConsistencyReport, code: str):
    matches = [issue for issue in report.issues if issue.code == code]
    assert len(matches) == 1
    return matches[0]
