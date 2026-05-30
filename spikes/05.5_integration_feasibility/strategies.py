"""Search strategies for the 05.5 spike."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from objective import ScoreResult
from option_ir import OptionV0, raw_options


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
