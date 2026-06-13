from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from agent import (
    RunLevelRecord,
    compare_run_records,
    compute_result_combo_hash,
    iid_percentile_bootstrap_ci,
    moving_block_bootstrap_ci,
)
from agent.skills.fake_gbs import FakeGbsNoiseModel


pytestmark = pytest.mark.slow

UTC = timezone.utc
NOW = datetime(2026, 6, 13, 16, 0, tzinfo=UTC)
SHA_A = "sha256:" + "a" * 64
BURSTY_STATIONARY_MEAN = -(7.0 / 3.0 + 22.0 / 9.0)


def test_iid_gaussian_bootstrap_coverage_regression() -> None:
    coverage = _iid_gaussian_coverage(
        reps=200,
        sample_size=40,
        bootstrap_samples=400,
        seed=20260610,
    )

    assert 0.92 <= coverage <= 0.97


def test_bursty_naive_undercoverage_and_moving_block_improvement_regression() -> None:
    naive_coverage = _bursty_coverage(
        method="iid",
        reps=180,
        sample_size=40,
        bootstrap_samples=300,
        seed=20260613,
    )
    block_coverage = _bursty_coverage(
        method="moving_block",
        reps=180,
        sample_size=40,
        bootstrap_samples=300,
        seed=20260613,
    )

    assert naive_coverage < 0.85
    assert block_coverage > naive_coverage + 0.03


def test_detected_unpaired_autocorrelation_is_always_inconclusive_regression() -> None:
    significant = 0
    inconclusive = 0
    for seed in range(30):
        baseline_scores = tuple(float(index) for index in range(1, 21))
        candidate_scores = tuple(value + 25.0 for value in baseline_scores)
        result = compare_run_records(
            _records(baseline_scores, prefix=f"base_{seed}"),
            _records(candidate_scores, prefix=f"cand_{seed}"),
            bootstrap_samples=120,
            seed=20260613 + seed,
        )
        if result.significant_single_comparison:
            significant += 1
        if result.verdict == "inconclusive":
            inconclusive += 1

    assert significant == 0
    assert inconclusive == 30


def _iid_gaussian_coverage(
    *,
    reps: int,
    sample_size: int,
    bootstrap_samples: int,
    seed: int,
) -> float:
    rng = random.Random(seed)
    covered = 0
    truth = 3.0
    for rep in range(reps):
        values = tuple(rng.gauss(truth, 2.0) for _ in range(sample_size))
        ci = iid_percentile_bootstrap_ci(
            values,
            bootstrap_samples=bootstrap_samples,
            seed=seed + rep,
        )
        if ci.ci_low <= truth <= ci.ci_high:
            covered += 1
    return covered / reps


def _bursty_coverage(
    *,
    method: str,
    reps: int,
    sample_size: int,
    bootstrap_samples: int,
    seed: int,
) -> float:
    covered = 0
    for rep in range(reps):
        values = _fake_gbs_bursty_values(seed + rep, sample_size)
        if method == "iid":
            ci = iid_percentile_bootstrap_ci(
                values,
                bootstrap_samples=bootstrap_samples,
                seed=seed + rep,
            )
        elif method == "moving_block":
            ci = moving_block_bootstrap_ci(
                values,
                bootstrap_samples=bootstrap_samples,
                seed=seed + rep,
            )
        else:
            raise ValueError(f"unknown method {method!r}")
        if ci.ci_low <= BURSTY_STATIONARY_MEAN <= ci.ci_high:
            covered += 1
    return covered / reps


def _fake_gbs_bursty_values(seed: int, sample_size: int) -> tuple[float, ...]:
    model = FakeGbsNoiseModel(seed=seed)
    for _ in range(100):
        model.sample("bursty")
    return tuple(model.sample("bursty").value for _ in range(sample_size))


def _records(scores: Sequence[float], *, prefix: str) -> tuple[RunLevelRecord, ...]:
    return tuple(
        RunLevelRecord(
            run_id=f"{prefix}_{index}",
            run_index=index,
            combo_hash=compute_result_combo_hash(["-O2"]),
            score=score,
            phase="measured",
            metric_name="throughput",
            metric_unit="items/sec",
            objective_direction="higher_is_better",
            duration_sec=0.1,
            started_at=NOW + timedelta(seconds=index),
            ended_at=NOW + timedelta(seconds=index, milliseconds=100),
            exit_code=0,
            stdout_ref="logs/bench.stdout#L1",
            stderr_ref="logs/bench.stderr#L1",
            valid_for_scoring=True,
            benchmark_cmd=("fake-gbs", "benchmark"),
            artifact_ref="artifacts/fake/run.artifact",
            artifact_hash=SHA_A,
            artifact_hash_verified=True,
            score_source_ref="logs/bench.stdout#L1",
        )
        for index, score in enumerate(scores)
    )
