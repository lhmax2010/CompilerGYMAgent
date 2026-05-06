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

Notes:
- Trace writes, atomic YAML writes, imported prompt quote behavior, and hash calculation remain not directly applicable to the config-only parser, but their config flags are represented where Appendix B defines them.
