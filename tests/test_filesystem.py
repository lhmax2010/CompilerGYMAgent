from __future__ import annotations

from pathlib import Path

import pytest

from agent.filesystem import (
    RemoteFilesystemWarning,
    inspect_filesystem,
    is_remote_filesystem_type,
    warn_if_remote_filesystem,
)


MOUNTINFO = """\
11 1 8:1 / / rw,relatime - ext4 /dev/root rw
22 11 0:45 / /home/user/ws rw,relatime - nfs4 server:/exports/ws rw
33 11 0:56 / /home/user/ws/fuse\\040space rw,nosuid - fuse.sshfs sshfs rw
"""


@pytest.mark.parametrize(
    "fs_type",
    ["nfs", "nfs4", "fuse", "fuse.sshfs", "cifs", "9p", "lustre"],
)
def test_is_remote_filesystem_type_flags_remote_like_types(fs_type: str) -> None:
    assert is_remote_filesystem_type(fs_type) is True


@pytest.mark.parametrize("fs_type", ["ext4", "xfs", "btrfs", "overlay", "tmpfs"])
def test_is_remote_filesystem_type_leaves_local_like_types(fs_type: str) -> None:
    assert is_remote_filesystem_type(fs_type) is False


def test_inspect_filesystem_uses_longest_mount_match_and_decodes_paths() -> None:
    inspection = inspect_filesystem(
        Path("/home/user/ws/fuse space/project"),
        mountinfo_text=MOUNTINFO,
    )

    assert inspection.mount is not None
    assert inspection.mount.mount_point == Path("/home/user/ws/fuse space")
    assert inspection.fs_type == "fuse.sshfs"
    assert inspection.source == "sshfs"
    assert inspection.is_remote_like is True


def test_inspect_filesystem_reports_local_mount_without_warning_flag() -> None:
    inspection = inspect_filesystem(Path("/var/tmp/project"), mountinfo_text=MOUNTINFO)

    assert inspection.mount is not None
    assert inspection.mount.mount_point == Path("/")
    assert inspection.fs_type == "ext4"
    assert inspection.is_remote_like is False


def test_warn_if_remote_filesystem_emits_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent.filesystem.inspect_filesystem",
        lambda path: inspect_filesystem(Path("/home/user/ws/project"), mountinfo_text=MOUNTINFO),
    )

    with pytest.warns(RemoteFilesystemWarning, match="unverified"):
        inspection = warn_if_remote_filesystem(
            Path("/home/user/ws/project"),
            context="workspace lock",
        )

    assert inspection.is_remote_like is True
    assert inspection.warning_message is not None
    assert "workspace lock" in inspection.warning_message


def test_warn_if_remote_filesystem_is_nonblocking_for_local_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent.filesystem.inspect_filesystem",
        lambda path: inspect_filesystem(Path("/var/tmp/project"), mountinfo_text=MOUNTINFO),
    )

    inspection = warn_if_remote_filesystem(Path("/var/tmp/project"), context="agent init")

    assert inspection.is_remote_like is False
    assert inspection.warning_message is None
