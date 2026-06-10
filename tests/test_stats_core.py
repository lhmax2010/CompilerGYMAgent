from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from agent import (
    FailureClassification,
    RunLevelRecord,
    compute_acf_effective_sample_size,
    compute_effective_sample_size,
    compute_lag_autocorrelation,
    compute_lag1_autocorrelation,
    compute_summary_effective_sample_size,
    compute_result_combo_hash,
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


def test_valid_measured_record_without_score_is_rejected_defensively() -> None:
    class ScorelessRecord:
        phase = "measured"
        valid_for_scoring = True
        score = None

    with pytest.raises(ValueError, match="valid measured records"):
        measured_valid_scores((ScorelessRecord(),))  # type: ignore[arg-type]


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
