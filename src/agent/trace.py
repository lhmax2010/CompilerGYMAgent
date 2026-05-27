"""Trace producer helpers built on the canonical JSONL writer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .fs_memory import (
    CheckpointState,
    NamespaceLayout,
    TraceAppendResult,
    TraceError,
    append_trace_event,
    checkpoint_payload,
    iter_trace_events,
)


class TraceSessionError(TraceError):
    """Raised when a trace producer would emit inconsistent session metadata."""


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


@dataclass
class TraceSessionWriter:
    """Lock-scoped trace producer that injects session context and line numbers."""

    layout: NamespaceLayout
    session_id: str
    dry_run: bool = False
    next_line_number: int = 1

    def __post_init__(self) -> None:
        _validate_session_id(self.session_id)
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
        """

        state = CheckpointState.model_validate(checkpoint)
        expected_namespace = str(layout.namespace)
        if state.namespace != expected_namespace:
            raise TraceSessionError(
                "checkpoint namespace does not match layout "
                f"(expected={expected_namespace!r}, actual={state.namespace!r})"
            )
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
        rejection_reason: str,
        **fields: Any,
    ) -> TraceAppendResult:
        return self.append(
            "candidate_rejected",
            candidate=list(candidate),
            rejection_reason=rejection_reason,
            **fields,
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


def _reject_context_overrides(payload: Mapping[str, Any]) -> None:
    for key in ("session_id", "namespace"):
        if key in payload:
            raise TraceSessionError(f"trace field {key!r} is managed by TraceSessionWriter")


def _validate_session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise TraceSessionError("session_id must be a non-empty string")
    if value != value.strip():
        raise TraceSessionError("session_id cannot contain surrounding whitespace")
    if value in {".", ".."}:
        raise TraceSessionError(f"session_id cannot be {value!r}")
    if "/" in value or "\\" in value:
        raise TraceSessionError("session_id cannot contain path separators")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise TraceSessionError("session_id cannot contain control characters")
    if not all(char.isascii() and (char.isalnum() or char in "_-") for char in value):
        raise TraceSessionError(
            "session_id can contain only ASCII letters, digits, '_' or '-'"
        )
