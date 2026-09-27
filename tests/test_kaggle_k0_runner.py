"""Small local checks for the Kaggle orchestration gates."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kaggle_k0_runner", ROOT / "infra/kaggle/kernel/runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_kaggle_k0", ROOT / "scripts/verify_kaggle_k0.py")
verifier = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verifier)


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
    assert not runner.w1g_gates(dict(summary, max_normal_error=0.002), rows, "")["G6_normal"]
    wrong = dict(summary, backend_identity=dict(summary["backend_identity"], gpu_uuid="GPU-b"))
    assert not runner.w1g_gates(wrong, rows, "")["G9_backend"]
