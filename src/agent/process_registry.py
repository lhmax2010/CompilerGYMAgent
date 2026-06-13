"""Derived process lease registry for Phase 06 process management."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import field_validator, model_validator

from .config import NonEmptyStr
from .errors import AgentError, EXIT_VALIDATION
from .fs_memory import NamespaceLayout, atomic_write_yaml
from .identifiers import validate_session_id_atom
from .process_identity import ProcessRecord


PROCESS_LEASE_SCHEMA_VERSION = "process_lease.v1"
MAX_PROCESS_LEASE_BYTES = 64 * 1024
ProcessLeaseStatus = Literal["running", "exited", "killed", "unsafe_skip", "unknown"]


class ProcessRegistryError(AgentError):
    """Raised when process lease registry operations fail."""

    exit_code = EXIT_VALIDATION


class ProcessLeaseYamlLoader(yaml.SafeLoader):
    """Safe YAML loader for process lease files."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in process leases")
        return super().compose_node(parent, index)


class StrictProcessRegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProcessLease(StrictProcessRegistryModel):
    """Derived process lease persisted under state/processes/."""

    schema_version: NonEmptyStr = PROCESS_LEASE_SCHEMA_VERSION
    session_id: NonEmptyStr
    trial_id: NonEmptyStr
    role: NonEmptyStr
    lease_id: str | None = None
    record: ProcessRecord
    status: ProcessLeaseStatus = "running"
    created_at: NonEmptyStr
    updated_at: NonEmptyStr
    ended_at: NonEmptyStr | None = None
    exit_code: int | None = None
    signal: int | None = Field(default=None, ge=0)
    cleanup_attempts: int = Field(default=0, ge=0)

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_match(cls, value: str) -> str:
        if value != PROCESS_LEASE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {PROCESS_LEASE_SCHEMA_VERSION!r}"
            )
        return value

    @field_validator("session_id", "trial_id", "role", mode="before")
    @classmethod
    def atom_must_not_be_trimmed(cls, value: Any, info: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError(f"{info.field_name} cannot contain surrounding whitespace")
        return value

    @field_validator("session_id", "trial_id", "role")
    @classmethod
    def atom_must_be_safe(cls, value: str, info: Any) -> str:
        validate_session_id_atom(value, info.field_name)
        return value

    @field_validator("lease_id", mode="before")
    @classmethod
    def optional_lease_id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("lease_id cannot contain surrounding whitespace")
        return value

    @field_validator("lease_id")
    @classmethod
    def optional_lease_id_must_be_safe(cls, value: str | None) -> str | None:
        if value is not None:
            validate_session_id_atom(value, "lease_id")
        return value

    @field_validator("created_at", "updated_at", "ended_at")
    @classmethod
    def timestamp_must_be_utc_isoformat(cls, value: str | None, info: Any) -> str | None:
        if value is not None:
            _parse_utc_isoformat(value, info.field_name)
        return value

    @model_validator(mode="after")
    def lease_consistency(self) -> ProcessLease:
        if self.record.session_id != self.session_id:
            raise ValueError("record.session_id must match lease session_id")
        if self.record.trial_id is not None and self.record.trial_id != self.trial_id:
            raise ValueError("record.trial_id must match lease trial_id")
        if self.lease_id is not None and self.record.trial_id != self.trial_id:
            raise ValueError("record.trial_id must match lease trial_id")
        if (
            self.record.lease_id is not None or self.lease_id is not None
        ) and self.record.lease_id != self.lease_id:
            raise ValueError("record.lease_id must match lease lease_id")
        created_at = _parse_utc_isoformat(self.created_at, "created_at")
        updated_at = _parse_utc_isoformat(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise ValueError("updated_at cannot be before created_at")
        if self.ended_at is not None:
            ended_at = _parse_utc_isoformat(self.ended_at, "ended_at")
            if ended_at < created_at:
                raise ValueError("ended_at cannot be before created_at")
        if self.status == "running":
            if self.ended_at is not None:
                raise ValueError("running leases must not include ended_at")
            if self.exit_code is not None:
                raise ValueError("running leases must not include exit_code")
            if self.signal is not None:
                raise ValueError("running leases must not include signal")
        else:
            if self.ended_at is None:
                raise ValueError(f"{self.status} leases must include ended_at")
        if self.status == "exited":
            if self.exit_code is None:
                raise ValueError("exited leases must include exit_code")
            if self.signal is not None:
                raise ValueError("exited leases must not include signal")
        elif self.status == "killed":
            if self.signal is None:
                raise ValueError("killed leases must include signal")
            if self.exit_code is not None:
                raise ValueError("killed leases must not include exit_code")
        elif self.status in {"unsafe_skip", "unknown"}:
            if self.exit_code is not None:
                raise ValueError(f"{self.status} leases must not include exit_code")
            if self.signal is not None:
                raise ValueError(f"{self.status} leases must not include signal")
        return self


def process_lease_payload(lease: ProcessLease | Mapping[str, Any]) -> dict[str, Any]:
    validated = ProcessLease.model_validate(lease)
    return validated.model_dump(mode="json", exclude_none=True)


def process_leases_dir(layout: NamespaceLayout) -> Path:
    return layout.state_dir / "processes"


def process_trial_leases_dir(
    layout: NamespaceLayout, *, session_id: str, trial_id: str
) -> Path:
    safe_session_id = validate_session_id_atom(session_id, "session_id")
    safe_trial_id = validate_session_id_atom(trial_id, "trial_id")
    return process_leases_dir(layout) / safe_session_id / safe_trial_id


def process_lease_path(
    layout: NamespaceLayout,
    *,
    session_id: str,
    trial_id: str,
    role: str,
    pid: int,
) -> Path:
    if pid <= 0:
        raise ProcessRegistryError("pid must be > 0")
    safe_role = validate_session_id_atom(role, "role")
    return (
        process_trial_leases_dir(
            layout,
            session_id=session_id,
            trial_id=trial_id,
        )
        / f"{safe_role}-{pid}.yaml"
    )


def register_process_lease(
    layout: NamespaceLayout,
    *,
    record: ProcessRecord,
    trial_id: str,
    role: str,
    lease_id: str | None = None,
    now: datetime | None = None,
) -> ProcessLease:
    timestamp = _utc_now_isoformat(now)
    resolved_lease_id = lease_id if lease_id is not None else record.lease_id
    record_for_lease = record
    updates: dict[str, str] = {}
    if resolved_lease_id is not None:
        validate_session_id_atom(resolved_lease_id, "lease_id")
        if record.lease_id is None:
            updates["lease_id"] = resolved_lease_id
        elif record.lease_id != resolved_lease_id:
            raise ProcessRegistryError("record.lease_id must match lease_id")
        if record.trial_id is None:
            updates["trial_id"] = trial_id
        elif record.trial_id != trial_id:
            raise ProcessRegistryError("record.trial_id must match trial_id")
    elif record.trial_id is not None and record.trial_id != trial_id:
        raise ProcessRegistryError("record.trial_id must match trial_id")
    if updates:
        record_for_lease = ProcessRecord.model_validate(
            {**record.model_dump(mode="json"), **updates}
        )
    lease = ProcessLease(
        session_id=record_for_lease.session_id,
        trial_id=trial_id,
        role=role,
        lease_id=resolved_lease_id,
        record=record_for_lease,
        status="running",
        created_at=timestamp,
        updated_at=timestamp,
    )
    write_process_lease(layout, lease)
    return lease


def write_process_lease(layout: NamespaceLayout, lease: ProcessLease) -> Path:
    target = process_lease_path(
        layout,
        session_id=lease.session_id,
        trial_id=lease.trial_id,
        role=lease.role,
        pid=lease.record.pid,
    )
    if target.exists() and target.is_symlink():
        raise ProcessRegistryError(f"process lease path must not be a symlink: {target}")
    try:
        atomic_write_yaml(process_lease_payload(lease), target, file_mode=0o600)
    except Exception as exc:
        if isinstance(exc, ProcessRegistryError):
            raise
        raise ProcessRegistryError(f"failed to write process lease {target}: {exc}") from exc
    return target


def transition_process_lease(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    status: ProcessLeaseStatus,
    exit_code: int | None = None,
    signal: int | None = None,
    cleanup_attempts: int | None = None,
    now: datetime | None = None,
) -> ProcessLease:
    if lease.status != "running":
        raise ProcessRegistryError(
            f"cannot transition process lease from terminal status {lease.status!r}"
        )
    if status == "running":
        raise ProcessRegistryError("transition status must not be 'running'")
    timestamp = _utc_now_isoformat(now)
    transitioned = ProcessLease.model_validate(
        {
            **lease.model_dump(mode="json"),
            "status": status,
            "updated_at": timestamp,
            "ended_at": timestamp,
            "exit_code": exit_code,
            "signal": signal,
            "cleanup_attempts": (
                lease.cleanup_attempts
                if cleanup_attempts is None
                else cleanup_attempts
            ),
        }
    )
    write_process_lease(layout, transitioned)
    return transitioned


def mark_process_exited(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    exit_code: int,
    now: datetime | None = None,
) -> ProcessLease:
    return transition_process_lease(
        layout,
        lease,
        status="exited",
        exit_code=exit_code,
        now=now,
    )


def mark_process_killed(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    signal: int,
    cleanup_attempts: int | None = None,
    now: datetime | None = None,
) -> ProcessLease:
    return transition_process_lease(
        layout,
        lease,
        status="killed",
        signal=signal,
        cleanup_attempts=cleanup_attempts,
        now=now,
    )


def mark_process_unsafe_skip(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    cleanup_attempts: int | None = None,
    now: datetime | None = None,
) -> ProcessLease:
    return transition_process_lease(
        layout,
        lease,
        status="unsafe_skip",
        cleanup_attempts=cleanup_attempts,
        now=now,
    )


def mark_process_unknown(
    layout: NamespaceLayout,
    lease: ProcessLease,
    *,
    cleanup_attempts: int | None = None,
    now: datetime | None = None,
) -> ProcessLease:
    return transition_process_lease(
        layout,
        lease,
        status="unknown",
        cleanup_attempts=cleanup_attempts,
        now=now,
    )


def load_process_lease(path: str | Path) -> ProcessLease:
    lease_path = Path(path)
    if lease_path.is_symlink():
        raise ProcessRegistryError(f"process lease path must not be a symlink: {lease_path}")
    try:
        file_size = lease_path.stat().st_size
    except FileNotFoundError as exc:
        raise ProcessRegistryError(f"process lease file not found: {lease_path}") from exc
    if file_size > MAX_PROCESS_LEASE_BYTES:
        raise ProcessRegistryError(
            f"process lease {lease_path} is too large "
            f"({file_size} bytes > {MAX_PROCESS_LEASE_BYTES} bytes)"
        )
    try:
        raw_text = lease_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProcessRegistryError(
            f"process lease {lease_path} is not valid UTF-8"
        ) from exc
    try:
        data = yaml.load(raw_text, Loader=ProcessLeaseYamlLoader)
    except yaml.YAMLError as exc:
        raise ProcessRegistryError(
            f"process lease {lease_path} failed to parse YAML: {exc}"
        ) from exc
    if not data:
        raise ProcessRegistryError(f"process lease {lease_path} is empty")
    if not isinstance(data, Mapping):
        raise ProcessRegistryError(
            f"process lease {lease_path} must contain a YAML mapping"
        )
    try:
        return ProcessLease.model_validate(data)
    except ValidationError as exc:
        raise ProcessRegistryError(f"process lease {lease_path} is invalid:\n{exc}") from exc


def load_process_lease_for_layout(
    layout: NamespaceLayout,
    *,
    session_id: str,
    trial_id: str,
    role: str,
    pid: int,
) -> ProcessLease:
    return load_process_lease(
        process_lease_path(
            layout,
            session_id=session_id,
            trial_id=trial_id,
            role=role,
            pid=pid,
        )
    )


def iter_process_lease_paths(layout: NamespaceLayout) -> Iterator[Path]:
    root = process_leases_dir(layout)
    if not root.exists():
        return iter(())
    return iter(sorted(path for path in root.rglob("*.yaml") if path.is_file()))


def load_process_leases(layout: NamespaceLayout) -> tuple[ProcessLease, ...]:
    return tuple(load_process_lease(path) for path in iter_process_lease_paths(layout))


def _utc_now_isoformat(now: datetime | None) -> str:
    value = datetime.now(UTC) if now is None else now
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProcessRegistryError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _parse_utc_isoformat(value: str, label: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC timezone-aware ISO 8601")
    return parsed
