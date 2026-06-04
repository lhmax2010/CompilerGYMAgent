# Phase 05 Review Notes

## Subtask 5.1 - env marker refinement + pid-independent lease_id

- [x] `lease_id` is generated before `Popen` and does not depend on pid.
- [x] Child env includes `AGENT_SESSION_ID`, `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and `AGENT_PROCESS_ROLE`.
- [x] `ProcessRecord` keeps `trial_id` / `lease_id` optional for legacy compatibility.
- [x] `ProcessLease` persists `lease_id` and validates record/lease consistency.
- [x] Cleaner env scan filters new records to trial + lease granularity.
- [x] Cleaner env scan remains backward-compatible for legacy session-only records.
- [x] Cleaner env marker read remains single-shot with no retry.
- [x] Targeted process tests pass.
- [x] Full test suite passes.

## Subtask 5.2 - fake_gbs mock harness

- [x] fake_gbs compile/benchmark uses real `process_runner` subprocesses.
- [x] Subprocesses create process leases and expose pid/pgid/env marker payloads.
- [x] Compile success writes a real artifact and artifact hash.
- [x] Benchmark consumes artifact and verifies artifact hash.
- [x] Failure modes cover invalid option, timeout, crash signal, OOM-like exit, artifact missing, and score parse failure.
- [x] Timeout path uses `cleanup_process_lease()` and killpg.
- [x] Noise profiles include gaussian, right_skewed, and bursty.
- [x] Bursty mode uses a seeded Markov state machine and has 100-round pressure coverage.
- [x] Same seed replays score/noise state sequence.
- [x] Targeted and full test suites pass.

## Subtask 5.5a - failure/result schema skeleton

- [x] `FailureClassification` defaults to `route=unknown` and `write_failed_combos=False`.
- [x] Model validation rejects `write_failed_combos=True` unless `route=option_related` and `confidence=HIGH`.
- [x] Failure category, route, confidence, run phase, and objective direction are closed schema values, not arbitrary strings.
- [x] `EvidenceLine` includes log_ref, text, and pattern_id for traceable evidence.
- [x] `RunLevelRecord` requires `objective_direction`.
- [x] `RunLevelRecord` includes run_id, run_index, combo_hash, metric metadata, artifact verification, score_source_ref, pair_key, failure_classification, and summary_hint.
- [x] Successful runs require a score and reject failure metadata.
- [x] Invalid runs require invalid_reason and failure_classification.
- [x] `score_parse_failed` invalid runs require score_source_ref.
- [x] Subtask remains schema-only; no classifier rule matching or log parsing is implemented.
- [x] Targeted, adjacent, and full test suites pass.

## Subtask 5.3 - compile skill

- [x] `compile_candidate()` consumes fake_gbs through the real process-backed harness.
- [x] Workspace protection wraps compile with snapshot, spec backup, spec injection, spec restore, and workspace verify.
- [x] fake_gbs `on_spawn` hook lets compile skill write canonical trace/checkpoint state immediately after lease creation.
- [x] `process_started` trace contains full ProcessRecord and ProcessLease payloads.
- [x] Checkpoint operation ledger receives compile process_refs and does not write deprecated `current_trial.process`.
- [x] Successful compile records artifact_ref and artifact_hash.
- [x] Trace failure after lease creation kills the process group and terminalizes the lease.
- [x] Failure classifications use 5.5a schema and keep `write_failed_combos=False`.
- [x] Targeted, adjacent, and full test suites pass.
