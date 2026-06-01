from __future__ import annotations

import os

import psutil
import pytest

from agent import ProcessRecord
from tests.fixtures.process_lab import create_process_lab


pytestmark = pytest.mark.skipif(os.name != "posix", reason="process_lab is POSIX-only")


def test_process_lab_spawns_live_process_group(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_live(session_id="sess_lab_live")

        assert process.pid == process.record.pid
        assert os.getpgid(process.pid) == process.pgid
        assert process.record.session_id == "sess_lab_live"
        assert process.record.env_marker_visible_at_spawn is True
        assert process.record.cmdline_hash.startswith("sha256:")
    finally:
        lab.cleanup()


def test_process_lab_can_create_pid_gone_record(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        record = lab.make_pid_gone_record()

        assert isinstance(record, ProcessRecord)
        assert not _same_process_is_alive(record)
    finally:
        lab.cleanup()


def test_process_lab_record_mutators_cover_drift_and_pgid_mismatch(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_live()

        drifted = lab.with_create_time_drift(process.record, drift_seconds=99.0)
        mismatched = lab.with_pgid_mismatch(process.record, pgid=0)

        assert drifted.create_time == process.record.create_time + 99.0
        assert drifted.pid == process.record.pid
        assert mismatched.pgid == 0
        assert mismatched.pid == process.record.pid
    finally:
        lab.cleanup()


def test_process_lab_can_spawn_without_env_marker(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_live(
            session_id="sess_lab_no_marker",
            include_env_marker=False,
        )

        assert process.record.session_id == "sess_lab_no_marker"
        assert process.record.env_marker_visible_at_spawn is False
    finally:
        lab.cleanup()


def test_process_lab_exposes_access_denied_exception(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    error = lab.access_denied_for(12345)

    assert isinstance(error, psutil.AccessDenied)
    assert error.pid == 12345


def test_process_lab_leader_dead_children_alive_scenario(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_leader_dead_children_alive(
            session_id="sess_lab_leader_dead"
        )

        assert process.popen.poll() == 0
        assert process.child_pids
        assert process.child_pgids == (process.pgid,)
        assert psutil.pid_exists(process.child_pids[0])
    finally:
        lab.cleanup()


def test_process_lab_double_fork_escape_scenario(tmp_path) -> None:
    lab = create_process_lab(tmp_path)
    try:
        process = lab.spawn_double_fork_escape(session_id="sess_lab_escape")

        assert process.popen.poll() == 0
        assert process.child_pids
        assert process.child_pgids[0] != process.pgid
        assert psutil.pid_exists(process.child_pids[0])
    finally:
        lab.cleanup()


def _same_process_is_alive(record: ProcessRecord) -> bool:
    try:
        proc = psutil.Process(record.pid)
    except psutil.NoSuchProcess:
        return False
    try:
        return abs(proc.create_time() - record.create_time) < 0.001
    except psutil.NoSuchProcess:
        return False
