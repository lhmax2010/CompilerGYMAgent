from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.fs_memory import (
    NamespaceLayout,
    append_trace_event,
    load_trace_events,
    trace_event_payload,
)
from agent.registry import ProjectNamespace
from agent.trace import TraceSessionError, TraceSessionWriter, count_trace_events


def namespace() -> ProjectNamespace:
    return ProjectNamespace(
        module="multimedia",
        framework="ffmpeg",
        compiler="gcc-13.2.0",
        code_commit="code-a1b2c3d",
        kg_version="kg-v3",
    )


def layout(tmp_path: Path) -> NamespaceLayout:
    return NamespaceLayout(workspace=tmp_path, namespace=namespace())


def event_payloads(current_layout: NamespaceLayout) -> list[dict]:
    return [trace_event_payload(event) for event in load_trace_events(current_layout.trace_path)]


def test_trace_session_writer_injects_context_and_line_counter(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
    )

    first = writer.round_start(
        round=12,
        phase="steady_state",
        ts=datetime(2026, 4, 30, 10, 0, 0, tzinfo=UTC),
    )
    second = writer.trial_start(
        trial_id="r12_t3",
        combo=["-O3", "-fno-plt"],
        mode="exploit",
        candidate_source="llm_proposal",
        ts="2026-04-30T10:01:00Z",
    )

    assert first.trace_id == "events.jsonl#L1"
    assert second.trace_id == "events.jsonl#L2"
    assert writer.next_line_number == 3

    payloads = event_payloads(current_layout)
    assert payloads[0]["session_id"] == "sess_20260430_abc"
    assert payloads[0]["namespace"] == str(namespace())
    assert payloads[0]["kind"] == "round_start"
    assert payloads[1]["kind"] == "trial_start"
    assert payloads[1]["combo"] == ["-O3", "-fno-plt"]
    assert payloads[1]["mode"] == "exploit"


def test_trace_session_writer_resumes_line_counter_from_existing_trace(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )

    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
    )
    result = writer.candidate_generation(
        generator="llm_proposer",
        candidates_count=5,
        ts="2026-04-30T10:01:00Z",
    )

    assert count_trace_events(current_layout.trace_path) == 2
    assert writer.next_line_number == 3
    assert result.trace_id == "events.jsonl#L2"
    assert event_payloads(current_layout)[1]["candidates_count"] == 5


def test_trace_session_writer_dry_run_injects_mode_and_rejects_conflict(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
        dry_run=True,
    )

    writer.round_start(round=1, phase="dry_run_probe", ts="2026-04-30T10:00:00Z")

    assert event_payloads(current_layout)[0]["mode"] == "dry_run"
    with pytest.raises(TraceSessionError, match="dry-run trace events"):
        writer.trial_start(
            trial_id="dryrun_r1_t1",
            combo=["-O3"],
            mode="exploit",
            ts="2026-04-30T10:01:00Z",
        )


@pytest.mark.parametrize("field", ["session_id", "namespace"])
def test_trace_session_writer_rejects_context_overrides(
    tmp_path: Path,
    field: str,
) -> None:
    writer = TraceSessionWriter.for_layout(
        layout(tmp_path),
        session_id="sess_20260430_abc",
    )

    with pytest.raises(TraceSessionError, match=field):
        writer.append("round_start", **{field: "override"})


@pytest.mark.parametrize(
    "session_id",
    [" sess", "sess abc", "sess\nabc", "../../etc", "sess=abc", ".", ".."],
)
def test_trace_session_writer_rejects_unsafe_session_id(
    tmp_path: Path,
    session_id: str,
) -> None:
    with pytest.raises(TraceSessionError):
        TraceSessionWriter.for_layout(layout(tmp_path), session_id=session_id)


def test_trace_session_writer_rejects_non_positive_next_line_number(
    tmp_path: Path,
) -> None:
    with pytest.raises(TraceSessionError, match="next_line_number"):
        TraceSessionWriter.for_layout(
            layout(tmp_path),
            session_id="sess_20260430_abc",
            next_line_number=0,
        )


def test_trace_session_writer_convenience_events(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
    )

    writer.candidate_rejected(
        candidate=["-O3", "-funroll-loops"],
        rejection_reason="duplicate_hash",
        generator="local_mutation",
        matched_trial="r8_t2",
        ts="2026-04-30T10:00:00Z",
    )
    writer.skill_span(
        skill="spec_backup",
        duration_ms=12,
        success=True,
        ts="2026-04-30T10:01:00Z",
    )
    writer.trial_end(
        trial_id="r12_t3",
        outcome="success",
        score=1.234,
        ts="2026-04-30T10:02:00Z",
    )
    writer.trial_yaml_written(
        path=Path("trials/data/2026-04/trial_r12_t3.yaml"),
        ts="2026-04-30T10:03:00Z",
    )

    payloads = event_payloads(current_layout)
    assert [payload["kind"] for payload in payloads] == [
        "candidate_rejected",
        "skill_span",
        "trial_end",
        "trial_yaml_written",
    ]
    assert payloads[0]["candidate"] == ["-O3", "-funroll-loops"]
    assert payloads[0]["matched_trial"] == "r8_t2"
    assert payloads[1]["success"] is True
    assert payloads[2]["score"] == 1.234
    assert payloads[3]["path"] == "trials/data/2026-04/trial_r12_t3.yaml"
