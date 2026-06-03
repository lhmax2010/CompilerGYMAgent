"""Init confirmation flow and `.initialized` namespace guard.

This module implements REQUIREMENTS.md section 4.1.1. The public functions are
kept UI-light so a later CLI layer can call them without duplicating safety
checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .config import AgentConfig, NonEmptyStr, ProjectConfig, load_config
from .errors import AgentError, EXIT_EXECUTION_REFUSED, EXIT_VALIDATION
from .filesystem import warn_if_remote_filesystem
from .fs_memory import atomic_write_yaml
from .registry import (
    ModulesRegistry,
    ProjectNamespace,
    RegistryValidationError,
    compute_project_namespace,
    load_modules_registry,
    registry_path_for_workspace,
    validate_project_against_registry,
)


INIT_SCHEMA_VERSION = "agent.initialized.v1"
MAX_INITIALIZED_BYTES = 1_048_576
InitChoice = Literal["yes", "no", "edit"]
InitStatus = Literal["initialized", "already_initialized"]


class InitError(AgentError):
    """Base error for init flow failures."""


class InitAborted(InitError):
    """Raised when the user rejects the init confirmation."""

    exit_code = EXIT_EXECUTION_REFUSED


class InitEditRequested(InitError):
    """Raised when the user chooses to edit config before initializing."""

    exit_code = EXIT_EXECUTION_REFUSED


class InitializedLoadError(InitError):
    """Raised when `.initialized` cannot be parsed or validated."""

    exit_code = EXIT_VALIDATION


class NamespaceMismatchError(InitError):
    """Raised when `.initialized` records a different namespace."""

    exit_code = EXIT_VALIDATION


class InitYamlLoader(yaml.SafeLoader):
    """Safe loader for user-readable init state YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in .initialized")
        return super().compose_node(parent, index)


class StrictInitModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InitializedState(StrictInitModel):
    schema_version: Literal["agent.initialized.v1"]
    namespace: NonEmptyStr
    namespace_parts: list[NonEmptyStr] = Field(min_length=5, max_length=5)
    project: ProjectConfig
    baseline_combo: list[NonEmptyStr] = Field(min_length=1)
    created_at: NonEmptyStr

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_utc_isoformat(cls, value: str) -> str:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("created_at must be ISO 8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC timezone-aware ISO 8601")
        return value

    @model_validator(mode="after")
    def namespace_identity_must_match_project(self) -> InitializedState:
        parts_namespace = "/".join(self.namespace_parts)
        if self.namespace != parts_namespace:
            raise ValueError("namespace must equal '/'.join(namespace_parts)")

        expected_namespace = compute_project_namespace(self.project)
        expected_parts = list(expected_namespace.parts)
        if self.namespace_parts != expected_parts:
            raise ValueError(
                "namespace_parts do not match project identity "
                f"(parts={self.namespace_parts!r}, expected={expected_parts!r})"
            )
        return self


@dataclass(frozen=True)
class HistorySummary:
    namespace_exists: bool
    initialized_exists: bool
    trial_files: int
    failed_combo_files: int
    learned_rule_files: int
    experience_files: int
    baseline_exists: bool

    @property
    def has_history(self) -> bool:
        return any(
            [
                self.initialized_exists,
                self.trial_files,
                self.failed_combo_files,
                self.learned_rule_files,
                self.experience_files,
                self.baseline_exists,
            ]
        )


@dataclass(frozen=True)
class InitContext:
    config_path: Path
    registry_path: Path
    config: AgentConfig
    registry: ModulesRegistry
    namespace: ProjectNamespace
    workspace: Path
    namespace_dir: Path
    initialized_path: Path
    history: HistorySummary


@dataclass(frozen=True)
class InitResult:
    status: InitStatus
    context: InitContext
    state: InitializedState


def prepare_init_context(
    config_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    existing_trial_compiler_versions: list[str] | None = None,
) -> InitContext:
    config_file = Path(config_path)
    config = load_config(config_file)
    warn_if_remote_filesystem(config.memory.workspace, context="agent init workspace")
    registry_file = (
        Path(registry_path)
        if registry_path is not None
        else registry_path_for_workspace(config.memory.workspace)
    )
    registry = load_modules_registry(registry_file)
    namespace = validate_project_against_registry(
        config,
        registry,
        existing_trial_compiler_versions=existing_trial_compiler_versions,
    )
    namespace_dir = namespace.resolve_under(config.memory.workspace)
    initialized_path = namespace_dir / ".initialized"
    history = collect_history_summary(namespace_dir)
    return InitContext(
        config_path=config_file,
        registry_path=registry_file,
        config=config,
        registry=registry,
        namespace=namespace,
        workspace=config.memory.workspace,
        namespace_dir=namespace_dir,
        initialized_path=initialized_path,
        history=history,
    )


def collect_history_summary(namespace_dir: str | Path) -> HistorySummary:
    root = Path(namespace_dir)
    return HistorySummary(
        namespace_exists=root.exists(),
        initialized_exists=(root / ".initialized").exists(),
        trial_files=_count_yaml_files(root / "trials" / "data"),
        failed_combo_files=_count_yaml_files(root / "failed_combos"),
        learned_rule_files=_count_yaml_files(root / "learned" / "rules"),
        experience_files=_count_yaml_files(root / "experiences"),
        baseline_exists=(root / "baseline" / "baseline.yaml").is_file(),
    )


def render_init_confirmation(context: InitContext) -> str:
    project = context.config.project
    compiler = f"{project.compiler.type}-{project.compiler.version}"
    history = context.history
    history_status = "existing history found" if history.has_history else "no existing history"
    lines = [
        "Resolved project init:",
        f"  module: {project.module}",
        f"  framework: {project.framework}",
        f"  compiler: {compiler}",
        f"  code_commit: {project.code_commit}",
        f"  kg_version: {project.kg_version}",
        f"  namespace: {context.namespace.as_posix}",
        f"  workspace: {context.workspace}",
        f"  namespace_dir: {context.namespace_dir}",
        f"  baseline_combo: {context.config.baseline.combo}",
        "Existing history summary:",
        f"  status: {history_status}",
        f"  initialized: {history.initialized_exists}",
        f"  trials: {history.trial_files}",
        f"  failed_combos: {history.failed_combo_files}",
        f"  learned_rules: {history.learned_rule_files}",
        f"  experiences: {history.experience_files}",
        f"  baseline: {history.baseline_exists}",
    ]
    return "\n".join(lines)


def normalize_init_choice(response: str) -> InitChoice:
    value = response.strip().lower()
    if value in {"y", "yes"}:
        return "yes"
    if value in {"n", "no"}:
        return "no"
    if value in {"e", "edit"}:
        return "edit"
    raise ValueError("expected y/yes, n/no, or e/edit")


def prompt_for_init_confirmation(
    context: InitContext,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> InitChoice:
    output_func(render_init_confirmation(context))
    while True:
        try:
            response = input_func("Confirm init? [y]es/[n]o/[e]dit: ")
        except EOFError as exc:
            raise InitAborted("agent init aborted by EOF") from exc
        try:
            return normalize_init_choice(response)
        except ValueError:
            output_func("Please answer y, n, or edit.")


def run_init(
    config_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    existing_trial_compiler_versions: list[str] | None = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    now: datetime | None = None,
) -> InitResult:
    context = prepare_init_context(
        config_path,
        registry_path=registry_path,
        existing_trial_compiler_versions=existing_trial_compiler_versions,
    )
    if context.initialized_path.exists():
        state = assert_initialized_matches(context.initialized_path, context.namespace)
        return InitResult(status="already_initialized", context=context, state=state)

    choice = prompt_for_init_confirmation(
        context,
        input_func=input_func,
        output_func=output_func,
    )
    if choice == "no":
        raise InitAborted("agent init aborted by user")
    if choice == "edit":
        raise InitEditRequested(f"edit config before init: {context.config_path}")

    state = write_initialized_state(context, now=now)
    return InitResult(status="initialized", context=context, state=state)


def assert_initialized_matches(
    initialized_path: str | Path,
    expected_namespace: ProjectNamespace | str,
) -> InitializedState:
    state = load_initialized_state(initialized_path)
    expected = (
        expected_namespace.as_posix
        if isinstance(expected_namespace, ProjectNamespace)
        else expected_namespace
    )
    if state.namespace != expected:
        raise NamespaceMismatchError(
            ".initialized namespace mismatch "
            f"(expected={expected!r}, actual={state.namespace!r})"
        )
    return state


def verify_initialized_for_startup(
    config_path: str | Path,
    *,
    registry_path: str | Path | None = None,
    existing_trial_compiler_versions: list[str] | None = None,
) -> InitContext:
    context = prepare_init_context(
        config_path,
        registry_path=registry_path,
        existing_trial_compiler_versions=existing_trial_compiler_versions,
    )
    if not context.initialized_path.exists():
        raise InitializedLoadError(
            f"namespace is not initialized: {context.initialized_path}"
        )
    assert_initialized_matches(context.initialized_path, context.namespace)
    return context


def write_initialized_state(
    context: InitContext,
    *,
    now: datetime | None = None,
) -> InitializedState:
    created_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    state = InitializedState(
        schema_version=INIT_SCHEMA_VERSION,
        namespace=context.namespace.as_posix,
        namespace_parts=list(context.namespace.parts),
        project=context.config.project,
        baseline_combo=list(context.config.baseline.combo),
        created_at=created_at,
    )
    context.namespace_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_yaml(state.model_dump(mode="json"), context.initialized_path)
    return state


def load_initialized_state(path: str | Path) -> InitializedState:
    initialized_path = Path(path)
    try:
        file_size = initialized_path.stat().st_size
        if file_size > MAX_INITIALIZED_BYTES:
            raise InitializedLoadError(
                f".initialized file {initialized_path} is too large "
                f"({file_size} bytes > {MAX_INITIALIZED_BYTES} bytes)"
            )
        raw_text = initialized_path.read_text(encoding="utf-8")
    except InitializedLoadError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise InitializedLoadError(f"failed to read .initialized {initialized_path}: {exc}") from exc

    try:
        data = yaml.load(raw_text, Loader=InitYamlLoader)
    except yaml.YAMLError as exc:
        raise InitializedLoadError(
            f"failed to parse YAML .initialized {initialized_path}: {exc}"
        ) from exc

    if data is None:
        raise InitializedLoadError(f".initialized file {initialized_path} is empty")
    if not isinstance(data, dict):
        raise InitializedLoadError(
            f".initialized file {initialized_path} must contain a YAML mapping"
        )

    try:
        return InitializedState.model_validate(data)
    except ValidationError as exc:
        raise InitializedLoadError(
            f".initialized file {initialized_path} is invalid:\n{exc}"
        ) from exc


def _count_yaml_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*.yaml") if item.is_file())
