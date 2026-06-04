# Self Review - Phase 05 / Subtask 5.5a

## Scope

This subtask adds schema-only result contracts for compile/benchmark skills. It intentionally defines models and invariants only; classifier rules and log pattern matching remain deferred to 5.5b.

## Checks

- `FailureClassification` defaults to `route=unknown` and `write_failed_combos=False`.
- `write_failed_combos=True` is structurally invalid unless the classification is `route=option_related` and `confidence=HIGH`.
- Failure category, route, confidence, run phase, and objective direction are closed values.
- Evidence lines preserve log_ref, text, and pattern_id.
- `RunLevelRecord` requires objective_direction.
- Successful run records require score and reject invalid/failure metadata.
- Invalid run records require invalid_reason and failure_classification.
- `score_parse_failed` records require score_source_ref.
- Artifact verification cannot be true without artifact_hash.
- exit_code and signal are mutually exclusive.
- Timestamps are UTC-normalized and ended_at must not precede started_at.
- The module contains no classifier pattern matching or log parser rules.
- Targeted, adjacent, and full test suites pass.

## Result

No known findings. The schema-level failed-combo write gate is enforced before classifier rules exist.

