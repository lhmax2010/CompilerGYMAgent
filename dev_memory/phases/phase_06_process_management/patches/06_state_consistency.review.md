# Phase 06 / Subtask 6.6 Self Review

## Scope

- Adds the read-only state consistency validator that later doctor CLI output
  can render.
- Does not mutate checkpoint, trace, process leases, or live processes.

## Checks

- [x] Reuses 3.8 trace/checkpoint alignment helper.
- [x] Reuses 3.9 trace session span helper.
- [x] Reports checkpoint load failures as structured findings.
- [x] Reports malformed process leases without aborting valid lease inspection.
- [x] Checks current_trial_start_line against trace line content.
- [x] Checks operation process_refs for missing leases.
- [x] Checks operation status vs lease status.
- [x] Reports orphan leases with severity based on lease status.
- [x] Exports public doctor symbols.
- [x] Targeted and full test suites pass.

## Residual Risk

- The validator intentionally diagnoses only. Actual repair flows, lock
  acquisition, force flags, and user-facing doctor output remain Phase 10 scope.
- Layer D clean trace protection remains 6.7 scope; this subtask only validates
  the checkpoint anchor that Layer D will consume.
