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


# ---- analysis quantities ---------------------------------------------------------------------------------------------------------------------------------
from cfd_sdf.step01_contract import (additivity_defect, agreement_radius, centered_secant, even_ratio, interpolate_signed_response, is_resolved, secant_drift_radius,
                                     sign_stability)


def test_centered_secant_cancels_the_even_part_and_even_ratio_isolates_it():
    r0, g, c, s = 0.3, -2.0, 7.0, 0.01                       # R(s) = r0 + g s + c s^2
    rp, rm = r0 + g * s + c * s**2, r0 - g * s + c * s**2
    assert centered_secant(rp, rm, s) == pytest.approx(g)
    assert even_ratio(rp, rm, r0) == pytest.approx(abs(2 * c * s**2) / abs(2 * g * s))
    assert even_ratio(1.0, 1.0, 1.0) != even_ratio(1.0, 1.0, 1.0)         # no odd part: nan
    with pytest.raises(ValueError):
        centered_secant(1.0, 0.0, 0.0)


def test_resolved_flags_use_ten_nominal_sigma():
    assert is_resolved(3.1e-5, -4e-5) and not is_resolved(3.1e-5, 2e-5) and not is_resolved(float("nan"))


def test_sign_stability_reports_constancy_reference_and_first_flip():
    assert sign_stability([-1, -2, -3], g_hat=-1.5)["constant_over_resolved_steps"] is True
    s = sign_stability([-1, -2, 0.5, -3], g_hat=-1.5)
    assert s["first_flip_index"] == 2 and s["constant_over_resolved_steps"] is False and s["same_sign_as_g_hat_over_resolved_steps"] is False
    s = sign_stability([0.1, -2, -3], g_hat=-1.0, resolved=[False, True, True])          # an unresolved step is neither the reference nor a flip
    assert s["reference_sign"] == -1 and s["constant_over_resolved_steps"] is True and s["unresolved_indices"] == [0]


def test_agreement_radius_is_contiguous_from_the_smallest_step_and_can_be_none():
    steps = [2.5, 5, 7.5, 10, 12.5]
    g = [-1.0, -1.1, -1.4, -0.9, -1.0]                       # -1.4 leaves 30% but not 50%; the later steps come back inside, which must not extend the radius
    assert agreement_radius(steps, g, -1.0, 0.30) == 5 and agreement_radius(steps, g, -1.0, 0.50) == 12.5
    assert agreement_radius(steps, [-2.0, -1, -1, -1, -1], -1.0, 0.30) is None                 # the smallest step already disagrees
    assert agreement_radius(steps, [1.0, 1.0, 1.0, 1.0, 1.0], -1.0, 0.50) is None             # the opposite sign never agrees
    with pytest.raises(ValueError):
        agreement_radius(steps, g, 0.0, 0.3)


def test_secant_drift_radius_marks_where_the_secant_bends():
    d = secant_drift_radius([2.5, 5, 7.5, 10, 12.5], [1.0, 1.05, 1.2, 1.4, 1.7], 0.30)
    assert d == {"reference_step_mm": 2.5, "last_step_within_mm": 7.5, "first_step_outside_mm": 10}
    d = secant_drift_radius([2.5, 5], [1.0, 1.1], 0.30)
    assert d["first_step_outside_mm"] is None and d["last_step_within_mm"] == 5


def test_signed_interpolation_and_additivity_defect():
    steps, dr = [-5, -2.5, 2.5, 5], [2.0, 1.0, -1.0, -2.0]                       # a linear response through the origin
    q = interpolate_signed_response(steps, dr, 3.75)
    assert q["pchip_n"] == pytest.approx(-1.5, abs=1e-9) and q["linear_n"] == pytest.approx(-1.5) and q["interpolation_spread_n"] < 1e-9
    with pytest.raises(ValueError):
        interpolate_signed_response(steps, dr, 6.0)
    a = additivity_defect(-3.1, -3.0, 0.05)
    assert a["defect_n"] == pytest.approx(-0.1) and a["relative_to_combo"] == pytest.approx(0.1 / 3.1) and a["defect_exceeds_interpolation_spread_and_resolution"] is True
    # a defect below the measurement resolution (10 sigma0 = 3e-5 N) or below the interpolation spread is NOT flagged, even when the spread is exactly zero
    assert additivity_defect(-3.0, -3.0 - 1e-5, 0.0)["defect_exceeds_interpolation_spread_and_resolution"] is False
    assert additivity_defect(-3.0, -3.0 - 1e-2, 0.5)["defect_exceeds_interpolation_spread_and_resolution"] is False
    assert additivity_defect(0.0, 0.1)["relative_to_combo"] != additivity_defect(0.0, 0.1)["relative_to_combo"]        # a zero combined response: nan, never a crash


def test_is_resolved_boundary_and_drift_validation():
    assert not is_resolved(3e-5) and is_resolved(3.0000001e-5) and is_resolved(-3.1e-5)
    with pytest.raises(ValueError):
        secant_drift_radius([2.5, 5], [0.0, 1.0], 0.3)
    with pytest.raises(ValueError):
        interpolate_signed_response([1, 1], [0.0, 1.0], 1.0)
