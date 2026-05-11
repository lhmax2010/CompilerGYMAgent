# Phase 02 / Subtask 2.5 Self-Review

## Scope

- Implement rebuildable `trials/_index.sqlite` from canonical trial YAML.
- Keep trial YAML as the source of truth.
- Keep CLI command wiring and startup integration out of scope.

## Checklist

- [x] Rebuild reads verified trial YAML through `discover_trial_records`.
- [x] Rebuild never reads an existing SQLite index as source data.
- [x] Rebuild creates a fresh same-directory temp database.
- [x] Rebuild atomically replaces `trials/_index.sqlite`.
- [x] Rebuild fsyncs the temp database and parent directory.
- [x] Existing index is preserved on discovery failure.
- [x] Existing index is preserved on SQLite population failure.
- [x] Metadata records schema version, index type, rebuild timestamp, trial count, and latest source mtime.
- [x] Row projection includes trial id, relative path, namespace, round, timestamp, duration, combo hash, combo, mode, candidate source, schedule slot, bench level, outcome, score fields, integrity hash, and source mtime.
- [x] Stale detection returns true when the index is missing.
- [x] Stale detection returns true when a trial YAML file is newer than the index.
- [x] `ensure_trial_index_current` does not rebuild when the index is current.
- [x] Public exports include the new index APIs.
- [x] Targeted and full unit suites pass.

## Findings

No blocking issues found.

The index is intentionally derived cache state. It is safe to delete and rebuild from YAML, and a missing/bad schema index is surfaced as `TrialIndexError` rather than silently trusted.

## Deferred

- Wire `ensure_trial_index_current` into startup under `WorkspaceLock`.
- Add the CLI command for `agent reindex --type trials`.
- Add workflow-level concurrent read/rebuild tests once the process-level lock is integrated.
