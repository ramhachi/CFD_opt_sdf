"""Contract and gate checks for the registered W2b Kaggle ladder."""

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "kaggle_w2b_runner", ROOT / "infra/kaggle/kernel_w2b/runner.py"
)
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)
sys.path.insert(0, str(ROOT / "scripts"))
import verify_kaggle_w2b as verifier


def valid_summaries():
    summaries = {}
    for case in runner.W2B_CASES:
        case_id = case["case_id"]
        cells = case["cells_per_diameter"]
        mode = case["mode"]
        baseline = (runner.W2T4A_ANALYTIC_DRAG if mode == "analytic"
                    else runner.W2T4B_GRID_SDF_DRAG)
        drag = baseline * (cells / 16) ** 2
        summary = {
            **{key: list(value) if isinstance(value, tuple) else value
               for key, value in case.items()},
            "steps": 2242,
            "t_end_target": 60.0,
            "t_end_reached": 60.001,
            "finite_u": True,
            "finite_p": True,
            "finite_forces": True,
            "force_samples": 560,
            "window_mean_drag": drag,
            "window_mean_lift": 0.0,
            "first_half_mean_drag": drag,
            "second_half_mean_drag": drag,
            "time_weighted_cd": baseline / (0.5 * math.pi * 8**2),
            "phi_sha256": runner.CANONICAL_PHI_SHA256 if mode == "gridsdf" else "",
            "device_roundtrip_sha256": runner.CANONICAL_PHI_SHA256 if mode == "gridsdf" else "",
            "phi_margin_m": runner.PHI_MARGIN_EXPECTED_M if mode == "gridsdf" else None,
            "phi_margin_gate_m": runner.PHI_MARGIN_MIN_M if mode == "gridsdf" else None,
            "wall_seconds": 100.0,
            "ms_per_step": 1.0,
            "peak_vram_bytes": 100,
            "vram_total_bytes": 1000,
            "gpu_name": "Tesla T4",
            "julia_version": "1.12.6",
            "julia_threads": 1,
            "cuda_jl_version": "6.3.1",
            "waterlily_version": "1.8.0",
        }
        summaries[case_id] = summary
    return summaries


def test_runner_matches_registered_w2b_matrix_and_thresholds():
    criteria = json.loads(verifier.CRITERIA.read_text())
    round2 = json.loads(verifier.ROUND2_CRITERIA.read_text())
    round1 = json.loads(verifier.ROUND1_CRITERIA.read_text())
    runtime_diagnostic = json.loads(verifier.ROUND2_DIAGNOSTIC.read_text())
    fixture_cases = criteria["fixture"]["cases"]
    assert runner.CASE_IDS == [case["case_id"] for case in fixture_cases]
    assert runner.SOURCE_COMMIT == criteria["source_commit"]
    assert runner.CUDA_DRIVER_API_VERSION == criteria["backend"]["cuda_driver_api_version"]
    assert runner.CUDA_RUNTIME_VERSION == criteria["backend"]["cuda_runtime_version"]
    assert runner.SOURCE_REF == "refs/heads/codex/kaggle-batch-migration"
    assert runner.SOURCE_FETCH_DEPTH >= 4
    assert criteria["round"] == 3
    assert criteria["previous_round"]["criteria_sha256"] == verifier.sha256(verifier.ROUND2_CRITERIA)
    assert criteria["thresholds"] == round1["thresholds"] == round2["thresholds"]
    assert criteria["fixture"] == round1["fixture"] == round2["fixture"]
    assert criteria["inputs"] == round1["inputs"] == round2["inputs"]
    assert criteria["backend"]["cuda_runtime_version"] == runtime_diagnostic[
        "environment"]["cuda_runtime_version"]
    assert criteria["backend"]["cuda_driver_api_version"] == runtime_diagnostic[
        "environment"]["cuda_driver_api_version"]
    assert runner.CRITERIA_SHA256 == verifier.sha256(verifier.CRITERIA)
    assert runner.CANONICAL_PHI_SHA256 == criteria["inputs"]["canonical_phi_sha256"]

    thresholds = criteria["thresholds"]
    assert runner.STATIONARITY_TOL == thresholds["stationarity_relative_drift"]
    assert runner.LIFT_RATIO_TOL == thresholds["relative_lift_to_drag"]
    assert runner.T4_BASELINE_DRAG_TOL == thresholds["t4_baseline_relative_drag"]
    assert runner.GEOMETRY_CD_TOL == thresholds["analytic_gridsdf_time_weighted_relative_cd"]
    assert runner.FINEST_GRID_CD_TOL == thresholds["finest_two_grid_time_weighted_relative_cd"]
    assert runner.PHI_MARGIN_MIN_M == thresholds["phi_margin_min_m"]

    registered_inputs = {
        item["path"]: item["sha256"] for item in criteria["inputs"].values()
        if isinstance(item, dict) and "path" in item
    }
    assert runner.REGISTERED_INPUTS == registered_inputs


def test_w2b_gates_accept_valid_matrix_and_reject_registered_bound_drift():
    rows = [
        "0, Tesla T4, GPU-a, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-b, 15360 MiB, 580.159.04",
    ]
    smoke = ("GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_DRIVER_VERSION 13.3.0 "
             "CUDA_RUNTIME_VERSION 12.8.0")
    summaries = valid_summaries()
    finite_csv = {case_id: True for case_id in runner.CASE_IDS}
    assert all(runner.w2b_gates(summaries, finite_csv, rows, smoke).values())

    changed = copy.deepcopy(summaries)
    changed["gridsdf_32"]["phi_margin_m"] = 0.15
    assert not runner.w2b_gates(changed, finite_csv, rows, smoke)["T7_canonical_grid"]

    changed = copy.deepcopy(summaries)
    for case_id in ("analytic_24", "gridsdf_24"):
        changed[case_id]["time_weighted_cd"] *= 1.05
    assert not runner.w2b_gates(changed, finite_csv, rows, smoke)["T10_finest_grid_response"]
    assert runner.w2b_gates(changed, finite_csv, rows, smoke)["T9_geometry_interpolation_agreement"]

    changed = copy.deepcopy(summaries)
    changed["analytic_32"]["wall_seconds"] = 1801.0
    assert not runner.w2b_gates(changed, finite_csv, rows, smoke)["T11_runtime_vram"]

    changed = copy.deepcopy(summaries)
    changed["gridsdf_24"]["julia_threads"] = 2
    assert not runner.w2b_gates(changed, finite_csv, rows, smoke)["T12_backend_identity"]


def test_host_metric_recomputation_uses_force_csv_values():
    rows = [
        [1.0, 40.0, 10.0, 1.0, 0.0, 4.0, 6.0],
        [2.0, 45.0, 12.0, 2.0, 0.0, 5.0, 7.0],
        [3.0, 50.0, 14.0, 3.0, 0.0, 6.0, 8.0],
        [4.0, 60.0, 16.0, 4.0, 0.0, 7.0, 9.0],
    ]
    case = {"solver_radius": 8.0, "u_inf": 1.0}
    summary = {
        "window_mean_drag": 13.0,
        "window_mean_lift": 2.5,
        "window_mean_side": 0.0,
        "time_weighted_mean_drag": 13.5,
        "time_weighted_mean_lift": 2.75,
        "time_weighted_mean_side": 0.0,
        "first_half_mean_drag": 11.0,
        "second_half_mean_drag": 15.0,
        "cd": 13.0 / (0.5 * math.pi * 8**2),
        "time_weighted_cd": 13.5 / (0.5 * math.pi * 8**2),
        "final_force": [16.0, 4.0, 0.0, 7.0, 9.0],
    }
    verifier.verify_case_metrics("fixture", case, summary, rows)
    with pytest.raises(ValueError, match="does not match force CSV"):
        verifier.verify_case_metrics("fixture", case, {**summary, "window_mean_drag": 99.0}, rows)


def test_verifier_refuses_missing_done_marker(tmp_path):
    with pytest.raises(ValueError, match="completion marker"):
        verifier.verify(tmp_path)
