from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil
import pytest

from agent.process_identity import (
    AGENT_SESSION_ID_ENV,
    ProcessRecord,
    compute_cmdline_hash,
)


_WORKER_SOURCE = r'''
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_info(path: Path, **extra: object) -> None:
    payload = {
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "ppid": os.getppid(),
        "env_marker": os.environ.get("AGENT_SESSION_ID"),
    }
    payload.update(extra)
    atomic_write_json(path, payload)


def wait_for_json(path: Path, timeout: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                last_error = exc
        time.sleep(0.01)
    if last_error is not None:
        raise RuntimeError(f"timed out reading {path}") from last_error
    raise RuntimeError(f"timed out waiting for {path}")


def sleep_loop(lifetime: float) -> None:
    deadline = time.monotonic() + lifetime
    while time.monotonic() < deadline:
        time.sleep(0.1)


def spawn_child(script: Path, info: Path, lifetime: float, *, start_new_session: bool) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--mode",
            "sleep",
            "--info",
            str(info),
            "--lifetime",
            str(lifetime),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=start_new_session,
        env=os.environ.copy(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["sleep", "child_same_pgid", "leader_exit_child_alive", "double_fork_escape"], required=True)
    parser.add_argument("--info", required=True)
    parser.add_argument("--child-info")
    parser.add_argument("--lifetime", type=float, default=60.0)
    args = parser.parse_args()

    info = Path(args.info)
    child_info = Path(args.child_info) if args.child_info else None
    script = Path(__file__).resolve()

    if args.mode == "sleep":
        write_info(info)
        sleep_loop(args.lifetime)
        return 0

    if child_info is None:
        raise RuntimeError("--child-info is required for child modes")

    if args.mode == "child_same_pgid":
        child = spawn_child(script, child_info, args.lifetime, start_new_session=False)
        child_payload = wait_for_json(child_info)
        write_info(
            info,
            child_pid=child.pid,
            child_pgid=child_payload["pgid"],
            child_info=str(child_info),
        )
        sleep_loop(args.lifetime)
        return 0

    if args.mode == "leader_exit_child_alive":
        child = spawn_child(script, child_info, args.lifetime, start_new_session=False)
        child_payload = wait_for_json(child_info)
        write_info(
            info,
            child_pid=child.pid,
            child_pgid=child_payload["pgid"],
            child_info=str(child_info),
        )
        return 0

    child = spawn_child(script, child_info, args.lifetime, start_new_session=True)
    child_payload = wait_for_json(child_info)
    write_info(
        info,
        child_pid=child.pid,
        child_pgid=child_payload["pgid"],
        child_info=str(child_info),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


@dataclass(frozen=True)
class LabProcess:
    popen: subprocess.Popen[bytes]
    record: ProcessRecord
    info_path: Path
    child_pids: tuple[int, ...] = ()
    child_pgids: tuple[int, ...] = ()

    @property
    def pid(self) -> int:
        return self.record.pid

    @property
    def pgid(self) -> int:
        return self.record.pgid


class ProcessLab:
    """Reusable process fixture for Phase 06 process-management tests."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.script_path = self.root / "_process_lab_worker.py"
        self.script_path.write_text(_WORKER_SOURCE, encoding="utf-8")
        self._tracked_popen: list[subprocess.Popen[bytes]] = []
        self._tracked_pgids: set[int] = set()

    def spawn_live(
        self,
        *,
        session_id: str = "sess_process_lab",
        role: str = "worker",
        include_env_marker: bool = True,
        lifetime: float = 60.0,
    ) -> LabProcess:
        return self._spawn(
            mode="sleep",
            session_id=session_id,
            role=role,
            include_env_marker=include_env_marker,
            lifetime=lifetime,
        )

    def spawn_with_same_pgid_child(
        self,
        *,
        session_id: str = "sess_process_lab",
        role: str = "worker",
        lifetime: float = 60.0,
    ) -> LabProcess:
        return self._spawn(
            mode="child_same_pgid",
            session_id=session_id,
            role=role,
            include_env_marker=True,
            lifetime=lifetime,
        )

    def spawn_leader_dead_children_alive(
        self,
        *,
        session_id: str = "sess_process_lab",
        role: str = "worker",
        lifetime: float = 60.0,
    ) -> LabProcess:
        process = self._spawn(
            mode="leader_exit_child_alive",
            session_id=session_id,
            role=role,
            include_env_marker=True,
            lifetime=lifetime,
        )
        process.popen.wait(timeout=5)
        return process

    def spawn_double_fork_escape(
        self,
        *,
        session_id: str = "sess_process_lab",
        role: str = "worker",
        lifetime: float = 60.0,
    ) -> LabProcess:
        process = self._spawn(
            mode="double_fork_escape",
            session_id=session_id,
            role=role,
            include_env_marker=True,
            lifetime=lifetime,
        )
        process.popen.wait(timeout=5)
        return process

    def make_pid_gone_record(self) -> ProcessRecord:
        process = self.spawn_live(lifetime=60.0)
        self.terminate_process_group(process.pgid)
        process.popen.wait(timeout=5)
        return process.record

    def with_create_time_drift(
        self, record: ProcessRecord, *, drift_seconds: float = 3600.0
    ) -> ProcessRecord:
        return record.model_copy(
            update={"create_time": record.create_time + drift_seconds}
        )

    def with_pgid_mismatch(self, record: ProcessRecord, *, pgid: int = 0) -> ProcessRecord:
        return record.model_copy(update={"pgid": pgid})

    def access_denied_for(self, pid: int) -> psutil.AccessDenied:
        return psutil.AccessDenied(pid=pid, name="process_lab")

    def terminate_process_group(self, pgid: int) -> None:
        if pgid <= 0 or pgid == os.getpgrp():
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not _pgid_has_members(pgid):
                return
            time.sleep(0.02)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def cleanup(self) -> None:
        for pgid in sorted(self._tracked_pgids, reverse=True):
            self.terminate_process_group(pgid)
        for popen in self._tracked_popen:
            try:
                popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                popen.kill()
                popen.wait(timeout=2)

    def _spawn(
        self,
        *,
        mode: str,
        session_id: str,
        role: str,
        include_env_marker: bool,
        lifetime: float,
    ) -> LabProcess:
        info_path = self.root / f"{role}-{mode}-{time.monotonic_ns()}.json"
        child_info_path = self.root / f"{role}-{mode}-{time.monotonic_ns()}-child.json"
        args = [
            sys.executable,
            str(self.script_path),
            "--mode",
            mode,
            "--info",
            str(info_path),
            "--lifetime",
            str(lifetime),
        ]
        if mode != "sleep":
            args.extend(["--child-info", str(child_info_path)])

        env = os.environ.copy()
        if include_env_marker:
            env[AGENT_SESSION_ID_ENV] = session_id
        else:
            env.pop(AGENT_SESSION_ID_ENV, None)

        popen = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
        self._tracked_popen.append(popen)
        payload = _wait_for_json(info_path, process=popen)
        child_pids, child_pgids = _child_identity(payload)
        record = self._build_record(
            pid=popen.pid,
            session_id=session_id,
            fallback_cmdline=args,
            fallback_env_marker=payload.get("env_marker") == session_id,
        )
        self._tracked_pgids.add(record.pgid)
        self._tracked_pgids.update(child_pgids)
        _wait_for_child_processes_ready(
            child_pids=child_pids,
            child_pgids=child_pgids,
            session_id=session_id,
            require_env_marker=include_env_marker,
        )
        return LabProcess(
            popen=popen,
            record=record,
            info_path=info_path,
            child_pids=child_pids,
            child_pgids=child_pgids,
        )

    def _build_record(
        self,
        *,
        pid: int,
        session_id: str,
        fallback_cmdline: list[str],
        fallback_env_marker: bool,
    ) -> ProcessRecord:
        proc = psutil.Process(pid)
        try:
            cmdline = proc.cmdline()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cmdline = fallback_cmdline
        return ProcessRecord(
            pid=pid,
            pgid=os.getpgid(pid),
            create_time=proc.create_time(),
            session_id=session_id,
            cmdline_hash=compute_cmdline_hash(cmdline),
            env_marker_visible_at_spawn=_env_marker_visible(
                proc, session_id, fallback=fallback_env_marker
            ),
            cgroup_path=None,
        )


def create_process_lab(tmp_path: Path) -> ProcessLab:
    return ProcessLab(tmp_path / "process_lab")


@pytest.fixture
def process_lab(tmp_path: Path) -> ProcessLab:
    lab = create_process_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()


def _wait_for_json(
    path: Path,
    *,
    timeout: float = 20.0,
    process: subprocess.Popen[bytes] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                last_error = exc
        time.sleep(0.01)
    process_detail = _process_timeout_detail(process)
    if last_error is not None:
        raise RuntimeError(
            f"timed out reading process lab info {path}; {process_detail}"
        ) from last_error
    raise RuntimeError(f"timed out waiting for process lab info {path}; {process_detail}")


def _process_timeout_detail(process: subprocess.Popen[bytes] | None) -> str:
    if process is None:
        return "worker process unavailable"
    returncode = process.poll()
    if returncode is None:
        return f"worker pid={process.pid} still running"
    try:
        stdout, stderr = process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        return f"worker pid={process.pid} exited with {returncode}; output unavailable"
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    return (
        f"worker pid={process.pid} exited with {returncode}; "
        f"stdout={stdout_text!r}; stderr={stderr_text!r}"
    )


def _child_identity(payload: dict[str, Any]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if "child_pid" not in payload:
        return (), ()
    return (int(payload["child_pid"]),), (int(payload["child_pgid"]),)


def _wait_for_child_processes_ready(
    *,
    child_pids: tuple[int, ...],
    child_pgids: tuple[int, ...],
    session_id: str,
    require_env_marker: bool,
    timeout: float = 5.0,
) -> None:
    for child_pid, child_pgid in zip(child_pids, child_pgids, strict=True):
        _wait_for_child_process_ready(
            child_pid=child_pid,
            child_pgid=child_pgid,
            session_id=session_id,
            require_env_marker=require_env_marker,
            timeout=timeout,
        )


def _wait_for_child_process_ready(
    *,
    child_pid: int,
    child_pgid: int,
    session_id: str,
    require_env_marker: bool,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not checked"
    while time.monotonic() < deadline:
        try:
            proc = psutil.Process(child_pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                last_error = "child is zombie"
                time.sleep(0.01)
                continue
            actual_pgid = os.getpgid(child_pid)
            if actual_pgid != child_pgid:
                last_error = f"pgid {actual_pgid} != expected {child_pgid}"
                time.sleep(0.01)
                continue
            if require_env_marker:
                marker = proc.environ().get(AGENT_SESSION_ID_ENV)
                if marker != session_id:
                    last_error = f"env marker {marker!r} != {session_id!r}"
                    time.sleep(0.01)
                    continue
            return
        except (ProcessLookupError, psutil.NoSuchProcess) as exc:
            last_error = f"child not visible yet: {exc}"
        except psutil.AccessDenied as exc:
            last_error = f"child env/metadata access denied: {exc}"
        time.sleep(0.01)
    raise RuntimeError(
        f"timed out waiting for child process {child_pid} readiness: {last_error}"
    )


def _env_marker_visible(
    proc: psutil.Process, session_id: str, *, fallback: bool
) -> bool:
    try:
        return proc.environ().get(AGENT_SESSION_ID_ENV) == session_id
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return fallback


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
