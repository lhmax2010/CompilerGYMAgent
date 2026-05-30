from __future__ import annotations

from mock_llm import MockLLM
from objective import ScoreResult, SyntheticObjective
from option_ir import DEFAULT_OPTIONS
from runner import run_strategy
from strategies import LLMOnlyStrategy, LocalMutationStrategy, TrialOutcome
from full_agent import ConstraintLayer, ExperienceMemory, FullAgentStrategy


def objective_without_noise() -> SyntheticObjective:
    return SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)


def run_until_exhausted(
    strategy: FullAgentStrategy,
    objective: SyntheticObjective,
    *,
    rounds: int,
    seed: int,
) -> tuple[list[TrialOutcome], bool]:
    import random

    rng = random.Random(seed)
    history: list[TrialOutcome] = []
    exhausted = False
    for round_index in range(rounds):
        try:
            combo = strategy.propose(history, rng)
        except RuntimeError:
            exhausted = True
            break
        history.append(
            TrialOutcome(
                round_index=round_index,
                combo=combo,
                module="core",
                result=objective.evaluate(combo, module="core", rng=rng),
            )
        )
    return history, exhausted


def test_full_agent_blocks_poor_llm_conflicts_and_unknowns_before_execution() -> None:
    objective = objective_without_noise()
    strategy = FullAgentStrategy(llm=MockLLM(quality="poor"))

    result = run_strategy(strategy, objective, rounds=30, seed=5)
    known = {
        "-O3",
        "-Os",
        "-funroll-loops",
        "-fA",
        "-fB",
        "-ffast-math",
        "-fno-plt",
        "-flto",
    }

    assert result.compile_failed_count == 0
    assert all(trial.combo <= known for trial in result.trials)
    assert {"conflict", "unknown_option", "duplicate"} <= {
        rejection.reason for rejection in strategy.rejections
    }


def test_full_agent_finds_second_order_optimum_with_poor_llm() -> None:
    objective = objective_without_noise()
    hits = 0
    for seed in range(10):
        strategy = FullAgentStrategy(llm=MockLLM(quality="poor"))
        result = run_strategy(strategy, objective, rounds=40, seed=seed)
        hits += int(
            result.best_trial is not None
            and result.best_trial.combo == objective.known_optimum
        )

    assert hits >= 8


def test_full_agent_finds_second_order_without_random_or_enumeration() -> None:
    objective = objective_without_noise()
    hits = 0
    for seed in range(10):
        strategy = FullAgentStrategy(
            llm=MockLLM(quality="poor"),
            max_random_fallbacks=0,
        )
        result = run_strategy(strategy, objective, rounds=20, seed=seed)
        hits += int(
            result.best_trial is not None
            and result.best_trial.combo == objective.known_optimum
        )

    assert hits == 10
    assert not hasattr(FullAgentStrategy, "_enumerated_candidates")


def test_guided_interaction_is_required_without_random_fallback() -> None:
    class NoGuidedInteraction(FullAgentStrategy):
        def _guided_interaction_candidates(self, history):  # type: ignore[no-untyped-def]
            del history
            return iter(())

    objective = objective_without_noise()
    strategy = NoGuidedInteraction(
        llm=MockLLM(quality="poor"),
        max_random_fallbacks=0,
    )

    history, exhausted = run_until_exhausted(strategy, objective, rounds=40, seed=3)

    assert exhausted
    assert objective.known_optimum not in {trial.combo for trial in history}


def test_full_agent_beats_poor_llm_only_and_local_mutation() -> None:
    objective = objective_without_noise()

    full = run_strategy(
        FullAgentStrategy(llm=MockLLM(quality="poor")),
        objective,
        rounds=40,
        seed=3,
    )
    llm_only = run_strategy(
        LLMOnlyStrategy(MockLLM(quality="poor")),
        objective,
        rounds=40,
        seed=3,
    )
    local = run_strategy(
        LocalMutationStrategy(DEFAULT_OPTIONS),
        objective,
        rounds=40,
        seed=3,
    )

    assert full.best_trial is not None
    assert full.best_trial.combo == objective.known_optimum
    assert full.best_score == objective.optimum_score(module="core")
    assert llm_only.best_score is not None
    assert local.best_score is not None
    assert full.best_score > llm_only.best_score
    assert full.best_score > local.best_score


def test_full_agent_good_llm_wins_efficiency_against_llm_only() -> None:
    objective = objective_without_noise()

    full = run_strategy(
        FullAgentStrategy(llm=MockLLM(quality="good")),
        objective,
        rounds=24,
        seed=9,
    )
    llm_only = run_strategy(
        LLMOnlyStrategy(MockLLM(quality="good")),
        objective,
        rounds=24,
        seed=9,
    )

    assert full.best_trial is not None
    assert llm_only.best_trial is not None
    assert full.best_trial.combo == objective.known_optimum
    assert llm_only.best_trial.combo == objective.known_optimum
    assert full.duplicate_trial_rate == 0.0
    assert llm_only.duplicate_trial_rate > 0.5
    assert full.unique_combo_count > llm_only.unique_combo_count


def test_constraint_layer_filters_known_failed_subsets() -> None:
    failed = frozenset({"-ffast-math"})
    memory = ExperienceMemory.from_history(
        [
            TrialOutcome(
                round_index=0,
                combo=failed,
                module="core",
                result=ScoreResult(outcome="compile_failed", reason="conflict"),
            )
        ]
    )
    layer = ConstraintLayer()

    reason = layer.validate(
        frozenset({"-O3", "-ffast-math"}),
        memory=memory,
    )

    assert reason == "known_failed_subset"


def test_suspicion_counter_forces_soft_blocked_candidate_once() -> None:
    optimum = SyntheticObjective().known_optimum
    layer = ConstraintLayer(
        soft_blocked=frozenset({optimum}),
        suspicion_threshold=3,
    )
    memory = ExperienceMemory.from_history([])

    assert layer.validate(optimum, memory=memory) == "soft_blocked"
    assert layer.validate(optimum, memory=memory) == "soft_blocked"
    assert layer.validate(optimum, memory=memory) is None
    assert layer.forced_candidates == [optimum]


def test_full_agent_does_not_spend_budget_on_duplicates() -> None:
    objective = objective_without_noise()
    strategy = FullAgentStrategy(llm=MockLLM(quality="good"))

    result = run_strategy(strategy, objective, rounds=30, seed=7)

    assert result.duplicate_trial_rate == 0.0
    assert any(rejection.reason == "duplicate" for rejection in strategy.rejections)
