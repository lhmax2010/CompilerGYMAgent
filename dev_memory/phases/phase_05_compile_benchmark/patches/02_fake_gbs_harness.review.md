# Self Review - Phase 05 / Subtask 5.2

## Scope

This subtask adds the fake_gbs harness that later compile/benchmark skills will use before real gbs integration lands.

## Checks

- fake_gbs uses `process_runner.spawn_process()` for compile and benchmark; no function-level sleep/return mock.
- Worker subprocesses expose pid, pgid, and process env markers in result JSON.
- Compile success writes a real artifact and hash.
- Benchmark verifies and consumes the artifact.
- Failure modes are represented through real process behavior:
  - invalid option exits nonzero,
  - timeout is killed through cleaner/killpg,
  - crash signal exits via SIGSEGV,
  - OOM-like exits with 137,
  - artifact missing exits cleanly without artifact,
  - score parse failed exits zero without SCORE.
- Noise generation is seeded and reproducible.
- Bursty profile uses a Markov state machine with clustered degraded/failed samples.
- Tests leave no intentional residual process groups.

## Result

No known findings. Targeted, adjacent, and full test suites pass.

