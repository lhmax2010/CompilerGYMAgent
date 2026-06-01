# Phase 06 / Subtask 6.5 Self Review

## Scope

- Add checkpoint operation ledger model and validation.
- Keep existing checkpoint fields compatible.
- Do not implement resume, doctor, or clean trace Layer D behavior yet.

## Checks

- [x] Legacy checkpoints without `operations` still load.
- [x] New ledgers require `current_trial_start_line`.
- [x] Operation process refs must point at the process lease registry.
- [x] Operation process refs must match checkpoint session and trial ids.
- [x] Duplicate process refs are rejected.
- [x] Output refs reject absolute, parent, denormalized, and backslash paths.
- [x] Operation details are JSON-only.
- [x] Checkpoint write/load round-trips operation ledgers.
- [x] Full suite passes.

## Residual Risk

- This subtask defines the canonical data shape only. Replay policy, operation
  idempotency, state-consistency checks, and clean trace Layer D enforcement
  remain in later Phase 06/09/10 subtasks.
