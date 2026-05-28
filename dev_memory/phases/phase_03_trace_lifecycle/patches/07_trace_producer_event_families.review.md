# Phase 03 / Subtask 3.5 Self Review

## Scope

- Strengthen rejected-candidate trace producers before the candidate engine
  owns real filtering decisions.
- Add workflow-facing helpers for the remaining trace event families that later
  process, memory, KG, user-command, and workspace workflows will call.
- Preserve the low-level trace storage boundary.

## Checklist

- [x] `candidate_rejected()` requires `generator`.
- [x] Rejection reasons are limited to the documented reason set.
- [x] Each rejection reason requires its documented matched-reference fields.
- [x] Experience hard filters require `filter_strength: hard`.
- [x] Experience soft filters require `filter_strength: soft`, finite
  `penalty`, and finite `score_after_penalty`.
- [x] Runtime event helpers cover process, LLM, memory, KG, user action, and
  workspace snapshot events.
- [x] No new public symbols were exported from `agent.__init__`.

## Notes

- The storage primitive remains strict-common/open-payload. It still only knows
  how to validate JSONL safety and event common fields.
- Candidate rejection semantics now live at the producer layer, where the
  constraint layer will eventually call them.
- The runtime event helpers intentionally stay lightweight. Detailed process,
  KG, clean, and user-command schemas should be introduced alongside those
  workflow modules rather than guessed here.

## Tests

- `.venv\Scripts\python.exe -m pytest tests/test_trace_session.py -v` -> 26 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_trace_memory.py -q` -> 22 passed.
- `.venv\Scripts\python.exe -m pytest tests/test_fs_memory.py -q` -> 130 passed.
- `.venv\Scripts\python.exe -m pytest -q` -> 336 passed, 1 skipped on Windows.

## Review Conclusion

Subtask 3.5 is ready for external review and Ubuntu validation. The main
review focus should be whether the rejected-candidate field matrix is strict
enough without over-constraining non-rule rejection reasons.
