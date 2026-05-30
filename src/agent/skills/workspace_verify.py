"""Workspace verification skill for post-trial protection checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from agent.config import AgentConfig
from agent.fs_memory import NamespaceLayout, atomic_write_yaml, compute_payload_hash
from agent.skills.workspace_snapshot import (
    WorkspaceIntegrityError,
    WorkspaceSnapshotResult,
    load_workspace_snapshot,
    workspace_snapshot,
)


@dataclass(frozen=True)
class WorkspaceVerifyResult:
    """Result of comparing a post-trial workspace snapshot against pre state."""

    pre_snapshot_path: Path
    post_snapshot_path: Path
    pre_snapshot_hash: str
    post_snapshot_hash: str
    spec_matches_pre: bool
    source_tree_changes: tuple[dict[str, str], ...]

    @property
    def ok(self) -> bool:
        return self.spec_matches_pre and not self.source_tree_changes


def workspace_verify(
    config: AgentConfig,
    layout: NamespaceLayout,
    *,
    trial_id: str,
    pre_snapshot: str | Path | WorkspaceSnapshotResult | Mapping[str, Any],
    now: datetime | None = None,
) -> WorkspaceVerifyResult:
    """Capture a post snapshot and compare it with a pre-trial snapshot."""

    pre_path, pre_payload = _coerce_pre_snapshot(pre_snapshot)
    post_result = workspace_snapshot(
        config,
        layout,
        trial_id=trial_id,
        phase="post",
        now=now,
    )
    post_payload = dict(post_result.payload)
    source_tree_changes = _source_tree_changes(pre_payload, post_payload)
    if config.workspace_protection.source_dirty_action == "ignore":
        source_tree_changes = ()

    spec_matches_pre = (
        pre_payload.get("spec", {}).get("hash")
        == post_payload.get("spec", {}).get("hash")
    )
    post_payload["source_tree"] = dict(post_payload["source_tree"])
    post_payload["source_tree"]["changes_vs_pre"] = list(source_tree_changes)
    post_payload["spec"] = dict(post_payload["spec"])
    post_payload["spec"]["matches_pre"] = spec_matches_pre
    post_payload["hash"] = compute_payload_hash(
        post_payload,
        excluded_fields=("hash",),
    )
    atomic_write_yaml(post_payload, post_result.snapshot_path)

    result = WorkspaceVerifyResult(
        pre_snapshot_path=pre_path,
        post_snapshot_path=post_result.snapshot_path,
        pre_snapshot_hash=str(pre_payload["hash"]),
        post_snapshot_hash=str(post_payload["hash"]),
        spec_matches_pre=spec_matches_pre,
        source_tree_changes=source_tree_changes,
    )
    _raise_if_configured_failure(config, result)
    return result


def _coerce_pre_snapshot(
    value: str | Path | WorkspaceSnapshotResult | Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if isinstance(value, WorkspaceSnapshotResult):
        return value.snapshot_path, dict(value.payload)
    if isinstance(value, (str, Path)):
        path = Path(value)
        return path, load_workspace_snapshot(path)
    return Path("-"), dict(value)


def _source_tree_changes(
    pre_payload: Mapping[str, Any],
    post_payload: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    pre_hashes = dict(pre_payload.get("source_tree", {}).get("key_file_hashes") or {})
    post_hashes = dict(post_payload.get("source_tree", {}).get("key_file_hashes") or {})
    changes: list[dict[str, str]] = []
    for file_name in sorted(set(pre_hashes) | set(post_hashes)):
        before = pre_hashes.get(file_name)
        after = post_hashes.get(file_name)
        if before == after:
            continue
        if before is None:
            action = "created"
        elif after is None:
            action = "deleted"
        else:
            action = "modified"
        changes.append({"file": file_name, "action": action})

    pre_status = pre_payload.get("source_tree", {}).get("git_status")
    post_status = post_payload.get("source_tree", {}).get("git_status")
    if pre_status != post_status and not changes:
        changes.append({"file": ".", "action": "git_status_changed"})
    return tuple(changes)


def _raise_if_configured_failure(
    config: AgentConfig,
    result: WorkspaceVerifyResult,
) -> None:
    if config.spec.hash_must_match_after_restore and not result.spec_matches_pre:
        raise WorkspaceIntegrityError(
            "spec hash does not match pre-trial snapshot after restore "
            f"(pre={result.pre_snapshot_hash}, post={result.post_snapshot_hash})"
        )
    if (
        config.workspace_protection.source_dirty_action == "fail"
        and result.source_tree_changes
    ):
        changed = ", ".join(
            f"{item['file']}:{item['action']}" for item in result.source_tree_changes
        )
        raise WorkspaceIntegrityError(
            "source tree changed during trial and source_dirty_action=fail "
            f"({changed})"
        )
