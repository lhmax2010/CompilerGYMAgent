# Phase 06 / Post-Close Blocker Hardening Self Review

## Scope

- External-review hardening 1: define `force_suspected=True` as "kill owned
  plus suspected" for mixed cleanup targets.
- External-review hardening 2: prevent one process lease from being referenced
  by multiple current-trial operations.

## Checks

- [x] Default mixed target cleanup remains conservative and kills only owned
  targets.
- [x] Forced mixed target cleanup kills owned and suspected targets.
- [x] Suspected-only forced cleanup remains covered by existing tests.
- [x] Cross-operation duplicate process_refs are rejected.
- [x] Single-operation duplicate process_refs remain rejected.
- [x] Targeted and full test suites pass.

## Residual Risk

- Phase 05 marker refinement should narrow suspected discovery to trial/lease
  granularity. The force behavior here is the operator escape hatch when
  suspected process cleanup is intentionally requested.

## Review Focus

- Confirm semantic choice 2: force cleanup means owned + suspected targets are
  killed.
- Confirm global operation process_ref uniqueness matches resume/doctor/cleanup
  assumptions.
