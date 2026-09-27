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
