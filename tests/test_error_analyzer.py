from __future__ import annotations

from agent import (
    CLASSIFIER_VERSION,
    LogContent,
    classify_benchmark_failure,
    classify_compile_failure,
)


def test_compile_invalid_option_high_confidence_writes_failed_combos() -> None:
    failure = classify_compile_failure(
        "invalid_option",
        combo=["-O3", "-funknown-flag"],
        stderr=LogContent(
            ref="logs/compile.stderr",
            text="gcc: error: unrecognized command-line option '-funknown-flag'\n",
        ),
        result_json_ref="results/compile.json",
    )

    assert failure is not None
    assert failure.category == "invalid_option"
    assert failure.route == "option_related"
    assert failure.confidence == "HIGH"
    assert failure.affected_options == ("-funknown-flag",)
    assert failure.write_failed_combos is True
    assert failure.matched_rule_id == "gcc_unknown_option_v1"
    assert failure.classifier_version == CLASSIFIER_VERSION
    assert {evidence.pattern_id for evidence in failure.evidence} == {
        "status_invalid_option_v1",
        "gcc_unknown_option_v1",
    }


def test_compile_invalid_option_extracts_only_reported_option() -> None:
    failure = classify_compile_failure(
        "invalid_option",
        combo=["-O3", "-funroll-loops", "-fno-such-pass"],
        stderr=LogContent(
            ref="logs/compile.stderr",
            text="clang: error: unknown option '-fno-such-pass'; did you mean '-O3'?\n",
        ),
        result_json_ref="results/compile.json",
    )

    assert failure is not None
    assert failure.affected_options == ("-fno-such-pass",)
    assert "-O3" not in failure.affected_options


def test_compile_option_conflict_high_confidence_writes_affected_options() -> None:
    failure = classify_compile_failure(
        "option_conflict",
        combo=["-O3", "-Os", "-funroll-loops"],
        stderr=LogContent(
            ref="logs/compile.stderr",
            text="error: conflicting optimization options -O3 and -Os are mutually exclusive\n",
        ),
        result_json_ref="results/compile.json",
    )

    assert failure is not None
    assert failure.category == "option_conflict"
    assert failure.route == "option_related"
    assert failure.confidence == "HIGH"
    assert failure.affected_options == ("-O3", "-Os")
    assert failure.write_failed_combos is True


def test_environment_related_failures_never_write_failed_combos() -> None:
    cases = [
        (
            "infra_failure",
            "ld: cannot write output file: No space left on device",
            "disk_full_or_quota",
        ),
        (
            "oom_like_exit",
            "Killed",
            "oom_killed",
        ),
        (
            "timeout",
            "build timed out after 120 seconds",
            "build_timeout",
        ),
        (
            "infra_failure",
            "curl: (6) Could not resolve host: mirror.example",
            "network_failure",
        ),
        (
            "infra_failure",
            "mkdir build: Permission denied",
            "permission_denied",
        ),
    ]

    for status, stderr, category in cases:
        failure = classify_compile_failure(
            status,
            combo=["-O3"],
            stderr=LogContent(ref="logs/compile.stderr", text=stderr),
            result_json_ref="results/compile.json",
        )

        assert failure is not None
        assert failure.category == category
        assert failure.route == "environment_related"
        assert failure.write_failed_combos is False


def test_high_confidence_environment_evidence_overrides_option_match() -> None:
    failure = classify_compile_failure(
        "oom_like_exit",
        combo=["-funknown-flag"],
        stderr=LogContent(
            ref="logs/compile.stderr",
            text=(
                "gcc: error: unrecognized command-line option '-funknown-flag'\n"
                "Killed\n"
            ),
        ),
        result_json_ref="results/compile.json",
    )

    assert failure is not None
    assert failure.category == "oom_killed"
    assert failure.route == "environment_related"
    assert failure.confidence == "HIGH"
    assert failure.write_failed_combos is False


def test_single_option_log_match_is_medium_and_does_not_write_failed_combos() -> None:
    failure = classify_compile_failure(
        "infra_failure",
        combo=["-funknown-flag"],
        stderr=LogContent(
            ref="logs/compile.stderr",
            text="gcc: error: unrecognized command-line option '-funknown-flag'\n",
        ),
    )

    assert failure is not None
    assert failure.category == "invalid_option"
    assert failure.route == "option_related"
    assert failure.confidence == "MEDIUM"
    assert failure.write_failed_combos is False


def test_unknown_failure_defaults_conservatively() -> None:
    failure = classify_compile_failure(
        "mysterious",
        combo=["-O2"],
        stderr=LogContent(ref="logs/compile.stderr", text="something strange happened\n"),
    )

    assert failure is not None
    assert failure.category == "unknown_failure"
    assert failure.route == "unknown"
    assert failure.confidence == "LOW"
    assert failure.write_failed_combos is False
    assert failure.evidence == ()


def test_benchmark_score_parse_failed_has_score_evidence_and_no_memory_write() -> None:
    failure = classify_benchmark_failure(
        "score_parse_failed",
        stdout=LogContent(
            ref="logs/benchmark.stdout",
            text="benchmark completed but score line is malformed\n",
        ),
        result_json_ref="results/benchmark.json",
    )

    assert failure is not None
    assert failure.category == "score_parse_failed"
    assert failure.route == "unknown"
    assert failure.confidence == "HIGH"
    assert failure.retryable is True
    assert failure.write_failed_combos is False
    assert {evidence.pattern_id for evidence in failure.evidence} == {
        "status_score_parse_failed_v1",
        "benchmark_score_parse_failed_v1",
    }


def test_benchmark_environment_failure_is_routed_without_failed_combo_write() -> None:
    failure = classify_benchmark_failure(
        "oom_like_exit",
        stderr=LogContent(ref="logs/benchmark.stderr", text="Killed\n"),
        result_json_ref="results/benchmark.json",
    )

    assert failure is not None
    assert failure.category == "environment_unstable"
    assert failure.route == "environment_related"
    assert failure.confidence == "HIGH"
    assert failure.write_failed_combos is False
