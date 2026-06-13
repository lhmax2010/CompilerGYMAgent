from __future__ import annotations

import multiprocessing as mp
import os
import sys
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

import psutil
import pytest
import yaml

from agent.fs_memory import (
    NamespaceLayout,
    append_trace_event,
    iter_trace_events,
    load_trace_events,
    trace_event_payload,
    write_checkpoint_state,
)
from agent.registry import ProjectNamespace
from agent.trace_cleanup import (
    ByteRange,
    LineRange,
    TraceCleanupError,
    compute_clean_plan,
)
from agent.workspace_lock import WorkspaceLock, WorkspaceLockHolder


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


def checkpoint_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "session_id": "sess_checkpoint",
        "namespace": str(namespace()),
        "last_completed_trial": None,
        "current_trial": None,
        "current_best": None,
        "explorer_state": {},
        "random_seed": 42,
        "total_tokens_consumed": 100,
        "last_updated": "2026-04-30T10:30:22Z",
    }
    data.update(overrides)
    return data


def append_event(
    current_layout: NamespaceLayout,
    line_number: int,
    *,
    ts: str,
    session_id: str | None = None,
    kind: str = "probe",
) -> None:
    payload = {"ts": ts, "kind": kind}
    if session_id is not None:
        payload["session_id"] = session_id
    append_trace_event(
        current_layout,
        payload,
        expected_line_number=line_number,
    )


def write_checkpoint(
    current_layout: NamespaceLayout,
    *,
    session_id: str = "sess_checkpoint",
    trace_line_count: int | None = None,
    current_trial: dict[str, object] | None = None,
) -> None:
    payload = checkpoint_data(session_id=session_id, current_trial=current_trial)
    if trace_line_count is not None:
        payload["trace_line_count"] = trace_line_count
    write_checkpoint_state(current_layout, payload)


def current_trial_data(
    *,
    trial_id: str = "trial_active",
    start_line: int = 2,
) -> dict[str, object]:
    return {
        "trial_id": trial_id,
        "started_at": "2026-04-30T10:18:00Z",
        "current_stage": "spec_inject",
        "stage_started_at": "2026-04-30T10:19:00Z",
        "spec_backup_path": "spec_backups/pre_trial.spec.bak",
        "workspace_snapshot_pre": "workspace_snapshots/pre.yaml",
        "build_dir": "build_dirs/trial_active",
        "artifact_staging": "artifacts/staging/trial_active",
        "current_trial_start_line": start_line,
        "operations": [
            {
                "op": "spec_inject",
                "status": "running",
                "details": {"attempt": 1},
            }
        ],
    }


def write_lock_holder(
    workspace: Path,
    *,
    session_id: str,
    pid: int,
    create_time: float,
) -> None:
    holder = WorkspaceLockHolder(
        pid=pid,
        pgid=pid,
        create_time=create_time,
        session_id=session_id,
        command="agent run",
        started_at="2026-05-29T00:00:00+00:00",
        hostname="dev-host",
        agent_version="0.1.test",
    )
    lock_path = workspace / "state" / "run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        yaml.safe_dump(holder.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def hold_workspace_lock(
    workspace: str,
    session_id: str,
    ready: mp.Event,
    release_now: mp.Event,
    result_queue: mp.Queue,
) -> None:
    lock: WorkspaceLock | None = None
    try:
        lock = WorkspaceLock(Path(workspace)).acquire("agent run", session_id)
        ready.set()
        release_now.wait(5)
        result_queue.put("released")
    except Exception as exc:  # pragma: no cover - surfaced in parent assertion.
        result_queue.put(f"error:{type(exc).__name__}:{exc}")
    finally:
        if lock is not None:
            lock.release()


def start_lock_holder_process(
    workspace: Path,
    session_id: str,
) -> tuple[mp.Process, mp.Event, mp.Queue]:
    ready = mp.Event()
    release_now = mp.Event()
    result_queue: mp.Queue = mp.Queue()
    process = mp.Process(
        target=hold_workspace_lock,
        args=(str(workspace), session_id, ready, release_now, result_queue),
    )
    process.start()
    if not ready.wait(5):
        process.join(1)
        detail = "no child result"
        if not result_queue.empty():
            detail = str(result_queue.get_nowait())
        if process.is_alive():
            process.terminate()
            process.join(5)
        pytest.fail(f"lock holder process did not become ready: {detail}")
    return process, release_now, result_queue


def stop_lock_holder_process(
    process: mp.Process,
    release_now: mp.Event,
    result_queue: mp.Queue,
) -> None:
    release_now.set()
    process.join(5)
    if process.is_alive():
        process.terminate()
        process.join(5)
    assert process.exitcode == 0
    assert result_queue.get(timeout=1) == "released"


def fixed_now() -> datetime:
    return datetime(2026, 5, 10, tzinfo=UTC)


def test_compute_clean_plan_protects_checkpoint_session_span_layer_one(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    append_event(
        current_layout,
        2,
        ts="2026-04-01T00:01:00Z",
        session_id="sess_checkpoint",
    )
    append_event(current_layout, 3, ts="2026-04-01T00:02:00Z", session_id="sess_mid")
    append_event(
        current_layout,
        4,
        ts="2026-04-01T00:03:00Z",
        session_id="sess_checkpoint",
    )
    write_checkpoint(current_layout, trace_line_count=4)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.protected_session_ids == frozenset({"sess_checkpoint"})
    assert plan.protected_line_ranges == (LineRange(2, 4),)
    assert plan.checkpoint_hash is not None
    assert plan.checkpoint_hash.startswith("sha256:")
    assert plan.protected_sessions_hash is not None
    assert plan.protected_sessions_hash.startswith("sha256:")
    assert plan.removable_line_ranges == (LineRange(1, 1),)
    assert plan.removable_event_count == 1
    assert plan.can_execute is True


def test_compute_clean_plan_protects_current_trial_layer_d(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    append_event(current_layout, 2, ts="2026-04-01T00:01:00Z", session_id="sess_mid")
    append_event(current_layout, 3, ts="2026-04-01T00:02:00Z", session_id="sess_mid")
    append_event(current_layout, 4, ts="2026-04-01T00:03:00Z", session_id="sess_tail")
    write_checkpoint(
        current_layout,
        trace_line_count=3,
        current_trial=current_trial_data(start_line=2),
    )

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.current_trial_protected_line_range == LineRange(2, 4)
    assert plan.protected_line_ranges == (LineRange(2, 4),)
    assert plan.removable_line_ranges == (LineRange(1, 1),)
    assert plan.removable_event_count == 1


def test_compute_clean_plan_refuses_current_trial_start_line_ahead(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    write_checkpoint(
        current_layout,
        trace_line_count=1,
        current_trial=current_trial_data(start_line=2),
    )

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.current_trial_protected_line_range is None
    assert "current_trial_start_line is ahead" in str(plan.refusal_reason)
    assert plan.can_execute is False


def test_compute_clean_plan_protects_post_checkpoint_lines_layer_two(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    for index in range(1, 5):
        append_event(
            current_layout,
            index,
            ts=f"2026-04-01T00:0{index}:00Z",
            session_id=f"sess_old_{index}",
        )
    write_checkpoint(current_layout, session_id="sess_checkpoint", trace_line_count=2)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.post_checkpoint_boundary_line == 2
    assert plan.protected_line_ranges == ()
    assert plan.removable_line_ranges == (LineRange(1, 2),)
    assert plan.removable_event_count == 2


def test_compute_clean_plan_refuses_legacy_checkpoint_missing_trace_line_count(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    for index in range(1, 6):
        append_event(
            current_layout,
            index,
            ts=f"2026-04-01T00:0{index}:00Z",
            session_id=f"sess_old_{index}",
        )
    write_checkpoint(current_layout, session_id="sess_checkpoint")

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.post_checkpoint_boundary_line is None
    assert "lacks trace_line_count" in str(plan.refusal_reason)
    assert plan.removable_event_count == 5
    assert plan.can_execute is False
    assert plan.can_execute_with_force_inactive_only is False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux fcntl")
def test_compute_clean_plan_reports_held_by_other_without_hiding_removable_lines(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    process, release_now, result_queue = start_lock_holder_process(
        tmp_path,
        "sess_active_elsewhere",
    )
    try:
        plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

        assert plan.lock_status == "held_by_other"
        assert plan.blocking_lock_holder is not None
        assert plan.blocking_lock_holder.session_id == "sess_active_elsewhere"
        assert plan.refusal_reason == "workspace lock is held by another agent process"
        assert plan.removable_line_ranges == (LineRange(1, 1),)
        assert plan.can_execute is False
        assert plan.can_execute_with_force_inactive_only is False
    finally:
        stop_lock_holder_process(process, release_now, result_queue)


def test_compute_clean_plan_released_but_live_holder_metadata_is_free(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    current_process = psutil.Process()
    write_lock_holder(
        tmp_path,
        session_id="sess_released_but_live",
        pid=os.getpid(),
        create_time=current_process.create_time(),
    )

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.lock_status == "free"
    assert plan.blocking_lock_holder is None
    assert plan.refusal_reason is None
    assert plan.can_execute is True


@pytest.mark.parametrize(
    ("raw_holder", "expected_error"),
    [
        ("", "lock file is empty"),
        ("not: [valid\n", "failed to parse YAML"),
        ("x" * 65_537, "too large"),
        ("pid: 1234\npgid: 0\ncreate_time: 1", "invalid lock holder"),
    ],
)
def test_compute_clean_plan_bad_lock_metadata_returns_graceful_refusal(
    tmp_path: Path,
    raw_holder: str,
    expected_error: str,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    lock_path = tmp_path / "state" / "run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(raw_holder, encoding="utf-8")

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.lock_status == "unknown"
    assert plan.blocking_lock_holder is None
    assert "workspace lock metadata could not be read" in str(plan.refusal_reason)
    assert expected_error in str(plan.refusal_reason)
    assert plan.removable_line_ranges == (LineRange(1, 1),)
    assert plan.can_execute is False
    assert plan.can_execute_with_force_inactive_only is False


def test_compute_clean_plan_merges_layer_one_and_two_overlap(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")
    append_event(
        current_layout,
        2,
        ts="2026-04-01T00:01:00Z",
        session_id="sess_checkpoint",
    )
    append_event(
        current_layout,
        3,
        ts="2026-04-01T00:02:00Z",
        session_id="sess_checkpoint",
    )
    append_event(current_layout, 4, ts="2026-04-01T00:03:00Z", session_id="sess_other")
    write_checkpoint(current_layout, trace_line_count=2)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.protected_line_ranges == (LineRange(2, 3),)
    assert plan.post_checkpoint_boundary_line == 2
    assert plan.removable_line_ranges == (LineRange(1, 1),)
    assert plan.removable_event_count == 1


def test_compute_clean_plan_can_remove_all_when_no_protection_and_old(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    for index in range(1, 4):
        append_event(
            current_layout,
            index,
            ts=f"2026-04-01T00:0{index}:00Z",
            session_id=f"sess_old_{index}",
        )

    plan = compute_clean_plan(current_layout, keep_days=0, now=fixed_now())

    assert plan.protected_session_ids == frozenset()
    assert plan.protected_line_ranges == ()
    assert plan.post_checkpoint_boundary_line is None
    assert plan.removable_line_ranges == (LineRange(1, 3),)
    assert plan.removable_byte_ranges == (
        ByteRange(0, current_layout.trace_path.stat().st_size),
    )
    assert plan.can_execute is True


def test_compute_clean_plan_all_layers_trigger_without_removable_events(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_active")
    append_event(
        current_layout,
        2,
        ts="2026-04-01T00:01:00Z",
        session_id="sess_checkpoint",
    )
    append_event(current_layout, 3, ts="2026-04-01T00:02:00Z", session_id="sess_other")
    append_event(current_layout, 4, ts="2026-05-09T00:00:00Z", session_id="sess_recent")
    write_checkpoint(current_layout, trace_line_count=2)

    with WorkspaceLock(current_layout.workspace).acquire("agent run", "sess_active"):
        plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.lock_status == "held_by_self"
    assert plan.protected_session_ids == frozenset({"sess_active", "sess_checkpoint"})
    assert plan.protected_line_ranges == (LineRange(1, 2),)
    assert plan.removable_line_ranges == ()
    assert plan.removable_event_count == 0
    assert plan.can_execute is False


def test_compute_clean_plan_time_cutoff_splits_old_and_recent_events(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-05-02T23:59:59Z", session_id="sess_old")
    append_event(current_layout, 2, ts="2026-05-03T00:00:00Z", session_id="sess_edge")
    append_event(current_layout, 3, ts="2026-05-04T00:00:00Z", session_id="sess_new")

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.cutoff_ts == datetime(2026, 5, 3, tzinfo=UTC)
    assert plan.removable_line_ranges == (LineRange(1, 1),)
    assert plan.removable_event_count == 1


def test_compute_clean_plan_large_keep_days_keeps_everything(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")

    plan = compute_clean_plan(current_layout, keep_days=10_000, now=fixed_now())

    assert plan.removable_line_ranges == ()
    assert plan.can_execute is False


def test_compute_clean_plan_lock_status_execute_matrix(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path / "free")
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z")
    free_plan = compute_clean_plan(current_layout, keep_days=0, now=fixed_now())

    self_layout = layout(tmp_path / "self")
    append_event(self_layout, 1, ts="2026-04-01T00:00:00Z")
    with WorkspaceLock(self_layout.workspace).acquire("agent run", "sess_self"):
        self_plan = compute_clean_plan(self_layout, keep_days=0, now=fixed_now())

    other_layout = layout(tmp_path / "other")
    append_event(other_layout, 1, ts="2026-04-01T00:00:00Z")
    process, release_now, result_queue = start_lock_holder_process(
        other_layout.workspace,
        "sess_other",
    )
    try:
        other_plan = compute_clean_plan(other_layout, keep_days=0, now=fixed_now())
    finally:
        stop_lock_holder_process(process, release_now, result_queue)

    assert (free_plan.lock_status, free_plan.can_execute) == ("free", True)
    assert free_plan.can_execute_with_force_inactive_only is True
    assert (self_plan.lock_status, self_plan.can_execute) == ("held_by_self", False)
    assert self_plan.can_execute_with_force_inactive_only is True
    assert (other_plan.lock_status, other_plan.can_execute) == ("held_by_other", False)
    assert other_plan.can_execute_with_force_inactive_only is False


def test_compute_clean_plan_empty_trace_and_missing_checkpoint(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.total_lines == 0
    assert plan.file_size_bytes == 0
    assert plan.post_checkpoint_boundary_line is None
    assert plan.removable_line_ranges == ()
    assert plan.removable_byte_ranges == ()
    assert plan.is_dry_run_safe is True


def test_compute_clean_plan_single_session_across_file_is_protected(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    for index in range(1, 4):
        append_event(
            current_layout,
            index,
            ts=f"2026-04-01T00:0{index}:00Z",
            session_id="sess_checkpoint",
        )
    write_checkpoint(current_layout, trace_line_count=3)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.protected_line_ranges == (LineRange(1, 3),)
    assert plan.removable_line_ranges == ()


def test_compute_clean_plan_byte_ranges_round_trip(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old_a")
    append_event(current_layout, 2, ts="2026-05-05T00:00:00Z", session_id="sess_recent")
    append_event(current_layout, 3, ts="2026-04-01T00:02:00Z", session_id="sess_old_b")
    append_event(current_layout, 4, ts="2026-05-06T00:00:00Z", session_id="sess_recent")

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())
    raw_trace = current_layout.trace_path.read_bytes()
    rewritten = _bytes_without_ranges(raw_trace, plan.removable_byte_ranges)
    rewritten_path = tmp_path / "rewritten-events.jsonl"
    rewritten_path.write_bytes(rewritten)

    loaded = load_trace_events(rewritten_path)

    assert plan.removable_line_ranges == (LineRange(1, 1), LineRange(3, 3))
    assert len(loaded) == plan.total_lines - plan.removable_event_count
    assert [trace_event_payload(event)["session_id"] for event in loaded] == [
        "sess_recent",
        "sess_recent",
    ]


def test_compute_clean_plan_rejects_trace_changed_between_validation_and_byte_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_old")

    def mutate_after_validation(path: str | Path):
        yield from iter_trace_events(path)
        Path(path).open("ab").write(
            b'{"ts":"2026-04-01T00:01:00Z","kind":"probe"}\n'
        )

    monkeypatch.setattr(
        "agent.trace_cleanup.iter_trace_events",
        mutate_after_validation,
    )

    with pytest.raises(TraceCleanupError, match="trace changed"):
        compute_clean_plan(current_layout, keep_days=7, now=fixed_now())


def test_compute_clean_plan_non_contiguous_session_span_over_preserves_middle_events(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_event(current_layout, 1, ts="2026-04-01T00:00:00Z", session_id="sess_a")
    append_event(current_layout, 2, ts="2026-04-01T00:01:00Z", session_id="sess_b")
    append_event(current_layout, 3, ts="2026-04-01T00:02:00Z", session_id="sess_a")
    append_event(current_layout, 4, ts="2026-04-01T00:03:00Z", session_id="sess_b")
    append_event(current_layout, 5, ts="2026-04-01T00:04:00Z", session_id="sess_a")
    write_checkpoint(current_layout, session_id="sess_a", trace_line_count=5)

    plan = compute_clean_plan(current_layout, keep_days=7, now=fixed_now())

    assert plan.protected_session_ids == frozenset({"sess_a"})
    assert plan.protected_line_ranges == (LineRange(1, 5),)
    assert plan.removable_line_ranges == ()


def test_compute_clean_plan_rejects_invalid_time_inputs(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)

    with pytest.raises(TraceCleanupError, match="keep_days"):
        compute_clean_plan(current_layout, keep_days=-1, now=fixed_now())
    with pytest.raises(TraceCleanupError, match="timezone-aware"):
        compute_clean_plan(current_layout, keep_days=7, now=datetime(2026, 5, 10))


def _bytes_without_ranges(raw: bytes, ranges: tuple[ByteRange, ...]) -> bytes:
    chunks: list[bytes] = []
    cursor = 0
    for item in ranges:
        chunks.append(raw[cursor : item.start])
        cursor = item.end
    chunks.append(raw[cursor:])
    return b"".join(chunks)
