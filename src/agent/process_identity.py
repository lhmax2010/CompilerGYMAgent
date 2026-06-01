"""Shared process identity models for Phase 06 process management."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator

from .config import NonEmptyStr
from .identifiers import validate_session_id_atom


AGENT_SESSION_ID_ENV = "AGENT_SESSION_ID"


class StrictProcessIdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProcessIdentity(StrictProcessIdentityModel):
    """Identity evidence for an agent-managed process group.

    `cmdline_hash` is diagnostic only. Cleanup attribution must not use it as
    a safety score because command lines are too brittle across wrappers and
    workspace moves.
    """

    pid: int = Field(gt=0)
    pgid: int = Field(ge=0)
    create_time: float = Field(ge=0)
    session_id: NonEmptyStr
    cmdline_hash: NonEmptyStr
    env_marker_visible_at_spawn: bool
    cgroup_path: str | None = None

    @field_validator("session_id", mode="before")
    @classmethod
    def session_id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("session_id cannot contain surrounding whitespace")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_safe(cls, value: str) -> str:
        validate_session_id_atom(value, "session_id")
        return value

    @field_validator("cmdline_hash")
    @classmethod
    def cmdline_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "cmdline_hash")
        return value

    @field_validator("cgroup_path")
    @classmethod
    def cgroup_path_must_be_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("cgroup_path cannot be empty")
        return value


class ProcessRecord(ProcessIdentity):
    """Concrete process lease/checkpoint identity record."""


def compute_cmdline_hash(cmdline: Sequence[str]) -> str:
    """Return a stable diagnostic hash for a process command line."""

    payload = "\0".join(cmdline).encode("utf-8", errors="surrogateescape")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_sha256_digest(value: str, label: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{label} must start with 'sha256:'")
    hexdigest = value[len(prefix) :]
    if len(hexdigest) != 64:
        raise ValueError(f"{label} must contain a 64-character sha256 digest")
    try:
        int(hexdigest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be hexadecimal") from exc
