"""Controlled subprocess runner with Phase 06 process lease registration."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import psutil

from .errors import AgentError, EXIT_GENERIC
from .fs_memory import NamespaceLayout
from .identifiers import validate_session_id_atom
from .process_identity import (
    AGENT_LEASE_ID_ENV,
    AGENT_PROCESS_ROLE_ENV,
    AGENT_SESSION_ID_ENV,
    AGENT_TRIAL_ID_ENV,
    ProcessRecord,
    compute_cmdline_hash,
    generate_lease_id,
)
from .process_registry import (
    ProcessLease,
    ProcessRegistryError,
    mark_process_exited,
    mark_process_killed,
    register_process_lease,
)


class ProcessRunnerError(AgentError):
    """Raised when a managed subprocess cannot be started or recorded."""

    exit_code = EXIT_GENERIC


@dataclass(frozen=True)
class ProcessSpawnResult:
    popen: subprocess.Popen[bytes]
    lease: ProcessLease

    @property
    def record(self) -> ProcessRecord:
        return self.lease.record


def spawn_process(
    layout: NamespaceLayout,
    args: Sequence[str | os.PathLike[str]],
    *,
    session_id: str,
    trial_id: str,
    role: str,
    lease_id: str | None = None,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    stdin: int | None = subprocess.DEVNULL,
    stdout: int | None = subprocess.DEVNULL,
    stderr: int | None = subprocess.DEVNULL,
) -> ProcessSpawnResult:
    """Start a managed child process and persist a running process lease."""

    argv = [os.fspath(arg) for arg in args]
    if not argv:
        raise ProcessRunnerError("process args must not be empty")
    resolved_lease_id = (
        generate_lease_id(role)
        if lease_id is None
        else validate_session_id_atom(lease_id, "lease_id")
    )
    child_env = os.environ.copy()
    if env is not None:
        child_env.update({str(key): str(value) for key, value in env.items()})
    child_env[AGENT_SESSION_ID_ENV] = session_id
    child_env[AGENT_TRIAL_ID_ENV] = trial_id
    child_env[AGENT_LEASE_ID_ENV] = resolved_lease_id
    child_env[AGENT_PROCESS_ROLE_ENV] = role

    try:
        popen = subprocess.Popen(
            argv,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            cwd=None if cwd is None else os.fspath(cwd),
            env=child_env,
            start_new_session=True,
        )
    except OSError as exc:
        raise ProcessRunnerError(f"failed to start process {argv!r}: {exc}") from exc

    try:
        record = process_record_for_pid(
            popen.pid,
            session_id=session_id,
            trial_id=trial_id,
            lease_id=resolved_lease_id,
            fallback_cmdline=argv,
        )
        lease = register_process_lease(
            layout,
            record=record,
            trial_id=trial_id,
            role=role,
            lease_id=resolved_lease_id,
        )
    except Exception as exc:
        _terminate_started_process_group(popen)
        if isinstance(exc, (ProcessRunnerError, ProcessRegistryError)):
            raise
        raise ProcessRunnerError(
            f"failed to record started process {popen.pid}: {exc}"
        ) from exc

    return ProcessSpawnResult(popen=popen, lease=lease)


def process_record_for_pid(
    pid: int,
    *,
    session_id: str,
    trial_id: str | None = None,
    lease_id: str | None = None,
    fallback_cmdline: Sequence[str] = (),
    cgroup_path: str | None = None,
) -> ProcessRecord:
    """Read process identity evidence for a just-spawned managed child."""

    try:
        proc = psutil.Process(pid)
        create_time = proc.create_time()
        pgid = os.getpgid(pid)
    except (psutil.Error, ProcessLookupError) as exc:
        raise ProcessRunnerError(f"process {pid} disappeared before recording") from exc

    try:
        cmdline = proc.cmdline()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        cmdline = list(fallback_cmdline)
    if not cmdline:
        cmdline = list(fallback_cmdline) or [str(pid)]

    return ProcessRecord(
        pid=pid,
        pgid=pgid,
        create_time=create_time,
        session_id=session_id,
        trial_id=trial_id,
        lease_id=lease_id,
        cmdline_hash=compute_cmdline_hash(cmdline),
        env_marker_visible_at_spawn=_env_marker_visible(
            proc,
            session_id,
            trial_id=trial_id,
            lease_id=lease_id,
        ),
        cgroup_path=cgroup_path,
    )


def refresh_process_lease_from_popen(
    layout: NamespaceLayout,
    result: ProcessSpawnResult,
) -> ProcessLease:
    """Mark a lease exited/killed when the associated Popen has completed."""

    return_code = result.popen.poll()
    if return_code is None:
        return result.lease
    if return_code < 0:
        return mark_process_killed(
            layout,
            result.lease,
            signal=-return_code,
        )
    return mark_process_exited(
        layout,
        result.lease,
        exit_code=return_code,
    )


def _env_marker_visible(
    proc: psutil.Process,
    session_id: str,
    *,
    trial_id: str | None = None,
    lease_id: str | None = None,
    timeout_seconds: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            environ = proc.environ()
            if environ.get(AGENT_SESSION_ID_ENV) != session_id:
                marker_visible = False
            elif trial_id is not None and environ.get(AGENT_TRIAL_ID_ENV) != trial_id:
                marker_visible = False
            elif lease_id is not None and environ.get(AGENT_LEASE_ID_ENV) != lease_id:
                marker_visible = False
            else:
                marker_visible = True
            if marker_visible:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def _terminate_started_process_group(popen: subprocess.Popen[bytes]) -> None:
    try:
        pgid = os.getpgid(popen.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if popen.poll() is not None:
            return
        time.sleep(0.02)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        popen.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return
