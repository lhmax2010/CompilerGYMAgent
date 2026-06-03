# Phase 06 / Post-Close Blocker Fix Self Review

## Scope

- External-review blocker 1: `cleanup_process_lease()` must not kill suspected
  targets merely because another target in the same scan is owned.
- External-review blocker 2: the operation ledger must be the active process
  authority; deprecated `current_trial.process` must remain optional for
  compatibility.

## Checks

- [x] Mixed target sets are filtered by verdict before killpg.
- [x] Owned targets remain killable.
- [x] Suspected targets are not carried along when an owned target exists.
- [x] Existing suspected-only default skip and `force_suspected=True` behavior
  remains covered.
- [x] The mixed-verdict regression uses real subprocesses:
  one recorded owned process plus one same-session/different-pgid suspected
  process.
- [x] Deprecated `current_trial.process` can be absent with
  `current_stage="compiling"`.
- [x] Legacy checkpoints that still include `current_trial.process` remain
  accepted.
- [x] Running process references are sourced from operation ledger entries with
  `status="running"`.
- [x] Targeted and full test suites pass.

## Residual Risk

- Phase 05 should not reintroduce `current_trial.process` as a second source of
  process authority. Compile and benchmark skills should attach process leases
  through operation `process_refs`.

## Review Focus

- Confirm that the mixed target regression would have failed under the old
  kill-all-targets behavior.
- Confirm that removing the `current_stage` -> old `process` invariant does not
  break legacy checkpoint loading.
