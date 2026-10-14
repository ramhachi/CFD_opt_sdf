"""GRAD-TA1 CPU checks of scripts/quick_tie.jl and of the bridge's 20-step preflight (Amendment 1, C6).  Needs julia and the WaterLily 1.8.0 CPU project."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JULIA = shutil.which("julia")
PROJECT = ROOT / "julia/CFDSDFWaterLily"
INPUTS = ROOT / "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
PHI = ROOT / "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
DIRS = {"D0_interface_offset": "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549",
        "D1_filtered_seed11": "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87",
        "D2_filtered_seed2026": "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de",
        "P1_upstream_lobe": "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc"}
need_julia = pytest.mark.skipif(JULIA is None or not (PROJECT / "Manifest.toml").is_file(), reason="julia / CPU project not available")


def julia(*args, env=None, timeout=1800):
    import os
    return subprocess.run([JULIA, "-t", "1", f"--project={PROJECT}", *map(str, args)], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})


@need_julia
def test_quick_tie_unit_tests():
    result = julia(ROOT / "scripts/test_quick_tie.jl")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert "Fail" not in result.stdout and "Error" not in result.stdout


@need_julia
def test_twenty_step_cpu_preflight_quicktie_dual_equals_quick_dual_bitwise(tmp_path):
    args = [ROOT / "scripts/waterlily_grad_ta1_2026_10_15.jl", PHI, "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431", tmp_path / "out"]
    for name, sha in DIRS.items():
        args += [INPUTS / f"{name}.dir_f4_fortran.raw", sha]
    result = julia(*args, env={"G2_BACKEND": "cpu", "TA1_PREFLIGHT_ONLY": "1"})
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    pre = json.loads((tmp_path / "out/preflight.json").read_text())
    assert pre["steps"] == 20 and pre["pass"] is True and pre["primal_u_bit_equal"] is True and pre["primal_p_bit_equal"] is True
    assert all(a["tangent_u_finite"] and a["tangent_p_finite"] and a["primal_finite"] for a in pre["arms"].values())
    assert json.loads((tmp_path / "out/g2_run_index.json").read_text())["status"] == "PREFLIGHT_ONLY"
    # the TA1 build path stores the requested scheme in sim.flow.λ (sim_step!(sim; λ) would not): the second arm is QuickTie, the first plain quick
    assert pre["arms"]["quick"]["lambda_type"] == "typeof(quick)" and pre["arms"]["quick_tie"]["lambda_type"] == "WaterLily.QuickTie{Float32}"
    assert "tangent_p_max_abs_difference_report_only" in pre and "tangent_u_max_abs_difference_report_only" in pre and "never gated" in pre["tangent_difference_note"]


def test_quick_tie_source_has_no_silent_fallback_and_asserts_width_one():
    text = (ROOT / "scripts/quick_tie.jl").read_text()
    assert "Dual{<:Any,<:Any,1}" in text and "error(" in text and "= quick(u, c, d)\n(q::QuickTie)(u, c, d) = error" in text.replace("   # value-only arguments (no derivative involved): the original limiter", "")


def test_the_bridge_restricts_dry_run_switches_to_cpu_and_uses_quicktie():
    text = (ROOT / "scripts/waterlily_grad_ta1_2026_10_15.jl").read_text()
    for needle in ("TA1_PREFLIGHT_ONLY is only allowed with G2_BACKEND=cpu", "TA1_BLOCK_LIMIT is only allowed with G2_BACKEND=cpu", "G2_DRYRUN_T_END is only allowed with G2_BACKEND=cpu",
                   "const LAMBDA = WaterLily.QuickTie(TAU)", "const TAU = 1f-5", "const WATCH_EVERY = 100", "const WALL_FACTOR = 8.0", "1.0e30"):
        assert needle in text


@need_julia
def test_lambda_reaches_the_solver_through_the_constructor_not_sim_step_kwargs():
    result = julia(ROOT / "scripts/test_ta1_lambda_routing.jl")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert "Fail" not in result.stdout and "Error" not in result.stdout


def test_the_bridge_routes_lambda_through_the_constructor_and_never_through_sim_step():
    text = (ROOT / "scripts/waterlily_grad_ta1_2026_10_15.jl").read_text()
    assert "mem=mem, λ=λ)" in text and "typeof(sim.flow.λ) === typeof(λ) ||" in text
    assert "WaterLily.sim_step!(sim; λ)" not in text and text.count("WaterLily.sim_step!(sim)") == 3
