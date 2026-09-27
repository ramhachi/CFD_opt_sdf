import hashlib
import importlib.util
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "infra/kaggle/kernel_w3/runner.py"
SPEC = importlib.util.spec_from_file_location("kaggle_w3_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
HOST_VERIFIER_PATH = ROOT / "scripts/verify_kaggle_w3_v16.py"
HOST_SPEC = importlib.util.spec_from_file_location("verify_kaggle_w3_v16", HOST_VERIFIER_PATH)
host_verifier = importlib.util.module_from_spec(HOST_SPEC)
HOST_SPEC.loader.exec_module(host_verifier)
REGISTRAR_PATH = ROOT / "scripts/register_kaggle_w3_v16_primal_2026_09.py"
REG_SPEC = importlib.util.spec_from_file_location("register_kaggle_w3_v16", REGISTRAR_PATH)
registrar = importlib.util.module_from_spec(REG_SPEC)
REG_SPEC.loader.exec_module(registrar)


def fixture():
    runner_sha = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
    criteria = {
        "source_commit": "a" * 40,
        "inputs": {"kernel_runner": {"sha256": runner_sha}},
        "geometry": {
            "state_sha256": "b" * 64,
            "source_surface_sha256": "c" * 64,
            "phi_c_order_sha256": "d" * 64,
            "phi_fortran_sha256": "e" * 64,
            "origin_m": [-1.0, -0.8, -0.6],
            "spacing_m": 0.05,
            "margin_gate_m": 0.15,
            "expected_margin_m": 0.35,
            "margin_tolerance_m": 1e-6,
        },
        "profile_adapter": {
            "cell_dims": [60, 32, 24],
            "x_max_boundary": "WaterLily convective exit",
            "pressure_boundary": "WaterLily projection pressure; no per-patch freestreamPressure input",
        },
        "backend": {
            "accelerator": "NvidiaTeslaT4",
            "gpu_name": "Tesla T4",
            "gpu_count": 2,
            "driver_version": "580.159.04",
            "compute_capability": "7.5.0",
            "julia_version": "1.12.6",
            "julia_threads": 1,
            "waterlily_version": "1.8.0",
            "cuda_jl_version": "6.3.1",
        },
        "measurement": {
            "burn_in_t_u_l": 80.0,
            "t_end_t_u_l": 120.0,
            "minimum_window_samples": 4,
            "sample_every_solver_steps": 8,
            "host_recompute_relative_tolerance": 1e-9,
            "force_component_relative_tolerance": 1e-6,
            "force_component_absolute_tolerance": 1e-8,
            "reference_area_m2": 0.64,
            "spacing_m": 0.05,
            "runtime_limit_s": 1800.0,
        },
    }
    rows = [
        {"step": 8.0, "t_u_l": 80.0, "fx_solver": 2.0, "fy_solver": 0.1,
         "fz_solver": -0.5, "drag_solver": 2.0, "downforce_solver": 0.5,
         "pressure_drag_solver": 1.7, "viscous_drag_solver": 0.3},
        {"step": 16.0, "t_u_l": 90.0, "fx_solver": 2.2, "fy_solver": 0.1,
         "fz_solver": -0.55, "drag_solver": 2.2, "downforce_solver": 0.55,
         "pressure_drag_solver": 1.8, "viscous_drag_solver": 0.4},
        {"step": 24.0, "t_u_l": 110.0, "fx_solver": 2.5, "fy_solver": 0.1,
         "fz_solver": -0.6, "drag_solver": 2.5, "downforce_solver": 0.6,
         "pressure_drag_solver": 2.0, "viscous_drag_solver": 0.5},
        {"step": 32.0, "t_u_l": 120.0, "fx_solver": 2.7, "fy_solver": 0.1,
         "fz_solver": -0.65, "drag_solver": 2.7, "downforce_solver": 0.65,
         "pressure_drag_solver": 2.1, "viscous_drag_solver": 0.6},
    ]
    summary = {
        "state_sha256": "b" * 64,
        "source_surface_sha256": "c" * 64,
        "phi_c_order_sha256": "d" * 64,
        "phi_fortran_sha256": "e" * 64,
        "device_roundtrip_sha256": "e" * 64,
        "dims": [60, 32, 24],
        "origin_m": [-1.0, -0.8, -0.6],
        "spacing_m": 0.05,
        "phi_margin_gate_m": 0.15,
        "phi_margin_m": 0.35,
        "source_profile_equivalent": False,
        "physical_profile_qualified": False,
        "x_max_boundary": criteria["profile_adapter"]["x_max_boundary"],
        "pressure_boundary": criteria["profile_adapter"]["pressure_boundary"],
        "gpu_uuid": "GPU-test-0",
        "gpu_name": "Tesla T4",
        "julia_version": "1.12.6",
        "julia_threads": 1,
        "waterlily_version": "1.8.0",
        "cuda_jl_version": "6.3.1",
        "t_end_target": 120.0,
        "t_end_reached": 120.2,
        "steps": 33,
        "finite_u": True,
        "finite_p": True,
        "force_samples": 4,
        "window_samples": 4,
        "wall_seconds": 10.0,
        "peak_vram_bytes": 100,
        "vram_total_bytes": 1000,
    }
    summary.update(runner.recompute_metrics(rows, criteria["measurement"]))
    return criteria, summary, rows


def test_w3_registered_mapping_gates_accept_correct_native_approximation():
    criteria, summary, rows = fixture()
    gpu_rows = [
        "0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04",
    ]
    smoke = "W0B_SMOKE_DONE\nCUDA_FUNCTIONAL true\nGPU_COMPUTE_CAPABILITY 7.5.0\nCUDA_DRIVER_VERSION 13.3.0\nCUDA_RUNTIME_VERSION 12.8.0\n"
    gates, metrics = runner.evaluate_gates(
        criteria, summary, rows, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "f" * 64,
        gpu_rows, smoke,
    )
    assert all(gates.values())
    assert math.isclose(metrics["cd_time_weighted"], summary["cd_time_weighted"])


def test_w3_does_not_upgrade_native_waterlily_adapter_to_profile_equivalence():
    criteria, summary, rows = fixture()
    summary["source_profile_equivalent"] = True
    gpu_rows = [
        "0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04",
    ]
    smoke = "W0B_SMOKE_DONE CUDA_FUNCTIONAL true GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_DRIVER_VERSION 13.3.0 CUDA_RUNTIME_VERSION 12.8.0"
    gates, _ = runner.evaluate_gates(
        criteria, summary, rows, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "f" * 64,
        gpu_rows, smoke,
    )
    assert gates["T3_profile_adapter_is_explicitly_limited"] is False


def test_w3_drag_gate_uses_candidate_force_orientation():
    criteria, summary, rows = fixture()
    for row in rows:
        row["fx_solver"] *= -1
        row["drag_solver"] *= -1
    summary.update(runner.recompute_metrics(rows, criteria["measurement"]))
    gpu_rows = [
        "0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04",
    ]
    smoke = "W0B_SMOKE_DONE CUDA_FUNCTIONAL true GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_DRIVER_VERSION 13.3.0 CUDA_RUNTIME_VERSION 12.8.0"
    gates, _ = runner.evaluate_gates(
        criteria, summary, rows, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "f" * 64,
        gpu_rows, smoke,
    )
    assert gates["T7_drag_orientation_and_host_recomputation"] is False


def test_w3_force_csv_rejects_schema_and_nonfinite_values(tmp_path):
    path = tmp_path / "forces.csv"
    path.write_text("step,t_u_l,drag\n1,80,nan\n")
    try:
        runner.parse_force_csv(path)
    except RuntimeError as error:
        assert "schema mismatch" in str(error)
    else:
        raise AssertionError("malformed W3 force CSV was accepted")


def test_w3_force_gate_checks_sampling_and_component_closure():
    criteria, summary, rows = fixture()
    gpu_rows = [
        "0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04",
    ]
    smoke = "W0B_SMOKE_DONE CUDA_FUNCTIONAL true GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_DRIVER_VERSION 13.3.0 CUDA_RUNTIME_VERSION 12.8.0"
    rows[1]["pressure_drag_solver"] += 0.1
    gates, _ = runner.evaluate_gates(
        criteria, summary, rows, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "f" * 64,
        gpu_rows, smoke,
    )
    assert gates["T6_finite_fields_and_candidate_forces"] is True
    assert gates["T7_drag_orientation_and_host_recomputation"] is False


def test_w3_criteria_input_names_match_runner_contract():
    assert registrar.SOURCE_INPUTS["kernel_runner"] == RUNNER_PATH
    assert registrar.SOURCE_INPUTS["project"].name == "Project.toml"
    assert registrar.SOURCE_INPUTS["manifest"].name == "Manifest.toml"
    assert registrar.SOURCE_INPUTS["host_verifier"] == HOST_VERIFIER_PATH


def test_w3_host_verifier_recomputes_force_metrics_independently():
    criteria, _, rows = fixture()
    remote_metrics = runner.recompute_metrics(rows, criteria["measurement"])
    host_metrics = host_verifier.recompute_metrics(rows, criteria["measurement"])
    assert set(host_metrics) == set(remote_metrics)
    assert all(math.isclose(host_metrics[key], remote_metrics[key], rel_tol=1e-12, abs_tol=1e-12)
               for key in host_metrics)
    assert host_verifier.force_components_close(rows, criteria["measurement"])
    rows[-1]["pressure_drag_solver"] += 0.01
    assert not host_verifier.force_components_close(rows, criteria["measurement"])
