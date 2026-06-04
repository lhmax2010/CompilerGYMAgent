# Phase 05 UT Results

## Subtask 5.1

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_process_identity.py tests/test_process_registry.py tests/test_process_runner.py tests/test_process_cleaner.py -q`
  - Result: 44 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 550 passed, 0 failed

## Subtask 5.2

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_fake_gbs.py -q`
  - Result: 9 passed, 0 failed
- Adjacent:
  - Command: `.venv/bin/python -m pytest tests/test_fake_gbs.py tests/test_process_runner.py tests/test_process_cleaner.py -q`
  - Result: 28 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 559 passed, 0 failed
- Bursty probe:
  - `FakeGbsNoiseModel(seed=31)` over 100 bursty samples produced healthy=57, degraded=33, failed=10 with 31 adjacent non-healthy transitions.

## Subtask 5.5a

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_result_schema.py -q`
  - Result: 19 passed, 0 failed
- Adjacent:
  - Command: `.venv/bin/python -m pytest tests/test_fake_gbs.py tests/test_result_schema.py -q`
  - Result: 28 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 578 passed, 0 failed

## Subtask 5.3

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_compile_skill.py -q`
  - Result: 3 passed, 0 failed
- Adjacent:
  - Command: `.venv/bin/python -m pytest tests/test_compile_skill.py tests/test_fake_gbs.py tests/test_spec_skills.py tests/test_workspace_skills.py tests/test_process_runner.py tests/test_process_cleaner.py -q`
  - Result: 55 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 581 passed, 0 failed

## Subtask 5.4

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_benchmark_skill.py -q`
  - Result: 4 passed, 0 failed
- Adjacent:
  - Command: `.venv/bin/python -m pytest tests/test_benchmark_skill.py tests/test_compile_skill.py tests/test_fake_gbs.py tests/test_result_schema.py tests/test_process_runner.py tests/test_process_cleaner.py -q`
  - Result: 54 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 585 passed, 0 failed

## Subtask 5.5b

- Targeted:
  - Command: `.venv/bin/python -m pytest tests/test_error_analyzer.py -q`
  - Result: 9 passed, 0 failed
- Adjacent:
  - Command: `.venv/bin/python -m pytest tests/test_error_analyzer.py tests/test_compile_skill.py tests/test_benchmark_skill.py tests/test_result_schema.py tests/test_fake_gbs.py -q`
  - Result: 44 passed, 0 failed
- Full:
  - Command: `.venv/bin/python -m pytest tests/ -q`
  - Result: 594 passed, 0 failed
