from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

import pytest

from agent.fs_memory import (
    NamespaceLayout,
    append_trace_event,
    load_trace_events,
    trace_event_payload,
    write_checkpoint_state,
)
from agent.registry import ProjectNamespace
import agent.trace_cleanup as trace_cleanup
from agent.trace_cleanup import (
    ByteRange,
    CleanExecutionRefusedError,
    CleanPlan,
    StaleCleanPlanError,
    compute_clean_plan,
    execute_clean_plan,
)
from agent.workspace_lock import WorkspaceBusyError, WorkspaceLock


def namespace() -> ProjectNamespace:
    return ProjectNamespace(
        module="multimedia",
        framework="ffmpeg",
        compiler="gcc-13.2.0",
        code_commit="code-a1b2c3d",
        kg_version="kg-v3",
    )


def layout(tmp_path: Path) -> NamespaceLayout:
    return NamespaceLayout(workspace=tmp_path, namespace=namespace())


def append_event(
    current_layout: NamespaceLayout,
    line_number: int,
    *,
    ts: str,
    session_id: str | None = None,
) -> None:
    payload = {"ts": ts, "kind": "probe"}
    if session_id is not None:
        payload["session_id"] = session_id
    append_trace_event(
        current_layout,
        payload,
        expected_line_number=line_number,
    )


def old_recent_trace(current_layout: NamespaceLayout) -> None:
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    append_event(
        current_layout,
        2,
        ts="2026-05-09T00:00:00Z",
        session_id="sess_recent",
    )
    append_event(
        current_layout,
        3,
        ts="2026-04-01T00:02:00Z",
        session_id="sess_old_2",
    )


def checkpoint_data(current_layout: NamespaceLayout, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "session_id": "sess_checkpoint",
        "namespace": str(current_layout.namespace),
        "last_completed_trial": None,
        "current_trial": None,
        "current_best": None,
        "explorer_state": {},
        "random_seed": 42,
        "total_tokens_consumed": 0,
        "trace_line_count": 0,
        "last_updated": "2026-05-10T12:00:00Z",
    }
    data.update(overrides)
    return data


def fixed_now() -> datetime:
    return datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


def payloads(path: Path) -> list[dict]:
    return [trace_event_payload(event) for event in load_trace_events(path)]


def test_execute_refuses_before_reading_trace_or_acquiring_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    plan = CleanPlan(
        trace_path=current_layout.trace_path,
        total_lines=1,
        file_size_bytes=100,
        protected_session_ids=frozenset(),
        protected_line_ranges=(),
        post_checkpoint_boundary_line=None,
        lock_status="free",
        blocking_lock_holder=None,
        keep_days=7,
        cutoff_ts=fixed_now(),
        removable_line_ranges=(),
        removable_byte_ranges=(ByteRange(0, 10),),
        removable_event_count=1,
        refusal_reason="blocked by test",
    )

    def fail_if_lock_created(workspace: Path) -> WorkspaceLock:
        raise AssertionError(f"unexpected lock acquisition for {workspace}")

    monkeypatch.setattr("agent.trace_cleanup.WorkspaceLock", fail_if_lock_created)

    with pytest.raises(CleanExecutionRefusedError, match="blocked by test"):
        execute_clean_plan(current_layout, plan)


def test_execute_detects_stale_plan_after_lock_acquisition(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    append_event(
        current_layout,
        4,
        ts="2026-04-01T00:03:00Z",
        session_id="sess_late",
    )

    with pytest.raises(StaleCleanPlanError, match="stale"):
        execute_clean_plan(current_layout, plan, backup=False)


def test_execute_detects_checkpoint_changed_after_planning(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    write_checkpoint_state(
        current_layout,
        checkpoint_data(current_layout, trace_line_count=3),
    )

    with pytest.raises(StaleCleanPlanError, match="checkpoint changed"):
        execute_clean_plan(current_layout, plan, backup=False)


def test_execute_detects_protected_session_boundaries_changed_without_size_change(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_a")
    append_event(current_layout, 2, ts="2026-04-01T00:01:00Z", session_id="sess_b")
    write_checkpoint_state(
        current_layout,
        checkpoint_data(
            current_layout,
            session_id="sess_a",
            trace_line_count=2,
        ),
    )
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    original_size = current_layout.trace_path.stat().st_size
    current_layout.trace_path.write_text(
        current_layout.trace_path.read_text(encoding="utf-8").replace(
            '"sess_a"',
            '"sess_c"',
        ),
        encoding="utf-8",
    )
    assert current_layout.trace_path.stat().st_size == original_size

    with pytest.raises(StaleCleanPlanError, match="protected session"):
        execute_clean_plan(current_layout, plan, backup=False)


def test_execute_rewrites_trace_from_real_plan_and_writes_backup(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    original_payloads = payloads(current_layout.trace_path)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    result = execute_clean_plan(current_layout, plan, now=fixed_now())

    assert result.removed_event_count == 2
    assert result.bytes_freed == sum(
        byte_range.end - byte_range.start for byte_range in plan.removable_byte_ranges
    )
    assert result.backup_path == (
        tmp_path / "_trash" / "20260510T120000Z" / "events.jsonl"
    )
    assert result.backup_path is not None
    assert payloads(result.backup_path) == original_payloads
    assert [payload["session_id"] for payload in payloads(current_layout.trace_path)] == [
        "sess_recent"
    ]


def test_execute_no_backup_skips_trash(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    result = execute_clean_plan(
        current_layout,
        plan,
        backup=False,
        now=fixed_now(),
    )

    assert result.backup_path is None
    assert not (tmp_path / "_trash").exists()
    assert len(load_trace_events(current_layout.trace_path)) == 1


def test_execute_force_inactive_only_uses_plan_predicate(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    held_by_self_plan = replace(plan, lock_status="held_by_self")

    with pytest.raises(CleanExecutionRefusedError):
        execute_clean_plan(current_layout, held_by_self_plan, backup=False)

    result = execute_clean_plan(
        current_layout,
        held_by_self_plan,
        force_inactive_only=True,
        backup=False,
    )

    assert result.removed_event_count == 2


def test_execute_force_inactive_only_runs_under_existing_self_lock(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)

    with WorkspaceLock(current_layout.workspace).acquire("agent run", "sess_active"):
        plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

        assert plan.lock_status == "held_by_self"
        assert plan.can_execute is False
        assert plan.can_execute_with_force_inactive_only is True

        result = execute_clean_plan(
            current_layout,
            plan,
            force_inactive_only=True,
            backup=False,
        )

    assert result.removed_event_count == 2
    assert [payload["session_id"] for payload in payloads(current_layout.trace_path)] == [
        "sess_recent"
    ]


def test_execute_crash_before_replace_leaves_original_trace_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    original = current_layout.trace_path.read_bytes()
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    def fail_before_replace(source: Path, target: Path) -> None:
        del source, target
        raise RuntimeError("boom before replace")

    monkeypatch.setattr("agent.trace_cleanup._replace_file", fail_before_replace)

    with pytest.raises(RuntimeError, match="boom before replace"):
        execute_clean_plan(current_layout, plan, backup=False)

    assert current_layout.trace_path.read_bytes() == original
    assert len(load_trace_events(current_layout.trace_path)) == 3


def test_execute_crash_after_replace_leaves_complete_new_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    def replace_then_fail(source: Path, target: Path) -> None:
        os.replace(source, target)
        raise RuntimeError("boom after replace")

    monkeypatch.setattr("agent.trace_cleanup._replace_file", replace_then_fail)

    with pytest.raises(RuntimeError, match="boom after replace"):
        execute_clean_plan(current_layout, plan, backup=False)

    assert [payload["session_id"] for payload in payloads(current_layout.trace_path)] == [
        "sess_recent"
    ]


def test_execute_holds_workspace_lock_during_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    old_recent_trace(current_layout)
    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    original_rewrite = trace_cleanup._rewrite_trace_file

    def assert_lock_held_during_rewrite(active_plan: CleanPlan) -> None:
        with pytest.raises(WorkspaceBusyError):
            WorkspaceLock(current_layout.workspace).acquire(
                "agent run",
                "sess_competing",
            )
        original_rewrite(active_plan)

    monkeypatch.setattr(
        "agent.trace_cleanup._rewrite_trace_file",
        assert_lock_held_during_rewrite,
    )

    result = execute_clean_plan(current_layout, plan, backup=False)

    assert result.removed_event_count == 2
