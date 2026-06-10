# Phase 08a UT Results

## Pre-implementation

- Claude external design review for `f34c28d..6b72d43`: Approve, no Critical or
  High findings.
- Windows Python environment was later provisioned with `uv` and Python 3.11.

## Subtask 08a.1

- Implementation status: complete, review-alignment patch applied.
- Targeted tests added:
  - `tests/test_stats_core.py`,
  - new `RunSummaryHint` finite/count tests in `tests/test_result_schema.py`,
  - benchmark summary count/ESS assertions in `tests/test_benchmark_skill.py`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `48 passed, 5 skipped`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 554 passed, 51 skipped, 4 errors`.
  - Scope note: failures are existing Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Pending external/server run.
- Non-Python validation:
  - `git diff --check` -> passed, with only Windows CRLF conversion warnings.
- Claude static implementation review:
  - Verdict: Approve with follow-ups.
  - Critical/High findings: none.
  - Medium follow-ups were addressed in the working tree before this note.
- External review alignment:
  - ESS changed from lag-1-only to conservative min(lag-1, multi-lag ACF) for
    n>=8.
  - `ess_preliminary` added for n<8 lag-1 fallback.
  - 08a single-comparison/no-multiple-correction boundary recorded.
