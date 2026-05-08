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
