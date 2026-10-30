from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
JULIA_PROJECT = ROOT / "julia" / "CFDSDFWaterLily"
FIXTURE_RUNNER = ROOT / "scripts" / "sdf_native_fd07_continuous_replacement_fixtures.jl"


@pytest.mark.skipif(shutil.which("julia") is None, reason="Julia is required for the WaterLily operator fixture")
def test_continuous_sign_operator_analytic_selftest():
    result = subprocess.run(
        ["julia", f"--project={JULIA_PROJECT}", str(FIXTURE_RUNNER), "--selftest"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "analytic_sign_operator_selftest=passed" in result.stdout
