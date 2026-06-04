from __future__ import annotations

import os
import signal
import sys
import time

import psutil
import pytest

from agent import (
    OWNED_SCORE_THRESHOLD,
    SUSPECTED_SCORE_THRESHOLD,
    ProcessRecord,
    attribute_process,
    cleanup_process_lease,
    find_cleanup_targets,
    garbage_collect_process_leases,
    load_process_leases,
    mark_process_exited,
    read_env_marker,
    register_process_lease,
    spawn_process,
)
from tests.fixtures.fake_workspace import create_fake_workspace
from tests.fixtures.process_lab import create_process_lab


pytestmark = pytest.mark.skipif(os.name != "posix", reason="process cleaner is POSIX-only")


def test_read_env_marker_is_single_read_without_retry() -> None:
    class FakeProc:
        pid = 123

        def __init__(self) -> None:
            self.calls = 0

        def environ(self) -> dict[str, str]:
            self.calls += 1
            return {
                "AGENT_SESSION_ID": "sess_marker",
                "AGENT_TRIAL_ID": "trial_marker",
                "AGENT_LEASE_ID": "compile-marker",
                "AGENT_PROCESS_ROLE": "compile",
            }

    proc = FakeProc()

    marker = read_env_marker(proc)  # type: ignore[arg-type]

    assert marker.value == "sess_marker"
    assert marker.status == "matched"
    assert marker.session_id == "sess_marker"
    assert marker.trial_id == "trial_marker"
    assert marker.lease_id == "compile-marker"
    assert marker.process_role == "compile"
    assert proc.calls == 1


def test_read_env_marker_reports_missing_without_retry() -> None:
    class FakeProc:
        pid = 123

        def __init__(self) -> None:
            self.calls = 0

        def environ(self) -> dict[str, str]:
            self.calls += 1
            return {}

    proc = FakeProc()

    marker = read_env_marker(proc)  # type: ignore[arg-type]

    assert marker.value is None
    assert marker.status == "missing"
    assert proc.calls == 1


def test_read_env_marker_handles_access_denied_without_retry() -> None:
    class FakeProc:
        pid = 123

        def __init__(self) -> None:
            self.calls = 0

        def environ(self) -> dict[str, str]:
            self.calls += 1
            raise psutil.AccessDenied(pid=self.pid)

    proc = FakeProc()

    marker = read_env_marker(proc)  # type: ignore[arg-type]

    assert marker.value is None
    assert marker.status == "unavailable"
    assert proc.calls == 1


def test_attribute_process_scores_owned_and_suspected(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        owned = lab.spawn_live(session_id="sess_clean_owned")
        owned_attr = attribute_process(psutil.Process(owned.pid), owned.record)

        assert owned_attr.score >= OWNED_SCORE_THRESHOLD
        assert owned_attr.verdict == "owned"
        assert owned_attr.pid_create_time_match is True
        assert owned_attr.pgid_match is True
        assert owned_attr.env_marker_match is True

        no_marker = lab.spawn_live(
            session_id="sess_clean_nomarker",
            include_env_marker=False,
        )
        suspected_attr = attribute_process(
            psutil.Process(no_marker.pid),
            no_marker.record,
        )

        assert suspected_attr.score == 6
        assert suspected_attr.score >= SUSPECTED_SCORE_THRESHOLD
        assert suspected_attr.verdict == "suspected"
        assert suspected_attr.env_marker_status == "missing"
    finally:
        lab.cleanup()


def test_cleanup_kills_owned_process_group_and_marks_lease(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_live(session_id="sess_clean_kill")
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_kill",
            role="compile",
        )

        result = cleanup_process_lease(fake.layout, lease)

        assert result.action == "killed"
        assert process.pgid in result.killed_pgids
        assert result.updated_lease is not None
        assert result.updated_lease.status == "killed"
        assert result.updated_lease.signal == signal.SIGTERM
        _wait_until(lambda: not _pid_alive(process.pid))
    finally:
        lab.cleanup()


def test_cleanup_mixed_targets_kills_only_owned_process_group(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        owned = lab.spawn_live(session_id="sess_clean_mixed")
        same_session_suspected = lab.spawn_live(session_id="sess_clean_mixed")
        lease = register_process_lease(
            fake.layout,
            record=owned.record,
            trial_id="trial_mixed",
            role="compile",
        )

        assert owned.record.trial_id is None
        assert owned.record.lease_id is None
        result = cleanup_process_lease(fake.layout, lease)

        by_pid = {target.pid: target for target in result.targets}
        assert by_pid[owned.pid].attribution.verdict == "owned"
        assert by_pid[same_session_suspected.pid].attribution.verdict == "suspected"
        assert result.action == "killed"
        assert owned.pgid in result.killed_pgids
        assert same_session_suspected.pgid not in result.killed_pgids
        _wait_until(lambda: not _pid_alive(owned.pid))
        assert _pid_alive(same_session_suspected.pid)
    finally:
        lab.cleanup()


def test_new_lease_env_scan_filters_same_session_to_lease_granularity(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    first = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_clean_precise",
        trial_id="trial_precise",
        role="compile",
    )
    second = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_clean_precise",
        trial_id="trial_precise",
        role="benchmark",
    )
    try:
        assert first.record.lease_id is not None
        assert second.record.lease_id is not None
        assert first.record.lease_id != second.record.lease_id

        targets = find_cleanup_targets(first.record)
        assert tuple(target.pid for target in targets) == (first.record.pid,)

        result = cleanup_process_lease(fake.layout, first.lease)

        assert result.action == "killed"
        assert first.record.pgid in result.killed_pgids
        assert second.record.pgid not in result.killed_pgids
        _wait_until(lambda: not _pid_alive(first.record.pid))
        assert _pid_alive(second.record.pid)
    finally:
        _terminate_spawned(second)
        _terminate_spawned(first)


def test_force_cleanup_mixed_targets_kills_owned_and_suspected(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        owned = lab.spawn_live(session_id="sess_clean_mixed_force")
        same_session_suspected = lab.spawn_live(session_id="sess_clean_mixed_force")
        lease = register_process_lease(
            fake.layout,
            record=owned.record,
            trial_id="trial_mixed_force",
            role="compile",
        )

        result = cleanup_process_lease(fake.layout, lease, force_suspected=True)

        by_pid = {target.pid: target for target in result.targets}
        assert by_pid[owned.pid].attribution.verdict == "owned"
        assert by_pid[same_session_suspected.pid].attribution.verdict == "suspected"
        assert result.action == "killed"
        assert owned.pgid in result.killed_pgids
        assert same_session_suspected.pgid in result.killed_pgids
        _wait_until(lambda: not _pid_alive(owned.pid))
        _wait_until(lambda: not _pid_alive(same_session_suspected.pid))
    finally:
        lab.cleanup()


def test_suspected_process_is_skipped_by_default_and_force_killed(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_live(
            session_id="sess_clean_suspected",
            include_env_marker=False,
        )
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_skip",
            role="compile",
        )

        skipped = cleanup_process_lease(fake.layout, lease)

        assert skipped.action == "unsafe_skip"
        assert skipped.updated_lease is not None
        assert skipped.updated_lease.status == "unsafe_skip"
        assert _pid_alive(process.pid)
    finally:
        lab.cleanup()

    lab_force = create_process_lab(tmp_path)
    try:
        process = lab_force.spawn_live(
            session_id="sess_clean_suspected_force",
            include_env_marker=False,
        )
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_force",
            role="compile",
        )

        killed = cleanup_process_lease(fake.layout, lease, force_suspected=True)

        assert killed.action == "killed"
        assert process.pgid in killed.killed_pgids
        _wait_until(lambda: not _pid_alive(process.pid))
    finally:
        lab_force.cleanup()


def test_leader_dead_children_alive_is_found_by_pgid_scan(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_leader_dead_children_alive(
            session_id="sess_clean_leader_dead"
        )
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_leader_dead",
            role="compile",
        )

        targets = find_cleanup_targets(process.record)
        result = cleanup_process_lease(fake.layout, lease)

        assert any(target.attribution.source == "pgid_scan+env_scan" for target in targets)
        assert result.action == "killed"
        assert process.pgid in result.killed_pgids
        assert process.child_pids
        _wait_until(lambda: not _pid_alive(process.child_pids[0]))
    finally:
        lab.cleanup()


def test_double_fork_escape_requires_env_marker_and_force(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_double_fork_escape(session_id="sess_clean_escape")
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_escape_skip",
            role="compile",
        )

        targets = find_cleanup_targets(process.record)
        skipped = cleanup_process_lease(fake.layout, lease)

        assert process.child_pids
        assert process.child_pgids[0] != process.pgid
        assert any(target.attribution.source == "env_scan" for target in targets)
        assert all(target.attribution.verdict == "suspected" for target in targets)
        assert skipped.action == "unsafe_skip"
        assert _pid_alive(process.child_pids[0])
    finally:
        lab.cleanup()

    lab_force = create_process_lab(tmp_path)
    try:
        process = lab_force.spawn_double_fork_escape(
            session_id="sess_clean_escape_force"
        )
        lease = register_process_lease(
            fake.layout,
            record=process.record,
            trial_id="trial_escape_force",
            role="compile",
        )

        killed = cleanup_process_lease(fake.layout, lease, force_suspected=True)

        assert killed.action == "killed"
        assert process.child_pgids[0] in killed.killed_pgids
        _wait_until(lambda: not _pid_alive(process.child_pids[0]))
    finally:
        lab_force.cleanup()


def test_garbage_collect_process_leases_deletes_only_orphans(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lab = create_process_lab(tmp_path)
    try:
        live = lab.spawn_live(session_id="sess_clean_gc_live")
        live_lease = register_process_lease(
            fake.layout,
            record=live.record,
            trial_id="trial_live",
            role="compile",
        )

        gone_record = lab.make_pid_gone_record()
        register_process_lease(
            fake.layout,
            record=gone_record,
            trial_id="trial_gone",
            role="compile",
        )

        terminal = mark_process_exited(
            fake.layout,
            register_process_lease(
                fake.layout,
                record=_dead_record(pid=999_991),
                trial_id="trial_terminal",
                role="compile",
            ),
            exit_code=0,
        )

        gc = garbage_collect_process_leases(fake.layout)

        assert any("trial_gone" in path for path in gc.deleted_paths)
        assert any("trial_terminal" in path for path in gc.deleted_paths)
        assert any("trial_live" in path for path in gc.kept_paths)
        remaining = load_process_leases(fake.layout)
        assert tuple(lease.trial_id for lease in remaining) == (live_lease.trial_id,)
        assert terminal.trial_id == "trial_terminal"
    finally:
        lab.cleanup()


def _dead_record(*, pid: int) -> ProcessRecord:
    return ProcessRecord(
        pid=pid,
        pgid=pid,
        create_time=1.0,
        session_id="sess_dead",
        cmdline_hash="sha256:" + "0" * 64,
        env_marker_visible_at_spawn=False,
    )


def _pid_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    try:
        return proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not become true before timeout")


def _terminate_spawned(result) -> None:
    if result.popen.poll() is not None:
        return
    try:
        os.killpg(result.record.pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if result.popen.poll() is not None:
            return
        time.sleep(0.02)
    try:
        os.killpg(result.record.pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        result.popen.wait(timeout=2)
    except Exception:
        return
