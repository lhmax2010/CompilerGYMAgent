# Self Review - Phase 05.5 / Subtask 05.5.4 Guided Interaction

## Scope

This subtask is a follow-up to 05.5.3 Med-1. It changes only spike code and
dev_memory records. It does not touch production `src/agent`.

## Checks

- Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- No production `src/agent/` files changed.
- Deterministic `_enumerated_candidates` fallback is removed.
- Interaction discovery now uses observed near-miss single additions.
- Near-miss suspect count is bounded.
- Full agent finds the second-order optimum with poor LLM and random fallback
  disabled.
- Disabling guided interaction under the same conditions prevents discovery.
- Good/poor LLM scenario split remains valid.

## Reviewer Focus

- Confirm this resolves the 05.5.3 mechanism attribution problem.
- Confirm success is not just hidden brute-force enumeration under a new name.
- Confirm the bounded near-miss heuristic is a plausible Phase 07 candidate
  direction, while still honest about being a spike.

## Validation

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
# 23 passed in 0.04s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.66s
```
