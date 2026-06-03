"""Read-only trace cleanup planning helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator, Literal

import psutil

from .errors import EXIT_EXECUTION_REFUSED, EXIT_STALE, EXIT_VALIDATION
from .fs_memory import (
    CheckpointState,
    NamespaceLayout,
    TraceError,
    TraceEvent,
    checkpoint_payload,
    iter_trace_events,
    load_checkpoint_for_layout,
    trace_event_payload,
)
from .trace import inspect_trace_session_spans
from .workspace_lock import WorkspaceBusyError, WorkspaceLock, WorkspaceLockHolder


LockStatus = Literal["free", "held_by_self", "held_by_other", "unknown"]
_LOCK_CREATE_TIME_TOLERANCE_SECONDS = 0.5


class TraceCleanupError(TraceError):
    """Raised when a trace cleanup plan cannot be computed safely."""

    exit_code = EXIT_VALIDATION


class CleanExecutionRefusedError(TraceCleanupError):
    """Raised when a clean plan is not executable."""

    exit_code = EXIT_EXECUTION_REFUSED


class StaleCleanPlanError(TraceCleanupError):
    """Raised when a clean plan no longer matches the trace file."""

    exit_code = EXIT_STALE


@dataclass(frozen=True)
class LineRange:
    """Physical 1-based line-number interval, inclusive."""

    first: int
    last: int

    def __post_init__(self) -> None:
        _require_int(self.first, "first")
        _require_int(self.last, "last")
        if self.first < 1:
            raise TraceCleanupError("line range first must be >= 1")
        if self.last < self.first:
            raise TraceCleanupError("line range last must be >= first")


@dataclass(frozen=True)
class ByteRange:
    """Physical byte interval, half-open."""

    start: int
    end: int

    def __post_init__(self) -> None:
        _require_int(self.start, "start")
        _require_int(self.end, "end")
        if self.start < 0:
            raise TraceCleanupError("byte range start must be >= 0")
        if self.end < self.start:
            raise TraceCleanupError("byte range end must be >= start")


@dataclass(frozen=True)
class CleanPlan:
    """Pure-data trace cleanup plan with no side effects."""

    trace_path: Path
    total_lines: int
    file_size_bytes: int
    protected_session_ids: frozenset[str]
    protected_line_ranges: tuple[LineRange, ...]
    post_checkpoint_boundary_line: int | None
    lock_status: LockStatus
    blocking_lock_holder: WorkspaceLockHolder | None
    keep_days: int
    cutoff_ts: datetime
    removable_line_ranges: tuple[LineRange, ...]
    removable_byte_ranges: tuple[ByteRange, ...]
    removable_event_count: int
    refusal_reason: str | None
    checkpoint_hash: str | None = None
    protected_sessions_hash: str | None = None
    current_trial_protected_line_range: LineRange | None = None

    @property
    def is_dry_run_safe(self) -> bool:
        """Clean plans are render-only objects and never mutate state."""

        return True

    @property
    def can_execute(self) -> bool:
        """Return whether normal clean trace execution would be allowed."""

        return (
            self.refusal_reason is None
            and self.lock_status == "free"
            and self.removable_event_count > 0
        )

    @property
    def can_execute_with_force_inactive_only(self) -> bool:
        """Return whether force-clean-inactive-only execution would be allowed."""

        return (
            self.refusal_reason is None
            and self.lock_status in {"free", "held_by_self"}
            and self.removable_event_count > 0
        )


@dataclass(frozen=True)
class CleanResult:
    """Result snapshot for one physical trace cleanup execution."""

    trace_path: Path
    removed_event_count: int
    removed_line_ranges: tuple[LineRange, ...]
    removed_byte_ranges: tuple[ByteRange, ...]
    bytes_freed: int
    backup_path: Path | None


@dataclass(frozen=True)
class _TraceLine:
    line_number: int
    byte_start: int
    byte_end: int
    event: TraceEvent


@dataclass(frozen=True)
class _LockSnapshot:
    status: LockStatus
    active_holder: WorkspaceLockHolder | None
    blocking_holder: WorkspaceLockHolder | None
    refusal_reason: str | None


def compute_clean_plan(
    layout: NamespaceLayout,
    *,
    keep_days: int = 7,
    now: datetime | None = None,
) -> CleanPlan:
    """Compute a read-only trace cleanup plan under the three protection layers."""

    _validate_keep_days(keep_days)
    now_utc = _normalize_now(now)
    cutoff_ts = now_utc - timedelta(days=keep_days)

    checkpoint = _load_checkpoint_if_present(layout)
    checkpoint_hash = _checkpoint_hash(checkpoint)
    lock_snapshot = _read_workspace_lock(layout)
    trace_lines, file_size_bytes = _scan_trace_lines(layout.trace_path)
    total_lines = len(trace_lines)

    protected_session_ids = set[str]()
    if checkpoint is not None:
        protected_session_ids.add(checkpoint.session_id)
    if lock_snapshot.active_holder is not None:
        protected_session_ids.add(lock_snapshot.active_holder.session_id)

    post_checkpoint_boundary_line = (
        None if checkpoint is None else checkpoint.trace_line_count
    )
    current_trial_protected_line_range = _current_trial_protected_line_range(
        checkpoint,
        total_lines=total_lines,
    )
    protected_line_ranges = _protected_line_ranges(
        layout,
        protected_session_ids=frozenset(protected_session_ids),
        current_trial_protected_line_range=current_trial_protected_line_range,
    )
    protected_sessions_hash = _protected_sessions_hash(
        protected_session_ids=frozenset(protected_session_ids),
        protected_line_ranges=protected_line_ranges,
        post_checkpoint_boundary_line=post_checkpoint_boundary_line,
        current_trial_protected_line_range=current_trial_protected_line_range,
    )

    refusal_reason = lock_snapshot.refusal_reason
    if checkpoint is not None and checkpoint.trace_line_count is None:
        refusal_reason = _combine_refusal(
            refusal_reason,
            "checkpoint lacks trace_line_count; reconcile trace checkpoint state "
            "before clean trace execution",
        )
    if (
        post_checkpoint_boundary_line is not None
        and post_checkpoint_boundary_line > total_lines
    ):
        refusal_reason = _combine_refusal(
            refusal_reason,
            "checkpoint trace_line_count is ahead of validated trace events",
        )
    if (
        checkpoint is not None
        and checkpoint.current_trial is not None
        and checkpoint.current_trial.operations
        and checkpoint.current_trial.current_trial_start_line is not None
        and checkpoint.current_trial.current_trial_start_line > total_lines
    ):
        refusal_reason = _combine_refusal(
            refusal_reason,
            "current_trial_start_line is ahead of validated trace events",
        )

    removable_lines = tuple(
        trace_line
        for trace_line in trace_lines
        if _is_removable_trace_line(
            trace_line,
            protected_line_ranges=protected_line_ranges,
            post_checkpoint_boundary_line=post_checkpoint_boundary_line,
            cutoff_ts=cutoff_ts,
        )
    )
    removable_line_ranges, removable_byte_ranges = _ranges_for_trace_lines(
        removable_lines
    )

    return CleanPlan(
        trace_path=layout.trace_path,
        total_lines=total_lines,
        file_size_bytes=file_size_bytes,
        protected_session_ids=frozenset(protected_session_ids),
        protected_line_ranges=protected_line_ranges,
        post_checkpoint_boundary_line=post_checkpoint_boundary_line,
        lock_status=lock_snapshot.status,
        blocking_lock_holder=lock_snapshot.blocking_holder,
        keep_days=keep_days,
        cutoff_ts=cutoff_ts,
        removable_line_ranges=removable_line_ranges,
        removable_byte_ranges=removable_byte_ranges,
        removable_event_count=len(removable_lines),
        refusal_reason=refusal_reason,
        checkpoint_hash=checkpoint_hash,
        protected_sessions_hash=protected_sessions_hash,
        current_trial_protected_line_range=current_trial_protected_line_range,
    )


def execute_clean_plan(
    layout: NamespaceLayout,
    plan: CleanPlan,
    *,
    force_inactive_only: bool = False,
    backup: bool = True,
    now: datetime | None = None,
) -> CleanResult:
    """Physically rewrite `trace/events.jsonl` according to an executable plan."""

    _validate_plan_for_layout(layout, plan)
    _require_plan_execution_allowed(
        plan,
        force_inactive_only=force_inactive_only,
    )

    with _execution_workspace_lock(
        layout,
        plan,
        force_inactive_only=force_inactive_only,
    ):
        _require_plan_still_matches_state(layout, plan)
        backup_path = _backup_trace_file(layout, plan, now=now) if backup else None
        _rewrite_trace_file(plan)

    return CleanResult(
        trace_path=plan.trace_path,
        removed_event_count=plan.removable_event_count,
        removed_line_ranges=plan.removable_line_ranges,
        removed_byte_ranges=plan.removable_byte_ranges,
        bytes_freed=sum(
            byte_range.end - byte_range.start
            for byte_range in plan.removable_byte_ranges
        ),
        backup_path=backup_path,
    )


def _validate_plan_for_layout(layout: NamespaceLayout, plan: CleanPlan) -> None:
    if plan.trace_path != layout.trace_path:
        raise CleanExecutionRefusedError(
            "clean plan trace_path does not match layout trace_path"
        )


def _require_plan_execution_allowed(
    plan: CleanPlan,
    *,
    force_inactive_only: bool,
) -> None:
    allowed = (
        plan.can_execute_with_force_inactive_only
        if force_inactive_only
        else plan.can_execute
    )
    if not allowed:
        detail = plan.refusal_reason or "clean plan is not executable"
        raise CleanExecutionRefusedError(detail)


@contextmanager
def _execution_workspace_lock(
    layout: NamespaceLayout,
    plan: CleanPlan,
    *,
    force_inactive_only: bool,
) -> Iterator[None]:
    lock = WorkspaceLock(layout.workspace)
    try:
        lock.acquire("agent clean trace", "agent_clean_trace")
    except WorkspaceBusyError as exc:
        if not _can_execute_under_existing_self_lock(
            plan,
            exc,
            force_inactive_only=force_inactive_only,
        ):
            raise
        yield
        return
    try:
        yield
    finally:
        lock.release()


def _can_execute_under_existing_self_lock(
    plan: CleanPlan,
    exc: WorkspaceBusyError,
    *,
    force_inactive_only: bool,
) -> bool:
    return (
        force_inactive_only
        and plan.lock_status == "held_by_self"
        and exc.holder is not None
        and _classify_lock_holder(exc.holder) == "held_by_self"
    )


def _require_plan_still_matches_state(layout: NamespaceLayout, plan: CleanPlan) -> None:
    _require_plan_still_matches_trace(plan)
    _require_plan_still_matches_checkpoint(layout, plan)
    _require_plan_still_matches_protected_sessions(layout, plan)


def _require_plan_still_matches_trace(plan: CleanPlan) -> None:
    total_lines = sum(1 for _ in iter_trace_events(plan.trace_path))
    try:
        file_size = plan.trace_path.stat().st_size
    except FileNotFoundError as exc:
        raise StaleCleanPlanError("trace file disappeared after planning") from exc
    if total_lines != plan.total_lines or file_size != plan.file_size_bytes:
        raise StaleCleanPlanError(
            "clean plan is stale; trace line count or file size changed"
        )


def _require_plan_still_matches_checkpoint(
    layout: NamespaceLayout,
    plan: CleanPlan,
) -> None:
    checkpoint = _load_checkpoint_if_present(layout)
    if _checkpoint_hash(checkpoint) != plan.checkpoint_hash:
        raise StaleCleanPlanError(
            "clean plan is stale; checkpoint changed after planning"
        )


def _require_plan_still_matches_protected_sessions(
    layout: NamespaceLayout,
    plan: CleanPlan,
) -> None:
    if plan.protected_sessions_hash is None:
        raise StaleCleanPlanError(
            "clean plan is stale; missing protected session snapshot"
        )
    checkpoint = _load_checkpoint_if_present(layout)
    current_trial_protected_line_range = _current_trial_protected_line_range(
        checkpoint,
        total_lines=plan.total_lines,
    )
    protected_line_ranges = _protected_line_ranges(
        layout,
        protected_session_ids=plan.protected_session_ids,
        current_trial_protected_line_range=current_trial_protected_line_range,
    )
    current_hash = _protected_sessions_hash(
        protected_session_ids=plan.protected_session_ids,
        protected_line_ranges=protected_line_ranges,
        post_checkpoint_boundary_line=(
            None if checkpoint is None else checkpoint.trace_line_count
        ),
        current_trial_protected_line_range=current_trial_protected_line_range,
    )
    if current_hash != plan.protected_sessions_hash:
        raise StaleCleanPlanError(
            "clean plan is stale; protected session boundaries changed"
        )


def _backup_trace_file(
    layout: NamespaceLayout,
    plan: CleanPlan,
    *,
    now: datetime | None,
) -> Path:
    backup_path = _unique_backup_path(layout.workspace, now=now)
    _atomic_copy_file(plan.trace_path, backup_path)
    return backup_path


def _unique_backup_path(workspace: Path, *, now: datetime | None) -> Path:
    timestamp = _timestamp_for_path(_normalize_now(now))
    backup_dir = workspace / "_trash" / timestamp
    backup_path = backup_dir / "events.jsonl"
    if not backup_path.exists():
        return backup_path
    suffix = 1
    while True:
        candidate = workspace / "_trash" / f"{timestamp}-{suffix}" / "events.jsonl"
        if not candidate.exists():
            return candidate
        suffix += 1


def _timestamp_for_path(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _atomic_copy_file(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.{os.getpid()}.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with source_path.open("rb") as source, os.fdopen(fd, "wb") as target:
            _copy_bytes(source, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, target_path)
        _fsync_parent_dir(target_path.parent)
    except Exception:
        _unlink_if_exists(temp_path)
        raise


def _rewrite_trace_file(plan: CleanPlan) -> None:
    target_path = plan.trace_path
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.{os.getpid()}.",
        suffix=".tmp",
        dir=target_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with target_path.open("rb") as source, os.fdopen(fd, "wb") as target:
            cursor = 0
            for byte_range in plan.removable_byte_ranges:
                source.seek(cursor)
                _copy_bytes(source, target, byte_range.start - cursor)
                cursor = byte_range.end
            source.seek(cursor)
            _copy_bytes(source, target)
            target.flush()
            os.fsync(target.fileno())
        _replace_file(temp_path, target_path)
        _fsync_parent_dir(target_path.parent)
    except Exception:
        _unlink_if_exists(temp_path)
        raise


def _copy_bytes(source: object, target: object, limit: int | None = None) -> None:
    remaining = limit
    while remaining is None or remaining > 0:
        chunk_size = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
        chunk = source.read(chunk_size)
        if not chunk:
            break
        target.write(chunk)
        if remaining is not None:
            remaining -= len(chunk)


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _validate_keep_days(keep_days: int) -> None:
    _require_int(keep_days, "keep_days")
    if keep_days < 0:
        raise TraceCleanupError("keep_days must be >= 0")


def _require_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TraceCleanupError(f"{name} must be an integer")


def _normalize_now(now: datetime | None) -> datetime:
    value = datetime.now(UTC) if now is None else now
    if value.tzinfo is None or value.utcoffset() is None:
        raise TraceCleanupError("now must be timezone-aware")
    return value.astimezone(UTC)


def _load_checkpoint_if_present(layout: NamespaceLayout) -> CheckpointState | None:
    if not layout.checkpoint_path.exists():
        return None
    return load_checkpoint_for_layout(layout)


def _read_workspace_lock(layout: NamespaceLayout) -> _LockSnapshot:
    lock = WorkspaceLock(layout.workspace)
    if not lock.lock_path.exists():
        return _LockSnapshot(
            status="free",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=None,
        )

    probe = lock.probe_lock()
    if probe.error is not None:
        return _LockSnapshot(
            status="unknown",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=f"workspace lock state could not be probed: {probe.error}",
        )

    holder_result = lock.read_holder()
    holder = holder_result.holder
    if holder is None:
        reason = holder_result.error or "workspace lock holder is unavailable"
        return _LockSnapshot(
            status="unknown",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=f"workspace lock metadata could not be read: {reason}",
        )

    if not probe.is_locked:
        return _LockSnapshot(
            status="free",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=None,
        )

    status = _classify_lock_holder(holder)
    if status == "free":
        return _LockSnapshot(
            status="unknown",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=(
                "workspace lock is held but holder metadata does not match "
                "a live agent process"
            ),
        )
    if status == "held_by_self":
        return _LockSnapshot(
            status="held_by_self",
            active_holder=holder,
            blocking_holder=None,
            refusal_reason=None,
        )
    return _LockSnapshot(
        status="held_by_other",
        active_holder=holder,
        blocking_holder=holder,
        refusal_reason="workspace lock is held by another agent process",
    )


def _classify_lock_holder(holder: WorkspaceLockHolder) -> LockStatus:
    try:
        process_create_time = psutil.Process(holder.pid).create_time()
    except psutil.NoSuchProcess:
        return "free"
    except psutil.Error:
        return "held_by_other"
    if (
        abs(process_create_time - holder.create_time)
        > _LOCK_CREATE_TIME_TOLERANCE_SECONDS
    ):
        return "free"
    if holder.pid == os.getpid():
        return "held_by_self"
    return "held_by_other"


def _scan_trace_lines(path: Path) -> tuple[tuple[_TraceLine, ...], int]:
    events = tuple(iter_trace_events(path))
    if not path.exists():
        return (), 0

    byte_ranges: list[tuple[int, int]] = []
    offset = 0
    with path.open("rb") as handle:
        for raw_line in handle:
            next_offset = offset + len(raw_line)
            byte_ranges.append((offset, next_offset))
            offset = next_offset

    if len(byte_ranges) != len(events):
        raise TraceCleanupError(
            "trace changed while computing clean plan; retry after the writer is idle"
        )

    return (
        tuple(
            _TraceLine(
                line_number=index,
                byte_start=start,
                byte_end=end,
                event=event,
            )
            for index, ((start, end), event) in enumerate(
                zip(byte_ranges, events),
                start=1,
            )
        ),
        offset,
    )


def _protected_line_ranges(
    layout: NamespaceLayout,
    *,
    protected_session_ids: frozenset[str],
    current_trial_protected_line_range: LineRange | None,
) -> tuple[LineRange, ...]:
    session_spans = inspect_trace_session_spans(layout)
    ranges = [
        LineRange(
            first=span.first_line_number,
            last=span.last_line_number,
        )
        for span in session_spans
        if span.session_id in protected_session_ids
    ]
    if current_trial_protected_line_range is not None:
        ranges.append(current_trial_protected_line_range)
    return _merge_line_ranges(ranges)


def _current_trial_protected_line_range(
    checkpoint: CheckpointState | None,
    *,
    total_lines: int,
) -> LineRange | None:
    if checkpoint is None or checkpoint.current_trial is None:
        return None
    current_trial = checkpoint.current_trial
    if not current_trial.operations:
        return None
    start_line = current_trial.current_trial_start_line
    if start_line is None or start_line > total_lines:
        return None
    return LineRange(first=start_line, last=total_lines)


def _checkpoint_hash(checkpoint: CheckpointState | None) -> str | None:
    if checkpoint is None:
        return None
    return _stable_sha256(checkpoint_payload(checkpoint))


def _protected_sessions_hash(
    *,
    protected_session_ids: frozenset[str],
    protected_line_ranges: tuple[LineRange, ...],
    post_checkpoint_boundary_line: int | None,
    current_trial_protected_line_range: LineRange | None,
) -> str:
    return _stable_sha256(
        {
            "protected_session_ids": sorted(protected_session_ids),
            "protected_line_ranges": [
                {"first": item.first, "last": item.last}
                for item in protected_line_ranges
            ],
            "post_checkpoint_boundary_line": post_checkpoint_boundary_line,
            "current_trial_protected_line_range": (
                None
                if current_trial_protected_line_range is None
                else {
                    "first": current_trial_protected_line_range.first,
                    "last": current_trial_protected_line_range.last,
                }
            ),
        }
    )


def _stable_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_removable_trace_line(
    trace_line: _TraceLine,
    *,
    protected_line_ranges: tuple[LineRange, ...],
    post_checkpoint_boundary_line: int | None,
    cutoff_ts: datetime,
) -> bool:
    if _line_is_in_ranges(trace_line.line_number, protected_line_ranges):
        return False
    if (
        post_checkpoint_boundary_line is not None
        and trace_line.line_number > post_checkpoint_boundary_line
    ):
        return False
    event_ts = _parse_event_ts(trace_event_payload(trace_line.event)["ts"])
    return event_ts < cutoff_ts


def _parse_event_ts(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC)


def _line_is_in_ranges(line_number: int, ranges: tuple[LineRange, ...]) -> bool:
    return any(item.first <= line_number <= item.last for item in ranges)


def _merge_line_ranges(ranges: Iterable[LineRange]) -> tuple[LineRange, ...]:
    sorted_ranges = sorted(ranges, key=lambda item: (item.first, item.last))
    merged: list[LineRange] = []
    for item in sorted_ranges:
        if not merged or item.first > merged[-1].last + 1:
            merged.append(item)
            continue
        previous = merged[-1]
        merged[-1] = LineRange(
            first=previous.first,
            last=max(previous.last, item.last),
        )
    return tuple(merged)


def _ranges_for_trace_lines(
    trace_lines: tuple[_TraceLine, ...],
) -> tuple[tuple[LineRange, ...], tuple[ByteRange, ...]]:
    if not trace_lines:
        return (), ()

    line_ranges: list[LineRange] = []
    byte_ranges: list[ByteRange] = []
    first_line = previous_line = trace_lines[0]

    for current in trace_lines[1:]:
        if (
            current.line_number == previous_line.line_number + 1
            and current.byte_start == previous_line.byte_end
        ):
            previous_line = current
            continue
        line_ranges.append(
            LineRange(first=first_line.line_number, last=previous_line.line_number)
        )
        byte_ranges.append(
            ByteRange(start=first_line.byte_start, end=previous_line.byte_end)
        )
        first_line = previous_line = current

    line_ranges.append(
        LineRange(first=first_line.line_number, last=previous_line.line_number)
    )
    byte_ranges.append(
        ByteRange(start=first_line.byte_start, end=previous_line.byte_end)
    )
    return tuple(line_ranges), tuple(byte_ranges)


def _combine_refusal(current: str | None, reason: str) -> str:
    if current is None:
        return reason
    return f"{current}; {reason}"


def _fsync_parent_dir(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", None)
    if flags is None:
        return
    dir_fd = os.open(path, os.O_RDONLY | flags)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
