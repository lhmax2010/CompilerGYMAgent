# Self-review: 7.0-contracts code deliverables

Verdict: ready for external review after full Python 3.10 validation.

Checks performed:
- 08a verdict and pair_quality gates remain in _statistical_verdict/_pair_quality; the patch adds fields/helpers but does not relax those gates.
- p_value is diagnostic-only and computed from the same bootstrap distribution used for percentile CI.
- family_screen is batch-level and uses m=len(results), with direction filtered by verdict==significant_improvement.
- can_accept takes is_family_screened as an input and returns AcceptDecision reason codes.
- MeasurementPlan owns candidate/family/baseline identity; RunLevelRecord only gains optional measurement_plan_id and run-specific provenance fields.
- compute_combo_hash is shared through agent.candidate_identity; no persisted combo_hash data was found outside docs/dev_memory/tests.

Validation:
- focused contracts: 284 passed in 1.23s
- adjacent compile/benchmark/trace: 76 passed in 3.28s
- full tests: 703 passed in 8.54s
- git diff --check: passed
