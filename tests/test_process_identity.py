from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent import (
    AGENT_LEASE_ID_ENV,
    AGENT_PROCESS_ROLE_ENV,
    AGENT_SESSION_ID_ENV,
    AGENT_TRIAL_ID_ENV,
    ProcessIdentity,
    ProcessRecord,
    compute_cmdline_hash,
    generate_lease_id,
)


def test_process_record_accepts_expected_fields() -> None:
    record = ProcessRecord(
        pid=123,
        pgid=456,
        create_time=1.25,
        session_id="sess_process_1",
        cmdline_hash=compute_cmdline_hash(["python", "-m", "worker"]),
        env_marker_visible_at_spawn=True,
        cgroup_path=None,
    )

    assert record.pid == 123
    assert record.pgid == 456
    assert record.session_id == "sess_process_1"
    assert record.trial_id is None
    assert record.lease_id is None
    assert record.env_marker_visible_at_spawn is True
    assert ProcessIdentity.model_validate(record.model_dump()).model_dump() == (
        record.model_dump()
    )
    assert AGENT_SESSION_ID_ENV == "AGENT_SESSION_ID"
    assert AGENT_TRIAL_ID_ENV == "AGENT_TRIAL_ID"
    assert AGENT_LEASE_ID_ENV == "AGENT_LEASE_ID"
    assert AGENT_PROCESS_ROLE_ENV == "AGENT_PROCESS_ROLE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid", 0),
        ("pgid", -1),
        ("create_time", -0.1),
        ("cmdline_hash", "not-a-sha"),
        ("trial_id", "../escape"),
        ("lease_id", "bad/slash"),
        ("cgroup_path", ""),
    ],
)
def test_process_record_rejects_invalid_field_values(
    field: str, value: object
) -> None:
    data = {
        "pid": 123,
        "pgid": 456,
        "create_time": 1.25,
        "session_id": "sess_process_1",
        "cmdline_hash": compute_cmdline_hash(["python"]),
        "env_marker_visible_at_spawn": True,
        "cgroup_path": None,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        ProcessRecord.model_validate(data)


@pytest.mark.parametrize(
    "session_id",
    ["../escape", "bad/slash", "bad space", " trimmed", ".", ""],
)
def test_process_record_reuses_safe_session_id_contract(session_id: str) -> None:
    with pytest.raises(ValidationError):
        ProcessRecord(
            pid=123,
            pgid=456,
            create_time=1.25,
            session_id=session_id,
            cmdline_hash=compute_cmdline_hash(["python"]),
            env_marker_visible_at_spawn=True,
        )


def test_compute_cmdline_hash_is_stable_and_boundary_sensitive() -> None:
    assert compute_cmdline_hash(["ab", "c"]) == compute_cmdline_hash(["ab", "c"])
    assert compute_cmdline_hash(["ab", "c"]) != compute_cmdline_hash(["a", "bc"])


def test_generate_lease_id_is_pid_independent_and_role_prefixed() -> None:
    lease_id = generate_lease_id("compile")

    assert lease_id.startswith("compile-")
    assert len(lease_id.removeprefix("compile-")) == 32

    with pytest.raises(ValueError):
        generate_lease_id("bad/slash")
