from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

import pytest

from agent import (
    FailureClassification,
    IID_PERCENTILE_BOOTSTRAP_METHOD,
    MOVING_BLOCK_BOOTSTRAP_METHOD,
    RunLevelRecord,
    StatisticalResult,
    autocorrelation_aware_bootstrap_ci,
    can_accept,
    compare_run_records,
    compute_acf_effective_sample_size,
    compute_effective_sample_size,
    compute_lag_autocorrelation,
    compute_lag1_autocorrelation,
    compute_summary_effective_sample_size,
    compute_result_combo_hash,
    diagnose_iid_assumption,
    family_screen,
    iid_percentile_bootstrap_ci,
    is_decision_grade,
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
    assert 0.0 < first.p_value <= 1.0
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
    assert ci.p_value == pytest.approx(2.0 / 26.0)


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
    assert result.relative_ci_low_pct == pytest.approx(20.0)
    assert result.relative_ci_high_pct == pytest.approx(20.0)
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.p_value == pytest.approx(2.0 / 81.0)
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
    assert result.p_value == pytest.approx(1.0)
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
    assert result.relative_ci_low_pct is None
    assert result.relative_ci_high_pct is None
    assert result.verdict == "significant_improvement"


def test_compare_run_records_marks_incomplete_provenance_until_7_0_records_fill_it() -> None:
    baseline = _records([10.0] * 12, prefix="base")
    candidate = _records([12.0] * 12, prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=55,
    )

    assert result.provenance_complete is False


def test_compare_run_records_marks_complete_provenance_when_records_have_plan_and_run_refs() -> None:
    baseline = _records(
        [10.0] * 12,
        prefix="base",
        measurement_plan_id="plan_1",
        source_commit="commit_abc",
        benchmark_id="bench_1",
        objective_id="throughput",
    )
    candidate = _records(
        [12.0] * 12,
        prefix="cand",
        measurement_plan_id="plan_1",
        source_commit="commit_abc",
        benchmark_id="bench_1",
        objective_id="throughput",
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=56,
    )

    assert result.provenance_complete is True


def test_compare_run_records_marks_incomplete_provenance_when_plan_refs_disagree() -> None:
    baseline = _records(
        [10.0] * 12,
        prefix="base",
        measurement_plan_id="plan_1",
        source_commit="commit_abc",
        benchmark_id="bench_1",
        objective_id="throughput",
    )
    candidate = _records(
        [12.0] * 12,
        prefix="cand",
        measurement_plan_id="plan_2",
        source_commit="commit_abc",
        benchmark_id="bench_1",
        objective_id="throughput",
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=57,
    )

    assert result.provenance_complete is False


def test_family_screen_uses_full_family_m_and_improvement_verdict_direction() -> None:
    results = [
        _statistical_result(verdict="significant_improvement", p_value=0.01),
        _statistical_result(verdict="significant_improvement", p_value=0.06),
        _statistical_result(verdict="significant_regression", p_value=0.001),
        _statistical_result(verdict="no_difference", p_value=0.02),
    ]

    assert family_screen(results, q=0.10) == [True, False, False, False]


def test_family_screen_selects_lower_is_better_improvement_by_verdict_not_relative_sign() -> None:
    lower_is_better_improvement = _statistical_result(
        objective_direction="lower_is_better",
        verdict="significant_improvement",
        p_value=0.01,
        relative_effect_pct=-5.0,
        relative_ci_low_pct=-7.0,
        relative_ci_high_pct=-3.0,
    )
    regression = _statistical_result(
        objective_direction="lower_is_better",
        verdict="significant_regression",
        p_value=0.001,
        relative_effect_pct=10.0,
        relative_ci_low_pct=8.0,
        relative_ci_high_pct=12.0,
    )

    assert family_screen([lower_is_better_improvement, regression], q=0.10) == [
        True,
        False,
    ]


def test_is_decision_grade_uses_schema_consistent_path_predicate() -> None:
    paired_result = _statistical_result(paired=True, pair_quality="good")
    unpaired_non_autocorrelated = _statistical_result(
        paired=False,
        iid_assumption_valid=False,
        autocorrelation_detected=False,
    )

    assert is_decision_grade(paired_result) is True
    assert is_decision_grade(unpaired_non_autocorrelated) is True


def test_can_accept_requires_screen_confirmation_practical_threshold_and_provenance() -> None:
    accepted_result = _statistical_result(
        relative_effect_pct=5.0,
        relative_ci_low_pct=3.5,
        relative_ci_high_pct=6.5,
        provenance_complete=True,
    )

    assert can_accept(
        accepted_result,
        is_family_screened=True,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "accepted"
    assert can_accept(
        accepted_result,
        is_family_screened=False,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "rejected_not_screened"
    assert can_accept(
        accepted_result,
        is_family_screened=True,
        confirmation_status="pending",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "needs_confirmation"

    incomplete = _statistical_result(provenance_complete=False)
    assert can_accept(
        incomplete,
        is_family_screened=True,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "rejected_incomplete_provenance"

    default_incomplete_payload = _statistical_result().model_dump()
    default_incomplete_payload.pop("provenance_complete")
    default_incomplete = StatisticalResult.model_validate(default_incomplete_payload)
    assert default_incomplete.provenance_complete is False
    assert can_accept(
        default_incomplete,
        is_family_screened=True,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "rejected_incomplete_provenance"

    weak_practical = _statistical_result(relative_ci_low_pct=2.5)
    assert can_accept(
        weak_practical,
        is_family_screened=True,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "rejected_practical_threshold"

    no_relative = _statistical_result(
        relative_effect_pct=None,
        relative_ci_low_pct=None,
        relative_ci_high_pct=None,
    )
    assert can_accept(
        no_relative,
        is_family_screened=True,
        confirmation_status="confirmed",
        practical_threshold_pct=3.0,
        objective_direction="higher_is_better",
    ).reason == "rejected_relative_threshold_unavailable"


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
    baseline = _records(
        [0.0] * len(low_power_effects),
        prefix="base",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
    )
    candidate = _records(
        low_power_effects,
        prefix="cand",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
        started_at_offset_sec=0.1,
    )

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


@pytest.mark.parametrize(
    ("pair_order", "pair_time_gap_sec"),
    [
        (None, 0.1),
        ("baseline_first", 999.0),
    ],
)
def test_compare_run_records_blocks_significance_for_suspect_pair_quality(
    pair_order: str | None,
    pair_time_gap_sec: float,
) -> None:
    baseline = _records(
        [10.0] * 12,
        prefix="base",
        paired=True,
        pair_order=pair_order,
        pair_time_gap_sec=pair_time_gap_sec,
    )
    candidate = _records(
        [12.0] * 12,
        prefix="cand",
        paired=True,
        pair_order=pair_order,
        pair_time_gap_sec=pair_time_gap_sec,
        started_at_offset_sec=0.1,
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.low_power is True
    assert result.significant_single_comparison is False
    assert "suspect_pair_quality" in result.notes


def test_compare_run_records_rejects_lied_pair_time_gap_using_started_at() -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=0.1,
            run_id=f"base_lied_gap_{index}",
            started_at=NOW + timedelta(seconds=index),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=0.1,
            run_id=f"cand_lied_gap_{index}",
            started_at=NOW + timedelta(hours=10, seconds=index),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "pair_time_gap_conflict" in result.notes
    assert "suspect_pair_quality" in result.notes


@pytest.mark.parametrize("reported_duration_sec", [1.0, 10_000.0])
def test_compare_run_records_rejects_large_gap_when_duration_is_spoofed(
    reported_duration_sec: float,
) -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"base_duration_spoof_{index}",
            duration_sec=reported_duration_sec,
            started_at=NOW + timedelta(seconds=index * 1_000),
            ended_at=NOW + timedelta(seconds=index * 1_000 + 1),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"cand_duration_spoof_{index}",
            duration_sec=reported_duration_sec,
            started_at=NOW + timedelta(seconds=index * 1_000 + 250),
            ended_at=NOW + timedelta(seconds=index * 1_000 + 251),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "suspect_pair_quality" in result.notes


def test_compare_run_records_uses_per_pair_duration_for_gap_threshold() -> None:
    baseline_records: list[RunLevelRecord] = []
    candidate_records: list[RunLevelRecord] = []
    for index in range(11):
        pair_start = NOW + timedelta(seconds=index * 600)
        baseline_records.append(
            _record(
                score=10.0,
                run_index=index,
                pair_key=f"slow_pair_{index}",
                pair_order="baseline_first",
                run_id=f"base_slow_pair_{index}",
                duration_sec=300.0,
                started_at=pair_start,
                ended_at=pair_start + timedelta(seconds=300),
            )
        )
        candidate_records.append(
            _record(
                score=12.0,
                run_index=index,
                pair_key=f"slow_pair_{index}",
                pair_order="baseline_first",
                run_id=f"cand_slow_pair_{index}",
                duration_sec=300.0,
                started_at=pair_start + timedelta(seconds=300),
                ended_at=pair_start + timedelta(seconds=600),
            )
        )

    fast_pair_start = NOW + timedelta(seconds=11 * 600)
    baseline_records.append(
        _record(
            score=10.0,
            run_index=11,
            pair_key="fast_pair",
            pair_order="baseline_first",
            run_id="base_fast_pair_masked_by_slow_pairs",
            duration_sec=0.1,
            started_at=fast_pair_start,
            ended_at=fast_pair_start + timedelta(seconds=0.1),
        )
    )
    candidate_records.append(
        _record(
            score=12.0,
            run_index=11,
            pair_key="fast_pair",
            pair_order="baseline_first",
            run_id="cand_fast_pair_masked_by_slow_pairs",
            duration_sec=0.1,
            started_at=fast_pair_start + timedelta(seconds=250),
            ended_at=fast_pair_start + timedelta(seconds=250.1),
        )
    )

    result = compare_run_records(
        tuple(baseline_records),
        tuple(candidate_records),
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "suspect_pair_quality" in result.notes
    assert "run_overlap_detected" not in result.notes
    assert "pair_time_gap_conflict" not in result.notes


def test_compare_run_records_rejects_coordinated_duration_and_ended_at_spoofing() -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"base_duration_ended_spoof_{index}",
            duration_sec=10_000.0,
            started_at=NOW + timedelta(seconds=index * 10),
            ended_at=NOW + timedelta(seconds=index * 10 + 10_000),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"cand_duration_ended_spoof_{index}",
            duration_sec=10_000.0,
            started_at=NOW + timedelta(seconds=index * 10 + 250),
            ended_at=NOW + timedelta(seconds=index * 10 + 10_250),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "run_overlap_detected" in result.notes
    assert "suspect_pair_quality" in result.notes


def test_compare_run_records_rejects_cross_arm_time_overlap_spoofing() -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"base_cross_arm_overlap_{index}",
            duration_sec=10_000.0,
            started_at=NOW + timedelta(seconds=index * 10_000),
            ended_at=NOW + timedelta(seconds=(index + 1) * 10_000),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            run_id=f"cand_cross_arm_overlap_{index}",
            duration_sec=10_000.0,
            started_at=NOW + timedelta(seconds=index * 10_000 + 250),
            ended_at=NOW + timedelta(seconds=(index + 1) * 10_000 + 250),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "suspect"
    assert result.ci_low == pytest.approx(2.0)
    assert result.ci_high == pytest.approx(2.0)
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert "run_overlap_detected" in result.notes
    assert "suspect_pair_quality" in result.notes


def test_compare_run_records_keeps_good_pairs_decision_grade() -> None:
    baseline = _records(
        [10.0] * 12,
        prefix="base",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
    )
    candidate = _records(
        [12.0] * 12,
        prefix="cand",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
        started_at_offset_sec=0.1,
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "good"
    assert result.verdict == "significant_improvement"
    assert result.significant_single_comparison is True
    assert result.low_power is False
    assert "run_overlap_detected" not in result.notes


def test_compare_run_records_allows_fast_benchmark_pair_gap_floor() -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=1.0,
            run_id=f"base_fast_gap_{index}",
            started_at=NOW + timedelta(seconds=index * 3),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=1.0,
            run_id=f"cand_fast_gap_{index}",
            started_at=NOW + timedelta(seconds=index * 3 + 1),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=60,
    )

    assert result.paired is True
    assert result.pair_quality == "good"
    assert result.verdict == "significant_improvement"
    assert result.significant_single_comparison is True
    assert "pair_time_gap_conflict" not in result.notes
    assert "run_overlap_detected" not in result.notes
    assert "suspect_pair_quality" not in result.notes


def test_compare_run_records_med1_blocks_small_autocorrelated_significance() -> None:
    baseline = _records(
        [0.0] * 20,
        prefix="base",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
    )
    candidate = _records(
        [float(index) for index in range(1, 21)],
        prefix="cand",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
        started_at_offset_sec=0.1,
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
    baseline = _records(
        [100.0] * 12,
        prefix="base",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
    )
    candidate = _records(
        [100.0 + float(index) for index in range(1, 13)],
        prefix="cand",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
        started_at_offset_sec=0.1,
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


def test_compare_run_records_sorts_measured_records_before_autocorrelation() -> None:
    baseline = _records(
        [0.0] * 20,
        prefix="base",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
    )
    candidate = _records(
        [float(index) for index in range(1, 21)],
        prefix="cand",
        paired=True,
        pair_order="baseline_first",
        pair_time_gap_sec=0.1,
        started_at_offset_sec=0.1,
    )
    shuffled_indices_list = list(range(20))
    random.Random(2).shuffle(shuffled_indices_list)
    shuffled_indices = tuple(shuffled_indices_list)
    shuffled_candidate = tuple(candidate[index] for index in shuffled_indices)
    shuffled_effects = tuple(float(index + 1) for index in shuffled_indices)

    assert compute_lag1_autocorrelation(shuffled_effects) < 0.3

    sorted_result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=72,
    )
    shuffled_result = compare_run_records(
        baseline,
        shuffled_candidate,
        bootstrap_samples=80,
        seed=72,
    )

    assert shuffled_result.lag1_autocorrelation == pytest.approx(
        sorted_result.lag1_autocorrelation
    )
    assert shuffled_result.lag1_autocorrelation == pytest.approx(1.0)
    assert shuffled_result.autocorrelation_detected is True
    assert shuffled_result.verdict == "inconclusive"
    assert "input_order_unverified" not in shuffled_result.notes


def test_compare_run_records_sorts_mixed_utc_started_at_formats_by_datetime() -> None:
    baseline = tuple(
        _record(
            score=0.0,
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=0.1,
            run_id=f"base_mixed_{index}",
            started_at=_mixed_utc_timestamp(index),
            duration_sec=0.01,
        )
        for index in range(20)
    )
    candidate = tuple(
        _record(
            score=float(index + 1),
            run_index=index,
            pair_key=f"pair_{index}",
            pair_order="baseline_first",
            pair_time_gap_sec=0.1,
            run_id=f"cand_mixed_{index}",
            started_at=_mixed_utc_timestamp(index, offset_micros=10_000),
            duration_sec=0.01,
        )
        for index in range(20)
    )
    shuffled_indices_list = list(range(20))
    random.Random(4).shuffle(shuffled_indices_list)
    shuffled_candidate = tuple(candidate[index] for index in shuffled_indices_list)

    result = compare_run_records(
        baseline,
        shuffled_candidate,
        bootstrap_samples=80,
        seed=72,
    )

    assert result.pair_quality == "good"
    assert result.lag1_autocorrelation == pytest.approx(1.0)
    assert result.autocorrelation_detected is True
    assert result.verdict == "inconclusive"


def test_compare_run_records_marks_order_source_conflict() -> None:
    baseline = tuple(
        _record(
            score=10.0,
            run_index=index,
            run_id=f"base_conflict_{index}",
            started_at=NOW + timedelta(seconds=11 - index),
        )
        for index in range(12)
    )
    candidate = tuple(
        _record(
            score=12.0,
            run_index=index,
            run_id=f"cand_conflict_{index}",
            started_at=NOW + timedelta(seconds=11 - index),
        )
        for index in range(12)
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=72,
    )

    assert result.verdict == "significant_improvement"
    assert "order_source_conflict" in result.notes


def test_compare_run_records_sets_exploratory_signal_for_strong_unpaired_autocorrelation() -> None:
    baseline = _records(_ar1_scores(seed=1, mean=100.0), prefix="base")
    candidate = _records(_ar1_scores(seed=1001, mean=106.0), prefix="cand")

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=300,
        seed=123,
    )

    assert result.paired is False
    assert result.autocorrelation_detected is True
    assert result.effective_sample_size is not None
    assert result.effective_sample_size >= 20.0
    assert result.ci_low > 0.0
    assert result.verdict == "inconclusive"
    assert result.significant_single_comparison is False
    assert result.exploratory_signal == "suggestive_improvement"
    assert result.requires_confirmation is True
    assert "unpaired_autocorrelation_inconclusive" in result.notes
    assert "exploratory_requires_confirmation" in result.notes


def test_compare_run_records_marks_unverified_order_when_no_time_or_index() -> None:
    class MinimalRecord:
        phase = "measured"
        valid_for_scoring = True
        objective_direction = "higher_is_better"
        pair_key = None

        def __init__(self, score: float) -> None:
            self.score = score

    baseline = tuple(MinimalRecord(10.0) for _ in range(12))
    candidate = tuple(MinimalRecord(12.0) for _ in range(12))

    result = compare_run_records(
        baseline,  # type: ignore[arg-type]
        candidate,  # type: ignore[arg-type]
        bootstrap_samples=80,
        seed=73,
    )

    assert result.verdict == "significant_improvement"
    assert "input_order_unverified" in result.notes


def test_compare_run_records_reports_unpaired_block_sizes_separately() -> None:
    baseline = _records([float(index) for index in range(1, 21)], prefix="base")
    candidate = _records(
        [float(index + 20) for index in range(1, 13)],
        prefix="cand",
    )

    result = compare_run_records(
        baseline,
        candidate,
        bootstrap_samples=80,
        seed=74,
    )

    assert result.paired is False
    assert result.method == MOVING_BLOCK_BOOTSTRAP_METHOD
    assert result.baseline_block_size == 10
    assert result.candidate_block_size == 6
    assert result.block_size == 10
    assert result.verdict == "inconclusive"


def test_bootstrap_ci_handles_zero_variance_sequence() -> None:
    ci = iid_percentile_bootstrap_ci(
        (3.14,) * 12,
        bootstrap_samples=80,
        seed=75,
    )

    assert ci.point_estimate == pytest.approx(3.14)
    assert ci.ci_low == pytest.approx(3.14)
    assert ci.ci_high == pytest.approx(3.14)
    assert ci.diagnostics.lag1_autocorrelation is None


def test_tiny_variance_sequence_keeps_acf_and_cv_finite() -> None:
    scores = tuple(1.0 + (1e-12 if index % 2 else -1e-12) for index in range(12))
    records = _records(scores, prefix="tiny")

    stats = summarize_run_records(records)
    rho1 = compute_lag1_autocorrelation(scores)

    assert rho1 is None or math.isfinite(rho1)
    assert stats.cv is None or math.isfinite(stats.cv)
    assert stats.effective_sample_size is None or math.isfinite(
        stats.effective_sample_size
    )


def test_autocorrelation_aware_bootstrap_handles_large_n_without_excessive_work() -> None:
    rng = random.Random(20260613)
    scores = tuple(rng.gauss(0.0, 1.0) for _ in range(1000))

    ci = autocorrelation_aware_bootstrap_ci(
        scores,
        bootstrap_samples=80,
        seed=76,
    )

    assert ci.n == 1000
    assert ci.ci_low <= ci.point_estimate <= ci.ci_high


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
    pair_order: str | None = None,
    pair_time_gap_sec: float | None = None,
    started_at_offset_sec: float = 0.0,
    measurement_plan_id: str | None = None,
    source_commit: str | None = None,
    benchmark_id: str | None = None,
    objective_id: str | None = None,
) -> tuple[RunLevelRecord, ...]:
    return tuple(
        _record(
            score=score,
            run_index=index,
            objective_direction=objective_direction,
            pair_key=f"pair_{index}" if paired else None,
            pair_order=pair_order,
            pair_time_gap_sec=pair_time_gap_sec,
            run_id=f"{prefix}_{index}",
            started_at=NOW + timedelta(seconds=index + started_at_offset_sec),
            measurement_plan_id=measurement_plan_id,
            source_commit=source_commit,
            benchmark_id=benchmark_id,
            objective_id=objective_id,
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
    pair_order: str | None = None,
    pair_time_gap_sec: float | None = None,
    run_id: str | None = None,
    started_at: datetime | str | None = None,
    ended_at: datetime | str | None = None,
    duration_sec: float = 0.1,
    measurement_plan_id: str | None = None,
    source_commit: str | None = None,
    benchmark_id: str | None = None,
    objective_id: str | None = None,
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
    record_started_at = started_at or NOW + timedelta(seconds=run_index)
    if isinstance(record_started_at, str):
        parsed_started_at = datetime.fromisoformat(
            record_started_at.replace("Z", "+00:00")
        )
        record_ended_at: datetime | str = ended_at or (
            parsed_started_at + timedelta(seconds=duration_sec)
        )
    else:
        record_ended_at = ended_at or record_started_at + timedelta(
            seconds=duration_sec
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
        duration_sec=duration_sec,
        started_at=record_started_at,
        ended_at=record_ended_at,
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
        pair_order=pair_order,  # type: ignore[arg-type]
        pair_time_gap_sec=pair_time_gap_sec,
        measurement_plan_id=measurement_plan_id,
        source_commit=source_commit,
        benchmark_id=benchmark_id,
        objective_id=objective_id,
        failure_classification=failure,
    )


def _statistical_result(**overrides: object) -> StatisticalResult:
    payload: dict[str, object] = {
        "comparison": "candidate_vs_baseline",
        "objective_direction": "higher_is_better",
        "point_estimate": 5.0,
        "relative_effect_pct": 5.0,
        "relative_ci_low_pct": 3.5,
        "relative_ci_high_pct": 6.5,
        "ci_low": 3.5,
        "ci_high": 6.5,
        "confidence_level": 0.95,
        "method": "iid_percentile_bootstrap",
        "p_value": 0.01,
        "verdict": "significant_improvement",
        "significant_single_comparison": True,
        "n_measured": 20,
        "n_valid": 10,
        "n_invalid": 0,
        "baseline_n_valid": 10,
        "candidate_n_valid": 10,
        "effective_sample_size": 10.0,
        "lag1_autocorrelation": 0.0,
        "paired": False,
        "pair_quality": "unknown",
        "provenance_complete": True,
    }
    payload.update(overrides)
    if payload.get("paired") is True and "pair_count" not in overrides:
        payload["pair_count"] = 10
    if payload.get("verdict") not in {
        "significant_improvement",
        "significant_regression",
    }:
        payload["significant_single_comparison"] = False
    return StatisticalResult.model_validate(payload)


def _mixed_utc_timestamp(index: int, *, offset_micros: int = 0) -> str:
    micros = index * 50_000 + offset_micros
    if micros == 0:
        return "2026-06-10T09:00:00Z"
    if index % 4 == 0:
        return f"2026-06-10T09:00:00.{micros // 1000:03d}Z"
    if index % 4 == 1:
        return f"2026-06-10T09:00:00.{micros:06d}+00:00"
    if index % 4 == 2:
        return f"2026-06-10T09:00:00.{micros // 1000:03d}+00:00"
    return f"2026-06-10T09:00:00.{micros:06d}Z"


def _ar1_scores(
    *,
    seed: int,
    mean: float,
    n: int = 80,
    phi: float = 0.35,
    sigma: float = 0.2,
) -> tuple[float, ...]:
    rng = random.Random(seed)
    state = 0.0
    scores: list[float] = []
    for _ in range(n):
        state = phi * state + rng.gauss(0.0, sigma)
        scores.append(mean + state)
    return tuple(scores)
