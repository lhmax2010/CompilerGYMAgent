"""FS-Memory filesystem helpers and atomic SoT writes.

This module implements the Phase 02 foundation from REQUIREMENTS.md sections
4.2.3 and 4.7.5. User-readable files remain the source of truth; indexes and
caches must be rebuildable from these paths.
"""

from __future__ import annotations

import os
import copy
import hashlib
import json
import math
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .config import AgentConfig, NonEmptyStr
from .errors import (
    AgentError,
    EXIT_EXECUTION_REFUSED,
    EXIT_GENERIC,
    EXIT_INTEGRITY,
    EXIT_STALE,
    EXIT_VALIDATION,
)
from .identifiers import validate_session_id_atom
from .registry import ProjectNamespace, compute_project_namespace


class FsMemoryError(AgentError):
    """Base error for FS-Memory failures."""

    exit_code = EXIT_GENERIC


class AtomicWriteError(FsMemoryError):
    """Raised when an atomic SoT write cannot be completed."""


class TrialRecordError(FsMemoryError):
    """Raised when trial record data is invalid for FS-Memory use."""

    exit_code = EXIT_VALIDATION


class TrialImmutableError(TrialRecordError):
    """Raised when an immutable trial YAML path already exists."""

    exit_code = EXIT_EXECUTION_REFUSED


class TrialIntegrityError(TrialRecordError):
    """Raised when trial record integrity data is missing or invalid."""

    exit_code = EXIT_INTEGRITY


class TrialLoadError(TrialRecordError):
    """Raised when immutable trial YAML cannot be parsed or validated."""


class TrialDiscoveryError(TrialLoadError):
    """Raised when discovered trial YAML does not match its FS layout."""


class TrialIndexError(TrialRecordError):
    """Raised when the rebuildable trial SQLite index cannot be used."""

    exit_code = EXIT_STALE


class LearnedRuleError(FsMemoryError):
    """Raised when learned rule data is invalid for FS-Memory use."""

    exit_code = EXIT_VALIDATION


class LearnedRuleExistsError(LearnedRuleError):
    """Raised when a learned rule YAML path already exists."""

    exit_code = EXIT_EXECUTION_REFUSED


class LearnedRuleIntegrityError(LearnedRuleError):
    """Raised when learned rule integrity data is missing or invalid."""

    exit_code = EXIT_INTEGRITY


class LearnedRuleLoadError(LearnedRuleError):
    """Raised when learned rule YAML cannot be parsed or validated."""


class ExperienceError(FsMemoryError):
    """Raised when experience data is invalid for FS-Memory use."""

    exit_code = EXIT_VALIDATION


class ExperienceExistsError(ExperienceError):
    """Raised when an experience YAML path already exists."""

    exit_code = EXIT_EXECUTION_REFUSED


class ExperienceIntegrityError(ExperienceError):
    """Raised when experience integrity data is missing or invalid."""

    exit_code = EXIT_INTEGRITY


class ExperienceLoadError(ExperienceError):
    """Raised when experience YAML cannot be parsed or validated."""


class TraceError(FsMemoryError):
    """Raised when canonical trace data is invalid for FS-Memory use."""

    exit_code = EXIT_VALIDATION


class TraceWriteError(TraceError):
    """Raised when `trace/events.jsonl` cannot be appended safely."""


class TraceLoadError(TraceError):
    """Raised when `trace/events.jsonl` cannot be parsed or validated."""


class CheckpointError(FsMemoryError):
    """Raised when checkpoint state is invalid for FS-Memory use."""

    exit_code = EXIT_VALIDATION


class CheckpointLoadError(CheckpointError):
    """Raised when `state/checkpoint.yaml` cannot be parsed or validated."""


class StrictFsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SotYamlDumper(yaml.SafeDumper):
    """Safe dumper that keeps generated SoT YAML free of anchors."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


class CheckpointYamlLoader(yaml.SafeLoader):
    """Safe loader for user-readable canonical checkpoint YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in checkpoint state")
        return super().compose_node(parent, index)


class TrialYamlLoader(yaml.SafeLoader):
    """Safe loader for user-readable immutable trial YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in trial records")
        return super().compose_node(parent, index)


class LearnedRuleYamlLoader(yaml.SafeLoader):
    """Safe loader for user-readable learned rule YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in learned rules")
        return super().compose_node(parent, index)


class ExperienceYamlLoader(yaml.SafeLoader):
    """Safe loader for user-readable experience YAML."""

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in experiences")
        return super().compose_node(parent, index)


MAX_TRIAL_RECORD_BYTES = 1_048_576
MAX_CHECKPOINT_BYTES = 1_048_576
MAX_LEARNED_RULE_BYTES = 1_048_576
MAX_EXPERIENCE_BYTES = 1_048_576
MAX_TRACE_EVENT_BYTES = 1_048_576
TRIAL_INDEX_SCHEMA_VERSION = 1
TRIAL_HASH_FIELDS_EXCLUDED = ("integrity",)
LEARNED_RULE_HASH_FIELDS_EXCLUDED = ("integrity", "user_validated", "user_notes")
EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED = (
    "source_integrity",
    "local_integrity",
    "validation.evidence_count",
    "validation.contradictions",
    "validation.canary_attempts",
    "audit",
    "user_notes",
)
TrialMode = Literal["exploit", "explore", "warmup", "canary", "mixed"]
CandidateSource = Literal["llm_proposal", "local_mutation", "weighted_random", "ablation"]
ScheduleSlot = Literal["exploit", "mutation", "novelty", "warmup", "canary"]
BenchLevel = Literal["build_only", "quick", "full"]
ObjectiveDirection = Literal["higher_is_better", "lower_is_better"]
BootstrapMode = Literal["paired", "unpaired"]
ExperienceTrustLevel = Literal["tentative", "verified", "authoritative", "disputed"]
ExperienceOrigin = Literal["local", "imported"]
ExperienceHardness = Literal["soft", "hard"]
TrialOutcome = Literal[
    "success",
    "compile_failed",
    "benchmark_failed",
    "timeout",
    "infra_failure",
    "aborted_by_user",
    "spec_corruption",
    "workspace_corruption",
]
CanaryValidationResult = Literal["supports", "contradicts", "inconclusive"]
CheckpointStage = Literal[
    "workspace_snapshot_pre",
    "spec_backup",
    "spec_inject",
    "compiling",
    "benchmarking",
    "score_aggregate",
    "spec_restore",
    "workspace_verify",
    "artifact_rename",
    "memory_write",
    "build_dir_cleanup",
]
CHECKPOINT_PROCESS_STAGES = frozenset({"compiling", "benchmarking"})


class TrialIntegrity(StrictFsModel):
    payload_hash: NonEmptyStr
    hash_fields_excluded: list[NonEmptyStr] = Field(default_factory=lambda: ["integrity"])

    @field_validator("payload_hash")
    @classmethod
    def payload_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "integrity.payload_hash")
        return value

    @field_validator("hash_fields_excluded")
    @classmethod
    def excluded_fields_must_match_trial_contract(cls, value: list[str]) -> list[str]:
        if value != list(TRIAL_HASH_FIELDS_EXCLUDED):
            raise ValueError("trial integrity must exclude exactly ['integrity']")
        return value


class LearnedRuleIntegrity(StrictFsModel):
    payload_hash: NonEmptyStr
    hash_fields_excluded: list[NonEmptyStr] = Field(
        default_factory=lambda: list(LEARNED_RULE_HASH_FIELDS_EXCLUDED)
    )

    @field_validator("payload_hash")
    @classmethod
    def payload_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "integrity.payload_hash")
        return value

    @field_validator("hash_fields_excluded")
    @classmethod
    def excluded_fields_must_match_learned_rule_contract(
        cls,
        value: list[str],
    ) -> list[str]:
        if value != list(LEARNED_RULE_HASH_FIELDS_EXCLUDED):
            raise ValueError(
                "learned rule integrity must exclude exactly "
                "['integrity', 'user_validated', 'user_notes']"
            )
        return value


class ExperienceLocalIntegrity(StrictFsModel):
    payload_hash: NonEmptyStr
    hash_fields_excluded: list[NonEmptyStr] = Field(
        default_factory=lambda: list(EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED)
    )

    @field_validator("payload_hash")
    @classmethod
    def payload_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "local_integrity.payload_hash")
        return value

    @field_validator("hash_fields_excluded")
    @classmethod
    def excluded_fields_must_match_experience_contract(
        cls,
        value: list[str],
    ) -> list[str]:
        if value != list(EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED):
            raise ValueError(
                "experience local_integrity must exclude exactly "
                f"{list(EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED)!r}"
            )
        return value


class ExperienceSourceIntegrity(StrictFsModel):
    source_payload_hash: NonEmptyStr
    source_package_hash: NonEmptyStr
    verified_at_import: bool
    verified_at: NonEmptyStr
    original_file: NonEmptyStr

    @field_validator("source_payload_hash", "source_package_hash")
    @classmethod
    def source_hash_must_be_sha256(cls, value: str, info: Any) -> str:
        _validate_sha256_digest(value, f"source_integrity.{info.field_name}")
        return value

    @field_validator("verified_at", mode="before")
    @classmethod
    def verified_at_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "source_integrity.verified_at")

    @field_validator("verified_at")
    @classmethod
    def verified_at_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "source_integrity.verified_at")
        return value

    @field_validator("original_file")
    @classmethod
    def original_file_must_be_manifest_item_path(cls, value: str) -> str:
        _validate_experience_item_file(value, "source_integrity.original_file")
        return value


class SourceTreeChange(StrictFsModel):
    file: NonEmptyStr
    action: NonEmptyStr


class WorkspaceState(StrictFsModel):
    pre_snapshot_hash: NonEmptyStr
    post_snapshot_hash: NonEmptyStr
    source_tree_changes: list[SourceTreeChange] = Field(default_factory=list)
    build_dir: NonEmptyStr
    artifact_path: NonEmptyStr | None = None
    cleanup_status: Literal["completed", "partial", "failed"]


class ScoreVsBest(StrictFsModel):
    delta_pct: float
    significant: bool
    significance_method: NonEmptyStr
    bootstrap_mode: BootstrapMode
    p_value_or_ci_test: float = Field(ge=0)


class TrialScore(StrictFsModel):
    objective_direction: ObjectiveDirection
    baseline_score: float = Field(gt=0)
    raw_runs: list[float] = Field(min_length=1)
    geomean: float = Field(gt=0)
    stddev: float = Field(ge=0)
    ci_95: list[float] = Field(min_length=2, max_length=2)
    baseline_normalized: float = Field(gt=0)
    vs_best: ScoreVsBest
    noisy: bool


class CanaryRecord(StrictFsModel):
    for_experience: NonEmptyStr | None = None
    hypothesis: NonEmptyStr | None = None
    expected_outcome: NonEmptyStr | None = None
    actual_outcome: NonEmptyStr | None = None
    validation_result: CanaryValidationResult | None = None


class TrialRecord(StrictFsModel):
    trial_id: NonEmptyStr
    round: int = Field(ge=0)
    timestamp: NonEmptyStr
    duration_sec: float = Field(ge=0)
    namespace: NonEmptyStr
    combo: list[NonEmptyStr] = Field(min_length=1)
    combo_hash: NonEmptyStr
    mode: TrialMode
    candidate_source: CandidateSource
    schedule_slot: ScheduleSlot
    bench_level: BenchLevel
    environment_snapshot_hash: NonEmptyStr | None = None
    spec_patch: str = ""
    workspace_state: WorkspaceState
    score: TrialScore | None = None
    outcome: TrialOutcome
    canary: CanaryRecord | None = None
    agent_reasoning: str = ""
    trace_id: NonEmptyStr
    kg_version_used: NonEmptyStr
    integrity: TrialIntegrity | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def timestamp_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "timestamp")

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "timestamp")
        return value

    @field_validator("combo_hash")
    @classmethod
    def combo_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "combo_hash")
        return value

    @field_validator("trial_id")
    @classmethod
    def trial_id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "trial_id")
        return value

    @field_validator("namespace")
    @classmethod
    def namespace_must_be_safe(cls, value: str) -> str:
        _validate_namespace_string(value, "namespace")
        return value

    @model_validator(mode="after")
    def trial_consistency(self) -> TrialRecord:
        expected_combo_hash = compute_combo_hash(self.combo)
        if self.combo_hash != expected_combo_hash:
            raise ValueError(
                "combo_hash does not match combo "
                f"(expected={expected_combo_hash!r}, actual={self.combo_hash!r})"
            )
        if self.outcome == "success" and self.score is None:
            raise ValueError("successful trials must include score")
        if (self.mode == "canary") != (self.schedule_slot == "canary"):
            raise ValueError("canary mode and schedule_slot must match")
        if self.mode == "canary" and self.canary is None:
            raise ValueError("canary trials must include canary details")
        return self


class LearnedRuleScope(StrictFsModel):
    framework: NonEmptyStr | None = None
    module: NonEmptyStr | None = None
    options_involved: list[NonEmptyStr] = Field(default_factory=list)
    context_hint: NonEmptyStr | None = None

    @model_validator(mode="after")
    def scope_must_specify_something(self) -> LearnedRuleScope:
        if (
            self.framework is None
            and self.module is None
            and not self.options_involved
            and self.context_hint is None
        ):
            raise ValueError(
                "scope must specify at least one of framework, module, "
                "options_involved, or context_hint"
            )
        return self


class LearnedRuleEvidence(StrictFsModel):
    supporting_trials: list[NonEmptyStr] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)

    @field_validator("supporting_trials")
    @classmethod
    def supporting_trials_must_be_file_safe(cls, value: list[str]) -> list[str]:
        for trial_id in value:
            _validate_file_atom(trial_id, "evidence.supporting_trials")
        return value


class LearnedRule(StrictFsModel):
    rule_id: NonEmptyStr
    created_at: NonEmptyStr
    created_by: NonEmptyStr
    rule_type: NonEmptyStr
    description: NonEmptyStr
    scope: LearnedRuleScope
    evidence: LearnedRuleEvidence
    action_hint: NonEmptyStr
    user_validated: bool = False
    user_notes: str = ""
    integrity: LearnedRuleIntegrity | None = None

    @field_validator("rule_id", mode="before")
    @classmethod
    def rule_id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("rule_id cannot contain surrounding whitespace")
        return value

    @field_validator("rule_id")
    @classmethod
    def rule_id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "rule_id")
        return value

    @field_validator("created_at", mode="before")
    @classmethod
    def created_at_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "created_at")

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "created_at")
        return value

    @model_validator(mode="after")
    def evidence_count_must_match_supporting_trials(self) -> LearnedRule:
        if self.evidence.evidence_count != len(self.evidence.supporting_trials):
            raise ValueError("evidence_count must match supporting_trials length")
        return self


class ExperienceRuleScope(StrictFsModel):
    options: list[NonEmptyStr] = Field(default_factory=list)
    context_hint: NonEmptyStr | None = None

    @field_validator("options", mode="before")
    @classmethod
    def options_must_be_strict_before_strip(cls, value: Any) -> Any:
        if isinstance(value, list):
            for option in value:
                if isinstance(option, str):
                    _validate_option_string(option, "rule.scope.options")
        return value

    @field_validator("options")
    @classmethod
    def options_must_be_safe_strings(cls, value: list[str]) -> list[str]:
        for option in value:
            _validate_option_string(option, "rule.scope.options")
        return value


class ExperienceRule(StrictFsModel):
    type: NonEmptyStr
    description: NonEmptyStr
    scope: ExperienceRuleScope
    expected_outcome: NonEmptyStr
    hardness: ExperienceHardness


class ExperienceValidation(StrictFsModel):
    plausibility_score: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int = Field(ge=0)
    required_evidence: int = Field(ge=0)
    contradictions: int = Field(ge=0)
    canary_attempts: int = Field(ge=0)


class ExperienceAuditEvent(StrictFsModel):
    ts: NonEmptyStr
    action: NonEmptyStr
    by: NonEmptyStr

    @field_validator("ts", mode="before")
    @classmethod
    def ts_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "audit.ts")

    @field_validator("ts")
    @classmethod
    def ts_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "audit.ts")
        return value


class ExperienceImportMetadata(StrictFsModel):
    original_trust: ExperienceTrustLevel
    original_namespace: NonEmptyStr
    original_evidence_count: int = Field(ge=0)
    original_machine_info: NonEmptyStr

    @field_validator("original_namespace", mode="before")
    @classmethod
    def original_namespace_must_be_strict_before_strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            _validate_untrimmed_non_control_string(value, "import_metadata.original_namespace")
        return value

    @field_validator("original_namespace")
    @classmethod
    def original_namespace_must_be_safe(cls, value: str) -> str:
        _validate_namespace_string(value, "import_metadata.original_namespace")
        return value


class Experience(StrictFsModel):
    id: NonEmptyStr
    author: NonEmptyStr
    submitted_at: NonEmptyStr
    trust_level: ExperienceTrustLevel
    origin: ExperienceOrigin
    imported_by: NonEmptyStr | None = None
    imported_at: NonEmptyStr | None = None
    import_metadata: ExperienceImportMetadata | None = None
    rule: ExperienceRule
    validation: ExperienceValidation
    audit: list[ExperienceAuditEvent] = Field(min_length=1)
    user_notes: str = ""
    source_integrity: ExperienceSourceIntegrity | None = None
    local_integrity: ExperienceLocalIntegrity | None = None

    @field_validator("id", mode="before")
    @classmethod
    def id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("id cannot contain surrounding whitespace")
        return value

    @field_validator("id")
    @classmethod
    def id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "id")
        return value

    @field_validator("submitted_at", "imported_at", mode="before")
    @classmethod
    def timestamp_datetime_to_string(cls, value: Any, info: Any) -> Any:
        if value is None:
            return value
        return _datetime_to_utc_isoformat(value, info.field_name)

    @field_validator("submitted_at", "imported_at")
    @classmethod
    def timestamp_must_be_utc_isoformat(cls, value: str | None, info: Any) -> str | None:
        if value is not None:
            _parse_utc_isoformat(value, info.field_name)
        return value

    @model_validator(mode="after")
    def import_fields_match_origin(self) -> Experience:
        imported_fields = (
            self.imported_by,
            self.imported_at,
            self.import_metadata,
            self.source_integrity,
        )
        if self.origin == "imported":
            if any(field is None for field in imported_fields):
                raise ValueError(
                    "imported experiences must include imported_by, imported_at, "
                    "import_metadata, and source_integrity"
                )
        else:
            if any(field is not None for field in imported_fields):
                raise ValueError(
                    "local experiences must not include imported_by, imported_at, "
                    "import_metadata, or source_integrity"
                )
        return self


class CheckpointProcess(StrictFsModel):
    pid: int = Field(gt=0)
    pgid: int = Field(gt=0)
    create_time: float = Field(gt=0)
    cmdline_hash: NonEmptyStr
    session_marker: NonEmptyStr

    @field_validator("cmdline_hash")
    @classmethod
    def cmdline_hash_must_be_sha256(cls, value: str) -> str:
        _validate_sha256_digest(value, "current_trial.process.cmdline_hash")
        return value

    @field_validator("session_marker")
    @classmethod
    def session_marker_must_reference_agent_session(cls, value: str) -> str:
        if not value.startswith("AGENT_SESSION_ID="):
            raise ValueError("session_marker must start with 'AGENT_SESSION_ID='")
        return value


class CheckpointCurrentTrial(StrictFsModel):
    trial_id: NonEmptyStr
    started_at: NonEmptyStr
    current_stage: CheckpointStage
    stage_started_at: NonEmptyStr
    spec_backup_path: NonEmptyStr | None = None
    workspace_snapshot_pre: NonEmptyStr | None = None
    build_dir: NonEmptyStr
    artifact_staging: NonEmptyStr | None = None
    process: CheckpointProcess | None = None

    @field_validator("trial_id")
    @classmethod
    def trial_id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "current_trial.trial_id")
        return value

    @field_validator("started_at", "stage_started_at", mode="before")
    @classmethod
    def timestamp_datetime_to_string(cls, value: Any, info: Any) -> Any:
        return _datetime_to_utc_isoformat(value, f"current_trial.{info.field_name}")

    @field_validator("started_at", "stage_started_at")
    @classmethod
    def timestamp_must_be_utc_isoformat(cls, value: str, info: Any) -> str:
        _parse_utc_isoformat(value, f"current_trial.{info.field_name}")
        return value

    @model_validator(mode="after")
    def current_trial_consistency(self) -> CheckpointCurrentTrial:
        started_at = _parse_utc_isoformat(self.started_at, "current_trial.started_at")
        stage_started_at = _parse_utc_isoformat(
            self.stage_started_at,
            "current_trial.stage_started_at",
        )
        if stage_started_at < started_at:
            raise ValueError("stage_started_at cannot be before started_at")
        if self.current_stage in CHECKPOINT_PROCESS_STAGES and self.process is None:
            raise ValueError("active process stages must include process details")
        return self


class CheckpointBest(StrictFsModel):
    trial_id: NonEmptyStr
    score: float

    @field_validator("trial_id")
    @classmethod
    def trial_id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "current_best.trial_id")
        return value

    @field_validator("score")
    @classmethod
    def score_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("current_best.score must be finite")
        return value


class CheckpointState(StrictFsModel):
    session_id: NonEmptyStr
    namespace: NonEmptyStr
    last_completed_trial: NonEmptyStr | None = None
    current_trial: CheckpointCurrentTrial | None = None
    current_best: CheckpointBest | None = None
    explorer_state: dict[str, Any] = Field(default_factory=dict)
    random_seed: int = Field(ge=0)
    total_tokens_consumed: int = Field(ge=0)
    trace_line_count: int | None = Field(default=None, ge=0)
    last_updated: NonEmptyStr

    @field_validator("namespace")
    @classmethod
    def namespace_must_be_safe(cls, value: str) -> str:
        _validate_namespace_string(value, "namespace")
        return value

    @field_validator("session_id", mode="before")
    @classmethod
    def session_id_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str) and value != value.strip():
            raise ValueError("session_id cannot contain surrounding whitespace")
        return value

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_safe(cls, value: str) -> str:
        validate_session_id_atom(value, "session_id")
        return value

    @field_validator("last_completed_trial")
    @classmethod
    def last_completed_trial_must_be_file_safe(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_file_atom(value, "last_completed_trial")
        return value

    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "last_updated")

    @field_validator("last_updated")
    @classmethod
    def last_updated_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "last_updated")
        return value

    @model_validator(mode="after")
    def process_marker_must_match_session(self) -> CheckpointState:
        if self.current_trial is None or self.current_trial.process is None:
            return self
        expected_marker = f"AGENT_SESSION_ID={self.session_id}"
        actual_marker = self.current_trial.process.session_marker
        if actual_marker != expected_marker:
            raise ValueError(
                "current_trial.process.session_marker must match checkpoint session_id"
            )
        return self


class TraceEvent(BaseModel):
    """One canonical JSONL trace event.

    Common trace fields are strict; event-specific keys remain open so later
    workflow layers can add rejected-candidate, process, memory, or dry-run
    payloads without changing this base schema.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    ts: NonEmptyStr
    kind: NonEmptyStr

    @field_validator("ts", mode="before")
    @classmethod
    def ts_datetime_to_string(cls, value: Any) -> Any:
        return _datetime_to_utc_isoformat(value, "ts")

    @field_validator("ts")
    @classmethod
    def ts_must_be_utc_isoformat(cls, value: str) -> str:
        _parse_utc_isoformat(value, "ts")
        return value

    @field_validator("kind", mode="before")
    @classmethod
    def kind_must_not_be_trimmed(cls, value: Any) -> Any:
        if isinstance(value, str):
            _validate_untrimmed_non_control_string(value, "kind")
        return value

    @field_validator("kind")
    @classmethod
    def kind_must_be_trace_atom(cls, value: str) -> str:
        _validate_trace_kind(value, "kind")
        return value

    @model_validator(mode="after")
    def event_payload_must_be_json_compatible(self) -> TraceEvent:
        _validate_json_value(self.model_dump(mode="python"), "trace event")
        return self


@dataclass(frozen=True)
class DiscoveredTrialRecord:
    """One immutable trial YAML discovered from `trials/data`."""

    path: Path
    record: TrialRecord


@dataclass(frozen=True)
class TrialStartupValidationInputs:
    """Trial-derived inputs for startup registry validation."""

    compiler_versions: tuple[str, ...]
    trial_count: int
    trial_ids: tuple[str, ...]


@dataclass(frozen=True)
class TrialIndexRow:
    """One row projected from immutable trial YAML into `_index.sqlite`."""

    trial_id: str
    relative_path: str
    namespace: str
    round: int
    timestamp: str
    duration_sec: float
    combo_hash: str
    combo: tuple[str, ...]
    mode: str
    candidate_source: str
    schedule_slot: str
    bench_level: str
    outcome: str
    score_geomean: float | None
    baseline_normalized: float | None
    objective_direction: str | None
    integrity_hash: str
    source_mtime_ns: int


@dataclass(frozen=True)
class TrialIndexSummary:
    """Metadata for the rebuildable trial SQLite index."""

    index_path: Path
    schema_version: int
    trial_count: int
    rebuilt_at: str
    source_latest_mtime_ns: int | None


@dataclass(frozen=True)
class TraceAppendResult:
    """Location metadata for one appended trace event."""

    path: Path
    line_number: int | None
    byte_offset: int

    @property
    def trace_id(self) -> str:
        if self.line_number is None:
            raise ValueError(
                "trace line number is unavailable; pass expected_line_number "
                "to append_trace_event when a line-based trace_id is required"
            )
        return f"{self.path.name}#L{self.line_number}"

    @property
    def byte_ref(self) -> str:
        return f"{self.path.name}#B{self.byte_offset}"


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


def compute_combo_hash(combo: Sequence[str]) -> str:
    if not combo:
        raise ValueError("combo cannot be empty")
    for option in combo:
        if not isinstance(option, str) or not option.strip():
            raise ValueError("combo options must be non-empty strings")
        if option != option.strip():
            raise ValueError("combo options cannot contain surrounding whitespace")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in option):
            raise ValueError("combo options cannot contain control characters")
    payload = _canonical_yaml_bytes(list(combo))
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def compute_trial_payload_hash(record: TrialRecord | Mapping[str, Any]) -> str:
    trial = TrialRecord.model_validate(record)
    payload = trial_record_payload(trial, include_integrity=False)
    return compute_payload_hash(payload, excluded_fields=TRIAL_HASH_FIELDS_EXCLUDED)


def compute_payload_hash(
    payload: Mapping[str, Any],
    *,
    excluded_fields: Sequence[str] = TRIAL_HASH_FIELDS_EXCLUDED,
) -> str:
    if any("." in field_path for field_path in excluded_fields):
        canonical_payload = copy.deepcopy(dict(payload))
        for field_path in excluded_fields:
            canonical_payload.pop(field_path, None)
            _remove_mapping_path(canonical_payload, field_path)
    else:
        excluded = set(excluded_fields)
        canonical_payload = {
            key: value for key, value in dict(payload).items() if key not in excluded
        }
    digest = hashlib.sha256(_canonical_yaml_bytes(canonical_payload)).hexdigest()
    return f"sha256:{digest}"


def trial_record_payload(
    record: TrialRecord | Mapping[str, Any],
    *,
    include_integrity: bool = True,
) -> dict[str, Any]:
    trial = TrialRecord.model_validate(record)
    payload = trial.model_dump(mode="json", exclude_none=True)
    if not include_integrity:
        payload.pop("integrity", None)
    return payload


def with_trial_integrity(record: TrialRecord | Mapping[str, Any]) -> TrialRecord:
    trial = TrialRecord.model_validate(record)
    payload = trial_record_payload(trial, include_integrity=False)
    payload["integrity"] = {
        "payload_hash": compute_payload_hash(
            payload,
            excluded_fields=TRIAL_HASH_FIELDS_EXCLUDED,
        ),
        "hash_fields_excluded": list(TRIAL_HASH_FIELDS_EXCLUDED),
    }
    return TrialRecord.model_validate(payload)


def verify_trial_integrity(record: TrialRecord | Mapping[str, Any]) -> bool:
    trial = TrialRecord.model_validate(record)
    if trial.integrity is None:
        return False
    return trial.integrity.payload_hash == compute_trial_payload_hash(trial)


def compute_learned_rule_payload_hash(rule: LearnedRule | Mapping[str, Any]) -> str:
    learned_rule = LearnedRule.model_validate(rule)
    payload = learned_rule_payload(learned_rule, include_integrity=False)
    return compute_payload_hash(payload, excluded_fields=LEARNED_RULE_HASH_FIELDS_EXCLUDED)


def learned_rule_payload(
    rule: LearnedRule | Mapping[str, Any],
    *,
    include_integrity: bool = True,
) -> dict[str, Any]:
    learned_rule = LearnedRule.model_validate(rule)
    payload = learned_rule.model_dump(mode="json", exclude_none=True)
    if not include_integrity:
        payload.pop("integrity", None)
    return payload


def with_learned_rule_integrity(rule: LearnedRule | Mapping[str, Any]) -> LearnedRule:
    learned_rule = LearnedRule.model_validate(rule)
    payload = learned_rule_payload(learned_rule, include_integrity=False)
    payload["integrity"] = {
        "payload_hash": compute_payload_hash(
            payload,
            excluded_fields=LEARNED_RULE_HASH_FIELDS_EXCLUDED,
        ),
        "hash_fields_excluded": list(LEARNED_RULE_HASH_FIELDS_EXCLUDED),
    }
    return LearnedRule.model_validate(payload)


def verify_learned_rule_integrity(rule: LearnedRule | Mapping[str, Any]) -> bool:
    learned_rule = LearnedRule.model_validate(rule)
    if learned_rule.integrity is None:
        return False
    return learned_rule.integrity.payload_hash == compute_learned_rule_payload_hash(
        learned_rule
    )


def compute_experience_local_payload_hash(
    experience: Experience | Mapping[str, Any],
) -> str:
    validated = Experience.model_validate(experience)
    payload = experience_payload(validated, include_local_integrity=False)
    return compute_payload_hash(
        payload,
        excluded_fields=EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED,
    )


def experience_payload(
    experience: Experience | Mapping[str, Any],
    *,
    include_local_integrity: bool = True,
    include_source_integrity: bool = True,
) -> dict[str, Any]:
    validated = Experience.model_validate(experience)
    payload = validated.model_dump(mode="json", exclude_none=True)
    if not include_local_integrity:
        payload.pop("local_integrity", None)
    if not include_source_integrity:
        payload.pop("source_integrity", None)
    return payload


def with_experience_local_integrity(
    experience: Experience | Mapping[str, Any],
) -> Experience:
    validated = Experience.model_validate(experience)
    payload = experience_payload(validated, include_local_integrity=False)
    payload["local_integrity"] = {
        "payload_hash": compute_payload_hash(
            payload,
            excluded_fields=EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED,
        ),
        "hash_fields_excluded": list(EXPERIENCE_LOCAL_HASH_FIELDS_EXCLUDED),
    }
    return Experience.model_validate(payload)


def verify_experience_local_integrity(experience: Experience | Mapping[str, Any]) -> bool:
    validated = Experience.model_validate(experience)
    if validated.local_integrity is None:
        return False
    return (
        validated.local_integrity.payload_hash
        == compute_experience_local_payload_hash(validated)
    )


def experience_path(layout: NamespaceLayout, experience: Experience | Mapping[str, Any]) -> Path:
    validated = Experience.model_validate(experience)
    bucket = "imported" if validated.origin == "imported" else validated.trust_level
    return layout.experiences_dir / bucket / f"{validated.id}.yaml"


def learned_rule_path(layout: NamespaceLayout, rule: LearnedRule | Mapping[str, Any]) -> Path:
    learned_rule = LearnedRule.model_validate(rule)
    return layout.learned_rules_dir / f"{learned_rule.rule_id}.yaml"


def trial_record_path(layout: NamespaceLayout, record: TrialRecord | Mapping[str, Any]) -> Path:
    trial = TrialRecord.model_validate(record)
    timestamp = _parse_utc_isoformat(trial.timestamp, "timestamp")
    return (
        layout.trial_data_dir
        / f"{timestamp.year:04d}-{timestamp.month:02d}"
        / f"trial_{trial.trial_id}.yaml"
    )


def write_trial_record(
    layout: NamespaceLayout,
    record: TrialRecord | Mapping[str, Any],
) -> Path:
    """Write one completed immutable trial YAML.

    Callers must hold the workspace lock before invoking this function. The
    helper refuses existing paths, but cross-process immutability still depends
    on the section 4.15 lock serializing concurrent writers.
    """

    validated = TrialRecord.model_validate(record)
    expected_namespace = str(layout.namespace)
    if validated.namespace != expected_namespace:
        raise TrialRecordError(
            "trial namespace does not match layout "
            f"(expected={expected_namespace!r}, actual={validated.namespace!r})"
        )
    trial = with_trial_integrity(validated)
    target = trial_record_path(layout, trial)
    if target.exists() or target.is_symlink():
        raise TrialImmutableError(f"trial record already exists and is immutable: {target}")
    atomic_write_yaml(trial_record_payload(trial), target)
    return target


def write_learned_rule(
    layout: NamespaceLayout,
    rule: LearnedRule | Mapping[str, Any],
) -> Path:
    """Write one learned rule YAML.

    Callers must hold the workspace lock before invoking this function. The
    helper refuses existing paths to avoid clobbering user edits to learned
    rule files.
    """

    learned_rule = with_learned_rule_integrity(rule)
    target = learned_rule_path(layout, learned_rule)
    if target.exists() or target.is_symlink():
        raise LearnedRuleExistsError(f"learned rule already exists: {target}")
    atomic_write_yaml(learned_rule_payload(learned_rule), target)
    return target


def write_experience(
    layout: NamespaceLayout,
    experience: Experience | Mapping[str, Any],
) -> Path:
    """Write one user experience YAML.

    Callers must hold the workspace lock before invoking this function. The
    helper refuses existing paths so agent writes do not clobber user-edited
    validation counters, audit notes, or trust state.
    """

    validated = with_experience_local_integrity(experience)
    target = experience_path(layout, validated)
    if target.exists() or target.is_symlink():
        raise ExperienceExistsError(f"experience already exists: {target}")
    atomic_write_yaml(experience_payload(validated), target)
    return target


def load_trial_record(path: str | Path) -> TrialRecord:
    """Load one immutable trial YAML and verify its integrity block."""

    trial_path = Path(path)
    if trial_path.is_symlink():
        raise TrialLoadError(f"trial record path must not be a symlink: {trial_path}")
    try:
        file_size = trial_path.stat().st_size
    except FileNotFoundError as exc:
        raise TrialLoadError(f"trial record file not found: {trial_path}") from exc
    if file_size > MAX_TRIAL_RECORD_BYTES:
        raise TrialLoadError(
            f"trial record file {trial_path} is too large "
            f"({file_size} bytes > {MAX_TRIAL_RECORD_BYTES} bytes)"
        )

    try:
        raw_text = trial_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TrialLoadError(f"trial record file {trial_path} is not valid UTF-8") from exc

    try:
        data = yaml.load(raw_text, Loader=TrialYamlLoader)
    except yaml.YAMLError as exc:
        raise TrialLoadError(
            f"trial record file {trial_path} failed to parse YAML: {exc}"
        ) from exc

    if not data:
        raise TrialLoadError(f"trial record file {trial_path} is empty")
    if not isinstance(data, Mapping):
        raise TrialLoadError(f"trial record file {trial_path} must contain a YAML mapping")

    try:
        trial = TrialRecord.model_validate(data)
    except ValidationError as exc:
        raise TrialLoadError(f"trial record file {trial_path} is invalid:\n{exc}") from exc

    if trial.integrity is None:
        raise TrialIntegrityError(f"trial record file {trial_path} is missing integrity")
    if not verify_trial_integrity(trial):
        raise TrialIntegrityError(f"trial record file {trial_path} failed integrity check")
    return trial


def load_trial_record_for_layout(layout: NamespaceLayout, path: str | Path) -> TrialRecord:
    """Load one trial YAML and ensure namespace and path match the layout."""

    trial_path = Path(path)
    trial = load_trial_record(trial_path)
    _validate_discovered_trial(layout, trial_path, trial)
    return trial


def load_learned_rule(path: str | Path) -> LearnedRule:
    """Load one learned rule YAML and verify its integrity block."""

    rule_path = Path(path)
    if rule_path.is_symlink():
        raise LearnedRuleLoadError(f"learned rule path must not be a symlink: {rule_path}")
    try:
        file_size = rule_path.stat().st_size
    except FileNotFoundError as exc:
        raise LearnedRuleLoadError(f"learned rule file not found: {rule_path}") from exc
    if file_size > MAX_LEARNED_RULE_BYTES:
        raise LearnedRuleLoadError(
            f"learned rule file {rule_path} is too large "
            f"({file_size} bytes > {MAX_LEARNED_RULE_BYTES} bytes)"
        )

    try:
        raw_text = rule_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LearnedRuleLoadError(f"learned rule file {rule_path} is not valid UTF-8") from exc

    try:
        data = yaml.load(raw_text, Loader=LearnedRuleYamlLoader)
    except yaml.YAMLError as exc:
        raise LearnedRuleLoadError(
            f"learned rule file {rule_path} failed to parse YAML: {exc}"
        ) from exc

    if not data:
        raise LearnedRuleLoadError(f"learned rule file {rule_path} is empty")
    if not isinstance(data, Mapping):
        raise LearnedRuleLoadError(
            f"learned rule file {rule_path} must contain a YAML mapping"
        )

    try:
        learned_rule = LearnedRule.model_validate(data)
    except ValidationError as exc:
        raise LearnedRuleLoadError(
            f"learned rule file {rule_path} is invalid:\n{exc}"
        ) from exc

    if learned_rule.integrity is None:
        raise LearnedRuleIntegrityError(
            f"learned rule file {rule_path} is missing integrity"
        )
    if not verify_learned_rule_integrity(learned_rule):
        raise LearnedRuleIntegrityError(
            f"learned rule file {rule_path} failed integrity check"
        )
    return learned_rule


def load_experience(path: str | Path) -> Experience:
    """Load one experience YAML and verify its local integrity block."""

    experience_file = Path(path)
    if experience_file.is_symlink():
        raise ExperienceLoadError(f"experience path must not be a symlink: {experience_file}")
    try:
        file_size = experience_file.stat().st_size
    except FileNotFoundError as exc:
        raise ExperienceLoadError(f"experience file not found: {experience_file}") from exc
    if file_size > MAX_EXPERIENCE_BYTES:
        raise ExperienceLoadError(
            f"experience file {experience_file} is too large "
            f"({file_size} bytes > {MAX_EXPERIENCE_BYTES} bytes)"
        )

    try:
        raw_text = experience_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ExperienceLoadError(f"experience file {experience_file} is not valid UTF-8") from exc

    try:
        data = yaml.load(raw_text, Loader=ExperienceYamlLoader)
    except yaml.YAMLError as exc:
        raise ExperienceLoadError(
            f"experience file {experience_file} failed to parse YAML: {exc}"
        ) from exc

    if not data:
        raise ExperienceLoadError(f"experience file {experience_file} is empty")
    if not isinstance(data, Mapping):
        raise ExperienceLoadError(
            f"experience file {experience_file} must contain a YAML mapping"
        )

    try:
        experience = Experience.model_validate(data)
    except ValidationError as exc:
        raise ExperienceLoadError(
            f"experience file {experience_file} is invalid:\n{exc}"
        ) from exc

    if experience.local_integrity is None:
        raise ExperienceIntegrityError(
            f"experience file {experience_file} is missing local_integrity"
        )
    if not verify_experience_local_integrity(experience):
        raise ExperienceIntegrityError(
            f"experience file {experience_file} failed local integrity check"
        )
    return experience


def iter_trial_record_paths(layout: NamespaceLayout) -> tuple[Path, ...]:
    """Return canonical trial YAML paths under `trials/data`, sorted by path."""

    if not layout.trial_data_dir.exists():
        return ()
    if not layout.trial_data_dir.is_dir():
        raise TrialDiscoveryError(f"trial data path is not a directory: {layout.trial_data_dir}")
    return tuple(
        sorted(
            (
                path
                for path in layout.trial_data_dir.rglob("*.yaml")
                if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
            ),
            key=lambda path: path.as_posix(),
        )
    )


def discover_trial_records(layout: NamespaceLayout) -> tuple[DiscoveredTrialRecord, ...]:
    """Discover immutable trial YAML records from the canonical SoT directory."""

    discovered: list[DiscoveredTrialRecord] = []
    for path in iter_trial_record_paths(layout):
        trial = load_trial_record_for_layout(layout, path)
        discovered.append(DiscoveredTrialRecord(path=path, record=trial))
    return tuple(discovered)


def collect_trial_startup_validation_inputs(
    layout: NamespaceLayout,
    *,
    compiler_type: str,
) -> TrialStartupValidationInputs:
    """Collect existing trial facts needed by startup registry validation."""

    if not isinstance(compiler_type, str):
        raise TrialDiscoveryError("compiler_type must be a string")
    _validate_file_atom(compiler_type, "compiler_type")

    discovered = discover_trial_records(layout)
    compiler_versions = tuple(
        sorted(
            {
                _compiler_version_from_namespace(
                    item.record.namespace,
                    compiler_type=compiler_type,
                )
                for item in discovered
            }
        )
    )
    return TrialStartupValidationInputs(
        compiler_versions=compiler_versions,
        trial_count=len(discovered),
        trial_ids=tuple(item.record.trial_id for item in discovered),
    )


def existing_trial_compiler_versions(
    layout: NamespaceLayout,
    *,
    compiler_type: str,
) -> tuple[str, ...]:
    """Return unique compiler.version values from existing trial YAML SoT files."""

    return collect_trial_startup_validation_inputs(
        layout,
        compiler_type=compiler_type,
    ).compiler_versions


def rebuild_trial_index(
    layout: NamespaceLayout,
    *,
    discovered: Sequence[DiscoveredTrialRecord] | None = None,
) -> TrialIndexSummary:
    """Rebuild `trials/_index.sqlite` from canonical trial YAML.

    The index is derived state. Callers that rebuild during startup or a run
    should hold the workspace lock so readers never coordinate through a stale
    cache while another process is replacing it.
    """

    records = tuple(discovered) if discovered is not None else discover_trial_records(layout)
    target = layout.trial_index_path
    if target.exists() and target.is_dir():
        raise TrialIndexError(f"trial index path is a directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.{os.getpid()}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(fd)
    temp_path = Path(temp_name)
    rebuilt_at = datetime.now(UTC).isoformat()

    try:
        rows = [_trial_index_row_for_discovered(layout, item) for item in records]
        summary = TrialIndexSummary(
            index_path=target,
            schema_version=TRIAL_INDEX_SCHEMA_VERSION,
            trial_count=len(rows),
            rebuilt_at=rebuilt_at,
            source_latest_mtime_ns=max((row.source_mtime_ns for row in rows), default=None),
        )
        _write_trial_index_database(temp_path, rows, summary)
        _fsync_file(temp_path)
        os.replace(temp_path, target)
        _cleanup_sqlite_sidecars(target)
        _fsync_parent_dir(target.parent)
        return summary
    except Exception as exc:
        _cleanup_sqlite_temp_files(temp_path)
        if isinstance(exc, TrialRecordError):
            raise
        raise TrialIndexError(f"failed to rebuild trial index {target}: {exc}") from exc


def load_trial_index_summary(layout: NamespaceLayout) -> TrialIndexSummary:
    """Load metadata from the rebuildable trial SQLite index."""

    conn = _open_trial_index(layout.trial_index_path)
    try:
        meta = dict(conn.execute("SELECT key, value FROM trial_index_meta").fetchall())
        schema_version = int(meta.get("schema_version", "0"))
        if schema_version != TRIAL_INDEX_SCHEMA_VERSION:
            raise TrialIndexError(
                "unsupported trial index schema version "
                f"{schema_version!r}; expected {TRIAL_INDEX_SCHEMA_VERSION}"
            )
        source_latest = meta.get("source_latest_mtime_ns")
        return TrialIndexSummary(
            index_path=layout.trial_index_path,
            schema_version=schema_version,
            trial_count=int(meta.get("trial_count", "0")),
            rebuilt_at=meta.get("rebuilt_at", ""),
            source_latest_mtime_ns=int(source_latest) if source_latest else None,
        )
    except (sqlite3.Error, ValueError) as exc:
        raise TrialIndexError(f"failed to load trial index summary: {exc}") from exc
    finally:
        conn.close()


def load_trial_index_rows(layout: NamespaceLayout) -> tuple[TrialIndexRow, ...]:
    """Load rows from the rebuildable trial SQLite index."""

    _ = load_trial_index_summary(layout)
    conn = _open_trial_index(layout.trial_index_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT trial_id, relative_path, namespace, round, timestamp, duration_sec,
                   combo_hash, combo_yaml, mode, candidate_source, schedule_slot,
                   bench_level, outcome, score_geomean, baseline_normalized,
                   objective_direction, integrity_hash, source_mtime_ns
            FROM trials
            ORDER BY timestamp, trial_id
            """
        ).fetchall()
        return tuple(_trial_index_row_from_sql(row) for row in rows)
    except (sqlite3.Error, yaml.YAMLError, TypeError, ValueError) as exc:
        raise TrialIndexError(f"failed to load trial index rows: {exc}") from exc
    finally:
        conn.close()


def trial_index_is_stale(layout: NamespaceLayout) -> bool:
    """Return true when trial YAML and the derived SQLite index disagree."""

    if not layout.trial_index_path.exists():
        return True
    paths = iter_trial_record_paths(layout)
    try:
        summary = load_trial_index_summary(layout)
    except TrialIndexError:
        return True
    if summary.trial_count != len(paths):
        return True
    index_mtime_ns = layout.trial_index_path.stat().st_mtime_ns
    return any(path.stat().st_mtime_ns > index_mtime_ns for path in paths)


def ensure_trial_index_current(layout: NamespaceLayout) -> TrialIndexSummary:
    """Rebuild the trial index if missing, stale, corrupt, or schema-incompatible."""

    if trial_index_is_stale(layout):
        return rebuild_trial_index(layout)
    try:
        return load_trial_index_summary(layout)
    except TrialIndexError:
        return rebuild_trial_index(layout)


def trace_event_payload(event: TraceEvent | Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical JSON-compatible mapping for one trace event."""

    validated = TraceEvent.model_validate(event)
    return validated.model_dump(mode="json")


def append_trace_event(
    layout: NamespaceLayout,
    event: TraceEvent | Mapping[str, Any],
    *,
    expected_line_number: int | None = None,
) -> TraceAppendResult:
    """Append one canonical event to `trace/events.jsonl`.

    Callers must hold the workspace lock before invoking this function during
    normal runs. The append path uses `O_APPEND`, writes exactly one LF-terminated
    JSON object, fsyncs the file, and rejects symlink targets. The write path
    does not scan existing trace files; callers that need `events.jsonl#L<N>`
    should pass their lock-protected `expected_line_number`.
    """

    if expected_line_number is not None and expected_line_number <= 0:
        raise TraceWriteError("expected_line_number must be positive")
    payload = trace_event_payload(event)
    line = _trace_event_line(payload)
    target = layout.trace_path
    if len(line) > MAX_TRACE_EVENT_BYTES:
        raise TraceWriteError(
            f"trace event is too large ({len(line)} bytes > {MAX_TRACE_EVENT_BYTES} bytes)"
        )
    if target.is_symlink():
        raise TraceWriteError(f"trace path must not be a symlink: {target}")
    if target.exists() and target.is_dir():
        raise TraceWriteError(f"trace path is a directory: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existed = target.exists()
        byte_offset = target.stat().st_size if existed else 0
        if byte_offset > 0 and not _file_ends_with_newline(target):
            raise TraceWriteError(f"trace file is not newline-terminated: {target}")
        if byte_offset == 0:
            line_number = 1 if expected_line_number is None else expected_line_number
            if line_number != 1:
                raise TraceWriteError(
                    "expected_line_number must be 1 when creating a new trace file"
                )
        elif expected_line_number == 1:
            raise TraceWriteError(
                "expected_line_number cannot be 1 for a non-empty trace file"
            )
        else:
            line_number = expected_line_number
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            _write_all(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        if not existed:
            _fsync_parent_dir(target.parent)
        return TraceAppendResult(
            path=target,
            line_number=line_number,
            byte_offset=byte_offset,
        )
    except TraceWriteError:
        raise
    except OSError as exc:
        raise TraceWriteError(f"failed to append trace event to {target}: {exc}") from exc


def iter_trace_events(path: str | Path) -> Iterator[TraceEvent]:
    """Yield validated events from one canonical `events.jsonl` file."""

    yield from _iter_trace_events(path)


def load_trace_events(path: str | Path) -> tuple[TraceEvent, ...]:
    """Load and validate all events from one canonical `events.jsonl` file."""

    return tuple(iter_trace_events(path))


def _iter_trace_events(path: str | Path) -> Iterator[TraceEvent]:
    """Stream validated events from one canonical `events.jsonl` file."""

    trace_path = Path(path)
    if trace_path.is_symlink():
        raise TraceLoadError(f"trace path must not be a symlink: {trace_path}")
    if not trace_path.exists():
        return ()
    if trace_path.is_dir():
        raise TraceLoadError(f"trace path is a directory: {trace_path}")

    try:
        with trace_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if len(raw_line) > MAX_TRACE_EVENT_BYTES:
                    raise TraceLoadError(
                        f"trace line {line_number} is too large "
                        f"({len(raw_line)} bytes > {MAX_TRACE_EVENT_BYTES} bytes)"
                    )
                if not raw_line.endswith(b"\n"):
                    raise TraceLoadError(
                        f"trace line {line_number} is not newline-terminated"
                    )
                try:
                    text = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise TraceLoadError(
                        f"trace line {line_number} is not valid UTF-8"
                    ) from exc
                text = text[:-1]
                if not text.strip():
                    raise TraceLoadError(f"trace line {line_number} is empty")
                try:
                    data = json.loads(text, parse_constant=_reject_json_constant)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise TraceLoadError(
                        f"trace line {line_number} failed to parse JSON: {exc}"
                    ) from exc
                if not isinstance(data, Mapping):
                    raise TraceLoadError(
                        f"trace line {line_number} must contain a JSON object"
                    )
                try:
                    yield TraceEvent.model_validate(data)
                except ValidationError as exc:
                    raise TraceLoadError(
                        f"trace line {line_number} is invalid:\n{exc}"
                    ) from exc
    except TraceLoadError:
        raise
    except OSError as exc:
        raise TraceLoadError(f"failed to load trace file {trace_path}: {exc}") from exc


def checkpoint_payload(state: CheckpointState | Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = CheckpointState.model_validate(state)
    return checkpoint.model_dump(mode="json", exclude_none=True)


def write_checkpoint_state(
    layout: NamespaceLayout,
    state: CheckpointState | Mapping[str, Any],
) -> Path:
    """Write the mutable canonical recovery checkpoint.

    Callers must hold the workspace lock before invoking this function because
    `checkpoint.yaml` is overwritten as a session progresses.
    """

    checkpoint = CheckpointState.model_validate(state)
    expected_namespace = str(layout.namespace)
    if checkpoint.namespace != expected_namespace:
        raise CheckpointError(
            "checkpoint namespace does not match layout "
            f"(expected={expected_namespace!r}, actual={checkpoint.namespace!r})"
        )
    atomic_write_yaml(checkpoint_payload(checkpoint), layout.checkpoint_path)
    return layout.checkpoint_path


def load_checkpoint_state(path: str | Path) -> CheckpointState:
    checkpoint_path = Path(path)
    try:
        file_size = checkpoint_path.stat().st_size
    except FileNotFoundError as exc:
        raise CheckpointLoadError(f"checkpoint file not found: {checkpoint_path}") from exc
    if file_size > MAX_CHECKPOINT_BYTES:
        raise CheckpointLoadError(
            f"checkpoint file {checkpoint_path} is too large "
            f"({file_size} bytes > {MAX_CHECKPOINT_BYTES} bytes)"
        )

    try:
        raw_text = checkpoint_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CheckpointLoadError(
            f"checkpoint file {checkpoint_path} is not valid UTF-8"
        ) from exc

    try:
        data = yaml.load(raw_text, Loader=CheckpointYamlLoader)
    except yaml.YAMLError as exc:
        raise CheckpointLoadError(
            f"checkpoint file {checkpoint_path} failed to parse YAML: {exc}"
        ) from exc

    if not data:
        raise CheckpointLoadError(f"checkpoint file {checkpoint_path} is empty")
    if not isinstance(data, Mapping):
        raise CheckpointLoadError(
            f"checkpoint file {checkpoint_path} must contain a YAML mapping"
        )

    try:
        return CheckpointState.model_validate(data)
    except ValidationError as exc:
        raise CheckpointLoadError(f"checkpoint file {checkpoint_path} is invalid:\n{exc}") from exc


def load_checkpoint_for_layout(layout: NamespaceLayout) -> CheckpointState:
    checkpoint = load_checkpoint_state(layout.checkpoint_path)
    expected_namespace = str(layout.namespace)
    if checkpoint.namespace != expected_namespace:
        raise CheckpointLoadError(
            "checkpoint namespace does not match layout "
            f"(expected={expected_namespace!r}, actual={checkpoint.namespace!r})"
        )
    return checkpoint


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


def _canonical_yaml_bytes(payload: Any) -> bytes:
    text = yaml.dump(
        payload,
        Dumper=SotYamlDumper,
        sort_keys=True,
        allow_unicode=True,
    )
    return text.encode("utf-8")


def _remove_mapping_path(payload: dict[str, Any], field_path: str) -> None:
    current: Any = payload
    parts = field_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _validate_sha256_digest(value: str, label: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{label} must start with 'sha256:'")
    hexdigest = value[len(prefix) :]
    if len(hexdigest) != 64:
        raise ValueError(f"{label} must contain a 64-character sha256 digest")
    try:
        int(hexdigest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be hexadecimal") from exc


def _datetime_to_utc_isoformat(value: Any, label: str) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError(f"{label} datetime must be UTC timezone-aware")
        return value.astimezone(UTC).isoformat()
    return value


def _parse_utc_isoformat(value: str, label: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC timezone-aware ISO 8601")
    return parsed.astimezone(UTC)


def _validate_file_atom(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} cannot be empty")
    if value != value.strip():
        raise ValueError(f"{label} cannot contain surrounding whitespace")
    if value in {".", ".."}:
        raise ValueError(f"{label} cannot be {value!r}")
    if "/" in value or "\\" in value:
        raise ValueError(f"{label} cannot contain path separators")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} cannot contain control characters")


def _validate_option_string(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must contain non-empty strings")
    if value != value.strip():
        raise ValueError(f"{label} cannot contain surrounding whitespace")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} cannot contain control characters")


def _validate_untrimmed_non_control_string(value: str, label: str) -> None:
    if value != value.strip():
        raise ValueError(f"{label} cannot contain surrounding whitespace")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} cannot contain control characters")


def _validate_trace_kind(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} cannot be empty")
    if not all(
        char.isascii() and (char.isalnum() or char in {"_", "-", "."})
        for char in value
    ):
        raise ValueError(
            f"{label} can contain only ASCII letters, digits, '_', '-', or '.'"
        )


def _validate_json_value(value: Any, label: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} cannot contain non-finite floats")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} JSON object keys must be strings")
            _validate_json_value(nested, f"{label}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_json_value(nested, f"{label}[{index}]")
        return
    raise ValueError(f"{label} contains non-JSON value {type(value).__name__}")


def _trace_event_line(payload: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TraceWriteError(f"trace event is not JSON serializable: {exc}") from exc
    return f"{text}\n".encode("utf-8")


def _file_ends_with_newline(path: Path) -> bool:
    with path.open("rb") as handle:
        handle.seek(-1, os.SEEK_END)
        return handle.read(1) == b"\n"


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    total_written = 0
    while total_written < len(data):
        written = os.write(fd, view[total_written:])
        if written == 0:
            raise OSError("short write while appending trace event")
        total_written += written


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON constant {value!r} is not allowed")


def _validate_experience_item_file(value: str, label: str) -> None:
    if "\\" in value:
        raise ValueError(f"{label} must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(f"{label} cannot be absolute")
    if ".." in path.parts:
        raise ValueError(f"{label} cannot contain parent segments")
    if path.as_posix() != value:
        raise ValueError(f"{label} must be normalized")
    if len(path.parts) != 2 or path.parts[0] != "experiences":
        raise ValueError(f"{label} must match experiences/*.yaml")
    if path.suffix != ".yaml":
        raise ValueError(f"{label} must end with .yaml")
    if path.name.startswith("."):
        raise ValueError(f"{label} cannot use hidden file names")
    if any(char.isspace() for char in path.name):
        raise ValueError(f"{label} cannot contain whitespace")
    _validate_file_atom(path.name, label)


def _validate_namespace_string(value: str, label: str) -> None:
    parts = value.split("/")
    if len(parts) != 5:
        raise ValueError(f"{label} must contain exactly 5 path segments")
    for index, part in enumerate(parts, start=1):
        _validate_file_atom(part, f"{label} segment {index}")


def _write_trial_index_database(
    path: Path,
    rows: Sequence[TrialIndexRow],
    summary: TrialIndexSummary,
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA user_version = {TRIAL_INDEX_SCHEMA_VERSION}")
        conn.executescript(
            """
            CREATE TABLE trial_index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE trials (
                trial_id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                namespace TEXT NOT NULL,
                round INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                combo_hash TEXT NOT NULL,
                combo_yaml TEXT NOT NULL,
                mode TEXT NOT NULL,
                candidate_source TEXT NOT NULL,
                schedule_slot TEXT NOT NULL,
                bench_level TEXT NOT NULL,
                outcome TEXT NOT NULL,
                score_geomean REAL,
                baseline_normalized REAL,
                objective_direction TEXT,
                integrity_hash TEXT NOT NULL,
                source_mtime_ns INTEGER NOT NULL
            );

            CREATE INDEX trials_timestamp_idx ON trials(timestamp);
            CREATE INDEX trials_outcome_idx ON trials(outcome);
            CREATE INDEX trials_combo_hash_idx ON trials(combo_hash);
            """
        )
        _insert_trial_index_rows(conn, rows)
        conn.executemany(
            "INSERT INTO trial_index_meta(key, value) VALUES (?, ?)",
            [
                ("schema_version", str(summary.schema_version)),
                ("index_type", "trials"),
                ("rebuilt_at", summary.rebuilt_at),
                ("trial_count", str(summary.trial_count)),
                (
                    "source_latest_mtime_ns",
                    "" if summary.source_latest_mtime_ns is None else str(summary.source_latest_mtime_ns),
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_trial_index_rows(conn: sqlite3.Connection, rows: Sequence[TrialIndexRow]) -> None:
    conn.executemany(
        """
        INSERT INTO trials(
            trial_id, relative_path, namespace, round, timestamp, duration_sec,
            combo_hash, combo_yaml, mode, candidate_source, schedule_slot,
            bench_level, outcome, score_geomean, baseline_normalized,
            objective_direction, integrity_hash, source_mtime_ns
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.trial_id,
                row.relative_path,
                row.namespace,
                row.round,
                row.timestamp,
                row.duration_sec,
                row.combo_hash,
                yaml.dump(
                    list(row.combo),
                    Dumper=SotYamlDumper,
                    sort_keys=False,
                    allow_unicode=True,
                ),
                row.mode,
                row.candidate_source,
                row.schedule_slot,
                row.bench_level,
                row.outcome,
                row.score_geomean,
                row.baseline_normalized,
                row.objective_direction,
                row.integrity_hash,
                row.source_mtime_ns,
            )
            for row in rows
        ],
    )


def _open_trial_index(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise TrialIndexError(f"trial index file not found: {path}")
    try:
        return sqlite3.connect(path)
    except sqlite3.Error as exc:
        raise TrialIndexError(f"failed to open trial index {path}: {exc}") from exc


def _trial_index_row_for_discovered(
    layout: NamespaceLayout,
    discovered: DiscoveredTrialRecord,
) -> TrialIndexRow:
    trial = discovered.record
    if trial.integrity is None:
        raise TrialIntegrityError(f"trial {trial.trial_id!r} is missing integrity")
    try:
        relative_path = discovered.path.relative_to(layout.namespace_dir).as_posix()
        source_mtime_ns = discovered.path.stat().st_mtime_ns
    except (OSError, ValueError) as exc:
        raise TrialIndexError(
            f"cannot index trial {trial.trial_id!r} at {discovered.path}: {exc}"
        ) from exc
    return TrialIndexRow(
        trial_id=trial.trial_id,
        relative_path=relative_path,
        namespace=trial.namespace,
        round=trial.round,
        timestamp=trial.timestamp,
        duration_sec=trial.duration_sec,
        combo_hash=trial.combo_hash,
        combo=tuple(trial.combo),
        mode=trial.mode,
        candidate_source=trial.candidate_source,
        schedule_slot=trial.schedule_slot,
        bench_level=trial.bench_level,
        outcome=trial.outcome,
        score_geomean=trial.score.geomean if trial.score is not None else None,
        baseline_normalized=trial.score.baseline_normalized if trial.score is not None else None,
        objective_direction=trial.score.objective_direction if trial.score is not None else None,
        integrity_hash=trial.integrity.payload_hash,
        source_mtime_ns=source_mtime_ns,
    )


def _trial_index_row_from_sql(row: sqlite3.Row) -> TrialIndexRow:
    combo = yaml.safe_load(row["combo_yaml"])
    if not isinstance(combo, list) or not all(isinstance(option, str) for option in combo):
        raise ValueError("trial index combo_yaml must decode to a list of strings")
    return TrialIndexRow(
        trial_id=row["trial_id"],
        relative_path=row["relative_path"],
        namespace=row["namespace"],
        round=row["round"],
        timestamp=row["timestamp"],
        duration_sec=row["duration_sec"],
        combo_hash=row["combo_hash"],
        combo=tuple(combo),
        mode=row["mode"],
        candidate_source=row["candidate_source"],
        schedule_slot=row["schedule_slot"],
        bench_level=row["bench_level"],
        outcome=row["outcome"],
        score_geomean=row["score_geomean"],
        baseline_normalized=row["baseline_normalized"],
        objective_direction=row["objective_direction"],
        integrity_hash=row["integrity_hash"],
        source_mtime_ns=row["source_mtime_ns"],
    )


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _cleanup_sqlite_temp_files(path: Path) -> None:
    for candidate in (path, Path(f"{path}-journal"), Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except OSError:
            pass


def _cleanup_sqlite_sidecars(path: Path) -> None:
    for candidate in (Path(f"{path}-journal"), Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except OSError:
            pass


def _validate_discovered_trial(
    layout: NamespaceLayout,
    path: Path,
    trial: TrialRecord,
) -> None:
    expected_namespace = str(layout.namespace)
    if trial.namespace != expected_namespace:
        raise TrialDiscoveryError(
            "trial namespace does not match layout "
            f"(path={path}, expected={expected_namespace!r}, actual={trial.namespace!r})"
        )
    expected_path = trial_record_path(layout, trial)
    if path != expected_path:
        raise TrialDiscoveryError(
            "trial record path does not match trial identity "
            f"(expected={expected_path}, actual={path})"
        )


def _compiler_version_from_namespace(namespace: str, *, compiler_type: str) -> str:
    """Extract compiler.version when compiler_type exactly matches namespace construction."""

    _validate_namespace_string(namespace, "trial.namespace")
    compiler_segment = namespace.split("/")[2]
    prefix = f"{compiler_type}-"
    if not compiler_segment.startswith(prefix) or compiler_segment == prefix:
        raise TrialDiscoveryError(
            "trial compiler segment does not match configured compiler_type "
            f"(compiler_type={compiler_type!r}, compiler_segment={compiler_segment!r})"
        )
    compiler_version = compiler_segment[len(prefix) :]
    _validate_file_atom(compiler_version, "compiler.version")
    return compiler_version
