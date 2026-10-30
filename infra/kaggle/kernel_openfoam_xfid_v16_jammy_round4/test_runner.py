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
SPEC = importlib.util.spec_from_file_location("xfid_round4_runner", ROOT / "runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_embedded_payload_and_registered_case_contract():
    runner.self_check()
    assert runner.OPENFOAM_BASHRC == "/usr/lib/openfoam/openfoam2512/etc/bashrc"


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
