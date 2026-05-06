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

Decision records must include:
- timestamp
- affected requirement section
- decision
- rationale
- alternatives considered
