"""Read-only checkpoint/trace/process lease consistency diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import ValidationError

from ..errors import AgentError, EXIT_VALIDATION
from ..fs_memory import (
    CheckpointLoadError,
    CheckpointState,
    NamespaceLayout,
    TraceError,
    iter_trace_events,
    load_checkpoint_for_layout,
    trace_event_payload,
)
from ..process_registry import (
    ProcessLease,
    ProcessRegistryError,
    iter_process_lease_paths,
    load_process_lease,
)
from ..trace import (
    TraceCheckpointAlignment,
    TraceSessionSpan,
    inspect_trace_checkpoint_alignment,
    inspect_trace_session_spans,
)


StateConsistencySeverity = Literal["info", "warning", "error"]


class StateConsistencyError(AgentError):
    """Raised when state consistency diagnostics cannot be configured."""

    exit_code = EXIT_VALIDATION


@dataclass(frozen=True)
class StateConsistencyIssue:
    """One read-only doctor finding with an actionable repair hint."""

    code: str
    severity: StateConsistencySeverity
    message: str
    repair_suggestion: str
    details: dict[str, Any]


@dataclass(frozen=True)
class StateConsistencyReport:
    """Checkpoint/trace/process lease consistency snapshot."""

    layout: NamespaceLayout
    checkpoint: CheckpointState | None
    trace_alignment: TraceCheckpointAlignment | None
    session_spans: tuple[TraceSessionSpan, ...]
    process_leases: tuple[ProcessLease, ...]
    issues: tuple[StateConsistencyIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)

    def issues_with_severity(
        self,
        severity: StateConsistencySeverity,
    ) -> tuple[StateConsistencyIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == severity)


def inspect_state_consistency(layout: NamespaceLayout) -> StateConsistencyReport:
    """Inspect checkpoint, trace, and process lease state without mutation."""

    issues: list[StateConsistencyIssue] = []
    checkpoint = _load_checkpoint(layout, issues)
    trace_alignment = _inspect_trace_alignment(layout, checkpoint, issues)
    session_spans = _inspect_session_spans(layout, issues)
    process_leases, lease_paths = _load_process_leases(layout, issues)

    if checkpoint is not None:
        _inspect_trace_checkpoint_relationship(
            checkpoint,
            trace_alignment,
            session_spans,
            issues,
        )
        _inspect_current_trial_trace(layout, checkpoint, trace_alignment, issues)
        _inspect_process_refs(
            layout,
            checkpoint,
            lease_paths,
            issues,
        )
        _inspect_orphan_leases(
            layout,
            checkpoint,
            process_leases,
            issues,
        )

    return StateConsistencyReport(
        layout=layout,
        checkpoint=checkpoint,
        trace_alignment=trace_alignment,
        session_spans=session_spans,
        process_leases=process_leases,
        issues=tuple(issues),
    )


def _load_checkpoint(
    layout: NamespaceLayout,
    issues: list[StateConsistencyIssue],
) -> CheckpointState | None:
    try:
        return load_checkpoint_for_layout(layout)
    except CheckpointLoadError as exc:
        issues.append(
            _issue(
                code="checkpoint_load_error",
                severity="error",
                message=f"checkpoint could not be loaded: {exc}",
                repair="Restore checkpoint.yaml from backup or run resume/doctor repair once available.",
                path=layout.checkpoint_path,
            )
        )
        return None


def _inspect_trace_alignment(
    layout: NamespaceLayout,
    checkpoint: CheckpointState | None,
    issues: list[StateConsistencyIssue],
) -> TraceCheckpointAlignment | None:
    if checkpoint is None:
        return None
    try:
        alignment = inspect_trace_checkpoint_alignment(layout, checkpoint)
    except (TraceError, ValidationError, ValueError) as exc:
        issues.append(
            _issue(
                code="trace_alignment_error",
                severity="error",
                message=f"trace/checkpoint alignment could not be inspected: {exc}",
                repair="Inspect events.jsonl and checkpoint.yaml, then rerun doctor trace.",
                path=layout.trace_path,
            )
        )
        return None
    if alignment.status == "checkpoint_missing":
        issues.append(
            _issue(
                code="trace_line_count_missing",
                severity="warning",
                message="checkpoint is missing trace_line_count",
                repair="Run doctor trace reconciliation before mutating or cleaning trace state.",
                actual_trace_line_count=alignment.actual_trace_line_count,
            )
        )
    elif alignment.status == "trace_ahead":
        issues.append(
            _issue(
                code="trace_ahead",
                severity="warning",
                message="trace has events beyond checkpoint.trace_line_count",
                repair="Run trace/checkpoint reconciliation before resume or cleanup.",
                checkpoint_trace_line_count=alignment.checkpoint_trace_line_count,
                actual_trace_line_count=alignment.actual_trace_line_count,
            )
        )
    elif alignment.status == "checkpoint_ahead":
        issues.append(
            _issue(
                code="checkpoint_ahead",
                severity="error",
                message="checkpoint.trace_line_count is ahead of validated trace events",
                repair="Fail conservative: inspect trace truncation or restore trace from backup.",
                checkpoint_trace_line_count=alignment.checkpoint_trace_line_count,
                actual_trace_line_count=alignment.actual_trace_line_count,
            )
        )
    return alignment


def _inspect_session_spans(
    layout: NamespaceLayout,
    issues: list[StateConsistencyIssue],
) -> tuple[TraceSessionSpan, ...]:
    try:
        return inspect_trace_session_spans(layout)
    except (TraceError, ValueError) as exc:
        issues.append(
            _issue(
                code="trace_session_spans_error",
                severity="error",
                message=f"trace session spans could not be inspected: {exc}",
                repair="Fix events.jsonl validation errors before resume, status, or cleanup.",
                path=layout.trace_path,
            )
        )
        return ()


def _load_process_leases(
    layout: NamespaceLayout,
    issues: list[StateConsistencyIssue],
) -> tuple[tuple[ProcessLease, ...], dict[str, ProcessLease]]:
    leases: list[ProcessLease] = []
    by_ref: dict[str, ProcessLease] = {}
    for path in iter_process_lease_paths(layout):
        try:
            lease = load_process_lease(path)
        except ProcessRegistryError as exc:
            issues.append(
                _issue(
                    code="process_lease_invalid",
                    severity="error",
                    message=f"process lease could not be loaded: {exc}",
                    repair="Delete or repair the malformed derived lease, then rerun doctor.",
                    path=path,
                )
            )
            continue
        ref = _path_to_process_ref(layout, path)
        leases.append(lease)
        by_ref[ref] = lease
    return tuple(leases), by_ref


def _inspect_trace_checkpoint_relationship(
    checkpoint: CheckpointState,
    trace_alignment: TraceCheckpointAlignment | None,
    session_spans: tuple[TraceSessionSpan, ...],
    issues: list[StateConsistencyIssue],
) -> None:
    if trace_alignment is None or trace_alignment.actual_trace_line_count == 0:
        return
    span_session_ids = {span.session_id for span in session_spans}
    if checkpoint.session_id not in span_session_ids:
        issues.append(
            _issue(
                code="checkpoint_session_missing_from_trace",
                severity="warning",
                message="checkpoint session_id does not appear in trace session spans",
                repair="Confirm this checkpoint belongs to the current trace or reconcile session state.",
                session_id=checkpoint.session_id,
            )
        )


def _inspect_current_trial_trace(
    layout: NamespaceLayout,
    checkpoint: CheckpointState,
    trace_alignment: TraceCheckpointAlignment | None,
    issues: list[StateConsistencyIssue],
) -> None:
    trial = checkpoint.current_trial
    if trial is None:
        return
    if trial.current_trial_start_line is None:
        if trial.operations:
            issues.append(
                _issue(
                    code="current_trial_start_line_missing",
                    severity="error",
                    message="operation ledger exists without current_trial_start_line",
                    repair="Rebuild checkpoint from trace or discard the incomplete current trial state.",
                    trial_id=trial.trial_id,
                )
            )
        return
    if (
        trace_alignment is not None
        and trial.current_trial_start_line > trace_alignment.actual_trace_line_count
    ):
        issues.append(
            _issue(
                code="current_trial_start_line_ahead",
                severity="error",
                message="current_trial_start_line is beyond the end of trace",
                repair="Fail conservative: reconcile checkpoint/trace before resume or cleanup.",
                trial_id=trial.trial_id,
                current_trial_start_line=trial.current_trial_start_line,
                actual_trace_line_count=trace_alignment.actual_trace_line_count,
            )
        )
        return
    event = _trace_event_at_line(layout, trial.current_trial_start_line, issues)
    if event is None:
        return
    event_trial_id = event.get("trial_id")
    if event_trial_id != trial.trial_id:
        issues.append(
            _issue(
                code="current_trial_start_line_mismatch",
                severity="error",
                message="trace event at current_trial_start_line does not match current trial",
                repair="Reconcile checkpoint current trial with trace before resume.",
                expected_trial_id=trial.trial_id,
                actual_trial_id=event_trial_id,
                current_trial_start_line=trial.current_trial_start_line,
            )
        )
    if event.get("kind") != "trial_start":
        issues.append(
            _issue(
                code="current_trial_start_line_not_trial_start",
                severity="warning",
                message="current_trial_start_line does not point at a trial_start event",
                repair="Confirm the checkpoint start-line anchor before relying on Layer D trace protection.",
                kind=event.get("kind"),
                current_trial_start_line=trial.current_trial_start_line,
            )
        )


def _trace_event_at_line(
    layout: NamespaceLayout,
    line_number: int,
    issues: list[StateConsistencyIssue],
) -> dict[str, Any] | None:
    try:
        for current_line, event in enumerate(iter_trace_events(layout.trace_path), start=1):
            if current_line == line_number:
                return trace_event_payload(event)
    except TraceError as exc:
        issues.append(
            _issue(
                code="trace_event_lookup_error",
                severity="error",
                message=f"trace event lookup failed: {exc}",
                repair="Fix events.jsonl validation errors before resume.",
                line_number=line_number,
            )
        )
        return None
    issues.append(
        _issue(
            code="current_trial_start_line_missing_event",
            severity="error",
            message="current_trial_start_line does not resolve to a trace event",
            repair="Reconcile checkpoint/trace before resume.",
            line_number=line_number,
        )
    )
    return None


def _inspect_process_refs(
    layout: NamespaceLayout,
    checkpoint: CheckpointState,
    lease_by_ref: dict[str, ProcessLease],
    issues: list[StateConsistencyIssue],
) -> None:
    trial = checkpoint.current_trial
    if trial is None:
        return
    for operation in trial.operations:
        if operation.status == "pending" and operation.process_refs:
            issues.append(
                _issue(
                    code="pending_operation_has_process_refs",
                    severity="warning",
                    message="pending operation already has process_refs",
                    repair="Drop stale process_refs or move the operation out of pending.",
                    op=operation.op,
                    process_refs=list(operation.process_refs),
                )
            )
        for ref in operation.process_refs:
            lease = lease_by_ref.get(ref)
            if lease is None:
                path = _process_ref_to_path(layout, ref)
                issues.append(
                    _issue(
                        code="process_ref_missing",
                        severity="error",
                        message="operation process_ref points at a missing lease",
                        repair="Rebuild process lease registry from checkpoint/trace or mark the operation for cleanup.",
                        op=operation.op,
                        status=operation.status,
                        process_ref=ref,
                        path=path,
                    )
                )
                continue
            _inspect_operation_lease_status(operation.op, operation.status, ref, lease, issues)


def _inspect_operation_lease_status(
    op: str,
    operation_status: str,
    ref: str,
    lease: ProcessLease,
    issues: list[StateConsistencyIssue],
) -> None:
    if operation_status == "running" and lease.status != "running":
        issues.append(
            _issue(
                code="running_operation_terminal_lease",
                severity="warning",
                message="operation is running but its process lease is terminal",
                repair="Refresh checkpoint operation status from the lease before resume.",
                op=op,
                process_ref=ref,
                lease_status=lease.status,
            )
        )
    if operation_status in {"completed", "failed", "cleaned", "skipped"} and lease.status == "running":
        issues.append(
            _issue(
                code="terminal_operation_running_lease",
                severity="warning",
                message="operation is terminal but its process lease is still running",
                repair="Run process cleaner or refresh the operation ledger before resume.",
                op=op,
                operation_status=operation_status,
                process_ref=ref,
            )
        )


def _inspect_orphan_leases(
    layout: NamespaceLayout,
    checkpoint: CheckpointState,
    leases: tuple[ProcessLease, ...],
    issues: list[StateConsistencyIssue],
) -> None:
    active_refs = _checkpoint_process_refs(checkpoint)
    for lease in leases:
        ref = _lease_to_process_ref(layout, lease)
        if ref in active_refs:
            continue
        severity: StateConsistencySeverity = (
            "warning" if lease.status == "running" else "info"
        )
        issues.append(
            _issue(
                code="orphan_process_lease",
                severity=severity,
                message="process lease is not referenced by checkpoint current trial operations",
                repair="Run process lease GC after confirming no matching live process remains.",
                process_ref=ref,
                lease_status=lease.status,
            )
        )


def _checkpoint_process_refs(checkpoint: CheckpointState) -> set[str]:
    trial = checkpoint.current_trial
    if trial is None:
        return set()
    refs: set[str] = set()
    for operation in trial.operations:
        refs.update(operation.process_refs)
    return refs


def _path_to_process_ref(layout: NamespaceLayout, path: Path) -> str:
    try:
        return path.relative_to(layout.namespace_dir).as_posix()
    except ValueError as exc:
        raise StateConsistencyError(
            f"process lease path is outside namespace directory: {path}"
        ) from exc


def _lease_to_process_ref(layout: NamespaceLayout, lease: ProcessLease) -> str:
    return (
        f"state/processes/{lease.session_id}/{lease.trial_id}/"
        f"{lease.role}-{lease.record.pid}.yaml"
    )


def _process_ref_to_path(layout: NamespaceLayout, ref: str) -> Path:
    return layout.namespace_dir.joinpath(*PurePosixPath(ref).parts)


def _issue(
    *,
    code: str,
    severity: StateConsistencySeverity,
    message: str,
    repair: str,
    **details: Any,
) -> StateConsistencyIssue:
    normalized_details = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in details.items()
    }
    return StateConsistencyIssue(
        code=code,
        severity=severity,
        message=message,
        repair_suggestion=repair,
        details=normalized_details,
    )
