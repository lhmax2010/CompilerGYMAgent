from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from agent import (
    AGENT_SESSION_ID_ENV,
    ProcessRunnerError,
    load_process_lease_for_layout,
    refresh_process_lease_from_popen,
    spawn_process,
)
from tests.fixtures.fake_workspace import create_fake_workspace


pytestmark = pytest.mark.skipif(os.name != "posix", reason="process runner is POSIX-only")


def test_spawn_process_starts_new_session_and_writes_running_lease(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_runner_1",
        trial_id="trial_1",
        role="compile",
    )
    try:
        assert result.record.pid == result.popen.pid
        assert result.record.pgid == result.record.pid
        assert os.getpgid(result.popen.pid) == result.record.pgid
        assert result.record.env_marker_visible_at_spawn is True
        assert result.lease.status == "running"

        loaded = load_process_lease_for_layout(
            fake.layout,
            session_id="sess_runner_1",
            trial_id="trial_1",
            role="compile",
            pid=result.record.pid,
        )
        assert loaded == result.lease
    finally:
        _terminate_result(result)


def test_spawn_process_overrides_env_marker(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_runner_env",
        trial_id="trial_env",
        role="compile",
        env={AGENT_SESSION_ID_ENV: "wrong"},
    )
    try:
        assert result.record.session_id == "sess_runner_env"
        assert result.record.env_marker_visible_at_spawn is True
    finally:
        _terminate_result(result)


def test_refresh_process_lease_marks_exit_code(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = spawn_process(
        fake.layout,
        [
            sys.executable,
            "-c",
            "import sys, time; time.sleep(0.05); sys.exit(7)",
        ],
        session_id="sess_runner_exit",
        trial_id="trial_exit",
        role="benchmark",
    )

    result.popen.wait(timeout=5)
    refreshed = refresh_process_lease_from_popen(fake.layout, result)

    assert refreshed.status == "exited"
    assert refreshed.exit_code == 7
    assert refreshed.ended_at is not None


def test_refresh_process_lease_marks_killed_signal(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_runner_kill",
        trial_id="trial_kill",
        role="compile",
    )

    os.killpg(result.record.pgid, signal.SIGTERM)
    result.popen.wait(timeout=5)
    refreshed = refresh_process_lease_from_popen(fake.layout, result)

    assert refreshed.status == "killed"
    assert refreshed.signal == signal.SIGTERM


def test_refresh_process_lease_leaves_running_process_unchanged(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = spawn_process(
        fake.layout,
        [sys.executable, "-c", "import time; time.sleep(60)"],
        session_id="sess_runner_still",
        trial_id="trial_still",
        role="compile",
    )
    try:
        assert refresh_process_lease_from_popen(fake.layout, result) == result.lease
    finally:
        _terminate_result(result)


def test_spawn_process_rejects_empty_args(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)

    with pytest.raises(ProcessRunnerError, match="args"):
        spawn_process(
            fake.layout,
            [],
            session_id="sess_runner_empty",
            trial_id="trial_empty",
            role="compile",
        )


def _terminate_result(result) -> None:
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
    except subprocess.TimeoutExpired:
        return
