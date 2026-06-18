# Phase 7.0-contracts UT Results

## Focused Contracts

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_result_schema.py tests/test_stats_core.py tests/test_fs_memory.py tests/test_trace_memory.py -q`
- Result:
  `293 passed in 1.28s`
- Coverage:
  - canonical hash equivalence, deduplication, value-flag distinction, shared
    result_schema/fs_memory entry points, and TrialRecord validation;
  - p_value and relative CI propagation;
  - family_screen full-family BH and lower_is_better direction handling;
  - RunLevelRecord optional provenance;
  - MeasurementPlan schema and trace emission;
  - AcceptDecision reason codes.
  - fail-safe canonicalization for unmodelled bool/override flags;
  - provenance default rejection and same-plan/source/benchmark/objective checks.

## Adjacent Regression

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_compile_skill.py tests/test_benchmark_skill.py tests/test_fake_gbs.py tests/test_error_analyzer.py tests/test_trace_session.py -q`
- Result:
  `76 passed in 3.28s`

## Full Suite

- Command:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
- Result:
  `712 passed in 8.63s`

## Adversarial Probes

- `compute_combo_hash(["-fstrict-aliasing", "-fno-strict-aliasing"])` and the
  reverse order both reject with `ValueError`.
- `compute_combo_hash(["-flto", "-flto=thin"])` rejects because the bool and
  value forms share the `flto` key.
- `compute_combo_hash(["-flto", "-funroll-loops"])` still matches the reversed
  whitelist order.
- A hand-built significant `StatisticalResult` with omitted
  `provenance_complete` defaults to `False` and `can_accept()` returns
  `rejected_incomplete_provenance`.
- Baseline/candidate records with different `measurement_plan_id` produce
  `provenance_complete=False`.

## Static / Metadata

- `git diff --check` -> passed.
- YAML parse smoke for `dev_memory/ROADMAP.yaml`,
  `dev_memory/CURRENT_PHASE.yaml`, and
  `dev_memory/phases/phase_7_0_contracts/CHECKLIST.yaml` -> passed.
- Greenfield identity check:
  no persisted `combo_hash` data outside docs/dev_memory/tests.
