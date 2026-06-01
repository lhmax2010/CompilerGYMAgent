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
- [x] Runner retries spawn-time env-marker visibility briefly to avoid reading
  `/proc/<pid>/environ` before child exec/env is visible.
- [x] Runner uses `start_new_session=True`; spawned child `pgid == pid` in
  tests.
- [x] Runner can refresh leases to `exited` or `killed` from `Popen.returncode`.
- [x] Full suite passes.

Residual risks / follow-up:

- Ownership scoring and cleanup decisions remain 6.3 scope.
- Lease GC remains 6.3 scope.
- TrialState operation ledger remains 6.5 scope.

External review:

- Verdict: Approve
- Range: `7a6a6f9..e55a79d`
- Hardening range: `e55a79d..d38567e`
- Notes: lease status transitions, derived-state shape, spawn lease writes,
  failed-lease cleanup, and 0 residual process behavior all passed review.
- Follow-up for 6.3: cleaner must use single-read env-marker probing and must
  not reuse `process_runner._env_marker_visible()` because that helper has
  spawn-only retry semantics.

## Subtask 6.3 - Process Cleaner

Self-review checklist:

- [x] Cleaner uses single-read env marker probing; no retry and no dependency
  on `process_runner._env_marker_visible()`.
- [x] Graded scoring implements pid+create_time +3, pgid +3, env_marker +4.
- [x] Score thresholds map to owned/suspected/not_ours as designed.
- [x] AccessDenied / missing env marker does not add score.
- [x] Owned process groups are killed with `killpg`.
- [x] Suspected process groups are skipped by default and can be force-killed.
- [x] Leader-dead / children-alive is discoverable through pgid scan.
- [x] Double-fork-style escape is discoverable through env-marker scan and
  remains suspected unless forced.
- [x] Lease GC deletes orphan leases only when no live cleanup target remains.
- [x] Full suite passes.

Residual risks / follow-up:

- Trace process-cleanup event emission is still deferred.
- Cleaner CLI / doctor force flags are deferred to later CLI/doctor subtasks.
- Process-event kind whitelist closure still needs to be wired when trace
  process cleanup events are emitted.

External review:

- Verdict: Approve
- Range: `1f2bf61..ca9373a`
- Notes: graded scoring boundaries, single-read env marker probing,
  leader-dead pgid discovery, double-fork env-marker discovery, owned killpg
  cleanup, and orphan lease GC were independently probed.
- Low follow-up: lease GC can conservatively retain an orphan under rare
  pid/pgid reuse; the error direction is safe and can be tightened in later
  doctor/state-consistency work.

## Subtask 6.4 - Workspace Lock Probe + LockStatus unknown

Self-review checklist:

- [x] `WorkspaceLock.probe_lock()` opens the existing lock file and attempts
  `LOCK_EX | LOCK_NB` without creating, truncating, or replacing `run.lock`.
- [x] `_write_holder()` remains unchanged and still writes through the
  already-flocked fd in place.
- [x] `trace_cleanup._read_workspace_lock()` uses the flock probe as the
  source of truth for free vs busy.
- [x] Holder YAML is used only to explain a busy holder or provide a protected
  session id.
- [x] Unreadable holder YAML returns `lock_status="unknown"` and a refusal
  reason.
- [x] `can_execute` and `can_execute_with_force_inactive_only` reject
  `unknown`.
- [x] Released-but-live holder metadata is no longer treated as a held lock
  when the probe can acquire the flock.
- [x] Tests use real active locks for held_by_self / held_by_other instead of
  metadata-only simulation.
- [x] Full suite passes.

Residual risks / follow-up:

- Busy flock with stale-but-readable holder metadata becomes `unknown`; doctor
  state-consistency can later provide richer remediation text.
- Phase 6.7 still owns CleanPlan checkpoint/session hash hardening and Layer D
  active-trial protection.

External review:

- Verdict: Approve
- Range: `2b07a88..03ca715`
- Notes: real `LOCK_NB` probing fixed the released-but-live metadata false
  busy case; `unknown` lock status refuses normal and force clean; `_write_holder`
  and the never-`os.replace(run.lock)` red line were not touched.
- Validation re-run: targeted lock/cleanup/CLI set 78 passed; full suite 496
  passed.

## Subtask 6.5 - TrialState Operation Ledger

Self-review checklist:

- [x] `CheckpointTrialOperation` is additive and does not remove existing
  `current_stage` compatibility fields.
- [x] Legacy checkpoints missing `operations` still load.
- [x] New ledgers require `current_trial_start_line`.
- [x] `process_refs` must use `state/processes/<session>/<trial>/<lease>.yaml`.
- [x] `process_refs` session segment must match checkpoint `session_id`.
- [x] `process_refs` trial segment must match `current_trial.trial_id`.
- [x] `output_ref` rejects absolute, parent, backslash, and denormalized paths.
- [x] Operation `details` accepts only JSON-compatible values.
- [x] Round-trip checkpoint write/load preserves operations.
- [x] Full suite passes.

Residual risks / follow-up:

- 6.5 introduces the canonical ledger shape only; resume semantics and
  operation replay policies remain Phase 09/10 scope.
- 6.7 still wires `current_trial_start_line` into clean trace Layer D
  protection.
