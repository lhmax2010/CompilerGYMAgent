# Self Review - Phase 05.5 / Subtask 05.5.2 LLM And Local Baselines

## Scope

This subtask adds two baseline strategy families for the 05.5 mock-only spike:
`LLMOnlyStrategy` and `LocalMutationStrategy`. It does not implement the full
agent, constraint layer, experience memory, or schedule logic.

## Checks

- Spike code remains isolated under `spikes/05.5_integration_feasibility/`.
- No production `src/agent/` files changed.
- `MockLLM(quality="good")` is deterministic and emits only known catalog
  options.
- `MockLLM(quality="poor")` emits conflicts, unknown flags, and repeats.
- `LLMOnlyStrategy` does not filter or learn; it is intentionally weak.
- `LocalMutationStrategy` performs normal one-flip local search around the best
  successful combo.
- On the noiseless objective, local mutation reaches `{-O3, -funroll-loops}`
  and gets stuck there.
- Local mutation evaluates single `-fA` and `-fB` additions as worse neighbors.
- Local mutation never proposes the `-fA`/`-fB` pair, giving later full-agent
  strategy a meaningful second-order comparison target.

## Reviewer Focus

- Confirm LLM-only is not secretly doing dedup/constraints/memory.
- Confirm local mutation is a fair local-search baseline rather than
  artificially crippled.
- Confirm the local-mutation trap is strategy-caused on the noiseless objective,
  not noise luck.

## Validation

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
# 14 passed in 0.02s
```

```bash
.venv/bin/python -m pytest tests/ -q
# 451 passed in 1.64s
```
