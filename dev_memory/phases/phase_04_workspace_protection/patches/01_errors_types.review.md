# Self Review - Subtask 4.1 AgentError + TypeAlias

## Scope

This patch intentionally limits itself to shared error/type infrastructure:

- new `src/agent/errors.py`
- new `src/agent/types.py`
- existing exception inheritance and class-level `exit_code`
- public exports
- tests and dev_memory updates

No business logic, CLI formatting, workspace-lock mechanics, trace cleanup
predicates, or persistence behavior changed.

## Checks

- Existing error messages and trigger conditions remain untouched.
- `AgentError` inherits `RuntimeError` so previous broad catches continue to work.
- Specific exit-code categories are assigned where the current hierarchy already
  expresses the distinction:
  - validation: config/registry/init load/checkpoint/trace base validation
  - integrity: trial/learned-rule/experience integrity errors
  - stale: trial index and stale clean plan
  - lock busy: `WorkspaceBusyError`
  - execution refused: immutable/exists/init-aborted/clean-refused paths
- Type aliases use `TypeAlias`, not `NewType`, to avoid runtime/serialization friction.
- CLI behavior is left for the Phase 04 dispatcher and Phase 10 formatting work.

## Residual Risk

Exit-code category assignment is a policy surface. The implementation picks
conservative mappings from the existing hierarchy, but reviewer confirmation is
useful before later CLI dispatch starts relying on them.
