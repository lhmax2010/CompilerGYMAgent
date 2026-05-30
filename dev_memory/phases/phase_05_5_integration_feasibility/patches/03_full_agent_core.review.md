# Self Review - Phase 05.5 / Subtask 05.5.3 FullAgent Core

## Scope

This subtask adds the spike-local full-agent decision core: lightweight
constraints, experience memory, and a candidate schedule. It does not implement
real gbs, real LLM APIs, process management, workspace protection, LangGraph, or
production `src/agent` behavior.

## Checks

- Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- No production `src/agent/` files changed.
- `FullAgentStrategy` is a plain Python spike strategy.
- `ConstraintLayer` rejects duplicates, unknown options, conflicts, known
  failed subsets, and soft-blocked candidates before execution.
- `ExperienceMemory` is derived only from trial history.
- Candidate schedule is explicit:
  warmup -> LLM -> pair-jump -> local mutation -> random -> enumeration.
- Pair-jump exploration is generic over option pairs, not hard-coded to
  `-fA`/`-fB`.
- Poor LLM conflicts and unknown options do not produce compile-failed trials.
- Poor LLM scenario reaches the known second-order optimum.
- Good LLM scenario compares efficiency: full agent has duplicate rate 0.0
  while LLM-only repeats heavily.
- Suspicion counter provides the first false-positive recovery hook.

## Reviewer Focus

- Confirm full-agent success is not just a hard-coded answer path.
- Confirm good/poor LLM comparisons are reported separately:
  good LLM = trial efficiency, poor LLM = robustness and best-score recovery.
- Confirm constraint rejections before execution are fair for this spike and do
  not hide actual objective failures that should consume budget.
- Confirm the suspicion counter is a reasonable minimal foundation for the
  later bad-experience / Canary test.

## Validation

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
# 21 passed in 0.04s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.62s
```
