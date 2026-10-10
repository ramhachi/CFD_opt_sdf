"""Strict common-candidate selection and finite-step diagnostic semantics."""
from copy import deepcopy

import pytest

from cfd_sdf import lowdim03_contract as C


def responses(lift=0.0, drag=0.0):
    return {g: {"downforce_n": lift, "drag_n": drag} for g in C.GRIDS}


def test_joint_strict_boundaries_and_small_margin_are_not_relaxed():
    base = responses()
    assert C.evaluate_candidate(base, responses(3e-5, 0), True)["accepted"] is False
    assert C.evaluate_candidate(base, responses(3.0001e-5, 0), True)["accepted"] is True
    out = C.evaluate_candidate(base, responses(1e-4, 1e-15), True)
    assert out["accepted"] is False
    assert all(v["small_computed_drag_margin"] for v in out["per_grid"].values())
    mixed = responses(1e-4, -1e-6)
    mixed["flow_32"]["drag_n"] = 1e-6
    assert C.evaluate_candidate(base, mixed, True)["accepted"] is False
    mixed["flow_32"]["drag_n"] = 0
    mixed["flow_32"]["downforce_n"] = 1e-5
    assert C.evaluate_candidate(base, mixed, True)["accepted"] is False
    assert C.evaluate_candidate(base, responses(1e-4, -1e-4), False)["accepted"] is False


@pytest.mark.parametrize("bad", [True, False, "0.1", None, float("nan"), float("inf"), 10**1000])
def test_malformed_or_nonfinite_numbers_never_accept(bad):
    values = responses(1e-4, -1e-4)
    values["flow_32"]["drag_n"] = bad
    with pytest.raises(ValueError):
        C.evaluate_candidate(responses(), values, True)


def test_overflowed_difference_is_rejected():
    with pytest.raises(ValueError):
        C.evaluate_candidate(responses(-1e308), responses(1e308), True)


def test_selection_uses_common_worst_gain_and_exact_ties_prefer_smaller_step():
    steps = {C.state_name(s, 1): s for s in C.STEPS_MM}
    evaluations = {n: {"accepted": True, "worst_grid_downforce_gain_n": .0002} for n in steps}
    assert C.select_trial(evaluations, steps)["selected_step_mm"] == .625
    evaluations[C.state_name(1.25, 1)]["worst_grid_downforce_gain_n"] = .0003
    assert C.select_trial(evaluations, steps)["selected_step_mm"] == 1.25
    evaluations[C.state_name(1.25, 1)]["accepted"] = False
    assert C.select_trial(evaluations, steps)["selected_step_mm"] == .625
    for value in evaluations.values():
        value["accepted"] = False
    assert C.select_trial(evaluations, steps)["verdict"] == "LOWDIM03_NO_ACCEPT"
    evaluations[C.state_name(.625, -1)] = {"accepted": True, "worst_grid_downforce_gain_n": 100.0}
    with pytest.raises(ValueError):
        C.select_trial(evaluations, {**steps, C.state_name(.625, -1): .625})


def test_five_geometry_booleans_and_aggregate_are_exact():
    good = {"gates": {k: True for k in C.GEOMETRY_GATE_KEYS}, "all_hard_gates_pass": True}
    assert C.geometry_pass(good) is True
    bad = deepcopy(good)
    bad["gates"]["clearance"] = 1
    with pytest.raises(ValueError):
        C.geometry_pass(bad)
    bad = deepcopy(good)
    bad["all_hard_gates_pass"] = False
    with pytest.raises(ValueError):
        C.geometry_pass(bad)
    bad = deepcopy(good)
    bad["gates"].pop("clearance")
    with pytest.raises(ValueError):
        C.geometry_pass(bad)


def reference():
    return {"m_max_abs_sum": 2.0, "per_grid": {g: {
        "raw_downforce_slope_n_per_m": 1.0, "raw_drag_slope_n_per_m": -.2,
        "l1_robust_downforce_lower_slope_n_per_m": .8,
        "l1_robust_drag_upper_slope_n_per_m": -.1,
    } for g in C.GRIDS}}


def test_raw_rho_odd_even_and_robust_references_have_distinct_semantics():
    ref = reference()
    diagnostic = C.model_diagnostics(responses(), responses(.0005, -.00004),
                                    responses(-.0003, .00006), ref, 1.25)
    d = diagnostic["flow_32"]
    assert d["downforce"]["odd_part_n"] == pytest.approx(.0004)
    assert d["downforce"]["even_part_n"] == pytest.approx(.0001)
    assert d["downforce"]["odd_part_secant_n_per_m_of_max_norm_step"] == pytest.approx(.32)
    assert d["downforce"]["rho_actual_over_raw_linear"] == pytest.approx(.8)
    assert d["forward_predictions"]["l1_robust_downforce_lower_prediction_n"] == pytest.approx(.0005)
    assert d["drag"]["prediction_error_n"] == pytest.approx(.000085)
    assert "l1_robust_downforce_lower_prediction_n" not in C.predictions(ref, 1.25, -1)["flow_32"]
    ref["per_grid"]["flow_32"]["raw_downforce_slope_n_per_m"] = 0.0
    d = C.model_diagnostics(responses(), responses(), responses(), ref, 1.25)["flow_32"]["downforce"]
    assert d["rho_actual_over_raw_linear"] is None and d["rho_reason"] == "raw_prediction_nonpositive"
    ref["per_grid"]["flow_32"]["raw_downforce_slope_n_per_m"] = 1e-15
    d = C.model_diagnostics(responses(), responses(), responses(), ref, 1.25)["flow_32"]["downforce"]
    assert d["rho_actual_over_raw_linear"] == 0 and d["rho_reason"] == "raw_prediction_positive"
