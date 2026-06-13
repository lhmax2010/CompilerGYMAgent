"""Workspace snapshot skill for source/spec/build state capture."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path
from typing import Any, Literal, Mapping

import yaml

from agent.config import AgentConfig
from agent.errors import AgentError, EXIT_INTEGRITY, EXIT_VALIDATION
from agent.fs_memory import (
    NamespaceLayout,
    atomic_write_yaml,
    compute_payload_hash,
)
from agent.identifiers import validate_session_id_atom


WorkspaceSnapshotPhase = Literal["pre", "post"]


class WorkspaceProtectionError(AgentError):
    """Raised when workspace protection state cannot be captured safely."""

    exit_code = EXIT_VALIDATION


class WorkspaceIntegrityError(WorkspaceProtectionError):
    """Raised when workspace verification detects protected-state corruption."""

    exit_code = EXIT_INTEGRITY


@dataclass(frozen=True)
class WorkspaceSnapshotResult:
    """Result of one persisted workspace snapshot."""

    snapshot_path: Path
    snapshot_hash: str
    payload: Mapping[str, Any]


class WorkspaceSnapshotYamlLoader(yaml.SafeLoader):
    """Safe loader for generated workspace snapshot YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in workspace snapshots")
        return super().compose_node(parent, index)


def workspace_snapshot(
    config: AgentConfig,
    layout: NamespaceLayout,
    *,
    trial_id: str,
    phase: WorkspaceSnapshotPhase = "pre",
    now: datetime | None = None,
) -> WorkspaceSnapshotResult:
    """Capture and persist a workspace snapshot for one trial phase."""

    if not config.workspace_protection.enabled:
        raise WorkspaceProtectionError("workspace protection is disabled")
    if phase not in {"pre", "post"}:
        raise WorkspaceProtectionError("workspace snapshot phase must be 'pre' or 'post'")
    safe_trial_id = validate_session_id_atom(
        trial_id,
        "trial_id",
        error_type=WorkspaceProtectionError,
    )
    timestamp = _normalize_now(now).isoformat()

    source_tree = _source_tree_payload(config)
    spec_payload = _spec_payload(config)
    build_dir = Path(config.workspace_protection.build_dir_root) / safe_trial_id
    artifact_staging = (
        Path(config.workspace_protection.artifact_staging_dir) / safe_trial_id
    )
    if phase == "pre":
        build_dir.mkdir(parents=True, exist_ok=True)
        artifact_staging.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "trial_id": safe_trial_id,
        "captured_at": timestamp,
        "phase": phase,
        "source_tree": source_tree,
        "spec": spec_payload,
        "build_dir": {
            "path": str(build_dir),
            "exists": build_dir.exists(),
            "size_bytes": _directory_size_bytes(build_dir),
        },
        "artifact_staging": {
            "path": str(artifact_staging),
            "exists": artifact_staging.exists(),
        },
        "disk_free_gb": _disk_free_gb(Path(config.memory.workspace)),
    }
    payload["hash"] = compute_payload_hash(payload, excluded_fields=("hash",))

    target = layout.workspace_snapshots_dir / f"ws_{phase}_{safe_trial_id}.yaml"
    atomic_write_yaml(payload, target)
    return WorkspaceSnapshotResult(
        snapshot_path=target,
        snapshot_hash=str(payload["hash"]),
        payload=payload,
    )


def load_workspace_snapshot(path: str | Path) -> dict[str, Any]:
    """Load a generated workspace snapshot YAML file."""

    snapshot_path = Path(path)
    try:
        raw_text = snapshot_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkspaceProtectionError(
            f"failed to read workspace snapshot {snapshot_path}: {exc}"
        ) from exc
    try:
        data = yaml.load(raw_text, Loader=WorkspaceSnapshotYamlLoader)
    except yaml.YAMLError as exc:
        raise WorkspaceProtectionError(
            f"failed to parse workspace snapshot {snapshot_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise WorkspaceProtectionError(
            f"workspace snapshot must contain a YAML mapping: {snapshot_path}"
        )
    expected_hash = compute_payload_hash(data, excluded_fields=("hash",))
    if data.get("hash") != expected_hash:
        raise WorkspaceIntegrityError(
            "workspace snapshot hash mismatch "
            f"(path={snapshot_path}, expected={expected_hash!r}, "
            f"actual={data.get('hash')!r})"
        )
    return data


def _source_tree_payload(config: AgentConfig) -> dict[str, Any]:
    source_tree_path = config.workspace_protection.source_tree_path
    if source_tree_path is None:
        raise WorkspaceProtectionError(
            "workspace_protection.source_tree_path is required"
        )
    root = Path(source_tree_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise WorkspaceProtectionError(f"source tree path is not a directory: {root}")

    key_hashes, missing = _key_file_hashes(
        root,
        config.workspace_protection.key_files_to_hash,
    )
    return {
        "path": str(root),
        "git_status": _git_output(root, "status", "--short", "--untracked-files=all"),
        "git_head": _git_output(root, "rev-parse", "HEAD") or None,
        "key_file_hashes": key_hashes,
        "missing_key_files": missing,
    }


def _spec_payload(config: AgentConfig) -> dict[str, Any]:
    spec_path = Path(config.spec.source_path).expanduser()
    if not spec_path.exists() or not spec_path.is_file():
        raise WorkspaceProtectionError(f"spec source path is not a file: {spec_path}")
    return {"path": str(spec_path), "hash": _sha256_file(spec_path)}


def _key_file_hashes(
    root: Path,
    patterns: list[str],
) -> tuple[dict[str, str], list[str]]:
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for pattern in patterns:
        _validate_relative_pattern(pattern)
        matches = _pattern_matches(root, pattern)
        if not matches:
            missing.append(pattern)
            continue
        for path in matches:
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                hashes[relative] = _sha256_file(path)
    return dict(sorted(hashes.items())), sorted(missing)


def _pattern_matches(root: Path, pattern: str) -> list[Path]:
    if _has_glob_meta(pattern):
        candidates = list(root.glob(pattern))
    else:
        candidates = [root / pattern]
    matches: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise WorkspaceProtectionError(
                f"key file pattern resolves outside source tree: {pattern!r}"
            ) from exc
        if candidate.exists() and candidate.is_file():
            matches.append(candidate)
    return sorted(set(matches), key=lambda path: path.relative_to(root).as_posix())


def _validate_relative_pattern(pattern: str) -> None:
    value = Path(pattern)
    if value.is_absolute() or ".." in value.parts:
        raise WorkspaceProtectionError(
            f"key file pattern must stay inside source tree: {pattern!r}"
        )


def _has_glob_meta(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _disk_free_gb(path: Path) -> float:
    target = path if path.exists() else path.parent
    usage = shutil.disk_usage(target)
    return round(usage.free / (1024**3), 3)


def _git_output(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _normalize_now(now: datetime | None) -> datetime:
    value = datetime.now(UTC) if now is None else now
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkspaceProtectionError("snapshot time must be timezone-aware")
    return value.astimezone(UTC)
