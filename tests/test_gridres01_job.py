"""GRIDRES-01 Julia job, CPU smoke: it builds the flow_40 / flow_48 case with the frozen build_case and passes the local validation (no GPU, no phi, no solver run)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
JOB, PROJECT = ROOT / "scripts/waterlily_gridres01_job.jl", ROOT / "julia/CFDSDFWaterLilyT4"


def smoke(cells):
    env = {**os.environ, "GRIDRES01_SMOKE": "1", "GRIDRES01_CELLS": str(cells)}
    return subprocess.run(["julia", f"--project={PROJECT}", str(JOB), "x", "y"], capture_output=True, text=True, env=env, timeout=900)


@pytest.mark.skipif(shutil.which("julia") is None, reason="julia not installed")
@pytest.mark.parametrize("cells,dims,nu", [(40, "(250, 120, 90)", "0.5"), (48, "(300, 144, 108)", "0.6")])
def test_job_builds_and_locally_validates_the_case(cells, dims, nu):
    r = smoke(cells)
    if r.returncode and "GRIDRES01_SMOKE_OK" not in r.stdout and "Pkg" in r.stderr:
        pytest.skip("Julia project is not instantiated here")
    assert r.returncode == 0 and f"GRIDRES01_SMOKE_OK flow_{cells} dims={dims} nu={nu}" in r.stdout, r.stderr[-800:]


@pytest.mark.skipif(shutil.which("julia") is None, reason="julia not installed")
def test_job_refuses_an_unregistered_grid():
    r = smoke(32)
    assert r.returncode != 0 and "GRIDRES01_CELLS must be 40 or 48" in r.stderr
