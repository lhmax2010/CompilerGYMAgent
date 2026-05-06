"""Configuration schema and loading for the local agent.

The schema follows REQUIREMENTS.md section 4.1.2 and Appendix B.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ConfigLoadError(RuntimeError):
    """Raised when `agent.config.yaml` cannot be parsed or validated."""


def _option_list(default: str = "-O2") -> list[str]:
    return [default]


def _generator_priority() -> list[str]:
    return ["llm_proposer", "local_mutation", "weighted_random"]


def _key_files_to_hash() -> list[str]:
    return ["configure", "Makefile", "Makefile.am", "configure.ac"]


def _schema_versions() -> list[str]:
    return ["exp-pack-v1"]


def _allowed_non_item_files() -> list[str]:
    return ["manifest.yaml", "README.md"]


def _canary_priority_order() -> list[str]:
    return [
        "imported_authoritative_original",
        "imported_verified_original",
        "high_plausibility",
        "older_first",
    ]


def _clean_confirmations() -> list[str]:
    return ["namespace", "all", "kg-backups"]


def _always_redact() -> list[str]:
    return ["api_keys"]


def _process_multi_checks() -> list[str]:
    return ["create_time", "cmdline_hash", "session_marker"]


def _expand_path(value: Any) -> Any:
    if isinstance(value, str):
        return Path(value).expanduser()
    return value


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class CompilerConfig(StrictConfigModel):
    type: NonEmptyStr
    version: NonEmptyStr


class ProjectConfig(StrictConfigModel):
    module: NonEmptyStr
    framework: NonEmptyStr
    compiler: CompilerConfig
    code_commit: NonEmptyStr
    kg_version: NonEmptyStr


class MemoryConfig(StrictConfigModel):
    workspace: Path = Path("~/.agent_workspace").expanduser()
    vector_index_enabled: bool = False
    combo_hash_algo: Literal["sha256"] = "sha256"
    trial_partition: Literal["monthly"] = "monthly"
    auto_reindex_on_startup: bool = True
    reindex_fail_action: Literal["refuse_to_run"] = "refuse_to_run"
    vector_top_k: int = Field(default=5, gt=0)

    @field_validator("workspace", mode="before")
    @classmethod
    def expand_workspace(cls, value: Any) -> Any:
        return _expand_path(value)


class LLMConfig(StrictConfigModel):
    provider: NonEmptyStr = "kimi"
    strong_model: NonEmptyStr = "moonshot-v1-128k"
    light_model: NonEmptyStr = "moonshot-v1-32k"
    api_key_env: NonEmptyStr = "KIMI_API_KEY"


class ExplorationScheduleConfig(StrictConfigModel):
    window_size: int = Field(default=5, gt=0)
    exploit_per_window: int = Field(default=3, ge=0)
    mutation_per_window: int = Field(default=1, ge=0)
    novelty_per_window: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def quota_must_match_window(self) -> ExplorationScheduleConfig:
        total = self.exploit_per_window + self.mutation_per_window + self.novelty_per_window
        if total != self.window_size:
            raise ValueError(
                "exploration_schedule quotas must sum to window_size "
                f"(got {total}, expected {self.window_size})"
            )
        return self


class ConvergenceConfig(StrictConfigModel):
    no_improve_trials: int = Field(default=3, gt=0)
    min_improve_pct: float = Field(default=3.0, gt=0)
    require_statistical_significance: bool = True


class AgentRuntimeConfig(StrictConfigModel):
    warmup_rounds: int = Field(default=5, ge=0)
    exploration_schedule: ExplorationScheduleConfig = Field(default_factory=ExplorationScheduleConfig)
    exploration_ratio_stagnation: float = Field(default=0.6, ge=0.0, le=1.0)
    stagnation_threshold_trials: int = Field(default=3, gt=0)
    min_improve_pct: float = Field(default=3.0, gt=0)
    require_statistical_significance: bool = True
    max_rounds: int = Field(default=50, gt=0)
    top_k_best: int = Field(default=3, gt=0)
    recent_failed_window: int = Field(default=10, gt=0)
    novelty_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)

    @model_validator(mode="after")
    def synchronize_convergence_fields(self) -> AgentRuntimeConfig:
        fields_set = self.model_fields_set
        convergence_was_set = "convergence" in fields_set

        if convergence_was_set:
            conflicts = [
                (
                    "stagnation_threshold_trials",
                    self.stagnation_threshold_trials,
                    self.convergence.no_improve_trials,
                ),
                ("min_improve_pct", self.min_improve_pct, self.convergence.min_improve_pct),
                (
                    "require_statistical_significance",
                    self.require_statistical_significance,
                    self.convergence.require_statistical_significance,
                ),
            ]
            for field_name, top_level, nested in conflicts:
                if field_name in fields_set and top_level != nested:
                    raise ValueError(
                        f"agent.{field_name} conflicts with agent.convergence "
                        f"({top_level!r} != {nested!r})"
                    )

            if "stagnation_threshold_trials" not in fields_set:
                object.__setattr__(
                    self, "stagnation_threshold_trials", self.convergence.no_improve_trials
                )
            if "min_improve_pct" not in fields_set:
                object.__setattr__(self, "min_improve_pct", self.convergence.min_improve_pct)
            if "require_statistical_significance" not in fields_set:
                object.__setattr__(
                    self,
                    "require_statistical_significance",
                    self.convergence.require_statistical_significance,
                )
        else:
            object.__setattr__(
                self,
                "convergence",
                ConvergenceConfig(
                    no_improve_trials=self.stagnation_threshold_trials,
                    min_improve_pct=self.min_improve_pct,
                    require_statistical_significance=self.require_statistical_significance,
                ),
            )
        return self


class CandidateEngineConfig(StrictConfigModel):
    generator_priority: list[
        Literal["llm_proposer", "local_mutation", "weighted_random", "ablation"]
    ] = Field(default_factory=_generator_priority, min_length=1)

    @field_validator("generator_priority")
    @classmethod
    def generator_priority_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("candidate_engine.generator_priority must not contain duplicates")
        return value


class CanaryQueueConfig(StrictConfigModel):
    max_pending_total: int = Field(default=20, gt=0)
    max_per_session: int = Field(default=5, gt=0)
    priority_order: list[
        Literal[
            "imported_authoritative_original",
            "imported_verified_original",
            "high_plausibility",
            "older_first",
        ]
    ] = Field(default_factory=_canary_priority_order, min_length=1)

    @field_validator("priority_order")
    @classmethod
    def priority_order_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("experience.canary_queue.priority_order must not contain duplicates")
        return value


class ExperienceConfig(StrictConfigModel):
    plausibility_min: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence_for_verified: int = Field(default=3, gt=0)
    contradiction_for_demote: int = Field(default=2, gt=0)
    contradiction_for_authoritative_demote: int = Field(default=3, gt=0)
    canary_per_n_rounds: int = Field(default=5, gt=0)
    canary_default_bench_level: Literal["build_only"] = "build_only"
    canary_allow_full_benchmark: bool = False
    canary_excluded_from_stagnation: bool = True
    import_force_tentative: bool = True
    canary_queue: CanaryQueueConfig = Field(default_factory=CanaryQueueConfig)


class BaselineConfig(StrictConfigModel):
    combo: list[OptionStr] = Field(default_factory=_option_list, min_length=1)
    auto_run_first: bool = True
    default_combo: list[OptionStr] = Field(default_factory=_option_list, min_length=1)

    @model_validator(mode="after")
    def synchronize_combo_defaults(self) -> BaselineConfig:
        fields_set = self.model_fields_set
        if "combo" not in fields_set and "default_combo" in fields_set:
            object.__setattr__(self, "combo", list(self.default_combo))
        elif "default_combo" not in fields_set:
            object.__setattr__(self, "default_combo", list(self.combo))
        return self


class BenchmarkConfig(StrictConfigModel):
    runs_per_trial: int = Field(default=10, gt=0)
    aggregate: Literal["geometric_mean"] = "geometric_mean"
    variance_threshold: float = Field(default=0.05, ge=0.0)
    objective_direction: Literal["higher_is_better", "lower_is_better"] = "higher_is_better"
    significance_method: Literal["bootstrap_ci"] = "bootstrap_ci"
    bootstrap_iterations: int = Field(default=10000, gt=0)
    bootstrap_mode: Literal["paired", "unpaired"] = "unpaired"
    significance_alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    max_runs_on_high_variance: int = Field(default=20, gt=0)
    quick_runs: int = Field(default=3, gt=0)

    @model_validator(mode="after")
    def run_counts_must_be_consistent(self) -> BenchmarkConfig:
        if self.quick_runs > self.runs_per_trial:
            raise ValueError("benchmark.quick_runs must be <= benchmark.runs_per_trial")
        if self.max_runs_on_high_variance < self.runs_per_trial:
            raise ValueError(
                "benchmark.max_runs_on_high_variance must be >= benchmark.runs_per_trial"
            )
        return self


class SpecConfig(StrictConfigModel):
    source_path: Path
    backup_dir: Path = Path("~/.agent_workspace/spec_backups").expanduser()
    backup_retention: int = Field(default=20, gt=0)
    hash_must_match_after_restore: bool = True

    @field_validator("source_path", "backup_dir", mode="before")
    @classmethod
    def expand_paths(cls, value: Any) -> Any:
        return _expand_path(value)


class WorkspaceProtectionConfig(StrictConfigModel):
    enabled: bool = True
    source_tree_path: Path
    build_dir_root: Path = Path("~/.agent_workspace/build_dirs").expanduser()
    artifact_staging_dir: Path = Path("~/.agent_workspace/artifacts/staging").expanduser()
    artifact_final_dir: Path = Path("~/.agent_workspace/artifacts/final").expanduser()
    source_dirty_action: Literal["warn", "fail", "ignore"] = "warn"
    build_dir_cleanup: Literal["after_trial"] = "after_trial"
    build_dir_keep_on_failure: bool = True
    artifact_keep_count: int = Field(default=5, ge=0)
    min_free_gb_to_start_trial: int = Field(default=10, ge=0)
    key_files_to_hash: list[NonEmptyStr] = Field(default_factory=_key_files_to_hash, min_length=1)

    @field_validator(
        "source_tree_path",
        "build_dir_root",
        "artifact_staging_dir",
        "artifact_final_dir",
        mode="before",
    )
    @classmethod
    def expand_paths(cls, value: Any) -> Any:
        return _expand_path(value)


class LangfuseConfig(StrictConfigModel):
    enabled: bool = False
    host: NonEmptyStr = "http://localhost:3000"


class TracingConfig(StrictConfigModel):
    local_jsonl: Path = Path("trace/events.jsonl")
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    local_jsonl_required: bool = True
    langfuse_enabled: bool = False
    trace_rejected_candidates: bool = True

    @field_validator("local_jsonl", mode="before")
    @classmethod
    def expand_local_jsonl(cls, value: Any) -> Any:
        return _expand_path(value)

    @model_validator(mode="after")
    def synchronize_langfuse_flags(self) -> TracingConfig:
        fields_set = self.model_fields_set
        if "langfuse" in fields_set and "langfuse_enabled" in fields_set:
            if self.langfuse.enabled != self.langfuse_enabled:
                raise ValueError("tracing.langfuse.enabled conflicts with tracing.langfuse_enabled")
        elif "langfuse" in fields_set:
            object.__setattr__(self, "langfuse_enabled", self.langfuse.enabled)
        elif "langfuse_enabled" in fields_set:
            object.__setattr__(
                self, "langfuse", LangfuseConfig(enabled=self.langfuse_enabled)
            )
        return self


class CheckpointConfig(StrictConfigModel):
    enabled: bool = True
    every_n_trials: int = Field(default=1, gt=0)
    keep_history: int = Field(default=5, gt=0)
    langgraph_internal_state: Literal["cache_only"] = "cache_only"


class DryRunConfig(StrictConfigModel):
    enabled: bool = False
    mock_score_noise_pct: float = Field(default=5, ge=0)
    output_dir: Path = Path("dry_run_reports")
    import_overlay_dir: Path = Path("dry_run_reports/<run_id>/import_overlay")
    guard_forbidden_writes: bool = True
    doctor_check_forbidden_writes: bool = True

    @field_validator("output_dir", "import_overlay_dir", mode="before")
    @classmethod
    def expand_paths(cls, value: Any) -> Any:
        return _expand_path(value)


class KGMergeConstraintsConfig(StrictConfigModel):
    require_same_parent: bool = True
    llm_assisted_resolution: bool = False
    auto_modify_trial: bool = False


class KGConfig(StrictConfigModel):
    backup_retention: int = Field(default=10, gt=0)
    log_retention: int = Field(default=100, gt=0)
    v1_merge_constraints: KGMergeConstraintsConfig = Field(
        default_factory=KGMergeConstraintsConfig
    )


class ImportConfig(StrictConfigModel):
    schema_version_supported: list[NonEmptyStr] = Field(
        default_factory=_schema_versions, min_length=1
    )
    max_file_size_mb: int = Field(default=50, gt=0)
    max_description_length: int = Field(default=2048, gt=0)
    reject_symlinks: bool = True
    reject_hardlinks: bool = True
    reject_devices: bool = True
    reject_setuid_setgid: bool = True
    prompt_injection_quote: bool = True
    hash_validation_required: bool = True
    max_total_uncompressed_size_mb: int = Field(default=100, gt=0)
    max_members: int = Field(default=200, gt=0)
    max_experiences_per_pack: int = Field(default=100, gt=0)
    reject_undeclared_files: bool = True
    allowed_non_item_files: list[NonEmptyStr] = Field(
        default_factory=_allowed_non_item_files, min_length=1
    )
    final_target_must_not_exist: bool = True
    item_file_path_pattern: NonEmptyStr = r"^experiences/[^/]+\.yaml$"
    item_file_must_be_normalized: bool = True
    max_compression_ratio: int = Field(default=100, gt=0)
    always_quote_imported_in_prompts: bool = True

    @field_validator("item_file_path_pattern")
    @classmethod
    def item_pattern_must_compile(cls, value: str) -> str:
        re.compile(value)
        return value


class CleanConfig(StrictConfigModel):
    default_dry_run: bool = True
    trash_dir: Path = Path("<workspace>/_trash")
    trash_retention_days: int = Field(default=30, gt=0)
    require_confirmation_for: list[Literal["namespace", "all", "kg-backups"]] = Field(
        default_factory=_clean_confirmations,
        min_length=1,
    )

    @field_validator("trash_dir", mode="before")
    @classmethod
    def expand_trash_dir(cls, value: Any) -> Any:
        return _expand_path(value)

    @field_validator("require_confirmation_for")
    @classmethod
    def confirmations_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("clean.require_confirmation_for must not contain duplicates")
        return value


class IntegrityConfig(StrictConfigModel):
    check_on_startup: bool = True
    fail_action: Literal["paused_request_user_accept", "warn", "strict_fail"] = (
        "paused_request_user_accept"
    )


class ReportConfig(StrictConfigModel):
    redact_enabled: bool = True
    always_redact: list[NonEmptyStr] = Field(default_factory=_always_redact, min_length=1)

    @field_validator("always_redact")
    @classmethod
    def always_redact_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("report.always_redact must not contain duplicates")
        return value


class ProcessCleanupConfig(StrictConfigModel):
    start_new_session: bool = True
    multi_check_required: list[Literal["create_time", "cmdline_hash", "session_marker"]] = Field(
        default_factory=_process_multi_checks,
        min_length=1,
    )
    unsafe_action: Literal["skip_and_log", "abort"] = "skip_and_log"

    @field_validator("multi_check_required")
    @classmethod
    def checks_must_be_complete_and_unique(cls, value: list[str]) -> list[str]:
        required = set(_process_multi_checks())
        actual = set(value)
        if len(value) != len(actual):
            raise ValueError("process_cleanup.multi_check_required must not contain duplicates")
        if actual != required:
            raise ValueError(
                "process_cleanup.multi_check_required must include create_time, "
                "cmdline_hash, and session_marker"
            )
        return value


class WorkspaceLockConfig(StrictConfigModel):
    lock_file: Path = Path("state/run.lock")
    stale_check_required: bool = True
    on_busy_action: Literal["refuse_with_holder_info"] = "refuse_with_holder_info"
    high_risk_bypass_event_required: bool = True

    @field_validator("lock_file", mode="before")
    @classmethod
    def expand_lock_file(cls, value: Any) -> Any:
        return _expand_path(value)

    @model_validator(mode="after")
    def lock_safety_flags_must_stay_enabled(self) -> WorkspaceLockConfig:
        if not self.stale_check_required:
            raise ValueError("workspace_lock.stale_check_required must be true")
        if not self.high_risk_bypass_event_required:
            raise ValueError("workspace_lock.high_risk_bypass_event_required must be true")
        return self


class AgentConfig(StrictConfigModel):
    project: ProjectConfig
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    candidate_engine: CandidateEngineConfig = Field(default_factory=CandidateEngineConfig)
    experience: ExperienceConfig = Field(default_factory=ExperienceConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
    spec: SpecConfig
    workspace_protection: WorkspaceProtectionConfig
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    dry_run: DryRunConfig = Field(default_factory=DryRunConfig)
    kg: KGConfig = Field(default_factory=KGConfig)
    import_config: ImportConfig = Field(default_factory=ImportConfig, alias="import")
    clean: CleanConfig = Field(default_factory=CleanConfig)
    integrity: IntegrityConfig = Field(default_factory=IntegrityConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    process_cleanup: ProcessCleanupConfig = Field(default_factory=ProcessCleanupConfig)
    workspace_lock: WorkspaceLockConfig = Field(default_factory=WorkspaceLockConfig)
    dev_mode: bool = False


def load_config(path: str | Path) -> AgentConfig:
    """Load and validate `agent.config.yaml` with safe YAML parsing."""

    config_path = Path(path)
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"failed to read config file {config_path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"failed to parse YAML config {config_path}: {exc}") from exc

    if data is None:
        raise ConfigLoadError(f"config file {config_path} is empty")
    if not isinstance(data, dict):
        raise ConfigLoadError(f"config file {config_path} must contain a YAML mapping")

    try:
        return AgentConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(f"config file {config_path} is invalid:\n{exc}") from exc
