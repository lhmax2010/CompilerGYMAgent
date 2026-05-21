from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import agent.fs_memory as fs_memory
from agent.fs_memory import (
    NamespaceLayout,
    TraceLoadError,
    TraceWriteError,
    append_trace_event,
    iter_trace_events,
    load_trace_events,
    trace_event_payload,
)
from agent.registry import ProjectNamespace


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


def event_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "ts": "2026-04-30T10:23:45Z",
        "kind": "round_start",
        "session_id": "sess_20260430_abc",
        "namespace": str(namespace()),
    }
    data.update(overrides)
    return data


def test_append_trace_event_writes_jsonl_and_returns_line_reference(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)

    first = append_trace_event(
        current_layout,
        event_data(
            ts=datetime(2026, 4, 30, 10, 23, 45, tzinfo=UTC),
            round=12,
            phase="steady_state",
            mode="dry_run",
            message="编译 trace",
        ),
    )
    second = append_trace_event(
        current_layout,
        event_data(kind="trial_start", trial_id="r12_t3", combo=["-O3"], mode="exploit"),
    )

    assert first.line_number == 1
    assert first.byte_offset == 0
    assert first.trace_id == "events.jsonl#L1"
    assert second.line_number == 2
    assert second.byte_offset > first.byte_offset

    lines = current_layout.trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "编译 trace" in lines[0]
    assert json.loads(lines[0])["mode"] == "dry_run"

    loaded = load_trace_events(current_layout.trace_path)
    assert len(loaded) == 2
    assert trace_event_payload(loaded[0])["round"] == 12
    assert trace_event_payload(loaded[1])["trial_id"] == "r12_t3"
    assert tuple(iter_trace_events(current_layout.trace_path)) == loaded


@pytest.mark.parametrize(
    ("bad_event", "expected"),
    [
        ({"ts": "not-a-time", "kind": "round_start"}, "ISO 8601"),
        ({"ts": "2026-04-30T10:23:45Z", "kind": " round_start"}, "whitespace"),
        ({"ts": "2026-04-30T10:23:45Z", "kind": "round/start"}, "ASCII"),
        ({"ts": "2026-04-30T10:23:45Z", "kind": "round_start", "value": float("inf")}, "non-finite"),
        ({"ts": "2026-04-30T10:23:45Z", "kind": "round_start", "value": Path("x")}, "non-JSON"),
    ],
)
def test_append_trace_event_rejects_invalid_payloads(
    tmp_path: Path,
    bad_event: dict[str, object],
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=expected):
        append_trace_event(layout(tmp_path), bad_event)


def test_append_trace_event_rejects_oversized_event(tmp_path: Path) -> None:
    payload = event_data(message="x" * fs_memory.MAX_TRACE_EVENT_BYTES)

    with pytest.raises(TraceWriteError, match="too large"):
        append_trace_event(layout(tmp_path), payload)


def test_append_trace_event_rejects_unterminated_existing_file(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    current_layout.trace_path.parent.mkdir(parents=True)
    current_layout.trace_path.write_text(
        '{"kind":"round_start","ts":"2026-04-30T10:23:45Z"}',
        encoding="utf-8",
    )

    with pytest.raises(TraceWriteError, match="newline-terminated"):
        append_trace_event(current_layout, event_data(kind="trial_start"))


def test_trace_append_and_load_reject_symlink_target(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    current_layout.trace_path.parent.mkdir(parents=True)
    target = current_layout.trace_path.parent / "real_events.jsonl"
    target.write_text("", encoding="utf-8")
    try:
        current_layout.trace_path.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is not available: {exc}")

    with pytest.raises(TraceWriteError, match="symlink"):
        append_trace_event(current_layout, event_data())
    with pytest.raises(TraceLoadError, match="symlink"):
        load_trace_events(current_layout.trace_path)


@pytest.mark.parametrize(
    ("raw_bytes", "expected"),
    [
        (b"{not-json}\n", "failed to parse JSON"),
        (b"[]\n", "JSON object"),
        (b"\n", "empty"),
        (b'{"ts":"2026-04-30T10:23:45Z","kind":"round_start","value":NaN}\n', "not allowed"),
        (b"\xff\n", "valid UTF-8"),
        (b'{"ts":"2026-04-30T10:23:45Z","kind":"round_start"}', "newline-terminated"),
    ],
)
def test_load_trace_events_rejects_invalid_jsonl(
    tmp_path: Path,
    raw_bytes: bytes,
    expected: str,
) -> None:
    current_layout = layout(tmp_path)
    current_layout.trace_path.parent.mkdir(parents=True)
    current_layout.trace_path.write_bytes(raw_bytes)

    with pytest.raises(TraceLoadError, match=expected):
        load_trace_events(current_layout.trace_path)


def test_load_trace_events_rejects_oversized_line(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    current_layout.trace_path.parent.mkdir(parents=True)
    current_layout.trace_path.write_bytes(b"x" * (fs_memory.MAX_TRACE_EVENT_BYTES + 1) + b"\n")

    with pytest.raises(TraceLoadError, match="too large"):
        load_trace_events(current_layout.trace_path)


def test_load_trace_events_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert load_trace_events(layout(tmp_path).trace_path) == ()


def test_append_trace_event_rejects_directory_target(tmp_path: Path) -> None:
    current_layout = layout(tmp_path)
    current_layout.trace_path.mkdir(parents=True)

    with pytest.raises(TraceWriteError, match="directory"):
        append_trace_event(current_layout, event_data())
