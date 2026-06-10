"""Side-effect-free statistics helpers for benchmark run records."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.skills.result_schema import RunLevelRecord, RunSummaryHint


MEAN_ZERO_ABS_TOL = 1e-12
AUTOCORRELATION_RHO_THRESHOLD = 0.3
ESS_MIN = 3.0
LOW_POWER_MEASURED_RUNS_MAX = 5
DEFAULT_BOOTSTRAP_SAMPLES = 2000
DEFAULT_CONFIDENCE_LEVEL = 0.95
IID_PERCENTILE_BOOTSTRAP_METHOD = "iid_percentile_bootstrap"


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
            autocorrelation_warning=self.autocorrelation_warning,
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

    measured = tuple(record for record in records if record.phase == "measured")
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
    rho1 = compute_lag1_autocorrelation(scores)
    ess, ess_preliminary = compute_summary_effective_sample_size(scores, rho1=rho1)
    autocorrelation_warning = (
        rho1 is not None and rho1 > autocorrelation_threshold
    )
    # 08a.1 surfaces this as a diagnostic only. Verdict ownership, including
    # low-power inconclusive policy, lands in 08a.3/08a.5.
    low_power = n_valid <= LOW_POWER_MEASURED_RUNS_MAX or (
        ess is not None and ess < ess_min
    )

    return DescriptiveStatistics(
        n_measured=n_measured,
        n_valid=n_valid,
        n_invalid=n_invalid,
        mean=average,
        median=float(median(scores)),
        sample_stddev=sample_stddev,
        cv=coefficient_of_variation,
        effective_sample_size=ess,
        ess_preliminary=ess_preliminary,
        lag1_autocorrelation=rho1,
        autocorrelation_warning=autocorrelation_warning,
        low_power=low_power,
    )


def run_summary_hint(records: Iterable[RunLevelRecord]) -> RunSummaryHint | None:
    """Return a schema summary for measured valid records, or None if none exist."""

    stats = summarize_run_records(records)
    if stats.n_valid == 0:
        return None
    return stats.to_run_summary_hint()


def measured_valid_scores(records: Iterable[RunLevelRecord]) -> tuple[float, ...]:
    """Return finite scores from measured records valid for scoring."""

    scores: list[float] = []
    for record in records:
        if record.phase != "measured":
            continue
        if not record.valid_for_scoring:
            continue
        if record.score is None:
            raise ValueError("valid measured records must include score")
        scores.append(float(record.score))
    _validate_finite_sequence(scores)
    return tuple(scores)


def iid_percentile_bootstrap_ci(
    values: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int | str | bytes | bytearray | None = None,
) -> BootstrapConfidenceInterval:
    """Return an IID percentile bootstrap CI for the sample mean.

    This is the clean IID bootstrap used by 08a.2. Autocorrelation/ESS-aware CI
    widening and moving block bootstrap selection belong to 08a.3/08a.4.
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
    )


def compute_lag1_autocorrelation(scores: Sequence[float]) -> float | None:
    """Return lag-1 autocorrelation for a score sequence when defined."""

    return compute_lag_autocorrelation(scores, lag=1)


def compute_lag_autocorrelation(
    scores: Sequence[float],
    *,
    lag: int,
) -> float | None:
    """Return lag-k autocorrelation for a score sequence when defined."""

    _validate_finite_sequence(scores)
    if lag <= 0:
        raise ValueError("lag must be positive")
    if len(scores) <= lag:
        return None

    current = tuple(float(value) for value in scores[lag:])
    previous = tuple(float(value) for value in scores[:-lag])
    # Pearson over lagged pairs is intentionally conservative for monotone
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

    For n >= 8, use the lower of lag-1 ESS and an initial-positive-sequence
    multi-lag ACF ESS. For n < 8, multi-lag ACF is too unstable, so report the
    lag-1 ESS with a preliminary marker for downstream consumers.
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
    """Return ESS from the initial positive sequence of multi-lag ACF."""

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


def _validate_finite_sequence(values: Iterable[float]) -> None:
    for value in values:
        if not math.isfinite(value):
            raise ValueError("scores must be finite")
