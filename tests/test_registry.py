from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Callable

import pytest
import yaml

from agent.config import AgentConfig, ProjectConfig
from agent.registry import (
    MAX_REGISTRY_BYTES,
    ModulesRegistry,
    RegistryLoadError,
    RegistryValidationError,
    compute_project_namespace,
    load_modules_registry,
    registry_path_for_workspace,
    validate_project_against_registry,
)


def registry_data() -> dict:
    return {
        "schema_version": "modules.registry.v1",
        "kg_versions": ["v3"],
        "modules": {
            "multimedia": {
                "frameworks": {
                    "ffmpeg": {
                        "compilers": {
                            "gcc": {
                                "versions": ["13.2.0"],
                            },
                            "clang": {
                                "versions": ["17.0.0"],
                            },
                        },
                    },
                },
            },
        },
    }


def minimal_config_data() -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }


def write_registry(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "modules.registry.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def project_config(**overrides: object) -> ProjectConfig:
    data = deepcopy(minimal_config_data()["project"])
    for key, value in overrides.items():
        if key.startswith("compiler."):
            compiler_key = key.removeprefix("compiler.")
            data["compiler"][compiler_key] = value
        else:
            data[key] = value
    return ProjectConfig.model_validate(data)


def test_loads_registry_and_validates_project_namespace(tmp_path: Path) -> None:
    registry = load_modules_registry(write_registry(tmp_path, registry_data()))
    config = AgentConfig.model_validate(minimal_config_data())

    namespace = validate_project_against_registry(config, registry)

    assert namespace.as_posix == "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    assert namespace.relative_path == PurePosixPath(
        "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    )
    assert namespace.resolve_under(Path("/workspace")) == (
        Path("/workspace")
        / "namespaces"
        / "multimedia"
        / "ffmpeg"
        / "gcc-13.2.0"
        / "code-a1b2c3d"
        / "kg-v3"
    )


def test_namespace_experience_scopes_are_bottom_up() -> None:
    namespace = compute_project_namespace(project_config())

    assert [scope.as_posix() for scope in namespace.experience_scopes_bottom_up] == [
        "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3",
        "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d",
        "multimedia/ffmpeg/gcc-13.2.0",
        "multimedia/ffmpeg",
        "multimedia",
    ]


def test_registry_path_for_workspace_points_to_shared_registry() -> None:
    assert registry_path_for_workspace(Path("/workspace")) == (
        Path("/workspace") / "shared" / "modules.registry.yaml"
    )


def test_compute_project_namespace_accepts_project_config() -> None:
    namespace = compute_project_namespace(project_config())

    assert str(namespace) == "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    assert namespace.parts == (
        "multimedia",
        "ffmpeg",
        "gcc-13.2.0",
        "code-a1b2c3d",
        "kg-v3",
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("module", "../multimedia", "path separators"),
        ("framework", ".", "cannot be"),
        ("compiler.type", "gcc/x", "path separators"),
        ("compiler.version", "13\\2", "path separators"),
        ("code_commit", "bad/commit", "path separators"),
        ("kg_version", "..", "cannot be"),
    ],
)
def test_rejects_unsafe_namespace_segments(field: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compute_project_namespace(project_config(**{field: value}))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda data: data["modules"].update({"other": data["modules"].pop("multimedia")}),
            "project.module",
        ),
        (
            lambda data: data["modules"]["multimedia"]["frameworks"].update(
                {"otherfw": data["modules"]["multimedia"]["frameworks"].pop("ffmpeg")}
            ),
            "project.framework",
        ),
        (
            lambda data: data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
                "compilers"
            ].pop("gcc"),
            "compiler.type",
        ),
        (
            lambda data: data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
                "compilers"
            ]["gcc"].update({"versions": ["12.2.0"]}),
            "compiler.version",
        ),
        (lambda data: data.update({"kg_versions": ["v2"]}), "kg_version"),
    ],
)
def test_rejects_unregistered_project_values(
    mutator: Callable[[dict], object], message: str
) -> None:
    data = registry_data()
    mutator(data)
    registry = ModulesRegistry.model_validate(data)

    with pytest.raises(RegistryValidationError, match=message):
        validate_project_against_registry(project_config(), registry)


def test_rejects_existing_trial_compiler_version_mismatch() -> None:
    registry = ModulesRegistry.model_validate(registry_data())

    with pytest.raises(RegistryValidationError, match="incompatible with existing trials"):
        validate_project_against_registry(
            project_config(),
            registry,
            existing_trial_compiler_versions=["13.2.0", "12.2.0"],
        )


def test_accepts_matching_existing_trial_compiler_versions() -> None:
    registry = ModulesRegistry.model_validate(registry_data())

    namespace = validate_project_against_registry(
        project_config(),
        registry,
        existing_trial_compiler_versions=["13.2.0"],
    )

    assert namespace.as_posix.endswith("gcc-13.2.0/code-a1b2c3d/kg-v3")


@pytest.mark.parametrize(
    ("raw_text", "message"),
    [
        ("", "empty"),
        ("# comment only\n", "empty"),
        ("null\n", "empty"),
        ("- not\n- a\n- mapping\n", "must contain a YAML mapping"),
    ],
)
def test_rejects_empty_or_non_mapping_registry(
    tmp_path: Path, raw_text: str, message: str
) -> None:
    path = tmp_path / "modules.registry.yaml"
    path.write_text(raw_text, encoding="utf-8")

    with pytest.raises(RegistryLoadError, match=message):
        load_modules_registry(path)


def test_rejects_missing_registry_file(tmp_path: Path) -> None:
    with pytest.raises(RegistryLoadError, match="failed to read"):
        load_modules_registry(tmp_path / "missing.yaml")


def test_rejects_oversized_registry_file(tmp_path: Path) -> None:
    path = tmp_path / "modules.registry.yaml"
    path.write_text("x" * (MAX_REGISTRY_BYTES + 1), encoding="utf-8")

    with pytest.raises(RegistryLoadError, match="too large"):
        load_modules_registry(path)


def test_rejects_registry_python_tags(tmp_path: Path) -> None:
    path = tmp_path / "modules.registry.yaml"
    path.write_text(
        "!!python/object/apply:os.system ['echo unsafe']\n",
        encoding="utf-8",
    )

    with pytest.raises(RegistryLoadError, match="failed to parse YAML"):
        load_modules_registry(path)


def test_rejects_registry_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / "modules.registry.yaml"
    path.write_text(
        """
kg_versions: [v3]
modules:
  multimedia: &module
    frameworks:
      ffmpeg:
        compilers:
          gcc:
            versions: ["13.2.0"]
  copy: *module
""",
        encoding="utf-8",
    )

    with pytest.raises(RegistryLoadError, match="aliases are not allowed"):
        load_modules_registry(path)


def test_rejects_unknown_registry_fields(tmp_path: Path) -> None:
    data = registry_data()
    data["unexpected"] = True

    with pytest.raises(RegistryLoadError):
        load_modules_registry(write_registry(tmp_path, data))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: data.update({"kg_versions": ["v3", "v3"]}),
        lambda data: data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
            "compilers"
        ]["gcc"].update({"versions": ["13.2.0", "13.2.0"]}),
    ],
)
def test_rejects_duplicate_registry_values(mutator: Callable[[dict], object]) -> None:
    data = registry_data()
    mutator(data)

    with pytest.raises(ValueError, match="duplicates"):
        ModulesRegistry.model_validate(data)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda data: data["modules"].update({"../media": data["modules"]["multimedia"]}),
        lambda data: data["modules"]["multimedia"]["frameworks"].update(
            {"ff/mpeg": data["modules"]["multimedia"]["frameworks"]["ffmpeg"]}
        ),
        lambda data: data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
            "compilers"
        ].update(
            {
                "g/cc": data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
                    "compilers"
                ]["gcc"]
            }
        ),
        lambda data: data["modules"]["multimedia"]["frameworks"]["ffmpeg"][
            "compilers"
        ]["gcc"].update({"versions": ["13/2"]}),
        lambda data: data.update({"kg_versions": ["../v3"]}),
    ],
)
def test_rejects_unsafe_registry_namespace_values(
    mutator: Callable[[dict], object]
) -> None:
    data = registry_data()
    mutator(data)

    with pytest.raises(ValueError, match="path separators"):
        ModulesRegistry.model_validate(data)
