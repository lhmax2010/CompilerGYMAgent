from __future__ import annotations

import random
from statistics import median

from mock_llm import MockLLM
from objective import ScoreResult, SyntheticObjective
from option_ir import DEFAULT_OPTIONS
from runner import run_strategy
from strategies import LLMOnlyStrategy, LocalMutationStrategy, TrialOutcome
from full_agent import ConstraintLayer, ExperienceMemory, FullAgentStrategy


def objective_without_noise() -> SyntheticObjective:
    return SyntheticObjective(noise_sigma=0.0, infra_fail_rate=0.0)


class RepeatingLLM:
    def __init__(self, combo: frozenset[str]) -> None:
        self.combo = combo

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        del history, rng
        return self.combo


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


def run_manual_loop(
    strategy: FullAgentStrategy,
    objective: SyntheticObjective,
    *,
    rounds: int,
    rng: random.Random,
    history: list[TrialOutcome] | None = None,
) -> list[TrialOutcome]:
    from strategies import CandidateExhausted

    current = [] if history is None else list(history)
    start = len(current)
    for round_index in range(start, rounds):
        try:
            combo = strategy.propose(current, rng)
        except CandidateExhausted:
            break
        current.append(
            TrialOutcome(
                round_index=round_index,
                combo=combo,
                module="core",
                result=objective.evaluate(combo, module="core", rng=rng),
            )
        )
    return current


def test_full_agent_blocks_poor_llm_conflicts_and_unknowns_before_execution() -> None:
    objective = SyntheticObjective()
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
    assert not any({"-O3", "-Os"} <= trial.combo for trial in result.trials)
    assert all(trial.combo <= known for trial in result.trials)
    assert {"conflict", "unknown_option", "duplicate"} <= {
        rejection.reason for rejection in strategy.rejections
    }


def test_failed_experience_blocks_retry_without_trial_budget() -> None:
    failed = frozenset({"-ffast-math"})
    history = [
        TrialOutcome(
            round_index=0,
            combo=failed,
            module="core",
            result=ScoreResult(outcome="compile_failed", reason="synthetic fail"),
        )
    ]
    memory = ExperienceMemory.from_history(history)
    layer = ConstraintLayer()

    assert layer.validate(
        frozenset({"-O3", "-ffast-math"}),
        memory=memory,
    ) == "known_failed_subset"
    assert failed in memory.known_failed_subsets


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


def test_random_fallback_alone_does_not_find_second_order_optimum() -> None:
    class NoGuidedInteraction(FullAgentStrategy):
        def _guided_interaction_candidates(self, history):  # type: ignore[no-untyped-def]
            del history
            return iter(())

    objective = objective_without_noise()
    hits = 0
    for seed in range(20):
        strategy = NoGuidedInteraction(llm=MockLLM(quality="poor"))
        result = run_strategy(strategy, objective, rounds=40, seed=seed)
        hits += int(
            result.best_trial is not None
            and result.best_trial.combo == objective.known_optimum
        )

    assert hits == 0


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


def test_poor_llm_fallback_improves_under_noisy_default_objective() -> None:
    objective = SyntheticObjective()
    full_scores: list[float] = []
    llm_scores: list[float] = []
    for seed in range(20):
        full = run_strategy(
            FullAgentStrategy(llm=MockLLM(quality="poor")),
            objective,
            rounds=40,
            seed=seed,
        )
        llm_only = run_strategy(
            LLMOnlyStrategy(MockLLM(quality="poor")),
            objective,
            rounds=40,
            seed=seed,
        )
        assert full.best_score is not None
        assert llm_only.best_score is not None
        full_scores.append(full.best_score)
        llm_scores.append(llm_only.best_score)

    assert median(full_scores) >= median(llm_scores) + 10.0


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


def test_near_miss_suspects_exclude_neutral_noise_options() -> None:
    objective = objective_without_noise()
    center = frozenset({"-O3", "-funroll-loops"})
    combos = (
        center,
        frozenset({"-O3", "-funroll-loops", "-fA"}),
        frozenset({"-O3", "-funroll-loops", "-fB"}),
        frozenset({"-O3", "-funroll-loops", "-fno-plt"}),
        frozenset({"-O3", "-funroll-loops", "-flto"}),
    )
    history = [
        TrialOutcome(
            round_index=index,
            combo=combo,
            module="core",
            result=objective.evaluate(combo, module="core", rng=random.Random(index)),
        )
        for index, combo in enumerate(combos)
    ]
    memory = ExperienceMemory.from_history(history)

    suspects = memory.near_miss_additions(
        center=center,
        min_score_drop=0.75,
        max_score_drop=1.25,
        limit=6,
    )

    assert set(suspects) == {"-fA", "-fB"}


def test_noisy_success_and_infra_failure_do_not_become_hard_bad_experience() -> None:
    objective = SyntheticObjective()
    low_success_combo = frozenset({"-O3", "-fA"})
    infra_combo = frozenset({"-ffast-math"})
    infra_result = objective.evaluate(
        infra_combo,
        module="core",
        rng=random.Random(31),
    )
    assert infra_result.outcome == "infra_failure"
    history = [
        TrialOutcome(
            round_index=0,
            combo=low_success_combo,
            module="core",
            result=ScoreResult(outcome="success", score=1.0),
        ),
        TrialOutcome(
            round_index=1,
            combo=infra_combo,
            module="core",
            result=infra_result,
        ),
    ]
    memory = ExperienceMemory.from_history(history)
    layer = ConstraintLayer()

    assert memory.known_failed_subsets == frozenset()
    assert layer.validate(
        frozenset({"-O3", "-fA", "-fB"}),
        memory=memory,
    ) is None
    assert layer.validate(
        frozenset({"-ffast-math", "-fA"}),
        memory=memory,
    ) is None


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


def test_bad_experience_injection_is_not_permanent_with_suspicion_counter() -> None:
    legal_combo = frozenset({"-O3", "-funroll-loops", "-fA", "-fB"})
    layer = ConstraintLayer(
        soft_blocked=frozenset({legal_combo}),
        suspicion_threshold=2,
    )
    memory = ExperienceMemory.from_history([])

    assert layer.validate(legal_combo, memory=memory) == "soft_blocked"
    assert layer.validate(legal_combo, memory=memory) is None
    assert layer.forced_candidates == [legal_combo]


def test_full_agent_does_not_spend_budget_on_duplicates() -> None:
    objective = objective_without_noise()
    strategy = FullAgentStrategy(llm=MockLLM(quality="good"))

    result = run_strategy(strategy, objective, rounds=30, seed=7)

    assert result.duplicate_trial_rate == 0.0
    assert any(rejection.reason == "duplicate" for rejection in strategy.rejections)


def test_repeated_llm_pressure_is_rejected_without_trial_budget() -> None:
    repeated = frozenset({"-O3"})
    objective = SyntheticObjective()
    strategy = FullAgentStrategy(llm=RepeatingLLM(repeated))

    result = run_strategy(strategy, objective, rounds=12, seed=4)

    assert result.duplicate_trial_rate == 0.0
    assert any(rejection.combo == repeated for rejection in strategy.rejections)
    assert any(rejection.reason == "duplicate" for rejection in strategy.rejections)


def test_crash_resume_rebuilds_loop_state_from_history() -> None:
    objective = SyntheticObjective()
    seed = 17
    uninterrupted_rng = random.Random(seed)
    uninterrupted = run_manual_loop(
        FullAgentStrategy(llm=MockLLM(quality="poor")),
        objective,
        rounds=30,
        rng=uninterrupted_rng,
    )

    prefix_rng = random.Random(seed)
    prefix = run_manual_loop(
        FullAgentStrategy(llm=MockLLM(quality="poor")),
        objective,
        rounds=15,
        rng=prefix_rng,
    )
    rng_state = prefix_rng.getstate()
    resumed_rng = random.Random()
    resumed_rng.setstate(rng_state)
    resumed = run_manual_loop(
        FullAgentStrategy(llm=MockLLM(quality="poor")),
        objective,
        rounds=30,
        rng=resumed_rng,
        history=prefix,
    )

    assert resumed == uninterrupted
    assert len({trial.combo for trial in resumed}) == len(resumed)
    assert [trial.round_index for trial in resumed] == list(range(len(resumed)))
