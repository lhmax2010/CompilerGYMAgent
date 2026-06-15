"""Side-effect-free statistics helpers for benchmark run records.

08a intentionally refuses to claim significance for unpaired comparisons when
autocorrelation is detected. That is a design decision, not an implementation
gap: without pairing, time-correlated benchmark state is confounded with the
candidate/baseline label, and more samples alone do not remove that
confounding.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.skills.result_schema import RunLevelRecord, RunSummaryHint, StatisticalResult


MEAN_ZERO_ABS_TOL = 1e-12
HIGH_CV_THRESHOLD = 0.30
AUTOCORRELATION_RHO_THRESHOLD = 0.3
ESS_MIN = 3.0
LOW_POWER_ESS_MIN = 5.0
LOW_POWER_MEASURED_RUNS_MAX = 5
MIN_VALID_FOR_SIGNIFICANCE = 10
AUTOCORRELATED_MIN_VALID_FOR_SIGNIFICANCE = 60
DEFAULT_BOOTSTRAP_SAMPLES = 2000
DEFAULT_CONFIDENCE_LEVEL = 0.95
IID_PERCENTILE_BOOTSTRAP_METHOD = "iid_percentile_bootstrap"
MOVING_BLOCK_BOOTSTRAP_METHOD = "moving_block_bootstrap"
PAIR_QUALITY_GAP_DURATION_MULT = 5.0
PAIR_QUALITY_GAP_FLOOR_SEC = 5.0
PAIR_QUALITY_GAP_ABS_MAX_SEC = 300.0
PAIR_TIME_GAP_CONFLICT_RATIO = 10.0
PAIR_TIME_GAP_CONFLICT_ABS_SEC = 5.0
PAIR_RUN_OVERLAP_TOLERANCE_SEC = 0.001
EXPLORATORY_MIN_N = 40
EXPLORATORY_MIN_ESS = 20.0
EXPLORATORY_MIN_RELATIVE_EFFECT_PCT = 1.0


@dataclass(frozen=True)
class AutocorrelationDiagnostics:
    """IID-assumption diagnostics for a measured score sequence."""

    n: int
    lag1_autocorrelation: float | None
    effective_sample_size: float | None
    ess_preliminary: bool
    autocorrelation_detected: bool
    iid_assumption_valid: bool
    low_power: bool
    confidence_warning: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapConfidenceInterval:
    """Percentile bootstrap CI for a scalar statistic."""

    point_estimate: float
    ci_low: float
    ci_high: float
    confidence_level: float
    bootstrap_samples: int
    method: str
    statistic: str
    n: int
    diagnostics: AutocorrelationDiagnostics
    block_size: int | None = None
    baseline_block_size: int | None = None
    candidate_block_size: int | None = None


@dataclass(frozen=True)
class PairedScoreSamples:
    """Matched paired records and score vectors in baseline pair order."""

    baseline_records: tuple[RunLevelRecord, ...]
    candidate_records: tuple[RunLevelRecord, ...]
    baseline_scores: tuple[float, ...]
    candidate_scores: tuple[float, ...]
    partial_pairing: bool


@dataclass(frozen=True)
class PairQualityDiagnostics:
    """Quality verdict and diagnostics for matched paired records."""

    quality: str
    time_gap_conflict: bool = False
    run_overlap_detected: bool = False


@dataclass(frozen=True)
class PairTimeGap:
    """Conservative effective pair gap derived from all available sources."""

    effective_gap_sec: float | None
    source_conflict: bool = False


@dataclass(frozen=True)
class DescriptiveStatistics:
    """Descriptive statistics and autocorrelation diagnostics for measured runs."""

    n_measured: int
    n_valid: int
    n_invalid: int
    mean: float | None
    median: float | None
    sample_stddev: float | None
    cv: float | None
    effective_sample_size: float | None
    ess_preliminary: bool
    lag1_autocorrelation: float | None
    autocorrelation_detected: bool
    iid_assumption_valid: bool
    autocorrelation_warning: bool
    low_power: bool

    def to_run_summary_hint(self) -> RunSummaryHint:
        """Convert to the Phase 05/08 schema summary hint."""

        from agent.skills.result_schema import RunSummaryHint

        return RunSummaryHint(
            mean=self.mean,
            median=self.median,
            stddev=self.sample_stddev,
            cv=self.cv,
            n_measured=self.n_measured,
            n_valid=self.n_valid,
            n_invalid=self.n_invalid,
            effective_sample_size=self.effective_sample_size,
            ess_preliminary=self.ess_preliminary,
            lag1_autocorrelation=self.lag1_autocorrelation,
            autocorrelation_detected=self.autocorrelation_detected,
            iid_assumption_valid=self.iid_assumption_valid,
            autocorrelation_warning=self.autocorrelation_warning,
            low_power=self.low_power,
        )


def summarize_run_records(
    records: Iterable[RunLevelRecord],
    *,
    mean_zero_abs_tol: float = MEAN_ZERO_ABS_TOL,
    autocorrelation_threshold: float = AUTOCORRELATION_RHO_THRESHOLD,
    ess_min: float = ESS_MIN,
) -> DescriptiveStatistics:
    """Summarize measured run records without mutating external state.

    CI attachment to comparisons and final verdicts are later 08a subtasks.
    This layer still computes lag-1 rho and ESS so those later subtasks cannot
    accidentally treat bursty data as IID-only.
    """

    measured = _measured_records(tuple(records))
    scores = measured_valid_scores(measured)
    n_valid = len(scores)
    n_measured = len(measured)
    n_invalid = n_measured - n_valid

    if n_valid == 0:
        return DescriptiveStatistics(
            n_measured=n_measured,
            n_valid=0,
            n_invalid=n_invalid,
            mean=None,
            median=None,
            sample_stddev=None,
            cv=None,
            effective_sample_size=None,
            ess_preliminary=True,
            lag1_autocorrelation=None,
            autocorrelation_detected=False,
            iid_assumption_valid=True,
            autocorrelation_warning=False,
            low_power=True,
        )

    average = _mean(scores)
    sample_stddev = _sample_stddev(scores, average)
    coefficient_of_variation = (
        None
        if math.isclose(average, 0.0, abs_tol=mean_zero_abs_tol)
        else abs(sample_stddev / average)
    )
    diagnostics = diagnose_iid_assumption(
        scores,
        autocorrelation_threshold=autocorrelation_threshold,
        ess_min=ess_min,
    )

    return DescriptiveStatistics(
        n_measured=n_measured,
        n_valid=n_valid,
        n_invalid=n_invalid,
        mean=average,
        median=float(median(scores)),
        sample_stddev=sample_stddev,
        cv=coefficient_of_variation,
        effective_sample_size=diagnostics.effective_sample_size,
        ess_preliminary=diagnostics.ess_preliminary,
        lag1_autocorrelation=diagnostics.lag1_autocorrelation,
        autocorrelation_detected=diagnostics.autocorrelation_detected,
        iid_assumption_valid=diagnostics.iid_assumption_valid,
        autocorrelation_warning=diagnostics.autocorrelation_detected,
        low_power=diagnostics.low_power,
    )


def run_summary_hint(records: Iterable[RunLevelRecord]) -> RunSummaryHint | None:
    """Return a schema summary for measured valid records, or None if none exist."""

    stats = summarize_run_records(records)
    if stats.n_valid == 0:
        return None
    return stats.to_run_summary_hint()


def measured_valid_scores(records: Iterable[RunLevelRecord]) -> tuple[float, ...]:
    """Return finite scores from measured records valid for scoring."""

    measured = _measured_records(tuple(records))
    scores: list[float] = []
    for record in measured:
        if not record.valid_for_scoring:
            continue
        if record.score is None:
            raise ValueError("valid measured records must include score")
        scores.append(float(record.score))
    _validate_finite_sequence(scores)
    return tuple(scores)


def compare_run_records(
    baseline_records: Iterable[RunLevelRecord],
    candidate_records: Iterable[RunLevelRecord],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int | str | bytes | bytearray | None = None,
    comparison: str = "candidate_vs_baseline",
    base_zero_abs_tol: float = MEAN_ZERO_ABS_TOL,
    high_cv_threshold: float = HIGH_CV_THRESHOLD,
) -> StatisticalResult:
    """Compare candidate against baseline and return a single-comparison verdict."""

    from agent.skills.result_schema import StatisticalResult

    (
        baseline_measured,
        baseline_order_unverified,
        baseline_order_source_conflict,
    ) = _ordered_measured_records(tuple(baseline_records))
    (
        candidate_measured,
        candidate_order_unverified,
        candidate_order_source_conflict,
    ) = _ordered_measured_records(tuple(candidate_records))
    baseline_scores = measured_valid_scores(baseline_measured)
    candidate_scores = measured_valid_scores(candidate_measured)
    if not baseline_scores or not candidate_scores:
        raise ValueError("baseline and candidate must both include valid measured scores")
    _validate_confidence_level(confidence_level)
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    if not math.isfinite(base_zero_abs_tol) or base_zero_abs_tol < 0.0:
        raise ValueError("base_zero_abs_tol must be finite and non-negative")
    if not math.isfinite(high_cv_threshold) or high_cv_threshold < 0.0:
        raise ValueError("high_cv_threshold must be finite and non-negative")

    objective_direction = _objective_direction(
        baseline_measured + candidate_measured
    )
    baseline_stats = summarize_run_records(baseline_measured)
    candidate_stats = summarize_run_records(candidate_measured)
    paired_samples = _paired_score_samples(baseline_measured, candidate_measured)
    order_notes: list[str] = []
    if baseline_order_unverified or candidate_order_unverified:
        order_notes.append("input_order_unverified")
    if baseline_order_source_conflict or candidate_order_source_conflict:
        order_notes.append("order_source_conflict")

    pair_quality = "unknown"
    pair_time_gap_conflict = False
    run_overlap_detected = False
    if paired_samples is not None:
        pair_diagnostics = _pair_quality(paired_samples)
        pair_quality = pair_diagnostics.quality
        pair_time_gap_conflict = pair_diagnostics.time_gap_conflict
        run_overlap_detected = pair_diagnostics.run_overlap_detected
        effect_values = tuple(
            _signed_effect(
                baseline_score,
                candidate_score,
                objective_direction=objective_direction,
            )
            for baseline_score, candidate_score in zip(
                paired_samples.baseline_scores,
                paired_samples.candidate_scores,
                strict=True,
            )
        )
        ci = autocorrelation_aware_bootstrap_ci(
            effect_values,
            confidence_level=confidence_level,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        diagnostics = ci.diagnostics
        comparison_n_valid = len(effect_values)
        paired = True
        pair_count = comparison_n_valid
        unpaired_autocorrelation = False
        notes = order_notes + ["paired_difference"]
        if paired_samples.partial_pairing:
            notes.append("partial_pairing")
        if pair_time_gap_conflict:
            notes.append("pair_time_gap_conflict")
        if run_overlap_detected:
            notes.append("run_overlap_detected")
        if pair_quality == "suspect":
            notes.append("suspect_pair_quality")
        elif pair_quality == "unknown":
            notes.append("unknown_pair_quality")
    else:
        ci = _unpaired_mean_difference_bootstrap_ci(
            baseline_scores,
            candidate_scores,
            objective_direction=objective_direction,
            confidence_level=confidence_level,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )
        diagnostics = ci.diagnostics
        comparison_n_valid = min(len(baseline_scores), len(candidate_scores))
        paired = False
        pair_count = 0
        unpaired_autocorrelation = diagnostics.autocorrelation_detected
        notes = order_notes + ["unpaired_comparison"]

    high_cv = _has_high_cv(
        (baseline_stats.cv, candidate_stats.cv),
        threshold=high_cv_threshold,
    )
    verdict, low_power, recommend_more_runs, gate_notes = _statistical_verdict(
        ci_low=ci.ci_low,
        ci_high=ci.ci_high,
        diagnostics=diagnostics,
        n_valid=comparison_n_valid,
        paired=paired,
        pair_quality=pair_quality,
        unpaired_autocorrelation=unpaired_autocorrelation,
        partial_pairing=paired_samples.partial_pairing if paired_samples else False,
        high_cv=high_cv,
    )
    notes.extend(diagnostics.notes)
    notes.extend(gate_notes)

    baseline_mean = _mean(baseline_scores)
    point_estimate = ci.point_estimate
    relative_effect_pct = (
        None
        if math.isclose(baseline_mean, 0.0, abs_tol=base_zero_abs_tol)
        else point_estimate / abs(baseline_mean) * 100.0
    )
    exploratory_signal, requires_confirmation = _exploratory_signal(
        baseline_scores=baseline_scores,
        candidate_scores=candidate_scores,
        ci_low=ci.ci_low,
        ci_high=ci.ci_high,
        verdict=verdict,
        paired=paired,
        unpaired_autocorrelation=unpaired_autocorrelation,
        relative_effect_pct=relative_effect_pct,
    )
    if exploratory_signal != "none":
        notes.append("exploratory_requires_confirmation")
    n_measured = len(baseline_measured) + len(candidate_measured)
    baseline_invalid = len(baseline_measured) - len(baseline_scores)
    candidate_invalid = len(candidate_measured) - len(candidate_scores)
    n_invalid = baseline_invalid + candidate_invalid

    return StatisticalResult(
        comparison=comparison,
        objective_direction=objective_direction,
        point_estimate=point_estimate,
        relative_effect_pct=relative_effect_pct,
        ci_low=ci.ci_low,
        ci_high=ci.ci_high,
        confidence_level=ci.confidence_level,
        method=ci.method,
        verdict=verdict,
        significant_single_comparison=verdict
        in {"significant_improvement", "significant_regression"},
        comparison_scope="single_comparison",
        adjusted_for_multiple_testing=False,
        n_measured=n_measured,
        n_valid=comparison_n_valid,
        n_invalid=n_invalid,
        baseline_n_valid=len(baseline_scores),
        candidate_n_valid=len(candidate_scores),
        effective_sample_size=diagnostics.effective_sample_size,
        ess_preliminary=diagnostics.ess_preliminary,
        lag1_autocorrelation=diagnostics.lag1_autocorrelation,
        autocorrelation_detected=diagnostics.autocorrelation_detected,
        iid_assumption_valid=diagnostics.iid_assumption_valid,
        low_power=low_power,
        recommend_more_runs=recommend_more_runs,
        paired=paired,
        pair_count=pair_count,
        pair_quality=pair_quality,
        block_size=ci.block_size,
        baseline_block_size=ci.baseline_block_size,
        candidate_block_size=ci.candidate_block_size,
        exploratory_signal=exploratory_signal,
        requires_confirmation=requires_confirmation,
        notes=tuple(dict.fromkeys(notes)),
    )


def iid_percentile_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int | str | bytes | bytearray | None = None,
) -> BootstrapConfidenceInterval:
    """Return an IID percentile bootstrap CI for the sample mean.

    This is the clean IID bootstrap used by 08a.2. Autocorrelation diagnostics
    are attached, but the resampling model remains IID.
    """

    scores = tuple(float(value) for value in values)
    _validate_finite_sequence(scores)
    if not scores:
        raise ValueError("values must not be empty")
    _validate_confidence_level(confidence_level)
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    n = len(scores)
    rng = random.Random(seed)
    bootstrap_means: list[float] = []
    for _ in range(bootstrap_samples):
        sample_sum = 0.0
        for _ in range(n):
            sample_sum += scores[rng.randrange(n)]
        bootstrap_means.append(sample_sum / n)
    bootstrap_means.sort()

    alpha = 1.0 - confidence_level
    ci_low = _quantile_sorted(bootstrap_means, alpha / 2.0)
    ci_high = _quantile_sorted(bootstrap_means, 1.0 - alpha / 2.0)
    return BootstrapConfidenceInterval(
        point_estimate=_mean(scores),
        ci_low=ci_low,
        ci_high=ci_high,
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        method=IID_PERCENTILE_BOOTSTRAP_METHOD,
        statistic="mean",
        n=n,
        diagnostics=diagnose_iid_assumption(scores),
    )


def moving_block_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int | str | bytes | bytearray | None = None,
    block_size: int | None = None,
) -> BootstrapConfidenceInterval:
    """Return a moving-block percentile bootstrap CI for the sample mean."""

    scores = tuple(float(value) for value in values)
    _validate_finite_sequence(scores)
    if not scores:
        raise ValueError("values must not be empty")
    _validate_confidence_level(confidence_level)
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    diagnostics = diagnose_iid_assumption(scores)
    n = len(scores)
    if n <= LOW_POWER_MEASURED_RUNS_MAX:
        raise ValueError("moving block bootstrap requires more than 5 values")
    selected_block_size = block_size
    if selected_block_size is None:
        selected_block_size = select_moving_block_size(
            n,
            rho1=diagnostics.lag1_autocorrelation,
        )
    _validate_block_size(selected_block_size, n)

    rng = random.Random(seed)
    bootstrap_means: list[float] = []
    max_start = n - selected_block_size
    blocks_needed = math.ceil(n / selected_block_size)
    for _ in range(bootstrap_samples):
        sample_sum = 0.0
        sampled = 0
        for _ in range(blocks_needed):
            start = rng.randrange(max_start + 1)
            stop = start + selected_block_size
            for value in scores[start:stop]:
                if sampled >= n:
                    break
                sample_sum += value
                sampled += 1
        bootstrap_means.append(sample_sum / n)
    bootstrap_means.sort()

    alpha = 1.0 - confidence_level
    ci_low = _quantile_sorted(bootstrap_means, alpha / 2.0)
    ci_high = _quantile_sorted(bootstrap_means, 1.0 - alpha / 2.0)
    return BootstrapConfidenceInterval(
        point_estimate=_mean(scores),
        ci_low=ci_low,
        ci_high=ci_high,
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        method=MOVING_BLOCK_BOOTSTRAP_METHOD,
        statistic="mean",
        n=n,
        diagnostics=diagnostics,
        block_size=selected_block_size,
    )


def autocorrelation_aware_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int | str | bytes | bytearray | None = None,
) -> BootstrapConfidenceInterval:
    """Use moving-block bootstrap when autocorrelation diagnostics require it."""

    scores = tuple(float(value) for value in values)
    _validate_finite_sequence(scores)
    if not scores:
        raise ValueError("values must not be empty")
    _validate_confidence_level(confidence_level)
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    diagnostics = diagnose_iid_assumption(scores)
    block_size = select_moving_block_size(
        len(scores),
        rho1=diagnostics.lag1_autocorrelation,
    )
    if diagnostics.autocorrelation_detected and block_size is not None:
        return moving_block_bootstrap_ci(
            scores,
            confidence_level=confidence_level,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
            block_size=block_size,
        )
    return iid_percentile_bootstrap_ci(
        scores,
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )


def select_moving_block_size(n: int, *, rho1: float | None = None) -> int | None:
    """Return the 08a moving-block size, or None when n is too small."""

    if n < 0:
        raise ValueError("n must be non-negative")
    if rho1 is not None and not math.isfinite(rho1):
        raise ValueError("rho1 must be finite")
    if n <= LOW_POWER_MEASURED_RUNS_MAX:
        return None

    cube_root = math.ceil(n ** (1.0 / 3.0))
    if rho1 is None or rho1 <= 0.0:
        correlation_length = 1
    elif rho1 >= 1.0:
        correlation_length = n
    else:
        correlation_length = math.ceil((1.0 / (1.0 - rho1)) - 1e-12)
    uncapped = max(2, cube_root, correlation_length)
    return min(n // 2, uncapped)


def _unpaired_mean_difference_bootstrap_ci(
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    objective_direction: str,
    confidence_level: float,
    bootstrap_samples: int,
    seed: int | str | bytes | bytearray | None,
) -> BootstrapConfidenceInterval:
    baseline = tuple(float(value) for value in baseline_scores)
    candidate = tuple(float(value) for value in candidate_scores)
    baseline_diagnostics = diagnose_iid_assumption(baseline)
    candidate_diagnostics = diagnose_iid_assumption(candidate)
    diagnostics = _combine_unpaired_diagnostics(
        baseline_diagnostics,
        candidate_diagnostics,
    )
    baseline_block_size = (
        select_moving_block_size(
            len(baseline),
            rho1=baseline_diagnostics.lag1_autocorrelation,
        )
        if baseline_diagnostics.autocorrelation_detected
        else None
    )
    candidate_block_size = (
        select_moving_block_size(
            len(candidate),
            rho1=candidate_diagnostics.lag1_autocorrelation,
        )
        if candidate_diagnostics.autocorrelation_detected
        else None
    )
    uses_block = baseline_block_size is not None or candidate_block_size is not None

    rng = random.Random(seed)
    bootstrap_effects: list[float] = []
    for _ in range(bootstrap_samples):
        baseline_mean = _resampled_mean(
            baseline,
            rng=rng,
            block_size=baseline_block_size,
        )
        candidate_mean = _resampled_mean(
            candidate,
            rng=rng,
            block_size=candidate_block_size,
        )
        bootstrap_effects.append(
            _signed_effect(
                baseline_mean,
                candidate_mean,
                objective_direction=objective_direction,
            )
        )
    bootstrap_effects.sort()

    alpha = 1.0 - confidence_level
    point_estimate = _signed_effect(
        _mean(baseline),
        _mean(candidate),
        objective_direction=objective_direction,
    )
    return BootstrapConfidenceInterval(
        point_estimate=point_estimate,
        ci_low=_quantile_sorted(bootstrap_effects, alpha / 2.0),
        ci_high=_quantile_sorted(bootstrap_effects, 1.0 - alpha / 2.0),
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        method=(
            MOVING_BLOCK_BOOTSTRAP_METHOD
            if uses_block
            else IID_PERCENTILE_BOOTSTRAP_METHOD
        ),
        statistic="mean_difference",
        n=min(len(baseline), len(candidate)),
        diagnostics=diagnostics,
        block_size=max(
            (value for value in (baseline_block_size, candidate_block_size) if value),
            default=None,
        ),
        baseline_block_size=baseline_block_size,
        candidate_block_size=candidate_block_size,
    )


def _statistical_verdict(
    *,
    ci_low: float,
    ci_high: float,
    diagnostics: AutocorrelationDiagnostics,
    n_valid: int,
    paired: bool,
    pair_quality: str,
    unpaired_autocorrelation: bool,
    partial_pairing: bool,
    high_cv: bool,
) -> tuple[str, bool, bool, tuple[str, ...]]:
    notes: list[str] = []
    hard_inconclusive = False
    low_power = False

    if n_valid < LOW_POWER_MEASURED_RUNS_MAX:
        hard_inconclusive = True
        notes.append("n_valid_below_min")
    elif n_valid < MIN_VALID_FOR_SIGNIFICANCE:
        low_power = True
        notes.append("n_valid_low_power")

    ess = diagnostics.effective_sample_size
    if ess is None:
        hard_inconclusive = True
        notes.append("effective_sample_size_unavailable")
    elif ess < ESS_MIN:
        hard_inconclusive = True
        notes.append("effective_sample_size_below_min")
    elif ess < LOW_POWER_ESS_MIN:
        low_power = True
        notes.append("effective_sample_size_low_power")

    if unpaired_autocorrelation:
        hard_inconclusive = True
        notes.append("unpaired_autocorrelation_inconclusive")

    if paired and pair_quality != "good":
        low_power = True
        notes.append(
            "suspect_pair_quality"
            if pair_quality == "suspect"
            else "unknown_pair_quality"
        )

    if paired and partial_pairing:
        low_power = True
        notes.append("partial_pairing_low_power")

    if (
        paired
        and diagnostics.autocorrelation_detected
        and n_valid < AUTOCORRELATED_MIN_VALID_FOR_SIGNIFICANCE
    ):
        low_power = True
        notes.append("autocorrelated_small_n_med1")

    if diagnostics.ess_preliminary:
        low_power = True
        notes.append("ess_preliminary")

    if high_cv:
        notes.append("high_cv")

    insufficient_power = hard_inconclusive or low_power
    if insufficient_power:
        verdict = "inconclusive"
    elif ci_low > 0.0:
        verdict = "significant_improvement"
    elif ci_high < 0.0:
        verdict = "significant_regression"
    else:
        verdict = "no_difference"

    recommend_more_runs = insufficient_power or high_cv
    return verdict, insufficient_power, recommend_more_runs, tuple(dict.fromkeys(notes))


def _combine_unpaired_diagnostics(
    baseline: AutocorrelationDiagnostics,
    candidate: AutocorrelationDiagnostics,
) -> AutocorrelationDiagnostics:
    ess_candidates = tuple(
        value
        for value in (baseline.effective_sample_size, candidate.effective_sample_size)
        if value is not None
    )
    rho_candidates = tuple(
        value
        for value in (baseline.lag1_autocorrelation, candidate.lag1_autocorrelation)
        if value is not None
    )
    autocorrelation_detected = (
        baseline.autocorrelation_detected or candidate.autocorrelation_detected
    )
    notes = (
        tuple(f"baseline_{note}" for note in baseline.notes)
        + tuple(f"candidate_{note}" for note in candidate.notes)
    )
    return AutocorrelationDiagnostics(
        n=min(baseline.n, candidate.n),
        lag1_autocorrelation=(
            max(rho_candidates, key=abs) if rho_candidates else None
        ),
        effective_sample_size=min(ess_candidates) if ess_candidates else None,
        ess_preliminary=baseline.ess_preliminary or candidate.ess_preliminary,
        autocorrelation_detected=autocorrelation_detected,
        iid_assumption_valid=not autocorrelation_detected,
        low_power=baseline.low_power or candidate.low_power,
        confidence_warning=(
            baseline.confidence_warning or candidate.confidence_warning
        ),
        notes=tuple(dict.fromkeys(notes)),
    )


def diagnose_iid_assumption(
    values: Sequence[float],
    *,
    autocorrelation_threshold: float = AUTOCORRELATION_RHO_THRESHOLD,
    ess_min: float = ESS_MIN,
    low_power_measured_runs_max: int = LOW_POWER_MEASURED_RUNS_MAX,
) -> AutocorrelationDiagnostics:
    """Return autocorrelation/ESS diagnostics without changing the CI."""

    scores = tuple(float(value) for value in values)
    _validate_finite_sequence(scores)
    n = len(scores)
    if (
        not math.isfinite(autocorrelation_threshold)
        or autocorrelation_threshold < -1.0
        or autocorrelation_threshold > 1.0
    ):
        raise ValueError("autocorrelation_threshold must be finite and between -1 and 1")
    if not math.isfinite(ess_min) or ess_min < 0.0:
        raise ValueError("ess_min must be finite and non-negative")
    if low_power_measured_runs_max < 0:
        raise ValueError("low_power_measured_runs_max must be non-negative")

    if n == 0:
        return AutocorrelationDiagnostics(
            n=0,
            lag1_autocorrelation=None,
            effective_sample_size=None,
            ess_preliminary=True,
            autocorrelation_detected=False,
            iid_assumption_valid=True,
            low_power=True,
            confidence_warning=True,
            notes=("no_valid_scores", "low_power"),
        )

    rho1 = compute_lag1_autocorrelation(scores)
    ess, ess_preliminary = compute_summary_effective_sample_size(scores, rho1=rho1)
    autocorrelation_detected = (
        rho1 is not None and rho1 > autocorrelation_threshold
    )
    low_power = n <= low_power_measured_runs_max or (
        ess is not None and ess < ess_min
    )
    notes: list[str] = []
    if autocorrelation_detected:
        notes.append("autocorrelation_detected")
        notes.append("iid_ci_may_undercover")
    if ess_preliminary:
        notes.append("ess_preliminary")
    if ess is not None and ess < ess_min:
        notes.append("low_effective_sample_size")
    if n <= low_power_measured_runs_max:
        notes.append("low_measured_run_count")
    if low_power:
        notes.append("low_power")

    return AutocorrelationDiagnostics(
        n=n,
        lag1_autocorrelation=rho1,
        effective_sample_size=ess,
        ess_preliminary=ess_preliminary,
        autocorrelation_detected=autocorrelation_detected,
        iid_assumption_valid=not autocorrelation_detected,
        low_power=low_power,
        confidence_warning=autocorrelation_detected or low_power or ess_preliminary,
        notes=tuple(dict.fromkeys(notes)),
    )


def compute_lag1_autocorrelation(scores: Sequence[float]) -> float | None:
    """Return the lag-1 autocorrelation/drift indicator when defined."""

    return compute_lag_autocorrelation(scores, lag=1)


def compute_lag_autocorrelation(
    scores: Sequence[float],
    *,
    lag: int,
) -> float | None:
    """Return a lag-k autocorrelation/drift indicator when defined.

    This uses separate means for the current and previous lagged segments, not
    a strict global-mean sample ACF. The trend sensitivity is intentional:
    monotone drift violates IID and should trigger conservative 08a paths.
    """

    _validate_finite_sequence(scores)
    if lag <= 0:
        raise ValueError("lag must be positive")
    if len(scores) <= lag:
        return None

    current = tuple(float(value) for value in scores[lag:])
    previous = tuple(float(value) for value in scores[:-lag])
    # Pearson over lagged segments is intentionally conservative for monotone
    # drift; 08a.3/08a.4 own the threshold and block-bootstrap policy details.
    current_mean = _mean(current)
    previous_mean = _mean(previous)
    numerator = sum(
        (x - current_mean) * (y - previous_mean)
        for x, y in zip(current, previous, strict=True)
    )
    current_ss = sum((x - current_mean) ** 2 for x in current)
    previous_ss = sum((y - previous_mean) ** 2 for y in previous)
    denominator = math.sqrt(current_ss * previous_ss)
    if denominator == 0.0:
        return None
    rho = numerator / denominator
    return max(-1.0, min(1.0, rho))


def compute_summary_effective_sample_size(
    scores: Sequence[float],
    *,
    rho1: float | None = None,
) -> tuple[float | None, bool]:
    """Return conservative ESS and whether it is preliminary.

    For n >= 8, use the lower of lag-1 ESS and an initial-positive-lag
    heuristic over multi-lag ACF values. This is not strict Geyer IPS/IMS; the
    pair-sum/monotone upgrade is deferred beyond 08a. For n < 8, multi-lag ACF
    is too unstable, so report the lag-1 ESS with a preliminary marker for
    downstream consumers.
    """

    _validate_finite_sequence(scores)
    n = len(scores)
    if n == 0:
        return None, True
    lag1_rho = compute_lag1_autocorrelation(scores) if rho1 is None else rho1
    ess_lag1 = compute_effective_sample_size(n, lag1_rho)
    if n < 8:
        return ess_lag1, True

    ess_acf = compute_acf_effective_sample_size(scores)
    candidates = tuple(
        value for value in (ess_lag1, ess_acf) if value is not None
    )
    if not candidates:
        return None, False
    ess = min(candidates)
    if not math.isfinite(ess):
        raise ValueError("effective sample size must be finite")
    return max(0.0, min(float(n), ess)), False


def compute_acf_effective_sample_size(
    scores: Sequence[float],
    *,
    max_lag: int | None = None,
) -> float | None:
    """Return ESS from an initial-positive-lag multi-lag ACF heuristic.

    This is deliberately simpler than strict Geyer initial positive sequence or
    initial monotone sequence estimators; those upgrades are deferred beyond
    08a.
    """

    _validate_finite_sequence(scores)
    n = len(scores)
    if n == 0:
        return None
    if max_lag is not None and max_lag < 0:
        raise ValueError("max_lag must be non-negative")
    lag_limit = min(n // 2, 10) if max_lag is None else min(max_lag, n // 2, 10)
    sum_pos = 0.0
    for lag in range(1, lag_limit + 1):
        rho = compute_lag_autocorrelation(scores, lag=lag)
        if rho is None or rho <= 0.0:
            break
        sum_pos += rho
    denominator = 1.0 + 2.0 * sum_pos
    if denominator <= 0.0:
        return float(n)
    ess = n / denominator
    if not math.isfinite(ess):
        raise ValueError("effective sample size must be finite")
    return max(0.0, min(float(n), ess))


def compute_effective_sample_size(n: int, rho1: float | None) -> float | None:
    """Return ESS using lag-1 correction without inflating negative correlation."""

    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return None
    if rho1 is None:
        return float(n)
    if not math.isfinite(rho1):
        raise ValueError("rho1 must be finite")
    if rho1 <= 0.0:
        return float(n)
    if rho1 >= 1.0:
        return 0.0
    ess = n * (1.0 - rho1) / (1.0 + rho1)
    if not math.isfinite(ess):
        raise ValueError("effective sample size must be finite")
    return max(0.0, min(float(n), ess))


def _measured_records(records: Sequence[RunLevelRecord]) -> tuple[RunLevelRecord, ...]:
    measured, _order_unverified, _order_source_conflict = _ordered_measured_records(
        records
    )
    return measured


def _ordered_measured_records(
    records: Sequence[RunLevelRecord],
) -> tuple[tuple[RunLevelRecord, ...], bool, bool]:
    measured = tuple(record for record in records if record.phase == "measured")
    order_unverified = any(_record_order_unverified(record) for record in measured)
    ordered = tuple(
        record
        for _position, record in sorted(
            enumerate(measured),
            key=lambda item: _record_order_key(item[1], original_position=item[0]),
        )
    )
    return (
        ordered,
        order_unverified,
        _record_order_source_conflict(ordered),
    )


def _record_order_key(record: RunLevelRecord, *, original_position: int) -> tuple:
    started_at = getattr(record, "started_at", None)
    run_index = getattr(record, "run_index", None)
    if started_at is not None:
        return (
            0,
            _record_started_at_sort_value(started_at),
            _optional_int_sort_value(run_index),
            original_position,
        )
    if run_index is not None:
        return (1, _optional_int_sort_value(run_index), original_position)
    return (2, original_position)


def _record_order_unverified(record: RunLevelRecord) -> bool:
    return (
        getattr(record, "started_at", None) is None
        and getattr(record, "run_index", None) is None
    )


def _record_order_source_conflict(records: Sequence[RunLevelRecord]) -> bool:
    previous_run_index: int | None = None
    for record in records:
        if (
            getattr(record, "started_at", None) is None
            or getattr(record, "run_index", None) is None
        ):
            continue
        run_index = _optional_int_sort_value(getattr(record, "run_index", None))
        if previous_run_index is not None and run_index < previous_run_index:
            return True
        previous_run_index = run_index
    return False


def _optional_int_sort_value(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _record_started_at_sort_value(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    from agent.skills.result_schema import _parse_utc_isoformat

    return _parse_utc_isoformat(str(value), "started_at")


def _objective_direction(records: Sequence[RunLevelRecord]) -> str:
    directions = {record.objective_direction for record in records}
    if len(directions) != 1:
        raise ValueError("all measured records must share objective_direction")
    return directions.pop()


def _paired_score_samples(
    baseline_records: Sequence[RunLevelRecord],
    candidate_records: Sequence[RunLevelRecord],
) -> PairedScoreSamples | None:
    baseline_pairs = _record_by_pair_key(baseline_records)
    candidate_pairs = _record_by_pair_key(candidate_records)
    if not baseline_pairs or not candidate_pairs:
        return None

    common_keys = tuple(
        key for key in baseline_pairs.keys() if key in candidate_pairs
    )
    if not common_keys:
        return None
    matched_baseline_records = tuple(baseline_pairs[key] for key in common_keys)
    matched_candidate_records = tuple(candidate_pairs[key] for key in common_keys)
    baseline_scores = tuple(_record_score(record) for record in matched_baseline_records)
    candidate_scores = tuple(_record_score(record) for record in matched_candidate_records)
    partial_pairing = (
        len(common_keys) < len(baseline_pairs)
        or len(common_keys) < len(candidate_pairs)
    )
    return PairedScoreSamples(
        baseline_records=matched_baseline_records,
        candidate_records=matched_candidate_records,
        baseline_scores=baseline_scores,
        candidate_scores=candidate_scores,
        partial_pairing=partial_pairing,
    )


def _record_by_pair_key(records: Sequence[RunLevelRecord]) -> dict[str, RunLevelRecord]:
    pairs: dict[str, RunLevelRecord] = {}
    for record in records:
        if not record.valid_for_scoring or record.pair_key is None:
            continue
        if record.score is None:
            raise ValueError("valid measured records must include score")
        if record.pair_key in pairs:
            raise ValueError(f"duplicate pair_key {record.pair_key!r}")
        pairs[record.pair_key] = record
    return pairs


def _record_score(record: RunLevelRecord) -> float:
    if record.score is None:
        raise ValueError("valid measured records must include score")
    return float(record.score)


def _pair_quality(samples: PairedScoreSamples) -> PairQualityDiagnostics:
    if _records_have_time_overlap(
        samples.baseline_records
    ) or _records_have_time_overlap(samples.candidate_records):
        return PairQualityDiagnostics("suspect", run_overlap_detected=True)

    durations = tuple(
        _effective_record_duration_sec(record)
        for record in samples.baseline_records + samples.candidate_records
    )
    finite_durations = tuple(value for value in durations if math.isfinite(value))
    median_duration = float(median(finite_durations)) if finite_durations else None

    saw_unknown = False
    for baseline, candidate in zip(
        samples.baseline_records,
        samples.candidate_records,
        strict=True,
    ):
        baseline_order = getattr(baseline, "pair_order", None)
        candidate_order = getattr(candidate, "pair_order", None)
        if (
            baseline_order is None
            or candidate_order is None
            or baseline_order != candidate_order
        ):
            return PairQualityDiagnostics("suspect")

        gap = _pair_time_gap(baseline, candidate)
        if gap.source_conflict:
            return PairQualityDiagnostics("suspect", time_gap_conflict=True)
        if gap.effective_gap_sec is None:
            saw_unknown = True
            continue
        if gap.effective_gap_sec > PAIR_QUALITY_GAP_ABS_MAX_SEC:
            return PairQualityDiagnostics("suspect")
        duration_threshold = (
            PAIR_QUALITY_GAP_DURATION_MULT * median_duration
            if median_duration is not None
            else 0.0
        )
        allowed_gap = max(duration_threshold, PAIR_QUALITY_GAP_FLOOR_SEC)
        if gap.effective_gap_sec > allowed_gap:
            return PairQualityDiagnostics("suspect")

    return PairQualityDiagnostics("unknown" if saw_unknown else "good")


def _records_have_time_overlap(records: Sequence[RunLevelRecord]) -> bool:
    ordered = tuple(
        record
        for _position, record in sorted(
            enumerate(records),
            key=lambda item: _record_order_key(item[1], original_position=item[0]),
        )
    )
    for current, next_record in zip(ordered, ordered[1:], strict=False):
        current_ended_at = getattr(current, "ended_at", None)
        next_started_at = getattr(next_record, "started_at", None)
        if current_ended_at is None or next_started_at is None:
            continue
        overlap_sec = (
            _record_started_at_sort_value(current_ended_at)
            - _record_started_at_sort_value(next_started_at)
        ).total_seconds()
        if overlap_sec > PAIR_RUN_OVERLAP_TOLERANCE_SEC:
            return True
    return False


def _effective_record_duration_sec(record: RunLevelRecord) -> float:
    reported = getattr(record, "duration_sec", None)
    reported_duration = float(reported) if reported is not None else None
    started_at = getattr(record, "started_at", None)
    ended_at = getattr(record, "ended_at", None)
    derived_duration = None
    if started_at is not None and ended_at is not None:
        derived_duration = (
            _record_started_at_sort_value(ended_at)
            - _record_started_at_sort_value(started_at)
        ).total_seconds()
        if derived_duration < 0.0:
            raise ValueError("ended_at cannot be before started_at")
    if reported_duration is None:
        return float(derived_duration) if derived_duration is not None else math.nan
    if derived_duration is None:
        return reported_duration
    if not math.isfinite(reported_duration):
        return float(derived_duration)
    if not math.isfinite(derived_duration):
        return reported_duration
    return min(reported_duration, float(derived_duration))


def _pair_time_gap(
    baseline: RunLevelRecord,
    candidate: RunLevelRecord,
) -> PairTimeGap:
    field_gaps = tuple(
        float(value)
        for value in (
            getattr(baseline, "pair_time_gap_sec", None),
            getattr(candidate, "pair_time_gap_sec", None),
        )
        if value is not None
    )
    if field_gaps:
        if not all(math.isfinite(value) for value in field_gaps):
            raise ValueError("pair_time_gap_sec must be finite")
        field_gap = max(field_gaps)
    else:
        field_gap = None

    baseline_started = getattr(baseline, "started_at", None)
    candidate_started = getattr(candidate, "started_at", None)
    if baseline_started is None or candidate_started is None:
        derived_gap = None
    else:
        derived_gap = abs(
            (
                _record_started_at_sort_value(candidate_started)
                - _record_started_at_sort_value(baseline_started)
            ).total_seconds()
        )

    if field_gap is None and derived_gap is None:
        return PairTimeGap(None)
    if field_gap is None:
        return PairTimeGap(derived_gap)
    if derived_gap is None:
        return PairTimeGap(field_gap)
    return PairTimeGap(
        max(field_gap, derived_gap),
        source_conflict=_pair_time_gap_source_conflict(field_gap, derived_gap),
    )


def _pair_time_gap_source_conflict(field_gap: float, derived_gap: float) -> bool:
    if derived_gap <= field_gap:
        return False
    difference = derived_gap - field_gap
    ratio_threshold = max(
        field_gap * PAIR_TIME_GAP_CONFLICT_RATIO,
        PAIR_QUALITY_GAP_FLOOR_SEC,
    )
    return (
        derived_gap > ratio_threshold
        or difference > PAIR_TIME_GAP_CONFLICT_ABS_SEC
    )


def _exploratory_signal(
    *,
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    ci_low: float,
    ci_high: float,
    verdict: str,
    paired: bool,
    unpaired_autocorrelation: bool,
    relative_effect_pct: float | None,
) -> tuple[str, bool]:
    if paired or not unpaired_autocorrelation or verdict != "inconclusive":
        return "none", False
    if (
        len(baseline_scores) < EXPLORATORY_MIN_N
        or len(candidate_scores) < EXPLORATORY_MIN_N
    ):
        return "none", False

    baseline_diagnostics = diagnose_iid_assumption(baseline_scores)
    candidate_diagnostics = diagnose_iid_assumption(candidate_scores)
    if (
        baseline_diagnostics.effective_sample_size is None
        or candidate_diagnostics.effective_sample_size is None
        or baseline_diagnostics.effective_sample_size < EXPLORATORY_MIN_ESS
        or candidate_diagnostics.effective_sample_size < EXPLORATORY_MIN_ESS
    ):
        return "none", False
    if (
        relative_effect_pct is None
        or abs(relative_effect_pct) < EXPLORATORY_MIN_RELATIVE_EFFECT_PCT
    ):
        return "none", False
    if ci_low > 0.0:
        return "suggestive_improvement", True
    if ci_high < 0.0:
        return "suggestive_regression", True
    return "none", False


def _signed_effect(
    baseline_value: float,
    candidate_value: float,
    *,
    objective_direction: str,
) -> float:
    if objective_direction == "higher_is_better":
        return candidate_value - baseline_value
    if objective_direction == "lower_is_better":
        return baseline_value - candidate_value
    raise ValueError("objective_direction must be higher_is_better or lower_is_better")


def _has_high_cv(values: Iterable[float | None], *, threshold: float) -> bool:
    return any(value is not None and value > threshold for value in values)


def _resampled_mean(
    values: Sequence[float],
    *,
    rng: random.Random,
    block_size: int | None = None,
) -> float:
    if block_size is None:
        return sum(values[rng.randrange(len(values))] for _ in range(len(values))) / len(
            values
        )

    _validate_block_size(block_size, len(values))
    blocks_needed = math.ceil(len(values) / block_size)
    max_start = len(values) - block_size
    sample_sum = 0.0
    sampled = 0
    for _ in range(blocks_needed):
        start = rng.randrange(max_start + 1)
        for value in values[start : start + block_size]:
            if sampled >= len(values):
                break
            sample_sum += value
            sampled += 1
    return sample_sum / len(values)


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)


def _sample_stddev(values: Sequence[float], average: float) -> float:
    if len(values) <= 1:
        return 0.0
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _quantile_sorted(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("sorted_values must not be empty")
    if q < 0.0 or q > 1.0:
        raise ValueError("q must be between 0 and 1")
    position = (len(sorted_values) - 1) * q
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    weight = position - lower_index
    return lower + (upper - lower) * weight


def _validate_confidence_level(confidence_level: float) -> None:
    if not math.isfinite(confidence_level):
        raise ValueError("confidence_level must be finite")
    if confidence_level <= 0.0 or confidence_level >= 1.0:
        raise ValueError("confidence_level must be between 0 and 1")


def _validate_block_size(block_size: int, n: int) -> None:
    if block_size < 2:
        raise ValueError("block_size must be at least 2")
    if block_size > n:
        raise ValueError("block_size must not exceed sample size")


def _validate_finite_sequence(values: Iterable[float]) -> None:
    for value in values:
        if not math.isfinite(value):
            raise ValueError("scores must be finite")
