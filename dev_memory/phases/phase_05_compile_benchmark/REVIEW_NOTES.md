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
- [x] Failure classifications use 5.5a schema; 5.5b owns classifier routing and failed-combo write decisions.
- [x] Targeted, adjacent, and full test suites pass.

## Subtask 5.4 - benchmark skill

- [x] `benchmark_candidate()` consumes fake_gbs through the real process-backed harness.
- [x] Artifact hash is verified before spawning benchmark runs.
- [x] Artifact mismatch emits an invalid `artifact_invalid` run-level record and spawns no benchmark process.
- [x] Warmup and measured phases are explicit, with stable measured run_index ordering.
- [x] Returned records are 5.5a `RunLevelRecord` objects and include objective_direction, artifact verification, score_source_ref, env snapshot, pair_key, and summary_hint.
- [x] `score_parse_failed` is modeled as an invalid run with `FailureClassification`, not success with score=None.
- [x] `process_started` trace contains full ProcessRecord and ProcessLease payloads.
- [x] Checkpoint operation ledger receives benchmark process_refs and does not write deprecated `current_trial.process`.
- [x] Trace failure after lease creation kills the process group and terminalizes the lease through fake_gbs cleanup.
- [x] Outlier/statistical judgment is not implemented in Phase 05 and remains deferred to Phase 08.
- [x] Targeted, adjacent, and full test suites pass.

## Subtask 5.5b - failure classifier rules + routing tests

- [x] Compile and benchmark skills consume a shared classifier module.
- [x] invalid_option maps to option_related with affected_options extraction.
- [x] option_conflict maps to option_related and writes failed_combos only when HIGH confidence.
- [x] environment_related classifications never write failed_combos.
- [x] disk full, OOM, timeout, network, and permission patterns route to environment_related.
- [x] High-confidence environment evidence overrides option matches to prevent candidate-memory pollution.
- [x] Unmatched failures default to unknown/LOW/write_failed_combos=False.
- [x] matched_rule_id and classifier_version are populated.
- [x] score_parse_failed is classified as a first-class benchmark failure.
- [x] Targeted, adjacent, and full test suites pass.

## Phase Closeout

- [x] Phase 05 all planned subtasks approved.
- [x] Compile and benchmark skills both use process-backed fake_gbs rather than
  function-level mocks.
- [x] Compile and benchmark skills write operation-ledger process refs, not the
  deprecated `current_trial.process` authority.
- [x] Benchmark outputs run-level records with warmup/measured separation for
  Phase 08.
- [x] Failure classification has schema-level and rule-level guards against
  poisoning candidate memory.
- [x] clean trace CLI keep-days tests use relative timestamps and include a
  future-date regression.
- [x] Final full test suite passes at 595 tests.
- [x] Phase 05 is removed from `planned_phases` and added to `completed_phases`;
  Phase 05.5 remains planned/done as the completed spike.
