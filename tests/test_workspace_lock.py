from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest
import yaml

from agent.config import AgentConfig
from agent.workspace_lock import (
    LockReadResult,
    WorkspaceBusyError,
    WorkspaceLock,
    WorkspaceLockPlatformError,
    lock_path_for_workspace,
)


class FakeFcntl:
    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 4

    def __init__(self) -> None:
        self.held = False
        self.calls: list[int] = []

    def flock(self, fd: int, operation: int) -> None:
        self.calls.append(operation)
        if operation == self.LOCK_UN:
            self.held = False
            return
        if operation & self.LOCK_EX:
            if self.held:
                raise BlockingIOError("busy")
            self.held = True


class FakeProcess:
    def __init__(self, create_time: float) -> None:
        self._create_time = create_time

    def create_time(self) -> float:
        return self._create_time


def make_lock(
    workspace: Path,
    *,
    fcntl: FakeFcntl | None = None,
    pid: int = 12345,
    pgid: int = 12345,
    create_time: float = 1730000000.123,
    process_create_time: float | None = 1730000000.123,
    now: datetime = datetime(2026, 5, 7, 1, 2, 3, tzinfo=UTC),
) -> WorkspaceLock:
    fake_fcntl = fcntl or FakeFcntl()

    def process_lookup(lookup_pid: int) -> FakeProcess:
        if process_create_time is None:
            raise psutil.NoSuchProcess(lookup_pid)
        return FakeProcess(process_create_time)

    return WorkspaceLock(
        workspace,
        fcntl_module=fake_fcntl,
        pid_provider=lambda: pid,
        pgid_provider=lambda: pgid,
        create_time_provider=lambda: create_time,
        process_lookup=process_lookup,
        hostname_provider=lambda: "dev-host",
        now_provider=lambda: now,
        agent_version="0.1.test",
    )


def lock_holder_data(**overrides: object) -> dict:
    data = {
        "pid": 99999,
        "pgid": 99999,
        "create_time": 100.0,
        "session_id": "sess_old",
        "command": "agent run",
        "started_at": "2026-05-07T00:00:00+00:00",
        "hostname": "old-host",
        "agent_version": "0.1.old",
    }
    data.update(overrides)
    return data


def write_holder(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def minimal_config_data(workspace: Path) -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(workspace)},
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }


def test_lock_path_for_workspace_resolves_relative_lock_file(tmp_path: Path) -> None:
    assert lock_path_for_workspace(tmp_path, "state/run.lock") == (
        tmp_path / "state" / "run.lock"
    )


def test_workspace_lock_from_config_uses_configured_lock_file(tmp_path: Path) -> None:
    data = minimal_config_data(tmp_path)
    data["workspace_lock"] = {"lock_file": "state/custom.lock"}
    config = AgentConfig.model_validate(data)

    lock = WorkspaceLock.from_config(config, fcntl_module=FakeFcntl())

    assert lock.lock_path == tmp_path / "state" / "custom.lock"


def test_acquire_writes_holder_metadata_and_release_removes_file(tmp_path: Path) -> None:
    lock = make_lock(tmp_path)

    with lock.acquire("agent run", "sess_20260507_test"):
        assert lock.is_held is True
        holder = yaml.safe_load((tmp_path / "state" / "run.lock").read_text())
        assert holder == {
            "pid": 12345,
            "pgid": 12345,
            "create_time": 1730000000.123,
            "session_id": "sess_20260507_test",
            "command": "agent run",
            "started_at": "2026-05-07T01:02:03+00:00",
            "hostname": "dev-host",
            "agent_version": "0.1.test",
        }
        if os.name == "posix":
            assert (tmp_path / "state" / "run.lock").stat().st_mode & 0o777 == 0o600

    assert lock.is_held is False
    assert not (tmp_path / "state" / "run.lock").exists()


def test_release_is_idempotent(tmp_path: Path) -> None:
    lock = make_lock(tmp_path)
    lock.acquire("agent run", "sess_1")

    lock.release()
    lock.release()

    assert lock.is_held is False


def test_busy_lock_raises_with_holder_info(tmp_path: Path) -> None:
    fake_fcntl = FakeFcntl()
    first = make_lock(tmp_path, fcntl=fake_fcntl, pid=111, create_time=111.0)
    first.acquire("agent run", "sess_first")
    second = make_lock(tmp_path, fcntl=fake_fcntl, pid=222, create_time=222.0)

    with pytest.raises(WorkspaceBusyError) as exc_info:
        second.acquire("agent clean trials --apply", "sess_second")

    error = exc_info.value
    assert error.holder is not None
    assert error.holder.pid == 111
    assert error.holder.command == "agent run"
    assert error.holder.session_id == "sess_first"
    assert "pid=111" in str(error)
    assert "agent run" in str(error)

    first.release()


def test_busy_lock_with_unreadable_holder_fails_conservatively(tmp_path: Path) -> None:
    fake_fcntl = FakeFcntl()
    lock_path = tmp_path / "state" / "run.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("!!python/object/apply:os.system ['echo unsafe']\n", encoding="utf-8")
    fake_fcntl.held = True
    lock = make_lock(tmp_path, fcntl=fake_fcntl)

    with pytest.raises(WorkspaceBusyError, match="holder metadata could not be read") as exc_info:
        lock.acquire("agent run", "sess_new")

    assert exc_info.value.holder is None
    assert "failed to parse YAML" in (exc_info.value.holder_error or "")
    assert lock_path.exists()


def test_busy_lock_with_stale_metadata_does_not_bypass_active_fcntl(
    tmp_path: Path,
) -> None:
    fake_fcntl = FakeFcntl()
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(pid=99999, create_time=100.0))
    fake_fcntl.held = True
    lock = make_lock(tmp_path, fcntl=fake_fcntl, process_create_time=None)

    with pytest.raises(WorkspaceBusyError) as exc_info:
        lock.acquire("agent run", "sess_new")

    assert exc_info.value.holder is not None
    assert exc_info.value.holder.pid == 99999
    assert lock_path.exists()


def test_existing_stale_lock_file_is_overwritten_after_successful_flock(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(pid=99999, create_time=100.0))
    lock = make_lock(tmp_path, process_create_time=None)

    lock.acquire("agent run", "sess_new")

    assert lock.replaced_stale_holder is not None
    assert lock.replaced_stale_holder.pid == 99999
    written = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    assert written["pid"] == 12345
    assert written["session_id"] == "sess_new"
    lock.release()


def test_pid_reuse_create_time_mismatch_is_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(pid=12345, create_time=100.0))
    lock = make_lock(tmp_path, process_create_time=200.0)

    lock.acquire("agent run", "sess_new")

    assert lock.replaced_stale_holder is not None
    assert lock.replaced_stale_holder.pid == 12345
    lock.release()


def test_matching_pid_and_create_time_is_not_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(pid=12345, create_time=100.0))
    lock = make_lock(tmp_path, process_create_time=100.2)

    lock.acquire("agent run", "sess_new")

    assert lock.replaced_stale_holder is None
    lock.release()


def test_access_denied_during_stale_check_fails_conservative(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(pid=12345, create_time=100.0))

    def process_lookup(pid: int) -> FakeProcess:
        raise psutil.AccessDenied(pid=pid)

    lock = WorkspaceLock(
        tmp_path,
        fcntl_module=FakeFcntl(),
        pid_provider=lambda: 12345,
        pgid_provider=lambda: 12345,
        create_time_provider=lambda: 200.0,
        process_lookup=process_lookup,
        hostname_provider=lambda: "dev-host",
        now_provider=lambda: datetime(2026, 5, 7, tzinfo=UTC),
        agent_version="0.1.test",
    )

    lock.acquire("agent run", "sess_new")

    assert lock.replaced_stale_holder is None
    lock.release()


def test_workspace_lock_rejects_invalid_holder_timestamp(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    write_holder(lock_path, lock_holder_data(started_at="not-a-time"))
    lock = make_lock(tmp_path)

    result = lock.read_holder()

    assert result.holder is None
    assert result.error is not None
    assert "started_at must be ISO 8601" in result.error


def test_workspace_lock_rejects_yaml_aliases(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        "pid: &pid 123\npgid: *pid\n",
        encoding="utf-8",
    )
    lock = make_lock(tmp_path)

    result = lock.read_holder()

    assert result == LockReadResult(
        holder=None,
        error="failed to parse YAML: YAML aliases are not allowed in workspace lock files",
    )


def test_workspace_lock_rejects_oversized_holder_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "run.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("x" * 65_537, encoding="utf-8")
    lock = make_lock(tmp_path)

    result = lock.read_holder()

    assert result.holder is None
    assert result.error is not None
    assert "too large" in result.error


def test_acquire_rejects_empty_command_or_session(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="String should have at least 1 character"):
        make_lock(tmp_path).acquire("", "sess")

    with pytest.raises(ValueError, match="String should have at least 1 character"):
        make_lock(tmp_path).acquire("agent run", "")


def test_acquire_rejects_negative_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout"):
        make_lock(tmp_path).acquire("agent run", "sess", timeout=-1)


def test_acquire_requires_linux_fcntl_backend(tmp_path: Path) -> None:
    lock = WorkspaceLock(
        tmp_path,
        fcntl_module=None,
        pid_provider=lambda: 1,
        pgid_provider=lambda: 1,
        create_time_provider=lambda: 1.0,
    )

    with pytest.raises(WorkspaceLockPlatformError, match="fcntl"):
        lock.acquire("agent run", "sess")


def test_enter_requires_acquired_lock(tmp_path: Path) -> None:
    lock = make_lock(tmp_path)

    with pytest.raises(RuntimeError, match="call acquire"):
        with lock:
            pass
