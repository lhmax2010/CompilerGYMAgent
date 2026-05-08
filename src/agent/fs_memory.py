"""FS-Memory filesystem helpers and atomic SoT writes.

This module implements the Phase 02 foundation from REQUIREMENTS.md sections
4.2.3 and 4.7.5. User-readable files remain the source of truth; indexes and
caches must be rebuildable from these paths.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import AgentConfig
from .registry import ProjectNamespace, compute_project_namespace


class FsMemoryError(RuntimeError):
    """Base error for FS-Memory failures."""


class AtomicWriteError(FsMemoryError):
    """Raised when an atomic SoT write cannot be completed."""


class SotYamlDumper(yaml.SafeDumper):
    """Safe dumper that keeps generated SoT YAML free of anchors."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


@dataclass(frozen=True)
class NamespaceLayout:
    """Resolved paths for one namespace under a workspace."""

    workspace: Path
    namespace: ProjectNamespace

    @property
    def namespace_dir(self) -> Path:
        return self.namespace.resolve_under(self.workspace)

    @property
    def meta_path(self) -> Path:
        return self.namespace_dir / "_meta.yaml"

    @property
    def initialized_path(self) -> Path:
        return self.namespace_dir / ".initialized"

    @property
    def trials_dir(self) -> Path:
        return self.namespace_dir / "trials"

    @property
    def trial_data_dir(self) -> Path:
        return self.trials_dir / "data"

    @property
    def trial_index_path(self) -> Path:
        return self.trials_dir / "_index.sqlite"

    @property
    def failed_combos_dir(self) -> Path:
        return self.namespace_dir / "failed_combos"

    @property
    def learned_rules_dir(self) -> Path:
        return self.namespace_dir / "learned" / "rules"

    @property
    def experiences_dir(self) -> Path:
        return self.namespace_dir / "experiences"

    @property
    def baseline_path(self) -> Path:
        return self.namespace_dir / "baseline" / "baseline.yaml"

    @property
    def environment_snapshots_dir(self) -> Path:
        return self.namespace_dir / "environment" / "snapshots"

    @property
    def derived_views_dir(self) -> Path:
        return self.namespace_dir / "derived_views"

    @property
    def obsolete_trials_path(self) -> Path:
        return self.derived_views_dir / "obsolete_trials.yaml"

    @property
    def workspace_snapshots_dir(self) -> Path:
        return self.namespace_dir / "workspace_snapshots"

    @property
    def dry_run_reports_dir(self) -> Path:
        return self.namespace_dir / "dry_run_reports"

    @property
    def trace_path(self) -> Path:
        return self.namespace_dir / "trace" / "events.jsonl"

    @property
    def vectors_dir(self) -> Path:
        return self.namespace_dir / "vectors"

    @property
    def spec_backups_dir(self) -> Path:
        return self.namespace_dir / "spec_backups"

    @property
    def state_dir(self) -> Path:
        return self.namespace_dir / "state"

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / "checkpoint.yaml"

    @property
    def stop_requested_path(self) -> Path:
        return self.state_dir / "STOP_REQUESTED"

    @property
    def pause_requested_path(self) -> Path:
        return self.state_dir / "PAUSE_REQUESTED"

    @property
    def langgraph_cache_dir(self) -> Path:
        return self.state_dir / "langgraph_cache"

    def required_directories(self) -> tuple[Path, ...]:
        return (
            self.namespace_dir,
            self.trial_data_dir,
            self.failed_combos_dir,
            self.learned_rules_dir,
            self.experiences_dir,
            self.baseline_path.parent,
            self.environment_snapshots_dir,
            self.derived_views_dir,
            self.workspace_snapshots_dir,
            self.dry_run_reports_dir,
            self.trace_path.parent,
            self.vectors_dir,
            self.spec_backups_dir,
            self.state_dir,
            self.langgraph_cache_dir,
        )

    def ensure_directories(self) -> None:
        for directory in self.required_directories():
            directory.mkdir(parents=True, exist_ok=True)


def namespace_layout_for_config(config: AgentConfig) -> NamespaceLayout:
    """Resolve the FS-Memory layout for an already validated config."""

    return NamespaceLayout(
        workspace=Path(config.memory.workspace).expanduser(),
        namespace=compute_project_namespace(config),
    )


def atomic_write_yaml(
    data: Mapping[str, Any],
    path: str | Path,
    *,
    file_mode: int = 0o644,
) -> None:
    """Atomically write a YAML SoT file.

    The write follows REQUIREMENTS.md section 4.7.5: same-directory unique temp
    file, flush + fsync, `os.replace`, and parent directory fsync. v1 targets
    Linux/Ubuntu; non-Linux development hosts may skip parent fsync when
    `os.O_DIRECTORY` is unavailable.
    """

    if not isinstance(data, Mapping):
        raise TypeError("atomic_write_yaml data must be a mapping")

    target = Path(path)
    if target.exists() and target.is_dir():
        raise AtomicWriteError(f"cannot atomically write YAML over a directory: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.{os.getpid()}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(handle.fileno(), file_mode)
            yaml.dump(
                dict(data),
                handle,
                Dumper=SotYamlDumper,
                sort_keys=False,
                allow_unicode=True,
            )
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
