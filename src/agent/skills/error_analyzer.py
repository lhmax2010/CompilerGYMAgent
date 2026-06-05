"""Failure classification rules for Phase 05 compile/benchmark skills."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from .result_schema import (
    EvidenceLine,
    FailureCategory,
    FailureClassification,
    FailureConfidence,
    FailureRoute,
)


CLASSIFIER_VERSION = "failure_classifier.v1"

FailureDomain = Literal["compile", "benchmark"]


@dataclass(frozen=True)
class LogContent:
    """Named log text used as classifier evidence input."""

    ref: str
    text: str


@dataclass(frozen=True)
class _Rule:
    pattern_id: str
    category: FailureCategory
    route: FailureRoute
    retryable: bool
    pattern: re.Pattern[str]
    domains: tuple[FailureDomain, ...] = ("compile", "benchmark")
    base_confidence: FailureConfidence = "MEDIUM"
    extracts_options: bool = False


@dataclass(frozen=True)
class _Candidate:
    category: FailureCategory
    route: FailureRoute
    retryable: bool
    evidence: tuple[EvidenceLine, ...]
    affected_options: tuple[str, ...]
    matched_rule_id: str
    confidence: FailureConfidence
    source_keys: tuple[str, ...]


_CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_ROUTE_TIE_RANK = {"unknown": 1, "environment_related": 2, "option_related": 3}
_GENERIC_CATEGORIES = {"infra_failure", "unknown_failure"}


_COMPILE_STATUS: dict[str, tuple[FailureCategory, FailureRoute, bool, str]] = {
    "invalid_option": (
        "invalid_option",
        "option_related",
        False,
        "status_invalid_option_v1",
    ),
    "option_conflict": (
        "option_conflict",
        "option_related",
        False,
        "status_option_conflict_v1",
    ),
    "timeout": ("build_timeout", "environment_related", True, "status_build_timeout_v1"),
    "crash_signal": ("compiler_crash", "unknown", False, "status_compiler_crash_v1"),
    "oom_like_exit": ("oom_killed", "environment_related", True, "status_oom_killed_v1"),
    "artifact_missing": (
        "artifact_missing",
        "unknown",
        False,
        "status_artifact_missing_v1",
    ),
    "infra_failure": ("infra_failure", "environment_related", True, "status_infra_failure_v1"),
}

_BENCHMARK_STATUS: dict[str, tuple[FailureCategory, FailureRoute, bool, str]] = {
    "timeout": (
        "benchmark_timeout",
        "environment_related",
        True,
        "status_benchmark_timeout_v1",
    ),
    "crash_signal": ("benchmark_crash", "unknown", False, "status_benchmark_crash_v1"),
    "oom_like_exit": (
        "environment_unstable",
        "environment_related",
        True,
        "status_environment_unstable_v1",
    ),
    "artifact_missing": (
        "artifact_invalid",
        "unknown",
        False,
        "status_artifact_invalid_v1",
    ),
    "artifact_invalid": (
        "artifact_invalid",
        "unknown",
        False,
        "status_artifact_invalid_v1",
    ),
    "score_parse_failed": (
        "score_parse_failed",
        "unknown",
        True,
        "status_score_parse_failed_v1",
    ),
    "infra_failure": ("infra_failure", "environment_related", True, "status_infra_failure_v1"),
}


_COMPILE_RULES: tuple[_Rule, ...] = (
    _Rule(
        pattern_id="gcc_unknown_option_v1",
        category="invalid_option",
        route="option_related",
        retryable=False,
        extracts_options=True,
        domains=("compile",),
        pattern=re.compile(
            r"(?:unrecognized|unknown|unsupported)\s+(?:command-line\s+)?option\s+['\"]?(?P<option>-[^\s'\"]+)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="compiler_option_conflict_v1",
        category="option_conflict",
        route="option_related",
        retryable=False,
        extracts_options=True,
        domains=("compile",),
        pattern=re.compile(
            r"(?:conflicting|mutually exclusive|cannot be used together|not compatible)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="disk_full_or_quota_v1",
        category="disk_full_or_quota",
        route="environment_related",
        retryable=True,
        pattern=re.compile(
            r"(?:no space left on device|disk quota exceeded|quota exceeded|ENOSPC)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="oom_killed_v1",
        category="oom_killed",
        route="environment_related",
        retryable=True,
        domains=("compile",),
        pattern=re.compile(
            r"(?:^Killed$|out of memory|oom-killer|cannot allocate memory)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="permission_denied_v1",
        category="permission_denied",
        route="environment_related",
        retryable=True,
        pattern=re.compile(
            r"(?:permission denied|operation not permitted|EACCES)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="network_failure_v1",
        category="network_failure",
        route="environment_related",
        retryable=True,
        pattern=re.compile(
            r"(?:network is unreachable|temporary failure in name resolution|could not resolve host|connection timed out)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="dependency_missing_v1",
        category="dependency_missing",
        route="environment_related",
        retryable=True,
        domains=("compile",),
        pattern=re.compile(
            r"(?:required dependency .* missing|cannot find .* dependency|dependency .* not found)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="compiler_crash_v1",
        category="compiler_crash",
        route="unknown",
        retryable=False,
        domains=("compile",),
        pattern=re.compile(
            r"(?:internal compiler error|segmentation fault|compiler crash)",
            re.IGNORECASE,
        ),
    ),
)

_BENCHMARK_RULES: tuple[_Rule, ...] = (
    _Rule(
        pattern_id="benchmark_score_parse_failed_v1",
        category="score_parse_failed",
        route="unknown",
        retryable=True,
        domains=("benchmark",),
        pattern=re.compile(
            r"(?:score line is malformed|no SCORE line|could not parse score|score parse failed)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="benchmark_correctness_failed_v1",
        category="functional_correctness_failed",
        route="unknown",
        retryable=False,
        domains=("benchmark",),
        pattern=re.compile(
            r"(?:functional correctness failed|wrong answer|checksum mismatch|validation failed)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="benchmark_artifact_invalid_v1",
        category="artifact_invalid",
        route="unknown",
        retryable=False,
        domains=("benchmark",),
        pattern=re.compile(
            r"(?:artifact hash mismatch|artifact missing|artifact invalid)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="benchmark_environment_unstable_v1",
        category="environment_unstable",
        route="environment_related",
        retryable=True,
        domains=("benchmark",),
        pattern=re.compile(
            r"(?:^Killed$|out of memory|oom-killer|cannot allocate memory|thermal throttle|system load unstable)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        pattern_id="benchmark_too_noisy_v1",
        category="too_noisy",
        route="environment_related",
        retryable=True,
        domains=("benchmark",),
        pattern=re.compile(
            r"(?:too noisy|variance too high|coefficient of variation)",
            re.IGNORECASE,
        ),
    ),
)


def classify_compile_failure(
    status: str,
    *,
    combo: Sequence[str] = (),
    stdout: LogContent | None = None,
    stderr: LogContent | None = None,
    result_json_ref: str | None = None,
) -> FailureClassification | None:
    """Classify a compile failure using conservative routing."""

    if status == "success":
        return None
    return _classify(
        domain="compile",
        status=status,
        status_rules=_COMPILE_STATUS,
        log_rules=_COMPILE_RULES,
        combo=tuple(combo),
        logs=tuple(log for log in (stdout, stderr) if log is not None),
        result_json_ref=result_json_ref,
        unknown_category="unknown_failure",
        allow_failed_combo_write=True,
    )


def classify_benchmark_failure(
    status: str,
    *,
    stdout: LogContent | None = None,
    stderr: LogContent | None = None,
    result_json_ref: str | None = None,
) -> FailureClassification | None:
    """Classify a benchmark failure using conservative routing."""

    if status == "success":
        return None
    return _classify(
        domain="benchmark",
        status=status,
        status_rules=_BENCHMARK_STATUS,
        log_rules=(*_COMPILE_RULES, *_BENCHMARK_RULES),
        combo=(),
        logs=tuple(log for log in (stdout, stderr) if log is not None),
        result_json_ref=result_json_ref,
        unknown_category="unknown_failure",
        allow_failed_combo_write=False,
    )


def _classify(
    *,
    domain: FailureDomain,
    status: str,
    status_rules: dict[str, tuple[FailureCategory, FailureRoute, bool, str]],
    log_rules: Sequence[_Rule],
    combo: tuple[str, ...],
    logs: tuple[LogContent, ...],
    result_json_ref: str | None,
    unknown_category: FailureCategory,
    allow_failed_combo_write: bool,
) -> FailureClassification:
    candidates: list[_Candidate] = []
    if status in status_rules:
        category, route, retryable, pattern_id = status_rules[status]
        evidence = EvidenceLine(
            log_ref=f"{result_json_ref or 'result_json'}#status",
            text=f"status={status}",
            pattern_id=pattern_id,
        )
        candidates.append(
            _Candidate(
                category=category,
                route=route,
                retryable=retryable,
                evidence=(evidence,),
                affected_options=_status_affected_options(status, combo),
                matched_rule_id=pattern_id,
                confidence="MEDIUM",
                source_keys=(f"status:{pattern_id}",),
            )
        )

    candidates.extend(_match_log_rules(domain=domain, rules=log_rules, logs=logs, combo=combo))
    if not candidates:
        return FailureClassification(
            category=unknown_category,
            route="unknown",
            confidence="LOW",
            retryable=False,
            write_failed_combos=False,
            classifier_version=CLASSIFIER_VERSION,
        )

    merged = _merge_candidates(candidates)
    selected = _select_candidate(merged)
    write_failed = (
        allow_failed_combo_write
        and selected.route == "option_related"
        and selected.confidence == "HIGH"
        and bool(selected.affected_options)
    )
    return FailureClassification(
        category=selected.category,
        route=selected.route,
        confidence=selected.confidence,
        evidence=selected.evidence,
        affected_options=selected.affected_options,
        retryable=selected.retryable,
        write_failed_combos=write_failed,
        matched_rule_id=selected.matched_rule_id,
        classifier_version=CLASSIFIER_VERSION,
    )


def _match_log_rules(
    *,
    domain: FailureDomain,
    rules: Sequence[_Rule],
    logs: Sequence[LogContent],
    combo: tuple[str, ...],
) -> tuple[_Candidate, ...]:
    matches: list[_Candidate] = []
    for log in logs:
        for line_no, line in enumerate(log.text.splitlines(), start=1):
            for rule in rules:
                if domain not in rule.domains:
                    continue
                match = rule.pattern.search(line)
                if match is None:
                    continue
                affected_options = (
                    _extract_rule_options(rule=rule, match=match, line=line, combo=combo)
                    if rule.extracts_options
                    else ()
                )
                evidence = EvidenceLine(
                    log_ref=f"{log.ref}#L{line_no}",
                    text=line.strip(),
                    pattern_id=rule.pattern_id,
                )
                matches.append(
                    _Candidate(
                        category=rule.category,
                        route=rule.route,
                        retryable=rule.retryable,
                        evidence=(evidence,),
                        affected_options=affected_options,
                        matched_rule_id=rule.pattern_id,
                        confidence=rule.base_confidence,
                        source_keys=(f"log:{rule.pattern_id}",),
                    )
                )
    return tuple(matches)


def _merge_candidates(candidates: Sequence[_Candidate]) -> tuple[_Candidate, ...]:
    buckets: dict[tuple[FailureCategory, FailureRoute], list[_Candidate]] = {}
    for candidate in candidates:
        buckets.setdefault((candidate.category, candidate.route), []).append(candidate)

    merged: list[_Candidate] = []
    for (category, route), group in buckets.items():
        evidence = _dedupe_evidence(item for candidate in group for item in candidate.evidence)
        affected = _dedupe_strings(
            option for candidate in group for option in candidate.affected_options
        )
        source_keys = _dedupe_strings(
            key for candidate in group for key in candidate.source_keys
        )
        retryable = any(candidate.retryable for candidate in group)
        matched_rule_id = _preferred_rule_id(group)
        confidence = _merged_confidence(group, source_keys)
        merged.append(
            _Candidate(
                category=category,
                route=route,
                retryable=retryable,
                evidence=evidence,
                affected_options=affected,
                matched_rule_id=matched_rule_id,
                confidence=confidence,
                source_keys=source_keys,
            )
        )
    return tuple(merged)


def _select_candidate(candidates: Sequence[_Candidate]) -> _Candidate:
    high_environment = [
        candidate
        for candidate in candidates
        if candidate.route == "environment_related" and candidate.confidence == "HIGH"
    ]
    if high_environment:
        return sorted(
            high_environment,
            key=lambda item: (
                _CONFIDENCE_RANK[item.confidence],
                _specificity_rank(item),
                len(item.evidence),
                item.matched_rule_id,
            ),
            reverse=True,
        )[0]
    return sorted(
        candidates,
        key=lambda item: (
            _CONFIDENCE_RANK[item.confidence],
            _ROUTE_TIE_RANK[item.route],
            _specificity_rank(item),
            len(item.evidence),
            item.matched_rule_id,
        ),
        reverse=True,
    )[0]


def _specificity_rank(candidate: _Candidate) -> int:
    if candidate.category in _GENERIC_CATEGORIES:
        return 0
    return 1


def _merged_confidence(
    group: Sequence[_Candidate],
    source_keys: tuple[str, ...],
) -> FailureConfidence:
    if len(source_keys) >= 2:
        return "HIGH"
    return max((candidate.confidence for candidate in group), key=_CONFIDENCE_RANK.__getitem__)


def _preferred_rule_id(group: Sequence[_Candidate]) -> str:
    for candidate in group:
        if not candidate.matched_rule_id.startswith("status_"):
            return candidate.matched_rule_id
    return group[0].matched_rule_id


def _status_affected_options(status: str, combo: tuple[str, ...]) -> tuple[str, ...]:
    if status != "invalid_option":
        return ()
    return tuple(option for option in combo if "invalid" in option.lower())


def _extract_rule_options(
    *,
    rule: _Rule,
    match: re.Match[str],
    line: str,
    combo: tuple[str, ...],
) -> tuple[str, ...]:
    option = match.groupdict().get("option")
    if option:
        return _filter_options((option.rstrip(".,:;"),), combo)
    return _filter_options(_option_tokens(line), combo)


def _option_tokens(line: str) -> tuple[str, ...]:
    return tuple(
        token.strip("'\"`.,:;()[]{}")
        for token in re.findall(r"(?<!\w)-[A-Za-z0-9][A-Za-z0-9_+=:./-]*", line)
    )


def _filter_options(options: Iterable[str], combo: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = _dedupe_strings(option for option in options if option.startswith("-"))
    if not combo:
        return cleaned
    combo_set = set(combo)
    return tuple(option for option in cleaned if option in combo_set)


def _dedupe_strings(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _dedupe_evidence(values: Iterable[EvidenceLine]) -> tuple[EvidenceLine, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[EvidenceLine] = []
    for evidence in values:
        key = (evidence.log_ref, evidence.text, evidence.pattern_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(evidence)
    return tuple(result)
