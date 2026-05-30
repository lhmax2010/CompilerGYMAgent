# Spike 05.5 - Integration Feasibility Mock Spike

This directory is reserved for the mock-only integration feasibility spike.

Rules:

- Keep spike code isolated from production `src/agent/`.
- Do not call real gbs.
- Do not spawn subprocesses for process management.
- Do not touch workspace protection, spec files, LangGraph, or real LLM APIs.
- Use deterministic mock components and fixed seeds where possible.

Primary findings document:

- `dev_memory/spikes/05.5_integration_feasibility_findings.md`

Core question:

Can the automated decision loop (candidate engine + constraint layer +
experience memory + exploration schedule) beat naive baselines, learn
second-order option interactions, and recover from poor LLM proposals, noisy
benchmarks, bad experience, duplicate pressure, and crash/resume?

## Current Contents

- `option_ir.py`: minimal `OptionV0` IR and default option catalog.
- `objective.py`: synthetic objective with a known second-order optimum.
- `mock_llm.py`: deterministic controllable fake LLM with good/poor quality.
- `strategies.py`: random, LLM-only, and local-mutation baselines plus trial
  outcome record.
- `full_agent.py`: spike-local full-agent strategy with lightweight
  constraints, memory, schedule, and false-positive suspicion counter.
- `runner.py`: seeded plain Python strategy runner.
- `tests/`: spike-only pytest coverage.

## Test Command

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```
