from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

import cfd_sdf.runtime_diagnostics as diagnostics
from cfd_sdf.runtime_diagnostics import (
    collect_runtime_diagnostics,
    parse_nvidia_smi_output,
)


def test_nvidia_smi_parser_keeps_gpu_memory_structured_and_missing_values_none() -> None:
    assert parse_nvidia_smi_output(
        '"NVIDIA A100-SXM4-40GB", 40960, 39168\n'
        'NVIDIA Test, N/A, 0\n'
        'NVIDIA Invalid, -1, -2\n'
        'name, memory.total [MiB], memory.free [MiB]\n'
    ) == [
        {
            "name": "NVIDIA A100-SXM4-40GB",
            "memory_total_mib": 40960,
            "memory_free_mib": 39168,
        },
        {
            "name": "NVIDIA Test",
            "memory_total_mib": None,
            "memory_free_mib": 0,
        },
        {
            "name": "NVIDIA Invalid",
            "memory_total_mib": None,
            "memory_free_mib": None,
        },
    ]


def test_missing_tools_are_reported_without_invoking_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> object:
        calls.append(command)
        raise AssertionError(f"unexpected probe: {command}")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    monkeypatch.setattr(
        diagnostics.importlib.metadata,
        "version",
        lambda _name: (_ for _ in ()).throw(diagnostics.importlib.metadata.PackageNotFoundError()),
    )

    report = collect_runtime_diagnostics(timeout_seconds=0.25)

    assert calls == []
    assert report["gpu"]["nvidia"]["status"] == "missing"
    assert report["docker"]["status"] == "missing"
    assert report["openfoam"]["local"]["installed"] is False
    assert report["openfoam"]["local"]["reachable"] is False
    assert report["openfoam"]["wsl"]["status"] == "not_applicable"
    assert report["gpu"]["metal"]["checked"] is False
    json.dumps(report)


def test_nonzero_and_timeout_results_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.platform, "machine", lambda: "AMD64")
    command_paths = {
        "nvidia-smi": "C:/nvidia-smi.exe",
        "docker": "C:/docker.exe",
        "simpleFoam": "C:/simpleFoam.exe",
        "blockMesh": "C:/blockMesh.exe",
        "wsl": "C:/wsl.exe",
    }
    monkeypatch.setattr(diagnostics.shutil, "which", command_paths.get)
    monkeypatch.setattr(
        diagnostics.importlib.metadata,
        "version",
        lambda _name: (_ for _ in ()).throw(diagnostics.importlib.metadata.PackageNotFoundError()),
    )

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert kwargs["timeout"] == 0.4
        if command[0].endswith("nvidia-smi.exe"):
            return subprocess.CompletedProcess(command, 17, stdout="", stderr="driver error")
        if command[0].endswith("docker.exe"):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if command[0].endswith("wsl.exe"):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="no distro")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="not ready")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)

    report = collect_runtime_diagnostics(timeout_seconds=0.4)

    nvidia = report["gpu"]["nvidia"]
    assert nvidia["installed"] is True
    assert nvidia["reachable"] is False
    assert nvidia["status"] == "nonzero_exit"
    docker = report["docker"]
    assert docker["reachable"] is None
    assert docker["status"] == "timeout"
    assert docker["image_available"] is None
    local = report["openfoam"]["local"]
    assert local["installed"] is True
    assert local["reachable"] is False
    assert report["openfoam"]["wsl"]["status"] == "nonzero_exit"
    assert report["solver_physics"]["status"] == "not_evaluated"


def test_docker_image_timeout_is_unknown_not_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/docker" if name == "docker" else None)

    def fake_run(command: list[str], **kwargs: object) -> object:
        if command[1] == "info":
            return subprocess.CompletedProcess(command, 0, stdout="29.1.5\n", stderr="")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)

    report = diagnostics._docker(0.4, "opencfd/openfoam-default:2512")

    assert report["reachable"] is True
    assert report["image_available"] is None
    assert report["image_status"] == "timeout"


def test_mac_sysctl_and_nvidia_probe_are_parsed_without_sensitive_sysctl_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(diagnostics.platform, "machine", lambda: "arm64")
    command_paths = {
        "nvidia-smi": "/usr/local/bin/nvidia-smi",
        "docker": None,
        "simpleFoam": None,
        "blockMesh": None,
    }
    monkeypatch.setattr(diagnostics.shutil, "which", command_paths.get)
    monkeypatch.setattr(
        diagnostics.importlib.metadata,
        "version",
        lambda name: "0.32.2" if name == "mlx" else (_ for _ in ()).throw(
            diagnostics.importlib.metadata.PackageNotFoundError()
        ),
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["sysctl", "-n", "hw.memsize"]:
            return subprocess.CompletedProcess(command, 0, stdout="34359738368\n", stderr="")
        if command[:3] == ["sysctl", "-n", "machdep.cpu.brand_string"]:
            return subprocess.CompletedProcess(command, 0, stdout="Apple M4\n", stderr="")
        if command[:3] == ["sysctl", "-n", "hw.optional.arm64"]:
            return subprocess.CompletedProcess(command, 0, stdout="1\n", stderr="")
        if command[0].endswith("nvidia-smi"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="NVIDIA RTX 6000 Ada, 49140, 48000\n",
                stderr="",
            )
        raise AssertionError(command)

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    monkeypatch.setattr(
        diagnostics.importlib,
        "import_module",
        lambda name: SimpleNamespace(metal=SimpleNamespace(is_available=lambda: True)),
    )

    report = collect_runtime_diagnostics(timeout_seconds=0.3)

    assert report["hardware"]["mac_chip"]["name"] == "Apple M4"
    assert report["hardware"]["memory"]["total_bytes"] == 34359738368
    assert report["gpu"]["nvidia"]["gpus"] == [
        {
            "name": "NVIDIA RTX 6000 Ada",
            "memory_total_mib": 49140,
            "memory_free_mib": 48000,
        }
    ]
    assert report["gpu"]["metal"] == {
        "status": "available",
        "checked": True,
        "available": True,
    }
    queried = {tuple(command[2:]) for command in calls if command[0] == "sysctl"}
    assert all("hw.uuid" not in command and "serial" not in command for command in queried)


def test_metal_is_not_imported_when_mlx_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.importlib, "import_module", lambda _name: pytest.fail("must not import mlx"))

    result = diagnostics._metal(
        "Darwin",
        "arm64",
        {"installed": False, "version": None},
    )

    assert result["checked"] is False
    assert result["status"] == "not_checked"


def test_report_is_json_safe_and_rejects_empty_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        diagnostics.importlib.metadata,
        "version",
        lambda _name: (_ for _ in ()).throw(diagnostics.importlib.metadata.PackageNotFoundError()),
    )
    report = collect_runtime_diagnostics(timeout_seconds=0.2)
    assert report["kind"] == "runtime_diagnostics"
    json.dumps(report, allow_nan=False)
    with pytest.raises(ValueError, match="docker_image"):
        collect_runtime_diagnostics(timeout_seconds=0.2, docker_image="")


def test_timeout_is_bounded_even_when_caller_requests_large_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[float] = []
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/tool" if name == "docker" else None)
    monkeypatch.setattr(
        diagnostics.importlib.metadata,
        "version",
        lambda _name: (_ for _ in ()).throw(diagnostics.importlib.metadata.PackageNotFoundError()),
    )

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed.append(float(kwargs["timeout"]))
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    collect_runtime_diagnostics(timeout_seconds=1000)

    assert observed
    assert max(observed) == diagnostics.MAX_RUNTIME_DIAGNOSTICS_TIMEOUT_SECONDS
