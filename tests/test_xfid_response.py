from __future__ import annotations

import pytest

from cfd_sdf.xfid_response import (
    aggregate_verdicts,
    centered_contrast_n,
    centered_secant_n_per_unit,
    compare_direction,
    compare_resolved_delta,
    response_deltas,
)


def test_deltas_and_centered_secant_use_force_newtons_and_positive_step():
    plus, minus = response_deltas(10.0, 10.3, 9.8)
    assert plus == pytest.approx(0.3)
    assert minus == pytest.approx(-0.2)
    assert centered_contrast_n(10.3, 9.8) == pytest.approx(0.25)
    assert centered_secant_n_per_unit(10.3, 9.8, 0.25) == pytest.approx(1.0)


@pytest.mark.parametrize("wl,of", [(0.21, 0.31), (-0.21, -0.31)])
def test_resolved_same_sign_agrees_even_when_solver_magnitudes_differ(wl, of):
    assert compare_resolved_delta(wl, of, 0.1, 0.2) == "AGREE"


def test_resolved_opposite_sign_disagrees_only_after_both_floors():
    assert compare_resolved_delta(0.11, -0.31, 0.1, 0.2) == "DISAGREE"
    assert compare_resolved_delta(0.1, -0.31, 0.1, 0.2) == "UNRESOLVED"
    assert compare_resolved_delta(0.11, -0.2, 0.1, 0.2) == "UNRESOLVED"


def test_direction_requires_both_sides_and_centered_contrast_to_resolve():
    floors = (0.1, 0.1, 0.1)
    assert compare_direction((0.2, -0.3, 0.25), (0.4, -0.5, 0.45), floors, floors) == "AGREE"
    assert compare_direction((0.2, -0.3, 0.25), (0.4, 0.5, 0.45), floors, floors) == "DISAGREE"
    # A resolved disagreement remains evidence even if another contrast is unresolved.
    assert compare_direction((0.2, -0.3, 0.25), (0.4, 0.5, 0.1), floors, floors) == "DISAGREE"
    assert compare_direction((0.2, -0.3, 0.25), (0.4, -0.5, 0.1), floors, floors) == "UNRESOLVED"


def test_aggregate_prioritizes_resolved_disagreement_then_unresolved():
    assert aggregate_verdicts(["AGREE", "AGREE"]) == "AGREE"
    assert aggregate_verdicts(["AGREE", "UNRESOLVED"]) == "UNRESOLVED"
    assert aggregate_verdicts(["UNRESOLVED", "DISAGREE"]) == "DISAGREE"
    with pytest.raises(ValueError, match="at least one"):
        aggregate_verdicts([])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_arithmetic_inputs_fail_closed(value):
    with pytest.raises(ValueError, match="finite"):
        response_deltas(0.0, value, 0.0)
    with pytest.raises(ValueError, match="finite"):
        compare_resolved_delta(value, 1.0, 0.1, 0.1)


def test_invalid_step_and_missing_resolution_floor_are_rejected():
    with pytest.raises(ValueError, match="positive"):
        centered_secant_n_per_unit(1.1, 0.9, 0.0)
    with pytest.raises(ValueError, match="positive"):
        compare_resolved_delta(1.0, 1.0, 0.0, 0.1)


def test_direction_rejects_nonfinite_or_incomplete_contract_inputs():
    with pytest.raises(ValueError, match="finite"):
        compare_direction((1.0, float("nan"), 1.0), (1.0, 1.0, 1.0), (0.1,) * 3, (0.1,) * 3)
    with pytest.raises(ValueError, match="three values"):
        compare_direction((1.0, 1.0), (1.0, 1.0, 1.0), (0.1,) * 3, (0.1,) * 3)


def test_finite_inputs_that_overflow_derived_responses_fail_closed():
    with pytest.raises(ValueError, match="finite"):
        response_deltas(-1e308, 1e308, 0.0)
    assert centered_contrast_n(1e308, -1e308) == pytest.approx(1e308)
    with pytest.raises(ValueError, match="finite"):
        centered_secant_n_per_unit(1e308, -1e308, 1e-308)
