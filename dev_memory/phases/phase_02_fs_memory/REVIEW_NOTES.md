# Phase 02 Review Notes

## Subtask 2.1 - shared atomic YAML writer and namespace FS layout

- timestamp_utc: 2026-05-08T07:10:09Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/init.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] Implementation matches REQUIREMENTS.md section 4.2.3 directory layout and section 4.7.5 atomic write semantics.
- [x] Error handling covers serialization failure, directory target refusal, non-mapping data, and pre-existing temp-file non-clobbering.
- [x] Trace events are not applicable to this subtask; Phase 03 owns `trace/events.jsonl`.
- [x] `.initialized` now uses shared `atomic_write_yaml` instead of a private direct YAML writer.
- [x] User-readable SoT principle is preserved; generated YAML avoids anchors and supports Unicode text.
- [x] No SQLite/cache data is introduced as canonical state.
- [x] Namespace layout creation does not pre-create empty canonical files like `checkpoint.yaml` or `events.jsonl`.
- [x] v1 Linux/Ubuntu parent directory fsync uses `os.O_DIRECTORY` when available; Windows development hosts skip that branch.
- [x] Paths come from `ProjectNamespace` and `AgentConfig`, not hard-coded caller cwd assumptions.
- [x] Imported prompt quoting and hash field exclusion are outside Subtask 2.1 scope.

Findings:
- No blocking issues found.
- Implementation choice recorded in DECISIONS.md: promote atomic YAML writing to FS-Memory shared utility.
- Implementation choice recorded in DECISIONS.md: `NamespaceLayout.ensure_directories()` creates directories only, not empty SoT files.

## Subtask 2.1 - external review

- timestamp_utc: 2026-05-08T07:41:20Z
- reviewer: Claude
- verdict: Approve
- independently_verified:
  - `pytest` full suite: 163 passed, 0 failed
  - 11 additional probes covering symlink target behavior, parent fsync failure semantics, alias suppression, and failure-conservative paths

Findings:
- No Critical, High, or Medium issues.
- Low/Info deferred follow-ups:
  - Symlink targets are replaced as path entries by `os.replace`; this should be documented or covered by a contract test if callers might use symlinked SoT files.
  - Parent-directory fsync can fail after `os.replace` succeeds; callers should treat the write result as unknown and retry/inspect if this happens.
  - NamespaceLayout can gain experience trust-level directories, learned suggestions, baseline history, and environment active helpers when their owning writers are implemented.
  - Workspace-level layout helpers can wait for modules that own shared/kg/trash/import/export directories.
  - Optional write-size caps can be revisited when concrete SoT writer schemas define read caps.

Review conclusion:
- Subtask 2.1 is approved and can proceed to Subtask 2.2.

## Subtask 2.2 - TrialRecord schema, integrity hash, and immutable writer

- timestamp_utc: 2026-05-08T08:16:42Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] `TrialRecord` covers the documented fields from REQUIREMENTS.md section 4.2.6.
- [x] Outcome, mode, candidate source, schedule slot, bench level, objective direction, bootstrap mode, cleanup status, and canary validation result are strict enums.
- [x] `combo_hash` is recomputed from the canonical combo list and mismatches are rejected.
- [x] Successful trials require `score`; canary mode requires a `canary` block.
- [x] Trial timestamps are UTC timezone-aware ISO 8601 strings.
- [x] Trial `namespace` is a safe 5-segment namespace string.
- [x] `integrity.payload_hash` excludes the `integrity` block and uses sorted canonical YAML so mapping insertion order cannot change the hash.
- [x] `write_trial_record` derives `integrity`, writes through shared `atomic_write_yaml`, and refuses an existing trial path.
- [x] `write_trial_record` checks that the record namespace matches the target `NamespaceLayout`.
- [x] Trial YAML path uses the completion timestamp month: `trials/data/YYYY-MM/trial_<trial_id>.yaml`.
- [x] No running trial state is stored in trial YAML; checkpoint and trace remain later subtasks.
- [x] Public exports in `src/agent/__init__.py` match the new FS-Memory trial APIs.
- [x] Targeted and full UT suites pass.

Findings:
- No blocking issues found.
- The immutable writer rejects existing files before calling `atomic_write_yaml`; future CLI/workflow callers must still hold `WorkspaceLock` to avoid concurrent same-trial writers.
- Trace event emission for `trial_yaml_written` is out of scope for Subtask 2.2 and remains owned by the trace/event subtask.

Deferred low-priority follow-ups:
- Add a contract test or decision for concurrent same-path trial writes once workflow-level `WorkspaceLock` wrapping is wired into the CLI.
- Add load-side integrity checking helpers when Subtask 2.4 implements SoT discovery over existing trials.
- Decide whether `TrialIntegrityError` should be used by a future strict assertion helper or removed if the later integrity command path uses a different exception.

Review conclusion:
- Subtask 2.2 is ready for external review.

## Subtask 2.2 - external review and review fixes

- timestamp_utc: 2026-05-08T08:34:49Z
- reviewer: Claude
- verdict: Approve with minor changes
- files_reviewed:
  - src/agent/fs_memory.py
  - tests/test_fs_memory.py
  - dev_memory/DECISIONS.md

External findings addressed:
- M-1: `write_trial_record` has an inherent exists-before-replace TOCTOU window if callers skip `WorkspaceLock`.
  - Fix: added a docstring stating callers must hold the section 4.15 workspace lock; added a DECISIONS.md entry making the lock boundary explicit.
- L-5: namespace mismatch was checked after computing integrity.
  - Fix: `write_trial_record` now validates `record.namespace` against `layout.namespace` before computing integrity.
- L-2: direct `compute_combo_hash` calls accepted surrounding whitespace and control characters.
  - Fix: direct helper calls now reject surrounding whitespace and C0/DEL control characters; added parametrized tests.

Additional clarification:
- The external review listed mapping-order and integrity false-negative tests as gaps, but Subtask 2.2 already had `test_payload_hash_is_independent_of_mapping_insertion_order` and an integrity-block tamper check. This review-fix adds a payload-field tamper test as extra coverage.

Post-fix checklist:
- [x] `write_trial_record` documents its `WorkspaceLock` precondition.
- [x] DECISIONS.md records why trial immutability is enforced at the workspace-lock boundary rather than with a second writer-specific lock.
- [x] Namespace mismatch fails before integrity hash computation.
- [x] Dirty direct combo-hash inputs are rejected.
- [x] Payload tampering makes `verify_trial_integrity` return false.
- [x] Targeted and full UT suites pass.

Review conclusion:
- Subtask 2.2 review fixes are ready for Ubuntu validation.

## Subtask 2.2 - external review-fix verification

- timestamp_utc: 2026-05-09T01:49:36Z
- reviewer: Claude
- verdict: Approve
- range: `aaed15c..993cad0`
- tests: 180 passed, 0 failed

Regression check:
- [x] M-1: `write_trial_record` documents the section 4.15 `WorkspaceLock` precondition and DECISIONS.md records the architectural boundary.
- [x] L-5: namespace mismatch validation happens before integrity hash computation.
- [x] L-2: `compute_combo_hash` rejects untrimmed and control-character options in direct calls.
- [x] Payload and integrity hash tamper detection remain correct.
- [x] Round-trip trial write/load/verify remains correct.

Remaining non-blocking follow-ups:
- Clarify the exact error message contract for whitespace-only combo options if needed.
- Add workflow-level concurrent write integration tests once CLI/workflow code wraps writers with `WorkspaceLock`.
- Decide globally whether NonEmptyStr silent stripping remains the intended forgiving UX.

Review conclusion:
- Subtask 2.2 is approved and can proceed to Subtask 2.3.

## Subtask 2.2 - Ubuntu validation

- timestamp_utc: 2026-05-09T03:16:47Z
- environment: Ubuntu/Linux, Python 3.11.15, `.venv`
- reporter: user on target Ubuntu server
- targeted_pytest: 27 passed in 0.13s
- full_pytest: 180 passed in 0.61s
- manual_probe:
  - trial path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/data/2026-04/trial_r12_t3.yaml`
  - hash_fields_excluded: `[integrity]`
  - verify_trial_integrity: true
  - tmp_files: `[]`

Conclusion:
- Subtask 2.2 review-fix is validated on Ubuntu and can proceed to Subtask 2.3.

## Subtask 2.3 - Checkpoint schema and canonical checkpoint YAML read/write

- timestamp_utc: 2026-05-09T03:35:10Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] `CheckpointState` covers the documented `state/checkpoint.yaml` fields from REQUIREMENTS.md sections 3.3.4, 4.2.6, and 4.11.2.
- [x] Checkpoint timestamps are UTC timezone-aware ISO 8601 strings and hand-edited unquoted YAML timestamps are accepted when PyYAML parses them as UTC datetimes.
- [x] `current_trial.current_stage` is restricted to documented lifecycle stages, including `score_aggregate`.
- [x] Active process stages (`compiling`, `benchmarking`) require process details.
- [x] Process identity validates `pid`, `pgid`, `create_time`, `cmdline_hash`, and `AGENT_SESSION_ID` marker.
- [x] Process session marker must match the checkpoint `session_id`.
- [x] `checkpoint_payload` emits user-readable JSON-mode data and omits `None` fields.
- [x] `write_checkpoint_state` writes through shared `atomic_write_yaml` and rejects layout namespace drift.
- [x] `load_checkpoint_state` rejects missing, empty, non-mapping, alias-bearing, non-UTF-8, oversized, unsafe-tag, and schema-invalid YAML.
- [x] `load_checkpoint_for_layout` rejects canonical state that claims a different namespace than its filesystem layout.
- [x] Public exports in `src/agent/__init__.py` match the new checkpoint APIs.
- [x] Targeted and full UT suites pass.

Findings:
- No blocking issues found.
- `write_checkpoint_state` documents the WorkspaceLock precondition because checkpoint YAML is mutable and overwritten during a session.
- Checkpoint does not include an integrity block by design; this is recorded in DECISIONS.md as mutable canonical recovery state paired with trace events.

Deferred low-priority follow-ups:
- Add resume-level tests that compare checkpoint state with LangGraph cache once the LangGraph cache adapter exists.
- Add trace/event correlation tests for checkpoint stage transitions when the trace writer is implemented.
- Decide whether checkpoint `explorer_state` should gain a stricter schema after the exploration planner data model is introduced.

Review conclusion:
- Subtask 2.3 is ready for external review.

## Subtask 2.3 - external review and review fixes

- timestamp_utc: 2026-05-11T05:54:15Z
- reviewer: Claude
- verdict: Approve with minor changes
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/workspace_lock.py
  - tests/test_fs_memory.py
  - tests/test_workspace_lock.py

External findings addressed:
- M-1: `CheckpointBest.score` used `Field(gt=0)`, which rejected valid zero or negative best scores.
  - Fix: removed the positive bound and added finite-number validation to reject NaN/Inf.
- M-2: `session_id` accepted control characters, shell metacharacters, and traversal-like values before process-cleaner work consumes `AGENT_SESSION_ID=...` markers.
  - Fix: constrained both checkpoint and workspace lock session IDs to ASCII letters, digits, `_`, and `-`; added pre-strip whitespace rejection.

Post-fix checklist:
- [x] `current_best.score` accepts `0.0`.
- [x] `current_best.score` accepts negative finite scores.
- [x] `current_best.score` rejects NaN and +/-Inf.
- [x] `CheckpointState.session_id` rejects unsafe values.
- [x] `WorkspaceLockHolder.session_id` rejects unsafe values.
- [x] Invalid `WorkspaceLock.acquire()` session IDs do not leave the lock held.
- [x] Targeted and full UT suites pass.

Review conclusion:
- Subtask 2.3 review fixes are ready for external verification.

## Subtask 2.3 - review-fix external verification and Ubuntu validation

- timestamp_utc: 2026-05-11T06:39:57Z
- reviewer: Claude
- verdict: Approve
- range: `5de44e9..cd5aefa`
- tests: 223 passed, 0 failed

Verification summary:
- [x] M-1 fixed: checkpoint best scores accept zero and negative finite values while rejecting NaN/Inf.
- [x] M-2 fixed: checkpoint and workspace-lock session IDs share the ASCII-safe contract.
- [x] Linux real-fcntl workspace lock regression executed and passed on Ubuntu.
- [x] Manual probes confirmed negative checkpoint score acceptance and unsafe session-id rejection.

Remaining non-blocking follow-ups:
- Consider extracting duplicated session-id validation into a shared internal helper.
- Consider documenting the intentional `pgid` constraint difference between checkpoint child processes and workspace lock holders.

Review conclusion:
- Subtask 2.3 is approved and validated on Ubuntu. Proceed to Subtask 2.4.

## Subtask 2.4 - SoT discovery helpers for existing trials

- timestamp_utc: 2026-05-11T06:47:41Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] `load_trial_record` treats immutable trial YAML as canonical SoT and rejects missing, empty, non-mapping, alias-bearing, non-UTF-8, oversized, unsafe-tag, and schema-invalid YAML.
- [x] `load_trial_record` requires the `integrity` block and verifies the payload hash before returning a record.
- [x] `iter_trial_record_paths` scans `trials/data` deterministically and returns only YAML files, with missing trial history represented as an empty tuple.
- [x] `load_trial_record_for_layout` and `discover_trial_records` reject namespace drift between YAML content and `NamespaceLayout`.
- [x] Discovery rejects path drift where a record is not stored at the path derived from its UTC completion month and `trial_id`.
- [x] Startup validation inputs expose unique bare `compiler.version` values from discovered trial namespaces.
- [x] Public exports in `src/agent/__init__.py` include the new discovery dataclasses, errors, and helpers.
- [x] Targeted and full UT suites pass.

Findings:
- No blocking issues found.
- The helpers intentionally remain read-only and do not create or rebuild `trials/_index.sqlite`; section 4.2.4 treats indexes as rebuildable derivatives, and this subtask supplies the canonical SoT scan needed by that future rebuild.
- `TrialLoadError` covers read/parse/schema failures, while `TrialIntegrityError` remains the specific signal for missing or mismatched trial integrity.

Deferred low-priority follow-ups:
- Wire `existing_trial_compiler_versions(...)` into init/startup once startup owns the FS-Memory workspace context instead of test-injected version lists.
- Add SQLite `_index.sqlite` rebuild helpers after the canonical discovery API is externally reviewed.
- Consider extracting the alias-free bounded YAML loader pattern if more SoT YAML readers repeat the same structure.

Review conclusion:
- Subtask 2.4 is ready for external review.

## Subtask 2.4 - external review verification

- timestamp_utc: 2026-05-11T11:01:40Z
- reviewer: Claude
- verdict: Approve
- range: `f492284..1cff51d`
- tests: 241 passed, 0 failed

Verification summary:
- [x] `load_trial_record` safely loads immutable trial YAML with size, UTF-8, alias, unsafe-tag, mapping, schema, integrity, and tamper checks.
- [x] `load_trial_record_for_layout` rejects namespace mismatch and wrong month/path placement.
- [x] `iter_trial_record_paths` and `discover_trial_records` provide deterministic canonical YAML discovery without reading `_index.sqlite`.
- [x] Startup helpers return bare compiler versions compatible with `validate_project_against_registry(existing_trial_compiler_versions=...)`.
- [x] Public exports and error hierarchy are coherent.
- [x] dev_memory and patch three-piece are complete.

Low/Info follow-ups:
- L-1: Decide whether hidden `.yaml` files under `trials/data` should be ignored or remain fail-fast discovery blockers.
- L-2: Document or tighten partial-prefix `compiler_type` behavior for compiler types with hyphens.
- L-3: Decide whether a directory-level symlink for `trials/data` is allowed or should be rejected.
- L-4: Repeated namespace validation in compiler-version extraction is defensive but redundant.
- L-5: Consider documenting lock-free discovery concurrency semantics; atomic replace means discovery sees before-or-after state rather than partial files.

Review conclusion:
- Subtask 2.4 is approved. Proceed to Ubuntu validation, then Subtask 2.5.

## Subtask 2.4 - Ubuntu validation

- timestamp_utc: 2026-05-11T11:08:54Z
- reporter: user on target Ubuntu server
- environment: Ubuntu/Linux, Python 3.11.15, `.venv`
- full_pytest: 241 passed in 0.72s
- linux_fcntl_test: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter PASSED`
- manual_probe:
  - trial path: `namespaces/multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3/trials/data/2026-04/trial_r1_t1.yaml`
  - discovered trial ids: `['r1_t1']`
  - compiler_versions: `('13.2.0',)`

Conclusion:
- Subtask 2.4 is externally approved and validated on Ubuntu. Proceed to Subtask 2.5.

## Subtask 2.5 - Rebuildable trial SQLite index

- timestamp_utc: 2026-05-11T11:47:47Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] `rebuild_trial_index` uses canonical `discover_trial_records`, not an existing index, as the source of truth.
- [x] Rebuild writes a fresh same-directory temp SQLite database and atomically replaces `trials/_index.sqlite`.
- [x] Rebuild fsyncs the temp database and parent directory.
- [x] Existing indexes are preserved when trial discovery fails.
- [x] Existing indexes are preserved when SQLite population fails.
- [x] Index metadata records schema version, type, rebuild timestamp, trial count, and latest source mtime.
- [x] Index rows project documented trial search fields, including trial id, combo, score fields, and integrity hash.
- [x] `trial_index_is_stale` detects missing indexes and newer trial YAML.
- [x] `ensure_trial_index_current` rebuilds only when stale.
- [x] Public exports include the new index dataclasses, errors, and helpers.
- [x] Targeted and full UT suites pass.

Findings:
- No blocking issues found.
- `rebuild_trial_index` documents that callers should hold `WorkspaceLock` when mutating the derived index during startup or workflow execution.
- The index intentionally remains derived cache state; reads can fail if the database is missing or schema-incompatible, while callers can rebuild from YAML.

Deferred low-priority follow-ups:
- Integrate `ensure_trial_index_current` into startup once startup owns the FS-Memory workspace layout and lock boundary.
- Add CLI-facing `agent reindex --type trials` command around this helper in the CLI phase.
- Add cross-process index reader/writer integration tests once workflow-level locking exists.

Review conclusion:
- Subtask 2.5 is ready for external review.

## Subtask 2.5 - external review verification

- timestamp_utc: 2026-05-11T12:25:19Z
- reviewer: Claude
- verdict: Approve
- range: `fd52bc8..a3e7edf`
- tests: 249 passed, 0 failed

Verification summary:
- [x] `rebuild_trial_index` uses `discover_trial_records` as the canonical YAML source and never treats an existing index as authoritative.
- [x] Rebuild creates a same-directory temp SQLite database and atomically replaces `trials/_index.sqlite`.
- [x] Existing indexes are preserved on discovery failure and SQLite population failure.
- [x] Index metadata records schema version, index type, rebuild timestamp, trial count, and latest source mtime.
- [x] Trial rows project the documented trial fields, score fields, integrity hash, relative path, and source mtime.
- [x] `trial_index_is_stale` and `ensure_trial_index_current` cover missing/stale index behavior.
- [x] Public exports and error hierarchy are coherent.
- [x] dev_memory and patch three-piece are complete.

Low/Info follow-ups:
- L-1: Decide whether `ensure_trial_index_current` should auto-rebuild on schema mismatch or keep raising `TrialIndexError`.
- L-2: Consider cleaning stale SQLite sidecars (`-journal`, `-wal`, `-shm`) after successful rebuild.
- L-3: Consider avoiding the duplicate SQLite open in `load_trial_index_rows`.
- L-4: Decide whether `trials/_index.sqlite` symlinks should be rejected before rebuild or replaced by design.
- L-5: Keep or consume per-row `source_mtime_ns` in future doctor/drift checks.
- L-6: Document that WorkspaceLock is recommended for derived-index rebuild efficiency/coordination, not required for SoT correctness.

Review conclusion:
- Subtask 2.5 is approved. Proceed to Ubuntu validation, then Subtask 2.6.

## Subtask 2.5 - Ubuntu validation

- timestamp_utc: 2026-05-11T12:52:06Z
- reporter: user on target Ubuntu server
- environment: Ubuntu/Linux, Python 3.11.15, `.venv`
- full_pytest: 249 passed in 1.00s
- linux_fcntl_test: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter PASSED` in 0.09s
- manual_probe_note: Initial guide sample was incomplete (`score.vs_best` missing) and was rejected by schema validation; this was not an implementation failure.

Conclusion:
- Subtask 2.5 is externally approved and validated on Ubuntu. Proceed to Subtask 2.6.

## Subtask 2.6 - LearnedRule YAML schema and writer

- timestamp_utc: 2026-05-11T13:00:06Z
- files_reviewed:
  - src/agent/fs_memory.py
  - src/agent/__init__.py
  - tests/test_fs_memory.py

Review checklist:
- [x] `LearnedRule` covers the documented learned/rule fields from REQUIREMENTS.md section 4.2.6.
- [x] `LearnedRuleIntegrity.hash_fields_excluded` is fixed to `[integrity, user_validated, user_notes]`.
- [x] Learned rule payload hash excludes only the integrity block and documented user-editable fields.
- [x] User edits to `user_validated` and `user_notes` do not invalidate integrity.
- [x] Semantic edits to fields like `description` or `action_hint` are detected by integrity verification.
- [x] `write_learned_rule` writes through shared `atomic_write_yaml` and refuses existing paths.
- [x] `load_learned_rule` rejects missing, empty, non-mapping, alias-bearing, non-UTF-8, oversized, schema-invalid, missing-integrity, and tampered YAML.
- [x] Public exports in `src/agent/__init__.py` include the learned rule models, errors, and helpers.
- [x] Targeted and full UT suites pass.

Findings:
- No blocking issues found.
- `LearnedRuleScope` is intentionally narrower than future experience scope metadata; it models the documented learned-rule fields and can be expanded when later workflow code produces more scope dimensions.
- `write_learned_rule` refuses overwrite to protect user edits; future `agent integrity accept` can own explicit rewrite/accept flows.

Deferred low-priority follow-ups:
- Add learned-rule discovery/scanning helpers when doctor/integrity-check flows need to scan all rules.
- Decide whether `evidence_count` must equal `supporting_trials` length forever or should become `>=` if future non-trial evidence types are added.
- Consider extracting common integrity helper patterns once experience YAML and import local_integrity are implemented.

Review conclusion:
- Subtask 2.6 is ready for external review.

## Subtask 2.6 - external review verification

- timestamp_utc: 2026-05-13T13:50:20Z
- reviewer: Claude
- verdict: Approve
- range: `7ebdd06..96320f0`
- tests: 260 passed, 0 failed

Verification summary:
- [x] `LearnedRule` covers the documented learned-rule fields from REQUIREMENTS.md section 4.2.6.
- [x] `rule_id` and `evidence.supporting_trials` are path-safe.
- [x] `created_at` uses strict UTC ISO 8601 validation.
- [x] `evidence_count` matches `supporting_trials` length.
- [x] `confidence` is bounded to `[0, 1]`.
- [x] `user_validated` and `user_notes` are user-editable and excluded from integrity.
- [x] `integrity.hash_fields_excluded` is fixed and tamper-resistant.
- [x] `write_learned_rule` uses shared `atomic_write_yaml`, refuses overwrite, and refuses symlink overwrite.
- [x] `load_learned_rule` verifies safe YAML parsing, schema, and integrity.
- [x] Public exports and error hierarchy are coherent.
- [x] dev_memory and patch three-piece are complete.

Low/Info follow-ups:
- L-1: Decide whether an entirely empty `LearnedRule.scope` should be accepted or rejected.
- L-2: Document that learned rules intentionally omit a namespace field to support manual promotion/copying across namespace directories.
- L-3: Direct hash helpers validate through `LearnedRule.model_validate`, so there is no bypass path for evidence-count consistency.
- L-4: Consider whether `user_validated` should later become a three-state review status.
- L-5: Keep cross-rule duplicate/semantic consistency checks in future doctor/dedup tooling, not the writer.
- L-6: Document WorkspaceLock wording differences between SoT writers and derived-index rebuilds.

Review conclusion:
- Subtask 2.6 is approved. Proceed to Ubuntu validation, then Subtask 2.7.

## Subtask 2.6 - Ubuntu validation

- timestamp_utc: 2026-05-13T14:00:24Z
- reporter: user on target Ubuntu server
- environment: Ubuntu/Linux, Python 3.11.15, `.venv`
- full_pytest: 260 passed in 1.19s
- linux_fcntl_test: `tests/test_workspace_lock.py::test_real_fcntl_release_keeps_path_locked_for_preopened_waiter PASSED` in 0.10s
- manual_probe:
  - path: `learned/rules/rule_017.yaml`
  - excluded: `[integrity, user_validated, user_notes]`
  - verify_initial: true
  - loaded_notes: `accepted after manual review`
  - tamper_detected: true

Conclusion:
- Subtask 2.6 is externally approved and validated on Ubuntu. Proceed to Subtask 2.7.
