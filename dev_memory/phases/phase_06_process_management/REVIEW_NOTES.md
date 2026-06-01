# Phase 06 Review Notes

## Subtask 6.1 - Process Identity + process_lab

Self-review checklist:

- [x] `ProcessIdentity` / `ProcessRecord` are additive and do not mutate
  existing checkpoint or workspace-lock schemas.
- [x] `session_id` validation reuses `validate_session_id_atom()`.
- [x] `cmdline_hash` is modeled as diagnostic-only; no ownership scoring is
  implemented in 6.1.
- [x] `cgroup_path` is optional and reserved for v2 without introducing cgroup
  behavior.
- [x] `process_lab` uses controlled Python subprocess scripts, not raw fork.
- [x] Each process_lab child starts in a dedicated process group unless the
  scenario intentionally creates same-pgid children or escaped child sessions.
- [x] Cleanup uses `killpg` and skips the current test runner process group.
- [x] leader-dead / children-alive and escaped-child scenarios expose child
  pids and pgids for later cleaner tests.
- [x] AccessDenied is explicitly modeled as a simulation hook for later psutil
  monkeypatch tests.
- [x] Targeted tests cover model validation, hash stability, env marker
  visibility, pid-gone records, pgid mismatch, and process-group scenarios.
- [x] Full test suite passes after exports.

Residual risks / follow-up:

- Actual ownership scoring is intentionally deferred to 6.3.
- Lease persistence is intentionally deferred to 6.2.
- Operation ledger and checkpoint migration are intentionally deferred to 6.5.

External review:

- Verdict: Approve
- Range: `dce83d2..2ff1342`
- Notes: model validation is clean, existing schemas were not touched,
  process_lab reproduces the seven planned scenarios, and independent cleanup
  probing found 0 residual processes.

## Subtask 6.2 - Process Runner + Process Lease Registry

Self-review checklist:

- [x] Lease files use the planned `state/processes/<session>/<trial>/<role>-<pid>.yaml`
  shape.
- [x] `session_id`, `trial_id`, and `role` reuse path-safe atom validation.
- [x] Lease YAML uses a safe loader that rejects aliases.
- [x] Lease writes are atomic and use restrictive `0600` mode.
- [x] Lease payloads intentionally do not contain integrity hashes.
- [x] Status-specific validation rejects malformed terminal states.
- [x] Terminal status transitions reject attempts to move from a terminal state.
- [x] Runner injects `AGENT_SESSION_ID` and records
  `env_marker_visible_at_spawn`.
- [x] Runner uses `start_new_session=True`; spawned child `pgid == pid` in
  tests.
- [x] Runner can refresh leases to `exited` or `killed` from `Popen.returncode`.
- [x] Full suite passes.

Residual risks / follow-up:

- Ownership scoring and cleanup decisions remain 6.3 scope.
- Lease GC remains 6.3 scope.
- TrialState operation ledger remains 6.5 scope.
