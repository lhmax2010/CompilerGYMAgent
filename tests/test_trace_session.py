from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.fs_memory import (
    CheckpointState,
    NamespaceLayout,
    append_trace_event,
    load_checkpoint_for_layout,
    load_trace_events,
    trace_event_payload,
    write_checkpoint_state,
)
from agent.registry import ProjectNamespace
from agent.trace import (
    TraceCheckpointWriter,
    TraceSessionError,
    TraceSessionWriter,
    checkpoint_with_trace_line_count,
    count_trace_events,
)


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


def checkpoint_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "session_id": "sess_20260430_abc",
        "namespace": str(namespace()),
        "last_completed_trial": None,
        "current_trial": None,
        "current_best": None,
        "explorer_state": {},
        "random_seed": 42,
        "total_tokens_consumed": 100,
        "last_updated": "2026-04-30T10:30:22Z",
    }
    data.update(overrides)
    return data


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


def test_trace_session_writer_uses_checkpoint_trace_line_count_without_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    checkpoint = checkpoint_data(trace_line_count=7)

    def fail_if_scanned(path: Path) -> int:
        raise AssertionError(f"unexpected trace scan: {path}")

    monkeypatch.setattr("agent.trace.count_trace_events", fail_if_scanned)

    writer = TraceSessionWriter.for_checkpoint(current_layout, checkpoint)

    assert writer.session_id == "sess_20260430_abc"
    assert writer.next_line_number == 8
    assert writer.trace_line_count == 7


def test_trace_session_writer_for_checkpoint_falls_back_for_legacy_checkpoint(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )

    writer = TraceSessionWriter.for_checkpoint(current_layout, checkpoint_data())

    assert writer.next_line_number == 2


def test_trace_session_writer_for_checkpoint_rejects_namespace_mismatch(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    checkpoint = checkpoint_data(
        namespace="other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3",
        trace_line_count=1,
    )

    with pytest.raises(TraceSessionError, match="namespace does not match"):
        TraceSessionWriter.for_checkpoint(current_layout, checkpoint)


def test_checkpoint_with_trace_line_count_updates_checkpoint_payload(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T09:59:00Z", "kind": "session_resume"},
        expected_line_number=1,
    )
    writer = TraceSessionWriter.for_checkpoint(
        current_layout,
        checkpoint_data(trace_line_count=1),
    )
    writer.round_start(
        round=12,
        phase="steady_state",
        ts="2026-04-30T10:00:00Z",
    )

    payload = writer.checkpoint_with_current_trace_count(checkpoint_data())
    path = write_checkpoint_state(current_layout, payload)
    loaded = CheckpointState.model_validate(payload)

    assert path == current_layout.checkpoint_path
    assert payload["trace_line_count"] == 2
    assert loaded.trace_line_count == 2

    with pytest.raises(TraceSessionError, match="cannot move backward"):
        checkpoint_with_trace_line_count(payload, trace_line_count=1)
    with pytest.raises(TraceSessionError, match="non-negative integer"):
        checkpoint_with_trace_line_count(payload, trace_line_count=-1)


def test_trace_checkpoint_writer_appends_then_persists_checkpoint_counter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_layout = layout(tmp_path)
    original_write = write_checkpoint_state
    observed_trace_counts: list[int] = []

    def spy_write_checkpoint_state(
        target_layout: NamespaceLayout,
        checkpoint: CheckpointState | dict,
    ) -> Path:
        observed_trace_counts.append(len(load_trace_events(target_layout.trace_path)))
        return original_write(target_layout, checkpoint)

    monkeypatch.setattr("agent.trace.write_checkpoint_state", spy_write_checkpoint_state)
    writer = TraceCheckpointWriter.for_checkpoint(
        current_layout,
        checkpoint_data(trace_line_count=0),
    )

    result = writer.append_and_checkpoint(
        "session_resume",
        ts="2026-04-30T10:00:00Z",
        reason="manual",
    )

    assert observed_trace_counts == [1]
    assert result.trace.trace_id == "events.jsonl#L1"
    assert result.checkpoint_path == current_layout.checkpoint_path
    assert result.checkpoint.trace_line_count == 1
    assert writer.trace_line_count == 1

    loaded_checkpoint = load_checkpoint_for_layout(current_layout)
    assert loaded_checkpoint.trace_line_count == 1
    assert event_payloads(current_layout)[0]["kind"] == "session_resume"


def test_trace_checkpoint_writer_reuses_updated_checkpoint_for_next_event(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    writer = TraceCheckpointWriter.for_checkpoint(
        current_layout,
        checkpoint_data(trace_line_count=0),
    )

    first = writer.append_and_checkpoint(
        "session_resume",
        ts="2026-04-30T10:00:00Z",
    )
    second = writer.append_and_checkpoint(
        "round_start",
        round=1,
        phase="warmup",
        ts="2026-04-30T10:01:00Z",
    )

    assert first.trace.trace_id == "events.jsonl#L1"
    assert second.trace.trace_id == "events.jsonl#L2"
    assert second.checkpoint.trace_line_count == 2
    assert load_checkpoint_for_layout(current_layout).trace_line_count == 2


@pytest.mark.parametrize(
    "override",
    [
        {"session_id": "sess_other"},
        {"namespace": "other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"},
    ],
)
def test_trace_checkpoint_writer_rejects_checkpoint_context_mismatch_before_append(
    tmp_path: Path,
    override: dict[str, str],
) -> None:
    current_layout = layout(tmp_path)
    writer = TraceCheckpointWriter.for_checkpoint(
        current_layout,
        checkpoint_data(trace_line_count=0),
    )

    with pytest.raises(TraceSessionError, match="checkpoint"):
        writer.append_and_checkpoint(
            "session_resume",
            checkpoint=checkpoint_data(trace_line_count=0, **override),
            ts="2026-04-30T10:00:00Z",
        )

    assert not current_layout.trace_path.exists()
    assert not current_layout.checkpoint_path.exists()


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
