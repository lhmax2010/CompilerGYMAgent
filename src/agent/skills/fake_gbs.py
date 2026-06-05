"""fake_gbs harness used by Phase 05 compile/benchmark skill tests.

The harness is intentionally process-backed: even though the compiler and
benchmark behavior is fake, every compile/benchmark run goes through the real
Phase 06 process_runner, process lease registry, env markers, timeout, and
killpg cleanup paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Literal

from agent.fs_memory import NamespaceLayout
from agent.process_cleaner import ProcessCleanupResult, cleanup_process_lease
from agent.process_registry import ProcessLease
from agent.process_runner import (
    ProcessSpawnResult,
    refresh_process_lease_from_popen,
    spawn_process,
)


FakeGbsFailureMode = Literal[
    "invalid_option",
    "timeout",
    "crash_signal",
    "oom_like_exit",
    "artifact_missing",
    "score_parse_failed",
]
FakeGbsNoiseProfile = Literal["gaussian", "right_skewed", "bursty"]
FakeGbsBurstState = Literal["healthy", "degraded", "failed"]

DEFAULT_BURSTY_TRANSITIONS: dict[FakeGbsBurstState, tuple[tuple[FakeGbsBurstState, float], ...]] = {
    "healthy": (("healthy", 0.82), ("degraded", 0.16), ("failed", 0.02)),
    "degraded": (("healthy", 0.15), ("degraded", 0.65), ("failed", 0.20)),
    "failed": (("healthy", 0.45), ("degraded", 0.25), ("failed", 0.30)),
}


@dataclass(frozen=True)
class FakeGbsNoiseSample:
    profile: FakeGbsNoiseProfile
    value: float
    state: FakeGbsBurstState | None = None


@dataclass(frozen=True)
class FakeGbsCompileResult:
    status: str
    combo: tuple[str, ...]
    artifact_path: Path | None
    artifact_hash: str | None
    stdout_path: Path
    stderr_path: Path
    result_json_path: Path
    lease: ProcessLease
    updated_lease: ProcessLease | None
    exit_code: int | None
    signal: int | None
    worker_pid: int | None
    worker_pgid: int | None
    env_markers: Mapping[str, str | None]
    cleanup: ProcessCleanupResult | None = None


@dataclass(frozen=True)
class FakeGbsBenchmarkResult:
    status: str
    artifact_path: Path
    artifact_hash: str | None
    artifact_hash_verified: bool
    score: float | None
    noise: FakeGbsNoiseSample | None
    stdout_path: Path
    stderr_path: Path
    result_json_path: Path
    lease: ProcessLease
    updated_lease: ProcessLease | None
    exit_code: int | None
    signal: int | None
    worker_pid: int | None
    worker_pgid: int | None
    env_markers: Mapping[str, str | None]
    cleanup: ProcessCleanupResult | None = None


class FakeGbsNoiseModel:
    """Seeded fake benchmark noise with a stateful Markov bursty mode."""

    def __init__(
        self,
        *,
        seed: int,
        bursty_transitions: Mapping[
            FakeGbsBurstState, Sequence[tuple[FakeGbsBurstState, float]]
        ]
        | None = None,
    ) -> None:
        self._rng = Random(seed)
        self._bursty_state: FakeGbsBurstState = "healthy"
        self._bursty_transitions = {
            state: tuple(transitions)
            for state, transitions in (
                DEFAULT_BURSTY_TRANSITIONS
                if bursty_transitions is None
                else bursty_transitions
            ).items()
        }
        _validate_transition_matrix(self._bursty_transitions)

    @property
    def bursty_state(self) -> FakeGbsBurstState:
        return self._bursty_state

    def sample(self, profile: FakeGbsNoiseProfile) -> FakeGbsNoiseSample:
        if profile == "gaussian":
            return FakeGbsNoiseSample(profile=profile, value=self._rng.gauss(0.0, 1.5))
        if profile == "right_skewed":
            return FakeGbsNoiseSample(
                profile=profile,
                value=self._rng.expovariate(1.0 / 2.0) - 2.0,
            )
        state = self._advance_bursty_state()
        if state == "healthy":
            value = self._rng.gauss(0.0, 1.0)
        elif state == "degraded":
            value = self._rng.gauss(-7.0, 2.0)
        else:
            value = self._rng.gauss(-22.0, 4.0)
        return FakeGbsNoiseSample(profile=profile, value=value, state=state)

    def _advance_bursty_state(self) -> FakeGbsBurstState:
        transitions = self._bursty_transitions[self._bursty_state]
        draw = self._rng.random()
        cumulative = 0.0
        for state, probability in transitions:
            cumulative += probability
            if draw <= cumulative:
                self._bursty_state = state
                return state
        self._bursty_state = transitions[-1][0]
        return self._bursty_state


class FakeGbsHarness:
    """Process-backed fake compiler/benchmark harness."""

    def __init__(
        self,
        *,
        layout: NamespaceLayout,
        root: Path,
        session_id: str = "sess_fake_gbs",
        seed: int = 1,
    ) -> None:
        self.layout = layout
        self.root = Path(root)
        self.session_id = session_id
        self.noise_model = FakeGbsNoiseModel(seed=seed)
        self.logs_dir = self.root / "logs"
        self.artifacts_dir = self.root / "artifacts"
        self.results_dir = self.root / "results"
        self.worker_path = self.root / "_fake_gbs_worker.py"
        for directory in (self.logs_dir, self.artifacts_dir, self.results_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.worker_path.write_text(_WORKER_SOURCE, encoding="utf-8")

    def compile(
        self,
        combo: Sequence[str],
        *,
        trial_id: str,
        failure_mode: FakeGbsFailureMode | None = None,
        timeout_seconds: float = 2.0,
        on_spawn: Callable[[ProcessSpawnResult], None] | None = None,
    ) -> FakeGbsCompileResult:
        safe_combo = tuple(str(option) for option in combo)
        effective_failure = failure_mode
        if effective_failure is None and any("invalid" in option for option in safe_combo):
            effective_failure = "invalid_option"
        run_id = _run_id("compile", trial_id)
        artifact_path = self.artifacts_dir / f"{run_id}.artifact"
        context = self._spawn_worker(
            mode="compile",
            trial_id=trial_id,
            role="compile",
            run_id=run_id,
            extra_args=[
                "--combo-json",
                json.dumps(list(safe_combo)),
                "--artifact",
                str(artifact_path),
                "--failure-mode",
                effective_failure or "none",
            ],
            timeout_seconds=timeout_seconds,
            on_spawn=on_spawn,
        )
        payload = _load_result_payload(context.result_json_path)
        artifact_hash = _sha256_file(artifact_path) if artifact_path.exists() else None
        status = _compile_status(context, payload, artifact_path)
        return FakeGbsCompileResult(
            status=status,
            combo=safe_combo,
            artifact_path=artifact_path if artifact_path.exists() else None,
            artifact_hash=artifact_hash,
            stdout_path=context.stdout_path,
            stderr_path=context.stderr_path,
            result_json_path=context.result_json_path,
            lease=context.spawn.lease,
            updated_lease=context.updated_lease,
            exit_code=context.exit_code,
            signal=context.signal,
            worker_pid=_payload_int(payload, "pid"),
            worker_pgid=_payload_int(payload, "pgid"),
            env_markers=_payload_mapping(payload, "env_markers"),
            cleanup=context.cleanup,
        )

    def benchmark(
        self,
        artifact_path: Path,
        *,
        trial_id: str,
        run_index: int,
        noise_profile: FakeGbsNoiseProfile = "gaussian",
        failure_mode: FakeGbsFailureMode | None = None,
        timeout_seconds: float = 2.0,
        on_spawn: Callable[[ProcessSpawnResult], None] | None = None,
    ) -> FakeGbsBenchmarkResult:
        artifact = Path(artifact_path)
        artifact_hash = _sha256_file(artifact) if artifact.exists() else None
        noise = None
        score = None
        if failure_mode is None:
            noise = self.noise_model.sample(noise_profile)
            score = _base_score_for_artifact(artifact) + noise.value
        run_id = _run_id("benchmark", f"{trial_id}_{run_index}")
        context = self._spawn_worker(
            mode="benchmark",
            trial_id=trial_id,
            role="benchmark",
            run_id=run_id,
            extra_args=[
                "--artifact",
                str(artifact),
                "--score",
                "" if score is None else f"{score:.8f}",
                "--failure-mode",
                failure_mode or "none",
            ],
            timeout_seconds=timeout_seconds,
            on_spawn=on_spawn,
        )
        payload = _load_result_payload(context.result_json_path)
        status = _benchmark_status(context, payload, artifact)
        parsed_score = _parse_score(context.stdout_path) if status == "success" else None
        return FakeGbsBenchmarkResult(
            status=status,
            artifact_path=artifact,
            artifact_hash=artifact_hash,
            artifact_hash_verified=artifact_hash is not None and artifact.exists(),
            score=parsed_score,
            noise=noise,
            stdout_path=context.stdout_path,
            stderr_path=context.stderr_path,
            result_json_path=context.result_json_path,
            lease=context.spawn.lease,
            updated_lease=context.updated_lease,
            exit_code=context.exit_code,
            signal=context.signal,
            worker_pid=_payload_int(payload, "pid"),
            worker_pgid=_payload_int(payload, "pgid"),
            env_markers=_payload_mapping(payload, "env_markers"),
            cleanup=context.cleanup,
        )

    def sample_noise(self, profile: FakeGbsNoiseProfile) -> FakeGbsNoiseSample:
        return self.noise_model.sample(profile)

    def _spawn_worker(
        self,
        *,
        mode: str,
        trial_id: str,
        role: str,
        run_id: str,
        extra_args: Sequence[str],
        timeout_seconds: float,
        on_spawn: Callable[[ProcessSpawnResult], None] | None = None,
    ) -> _RunContext:
        stdout_path = self.logs_dir / f"{run_id}.stdout.log"
        stderr_path = self.logs_dir / f"{run_id}.stderr.log"
        result_json_path = self.results_dir / f"{run_id}.json"
        args = [
            sys.executable,
            str(self.worker_path),
            "--mode",
            mode,
            "--result-json",
            str(result_json_path),
            *extra_args,
        ]
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            spawn = spawn_process(
                self.layout,
                args,
                session_id=self.session_id,
                trial_id=trial_id,
                role=role,
                stdout=stdout,  # type: ignore[arg-type]
                stderr=stderr,  # type: ignore[arg-type]
            )
            if on_spawn is not None:
                try:
                    on_spawn(spawn)
                except Exception:
                    cleanup_process_lease(
                        self.layout,
                        spawn.lease,
                        force_suspected=True,
                        kill_timeout_seconds=timeout_seconds,
                    )
                    try:
                        spawn.popen.wait(timeout=timeout_seconds + 2.0)
                    except subprocess.TimeoutExpired:
                        pass
                    raise
        cleanup: ProcessCleanupResult | None = None
        updated_lease: ProcessLease | None = None
        timed_out = False
        try:
            spawn.popen.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            cleanup = cleanup_process_lease(
                self.layout,
                spawn.lease,
                force_suspected=True,
                kill_timeout_seconds=timeout_seconds,
            )
            try:
                spawn.popen.wait(timeout=timeout_seconds + 2.0)
            except subprocess.TimeoutExpired:
                pass
            updated_lease = cleanup.updated_lease
        if updated_lease is None:
            updated_lease = refresh_process_lease_from_popen(self.layout, spawn)
        returncode = spawn.popen.poll()
        return _RunContext(
            spawn=spawn,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_json_path=result_json_path,
            updated_lease=updated_lease,
            exit_code=returncode if returncode is not None and returncode >= 0 else None,
            signal=-returncode if returncode is not None and returncode < 0 else None,
            cleanup=cleanup,
            timed_out=timed_out,
        )


@dataclass(frozen=True)
class _RunContext:
    spawn: ProcessSpawnResult
    stdout_path: Path
    stderr_path: Path
    result_json_path: Path
    updated_lease: ProcessLease | None
    exit_code: int | None
    signal: int | None
    cleanup: ProcessCleanupResult | None
    timed_out: bool


def _compile_status(context: _RunContext, payload: Mapping[str, object], artifact: Path) -> str:
    if context.timed_out:
        return "timeout"
    if context.signal:
        return "crash_signal"
    if context.exit_code == 137:
        return "oom_like_exit"
    payload_status = str(payload.get("status", ""))
    if payload_status == "invalid_option":
        return "invalid_option"
    if payload_status == "artifact_missing":
        return "artifact_missing"
    if context.exit_code == 0 and not artifact.exists():
        return "artifact_missing"
    if context.exit_code == 0:
        return "success"
    return "infra_failure"


def _benchmark_status(
    context: _RunContext, payload: Mapping[str, object], artifact: Path
) -> str:
    if context.timed_out:
        return "timeout"
    if context.signal:
        return "crash_signal"
    if context.exit_code == 137:
        return "oom_like_exit"
    payload_status = str(payload.get("status", ""))
    if payload_status == "score_parse_failed":
        return "score_parse_failed"
    if not artifact.exists() or payload_status == "artifact_missing":
        return "artifact_missing"
    if context.exit_code == 0 and _parse_score(context.stdout_path) is not None:
        return "success"
    if context.exit_code == 0:
        return "score_parse_failed"
    return "infra_failure"


def _parse_score(stdout_path: Path) -> float | None:
    for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("SCORE "):
            try:
                score = float(line.split(maxsplit=1)[1])
            except (IndexError, ValueError):
                return None
            return score if math.isfinite(score) else None
    return None


def _load_result_payload(path: Path) -> Mapping[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _payload_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) else None


def _payload_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, str | None]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(k): (None if v is None else str(v)) for k, v in value.items()}


def _base_score_for_artifact(path: Path) -> float:
    digest = hashlib.sha256(path.read_bytes() if path.exists() else str(path).encode("utf-8")).digest()
    return 100.0 + (digest[0] / 255.0) * 5.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _run_id(prefix: str, token: str) -> str:
    safe = "".join(char if char.isalnum() or char in "_-" else "_" for char in token)
    return f"{prefix}_{safe}_{time.monotonic_ns()}"


def _validate_transition_matrix(
    matrix: Mapping[FakeGbsBurstState, Sequence[tuple[FakeGbsBurstState, float]]]
) -> None:
    expected = {"healthy", "degraded", "failed"}
    if set(matrix) != expected:
        raise ValueError("bursty transition matrix must define healthy/degraded/failed")
    for state, transitions in matrix.items():
        if not transitions:
            raise ValueError(f"{state} transitions cannot be empty")
        total = sum(probability for _, probability in transitions)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"{state} transition probabilities must sum to 1.0")
        for next_state, probability in transitions:
            if next_state not in expected:
                raise ValueError(f"unknown bursty state {next_state!r}")
            if probability < 0:
                raise ValueError("transition probabilities must be non-negative")


_WORKER_SOURCE = r'''
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def env_markers() -> dict[str, str | None]:
    return {
        "AGENT_SESSION_ID": os.environ.get("AGENT_SESSION_ID"),
        "AGENT_TRIAL_ID": os.environ.get("AGENT_TRIAL_ID"),
        "AGENT_LEASE_ID": os.environ.get("AGENT_LEASE_ID"),
        "AGENT_PROCESS_ROLE": os.environ.get("AGENT_PROCESS_ROLE"),
    }


def write_result(path: Path, *, status: str, **extra: object) -> None:
    payload = {
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "status": status,
        "env_markers": env_markers(),
    }
    payload.update(extra)
    atomic_write_json(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["compile", "benchmark"], required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--combo-json", default="[]")
    parser.add_argument("--score", default="")
    parser.add_argument("--failure-mode", default="none")
    args = parser.parse_args()

    result_json = Path(args.result_json)
    failure = args.failure_mode
    if failure == "timeout":
        time.sleep(60)
        return 124
    if failure == "crash_signal":
        os.kill(os.getpid(), signal.SIGSEGV)
    if failure == "oom_like_exit":
        write_result(result_json, status="oom_like_exit")
        print("Killed", file=sys.stderr)
        return 137

    artifact = Path(args.artifact) if args.artifact else None
    if args.mode == "compile":
        combo = json.loads(args.combo_json)
        if failure == "invalid_option":
            option = next((item for item in combo if "invalid" in str(item)), "<unknown>")
            print(f"gcc: error: unrecognized command-line option {option}", file=sys.stderr)
            write_result(result_json, status="invalid_option", combo=combo)
            return 2
        if failure == "artifact_missing":
            print("compile completed but artifact was not produced")
            write_result(result_json, status="artifact_missing", combo=combo)
            return 0
        if artifact is None:
            raise RuntimeError("--artifact is required for compile")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            "fake artifact\n" + "\n".join(str(item) for item in combo) + "\n",
            encoding="utf-8",
        )
        print(f"compiled {' '.join(str(item) for item in combo)}")
        write_result(result_json, status="success", combo=combo, artifact=str(artifact))
        return 0

    if artifact is None or not artifact.exists():
        print("benchmark artifact missing", file=sys.stderr)
        write_result(result_json, status="artifact_missing")
        return 3
    if failure == "score_parse_failed":
        print("benchmark completed but score line is malformed")
        write_result(result_json, status="score_parse_failed", artifact=str(artifact))
        return 0
    if not args.score:
        raise RuntimeError("--score is required for successful benchmark")
    print(f"SCORE {args.score}")
    write_result(result_json, status="success", artifact=str(artifact), score=args.score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
