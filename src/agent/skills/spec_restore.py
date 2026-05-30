"""Spec restore skill for defensive cleanup after spec mutation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent.config import AgentConfig
from agent.fs_memory import NamespaceLayout

from .spec_backup import (
    SpecBackupResult,
    _atomic_write_bytes,
    _ensure_workspace_protection_enabled,
    _file_mode,
    _normalize_now,
    _read_file_bytes,
    _sha256_file,
    _spec_path,
    _validate_trial_id,
)
from .workspace_snapshot import WorkspaceIntegrityError, WorkspaceProtectionError


@dataclass(frozen=True)
class SpecRestoreResult:
    """Result of restoring the spec file from a backup."""

    trial_id: str | None
    spec_path: Path
    backup_path: Path
    relative_backup_path: str
    backup_hash: str
    restored_hash: str
    expected_hash: str | None
    matches_expected: bool
    restored_at: str


def spec_restore(
    config: AgentConfig,
    layout: NamespaceLayout,
    *,
    backup: SpecBackupResult | str | Path,
    trial_id: str | None = None,
    expected_hash: str | None = None,
    now: datetime | None = None,
) -> SpecRestoreResult:
    """Restore the configured spec file from a namespace spec backup."""

    _ensure_workspace_protection_enabled(config)
    safe_trial_id = _coerce_trial_id(trial_id, backup)
    timestamp = _normalize_now(now).isoformat()
    spec_path = _spec_path(config)
    backup_path = _resolve_backup_path(layout, backup)
    backup_bytes = _read_file_bytes(backup_path)
    backup_hash = _sha256_file(backup_path)
    expected = _coerce_expected_hash(expected_hash, backup)
    matches_expected_before_write = expected is None or backup_hash == expected
    if config.spec.hash_must_match_after_restore and not matches_expected_before_write:
        raise WorkspaceIntegrityError(
            "spec backup hash does not match expected pre-trial hash; "
            f"refusing to restore (expected={expected!r}, backup={backup_hash!r})"
        )

    _atomic_write_bytes(
        backup_bytes,
        spec_path,
        file_mode=_file_mode(spec_path, default=0o644),
    )
    restored_hash = _sha256_file(spec_path)
    if restored_hash != backup_hash:
        raise WorkspaceIntegrityError(
            "spec restore hash mismatch after write "
            f"(backup={backup_hash!r}, restored={restored_hash!r})"
        )

    matches_expected = expected is None or restored_hash == expected
    if config.spec.hash_must_match_after_restore and not matches_expected:
        raise WorkspaceIntegrityError(
            "restored spec hash does not match expected pre-trial hash "
            f"(expected={expected!r}, actual={restored_hash!r})"
        )

    return SpecRestoreResult(
        trial_id=safe_trial_id,
        spec_path=spec_path,
        backup_path=backup_path,
        relative_backup_path=_relative_to_namespace(layout, backup_path),
        backup_hash=backup_hash,
        restored_hash=restored_hash,
        expected_hash=expected,
        matches_expected=matches_expected,
        restored_at=timestamp,
    )


def _coerce_trial_id(
    trial_id: str | None,
    backup: SpecBackupResult | str | Path,
) -> str | None:
    value = trial_id
    if value is None and isinstance(backup, SpecBackupResult):
        value = backup.trial_id
    if value is None:
        return None
    return _validate_trial_id(value)


def _coerce_expected_hash(
    expected_hash: str | None,
    backup: SpecBackupResult | str | Path,
) -> str | None:
    if expected_hash is not None:
        return expected_hash
    if isinstance(backup, SpecBackupResult):
        return backup.original_hash
    return None


def _resolve_backup_path(
    layout: NamespaceLayout,
    backup: SpecBackupResult | str | Path,
) -> Path:
    raw_path = backup.backup_path if isinstance(backup, SpecBackupResult) else Path(backup)
    if raw_path.is_absolute():
        candidate = raw_path
    elif raw_path.parts and raw_path.parts[0] == "spec_backups":
        candidate = layout.namespace_dir / raw_path
    else:
        candidate = layout.spec_backups_dir / raw_path

    if candidate.is_symlink():
        raise WorkspaceProtectionError(
            f"spec backup path must not be a symlink: {raw_path}"
        )
    base = layout.spec_backups_dir.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise WorkspaceProtectionError(
            f"spec backup path must stay inside {base}: {raw_path}"
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise WorkspaceProtectionError(f"spec backup path is not a file: {resolved}")
    return resolved


def _relative_to_namespace(layout: NamespaceLayout, path: Path) -> str:
    try:
        return path.relative_to(layout.namespace_dir).as_posix()
    except ValueError:
        return path.as_posix()
