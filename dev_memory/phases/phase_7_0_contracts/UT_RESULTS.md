# Phase 7.0-contracts UT Results

## Focused Contracts

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_result_schema.py tests/test_stats_core.py tests/test_fs_memory.py tests/test_trace_memory.py -q`
- Result:
  `284 passed in 1.23s`
- Coverage:
  - canonical hash equivalence, deduplication, value-flag distinction, shared
    result_schema/fs_memory entry points, and TrialRecord validation;
  - p_value and relative CI propagation;
  - family_screen full-family BH and lower_is_better direction handling;
  - RunLevelRecord optional provenance;
  - MeasurementPlan schema and trace emission;
  - AcceptDecision reason codes.

## Adjacent Regression

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_compile_skill.py tests/test_benchmark_skill.py tests/test_fake_gbs.py tests/test_error_analyzer.py tests/test_trace_session.py -q`
- Result:
  `76 passed in 3.28s`

## Full Suite

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
- Result:
  `703 passed in 8.54s`

## Static / Metadata

- `git diff --check` -> passed.
- YAML parse smoke for `dev_memory/ROADMAP.yaml`,
  `dev_memory/CURRENT_PHASE.yaml`, and
  `dev_memory/phases/phase_7_0_contracts/CHECKLIST.yaml` -> passed.
- Greenfield identity check:
  no persisted `combo_hash` data outside docs/dev_memory/tests.
