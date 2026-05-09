"""FS-Memory filesystem helpers and atomic SoT writes.

This module implements the Phase 02 foundation from REQUIREMENTS.md sections
4.2.3 and 4.7.5. User-readable files remain the source of truth; indexes and
caches must be rebuildable from these paths.
"""

from __future__ import annotations

import os
import hashlib
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


MAX_CHECKPOINT_BYTES = 1_048_576
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
    score: float = Field(gt=0)

    @field_validator("trial_id")
    @classmethod
    def trial_id_must_be_file_safe(cls, value: str) -> str:
        _validate_file_atom(value, "current_best.trial_id")
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
