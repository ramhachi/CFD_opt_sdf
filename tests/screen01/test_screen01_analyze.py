"""SCREEN-01 (#64): the analyzer on synthetic data, every §5.8 step, every §5.9 row, the estimators, the labels, the guards (write-once, constants, freezes, budget, INFRA_LOSS).

The cross-check against the independent implementation is in test_screen01_crosscheck.py."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import synthetic as Y  # noqa: E402

S, P, SC = Y.S, Y.P, Y.S.SC


@pytest.fixture(autouse=True)
def small_grid(monkeypatch):
    monkeypatch.setattr(S, "GRID_N", 41)   # the registered 81 per axis is used by the cross-check tests


def res(name):
    return S.compute(Y.branch(name))


def run(df, dr=0.0, ok=True):
    return {"downforce": df, "drag": dr, "ok": ok}


def tiny(runs, extra=None):
    roles = {Y.PARENT: {"role": "parent", "order": 0, "u": None}, "x": {"role": "axial", "order": 0, "u": [1.0, 0.0, 0.0]}, Y.ROLL: {"role": "nc", "order": 0, "u": None}, **(extra or {})}
    return {"schema": "screen01-T-v1", "stage": "rs", "roles": roles, "runs": {"g1": runs}, "lost_kernels": [], "gating": []}


# ---- constants and guards ---------------------------------------------------------------------------------------------------------------------------
def test_constants_are_reread_and_consistent():
    c = S.coefficients()
    assert c["fid_analysis_sha256"].startswith("b89203d0") and c["m2_analysis_sha256"].startswith("ee71c6d6")
    assert abs(S.G_MIN * S.J_B48 - S.X_STAR) < 1e-17 and abs(S.E2 - 2 * S.S_D * S.J_B48) < 1e-18 and abs(2 * S.S_D_OF - S.XV_FLOOR) < 1e-15
    assert abs(c["tier_a_residual_sd_n"] - 5.61e-4) < 5e-7 and abs(c["tier_a_slope"] - 0.655) < 5e-4


def test_constant_file_sha_mismatch_refused(tmp_path):
    fid, m2 = tmp_path / "fid.json", tmp_path / "m2.json"
    a = json.loads(S.FID_ANALYSIS.read_text())
    a["m3b_min_gain"]["min_gain_relative"] += 1e-9
    fid.write_text(json.dumps(a))
    m2.write_text(S.M2_ANALYSIS.read_text())
    with pytest.raises(ValueError, match="FID-01 analysis.json differs"):
        S.coefficients(fid, m2)
    fid.write_text(S.FID_ANALYSIS.read_text())
    m2.write_text(S.M2_ANALYSIS.read_text() + " ")
    with pytest.raises(ValueError, match="M2 analysis.json differs"):
        S.coefficients(fid, m2)


def test_refuses_without_freeze_records(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EV", tmp_path)
    for name in ("freeze1", "freeze2", "freeze2_1", "freeze3"):
        with pytest.raises(ValueError, match="is missing"):
            S.freeze(name)
    with pytest.raises(ValueError, match="is missing"):
        S.run_rs(argparse.Namespace())
    with pytest.raises(ValueError, match="is missing"):
        S.run_finalist(argparse.Namespace())
    with pytest.raises(ValueError, match="is missing"):
        S.run_main(argparse.Namespace())


def test_write_once_refuses_second_write(tmp_path):
    S.write_once(tmp_path / "x.json", "a")
    with pytest.raises(FileExistsError):
        S.write_once(tmp_path / "x.json", "b")
    assert (tmp_path / "x.json").read_text() == "a"


def test_canon_normalises_numeric_keys():
    assert S.canon({1: {"u": (1, 2)}, "1.5": 2, 2.0: 3, "v18__x": 4, "11": 5}) == {"1": {"u": [1, 2]}, "1.5": 2, "2": 3, "v18__x": 4, "11": 5}


def test_cross_check_refuses_on_discrepancy():
    T = Y.branch("rs_base")
    mine = S.compute(T)
    agree = types.SimpleNamespace(check=lambda t: S.compute(t), compare=lambda a, b, stage: [k for k in a if a[k] != b.get(k)])
    assert S.cross_check(mine, T, agree)["discrepancies"] == []
    bad = types.SimpleNamespace(check=lambda t: {**S.compute(t), "stop_after": 99}, compare=agree.compare)
    with pytest.raises(ValueError, match="cross-check discrepancies.*stop_after"):
        S.cross_check(mine, T, bad)


# ---- §5.1 estimators and DATA_LOSS --------------------------------------------------------------------------------------------------------------
def test_estimator_p1_uses_the_floor_and_p2_the_sample_sd():
    e1 = S.est([0.004], S.FLOOR["downforce"])
    assert e1["P"] == 1 and e1["sigma_d"] is None and e1["se_eff"] == S.FLOOR["downforce"] and e1["delta_bar"] == 0.004
    e2 = S.est([0.0, 0.002], S.FLOOR["downforce"])
    assert math.isclose(e2["sigma_d"], 0.002 / math.sqrt(2)) and math.isclose(e2["se_eff"], e2["sigma_d"] / math.sqrt(2))
    e3 = S.est([0.0010, 0.00101], S.FLOOR["downforce"])   # sigma_d below the floor: the floor
    assert math.isclose(e3["se_eff"], S.FLOOR["downforce"] / math.sqrt(2))
    assert S.est([1.0, 1.0, 1.0], 1e-4)["P"] == 3


def test_data_loss_triggers_and_boundary():
    par = {"11": run(1.0, 1.0), "12": run(1.0, 1.0)}
    runs = {Y.PARENT: par, "x": {"11": run(1.0, 1.0, ok=False), "12": run(None, 1.0)}, "y": {"11": run(math.nan, 1.0), "12": run(1.0, math.inf)},
            "z": {"11": run(1.25, 1.0), "12": run(1.2500001, 1.0)}, "w": {"11": run(1.0, 1.25), "12": run(1.0, 0.7499999)}}
    V, loss = S.valid_runs(tiny(runs))
    assert loss == ["w@g1@12", "x@g1@11", "x@g1@12", "y@g1@11", "y@g1@12", "z@g1@12"]
    assert set(V["g1"]["z"]) == {"11"} and set(V["g1"]["w"]) == {"11"} and "x" not in V["g1"]       # 0.25 exactly is kept (the bound is strict)


def test_data_loss_parent_lost_leaves_candidates_unpaired_but_not_lost():
    runs = {Y.PARENT: {"11": run(None), "12": run(1.0, 1.0)}, "x": {"11": run(1.0, 1.0), "12": run(1.01, 1.0)}}
    T = tiny(runs)
    V, loss = S.valid_runs(T)
    assert loss == [f"{Y.PARENT}@g1@11"] and list(S.diffs(V, "g1", "x", Y.PARENT)) == ["12"]


def test_data_loss_is_applied_per_group_against_that_groups_parent():
    T = tiny({Y.PARENT: {"11": run(1.0, 1.0)}, "x": {"11": run(1.1, 1.0)}})
    T["runs"]["g2"] = {Y.PARENT: {"11": run(2.0, 1.0)}, "x": {"11": run(1.1, 1.0)}}   # 45 % away from the g2 parent only
    _, loss = S.valid_runs(T)
    assert loss == ["x@g2@11"]


# ---- §5.2 response surface and the refinement --------------------------------------------------------------------------------------------------
def test_fit_recovers_the_truth_and_the_constrained_optimum_is_feasible():
    r = res("rs_base")
    assert np.allclose(r["fit"]["downforce"]["coef"], Y.BY, atol=1e-12) and np.allclose(r["fit"]["drag"]["coef"], Y.BZ, atol=1e-12)
    assert r["fit"]["rank"] == 9 and r["fit"]["cond"] <= 20 and not r["rs_not_fit"] and r["rs_fit_poor"] is False
    assert r["pool_limited_pre"] is True and r["y_star_1"] >= S.X_STAR
    u = np.array(r["u_star_1"])
    assert (u >= [-1, -1.5, -1]).all() and (u <= [1, 1, 1]).all() and Y.surface(Y.BZ, u) <= -P.M_D + 1e-12
    for tau in (1.0, 1.5, 2.0):
        t = r["targets"][f"{tau:g}"]
        assert t["z_pred"] <= -tau * P.M_D + 1e-12 and math.isclose(t["y_pred"], Y.surface(Y.BY, t["u_star"]), abs_tol=1e-12)


def test_gating_record_and_proposals_follow_the_registered_rule():
    T = Y.branch("rs_base")
    r = S.compute(T)
    assert r["stop_after"] == len(r["gated"]) == len(T["gating"]) <= 36 and r["stop_after"] % 4 == 0
    assert 1 <= len(r["proposals"]) <= 4 and all(T["gating"][i]["admissible"] for i in r["proposals"])
    assert [g[0] for g in r["gated"]] == [x["target_index"] for x in T["gating"]]
    assert all(g[1] == [round(x, 6) for x in rec["u"]] for g, rec in zip(r["gated"], T["gating"]))
    first = [T["gating"][i]["target_index"] for i in r["proposals"][:3]]
    assert first == sorted(set(first))      # one proposal per target first, in target order


def test_refinement_stops_after_the_round_with_two_admissible_points_per_target():
    T = Y.make("rs", oracle=lambda u: True, n_grid=41)
    assert len(T["gating"]) == 8 and len(S.compute(T)["proposals"]) == 4
    T = Y.make("rs", oracle=lambda u: False, n_grid=41)
    r = S.compute(T)
    assert r["stop_after"] == 36 and r["proposals"] == []       # the 36-point cap
    assert S.compute({**T, "stage": "finalist"})["search_complete"] is True


def test_rs_not_fit_gives_no_proposals_and_none_fields():
    r = res("rs_not_fit")
    assert r["rs_not_fit"] is True and r["fit"]["rank"] < 9 and r["fit"]["downforce"]["coef"] is None and r["fit"]["cond"] is None and r["rs_fit_poor"] is False
    assert r["u_star_1"] is None and r["y_star_1"] is None and r["pool_limited_pre"] is False and r["gated"] == [] and r["proposals"] == []
    assert all(t["u_star"] is None for t in r["targets"].values()) and len(r["data_loss"]) == 16


def test_rs_loss_rows():
    one = res("rs_one_kernel_lost")                # one G1 kernel lost: every state has P = 1, the fit still runs
    T = Y.branch("rs_one_kernel_lost")
    V, _ = S.valid_runs(T)
    assert not one["rs_not_fit"] and all(e["downforce"]["P"] == 1 for e in S.fit_stage(T, V)["est"].values()) and T["lost_kernels"] == ["g1k12"]
    both = res("rs_both_kernels_lost")
    assert both["rs_not_fit"] and both["fit"]["rank"] == 0
    pt = res("rs_lost_point")                      # a point is dropped when both phases are lost; 14 points still give rank 9
    T = Y.branch("rs_lost_point")
    V, loss = S.valid_runs(T)
    assert not pt["rs_not_fit"] and len(S.fit_stage(T, V)["points"]) == 14 and len(loss) == 2
    two = res("rs_lost_both_phases_two_points")    # null forces
    assert not two["rs_not_fit"] and len(two["data_loss"]) == 4


def test_rs_fit_poor_and_weak_surface_and_no_feasible_target():
    assert res("rs_fit_poor")["rs_fit_poor"] is True and res("rs_noisy")["rs_fit_poor"] is False
    assert res("rs_weak")["pool_limited_pre"] is False
    r = res("rs_no_feasible_target")
    assert not r["rs_not_fit"] and r["gated"] == [] and r["proposals"] == [] and r["y_star_1"] is None and all(t["u_star"] is None for t in r["targets"].values())


def test_gating_record_inconsistent_with_propose_is_refused():
    T = Y.branch("rs_base")
    bad = copy.deepcopy(T)
    bad["gating"][0]["name"] = "v18__other"
    with pytest.raises(ValueError, match="not the point propose"):
        S.compute(bad)
    short = copy.deepcopy(T)
    short["gating"].pop()
    with pytest.raises(ValueError, match="gates more points"):
        S.compute(short)
    extra = copy.deepcopy(T)
    extra["gating"].append(dict(T["gating"][-1]))
    with pytest.raises(ValueError, match="does not gate"):
        S.compute(extra)
    nofit = Y.branch("rs_not_fit")
    nofit["gating"] = [dict(T["gating"][0])]
    with pytest.raises(ValueError, match="not fit"):
        S.compute(nofit)


# ---- §5.4 finalist, futility, search_complete ----------------------------------------------------------------------------------------------------
def test_finalist_is_the_feasible_candidate_with_the_largest_downforce():
    T = Y.branch("fin_base")
    r = S.compute(T)
    c = r["candidates"]
    feas = {n: v["delta_bar"]["downforce"] for n, v in c.items() if v["feasible"]}
    assert r["finalist"] == max(feas, key=feas.get) and T["roles"][r["finalist"]]["role"] == "proposal"
    assert r["K_opt"] == 19 == len(c) == r["K_rand"] and r["search_complete"] is True and r["pool_limited"] is False and r["futility"] is None
    assert all(v["feasible"] == (v["delta_bar"]["drag"] <= 0) and v["P"] == 2 for v in c.values())
    assert r["proposals_from_gating"] == S.names(T["roles"], "proposal") and r["r_best"] in S.names(T["roles"], "random")


def test_exact_ties_go_to_the_registered_order():
    T = Y.branch("fin_tie_axial_design")
    assert S.compute(T)["finalist"] == S.names(T["roles"], "axial")[0]          # axial before design
    T = Y.branch("fin_tie_design_design")
    assert S.compute(T)["finalist"] == S.names(T["roles"], "design")[2]         # freeze order inside a role
    # the axial order: mode order, + before -
    assert [T["roles"][n]["u"] for n in S.names(T["roles"], "axial")] == [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    cands = {"a": {"feasible": True, "delta_bar": {"downforce": 0.02}}, "b": {"feasible": True, "delta_bar": {"downforce": 0.02}}, "c": {"feasible": False, "delta_bar": {"downforce": 0.09}}}
    roles = {"a": {"role": "proposal", "order": 0}, "b": {"role": "design", "order": 8}, "c": {"role": "axial", "order": 0}}
    assert S.pick(cands, roles) == "b" and S.pick({"c": cands["c"]}, roles) is None


def test_futility_both_causes_and_no_proposals_case():
    r = res("fin_no_feasible")
    assert r["finalist"] is None and r["futility"] == "NO_FEASIBLE_CANDIDATE" and r["selected_before_futility"] is None and r["search_complete"] is True
    r = res("fin_gain_below_min_at_selection")
    assert r["finalist"] is None and r["futility"] == "GAIN_BELOW_MIN_AT_SELECTION" and r["selected_before_futility"] is not None
    best = r["candidates"][r["selected_before_futility"]]
    assert best["delta_bar"]["downforce"] < S.X_STAR - 3 * best["se_eff"]["downforce"]
    r = res("fin_no_proposals")
    assert r["proposals_from_gating"] == [] and r["search_complete"] is True and r["K_opt"] == 15


def test_futility_is_the_3se_lower_edge_not_the_point_estimate():
    edge = S.X_STAR - 3 * S.FLOOR["downforce"] / math.sqrt(2)               # P = 2 equal phases: SE_eff = floor / sqrt(2)

    def run_with(df):
        return S.compute(Y.make("finalist", by=Y._weak(0.1), n_grid=41, edits={"g2": lambda T, al: Y.set_delta(T, "g2", al.proposals[0], None, ddf=df, ddr=-1e-3)}))
    kept = run_with(edge + 1e-6)
    assert kept["futility"] is None and kept["finalist"] == kept["proposals_from_gating"][0]                # below g_min J but within 3 SE_eff: kept
    assert run_with(edge - 1e-6)["futility"] == "GAIN_BELOW_MIN_AT_SELECTION"


def test_search_complete_rows():
    assert res("fin_base")["search_complete"] is True
    g2 = res("fin_g2_lost")                                                  # G2 lost: the finalist comes from the measured states, the study continues
    assert g2["search_complete"] is False and g2["incomplete_causes"] == ["DATA_G2"] and g2["finalist"] is not None
    assert sum(c["P"] == 0 for c in g2["candidates"].values()) == 4 and len(g2["candidates"]) == 19          # lost candidates are listed with P = 0
    weak = res("fin_g2_lost_weak")
    assert weak["finalist"] is None and weak["incomplete_causes"] == ["DATA_G2"]
    assert res("fin_one_proposal_phase_lost")["incomplete_causes"] == ["DATA_G2"]
    assert res("fin_g1_state_phase_lost")["incomplete_causes"] == ["DATA_G1"]
    assert res("fin_g1_kernel_lost")["incomplete_causes"] == ["DATA_G1"]
    assert res("fin_random_lost")["search_complete"] is True                  # R and M state-phases have no effect (§5.9)


def test_pool_limited_r_best_and_k_labels():
    assert res("fin_pool_limited")["pool_limited"] is True and res("fin_base")["pool_limited"] is False
    r = res("fin_random_none_feasible")
    assert r["r_best"] is None and r["finalist"] is not None
    k = res("fin_k_mismatch")
    assert (k["K_opt"], k["K_rand"]) == (19, 18)


def test_roles_must_match_the_proposals_of_the_gating_record():
    T = Y.branch("fin_base")
    bad = copy.deepcopy(T)
    del bad["roles"][S.names(bad["roles"], "proposal")[0]]
    with pytest.raises(ValueError, match="proposal states differ"):
        S.compute(bad)


# ---- §5.8 every step and §5.9 every row -----------------------------------------------------------------------------------------------------------
OUTCOMES = {
    "main_gain": ("SCREEN01_GAIN", []),
    "main_gain_noisy": ("SCREEN01_GAIN", []),
    "main_gain_f48_one_kernel": ("SCREEN01_GAIN", []),                     # §5.9: one f48 kernel lost, |Phi_48| = 1 continues
    "main_continue_g2_lost": ("SCREEN01_GAIN", []),                        # §5.9: G2 lost but a finalist among the measured states
    "main_gain_drift": ("SCREEN01_GAIN", []),
    "main_gain_no_manual": ("SCREEN01_GAIN", []),
    "main_gain_drag_unresolved": ("SCREEN01_GAIN", []),
    "main_random_beats_opt": ("SCREEN01_GAIN", []),
    "main_manual_beats_opt": ("SCREEN01_GAIN", []),
    "main_random_fails_g": ("SCREEN01_GAIN", []),
    "main_random_no_feasible": ("SCREEN01_GAIN", []),
    # step 1
    "main_incomplete_no_parent_g1": ("SCREEN01_INCOMPLETE", ["DATA_G1"]),
    "main_incomplete_no_nc_g1": ("SCREEN01_INCOMPLETE", ["DATA_G1"]),      # §5.9: NC lost at both phases
    # step 2
    "main_invalid_nc_g1": ("SCREEN01_INVALID", ["NC_G1"]),
    "main_invalid_nondeterminism_g1": ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"]),
    # step 3
    "main_no_gain_no_feasible": ("SCREEN01_NO_GAIN", ["NO_FEASIBLE_CANDIDATE"]),
    "main_no_gain_futility_gain": ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN_AT_SELECTION"]),
    "main_incomplete_g1_kernel": ("SCREEN01_INCOMPLETE", ["DATA_G1"]),     # §5.9: a G1 kernel lost, NO_GAIN becomes INCOMPLETE
    "main_incomplete_refine": ("SCREEN01_INCOMPLETE", ["DATA_REFINE"]),    # §5.9: RS_NOT_FIT from state-phase loss
    "main_incomplete_g2": ("SCREEN01_INCOMPLETE", ["DATA_G2"]),            # §5.9: G2 lost, no finalist among the measured states
    # step 4
    "main_incomplete_f32_kernel": ("SCREEN01_INCOMPLETE", ["DATA_F"]),     # |Phi_s| = 2
    "main_incomplete_f48_both": ("SCREEN01_INCOMPLETE", ["DATA_F"]),
    "main_incomplete_nc_f": ("SCREEN01_INCOMPLETE", ["DATA_F"]),
    "main_incomplete_f_not_run": ("SCREEN01_INCOMPLETE", ["BUDGET"]),                 # F never run and not declared lost: the §4.3 budget stop
    # step 5
    "main_invalid_nc_f": ("SCREEN01_INVALID", ["NC_F"]),
    "main_invalid_nondeterminism_f32a": ("SCREEN01_INVALID", ["NONDETERMINISM_F32A"]),
    # step 6
    "main_no_gain_below_min": ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN"]),
    "main_no_gain_drag": ("SCREEN01_NO_GAIN", ["DRAG_VIOLATION"]),
    "main_no_gain_drag_unresolved": ("SCREEN01_NO_GAIN", ["DRAG_VIOLATION"]),
    "main_no_gain_sign_split": ("SCREEN01_NO_GAIN", ["GRID_SIGN_SPLIT"]),
    "main_no_gain_all_three": ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN", "DRAG_VIOLATION", "GRID_SIGN_SPLIT"]),
    # step 7
    "main_inconclusive_g": ("SCREEN01_INCONCLUSIVE", ["G_UNRESOLVED"]),
    "main_inconclusive_r3": ("SCREEN01_INCONCLUSIVE", ["R3_UNRESOLVED"]),
}


@pytest.mark.parametrize("name", list(OUTCOMES))
def test_outcome_and_cause_per_branch(name):
    r = res(name)
    assert (r["outcome"], r["cause"]) == OUTCOMES[name]


OUTCOMES_PARTIAL = {
    "main_both_g1_kernels_lost": ("SCREEN01_INCOMPLETE", ["DATA_G1"]),                      # §5.9: both G1 kernels lost, nothing to fit
    "main_nondeterminism_drag_only_g1": ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"]),
    "main_nondeterminism_drag_only_f32a": ("SCREEN01_INVALID", ["NONDETERMINISM_F32A"]),
    "main_drift_drag_only": ("SCREEN01_GAIN", []),
    "main_repeat_missing": ("SCREEN01_GAIN", []),
    "main_nc_g1_one_phase": ("SCREEN01_GAIN", []),
    "main_nc_f_one_phase": ("SCREEN01_GAIN", []),
    "main_f32_three_phases": ("SCREEN01_GAIN", []),
    "main_f32_both_kernels_lost": ("SCREEN01_INCOMPLETE", ["DATA_F"]),
    "main_budget_f32b_not_run": ("SCREEN01_INCOMPLETE", ["BUDGET"]),
    "main_budget_and_lost": ("SCREEN01_INCOMPLETE", ["BUDGET"]),
    "main_f48_one_phase_lost_data": ("SCREEN01_GAIN", []),
    "main_rbest_single_phase": ("SCREEN01_GAIN", []),                                       # R / M state-phases: no effect on the outcome
    "main_manual_missing_in_f": ("SCREEN01_GAIN", []),
    "main_d_zero_drag": ("SCREEN01_GAIN", []),
    "main_r3_ratio_out_of_band": ("SCREEN01_GAIN", []),                                     # labels only
    "main_r3_e2_exceeded_only": ("SCREEN01_GAIN", []),
    "main_g_resolved_edge": ("SCREEN01_GAIN", []),
}


@pytest.mark.parametrize("name", list(OUTCOMES_PARTIAL))
def test_outcome_and_cause_partial_data_branches(name):
    r = res(name)
    assert (r["outcome"], r["cause"]) == OUTCOMES_PARTIAL[name]


def test_partial_data_labels_and_blocks():
    r = res("main_f32_both_kernels_lost")                                                   # R3 needs flow_48 only; G, D, selection_bias need |Phi_s| >= 3
    assert r["G"] is None and r["D"] is None and r["selection_bias"] is None and r["R3"]["label"] == "R3_CONFIRMED" and r["confirmation"]["f32"] is None
    assert r["R3"]["R3_RATIO_IN_BAND"] is None and r["NC"]["f32"] == {"z": None, "label": None}
    r = res("main_f32_three_phases")
    assert r["confirmation"]["f32"]["P"] == 3 and r["G"]["decision"] == "PASS"
    r = res("main_nc_f_one_phase")
    assert r["NC"]["f32"]["label"] == "CONSISTENT" and res("main_nc_g1_one_phase")["NC"]["g1"]["label"] == "CONSISTENT"
    r = res("main_f48_one_phase_lost_data")
    assert r["confirmation"]["f48"]["P"] == 1 and r["confirmation"]["f48"]["se_eff"]["downforce"] == S.FLOOR["downforce"]
    assert res("main_d_zero_drag")["D"] == {"decision": "PASS", "label": "PASS_UNRESOLVED"}
    r3 = res("main_r3_ratio_out_of_band")["R3"]
    assert r3["R3_RATIO_IN_BAND"] is False and r3["R3_E2_EXCEEDED"] is True
    r3 = res("main_r3_e2_exceeded_only")["R3"]
    assert r3["R3_RATIO_IN_BAND"] is True and r3["R3_E2_EXCEEDED"] is True and r3["R3_DRAG_SAME_SIGN"] is False
    assert res("main_rbest_single_phase")["controls"]["OPT_VS_RANDOM"] == "OPT_RANDOM_UNRESOLVED" and res("main_rbest_single_phase")["controls"]["RANDOM_FEASIBLE_GAIN"] is False
    assert res("main_manual_missing_in_f")["controls"]["OPT_VS_MANUAL"] == "OPT_MANUAL_UNRESOLVED"
    assert res("main_drift_drag_only")["generation_drift"]["drift"] is True and res("main_nondeterminism_drag_only_g1")["determinism"]["g1k11"]["nondeterminism"] is True
    assert res("main_repeat_missing")["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": False}
    r = res("main_both_g1_kernels_lost")
    assert r["controls"]["OPT_VS_RANDOM"] is None and r["controls"]["K_MISMATCH"] is True and r["confirmation"] == {"f32": None, "f48": None} and r["NC"]["g1"]["label"] is None


def test_finalist_edge_and_partial_branches():
    r = res("fin_futility_edge_kept")
    assert r["futility"] is None and r["finalist"] == r["proposals_from_gating"][0]
    assert res("fin_futility_edge_dropped")["futility"] == "GAIN_BELOW_MIN_AT_SELECTION"
    T = Y.branch("fin_proposal_single_phase")
    r = S.compute(T)
    ps = S.names(T["roles"], "proposal")
    assert [r["candidates"][n]["P"] for n in ps[:2]] == [1, 1] and r["search_complete"] is False and r["incomplete_causes"] == ["DATA_G2"]
    assert r["candidates"][ps[0]]["se_eff"]["downforce"] == S.FLOOR["downforce"]                       # P = 1: the floor
    T = Y.branch("fin_random_tie")
    assert S.compute(T)["r_best"] == S.names(T["roles"], "random")[1]                                  # tie between random 1 and 3: the lower order
    T = Y.branch("fin_implausible_candidate")
    r = S.compute(T)
    assert r["candidates"][S.names(T["roles"], "axial")[2]]["P"] == 0 and any("@g1@" in x for x in r["data_loss"]) and r["incomplete_causes"] == ["DATA_G1"]
    r = res("fin_both_g1_kernels_lost")
    assert r["finalist"] is None and r["futility"] == "NO_FEASIBLE_CANDIDATE" and r["incomplete_causes"] == ["DATA_G1"] and r["search_complete"] is False


def test_every_registered_branch_computes():
    for name in Y.BRANCHES:
        assert set(S.CMP[Y.BRANCHES[name][0]]) <= set(res(name))


def test_evaluation_order_first_match_wins():
    T = Y.branch("main_gain")
    f = S.compute(T)["finalist"]
    # step 2 before 3-8: an inconsistent G1 NC beats everything after it, even a failing G rule
    Y.set_delta(T, "g1", Y.ROLL, "11", 5e-3)
    Y.set_delta(T, "f32", f, None, 0.001)
    assert S.compute(T)["outcome"] == "SCREEN01_INVALID"
    # step 4 before step 5: too few confirmation phases is INCOMPLETE even with an inconsistent F-stage NC
    T = Y.branch("main_gain")
    Y.lose(T, "f32b")
    Y.set_delta(T, "f32", Y.ROLL, None, 5e-3)
    assert S.compute(T)["outcome"] == "SCREEN01_INCOMPLETE"
    # step 6 before step 7: a drag violation beats an unresolved G
    T = Y.make("main", edits={"f": Y._chain(Y._f(df32=[0.0195, -0.0045, 0.0195, -0.0045], dr32=[3e-3] * 4))}, n_grid=41)
    assert S.compute(T)["outcome"] == "SCREEN01_NO_GAIN" and S.compute(T)["cause"] == ["DRAG_VIOLATION"]
    # a lost f48 kernel pair gives R3 nothing to judge even when G fails: step 4 first
    T = Y.make("main", edits={"f": Y._chain(Y._f(df32=0.001), lambda T, al: (Y.lose(T, "f48k13"), Y.lose(T, "f48k14")))}, n_grid=41)
    assert S.compute(T)["outcome"] == "SCREEN01_INCOMPLETE"


def test_confirmation_needs_at_least_three_phases_for_the_finalist():
    T = Y.branch("main_gain")
    f = S.compute(T)["finalist"]
    Y.drop(T, "f32", f, "16")
    assert S.compute(T)["outcome"] == "SCREEN01_GAIN"                         # |Phi_s| = 3 suffices
    Y.drop(T, "f32", f, "15")
    r = S.compute(T)
    assert r["outcome"] == "SCREEN01_INCOMPLETE" and r["cause"] == ["DATA_F"]


def test_data_loss_in_confirmation_runs_reduces_the_phase_set():
    T = Y.branch("main_gain")
    f = S.compute(T)["finalist"]
    Y.set_run(T, "f32", f, "13", ok=False)
    Y.set_run(T, "f32", f, "14", downforce=None)
    r = S.compute(T)
    assert r["outcome"] == "SCREEN01_INCOMPLETE" and {f"{f}@f32@13", f"{f}@f32@14"} <= set(r["data_loss"])
    T = Y.branch("main_gain")
    Y.set_run(T, "f32", f, "13", downforce=T["runs"]["f32"][Y.PARENT]["13"]["downforce"] * 1.3)   # implausible: 30 % above the parent
    r = S.compute(T)
    assert f"{f}@f32@13" in r["data_loss"] and r["confirmation"]["f32"]["P"] == 3 and r["outcome"] == "SCREEN01_GAIN"


# ---- G, D, R3 labels -----------------------------------------------------------------------------------------------------------------------------
def est_dict(d, se, p=4):
    return {r: {"delta_bar": d if r == "downforce" else d, "se_eff": se, "P": p, "sigma_d": None} for r in S.RESP}


def test_g_rule_pass_unresolved_fail_and_resolved_label():
    x = S.X_STAR
    assert S.g_rule(est_dict(x, 1e-4)) == {"decision": "PASS", "GAIN_RESOLVED_ABOVE_MIN": False}     # >= g_min J exactly, and > 3 SE
    assert S.g_rule(est_dict(x + 1e-3, 1e-4))["GAIN_RESOLVED_ABOVE_MIN"] is True
    assert S.g_rule(est_dict(x - 1e-12, 1e-4))["decision"] == "FAIL"
    assert S.g_rule(est_dict(x + 1e-6, 3e-3))["decision"] == "UNRESOLVED"                             # >= g_min J but within 3 SE
    assert S.g_rule(est_dict(3e-3 + 1e-9, 1e-3))["decision"] == "FAIL"                                # below g_min J whatever the SE
    d = x + S.tcrit(4) * 1e-4
    assert S.g_rule(est_dict(d + 1e-9, 1e-4))["GAIN_RESOLVED_ABOVE_MIN"] is True and S.g_rule(est_dict(d - 1e-9, 1e-4))["GAIN_RESOLVED_ABOVE_MIN"] is False


def test_d_rule_four_labels_and_point_sign_decision():
    t = S.tcrit(4)
    lab = lambda d: S.d_rule(est_dict(d, 1e-3))   # noqa: E731
    assert lab(-0.01) == {"decision": "PASS", "label": "PASS_RESOLVED"}
    assert lab(-1e-3) == {"decision": "PASS", "label": "PASS_UNRESOLVED"}
    assert lab(0.0) == {"decision": "PASS", "label": "PASS_UNRESOLVED"}
    assert lab(1e-3) == {"decision": "VIOLATION", "label": "VIOLATION_UNRESOLVED"}
    assert lab(t * 1e-3 + 1e-9) == {"decision": "VIOLATION", "label": "VIOLATION_RESOLVED"}
    assert lab(-t * 1e-3 + 1e-9)["label"] == "PASS_UNRESOLVED" and lab(-t * 1e-3)["label"] == "PASS_RESOLVED"
    for name, label in (("main_gain", "PASS_RESOLVED"), ("main_gain_drag_unresolved", "PASS_UNRESOLVED"), ("main_no_gain_drag_unresolved", "VIOLATION_UNRESOLVED"),
                        ("main_no_gain_drag", "VIOLATION_RESOLVED")):
        assert res(name)["D"]["label"] == label


def test_r3_labels_and_secondary_labels():
    r = res("main_gain")["R3"]
    assert r["label"] == "R3_CONFIRMED" and r["R3_RATIO_IN_BAND"] is True and r["G48_ABOVE_MIN"] is True and r["R3_E2_EXCEEDED"] is False and r["R3_DRAG_SAME_SIGN"] is True
    assert res("main_no_gain_sign_split")["R3"]["label"] == "R3_SIGN_SPLIT"
    assert res("main_inconclusive_r3")["R3"]["label"] == "R3_UNRESOLVED"
    f32 = res("main_gain")["confirmation"]["f32"]["delta_bar"]["downforce"]

    def r3(df48=None, dr48=None):
        return S.compute(Y.make("main", edits={"f": Y._f(df48=df48, dr48=dr48)}, n_grid=41))["R3"]
    far = r3(df48=0.7 * f32)                                                  # ratio out of band, E2 exceeded (|d48 - d32| = 0.3 * 0.02 = 6e-3 > 1.807e-3)
    assert far["label"] == "R3_CONFIRMED" and far["R3_RATIO_IN_BAND"] is False and far["R3_E2_EXCEEDED"] is True
    near = r3(df48=f32 - 1.0e-3)                                              # ratio 0.95, |diff| 1e-3 < E2
    assert near["R3_RATIO_IN_BAND"] is True and near["R3_E2_EXCEEDED"] is False
    assert r3(df48=0.005)["G48_ABOVE_MIN"] is False and r3(df48=0.005)["G48_MARGIN"] < 0
    assert r3(dr48=+2e-3)["R3_DRAG_SAME_SIGN"] is False
    assert r3(df48=-1e-9)["label"] == "R3_SIGN_SPLIT" and r3(df48=0.0)["label"] == "R3_SIGN_SPLIT"      # the point sign decides, <= 0 is a split


def test_r3_confirmed_threshold_and_single_phase_floor():
    f = S.compute(Y.branch("main_gain"))["finalist"]
    floor = S.FLOOR["downforce"]
    for d, label in ((3 * floor / math.sqrt(2) + 1e-7, "R3_CONFIRMED"), (3 * floor / math.sqrt(2) - 1e-7, "R3_UNRESOLVED")):
        T = Y.branch("main_gain")
        Y.set_delta(T, "f48", f, None, d)
        assert S.compute(T)["R3"]["label"] == label                          # P = 2, equal phases: SE_eff = floor / sqrt(2)
    T = Y.branch("main_gain")
    Y.lose(T, "f48k14")
    Y.set_delta(T, "f48", f, None, 3 * floor + 1e-7)
    r = S.compute(T)
    assert r["confirmation"]["f48"]["P"] == 1 and r["confirmation"]["f48"]["se_eff"]["downforce"] == floor and r["R3"]["label"] == "R3_CONFIRMED"


# ---- NC, determinism, drift ---------------------------------------------------------------------------------------------------------------------
def test_nc_z_boundary_at_3p5():
    for n in (1, 2, 4):
        sd = math.hypot(S.NC_FLOOR / math.sqrt(n), S.NC_SE)
        ph = [str(11 + i) for i in range(n)]
        for sign in (+1, -1):
            for k, label in ((3.5 * (1 - 1e-6), "CONSISTENT"), (3.5 * (1 + 1e-6), "NOT_CONSISTENT")):
                T = tiny({Y.PARENT: {p: run(1.0, 1.0) for p in ph}, Y.ROLL: {p: run(1.0 + S.NC_REF + sign * k * sd, 1.0) for p in ph}})
                nc = S.nc_stage(T, S.valid_runs(T)[0], "g1")
                assert nc["label"] == label and abs(nc["z"] - k) < 1e-6
    T = tiny({Y.PARENT: {p: run(1.0, 1.0) for p in ("11", "12")}, Y.ROLL: {p: run(1.0 + S.NC_REF, 1.0) for p in ("11", "12")}})
    assert S.nc_stage(T, S.valid_runs(T)[0], "g1")["z"] < 1e-9
    assert S.nc_stage(tiny({Y.PARENT: {"11": run(1.0)}}), {"g1": {Y.PARENT: {"11": (1.0, 0.0)}}}, "g1") == {"z": None, "label": None}


def test_nondeterminism_and_generation_drift():
    r = res("main_invalid_nondeterminism_g1")
    assert r["determinism"]["g1k11"]["nondeterminism"] is True and r["outcome"] == "SCREEN01_INVALID"
    r = res("main_invalid_nondeterminism_f32a")
    assert r["determinism"]["f32a"]["nondeterminism"] is True and r["determinism"]["g1k11"]["nondeterminism"] is False
    T = Y.branch("main_gain")
    Y.set_delta(T, "g1", Y.REPEAT, "11", 0.999 * S.REPEAT_TOL, -0.999 * S.REPEAT_TOL)       # within the downforce floor (both responses): reproduced
    assert S.compute(T)["determinism"]["g1k11"]["nondeterminism"] is False
    Y.set_delta(T, "g1", Y.REPEAT, "11", 0.0, 1.001 * S.REPEAT_TOL)            # drag is judged too
    d = S.compute(T)["determinism"]["g1k11"]
    assert d["nondeterminism"] is True and d["max_abs_diff"]["downforce"] == 0.0 and d["max_abs_diff"]["drag"] > S.REPEAT_TOL
    Y.set_run(T, "g1", Y.REPEAT, "11", downforce=T["runs"]["g1"][Y.PARENT]["11"]["downforce"] * 1.4, drag=T["runs"]["g1"][Y.PARENT]["11"]["drag"])
    r = S.compute(T)                                                           # implausible repeat: still NONDETERMINISM (judged on raw finite runs), and listed as lost
    assert r["determinism"]["g1k11"]["nondeterminism"] is True and f"{Y.REPEAT}@g1@11" in r["data_loss"]
    Y.drop(T, "g1", Y.REPEAT)
    r = S.compute(T)
    assert r["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": False} and r["outcome"] == "SCREEN01_GAIN"     # not measured: no verdict
    d = res("main_gain_drift")
    assert d["generation_drift"]["drift"] is True and d["outcome"] == "SCREEN01_GAIN" and res("main_gain")["generation_drift"]["drift"] is False
    T = Y.branch("main_gain")
    T["runs"]["f32"][Y.PARENT]["11"]["downforce"] = T["runs"]["g1"][Y.PARENT]["11"]["downforce"] + 0.999 * S.REPEAT_TOL
    assert S.compute(T)["generation_drift"]["drift"] is False
    T["runs"]["f32"][Y.PARENT]["11"]["drag"] = T["runs"]["g1"][Y.PARENT]["11"]["drag"] - 1.001 * S.REPEAT_TOL
    assert S.compute(T)["generation_drift"]["drift"] is True
    Y.drop(T, "f32", Y.PARENT, "11")
    assert S.compute(T)["generation_drift"] == {"max_abs_diff": None, "drift": False}


# ---- controls, K, amplitude, selection-bias statement --------------------------------------------------------------------------------------------
def test_control_labels():
    c = res("main_gain")["controls"]
    assert c == {"OPT_VS_RANDOM": "OPT_BEATS_RANDOM", "OPT_VS_MANUAL": "OPT_BEATS_MANUAL", "RANDOM_FEASIBLE_GAIN": True, "K_MISMATCH": False}
    assert res("main_random_beats_opt")["controls"]["OPT_VS_RANDOM"] == "RANDOM_BEATS_OPT"
    assert res("main_manual_beats_opt")["controls"]["OPT_VS_MANUAL"] == "MANUAL_BEATS_OPT"
    assert res("main_gain_no_manual")["controls"]["OPT_VS_MANUAL"] == "MANUAL_NONE"
    r = res("main_random_no_feasible")["controls"]
    assert r["OPT_VS_RANDOM"] == "RANDOM_NO_FEASIBLE" and r["RANDOM_FEASIBLE_GAIN"] is False
    assert res("main_random_fails_g")["controls"]["RANDOM_FEASIBLE_GAIN"] is False
    unres = S.compute(Y.make("main", edits={"f": Y._f(df32=[0.03, 0.01, 0.03, 0.01], who="rbest")}, n_grid=41))["controls"]["OPT_VS_RANDOM"]
    assert unres in ("OPT_RANDOM_UNRESOLVED", "OPT_BEATS_RANDOM", "RANDOM_BEATS_OPT")
    T = Y.branch("main_gain")
    rb = S.compute(T)["r_best"]
    f = S.compute(T)["finalist"]
    for ph, (a, b) in zip(("13", "14", "15", "16"), ((0.02, 0.0), (0.0, 0.02), (0.02, 0.0), (0.0, 0.02))):   # e_k = +-0.02: mean 0, SE 0.0115: unresolved
        Y.set_delta(T, "f32", f, ph, ddf=a + 0.02)
        Y.set_delta(T, "f32", rb, ph, ddf=b + 0.02)
    assert S.compute(T)["controls"]["OPT_VS_RANDOM"] == "OPT_RANDOM_UNRESOLVED"
    Y.drop(T, "f32", rb, "14"), Y.drop(T, "f32", rb, "15"), Y.drop(T, "f32", rb, "16")      # a single common phase cannot resolve
    assert S.compute(T)["controls"]["OPT_VS_RANDOM"] == "OPT_RANDOM_UNRESOLVED"
    assert res("fin_k_mismatch")["K_rand"] == 18
    assert S.compute(Y.make("main", n_random=18, n_grid=41))["controls"]["K_MISMATCH"] is True


def test_amplitude_mismatch_label_and_exploration_controls():
    d = res("main_gain")["detail"]
    assert set(d["amplitude_median_u_inf"]) == {"opt", "random"} and isinstance(d["AMPLITUDE_MISMATCH"], bool)
    assert d["exploration_controls"]["OPT_VS_RANDOM"] in ("OPT_BEATS_RANDOM", "RANDOM_BEATS_OPT", "OPT_RANDOM_UNRESOLVED")


def test_expected_maximum_of_standard_normals():
    assert abs(S.e_max_normals(19) - 1.8445) < 5e-4 and abs(S.e_max_normals(1)) < 1e-12 and math.isclose(S.e_max_normals(2), 1 / math.sqrt(math.pi), rel_tol=1e-10)
    rng = np.random.default_rng(0)
    assert abs(S.e_max_normals(15) - rng.standard_normal((200000, 15)).max(1).mean()) < 0.01


def test_selection_bias_statement_and_margin_boundaries():
    r = res("main_gain")
    sb, k = r["selection_bias"], r["K_opt"]
    assert k == 19 and math.isclose(r["detail"]["E_max_K"], S.e_max_normals(19), rel_tol=1e-12)
    sb["E_max_K"] = r["detail"]["E_max_K"]
    assert math.isclose(sb["b_K"]["central"], sb["E_max_K"] * 5.61e-4, rel_tol=1e-12) and math.isclose(sb["b_K"]["upper"], sb["E_max_K"] * 1.4474126675928642e-3, rel_tol=1e-12)
    i_s = r["confirmation"]["f32"]["delta_bar"]["downforce"] / S.J_B48
    assert math.isclose(sb["g_XV_exp"]["central"], 0.655 * (i_s - sb["b_K"]["central"] / S.J_B48), rel_tol=1e-12)
    assert math.isclose(sb["g_XV_exp"]["pessimistic"], 0.57 * (i_s - sb["b_K"]["upper"] / S.J_B48), rel_tol=1e-12)
    emax = S.e_max_normals(19)
    cb = S.XV_FLOOR / 0.655 + emax * 5.61e-4 / S.J_B48                          # central boundary I_s = 2.32 %
    pb = S.XV_FLOOR / 0.57 + emax * 1.4474126675928642e-3 / S.J_B48            # pessimistic 3.23 %
    assert abs(cb - 0.0232) < 5e-5 and abs(pb - 0.0323) < 5e-5
    f = r["finalist"]

    def labels(i):
        T = Y.branch("main_gain")
        Y.set_delta(T, "f32", f, None, ddf=i * S.J_B48, ddr=-1e-3)
        Y.set_delta(T, "f48", f, None, ddf=i * S.J_B48)
        return S.compute(T)["selection_bias"]["XV_MARGIN"]
    assert labels(cb + 1e-6) == {"central": "XV_MARGIN_ADEQUATE", "pessimistic": "XV_MARGIN_THIN"}
    assert labels(cb - 1e-6)["central"] == "XV_MARGIN_THIN"
    assert labels(pb + 1e-6) == {"central": "XV_MARGIN_ADEQUATE", "pessimistic": "XV_MARGIN_ADEQUATE"}
    assert labels(pb - 1e-6)["pessimistic"] == "XV_MARGIN_THIN"
    d = r["detail"]
    assert math.isclose(d["placement_noise_bias_n"], r["candidates"][f]["delta_bar"]["downforce"] - r["confirmation"]["f32"]["delta_bar"]["downforce"])
    assert d["xv_drag_margin"]["interval_90_n"][0] < d["xv_drag_margin"]["delta_bar_drag_n"] < d["xv_drag_margin"]["interval_90_n"][1]
    k15 = S.compute(Y.branch("main_no_gain_no_feasible"))
    assert k15["selection_bias"] is None and k15["G"] is None                 # no finalist: nothing confirmed


def test_confirmation_estimates_use_only_the_confirmation_phases():
    r = res("main_gain_noisy")
    c = r["confirmation"]["f32"]
    assert c["P"] == 4 and r["confirmation"]["f48"]["P"] == 2 and c["sigma_d"]["downforce"] is not None
    assert r["determinism"]["f32a"]["nondeterminism"] is False
    T = Y.branch("main_gain")
    f = S.compute(T)["finalist"]
    assert sorted(T["runs"]["f32"][f]) == ["13", "14", "15", "16"] and "11" in T["runs"]["f32"][Y.PARENT]                       # the replay phase is the parent's only
    assert S.estimates(S.valid_runs(T)[0], "f32", f, Y.PARENT)["phases"] == ["13", "14", "15", "16"]


# ---- INCOMPLETE vs BUDGET, written outputs, loaders ---------------------------------------------------------------------------------------------------
def test_budget_decision_and_estimates(tmp_path):
    def log(name, wall):
        p = tmp_path / name
        p.write_text(json.dumps([{"stream_name": "stdout", "time": 1.0, "data": "x"}, {"stream_name": "stdout", "time": wall, "data": "y"}]))
        return str(p)
    ok = S.budget([("g1k11", log("a", 16000.0)), ("g1k12", log("b", 15000.0))], [("g2", None), ("f48k13", None), ("f48k14", None), ("f32a", None), ("f32b", None)])
    assert ok["decision"] == "go" and ok["T_s"] == 31000 + 4410 + 2 * 7280 + 5240 + 4410
    assert S.budget([], [(k, None) for k in S.REG_RUNS])["T_s"] == 61095                                          # the registered formal estimate
    stop = S.budget([("g1k11", log("c", 45000.0)), ("g1k12", log("d", 45000.0))], [("g2", None)])
    assert stop["decision"] == "stop" and stop["T_s"] == 90000 + 4410
    rest = [(k, None) for k in ("g2", "f48k13", "f48k14", "f32a", "f32b")]
    one = S.budget([("g1k11", log("e", 23300.0)), ("g1k12", log("f", 16030.0))], [("g1k11", None)] + rest)           # a failed first attempt at the timeout + its rerun: fits
    assert one["decision"] == "go" and one["T_s"] == 23300 + 16030 + 16445 + 4410 + 2 * 7280 + 5240 + 4410
    two = S.budget([("g1k11", log("g", 23300.0)), ("g1k12", log("h", 23300.0))], [("g1k11", None), ("g1k12", None)] + rest)
    assert two["decision"] == "stop"                                                                                 # two G1 reruns do not fit (§4.3)
    dup = S.budget([("g1k11", log("i", 100.0)), ("g1k11", log("j", 200.0))], [])
    assert dup["finished_session_wall_s"] == {"g1k11": 300.0}                                                        # attempts of one kernel are summed
    assert S.budget([], [("f48k13", 2)])["T_s"] == 2 * 2340 + 260
    with pytest.raises(ValueError, match="unknown kernel"):
        S.budget([], [("nope", None)])


def test_budget_cli_and_write_once(tmp_path, monkeypatch, capsys):
    p = tmp_path / "l.json"
    p.write_text(json.dumps([{"time": 100.0, "data": ""}]))
    monkeypatch.setattr(sys, "argv", ["x", "budget", "--finished", f"g1k11={p}", "--pending", "g1k12", "f48k13=2", "--out", str(tmp_path / "b.json")])
    S.main()
    out = json.loads((tmp_path / "b.json").read_text())
    assert out["decision"] == "go" and out["T_s"] == 100 + 38 * 415 + 260 + 2 * 2340 + 260
    with pytest.raises(FileExistsError):
        S.main()


def make_infra(tmp_path, done=False, error=None, complete_states=0, log="[]"):
    d = tmp_path / "out"
    d.mkdir(exist_ok=True)
    if done:
        (d / "DONE").write_text("")
    if error is not None:
        (d / "ERROR.txt").write_text(error)
    (d / "harness_index.json").write_text(json.dumps({"states": [{"complete": i < complete_states} for i in range(3)]}))
    lg = tmp_path / "k.log"
    lg.write_text(log)
    return d, lg


@pytest.mark.parametrize("kw,status,verify_failed,expected", [
    (dict(done=True), "", False, ("COMPLETE", None)),
    (dict(done=True), "", True, ("INFRA_LOSS", "VERIFY_FAILED")),
    (dict(), "", False, ("INFRA_LOSS", "SESSION_KILL")),
    (dict(error="RuntimeError: Pkg.instantiate failed"), "", False, ("INFRA_LOSS", "JULIA_INSTALL")),
    (dict(error="RuntimeError: Pkg.instantiate failed", complete_states=1), "", False, ("NOT_INFRASTRUCTURE", None)),   # not before any state
    (dict(error="RuntimeError: independent CUDA device UUID probe failed"), "", False, ("INFRA_LOSS", "GPU_IDENTITY")),
    (dict(error="RuntimeError: observed CUDA singleton/default UUID differs from selected physical GPU", complete_states=2), "", False, ("INFRA_LOSS", "GPU_IDENTITY")),
    (dict(error="ValueError: every visible worker GPU must be a Tesla T4"), "", False, ("INFRA_LOSS", "GPU_IDENTITY")),
    (dict(error="boom", log=json.dumps([{"data": "502 Bad Gateway"}])), "", False, ("INFRA_LOSS", "PLATFORM_ERROR")),
    (dict(error="boom"), "Service Unavailable", False, ("INFRA_LOSS", "PLATFORM_ERROR")),
    (dict(error="RuntimeError: registered per-state or aggregate solver wall-time budget exceeded"), "", False, ("NOT_INFRASTRUCTURE", None)),    # default
    (dict(error="RuntimeError: state did not complete: x (exit 1)", log="plain text log"), "", False, ("NOT_INFRASTRUCTURE", None)),
])
def test_infra_signature_table(tmp_path, kw, status, verify_failed, expected):
    d, lg = make_infra(tmp_path, **kw)
    r = S.classify_infra(d, lg, status, verify_failed)
    assert (r["classification"], r["signature"]) == expected


def test_infra_cli(tmp_path, monkeypatch, capsys):
    d, lg = make_infra(tmp_path, error="Pkg.instantiate failed")
    monkeypatch.setattr(sys, "argv", ["x", "infra", "--output-dir", str(d), "--log", str(lg)])
    S.main()
    assert json.loads(capsys.readouterr().out)["signature"] == "JULIA_INSTALL"


# ---- the harness-table loader --------------------------------------------------------------------------------------------------------------------
def build_campaign(tmp_path, cid, T, group, kernel_root, extra=None):
    """A minimal campaign JSON, per-kernel tables and the kernel files of the runs of one group of T."""
    km = Y.KERNEL_OF[group]
    out_prefix = f"{cid}_"
    c = {"campaign_id": cid, "out_prefix": out_prefix, "kernels": {}, **(extra or {})}
    tables = {}
    for k in sorted(set(km.values())):
        runs, forces = [], {}
        for s, by in T["runs"].get(group, {}).items():
            for ph, r in by.items():
                if km.get(ph) != k:
                    continue
                name = f"{s}__k{ph}"
                runs.append({"state": s, "name": name, "env": {}})
                d = kernel_root / f"{out_prefix}{k}" / "states" / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "flow_32.summary.json").write_text(json.dumps({"name": name, "k": k}))
                (d / "flow_32.forces.csv").write_text(f"{name},{r['downforce']}\n")
                forces[name] = {"downforce_n": r["downforce"], "drag_n": r["drag"], "forces_csv_sha256": SC.sha256_path(d / "flow_32.forces.csv"),
                                "summary_sha256": SC.sha256_path(d / "flow_32.summary.json"), "solver_process_wall_seconds": 400.0, "julia_summary_wall_seconds": 390.0}
        if runs:
            c["kernels"][k] = {"case": {"case_id": "flow_32"}, "runs": runs}
            tables[k] = forces
    path = tmp_path / "docs" / "harness" / f"{cid}_campaign.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(c, sort_keys=True))
    files = []
    for k, forces in tables.items():
        t = {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "smoke": False, "integrity": {"pass": True, "failures": []}, "campaign_id": cid,
             "campaign_sha256": SC.sha256_path(path), "state_forces_n": {k: forces}}
        tp = tmp_path / "tables" / f"{cid}_{k}.json"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(json.dumps(t))
        files.append(tp)
    return path, files, {"kind": "freeze", "file_sha256": {f"docs/harness/{path.name}": SC.sha256_path(path)}}


@pytest.fixture
def no_schema(monkeypatch):
    monkeypatch.setattr(SC, "validate_campaign", lambda c: None)


def test_loader_reads_verified_tables_and_checks_files_and_freeze(tmp_path, no_schema):
    T = Y.branch("fin_base")
    kr = tmp_path / "kernels"
    camp, tabs, fz = build_campaign(tmp_path, "screen01", T, "g1", kr)
    runs, meta = S.load_group("g1", camp, tabs, kr, [], fz)
    assert runs[Y.PARENT]["11"]["downforce"] == T["runs"]["g1"][Y.PARENT]["11"]["downforce"] and set(runs[Y.PARENT]) == {"11", "12"} and set(runs[Y.REPEAT]) == {"11"}
    assert meta["kernels_lost"] == [] and set(meta["table_sha256"]) == {t.name for t in tabs}
    with pytest.raises(ValueError, match="no verified table and are not declared lost"):
        S.load_group("g1", camp, tabs[:1], kr, [], fz)
    runs, meta = S.load_group("g1", camp, tabs[:1], kr, ["g1k12"], fz)
    assert meta["kernels_lost"] == ["g1k12"] and all(set(v) <= {"11"} for v in runs.values())
    with pytest.raises(ValueError, match="declared lost / budget-stopped but have"):
        S.load_group("g1", camp, tabs, kr, ["g1k12"], fz)
    S.load_group("g1", camp, tabs[:1], kr, [], fz, stopped=["g1k12"])                                  # a budget-stopped kernel needs no table
    with pytest.raises(ValueError, match="not the campaign frozen"):
        S.load_group("g1", camp, tabs, kr, [], {"kind": "freeze", "file_sha256": {"docs/harness/screen01_campaign.json": "0" * 64}})
    with pytest.raises(ValueError, match="is not a g2 campaign|not a"):
        S.load_group("f48", camp, tabs, kr, [], fz)
    d = kr / "screen01_g1k11" / "states" / f"{Y.PARENT}__k11" / "flow_32.forces.csv"
    d.write_text("tampered\n")
    with pytest.raises(ValueError, match="kernel output differs from the verified table"):
        S.load_group("g1", camp, tabs, kr, [], fz)
    with pytest.raises(ValueError, match="--kernel-root is required"):
        S.load_group("g1", camp, tabs, None, [], fz)


def test_loader_refuses_smoke_and_foreign_tables(tmp_path, no_schema):
    T = Y.branch("fin_base")
    kr = tmp_path / "kernels"
    camp, tabs, fz = build_campaign(tmp_path, "screen01", T, "g1", kr)
    t = json.loads(tabs[0].read_text())
    t["smoke"] = True
    tabs[0].write_text(json.dumps(t))
    with pytest.raises(ValueError, match="smoke"):
        S.load_group("g1", camp, tabs, kr, [], fz)
    t["smoke"], t["campaign_sha256"] = False, "0" * 64
    tabs[0].write_text(json.dumps(t))
    with pytest.raises(ValueError, match="another campaign"):
        S.load_group("g1", camp, tabs, kr, [], fz)


def test_restrict_and_group_tables():
    T = Y.branch("main_gain")
    r = S.restrict(T, "rs")
    assert r["stage"] == "rs" and set(r["runs"]) == {"g1"} and all(v["role"] != "proposal" for v in r["roles"].values())
    f = S.restrict(T, "finalist")
    assert set(f["runs"]) == {"g1", "g2"} and any(v["role"] == "proposal" for v in f["roles"].values())
    assert S.compute(r)["gated"] == S.compute(Y.branch("rs_base"))["gated"]
    T2 = Y.branch("main_continue_g2_lost")
    assert S.restrict(T2, "finalist")["lost_kernels"] == ["g2"] and S.restrict(T2, "rs")["lost_kernels"] == []


# ---- the whole pipeline on disk: rs -> finalist -> main (synthetic tables, kernel files, freezes, fake checker) ------------------------------------
class Disk:
    def __init__(self, tmp_path, monkeypatch, name="main_gain", checker=None):
        self.tmp, self.T = tmp_path, Y.branch(name)
        self.ev = tmp_path / "ev"
        self.ev.mkdir()
        monkeypatch.setattr(S, "EV", self.ev)
        monkeypatch.setattr(SC, "validate_campaign", lambda c: None)
        monkeypatch.setattr(S, "SOURCES", ("analyze_screen01.py", "screen01_pool.py"))
        monkeypatch.setattr(S, "CHECKER", checker or types.SimpleNamespace(check=lambda t: S.compute(t), compare=lambda a, b, stage: [k for k in a if S.canon(a[k]) != S.canon(b.get(k))]))
        self.kr = tmp_path / "kernels"
        states = {n: {"role": r["role"], "order": r["order"], "u": r["u"], "spec": None if r["u"] is None else P.u_to_spec(r["u"])} for n, r in self.T["roles"].items()
                  if r["role"] != "proposal"}
        self.states = self.ev / "states.json"
        self.states.write_text(json.dumps({"schema": "screen01-states-v1", "parent": Y.PARENT, "states": states}, sort_keys=True))
        self.camp, self.tabs, self.fz = {}, {}, {}
        fin = S.compute(self.T)
        ident = lambda n: {k: hashlib.sha256(f"{n}{k}".encode()).hexdigest() if k.endswith("sha256") else 0.1 for k in SC.STATE_IDENTITY_KEYS}   # noqa: E731
        extra32 = {"states": {Y.PARENT: {"kind": "parent", **ident("p")}, fin["finalist"]: {"kind": "candidate", "direction": "d1", "step_mm": 1.0, "sign": 1, **ident("f")}},
                   "directions": {"d1": {"path": "d1.raw", "sha256_fortran_raw": "a" * 64}}, "domain": {"flow_origin_m": [0, 0, 0], "physical_box_max_m": [1, 1, 1]},
                   "baseline": {"path": "b.raw", "sha256_fortran_raw": "b" * 64}}
        for g, cid in (("g1", "screen01"), ("g2", "screen01_g2"), ("f32", "screen01_f"), ("f48", "screen01_f48")):
            if g in self.T["runs"]:
                c, t, f = build_campaign(tmp_path, cid, self.T, g, self.kr, extra32 if g == "f32" else None)
                self.camp[g], self.tabs[g], self.fz[g] = c, t, f
        files = {f"scripts/screen01/{s}": SC.sha256_path(S.ROOT / "scripts/screen01" / s) for s in S.SOURCES}
        files[f"docs/evidence/x/{self.states.name}"] = SC.sha256_path(self.states)
        files["docs/gate_profile.json"] = "c" * 64
        self.write("freeze1", {"kind": "freeze1", "file_sha256": files})
        self.write("freeze2", {"kind": "freeze2", "file_sha256": self.fz["g1"]["file_sha256"]})
        self.args = argparse.Namespace(states=self.states, g1=[self.camp["g1"], *self.tabs["g1"]], g2=None, f32=None, f48=None, rs=self.ev / "rs.json", finalist=self.ev / "finalist.json",
                                       kernel_root=self.kr, lost=[], budget_stopped=[], workers=4, out=None)

    def write(self, name, rec):
        (self.ev / f"{name}.json").write_text(json.dumps(rec, sort_keys=True))

    def oracle(self, T, workers):
        rows = {}

        def ask(u):
            n = Y.sname(u)
            rows[n] = {"name": n, "admissible": bool(Y.default_oracle(u)), "gate_values": {"min_feature_width": 1.0}, "phi_fortran_sha256": hashlib.sha256(n.encode()).hexdigest()}
            return rows[n]["admissible"]
        return ask, rows

    def stage_rs(self):
        rec = S.run_rs(self.args, self.oracle)
        S.write_once(self.args.rs, S.dumps(rec))
        self.write("freeze2_1", {"kind": "freeze2_1", "file_sha256": self.fz["g2"]["file_sha256"] if "g2" in self.fz else {}, "rs_json_sha256": SC.sha256_path(self.args.rs)})
        return rec

    def stage_finalist(self):
        if "g2" in self.camp:
            self.args.g2 = [self.camp["g2"], *self.tabs["g2"]]
        rec = S.run_finalist(self.args)
        S.write_once(self.args.finalist, S.dumps(rec))
        f32 = self.fz.get("f32", {"file_sha256": {}})["file_sha256"] | self.fz.get("f48", {"file_sha256": {}})["file_sha256"]
        self.write("freeze3", {"kind": "freeze3", "file_sha256": f32, "finalist_json_sha256": SC.sha256_path(self.args.finalist)})
        return rec

    def stage_main(self, out=None):
        self.args.f32 = [self.camp["f32"], *self.tabs["f32"]] if "f32" in self.camp else None
        self.args.f48 = [self.camp["f48"], *self.tabs["f48"]] if "f48" in self.camp else None
        self.args.out = out or self.ev / "analysis.json"
        return S.run_main(self.args)


def test_pipeline_rs_finalist_main_gain_writes_once(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    rs = d.stage_rs()
    assert rs["comparable"]["proposals"] and rs["proposals"] and rs["cross_check"]["discrepancies"] == []
    assert all(g["phi_fortran_sha256"] and g["name"] and "admissible" in g for g in rs["gating"]) and [p["name"] for p in rs["proposals"]] == S.compute(d.T)["proposals_from_gating"]
    assert set(rs["coefficients"]) >= {"fid_analysis_sha256", "tier_a_slope"} and rs["shape_update_allowed"] is False
    fin = d.stage_finalist()
    assert fin["comparable"]["finalist"] == fin["finalist"] == S.compute(d.T)["finalist"] and fin["r_best"] == S.compute(d.T)["r_best"] and fin["rs_json_sha256"] == SC.sha256_path(d.args.rs)
    out = d.stage_main()
    assert [p.name for p in out] == ["analysis.json", "analysis.md", "xv_handoff.json"]
    ana = json.loads(out[d.args.out])
    assert ana["outcome"] == "SCREEN01_GAIN" and ana["cause"] == [] and ana["cross_check"]["discrepancies"] == [] and ana["shape_update_allowed"] is False
    h = json.loads(out[d.args.out.with_name("xv_handoff.json")])
    assert h["finalist"] == ana["finalist"] and h["analysis_sha256"] == hashlib.sha256(out[d.args.out].encode()).hexdigest() and h["in_camber_extension"] is True
    assert h["admissibility_row"]["name"] == h["finalist"] and h["state"]["direction_raw_sha256"] == "a" * 64 and h["selection_record"]["rs_json_sha256"] == SC.sha256_path(d.args.rs)
    assert "SCREEN01_GAIN" in out[d.args.out.with_suffix(".md")]
    for p, text in out.items():
        S.write_once(p, text)
    with pytest.raises(ValueError, match="already exists"):
        d.stage_main()
    with pytest.raises(FileExistsError):
        S.write_once(d.args.rs, "again")


def test_pipeline_no_handoff_without_gain_and_budget_stop_is_a_budget_cause(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "main_no_gain_below_min")
    d.stage_rs()
    d.stage_finalist()
    out = d.stage_main()
    assert [p.name for p in out] == ["analysis.json", "analysis.md"]
    (tmp_path / "b").mkdir()
    d = Disk(tmp_path / "b", monkeypatch, "main_incomplete_f_not_run")
    d.stage_rs()
    d.stage_finalist()
    d.args.budget_stopped = ["f32a", "f32b", "f48k13", "f48k14"]
    out = d.stage_main()
    ana = json.loads(out[d.args.out])
    assert ana["outcome"] == "SCREEN01_INCOMPLETE" and ana["cause"] == ["BUDGET"]


def test_pipeline_refuses_unfrozen_or_inconsistent_inputs(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.stage_rs()
    # rs.json differs from the frozen SHA
    fz = json.loads((d.ev / "freeze2_1.json").read_text())
    d.write("freeze2_1", {**fz, "rs_json_sha256": "0" * 64})
    d.args.g2 = [d.camp["g2"], *d.tabs["g2"]]
    with pytest.raises(ValueError, match="rs.json is not the one frozen"):
        S.run_finalist(d.args)
    # rs.json re-frozen after tampering with its comparable part: re-derivation refuses
    bad = json.loads(d.args.rs.read_text())
    bad["comparable"]["stop_after"] += 1
    d.args.rs.write_text(S.dumps(bad))
    d.write("freeze2_1", {**fz, "rs_json_sha256": SC.sha256_path(d.args.rs)})
    with pytest.raises(ValueError, match="does not re-derive"):
        S.run_finalist(d.args)
    # a campaign that is not the frozen one
    d.write("freeze2", {"kind": "freeze2", "file_sha256": {"docs/harness/screen01_campaign.json": "0" * 64}})
    with pytest.raises(ValueError, match="not the campaign frozen"):
        S.run_rs(d.args, d.oracle)


def test_pipeline_refuses_changed_sources_and_a_failing_cross_check(tmp_path, monkeypatch):
    bad = types.SimpleNamespace(check=lambda t: {**S.compute(t), "stop_after": -1}, compare=lambda a, b, stage: [k for k in a if S.canon(a[k]) != S.canon(b.get(k))])
    d = Disk(tmp_path, monkeypatch, checker=bad)
    with pytest.raises(ValueError, match="cross-check discrepancies"):
        S.run_rs(d.args, d.oracle)
    assert not d.args.rs.exists()
    fz = json.loads((d.ev / "freeze1.json").read_text())
    fz["file_sha256"]["scripts/screen01/analyze_screen01.py"] = "0" * 64
    d.write("freeze1", fz)
    with pytest.raises(ValueError, match="not the source frozen"):
        S.run_rs(d.args, d.oracle)


def test_pipeline_refuses_tables_for_a_group_nobody_needs(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "fin_no_proposals")
    d.stage_rs()
    d.args.g2 = [d.camp["g1"], *d.tabs["g1"]]
    with pytest.raises(ValueError, match="not needed"):
        S.run_finalist(d.args)
    d.args.g2 = None
    fin = S.run_finalist(d.args)
    assert fin["comparable"]["finalist"] is None and fin["finalist"] is None and fin["comparable"]["futility"] == "NO_FEASIBLE_CANDIDATE"


def test_real_oracle_evaluates_rounds_of_four_in_parallel(monkeypatch):
    T = Y.make("rs", n_grid=41)
    T0 = {**T, "gating": []}
    calls = []

    def fake_rows(specs, workers, log):
        calls.append([P.D.name(s) for s in specs])
        return [{"name": P.D.name(s), "admissible": sum(P.D.name(s).encode()) % 7 < 4} for s in specs]
    monkeypatch.setattr(P, "admissible_rows", fake_rows)
    ask, rows = S.real_oracle(T0, 4)
    T1 = S.rs_gate(T0, ask)
    assert T1["gating"] == T["gating"]                                                                            # same record as the sequential fake oracle
    assert all(len(c) <= 4 for c in calls) and sum(len(c) for c in calls) == len({g["name"] for g in T1["gating"]}) >= 4
    assert set(rows) >= {g["name"] for g in T1["gating"]}


def test_cli_finalist_and_main_write_the_outputs_once(tmp_path, monkeypatch, capsys):
    d = Disk(tmp_path, monkeypatch)
    d.stage_rs()
    grp = lambda g: [str(d.camp[g]), *map(str, d.tabs[g])]   # noqa: E731
    fin = d.ev / "finalist.json"
    monkeypatch.setattr(sys, "argv", ["x", "finalist", "--states", str(d.states), "--g1", *grp("g1"), "--g2", *grp("g2"), "--rs", str(d.args.rs), "--kernel-root", str(d.kr), "--out", str(fin)])
    S.main()
    d.write("freeze3", {"kind": "freeze3", "file_sha256": {**d.fz["f32"]["file_sha256"], **d.fz["f48"]["file_sha256"]}, "finalist_json_sha256": SC.sha256_path(fin)})
    out = d.ev / "analysis.json"
    argv = ["x", "main", "--states", str(d.states), "--g1", *grp("g1"), "--g2", *grp("g2"), "--f32", *grp("f32"), "--f48", *grp("f48"), "--rs", str(d.args.rs), "--finalist", str(fin),
            "--kernel-root", str(d.kr), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    S.main()
    assert json.loads(out.read_text())["outcome"] == "SCREEN01_GAIN" and (d.ev / "analysis.md").exists() and (d.ev / "xv_handoff.json").exists()
    with pytest.raises(ValueError, match="already exists"):
        S.main()
    with pytest.raises(FileExistsError):
        monkeypatch.setattr(sys, "argv", ["x", "finalist", "--states", str(d.states), "--g1", *grp("g1"), "--g2", *grp("g2"), "--rs", str(d.args.rs), "--kernel-root", str(d.kr), "--out", str(fin)])
        S.main()
    monkeypatch.setattr(sys, "argv", ["x", "main", "--workers", "5", "--out", str(out)])
    with pytest.raises(ValueError, match="at most 4 workers"):
        S.main()
