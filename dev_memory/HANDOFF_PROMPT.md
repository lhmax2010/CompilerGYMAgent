# CompilerGYMAgent Server-Migration Handoff Prompt

Use this prompt when continuing development on another server.

```text
You are Codex taking over development of the CompilerGYMAgent repository.

Repository:
- GitHub: https://github.com/lhmax2010/CompilerGYMAgent.git
- Branch: main
- Expected HEAD after `git pull --ff-only origin main`: the latest 08a closeout
  commit on `origin/main`. Verify with `git log --oneline -8`.

Start with:
1. `git pull --ff-only origin main`
2. `git status --short --branch`  # should be clean
3. `git log --oneline -8`
4. Read:
   - `dev_memory/CURRENT_PHASE.yaml`
   - `dev_memory/PROGRESS.md` top entries
   - `dev_memory/ROADMAP.md`
   - `dev_memory/ROADMAP.yaml`
   - `dev_memory/DECISIONS.md` entries from 2026-06-05 onward
   - `dev_memory/BLOCKERS.md`
   - `dev_memory/phases/phase_08a_statistics_core/SUMMARY.md`
   - `dev_memory/phases/phase_08a_statistics_core/UT_RESULTS.md`

Current status:
- Completed production phases: 01, 02, 03, 04, 06, 05, 08a.
- Phase 05.5 integration spike is done, but remains in planned phases because
  it is a spike, not a completed milestone.
- Phase 05 Compile / Benchmark Skills is closed.
- Phase 08a Minimal Stats Core is closed. It delivered descriptive statistics,
  conservative ESS/autocorrelation diagnostics, IID and moving-block bootstrap,
  `StatisticalResult` verdict gates, fixed-seed coverage regressions,
  `exploratory_signal`, and hardened `pair_quality`.
- 08a pair_quality went through eight adversarial review rounds plus numerical
  validation. Detectable time-metadata inconsistency and global-duration
  coupling paths are closed. The only remaining boundary is fully
  self-consistent forged time metadata with no physical/statistical fingerprint.
- Real target runtime is Python 3.10. The compatibility patch lowers
  `requires-python` to `>=3.10` and removes 3.11-only `datetime.UTC`,
  `typing.Self`, and `tomllib` assumptions.
- `tests/__init__.py` is required so Ubuntu/Python 3.10 resolves absolute
  `tests.fixtures` imports to this repository instead of an unrelated installed
  `tests` package.
- `dev_memory/BLOCKERS.md` currently records no active blockers.

Latest important commits:
- `b5dd98b phase_08a: use per-pair duration for pair gaps`
- `16e106f phase_08a: detect merged pair timeline overlap`
- `a156c12 phase_08a: detect paired run time overlap`
- `93d726a phase_08a: bound pair duration threshold by timestamps`
- `ca92868 phase_08a: harden pair time gap validation`
- `00875f2 phase_08a: harden pair quality and exploratory signals`
- `8c95109 phase_08a: record exploratory signal design`
- `e594eb4 phase_08a: harden statistical ordering and coverage`
- `9dba60b dev_memory: record 08a.5 statistical review`

Recent Phase 05/08a preconditions already handled:
- Phase 05 emits process-backed compile/benchmark records.
- fake_gbs runs through the real process runner and supports gaussian,
  right-skewed, and bursty Markov noise.
- RunLevelRecord and FailureClassification schemas are in place.
- NaN/Inf score and float hygiene blockers were fixed before 08a.
- Benchmark failures never write `failed_combos` in Phase 05/08a.
- Valid scoring runs require verified artifact hashes.
- `write_failed_combos=True` requires HIGH confidence, option_related route,
  and non-empty affected_options.

Current next action:
- Start Phase 7.0 Candidate Engine Search Strategy + Constraint Solver Spike.
- Consume the 08a `StatisticalResult` contract strictly:
  - decision-grade accept/reject/promote requires good paired evidence or
    otherwise valid IID single-comparison evidence,
  - unpaired autocorrelation remains inconclusive,
  - `exploratory_signal` can only propose/prioritize/schedule confirmation.
- Define randomized AB/BA paired measurement plans that produce truthful
  `pair_order`, `started_at`, `ended_at`, `duration_sec`, and
  `pair_time_gap_sec`.
- Explicitly forbid sequential testing/peeking until Phase 08b/07 policy exists;
  multiple-comparison correction belongs to Phase 07.
- Carry non-blocking 08b follow-ups: `env_snapshot_distance` or equivalent
  cross-signal pair-quality evidence, cosmetic `pair_order` vs `started_at`
  cross-check, and calibration of the 5x/300s/5s pair-quality knobs.

Validation expectations:
- Run targeted tests for the phase being changed.
- Run full suite before commit.
- Preserve the established dev_memory workflow:
  - update CURRENT_PHASE.yaml,
  - append PROGRESS.md,
  - update phase CHECKLIST/UT_RESULTS/REVIEW_NOTES/SUMMARY as applicable,
  - generate patch triplet,
  - commit, push, send Claude review range.

Known useful commands:
- `git status --short --branch`
- `git log --oneline -8`
- `python - <<'PY'
  import yaml
  from pathlib import Path
  yaml.safe_load(Path("dev_memory/ROADMAP.yaml").read_text())
  yaml.safe_load(Path("dev_memory/CURRENT_PHASE.yaml").read_text())
  PY`
- `uv run --python 3.10 --system-certs --extra dev pytest tests/test_stats_core.py tests/test_result_schema.py tests/test_benchmark_skill.py -q`
- `uv run --python 3.10 --system-certs --extra dev pytest tests/ -q`
- `git diff --check`

Important guardrails:
- Do not modify `doc/REQUIREMENTS.md` unless explicitly instructed.
- Do not start Phase 07 candidate engine before 08a and 7.0 are ready.
- Do not regress Phase 06 process-cleaning safety.
- Do not reintroduce benchmark NaN/Inf acceptance.
- Do not let benchmark failures write `failed_combos` in Phase 05/08a.
- Use `apply_patch` for manual edits and `rg` for search.
- If push fails with an HTTP/2 empty reply, retry:
  `git -c http.version=HTTP/1.1 push origin HEAD:main`
```
