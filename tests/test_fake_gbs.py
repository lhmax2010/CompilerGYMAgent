from __future__ import annotations

import os
import signal

import psutil
import pytest

from agent.skills.fake_gbs import FakeGbsHarness, FakeGbsNoiseModel
from tests.fixtures.fake_workspace import create_fake_workspace


pytestmark = pytest.mark.skipif(os.name != "posix", reason="fake_gbs uses process_runner")


def test_fake_gbs_compile_and_benchmark_use_real_process_runner(tmp_path) -> None:
    fake = create_fake_workspace(tmp_path)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=tmp_path / "fake_gbs",
        session_id="sess_fake_gbs_real",
        seed=11,
    )

    compile_result = harness.compile(["-O3", "-funroll-loops"], trial_id="trial_real")

    assert compile_result.status == "success"
    assert compile_result.artifact_path is not None
    assert compile_result.artifact_path.exists()
    assert compile_result.artifact_hash is not None
    assert compile_result.stdout_path.read_text(encoding="utf-8").startswith("compiled")
    assert compile_result.stderr_path.exists()
    assert compile_result.lease.record.pgid == compile_result.lease.record.pid
    assert compile_result.lease.lease_id == compile_result.lease.record.lease_id
    assert compile_result.lease.record.trial_id == "trial_real"
    assert compile_result.env_markers["AGENT_SESSION_ID"] == "sess_fake_gbs_real"
    assert compile_result.env_markers["AGENT_TRIAL_ID"] == "trial_real"
    assert compile_result.env_markers["AGENT_LEASE_ID"] == compile_result.lease.lease_id
    assert compile_result.env_markers["AGENT_PROCESS_ROLE"] == "compile"

    benchmark_result = harness.benchmark(
        compile_result.artifact_path,
        trial_id="trial_real",
        run_index=0,
        noise_profile="gaussian",
    )

    assert benchmark_result.status == "success"
    assert benchmark_result.score is not None
    assert benchmark_result.artifact_hash == compile_result.artifact_hash
    assert benchmark_result.artifact_hash_verified is True
    assert benchmark_result.stdout_path.read_text(encoding="utf-8").startswith("SCORE ")
    assert benchmark_result.lease.record.pgid == benchmark_result.lease.record.pid
    assert benchmark_result.env_markers["AGENT_LEASE_ID"] == benchmark_result.lease.lease_id
    assert benchmark_result.env_markers["AGENT_PROCESS_ROLE"] == "benchmark"


@pytest.mark.parametrize(
    ("mode", "failure_mode", "expected_status"),
    [
        ("compile", "invalid_option", "invalid_option"),
        ("compile", "artifact_missing", "artifact_missing"),
        ("compile", "oom_like_exit", "oom_like_exit"),
        ("compile", "crash_signal", "crash_signal"),
        ("compile", "timeout", "timeout"),
        ("benchmark", "score_parse_failed", "score_parse_failed"),
    ],
)
def test_fake_gbs_failure_modes_use_real_process_exit_paths(
    tmp_path, mode: str, failure_mode: str, expected_status: str
) -> None:
    fake = create_fake_workspace(tmp_path)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=tmp_path / f"fake_gbs_{mode}_{failure_mode}",
        session_id=f"sess_fake_{mode}_{failure_mode}",
        seed=17,
    )

    if mode == "compile":
        result = harness.compile(
            ["-finvalid-option"] if failure_mode == "invalid_option" else ["-O2"],
            trial_id=f"trial_{failure_mode}",
            failure_mode=failure_mode,  # type: ignore[arg-type]
            timeout_seconds=0.1 if failure_mode == "timeout" else 2.0,
        )
    else:
        compile_result = harness.compile(["-O2"], trial_id="trial_bench_source")
        assert compile_result.artifact_path is not None
        result = harness.benchmark(
            compile_result.artifact_path,
            trial_id=f"trial_{failure_mode}",
            run_index=0,
            failure_mode=failure_mode,  # type: ignore[arg-type]
            timeout_seconds=0.1 if failure_mode == "timeout" else 2.0,
        )

    assert result.status == expected_status
    assert result.stdout_path.exists()
    assert result.stderr_path.exists()

    if failure_mode == "timeout":
        assert result.cleanup is not None
        assert result.cleanup.action == "killed"
        assert result.updated_lease is not None
        assert result.updated_lease.status == "killed"
        assert result.cleanup.killed_pgids
        for pgid in result.cleanup.killed_pgids:
            assert not _pgid_has_members(pgid)
    elif failure_mode == "crash_signal":
        assert result.signal == signal.SIGSEGV
        assert result.updated_lease is not None
        assert result.updated_lease.status == "killed"
    elif failure_mode == "oom_like_exit":
        assert result.exit_code == 137
        assert result.updated_lease is not None
        assert result.updated_lease.status == "exited"
    elif failure_mode == "score_parse_failed":
        assert result.exit_code == 0
        assert getattr(result, "score") is None


def test_fake_gbs_seed_replay_includes_bursty_state(tmp_path) -> None:
    first = _score_sequence(tmp_path / "one", seed=23, profile="bursty")
    second = _score_sequence(tmp_path / "two", seed=23, profile="bursty")

    assert first == second


def test_bursty_markov_profile_has_stateful_clustered_bursts() -> None:
    model = FakeGbsNoiseModel(seed=31)
    samples = [model.sample("bursty") for _ in range(100)]
    states = [sample.state for sample in samples]

    non_healthy = [state for state in states if state != "healthy"]
    adjacent_non_healthy = sum(
        1
        for left, right in zip(states, states[1:], strict=False)
        if left != "healthy" and right != "healthy"
    )
    failed_runs = sum(1 for state in states if state == "failed")

    assert len(non_healthy) >= 20
    assert adjacent_non_healthy >= 10
    assert failed_runs >= 3
    assert len(set(states)) == 3


def _score_sequence(tmp_path, *, seed: int, profile: str) -> list[tuple[float, str | None]]:
    fake = create_fake_workspace(tmp_path)
    harness = FakeGbsHarness(
        layout=fake.layout,
        root=tmp_path / "fake_gbs",
        session_id=f"sess_seed_{seed}",
        seed=seed,
    )
    compile_result = harness.compile(["-O3"], trial_id="trial_seed")
    assert compile_result.artifact_path is not None
    values = []
    for index in range(8):
        result = harness.benchmark(
            compile_result.artifact_path,
            trial_id="trial_seed",
            run_index=index,
            noise_profile=profile,  # type: ignore[arg-type]
        )
        assert result.status == "success"
        assert result.score is not None
        assert result.noise is not None
        values.append((round(result.score, 8), result.noise.state))
    return values


def _pgid_has_members(pgid: int) -> bool:
    for proc in psutil.process_iter(["pid", "status"]):
        try:
            if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                continue
            if os.getpgid(proc.info["pid"]) == pgid:
                return True
        except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False
