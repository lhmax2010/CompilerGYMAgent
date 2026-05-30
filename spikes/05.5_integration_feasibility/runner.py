"""Plain Python runner for the 05.5 mock decision loop."""

from __future__ import annotations

import random
from dataclasses import dataclass

from objective import SyntheticObjective
from strategies import CandidateExhausted, SearchStrategy, TrialOutcome


@dataclass(frozen=True)
class RunResult:
    """Summary of one mock strategy run."""

    seed: int
    module: str
    trials: tuple[TrialOutcome, ...]
    exhausted: bool = False

    @property
    def successful_trials(self) -> tuple[TrialOutcome, ...]:
        return tuple(trial for trial in self.trials if trial.result.succeeded)

    @property
    def best_trial(self) -> TrialOutcome | None:
        successes = self.successful_trials
        if not successes:
            return None
        return max(successes, key=lambda trial: trial.result.score or float("-inf"))

    @property
    def best_score(self) -> float | None:
        best = self.best_trial
        return None if best is None else best.result.score

    @property
    def compile_failed_count(self) -> int:
        return sum(1 for trial in self.trials if trial.result.outcome == "compile_failed")

    @property
    def infra_failure_count(self) -> int:
        return sum(1 for trial in self.trials if trial.result.outcome == "infra_failure")

    @property
    def unique_combo_count(self) -> int:
        return len({trial.combo for trial in self.trials})

    @property
    def duplicate_trial_rate(self) -> float:
        if not self.trials:
            return 0.0
        duplicates = len(self.trials) - self.unique_combo_count
        return duplicates / len(self.trials)


def run_strategy(
    strategy: SearchStrategy,
    objective: SyntheticObjective,
    *,
    rounds: int,
    seed: int,
    module: str = "core",
) -> RunResult:
    """Run one strategy against the synthetic objective."""

    if rounds <= 0:
        raise ValueError("rounds must be positive")
    rng = random.Random(seed)
    history: list[TrialOutcome] = []
    for round_index in range(rounds):
        try:
            combo = strategy.propose(history, rng)
        except CandidateExhausted:
            return RunResult(
                seed=seed,
                module=module,
                trials=tuple(history),
                exhausted=True,
            )
        result = objective.evaluate(combo, module=module, rng=rng)
        history.append(
            TrialOutcome(
                round_index=round_index,
                combo=combo,
                module=module,
                result=result,
            )
        )
    return RunResult(seed=seed, module=module, trials=tuple(history))
