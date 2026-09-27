import hashlib
import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("w3_round3_runner", ROOT / "infra/kaggle/kernel_w3/runner.py")
host = load("w3_round3_host", ROOT / "scripts/verify_kaggle_w3_v16.py")
registrar = load("w3_round3_registrar", ROOT / "scripts/register_kaggle_w3_v16_primal_2026_09.py")


def fixture(linear=False):
    runner_path = ROOT / "infra/kaggle/kernel_w3/runner.py"
    criteria = {
        "source_commit": "a" * 40,
        "inputs": {"kernel_runner": {"sha256": hashlib.sha256(runner_path.read_bytes()).hexdigest()}},
        "geometry": {
            "state_sha256": "b" * 64, "state_npz_sha256": "c" * 64,
            "source_surface_sha256": "d" * 64, "design_domain_sha256": "e" * 64,
            "phi_c_order_sha256": "f" * 64, "phi_fortran_sha256": "1" * 64,
            "point_shape": [61, 33, 25], "cell_shape": [60, 32, 24],
            "canonical_sdf_origin_m": [-1.0, -0.8, -0.6], "spacing_m": 0.05,
            "margin_gate_m": 0.15, "expected_margin_m": 0.35, "margin_tolerance_m": 1e-6,
        },
        "profile_adapter": {
            "cell_dims": [100, 48, 36], "flow_origin_m": [-2.5, -1.2, -0.9],
            "physical_box_m": [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]],
            "spacing_m": 0.05, "solver_length": 16.0, "solver_viscosity": 0.2, "reynolds": 80.0,
            "x_max_boundary": "WaterLily convective exit",
            "pressure_boundary": "WaterLily projection pressure; no per-patch freestreamPressure input",
        },
        "backend": {
            "accelerator": "NvidiaTeslaT4", "machine_shape": "NvidiaTeslaT4", "gpu_name": "Tesla T4",
            "gpu_count": 2, "driver_version": "580.159.04", "cuda_visible_devices": "0",
            "julia_archive_sha256": runner.JULIA_SHA256, "compute_capability": "7.5.0",
            "cuda_driver_api_version": "13.3.0", "cuda_runtime_version": "12.8.0",
            "julia_version": "1.12.6", "julia_threads": 1, "waterlily_version": "1.8.0",
            "cuda_jl_version": "6.3.1",
        },
        "measurement": {
            "burn_in_t_u_l": 80.0, "t_end_t_u_l": 120.0, "force_window_t_u_l": [80.0, 120.0],
            "minimum_window_samples": 4, "sample_every_solver_steps": 8,
            "host_recompute_relative_tolerance": 1e-9, "force_component_relative_tolerance": 1e-6,
            "force_component_absolute_tolerance": 1e-8, "reference_area_m2": 0.64,
            "spacing_m": 0.05, "density_kg_m3": 1.0, "freestream_mps": [1.0, 0.0, 0.0],
            "runtime_limit_s": 1800.0, "stationarity": {"relative_half_window_drift_max": 0.02},
        },
    }
    rows = []
    for step, t in zip((8, 16, 24, 32, 40, 43), (79.0, 85.0, 95.0, 105.0, 115.0, 121.0)):
        drag, down = (t, 0.5 * t) if linear else (2.0, 0.5)
        p, v = (0.8 * drag, 0.12, -0.75 * down), (0.2 * drag, 0.08, -0.25 * down)
        rows.append({
            "step": float(step), "t_u_l": t, "fx_solver": drag, "fy_solver": p[1] + v[1],
            "fz_solver": -down, "drag_solver": drag, "downforce_solver": down,
            "pressure_fx_solver": p[0], "pressure_fy_solver": p[1], "pressure_fz_solver": p[2],
            "viscous_fx_solver": v[0], "viscous_fy_solver": v[1], "viscous_fz_solver": v[2],
        })
    summary = {
        "state_sha256": "b" * 64, "source_surface_sha256": "d" * 64,
        "phi_c_order_sha256": "f" * 64, "phi_fortran_sha256": "1" * 64,
        "device_roundtrip_sha256": "1" * 64, "dims": [100, 48, 36],
        "canonical_sdf_origin_m": [-1.0, -0.8, -0.6], "flow_origin_m": [-2.5, -1.2, -0.9],
        "flow_upper_m": [2.5, 1.2, 0.9], "spacing_m": 0.05,
        "phi_margin_gate_m": 0.15, "phi_margin_m": 0.35,
        "source_profile_equivalent": False, "physical_profile_qualified": False,
        "x_max_boundary": criteria["profile_adapter"]["x_max_boundary"],
        "pressure_boundary": criteria["profile_adapter"]["pressure_boundary"],
        "reynolds": 80.0, "solver_length": 16.0, "solver_viscosity": 0.2,
        "gpu_uuid": "GPU-test-0", "gpu_name": "Tesla T4", "julia_version": "1.12.6",
        "julia_threads": 1, "waterlily_version": "1.8.0", "waterlily_backend": "KernelAbstractions",
        "cuda_jl_version": "6.3.1", "t_end_target": 120.0, "t_end_reached": 121.0,
        "steps": 43, "finite_u": True, "finite_p": True, "force_samples": len(rows),
        "wall_seconds": 10.0, "peak_vram_bytes": 100, "vram_total_bytes": 1000,
    }
    summary.update(runner.recompute_metrics(rows, criteria["measurement"]))
    adapter = {
        "source_profile_equivalent": False, "physical_profile_qualified": False,
        "flow_origin_m": [-2.5, -1.2, -0.9], "flow_cell_dims": [100, 48, 36],
        "canonical_sdf_origin_m": [-1.0, -0.8, -0.6],
        "x_max_boundary": criteria["profile_adapter"]["x_max_boundary"],
        "pressure_boundary": criteria["profile_adapter"]["pressure_boundary"],
    }
    gpu = ["0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
           "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04"]
    smoke = "W0B_SMOKE_DONE CUDA_FUNCTIONAL true GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_DRIVER_VERSION 13.3.0 CUDA_RUNTIME_VERSION 12.8.0 JULIA_VERSION 1.12.6 CUDA_JL_VERSION 6.3.1 WATERLILY_VERSION 1.8.0 GPU_NAME Tesla T4 NO_SOLVER_STEP"
    return criteria, summary, rows, adapter, gpu, smoke


def compare_gates(criteria, summary, rows, adapter, gpu, smoke):
    rg, rm = runner.evaluate_gates(
        criteria, summary, rows, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "2" * 64, gpu, smoke,
        adapter_contract=adapter)
    hm = host.recompute_metrics(rows, criteria["measurement"])
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "2" * 64, "julia_archive_sha256": runner.JULIA_SHA256,
        "cuda_visible_devices": "0",
    }
    hg = host.evaluate_gates(
        criteria, summary, rows, True, {"state_sha256": "b" * 64}, 0.35, adapter,
        [[s.strip() for s in r.split(",")] for r in gpu], "GPU-test-0", smoke,
        fingerprint, hm, host.metrics_match(summary, hm, criteria["measurement"]),
        host.force_components_close(rows, criteria["measurement"]))
    return rg, hg, rm, hm


def test_expanded_flow_mapping_keeps_canonical_sdf_fixed():
    criteria, summary, _, adapter, *_ = fixture()
    assert criteria["geometry"]["canonical_sdf_origin_m"] == [-1.0, -0.8, -0.6]
    assert summary["flow_origin_m"] == [-2.5, -1.2, -0.9]
    assert summary["flow_origin_m"] != summary["canonical_sdf_origin_m"]
    target = [0.25, 0.0, 0.0]
    solver = [(target[i] - x) / 0.05 for i, x in enumerate(summary["flow_origin_m"])]
    world = [x + 0.05 * q for x, q in zip(summary["flow_origin_m"], solver)]
    assert world == pytest.approx(target)
    assert adapter["flow_cell_dims"] == [100, 48, 36]
    assert criteria["profile_adapter"]["solver_length"] == 16
    assert criteria["profile_adapter"]["solver_viscosity"] == 0.2
    assert criteria["profile_adapter"]["reynolds"] == 80


def test_exact_endpoint_clipping_and_weighted_half_windows():
    criteria, _, rows, *_ = fixture(linear=True)
    rm = runner.recompute_metrics(rows, criteria["measurement"])
    hm = host.recompute_metrics(rows, criteria["measurement"])
    assert rm == pytest.approx(hm, rel=1e-12, abs=1e-12)
    assert rm["window_time_weighted_drag_solver"] == pytest.approx(100.0)
    assert rm["window_time_weighted_downforce_solver"] == pytest.approx(50.0)
    assert rm["diagnostic_first_half_time_weighted_drag_solver"] == pytest.approx(90.0)
    assert rm["diagnostic_second_half_time_weighted_drag_solver"] == pytest.approx(110.0)
    assert rm["stationarity_relative_half_window_drift_drag"] == pytest.approx(0.2)
    clipped = runner.clipped_force_window(rows, 80.0, 120.0)
    assert (clipped[0]["t_u_l"], clipped[-1]["t_u_l"]) == (80.0, 120.0)


def test_host_runner_gates_match_for_t7_orientation_and_t10_stationarity():
    criteria, summary, rows, adapter, gpu, smoke = fixture(linear=True)
    rg, hg, *_ = compare_gates(criteria, summary, rows, adapter, gpu, smoke)
    assert rg == hg
    assert rg["T7_drag_orientation_and_host_recomputation"] is True
    assert rg["T10_stationarity"] is False
    criteria, summary, rows, adapter, gpu, smoke = fixture()
    rg, hg, *_ = compare_gates(criteria, summary, rows, adapter, gpu, smoke)
    assert rg == hg and all(rg.values())
    summary["window_time_weighted_drag_solver"] = -1.0
    rg, hg, *_ = compare_gates(criteria, summary, rows, adapter, gpu, smoke)
    assert rg == hg and rg["T7_drag_orientation_and_host_recomputation"] is False


def test_pressure_viscous_closure_covers_all_force_axes():
    criteria, _, rows, *_ = fixture()
    assert runner.force_components_close(rows, criteria["measurement"])
    assert host.force_components_close(rows, criteria["measurement"])
    rows[2]["viscous_fy_solver"] += 0.1
    assert not runner.force_components_close(rows, criteria["measurement"])
    assert not host.force_components_close(rows, criteria["measurement"])


def test_phi_hash_lineage_rejects_changed_gpu_round_trip():
    criteria, summary, rows, adapter, gpu, smoke = fixture()
    assert summary["device_roundtrip_sha256"] == criteria["geometry"]["phi_fortran_sha256"]
    summary["device_roundtrip_sha256"] = "9" * 64
    rg, hg, *_ = compare_gates(criteria, summary, rows, adapter, gpu, smoke)
    assert rg == hg and rg["T1_canonical_v16_identity"] is False


def test_sampling_contract_allows_only_terminal_bracketing_extra():
    criteria, summary, rows, adapter, gpu, smoke = fixture()
    assert compare_gates(criteria, summary, rows, adapter, gpu, smoke)[0][
        "T6_finite_fields_and_candidate_forces"]
    rows[-2]["step"] = 39
    rg, hg, *_ = compare_gates(criteria, summary, rows, adapter, gpu, smoke)
    assert rg == hg and not rg["T6_finite_fields_and_candidate_forces"]


def test_force_csv_requires_all_13_columns(tmp_path):
    path = tmp_path / "forces.csv"
    path.write_text("step,t_u_l,drag_solver\n1,80,nan\n")
    with pytest.raises(RuntimeError, match="schema mismatch"):
        runner.parse_force_csv(path)


def test_round3_registration_is_expanded_domain_and_append_only():
    assert registrar.criteria_output_path(3).name == "kaggle_w3_v16_primal_criteria_2026_09_round3.json"
    with pytest.raises(ValueError, match="expanded-domain"):
        registrar.build_criteria("a" * 40, criteria_round=2)


def test_pass_result_and_sha_sidecar_are_append_only(tmp_path):
    result_path = tmp_path / "w3_round3_result.json"
    result = {"verdict": "PASS", "kernel_version": 4}
    digest = host.write_result_evidence(result_path, result)
    assert digest == host.sha256(result_path)
    assert result_path.with_suffix(".json.sha256").read_text() == digest + "\n"
    with pytest.raises(ValueError, match="already exists"):
        host.write_result_evidence(result_path, result)
