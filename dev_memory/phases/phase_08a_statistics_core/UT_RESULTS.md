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
  - Environment: Ubuntu/Linux server, Python 3.11 via `uv sync`.
  - Head: `ee0fe4b77cf546bcea170734464265980481842a`.
  - Targeted command: `python -m pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `53 passed in 0.83s`.
  - Full command: `python -m pytest tests/ -q`
  - Full result: `631 passed in 7.70s`.
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

## Subtask 08a.2

- Implementation status: complete locally, pending external coverage-simulation
  review and Ubuntu validation.
- Added tests:
  - seeded reproducibility and deterministic percentile CI output,
  - single-sample bootstrap boundary,
  - IID Gaussian and right-skewed exponential coverage smoke tests,
  - invalid empty/non-finite/confidence/B inputs.
- Local stats-core validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py -q`
  - Result: `13 passed in 1.26s`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `52 passed, 5 skipped in 1.30s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 558 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Linux container full suite passed at
    `457caa46d5597da9b010e3f8e20920695facef8e`.
  - Full result: `635 passed`.
  - Scope note: full Linux pass confirms the Windows full-suite failures are
    existing platform-sensitive non-08a paths, not 08a.2 regressions.
- External coverage-simulation review:
  - IID gaussian 95% CI coverage: n=20 -> 94.8%, n=50 -> 93.8%.
  - Right-skewed lognormal coverage: n=30 -> 92.0%, n=60 -> 93.2%.
  - Seeded reproducibility, different-seed behavior, normal CI bounds, and
    small-sample behavior all passed.

## Subtask 08a.3

- Implementation status: complete locally, pending external numerical review
  and Ubuntu validation.
- Added tests:
  - high lag-1 autocorrelation detection (`rho1 > 0.3`),
  - weak positive autocorrelation below threshold,
  - IID bootstrap CI diagnostics without changing method,
  - `RunSummaryHint` diagnostic fields,
  - invalid diagnostic inputs.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `57 passed, 5 skipped in 1.35s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 563 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Ubuntu validation:
  - Environment: Ubuntu/Linux server, Python 3.11 via `uv sync --extra dev`.
  - Head: `12ac2bb`.
  - Targeted command: `python -m pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `62 passed in 1.49s`.
  - Full command: `python -m pytest tests/ -q`
  - Full result: `640 passed in 9.24s`.
- External statistical correctness review:
  - Range: `aafa406..12ac2bb`.
  - Verdict: approve, no Critical/High/Medium/Low findings.
  - Autocorrelation threshold check passed for phi=0.2 vs phi=0.5/0.7.
  - Naive IID bootstrap control coverage: 95.0%/93.4% on IID gaussian.
  - Naive IID bootstrap bursty coverage: 73.0%/74.4%, establishing the
    08a.4 moving-block-bootstrap comparison baseline.

## Subtask 08a.4

- Implementation status: complete locally, pending full Windows validation,
  external bursty coverage review, and Ubuntu validation.
- Added tests:
  - block-size formula, rho correlation length, n//2 cap, and n<=5 no-block,
  - moving-block seeded reproducibility and method/block_size metadata,
  - contiguous-block resampling behavior,
  - autocorrelation-aware method selection,
  - weak-autocorrelation and small-sample IID fallback,
  - invalid moving-block inputs.
- Local stats-core validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py -q`
  - Result: `23 passed in 1.37s`.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `63 passed, 5 skipped in 1.37s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 569 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Linux validation:
  - Full result from external review: `646 passed` at `338232b`.
- External statistical correctness review:
  - Range: `5957109..338232b`.
  - Verdict: approve with finding, one Medium follow-up.
  - Moving block improved fake_gbs bursty coverage over naive IID but remained
    below 90% at smaller n; carry low-power/inconclusive handling into 08a.5.

## Subtask 08a.5

- Implementation status: complete locally, pending full Windows validation,
  external Med-1 verdict-gate review, and Ubuntu validation.
- Added tests:
  - `StatisticalResult` schema accepts single-comparison result fields,
  - schema rejects inconsistent `significant_single_comparison` and
    multiple-testing adjustment,
  - significant single-comparison output for adequately powered improvement,
  - lower-is-better direction sign,
  - adequate-power `no_difference` vs low-power `inconclusive`,
  - baseline approximately zero relative-effect defense,
  - n_valid <5 and 5<=n_valid<10 power gates,
  - ESS<3 and 3<=ESS<5 power gates,
  - Med-1 small-n autocorrelated paired data blocked from significance,
  - paired difference autocorrelation diagnostics,
  - unpaired high autocorrelation marked inconclusive.
- Targeted local validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Result: `75 passed, 5 skipped in 1.43s`.
- Full Windows validation:
  - Command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Result: `24 failed, 581 passed, 51 skipped, 4 errors`.
  - Scope note: failures are the known Windows/platform-sensitive paths outside
    08a, concentrated in clean-trace CLI, filesystem mount inspection,
    process registry/state consistency, and trace cleanup tests.
- Python 3.10 compatibility validation:
  - Command: `.venv\Scripts\uv.exe run --python 3.10 --system-certs --extra dev python -c "import sys; print(sys.version)"`
  - Result: CPython 3.10.20 installed/used; `.venv` recreated for Python 3.10.
  - Targeted command: `.venv\Scripts\python.exe -m pytest tests\test_stats_core.py tests\test_result_schema.py tests\test_benchmark_skill.py -q`
  - Targeted result: `75 passed, 5 skipped in 3.10s`.
  - Full command: `.venv\Scripts\python.exe -m pytest tests\ -q`
  - Full result: `24 failed, 581 passed, 51 skipped, 4 errors`.
  - Scope note: the full suite now collects and runs under Python 3.10 without
    the previous `datetime.UTC` / `typing.Self` / `tomllib` ImportError.
  - Follow-up collection fix: added `tests/__init__.py` so absolute
    `tests.fixtures` imports resolve to this repository on Ubuntu/Python 3.10.
  - Collection smoke:
    `.venv\Scripts\python.exe -m pytest --collect-only tests\test_benchmark_skill.py tests\test_compile_skill.py tests\test_fake_gbs.py -q`
    -> 22 tests collected, no `tests` import error.
- Ubuntu Python 3.10 validation:
  - Head: `b78c744`.
  - Pull: `git pull --ff-only origin main` fast-forwarded `0c87bb3..b78c744`.
  - Targeted command: `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
  - Targeted result: `80 passed in 1.00s`.
  - Full command: `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
  - Full result: `658 passed in 7.56s`.
- Review gate:
  - External numerical review should stress Med-1 cases where block-bootstrap
    coverage remains below nominal and confirm the verdict remains
    low_power/inconclusive, not significant.
  - Ubuntu validation remains required because Windows full-suite failures are
    known platform-sensitive non-08a paths.
