"""Trace producer helpers built on the canonical JSONL writer."""

from __future__ import annotations

from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
import math
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from .fs_memory import (
    CheckpointState,
    NamespaceLayout,
    TraceAppendResult,
    TraceError,
    append_trace_event,
    checkpoint_payload,
    iter_trace_events,
    trace_event_payload,
    write_checkpoint_state,
)
from .identifiers import validate_session_id_atom


class TraceSessionError(TraceError):
    """Raised when a trace producer would emit inconsistent session metadata."""


_REJECTION_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "duplicate_hash": ("matched_trial",),
    "whitelist_unknown_option": ("unknown_options",),
    "mutual_exclusion": ("conflict_group", "conflicting_options"),
    "failed_subset_match": ("matched_failed", "matched_failed_path"),
    "experience_hard_filter": (
        "matched_rule_id",
        "matched_rule_path",
        "filter_strength",
    ),
    "experience_soft_filter_with_low_score": (
        "matched_rule_id",
        "matched_rule_path",
        "filter_strength",
        "penalty",
        "score_after_penalty",
    ),
    "module_incompatibility": ("matched_failed", "matched_failed_path"),
}
_REJECTION_STRING_FIELDS = frozenset(
    {
        "conflict_group",
        "filter_strength",
        "matched_failed",
        "matched_failed_path",
        "matched_rule_id",
        "matched_rule_path",
        "matched_trial",
    }
)
_REJECTION_SEQUENCE_FIELDS = frozenset(
    {
        "conflicting_options",
        "unknown_options",
    }
)
TraceCheckpointAlignmentStatus = Literal[
    "aligned",
    "checkpoint_missing",
    "trace_ahead",
    "checkpoint_ahead",
]


def count_trace_events(path: str | Path) -> int:
    """Return the number of validated events currently in `events.jsonl`."""

    return sum(1 for _ in iter_trace_events(path))


def checkpoint_with_trace_line_count(
    checkpoint: CheckpointState | Mapping[str, Any],
    *,
    trace_line_count: int,
) -> dict[str, Any]:
    """Return a checkpoint payload updated with the current trace line count."""

    if (
        not isinstance(trace_line_count, int)
        or isinstance(trace_line_count, bool)
        or trace_line_count < 0
    ):
        raise TraceSessionError("trace_line_count must be a non-negative integer")
    validated = CheckpointState.model_validate(checkpoint)
    if (
        validated.trace_line_count is not None
        and trace_line_count < validated.trace_line_count
    ):
        raise TraceSessionError("trace_line_count cannot move backward")

    payload = checkpoint_payload(validated)
    payload["trace_line_count"] = trace_line_count
    return payload


@dataclass(frozen=True)
class TraceCheckpointAlignment:
    """Trace/checkpoint line-count relationship for doctor-style checks."""

    checkpoint: CheckpointState
    checkpoint_trace_line_count: int | None
    actual_trace_line_count: int
    status: TraceCheckpointAlignmentStatus

    @property
    def needs_reconcile(self) -> bool:
        return self.status != "aligned"

    @property
    def can_reconcile(self) -> bool:
        return self.status in {"checkpoint_missing", "trace_ahead"}


@dataclass(frozen=True)
class TraceSessionSpan:
    """Line range occupied by one session in a canonical trace file."""

    session_id: str
    first_line_number: int
    last_line_number: int
    event_count: int


def inspect_trace_checkpoint_alignment(
    layout: NamespaceLayout,
    checkpoint: CheckpointState | Mapping[str, Any],
) -> TraceCheckpointAlignment:
    """Scan trace non-hot-path and compare it with checkpoint line metadata."""

    state = CheckpointState.model_validate(checkpoint)
    _validate_checkpoint_namespace(layout, state)
    actual_count = count_trace_events(layout.trace_path)
    checkpoint_count = state.trace_line_count
    if checkpoint_count is None:
        status: TraceCheckpointAlignmentStatus = "checkpoint_missing"
    elif checkpoint_count == actual_count:
        status = "aligned"
    elif checkpoint_count < actual_count:
        status = "trace_ahead"
    else:
        status = "checkpoint_ahead"
    return TraceCheckpointAlignment(
        checkpoint=state,
        checkpoint_trace_line_count=checkpoint_count,
        actual_trace_line_count=actual_count,
        status=status,
    )


def inspect_trace_session_spans(
    layout_or_path: NamespaceLayout | str | Path,
) -> tuple[TraceSessionSpan, ...]:
    """Return conservative session line spans from a validated trace file.

    This helper scans `events.jsonl` for doctor/status/clean planning paths.
    Events without `session_id` are ignored for backwards compatibility with
    low-level trace tests and early bootstrap events. If a session appears in
    non-contiguous chunks, the span covers the first through last occurrence so
    later cleanup code can preserve conservatively.
    """

    trace_path = (
        layout_or_path.trace_path
        if isinstance(layout_or_path, NamespaceLayout)
        else Path(layout_or_path)
    )
    spans: dict[str, TraceSessionSpan] = {}
    for line_number, event in enumerate(iter_trace_events(trace_path), start=1):
        payload = trace_event_payload(event)
        raw_session_id = payload.get("session_id")
        if raw_session_id is None:
            continue
        session_id = validate_session_id_atom(
            raw_session_id,
            "trace session_id",
            error_type=TraceSessionError,
        )
        previous = spans.get(session_id)
        if previous is None:
            spans[session_id] = TraceSessionSpan(
                session_id=session_id,
                first_line_number=line_number,
                last_line_number=line_number,
                event_count=1,
            )
        else:
            spans[session_id] = TraceSessionSpan(
                session_id=session_id,
                first_line_number=previous.first_line_number,
                last_line_number=line_number,
                event_count=previous.event_count + 1,
            )
    return tuple(sorted(spans.values(), key=lambda span: span.first_line_number))


def checkpoint_with_reconciled_trace_count(
    layout: NamespaceLayout,
    checkpoint: CheckpointState | Mapping[str, Any],
) -> dict[str, Any]:
    """Return checkpoint payload reconciled to the validated trace line count.

    This helper intentionally scans `events.jsonl`, so it belongs to doctor,
    resume repair, or explicit validation paths rather than hot event append
    paths. If checkpoint claims more lines than the trace currently contains,
    the trace may have been truncated; callers should fail conservative.
    """

    alignment = inspect_trace_checkpoint_alignment(layout, checkpoint)
    if alignment.status == "checkpoint_ahead":
        raise TraceSessionError(
            "checkpoint trace_line_count is ahead of trace events "
            f"(checkpoint={alignment.checkpoint_trace_line_count}, "
            f"actual={alignment.actual_trace_line_count})"
        )
    if alignment.status == "aligned":
        return checkpoint_payload(alignment.checkpoint)
    return checkpoint_with_trace_line_count(
        alignment.checkpoint,
        trace_line_count=alignment.actual_trace_line_count,
    )


@dataclass
class TraceSessionWriter:
    """Lock-scoped trace producer that injects session context and line numbers."""

    layout: NamespaceLayout
    session_id: str
    dry_run: bool = False
    next_line_number: int = 1

    def __post_init__(self) -> None:
        validate_session_id_atom(
            self.session_id,
            "session_id",
            error_type=TraceSessionError,
        )
        if self.next_line_number <= 0:
            raise TraceSessionError("next_line_number must be positive")

    @classmethod
    def for_layout(
        cls,
        layout: NamespaceLayout,
        *,
        session_id: str,
        dry_run: bool = False,
        next_line_number: int | None = None,
    ) -> TraceSessionWriter:
        if next_line_number is None:
            next_line_number = count_trace_events(layout.trace_path) + 1
        return cls(
            layout=layout,
            session_id=session_id,
            dry_run=dry_run,
            next_line_number=next_line_number,
        )

    @classmethod
    def for_checkpoint(
        cls,
        layout: NamespaceLayout,
        checkpoint: CheckpointState | Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> TraceSessionWriter:
        """Create a writer from canonical checkpoint recovery state.

        New checkpoints carry `trace_line_count` so resume can restore the
        line counter without scanning `events.jsonl`. Older checkpoints that
        lack the field fall back to validated trace counting.

        Workflow code must update and persist `checkpoint.trace_line_count`
        after successful trace appends while holding the same workspace lock
        that serializes the session writer. If a crash happens after a trace
        append but before checkpoint persistence, line-based `trace_id` values
        may be offset on resume; byte-offset references remain accurate.
        """

        state = CheckpointState.model_validate(checkpoint)
        _validate_checkpoint_namespace(layout, state)
        if state.trace_line_count is None:
            next_line_number = count_trace_events(layout.trace_path) + 1
        else:
            next_line_number = state.trace_line_count + 1
        return cls(
            layout=layout,
            session_id=state.session_id,
            dry_run=dry_run,
            next_line_number=next_line_number,
        )

    @property
    def trace_line_count(self) -> int:
        return self.next_line_number - 1

    def checkpoint_with_current_trace_count(
        self,
        checkpoint: CheckpointState | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return checkpoint data updated to this writer's current trace line."""

        return checkpoint_with_trace_line_count(
            checkpoint,
            trace_line_count=self.trace_line_count,
        )

    def append(
        self,
        kind: str,
        *,
        ts: datetime | str | None = None,
        **fields: Any,
    ) -> TraceAppendResult:
        """Append one event with session metadata and a lock-protected line id."""

        event = self._event_payload(kind, ts=ts, fields=fields)
        result = append_trace_event(
            self.layout,
            event,
            expected_line_number=self.next_line_number,
        )
        self.next_line_number += 1
        return result

    def round_start(self, *, round: int, phase: str, **fields: Any) -> TraceAppendResult:
        return self.append("round_start", round=round, phase=phase, **fields)

    def candidate_generation(
        self,
        *,
        generator: str,
        candidates_count: int,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            "candidate_generation",
            generator=generator,
            candidates_count=candidates_count,
            **fields,
        )

    def candidate_rejected(
        self,
        *,
        candidate: Sequence[str],
        generator: str,
        rejection_reason: str,
        candidate_hash: str | None = None,
        **fields: Any,
    ) -> TraceAppendResult:
        _validate_candidate_rejection(rejection_reason, fields)
        payload: dict[str, Any] = {
            "candidate": list(candidate),
            "generator": generator,
            "rejection_reason": rejection_reason,
            **fields,
        }
        if candidate_hash is not None:
            payload["candidate_hash"] = candidate_hash
        return self.append(
            "candidate_rejected",
            **payload,
        )

    def trial_start(
        self,
        *,
        trial_id: str,
        combo: Sequence[str],
        mode: str,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            "trial_start",
            trial_id=trial_id,
            combo=list(combo),
            mode=mode,
            **fields,
        )

    def trial_end(
        self,
        *,
        trial_id: str,
        outcome: str,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append("trial_end", trial_id=trial_id, outcome=outcome, **fields)

    def trial_yaml_written(self, *, path: str | Path, **fields: Any) -> TraceAppendResult:
        return self.append("trial_yaml_written", path=Path(path).as_posix(), **fields)

    def skill_span(
        self,
        *,
        skill: str,
        duration_ms: int,
        success: bool,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            "skill_span",
            skill=skill,
            duration_ms=duration_ms,
            success=success,
            **fields,
        )

    def process_event(
        self,
        kind: str,
        *,
        pid: int,
        pgid: int,
        create_time: float,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            kind,
            pid=pid,
            pgid=pgid,
            create_time=create_time,
            **fields,
        )

    def llm_call(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        **fields: Any,
    ) -> TraceAppendResult:
        _require_non_negative_int(prompt_tokens, "prompt_tokens")
        _require_non_negative_int(completion_tokens, "completion_tokens")
        return self.append(
            "llm_call",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            **fields,
        )

    def memory_op(
        self,
        *,
        op_type: str,
        path: str | Path,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            "memory_op",
            op_type=op_type,
            path=Path(path).as_posix(),
            **fields,
        )

    def kg_op(
        self,
        *,
        op_id: str,
        op_type: str,
        backup_ref: str | None = None,
        **fields: Any,
    ) -> TraceAppendResult:
        payload: dict[str, Any] = {
            "op_id": op_id,
            "op_type": op_type,
            **fields,
        }
        if backup_ref is not None:
            payload["backup_ref"] = backup_ref
        return self.append("kg_op", **payload)

    def user_action(
        self,
        *,
        command: str,
        args: Sequence[str] | None = None,
        **fields: Any,
    ) -> TraceAppendResult:
        payload: dict[str, Any] = {"command": command, **fields}
        if args is not None:
            payload["args"] = list(args)
        return self.append("user_action", **payload)

    def workspace_snapshot(
        self,
        *,
        phase: str,
        ws_hash: str,
        **fields: Any,
    ) -> TraceAppendResult:
        if phase not in {"pre", "post"}:
            raise TraceSessionError("workspace snapshot phase must be 'pre' or 'post'")
        return self.append(
            f"workspace_snapshot_{phase}",
            ws_hash=ws_hash,
            **fields,
        )

    def _event_payload(
        self,
        kind: str,
        *,
        ts: datetime | str | None,
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = dict(fields)
        _reject_context_overrides(payload)
        if self.dry_run:
            requested_mode = payload.get("mode")
            if requested_mode not in {None, "dry_run"}:
                raise TraceSessionError(
                    "dry-run trace events must use mode='dry_run'; "
                    "store trial mode in a different field"
                )
            payload["mode"] = "dry_run"

        return {
            "ts": datetime.now(UTC) if ts is None else ts,
            "kind": kind,
            "session_id": self.session_id,
            "namespace": str(self.layout.namespace),
            **payload,
        }


@dataclass(frozen=True)
class TraceCheckpointResult:
    """Result of an append followed by checkpoint persistence."""

    trace: TraceAppendResult
    checkpoint_path: Path
    checkpoint: CheckpointState


@dataclass
class TraceCheckpointWriter:
    """Workflow helper that preserves trace -> checkpoint ordering.

    Callers must use this while holding the workspace lock. The helper appends
    the trace event first, then persists `checkpoint.trace_line_count` with the
    writer's current line count. This encodes the crash-consistency contract
    documented on `TraceSessionWriter.for_checkpoint()`.
    """

    writer: TraceSessionWriter
    checkpoint: CheckpointState

    def __post_init__(self) -> None:
        self.checkpoint = self._validate_checkpoint_context(self.checkpoint)

    @classmethod
    def for_checkpoint(
        cls,
        layout: NamespaceLayout,
        checkpoint: CheckpointState | Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> TraceCheckpointWriter:
        state = CheckpointState.model_validate(checkpoint)
        writer = TraceSessionWriter.for_checkpoint(
            layout,
            state,
            dry_run=dry_run,
        )
        return cls(writer=writer, checkpoint=state)

    @property
    def trace_line_count(self) -> int:
        return self.writer.trace_line_count

    def append_and_checkpoint(
        self,
        kind: str,
        *,
        checkpoint: CheckpointState | Mapping[str, Any] | None = None,
        ts: datetime | str | None = None,
        **fields: Any,
    ) -> TraceCheckpointResult:
        """Append an event, then persist checkpoint with the updated trace line.

        If checkpoint persistence fails after the append succeeds, the trace
        event is already durable. Callers should not blindly retry the same
        logical event; rebuild or reconcile session state first.
        """

        checkpoint_state = self._validate_checkpoint_context(
            self.checkpoint if checkpoint is None else checkpoint
        )
        trace_result = self.writer.append(kind, ts=ts, **fields)
        checkpoint_data = self.writer.checkpoint_with_current_trace_count(
            checkpoint_state
        )
        checkpoint_path = write_checkpoint_state(self.writer.layout, checkpoint_data)
        self.checkpoint = CheckpointState.model_validate(checkpoint_data)
        return TraceCheckpointResult(
            trace=trace_result,
            checkpoint_path=checkpoint_path,
            checkpoint=self.checkpoint,
        )

    def _validate_checkpoint_context(
        self,
        checkpoint: CheckpointState | Mapping[str, Any],
    ) -> CheckpointState:
        state = CheckpointState.model_validate(checkpoint)
        expected_namespace = str(self.writer.layout.namespace)
        if state.namespace != expected_namespace:
            raise TraceSessionError(
                "checkpoint namespace does not match layout "
                f"(expected={expected_namespace!r}, actual={state.namespace!r})"
            )
        if state.session_id != self.writer.session_id:
            raise TraceSessionError(
                "checkpoint session_id does not match trace writer "
                f"(expected={self.writer.session_id!r}, actual={state.session_id!r})"
            )
        return state


def _reject_context_overrides(payload: Mapping[str, Any]) -> None:
    for key in ("session_id", "namespace"):
        if key in payload:
            raise TraceSessionError(f"trace field {key!r} is managed by TraceSessionWriter")


def _validate_checkpoint_namespace(
    layout: NamespaceLayout,
    checkpoint: CheckpointState,
) -> None:
    expected_namespace = str(layout.namespace)
    if checkpoint.namespace != expected_namespace:
        raise TraceSessionError(
            "checkpoint namespace does not match layout "
            f"(expected={expected_namespace!r}, actual={checkpoint.namespace!r})"
        )


def _validate_candidate_rejection(
    rejection_reason: str,
    payload: Mapping[str, Any],
) -> None:
    required_fields = _REJECTION_REQUIRED_FIELDS.get(rejection_reason)
    if required_fields is None:
        raise TraceSessionError(f"unknown candidate rejection reason: {rejection_reason!r}")
    missing = [field for field in required_fields if field not in payload]
    if missing:
        joined = ", ".join(missing)
        raise TraceSessionError(
            f"candidate_rejected {rejection_reason!r} missing required field(s): {joined}"
        )
    for field in required_fields:
        _require_rejection_field_value(field, payload[field])

    if rejection_reason == "experience_hard_filter":
        _require_filter_strength(payload, "hard")
    elif rejection_reason == "experience_soft_filter_with_low_score":
        _require_filter_strength(payload, "soft")
        for field in ("penalty", "score_after_penalty"):
            _require_finite_number(payload[field], field)


def _require_filter_strength(payload: Mapping[str, Any], expected: str) -> None:
    if payload.get("filter_strength") != expected:
        raise TraceSessionError(f"filter_strength must be {expected!r}")


def _require_finite_number(value: Any, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
    ):
        raise TraceSessionError(f"{field} must be a finite number")


def _require_non_negative_int(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TraceSessionError(f"{field} must be a non-negative integer")


def _require_rejection_field_value(field: str, value: Any) -> None:
    if field in _REJECTION_STRING_FIELDS:
        if not isinstance(value, str) or not value.strip():
            raise TraceSessionError(f"{field} must be a non-empty string")
        return
    if field in _REJECTION_SEQUENCE_FIELDS:
        if (
            not isinstance(value, SequenceABC)
            or isinstance(value, str | bytes)
            or not value
        ):
            raise TraceSessionError(f"{field} must be a non-empty list")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise TraceSessionError(f"{field} must contain non-empty strings")
        return
    if value is None:
        raise TraceSessionError(f"{field} must not be null")
