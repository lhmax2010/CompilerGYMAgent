# Subtask 3.10 Self Review - Trace Clean Plan Computation

## Scope

- Add a read-only plan computation layer for future `agent clean trace`.
- Combine the section 4.14.7a protection data produced by earlier subtasks.
- Do not implement physical cleanup, CLI, lock acquisition, or file mutation.

## Checklist

- [x] `compute_clean_plan()` performs read-only IO only.
- [x] `CleanPlan` is pure data with execution predicates for later CLI/executor use.
- [x] Session protection reuses `inspect_trace_session_spans()` from Subtask 3.9.
- [x] Checkpoint-after protection uses `checkpoint.trace_line_count`.
- [x] Workspace lock status is read from holder metadata without acquiring the lock.
- [x] `held_by_other` returns a complete plan plus a refusal reason.
- [x] `held_by_self` allows future `--force-clean-inactive-only` execution through the plan predicate.
- [x] Removable byte ranges round-trip through a skip-and-reload test.
- [x] Empty trace and missing checkpoint cases return a valid empty plan.
- [x] No CLI or physical rewrite code was introduced.

## Validation

- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup.py -q` -> 14 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_trace_cleanup.py tests/test_trace_session.py tests/test_trace_memory.py -q` -> 80 passed.
- `uv run --python 3.11 --extra dev pytest tests/test_fs_memory.py tests/test_workspace_lock.py tests/test_identifiers.py -q` -> 181 passed.
- `uv run --python 3.11 --extra dev pytest -q` -> 393 passed.

## Notes

- The planner refuses execution if checkpoint `trace_line_count` is ahead of the validated trace line count, because that can indicate trace truncation or data loss.
- Byte ranges are computed from validated events plus raw physical line lengths, keeping validation and rewrite metadata tied to the same canonical file content.
- Subtask 3.11 should own lock acquisition, trash/rewrite mechanics, and CLI behavior.
