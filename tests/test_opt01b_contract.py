"""OPT-01 v1 Stage B contract: the ladder plan, the unchanged LOWDIM-03 accept rule, the contract-derived ladder, selection, and the descriptive hindcast."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import opt01b_contract as C  # noqa: E402
import opt01b_states as L  # noqa: E402
from cfd_sdf import lowdim03_contract as L3  # noqa: E402


def test_plan_is_parent_then_four_positive_steps_then_two_reverse_diagnostics():
    plan = L.plan()
    assert [r["name"] for r in plan] == ["opt01b__parent", *[f"opt01b__prop__s{s:g}mm" for s in (0.3125, 0.625, 0.9375, 1.25)], "opt01b__ctrl_reverse__s0.625mm", "opt01b__ctrl_reverse__s1.25mm"]
    assert [r["kind"] for r in plan] == ["parent", "candidate", "candidate", "candidate", "candidate", "control", "control"] and plan[0]["direction"] is None
    assert all(r["direction"] == "robust_opt01a" for r in plan[1:]) and [r["sign"] for r in plan] == [0, 1, 1, 1, 1, -1, -1]


def test_the_accept_rule_is_lowdim03s_unchanged():
    assert (C.MIN_DOWNFORCE_GAIN_N, C.DRAG_ALLOWANCE_N, C.SMALL_DRAG_MARGIN_N) == (3e-5, 0.0, 3e-5) and C.evaluate_candidate is L3.evaluate_candidate


def forces(d24, d32, base24=(0.33, 0.32), base32=(0.36, 0.35)):
    mk = lambda base, dd: {"downforce_n": base[0] + dd[0], "drag_n": base[1] + dd[1]}
    return ({"flow_24": mk(base24, (0, 0)), "flow_32": mk(base32, (0, 0))}, {"flow_24": mk(base24, d24), "flow_32": mk(base32, d32)})


def evaluation(d24, d32):
    base, plus = forces(d24, d32)
    return C.evaluate_candidate(base, plus, True)


def test_accept_needs_strictly_more_than_the_floor_and_nonpositive_drag_on_both_grids():
    assert evaluation((5e-5, -1e-5), (6e-5, 0.0))["accepted"]
    exact = C.evaluate_candidate({"flow_24": {"downforce_n": 0.0, "drag_n": 0.0}, "flow_32": {"downforce_n": 0.0, "drag_n": 0.0}},
                                 {"flow_24": {"downforce_n": 3e-5, "drag_n": 0.0}, "flow_32": {"downforce_n": 6e-5, "drag_n": 0.0}}, True)  # exactly the floor: strict > fails
    assert not exact["accepted"] and exact["per_grid"]["flow_24"]["downforce_change_n"] == 3e-5
    assert not evaluation((2.9e-5, 0.0), (6e-5, 0.0))["accepted"]
    assert not evaluation((5e-5, 1e-6), (6e-5, 0.0))["accepted"]
    assert not evaluation((5e-5, 0.0), (6e-5, 2e-5))["accepted"]


def selection(gains):
    steps = {L.candidate_name(s): s for s in L.STEPS_MM}
    ev = {n: {"accepted": g is not None, "worst_grid_downforce_gain_n": g if g is not None else 0.0} for n, g in zip(steps, gains)}
    return C.select_trial(ev, steps)


def test_selection_takes_the_largest_minimum_gain_ties_use_the_smaller_step_and_none_is_no_accept():
    s = selection([4e-5, 7e-5, 5e-5, None])
    assert s["verdict"] == "OPT01_V1_ACCEPT" and s["selected"] == "opt01b__prop__s0.625mm" and s["selected_step_mm"] == 0.625
    assert selection([6e-5, 6e-5, 6e-5, 6e-5])["selected_step_mm"] == 0.3125
    n = selection([None, None, None, None])
    assert n["verdict"] == "OPT01_V1_REJECT" and n["selected"] is None
    with pytest.raises(ValueError):
        C.select_trial({}, {})
    with pytest.raises(ValueError):
        selection([2e-5, None, None, None])  # an "accepted" candidate at or below the floor is an inconsistent record


def stage_a_stub(w_m, g_lift, even_lift):
    secants = {g: {q: {d: {"g_sec_n_per_m": 0.0, "even_part_n": 0.0} for d in L.BASIS} for q in C.RESPONSES} for g in C.GRIDS}
    for gi, g in enumerate(C.GRIDS):
        for di, d in enumerate(L.BASIS):
            secants[g]["downforce"][d] = {"g_sec_n_per_m": g_lift[gi][di], "even_part_n": even_lift[gi][di]}
    return {"secants": secants, "predictions_at_1p25mm": {"robust_cross_grid": {"normalization": {"basis_coefficients_m": w_m}}}}


def test_hindcast_scales_the_linear_term_by_f_and_the_curvature_term_by_f_squared_and_pair_parts_split_odd_even():
    w = [0.5e-3, 0.0, 0.0, 0.0]
    a = stage_a_stub(w, [[0.4, 0, 0, 0], [0.4, 0, 0, 0]], [[-1e-4, 0, 0, 0], [-1e-4, 0, 0, 0]])
    base, plus = forces((1e-4, 0.0), (1e-4, 0.0))
    states = {g: {L.PARENT_NAME: base[g], L.candidate_name(0.625): plus[g], L.control_name(0.625): {"downforce_n": base[g]["downforce_n"] - 3e-4, "drag_n": base[g]["drag_n"]}} for g in C.GRIDS}
    h = C.hindcast(a, states, 0.625)["flow_24"]["downforce"]
    f = 0.625 / 1.25
    assert h["stage_a_linear_prediction_n"] == pytest.approx(0.4 * 0.5e-3 * f)
    assert h["stage_a_diagonal_curvature_estimate_n"] == pytest.approx(0.4 * 0.5e-3 * f + (-1e-4) * (0.5e-3 * f / 0.00125) ** 2) and h["actual_change_n"] == pytest.approx(1e-4)
    p = C.pair_parts(states, 0.625)["flow_24"]["downforce"]
    assert p["odd_part_n"] == pytest.approx((1e-4 + 3e-4) / 2) and p["even_part_n"] == pytest.approx((1e-4 - 3e-4) / 2)


def test_select_trial_rejects_malformed_records():
    steps = {L.candidate_name(s): s for s in L.STEPS_MM}
    good = {n: {"accepted": False, "worst_grid_downforce_gain_n": 0.0} for n in steps}
    for bad in ({**good, L.control_name(0.625): good[next(iter(good))]}, {**good, next(iter(good)): {"accepted": 1, "worst_grid_downforce_gain_n": 1e-4}},
                {**good, next(iter(good)): {"accepted": True, "worst_grid_downforce_gain_n": float("nan")}}, {**good, next(iter(good)): {"accepted": False}}):
        with pytest.raises((ValueError, TypeError, KeyError)):
            C.select_trial(bad, steps)


def test_hindcast_linear_term_reproduces_stage_a_prediction_and_the_direction_matches_the_stage_a_basis_coefficients():
    import json
    import step01_states as S
    inv = json.loads((ROOT / "docs/evidence/opt01b_stage_b_2026_10_15/inventory.json").read_text())
    a = json.loads((ROOT / inv["stage_a"]["analysis_path"]).read_text())
    w = a["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["basis_coefficients_m"]
    states = {g: {L.PARENT_NAME: {"downforce_n": 0.0, "drag_n": 0.0}, L.candidate_name(1.25): {"downforce_n": 1e-4, "drag_n": 0.0}} for g in C.GRIDS}
    h = C.hindcast(a, states, 1.25)
    for g in C.GRIDS:
        assert h[g]["downforce"]["stage_a_linear_prediction_n"] == pytest.approx(a["predictions_at_1p25mm"]["robust_cross_grid"]["per_grid"][g]["raw_downforce_prediction_n"], rel=1e-12)
    dirs = {n: S.read_f4(ROOT / inv["directions"][n]["path"]).astype("float64") for n in L.BASIS}
    prop = S.read_f4(ROOT / inv["proposal"]["file"]).astype("float64")
    assert abs(1.25e-3 * prop - sum(wi * dirs[n] for wi, n in zip(w, L.BASIS))).max() < 1e-9  # state + is phi + s*d with the Stage A basis coefficients w = c*(s/m)


def test_the_ladder_and_scope_come_from_the_pinned_contract_and_a_gate_failing_step_cannot_be_accepted():
    import hashlib
    assert hashlib.sha256((ROOT / L.CONTRACT_REL).read_bytes()).hexdigest() == L.CONTRACT_SHA256
    assert (L.STEPS_MM, L.CONTROL_STEPS_MM) == ((0.3125, 0.625, 0.9375, 1.25), (0.625, 1.25)) and L.BASIS == tuple(L.CONTRACT["pins"]["basis_order"])
    table = {"near_zero_gradient_band": "fail", "p22_v2": "pass", "retained_clearance": "pass"}
    assert L.hard_failures("candidate", table) == ["near_zero_gradient_band"] and L.hard_failures("parent", table) == ["near_zero_gradient_band"]  # proposals: crossing-slope is hard
    assert L.hard_failures("control", table) == []  # reverse diagnostics are probes: crossing-slope is report-only
    for gate in ("p22_v2", "retained_clearance", "export_surface_integrity", "count_equal_margin_positive"):
        assert L.hard_failures("control", {**table, gate: "fail"}) == [gate]  # a probe failing any other gate still blocks
    assert L.hard_failures("control", {**table, "x": "unmeasured"}) == ["x"]
    base, plus = forces((5e-5, -1e-5), (6e-5, 0.0))
    assert C.evaluate_candidate(base, plus, True)["accepted"] and not C.evaluate_candidate(base, plus, False)["accepted"]  # a gate-rejected step is ineligible whatever its responses
    steps = {L.candidate_name(s): s for s in L.STEPS_MM}
    ev = {n: {"accepted": False, "worst_grid_downforce_gain_n": 9e-5} for n in steps}  # all gate-rejected: REJECT, not a dropped step
    assert C.select_trial(ev, steps)["verdict"] == "OPT01_V1_REJECT"
    assert C.TERMINALS == ("OPT01_V1_ACCEPT", "OPT01_V1_REJECT", "OPT01_V1_INCOMPLETE")
