from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfd_sdf.step01_contract import (
    finite_step_response,
    validate_step01_preflight,
    validate_step_fraction,
)


@pytest.mark.parametrize("step", [0.1, 0.25, 0.5])
def test_step01_accepts_registered_fraction_range(step: float):
    assert validate_step_fraction(step) == step


@pytest.mark.parametrize("step", [0.099, 0.501, float("nan")])
def test_step01_rejects_out_of_range_step_fraction(step: float):
    with pytest.raises(ValueError, match="step_fraction_h"):
        validate_step_fraction(step)


def test_step01_reports_force_change_and_finite_secant_in_n_units():
    result = finite_step_response(baseline_n=0.33, candidate_n=0.31, step_m=0.01)
    assert result["delta_response_n"] == pytest.approx(-0.02)
    assert result["finite_secant_n_per_m"] == pytest.approx(-2.0)
    assert result["oracle_type"] == "finite_step_response_secant"
    assert result["gradient_qualification"] is False
    negative_step = finite_step_response(baseline_n=0.33, candidate_n=0.35, step_m=-0.01)
    assert negative_step["finite_secant_n_per_m"] == pytest.approx(-2.0)


def test_step01_preflight_fails_closed_without_candidate_c_identity(tmp_path: Path):
    bindings = {
        "repository": tmp_path,
        "backend_identity": "Kaggle-T4",
        "flow_id": "flow_24",
        "window_tu_l": (80, 120),
        "canonical_state_sha256": "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb",
        "canonical_phi_fortran_f32_sha256": "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431",
        "direction_id": "caller-selected-direction",
        "step_fraction_h": 0.25,
        "sign": -1,
    }
    with pytest.raises(ValueError, match="frozen Candidate C identity"):
        validate_step01_preflight(**bindings)
    with pytest.raises(ValueError, match="Kaggle-T4"):
        validate_step01_preflight(**{**bindings, "backend_identity": "CPU"})


@pytest.mark.parametrize("step", [0.0024, 0.0126, float("nan")])
def test_step01_secant_rejects_out_of_scope_physical_displacement(step: float):
    with pytest.raises(ValueError, match=r"abs\(step_m\) must be"):
        finite_step_response(baseline_n=0.33, candidate_n=0.31, step_m=step)


def test_step01_secant_rejects_boolean_force_inputs():
    with pytest.raises(ValueError, match="not booleans"):
        finite_step_response(baseline_n=True, candidate_n=0.31, step_m=0.01)
