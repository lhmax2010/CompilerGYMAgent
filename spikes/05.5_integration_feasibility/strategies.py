"""Search strategies for the 05.5 spike."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from objective import ScoreResult
from option_ir import OptionV0, raw_options


class CandidateExhausted(RuntimeError):
    """Strategy has no more candidates worth spending trial budget on."""


@dataclass(frozen=True)
class TrialOutcome:
    """One proposed combo and its mock evaluation result."""

    round_index: int
    combo: frozenset[str]
    module: str
    result: ScoreResult


class SearchStrategy(Protocol):
    """Strategy protocol used by the plain Python spike runner."""

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        """Propose one combo."""


@dataclass(frozen=True)
class RandomStrategy:
    """Naive baseline that samples options independently."""

    options: tuple[OptionV0, ...]
    include_probability: float = 0.35
    allow_empty: bool = False

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        del history
        selected = tuple(
            option for option in raw_options(self.options)
            if rng.random() < self.include_probability
        )
        if selected or self.allow_empty:
            return frozenset(selected)
        fallback = rng.choice(raw_options(self.options))
        return frozenset({fallback})


@dataclass(frozen=True)
class LLMOnlyStrategy:
    """Baseline that trusts MockLLM output without memory or constraints."""

    llm: object

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        propose = getattr(self.llm, "propose")
        return frozenset(propose(history, rng))


@dataclass(frozen=True)
class LocalMutationStrategy:
    """One-flip hill climber around the best successful combo.

    This baseline intentionally cannot propose two simultaneous additions, so it
    should get stuck before discovering the `-fA` + `-fB` interaction.
    """

    options: tuple[OptionV0, ...]
    start_combo: frozenset[str] = frozenset()

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        del rng
        tried = {trial.combo for trial in history}
        center = self._best_successful_combo(history)
        for neighbor in self._one_flip_neighbors(center):
            if neighbor not in tried:
                return neighbor
        return center

    def _best_successful_combo(
        self,
        history: list[TrialOutcome],
    ) -> frozenset[str]:
        successes = [trial for trial in history if trial.result.succeeded]
        if not successes:
            return self.start_combo
        best = max(successes, key=lambda trial: trial.result.score or float("-inf"))
        return best.combo

    def _one_flip_neighbors(self, combo: frozenset[str]) -> tuple[frozenset[str], ...]:
        neighbors: list[frozenset[str]] = []
        for option in raw_options(self.options):
            if option in combo:
                neighbors.append(frozenset(value for value in combo if value != option))
            else:
                neighbors.append(frozenset((*combo, option)))
        return tuple(sorted(neighbors, key=lambda item: tuple(sorted(item))))
