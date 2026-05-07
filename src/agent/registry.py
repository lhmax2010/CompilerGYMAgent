"""Module registry validation and namespace helpers.

This module implements REQUIREMENTS.md sections 4.1.3 and 4.1.4.
The registry is a user-editable YAML file stored at
`<workspace>/shared/modules.registry.yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import AgentConfig, MAX_CONFIG_BYTES, NonEmptyStr, ProjectConfig


MAX_REGISTRY_BYTES = MAX_CONFIG_BYTES


class RegistryLoadError(RuntimeError):
    """Raised when `shared/modules.registry.yaml` cannot be loaded."""


class RegistryValidationError(RuntimeError):
    """Raised when project config fails startup registry validation."""


class RegistryYamlLoader(yaml.SafeLoader):
    """Safe registry loader that rejects YAML aliases to avoid expansion bombs."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in modules.registry.yaml")
        return super().compose_node(parent, index)


class StrictRegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _unique_values(values: list[str], label: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")
    return values


def _validate_namespace_segment(value: str, label: str) -> str:
    segment = value.strip()
    if not segment:
        raise ValueError(f"{label} cannot be empty")
    if segment != value:
        raise ValueError(f"{label} cannot contain surrounding whitespace")
    if segment in {".", ".."}:
        raise ValueError(f"{label} cannot be {segment!r}")
    if "/" in segment or "\\" in segment:
        raise ValueError(f"{label} cannot contain path separators")
    if "\x00" in segment:
        raise ValueError(f"{label} cannot contain NUL bytes")
    return segment


def _validate_mapping_keys(mapping: dict[str, Any], label: str) -> dict[str, Any]:
    for key in mapping:
        _validate_namespace_segment(key, label)
    return mapping


class CompilerRegistryEntry(StrictRegistryModel):
    versions: list[NonEmptyStr] = Field(min_length=1)

    @field_validator("versions")
    @classmethod
    def versions_must_be_unique_and_safe(cls, value: list[str]) -> list[str]:
        _unique_values(value, "compiler.versions")
        for version in value:
            _validate_namespace_segment(version, "compiler.version")
        return value


class FrameworkRegistryEntry(StrictRegistryModel):
    compilers: dict[NonEmptyStr, CompilerRegistryEntry] = Field(min_length=1)

    @field_validator("compilers")
    @classmethod
    def compiler_keys_must_be_safe(
        cls, value: dict[str, CompilerRegistryEntry]
    ) -> dict[str, CompilerRegistryEntry]:
        return _validate_mapping_keys(value, "compiler.type")


class ModuleRegistryEntry(StrictRegistryModel):
    frameworks: dict[NonEmptyStr, FrameworkRegistryEntry] = Field(min_length=1)

    @field_validator("frameworks")
    @classmethod
    def framework_keys_must_be_safe(
        cls, value: dict[str, FrameworkRegistryEntry]
    ) -> dict[str, FrameworkRegistryEntry]:
        return _validate_mapping_keys(value, "framework")


class ModulesRegistry(StrictRegistryModel):
    schema_version: Literal["modules.registry.v1"] = "modules.registry.v1"
    kg_versions: list[NonEmptyStr] = Field(min_length=1)
    modules: dict[NonEmptyStr, ModuleRegistryEntry] = Field(min_length=1)

    @field_validator("kg_versions")
    @classmethod
    def kg_versions_must_be_unique_and_safe(cls, value: list[str]) -> list[str]:
        _unique_values(value, "kg_versions")
        for kg_version in value:
            _validate_namespace_segment(kg_version, "kg_version")
        return value

    @field_validator("modules")
    @classmethod
    def module_keys_must_be_safe(
        cls, value: dict[str, ModuleRegistryEntry]
    ) -> dict[str, ModuleRegistryEntry]:
        return _validate_mapping_keys(value, "module")


@dataclass(frozen=True)
class ProjectNamespace:
    module: str
    framework: str
    compiler: str
    code_commit: str
    kg_version: str

    @property
    def parts(self) -> tuple[str, str, str, str, str]:
        return (
            self.module,
            self.framework,
            self.compiler,
            self.code_commit,
            self.kg_version,
        )

    @property
    def relative_path(self) -> PurePosixPath:
        return PurePosixPath(*self.parts)

    @property
    def experience_scopes_bottom_up(self) -> tuple[PurePosixPath, ...]:
        return tuple(
            PurePosixPath(*self.parts[:depth])
            for depth in range(len(self.parts), 0, -1)
        )

    @property
    def as_posix(self) -> str:
        return self.relative_path.as_posix()

    def resolve_under(self, workspace: Path) -> Path:
        return Path(workspace).joinpath("namespaces", *self.parts)

    def __str__(self) -> str:
        return self.as_posix


def registry_path_for_workspace(workspace: str | Path) -> Path:
    return Path(workspace).expanduser() / "shared" / "modules.registry.yaml"


def load_modules_registry(path: str | Path) -> ModulesRegistry:
    registry_path = Path(path)
    try:
        file_size = registry_path.stat().st_size
        if file_size > MAX_REGISTRY_BYTES:
            raise RegistryLoadError(
                f"registry file {registry_path} is too large "
                f"({file_size} bytes > {MAX_REGISTRY_BYTES} bytes)"
            )
        raw_text = registry_path.read_text(encoding="utf-8")
    except RegistryLoadError:
        raise
    except OSError as exc:
        raise RegistryLoadError(f"failed to read registry file {registry_path}: {exc}") from exc

    try:
        data = yaml.load(raw_text, Loader=RegistryYamlLoader)
    except yaml.YAMLError as exc:
        raise RegistryLoadError(f"failed to parse YAML registry {registry_path}: {exc}") from exc

    if data is None:
        raise RegistryLoadError(f"registry file {registry_path} is empty")
    if not isinstance(data, dict):
        raise RegistryLoadError(f"registry file {registry_path} must contain a YAML mapping")

    try:
        return ModulesRegistry.model_validate(data)
    except ValidationError as exc:
        raise RegistryLoadError(f"registry file {registry_path} is invalid:\n{exc}") from exc


def compute_project_namespace(config: AgentConfig | ProjectConfig) -> ProjectNamespace:
    project = _project_from_config(config)
    module = _validate_namespace_segment(project.module, "project.module")
    framework = _validate_namespace_segment(project.framework, "project.framework")
    compiler_type = _validate_namespace_segment(project.compiler.type, "project.compiler.type")
    compiler_version = _validate_namespace_segment(
        project.compiler.version, "project.compiler.version"
    )
    code_commit = _validate_namespace_segment(project.code_commit, "project.code_commit")
    kg_version = _validate_namespace_segment(project.kg_version, "project.kg_version")

    return ProjectNamespace(
        module=module,
        framework=framework,
        compiler=f"{compiler_type}-{compiler_version}",
        code_commit=f"code-{code_commit}",
        kg_version=f"kg-{kg_version}",
    )


def validate_project_against_registry(
    config: AgentConfig | ProjectConfig,
    registry: ModulesRegistry,
    *,
    existing_trial_compiler_versions: Iterable[str] | None = None,
) -> ProjectNamespace:
    project = _project_from_config(config)
    namespace = compute_project_namespace(project)

    module = registry.modules.get(project.module)
    if module is None:
        raise RegistryValidationError(
            f"project.module {project.module!r} is not registered in modules.registry.yaml"
        )

    framework = module.frameworks.get(project.framework)
    if framework is None:
        raise RegistryValidationError(
            f"project.framework {project.framework!r} is not registered under "
            f"module {project.module!r}"
        )

    compiler = framework.compilers.get(project.compiler.type)
    if compiler is None:
        raise RegistryValidationError(
            f"compiler.type {project.compiler.type!r} is not registered for "
            f"{project.module}/{project.framework}"
        )

    if project.compiler.version not in compiler.versions:
        raise RegistryValidationError(
            f"compiler.version {project.compiler.version!r} is not registered for "
            f"{project.module}/{project.framework}/{project.compiler.type}"
        )

    if project.kg_version not in registry.kg_versions:
        raise RegistryValidationError(
            f"kg_version {project.kg_version!r} is not registered in modules.registry.yaml"
        )

    incompatible_versions = sorted(
        {
            version
            for version in existing_trial_compiler_versions or []
            if version != project.compiler.version
        }
    )
    if incompatible_versions:
        raise RegistryValidationError(
            "compiler.version is incompatible with existing trials "
            f"(config={project.compiler.version!r}, existing={incompatible_versions!r})"
        )

    return namespace


def _project_from_config(config: AgentConfig | ProjectConfig) -> ProjectConfig:
    if isinstance(config, AgentConfig):
        return config.project
    return config
