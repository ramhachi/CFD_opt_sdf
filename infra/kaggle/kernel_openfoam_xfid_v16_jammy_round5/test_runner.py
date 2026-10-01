from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("xfid_round5_runner", ROOT / "runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_embedded_payload_and_registered_case_contract():
    runner.self_check()
    assert runner.OPENFOAM_BASHRC == "/usr/lib/openfoam/openfoam2512/etc/bashrc"


def test_recorded_version_command_matches_the_executed_command():
    assert runner.execution_commands()["version"] == runner.foam_version_command()[2]
    assert 'source "$WM_PROJECT_DIR/etc/config.sh/aliases"' in runner.execution_commands()["version"]


def test_foam_version_is_selected_from_separate_raw_streams():
    assert runner.parse_foam_version("", "MPI warning\nOpenFOAM-v2512\n") == "OpenFOAM-v2512"
    with pytest.raises(RuntimeError, match="expected one"):
        runner.parse_foam_version("OpenFOAM-v2512\n", "OpenFOAM-v2512\n")
    with pytest.raises(RuntimeError, match="unexpected foamVersion stdout"):
        runner.parse_foam_version("diagnostic\nOpenFOAM-v2512\n", "")


def test_foam_version_probe_is_saved_before_output_validation(tmp_path):
    completed = SimpleNamespace(returncode=0, stdout="", stderr="unexpected version text\n")
    with pytest.raises(RuntimeError, match="expected one"):
        runner.record_foam_version_probe(tmp_path, ["bash", "-lc", "foamVersion"], completed)
    probe = json.loads((tmp_path / "foam_version_probe.json").read_text())
    assert probe["stdout"] == ""
    assert probe["stderr"] == "unexpected version text\n"


def test_error_json_keeps_command_output_and_install_progress(tmp_path):
    runner.OUTPUT = tmp_path / "openfoam_xfid_v16"
    runner.OUTPUT.mkdir()
    runner.RUN_STARTED = True
    runner.FAILURE_STAGE = "environment_install"
    progress = {
        "status": "packages_installed_and_hash_verified_before_foamVersion",
        "os_version": "22.04.5",
        "architecture": "amd64",
        "package_records": [{"name": "openfoam2512-common", "sha256": "abc123"}],
        "installed_packages": ["openfoam2512-common=2512.0-2"],
    }
    progress_path = runner.OUTPUT / "installation_progress.json"
    runner.write_json(progress_path, progress)
    failure = subprocess.CalledProcessError(
        1, ["bash", "-lc", "source foam/etc/bashrc && foamVersion"],
        output="stdout diagnostic", stderr="stderr diagnostic",
    )

    with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout="amd64\n")), \
            patch.object(runner.platform, "platform", return_value="test-platform"):
        runner.write_error(failure)

    error = json.loads((runner.OUTPUT / "ERROR.json").read_text())
    assert error["command_failure"] == {
        "command": failure.cmd,
        "returncode": 1,
        "stdout": "stdout diagnostic",
        "stderr": "stderr diagnostic",
    }
    assert error["installation_progress"]["records"] == progress
    assert error["installation_progress"]["sha256"] == hashlib.sha256(progress_path.read_bytes()).hexdigest()


def test_noninteractive_version_probe_loads_real_package_function(tmp_path, monkeypatch):
    # Reproduce the package's PS1 guard, using its exact pinned aliases file.
    etc = tmp_path / "etc"
    (etc / "config.sh").mkdir(parents=True)
    package_aliases = ROOT.parents[2] / "docs/evidence/xfid_v16_environment_reproduction_2026_10_02_round4/terminal_failure_kernel_v3/package_shell_sources/config.sh/aliases"
    aliases = package_aliases.read_bytes()
    assert hashlib.sha256(aliases).hexdigest() == "281b1d4efb094b7fe3a8ee3fae73e822fc084ae7ccfa31609467f7f58661ec09"
    (etc / "config.sh/aliases").write_bytes(aliases)
    bashrc = etc / "bashrc"
    bashrc.write_text(f'export WM_PROJECT_DIR="{tmp_path}"\nexport WM_PROJECT_VERSION=v2512\nif [ -n "$PS1" ]; then source "$WM_PROJECT_DIR/etc/config.sh/aliases"; fi\n')
    monkeypatch.setattr(runner, "OPENFOAM_BASHRC", str(bashrc))
    old = subprocess.run(["bash", "-lc", f"source {bashrc} && foamVersion"], capture_output=True, text=True)
    assert old.returncode == 127
    result = runner.run_capture(runner.foam_version_command())
    assert result.stdout == ""
    assert runner.parse_foam_version(result.stdout, result.stderr) == "OpenFOAM-v2512"
