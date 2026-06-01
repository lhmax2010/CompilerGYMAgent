"""Process ownership scoring and cleanup for Phase 06."""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from typing import Literal

import psutil

from .errors import AgentError, EXIT_GENERIC
from .fs_memory import NamespaceLayout
from .process_identity import AGENT_SESSION_ID_ENV, ProcessRecord
from .process_registry import (
    ProcessLease,
    load_process_leases,
    mark_process_killed,
    mark_process_unknown,
    mark_process_unsafe_skip,
    process_lease_path,
)


CREATE_TIME_TOLERANCE_SECONDS = 0.5
OWNED_SCORE_THRESHOLD = 7
SUSPECTED_SCORE_THRESHOLD = 4

OwnershipVerdict = Literal["owned", "suspected", "not_ours"]
EnvMarkerStatus = Literal["matched", "mismatch", "missing", "unavailable", "gone"]
CleanupAction = Literal["killed", "unsafe_skip", "unknown", "deleted_orphan"]


class ProcessCleanerError(AgentError):
    """Raised when process cleanup cannot complete safely."""

    exit_code = EXIT_GENERIC


@dataclass(frozen=True)
class EnvMarkerRead:
    value: str | None
    status: EnvMarkerStatus


@dataclass(frozen=True)
class ProcessAttribution:
    pid: int
    pgid: int | None
    score: int
    verdict: OwnershipVerdict
    pid_create_time_match: bool
    pgid_match: bool
    env_marker_match: bool
    env_marker_status: EnvMarkerStatus
    source: str


@dataclass(frozen=True)
class CleanupTarget:
    pid: int
    pgid: int
    attribution: ProcessAttribution


@dataclass(frozen=True)
class ProcessCleanupResult:
    lease: ProcessLease
    action: CleanupAction
    updated_lease: ProcessLease | None
    targets: tuple[CleanupTarget, ...]
    killed_pgids: tuple[int, ...]
    reason: str | None = None


@dataclass(frozen=True)
class LeaseGcResult:
    deleted_paths: tuple[str, ...]
    kept_paths: tuple[str, ...]


def read_env_marker(proc: psutil.Process) -> EnvMarkerRead:
    """Read AGENT_SESSION_ID once.

    This function intentionally does not retry. Cleaner scans arbitrary
    processes, so a missing marker means "not present", not "wait for spawn".
    """

    try:
        value = proc.environ().get(AGENT_SESSION_ID_ENV)
    except psutil.NoSuchProcess:
        return EnvMarkerRead(value=None, status="gone")
    except psutil.AccessDenied:
        return EnvMarkerRead(value=None, status="unavailable")
    if value is None:
        return EnvMarkerRead(value=None, status="missing")
    return EnvMarkerRead(value=value, status="matched")


def attribute_process(
    proc: psutil.Process,
    record: ProcessRecord,
    *,
    source: str = "direct",
) -> ProcessAttribution:
    pid_create_time_match = False
    pgid_match = False
    env_marker_match = False
    score = 0
    pgid: int | None = None

    try:
        pid = proc.pid
        if pid == record.pid:
            create_time = proc.create_time()
            if abs(create_time - record.create_time) <= CREATE_TIME_TOLERANCE_SECONDS:
                pid_create_time_match = True
                score += 3
        pgid = os.getpgid(pid)
        if pgid == record.pgid:
            pgid_match = True
            score += 3
    except (psutil.NoSuchProcess, ProcessLookupError):
        return ProcessAttribution(
            pid=getattr(proc, "pid", record.pid),
            pgid=None,
            score=0,
            verdict="not_ours",
            pid_create_time_match=False,
            pgid_match=False,
            env_marker_match=False,
            env_marker_status="gone",
            source=source,
        )

    marker = _read_env_marker_for_session(proc, record.session_id)
    if marker.status == "matched":
        env_marker_match = True
        score += 4

    return ProcessAttribution(
        pid=pid,
        pgid=pgid,
        score=score,
        verdict=_verdict_for_score(score),
        pid_create_time_match=pid_create_time_match,
        pgid_match=pgid_match,
        env_marker_match=env_marker_match,
        env_marker_status=marker.status,
        source=source,
    )


def find_cleanup_targets(record: ProcessRecord) -> tuple[CleanupTarget, ...]:
    """Find candidate processes for a recorded process lease.

    PID disappearance is not enough to skip cleanup: children can survive in
    the old pgid or escape into a new session while retaining AGENT_SESSION_ID.
    """

    targets: dict[int, CleanupTarget] = {}

    try:
        proc = psutil.Process(record.pid)
    except psutil.NoSuchProcess:
        proc = None
    if proc is not None:
        _add_target(targets, proc, record, source="recorded_pid")

    for proc in psutil.process_iter(["pid", "status"]):
        if proc.info.get("status") == psutil.STATUS_ZOMBIE:
            continue
        try:
            pid = int(proc.info["pid"])
        except (TypeError, ValueError):
            continue
        if pid == os.getpid():
            continue
        source = _scan_source(proc, record)
        if source is None:
            continue
        _add_target(targets, proc, record, source=source)

    return tuple(sorted(targets.values(), key=lambda target: target.pid))


def cleanup_process_lease(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    force_suspected: bool = False,
    sig: int = signal.SIGTERM,
    kill_timeout_seconds: float = 2.0,
) -> ProcessCleanupResult:
    targets = find_cleanup_targets(lease.record)
    if not targets:
        updated = mark_process_unknown(
            layout,
            lease,
            cleanup_attempts=lease.cleanup_attempts + 1,
        )
        return ProcessCleanupResult(
            lease=lease,
            action="unknown",
            updated_lease=updated,
            targets=(),
            killed_pgids=(),
            reason="no matching live process found",
        )

    if any(target.attribution.verdict == "owned" for target in targets):
        killable = targets
    elif force_suspected and any(
        target.attribution.verdict == "suspected" for target in targets
    ):
        killable = targets
    else:
        updated = mark_process_unsafe_skip(
            layout,
            lease,
            cleanup_attempts=lease.cleanup_attempts + 1,
        )
        return ProcessCleanupResult(
            lease=lease,
            action="unsafe_skip",
            updated_lease=updated,
            targets=targets,
            killed_pgids=(),
            reason="ownership score below kill threshold",
        )

    killed_pgids = _kill_target_process_groups(
        killable,
        sig=sig,
        timeout_seconds=kill_timeout_seconds,
    )
    updated = mark_process_killed(
        layout,
        lease,
        signal=sig,
        cleanup_attempts=lease.cleanup_attempts + 1,
    )
    return ProcessCleanupResult(
        lease=lease,
        action="killed",
        updated_lease=updated,
        targets=targets,
        killed_pgids=killed_pgids,
    )


def garbage_collect_process_leases(layout: NamespaceLayout) -> LeaseGcResult:
    deleted: list[str] = []
    kept: list[str] = []
    for lease in load_process_leases(layout):
        path = process_lease_path(
            layout,
            session_id=lease.session_id,
            trial_id=lease.trial_id,
            role=lease.role,
            pid=lease.record.pid,
        )
        targets = find_cleanup_targets(lease.record)
        if not targets:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            deleted.append(str(path))
        else:
            kept.append(str(path))
    return LeaseGcResult(deleted_paths=tuple(deleted), kept_paths=tuple(kept))


def _read_env_marker_for_session(
    proc: psutil.Process,
    session_id: str,
) -> EnvMarkerRead:
    marker = read_env_marker(proc)
    if marker.value is None:
        return marker
    if marker.value == session_id:
        return EnvMarkerRead(value=marker.value, status="matched")
    return EnvMarkerRead(value=marker.value, status="mismatch")


def _verdict_for_score(score: int) -> OwnershipVerdict:
    if score >= OWNED_SCORE_THRESHOLD:
        return "owned"
    if score >= SUSPECTED_SCORE_THRESHOLD:
        return "suspected"
    return "not_ours"


def _scan_source(proc: psutil.Process, record: ProcessRecord) -> str | None:
    sources: list[str] = []
    try:
        if os.getpgid(proc.pid) == record.pgid:
            sources.append("pgid_scan")
    except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    marker = _read_env_marker_for_session(proc, record.session_id)
    if marker.status == "matched":
        sources.append("env_scan")
    if not sources:
        return None
    return "+".join(sources)


def _add_target(
    targets: dict[int, CleanupTarget],
    proc: psutil.Process,
    record: ProcessRecord,
    *,
    source: str,
) -> None:
    attribution = attribute_process(proc, record, source=source)
    if attribution.pgid is None:
        return
    existing = targets.get(attribution.pid)
    if existing is not None and existing.attribution.score >= attribution.score:
        return
    targets[attribution.pid] = CleanupTarget(
        pid=attribution.pid,
        pgid=attribution.pgid,
        attribution=attribution,
    )


def _kill_target_process_groups(
    targets: tuple[CleanupTarget, ...],
    *,
    sig: int,
    timeout_seconds: float,
) -> tuple[int, ...]:
    current_pgid = os.getpgrp()
    pgids = tuple(
        sorted({target.pgid for target in targets if target.pgid > 0 and target.pgid != current_pgid})
    )
    for pgid in pgids:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            continue
    _wait_for_pgids_to_exit(pgids, timeout_seconds=timeout_seconds)
    for pgid in pgids:
        if _pgid_has_members(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                continue
    _wait_for_pgids_to_exit(pgids, timeout_seconds=timeout_seconds)
    return pgids


def _wait_for_pgids_to_exit(pgids: tuple[int, ...], *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(not _pgid_has_members(pgid) for pgid in pgids):
            return
        time.sleep(0.02)


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
