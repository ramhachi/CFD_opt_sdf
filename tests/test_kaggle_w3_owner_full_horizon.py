from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts/verify_kaggle_w3_owner_full_horizon.py"
SPEC = importlib.util.spec_from_file_location("w3_owner_full_horizon_host", VERIFY_PATH)
HOST = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(HOST)


def force_row(step: int, time: float, fx: float, fy: float, fz: float,
              p=(2.0, 3.0, 4.0), v=(1.0, -1.0, 2.0)) -> dict[str, float]:
    total = (fx, fy, fz)
    result = {"step": float(step), "t_u_l": time,
              "fx_solver": total[0], "fy_solver": total[1], "fz_solver": total[2],
              "drag_solver": total[0], "downforce_solver": -total[2]}
    for axis, value, pressure, viscous in zip("xyz", total, p, v):
        result[f"pressure_f{axis}_solver"] = pressure
        result[f"viscous_f{axis}_solver"] = viscous
    return result


def test_exact_window_endpoint_interpolation_and_trapezoid_mean():
    rows = [
        force_row(8, 79.5, 79.5, 0.0, 0.0, p=(50.0, 0.0, 0.0), v=(29.5, 0.0, 0.0)),
        force_row(16, 80.5, 80.5, 0.0, 0.0, p=(50.0, 0.0, 0.0), v=(30.5, 0.0, 0.0)),
        force_row(1272, 119.5, 119.5, 0.0, 0.0, p=(50.0, 0.0, 0.0), v=(69.5, 0.0, 0.0)),
        force_row(1280, 120.5, 120.5, 0.0, 0.0, p=(50.0, 0.0, 0.0), v=(70.5, 0.0, 0.0)),
    ]
    clipped = HOST.clipped_window(rows, 80.0, 120.0)
    assert clipped[0]["t_u_l"] == 80.0
    assert clipped[0]["drag_solver"] == 80.0
    assert clipped[-1]["t_u_l"] == 120.0
    assert clipped[-1]["drag_solver"] == 120.0
    assert HOST.time_weighted_mean(clipped, "drag_solver") == 100.0


def test_force_closure_checks_all_three_axes_and_projection():
    criteria = {"causal_decision_rules": {
        "force_component_absolute_tolerance": 1e-8,
        "force_component_relative_tolerance": 1e-6,
    }}
    row = force_row(8, 80.0, 3.0, 2.0, -5.0, p=(2.0, 3.0, -4.0), v=(1.0, -1.0, -1.0))
    result = HOST.force_closure([row], criteria)
    assert result["passed"] is True
    assert result["checked_axis_components"] == 3
    row["pressure_fy_solver"] += 0.25
    assert HOST.force_closure([row], criteria)["passed"] is False


def test_exact_zero_history_requires_every_raw_force_component_to_be_zero():
    zero = force_row(8, 80.0, 0.0, -0.0, 0.0, p=(0.0, 0.0, 0.0), v=(0.0, 0.0, 0.0))
    assert HOST.exact_zero_history([zero]) is True
    nonzero_viscous = dict(zero, viscous_fz_solver=1e-12)
    assert HOST.exact_zero_history([nonzero_viscous]) is False
    assert HOST.exact_zero_history([]) is False


def test_monotonicity_gate_rejects_duplicate_or_reordered_force_samples():
    assert HOST.strictly_increasing([1.0, 2.0, 3.0]) is True
    assert HOST.strictly_increasing([1.0, 1.0, 2.0]) is False
    assert HOST.strictly_increasing([1.0, 3.0, 2.0]) is False
    assert HOST.strictly_increasing([]) is False


def test_production_fix_requires_natural_collection_and_replicated_same_corruption():
    corruption = {
        "owner_weakref_cleared": True,
        "reproducible_corruption_observed": True,
        "corruption_class": "post_collection_force_divergence",
        "status": "completed",
        "progress_t_u_l_reached": 120.015625,
    }
    assert HOST.production_fix_gate(True, [corruption, dict(corruption)]) is True
    forced_only_cannot_authorize = dict(corruption, owner_weakref_cleared=False)
    assert HOST.production_fix_gate(True, [forced_only_cannot_authorize, forced_only_cannot_authorize]) is False
    mismatch = dict(corruption, corruption_class="post_collection_nonfinite_force_or_fields")
    assert HOST.production_fix_gate(True, [corruption, mismatch]) is False
    assert HOST.production_fix_gate(False, [corruption, dict(corruption)]) is False


def test_w3_v4_production_job_remains_byte_identical_and_arm_order_is_fixed():
    import json
    import re

    criteria = json.loads((ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json").read_text())
    job = ROOT / "scripts/waterlily_w3_v16_primal_job.jl"
    assert HOST.sha256(job) == criteria["inputs"]["job"]["sha256"]
    production = job.read_text()
    diagnostic = (ROOT / "scripts/waterlily_w3_v16_owner_full_horizon_job.jl").read_text()
    for constant in ("T_END", "BURN_IN", "SAMPLE_EVERY"):
        pattern = rf"(?m)^const {constant}\s*=\s*(.+)$"
        production_value = re.search(pattern, production)
        diagnostic_value = re.search(pattern, diagnostic)
        assert production_value and diagnostic_value
        assert production_value.group(1).strip() == diagnostic_value.group(1).strip()
    assert "pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))" in production
    assert "viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))" in production
    assert "pressure = -WaterLily.pressure_force(sim.flow, candidate)" in diagnostic
    assert "viscous = -WaterLily.viscous_force(sim.flow, candidate)" in diagnostic
    assert "total = pressure + viscous" in production
    assert "total = pressure + viscous" in diagnostic
    assert "downforce = -total[3]" in production
    assert "Float64(-total[3])" in diagnostic
    import runpy
    runner = runpy.run_path(str(ROOT / "infra/kaggle/kernel_w3_owner_full_horizon/runner.py"))
    assert runner["ARMS"] == ("A-natural", "A-forced", "B-natural-1", "B-natural-2", "B-forced-1", "B-forced-2")


def test_registered_probe_points_preserve_design_origin_and_use_flow_origin(tmp_path: Path):
    import runpy
    import struct

    registrar = runpy.run_path(str(ROOT / "scripts/register_kaggle_w3_owner_full_horizon_2026_09.py"))
    values = (-3.0, 1.0, -0.2, 2.0, 0.1, 3.0, 4.0, 5.0)
    phi = tmp_path / "phi.raw"
    phi.write_bytes(struct.pack("<8f", *values))
    geometry = {"point_shape": [2, 2, 2], "canonical_sdf_origin_m": [-1.0, -2.0, -3.0], "spacing_m": 0.5}
    probes = registrar["candidate_probe_definition"](phi, geometry, [-2.0, -3.0, -4.0])
    assert probes[0]["name"] == "candidate_min_phi"
    assert probes[0]["canonical_index_1based"] == [1, 1, 1]
    assert probes[0]["world_m"] == [-1.0, -2.0, -3.0]
    assert probes[0]["flow_solver"] == [2.0, 2.0, 2.0]
    assert probes[-1]["name"] == "world_origin"
    assert probes[-1]["world_m"] == [0.0, 0.0, 0.0]
    assert probes[-1]["flow_solver"] == [4.0, 6.0, 8.0]


def test_diagnostic_buffers_match_registered_snapshot_count_and_have_no_undefined_stride():
    job = (ROOT / "scripts/waterlily_w3_v16_owner_full_horizon_job.jl").read_text()
    assert "FIELD_EVERY" not in job
    assert "FIELD_DIAGNOSTIC_CAPACITY = 2" in job
    assert "CANDIDATE_PROBE_CAPACITY = 4 * FIELD_DIAGNOSTIC_CAPACITY" in job


def test_runner_enforces_per_arm_and_kernel_time_limits():
    import runpy

    runner = runpy.run_path(str(ROOT / "infra/kaggle/kernel_w3_owner_full_horizon/runner.py"))
    bound = runner["bounded_timeout_seconds"]
    assert bound(100.0, 7200, 1800, now=500.0) == 1800
    assert bound(100.0, 7200, 1800, now=5501.0) == 1799
    try:
        bound(100.0, 7200, 1800, now=7300.0)
    except TimeoutError as error:
        assert "budget is exhausted" in str(error)
    else:
        raise AssertionError("exhausted kernel budget was accepted")
