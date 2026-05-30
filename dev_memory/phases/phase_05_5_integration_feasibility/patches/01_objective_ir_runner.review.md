# Self Review - Phase 05.5 / Subtask 05.5.1 Objective IR Runner

## Scope

This is spike code only. It does not touch production `src/agent/`, real gbs,
process management, workspace protection, LangGraph, or real LLM APIs.

## Checks

- `OptionV0` is intentionally minimal and serializable.
- The default option catalog validates unique ids/raw strings and known
  conflict/requirement references.
- `SyntheticObjective` has an exact known optimum:
  `{-O3, -funroll-loops, -fA, -fB}`.
- `-fA` and `-fB` are each harmful alone but jointly strong.
- Extra options are penalized so random supersets cannot tie the optimum.
- `-O3 + -Os` returns `compile_failed`.
- `-ffast-math` is module-sensitive and bad for `fp_sensitive`.
- `RandomStrategy` is intentionally naive and can propose invalid/conflicting
  combos; later constraint-layer subtasks should improve on this.
- `run_strategy()` produces deterministic histories for fixed seeds.
- Spike tests and production regression tests passed.

## Reviewer Focus

- Confirm the objective is not too easy for greedy/local strategies.
- Confirm the optimum is exact, not tied by supersets.
- Confirm RandomStrategy should stay naive before the constraint-layer subtask.
- Confirm this is the right first slice before adding LLM-only/local-mutation
  and full-agent strategies.

## Validation

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
# 7 passed in 0.01s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.63s
```
