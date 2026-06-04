# Phase 06 UT Results

## Subtask 6.1 - Process Identity + process_lab

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_identity.py -q
.venv/bin/python -m pytest tests/test_process_lab.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_identity.py`: 13 passed
- `tests/test_process_lab.py`: 7 passed
- Full suite: 471 passed

Notes:

- `test_process_lab.py` is marked POSIX-only because it exercises real process
  groups and `killpg`.
- process_lab tests were run on Linux in the local environment.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `dce83d2..2ff1342`
- Re-run targeted tests: 20 passed
- Re-run full suite: 471 passed
- Independent reviewer probe: seven process_lab scenarios reproducible; 0
  residual processes after cleanup.

## Subtask 6.2 - Process Runner + Process Lease Registry

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_registry.py -q
.venv/bin/python -m pytest tests/test_process_runner.py -q
.venv/bin/python -m pytest tests/test_errors.py tests/test_process_identity.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_registry.py`: 7 passed
- `tests/test_process_runner.py`: 6 passed
- `tests/test_errors.py tests/test_process_identity.py`: 16 passed
- Full suite: 484 passed

Notes:

- `test_process_runner.py` is POSIX-only because it checks real
  `start_new_session` / process-group behavior.
- A concurrent validation run exposed a spawn-time env visibility race; after
  adding a short retry in `process_runner`, targeted runner tests and the full
  suite passed consistently.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `7a6a6f9..e55a79d`
- Hardening range: `e55a79d..d38567e`
- Re-run targeted tests: 29 passed
- Re-run full suite: 484 passed
- Follow-up: 6.3 cleaner must use single-read env marker probing.

## Subtask 6.3 - Process Cleaner

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_cleaner.py -q
.venv/bin/python -m pytest tests/test_process_cleaner.py tests/test_process_registry.py tests/test_process_runner.py tests/test_process_lab.py tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_cleaner.py`: 8 passed
- Cleaner adjacent target set: 31 passed
- Full suite: 492 passed

Notes:

- Tests exercise real process groups for owned cleanup, leader-dead child
  cleanup, and double-fork-style env-marker discovery.
- Cleaner env marker reads are intentionally single-shot to avoid scanning
  arbitrary external processes with runner-style retry delays.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `1f2bf61..ca9373a`
- Re-run targeted cleaner-adjacent tests: 31 passed
- Re-run full suite: 492 passed
- Independent reviewer probe: graded scoring, leader-dead pgid scan,
  double-fork env scan, conservative env-missing behavior, owned killpg, and
  lease GC all matched the Phase 06 design.

## Subtask 6.4 - Workspace Lock Probe + LockStatus unknown

Commands:

```bash
.venv/bin/python -m pytest tests/test_workspace_lock.py tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py -q
.venv/bin/python -m pytest tests/test_cli_clean_trace.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- Lock / trace cleanup targeted tests: 68 passed
- CLI clean trace smoke/regression tests: 10 passed
- Full suite: 496 passed

Notes:

- Targeted tests cover free probe, busy probe, unknown lock metadata,
  released-but-live holder metadata, held_by_self, and held_by_other using real
  active flock state.
- `run.lock` is never atomic-replaced; `_write_holder()` remains unchanged.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `2b07a88..03ca715`
- Re-run targeted lock/cleanup/CLI tests: 78 passed
- Re-run full suite: 496 passed
- Independent reviewer probe: free/busy flock probing, released-but-live
  metadata, unknown refusal, and never-`os.replace(run.lock)` all matched the
  Phase 06 design.

## Subtask 6.5 - TrialState Operation Ledger

Commands:

```bash
.venv/bin/python -m pytest tests/test_fs_memory.py tests/test_identifiers.py -q
.venv/bin/python -m pytest tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- Checkpoint / identifier targeted tests: 164 passed
- Error framework smoke: 3 passed
- Full suite: 508 passed

Notes:

- Targeted tests cover legacy checkpoint migration, operation ledger acceptance,
  required `current_trial_start_line`, YAML round-trip, unsafe process refs,
  session/trial mismatch, duplicate refs, and JSON-only operation details.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `eef6b02..4bde11a`
- Re-run checkpoint/identifier targeted tests: 164 passed
- Re-run process_lab/process_cleaner targeted tests after flaky hardening: 15 passed
- Re-run process suite stress loop after atomic JSON IPC hardening:
  20/20 iterations passed
- Re-run double-fork stress loop after atomic JSON IPC hardening: 50/50 passed
- Re-run full suite: 508 passed
- Low-1 flaky resolved by making process_lab worker/grandchild JSON IPC atomic
  (`temp` + `os.replace`) and by waiting for JSON payloads to parse
  successfully before reading them. The earlier timeout-only hardening was not
  sufficient under process-suite load because it still allowed a reader to see
  a half-written JSON file.

## Subtask 6.6 - doctor/state_consistency.py

Commands:

```bash
.venv/bin/python -m pytest tests/test_state_consistency.py -q
.venv/bin/python -m pytest tests/test_errors.py -q
.venv/bin/python -m pytest tests/test_state_consistency.py tests/test_trace_session.py tests/test_process_registry.py tests/test_fs_memory.py tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_state_consistency.py`: 7 passed
- `tests/test_errors.py`: 3 passed
- Adjacent targeted set: 203 passed
- Full suite: 515 passed

Notes:

- Targeted tests cover a healthy checkpoint/trace/lease state, trace-ahead and
  checkpoint-ahead alignment findings, missing process refs, operation/lease
  status mismatch, orphan leases, current-trial trace mismatch, and malformed
  lease diagnostics.
- The validator is read-only and does not mutate checkpoint, trace, leases, or
  processes.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `a196c52..b109e45`
- Re-run full suite: 515 passed
- Independent reviewer probe: clean/read-only state, dangling process refs,
  orphan leases, malformed lease YAML, operation/lease mismatch, and
  repair_suggestion fields all matched the 6.6 contract.

## Subtask 6.7 - Clean Trace Hardening

Commands:

```bash
.venv/bin/python -m pytest tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py -q
.venv/bin/python -m pytest tests/test_trace_cleanup.py tests/test_trace_cleanup_execute.py tests/test_cli_clean_trace.py tests/test_trace_session.py tests/test_state_consistency.py -q
.venv/bin/python -m pytest tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- Trace cleanup targeted tests: 34 passed
- Trace/cleanup adjacent set: 95 passed
- Error framework smoke: 3 passed
- Full suite: 519 passed

Notes:

- New tests cover Layer D current-trial protection, refusal when
  `current_trial_start_line` is ahead of trace, stale checkpoint hash detection,
  and protected-session hash detection with unchanged trace line count/file
  size.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `a0dffdd..379309f`
- Independent reviewer probe: checkpoint hash staleness, Layer D current-trial
  range protection, start-line-ahead refusal, and no-current-trial
  compatibility all matched the 6.7 contract.
- Re-run trace cleanup targeted set: 34 passed
- Re-run adjacent targeted set: 95 passed
- Re-run full suite: 519 passed

## Subtask 6.8 - NFS/FUSE Warning + LangGraph Reservation

Commands:

```bash
.venv/bin/python -m pytest tests/test_filesystem.py tests/test_workspace_lock.py tests/test_init.py tests/test_fs_memory.py -q
.venv/bin/python -m pytest tests/test_errors.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- Filesystem / workspace lock / init / fs_memory targeted set: 234 passed
- Error framework smoke: 3 passed
- Full suite: 538 passed

Notes:

- Targeted tests cover NFS/FUSE/remote-like type classification, mountinfo
  longest-match parsing, nonblocking warning behavior, init warning hook,
  workspace lock warning hook, and strict rejection of the reserved
  `langgraph_state_snapshot` field.

Review / validation sync:

- Claude review verdict: Approve
- Review range: `2d7e657..c62954e`
- Independent reviewer probe: injected NFS mountinfo detection, local filesystem
  non-warning, warning-only behavior, missing mountinfo graceful fallback, and
  strict `langgraph_state_snapshot` rejection all matched the 6.8 contract.
- Re-run targeted set: 234 passed
- Re-run full suite: 538 passed

## Phase 06 Closure

- Final full suite: 542 passed
- Actual patch-count subtasks: 11
- Ubuntu/Linux validation: passed

## Post-Close Blocker Fix - pre-Phase 05

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_cleaner.py -q
.venv/bin/python -m pytest tests/test_fs_memory.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_cleaner.py`: 9 passed
- `tests/test_fs_memory.py`: 144 passed
- Full suite: 540 passed

Notes:

- Process cleaner regression covers a mixed target set containing one owned
  target plus one same-session suspected target. The cleanup kills only the
  owned pgid; the suspected process remains alive until fixture cleanup.
- Checkpoint regression covers deprecated `current_trial.process` absence for
  an active `current_stage` and verifies running process refs are sourced from
  operation ledger entries.

## Post-Close Blocker Hardening - pre-Phase 05

Commands:

```bash
.venv/bin/python -m pytest tests/test_process_cleaner.py -q
.venv/bin/python -m pytest tests/test_fs_memory.py -q
.venv/bin/python -m pytest tests/ -q
```

Results:

- `tests/test_process_cleaner.py`: 10 passed
- `tests/test_fs_memory.py`: 145 passed
- Full suite: 542 passed

Notes:

- Process cleaner tests now lock the three force semantics:
  default mixed owned+suspected kills only owned, forced mixed kills both, and
  suspected-only force kills suspected.
- Checkpoint tests now reject duplicate lease refs across different operations.
