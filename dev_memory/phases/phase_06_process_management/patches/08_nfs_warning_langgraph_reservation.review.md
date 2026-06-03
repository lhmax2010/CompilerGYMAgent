# Phase 06 / Subtask 6.8 Self Review

## Scope

- Runtime warning for unvalidated workspace filesystem types.
- Comment-only LangGraph checkpoint reservation.
- No process cleanup, no workspace-lock write-path changes, and no checkpoint
  schema expansion.

## Checks

- [x] Mount inspection is read-only and parses Linux `/proc/self/mountinfo`.
- [x] Longest mount-point match is selected for nested mounts.
- [x] NFS/FUSE/remote-like filesystem types emit `RemoteFilesystemWarning`.
- [x] ext4/xfs/btrfs/overlay/tmpfs are treated as local-like and do not warn.
- [x] `agent init` calls the warning helper and continues.
- [x] `WorkspaceLock.acquire()` calls the warning helper and continues.
- [x] Warning behavior is nonblocking.
- [x] `WorkspaceLock._write_holder()` is unchanged; `run.lock` is never
  atomic-replaced.
- [x] `CheckpointState` only has a comment reservation for
  `langgraph_state_snapshot`.
- [x] `langgraph_state_snapshot` remains rejected as an extra checkpoint field.
- [x] Targeted and full test suites pass.

## Residual Risk

- Filesystem classification is heuristic. It makes the v1 local-filesystem
  assumption visible but does not prove exact lock/fsync semantics for every
  mount implementation.
- Future CLI/doctor layers can render the warning more prominently.
