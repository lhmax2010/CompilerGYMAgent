# Phase 7.0-contracts Summary

Phase 7.0-contracts implements the seven code deliverables frozen by
`doc/PHASE_7.0_CONTRACTS_DRAFT.md` v4. The goal is to turn the reviewed 07 input
contracts into concrete schema/statistics/identity/trace APIs before the later
7.0 scaling spike and Phase 07 candidate engine work.

Implemented scope so far:

- Split `ROADMAP.yaml` Phase 7.0 into `7.0-contracts` and `7.0-spike`.
- Added a shared candidate identity helper for commutative-only canonicalization
  and unified both `compute_combo_hash` entry points.
- Added bootstrap-derived `p_value` as diagnostic output without changing 08a
  verdict or pair-quality gates.
- Added relative CI percentage fields for practical-threshold consumers.
- Added `family_screen`, `is_decision_grade`, `AcceptDecision`, and
  `can_accept` helpers.
- Extended `RunLevelRecord` with optional measurement provenance fields.
- Added `MeasurementPlan` and trace-writer support for
  `measurement_plan_created` events.

Key boundary:

- The additive fields and helpers are consumer contract surface for 07. They do
  not relax 08a's conservative statistical verdict gates.

Validation so far:

- Focused contract/schema/stats/fs/trace tests:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_result_schema.py tests/test_stats_core.py tests/test_fs_memory.py tests/test_trace_memory.py -q`
  -> 284 passed in 1.23s.
- Adjacent compile/benchmark/fake_gbs/error/trace-session tests:
  `uv run --python 3.10 --system-certs --extra dev pytest tests/test_compile_skill.py tests/test_benchmark_skill.py tests/test_fake_gbs.py tests/test_error_analyzer.py tests/test_trace_session.py -q`
  -> 76 passed in 3.28s.

Full-suite validation:

- `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  -> 712 passed in 8.63s.

Post-review fail-open fixes:

- Candidate canonicalization now uses an explicit commutative whitelist. Unknown
  bool/override flags such as `-fstrict-aliasing` / `-fno-strict-aliasing`
  reject instead of being sorted into one candidate identity.
- `StatisticalResult.provenance_complete` defaults to `False`, so hand-built or
  deserialized significant results without explicit provenance fail safe at
  `can_accept()`.
- `is_decision_grade()` and the schema validator share one private
  decision-grade predicate.
- `_records_have_complete_provenance()` now requires
  `measurement_plan_id`/`source_commit`/`benchmark_id`/`objective_id` to be
  present and identical across the comparison.
