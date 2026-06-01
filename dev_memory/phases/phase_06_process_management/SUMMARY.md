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
