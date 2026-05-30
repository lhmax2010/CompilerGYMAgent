from __future__ import annotations

import random

import pytest

from objective import SyntheticObjective
from option_ir import DEFAULT_OPTIONS, OptionV0, option_by_raw, validate_option_catalog
from runner import run_strategy
from strategies import RandomStrategy


def objective_without_noise() -> SyntheticObjective:
    return SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)


def test_option_catalog_validates_unique_ids_and_known_conflicts() -> None:
    catalog = validate_option_catalog(DEFAULT_OPTIONS)

    assert option_by_raw(catalog)["-O3"].conflicts == ("opt_Os",)
    with pytest.raises(ValueError, match="unique"):
        validate_option_catalog(
            (
                OptionV0("dup", "-O3"),
                OptionV0("dup", "-Os"),
            )
        )
    with pytest.raises(ValueError, match="unknown conflict"):
        validate_option_catalog((OptionV0("opt_x", "-fx", conflicts=("missing",)),))


def test_synthetic_objective_rejects_conflicting_optimization_levels() -> None:
    objective = objective_without_noise()

    result = objective.evaluate(
        frozenset({"-O3", "-Os"}),
        module="core",
        rng=random.Random(1),
    )

    assert result.outcome == "compile_failed"
    assert result.reason == "conflicting opt levels"


def test_second_order_interaction_is_not_single_option_greedy() -> None:
    objective = objective_without_noise()

    baseline = objective.deterministic_score(
        frozenset({"-O3", "-funroll-loops"}),
        module="core",
    )
    with_a = objective.deterministic_score(
        frozenset({"-O3", "-funroll-loops", "-fA"}),
        module="core",
    )
    with_b = objective.deterministic_score(
        frozenset({"-O3", "-funroll-loops", "-fB"}),
        module="core",
    )
    with_pair = objective.deterministic_score(
        frozenset({"-O3", "-funroll-loops", "-fA", "-fB"}),
        module="core",
    )

    assert with_a < baseline
    assert with_b < baseline
    assert with_pair == objective.optimum_score(module="core")
    assert with_pair - baseline == 12.0


def test_known_optimum_beats_superset_with_extra_flags() -> None:
    objective = objective_without_noise()

    optimum = objective.optimum_score(module="core")
    superset = objective.deterministic_score(
        objective.known_optimum | frozenset({"-flto", "-fno-plt"}),
        module="core",
    )

    assert optimum > superset


def test_fp_sensitive_module_penalizes_fast_math() -> None:
    objective = objective_without_noise()

    neutral = objective.deterministic_score(
        frozenset({"-O3", "-ffast-math"}),
        module="core",
    )
    fp_sensitive = objective.deterministic_score(
        frozenset({"-O3", "-ffast-math"}),
        module="fp_sensitive",
    )

    assert neutral - fp_sensitive == 10.0


def test_random_strategy_runner_is_seed_deterministic() -> None:
    objective = SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)
    strategy = RandomStrategy(DEFAULT_OPTIONS, include_probability=0.4)

    first = run_strategy(strategy, objective, rounds=12, seed=42)
    second = run_strategy(strategy, objective, rounds=12, seed=42)

    assert first.trials == second.trials
    assert len(first.trials) == 12
    assert first.best_trial is not None


def test_random_strategy_runner_records_failures_and_successes() -> None:
    objective = SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)
    strategy = RandomStrategy(DEFAULT_OPTIONS, include_probability=0.6)

    result = run_strategy(strategy, objective, rounds=20, seed=7)

    assert result.successful_trials
    assert result.compile_failed_count > 0
    assert result.infra_failure_count == 0
    assert all(trial.round_index == index for index, trial in enumerate(result.trials))
