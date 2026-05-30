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

## Subtask 05.5.2 - MockLLM / LLMOnly / LocalMutation Baselines

Self-review checklist:

- [x] Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- [x] No production `src/agent/` files changed.
- [x] `MockLLM(quality="good")` is deterministic and only emits catalog options.
- [x] `MockLLM(quality="poor")` emits conflicts, unknown options, and repeated shallow guesses.
- [x] `LLMOnlyStrategy` does not filter, dedup, or learn from history.
- [x] `LocalMutationStrategy` mutates exactly one option around the best successful combo.
- [x] Local mutation gets stuck at `{-O3, -funroll-loops}` on the noiseless objective.
- [x] Local mutation tries `-fA` and `-fB` individually and observes they are worse.
- [x] Local mutation never proposes the `-fA`/`-fB` pair in this baseline.
- [x] Spike tests and production regression tests passed.

Reviewer focus:

- Confirm `LLMOnlyStrategy` is intentionally weak enough to be a meaningful
  baseline, not a hidden full-agent implementation.
- Confirm `LocalMutationStrategy` is a fair local-search baseline and not
  artificially prevented from doing normal one-flip hill climbing.
- Confirm the local-mutation trap is strategy-caused, not noise-caused, because
  these tests use the noiseless objective.

### External Review

Claude verdict: Approve.

Findings: no Critical / High / Medium findings. Low-1 noted that the
good-quality `MockLLM` proposal pool includes the complete known optimum, so
good LLM-only can also find the best combo. This is acceptable, but the final
against-baseline report must split the comparison:

- good LLM: full agent should show better trial efficiency (lower duplicate /
  failure budget burn), not necessarily higher best score;
- poor LLM: full agent should show robustness by using fallback exploration to
  find what LLM-only misses.

Post-review validation:

- Spike tests: 14 passed
- Production regression suite: 451 passed
- Production `src/agent` changes: none

## Subtask 05.5.3 - FullAgentStrategy Core

Self-review checklist:

- [x] Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- [x] No production `src/agent/` files changed.
- [x] `FullAgentStrategy` is spike-local and intentionally plain Python.
- [x] `ConstraintLayer` rejects duplicates, unknown options, conflicts, known failed subsets, and soft-blocked candidates before trial execution.
- [x] `ExperienceMemory` derives tried combos, successes, and failed subsets from prior `TrialOutcome` history.
- [x] Candidate schedule includes warmup, LLM proposal, pair-jump exploration, local mutation, random fallback, and deterministic enumeration.
- [x] Pair-jump exploration is generic over option pairs, not hard-coded to `-fA`/`-fB`.
- [x] Poor LLM conflicts and unknown options do not reach `SyntheticObjective.evaluate`.
- [x] Poor LLM scenario reaches the second-order optimum.
- [x] Good LLM scenario compares trial efficiency rather than pretending LLM-only cannot find the optimum.
- [x] Suspicion counter can force a soft-blocked combo after repeated rejection.
- [x] Spike tests and production regression tests passed.

Reviewer focus:

- Confirm full-agent success is not just hard-coding the known optimum; the
  pair-jump generator should be judged as a generic two-option exploration
  fallback.
- Confirm against-baseline reporting stays split by scenario:
  good LLM = efficiency, poor LLM = robustness / best-score recovery.
- Confirm rejecting duplicates/conflicts/unknowns before execution is a fair
  simulation of constraint-layer behavior, not silently hiding failed trials.
- Confirm the suspicion counter is enough foundation for the later false
  positive recovery test, even though this subtask does not yet implement full
  bad-experience canary behavior.

### External Review

Claude verdict: Approve with follow-up.

Findings:

- Med-1: ablation showed the full agent's second-order optimum discovery is
  mainly driven by `_enumerated_candidates`, not by `_pair_jump_candidates` or
  learned interaction exploration. Disabling pair-jump still found the optimum
  in repeated seeds; disabling random/enumerated fallback reduced discovery to
  zero. This means the current "learns interaction" result does not yet
  extrapolate to real-scale option spaces.
- Low-1: pair-jump itself enumerates all missing option pairs. It is better
  than full size-4 enumeration at this toy scale, but still not the
  experience-guided interaction search Phase 07 will need.

Post-review decision:

- Take path (a): remove or sharply limit brute enumeration in the next subtask
  so the spike tests scalable interaction exploration instead of small-space
  brute force.
- Record the ablation honestly in findings.

Post-review validation:

- Spike tests: 21 passed
- Production regression suite: 451 passed
- Production `src/agent` changes: none

## Subtask 05.5.4 - Guided Interaction Follow-up

Self-review checklist:

- [x] Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- [x] No production `src/agent/` files changed.
- [x] Deterministic size-1..4 enumeration fallback is removed.
- [x] Interaction exploration now depends on observed near-miss single additions.
- [x] Near-miss suspect count is bounded by `interaction_suspect_limit`.
- [x] With random fallback disabled, full agent still finds the second-order optimum.
- [x] With guided interaction disabled and random fallback disabled, full agent no longer finds the second-order optimum.
- [x] Existing constraint, duplicate, and good/poor LLM efficiency tests still pass.
- [x] Spike tests and production regression tests passed.

Reviewer focus:

- Confirm the 05.5.3 Med-1 mechanism attribution is fixed: success should no
  longer be driven by deterministic enumeration.
- Confirm the guided interaction heuristic is still generic enough for a Phase
  07 path: it uses observed near-miss single additions rather than hard-coding
  `-fA` / `-fB`.
- Confirm the bounded suspect pair generation is a plausible spike proxy, not a
  hidden exhaustive search over the entire option catalog.
