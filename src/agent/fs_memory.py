"""FS-Memory filesystem helpers and atomic SoT writes.

This module implements the Phase 02 foundation from REQUIREMENTS.md sections
4.2.3 and 4.7.5. User-readable files remain the source of truth; indexes and
caches must be rebuildable from these paths.
"""

from __future__ import annotations

import os
import hashlib
import math
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .config import AgentConfig, NonEmptyStr
from .registry import ProjectNamespace, compute_project_namespace


class FsMemoryError(RuntimeError):
    """Base error for FS-Memory failures."""


class AtomicWriteError(FsMemoryError):
    """Raised when an atomic SoT write cannot be completed."""


class TrialRecordError(FsMemoryError):
    """Raised when trial record data is invalid for FS-Memory use."""


class TrialImmutableError(TrialRecordError):
    """Raised when an immutable trial YAML path already exists."""


class TrialIntegrityError(TrialRecordError):
    """Raised when trial record integrity data is missing or invalid."""


class TrialLoadError(TrialRecordError):
    """Raised when immutable trial YAML cannot be parsed or validated."""


class TrialDiscoveryError(TrialLoadError):
    """Raised when discovered trial YAML does not match its FS layout."""


class TrialIndexError(TrialRecordError):
    """Raised when the rebuildable trial SQLite index cannot be used."""


class CheckpointError(FsMemoryError):
    """Raised when checkpoint state is invalid for FS-Memory use."""


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


MAX_TRIAL_RECORD_BYTES = 1_048_576
MAX_CHECKPOINT_BYTES = 1_048_576
TRIAL_INDEX_SCHEMA_VERSION = 1
TRIAL_HASH_FIELDS_EXCLUDED = ("integrity",)
TrialMode = Literal["exploit", "explore", "warmup", "canary", "mixed"]
CandidateSource = Literal["llm_proposal", "local_mutation", "weighted_random", "ablation"]
ScheduleSlot = Literal["exploit", "mutation", "novelty", "warmup", "canary"]
BenchLevel = Literal["build_only", "quick", "full"]
ObjectiveDirection = Literal["higher_is_better", "lower_is_better"]
BootstrapMode = Literal["paired", "unpaired"]
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
        if self.mode == "canary" and self.canary is None:
            raise ValueError("canary trials must include canary details")
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
        _validate_session_id_atom(value, "session_id")
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
    canonical_payload = {
        key: value for key, value in dict(payload).items() if key not in set(excluded_fields)
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
                if path.is_file() or path.is_symlink()
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
    """Return true when trial YAML is newer than the derived SQLite index."""

    if not layout.trial_index_path.exists():
        return True
    index_mtime_ns = layout.trial_index_path.stat().st_mtime_ns
    return any(path.stat().st_mtime_ns > index_mtime_ns for path in iter_trial_record_paths(layout))


def ensure_trial_index_current(layout: NamespaceLayout) -> TrialIndexSummary:
    """Rebuild the trial index if missing or older than canonical trial YAML."""

    if trial_index_is_stale(layout):
        return rebuild_trial_index(layout)
    return load_trial_index_summary(layout)


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


def _validate_namespace_string(value: str, label: str) -> None:
    parts = value.split("/")
    if len(parts) != 5:
        raise ValueError(f"{label} must contain exactly 5 path segments")
    for index, part in enumerate(parts, start=1):
        _validate_file_atom(part, f"{label} segment {index}")


def _validate_session_id_atom(value: str, label: str) -> None:
    _validate_file_atom(value, label)
    if not all(char.isascii() and (char.isalnum() or char in "_-") for char in value):
        raise ValueError(f"{label} can contain only ASCII letters, digits, '_' or '-'")


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
