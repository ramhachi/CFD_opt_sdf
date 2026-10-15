"""GRID-02 contract: grid cases, placements, kernel plan, fits on the retained OPT-01 Stage B numbers, exact threshold boundaries, guards."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_sdf import grid02_contract as C  # noqa: E402

STEPS = [0.3125, 0.625, 0.9375, 1.25]
DL24 = [3.509e-6, -2.776e-5, -1.0546e-4, -2.334e-4]
DL32 = [1.335e-4, 2.754e-4, 3.847e-4, 4.683e-4]
OPT01B = json.loads((ROOT / "docs/evidence/opt01b_stage_b_2026_10_15/inventory.json").read_text())


def test_cases_match_the_registered_opt01b_measurement_cases_and_scale():
    for kernel, case in (("a", "flow_24"), ("b", "flow_32")):
        reg = OPT01B["grids"][kernel]["measurement"]["case"]
        assert {k: reg[k] for k in C.case_dict(case)} == C.case_dict(case)
        assert C.force_scale_n(case) == OPT01B["grids"][kernel]["baseline_reference"]["force_scale_n_per_solver_force"]
    assert C.case_dict("flow_48")["flow_dims"] == [300, 144, 108] and C.case_dict("flow_16")["flow_dims"] == [100, 48, 36]
    assert C.case_dict("flow_48")["flow_spacing_m"] == 0.8 / 48 and C.case_dict("flow_48")["solver_viscosity"] == 48 / 80 and C.case_dict("flow_16")["solver_viscosity"] == 0.2
    assert C.force_scale_n("flow_48") == (0.8 / 48) ** 2


def test_placements_shift_x_and_y_by_half_a_design_cell_and_never_z():
    n, s = C.PLACEMENTS["native"], C.PLACEMENTS["shifted"]
    assert C.origin_env("native") == OPT01B["job_env_common"]["W4_CANONICAL_ORIGIN_M"] == "-1.0,-0.8,-0.6" and C.origin_env("shifted") == "-0.9875,-0.7875,-0.6"
    assert [round(b - a, 12) for a, b in zip(n, s)] == [C.DESIGN_SPACING_M / 2, C.DESIGN_SPACING_M / 2, 0.0]


def test_kernel_plan_is_the_registered_table():
    K = C.KERNELS
    assert list(K) == ["s24", "s32", "f48a", "f48b", "f16"]
    assert K["s24"]["states"] == K["s32"]["states"] == C.SEVEN and len(C.SEVEN) == 7 and K["f16"]["states"] == C.SEVEN + (C.REPEAT,)
    assert K["f48a"]["states"] == (C.PARENT, "opt01b__prop__s0.3125mm", "opt01b__prop__s0.625mm", "opt01b__prop__s0.9375mm")
    assert K["f48b"]["states"] == (C.REPEAT, "opt01b__prop__s1.25mm", "opt01b__ctrl_reverse__s1.25mm")
    assert {k: C.aggregate_cap_s(k) for k in K} == {"s24": 6300, "s32": 6300, "f48a": 18000, "f48b": 13500, "f16": 7200}
    assert all(v["kernel_timeout_s"] - 300 > C.aggregate_cap_s(k) for k, v in K.items()) and K["f48a"]["kernel_timeout_s"] == K["f48b"]["kernel_timeout_s"] == 21600
    assert [K[k]["placement"] for k in K] == ["shifted", "shifted", "native", "native", "native"] and [K[k]["grid02_case"] for k in K] == [None, None, "flow_48", "flow_48", "flow_16"]
    assert set(OPT01B["kernels"]["a"]) == set(C.SEVEN) and OPT01B["kernels"]["a"] == list(C.SEVEN)


def test_fits_reproduce_the_retained_stage_b_refit():
    f = C.fit_quadratic(STEPS, DL24)
    assert 0.9e-4 < f["b_n_per_mm"] < 1.05e-4 and -2.4e-4 < f["a_n_per_mm2"] < -2.2e-4 and f["max_residual_n"] < 6e-6
    assert f["zero_crossing_mm"] == pytest.approx(f["b_n_per_mm"] / abs(f["a_n_per_mm2"])) and 0.35 < f["zero_crossing_mm"] < 0.45
    assert f["attainable_gain_n"] == pytest.approx(f["b_n_per_mm"] ** 2 / (2 * abs(f["a_n_per_mm2"]))) and f["attainable_gain_n"] < C.RESOLUTION_FLOOR_N
    g = C.fit_quadratic(STEPS, DL32)
    assert 4.7e-4 < g["b_n_per_mm"] < 5.0e-4 and -1.5e-4 < g["a_n_per_mm2"] < -0.8e-4 and g["max_residual_n"] < 2e-5 and 3 < g["zero_crossing_mm"] < 6 and g["attainable_gain_n"] > 5e-4
    h = C.fit_with_intercept([0.0] + STEPS, [0.0] + DL32)
    assert abs(h["c_n"]) < 2e-5 and h["b_n_per_mm"] == pytest.approx(g["b_n_per_mm"], rel=0.1) and h["max_residual_n"] < 2e-5


def test_fit_is_exact_on_exact_data_and_reports_the_non_attainable_cases():
    f = C.fit_quadratic([1, 2, 3, 4], [2 * s - 0.5 * s * s for s in (1, 2, 3, 4)])
    assert f["b_n_per_mm"] == pytest.approx(2) and f["a_n_per_mm2"] == pytest.approx(-0.5) and f["max_residual_n"] < 1e-12
    assert f["zero_crossing_mm"] == pytest.approx(4) and f["attainable_gain_n"] == pytest.approx(4)
    u = C.fit_quadratic([1, 2, 3], [s + 0.1 * s * s for s in (1, 2, 3)])
    assert u["zero_crossing_mm"] is None and u["attainable_gain_n"] is None and u["attainable_reason"] == "unbounded in range"
    n = C.fit_quadratic([1, 2, 3], [-s - 0.1 * s * s for s in (1, 2, 3)])
    assert n["attainable_gain_n"] is None and "b <= 0" in n["attainable_reason"]
    i = C.fit_with_intercept([0, 1, 2, 3], [1 + 2 * s + 0.5 * s * s for s in (0, 1, 2, 3)])
    assert (i["c_n"], i["b_n_per_mm"], i["a_n_per_mm2"]) == pytest.approx((1, 2, 0.5))


def test_fit_rejects_degenerate_or_non_finite_input():
    for bad in (([1.0], [1.0]), ([1.0, 1.0], [1.0, 2.0]), ([1, 2, 3], [1, 2]), ([1, 2, 3], [1, math.nan, 3]), ([1, 2, 3], [1, 2, math.inf])):
        with pytest.raises(ValueError):
            C.fit_quadratic(*bad)
    with pytest.raises(ValueError):
        C.fit_with_intercept([1, 2], [1, 2])


def test_resolution_and_sign_status_boundaries():
    assert C.resolution([]) == C.resolution([0.0, 1e-5, -2e-5]) == 3e-5 and C.resolution([5e-5, -7e-5]) == 7e-5 and C.resolution([3e-5]) == 3e-5
    with pytest.raises(ValueError):
        C.resolution([math.nan])
    assert C.sign_status(3.1e-5, 3e-5) == "positive_resolved" and C.sign_status(3e-5, 3e-5) == "unresolved" and C.sign_status(-3e-5, 3e-5) == "unresolved"
    assert C.sign_status(-3.1e-5, 3e-5) == "negative_resolved" and C.sign_status(0.0, 3e-5) == "unresolved"
    with pytest.raises(ValueError):
        C.sign_status(math.nan, 3e-5)


def al(m24, m32):  # G = 4: slopes chosen so that m24, m32 are exactly representable
    return C.alignment_classification(0.0, 4 * m24, 4.0, 4.0 - 4 * m32)


@pytest.mark.parametrize("m24,m32,want", [
    (0.5, 0.5, "GRID02_ALIGNMENT_DOMINANT"), (0.5, 0.75, "GRID02_ALIGNMENT_DOMINANT"), (1.0, 0.5, "GRID02_ALIGNMENT_DOMINANT"), (0.25, 0.5, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"),
    (0.5, 0.25, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (0.25, 0.25, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (0.0, 0.0, "GRID02_ALIGNMENT_NEGLIGIBLE"),
    (0.125, -0.125, "GRID02_ALIGNMENT_NEGLIGIBLE"), (-0.25, 0.0, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (0.0, 0.25, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"),
    (0.5, -0.5, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED"), (-0.5, -0.5, "GRID02_ALIGNMENT_PARTIAL_OR_MIXED")])
def test_alignment_classification_cases(m24, m32, want):
    r = al(m24, m32)
    assert r["G"] == 4.0 and r["m24"] == m24 and r["m32"] == m32 and r["classification"] == want


def test_alignment_negligible_boundary_is_0p2_inclusive():
    g = 5.0  # b_24s = b_24n + m24 G with m24 = 0.2 exactly after division: 1.0 / 5.0 == 0.2
    r = C.alignment_classification(0.0, 1.0, 5.0, 4.0)
    assert r["m24"] == 0.2 and r["m32"] == 0.2 and r["classification"] == "GRID02_ALIGNMENT_NEGLIGIBLE"
    r = C.alignment_classification(0.0, 1.0001, 5.0, 4.0)
    assert r["classification"] == "GRID02_ALIGNMENT_PARTIAL_OR_MIXED" and g == 5.0


def test_alignment_negative_gap_is_handled_by_the_signed_ratio():
    r = C.alignment_classification(4.0, 2.0, 0.0, 2.0)  # G = -4: both bases move toward each other by half the gap
    assert r["G"] == -4.0 and r["m24"] == 0.5 and r["m32"] == 0.5 and r["classification"] == "GRID02_ALIGNMENT_DOMINANT"


def test_guards_refuse_a_zero_or_non_finite_gap_and_non_finite_slopes():
    for args in ((1.0, 2.0, 1.0, 2.0), (math.nan, 1.0, 2.0, 1.0), (1.0, 1.0, math.inf, 1.0), (0.0, 0.0, 1e-400, 0.0)):
        with pytest.raises(ValueError):
            C.alignment_classification(*args)
    for args in ((1.0, 1.0, 2.0), (1.0, math.nan, 2.0), (0.0, 1.0, math.inf)):
        with pytest.raises(ValueError):
            C.fine_classification(*args)


@pytest.mark.parametrize("r,want", [(0.5, "FINE_CONTINUES_TO_FLOW32"), (0.75, "FINE_CONTINUES_TO_FLOW32"), (1.5, "FINE_CONTINUES_TO_FLOW32"), (0.25, "FINE_INTERMEDIATE"),
                                    (0.375, "FINE_INTERMEDIATE"), (0.125, "FINE_REVERSES_TOWARD_FLOW24"), (0.0, "FINE_REVERSES_TOWARD_FLOW24"), (-1.0, "FINE_REVERSES_TOWARD_FLOW24")])
def test_fine_classification_cases(r, want):  # G = 4, so b_48n = 4 r
    out = C.fine_classification(0.0, 4.0, 4.0 * r)
    assert out["G"] == 4.0 and out["r"] == r and out["classification"] == want


def test_fine_classification_exact_thresholds_and_stability_band():
    assert C.fine_classification(0.0, 10.0, 5.0)["classification"] == "FINE_CONTINUES_TO_FLOW32"  # r = 0.5 inclusive
    assert C.fine_classification(0.0, 10.0, 2.0)["classification"] == "FINE_REVERSES_TOWARD_FLOW24"  # r = 0.2 inclusive
    assert C.fine_classification(0.0, 10.0, 2.0001)["classification"] == "FINE_INTERMEDIATE" and C.fine_classification(0.0, 10.0, 4.9999)["classification"] == "FINE_INTERMEDIATE"
    assert C.fine_classification(0.0, 10.0, 13.0)["stable_32_to_48"] is True and C.fine_classification(0.0, 10.0, 7.0)["stable_32_to_48"] is True  # |db| = 0.3 |b32| inclusive
    assert C.fine_classification(0.0, 10.0, 13.0001)["stable_32_to_48"] is False and C.fine_classification(0.0, 10.0, 6.9999)["stable_32_to_48"] is False
    assert C.fine_classification(0.0, -10.0, -13.0)["stable_32_to_48"] is True and C.fine_classification(0.0, -10.0, -13.5)["stable_32_to_48"] is False


def test_decision_map_branches_and_validation():
    a = C.ALIGNMENT
    assert "placement artifact" in C.decision_text(a[0], C.FINE[0], True) and "placement artifact" in C.decision_text(a[0], C.FINE[1], False)
    assert "stable working map" in C.decision_text(a[1], C.FINE[0], True) and "no affordable grid" in C.decision_text(a[1], C.FINE[2], False)
    assert "second placement phase study" in C.decision_text(a[2], C.FINE[1], True) and C.decision_text(a[1], C.FINE[0], True).startswith(a[1])
    for bad in (("x", C.FINE[0], True), (a[0], "x", True), (a[0], C.FINE[0], 1)):
        with pytest.raises(ValueError):
            C.decision_text(*bad)


def test_both_grid_rule_on_the_retained_numbers_is_the_known_reject_and_boundaries_are_strict():
    dl = {"flow_24": DL24[3], "flow_32": DL32[3]}
    assert C.both_grid_rule(dl, {"flow_24": 1e-6, "flow_32": 1e-6})["pass"] is False  # the retained pair: flow_24 loses downforce at every step
    assert C.both_grid_rule({"g1": 3.1e-5, "g2": 4e-5}, {"g1": 0.0, "g2": -1e-6})["pass"] is True
    assert C.both_grid_rule({"g1": 3e-5, "g2": 4e-5}, {"g1": 0.0, "g2": 0.0})["pass"] is False  # strictly greater
    r = C.both_grid_rule({"g1": 4e-5}, {"g1": 1e-9})
    assert r["pass"] is False and r["per_grid"]["g1"] == {"gain_ok": True, "drag_ok": False}
    for bad in (({}, {}), ({"a": 1.0}, {"b": 1.0}), ({"a": math.nan}, {"a": 0.0})):
        with pytest.raises(ValueError):
            C.both_grid_rule(*bad)
