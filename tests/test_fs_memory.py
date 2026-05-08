from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

import agent.fs_memory as fs_memory
from agent.config import AgentConfig
from agent.fs_memory import (
    AtomicWriteError,
    NamespaceLayout,
    atomic_write_yaml,
    namespace_layout_for_config,
)
from agent.registry import ProjectNamespace


def config_data(workspace: Path) -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(workspace)},
        "baseline": {"combo": ["-O3"]},
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }


def namespace() -> ProjectNamespace:
    return ProjectNamespace(
        module="multimedia",
        framework="ffmpeg",
        compiler="gcc-13.2.0",
        code_commit="code-a1b2c3d",
        kg_version="kg-v3",
    )


def test_namespace_layout_for_config_matches_requirements_paths(tmp_path: Path) -> None:
    config = AgentConfig.model_validate(config_data(tmp_path / "workspace"))

    layout = namespace_layout_for_config(config)

    namespace_dir = (
        tmp_path
        / "workspace"
        / "namespaces"
        / "multimedia"
        / "ffmpeg"
        / "gcc-13.2.0"
        / "code-a1b2c3d"
        / "kg-v3"
    )
    assert layout.namespace_dir == namespace_dir
    assert layout.initialized_path == namespace_dir / ".initialized"
    assert layout.trial_data_dir == namespace_dir / "trials" / "data"
    assert layout.trial_index_path == namespace_dir / "trials" / "_index.sqlite"
    assert layout.failed_combos_dir == namespace_dir / "failed_combos"
    assert layout.learned_rules_dir == namespace_dir / "learned" / "rules"
    assert layout.experiences_dir == namespace_dir / "experiences"
    assert layout.baseline_path == namespace_dir / "baseline" / "baseline.yaml"
    assert layout.environment_snapshots_dir == namespace_dir / "environment" / "snapshots"
    assert layout.obsolete_trials_path == namespace_dir / "derived_views" / "obsolete_trials.yaml"
    assert layout.workspace_snapshots_dir == namespace_dir / "workspace_snapshots"
    assert layout.dry_run_reports_dir == namespace_dir / "dry_run_reports"
    assert layout.trace_path == namespace_dir / "trace" / "events.jsonl"
    assert layout.vectors_dir == namespace_dir / "vectors"
    assert layout.spec_backups_dir == namespace_dir / "spec_backups"
    assert layout.checkpoint_path == namespace_dir / "state" / "checkpoint.yaml"
    assert layout.stop_requested_path == namespace_dir / "state" / "STOP_REQUESTED"
    assert layout.pause_requested_path == namespace_dir / "state" / "PAUSE_REQUESTED"
    assert layout.langgraph_cache_dir == namespace_dir / "state" / "langgraph_cache"


def test_namespace_layout_ensure_directories_creates_only_directories(tmp_path: Path) -> None:
    layout = NamespaceLayout(workspace=tmp_path / "workspace", namespace=namespace())

    layout.ensure_directories()

    for directory in layout.required_directories():
        assert directory.is_dir()
    assert not layout.initialized_path.exists()
    assert not layout.checkpoint_path.exists()
    assert not layout.trace_path.exists()
    assert not layout.trial_index_path.exists()
    assert not layout.obsolete_trials_path.exists()


def test_atomic_write_yaml_writes_user_readable_yaml_and_removes_temp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"

    atomic_write_yaml({"message": "hello", "unicode": "编译", "items": [1, 2]}, target)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {
        "message": "hello",
        "unicode": "编译",
        "items": [1, 2],
    }
    assert "unicode: 编译" in target.read_text(encoding="utf-8")
    assert not list(target.parent.glob(".checkpoint.yaml.*.tmp"))


def test_atomic_write_yaml_preserves_existing_target_on_dump_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    atomic_write_yaml({"status": "old"}, target)

    class NotYamlSerializable:
        pass

    with pytest.raises(yaml.representer.RepresenterError):
        atomic_write_yaml({"bad": NotYamlSerializable()}, target)

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"status": "old"}
    assert not list(target.parent.glob(".checkpoint.yaml.*.tmp"))


def test_atomic_write_yaml_rejects_directory_target(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.yaml"
    target.mkdir()

    with pytest.raises(AtomicWriteError, match="directory"):
        atomic_write_yaml({"status": "new"}, target)

    assert target.is_dir()


def test_atomic_write_yaml_rejects_non_mapping_data(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="mapping"):
        atomic_write_yaml(["not", "a", "mapping"], tmp_path / "x.yaml")  # type: ignore[arg-type]


def test_atomic_write_yaml_does_not_emit_yaml_aliases(tmp_path: Path) -> None:
    target = tmp_path / "experience.yaml"
    shared = ["-O3", "-flto"]

    atomic_write_yaml({"a": shared, "b": shared}, target)

    raw = target.read_text(encoding="utf-8")
    assert "&id" not in raw
    assert "*id" not in raw
    assert yaml.safe_load(raw) == {"a": shared, "b": shared}


def test_atomic_write_yaml_uses_same_parent_unique_temp_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    real_mkstemp = tempfile.mkstemp
    observed: dict[str, object] = {}

    def recording_mkstemp(*, prefix: str, suffix: str, dir: Path, text: bool) -> tuple[int, str]:
        observed["prefix"] = prefix
        observed["suffix"] = suffix
        observed["dir"] = dir
        observed["text"] = text
        return real_mkstemp(prefix=prefix, suffix=suffix, dir=dir, text=text)

    monkeypatch.setattr(fs_memory.tempfile, "mkstemp", recording_mkstemp)

    atomic_write_yaml({"status": "ok"}, target)

    assert observed == {
        "prefix": f".{target.name}.{os.getpid()}.",
        "suffix": ".tmp",
        "dir": target.parent,
        "text": True,
    }


def test_atomic_write_yaml_does_not_clobber_existing_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "state" / "checkpoint.yaml"
    target.parent.mkdir(parents=True)
    sentinel = target.parent / f".{target.name}.{os.getpid()}.sentinel.tmp"
    sentinel.write_text("keep me", encoding="utf-8")

    atomic_write_yaml({"status": "ok"}, target)

    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"status": "ok"}


def test_atomic_write_yaml_flushes_file_and_fsyncs_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "checkpoint.yaml"
    fsync_calls: list[int] = []
    parent_calls: list[Path] = []

    monkeypatch.setattr(fs_memory.os, "fsync", fsync_calls.append)
    monkeypatch.setattr(fs_memory, "_fsync_parent_dir", parent_calls.append)

    atomic_write_yaml({"status": "ok"}, target)

    assert len(fsync_calls) == 1
    assert parent_calls == [target.parent]
