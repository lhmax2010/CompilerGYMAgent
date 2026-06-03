# Phase 06 - Process Management

## Subtask 6.1 - Process Identity + process_lab

Started Phase 06 with the shared model and test substrate that later runner,
lease registry, cleaner, and doctor work will depend on.

### Changes

- Added `src/agent/process_identity.py`.
- Added `ProcessIdentity` and `ProcessRecord` Pydantic models with:
  - `pid`
  - `pgid`
  - `create_time`
  - `session_id`
  - `cmdline_hash`
  - `env_marker_visible_at_spawn`
  - `cgroup_path`
- Reused `validate_session_id_atom()` for process session id validation.
- Added `compute_cmdline_hash()` for stable diagnostic command-line hashes.
- Exported the new process identity symbols from `agent.__init__`.
- Added `tests/fixtures/process_lab.py` as a reusable real-subprocess fixture.
- Added process_lab support for:
  - live process groups,
  - pid-gone records,
  - create-time drift records,
  - pgid mismatch records,
  - missing env marker at spawn,
  - simulated `psutil.AccessDenied`,
  - leader-dead / children-alive process groups,
  - double-fork-style escaped child sessions.

### Guardrails

- Existing `CheckpointProcess` and `WorkspaceLockHolder` schemas were not
  changed.
- No process cleanup behavior was introduced in this subtask.
- process_lab uses controlled Python subprocesses rather than raw fork.

### Validation

- `tests/test_process_identity.py`: 13 passed
- `tests/test_process_lab.py`: 7 passed
- Full suite: 471 passed

### Review

- Claude review verdict: Approve
- Review range: `dce83d2..2ff1342`
- Ubuntu/Linux validation re-run:
  - targeted 20 passed
  - full suite 471 passed

## Subtask 6.2 - Process Runner + Process Lease Registry

Added the first process-management behavior above the 6.1 model/fixture
foundation.

### Changes

- Added `src/agent/process_registry.py`.
- Added `ProcessLease` and `ProcessLeaseStatus`.
- Added lease path helpers for
  `state/processes/<session_id>/<trial_id>/<role>-<pid>.yaml`.
- Added safe process lease YAML loading and atomic writing.
- Added running lease registration.
- Added terminal state transitions:
  - `exited`
  - `killed`
  - `unsafe_skip`
  - `unknown`
- Kept process leases as derived state without integrity hashes.
- Added `src/agent/process_runner.py`.
- Added `spawn_process()` using `subprocess.Popen(start_new_session=True)` and
  injected `AGENT_SESSION_ID`.
- Hardened spawn-time env-marker visibility probing with a short retry loop to
  avoid the `Popen`/`exec` race where `/proc/<pid>/environ` is read before the
  child environment is visible.
- Added `refresh_process_lease_from_popen()` to mark completed processes as
  `exited` or `killed`.
- Exported process registry and runner symbols from `agent.__init__`.

### Guardrails

- Process cleanup / ownership scoring is still deferred to 6.3.
- Lease GC is still deferred to 6.3 doctor/cleanup integration.
- Checkpoint operation ledger is still deferred to 6.5.

### Validation

- `tests/test_process_registry.py`: 7 passed
- `tests/test_process_runner.py`: 6 passed
- Adjacent targeted tests: 16 passed
- Full suite: 484 passed

### Review

- Claude review verdict: Approve
- Review range: `7a6a6f9..e55a79d`
- Hardening range: `e55a79d..d38567e`
- Validation re-run:
  - targeted 29 passed
  - full suite 484 passed
- Follow-up carried into 6.3: process cleaner env-marker reads must be
  single-shot and must not reuse the runner's retry helper.

## Subtask 6.3 - Process Cleaner

Implemented Phase 06's core process ownership and cleanup logic.

### Changes

- Added `src/agent/process_cleaner.py`.
- Added single-read `read_env_marker()` for cleaner scans. It intentionally
  does not retry and does not reuse the runner's spawn-only retry helper.
- Added graded process attribution:
  - pid + create_time match: +3
  - pgid match: +3
  - env marker match: +4
  - score >= 7: owned
  - score >= 4: suspected
  - score < 4: not ours
- Added cleanup target discovery through:
  - recorded pid,
  - pgid scan,
  - env-marker scan.
- Added `cleanup_process_lease()`:
  - owned targets are killed with `killpg`,
  - suspected targets become `unsafe_skip` by default,
  - `force_suspected=True` can kill suspected targets,
  - no matching live target becomes `unknown`.
- Added `garbage_collect_process_leases()` for orphan lease deletion when no
  live cleanup targets remain.
- Exported cleaner symbols from `agent.__init__`.

### Validation

- `tests/test_process_cleaner.py`: 8 passed
- Cleaner adjacent target set: 31 passed
- Full suite: 492 passed

### Review

- Claude review verdict: Approve
- Review range: `1f2bf61..ca9373a`
- Validation re-run:
  - targeted cleaner-adjacent set 31 passed
  - full suite 492 passed
- Reviewer independently verified:
  - single-read env marker probing avoids runner-style retry delays,
  - score thresholds map correctly to owned/suspected/not_ours,
  - leader-dead children-alive is discovered through pgid scanning,
  - double-fork escape is discovered through env-marker scanning,
  - owned cleanup kills the process group and updates the lease to `killed`.

## Subtask 6.4 - Workspace Lock Probe + LockStatus unknown

Hardened read-only workspace lock classification for trace cleanup.

### Changes

- Added `LockProbeResult` and `WorkspaceLock.probe_lock()`.
- `probe_lock()` performs a nonblocking flock probe on the existing
  `state/run.lock` file and immediately unlocks if the probe succeeds.
- Kept `_write_holder()` unchanged; holder metadata is still written in place
  through the already-flocked fd.
- Changed trace cleanup lock classification so the flock probe determines
  free vs busy.
- Changed unreadable holder metadata from `lock_status="free"` to
  `lock_status="unknown"` with a refusal reason.
- Preserved held_by_self / held_by_other behavior when an actual flock is busy
  and holder metadata is readable.
- Exported `LockProbeResult` from `agent.__init__`.

### Validation

- `tests/test_workspace_lock.py tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py`: 68 passed
- `tests/test_cli_clean_trace.py`: 10 passed
- Full suite: 496 passed

### Review

- Claude review verdict: Approve
- Review range: `2b07a88..03ca715`
- Validation re-run:
  - lock/cleanup/CLI targeted set 78 passed
  - full suite 496 passed
- Reviewer independently verified:
  - real flock probe distinguishes free/busy,
  - released-but-live holder metadata no longer reports held_by_other,
  - corrupted holder metadata reports `unknown`,
  - normal and force clean reject `unknown`,
  - `_write_holder()` remains unchanged and `run.lock` is never replaced.

## Subtask 6.5 - TrialState Operation Ledger

Added the checkpoint schema extension that later resume, doctor, and clean trace
Layer D work will use.

### Changes

- Added `CheckpointTrialOperation`.
- Added operation names and statuses for workspace/spec/compile/benchmark/
  restore/memory/cleanup operations.
- Added `current_trial.operations`.
- Added `current_trial.current_trial_start_line`.
- Kept existing `current_stage`, `stage_started_at`, and `process` fields for
  backward compatibility.
- Added validation for safe relative `output_ref` values.
- Added validation for `process_refs` lease registry paths.
- Added session/trial alignment checks for operation `process_refs`.
- Exported checkpoint operation symbols from `agent.__init__`.

### Validation

- `tests/test_fs_memory.py tests/test_identifiers.py`: 164 passed
- `tests/test_errors.py`: 3 passed
- Full suite: 508 passed

### Review

- Claude review verdict: Approve
- Review range: `eef6b02..4bde11a`
- Validation re-run:
  - checkpoint/identifier targeted set 164 passed
  - process_lab/process_cleaner targeted set 15 passed
  - full suite 508 passed
- Reviewer independently verified:
  - legacy checkpoints without `operations` load cleanly,
  - operation ledgers round-trip through YAML,
  - process refs cannot traverse paths or point at another session/trial,
  - non-empty operations require `current_trial_start_line`.
- Low finding resolved in follow-up hardening: process_lab worker/grandchild
  JSON IPC now writes payloads atomically (`temp` + `os.replace`) and readers
  wait until JSON parsing succeeds. This removes the half-written JSON window
  that remained after the timeout-only hardening. The fixture still waits for
  escaped child readiness before cleaner tests probe env/pgid state.

## Subtask 6.6 - doctor/state_consistency.py

Added the read-only checkpoint/trace/process lease consistency validator that
Phase 10 doctor commands will render later.

### Changes

- Added `src/agent/doctor/`.
- Added `StateConsistencyIssue`, `StateConsistencyReport`, and
  `inspect_state_consistency()`.
- Reused `inspect_trace_checkpoint_alignment()` for checkpoint/trace line-count
  status.
- Reused `inspect_trace_session_spans()` for trace session coverage.
- Added current-trial trace anchor validation:
  - `current_trial_start_line` must be within trace bounds,
  - the event at that line must match `current_trial.trial_id`,
  - non-`trial_start` anchors are reported as warnings.
- Added operation `process_refs` checks:
  - missing lease refs are errors,
  - running operations with terminal leases are warnings,
  - terminal operations with running leases are warnings,
  - pending operations with process refs are warnings.
- Added orphan lease diagnostics:
  - running unreferenced leases are warnings,
  - terminal unreferenced leases are info findings.
- Exported state-consistency symbols from `agent.__init__`.

### Guardrails

- The validator is read-only: it does not reconcile trace/checkpoint state,
  delete or GC leases, or inspect/kill live processes.
- Process leases remain derived state; the validator only reports consistency
  findings and repair suggestions.

### Validation

- `tests/test_state_consistency.py`: 7 passed
- Adjacent targeted set
  (`state_consistency`, `trace_session`, `process_registry`, `fs_memory`,
  `errors`): 203 passed
- Full suite: 515 passed

### Review

- Claude review verdict: Approve
- Review range: `a196c52..b109e45`
- Reviewer independently verified:
  - 3.8 trace/checkpoint alignment and 3.9 session spans are reused,
  - process refs, orphan leases, malformed leases, and status mismatches are
    diagnosed correctly,
  - repeated inspection is read-only and does not mutate files,
  - findings include `repair_suggestion` and structured details.

## Subtask 6.7 - Clean Trace Hardening

Added the Phase 06 clean trace hardening promised by ROADMAP: plan snapshot
hashes and Layer D active-trial protection.

### Changes

- Added `checkpoint_hash` to `CleanPlan`.
- Added `protected_sessions_hash` to `CleanPlan`.
- Added `current_trial_protected_line_range` to `CleanPlan` for Layer D
  visibility.
- `execute_clean_plan()` now revalidates, while holding the workspace lock:
  - trace line count and file size,
  - checkpoint hash,
  - protected session/current-trial line boundaries.
- Layer D protection now preserves current-trial trace lines from
  `current_trial_start_line` through the current trace end when checkpoint
  operations indicate an in-progress trial.
- Planning refuses execution if `current_trial_start_line` is ahead of
  validated trace events.
- Added stable canonical JSON SHA-256 helpers for checkpoint and protected
  session snapshots.

### Validation

- `tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py`: 34 passed
- Trace/cleanup adjacent set
  (`trace_cleanup`, `trace_cleanup_execute`, `cli_clean_trace`,
  `trace_session`, `state_consistency`): 95 passed
- `tests/test_errors.py`: 3 passed
- Full suite: 519 passed

### Review

- Claude review verdict: Approve
- Review range: `a0dffdd..379309f`
- Reviewer independently verified:
  - checkpoint content changes after planning make execute reject the plan even
    when trace line count and file size are unchanged,
  - Layer D protects current-trial trace lines from
    `current_trial_start_line` through trace end,
  - `current_trial_start_line` ahead of trace causes conservative refusal,
  - existing trace cleanup behavior remains compatible.

## Subtask 6.8 - NFS/FUSE Warning + LangGraph Reservation

Completed the final Phase 06 planned deliverable.

### Changes

- Added `src/agent/filesystem.py`.
- Added `/proc/self/mountinfo` parsing and longest-mount matching.
- Classified NFS/FUSE/remote-like filesystem types for runtime warnings.
- Added `RemoteFilesystemWarning`.
- `prepare_init_context()` now warns when the configured workspace appears to be
  on NFS/FUSE/remote-like storage.
- `WorkspaceLock.acquire()` now warns when the lock directory appears to be on
  NFS/FUSE/remote-like storage.
- Added a comment-only `CheckpointState` reservation for future Phase 9.0
  LangGraph state. The schema field is not added.

### Guardrails

- Remote filesystem detection is warning-only and does not block init or lock
  acquisition.
- `WorkspaceLock._write_holder()` remains unchanged and `run.lock` is not
  replaced.
- `langgraph_state_snapshot` remains rejected as an extra checkpoint field.

### Validation

- `tests/test_filesystem.py tests/test_workspace_lock.py tests/test_init.py tests/test_fs_memory.py`: 234 passed
- `tests/test_errors.py`: 3 passed
- Full suite: 538 passed

### Review

- Claude review verdict: Approve
- Review range: `2d7e657..c62954e`
- Reviewer independently verified:
  - NFS/FUSE/remote-like filesystem detection via injected mountinfo,
  - warning-only behavior for NFS paths,
  - graceful local and mountinfo-unavailable behavior,
  - `langgraph_state_snapshot` is still rejected by the strict checkpoint
    schema,
  - `_write_holder()` was untouched.

## Phase 06 Closure

- Status: done
- Closed at: 2026-06-03T15:44:39+08:00
- Actual patch-count subtasks: 10
- Final full suite: 540 passed
- Next phase: Phase 05 - Compile / Benchmark Skills

## Post-Close Blocker Fix - pre-Phase 05

Fixed two externally reviewed blockers before Phase 05 starts.

### Changes

- `cleanup_process_lease()` now filters mixed target sets by verdict before
  killing:
  - owned targets are killed when any owned target exists,
  - suspected targets are only killable through the suspected-only
    `force_suspected` path,
  - suspected targets are no longer killed just because another target in the
    same lease cleanup is owned.
- Added a real-process regression test with one owned recorded pid target and
  one same-session/different-pgid suspected target. The owned pgid is killed;
  the suspected process remains alive until fixture cleanup.
- Removed the old checkpoint invariant that forced
  `current_trial.process != None` for `compiling` / `benchmarking` stages.
- Kept `current_trial.process` as a deprecated compatibility field for old
  checkpoints.
- Added `CheckpointCurrentTrial.running_process_refs`, sourced from
  `operations` entries with `status="running"`.

### Validation

- `tests/test_process_cleaner.py`: 9 passed
- `tests/test_fs_memory.py`: 144 passed
- Full suite: 540 passed
