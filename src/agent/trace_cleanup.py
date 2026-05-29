"""Read-only trace cleanup planning helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable, Literal

import psutil

from .fs_memory import (
    CheckpointState,
    NamespaceLayout,
    TraceError,
    TraceEvent,
    iter_trace_events,
    load_checkpoint_for_layout,
    trace_event_payload,
)
from .trace import inspect_trace_session_spans
from .workspace_lock import WorkspaceLock, WorkspaceLockHolder


LockStatus = Literal["free", "held_by_self", "held_by_other"]
_LOCK_CREATE_TIME_TOLERANCE_SECONDS = 0.5


class TraceCleanupError(TraceError):
    """Raised when a trace cleanup plan cannot be computed safely."""


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
    lock_snapshot = _read_workspace_lock(layout)
    trace_lines, file_size_bytes = _scan_trace_lines(layout.trace_path)
    total_lines = len(trace_lines)

    protected_session_ids = set[str]()
    if checkpoint is not None:
        protected_session_ids.add(checkpoint.session_id)
    if lock_snapshot.active_holder is not None:
        protected_session_ids.add(lock_snapshot.active_holder.session_id)

    session_spans = inspect_trace_session_spans(layout)
    protected_line_ranges = _merge_line_ranges(
        LineRange(
            first=span.first_line_number,
            last=span.last_line_number,
        )
        for span in session_spans
        if span.session_id in protected_session_ids
    )
    post_checkpoint_boundary_line = (
        None if checkpoint is None else checkpoint.trace_line_count
    )

    refusal_reason = lock_snapshot.refusal_reason
    if (
        post_checkpoint_boundary_line is not None
        and post_checkpoint_boundary_line > total_lines
    ):
        refusal_reason = _combine_refusal(
            refusal_reason,
            "checkpoint trace_line_count is ahead of validated trace events",
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
    )


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

    holder_result = lock.read_holder()
    holder = holder_result.holder
    if holder is None:
        reason = holder_result.error or "workspace lock holder is unavailable"
        return _LockSnapshot(
            status="free",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=f"workspace lock metadata could not be read: {reason}",
        )

    status = _classify_lock_holder(holder)
    if status == "free":
        return _LockSnapshot(
            status="free",
            active_holder=None,
            blocking_holder=None,
            refusal_reason=None,
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
