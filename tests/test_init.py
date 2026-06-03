from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from agent.config import AgentConfig
from agent.init import (
    INIT_SCHEMA_VERSION,
    MAX_INITIALIZED_BYTES,
    InitAborted,
    InitEditRequested,
    InitializedLoadError,
    NamespaceMismatchError,
    assert_initialized_matches,
    load_initialized_state,
    normalize_init_choice,
    prepare_init_context,
    prompt_for_init_confirmation,
    render_init_confirmation,
    run_init,
    verify_initialized_for_startup,
    write_initialized_state,
)
from agent.registry import RegistryValidationError


def registry_data() -> dict:
    return {
        "schema_version": "modules.registry.v1",
        "kg_versions": ["v3"],
        "modules": {
            "multimedia": {
                "frameworks": {
                    "ffmpeg": {
                        "compilers": {
                            "gcc": {"versions": ["13.2.0"]},
                        },
                    },
                },
            },
        },
    }


def config_data(workspace: Path) -> dict:
    return {
        "project": {
            "module": "multimedia",
            "framework": "ffmpeg",
            "compiler": {"type": "gcc", "version": "13.2.0"},
            "code_commit": "a1b2c3d",
            "kg_version": "v3",
        },
        "memory": {"workspace": str(workspace)},
        "baseline": {"combo": ["-O3", "-flto"]},
        "spec": {"source_path": "/path/to/project.spec"},
        "workspace_protection": {"source_tree_path": "/path/to/source"},
    }


def write_yaml(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_project_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    config_path = write_yaml(tmp_path / "agent.config.yaml", config_data(workspace))
    registry_path = write_yaml(
        workspace / "shared" / "modules.registry.yaml",
        registry_data(),
    )
    namespace_dir = (
        workspace
        / "namespaces"
        / "multimedia"
        / "ffmpeg"
        / "gcc-13.2.0"
        / "code-a1b2c3d"
        / "kg-v3"
    )
    return config_path, registry_path, namespace_dir


def initialized_data(namespace: str) -> dict:
    return {
        "schema_version": INIT_SCHEMA_VERSION,
        "namespace": namespace,
        "namespace_parts": namespace.split("/"),
        "project": config_data(Path("/workspace"))["project"],
        "baseline_combo": ["-O3", "-flto"],
        "created_at": "2026-05-07T00:00:00+00:00",
    }


def test_prepare_init_context_loads_registry_and_existing_history(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)
    write_yaml(namespace_dir / "trials" / "data" / "2026-05" / "trial.yaml", {"id": "t1"})
    write_yaml(namespace_dir / "failed_combos" / "failed.yaml", {"combo": ["-bad"]})
    write_yaml(namespace_dir / "learned" / "rules" / "rule.yaml", {"rule": "x"})
    write_yaml(namespace_dir / "experiences" / "exp.yaml", {"experience": "x"})
    write_yaml(namespace_dir / "baseline" / "baseline.yaml", {"combo": ["-O3"]})

    context = prepare_init_context(config_path, registry_path=registry_path)

    assert context.namespace.as_posix == "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    assert context.namespace_dir == namespace_dir
    assert context.initialized_path == namespace_dir / ".initialized"
    assert context.history.namespace_exists is True
    assert context.history.trial_files == 1
    assert context.history.failed_combo_files == 1
    assert context.history.learned_rule_files == 1
    assert context.history.experience_files == 1
    assert context.history.baseline_exists is True
    assert context.history.has_history is True


def test_prepare_init_context_remote_filesystem_warning_is_nonblocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    workspace = tmp_path / "workspace"

    def warn(path: object, *, context: str) -> None:
        assert Path(path) == workspace
        assert context == "agent init workspace"
        import warnings

        warnings.warn("remote init warning", RuntimeWarning, stacklevel=2)

    monkeypatch.setattr("agent.init.warn_if_remote_filesystem", warn)

    with pytest.warns(RuntimeWarning, match="remote init warning"):
        context = prepare_init_context(config_path, registry_path=registry_path)

    assert context.workspace == workspace


def test_render_init_confirmation_includes_identity_baseline_and_history(
    tmp_path: Path,
) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)
    write_yaml(namespace_dir / "trials" / "data" / "trial.yaml", {"id": "t1"})
    context = prepare_init_context(config_path, registry_path=registry_path)

    rendered = render_init_confirmation(context)

    assert "module: multimedia" in rendered
    assert "framework: ffmpeg" in rendered
    assert "compiler: gcc-13.2.0" in rendered
    assert "code_commit: a1b2c3d" in rendered
    assert "kg_version: v3" in rendered
    assert "baseline_combo: ['-O3', '-flto']" in rendered
    assert "trials: 1" in rendered


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("y", "yes"),
        ("YES", "yes"),
        ("n", "no"),
        ("no", "no"),
        ("e", "edit"),
        (" edit ", "edit"),
    ],
)
def test_normalize_init_choice(response: str, expected: str) -> None:
    assert normalize_init_choice(response) == expected


def test_normalize_init_choice_rejects_unknown_response() -> None:
    with pytest.raises(ValueError, match="expected"):
        normalize_init_choice("maybe")


def test_prompt_for_init_confirmation_reprompts_until_valid(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    context = prepare_init_context(config_path, registry_path=registry_path)
    responses = iter(["maybe", "edit"])
    output: list[str] = []

    choice = prompt_for_init_confirmation(
        context,
        input_func=lambda _: next(responses),
        output_func=output.append,
    )

    assert choice == "edit"
    assert any("Please answer" in item for item in output)


def test_prompt_for_init_confirmation_treats_eof_as_abort(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    context = prepare_init_context(config_path, registry_path=registry_path)

    with pytest.raises(InitAborted, match="EOF"):
        prompt_for_init_confirmation(
            context,
            input_func=lambda _: (_ for _ in ()).throw(EOFError),
            output_func=lambda _: None,
        )


def test_run_init_yes_writes_initialized_file(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)

    result = run_init(
        config_path,
        registry_path=registry_path,
        input_func=lambda _: "yes",
        output_func=lambda _: None,
        now=datetime(2026, 5, 7, 1, 2, 3, tzinfo=UTC),
    )

    assert result.status == "initialized"
    initialized_path = namespace_dir / ".initialized"
    assert initialized_path.exists()
    state = load_initialized_state(initialized_path)
    assert state.schema_version == INIT_SCHEMA_VERSION
    assert state.namespace == "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"
    assert state.namespace_parts == [
        "multimedia",
        "ffmpeg",
        "gcc-13.2.0",
        "code-a1b2c3d",
        "kg-v3",
    ]
    assert state.project.module == "multimedia"
    assert state.baseline_combo == ["-O3", "-flto"]
    assert state.created_at == "2026-05-07T01:02:03+00:00"
    assert not list(namespace_dir.glob(".initialized.*.tmp"))


def test_run_init_no_aborts_without_writing(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)

    with pytest.raises(InitAborted):
        run_init(
            config_path,
            registry_path=registry_path,
            input_func=lambda _: "no",
            output_func=lambda _: None,
        )

    assert not (namespace_dir / ".initialized").exists()


def test_run_init_edit_requests_without_writing(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)

    with pytest.raises(InitEditRequested, match="edit config"):
        run_init(
            config_path,
            registry_path=registry_path,
            input_func=lambda _: "edit",
            output_func=lambda _: None,
        )

    assert not (namespace_dir / ".initialized").exists()


def test_run_init_existing_matching_state_skips_prompt(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    context = prepare_init_context(config_path, registry_path=registry_path)
    write_initialized_state(context, now=datetime(2026, 5, 7, tzinfo=UTC))

    result = run_init(
        config_path,
        registry_path=registry_path,
        input_func=lambda _: pytest.fail("prompt should not be called"),
        output_func=lambda _: None,
    )

    assert result.status == "already_initialized"
    assert result.state.namespace == context.namespace.as_posix


def test_verify_initialized_for_startup_requires_initialized_file(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)

    with pytest.raises(InitializedLoadError, match="not initialized"):
        verify_initialized_for_startup(config_path, registry_path=registry_path)

    assert not (namespace_dir / ".initialized").exists()


def test_verify_initialized_for_startup_accepts_matching_state(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    context = prepare_init_context(config_path, registry_path=registry_path)
    write_initialized_state(context, now=datetime(2026, 5, 7, tzinfo=UTC))

    verified = verify_initialized_for_startup(config_path, registry_path=registry_path)

    assert verified.namespace.as_posix == context.namespace.as_posix


def test_verify_initialized_for_startup_rejects_namespace_mismatch(
    tmp_path: Path,
) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)
    data = initialized_data("other/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data["project"]["module"] = "other"
    write_yaml(
        namespace_dir / ".initialized",
        data,
    )

    with pytest.raises(NamespaceMismatchError, match="namespace mismatch"):
        verify_initialized_for_startup(config_path, registry_path=registry_path)


def test_assert_initialized_matches_accepts_expected_namespace(tmp_path: Path) -> None:
    _, _, namespace_dir = write_project_files(tmp_path)
    path = write_yaml(
        namespace_dir / ".initialized",
        initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3"),
    )

    state = assert_initialized_matches(
        path,
        "multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3",
    )

    assert state.namespace_parts[-1] == "kg-v3"


@pytest.mark.parametrize(
    ("raw_text", "message"),
    [
        ("", "empty"),
        ("null\n", "empty"),
        ("- not\n- mapping\n", "must contain a YAML mapping"),
        ("!!python/object/apply:os.system ['echo unsafe']\n", "failed to parse YAML"),
    ],
)
def test_load_initialized_state_rejects_invalid_yaml(
    tmp_path: Path, raw_text: str, message: str
) -> None:
    path = tmp_path / ".initialized"
    path.write_text(raw_text, encoding="utf-8")

    with pytest.raises(InitializedLoadError, match=message):
        load_initialized_state(path)


def test_load_initialized_state_rejects_yaml_aliases(tmp_path: Path) -> None:
    path = tmp_path / ".initialized"
    path.write_text(
        """
schema_version: &version agent.initialized.v1
schema_copy: *version
""",
        encoding="utf-8",
    )

    with pytest.raises(InitializedLoadError, match="aliases are not allowed"):
        load_initialized_state(path)


def test_load_initialized_state_rejects_missing_schema_version(tmp_path: Path) -> None:
    data = initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data.pop("schema_version")

    with pytest.raises(InitializedLoadError, match="schema_version"):
        load_initialized_state(write_yaml(tmp_path / ".initialized", data))


def test_load_initialized_state_rejects_namespace_parts_mismatch(
    tmp_path: Path,
) -> None:
    data = initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data["namespace_parts"] = ["wrong", "ffmpeg", "gcc-13.2.0", "code-a1b2c3d", "kg-v3"]

    with pytest.raises(InitializedLoadError, match="namespace must equal"):
        load_initialized_state(write_yaml(tmp_path / ".initialized", data))


def test_load_initialized_state_rejects_project_identity_mismatch(
    tmp_path: Path,
) -> None:
    data = initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data["project"]["module"] = "other"

    with pytest.raises(InitializedLoadError, match="project identity"):
        load_initialized_state(write_yaml(tmp_path / ".initialized", data))


@pytest.mark.parametrize("created_at", ["garbage", "2026-05-07T00:00:00"])
def test_load_initialized_state_rejects_invalid_created_at(
    tmp_path: Path, created_at: str
) -> None:
    data = initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data["created_at"] = created_at

    with pytest.raises(InitializedLoadError, match="created_at"):
        load_initialized_state(write_yaml(tmp_path / ".initialized", data))


def test_load_initialized_state_accepts_zulu_utc_created_at(tmp_path: Path) -> None:
    data = initialized_data("multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3")
    data["created_at"] = "2026-05-07T00:00:00Z"

    state = load_initialized_state(write_yaml(tmp_path / ".initialized", data))

    assert state.created_at == "2026-05-07T00:00:00Z"


def test_load_initialized_state_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / ".initialized"
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(InitializedLoadError, match="failed to read"):
        load_initialized_state(path)


def test_load_initialized_state_rejects_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / ".initialized"
    path.write_text("x" * (MAX_INITIALIZED_BYTES + 1), encoding="utf-8")

    with pytest.raises(InitializedLoadError, match="too large"):
        load_initialized_state(path)


def test_run_init_propagates_registry_validation_failure(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)
    data = registry_data()
    data["kg_versions"] = ["v2"]
    write_yaml(registry_path, data)

    with pytest.raises(RegistryValidationError, match="kg_version"):
        run_init(
            config_path,
            registry_path=registry_path,
            input_func=lambda _: "yes",
            output_func=lambda _: None,
        )


def test_run_init_checks_existing_trial_compiler_versions(tmp_path: Path) -> None:
    config_path, registry_path, _ = write_project_files(tmp_path)

    with pytest.raises(RegistryValidationError, match="existing trials"):
        run_init(
            config_path,
            registry_path=registry_path,
            existing_trial_compiler_versions=["12.2.0"],
            input_func=lambda _: "yes",
            output_func=lambda _: None,
        )


def test_initialized_state_file_is_user_readable_yaml(tmp_path: Path) -> None:
    config_path, registry_path, namespace_dir = write_project_files(tmp_path)
    config = AgentConfig.model_validate(config_data(tmp_path / "workspace"))
    context = prepare_init_context(config_path, registry_path=registry_path)
    assert context.config.project == config.project

    write_initialized_state(context, now=datetime(2026, 5, 7, tzinfo=UTC))
    raw_text = (namespace_dir / ".initialized").read_text(encoding="utf-8")

    assert "schema_version: agent.initialized.v1" in raw_text
    assert "namespace: multimedia/ffmpeg/gcc-13.2.0/code-a1b2c3d/kg-v3" in raw_text
    assert "baseline_combo:" in raw_text
