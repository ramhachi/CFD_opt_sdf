from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfd_sdf.step01_contract import finite_step_response, validate_step_fraction


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
