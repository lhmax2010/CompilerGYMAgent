from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agent import (
    ProcessLease,
    ProcessRegistryError,
    ProcessRecord,
    compute_cmdline_hash,
    load_process_lease,
    load_process_lease_for_layout,
    load_process_leases,
    mark_process_exited,
    mark_process_killed,
    mark_process_unknown,
    mark_process_unsafe_skip,
    process_lease_path,
    process_lease_payload,
    process_leases_dir,
    register_process_lease,
    transition_process_lease,
)
from tests.fixtures.fake_workspace import create_fake_workspace


def test_register_process_lease_writes_derived_yaml(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    record = _record(pid=123)
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)

    lease = register_process_lease(
        fake.layout,
        record=record,
        trial_id="trial_1",
        role="compile",
        now=now,
    )

    expected_path = (
        fake.layout.state_dir
        / "processes"
        / "sess_1"
        / "trial_1"
        / "compile-123.yaml"
    )
    assert process_lease_path(
        fake.layout,
        session_id="sess_1",
        trial_id="trial_1",
        role="compile",
        pid=123,
    ) == expected_path
    assert expected_path.exists()
    assert oct(expected_path.stat().st_mode & 0o777) == "0o600"
    assert lease.status == "running"
    assert lease.created_at == "2026-06-01T08:00:00+00:00"
    assert "integrity" not in process_lease_payload(lease)
    assert load_process_lease(expected_path) == lease
    assert load_process_lease_for_layout(
        fake.layout,
        session_id="sess_1",
        trial_id="trial_1",
        role="compile",
        pid=123,
    ) == lease
    assert load_process_leases(fake.layout) == (lease,)
    assert process_leases_dir(fake.layout) == fake.layout.state_dir / "processes"


def test_process_lease_status_transitions(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    now = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)

    exited = mark_process_exited(
        fake.layout,
        _register(fake.layout, pid=201, now=now),
        exit_code=7,
        now=now + timedelta(seconds=1),
    )
    killed = mark_process_killed(
        fake.layout,
        _register(fake.layout, pid=202, now=now),
        signal=15,
        cleanup_attempts=1,
        now=now + timedelta(seconds=2),
    )
    unsafe = mark_process_unsafe_skip(
        fake.layout,
        _register(fake.layout, pid=203, now=now),
        cleanup_attempts=2,
        now=now + timedelta(seconds=3),
    )
    unknown = mark_process_unknown(
        fake.layout,
        _register(fake.layout, pid=204, now=now),
        cleanup_attempts=3,
        now=now + timedelta(seconds=4),
    )

    assert exited.status == "exited"
    assert exited.exit_code == 7
    assert killed.status == "killed"
    assert killed.signal == 15
    assert killed.cleanup_attempts == 1
    assert unsafe.status == "unsafe_skip"
    assert unsafe.cleanup_attempts == 2
    assert unknown.status == "unknown"
    assert unknown.cleanup_attempts == 3
    assert tuple(lease.record.pid for lease in load_process_leases(fake.layout)) == (
        201,
        202,
        203,
        204,
    )


def test_process_lease_rejects_invalid_transitions_and_fields(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lease = _register(fake.layout, pid=301)

    with pytest.raises(ProcessRegistryError, match="transition status"):
        transition_process_lease(fake.layout, lease, status="running")

    exited = mark_process_exited(fake.layout, lease, exit_code=0)
    with pytest.raises(ProcessRegistryError, match="terminal status"):
        mark_process_unknown(fake.layout, exited)

    with pytest.raises(ValidationError):
        ProcessLease.model_validate(
            {
                **exited.model_dump(mode="json"),
                "status": "killed",
                "exit_code": 0,
                "signal": None,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_id", "../escape"),
        ("trial_id", "bad/slash"),
        ("role", "bad role"),
    ],
)
def test_process_lease_rejects_unsafe_path_atoms(field: str, value: str) -> None:
    data = _running_lease(pid=401).model_dump(mode="json")
    data[field] = value
    if field == "session_id":
        data["record"]["session_id"] = value

    with pytest.raises(ValidationError):
        ProcessLease.model_validate(data)


def test_process_lease_loader_rejects_alias_and_symlink(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    lease = _register(fake.layout, pid=501)
    path = process_lease_path(
        fake.layout,
        session_id=lease.session_id,
        trial_id=lease.trial_id,
        role=lease.role,
        pid=lease.record.pid,
    )
    path.write_text("a: &a 1\nb: *a\n", encoding="utf-8")
    with pytest.raises(ProcessRegistryError, match="aliases"):
        load_process_lease(path)

    target = tmp_path / "target.yaml"
    target.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "lease-link.yaml"
    symlink.symlink_to(target)
    with pytest.raises(ProcessRegistryError, match="symlink"):
        load_process_lease(symlink)


def _register(layout, *, pid: int, now: datetime | None = None):
    return register_process_lease(
        layout,
        record=_record(pid=pid),
        trial_id=f"trial_{pid}",
        role="compile",
        now=now,
    )


def _running_lease(*, pid: int) -> ProcessLease:
    return ProcessLease(
        session_id="sess_1",
        trial_id=f"trial_{pid}",
        role="compile",
        record=_record(pid=pid),
        created_at="2026-06-01T08:00:00+00:00",
        updated_at="2026-06-01T08:00:00+00:00",
    )


def _record(*, pid: int) -> ProcessRecord:
    return ProcessRecord(
        pid=pid,
        pgid=pid,
        create_time=1.0 + pid,
        session_id="sess_1",
        cmdline_hash=compute_cmdline_hash(["python", str(pid)]),
        env_marker_visible_at_spawn=True,
        cgroup_path=None,
    )
