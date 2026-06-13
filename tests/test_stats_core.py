from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from agent import (
    FailureClassification,
    IID_PERCENTILE_BOOTSTRAP_METHOD,
    MOVING_BLOCK_BOOTSTRAP_METHOD,
    RunLevelRecord,
    autocorrelation_aware_bootstrap_ci,
    compare_run_records,
    compute_acf_effective_sample_size,
    compute_effective_sample_size,
    compute_lag_autocorrelation,
    compute_lag1_autocorrelation,
    compute_summary_effective_sample_size,
    compute_result_combo_hash,
    diagnose_iid_assumption,
    iid_percentile_bootstrap_ci,
    measured_valid_scores,
    moving_block_bootstrap_ci,
    run_summary_hint,
    select_moving_block_size,
    summarize_run_records,
)


NOW = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
SHA_A = "sha256:" + "a" * 64


def test_summarize_run_records_counts_measured_records_and_scores_only_valid() -> None:
    records = (
        _record(score=100.0, phase="warmup", run_index=0),
        _record(score=10.0, phase="measured", run_index=0),
        _record(score=14.0, phase="measured", run_index=1),
        _record(score=None, phase="measured", run_index=2, valid_for_scoring=False),
    )

    stats = summarize_run_records(records)

    assert measured_valid_scores(records) == (10.0, 14.0)
    assert stats.n_measured == 3
    assert stats.n_valid == 2
    assert stats.n_invalid == 1
    assert stats.mean == 12.0
    assert stats.median == 12.0
    assert stats.sample_stddev == pytest.approx(math.sqrt(8.0))
    assert stats.cv == pytest.approx(math.sqrt(8.0) / 12.0)
    assert stats.effective_sample_size == 2.0
    assert stats.ess_preliminary is True
    assert stats.lag1_autocorrelation is None
    assert stats.autocorrelation_warning is False
    assert stats.low_power is True

    hint = stats.to_run_summary_hint()
    assert hint.n_measured == 3
    assert hint.n_valid == 2
    assert hint.n_invalid == 1
    assert hint.ess_preliminary is True
    assert hint.autocorrelation_detected is False
    assert hint.iid_assumption_valid is True
    assert hint.low_power is True


def test_summary_uses_sample_stddev_and_none_cv_for_near_zero_mean() -> None:
    stats = summarize_run_records(
        (
            _record(score=-1.0, run_index=0),
            _record(score=1.0, run_index=1),
        )
    )

    assert stats.mean == 0.0
    assert stats.sample_stddev == pytest.approx(math.sqrt(2.0))
    assert stats.cv is None


def test_positive_lag1_autocorrelation_sets_warning_and_reduces_ess() -> None:
    records = tuple(
        _record(score=float(index), run_index=index)
        for index in range(1, 7)
    )

    stats = summarize_run_records(records)

    assert stats.lag1_autocorrelation == pytest.approx(1.0)
    assert stats.effective_sample_size == 0.0
    assert stats.ess_preliminary is True
    assert stats.autocorrelation_warning is True
    assert stats.low_power is True


def test_moderate_lag1_autocorrelation_reduces_ess_without_collapsing_to_zero() -> None:
    scores = (1.0, 2.0, 3.0, 2.0, 3.0, 4.0)
    stats = summarize_run_records(
        tuple(_record(score=score, run_index=index) for index, score in enumerate(scores))
    )

    assert stats.lag1_autocorrelation == pytest.approx(3.0 / 7.0)
    assert stats.effective_sample_size == pytest.approx(2.4)
    assert stats.ess_preliminary is True
    assert stats.autocorrelation_warning is True


def test_multi_lag_acf_ess_is_used_for_non_preliminary_sample_sizes() -> None:
    scores = (1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 3.0, 4.0, 5.0, 4.0)
    stats = summarize_run_records(
        tuple(_record(score=score, run_index=index) for index, score in enumerate(scores))
    )

    lag1_ess = compute_effective_sample_size(len(scores), stats.lag1_autocorrelation)

    assert stats.ess_preliminary is False
    assert stats.lag1_autocorrelation == pytest.approx(0.6123724356957945)
    assert lag1_ess == pytest.approx(2.4040820577345756)
    assert stats.effective_sample_size == pytest.approx(1.70093117159203)
    assert stats.effective_sample_size < lag1_ess
    assert compute_acf_effective_sample_size(scores) == pytest.approx(
        stats.effective_sample_size
    )


def test_negative_autocorrelation_does_not_inflate_effective_sample_size() -> None:
    scores = (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)
    stats = summarize_run_records(
        tuple(_record(score=score, run_index=index) for index, score in enumerate(scores))
    )

    assert stats.lag1_autocorrelation == pytest.approx(-1.0)
    assert stats.effective_sample_size == float(len(scores))
    assert stats.ess_preliminary is True
    assert stats.autocorrelation_warning is False
    assert stats.low_power is False


def test_run_summary_hint_returns_none_when_no_valid_measured_scores() -> None:
    records = (
        _record(score=100.0, phase="warmup", run_index=0),
        _record(score=None, phase="measured", run_index=0, valid_for_scoring=False),
    )

    assert run_summary_hint(records) is None

    stats = summarize_run_records(records)
    assert stats.n_measured == 1
    assert stats.n_valid == 0
    assert stats.n_invalid == 1
    assert stats.low_power is True


def test_iid_percentile_bootstrap_ci_is_seeded_and_reports_mean_ci() -> None:
    scores = (1.0, 2.0, 3.0, 4.0)

    first = iid_percentile_bootstrap_ci(
        scores,
        confidence_level=0.90,
        bootstrap_samples=20,
        seed=123,
    )
    second = iid_percentile_bootstrap_ci(
        scores,
        confidence_level=0.90,
        bootstrap_samples=20,
        seed=123,
    )

    assert first == second
    assert first.point_estimate == 2.5
    assert first.ci_low == pytest.approx(1.75)
    assert first.ci_high == pytest.approx(3.75)
    assert first.confidence_level == 0.90
    assert first.bootstrap_samples == 20
    assert first.method == IID_PERCENTILE_BOOTSTRAP_METHOD
    assert first.statistic == "mean"
    assert first.n == len(scores)
    assert first.diagnostics.n == len(scores)
    assert first.diagnostics.ess_preliminary is True
    assert first.diagnostics.low_power is True


def test_iid_percentile_bootstrap_ci_handles_single_sample() -> None:
    ci = iid_percentile_bootstrap_ci(
        (4.2,),
        bootstrap_samples=25,
        seed=7,
    )

    assert ci.point_estimate == 4.2
    assert ci.ci_low == 4.2
    assert ci.ci_high == 4.2


def test_iid_percentile_bootstrap_ci_coverage_smoke_for_iid_distributions() -> None:
    reps = 120
    bootstrap_samples = 300

    gaussian_coverage = _bootstrap_mean_coverage(
        truth=3.0,
        reps=reps,
        sample_size=40,
        bootstrap_samples=bootstrap_samples,
        seed=20260610,
        sampler=lambda rng: rng.gauss(3.0, 2.0),
    )
    right_skewed_coverage = _bootstrap_mean_coverage(
        truth=1.0,
        reps=reps,
        sample_size=40,
        bootstrap_samples=bootstrap_samples,
        seed=20260611,
        sampler=lambda rng: rng.expovariate(1.0),
    )

    assert 0.90 <= gaussian_coverage <= 0.99
    assert 0.86 <= right_skewed_coverage <= 0.98


def test_iid_diagnostics_detect_high_lag1_autocorrelation() -> None:
    scores = tuple(float(index) for index in range(1, 13))

    diagnostics = diagnose_iid_assumption(scores)

    assert diagnostics.n == len(scores)
    assert diagnostics.lag1_autocorrelation == pytest.approx(1.0)
    assert diagnostics.effective_sample_size == 0.0
    assert diagnostics.ess_preliminary is False
    assert diagnostics.autocorrelation_detected is True
    assert diagnostics.iid_assumption_valid is False
    assert diagnostics.low_power is True
    assert diagnostics.confidence_warning is True
    assert "autocorrelation_detected" in diagnostics.notes
    assert "iid_ci_may_undercover" in diagnostics.notes
    assert "low_effective_sample_size" in diagnostics.notes


def test_iid_diagnostics_accept_weak_positive_autocorrelation() -> None:
    scores = (0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0)

    diagnostics = diagnose_iid_assumption(scores)

    assert diagnostics.lag1_autocorrelation == pytest.approx(0.1)
    assert diagnostics.autocorrelation_detected is False
    assert diagnostics.iid_assumption_valid is True
    assert diagnostics.low_power is False
    assert diagnostics.confidence_warning is False


def test_iid_bootstrap_ci_marks_autocorrelated_data_without_changing_method() -> None:
    scores = tuple(float(index) for index in range(1, 13))

    ci = iid_percentile_bootstrap_ci(
        scores,
        bootstrap_samples=100,
        seed=11,
    )

    assert ci.method == IID_PERCENTILE_BOOTSTRAP_METHOD
    assert ci.diagnostics.autocorrelation_detected is True
    assert ci.diagnostics.iid_assumption_valid is False
    assert ci.diagnostics.confidence_warning is True
    assert ci.diagnostics.effective_sample_size == 0.0


def test_select_moving_block_size_uses_cube_root_rho_and_cap() -> None:
    assert select_moving_block_size(5, rho1=0.9) is None
    assert select_moving_block_size(64, rho1=0.0) == 4
    assert select_moving_block_size(40, rho1=0.8) == 5
    assert select_moving_block_size(20, rho1=0.95) == 10
    assert select_moving_block_size(12, rho1=1.0) == 6


def test_moving_block_bootstrap_ci_is_seeded_and_reports_block_method() -> None:
    scores = (1.0, 2.0, 3.0, 9.0, 10.0, 11.0, 3.0, 4.0, 5.0)

    first = moving_block_bootstrap_ci(
        scores,
        confidence_level=0.90,
        bootstrap_samples=40,
        seed=23,
        block_size=3,
    )
    second = moving_block_bootstrap_ci(
        scores,
        confidence_level=0.90,
        bootstrap_samples=40,
        seed=23,
        block_size=3,
    )

    assert first == second
    assert first.method == MOVING_BLOCK_BOOTSTRAP_METHOD
    assert first.block_size == 3
    assert first.statistic == "mean"
    assert first.n == len(scores)
    assert first.point_estimate == pytest.approx(sum(scores) / len(scores))
    assert first.ci_low <= first.point_estimate <= first.ci_high


def test_moving_block_bootstrap_resamples_contiguous_blocks() -> None:
    scores = (1.0, 100.0, 1.0, 100.0, 1.0, 100.0)

    ci = moving_block_bootstrap_ci(
        scores,
        bootstrap_samples=30,
        seed=37,
        block_size=2,
    )

    assert ci.point_estimate == 50.5
    assert ci.ci_low == 50.5
    assert ci.ci_high == 50.5


def test_autocorrelation_aware_bootstrap_ci_selects_moving_block_when_detected() -> None:
    scores = tuple(float(index) for index in range(1, 21))

    ci = autocorrelation_aware_bootstrap_ci(
        scores,
        bootstrap_samples=80,
        seed=17,
    )

    assert ci.method == MOVING_BLOCK_BOOTSTRAP_METHOD
    assert ci.block_size == 10
    assert ci.diagnostics.autocorrelation_detected is True
    assert ci.diagnostics.iid_assumption_valid is False


def test_autocorrelation_aware_bootstrap_ci_keeps_iid_for_weak_or_small_samples() -> None:
    weak_scores = (0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0)
    small_autocorrelated_scores = (1.0, 2.0, 3.0, 4.0, 5.0)

    weak_ci = autocorrelation_aware_bootstrap_ci(
        weak_scores,
        bootstrap_samples=40,
        seed=29,
    )
    small_ci = autocorrelation_aware_bootstrap_ci(
        small_autocorrelated_scores,
        bootstrap_samples=40,
        seed=31,
    )

    assert weak_ci.method == IID_PERCENTILE_BOOTSTRAP_METHOD
    assert weak_ci.block_size is None
    assert weak_ci.diagnostics.autocorrelation_detected is False
    assert small_ci.method == IID_PERCENTILE_BOOTSTRAP_METHOD
    assert small_ci.block_size is None
    assert small_ci.diagnostics.autocorrelation_detected is True
    assert small_ci.diagnostics.low_power is True


def test_compare_run_records_reports_significant_single_comparison() -> None:
    baseline = _records([10.0] * 12, prefix="base")
    candidate = _records([12.0] * 12, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=41,
    )

    assert result.point_estimate == pytest.approx(2.0)
    assert result.relative_effect_pct == pytest.approx(20.0)
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "significant_improvement"
    assert result.significant_single_comparison is True
    assert result.comparison_scope == "single_comparison"
    assert result.adjusted_for_multiple_testing is False
    assert result.low_power is False
    assert "bare_significant" not in result.model_dump()


def test_compare_run_records_uses_lower_is_better_direction() -> None:
    baseline = _records(
        [10.0] * 12,
        prefix="base",
        objective_direction="lower_is_better",
    )
    candidate = _records(
        [8.0] * 12,
        prefix="cand",
        objective_direction="lower_is_better",
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=43,
    )

    assert result.point_estimate == pytest.approx(2.0)
    assert result.relative_effect_pct == pytest.approx(20.0)
    assert result.verdict == "significant_improvement"


def test_compare_run_records_returns_no_difference_only_with_adequate_power() -> None:
    baseline = _records([10.0] * 12, prefix="base")
    candidate = _records([10.0] * 12, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=47,
    )

    assert result.verdict == "no_difference"
    assert result.low_power is False
    assert result.significant_single_comparison is False


def test_compare_run_records_defends_relative_effect_when_baseline_is_zero() -> None:
    baseline = _records([0.0] * 12, prefix="base")
    candidate = _records([1.0] * 12, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=53,
    )

    assert result.point_estimate == pytest.approx(1.0)
    assert result.relative_effect_pct is None
    assert result.verdict == "significant_improvement"


def test_compare_run_records_blocks_significance_for_small_samples() -> None:
    baseline = _records([10.0] * 4, prefix="base")
    candidate = _records([12.0] * 4, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=59,
    )

    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.low_power is True
    assert result.recommend_more_runs is True
    assert "n_valid_below_min" in result.notes


def test_compare_run_records_blocks_significance_for_low_power_run_count() -> None:
    baseline = _records([10.0] * 6, prefix="base")
    candidate = _records([12.0] * 6, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.low_power is True
    assert result.significant_single_comparison is False
    assert "n_valid_low_power" in result.notes


def test_compare_run_records_blocks_significance_for_low_power_ess() -> None:
    low_power_effects = [10.0, 10.0, 10.0, 11.0, 11.0, 11.0] * 2
    baseline = _records([0.0] * len(low_power_effects), prefix="base", paired=True)
    candidate = _records(low_power_effects, prefix="cand", paired=True)

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=120,
        seed=60,
    )

    assert 3.0 <= result.effective_sample_size < 5.0
    assert result.ci_low > 0.0
    assert result.verdict == "inconclusive"
    assert result.low_power is True
    assert result.significant_single_comparison is False
    assert "effective_sample_size_low_power" in result.notes


def test_compare_run_records_med1_blocks_small_autocorrelated_significance() -> None:
    baseline = _records([0.0] * 20, prefix="base", paired=True)
    candidate = _records(
        [float(index) for index in range(1, 21)],
        prefix="cand",
        paired=True,
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=120,
        seed=61,
    )

    assert result.paired is True
    assert result.method == MOVING_BLOCK_BOOTSTRAP_METHOD
    assert result.ci_low > 0.0
    assert result.autocorrelation_detected is True
    assert result.verdict == "inconclusive"
    assert result.low_power is True
    assert result.significant_single_comparison is False
    assert "autocorrelated_small_n_med1" in result.notes


def test_compare_run_records_checks_autocorrelation_on_paired_differences() -> None:
    baseline = _records([100.0] * 12, prefix="base", paired=True)
    candidate = _records(
        [100.0 + float(index) for index in range(1, 13)],
        prefix="cand",
        paired=True,
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=67,
    )

    assert result.paired is True
    assert result.pair_count == 12
    assert result.lag1_autocorrelation == pytest.approx(1.0)
    assert result.autocorrelation_detected is True
    assert result.iid_assumption_valid is False
    assert result.verdict == "inconclusive"
    assert "effective_sample_size_below_min" in result.notes


def test_compare_run_records_unpaired_autocorrelation_is_inconclusive() -> None:
    baseline = _records([float(index) for index in range(1, 13)], prefix="base")
    candidate = _records([float(index + 20) for index in range(1, 13)], prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=71,
    )

    assert result.paired is False
    assert result.ci_low > 0.0
    assert result.autocorrelation_detected is True
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "unpaired_autocorrelation_inconclusive" in result.notes


def test_lag1_and_ess_helpers_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="finite"):
        compute_lag1_autocorrelation((1.0, math.nan))
    with pytest.raises(ValueError, match="positive"):
        compute_lag_autocorrelation((1.0, 2.0), lag=0)
    with pytest.raises(ValueError, match="non-negative"):
        compute_effective_sample_size(-1, None)
    with pytest.raises(ValueError, match="finite"):
        compute_effective_sample_size(3, math.inf)
    with pytest.raises(ValueError, match="finite"):
        compute_effective_sample_size(3, -math.inf)
    with pytest.raises(ValueError, match="non-negative"):
        compute_acf_effective_sample_size((1.0, 2.0), max_lag=-1)
    assert compute_effective_sample_size(4, 1.0) == 0.0
    assert compute_summary_effective_sample_size(()) == (None, True)


def test_iid_percentile_bootstrap_ci_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="empty"):
        iid_percentile_bootstrap_ci(())
    with pytest.raises(ValueError, match="finite"):
        iid_percentile_bootstrap_ci((1.0, math.nan))
    with pytest.raises(ValueError, match="finite"):
        iid_percentile_bootstrap_ci((1.0, 2.0), confidence_level=math.inf)
    with pytest.raises(ValueError, match="between 0 and 1"):
        iid_percentile_bootstrap_ci((1.0, 2.0), confidence_level=1.0)
    with pytest.raises(ValueError, match="positive"):
        iid_percentile_bootstrap_ci((1.0, 2.0), bootstrap_samples=0)


def test_iid_diagnostics_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="finite"):
        diagnose_iid_assumption((1.0, math.nan))
    with pytest.raises(ValueError, match="autocorrelation_threshold"):
        diagnose_iid_assumption((1.0, 2.0), autocorrelation_threshold=math.nan)
    with pytest.raises(ValueError, match="ess_min"):
        diagnose_iid_assumption((1.0, 2.0), ess_min=math.inf)
    with pytest.raises(ValueError, match="low_power"):
        diagnose_iid_assumption((1.0, 2.0), low_power_measured_runs_max=-1)


def test_moving_block_bootstrap_ci_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="empty"):
        moving_block_bootstrap_ci(())
    with pytest.raises(ValueError, match="finite"):
        moving_block_bootstrap_ci((1.0, math.nan))
    with pytest.raises(ValueError, match="positive"):
        moving_block_bootstrap_ci((1.0, 2.0, 3.0, 4.0, 5.0, 6.0), bootstrap_samples=0)
    with pytest.raises(ValueError, match="at least 2"):
        moving_block_bootstrap_ci((1.0, 2.0, 3.0, 4.0, 5.0, 6.0), block_size=1)
    with pytest.raises(ValueError, match="sample size"):
        moving_block_bootstrap_ci((1.0, 2.0, 3.0, 4.0, 5.0, 6.0), block_size=7)
    with pytest.raises(ValueError, match="more than 5"):
        moving_block_bootstrap_ci((1.0, 2.0, 3.0, 4.0, 5.0))
    with pytest.raises(ValueError, match="non-negative"):
        select_moving_block_size(-1, rho1=None)
    with pytest.raises(ValueError, match="finite"):
        select_moving_block_size(10, rho1=math.inf)


def test_valid_measured_record_without_score_is_rejected_defensively() -> None:
    class ScorelessRecord:
        phase = "measured"
        valid_for_scoring = True
        score = None

    with pytest.raises(ValueError, match="valid measured records"):
        measured_valid_scores((ScorelessRecord(),))  # type: ignore[arg-type]


def _bootstrap_mean_coverage(
    *,
    truth: float,
    reps: int,
    sample_size: int,
    bootstrap_samples: int,
    seed: int,
    sampler,
) -> float:
    rng = random.Random(seed)
    covered = 0
    for rep in range(reps):
        values = tuple(sampler(rng) for _ in range(sample_size))
        ci = iid_percentile_bootstrap_ci(
            values,
            bootstrap_samples=bootstrap_samples,
            seed=seed + rep,
        )
        if ci.ci_low <= truth <= ci.ci_high:
            covered += 1
    return covered / reps


def _records(
    scores: Sequence[float],
    *,
    prefix: str,
    objective_direction: str = "higher_is_better",
    paired: bool = False,
) -> tuple[RunLevelRecord, ...]:
    return tuple(
        _record(
            score=score,
            run_index=index,
            objective_direction=objective_direction,
            pair_key=f"pair_{index}" if paired else None,
            run_id=f"{prefix}_{index}",
        )
        for index, score in enumerate(scores)
    )


def _record(
    *,
    score: float | None,
    run_index: int,
    phase: str = "measured",
    valid_for_scoring: bool = True,
    objective_direction: str = "higher_is_better",
    pair_key: str | None = None,
    run_id: str | None = None,
) -> RunLevelRecord:
    failure = (
        None
        if valid_for_scoring
        else FailureClassification(
            category="environment_unstable",
            route="environment_related",
            confidence="LOW",
            retryable=True,
        )
    )
    return RunLevelRecord(
        run_id=run_id or f"run_{phase}_{run_index}",
        run_index=run_index,
        combo_hash=compute_result_combo_hash(["-O2"]),
        score=score,
        phase=phase,  # type: ignore[arg-type]
        metric_name="throughput",
        metric_unit="items/sec",
        objective_direction=objective_direction,  # type: ignore[arg-type]
        duration_sec=0.1,
        started_at=NOW,
        ended_at=NOW + timedelta(milliseconds=100),
        exit_code=0,
        stdout_ref="logs/bench.stdout#L1",
        stderr_ref="logs/bench.stderr#L1",
        valid_for_scoring=valid_for_scoring,
        invalid_reason=None if valid_for_scoring else "environment_unstable",
        benchmark_cmd=("fake-gbs", "benchmark"),
        artifact_ref="artifacts/fake/run.artifact",
        artifact_hash=SHA_A,
        artifact_hash_verified=True,
        score_source_ref="logs/bench.stdout#L1",
        pair_key=pair_key,
        failure_classification=failure,
    )
