# Implementation Decisions

## 2026-05-06T08:44:19Z - Initialize local Git repository

- affected_requirement:
  - CODEX_KICKOFF_PROMPT.md Patch file generation
  - CODEX_KICKOFF_PROMPT.md Work loop step 12
- decision: Initialize a local Git repository in the workspace and commit the kickoff baseline.
- rationale: The required workflow depends on `git status`, `git diff`, patch files, and per-subtask commits. The initial workspace had no `.git` directory, so the workflow could not run.
- alternatives_considered:
  - Ask the user to move the files under an existing repository root.
  - Continue without commits, which would violate the kickoff workflow.

## 2026-05-06T08:52:00Z - Use PEP 621 pyproject with uv for local test execution

- affected_requirement:
  - REQUIREMENTS.md section 7
  - CODEX_KICKOFF_PROMPT.md dependency management
- decision: Use a standard PEP 621 `pyproject.toml` with setuptools metadata, runtime dependencies `pydantic`, `PyYAML`, and `loguru`, and dev dependency `pytest`. Use `uv` only as the local command runner because no `python` executable is available on PATH in this workspace.
- rationale: REQUIREMENTS.md section 7 selects YAML + pydantic for configuration, and the kickoff prompt requires pytest/loguru/Python 3.11+. `uv --native-tls` can provision the test interpreter reproducibly in this environment.
- alternatives_considered:
  - Poetry or PDM project metadata, which would add tool-specific files before the repo has an established packaging preference.
  - Rely on system `python`, which is unavailable in the current shell.

## 2026-05-06T13:56:52Z - Defer non-Subtask 1.1 dependencies until their owning phases

- affected_requirement:
  - REQUIREMENTS.md section 7
  - CODEX_KICKOFF_PROMPT.md dependency management
- decision: Keep Subtask 1.1 dependencies limited to configuration parsing and tests: `pydantic`, `PyYAML`, and `pytest`. Remove unused `loguru` for now. Introduce `loguru`, `langgraph`, `litellm`, `scipy`, `psutil`, and optional `sqlite-vec` in the phase/subtask that first uses each dependency.
- rationale: The kickoff prompt forbids introducing unnecessary dependencies without a reason. Subtask 1.1 does not log, orchestrate, call LLMs, run statistics, manage processes, or build indexes yet.
- alternatives_considered:
  - Add every section 7 dependency immediately, which bloats the initial config-only patch.
  - Keep unused `loguru`, which makes the dependency graph look more implemented than it is.

## 2026-05-06T08:52:00Z - Support documented duplicate config field shapes

- affected_requirement:
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B
- decision: Accept both the nested example shape from section 4.1.2 and Appendix B defaults where names overlap. Specifically, `agent.convergence.no_improve_trials` is synchronized with `agent.stagnation_threshold_trials`, `baseline.combo` with `baseline.default_combo`, and `tracing.langfuse.enabled` with `tracing.langfuse_enabled`.
- rationale: The locked docs contain both shapes. Supporting both keeps user config readable while rejecting conflicting values instead of silently choosing one.
- alternatives_considered:
  - Support only section 4.1.2, which would omit Appendix B schema fields.
  - Support only Appendix B, which would reject the primary config example.

## 2026-05-06T13:56:52Z - Keep baseline default optional but force init confirmation

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.1.2
  - REQUIREMENTS.md Appendix B baseline
- decision: Continue accepting a missing `baseline` block by applying Appendix B default `["-O2"]`, while ensuring future Subtask 1.3 init flow displays the resolved baseline for user confirmation.
- rationale: Appendix B explicitly provides `baseline.default_combo: ["-O2"]`, while section 4.1.2 shows `baseline.combo` in the sample config. Treating the Appendix B default as the parser fallback keeps minimal config usable, and the init confirmation flow prevents silent baseline execution.
- alternatives_considered:
  - Make `baseline.combo` mandatory now, which would contradict Appendix B defaults.
  - Silently accept conflicting `combo` and `default_combo`, which external review correctly identified as unsafe and has been fixed.

## 2026-05-06T13:56:52Z - Preserve template and relative path semantics in config

- affected_requirement:
  - REQUIREMENTS.md section 4.2.3
  - REQUIREMENTS.md Appendix B dry_run
  - REQUIREMENTS.md Appendix B clean
  - REQUIREMENTS.md Appendix B workspace_lock
- decision: Keep template paths like `<workspace>/_trash` and `dry_run_reports/<run_id>/import_overlay` as explicit strings in config models and provide resolver helpers. Preserve relative paths such as `trace/events.jsonl` and `state/run.lock` as relative `Path` values; namespace-aware anchoring belongs to init/namespace/lock helpers.
- rationale: Parsing config should not accidentally create literal `<workspace>` paths or guess a namespace root before Subtask 1.2 computes it.
- alternatives_considered:
  - Convert template values directly to `Path`, which hides unresolved tokens.
  - Resolve relative paths against the current working directory, which would make behavior invocation-dependent.

## 2026-05-06T13:56:52Z - Harden config YAML loader

- affected_requirement:
  - REQUIREMENTS.md section 1.3
  - REQUIREMENTS.md section 5.3
- decision: Add a 1 MiB size limit for `agent.config.yaml` and reject YAML aliases by using a dedicated `ConfigYamlLoader` derived from `yaml.SafeLoader`.
- rationale: Config is a local user input path. Even though it is not import tar handling, bounded parsing and alias rejection reduce accidental or malicious resource exhaustion without changing the user-readable YAML format.
- alternatives_considered:
  - Plain `yaml.safe_load`, which blocks Python object construction but not oversized files or aliases.

## 2026-05-07T03:56:38Z - Model exploration schedule quotas as lower-bound slots

- affected_requirement:
  - REQUIREMENTS.md section 4.6.3
  - REQUIREMENTS.md Appendix B agent.exploration_schedule
- decision: Validate that `exploit_per_window + mutation_per_window + novelty_per_window <= window_size`, not exactly equal to `window_size`. Keep `mutation_per_window` and `novelty_per_window` strictly positive.
- rationale: Section 4.6.3 defines the fields as "at least N" quota slots. If quota sum is less than the window size, leftover slots are selected by generator priority. If quota sum exceeds the window size, the schedule is unsatisfiable. `mutation` and `novelty` stay positive to preserve the v0.5 design goal that local mutation and novelty are not starved.
- alternatives_considered:
  - Require exact equality, which rejects valid schedules with priority fallback slots.
  - Allow zero mutation or novelty quota, which can regress to the v0.4 priority-only behavior.

## 2026-05-07T03:56:38Z - Include process_cleanup.require_env_marker from recovery prose

- affected_requirement:
  - REQUIREMENTS.md section 4.11.4
  - REQUIREMENTS.md Appendix B process_cleanup
- decision: Add `process_cleanup.require_env_marker: true` to the schema even though Appendix B omits it.
- rationale: Section 4.11.4 explicitly defines this field for Linux `hidepid`/container/low-permission environments. Appendix B is incomplete here, so the schema follows the more specific recovery requirement while retaining strict defaults.
- alternatives_considered:
  - Treat the omission as a blocker. This is unnecessary because the prose defines a concrete field, default, and degraded behavior.
  - Ignore the field until the process cleaner subtask, which would make current config validation reject a documented recovery setting.

## 2026-05-07T03:56:38Z - Remove accidental ZIP artifact from doc baseline

- affected_requirement:
  - CODEX_KICKOFF_PROMPT.md baseline docs
- decision: Remove tracked `doc/files (4).zip` and ignore future `*.zip` artifacts.
- rationale: The kickoff prompt only calls for the locked markdown requirements in `doc/`. The ZIP name indicates a local download artifact and it is not part of the readable project baseline.
- alternatives_considered:
  - Keep the ZIP because it was in the kickoff commit, which would continue carrying an opaque binary artifact in a local-first readable repo.

Decision records must include:
- timestamp
- affected requirement section
- decision
- rationale
- alternatives considered

## 2026-05-07T08:21:27Z - Define minimal modules.registry.yaml schema

- affected_requirement:
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- decision: Represent `shared/modules.registry.yaml` as a strict, user-editable YAML schema with required `schema_version: modules.registry.v1`, top-level `kg_versions`, and a `modules -> frameworks -> compilers -> versions` tree.
- rationale: Section 4.1.4 requires startup to fail when module/framework, compiler version, or kg_version are not registered, but does not define the exact registry file fields. A compact explicit tree keeps the SoT human-readable and gives init/startup code a deterministic validation surface.
- alternatives_considered:
  - Infer validity only from existing workspace directories, which would hide the registry contract in filesystem side effects.
  - Put `kg_versions` under each framework, which would duplicate global KG release identifiers and complicate later KG validation.
  - Let missing `schema_version` default to v1, which would make future schema migrations ambiguous.

## 2026-05-07T08:21:27Z - Keep namespace path segments literal but separator-safe

- affected_requirement:
  - REQUIREMENTS.md section 4.1.3
  - REQUIREMENTS.md section 1.3
- decision: Preserve user-provided namespace atoms literally after config validation, but reject empty values, `.`/`..`, NUL bytes, and `/` or `\` separators before constructing namespace paths.
- rationale: The namespace must remain user-readable (`module/framework/compiler-version/code-commit/kg-version`) while preventing traversal or accidental multi-segment injection. This avoids inventing opaque hashes or lossy slugification.
- alternatives_considered:
  - Slugify every value, which could make the on-disk namespace differ from the user's config and hide mistakes.
  - Accept arbitrary strings because v1 targets Linux, which would allow traversal-shaped values.

## 2026-05-07T08:51:09Z - Prefix code_commit and kg_version namespace segments explicitly

- affected_requirement:
  - REQUIREMENTS.md section 4.1.3
- decision: Always render namespace commit and KG atoms as `code-{project.code_commit}` and `kg-{project.kg_version}`.
- rationale: The section 4.1.3 example uses `code-a1b2c3d/kg-v3`. Treating `code-` and `kg-` as structural prefixes keeps the five namespace levels self-describing and avoids ambiguous bare values when browsing `namespaces/`.
- alternatives_considered:
  - Treat config values as complete path segments, which would require users to include structural prefixes in `agent.config.yaml`.
  - Strip an already-present `code-` or `kg-` prefix, which would create surprising normalization and could hide user typos.

## 2026-05-07T08:21:27Z - Make existing-trial compiler compatibility an explicit validator input

- affected_requirement:
  - REQUIREMENTS.md section 4.1.4
  - REQUIREMENTS.md section 4.2.3
- decision: `validate_project_against_registry` accepts optional `existing_trial_compiler_versions` and rejects any version that differs from the configured compiler version.
- rationale: Subtask 1.2 does not yet own FS-memory trial discovery, but the startup failure condition belongs in this validation layer. Making existing trial versions an explicit input lets later FS-memory code connect canonical trial metadata without changing the registry API.
- alternatives_considered:
  - Ignore existing trial compatibility until Phase 02, which would leave a documented startup failure path unrepresented.
  - Read trial YAML files directly from the registry module, which would couple Subtask 1.2 to FS-memory layout before that subsystem exists.

## 2026-05-07T09:59:55Z - Store init guard as explicit .initialized YAML

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- decision: Write `.initialized` as strict user-readable YAML with required `schema_version: agent.initialized.v1`, namespace, five namespace parts, project identity, baseline combo, and creation timestamp.
- rationale: Section 4.1.1 makes `.initialized` the later-startup namespace guard. Keeping it as YAML preserves the local-first readable SoT principle and lets users inspect exactly why a namespace is considered initialized.
- alternatives_considered:
  - Store only a bare namespace string, which is easy to read but too weak for diagnostics.
  - Store a hidden binary/cache marker, which would violate the user-readable project-state rule.

## 2026-05-07T09:59:55Z - Keep init edit as a core-flow signal, not an editor launch

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
- decision: The core `run_init` helper treats `edit` as `InitEditRequested` and does not launch an external editor.
- rationale: The requirement says the confirmation flow offers `y/n/edit`, but editor choice and process handling belong in a later CLI layer. Returning a clear edit signal keeps the safety behavior testable and avoids coupling the library to shell-specific editor behavior.
- alternatives_considered:
  - Spawn `$EDITOR` directly from the core helper, which would make tests and non-interactive usage fragile.
  - Treat `edit` as abort, which would lose the user's intended action.

## 2026-05-07T09:59:55Z - Use local atomic YAML write for .initialized

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.1
- decision: Write `.initialized` via a same-directory temporary file, file fsync, `os.replace`, and POSIX parent-directory fsync when available.
- rationale: `.initialized` influences subsequent startup decisions, so partial writes should not leave the namespace in an ambiguous state. A focused local helper is sufficient until Phase 02 introduces shared FS-memory atomic write utilities.
- alternatives_considered:
  - Direct `yaml.safe_dump` to the target path, which can leave truncated or partial YAML on interruption.
  - Wait for Phase 02 atomic-write helpers, which would leave Subtask 1.3's guard write weaker than necessary.

## 2026-05-07T13:53:40Z - Validate .initialized identity redundancy

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.2.3
- decision: Treat `.initialized.namespace`, `.initialized.namespace_parts`, and `.initialized.project` as redundant facts that must agree at load time.
- rationale: `.initialized` is a user-readable startup guard. If a user edits one identity field but not the others, startup should fail with a clear validation error instead of silently choosing one field as authoritative.
- alternatives_considered:
  - Compare only the flat `namespace` string, which keeps startup simple but lets corrupted readable state pass.
  - Remove the redundant fields, which would make `.initialized` less useful for inspection and diagnostics.

## 2026-05-07T13:53:40Z - Require UTC ISO 8601 .initialized timestamps

- affected_requirement:
  - REQUIREMENTS.md section 4.1.1
  - REQUIREMENTS.md section 4.10
- decision: Keep `.initialized.created_at` as a string for readability, but require it to parse as UTC timezone-aware ISO 8601.
- rationale: The writer emits UTC `datetime.isoformat()` strings. Requiring the same shape on load prevents user-edited timestamps like `yesterday` from becoming future doctor/report hazards.
- alternatives_considered:
  - Store `created_at` as a Pydantic `datetime`, which validates well but changes the exact dumped representation.
  - Accept any non-empty string, which is friendly but makes the field unreliable as audit metadata.

## 2026-05-07T13:53:40Z - Defer init serialization to WorkspaceLock

- affected_requirement:
  - REQUIREMENTS.md section 4.15
  - REQUIREMENTS.md section 4.1.1
- decision: `run_init` remains a core helper and does not implement its own cross-process lock; the upcoming WorkspaceLock subtask must wrap init/run entrypoints.
- rationale: Section 4.15 owns process-safe namespace locking. Duplicating a partial lock in init would risk divergent behavior right before the dedicated lock implementation.
- alternatives_considered:
  - Add an ad hoc lock inside `run_init`, which would conflict with the planned local WorkspaceLock design.
  - Ignore the race entirely, which would leave future CLI integration without a clear handoff.
