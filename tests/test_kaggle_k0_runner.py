"""Small local checks for the Kaggle orchestration gates."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kaggle_k0_runner", ROOT / "infra/kaggle/kernel/runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_kaggle_k0", ROOT / "scripts/verify_kaggle_k0.py")
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verifier)
sys.path.insert(0, str(ROOT / "scripts"))
import verify_kaggle_w1g
import verify_kaggle_w2t4b


def test_registered_params_and_analytic_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OUT", tmp_path)
    params = runner.write_params(ROOT).read_text()
    assert "flow_dims = (96, 64, 64)" in params
    assert "sample_every = 4" in params
    assert "t_end = 60.0" in params

    colab = json.loads((ROOT / "docs/evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json").read_text())
    summary = colab["runs"]["run"]
    reference = summary["window_mean_drag"]
    assert all(runner.assess_analytic(summary, reference, reference).values())
    changed = dict(summary, window_mean_drag=reference * 1.001)
    assert not runner.assess_analytic(changed, reference)["colab_agreement"]
    changed = dict(summary, finite_p=False)
    assert not runner.assess_analytic(changed, reference)["finite"]


def test_verifier_refuses_incomplete_download(tmp_path):
    with pytest.raises(ValueError, match="completion marker"):
        verifier.verify(tmp_path)
    with pytest.raises(ValueError, match="completion marker"):
        verify_kaggle_w1g.verify(tmp_path)
    with pytest.raises(ValueError, match="completion marker"):
        verify_kaggle_w2t4b.verify(tmp_path)


def test_w1g_gates_reject_geometry_and_identity_drift():
    rows = [
        "0, Tesla T4, GPU-a, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-b, 15360 MiB, 580.159.04",
    ]
    summary = {
        "mode": "gpu", "source_phi_sha256": runner.CANONICAL_PHI_SHA256,
        "device_roundtrip_sha256": runner.CANONICAL_PHI_SHA256,
        "probe_count": 200012, "bulk_box": 100000, "bulk_band": 100000,
        "representative_count": 12, "all_finite": True, "sign_violations": 0,
        "sign_gated_probes": 199321, "max_value_error_world_m": 3.6e-7,
        "max_normal_error": 3e-7, "normal_gated_probes": 199896,
        "outside_exact": True, "outside_probes": 6, "scalar_index_blocked": True,
        "backend_identity": {
            "gpu_name": "Tesla T4", "gpu_uuid": "GPU-a",
            "compute_capability": "7.5.0", "cuda_jl_version": "6.3.1",
            "waterlily_version": "1.8.0", "julia_version": "1.12.6",
            "cuda_runtime_version": "13.3.0",
        },
    }
    assert all(runner.w1g_gates(summary, rows, "").values())
    assert not runner.w1g_gates(dict(summary, all_finite=False), rows, "")["G3_finite"]
    assert not runner.w1g_gates(dict(summary, max_normal_error=0.002), rows, "")["G6_normal"]
    wrong = dict(summary, backend_identity=dict(summary["backend_identity"], gpu_uuid="GPU-b"))
    assert not runner.w1g_gates(wrong, rows, "")["G9_backend"]


def test_w2t4b_gates_reject_force_and_grid_drift():
    criteria_path = verify_kaggle_w2t4b.CRITERIA
    criteria = json.loads(criteria_path.read_text())
    round1 = json.loads((ROOT / "docs/evidence/kaggle_w2t4b_criteria_2026_09.json").read_text())
    assert criteria["previous_round"]["criteria_sha256"] == verifier.sha256(
        ROOT / "docs/evidence/kaggle_w2t4b_criteria_2026_09.json")
    assert criteria["thresholds"] == round1["thresholds"]
    assert runner.SOURCE_COMMIT == criteria["source_commit"]
    assert runner.W2T4B_CRITERIA_SHA256 == verifier.sha256(criteria_path)
    assert runner.W2A_CPU_SAMPLED_DRAG == criteria["reference_values"]["w2a_cpu_sampled"][
        "window_mean_drag"]
    assert runner.W2T4A_ANALYTIC_CD == criteria["reference_values"]["w2t4a_t4_analytic"]["cd"]
    assert runner.CPU_KAGGLE_SAMPLED_DRAG_TOL == criteria["thresholds"][
        "cpu_kaggle_sampled_relative_drag"]
    assert runner.SAMPLED_ANALYTIC_CD_TOL == criteria["thresholds"]["sampled_analytic_relative_cd"]
    assert runner.W2T4B_STATIONARITY_TOL == criteria["thresholds"]["stationarity_relative_drift"]
    assert runner.W2T4B_LIFT_RATIO_TOL == criteria["thresholds"]["relative_lift_to_drag"]
    assert runner.W2T4B_PHI_MARGIN_MIN_M == criteria["thresholds"]["phi_margin_min_m"]
    assert runner.W2T4B_PHI_MARGIN_GATE_M == criteria["fixture"]["canonical_phi"]["margin_gate_m"]
    assert runner.W2T4B_PHI_MARGIN_EXPECTED_M == criteria["thresholds"]["phi_margin_expected_m"]
    assert runner.W2T4B_PHI_MARGIN_TOL_M == criteria["thresholds"]["phi_margin_abs_tolerance_m"]
    assert runner.W2T4B_T_END == criteria["fixture"]["time"]["t_end_tu_d"]

    rows = [
        "0, Tesla T4, GPU-a, 15360 MiB, 580.159.04",
        "1, Tesla T4, GPU-b, 15360 MiB, 580.159.04",
    ]
    smoke = "GPU_COMPUTE_CAPABILITY 7.5.0 CUDA_RUNTIME_VERSION 13.3.0"
    summary = {
        "mode": "gridsdf", "steps": 2242, "t_end_reached": 60.001,
        "finite_u": True, "finite_p": True, "finite_forces": True,
        "force_samples": 560, "window_mean_drag": 88.2335,
        "first_half_mean_drag": 88.2335, "second_half_mean_drag": 88.2335,
        "cd": 0.8776, "window_mean_lift": 0.003,
        "phi_sha256": runner.CANONICAL_PHI_SHA256,
        "device_roundtrip_sha256": runner.CANONICAL_PHI_SHA256,
        "phi_margin_m": 0.19999998807907104,
        "phi_margin_gate_m": criteria["fixture"]["canonical_phi"]["margin_gate_m"],
        "wall_seconds": 28.0, "ms_per_step": 12.0,
        "peak_vram_bytes": 100, "vram_total_bytes": 1000,
        "gpu_name": "Tesla T4", "julia_version": "1.12.6",
        "cuda_jl_version": "6.3.1", "waterlily_version": "1.8.0",
    }
    assert all(runner.w2t4b_gates(summary, rows, smoke).values())
    changed = dict(summary, finite_forces=False)
    assert not runner.w2t4b_gates(changed, rows, smoke)["T3_force_finite"]
    changed = dict(summary, phi_sha256="0" * 64)
    assert not runner.w2t4b_gates(changed, rows, smoke)["T9_canonical_grid"]
    changed = dict(summary, phi_margin_gate_m=0.20)
    assert not runner.w2t4b_gates(changed, rows, smoke)["T9_canonical_grid"]
    changed = dict(summary, window_mean_drag=89.5)
    assert not runner.w2t4b_gates(changed, rows, smoke)["T6_cpu_kaggle_agreement"]
