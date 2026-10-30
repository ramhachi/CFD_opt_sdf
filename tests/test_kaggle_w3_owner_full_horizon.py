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


def test_w3_owner_fix_roots_owner_through_primal_and_preserves_registered_force_path():
    import json
    import re

    criteria = json.loads((ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json").read_text())
    owner_criteria = json.loads((ROOT / "docs/evidence/kaggle_w3_owner_full_horizon_criteria_2026_09_round3.json").read_text())
    job = ROOT / "scripts/waterlily_w3_v16_primal_job.jl"
    registered_v4_job_sha = criteria["inputs"]["job"]["sha256"]
    assert owner_criteria["comparison_production_source"]["production_job_sha256"] == registered_v4_job_sha
    assert owner_criteria["comparison_production_source"]["same_as_immutable_w3_round3_job"] is True
    assert HOST.sha256(job) != registered_v4_job_sha
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
    ownership_module = (ROOT / "julia/CFDSDFWaterLily/src/OwnedV16Run.jl").read_text()
    assert "struct OwnedV16Run{O,B,S}" in ownership_module
    assert "owner::O" in ownership_module and "bodies::B" in ownership_module and "sim::S" in ownership_module
    assert "using .CFDSDFW3RunOwnership: OwnedV16Run" in production
    assert "GC.@preserve owned" in production
    assert "owned_run = OwnedV16Run(device_owner, bodies, sim)" in production
    assert "summary = run_primal(owned_run; vram_total)" in production
    for key, constant in (("state_sha256", "EXPECTED_STATE_SHA256"),
                          ("phi_c_order_sha256", "EXPECTED_PHI_C_ORDER_SHA256"),
                          ("phi_fortran_sha256", "EXPECTED_PHI_FORTRAN_SHA256")):
        assert criteria["geometry"][key] in production
        assert f"const {constant}" in production
    assert "bodies = v16_physical_profile_bodies(device_grid; T = Float32,\n        point_shape = SDF_POINT_SHAPE, sdf_spacing_m = SDF_SPACING_M)" in production
    assert "sim = build_v16_physical_profile_simulation(bodies; T = Float32, mem = CuArray)" in production
    assert "drag = total[1]" in production
    assert "downforce = -total[3]" in production
    device_grid_api = (ROOT / "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl").read_text()
    assert "owning `DeviceGridSDF` (and its CuArray) must stay alive" in device_grid_api
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
    assert "const MAX_STEPS = 6000" in job
    assert "owner_lost = !alive && capture.first_collected_step == step" in job
    assert "row count $count exceeds buffer capacity" in job


def test_host_verifier_handles_nonfinite_corruption_and_exact_kernel_slug():
    bad = force_row(24, 0.5, math.nan, math.nan, math.nan,
                    p=(math.nan, math.nan, math.nan), v=(math.nan, math.nan, math.nan))
    assert HOST.raw_force_rows_finite([bad]) is False
    assert HOST.raw_force_rows_finite([force_row(8, 80.0, 1.0, 0.0, -1.0)]) is True
    HOST.validate_kernel_identity("ramhachi888/expected-slug", "ramhachi888/expected-slug")
    try:
        HOST.validate_kernel_identity("ramhachi888/expected-slug", "ramhachi888/actual-slug")
    except ValueError as error:
        assert "differs from immutable criteria id" in str(error)
    else:
        raise AssertionError("kernel slug mismatch was not rejected")


def test_round_reason_separates_slug_retry_from_harness_correction():
    import runpy

    registrar = runpy.run_path(str(ROOT / "scripts/register_kaggle_w3_owner_full_horizon_2026_09.py"))
    assert "title-derived Kaggle slug" in registrar["round_reason"](2)
    assert "Round 2 was frozen but never submitted" in registrar["round_reason"](3)
    assert "target horizon" in registrar["round_reason"](3)
    assert registrar["output_for_round"](3).name == "kaggle_w3_owner_full_horizon_criteria_2026_09_round3.json"


def test_qualification_flags_are_read_from_registered_output_schema():
    criteria = {"evidence_output": {"qualification_flags": {
        "waterlily_v16_primal_qualified": False,
        "shape_update_allowed": False,
    }}}
    assert HOST.registered_qualification_flags(criteria) == {
        "waterlily_v16_primal_qualified": False,
        "shape_update_allowed": False,
    }


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


def test_dataset_title_stays_within_kaggle_metadata_limit(tmp_path: Path):
    import json
    import runpy

    prepare = runpy.run_path(str(ROOT / "scripts/prepare_kaggle_w3_owner_full_horizon_dataset_2026_09.py"))
    criteria_path = ROOT / "docs/evidence/kaggle_w3_owner_full_horizon_criteria_2026_09.json"
    manifest = prepare["stage"](criteria_path, tmp_path / "dataset")
    metadata = json.loads((tmp_path / "dataset/dataset-metadata.json").read_text())
    assert len(metadata["title"]) <= 50
    assert manifest["dataset_id"] == "ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-criteria"


def test_kernel_slug_and_round3_dataset_source_are_registered_together():
    import json
    import re
    import runpy

    metadata = json.loads((ROOT / "infra/kaggle/kernel_w3_owner_full_horizon/kernel-metadata.json").read_text())
    registrar = runpy.run_path(str(ROOT / "scripts/register_kaggle_w3_owner_full_horizon_2026_09.py"))
    slug = re.sub(r"[^a-z0-9]+", "-", metadata["title"].lower()).strip("-")
    assert metadata["id"] == f"ramhachi888/{slug}"
    assert metadata["id"] == registrar["KERNEL_ID"]
    assert metadata["dataset_sources"][-1] == "ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-criteria-round3"
