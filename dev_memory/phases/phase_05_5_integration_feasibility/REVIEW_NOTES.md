# Phase 05.5 - Review Notes

## Subtask 05.5.1 - Synthetic Objective / OptionV0 IR / Random Runner

Self-review checklist:

- [x] Spike code lives under `spikes/05.5_integration_feasibility/`.
- [x] No production `src/agent/` files changed.
- [x] `OptionV0` is minimal: `option_id`, `raw`, `conflicts`, `requires`.
- [x] Catalog validation checks unique IDs/raw strings and known conflict/requirement references.
- [x] `SyntheticObjective` has a known exact optimum.
- [x] `-fA` and `-fB` are individually harmful but jointly valuable.
- [x] Extra options are penalized so random supersets do not tie the known optimum.
- [x] `-O3 + -Os` compiles to a mock `compile_failed` outcome.
- [x] `fp_sensitive` module penalizes `-ffast-math`.
- [x] `RandomStrategy` is intentionally naive and may propose conflicts.
- [x] Runner produces deterministic histories for fixed seeds.
- [x] Spike tests and production regression tests passed.

Reviewer focus:

- Confirm the synthetic objective is not accidentally too easy for greedy/local
  strategies.
- Confirm the known optimum is exact rather than tied by random supersets.
- Confirm allowing RandomStrategy to propose conflicts is acceptable for the
  baseline before the constraint layer lands.
- Confirm the first subtask's narrow scope is enough foundation for later
  LLM-only/local-mutation/full-agent strategy comparisons.

### External Review

Claude verdict: Approve.

Findings: no Critical / High / Medium findings. Low-1 noted that `-fA`/`-fB`
single-option penalty (-1) is inside the default benchmark noise
(`noise_sigma=2.0`). This is acceptable for now and should be re-checked when
the local-mutation baseline lands, because local mutation must not escape the
local optimum only by noise luck.

Post-review validation:

- Spike tests: 7 passed
- Production regression suite: 451 passed
- Production `src/agent` changes: none
