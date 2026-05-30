from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.config import AgentConfig, load_config
from agent.fs_memory import NamespaceLayout, namespace_layout_for_config


@dataclass(frozen=True)
class FakeWorkspace:
    root: Path
    workspace: Path
    source_tree: Path
    spec_path: Path
    config_path: Path
    config: AgentConfig
    layout: NamespaceLayout


def create_fake_workspace(tmp_path: Path, **config_overrides: object) -> FakeWorkspace:
    root = tmp_path
    workspace = root / "memory"
    source_tree = root / "source"
    source_tree.mkdir(parents=True)
    (source_tree / "configure").write_text("#!/bin/sh\n", encoding="utf-8")
    (source_tree / "Makefile").write_text("all:\n\ttrue\n", encoding="utf-8")
    (source_tree / "Makefile.am").write_text("bin_PROGRAMS = demo\n", encoding="utf-8")
    (source_tree / "configure.ac").write_text("AC_INIT([demo])\n", encoding="utf-8")
    (source_tree / "src").mkdir()
    (source_tree / "src" / "schema.proto").write_text(
        'syntax = "proto3";\n',
        encoding="utf-8",
    )
    spec_path = root / "project.spec"
    spec_path.write_text("Name: demo\n%build\n", encoding="utf-8")

    data = {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(workspace)},
        "spec": {"source_path": str(spec_path)},
        "workspace_protection": {
            "source_tree_path": str(source_tree),
            "build_dir_root": str(workspace / "build_dirs"),
            "artifact_staging_dir": str(workspace / "artifacts" / "staging"),
            "artifact_final_dir": str(workspace / "artifacts" / "final"),
            "key_files_to_hash": [
                "configure",
                "Makefile",
                "Makefile.am",
                "configure.ac",
                "src/**/*.proto",
            ],
        },
    }
    _deep_update(data, config_overrides)
    config_path = root / "agent.config.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    config = load_config(config_path)
    layout = namespace_layout_for_config(config)
    layout.ensure_directories()
    return FakeWorkspace(
        root=root,
        workspace=workspace,
        source_tree=source_tree,
        spec_path=spec_path,
        config_path=config_path,
        config=config,
        layout=layout,
    )


def _deep_update(target: dict, updates: dict[str, object]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)  # type: ignore[index,arg-type]
        else:
            target[key] = value
