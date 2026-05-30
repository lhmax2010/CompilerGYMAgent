from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from agent.skills import (
    WorkspaceIntegrityError,
    WorkspaceProtectionError,
    load_workspace_snapshot,
    workspace_snapshot,
    workspace_verify,
)
from tests.fixtures.fake_workspace import create_fake_workspace


def fixed_now() -> datetime:
    return datetime(2026, 5, 30, 1, 2, 3, tzinfo=UTC)


def test_workspace_snapshot_pre_writes_snapshot_and_creates_trial_dirs(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)

    result = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t1",
        phase="pre",
        now=fixed_now(),
    )

    assert result.snapshot_path == fake.layout.workspace_snapshots_dir / "ws_pre_r1_t1.yaml"
    assert result.snapshot_hash.startswith("sha256:")
    assert (fake.workspace / "build_dirs" / "r1_t1").is_dir()
    assert (fake.workspace / "artifacts" / "staging" / "r1_t1").is_dir()
    loaded = load_workspace_snapshot(result.snapshot_path)
    assert loaded["hash"] == result.snapshot_hash
    assert loaded["trial_id"] == "r1_t1"
    assert loaded["captured_at"] == "2026-05-30T01:02:03+00:00"
    assert loaded["phase"] == "pre"
    assert loaded["spec"]["path"] == str(fake.spec_path)
    assert loaded["spec"]["hash"].startswith("sha256:")
    assert loaded["source_tree"]["path"] == str(fake.source_tree.resolve())
    assert set(loaded["source_tree"]["key_file_hashes"]) == {
        "Makefile",
        "Makefile.am",
        "configure",
        "configure.ac",
        "src/schema.proto",
    }
    assert loaded["source_tree"]["missing_key_files"] == []
    assert loaded["build_dir"]["exists"] is True
    assert loaded["artifact_staging"]["exists"] is True


def test_workspace_verify_warn_records_key_file_change(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    pre = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t2",
        phase="pre",
        now=fixed_now(),
    )
    (fake.source_tree / "configure").write_text("# changed\n", encoding="utf-8")

    result = workspace_verify(
        fake.config,
        fake.layout,
        trial_id="r1_t2",
        pre_snapshot=pre,
        now=fixed_now(),
    )

    assert result.spec_matches_pre is True
    assert result.source_tree_changes == ({"file": "configure", "action": "modified"},)
    post = load_workspace_snapshot(result.post_snapshot_path)
    assert post["phase"] == "post"
    assert post["spec"]["matches_pre"] is True
    assert post["source_tree"]["changes_vs_pre"] == [
        {"file": "configure", "action": "modified"}
    ]
    assert post["hash"] == result.post_snapshot_hash


def test_workspace_verify_ignore_suppresses_source_change(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(
        tmp_path,
        workspace_protection={"source_dirty_action": "ignore"},
    )
    pre = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t3",
        phase="pre",
        now=fixed_now(),
    )
    (fake.source_tree / "Makefile").write_text("all:\n\tfalse\n", encoding="utf-8")

    result = workspace_verify(
        fake.config,
        fake.layout,
        trial_id="r1_t3",
        pre_snapshot=pre,
        now=fixed_now(),
    )

    assert result.source_tree_changes == ()
    assert result.ok is True


def test_workspace_verify_fail_raises_on_source_change(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(
        tmp_path,
        workspace_protection={"source_dirty_action": "fail"},
    )
    pre = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t4",
        phase="pre",
        now=fixed_now(),
    )
    (fake.source_tree / "Makefile.am").write_text("changed = yes\n", encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="source tree changed"):
        workspace_verify(
            fake.config,
            fake.layout,
            trial_id="r1_t4",
            pre_snapshot=pre,
            now=fixed_now(),
        )


def test_workspace_verify_raises_on_spec_mismatch(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    pre = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t5",
        phase="pre",
        now=fixed_now(),
    )
    fake.spec_path.write_text("Name: changed\n%build\n", encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="spec hash does not match"):
        workspace_verify(
            fake.config,
            fake.layout,
            trial_id="r1_t5",
            pre_snapshot=pre.snapshot_path,
            now=fixed_now(),
        )


def test_workspace_snapshot_records_missing_key_files(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    (fake.source_tree / "configure.ac").unlink()

    result = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t6",
        phase="pre",
        now=fixed_now(),
    )

    assert result.payload["source_tree"]["missing_key_files"] == ["configure.ac"]
    assert "configure.ac" not in result.payload["source_tree"]["key_file_hashes"]


def test_workspace_snapshot_rejects_key_pattern_outside_source_tree(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    bad_config = fake.config.model_copy(
        update={
            "workspace_protection": fake.config.workspace_protection.model_copy(
                update={"key_files_to_hash": ["../secret"]}
            )
        }
    )

    with pytest.raises(WorkspaceProtectionError, match="inside source tree"):
        workspace_snapshot(
            bad_config,
            fake.layout,
            trial_id="r1_t7",
            phase="pre",
            now=fixed_now(),
        )


def test_workspace_snapshot_rejects_symlinked_key_file_outside_source_tree(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(
        tmp_path,
        workspace_protection={"key_files_to_hash": ["leak"]},
    )
    secret = tmp_path / "secret.txt"
    secret.write_text("secret\n", encoding="utf-8")
    (fake.source_tree / "leak").symlink_to(secret)

    with pytest.raises(WorkspaceProtectionError, match="outside source tree"):
        workspace_snapshot(
            fake.config,
            fake.layout,
            trial_id="r1_t7b",
            phase="pre",
            now=fixed_now(),
        )


def test_workspace_snapshot_hash_detects_manual_edit(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)
    result = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r1_t8",
        phase="pre",
        now=fixed_now(),
    )
    payload = yaml.safe_load(result.snapshot_path.read_text(encoding="utf-8"))
    payload["spec"]["hash"] = "sha256:" + ("0" * 64)
    result.snapshot_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="hash mismatch"):
        load_workspace_snapshot(result.snapshot_path)


def test_workspace_snapshot_rejects_disabled_workspace_protection(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(
        tmp_path,
        workspace_protection={"enabled": False},
    )

    with pytest.raises(WorkspaceProtectionError, match="disabled"):
        workspace_snapshot(
            fake.config,
            fake.layout,
            trial_id="r1_t9",
            phase="pre",
            now=fixed_now(),
        )


def test_workspace_skill_exports_from_agent_package() -> None:
    import agent

    assert agent.workspace_snapshot is workspace_snapshot
    assert agent.workspace_verify is workspace_verify
    assert issubclass(agent.WorkspaceProtectionError, agent.AgentError)
    assert issubclass(agent.WorkspaceIntegrityError, agent.AgentError)
