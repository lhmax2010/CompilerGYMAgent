"""Spec backup skill for reversible spec-file mutation."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent.config import AgentConfig
from agent.fs_memory import NamespaceLayout
from agent.identifiers import validate_session_id_atom

from .workspace_snapshot import WorkspaceIntegrityError, WorkspaceProtectionError


@dataclass(frozen=True)
class SpecBackupResult:
    """Result of persisting the pre-trial spec backup."""

    trial_id: str
    spec_path: Path
    backup_path: Path
    relative_backup_path: str
    original_hash: str
    backup_hash: str
    created_at: str
    created: bool


def spec_backup(
    config: AgentConfig,
    layout: NamespaceLayout,
    *,
    trial_id: str,
    now: datetime | None = None,
) -> SpecBackupResult:
    """Back up the current spec file into the namespace spec_backups directory."""

    _ensure_workspace_protection_enabled(config)
    safe_trial_id = _validate_trial_id(trial_id)
    timestamp = _normalize_now(now).isoformat()
    spec_path = _spec_path(config)
    source_bytes = _read_file_bytes(spec_path)
    original_hash = _sha256_bytes(source_bytes)
    backup_path = _backup_path(layout, safe_trial_id, spec_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    created = False

    if backup_path.exists():
        if backup_path.is_symlink():
            raise WorkspaceProtectionError(
                f"spec backup path must not be a symlink: {backup_path}"
            )
        if not backup_path.is_file():
            raise WorkspaceProtectionError(
                f"spec backup path is not a file: {backup_path}"
            )
        backup_hash = _sha256_file(backup_path)
        if backup_hash != original_hash:
            raise WorkspaceIntegrityError(
                "existing spec backup does not match current spec; "
                f"refusing to overwrite {backup_path}"
            )
    else:
        _atomic_write_bytes(
            source_bytes,
            backup_path,
            file_mode=_file_mode(spec_path, default=0o644),
        )
        created = True
        backup_hash = _sha256_file(backup_path)
        if backup_hash != original_hash:
            raise WorkspaceIntegrityError(
                "spec backup hash mismatch after write "
                f"(expected={original_hash!r}, actual={backup_hash!r})"
            )

    return SpecBackupResult(
        trial_id=safe_trial_id,
        spec_path=spec_path,
        backup_path=backup_path,
        relative_backup_path=_relative_to_namespace(layout, backup_path),
        original_hash=original_hash,
        backup_hash=backup_hash,
        created_at=timestamp,
        created=created,
    )


def _ensure_workspace_protection_enabled(config: AgentConfig) -> None:
    if not config.workspace_protection.enabled:
        raise WorkspaceProtectionError("workspace protection is disabled")


def _validate_trial_id(trial_id: str) -> str:
    return validate_session_id_atom(
        trial_id,
        "trial_id",
        error_type=WorkspaceProtectionError,
    )


def _spec_path(config: AgentConfig) -> Path:
    path = Path(config.spec.source_path).expanduser()
    if not path.exists() or not path.is_file():
        raise WorkspaceProtectionError(f"spec source path is not a file: {path}")
    return path


def _backup_path(layout: NamespaceLayout, trial_id: str, spec_path: Path) -> Path:
    suffix = spec_path.suffix or ".spec"
    return layout.spec_backups_dir / f"pre_trial_{trial_id}{suffix}.bak"


def _relative_to_namespace(layout: NamespaceLayout, path: Path) -> str:
    try:
        return path.relative_to(layout.namespace_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise WorkspaceProtectionError("now must be timezone-aware")
    return value.astimezone(UTC)


def _read_file_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise WorkspaceProtectionError(f"failed to read spec file {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(_read_file_bytes(path))


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _file_mode(path: Path, *, default: int) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return default


def _atomic_write_bytes(data: bytes, path: Path, *, file_mode: int = 0o644) -> None:
    target = Path(path)
    if target.exists() and target.is_dir():
        raise WorkspaceProtectionError(f"cannot atomically write over directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.{os.getpid()}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(handle.fileno(), file_mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        _fsync_parent_dir(target.parent)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _fsync_parent_dir(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", None)
    if flags is None:
        return
    dir_fd = os.open(path, os.O_RDONLY | flags)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
