# Phase 05.5 - UT Results

## 2026-05-30 - Subtask 05.5.1 Objective / IR / Runner Baseline

Environment:

- Runner: local `.venv`
- Python: `.venv/bin/python`
- OS: Linux workspace

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
7 passed in 0.01s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.63s
```

### Post-review Ubuntu/Linux Validation

Claude review verdict: Approve.

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
7 passed in 0.01s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.63s
```

## 2026-05-30 - Subtask 05.5.2 MockLLM / LLMOnly / LocalMutation Baselines

Environment:

- Runner: local `.venv`
- Python: `.venv/bin/python`
- OS: Linux workspace

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
14 passed in 0.02s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.64s
```

### Post-review Ubuntu/Linux Validation

Claude review verdict: Approve.

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
14 passed in 0.02s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.62s
```

## 2026-05-30 - Subtask 05.5.3 FullAgentStrategy Core

Environment:

- Runner: local `.venv`
- Python: `.venv/bin/python`
- OS: Linux workspace

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
21 passed in 0.04s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.62s
```

Probe:

```text
good: full_hits=10/10, full_score_min=120.0, llm_score_max=120.0, full_dup_max=0.0, llm_dup_min=0.85
poor: full_hits=10/10, full_score_min=120.0, llm_score_max=102.5, full_dup_max=0.0, llm_dup_min=0.875
local: best={-O3, -funroll-loops}, score=108.0
```

### Post-review Ubuntu/Linux Validation

Claude review verdict: Approve with follow-up.

Commands:

```bash
.venv/bin/python -m pytest spikes/05.5_integration_feasibility/tests -q
```

Result:

```text
21 passed in 0.04s
```

```bash
.venv/bin/python -m pytest tests/ -q
```

Result:

```text
451 passed in 1.60s
```
