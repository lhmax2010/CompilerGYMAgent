from __future__ import annotations

import random

from mock_llm import MockLLM
from objective import SyntheticObjective
from option_ir import DEFAULT_OPTIONS, raw_options
from runner import run_strategy
from strategies import LLMOnlyStrategy, LocalMutationStrategy


def objective_without_noise() -> SyntheticObjective:
    return SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)


def test_mock_llm_good_is_seed_deterministic_and_catalog_bounded() -> None:
    llm = MockLLM(quality="good")

    first = [llm.propose([], random.Random(seed)) for seed in range(12)]
    second = [llm.propose([], random.Random(seed)) for seed in range(12)]
    known = set(raw_options(DEFAULT_OPTIONS))

    assert first == second
    assert all(combo <= known for combo in first)
    assert objective_without_noise().known_optimum in first


def test_mock_llm_poor_emits_conflicts_and_unknown_options() -> None:
    llm = MockLLM(quality="poor")
    proposals = [llm.propose([], random.Random(seed)) for seed in range(20)]
    known = set(raw_options(DEFAULT_OPTIONS))

    assert any({"-O3", "-Os"} <= combo for combo in proposals)
    assert any(combo - known for combo in proposals)


def test_llm_only_strategy_trusts_poor_llm_without_filtering() -> None:
    objective = objective_without_noise()
    strategy = LLMOnlyStrategy(MockLLM(quality="poor"))

    result = run_strategy(strategy, objective, rounds=18, seed=5)

    assert result.compile_failed_count > 0
    assert any("-fimaginary" in trial.combo for trial in result.trials)
    assert result.duplicate_trial_rate > 0.0


def test_llm_only_good_can_find_optimum_but_is_not_memory_driven() -> None:
    objective = objective_without_noise()
    strategy = LLMOnlyStrategy(MockLLM(quality="good"))

    result = run_strategy(strategy, objective, rounds=24, seed=9)

    assert any(trial.combo == objective.known_optimum for trial in result.trials)
    assert result.best_trial is not None
    assert result.best_trial.combo == objective.known_optimum
    assert result.duplicate_trial_rate > 0.0


def test_local_mutation_gets_stuck_at_single_flip_local_optimum() -> None:
    objective = objective_without_noise()
    strategy = LocalMutationStrategy(DEFAULT_OPTIONS)

    result = run_strategy(strategy, objective, rounds=40, seed=1)

    assert result.best_trial is not None
    assert result.best_trial.combo == frozenset({"-O3", "-funroll-loops"})
    assert result.best_score == 108.0
    assert result.best_score < objective.optimum_score(module="core")
    assert objective.known_optimum not in {trial.combo for trial in result.trials}


def test_local_mutation_evaluates_single_ab_neighbors_as_worse() -> None:
    objective = objective_without_noise()
    strategy = LocalMutationStrategy(DEFAULT_OPTIONS)

    result = run_strategy(strategy, objective, rounds=40, seed=1)
    scores_by_combo = {
        trial.combo: trial.result.score
        for trial in result.successful_trials
    }
    local_optimum = frozenset({"-O3", "-funroll-loops"})
    with_a = frozenset({"-O3", "-funroll-loops", "-fA"})
    with_b = frozenset({"-O3", "-funroll-loops", "-fB"})

    assert scores_by_combo[with_a] < scores_by_combo[local_optimum]
    assert scores_by_combo[with_b] < scores_by_combo[local_optimum]
    assert all(
        not {"-fA", "-fB"} <= trial.combo
        for trial in result.trials
    )


def test_local_mutation_history_is_seed_stable() -> None:
    objective = objective_without_noise()
    strategy = LocalMutationStrategy(DEFAULT_OPTIONS)

    first = run_strategy(strategy, objective, rounds=20, seed=11)
    second = run_strategy(strategy, objective, rounds=20, seed=99)

    assert first.trials == second.trials
