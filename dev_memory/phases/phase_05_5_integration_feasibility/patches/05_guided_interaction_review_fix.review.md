# Self Review - Phase 05.5 / Subtask 05.5.4 Guided Interaction Review Fix

## Scope

This is a review-fix for 05.5.4 High-1. It keeps all changes inside the spike
directory plus dev_memory records. No production `src/agent` files are touched.

## Checks

- Random fallback cannot build multi-option combinations anymore.
- Guided interaction can find the second-order optimum with random fallback
  disabled.
- Random fallback alone cannot find the second-order optimum when guided
  interaction is disabled.
- Near-miss suspects exclude neutral noise options via a minimum score-drop
  bound.
- Candidate exhaustion is represented in `RunResult` and does not erase an
  already-found optimum.
- The 2x2 ablation is explicit in tests.

## Reviewer Focus

- Confirm the 2x2 ablation now isolates guided interaction's independent
  contribution.
- Confirm the random fallback is no longer a disguised brute-force combo search.
- Confirm the near-miss band is honest: `-fA`/`-fB` are included, neutral
  options are excluded.

## Validation

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
# 25 passed in 0.04s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.61s
```
