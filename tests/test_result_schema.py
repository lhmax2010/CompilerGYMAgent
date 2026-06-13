from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

import pytest
from pydantic import ValidationError

from agent import (
    EvidenceLine,
    FailureClassification,
    RunEnvironmentSnapshot,
    RunLevelRecord,
    RunSummaryHint,
    StatisticalResult,
    compute_result_combo_hash,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def test_failure_classification_defaults_are_conservative() -> None:
    failure = FailureClassification()

    assert failure.category == "unknown_failure"
    assert failure.route == "unknown"
    assert failure.confidence == "LOW"
    assert failure.evidence == ()
    assert failure.affected_options == ()
    assert failure.retryable is False
    assert failure.write_failed_combos is False
    assert failure.classifier_version == "failure_classifier.v1"


def test_failure_classification_allows_high_confidence_option_memory_write() -> None:
    failure = FailureClassification(
        category="invalid_option",
        route="option_related",
        confidence="HIGH",
        evidence=(
            EvidenceLine(
                log_ref="logs/compile.stderr#L120",
                text="gcc: error: unrecognized command-line option '-fnope'",
                pattern_id="gcc_unknown_option_v1",
            ),
        ),
        affected_options=("-fnope",),
        retryable=False,
        write_failed_combos=True,
        matched_rule_id="gcc_unknown_option_v1",
    )

    assert failure.write_failed_combos is True
    assert failure.affected_options == ("-fnope",)


def test_write_failed_combos_requires_affected_options() -> None:
    with pytest.raises(ValidationError, match="affected_options"):
        FailureClassification(
            category="invalid_option",
            route="option_related",
            confidence="HIGH",
            evidence=(
                EvidenceLine(
                    log_ref="logs/compile.stderr#L120",
                    text="gcc: error: unrecognized command-line option",
                    pattern_id="gcc_unknown_option_v1",
                ),
            ),
            write_failed_combos=True,
            matched_rule_id="gcc_unknown_option_v1",
        )


@pytest.mark.parametrize(
    ("route", "confidence"),
    [
        ("environment_related", "HIGH"),
        ("unknown", "HIGH"),
        ("option_related", "MEDIUM"),
        ("option_related", "LOW"),
    ],
)
def test_write_failed_combos_requires_high_confidence_option_route(
    route: str, confidence: str
) -> None:
    with pytest.raises(ValidationError, match="write_failed_combos"):
        FailureClassification(
            category="invalid_option",
            route=route,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            write_failed_combos=True,
        )


def test_failure_classification_rejects_open_ended_strings() -> None:
    with pytest.raises(ValidationError):
        FailureClassification(category="disk_is_sad")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FailureClassification(route="maybe_option")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        FailureClassification(confidence="VERY_HIGH")  # type: ignore[arg-type]


def test_run_level_record_accepts_successful_measured_run() -> None:
    record = _record(valid_for_scoring=True)

    assert record.run_id == "run_1"
    assert record.run_index == 0
    assert record.combo_hash == compute_result_combo_hash(["-O3", "-funroll-loops"])
    assert record.objective_direction == "higher_is_better"
    assert record.score == 123.4
    assert record.failure_classification is None
    assert record.artifact_hash_verified is True
    assert record.summary_hint is not None
    assert record.env_snapshot.mem_available_bytes == 1024


def test_run_level_record_requires_objective_direction() -> None:
    payload = _record_payload(valid_for_scoring=True)
    payload.pop("objective_direction")

    with pytest.raises(ValidationError, match="objective_direction"):
        RunLevelRecord.model_validate(payload)


def test_run_level_record_accepts_invalid_score_parse_failure() -> None:
    failure = FailureClassification(
        category="score_parse_failed",
        route="unknown",
        confidence="MEDIUM",
        evidence=(
            EvidenceLine(
                log_ref="logs/bench.stdout#L80",
                text="benchmark completed but no SCORE line was found",
                pattern_id="score_line_missing_v1",
            ),
        ),
        retryable=True,
    )
    record = _record(
        valid_for_scoring=False,
        score=None,
        invalid_reason="score_parse_failed",
        failure_classification=failure,
        score_source_ref="logs/bench.stdout#L80-L90",
        exit_code=0,
    )

    assert record.valid_for_scoring is False
    assert record.failure_classification == failure
    assert record.score_source_ref == "logs/bench.stdout#L80-L90"


@pytest.mark.parametrize(
    "update",
    [
        {"valid_for_scoring": True, "score": None},
        {
            "valid_for_scoring": True,
            "failure_classification": FailureClassification(),
        },
        {"valid_for_scoring": False, "failure_classification": None},
        {"valid_for_scoring": False, "invalid_reason": None},
        {"exit_code": 1, "signal": 9},
        {"artifact_hash": None, "artifact_hash_verified": True},
        {"artifact_hash_verified": False},
    ],
)
def test_run_level_record_rejects_inconsistent_states(update: dict[str, object]) -> None:
    payload = _record_payload(valid_for_scoring=True)
    payload.update(update)
    if update.get("valid_for_scoring") is False:
        payload["score"] = None

    with pytest.raises(ValidationError):
        RunLevelRecord.model_validate(payload)


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_run_level_record_rejects_non_finite_scores(score: float) -> None:
    payload = _record_payload(valid_for_scoring=True)
    payload["score"] = score

    with pytest.raises(ValidationError, match="score"):
        RunLevelRecord.model_validate(payload)


@pytest.mark.parametrize("duration_sec", [math.nan, math.inf, -math.inf])
def test_run_level_record_rejects_non_finite_duration(duration_sec: float) -> None:
    payload = _record_payload(valid_for_scoring=True)
    payload["duration_sec"] = duration_sec

    with pytest.raises(ValidationError, match="duration_sec"):
        RunLevelRecord.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["loadavg_1m", "loadavg_5m", "loadavg_15m", "cpu_freq_mhz"],
)
def test_environment_snapshot_rejects_non_finite_floats(field: str) -> None:
    payload = {
        "loadavg_1m": 0.5,
        "loadavg_5m": 0.4,
        "loadavg_15m": 0.3,
        "cpu_freq_mhz": 3200.0,
    }
    payload[field] = math.inf

    with pytest.raises(ValidationError, match=field):
        RunEnvironmentSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "mean",
        "median",
        "stddev",
        "cv",
        "effective_sample_size",
        "lag1_autocorrelation",
    ],
)
def test_run_summary_hint_rejects_non_finite_values(field: str) -> None:
    payload = {
        "mean": 1.0,
        "median": 1.0,
        "stddev": 0.0,
        "cv": 0.0,
        "n_measured": 3,
        "n_valid": 3,
        "n_invalid": 0,
        "effective_sample_size": 3.0,
        "lag1_autocorrelation": 0.1,
    }
    payload[field] = math.nan

    with pytest.raises(ValidationError, match=field):
        RunSummaryHint.model_validate(payload)


def test_run_summary_hint_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValidationError, match="n_valid"):
        RunSummaryHint(n_measured=2, n_valid=2, n_invalid=1)


def test_run_summary_hint_rejects_ess_above_valid_count() -> None:
    with pytest.raises(ValidationError, match="effective_sample_size"):
        RunSummaryHint(n_measured=2, n_valid=2, effective_sample_size=2.5)


def test_run_summary_hint_accepts_iid_diagnostics() -> None:
    hint = RunSummaryHint(
        n_measured=8,
        n_valid=8,
        effective_sample_size=2.5,
        ess_preliminary=False,
        lag1_autocorrelation=0.5,
        autocorrelation_detected=True,
        iid_assumption_valid=False,
        autocorrelation_warning=True,
        low_power=True,
    )

    assert hint.autocorrelation_detected is True
    assert hint.iid_assumption_valid is False
    assert hint.low_power is True


def test_statistical_result_accepts_single_comparison_schema() -> None:
    result = StatisticalResult(
        comparison="candidate_vs_baseline",
        objective_direction="higher_is_better",
        point_estimate=2.0,
        relative_effect_pct=20.0,
        ci_low=1.0,
        ci_high=3.0,
        confidence_level=0.95,
        method="iid_percentile_bootstrap",
        verdict="significant_improvement",
        significant_single_comparison=True,
        n_measured=20,
        n_valid=10,
        n_invalid=0,
        baseline_n_valid=10,
        candidate_n_valid=10,
        effective_sample_size=10.0,
        lag1_autocorrelation=0.0,
        notes=("single_comparison",),
    )

    assert result.comparison_scope == "single_comparison"
    assert result.adjusted_for_multiple_testing is False
    assert result.significant_single_comparison is True


def test_statistical_result_rejects_inconsistent_significance_and_adjustment() -> None:
    with pytest.raises(ValidationError, match="significant_single_comparison"):
        StatisticalResult(
            comparison="candidate_vs_baseline",
            objective_direction="higher_is_better",
            point_estimate=0.0,
            ci_low=-1.0,
            ci_high=1.0,
            confidence_level=0.95,
            method="iid_percentile_bootstrap",
            verdict="no_difference",
            significant_single_comparison=True,
            n_measured=20,
            n_valid=10,
            n_invalid=0,
            baseline_n_valid=10,
            candidate_n_valid=10,
            effective_sample_size=10.0,
        )

    with pytest.raises(ValidationError, match="multiple-testing"):
        StatisticalResult(
            comparison="candidate_vs_baseline",
            objective_direction="higher_is_better",
            point_estimate=2.0,
            ci_low=1.0,
            ci_high=3.0,
            confidence_level=0.95,
            method="iid_percentile_bootstrap",
            verdict="significant_improvement",
            significant_single_comparison=True,
            adjusted_for_multiple_testing=True,
            n_measured=20,
            n_valid=10,
            n_invalid=0,
            baseline_n_valid=10,
            candidate_n_valid=10,
            effective_sample_size=10.0,
        )


def test_score_parse_failed_requires_score_source_ref() -> None:
    payload = _record_payload(valid_for_scoring=False)
    payload.update(
        {
            "score": None,
            "invalid_reason": "score_parse_failed",
            "failure_classification": FailureClassification(
                category="score_parse_failed",
                route="unknown",
                confidence="MEDIUM",
            ),
            "score_source_ref": None,
        }
    )

    with pytest.raises(ValidationError, match="score_source_ref"):
        RunLevelRecord.model_validate(payload)


def test_run_level_record_rejects_non_sha_hashes_and_time_travel() -> None:
    with pytest.raises(ValidationError, match="combo_hash"):
        _record(combo_hash="not-a-sha")
    with pytest.raises(ValidationError, match="ended_at"):
        _record(ended_at=datetime(2026, 6, 1, 7, 59, tzinfo=UTC))


def test_schema_module_contains_no_classifier_rule_patterns() -> None:
    import agent.skills.result_schema as result_schema

    source = result_schema.__loader__.get_source(result_schema.__name__)  # type: ignore[union-attr]
    assert source is not None
    assert "unrecognized command-line option" not in source
    assert "gcc_unknown_option" not in source


def _record(**overrides: object) -> RunLevelRecord:
    payload = _record_payload(valid_for_scoring=True)
    payload.update(overrides)
    return RunLevelRecord.model_validate(payload)


def _record_payload(*, valid_for_scoring: bool) -> dict[str, object]:
    started_at = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    return {
        "run_id": "run_1",
        "run_index": 0,
        "combo_hash": compute_result_combo_hash(["-O3", "-funroll-loops"]),
        "score": 123.4 if valid_for_scoring else None,
        "phase": "measured",
        "metric_name": "throughput",
        "metric_unit": "items/sec",
        "objective_direction": "higher_is_better",
        "duration_sec": 1.25,
        "started_at": started_at,
        "ended_at": started_at + timedelta(seconds=1.25),
        "exit_code": 0,
        "signal": None,
        "stdout_ref": "logs/bench.stdout#L1-L5",
        "stderr_ref": "logs/bench.stderr#L1-L2",
        "env_snapshot": RunEnvironmentSnapshot(
            loadavg_1m=0.5,
            loadavg_5m=0.4,
            loadavg_15m=0.3,
            cpu_governor="performance",
            cpu_freq_mhz=3200.0,
            thermal_throttle=False,
            mem_available_bytes=1024,
        ),
        "valid_for_scoring": valid_for_scoring,
        "invalid_reason": None,
        "benchmark_cmd": ("fake-gbs", "benchmark"),
        "artifact_ref": "artifacts/fake/run_1.artifact",
        "artifact_hash": SHA_A,
        "artifact_hash_verified": True,
        "score_source_ref": "logs/bench.stdout#L3",
        "pair_key": None,
        "failure_classification": None,
        "summary_hint": RunSummaryHint(
            mean=123.4,
            median=123.4,
            stddev=0.0,
            cv=0.0,
            n_measured=1,
            n_valid=1,
            n_invalid=0,
            effective_sample_size=1.0,
        ),
    }
