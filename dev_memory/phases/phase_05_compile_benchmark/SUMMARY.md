# Phase 05 Summary

Phase 05 implements compile and benchmark skills on top of the Phase 06 process-management substrate.

## 5.1 env marker refinement + pid-independent lease_id

- Added `AGENT_TRIAL_ID`, `AGENT_LEASE_ID`, and `AGENT_PROCESS_ROLE` marker constants.
- Added `ProcessRecord.trial_id` and `ProcessRecord.lease_id` as optional fields so old process leases remain loadable.
- Added `generate_lease_id(role)` to create `<role>-<uuid>` ids before spawning a process.
- Updated `spawn_process()` to generate the lease id before `Popen`, inject all process markers, and persist the same id into the running lease.
- Updated `ProcessLease` so new leases persist `lease_id` and ensure the nested `record` carries matching trial/lease metadata.
- Updated cleaner env scanning so new records require session + trial + lease matches, while legacy records with no trial/lease marker still fall back to session matching.

Validation:

- `.venv/bin/python -m pytest tests/test_process_identity.py tests/test_process_registry.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 44 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 550 passed.

## 5.2 fake_gbs mock harness

- Added `src/agent/skills/fake_gbs.py`.
- fake_gbs compile/benchmark run through `spawn_process()` and therefore use real subprocesses, process leases, independent process groups, and process env markers.
- Compile success produces a real artifact and `sha256:` artifact hash.
- Benchmark consumes and verifies the artifact and emits a parseable `SCORE` line.
- Failure modes covered:
  - invalid_option,
  - timeout,
  - crash_signal,
  - oom_like_exit,
  - artifact_missing,
  - score_parse_failed.
- Added gaussian, right_skewed, and bursty noise profiles.
- Bursty noise is a stateful seeded Markov chain over healthy/degraded/failed.
- Same seed replays score and burst state sequences.

Validation:

- `.venv/bin/python -m pytest tests/test_fake_gbs.py -q` -> 9 passed.
- `.venv/bin/python -m pytest tests/test_fake_gbs.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 28 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 559 passed.

## 5.5a failure/result schema skeleton

- Added `src/agent/skills/result_schema.py`.
- Defined closed schema aliases for failure category, route, confidence, run phase, and objective direction.
- Added `EvidenceLine` and `FailureClassification`.
- `FailureClassification` defaults conservatively to `route=unknown` and `write_failed_combos=False`.
- Model validation rejects `write_failed_combos=True` unless `route=option_related` and `confidence=HIGH`.
- Added `RunEnvironmentSnapshot`, `RunSummaryHint`, and `RunLevelRecord`.
- `RunLevelRecord` captures run_id, run_index, combo_hash, metric metadata, required objective_direction, timing, exit/signal state, stdout/stderr refs, env snapshot, artifact refs/hashes, score_source_ref, pair_key, failure classification, and summary hints.
- `score_parse_failed` invalid runs must carry `score_source_ref`.
- This subtask is schema-only and intentionally contains no classifier pattern matching or log parsing rules.

Validation:

- `.venv/bin/python -m pytest tests/test_result_schema.py -q` -> 19 passed.
- `.venv/bin/python -m pytest tests/test_fake_gbs.py tests/test_result_schema.py -q` -> 28 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 578 passed.

## 5.3 compile skill

- Added `src/agent/skills/compile.py`.
- Added `compile_candidate()` as the Phase 05 compile skill entry point.
- The skill runs workspace protection around compile:
  - `workspace_snapshot(pre)`,
  - `spec_backup`,
  - `spec_injector`,
  - fake_gbs compile,
  - `spec_restore`,
  - `workspace_verify`.
- Extended fake_gbs with an `on_spawn` hook so the skill can write canonical state immediately after `spawn_process()` creates the lease.
- Enforced spawn recovery ordering:
  - spawn process,
  - write lease,
  - trace `process_started` with full `ProcessRecord` and `ProcessLease` payload,
  - checkpoint operation ledger `process_refs`.
- If trace/checkpoint writing fails after lease creation, fake_gbs invokes `cleanup_process_lease(force_suspected=True)` and terminalizes the lease.
- The checkpoint operation ledger is the process authority; the deprecated `current_trial.process` field is not written.
- Compile failures return 5.5a `FailureClassification` objects; 5.5b classifier rules now control whether a HIGH-confidence option_related failure may write failed_combos.

Validation:

- `.venv/bin/python -m pytest tests/test_compile_skill.py -q` -> 3 passed.
- `.venv/bin/python -m pytest tests/test_compile_skill.py tests/test_fake_gbs.py tests/test_spec_skills.py tests/test_workspace_skills.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 55 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 581 passed.

## 5.4 benchmark skill

- Added `src/agent/skills/benchmark.py`.
- Added `benchmark_candidate()` as the Phase 05 benchmark skill entry point.
- The skill consumes compile artifacts and verifies the expected `sha256:` artifact hash before spawning benchmark runs.
- Artifact hash mismatch is a hard invalid `artifact_invalid` run-level record and does not spawn a benchmark process.
- Successful benchmark runs emit 5.5a `RunLevelRecord` objects with:
  - run_id,
  - run_index,
  - combo_hash,
  - warmup/measured phase,
  - metric metadata and objective_direction,
  - timing and exit/signal data,
  - stdout/stderr refs,
  - environment snapshot,
  - artifact_ref/artifact_hash/artifact_hash_verified,
  - score_source_ref,
  - nullable pair_key,
  - summary_hint.
- Warmup and measured runs are explicit phases; measured runs keep stable run_index ordering for Phase 08.
- The benchmark process path uses fake_gbs through the real process-backed harness.
- Spawn recovery ordering mirrors compile:
  - process spawned,
  - lease written,
  - trace `process_started` with full ProcessRecord and ProcessLease payload,
  - checkpoint operation ledger process_refs updated.
- Hard benchmark failures use 5.5a `FailureClassification` conservatively with `write_failed_combos=False`.
- Outlier and final statistical judgment remain deferred to Phase 08.

Validation:

- `.venv/bin/python -m pytest tests/test_benchmark_skill.py -q` -> 4 passed.
- `.venv/bin/python -m pytest tests/test_benchmark_skill.py tests/test_compile_skill.py tests/test_fake_gbs.py tests/test_result_schema.py tests/test_process_runner.py tests/test_process_cleaner.py -q` -> 54 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 585 passed.

## 5.5b failure classifier rules + routing tests

- Added `src/agent/skills/error_analyzer.py`.
- Added shared classifier entry points:
  - `classify_compile_failure()`,
  - `classify_benchmark_failure()`,
  - `LogContent`,
  - `CLASSIFIER_VERSION`.
- Compile and benchmark skills now consume the shared classifier instead of inline status-only mappings.
- Rules combine process result status, stdout/stderr log evidence, and result-json refs into 5.5a `FailureClassification`.
- HIGH confidence requires at least two evidence sources, such as result status plus a log pattern.
- invalid_option and option_conflict can write failed_combos only when they are HIGH-confidence option_related classifications.
- environment_related categories such as disk_full_or_quota, oom_killed, build_timeout, network_failure, and permission_denied never write failed_combos.
- High-confidence environment evidence overrides option matches, so OOM/disk/network failures do not poison candidate memory even when an option-looking log line is present.
- Unmatched failures default to unknown/LOW/write_failed_combos=False.
- affected_options extraction is token-aware and filters against the candidate combo when available.

Validation:

- `.venv/bin/python -m pytest tests/test_error_analyzer.py -q` -> 9 passed.
- `.venv/bin/python -m pytest tests/test_error_analyzer.py tests/test_compile_skill.py tests/test_benchmark_skill.py tests/test_result_schema.py tests/test_fake_gbs.py -q` -> 44 passed.
- `.venv/bin/python -m pytest tests/ -q` -> 594 passed.
