from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from agent import (
    FailureClassification,
    IID_PERCENTILE_BOOTSTRAP_METHOD,
    RunLevelRecord,
    compute_acf_effective_sample_size,
    compute_effective_sample_size,
    compute_lag_autocorrelation,
    compute_lag1_autocorrelation,
    compute_summary_effective_sample_size,
    compute_result_combo_hash,
    diagnose_iid_assumption,
    iid_percentile_bootstrap_ci,
    measured_valid_scores,
    run_summary_hint,
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


def _record(
    *,
    score: float | None,
    run_index: int,
    phase: str = "measured",
    valid_for_scoring: bool = True,
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
        run_id=f"run_{phase}_{run_index}",
        run_index=run_index,
        combo_hash=compute_result_combo_hash(["-O2"]),
        score=score,
        phase=phase,  # type: ignore[arg-type]
        metric_name="throughput",
        metric_unit="items/sec",
        objective_direction="higher_is_better",
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
        failure_classification=failure,
    )
