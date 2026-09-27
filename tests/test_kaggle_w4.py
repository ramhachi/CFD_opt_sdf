import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("kaggle_w4_runner", ROOT / "infra/kaggle/kernel_w4/runner.py")
host = load_module("verify_kaggle_w4", ROOT / "scripts/verify_kaggle_w4_v16.py")
registrar = load_module(
    "register_kaggle_w4", ROOT / "scripts/register_kaggle_w4_v16_sensitivity_2026_09.py")
DRAFT_PATH = ROOT / "docs/evidence/w4_v16_sensitivity_criteria_draft_2026_09.json"


def fixture():
    draft = json.loads(DRAFT_PATH.read_text())
    criteria = copy.deepcopy(draft)
    criteria.update({
        "immutable": True,
        "status": "registered_not_run",
        "registered_before_computation": True,
        "source_commit": "a" * 40,
        "registered_source_commit": "a" * 40,
        "input_dataset_id": "ramhachi888/cfd-opt-sdf-v16-w4-sensitivity",
        "inputs": {
            "kernel_runner": {"location": "source_repo", "path": "infra/kaggle/kernel_w4/runner.py",
            "sha256": hashlib.sha256(
                (ROOT / "infra/kaggle/kernel_w4/runner.py").read_bytes()).hexdigest()},
            "job": {"location": "source_repo", "path": "scripts/waterlily_w4_v16_sensitivity_job.jl",
                    "sha256": "b" * 64},
            "project": {"location": "source_repo", "path": "julia/CFDSDFWaterLilyT4/Project.toml",
                        "sha256": "c" * 64},
            "manifest": {"location": "source_repo", "path": "julia/CFDSDFWaterLilyT4/Manifest.toml",
                         "sha256": "d" * 64},
            "kaggle_smoke": {"location": "source_repo", "path": "scripts/w0b_t4_smoke.jl",
                             "sha256": "e" * 64},
            "canonical_state_npz": {"location": "kaggle_dataset", "path": "sdf_design_state.npz",
                                    "sha256": "f" * 64},
            "canonical_phi_fortran_raw": {"location": "kaggle_dataset",
                                           "path": "canonical_v16_phi_f4_fortran.raw",
                                           "sha256": "1" * 64},
        },
        "prerequisites": {"w3_result_evidence": {
            "path": "docs/evidence/kaggle_w3_v16_primal_result_2026_09.json",
            "sha256": "2" * 64, "criteria_sha256": "3" * 64,
            "kernel_version": 3, "host_verified": True,
        }},
    })
    criteria["measurement"].update({"minimum_force_window_samples": 4})
    criteria["backend"] = {
        "accelerator": "NvidiaTeslaT4", "machine_shape": "NvidiaTeslaT4",
        "gpu_count": 2, "gpu_name": "Tesla T4", "driver_version": "580.159.04",
        "cuda_visible_devices": "0", "julia_archive_sha256": "5" * 64,
        "compute_capability": "7.5.0", "cuda_driver_api_version": "13.3.0",
        "cuda_runtime_version": "12.8.0", "cuda_jl_version": "6.3.1",
        "julia_version": "1.12.6", "julia_threads": 1,
        "waterlily_version": "1.8.0", "waterlily_backend": "fixture-backend",
    }
    summaries, metrics_by_case, rows_by_case = {}, {}, {}
    for case_index, case in enumerate(criteria["cases"]):
        rows = []
        for step, time_value, offset in ((8, 80.0, 0.0), (16, 90.0, 0.1),
                                         (24, 110.0, 0.2), (32, 120.0, 0.3)):
            drag = 2.0 + 0.1 * case_index + (0.4 if case["case_id"] == "domain_xplus3p5_16" else 0) + offset
            downforce = 0.4 + 0.02 * case_index + 0.01 * offset
            rows.append({
                "step": float(step), "t_u_l": time_value,
                "fx_solver": drag, "fy_solver": 0.2, "fz_solver": -downforce,
                "drag_solver": drag, "downforce_solver": downforce,
                "pressure_fx_solver": drag * 0.8, "pressure_fy_solver": 0.1,
                "pressure_fz_solver": -downforce * 0.75,
                "viscous_fx_solver": drag * 0.2, "viscous_fy_solver": 0.1,
                "viscous_fz_solver": -downforce * 0.25,
            })
        metrics = runner.recompute_case_metrics(rows, case, criteria["measurement"])
        summary = copy.deepcopy(metrics)
        summary.update({
            "case_id": case["case_id"],
            "flow_dims": case["flow_dims"],
            "world_origin_m": criteria["geometry"]["world_origin_m"],
            "physical_box_max_m": case["physical_box_m"][1],
            "flow_spacing_m": case["flow_spacing_m"],
            "solver_length": case["solver_length"],
            "solver_time_unit_s": case["solver_time_unit_s"],
            "solver_viscosity": case["solver_viscosity"],
            "reynolds": case["reynolds"],
            "density_kg_m3": case["density_kg_m3"],
            "dynamic_viscosity_pa_s": case["dynamic_viscosity_pa_s"],
            "freestream_mps": case["freestream_mps"],
            "reference_length_m": case["reference_length_m"],
            "reference_area_m2": case["reference_area_m2"],
            "canonical_design_spacing_m": criteria["geometry"]["design_lattice_spacing_m"],
            "state_sha256": criteria["geometry"]["canonical_state_sha256"],
            "source_surface_sha256": criteria["geometry"]["source_surface_sha256"],
            "phi_c_order_sha256": criteria["geometry"]["canonical_phi_c_order_sha256"],
            "phi_fortran_sha256": criteria["geometry"]["canonical_phi_fortran_sha256"],
            "device_roundtrip_sha256": criteria["geometry"]["canonical_phi_fortran_sha256"],
            "phi_margin_m": criteria["geometry"]["phi_expected_margin_m"],
            "phi_margin_gate_m": criteria["geometry"]["phi_margin_gate_m"],
            "source_profile_equivalent": False,
            "physical_profile_qualified": False,
            "native_velocity_boundary": criteria["profile_semantics"]["native_velocity_boundary"],
            "side_top_tangential_boundary": criteria["profile_semantics"]["side_top_tangential_boundary"],
            "x_max_boundary": criteria["profile_semantics"]["x_plus_boundary"],
            "pressure_boundary": criteria["profile_semantics"]["pressure_boundary"],
            "ground_model": criteria["profile_semantics"]["ground_model"],
            "force_integration_body": criteria["profile_semantics"]["force_integration_body"],
            "force_projection_semantics": "drag=+Fx; downforce=-Fz",
            "gpu_uuid": "GPU-test-0", "gpu_name": "Tesla T4",
            "julia_version": "1.12.6", "julia_threads": 1,
            "waterlily_version": "1.8.0", "waterlily_backend": "fixture-backend",
            "cuda_jl_version": "6.3.1", "t_end_target": 120.0,
            "t_end_reached": 120.01, "steps": 33, "finite_u": True,
            "finite_p": True, "finite_forces": True, "force_samples": 4,
            "wall_seconds": 10.0, "peak_vram_bytes": 100, "vram_total_bytes": 1000,
        })
        summaries[case["case_id"]] = summary
        metrics_by_case[case["case_id"]] = metrics
        rows_by_case[case["case_id"]] = rows
    gpu_rows = [
        "0, Tesla T4, GPU-test-0, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-test-1, 15360 MiB, 580.159.04",
    ]
    smoke = " ".join((
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
        "CUDA_DRIVER_VERSION 13.3.0", "CUDA_RUNTIME_VERSION 12.8.0",
        "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
        "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4", "NO_SOLVER_STEP",
    ))
    return criteria, summaries, metrics_by_case, rows_by_case, gpu_rows, smoke


def test_w4_matrix_contract_and_runner_host_metrics_agree():
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture()
    runner.validate_case_contract(criteria)
    host.validate_case_contract(criteria)
    margin = criteria["geometry"]["phi_expected_margin_m"]
    runner_gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, margin, gpu_rows, smoke,
        criteria["source_commit"], criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "4" * 64,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
    }
    host_gates = host.recompute_gates(criteria, summaries, metrics, rows,
                                      margin, gpu_rows, smoke, fingerprint)
    assert all(runner_gates.values())
    assert all(host_gates.values())
    assert runner_gates == host_gates
    assert runner.response_analysis(metrics) == host.response_analysis(metrics)


def test_w4_component_closure_checks_all_axes_and_projection():
    criteria, _, _, rows, _, _ = fixture()
    measurements = criteria["measurement"]
    sample_rows = rows["flow_16"]
    assert runner.force_components_close(sample_rows, measurements)
    assert host.force_components_close(sample_rows, measurements)
    sample_rows[1]["viscous_fy_solver"] += 0.02
    assert not runner.force_components_close(sample_rows, measurements)
    assert not host.force_components_close(sample_rows, measurements)


def test_w4_trapezoidal_metric_clips_samples_to_exact_time_window():
    criteria, *_ = fixture()
    case = criteria["cases"][0]
    rows = []
    for step, time_value in ((8, 79.0), (16, 80.0), (24, 90.0),
                             (32, 105.0), (40, 118.0), (43, 121.0)):
        drag, downforce = time_value, 1.0
        rows.append({
            "step": float(step), "t_u_l": time_value,
            "fx_solver": drag, "fy_solver": 0.0, "fz_solver": -downforce,
            "drag_solver": drag, "downforce_solver": downforce,
            "pressure_fx_solver": 0.75 * drag, "pressure_fy_solver": 0.0,
            "pressure_fz_solver": -0.6, "viscous_fx_solver": 0.25 * drag,
            "viscous_fy_solver": 0.0, "viscous_fz_solver": -0.4,
        })
    for recompute in (runner.recompute_case_metrics, host.recompute_case_metrics):
        metrics = recompute(rows, case, criteria["measurement"])
        assert metrics["window_samples"] == 4
        assert math.isclose(metrics["window_time_weighted_drag_solver"], 100.0, abs_tol=1e-12)


def test_w4_case_mapping_gate_rejects_grid_identity_drift():
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture()
    summaries["flow_24"]["flow_dims"] = [89, 48, 36]
    gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    assert gates["T3_case_mapping_and_reynolds"] is False


def test_w4_criteria_contract_rejects_changed_case_matrix():
    criteria, *_ = fixture()
    runner.validate_case_contract(criteria)
    host.validate_case_contract(criteria)
    criteria["cases"][1]["flow_dims"] = [89, 48, 36]
    for validate in (runner.validate_case_contract, host.validate_case_contract):
        try:
            validate(criteria)
        except (RuntimeError, ValueError) as error:
            assert "mapping" in str(error) or "inventory" in str(error)
        else:
            raise AssertionError("changed W4 case matrix was accepted")


def test_w4_staged_dataset_allows_only_registered_files_and_upload_metadata(tmp_path):
    criteria = {"input_dataset_id": "ramhachi888/cfd-opt-sdf-v16-w4-sensitivity"}
    expected = {"sdf_design_state.npz", "w4_v16_criteria.json"}
    manifest_path = tmp_path / "w4_v16_dataset_manifest.json"
    manifest_path.write_text("{}")
    (tmp_path / "dataset-metadata.json").write_text(json.dumps({"id": criteria["input_dataset_id"]}))
    for name in expected:
        (tmp_path / name).write_text(name)

    host.verify_staged_dataset_inventory(criteria, tmp_path, expected, manifest_path)
    (tmp_path / "unregistered.txt").write_text("extra")
    with pytest.raises(ValueError, match="unregistered files"):
        host.verify_staged_dataset_inventory(criteria, tmp_path, expected, manifest_path)


def test_w4_final_criteria_registration_refuses_w3_error_diagnostic():
    w3_criteria = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09.json"
    w3_error = ROOT / "docs/evidence/kaggle_w3_v16_primal_version2_diagnostic_2026_09.json"

    with pytest.raises(ValueError, match="exact host-verified PASS"):
        registrar.load_w3_pass(w3_criteria, w3_error)


def test_w4_sensitive_domain_effect_requires_registered_followup():
    _, _, metrics, _, _, _ = fixture()
    result = host.response_analysis(metrics)
    assert result["drag_time_weighted_n"]["domain_delta_abs_n"] >= \
        result["drag_time_weighted_n"]["resolution_delta_abs_n"]
    assert result["drag_time_weighted_n"]["extended_domain_fine_grid_required"] is True
    assert result["any_force_component_requires_extended_domain_fine_grid"] is True


def test_w4_margin_matches_julia_lipschitz_bound_definition():
    import numpy as np

    phi = np.ones((5, 5, 5), dtype=np.float32)
    phi[2, 2, 2] = -0.25
    assert math.isclose(runner.zero_level_margin_m(phi, 0.05), -0.15, abs_tol=1e-12)
    assert math.isclose(host.zero_level_margin_m(phi, 0.05), -0.15, abs_tol=1e-12)


def test_w4_draft_cannot_be_loaded_as_an_immutable_registration(tmp_path):
    path = tmp_path / "w4_v16_criteria.json"
    path.write_bytes(DRAFT_PATH.read_bytes())
    (tmp_path / "w4_v16_criteria.json.sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    for verifier in (runner.read_criteria, host.load_criteria):
        try:
            verifier(path) if verifier is host.load_criteria else verifier(path.parent)
        except (RuntimeError, ValueError) as error:
            assert "immutable" in str(error) or "preregistration" in str(error)
        else:
            raise AssertionError("W4 draft was accepted for measurement")
