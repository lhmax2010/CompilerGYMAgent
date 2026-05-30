"""Minimal full-agent strategy for the 05.5 integration spike."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Literal

from mock_llm import MockLLM
from option_ir import DEFAULT_OPTIONS, OptionV0, option_by_raw, raw_options
from strategies import TrialOutcome


RejectReason = Literal[
    "empty",
    "duplicate",
    "unknown_option",
    "conflict",
    "known_failed_subset",
    "soft_blocked",
]


@dataclass(frozen=True)
class RejectedCandidate:
    """One candidate rejected before spending mock trial budget."""

    combo: frozenset[str]
    reason: RejectReason


@dataclass(frozen=True)
class ExperienceMemory:
    """Small memory extracted from prior trial outcomes."""

    tried_combos: frozenset[frozenset[str]]
    successful_trials: tuple[TrialOutcome, ...]
    known_failed_subsets: frozenset[frozenset[str]]

    @classmethod
    def from_history(cls, history: list[TrialOutcome]) -> ExperienceMemory:
        failed = frozenset(
            trial.combo
            for trial in history
            if trial.result.outcome == "compile_failed"
        )
        successes = tuple(trial for trial in history if trial.result.succeeded)
        return cls(
            tried_combos=frozenset(trial.combo for trial in history),
            successful_trials=successes,
            known_failed_subsets=failed,
        )

    def near_miss_additions(
        self,
        *,
        center: frozenset[str],
        max_score_drop: float,
        limit: int,
    ) -> tuple[str, ...]:
        """Return single additions that were only mildly worse than center."""

        center_score = self._score_for(center)
        if center_score is None:
            return ()
        near_misses: list[tuple[float, str]] = []
        for trial in self.successful_trials:
            combo = trial.combo
            added = combo - center
            if len(added) != 1 or not center < combo:
                continue
            score = trial.result.score
            if score is None:
                continue
            drop = center_score - score
            if 0.0 <= drop <= max_score_drop:
                near_misses.append((drop, next(iter(added))))
        near_misses.sort(key=lambda item: (item[0], item[1]))
        return tuple(raw for _drop, raw in near_misses[:limit])

    def _score_for(self, combo: frozenset[str]) -> float | None:
        for trial in reversed(self.successful_trials):
            if trial.combo == combo:
                return trial.result.score
        return None


@dataclass
class ConstraintLayer:
    """Reject candidates that should not consume mock trial budget."""

    options: tuple[OptionV0, ...] = DEFAULT_OPTIONS
    suspicion_threshold: int = 3
    soft_blocked: frozenset[frozenset[str]] = frozenset()
    suspicion_counts: dict[frozenset[str], int] = field(default_factory=dict)
    forced_candidates: list[frozenset[str]] = field(default_factory=list)

    def validate(
        self,
        combo: frozenset[str],
        *,
        memory: ExperienceMemory,
    ) -> RejectReason | None:
        """Return a rejection reason, or None when the combo may execute."""

        if not combo:
            return "empty"
        if combo in memory.tried_combos:
            return "duplicate"
        known_by_raw = option_by_raw(self.options)
        if combo - set(known_by_raw):
            return "unknown_option"
        if self._has_conflict(combo, known_by_raw):
            return "conflict"
        if any(failed <= combo for failed in memory.known_failed_subsets):
            return "known_failed_subset"
        if combo in self.soft_blocked and combo not in self.forced_candidates:
            count = self.suspicion_counts.get(combo, 0) + 1
            self.suspicion_counts[combo] = count
            if count >= self.suspicion_threshold:
                self.forced_candidates.append(combo)
                return None
            return "soft_blocked"
        return None

    def _has_conflict(
        self,
        combo: frozenset[str],
        known_by_raw: dict[str, OptionV0],
    ) -> bool:
        raw_by_id = {option.option_id: option.raw for option in known_by_raw.values()}
        for raw in combo:
            option = known_by_raw[raw]
            conflict_raws = {
                raw_by_id[conflict_id]
                for conflict_id in option.conflicts
            }
            if combo & conflict_raws:
                return True
        return False


@dataclass
class FullAgentStrategy:
    """Spike-local decision core: LLM + constraints + memory + exploration."""

    options: tuple[OptionV0, ...] = DEFAULT_OPTIONS
    llm: MockLLM = field(default_factory=lambda: MockLLM(quality="poor"))
    constraint_layer: ConstraintLayer | None = None
    max_random_fallbacks: int = 24
    interaction_max_score_drop: float = 1.25
    interaction_suspect_limit: int = 6
    rejections: list[RejectedCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.constraint_layer is None:
            self.constraint_layer = ConstraintLayer(options=self.options)

    def propose(
        self,
        history: list[TrialOutcome],
        rng: random.Random,
    ) -> frozenset[str]:
        memory = ExperienceMemory.from_history(history)
        for combo in self._candidate_stream(history, memory, rng):
            reason = self.constraint_layer.validate(combo, memory=memory)
            if reason is None:
                return combo
            self.rejections.append(RejectedCandidate(combo=combo, reason=reason))
        raise RuntimeError("FullAgentStrategy exhausted candidate stream")

    def _candidate_stream(
        self,
        history: list[TrialOutcome],
        memory: ExperienceMemory,
        rng: random.Random,
    ):
        del memory
        yield from self._warmup_candidates()
        yield self.llm.propose(history, rng)
        yield from self._local_mutation_candidates(history)
        yield from self._guided_interaction_candidates(history)
        yield from self._random_candidates(rng)

    def _warmup_candidates(self):
        yield frozenset({"-O3"})
        yield frozenset({"-O3", "-funroll-loops"})

    def _guided_interaction_candidates(self, history: list[TrialOutcome]):
        center = self._best_successful_combo(history)
        memory = ExperienceMemory.from_history(history)
        suspects = memory.near_miss_additions(
            center=center,
            max_score_drop=self.interaction_max_score_drop,
            limit=self.interaction_suspect_limit,
        )
        for first, second in itertools.combinations(suspects, 2):
            yield frozenset((*center, first, second))

    def _local_mutation_candidates(self, history: list[TrialOutcome]):
        center = self._best_successful_combo(history)
        for raw in tuple(sorted(raw_options(self.options))):
            if raw in center:
                yield frozenset(value for value in center if value != raw)
            else:
                yield frozenset((*center, raw))

    def _random_candidates(self, rng: random.Random):
        raws = tuple(raw_options(self.options))
        for _ in range(self.max_random_fallbacks):
            combo = frozenset(raw for raw in raws if rng.random() < 0.35)
            if combo:
                yield combo

    def _best_successful_combo(
        self,
        history: list[TrialOutcome],
    ) -> frozenset[str]:
        successes = [trial for trial in history if trial.result.succeeded]
        if not successes:
            return frozenset()
        best = max(successes, key=lambda trial: trial.result.score or float("-inf"))
        return best.combo
