# Self Review Notes

## Subtask 1.1 - config schema

- reviewed_at: 2026-05-06T08:52:59Z
- status: passed
- related_requirements:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
  - REQUIREMENTS.md section 7

Required checklist for each subtask:
- [x] Implementation matches referenced requirements.
- [x] Documented failure modes are covered.
- [x] Trace writes are present where required by SoT dual-track rules.
- [x] Atomic YAML writes are used where required.
- [x] No hidden canonical data is stored only in SQLite/cache.
- [x] No unsafe assumption about spec restore or workspace verification.
- [x] `dev_memory` progress is updated.
- [x] Linux/Ubuntu-only behavior is explicit where POSIX features are used.
- [x] No hardcoded paths that should come from config.
- [x] Imported experience text is quote-wrapped in prompts where applicable.
- [x] Hash calculation excludes fields listed in `hash_fields_excluded`.

Findings:
- `agent.convergence.no_improve_trials` in REQUIREMENTS.md section 4.1.2 overlaps with `agent.stagnation_threshold_trials` in Appendix B. Fixed by accepting both and rejecting conflicts; decision recorded in `dev_memory/DECISIONS.md`.
- `baseline.combo` in section 4.1.2 overlaps with `baseline.default_combo` in Appendix B. Fixed by synchronizing the default field when only one form is provided.
- `tracing.langfuse.enabled` in section 4.1.2 overlaps with `tracing.langfuse_enabled` in Appendix B. Fixed by synchronizing the flags and rejecting conflicts.
- Trace writes and atomic YAML writes are not applicable to Subtask 1.1 because it only reads user config and performs validation; no canonical SoT write path is implemented here.
- Imported prompt quoting and hash exclusion behavior are not implemented in Subtask 1.1, but their config flags are represented and tested.

## External Review Fix - Claude review

- started_at: 2026-05-06T13:52:19Z
- completed_at: 2026-05-06T13:56:52Z
- status: fixed
- verdict_received: Request changes
- accepted_for_immediate_fix:
  - Baseline `combo` vs `default_combo` conflict must be rejected.
  - Tilde path defaults must expand at model construction time, not module import time.
  - Template paths such as `<workspace>/_trash` and `<run_id>` must keep explicit unresolved semantics and have resolver helpers.
  - Top-level YAML key `import_config` must be rejected; only the documented `import` key is accepted.
  - Config YAML loading should reject oversized files and aliases before parsing.
  - Package readme should not point at locked requirements.
  - Unused `loguru` dependency should be removed until a logging subtask needs it.
- deferred_or_recorded:
  - `langgraph`, `litellm`, `scipy`, `psutil`, and optional `sqlite-vec` will be introduced in the phases that use them.
  - Relative paths such as `trace/events.jsonl` and `state/run.lock` are stored as config values and will be anchored to the namespace directory by Subtask 1.2/1.4 helpers.

Fixes applied:
- Replaced `object.__setattr__` synchronization for convergence, baseline, and langfuse with raw-dict `model_validator(mode="before")` normalization.
- Added baseline conflict rejection when both `combo` and `default_combo` are explicitly set differently.
- Changed tilde path defaults to runtime `default_factory` expansion.
- Preserved `<workspace>` and `<run_id>` path templates as strings with explicit resolver helpers.
- Tightened top-level `import` alias handling so YAML key `import_config` is rejected.
- Added `MAX_CONFIG_BYTES` and a config YAML loader that rejects aliases.
- Replaced package `readme = doc/REQUIREMENTS.md` with a root `README.md`.
- Removed unused `loguru` dependency and documented dependency deferral in `DECISIONS.md`.

Post-fix review checklist:
- [x] Implementation matches referenced requirements.
- [x] Documented failure modes are covered.
- [x] Trace writes are present where required by SoT dual-track rules.
- [x] Atomic YAML writes are used where required.
- [x] No hidden canonical data is stored only in SQLite/cache.
- [x] No unsafe assumption about spec restore or workspace verification.
- [x] `dev_memory` progress is updated.
- [x] Linux/Ubuntu-only behavior is explicit where POSIX features are used.
- [x] No hardcoded paths that should come from config.
- [x] Imported experience text is quote-wrapped in prompts where applicable.
- [x] Hash calculation excludes fields listed in `hash_fields_excluded`.

## Subtask 1.2 Self Review - modules.registry and namespace

- reviewed_at: 2026-05-07T08:21:27Z
- related_requirements:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- files_reviewed:
  - `src/agent/registry.py`
  - `src/agent/__init__.py`
  - `tests/test_registry.py`

Findings:
- The locked requirements name `shared/modules.registry.yaml` but do not define its complete schema. Recorded an implementation decision to use top-level `kg_versions` plus `modules -> frameworks -> compilers -> versions`.
- Initial UT for "unregistered module/framework" accidentally emptied required registry maps and hit schema validation before startup validation. Fixed the tests to replace entries with other valid names so they exercise `RegistryValidationError`.
- Added `experience_scopes_bottom_up` after review to cover the inheritance map from section 4.1.3, not just the full namespace string.

Review checklist:
- [x] Implementation strictly matches the referenced requirements or records implementation choices in `DECISIONS.md`.
- [x] Startup failure paths cover module/framework not in registry, compiler.version mismatch, kg_version missing, and existing trial compiler incompatibility.
- [x] Trace writes are not required in this read-only validation subtask.
- [x] Atomic YAML writes are not required because this subtask only reads registry YAML.
- [x] No hidden canonical data is stored in SQLite/cache; registry and namespace are user-readable YAML/path values.
- [x] No assumption about spec restore or workspace verification.
- [x] `dev_memory` progress is updated.
- [x] No POSIX process/locking behavior is introduced in this subtask; namespace computation avoids Windows-specific path semantics by exposing POSIX namespace strings and joining filesystem paths segment-by-segment.
- [x] No hardcoded project paths; the registry location is derived from configured workspace as `<workspace>/shared/modules.registry.yaml`.
- [x] Imported experience prompt quoting is not applicable.
- [x] Hash calculation is not applicable.

## Subtask 1.2 External Review Fix - Claude minor changes

- started_at: 2026-05-07T08:51:09Z
- completed_at: 2026-05-07T08:52:38Z
- status: fixed
- verdict_received: Approve with minor changes
- accepted_for_immediate_fix:
  - Reject namespace and registry segment control characters.
  - Require explicit `schema_version` in `modules.registry.yaml`.
  - Add direct `AgentConfig` namespace computation UT.
  - Add `existing_trial_compiler_versions` docstring.
  - Record `schema_version` and `code-`/`kg-` prefix decisions.

Fixes applied:
- `_validate_namespace_segment` now rejects all C0 control characters and DEL before path construction.
- `ModulesRegistry.schema_version` is now required and must be `modules.registry.v1`.
- Added regression tests for newline, tab, carriage return, BEL, ESC, and DEL in project namespace values, plus registry control-character values.
- Added tests for missing and unknown registry schema versions.
- Added direct `compute_project_namespace(AgentConfig)` coverage.
- Added a docstring explaining that `existing_trial_compiler_versions` is a defensive same-namespace compatibility input for later FS-memory integration.

Deferred low-priority review notes:
- Internal spaces, hidden dot-prefixed names, very long segment limits, and whitespace stripping semantics remain non-blocking polish candidates before or during Phase 02.

Post-fix review checklist:
- [x] Implementation matches referenced requirements.
- [x] Documented failure modes are covered.
- [x] Trace writes are not required in this read-only validation subtask.
- [x] Atomic YAML writes are not required because this subtask only reads registry YAML.
- [x] No hidden canonical data is stored only in SQLite/cache.
- [x] No unsafe assumption about spec restore or workspace verification.
- [x] `dev_memory` progress is updated.
- [x] No POSIX process/locking behavior is introduced.
- [x] No hardcoded project paths that should come from config.
- [x] Imported experience prompt quoting is not applicable.
- [x] Hash calculation is not applicable.

## Final External Review - Claude approve

- reviewed_at: 2026-05-07T06:54:29Z
- verdict: Approve
- tested: 51 passed, 0 failed
- conclusion: Subtask 1.1, including both external review fix rounds, is approved and can move to Subtask 1.2.
- non_blocking_followups:
  - Add assignment path expansion UT.
  - Add `allowed_non_item_files` empty-list UT.
  - Add baseline assignment conflict UT.

Notes:
- Trace writes, atomic YAML writes, imported prompt quote behavior, and hash calculation remain not directly applicable to the config-only parser, but their config flags are represented where Appendix B defines them.

## Second External Review Fix - Claude review

- started_at: 2026-05-07T03:54:17Z
- completed_at: 2026-05-07T03:56:38Z
- status: fixed
- verdict_received: Approve with minor changes
- accepted_for_immediate_fix:
  - Relax `ExplorationScheduleConfig` so quota total may be less than `window_size` but never greater.
  - Add `process_cleanup.require_env_marker` from REQUIREMENTS.md section 4.11.4 and model strict vs degraded cleanup checks.
  - Reject blank expanded path strings.
  - Preserve field-level empty combo validation during assignment.
  - Add UT guards for relative path preservation and selected duplicate validators.
  - Remove accidental tracked `doc/files (4).zip` and ignore future zip artifacts.

Fixes applied:
- `ExplorationScheduleConfig` now rejects quota totals greater than `window_size`, while allowing totals less than `window_size` for priority fallback slots.
- `mutation_per_window` and `novelty_per_window` now require positive values.
- `ProcessCleanupConfig` now supports `require_env_marker`; strict mode requires all three checks, degraded mode requires only `create_time` and `cmdline_hash`.
- Blank path strings now fail during path expansion.
- Empty baseline assignment now surfaces field-level list length validation instead of a misleading conflict error.
- Relative path preservation is covered by UT as a Subtask 1.1 contract.
- `doc/files (4).zip` was removed from Git tracking and `*.zip` added to `.gitignore`.

Post-fix review checklist:
- [x] Implementation matches referenced requirements.
- [x] Documented failure modes are covered.
- [x] Trace writes are present where required by SoT dual-track rules.
- [x] Atomic YAML writes are used where required.
- [x] No hidden canonical data is stored only in SQLite/cache.
- [x] No unsafe assumption about spec restore or workspace verification.
- [x] `dev_memory` progress is updated.
- [x] Linux/Ubuntu-only behavior is explicit where POSIX features are used.
- [x] No hardcoded paths that should come from config.
- [x] Imported experience text is quote-wrapped in prompts where applicable.
- [x] Hash calculation excludes fields listed in `hash_fields_excluded`.
