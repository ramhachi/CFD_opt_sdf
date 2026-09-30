import ast
import builtins
import copy
import hashlib
import importlib.util
import json
import shutil
import symtable
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cfd_sdf.gradients.directional_fd import registered_run_order


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = load_module(
    "fd_runner",
    "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py",
)
verifier = load_module(
    "fd_host_verifier",
    "scripts/verify_kaggle_sdf_directional_fd_v16.py",
)
preparer = load_module(
    "fd_dataset_preparer",
    "scripts/prepare_kaggle_sdf_directional_fd_v16_dataset_2026_09.py",
)
registrar = load_module(
    "fd_criteria_registrar",
    "scripts/register_kaggle_sdf_directional_fd_v16_2026_09.py",
)
sys.path.insert(0, str(ROOT / "scripts"))
v17_registrar = load_module(
    "fd_v17_flow24_criteria_registrar",
    "scripts/register_kaggle_sdf_directional_fd_v17_flow24_2026_09.py",
)


def test_runner_and_registered_contract_share_exact_33_run_order():
    assert tuple(runner.EXPECTED_RUN_ORDER) == registered_run_order()
    assert tuple(verifier.EXPECTED_RUNS) == registered_run_order()
    assert len(runner.EXPECTED_RUN_ORDER) == 33


def test_exact_host_verified_w3_w4_prerequisites_bind_registered_backend_and_flow16():
    _, w3_result, _, w4_result, w3_criteria_sha, w3_result_sha, w4_criteria_sha, w4_result_sha = (
        registrar.load_prerequisites()
    )
    backend = w4_result["backend_identity"]["registered_backend"]
    observation = w4_result["backend_identity"]
    assert w3_criteria_sha == "eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb"
    assert w3_result_sha == "d00949d0ea2f2ddcd222f0f376449d9d7aba9b634a650cf75822c640b9e6f4a8"
    assert w4_criteria_sha == "3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f"
    assert w4_result_sha == "87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae"
    assert backend == w3_result["backend_identity"]
    assert observation["selected_gpu_uuid"] == "GPU-85734d21-bc25-4f5b-2d90-2b22393f3dc8"
    flow16 = w4_result["case_measurements"]["flow_16"]["force_metrics_host_recomputed"]
    assert flow16["drag_time_weighted_n"] == pytest.approx(0.3360177299176748)
    assert flow16["downforce_time_weighted_n"] == pytest.approx(0.3533732402215731)


def test_loaded_w4_result_survives_source_temporary_directory_cleanup():
    criteria = json.loads((ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json").read_text())
    with tempfile.TemporaryDirectory(prefix="fd_prerequisite_source_") as temporary:
        source = Path(temporary) / "source"
        for info in criteria["prerequisites"].values():
            for key in ("criteria_path", "result_path"):
                relative = Path(info[key])
                destination = source / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
        backend, w4_result = runner.verify_prerequisites(source, criteria)

    assert not source.exists()
    assert backend == criteria["prerequisites"]["w4"]["backend_identity"]
    flow16 = w4_result["case_measurements"]["flow_16"]["force_metrics_host_recomputed"]
    assert flow16["drag_time_weighted_n"] == pytest.approx(0.3360177299176748)
    assert flow16["downforce_time_weighted_n"] == pytest.approx(0.3533732402215731)


def test_round5_kernel_identity_keeps_the_unique_slug_and_input_dataset_separate():
    draft = json.loads((ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json").read_text())
    metadata = json.loads((ROOT / "infra/kaggle/kernel_sdf_directional_fd_v16/kernel-metadata.json").read_text())
    assert draft["criteria_round"] == 5
    assert draft["input_dataset_id"] == registrar.DATASET_ID
    assert metadata["dataset_sources"] == [registrar.DATASET_ID]
    assert metadata["id"] == draft["kernel_id"]
    assert metadata["id"] != registrar.DATASET_ID
    assert metadata["title"] == "CFD Opt SDF v16 Directional FD Oracle Kernel"
    assert metadata["is_private"] is True
    assert metadata["enable_gpu"] is True
    assert metadata["machine_shape"] == "NvidiaTeslaT4"


def test_round2_retry_binding_preserves_round1_and_rejects_contract_changes():
    binding = registrar.load_round1_submission_retry_binding()
    assert binding["criteria_file_sha256"] == registrar.ROUND1_CRITERIA_FILE_SHA256
    assert binding["submission_diagnostic_sha256"] == registrar.ROUND1_SUBMISSION_DIAGNOSTIC_SHA256
    round1 = json.loads((ROOT / registrar.ROUND1_CRITERIA).read_text())
    round2 = json.loads(json.dumps(round1))
    registrar.assert_same_measurement_contract(round2, round1)
    round2["perturbation"]["epsilon_ladder_m"][0] *= 2
    with pytest.raises(ValueError, match="changed the registered measurement contract"):
        registrar.assert_same_measurement_contract(round2, round1)


def test_round3_retry_binds_exact_round2_pre_solver_diagnostic():
    binding = registrar.load_round2_preflight_retry_binding()
    assert binding["criteria_file_sha256"] == registrar.ROUND2_CRITERIA_FILE_SHA256
    assert binding["criteria_canonical_sha256"] == registrar.ROUND2_CRITERIA_CANONICAL_SHA256
    assert binding["kernel1_diagnostic_sha256"] == registrar.ROUND2_KERNEL1_DIAGNOSTIC_SHA256
    assert binding["kernel_id"] == registrar.RETRY_KERNEL_ID
    assert binding["kernel_version"] == 1
    assert binding["solver_started"] is False
    assert binding["solver_step_invoked"] == []
    assert binding["solver_step_returned"] == []
    assert "before GPU, Julia, or solver measurement" in binding["reason"]


def test_round3_measurement_contract_equals_round2_and_rejects_threshold_changes():
    round2 = json.loads((ROOT / registrar.ROUND2_CRITERIA).read_text())
    round3 = json.loads(json.dumps(round2))
    round3.update({
        "criteria_round": 3,
        "source_commit": "a" * 40,
        "registered_source_commit": "a" * 40,
        "kernel_id": registrar.RETRY_KERNEL_ID,
    })
    registrar.assert_same_measurement_contract(round3, round2)
    round3["measurement"]["stationarity_relative_half_window_drift_max"] = 0.03
    with pytest.raises(ValueError, match="changed the registered measurement contract"):
        registrar.assert_same_measurement_contract(round3, round2)


def test_round4_retry_binds_exact_round3_pre_primal_queue_failure():
    binding = registrar.load_round3_pre_primal_retry_binding()
    assert binding["criteria_file_sha256"] == registrar.ROUND3_CRITERIA_FILE_SHA256
    assert binding["criteria_canonical_sha256"] == registrar.ROUND3_CRITERIA_CANONICAL_SHA256
    assert binding["kernel2_diagnostic_sha256"] == registrar.ROUND3_KERNEL2_DIAGNOSTIC_SHA256
    assert binding["failure_analysis_sha256"] == registrar.ROUND3_FAILURE_ANALYSIS_SHA256
    assert binding["kernel_id"] == registrar.RETRY_KERNEL_ID
    assert binding["kernel_version"] == 2
    assert binding["dataset_version"] == 3
    assert binding["solver_started"] is False
    assert binding["solver_step_invoked"] == []
    assert binding["solver_step_returned"] == []
    assert binding["copy_source"] == binding["copy_destination"]
    assert "before any primal step" in binding["reason"]


def test_round4_measurement_contract_equals_round3_and_rejects_any_gate_change():
    round3 = json.loads((ROOT / registrar.ROUND3_CRITERIA).read_text())
    round4 = json.loads(json.dumps(round3))
    round4.update({
        "criteria_round": 4,
        "source_commit": "b" * 40,
        "registered_source_commit": "b" * 40,
        "source_tree_commit": "b" * 40,
    })
    registrar.assert_same_measurement_contract(round4, round3)
    round4["noise_and_plateau"]["resolution_factor"] = 21.0
    with pytest.raises(ValueError, match="changed the registered measurement contract"):
        registrar.assert_same_measurement_contract(round4, round3)


def test_round5_retries_only_round4_runner_lifetime_failure_without_reusing_results():
    binding = registrar.load_round4_host_recompute_lifetime_failure_binding()
    assert binding["criteria_file_sha256"] == registrar.ROUND4_CRITERIA_FILE_SHA256
    assert binding["kernel3_submission_sha256"] == registrar.ROUND4_KERNEL3_SUBMISSION_SHA256
    assert binding["kernel3_diagnostic_sha256"] == registrar.ROUND4_KERNEL3_DIAGNOSTIC_SHA256
    assert binding["dataset_verification_sha256"] == registrar.ROUND4_DATASET_VERIFICATION_SHA256
    assert binding["kernel_version"] == 3
    assert binding["dataset_version"] == 4
    assert binding["completed_primal_count"] == 33
    assert len(binding["solver_step_invoked"]) == 33
    assert binding["solver_started"] is True
    assert binding["prior_outputs_reusable_as_fresh_primal_run"] is False
    assert binding["measurement_thresholds_changed"] is False

    round4 = json.loads((ROOT / registrar.ROUND4_CRITERIA).read_text())
    round5 = json.loads(json.dumps(round4))
    round5.update({
        "criteria_round": 5,
        "source_commit": "c" * 40,
        "registered_source_commit": "c" * 40,
        "source_tree_commit": "c" * 40,
    })
    registrar.assert_same_measurement_contract(round5, round4)
    round5["measurement"]["run_wall_time_limit_s"] = 1799.0
    with pytest.raises(ValueError, match="changed the registered measurement contract"):
        registrar.assert_same_measurement_contract(round5, round4)


def test_run_queue_input_is_outside_the_julia_output_snapshot_path():
    with tempfile.TemporaryDirectory(prefix="fd_queue_base_") as base_text, \
            tempfile.TemporaryDirectory(prefix="fd_queue_output_") as output_text, \
            tempfile.TemporaryDirectory(prefix="fd_queue_dataset_") as dataset_text:
        base = Path(base_text)
        output = Path(output_text)
        dataset = Path(dataset_text)
        (dataset / "canonical.raw").write_bytes(b"canonical")
        (dataset / "perturbed.raw").write_bytes(b"perturbed")
        criteria = {
            "run_order": ["baseline_A", "D0_eps_0p0010m__plus"],
            "inputs": {"canonical_phi_fortran_raw": {
                "path": "canonical.raw", "sha256": "a" * 64,
            }},
            "geometry": {"canonical_state_sha256": "b" * 64},
            "perturbation_inventory": [{
                "case_id": "D0_eps_0p0010m__plus",
                "dataset_path": "perturbed.raw",
                "phi_file_sha256": "c" * 64,
                "state_sha256": "d" * 64,
                "direction_id": "D0",
                "epsilon_m": 0.001,
                "sign": 1,
            }],
        }

        queue_path = runner.write_run_queue(base, dataset, criteria)
        julia_output_snapshot = output / "run_queue.tsv"

        assert queue_path == base / "run_queue.tsv"
        assert queue_path != julia_output_snapshot
        assert queue_path.read_text().splitlines() == [
            f"baseline_A\t{dataset / 'canonical.raw'}\t{'a' * 64}\t{'b' * 64}\t\t0\t0",
            f"D0_eps_0p0010m__plus\t{dataset / 'perturbed.raw'}\t{'c' * 64}\t{'d' * 64}\tD0\t0.001\t1",
        ]


def test_runner_state_identity_payload_constructs_all_canonical_hashes_and_masks():
    state = SimpleNamespace(to_dict=lambda: {
        "state_sha256": "state", "point_shape": [61, 33, 25],
    })
    canonical_identity = {
        "canonical_phi_c_order_sha256": "c" * 64,
        "canonical_phi_fortran_sha256": "f" * 64,
        "canonical_margin_m": 0.35,
        "mask_sha256": {
            "design_mask": "1" * 64,
            "fixed_solid_mask": "2" * 64,
            "forbidden_mask": "3" * 64,
            "root_mask": "4" * 64,
        },
    }
    direction_audit = {"direction_sha256": {"D0": "5" * 64}}
    perturbation_preflight = [{"case_id": "D0_eps_0p0005m__plus", "zero_level_margin_m": 0.3}]

    payload = runner.build_state_identity_payload(
        state, "6" * 64, canonical_identity, direction_audit, perturbation_preflight,
    )

    assert payload["canonical_phi_c_order_sha256"] == "c" * 64
    assert payload["canonical_phi_fortran_sha256"] == "f" * 64
    assert payload["canonical_margin_m"] == pytest.approx(0.35)
    assert payload["mask_sha256"] == canonical_identity["mask_sha256"]
    assert set(payload["mask_sha256"]) == {
        "design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask",
    }
    assert payload["direction_audit"] == direction_audit
    assert payload["perturbation_preflight"] == perturbation_preflight
    json.dumps(payload, allow_nan=False)


def test_run_main_completes_host_input_identity_before_gpu_inventory():
    source = (ROOT / "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py").read_text()
    tree = ast.parse(source)
    run_main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "run_main")
    calls = [node for node in ast.walk(run_main)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    preflight = next(node for node in calls if node.func.id == "host_input_preflight")
    gpu = next(node for node in calls if node.func.id == "gpu_inventory")
    assert preflight.lineno < gpu.lineno
    assert "state_info) = host_input_preflight" in source
    assert "write_json(OUT / \"input_state_and_direction_identity.json\", state_info)" in source
    assert "mask_hashes" not in {
        node.id for node in ast.walk(run_main)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def test_runner_has_no_unbound_global_references_in_function_scopes():
    runner_path = ROOT / "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py"
    table = symtable.symtable(runner_path.read_text(), str(runner_path), "exec")
    module_names = set(table.get_identifiers())
    runtime_supplied = {"__file__"}
    unresolved = []

    def visit(scope):
        if scope is not table:
            for symbol in scope.get_symbols():
                name = symbol.get_name()
                if (symbol.is_referenced() and symbol.is_global()
                        and name not in module_names
                        and name not in dir(builtins)
                        and name not in runtime_supplied):
                    unresolved.append((scope.get_name(), name))
        for child in scope.get_children():
            visit(child)

    visit(table)
    assert unresolved == []


def test_host_evaluate_does_not_shadow_runner_metric_comparator():
    verifier_path = ROOT / "scripts/verify_kaggle_sdf_directional_fd_v16.py"
    tree = ast.parse(verifier_path.read_text())
    evaluate = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "evaluate")
    assigned_names = {node.id for node in ast.walk(evaluate)
                      if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    assert "runner_metrics_match" not in assigned_names


def test_runner_and_host_use_independent_but_matching_centered_fd_arithmetic():
    baseline = 0.336
    noise = 1e-8
    slopes = (2.0, 2.02, 1.98, 2.0, 2.01)
    pairs = [
        {
            "epsilon_m": epsilon,
            "plus_response": baseline + epsilon * slope,
            "minus_response": baseline - epsilon * slope,
        }
        for epsilon, slope in zip(runner.EXPECTED_EPSILONS, slopes)
    ]
    runner_result = runner.classify_response(
        pairs, baseline_median=baseline, noise_floor=noise
    )
    host_result = verifier.host_classify_pairs(
        [{"epsilon_m": p["epsilon_m"], "plus_response_n": p["plus_response"],
          "minus_response_n": p["minus_response"]} for p in pairs],
        baseline,
        noise,
    )
    assert runner_result["plateau_pass"] is True
    assert host_result["plateau_pass"] is True
    assert runner_result["resolved_epsilon_m"] == host_result["resolved_epsilon_m"]
    assert runner_result["plateau_epsilon_m"] == host_result["plateau_epsilon_m"]
    assert runner_result["reference_derivative_n_per_m"] == pytest.approx(
        host_result["reference_derivative_n_per_m"]
    )
    assert runner_result["plateau_relative_deviations"] == pytest.approx(
        host_result["plateau_relative_deviations"]
    )


def test_unresolved_classifier_outputs_are_json_safe_and_fail_closed():
    baseline = 0.336
    pairs = [{
        "epsilon_m": epsilon,
        "plus_response": baseline,
        "minus_response": baseline,
    } for epsilon in runner.EXPECTED_EPSILONS]
    runner_result = runner.classify_response(
        pairs, baseline_median=baseline, noise_floor=1e-8
    )
    host_result = verifier.host_classify_pairs(
        [{"epsilon_m": p["epsilon_m"], "plus_response_n": p["plus_response"],
          "minus_response_n": p["minus_response"]} for p in pairs],
        baseline,
        1e-8,
    )
    for result in (runner_result, host_result):
        assert result["resolved_count"] == 0
        assert result["plateau_pass"] is False
        assert result["reference_derivative_n_per_m"] is None
        assert result["directional_noise_equivalent_n_per_m"] is None
        assert result["plateau_max_relative_deviation"] is None
        json.dumps(result, allow_nan=False)


def test_runner_and_host_exact_window_endpoint_interpolation_match():
    rows = []
    for index, time_value in enumerate(range(79, 122, 2)):
        fx = 2.0 + 0.01 * time_value
        fy = -0.5 + 0.002 * time_value
        fz = -4.0 + 0.03 * time_value
        pressure = (0.8 * fx, 0.8 * fy, 0.8 * fz)
        viscous = (0.2 * fx, 0.2 * fy, 0.2 * fz)
        rows.append({
            "step": float(index * 8),
            "t_u_l": float(time_value),
            "fx_solver": fx,
            "fy_solver": fy,
            "fz_solver": fz,
            "drag_solver": fx,
            "downforce_solver": -fz,
            "pressure_fx_solver": pressure[0],
            "pressure_fy_solver": pressure[1],
            "pressure_fz_solver": pressure[2],
            "viscous_fx_solver": viscous[0],
            "viscous_fy_solver": viscous[1],
            "viscous_fz_solver": viscous[2],
        })
    criteria = json.loads((ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json").read_text())
    runner.force_rows_contract(rows, criteria["measurement"])
    assert runner.force_components_close(rows, criteria["measurement"])
    runner_metrics = runner.recompute_metrics(rows, criteria)
    host_metrics = verifier.recompute_run_metrics(rows, criteria)
    assert runner_metrics.keys() == host_metrics.keys()
    assert set(verifier.REQUIRED_WINDOW_COMPONENT_METRICS) <= host_metrics.keys()
    for key, value in host_metrics.items():
        assert runner_metrics[key] == pytest.approx(value, rel=1e-14, abs=1e-14)
    assert verifier.runner_metrics_match(host_metrics, host_metrics, 1e-14)
    assert host_metrics["window_time_weighted_fx_solver"] == pytest.approx(3.0)
    assert host_metrics["window_time_weighted_drag_solver"] == pytest.approx(3.0)
    assert host_metrics["window_time_weighted_downforce_solver"] == pytest.approx(1.0)


def test_host_runner_metric_integrity_requires_all_pressure_viscous_window_integrals():
    metrics = {key: float(index + 1)
               for index, key in enumerate(verifier.REQUIRED_WINDOW_COMPONENT_METRICS)}
    summary = dict(metrics)
    assert verifier.runner_metrics_match(summary, metrics, 1e-12)

    for key in verifier.REQUIRED_WINDOW_COMPONENT_METRICS:
        missing_summary = dict(summary)
        del missing_summary[key]
        assert not verifier.runner_metrics_match(missing_summary, metrics, 1e-12)

        missing_metrics = dict(metrics)
        del missing_metrics[key]
        assert not verifier.runner_metrics_match(summary, missing_metrics, 1e-12)

        changed_summary = dict(summary)
        changed_summary[key] += 1.0
        assert not verifier.runner_metrics_match(changed_summary, metrics, 1e-12)


def test_minimum_force_window_samples_and_full_flow_physics_identity_are_hard_gates():
    criteria = json.loads((ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json").read_text())
    flow = criteria["geometry"]["flow_case"]
    summary = {
        "run_id": "baseline_A",
        "phi_margin_m": criteria["geometry"]["canonical_phi_margin_m"],
        "phi_margin_gate_m": criteria["geometry"]["margin_gate_m"],
        "point_shape": criteria["geometry"]["point_shape"],
        "canonical_sdf_origin_m": criteria["geometry"]["canonical_sdf_origin_m"],
        "flow_origin_m": flow["flow_origin_m"],
        "flow_dims": flow["flow_dims"],
        "flow_spacing_m": flow["flow_spacing_m"],
        "solver_length": flow["solver_length"],
        "solver_viscosity": flow["solver_viscosity"],
        "solver_velocity": flow["solver_velocity"],
        "solver_time_unit_s": flow["solver_time_unit_s"],
        "reynolds": flow["reynolds"],
        "density_kg_m3": flow["density_kg_m3"],
        "dynamic_viscosity_pa_s": flow["dynamic_viscosity_pa_s"],
        "freestream_mps": flow["freestream_mps"],
        "reference_length_m": flow["reference_length_m"],
        "reference_area_m2": flow["reference_area_m2"],
        "canonical_design_spacing_m": criteria["geometry"]["design_spacing_m"],
        "candidate_body_mapping": flow["candidate_body_mapping"],
        "sdf_outside_value_m": criteria["geometry"]["outside_value_m"],
        "moving_ground_solver_plane": flow["moving_ground_solver_plane"],
        "moving_ground_world_plane_m": flow["moving_ground_world_plane_m"],
        "moving_ground_velocity_mps": flow["moving_ground_velocity_mps"],
        "force_window_t_u_l": criteria["measurement"]["force_window_t_u_l"],
        "stationarity_half_windows_t_u_l": criteria["measurement"]["stationarity_half_windows_t_u_l"],
        "sample_every_solver_steps": criteria["measurement"]["force_sample_every_solver_steps"],
        "physical_box_m": flow["physical_box_m"],
        "native_velocity_boundary": flow["native_velocity_boundary"],
        "side_top_tangential_boundary": flow["side_top_tangential_boundary"],
        "x_plus_boundary": flow["x_plus_boundary"],
        "pressure_boundary": flow["pressure_boundary"],
        "ground_model": flow["ground_model"],
        "force_integration_body": flow["force_integration_body"],
        "force_projection_semantics": flow["force_projection_semantics"],
        "source_profile_equivalent": flow["source_profile_equivalent"],
        "physical_profile_qualified": flow["physical_profile_qualified"],
    }
    assert runner.run_summary_contract(summary, criteria) is True
    assert verifier.host_physics_identity(summary, criteria) is True
    summary["phi_margin_m"] += 5e-7
    assert runner.run_summary_contract(summary, criteria) is True
    assert verifier.host_physics_identity(summary, criteria) is True
    summary["phi_margin_m"] += 2e-6
    assert runner.run_summary_contract(summary, criteria) is False
    assert verifier.host_physics_identity(summary, criteria) is False
    summary["phi_margin_m"] = criteria["geometry"]["canonical_phi_margin_m"]
    summary["flow_origin_m"] = summary["canonical_sdf_origin_m"]
    assert runner.run_summary_contract(summary, criteria) is False
    assert verifier.host_physics_identity(summary, criteria) is False

    rows = []
    for step, time_value in zip((0, 8, 16, 24), (79.0, 81.0, 119.0, 121.0)):
        fx, fy, fz = 3.0, -0.3, -1.0
        rows.append({
            "step": float(step), "t_u_l": time_value,
            "fx_solver": fx, "fy_solver": fy, "fz_solver": fz,
            "drag_solver": fx, "downforce_solver": -fz,
            "pressure_fx_solver": 0.8 * fx, "pressure_fy_solver": 0.8 * fy,
            "pressure_fz_solver": 0.8 * fz, "viscous_fx_solver": 0.2 * fx,
            "viscous_fy_solver": 0.2 * fy, "viscous_fz_solver": 0.2 * fz,
        })
    with pytest.raises(RuntimeError, match="too few raw samples"):
        runner.force_rows_contract(rows, criteria["measurement"])
    with pytest.raises(ValueError, match="too few raw samples"):
        verifier.validate_sample_stride(rows, criteria)


def test_host_runner_manifest_requires_exact_payload_inventory(tmp_path):
    output = tmp_path / "fd_output"
    output.mkdir()
    (output / "artifact.txt").write_text("fixed\n")
    manifest = {"artifact.txt": hashlib.sha256(b"fixed\n").hexdigest()}
    (output / "sha256.json").write_text(json.dumps(manifest))
    (output / "DONE").write_text("complete\n")
    hashes, manifest_sha = verifier.verify_output_files(output)
    assert hashes == manifest
    assert manifest_sha == hashlib.sha256((output / "sha256.json").read_bytes()).hexdigest()
    (output / "unexpected.txt").write_text("extra\n")
    with pytest.raises(ValueError, match="inventory"):
        verifier.verify_output_files(output)


def test_host_runtime_verifier_binds_the_registered_julia_archive_sha(tmp_path):
    backend = {
        "gpu_count": 2,
        "gpu_name": "Tesla T4",
        "driver_version": "580.159.04",
        "compute_capability": "7.5",
        "cuda_driver_api_version": "13.3.0",
        "cuda_runtime_version": "12.8.0",
        "cuda_jl_version": "6.3.1",
        "julia_version": "1.12.6",
        "julia_threads": 1,
        "waterlily_version": "1.8.0",
        "waterlily_backend": "KernelAbstractions.CUDABackend()",
        "cuda_visible_devices": "0",
        "julia_archive_sha256": "a" * 64,
    }
    criteria = {
        "backend": backend,
        "source_commit": "b" * 40,
        "input_dataset_id": "ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle",
        "inputs": {"kernel_runner": {"sha256": "c" * 64}},
    }
    output = tmp_path
    (output / "nvidia_smi.csv").write_text(
        "0, Tesla T4, GPU-0, 580.159.04\n1, Tesla T4, GPU-1, 580.159.04\n"
    )
    (output / "input_criteria.json").write_text("registered criteria\n")
    (output / "input_dataset_manifest.json").write_text("registered manifest\n")
    (output / "julia_smoke.log").write_text(
        "W0B_SMOKE_DONE\nCUDA_FUNCTIONAL true\nGPU_COMPUTE_CAPABILITY 7.5\n"
        "CUDA_DRIVER_VERSION 13.3.0\nCUDA_RUNTIME_VERSION 12.8.0\n"
        "JULIA_VERSION 1.12.6\nCUDA_JL_VERSION 6.3.1\n"
        "WATERLILY_VERSION 1.8.0\nGPU_NAME Tesla T4\nNO_SOLVER_STEP\n"
    )
    gpu_rows = ["0, Tesla T4, GPU-0, 580.159.04", "1, Tesla T4, GPU-1, 580.159.04"]
    fingerprint = {
        "criteria_sha256": hashlib.sha256((output / "input_criteria.json").read_bytes()).hexdigest(),
        "source_commit": criteria["source_commit"],
        "kernel_runner_sha256": criteria["inputs"]["kernel_runner"]["sha256"],
        "dataset_id": criteria["input_dataset_id"],
        "dataset_manifest_sha256": hashlib.sha256(
            (output / "input_dataset_manifest.json").read_bytes()
        ).hexdigest(),
        "julia_archive_sha256": backend["julia_archive_sha256"],
        "gpu_inventory": gpu_rows,
        "backend_expected": backend,
        "selected_gpu_uuid": "GPU-0",
    }
    (output / "runtime_fingerprint.json").write_text(json.dumps(fingerprint))
    verifier.verify_runtime(criteria, output, {})

    fingerprint["julia_archive_sha256"] = "d" * 64
    (output / "runtime_fingerprint.json").write_text(json.dumps(fingerprint))
    with pytest.raises(ValueError, match="runtime fingerprint source/backend identity"):
        verifier.verify_runtime(criteria, output, {})


def test_failed_run_diagnostic_is_append_only_and_keeps_qualification_false(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "execution_state.json").write_text(json.dumps({
        "stage": "julia_job", "solver_step_invoked": ["baseline_A"],
        "solver_step_returned": [], "solver_started": True,
    }))
    (output / "fd_v16.log").write_text(
        "FD_RUN_STARTED baseline_A\nFD_SOLVER_STEP_INVOKED baseline_A\n"
    )
    (output / "ERROR.txt").write_text("synthetic fixture failure\n")
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in output.iterdir()}
    (output / "sha256.json").write_text(json.dumps(files, sort_keys=True))
    status = tmp_path / "status.txt"
    status.write_text("KernelWorkerStatus.ERROR\n")
    log = tmp_path / "kaggle.log"
    log.write_text("exact version log\n")
    verification = tmp_path / "host.json"
    diagnostic = tmp_path / "fd-diagnostic.json"
    args = Namespace(
        criteria=ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json",
        output=output,
        status_file=status,
        kaggle_log_file=log,
        verification_output=verification,
        diagnostic_path=diagnostic,
        kernel_id="ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel",
        kernel_version=1,
        dataset_version=1,
    )
    path, digest = verifier.write_diagnostic(args, RuntimeError("exact test failure"))
    result = json.loads(path.read_text())
    assert result["host_verification_passed"] is False
    assert result["runner_execution_state"]["solver_started"] is True
    assert result["julia_progress_markers"]["solver_step_invoked"] == ["baseline_A"]
    assert result["output_manifest_consistent"] is True
    assert result["sdf_directional_fd_oracle_qualified"] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert path.with_suffix(path.suffix + ".sha256").read_text().strip() == digest
    with pytest.raises(FileExistsError, match="append-only"):
        verifier.write_diagnostic(args, RuntimeError("retry cannot overwrite"))


def test_dataset_preparer_rejects_mutable_draft_even_with_valid_sidecar(tmp_path):
    source = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json"
    criteria = tmp_path / "criteria.json"
    criteria.write_bytes(source.read_bytes())
    digest = hashlib.sha256(criteria.read_bytes()).hexdigest()
    criteria.with_suffix(criteria.suffix + ".sha256").write_text(digest + "\n")
    with pytest.raises(ValueError, match="immutable premeasurement"):
        preparer.stage(Path("unused-state.npz"), criteria, tmp_path / "dataset")


def test_v17_runner_discovers_criteria_filename_before_loading_criteria(tmp_path):
    original = (runner.STAGE, runner.OUT, runner.CRITERIA_NAME, runner.MANIFEST_NAME,
                runner.EXPECTED_DIRECTIONS, runner.EXPECTED_EPSILONS, runner.EXPECTED_RUN_ORDER)
    verifier_original = (verifier.OUTPUT_NAME, verifier.CRITERIA_NAME,
                         verifier.DATASET_MANIFEST_NAME, verifier.EXPECTED_RUNS,
                         verifier.DIRECTIONS, verifier.EPSILONS)
    try:
        directory = tmp_path / "dataset"
        directory.mkdir()
        criteria = {
            "immutable": True,
            "registered_before_computation": True,
            "status": "registered_not_run",
            "source_commit": "a" * 40,
            "registered_source_commit": "a" * 40,
            "formal_measurement_started": False,
            "kind": "sdf_directional_fd_flow24_criteria",
            "input_dataset_id": "ramhachi888/cfd-opt-sdf-v17-flow24-directional-fd-oracle",
            "artifacts": {
                "dataset_criteria_filename": "sdf_directional_fd_v17_flow24_criteria.json",
                "dataset_manifest_filename": "sdf_directional_fd_v17_flow24_dataset_manifest.json",
                "kernel_output_directory": "sdf_directional_fd_v17_flow24",
            },
            "direction_inventory": {
                name: {} for name in (
                    "D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026",
                )
            },
            "perturbation_inventory": [{"epsilon_m": value} for value in (
                0.0005, 0.001, 0.0025, 0.005, 0.01,
            ) for _ in range(6)],
            "run_order": ["baseline_A"],
        }
        criteria["criteria_sha256"] = runner.criteria_digest(criteria)
        path = directory / criteria["artifacts"]["dataset_criteria_filename"]
        path.write_text(json.dumps(criteria))
        path.with_suffix(path.suffix + ".sha256").write_text(
            hashlib.sha256(path.read_bytes()).hexdigest() + "\n")

        loaded, digest = runner.read_criteria(directory)

        assert loaded["kind"] == "sdf_directional_fd_flow24_criteria"
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
        assert runner.CRITERIA_NAME == "sdf_directional_fd_v17_flow24_criteria.json"
        assert runner.MANIFEST_NAME == "sdf_directional_fd_v17_flow24_dataset_manifest.json"
        assert runner.STAGE == "sdf_directional_fd_v17_flow24"
        assert preparer.artifact_names(loaded) == (
            "sdf_directional_fd_v17_flow24_criteria.json",
            "sdf_directional_fd_v17_flow24_dataset_manifest.json",
        )
        verifier.configure_criteria(loaded)
        assert verifier.CRITERIA_NAME == runner.CRITERIA_NAME
        assert verifier.DATASET_MANIFEST_NAME == runner.MANIFEST_NAME
        assert verifier.OUTPUT_NAME == runner.STAGE
    finally:
        (runner.STAGE, runner.OUT, runner.CRITERIA_NAME, runner.MANIFEST_NAME,
         runner.EXPECTED_DIRECTIONS, runner.EXPECTED_EPSILONS,
         runner.EXPECTED_RUN_ORDER) = original
        (verifier.OUTPUT_NAME, verifier.CRITERIA_NAME, verifier.DATASET_MANIFEST_NAME,
         verifier.EXPECTED_RUNS, verifier.DIRECTIONS, verifier.EPSILONS) = verifier_original


def test_v17_flow24_registration_preserves_fixed_r5_contract_and_rejects_threshold_change():
    r5_path = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json"
    r5 = json.loads(r5_path.read_text())
    criteria = copy.deepcopy(r5)
    criteria["gates"][0] = "T0_exact_W3_v17_W4_v17_flow24_prerequisites"
    criteria["perturbation"]["epsilon_relative_to_design_spacing"] = [0.02, 0.04, 0.1, 0.2, 0.4]
    criteria["perturbation_inventory"] = list(range(30))
    v17_registrar.assert_r5_unchanged(criteria, r5)

    criteria["noise_and_plateau"]["plateau_relative_tolerance"] += 0.01
    with pytest.raises(ValueError, match="R5-fixed contract block: noise_and_plateau"):
        v17_registrar.assert_r5_unchanged(criteria, r5)


def test_v17_flow24_job_environment_uses_registered_state_flow_directions_and_ladder():
    draft = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json"
    criteria = copy.deepcopy(json.loads(draft.read_text()))
    criteria["geometry"].update({
        "state_label": "v17",
        "canonical_state_sha256": "1" * 64,
        "canonical_phi_c_order_sha256": "2" * 64,
        "canonical_phi_fortran_sha256": "3" * 64,
        "source_surface_sha256": "4" * 64,
        "point_shape": [121, 65, 49],
        "canonical_sdf_origin_m": [-1.0, -0.8, -0.6],
        "design_spacing_m": 0.025,
        "canonical_phi_margin_m": 0.35,
        "margin_gate_m": 0.15,
    })
    criteria["geometry"]["flow_case"].update({
        "case_id": "flow_24", "flow_dims": [150, 72, 54],
        "flow_spacing_m": 1 / 30, "solver_length": 24.0,
        "solver_viscosity": 0.3, "solver_time_unit_s": 1 / 30,
    })
    criteria["direction_inventory"] = {
        name: {} for name in (
            "D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026",
        )
    }
    criteria["perturbation_inventory"] = [{"epsilon_m": value} for value in (
        0.0005, 0.001, 0.0025, 0.005, 0.01,
    ) for _ in range(6)]
    environment = runner.julia_job_environment(criteria)

    assert environment["FD_STATE_LABEL"] == "v17"
    assert environment["FD_POINT_SHAPE"] == "121,65,49"
    assert environment["FD_SDF_SPACING_M"] == "0.025"
    assert environment["FD_FLOW_CASE_ID"] == "flow_24"
    assert environment["FD_FLOW_DIMS"] == "150,72,54"
    assert environment["FD_FLOW_ORIGIN_M"] == "-2.5,-1.2,-0.9"
    assert environment["FD_SOLVER_LENGTH"] == "24.0"
    assert environment["FD_SOLVER_VISCOSITY"] == "0.3"
    assert environment["FD_DIRECTION_IDS"] == ",".join(criteria["direction_inventory"])
    assert environment["FD_EPSILONS_M"] == "0.0005,0.001,0.0025,0.005,0.01"


def test_v17_flow24_run_summary_must_bind_state_label_hashes_and_flow_case():
    criteria = copy.deepcopy(json.loads(
        (ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json").read_text()))
    geometry = criteria["geometry"]
    geometry.update({
        "state_label": "v17", "canonical_state_sha256": "1" * 64,
        "source_surface_sha256": "2" * 64, "point_shape": [121, 65, 49],
        "canonical_sdf_origin_m": [-1.0, -0.8, -0.6], "design_spacing_m": 0.025,
        "canonical_phi_margin_m": 0.35,
    })
    flow = geometry["flow_case"]
    flow.update({"case_id": "flow_24", "flow_dims": [150, 72, 54],
        "flow_spacing_m": 1 / 30, "solver_length": 24.0,
        "solver_time_unit_s": 1 / 30, "solver_viscosity": 0.3})
    summary = {
        "run_id": "baseline_A", "canonical_state_label": "v17",
        "canonical_state_sha256": geometry["canonical_state_sha256"],
        "canonical_source_surface_sha256": geometry["source_surface_sha256"],
        "phi_margin_m": geometry["canonical_phi_margin_m"],
        "phi_margin_gate_m": geometry["margin_gate_m"],
        "point_shape": geometry["point_shape"],
        "canonical_sdf_origin_m": geometry["canonical_sdf_origin_m"],
        "flow_origin_m": flow["flow_origin_m"], "flow_dims": flow["flow_dims"],
        "flow_spacing_m": flow["flow_spacing_m"], "solver_length": flow["solver_length"],
        "solver_viscosity": flow["solver_viscosity"], "solver_velocity": flow["solver_velocity"],
        "solver_time_unit_s": flow["solver_time_unit_s"], "reynolds": flow["reynolds"],
        "density_kg_m3": flow["density_kg_m3"],
        "dynamic_viscosity_pa_s": flow["dynamic_viscosity_pa_s"],
        "freestream_mps": flow["freestream_mps"],
        "reference_length_m": flow["reference_length_m"],
        "reference_area_m2": flow["reference_area_m2"],
        "canonical_design_spacing_m": geometry["design_spacing_m"],
        "candidate_body_mapping": flow["candidate_body_mapping"],
        "sdf_outside_value_m": geometry["outside_value_m"],
        "moving_ground_solver_plane": flow["moving_ground_solver_plane"],
        "moving_ground_world_plane_m": flow["moving_ground_world_plane_m"],
        "moving_ground_velocity_mps": flow["moving_ground_velocity_mps"],
        "force_window_t_u_l": criteria["measurement"]["force_window_t_u_l"],
        "stationarity_half_windows_t_u_l": criteria["measurement"]["stationarity_half_windows_t_u_l"],
        "sample_every_solver_steps": criteria["measurement"]["force_sample_every_solver_steps"],
        "physical_box_m": flow["physical_box_m"],
        "native_velocity_boundary": flow["native_velocity_boundary"],
        "side_top_tangential_boundary": flow["side_top_tangential_boundary"],
        "x_plus_boundary": flow["x_plus_boundary"],
        "pressure_boundary": flow["pressure_boundary"], "ground_model": flow["ground_model"],
        "force_integration_body": flow["force_integration_body"],
        "force_projection_semantics": flow["force_projection_semantics"],
        "source_profile_equivalent": flow["source_profile_equivalent"],
        "physical_profile_qualified": flow["physical_profile_qualified"],
    }
    assert runner.run_summary_contract(summary, criteria) is True
    assert verifier.host_physics_identity(summary, criteria) is True

    summary["canonical_state_sha256"] = "3" * 64
    assert runner.run_summary_contract(summary, criteria) is False
    assert verifier.host_physics_identity(summary, criteria) is False


def test_registered_v17_kernel_runner_is_the_shared_criteria_runner():
    kernel_directory = ROOT / "infra/kaggle/kernel_sdf_directional_fd_v17_flow24"
    metadata = json.loads((kernel_directory / "kernel-metadata.json").read_text())
    shared_runner = ROOT / "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py"
    assert (kernel_directory / "runner.py").read_bytes() == shared_runner.read_bytes()
    assert metadata["id"] == "ramhachi888/cfd-opt-sdf-v17-flow24-directional-fd-oracle-kernel"
    assert metadata["dataset_sources"] == ["ramhachi888/cfd-opt-sdf-v17-flow24-directional-fd-oracle"]
