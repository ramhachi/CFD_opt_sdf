import copy
import hashlib
import importlib.util
import json
import math
from types import SimpleNamespace
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


def fixture(criteria_override=None):
    draft = json.loads(DRAFT_PATH.read_text())
    criteria = copy.deepcopy(criteria_override if criteria_override is not None else draft)
    if criteria_override is None:
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
            "prerequisites": {
            "w3_baseline_reused": False,
            "all_four_cases_reexecuted": True,
            "w3_flow16_comparison_required": True,
            "w3_flow16_numerical_repeatability_gate_registered": False,
            "w3_result_evidence": {
                "path": "docs/evidence/kaggle_w3_v16_primal_result_2026_09.json",
                "sha256": "2" * 64, "criteria_sha256": "3" * 64,
                "criteria_path": "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json",
                "kernel_version": 3, "host_verified": True,
                }},
        })
        criteria["prerequisites"]["w3_result_evidence"]["criteria_sha256"] = \
            criteria["measurement"]["stationarity"]["precedent_criteria_sha256"]
    criteria["measurement"].update({"minimum_force_window_samples": 4})
    if criteria_override is None:
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
        for step, time_value, offset in ((8, 80.0, 0.0), (16, 90.0, 0.002),
                                         (24, 110.0, -0.002), (32, 120.0, 0.0)):
            drag = 2.0 + 0.1 * case_index + (0.4 if case["case_id"] == "domain_xplus1m_16" else 0) + offset
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
            "flow_origin_m": criteria["geometry"]["baseline_flow_origin_m"],
            "canonical_sdf_origin_m": criteria["geometry"]["canonical_sdf_origin_m"],
            "physical_box_max_m": [axis[1] for axis in case["physical_box_m"]],
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
            "canonical_state_label": criteria["geometry"].get("state_label", "v16"),
            "canonical_design_point_shape": criteria["geometry"]["point_shape"],
            "canonical_design_cell_shape": criteria["geometry"]["cell_shape"],
            "state_sha256": criteria["geometry"]["canonical_state_sha256"],
            "state_npz_sha256": criteria["geometry"].get("canonical_state_npz_sha256"),
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
            "waterlily_version": "1.8.0", "waterlily_backend": criteria["backend"]["waterlily_backend"],
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
    backend = criteria["backend"]
    smoke = " ".join((
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
        f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
        f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
        f"JULIA_VERSION {backend['julia_version']}", f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
        f"WATERLILY_VERSION {backend['waterlily_version']}", f"GPU_NAME {backend['gpu_name']}",
        "NO_SOLVER_STEP",
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


def test_w4_v17_registration_binds_exact_w3_state_and_separates_design_flow_grids():
    w3_criteria = ROOT / "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json"
    w3_result = ROOT / "docs/evidence/kaggle_w3_v17_primal_result_2026_09.json"
    criteria = registrar.build_criteria("a" * 40, 1, w3_criteria, w3_result)
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture(criteria)
    runner.validate_case_contract(criteria)
    host.validate_case_contract(criteria)
    assert criteria["geometry"]["state_label"] == "v17"
    assert criteria["prerequisites"]["canonical_state_identity"]["state_sha256"] == \
        "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
    assert criteria["prerequisites"]["w3_result_evidence"]["sha256"] == \
        "e7d48a98d912e570ea3b077bb5904106c2558c845fd286684775bd6907e68bba"
    assert criteria["geometry"]["design_lattice_spacing_m"] == 0.025
    assert [case["flow_spacing_m"] for case in criteria["cases"]] == \
        [0.05, 1 / 30, 0.025, 0.05]
    gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "4" * 64,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
    }
    host_gates = host.recompute_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, fingerprint,
    )
    assert all(gates.values())
    assert gates == host_gates
    diagnostic = host.historical_v16_w4_diagnostic(criteria, metrics, summaries)
    assert diagnostic["diagnostic_only"] is True
    assert diagnostic["qualification_gate"] is False
    assert diagnostic["reference_result_sha256"] == hashlib.sha256(
        (ROOT / "docs/evidence/kaggle_w4_v16_sensitivity_result_round4_2026_09.json")
        .read_bytes()).hexdigest()
    assert set(diagnostic["cases"]) == {case["case_id"] for case in criteria["cases"]}


def test_w4_v17_kernel_package_runner_is_the_registered_runner():
    packaged = ROOT / "infra/kaggle/kernel_w4_v17/runner.py"
    shared = ROOT / "infra/kaggle/kernel_w4/runner.py"
    metadata = json.loads((ROOT / "infra/kaggle/kernel_w4_v17/kernel-metadata.json").read_text())
    assert packaged.read_bytes() == shared.read_bytes()
    assert metadata["id"] == "ramhachi888/cfd-opt-sdf-w4-v17-sensitivity"
    assert metadata["is_private"] is True
    assert metadata["dataset_sources"] == ["ramhachi888/cfd-opt-sdf-v17-w4-sensitivity"]


def test_remote_inventory_digest_is_canonical_and_order_independent():
    left = {"b.raw": "b" * 64, "a.npz": "a" * 64}
    right = {"a.npz": "a" * 64, "b.raw": "b" * 64}
    assert host.remote_inventory_sha256(left) == host.remote_inventory_sha256(right)


def test_w4_host_failure_evidence_is_fail_closed_and_append_only(tmp_path):
    args = SimpleNamespace(
        criteria=DRAFT_PATH,
        download=tmp_path / "no_output",
        remote_inventory=None,
        terminal_log=None,
        kernel_id="ramhachi888/cfd-opt-sdf-w4-v17-sensitivity",
        kernel_version=1,
        dataset_version=1,
        terminal_status="KernelWorkerStatus.ERROR",
    )
    diagnostic = host.fail_closed_diagnostic(args, RuntimeError("fixture failure"))
    assert diagnostic["verdict"] == "FAIL_CLOSED"
    assert diagnostic["host_verification_passed"] is False
    assert diagnostic["all_T0_T10_passed"] is False
    assert diagnostic["fd05_execution_authorized"] is False
    evidence = tmp_path / "failed_w4.json"
    host.write_append_only_evidence(evidence, diagnostic)
    with pytest.raises(ValueError, match="append-only"):
        host.write_append_only_evidence(evidence, diagnostic)


def test_w4_dataset_inventory_uses_registered_filenames_not_logical_input_keys():
    criteria, *_ = fixture()
    expected = {
        "sdf_design_state.npz": "f" * 64,
        "canonical_v16_phi_f4_fortran.raw": "1" * 64,
    }

    assert runner.registered_dataset_files(criteria) == expected
    assert host.registered_dataset_files(criteria) == expected


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


def test_w4_stationarity_uses_exact_endpoint_weighted_half_windows_and_ten_gate():
    criteria, summaries, _, rows_by_case, gpu_rows, smoke = fixture()
    case = criteria["cases"][0]
    rows = rows_by_case["flow_16"]
    for row in rows:
        row["drag_solver"] = row["fx_solver"] = 2.0 + 0.02 * (row["t_u_l"] - 80.0)
        row["pressure_fx_solver"] = row["drag_solver"] * 0.8
        row["viscous_fx_solver"] = row["drag_solver"] * 0.2

    runner_metrics = runner.recompute_case_metrics(rows, case, criteria["measurement"])
    host_metrics = host.recompute_case_metrics(rows, case, criteria["measurement"])
    assert runner_metrics == host_metrics
    assert math.isclose(runner_metrics["stationarity_first_half_time_weighted_drag_solver"], 2.2)
    assert math.isclose(runner_metrics["stationarity_second_half_time_weighted_drag_solver"], 2.6)
    assert math.isclose(runner_metrics["stationarity_relative_half_window_drift_drag"], 1 / 6)

    summaries["flow_16"].update(runner_metrics)
    metrics = {case_id: runner.recompute_case_metrics(
        rows_by_case[case_id], next(c for c in criteria["cases"] if c["case_id"] == case_id),
        criteria["measurement"])
        for case_id in rows_by_case}
    gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows_by_case, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"], criteria["inputs"]["kernel_runner"]["sha256"],
        "4" * 64)
    assert gates["T10_stationarity"] is False
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "4" * 64,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
    }
    host_gates = host.recompute_gates(
        criteria, summaries, metrics, rows_by_case, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, fingerprint)
    assert host_gates["T10_stationarity"] is False
    assert gates == host_gates


def test_w4_stationarity_criteria_is_frozen_to_w3_precedent():
    criteria, *_ = fixture()
    runner.validate_case_contract(criteria)
    host.validate_case_contract(criteria)
    criteria["measurement"]["stationarity"]["relative_half_window_drift_max"] = 0.03
    for validate in (runner.validate_case_contract, host.validate_case_contract):
        with pytest.raises((RuntimeError, ValueError), match="stationarity"):
            validate(criteria)


def test_w4_job_structurally_retains_canonical_device_owner_for_all_cases():
    source = (ROOT / "scripts/waterlily_w4_v16_sensitivity_job.jl").read_text()
    assert "OwnedV16Run(owner, bodies, sim)" in source
    assert "GC.@preserve owned begin" in source
    assert "GC.@preserve device_owner begin" in source


def test_w4_job_materializes_registered_case_inventory_before_comparison():
    source = (ROOT / "scripts/waterlily_w4_v16_sensitivity_job.jl").read_text()
    assert "Tuple(case.case_id for case in cases) == EXPECTED_CASE_IDS" in source
    assert "validate_w4_case(case; canonical_design_origin_m=CANONICAL_ORIGIN_M" in source
    assert "validate_v16_w4_case(case)" not in source


def test_w4_force_metrics_expose_all_physical_pressure_viscous_splits():
    criteria, _, metrics, _, _, _ = fixture()
    for case in criteria["cases"]:
        values = metrics[case["case_id"]]
        assert math.isclose(values["pressure_drag_time_weighted_n"]
                            + values["viscous_drag_time_weighted_n"],
                            values["drag_time_weighted_n"], rel_tol=1e-12)
        assert math.isclose(values["pressure_downforce_time_weighted_n"]
                            + values["viscous_downforce_time_weighted_n"],
                            values["downforce_time_weighted_n"], rel_tol=1e-12)
    response = host.response_analysis(metrics)
    for quantity in (
        "drag_time_weighted_n", "downforce_time_weighted_n",
        "pressure_drag_time_weighted_n", "viscous_drag_time_weighted_n",
        "pressure_downforce_time_weighted_n", "viscous_downforce_time_weighted_n",
    ):
        assert set(response["force_component_deltas"][quantity]) == {
            "flow16_to_flow24", "flow24_to_flow32", "flow16_to_extended_domain16"}
        assert all("absolute_delta_n" in entry and "relative_delta_percent" in entry
                   for entry in response["force_component_deltas"][quantity].values())


def test_w4_reports_w3_flow16_delta_without_inventing_repeatability_bound():
    criteria, _, metrics, _, _, _ = fixture()
    w3_result = {"raw_measurements": {
        "drag_time_weighted_n": metrics["flow_16"]["drag_time_weighted_n"] * 0.9,
        "downforce_time_weighted_n": metrics["flow_16"]["downforce_time_weighted_n"] + 0.02,
        "cd_time_weighted": metrics["flow_16"]["cd_time_weighted"] - 0.03,
        "stationarity_relative_half_window_drift_drag": 0.001,
        "stationarity_relative_half_window_drift_downforce": 0.002,
        "steps": 4808,
        "t_end_reached": 120.0019,
    }}
    summary = {"steps": 4808, "t_end_reached": 120.0019}
    comparison = host.w3_flow16_comparison(w3_result, metrics["flow_16"], summary)
    assert comparison["numerical_repeatability_gate_registered"] is False
    assert comparison["force_sign_consistent"] is True
    assert comparison["force_sign"] == {"w3_round4": 1.0, "w4_flow_16": 1.0}
    assert math.isclose(comparison["drag_time_weighted_n"]["relative_delta"], 0.1 / 1.0)
    assert comparison["steps"] == {"w3_round4": 4808, "w4_flow_16": 4808}
    assert criteria["w3_flow16_comparison"]["numerical_repeatability_gate_registered"] is False


def test_w4_case_mapping_gate_rejects_grid_identity_drift():
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture()
    summaries["flow_24"]["flow_dims"] = [89, 48, 36]
    gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    assert gates["T3_case_mapping_and_reynolds"] is False


def test_w4_case_mapping_gate_checks_xyz_box_max_vector_in_runner_and_host():
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture()
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "4" * 64,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
    }

    runner_gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    host_gates = host.recompute_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, fingerprint,
    )
    assert runner_gates["T3_case_mapping_and_reynolds"] is True
    assert host_gates["T3_case_mapping_and_reynolds"] is True
    assert all(summary["physical_box_max_m"] == [axis[1] for axis in case["physical_box_m"]]
               for case in criteria["cases"]
               for summary in [summaries[case["case_id"]]])

    summaries["domain_xplus1m_16"]["physical_box_max_m"] = [3.5, 1.2]
    runner_gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    host_gates = host.recompute_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, fingerprint,
    )
    assert runner_gates["T3_case_mapping_and_reynolds"] is False
    assert host_gates["T3_case_mapping_and_reynolds"] is False
    assert runner_gates == host_gates


def test_w4_ground_descriptor_matches_registered_semantics_exactly():
    criteria, summaries, metrics, rows, gpu_rows, smoke = fixture()
    fingerprint = {
        "source_commit": criteria["source_commit"],
        "runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "criteria_sha256": "4" * 64,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
    }
    job = (ROOT / "scripts/waterlily_w4_v16_sensitivity_job.jl").read_text()
    expected = criteria["profile_semantics"]["ground_model"]
    assert f'ground_model="{expected}"' in job

    wrong = "moving planar half-space at world z=-0.9 m on the expanded flow-domain bottom, with +x wall velocity 1 m/s"
    for summary in summaries.values():
        summary["ground_model"] = wrong
    runner_gates = runner.evaluate_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, criteria["source_commit"],
        criteria["inputs"]["kernel_runner"]["sha256"], "4" * 64,
    )
    host_gates = host.recompute_gates(
        criteria, summaries, metrics, rows, criteria["geometry"]["phi_expected_margin_m"],
        gpu_rows, smoke, fingerprint,
    )
    assert runner_gates["T4_native_profile_limitation_preserved"] is False
    assert host_gates["T4_native_profile_limitation_preserved"] is False
    assert runner_gates == host_gates


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
    with pytest.raises(RuntimeError, match="canonical v17"):
        runner.zero_level_margin_m(np.zeros((2, 2, 2)), 0.025, "v17")


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


def test_verifier_functions_do_not_call_their_own_parameters():
    """Regression: `remote_inventory_sha256=` shadowed the module helper inside verify()."""
    import ast

    tree = ast.parse((Path(__file__).resolve().parents[1] / "scripts/verify_kaggle_w4_v16.py").read_text())
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        called = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert not params & called, (fn.name, params & called)
