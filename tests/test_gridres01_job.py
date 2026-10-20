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
@pytest.mark.parametrize("cells,dims,nu", [(24, "(150, 72, 54)", "0.3"), (32, "(200, 96, 72)", "0.4"), (40, "(250, 120, 90)", "0.5"), (48, "(300, 144, 108)", "0.6")])
def test_job_builds_and_locally_validates_the_case(cells, dims, nu):
    r = smoke(cells)
    if r.returncode and "GRIDRES01_SMOKE_OK" not in r.stdout and "Pkg" in r.stderr:
        pytest.skip("Julia project is not instantiated here")
    assert r.returncode == 0 and f"GRIDRES01_SMOKE_OK flow_{cells} dims={dims} nu=" in r.stdout, r.stderr[-800:]
    assert float(r.stdout.split("nu=")[1].split()[0]) == pytest.approx(float(nu), abs=1e-12)   # n/80 up to float rounding (flow_32 prints 0.3999999999999999)


@pytest.mark.skipif(shutil.which("julia") is None, reason="julia not installed")
def test_job_refuses_an_unregistered_grid():
    r = smoke(16)
    assert r.returncode != 0 and "GRIDRES01_CELLS must be 24, 32, 40 or 48" in r.stderr


@pytest.mark.skipif(shutil.which("julia") is None, reason="julia not installed")
def test_poisson_probe_is_passive_on_cpu(tmp_path):
    """Amendment 2 H1: the same small WaterLily run without and with the probe gives byte-identical force text and fields (determinism control included); the probe CSV is written."""
    csv = tmp_path / "probe.csv"
    r = subprocess.run(["julia", f"--project={PROJECT}", str(ROOT / "scripts/gridres01_poisson_passivity_check.jl")], capture_output=True, text=True, env={**os.environ, "GRIDRES01_PROBE_CSV": str(csv)}, timeout=900)
    if r.returncode and "GRIDRES01_PASSIVITY_OK" not in r.stdout and "Pkg" in r.stderr:
        pytest.skip("Julia project is not instantiated here")
    assert r.returncode == 0 and "GRIDRES01_PASSIVITY_OK" in r.stdout, r.stderr[-800:]
    import sys
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
    import analyze_gridres01 as A
    summary = A.poisson_summary(csv)   # the Julia-written CSV parses, and its aggregates are consistent
    assert summary["samples"] == 8 and summary["solves"] == 32 and summary["solves_at_cap"] == 0
