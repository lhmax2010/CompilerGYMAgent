# Phase 7.0-contracts Review Notes

## Self-review focus

- Verify delivery 1 is the only identity semantic change and remains greenfield.
- Verify deliveries 2-5 are additive and do not modify 08a verdict/pair_quality
  gates.
- Verify p_value uses the same bootstrap distribution as CI.
- Verify `family_screen` uses full pre-registered family size as BH denominator
  and filters by `verdict == significant_improvement`.
- Verify `can_accept` is per-candidate and takes `is_family_screened` as input
  rather than recomputing family-level BH.

## Current observations

- `compute_combo_hash` in both `result_schema.py` and `fs_memory.py` delegates
  to `agent.candidate_identity.compute_canonical_combo_hash`.
- `compare_run_records()` now fills p_value, relative CI, and provenance
  completeness, but the existing verdict and pair-quality gate function is
  unchanged.
- MeasurementPlan trace support is implemented as an open
  `measurement_plan_created` event via `TraceSessionWriter`.
- Patch artifacts are under
  `dev_memory/phases/phase_7_0_contracts/patches/01_contract_code_deliverables.*`.
