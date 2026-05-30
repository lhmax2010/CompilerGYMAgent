"""Deterministic mock LLM for the 05.5 integration feasibility spike."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from strategies import TrialOutcome


MockLLMQuality = Literal["good", "poor"]


@dataclass(frozen=True)
class MockLLM:
    """Controllable fake proposer.

    `good` produces mostly plausible catalog options and sometimes the known
    optimum. `poor` intentionally emits conflicts, unknown flags, and repeated
    shallow guesses so downstream fallback behavior can be tested.
    """

    quality: MockLLMQuality = "good"

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        if self.quality == "good":
            return frozenset(rng.choice(_good_proposals()))
        if self.quality == "poor":
            return frozenset(rng.choice(_poor_proposals(history)))
        raise ValueError(f"unknown MockLLM quality: {self.quality!r}")


def _good_proposals() -> tuple[tuple[str, ...], ...]:
    return (
        ("-O3",),
        ("-O3", "-funroll-loops"),
        ("-O3", "-fA", "-fB"),
        ("-O3", "-funroll-loops", "-fA", "-fB"),
        ("-O3", "-funroll-loops", "-flto"),
        ("-O3", "-fno-plt"),
    )


def _poor_proposals(history: list[TrialOutcome]) -> tuple[tuple[str, ...], ...]:
    repeated = tuple(sorted(history[-1].combo)) if history else ("-O3", "-Os")
    return (
        ("-O3", "-Os"),
        ("-fimaginary",),
        ("-funroll-loops", "-fmade-up"),
        ("-ffast-math",),
        ("-O3", "-Os", "-fimaginary"),
        repeated,
    )
