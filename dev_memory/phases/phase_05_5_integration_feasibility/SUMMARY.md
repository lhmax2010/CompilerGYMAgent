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
