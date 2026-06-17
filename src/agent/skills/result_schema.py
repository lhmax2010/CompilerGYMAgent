"""Shared compile/benchmark result schemas for Phase 05 skills."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.candidate_identity import (
    CandidateCanonicalizationSpec,
    CanonicalCandidate,
    canonicalize_candidate,
    compute_canonical_combo_hash,
)
from agent.config import NonEmptyStr


FailureCategory = Literal[
    "invalid_option",
    "option_conflict",
    "compiler_crash",
    "build_timeout",
    "build_system_failure",
    "dependency_missing",
    "disk_full_or_quota",
    "permission_denied",
    "oom_killed",
    "network_failure",
    "source_dirty",
    "spec_corruption",
    "artifact_missing",
    "infra_failure",
    "unknown_failure",
    "benchmark_timeout",
    "benchmark_crash",
    "score_parse_failed",
    "functional_correctness_failed",
    "artifact_invalid",
    "environment_unstable",
    "too_noisy",
]
FailureRoute = Literal["option_related", "environment_related", "unknown"]
FailureConfidence = Literal["HIGH", "MEDIUM", "LOW"]
RunPhase = Literal["warmup", "measured"]
ObjectiveDirection = Literal["higher_is_better", "lower_is_better"]
StatisticalVerdict = Literal[
    "significant_improvement",
    "significant_regression",
    "inconclusive",
    "no_difference",
]
ComparisonScope = Literal["single_comparison"]
ExploratorySignal = Literal[
    "suggestive_improvement",
    "suggestive_regression",
    "none",
]
PairOrder = Literal["baseline_first", "candidate_first"]
PairQuality = Literal["good", "suspect", "unknown"]
MeasurementPlanType = Literal["screen", "confirmation"]


class StrictResultSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceLine(StrictResultSchemaModel):
    """Evidence backing a failure classification."""

    log_ref: NonEmptyStr
    text: NonEmptyStr
    pattern_id: NonEmptyStr


class FailureClassification(StrictResultSchemaModel):
    """Structured failure classification with conservative memory routing."""

    category: FailureCategory = "unknown_failure"
    route: FailureRoute = "unknown"
    confidence: FailureConfidence = "LOW"
    evidence: tuple[EvidenceLine, ...] = ()
    affected_options: tuple[NonEmptyStr, ...] = ()
    retryable: bool = False
    write_failed_combos: bool = False
    matched_rule_id: NonEmptyStr | None = None
    classifier_version: NonEmptyStr = "failure_classifier.v1"

    @model_validator(mode="after")
    def failed_combo_write_requires_high_confidence_option_route(
        self,
    ) -> FailureClassification:
        if self.write_failed_combos and not (
            self.route == "option_related" and self.confidence == "HIGH"
        ):
            raise ValueError(
                "write_failed_combos requires route='option_related' "
                "and confidence='HIGH'"
            )
        if self.write_failed_combos and not self.affected_options:
            raise ValueError("write_failed_combos requires affected_options")
        return self


class RunEnvironmentSnapshot(StrictResultSchemaModel):
    """Minimal environment context captured for a benchmark run."""

    loadavg_1m: float | None = None
    loadavg_5m: float | None = None
    loadavg_15m: float | None = None
    cpu_governor: NonEmptyStr | None = None
    cpu_freq_mhz: float | None = Field(default=None, ge=0)
    thermal_throttle: bool | None = None
    mem_available_bytes: int | None = Field(default=None, ge=0)

    @field_validator("loadavg_1m", "loadavg_5m", "loadavg_15m", "cpu_freq_mhz")
    @classmethod
    def environment_floats_must_be_finite(
        cls, value: float | None, info: Any
    ) -> float | None:
        return _validate_optional_finite(value, info.field_name)


class RunSummaryHint(StrictResultSchemaModel):
    """Optional aggregate hint; Phase 08 owns final statistical decisions."""

    mean: float | None = None
    median: float | None = None
    stddev: float | None = Field(default=None, ge=0)
    cv: float | None = Field(default=None, ge=0)
    n_measured: int = Field(default=0, ge=0)
    n_valid: int = Field(default=0, ge=0)
    n_invalid: int = Field(default=0, ge=0)
    effective_sample_size: float | None = Field(default=None, ge=0)
    ess_preliminary: bool = False
    lag1_autocorrelation: float | None = Field(default=None, ge=-1, le=1)
    autocorrelation_detected: bool = False
    iid_assumption_valid: bool = True
    autocorrelation_warning: bool = False
    low_power: bool = False

    @field_validator(
        "mean",
        "median",
        "stddev",
        "cv",
        "effective_sample_size",
        "lag1_autocorrelation",
    )
    @classmethod
    def summary_numbers_must_be_finite(
        cls, value: float | None, info: Any
    ) -> float | None:
        return _validate_optional_finite(value, info.field_name)

    @model_validator(mode="after")
    def summary_counts_must_be_consistent(self) -> RunSummaryHint:
        if self.n_valid + self.n_invalid > self.n_measured:
            raise ValueError("n_valid + n_invalid cannot exceed n_measured")
        if (
            self.effective_sample_size is not None
            and self.effective_sample_size > self.n_valid
        ):
            raise ValueError("effective_sample_size cannot exceed n_valid")
        return self


class StatisticalResult(StrictResultSchemaModel):
    """Single-comparison statistical result produced by Phase 08a.

    `exploratory_signal` is non-decision-grade: it can prioritize paired
    confirmation work, but it must not accept/promote a candidate or update a
    champion. `pair_quality` makes the paired common-mode-noise assumption
    explicit so suspect pairs cannot masquerade as decision-grade evidence.
    """

    comparison: NonEmptyStr
    objective_direction: ObjectiveDirection
    point_estimate: float
    relative_effect_pct: float | None = None
    relative_ci_low_pct: float | None = None
    relative_ci_high_pct: float | None = None
    ci_low: float
    ci_high: float
    confidence_level: float = Field(gt=0, lt=1)
    method: NonEmptyStr
    p_value: float | None = Field(default=None, ge=0, le=1)
    verdict: StatisticalVerdict
    significant_single_comparison: bool = False
    comparison_scope: ComparisonScope = "single_comparison"
    adjusted_for_multiple_testing: bool = False
    n_measured: int = Field(ge=0)
    n_valid: int = Field(ge=0)
    n_invalid: int = Field(ge=0)
    baseline_n_valid: int = Field(ge=0)
    candidate_n_valid: int = Field(ge=0)
    effective_sample_size: float | None = Field(default=None, ge=0)
    ess_preliminary: bool = False
    lag1_autocorrelation: float | None = Field(default=None, ge=-1, le=1)
    autocorrelation_detected: bool = False
    iid_assumption_valid: bool = True
    low_power: bool = False
    recommend_more_runs: bool = False
    paired: bool = False
    pair_count: int = Field(default=0, ge=0)
    pair_quality: PairQuality = "unknown"
    block_size: int | None = Field(default=None, ge=2)
    baseline_block_size: int | None = Field(default=None, ge=2)
    candidate_block_size: int | None = Field(default=None, ge=2)
    exploratory_signal: ExploratorySignal = "none"
    requires_confirmation: bool = False
    provenance_complete: bool = True
    notes: tuple[NonEmptyStr, ...] = ()

    @field_validator(
        "point_estimate",
        "relative_effect_pct",
        "relative_ci_low_pct",
        "relative_ci_high_pct",
        "ci_low",
        "ci_high",
        "p_value",
        "effective_sample_size",
        "lag1_autocorrelation",
    )
    @classmethod
    def statistical_numbers_must_be_finite(
        cls, value: float | None, info: Any
    ) -> float | None:
        return _validate_optional_finite(value, info.field_name)

    @model_validator(mode="after")
    def statistical_result_must_be_consistent(self) -> StatisticalResult:
        if self.ci_low > self.ci_high:
            raise ValueError("ci_low cannot exceed ci_high")
        relative_ci_values = (self.relative_ci_low_pct, self.relative_ci_high_pct)
        if any(value is not None for value in relative_ci_values):
            if (
                self.relative_effect_pct is None
                or self.relative_ci_low_pct is None
                or self.relative_ci_high_pct is None
            ):
                raise ValueError("relative CI fields must all be present or all be None")
            relative_low = self.relative_ci_low_pct
            relative_effect = self.relative_effect_pct
            relative_high = self.relative_ci_high_pct
            assert relative_low is not None
            assert relative_effect is not None
            assert relative_high is not None
            if relative_low > relative_high:
                raise ValueError("relative_ci_low_pct cannot exceed relative_ci_high_pct")
            if not relative_low <= relative_effect <= relative_high:
                raise ValueError(
                    "relative_effect_pct must lie within the relative CI"
                )
        if self.n_valid + self.n_invalid > self.n_measured:
            raise ValueError("n_valid + n_invalid cannot exceed n_measured")
        if (
            self.effective_sample_size is not None
            and self.effective_sample_size > self.n_valid
        ):
            raise ValueError("effective_sample_size cannot exceed n_valid")
        expected_significant = _statistical_result_has_significant_verdict(self)
        if self.significant_single_comparison != expected_significant:
            raise ValueError(
                "significant_single_comparison must match the statistical verdict"
            )
        if self.adjusted_for_multiple_testing:
            raise ValueError("08a StatisticalResult is not multiple-testing adjusted")
        if self.comparison_scope != "single_comparison":
            raise ValueError("comparison_scope must be single_comparison")
        if self.paired and self.pair_count == 0:
            raise ValueError("paired results require pair_count")
        if self.exploratory_signal != "none":
            if self.verdict != "inconclusive":
                raise ValueError("exploratory_signal is non-decision-grade")
            if not self.requires_confirmation:
                raise ValueError("exploratory_signal requires confirmation")
        if self.paired and self.pair_quality != "good" and expected_significant:
            raise ValueError(
                "paired results require good pair_quality for decision-grade significant"
            )
        if (
            not self.paired
            and self.autocorrelation_detected
            and expected_significant
        ):
            raise ValueError(
                "unpaired autocorrelated results cannot be decision-grade significant"
            )
        return self


class MeasurementPlan(StrictResultSchemaModel):
    """Pre-registered measurement plan for 7.0/07 statistical comparisons."""

    measurement_plan_id: NonEmptyStr
    family_id: NonEmptyStr
    candidate_id: NonEmptyStr
    baseline_id: NonEmptyStr
    plan_type: MeasurementPlanType
    planned_n_pairs: int = Field(gt=0)
    abba_seed: NonEmptyStr
    pair_order: tuple[PairOrder, ...] = Field(min_length=1)
    created_at: NonEmptyStr

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
    def measurement_plan_must_match_planned_pairs(self) -> MeasurementPlan:
        if len(self.pair_order) != self.planned_n_pairs:
            raise ValueError("pair_order length must match planned_n_pairs")
        return self

    def to_trace_payload(self) -> dict[str, object]:
        """Return the JSON-compatible payload for a measurement_plan_created event."""

        return {
            "kind": "measurement_plan_created",
            "ts": self.created_at,
            "measurement_plan_id": self.measurement_plan_id,
            "family_id": self.family_id,
            "candidate_id": self.candidate_id,
            "baseline_id": self.baseline_id,
            "plan_type": self.plan_type,
            "planned_n_pairs": self.planned_n_pairs,
            "abba_seed": self.abba_seed,
            "pair_order": list(self.pair_order),
        }


class RunLevelRecord(StrictResultSchemaModel):
    """One benchmark run record consumed by Phase 08 statistics.

    `pair_order` and `pair_time_gap_sec` are pairing-quality metadata. Phase 7.0
    should generate randomized AB/BA pairs with small within-pair time gaps.
    """

    run_id: NonEmptyStr
    run_index: int = Field(ge=0)
    combo_hash: NonEmptyStr
    score: float | None = None
    phase: RunPhase
    metric_name: NonEmptyStr
    metric_unit: NonEmptyStr
    objective_direction: ObjectiveDirection
    duration_sec: float = Field(ge=0)
    started_at: NonEmptyStr
    ended_at: NonEmptyStr
    exit_code: int | None = None
    signal: int | None = Field(default=None, ge=0)
    stdout_ref: NonEmptyStr
    stderr_ref: NonEmptyStr
    env_snapshot: RunEnvironmentSnapshot = Field(default_factory=RunEnvironmentSnapshot)
    valid_for_scoring: bool
    invalid_reason: NonEmptyStr | None = None
    benchmark_cmd: tuple[NonEmptyStr, ...] = Field(min_length=1)
    artifact_ref: NonEmptyStr
    artifact_hash: NonEmptyStr | None = None
    artifact_hash_verified: bool = False
    score_source_ref: NonEmptyStr | None = None
    measurement_plan_id: NonEmptyStr | None = None
    source_commit: NonEmptyStr | None = None
    benchmark_id: NonEmptyStr | None = None
    benchmark_version: NonEmptyStr | None = None
    objective_id: NonEmptyStr | None = None
    pair_key: NonEmptyStr | None = None
    pair_order: PairOrder | None = None
    pair_time_gap_sec: float | None = Field(default=None, ge=0)
    failure_classification: FailureClassification | None = None
    summary_hint: RunSummaryHint | None = None

    @field_validator("combo_hash", "artifact_hash")
    @classmethod
    def hashes_must_be_sha256(cls, value: str | None, info: Any) -> str | None:
        if value is not None:
            _validate_sha256_digest(value, info.field_name)
        return value

    @field_validator("score", "pair_time_gap_sec")
    @classmethod
    def score_must_be_finite(cls, value: float | None, info: Any) -> float | None:
        return _validate_optional_finite(value, info.field_name)

    @field_validator("duration_sec")
    @classmethod
    def duration_must_be_finite(cls, value: float, info: Any) -> float:
        return _validate_finite(value, info.field_name)

    @field_validator("started_at", "ended_at", mode="before")
    @classmethod
    def datetime_to_utc_string(cls, value: Any, info: Any) -> Any:
        return _datetime_to_utc_isoformat(value, info.field_name)

    @field_validator("started_at", "ended_at")
    @classmethod
    def timestamps_must_be_utc_isoformat(cls, value: str, info: Any) -> str:
        _parse_utc_isoformat(value, info.field_name)
        return value

    @model_validator(mode="after")
    def run_consistency(self) -> RunLevelRecord:
        started_at = _parse_utc_isoformat(self.started_at, "started_at")
        ended_at = _parse_utc_isoformat(self.ended_at, "ended_at")
        if ended_at < started_at:
            raise ValueError("ended_at cannot be before started_at")
        if self.exit_code is not None and self.signal is not None:
            raise ValueError("exit_code and signal are mutually exclusive")
        if self.artifact_hash_verified and self.artifact_hash is None:
            raise ValueError("artifact_hash_verified requires artifact_hash")
        if self.valid_for_scoring:
            if self.score is None:
                raise ValueError("valid scoring runs must include score")
            if not self.artifact_hash_verified:
                raise ValueError("valid scoring runs require artifact_hash_verified")
            if self.failure_classification is not None:
                raise ValueError("valid scoring runs must not include failure_classification")
            if self.invalid_reason is not None:
                raise ValueError("valid scoring runs must not include invalid_reason")
        else:
            if self.failure_classification is None:
                raise ValueError("invalid scoring runs must include failure_classification")
            if self.invalid_reason is None:
                raise ValueError("invalid scoring runs must include invalid_reason")
        if (
            self.failure_classification is not None
            and self.failure_classification.category == "score_parse_failed"
            and self.score_source_ref is None
        ):
            raise ValueError("score_parse_failed runs must include score_source_ref")
        return self


def compute_combo_hash(
    combo: tuple[str, ...] | list[str],
    *,
    spec: CandidateCanonicalizationSpec | dict[str, Any] | None = None,
) -> str:
    """Return a deterministic sha256 hash for a compiler option combo."""

    return compute_canonical_combo_hash(combo, spec=spec)


def is_statistical_result_decision_grade(result: StatisticalResult) -> bool:
    """Return the schema-derived decision-grade predicate for a result."""

    validated = StatisticalResult.model_validate(result)
    if not _statistical_result_has_significant_verdict(validated):
        return False
    if validated.paired:
        return validated.pair_quality == "good"
    return validated.iid_assumption_valid and not validated.autocorrelation_detected


def _statistical_result_has_significant_verdict(result: StatisticalResult) -> bool:
    return result.verdict in {
        "significant_improvement",
        "significant_regression",
    }


def _validate_sha256_digest(value: str, label: str) -> None:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ValueError(f"{label} must start with 'sha256:'")
    digest = value[len(prefix) :]
    if len(digest) != 64:
        raise ValueError(f"{label} must contain a 64-character sha256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be hexadecimal") from exc


def _validate_optional_finite(value: float | None, label: str) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _validate_finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _datetime_to_utc_isoformat(value: Any, label: str) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")
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
    return parsed
