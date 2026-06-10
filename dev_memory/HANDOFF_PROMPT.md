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
- Phase 08a code has NOT started yet.
- `dev_memory/BLOCKERS.md` currently records no active blockers.

Latest important commits:
- `6b72d43 dev_memory: finalize 08a statistics core design`
- `f34c28d phase_05: harden benchmark scoring and failure routing`
- `6ed4b31 dev_memory: close Phase 05 compile benchmark skills`
- `6252761 tests: make clean trace CLI dates relative`
- `4ccf5c5 phase_05: add failure classifier rules`

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

Next real phase:
- Phase 08a - Baseline + Statistical Significance - Minimal Stats Core.
- It is pure statistics code: no process cleanup, no workspace mutation, and no
  candidate engine changes.
- 08a consumes Phase 05 `RunLevelRecord` values.
- Main technical risk: bursty/autocorrelated benchmark noise. Do not implement
  naive IID-only statistics.

Before writing 08a code:
1. Confirm whether Claude/external review for the 08a design commit
   `f34c28d..6b72d43` has been completed and recorded.
2. If not recorded, pause coding and ask for/record that design review.
3. Re-parse the roadmap:
   `python - <<'PY'
   import yaml
   from pathlib import Path
   data = yaml.safe_load(Path("dev_memory/ROADMAP.yaml").read_text())
   planned = data["planned_phases"]
   print(planned[0]["id"], planned[0]["status"])
   print(planned[1]["id"], planned[1]["status"], planned[1]["estimate_subtasks"])
   PY`
   Expected: `05.5 done`, then `08a planned`, estimate `low: 6, high: 8`.

Phase 08a first subtask:
- 08a.1 descriptive statistics + RunSummaryHint extension.
- Implement `src/agent/stats_core.py` only when design review is cleared.
- Add/extend schema in `src/agent/skills/result_schema.py` for:
  - n_measured, n_valid, n_invalid,
  - effective_sample_size,
  - lag1_autocorrelation,
  - autocorrelation_warning,
  - StatisticalResult if 08a.1 scope includes it per updated subtask split.
- Consume only measured runs with `valid_for_scoring=True`.
- Use sample stddev (n-1).
- CV is None when mean is effectively zero.
- All numeric fields must reject NaN/Inf.

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
- `.venv/bin/python -m pytest tests/ -q`
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
