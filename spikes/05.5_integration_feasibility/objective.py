"""Synthetic objective for the 05.5 integration feasibility spike."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal


ScoreOutcome = Literal["success", "compile_failed", "infra_failure"]


@dataclass(frozen=True)
class ScoreResult:
    """Mock compile+benchmark outcome."""

    outcome: ScoreOutcome
    score: float | None = None
    reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome == "success"


@dataclass(frozen=True)
class SyntheticObjective:
    """Mock compile+benchmark with a non-greedy second-order optimum.

    The optimum intentionally requires the pair `-fA` + `-fB`. Each option is
    mildly bad alone, so a single-option greedy strategy should avoid them.
    """

    known_optimum: frozenset[str] = frozenset(
        {"-O3", "-funroll-loops", "-fA", "-fB"}
    )
    noise_sigma: float = 2.0
    infra_fail_rate: float = 0.05

    def evaluate(
        self,
        combo: frozenset[str],
        *,
        module: str,
        rng: random.Random,
    ) -> ScoreResult:
        """Evaluate one mock candidate combo."""

        if "-O3" in combo and "-Os" in combo:
            return ScoreResult(
                outcome="compile_failed",
                reason="conflicting opt levels",
            )
        if rng.random() < self.infra_fail_rate:
            return ScoreResult(outcome="infra_failure", reason="transient infra")

        score = self.deterministic_score(combo, module=module)
        if self.noise_sigma:
            score += rng.gauss(0.0, self.noise_sigma)
        return ScoreResult(outcome="success", score=score)

    def deterministic_score(self, combo: frozenset[str], *, module: str) -> float:
        """Return score without infra failure or benchmark noise."""

        score = 100.0
        if "-O3" in combo:
            score += 5.0
        if "-Os" in combo:
            score += 2.0
        if "-funroll-loops" in combo:
            score += 3.0
        if "-fA" in combo and "-fB" in combo:
            score += 12.0
        elif "-fA" in combo or "-fB" in combo:
            score -= 1.0
        if "-ffast-math" in combo and module == "fp_sensitive":
            score -= 10.0

        extra_options = combo - self.known_optimum
        score -= 0.5 * len(extra_options)
        return score

    def optimum_score(self, *, module: str = "core") -> float:
        """Deterministic score of the known optimum."""

        return self.deterministic_score(self.known_optimum, module=module)
