# CompilerGYMAgent Server-Migration Handoff Prompt

Use this prompt when continuing development on another server.

```text
You are Codex taking over development of the CompilerGYMAgent repository.

Repository:
- GitHub: https://github.com/lhmax2010/CompilerGYMAgent.git
- Branch: main
- Expected HEAD after `git pull --ff-only origin main`: at least
  `6b72d43 dev_memory: finalize 08a statistics core design`
- This handoff document may be newer than that commit; if so, trust the newer
  handoff commit and verify `git log --oneline -5`.

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
   - `dev_memory/phases/phase_05_compile_benchmark/SUMMARY.md`

Current status:
- Completed production phases: 01, 02, 03, 04, 06, 05.
- Phase 05.5 integration spike is done, but remains in planned phases because
  it is a spike, not a completed milestone.
- Phase 05 Compile / Benchmark Skills is closed.
- Phase 08a design has been finalized in `dev_memory/ROADMAP.yaml` and
  `dev_memory/DECISIONS.md`.
- Phase 08a.1 through 08a.4 are implemented and externally/numerically
  reviewed. 08a.4 was approved with Med-1: moving block bootstrap improves
  bursty coverage but smaller-n bursty cases remain underpowered.
- Phase 08a.5 StatisticalResult/verdict gates are implemented and
  Ubuntu/Python 3.10 validated. External Med-1 verdict-gate review is pending.
- Real target runtime is Python 3.10. The compatibility patch lowers
  `requires-python` to `>=3.10` and removes 3.11-only `datetime.UTC`,
  `typing.Self`, and `tomllib` assumptions.
- `tests/__init__.py` is required so Ubuntu/Python 3.10 resolves absolute
  `tests.fixtures` imports to this repository instead of an unrelated installed
  `tests` package.
- `dev_memory/BLOCKERS.md` currently records no active blockers.

Latest important commits:
- `4fbd199 dev_memory: add 08a.5 handoff`
- `7087463 dev_memory: record 08a.5 ubuntu validation`
- `b78c744 tests: package fixtures for python 3.10 collection`
- `0c87bb3 compat: support python 3.10 runtime`
- `8b46a4c dev_memory: record 08a.5 implementation`
- `8936849 phase_08a: add statistical result verdict gates`
- `995ebf3 dev_memory: record 08a.4 statistical review`

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
- Request external review for range `995ebf3..7087463`.
- External review should focus on Med-1 safety: small-n/severe-bursty cases
  where CI coverage remains below nominal must be low_power/inconclusive, not
  significant.
- Ubuntu/Python 3.10 validation has passed at `b78c744`: targeted 80 passed,
  full 658 passed.

Phase 08a current subtask:
- 08a.5 baseline-normalized comparison + pair_key paired design +
  StatisticalResult verdict schema.
- Preserve pure statistics scope: no process cleanup, no workspace mutation,
  no multiple-comparison correction, no adaptive rerun action, no outlier
  policy, and no candidate engine changes.
- 08a consumes Phase 05 `RunLevelRecord` values only.
- Main technical risk remains bursty/autocorrelated benchmark noise. Do not
  treat naive IID-only significance as sufficient.

Phase 08a design requirements to preserve:
- IID/right-skewed percentile bootstrap must be seeded and reproducible.
- Lag-1 autocorrelation must drive ESS correction.
- ESS below ESS_MIN defaults to inconclusive, never significant.
- Autocorrelated data uses moving block bootstrap, not naive IID bootstrap.
- pair_key paired comparisons are preferred when available.
- Unpaired high-autocorrelation comparisons should be downgraded or
  inconclusive.
- fake_gbs bursty state exposure is deferred to 08a.6.

Validation expectations:
- Run targeted tests for each 08a subtask.
- Run full suite before commit.
- Preserve the established dev_memory workflow:
  - update CURRENT_PHASE.yaml,
  - append PROGRESS.md,
  - update phase CHECKLIST/UT_RESULTS/REVIEW_NOTES/SUMMARY,
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
