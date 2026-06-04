from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agent import (
    EvidenceLine,
    FailureClassification,
    RunEnvironmentSnapshot,
    RunLevelRecord,
    RunSummaryHint,
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
    ],
)
def test_run_level_record_rejects_inconsistent_states(update: dict[str, object]) -> None:
    payload = _record_payload(valid_for_scoring=True)
    payload.update(update)
    if update.get("valid_for_scoring") is False:
        payload["score"] = None

    with pytest.raises(ValidationError):
        RunLevelRecord.model_validate(payload)


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
        ),
    }
