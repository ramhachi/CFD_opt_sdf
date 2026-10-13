"""LOWDIM-04A Stage A contract: state plan, parameterized secants, cone verdict logic on synthetic responses."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import lowdim04a_contract as C  # noqa: E402
import lowdim04a_states as L  # noqa: E402
from cfd_sdf import grid01_contract as G  # noqa: E402


def test_plan_is_parent_first_then_eight_centered_perturbations_with_the_recorded_names():
    plan = L.plan()
    assert [r["name"] for r in plan][0] == "lowdim04a__parent" and len(plan) == 9
    blocker = json.loads((ROOT / "docs/evidence/lowdim04_dual_grid_local_model_2026_10_11/pre_registration_blocker.json").read_text())
    assert [r["name"] for r in plan[1:]] == [s["state_name"] for s in blocker["existing_lowdim_geometry_preflight"]["states"]]
    assert list(C.BASIS) == list(L.BASIS) == list(G.BASIS)


def test_secant_uses_the_registered_1p25_mm_step_not_grid01s_2p5_mm():
    a = C.secant_sample(1.0, 1.0 + 1e-3, 1.0 - 1e-3)
    assert a["g_sec_n_per_m"] == pytest.approx(2e-3 / (2 * 0.00125))
    assert G.secant_sample(1.0, 1.0 + 1e-3, 1.0 - 1e-3)["g_sec_n_per_m"] == pytest.approx(a["g_sec_n_per_m"] / 2)  # the silent halving that a naive reuse would cause
    assert C.EPSILON_N_PER_M == pytest.approx(0.012) and G.UNCERTAINTY_N_PER_M == pytest.approx(0.006)


def test_resolution_rule_and_even_part():
    s = C.secant_sample(1.0, 1.0 + 2e-5, 1.0 - 2e-5)  # contrast 4e-5 > 3e-5 floor
    assert s["resolved"] and s["resolved_sign"] == 1
    u = C.secant_sample(1.0, 1.0 + 1e-5, 1.0 - 1e-5)  # contrast 2e-5: unresolved, sign withheld
    assert not u["resolved"] and u["resolved_sign"] is None
    e = C.secant_sample(0.0, 1e-3, 1e-3)
    assert e["even_part_n"] == pytest.approx(1e-3) and e["contrast_plus_minus_n"] == 0.0 and e["eta_even"] is None


def _dirs():
    rng = np.random.default_rng(3)
    return {n: rng.uniform(-1, 1, (4, 3, 3)).astype(np.float32) for n in C.BASIS}


def test_a_feasible_model_is_found_and_every_solution_is_kkt_verified():
    lift = [[0.8, -0.1, -0.1, -0.4], [0.9, 0.05, -0.15, -0.5]]
    drag = [[-0.1, -0.07, -0.17, -0.2], [0.2, -0.1, -0.15, -0.05]]
    sol = C.solve(lift, drag)
    pred = C.predictions(sol, lift, drag, _dirs())
    v = C.verdict(sol, pred)
    assert sol["all_solutions_verified"] and v["verdict"] == "LOCAL_FEASIBLE_CONE_FOUND" and not v["reasons"]
    assert pred["main_cross_grid"]["normalization"]["max_abs_dphi_m"] == C.STEP_M


def test_an_infeasible_model_is_not_found_not_incomplete():
    lift = [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]  # lift and drag move together in the only useful direction: drag nonincrease forbids every gain
    drag = [[0.1, 0.0, 0.0, 0.0], [0.1, 0.0, 0.0, 0.0]]
    sol = C.solve(lift, drag)
    pred = C.predictions(sol, lift, drag, _dirs())  # a zero solution must not raise: the verdict is NOT_FOUND, never INCOMPLETE
    v = C.verdict(sol, pred)
    assert sol["all_solutions_verified"] and pred["main_cross_grid"]["normalization"].get("zero_solution") is True
    assert v["verdict"] == "LOCAL_FEASIBLE_CONE_NOT_FOUND" and v["reasons"]


def test_main_passing_but_robust_failing_is_not_found():
    lift = [[0.008, 0.0, 0.0, 0.0], [0.008, 0.0, 0.0, 0.0]]  # tiny slopes: the L1-robust lower bound (epsilon 0.012) cannot clear the floor
    drag = [[0.0, 0.0, 0.0, -0.1], [0.0, 0.0, 0.0, -0.1]]
    sol = C.solve(lift, drag)
    v = C.verdict(sol, C.predictions(sol, lift, drag, _dirs()))
    assert v["verdict"] == "LOCAL_FEASIBLE_CONE_NOT_FOUND"
