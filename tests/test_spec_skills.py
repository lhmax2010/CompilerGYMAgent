from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.skills import (
    WorkspaceIntegrityError,
    WorkspaceProtectionError,
    spec_backup,
    spec_injector,
    spec_restore,
    workspace_snapshot,
    workspace_verify,
)
from tests.fixtures.fake_workspace import create_fake_workspace


def fixed_now() -> datetime:
    return datetime(2026, 5, 30, 4, 5, 6, tzinfo=UTC)


def test_spec_backup_writes_namespace_backup_with_matching_hash(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)

    result = spec_backup(fake.config, fake.layout, trial_id="r2_t1", now=fixed_now())

    assert result.backup_path == fake.layout.spec_backups_dir / "pre_trial_r2_t1.spec.bak"
    assert result.relative_backup_path == "spec_backups/pre_trial_r2_t1.spec.bak"
    assert result.created is True
    assert result.original_hash == result.backup_hash
    assert result.created_at == "2026-05-30T04:05:06+00:00"
    assert result.backup_path.read_bytes() == fake.spec_path.read_bytes()


def test_spec_backup_is_idempotent_when_existing_backup_matches(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    first = spec_backup(fake.config, fake.layout, trial_id="r2_t2", now=fixed_now())

    second = spec_backup(fake.config, fake.layout, trial_id="r2_t2", now=fixed_now())

    assert second.created is False
    assert second.backup_path == first.backup_path
    assert second.backup_hash == first.backup_hash


def test_spec_backup_refuses_to_overwrite_mismatched_backup(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    backup_path = fake.layout.spec_backups_dir / "pre_trial_r2_t3.spec.bak"
    backup_path.write_text("stale backup\n", encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="refusing to overwrite"):
        spec_backup(fake.config, fake.layout, trial_id="r2_t3", now=fixed_now())


def test_spec_injector_replaces_default_placeholder_atomically(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    original = fake.spec_path.read_text(encoding="utf-8")

    result = spec_injector(
        fake.config,
        fake.layout,
        trial_id="r2_t4",
        combo=("-O3", "-funroll-loops"),
        now=fixed_now(),
    )

    injected = fake.spec_path.read_text(encoding="utf-8")
    assert "{{AGENT_COMBO}}" in original
    assert "{{AGENT_COMBO}}" not in injected
    assert 'export CFLAGS="-O3 -funroll-loops"' in injected
    assert result.combo == ("-O3", "-funroll-loops")
    assert result.rendered_options == "-O3 -funroll-loops"
    assert result.placeholder == "{{AGENT_COMBO}}"
    assert result.previous_hash != result.injected_hash


def test_spec_injector_missing_placeholder_leaves_spec_unchanged(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    fake.spec_path.write_text("Name: demo\n%build\n", encoding="utf-8")
    before = fake.spec_path.read_bytes()

    with pytest.raises(WorkspaceProtectionError, match="placeholder not found"):
        spec_injector(
            fake.config,
            fake.layout,
            trial_id="r2_t5",
            combo=("-O3",),
            now=fixed_now(),
        )

    assert fake.spec_path.read_bytes() == before


def test_spec_restore_restores_backup_and_verifies_hash(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    original = fake.spec_path.read_bytes()
    backup = spec_backup(fake.config, fake.layout, trial_id="r2_t6", now=fixed_now())
    spec_injector(
        fake.config,
        fake.layout,
        trial_id="r2_t6",
        combo=("-O1",),
        now=fixed_now(),
    )

    result = spec_restore(
        fake.config,
        fake.layout,
        backup=backup.relative_backup_path,
        trial_id="r2_t6",
        expected_hash=backup.original_hash,
        now=fixed_now(),
    )

    assert fake.spec_path.read_bytes() == original
    assert result.backup_hash == backup.backup_hash
    assert result.restored_hash == backup.original_hash
    assert result.matches_expected is True
    assert result.relative_backup_path == backup.relative_backup_path


def test_spec_restore_reports_expected_mismatch_when_config_allows(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(
        tmp_path,
        spec={"hash_must_match_after_restore": False},
    )
    backup = spec_backup(fake.config, fake.layout, trial_id="r2_t7", now=fixed_now())
    spec_injector(
        fake.config,
        fake.layout,
        trial_id="r2_t7",
        combo=("-O0",),
        now=fixed_now(),
    )

    result = spec_restore(
        fake.config,
        fake.layout,
        backup=backup,
        expected_hash="sha256:" + ("0" * 64),
        now=fixed_now(),
    )

    assert result.restored_hash == backup.original_hash
    assert result.matches_expected is False


def test_spec_restore_refuses_mismatched_backup_before_overwriting_spec(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    backup = spec_backup(fake.config, fake.layout, trial_id="r2_t8", now=fixed_now())
    spec_injector(
        fake.config,
        fake.layout,
        trial_id="r2_t8",
        combo=("-O2",),
        now=fixed_now(),
    )
    injected_bytes = fake.spec_path.read_bytes()
    backup.backup_path.write_text("corrupt backup\n", encoding="utf-8")

    with pytest.raises(WorkspaceIntegrityError, match="refusing to restore"):
        spec_restore(fake.config, fake.layout, backup=backup, now=fixed_now())

    assert fake.spec_path.read_bytes() == injected_bytes


def test_spec_restore_rejects_backup_path_outside_layout(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    outside = tmp_path / "outside.spec.bak"
    outside.write_text("not a namespace backup\n", encoding="utf-8")

    with pytest.raises(WorkspaceProtectionError, match="inside"):
        spec_restore(fake.config, fake.layout, backup=outside, now=fixed_now())


def test_spec_restore_rejects_symlink_backup(
    tmp_path: Path,
) -> None:
    fake = create_fake_workspace(tmp_path)
    target = fake.layout.spec_backups_dir / "real.spec.bak"
    target.write_text("backup\n", encoding="utf-8")
    link = fake.layout.spec_backups_dir / "link.spec.bak"
    link.symlink_to(target)

    with pytest.raises(WorkspaceProtectionError, match="symlink"):
        spec_restore(fake.config, fake.layout, backup=link, now=fixed_now())


def test_five_workspace_spec_skills_round_trip(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)

    pre = workspace_snapshot(
        fake.config,
        fake.layout,
        trial_id="r2_t9",
        phase="pre",
        now=fixed_now(),
    )
    backup = spec_backup(fake.config, fake.layout, trial_id="r2_t9", now=fixed_now())
    spec_injector(
        fake.config,
        fake.layout,
        trial_id="r2_t9",
        combo=("-O3",),
        now=fixed_now(),
    )
    spec_restore(fake.config, fake.layout, backup=backup, now=fixed_now())

    result = workspace_verify(
        fake.config,
        fake.layout,
        trial_id="r2_t9",
        pre_snapshot=pre,
        now=fixed_now(),
    )

    assert result.ok is True
    assert result.spec_matches_pre is True
    assert result.source_tree_changes == ()


def test_spec_skills_reject_unsafe_trial_id(tmp_path: Path) -> None:
    fake = create_fake_workspace(tmp_path)

    with pytest.raises(WorkspaceProtectionError, match="trial_id"):
        spec_backup(fake.config, fake.layout, trial_id="../escape", now=fixed_now())


def test_spec_skill_exports_from_agent_package() -> None:
    import agent

    assert agent.spec_backup is spec_backup
    assert agent.spec_injector is spec_injector
    assert agent.spec_restore is spec_restore
