from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc
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
    TraceCheckpointAlignment,
    TraceCheckpointWriter,
    TraceSessionError,
    TraceSessionSpan,
    TraceSessionWriter,
    checkpoint_with_reconciled_trace_count,
    checkpoint_with_trace_line_count,
    count_trace_events,
    inspect_trace_checkpoint_alignment,
    inspect_trace_session_spans,
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


def test_trace_checkpoint_alignment_reports_aligned_state(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )

    alignment = inspect_trace_checkpoint_alignment(
        current_layout,
        checkpoint_data(trace_line_count=1),
    )
    payload = checkpoint_with_reconciled_trace_count(
        current_layout,
        checkpoint_data(trace_line_count=1),
    )

    assert isinstance(alignment, TraceCheckpointAlignment)
    assert alignment.status == "aligned"
    assert alignment.needs_reconcile is False
    assert alignment.can_reconcile is False
    assert alignment.checkpoint_trace_line_count == 1
    assert alignment.actual_trace_line_count == 1
    assert payload["trace_line_count"] == 1


def test_trace_checkpoint_alignment_reconciles_legacy_missing_count(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )

    alignment = inspect_trace_checkpoint_alignment(current_layout, checkpoint_data())
    payload = checkpoint_with_reconciled_trace_count(current_layout, checkpoint_data())

    assert alignment.status == "checkpoint_missing"
    assert alignment.needs_reconcile is True
    assert alignment.can_reconcile is True
    assert alignment.checkpoint_trace_line_count is None
    assert alignment.actual_trace_line_count == 1
    assert payload["trace_line_count"] == 1


def test_trace_checkpoint_alignment_reconciles_trace_ahead_after_crash(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:01:00Z", "kind": "trial_start"},
        expected_line_number=2,
    )

    alignment = inspect_trace_checkpoint_alignment(
        current_layout,
        checkpoint_data(trace_line_count=1),
    )
    payload = checkpoint_with_reconciled_trace_count(
        current_layout,
        checkpoint_data(trace_line_count=1),
    )

    assert alignment.status == "trace_ahead"
    assert alignment.needs_reconcile is True
    assert alignment.can_reconcile is True
    assert alignment.checkpoint_trace_line_count == 1
    assert alignment.actual_trace_line_count == 2
    assert payload["trace_line_count"] == 2


def test_trace_checkpoint_alignment_rejects_checkpoint_ahead_of_trace(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:00:00Z", "kind": "round_start"},
        expected_line_number=1,
    )

    alignment = inspect_trace_checkpoint_alignment(
        current_layout,
        checkpoint_data(trace_line_count=3),
    )

    assert alignment.status == "checkpoint_ahead"
    assert alignment.needs_reconcile is True
    assert alignment.can_reconcile is False
    assert alignment.checkpoint_trace_line_count == 3
    assert alignment.actual_trace_line_count == 1
    with pytest.raises(TraceSessionError, match="ahead of trace events"):
        checkpoint_with_reconciled_trace_count(
            current_layout,
            checkpoint_data(trace_line_count=3),
        )


def test_trace_checkpoint_alignment_rejects_namespace_mismatch(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    checkpoint = checkpoint_data(
        namespace="other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3",
        trace_line_count=0,
    )

    with pytest.raises(TraceSessionError, match="namespace does not match"):
        inspect_trace_checkpoint_alignment(current_layout, checkpoint)


def test_trace_session_spans_report_conservative_line_ranges(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {
            "ts": "2026-04-30T10:00:00Z",
            "kind": "round_start",
            "session_id": "sess_a",
        },
        expected_line_number=1,
    )
    append_trace_event(
        current_layout,
        {"ts": "2026-04-30T10:01:00Z", "kind": "bootstrap_probe"},
        expected_line_number=2,
    )
    append_trace_event(
        current_layout,
        {
            "ts": "2026-04-30T10:02:00Z",
            "kind": "round_start",
            "session_id": "sess_b",
        },
        expected_line_number=3,
    )
    append_trace_event(
        current_layout,
        {
            "ts": "2026-04-30T10:03:00Z",
            "kind": "trial_end",
            "session_id": "sess_a",
        },
        expected_line_number=4,
    )

    spans = inspect_trace_session_spans(current_layout)

    assert spans == (
        TraceSessionSpan(
            session_id="sess_a",
            first_line_number=1,
            last_line_number=4,
            event_count=2,
        ),
        TraceSessionSpan(
            session_id="sess_b",
            first_line_number=3,
            last_line_number=3,
            event_count=1,
        ),
    )


def test_trace_session_spans_accept_path_and_missing_trace(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)

    assert inspect_trace_session_spans(current_layout.trace_path) == ()


def test_trace_session_spans_reject_invalid_session_id(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    append_trace_event(
        current_layout,
        {
            "ts": "2026-04-30T10:00:00Z",
            "kind": "round_start",
            "session_id": "bad session",
        },
        expected_line_number=1,
    )

    with pytest.raises(TraceSessionError, match="trace session_id"):
        inspect_trace_session_spans(current_layout)


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
        generator="local_mutation",
        rejection_reason="duplicate_hash",
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


def test_trace_session_writer_candidate_rejected_requires_reason_fields(
    tmp_path: Path,
) -> None:
    writer = TraceSessionWriter.for_layout(
        layout(tmp_path),
        session_id="sess_20260430_abc",
    )

    with pytest.raises(TraceSessionError, match="matched_rule_id"):
        writer.candidate_rejected(
            candidate=["-O3", "-flto=thin"],
            generator="llm_proposer",
            rejection_reason="experience_soft_filter_with_low_score",
            matched_rule_path="experiences/tentative/exp_001.yaml",
            filter_strength="soft",
            penalty=0.3,
            score_after_penalty=0.42,
            ts="2026-04-30T10:00:00Z",
        )
    with pytest.raises(TraceSessionError, match="filter_strength"):
        writer.candidate_rejected(
            candidate=["-O3"],
            generator="llm_proposer",
            rejection_reason="experience_hard_filter",
            matched_rule_id="exp_002",
            matched_rule_path="experiences/verified/exp_002.yaml",
            filter_strength="soft",
            ts="2026-04-30T10:00:00Z",
        )
    with pytest.raises(TraceSessionError, match="unknown"):
        writer.candidate_rejected(
            candidate=["-O3"],
            generator="llm_proposer",
            rejection_reason="mystery_filter",
            ts="2026-04-30T10:00:00Z",
        )

    assert not layout(tmp_path).trace_path.exists()


@pytest.mark.parametrize(
    ("rejection_reason", "field", "value", "extra"),
    [
        ("duplicate_hash", "matched_trial", "", {}),
        ("duplicate_hash", "matched_trial", "  ", {}),
        ("failed_subset_match", "matched_failed_path", 12, {"matched_failed": "fail_1"}),
        ("whitelist_unknown_option", "unknown_options", [], {}),
        ("whitelist_unknown_option", "unknown_options", ["-O3", ""], {}),
        (
            "mutual_exclusion",
            "conflicting_options",
            ["-O2", "  "],
            {"conflict_group": "opt_level"},
        ),
    ],
)
def test_trace_session_writer_candidate_rejected_rejects_empty_references(
    tmp_path: Path,
    rejection_reason: str,
    field: str,
    value: object,
    extra: dict[str, object],
) -> None:
    writer = TraceSessionWriter.for_layout(
        layout(tmp_path),
        session_id="sess_20260430_abc",
    )

    with pytest.raises(TraceSessionError, match=field):
        writer.candidate_rejected(
            candidate=["-O3"],
            generator="llm_proposer",
            rejection_reason=rejection_reason,
            ts="2026-04-30T10:00:00Z",
            **extra,
            **{field: value},
        )


def test_trace_session_writer_candidate_rejected_records_rule_match_contract(
    tmp_path: Path,
) -> None:
    current_layout = layout(tmp_path)
    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
    )

    result = writer.candidate_rejected(
        candidate=["-O3", "-flto=thin"],
        candidate_hash="sha256:" + "a" * 64,
        generator="llm_proposer",
        rejection_reason="experience_soft_filter_with_low_score",
        matched_rule_id="exp_001",
        matched_rule_path="experiences/tentative/exp_001.yaml",
        filter_strength="soft",
        penalty=0.3,
        score_after_penalty=0.42,
        ts="2026-04-30T10:00:00Z",
    )

    payload = event_payloads(current_layout)[0]
    assert result.trace_id == "events.jsonl#L1"
    assert payload["kind"] == "candidate_rejected"
    assert payload["candidate"] == ["-O3", "-flto=thin"]
    assert payload["candidate_hash"] == "sha256:" + "a" * 64
    assert payload["generator"] == "llm_proposer"
    assert payload["matched_rule_id"] == "exp_001"
    assert payload["matched_rule_path"] == "experiences/tentative/exp_001.yaml"
    assert payload["filter_strength"] == "soft"
    assert payload["penalty"] == 0.3
    assert payload["score_after_penalty"] == 0.42


def test_trace_session_writer_runtime_event_family_helpers(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    writer = TraceSessionWriter.for_layout(
        current_layout,
        session_id="sess_20260430_abc",
    )

    writer.process_event(
        "compile_start",
        pid=12345,
        pgid=12345,
        create_time=1730000000.123,
        cmdline_hash="sha256:" + "b" * 64,
        ts="2026-04-30T10:00:00Z",
    )
    writer.llm_call(
        model="moonshot-v1-128k",
        prompt_tokens=1234,
        completion_tokens=567,
        cost_usd=0.12,
        ts="2026-04-30T10:01:00Z",
    )
    writer.memory_op(
        op_type="read",
        path=Path("learned/rules/rule_001.yaml"),
        hits=3,
        ts="2026-04-30T10:02:00Z",
    )
    writer.kg_op(
        op_id="kgop_001",
        op_type="merge",
        backup_ref="kg_backups/backup_001.yaml",
        ts="2026-04-30T10:03:00Z",
    )
    writer.user_action(
        command="pause",
        args=["--reason", "inspect"],
        ts="2026-04-30T10:04:00Z",
    )
    writer.workspace_snapshot(
        phase="post",
        ws_hash="ws_post_xyz",
        source_changes=["modified:codec.c"],
        ts="2026-04-30T10:05:00Z",
    )

    payloads = event_payloads(current_layout)
    assert [payload["kind"] for payload in payloads] == [
        "compile_start",
        "llm_call",
        "memory_op",
        "kg_op",
        "user_action",
        "workspace_snapshot_post",
    ]
    assert payloads[0]["pid"] == 12345
    assert payloads[1]["model"] == "moonshot-v1-128k"
    assert payloads[2]["path"] == "learned/rules/rule_001.yaml"
    assert payloads[3]["backup_ref"] == "kg_backups/backup_001.yaml"
    assert payloads[4]["args"] == ["--reason", "inspect"]
    assert payloads[5]["source_changes"] == ["modified:codec.c"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt_tokens", -1),
        ("completion_tokens", -1),
        ("prompt_tokens", 1.5),
        ("completion_tokens", True),
    ],
)
def test_trace_session_writer_llm_call_rejects_invalid_token_counts(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    writer = TraceSessionWriter.for_layout(
        layout(tmp_path),
        session_id="sess_20260430_abc",
    )
    kwargs: dict[str, object] = {
        "model": "moonshot-v1-128k",
        "prompt_tokens": 1,
        "completion_tokens": 2,
        field: value,
        "ts": "2026-04-30T10:00:00Z",
    }

    with pytest.raises(TraceSessionError, match=field):
        writer.llm_call(**kwargs)


def test_trace_session_writer_rejects_invalid_workspace_snapshot_phase(
    tmp_path: Path,
) -> None:
    writer = TraceSessionWriter.for_layout(
        layout(tmp_path),
        session_id="sess_20260430_abc",
    )

    with pytest.raises(TraceSessionError, match="phase"):
        writer.workspace_snapshot(
            phase="middle",
            ws_hash="ws_mid_xyz",
            ts="2026-04-30T10:00:00Z",
        )
