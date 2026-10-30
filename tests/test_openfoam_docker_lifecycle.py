import subprocess
from pathlib import Path

import pytest

from cfd_sdf.execution import _command_for_backend, run_openfoam_case


def _make_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "Allrun").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (case_dir / "Allclean").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return case_dir


def _docker_container_name(command: list[str]) -> str:
    assert "docker" == command[0]
    name = command[command.index("--name") + 1]
    assert name and "--rm" in command
    return name


def test_docker_command_has_unique_container_name() -> None:
    case_dir = Path("/nonexistent/case")
    first = _command_for_backend("docker", case_dir, "opencfd/openfoam-default:2512")
    second = _command_for_backend("docker", case_dir, "opencfd/openfoam-default:2512")
    name_a = _docker_container_name(first)
    name_b = _docker_container_name(second)
    assert name_a != name_b
    assert name_a.startswith("openfoam-default_")
    assert "/" not in name_a and ":" not in name_a


def test_docker_timeout_triggers_container_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = _make_case(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command[0] == "docker" and command[1] == "run":
            raise subprocess.TimeoutExpired(cmd=command, timeout=1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cfd_sdf.execution.subprocess.run", fake_run)

    result = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=1)

    assert result.timed_out is True
    assert result.ok is False
    container_name = _docker_container_name(result.command)
    cleanup = [c for c in calls if c[:2] == ["docker", "rm"]]
    assert len(cleanup) == 1
    assert cleanup[0] == ["docker", "rm", "-f", container_name]


def test_docker_keyboard_interrupt_triggers_container_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = _make_case(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command[0] == "docker" and command[1] == "run":
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cfd_sdf.execution.subprocess.run", fake_run)

    with pytest.raises(KeyboardInterrupt):
        run_openfoam_case(case_dir, backend="docker", dry_run=False)

    container_name = None
    for call in calls:
        if call[0] == "docker" and call[1] == "run":
            container_name = call[call.index("--name") + 1]
    assert container_name is not None
    cleanup = [c for c in calls if c[:2] == ["docker", "rm"]]
    assert len(cleanup) == 1
    assert cleanup[0] == ["docker", "rm", "-f", container_name]
    summary = (case_dir / "openfoam_run_summary.json").exists()
    assert summary is False  # interrupt propagates before summary is written


def test_local_timeout_does_not_invoke_docker_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = _make_case(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr("cfd_sdf.execution.subprocess.run", fake_run)

    result = run_openfoam_case(case_dir, backend="local", dry_run=False, timeout_seconds=1)

    assert result.timed_out is True
    assert all(call[0] != "docker" for call in calls)
    assert result.command[0] != "docker"


def test_docker_normal_completion_does_not_invoke_docker_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = _make_case(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cfd_sdf.execution.subprocess.run", fake_run)

    result = run_openfoam_case(case_dir, backend="docker", dry_run=False)

    assert result.ok is True
    assert result.returncode == 0
    assert not any(c[:2] == ["docker", "rm"] for c in calls)
