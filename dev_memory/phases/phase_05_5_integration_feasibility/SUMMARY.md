# Phase 05.5 - Integration Feasibility Mock Spike

This phase is a mock-only spike. It is intentionally isolated from production
`src/agent/` code and can run in parallel with Phase 06.

## Subtask 05.5.1 - Synthetic Objective / OptionV0 IR / Random Runner

Implemented the foundation for the integration feasibility spike:

- `OptionV0` minimal IR and default option catalog.
- `SyntheticObjective` with:
  - known optimum `{-O3, -funroll-loops, -fA, -fB}`,
  - conflict failure for `-O3 + -Os`,
  - second-order interaction where `-fA`/`-fB` are bad alone and strong together,
  - `fp_sensitive` penalty for `-ffast-math`,
  - benchmark noise and transient infra failure knobs.
- `ScoreResult`, `TrialOutcome`, `RunResult`.
- `RandomStrategy` baseline.
- Seeded `run_strategy()` loop.

The subtask does not attempt to prove the full agent beats baselines yet. It
only establishes a fair, inspectable mock world and one naive baseline that
later subtasks can compare against.

### Validation

- Spike tests: 7 passed
- Production regression suite: 451 passed

### External Review

Claude verdict: Approve.

The synthetic objective passed the fairness audit: the known optimum is unique,
the second-order trap is effective, random has a plausible but not dominant
chance to find the optimum, and no production `src/agent` files changed.

Follow-up for 05.5.2: when adding `LocalMutationStrategy`, confirm it remains
stuck in the local optimum for strategy reasons rather than escaping only due to
noise luck.

## Subtask 05.5.2 - MockLLM / LLMOnly / LocalMutation Baselines

Added two more baselines and the controllable fake LLM needed for later
comparisons:

- `MockLLM`:
  - `quality="good"` emits deterministic catalog-bounded plausible proposals
    and can propose the known optimum.
  - `quality="poor"` emits conflicts, unknown options, and repeats.
- `LLMOnlyStrategy`:
  - trusts mock LLM output without constraints, dedup, or memory.
- `LocalMutationStrategy`:
  - one-flip hill climber around the best successful combo.
  - reaches `{-O3, -funroll-loops}` on the noiseless objective.
  - evaluates `-fA` and `-fB` as individually worse.
  - never proposes the `-fA`/`-fB` pair.
- `RunResult` now reports unique combo count and duplicate trial rate.

### Validation

- Spike tests: 14 passed
- Production regression suite: 451 passed

### External Review

Claude verdict: Approve.

The local-mutation baseline was independently verified to get stuck at
`{-O3, -funroll-loops}` across repeated seeds, giving the spike a stable
second-order-interaction contrast. Poor LLM emits realistic bad behavior
(conflicts, hallucinated flags, and repeats), while good LLM can directly
propose the known optimum.

Follow-up for 05.5.3: report full-agent comparisons by scenario. In the good
LLM setting, compare trial efficiency against LLM-only; in the poor LLM setting,
compare robustness and best-score recovery.
