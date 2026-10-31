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
    assert r["rs_not_fit"] is True and r["fit"]["rank"] < 9 and r["fit"]["downforce"]["coef"] is None and r["fit"]["cond"] is None and r["rs_fit_poor"] is None and r["rs_fit_label"] == "RS_FIT_UNDEFINED"
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
    "main_incomplete_refine": ("SCREEN01_INCOMPLETE", ["DATA_G1", "DATA_REFINE"]),    # §5.9 / §5.11.7: RS_NOT_FIT from state-phase loss (the lost phases are DATA_G1 too)
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
    assert res("main_repeat_missing")["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": False, "judged": False}
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
    assert r["finalist"] is None and r["futility"] == "NO_FEASIBLE_CANDIDATE" and r["incomplete_causes"] == ["DATA_G1", "DATA_REFINE"] and r["search_complete"] is False


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
    assert r["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": False, "judged": False} and r["outcome"] == "SCREEN01_GAIN"   # NOT_JUDGED: no verdict
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


def test_exploration_controls_are_reported():
    d = res("main_gain")["detail"]
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
    d.mkdir(parents=True, exist_ok=True)
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
    (dict(error="RuntimeError: registered per-state or aggregate solver wall-time budget exceeded"), "", False, ("RUN_LOSS", "WALL_CAP")),
    (dict(error="RuntimeError: state did not complete: x (exit 1)", log="plain text log"), "", False, ("RUN_LOSS", "STATE_FAILED")),
    (dict(error="RuntimeError: kernel time budget exhausted"), "", False, ("NOT_INFRASTRUCTURE", None)),                                  # default: no signature matches
    (dict(error="boom", complete_states=3, log="plain text log"), "", False, ("NOT_INFRASTRUCTURE", None)),
])
def test_infra_signature_table(tmp_path, kw, status, verify_failed, expected):
    d, lg = make_infra(tmp_path, **kw)
    r = S.classify_infra(d, lg, status, verify_failed)
    assert (r["classification"], r["signature"]) == expected


def test_nonfinite_is_judged_on_the_verify_log_before_verify_failed(tmp_path):
    d, lg = make_infra(tmp_path, done=True)
    nf = "ValueError: state fields or forces are not finite"
    assert S.classify_infra(d, lg, "", True, verify_text=nf) == {"classification": "RUN_LOSS", "signature": "NONFINITE"}
    assert S.classify_infra(d, lg, "", True, verify_text="state process wall time exceeds budget") == {"classification": "INFRA_LOSS", "signature": "VERIFY_FAILED"}
    assert S.classify_infra(d, lg, "", False, verify_text=nf) == {"classification": "COMPLETE", "signature": None}          # the verify log counts only when verify failed
    d2, lg2 = make_infra(tmp_path / "x", error="Pkg.instantiate failed")                                                      # NONFINITE precedes the output-directory signatures
    assert S.classify_infra(d2, lg2, "", True, verify_text="forces ... must be a finite number")["signature"] == "NONFINITE"


def test_signature_table_file_is_the_revised_frozen_table():
    t = S.infra_table()
    ids = ["NONFINITE", "VERIFY_FAILED", "SESSION_KILL", "JULIA_INSTALL", "GPU_IDENTITY", "PLATFORM_ERROR", "WALL_CAP", "STATE_FAILED"]
    assert t["evaluation_order"] == ids and [e["id"] for e in t["signatures"]] == ids and t["default"] == "NOT_INFRASTRUCTURE" and set(t["classes"]) == {"INFRA_LOSS", "RUN_LOSS"}
    assert {e["id"]: e["class"] for e in t["signatures"]} == {"NONFINITE": "RUN_LOSS", "VERIFY_FAILED": "INFRA_LOSS", "SESSION_KILL": "INFRA_LOSS", "JULIA_INSTALL": "INFRA_LOSS",
                                                             "GPU_IDENTITY": "INFRA_LOSS", "PLATFORM_ERROR": "INFRA_LOSS", "WALL_CAP": "RUN_LOSS", "STATE_FAILED": "RUN_LOSS"}
    assert [e["id"] for e in t["signatures"] if e["pattern"] is None] == ["VERIFY_FAILED", "SESSION_KILL"]            # NONFINITE has a pattern, on the verify log (see the report)
    assert "verify" in next(e for e in t["signatures"] if e["id"] == "NONFINITE")["source"] and all(e["meaning"] and e["source"] and e["condition"] for e in t["signatures"])
    assert "whatever the classification" in t["rerun_rule"] and "does not change the rerun rule" in t["default_statement"] and "No third attempt" in t["rerun_rule"]
    import re
    for e in t["signatures"]:
        if e["pattern"]:
            re.compile(e["pattern"])
    assert "registered per-state or aggregate solver wall-time budget exceeded" in next(e for e in t["signatures"] if e["id"] == "WALL_CAP")["pattern"]


def test_classification_reads_its_patterns_from_the_table(tmp_path):
    t = S.infra_table()
    t2 = json.loads(json.dumps(t))
    next(e for e in t2["signatures"] if e["id"] == "PLATFORM_ERROR")["pattern"] = "NEW_PLATFORM_TEXT"
    d, lg = make_infra(tmp_path, error="NEW_PLATFORM_TEXT happened")
    assert S.classify_infra(d, lg, table=t2)["signature"] == "PLATFORM_ERROR" and S.classify_infra(d, lg, table=t)["classification"] == "NOT_INFRASTRUCTURE"
    bad = json.loads(json.dumps(t))
    bad["signatures"].append(dict(bad["signatures"][0]))
    p = tmp_path / "t.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="malformed signature table"):
        S.infra_table(p)


def test_infra_out_writes_the_classification_record_once(tmp_path, monkeypatch, capsys):
    d, lg = make_infra(tmp_path, error="RuntimeError: registered per-state or aggregate solver wall-time budget exceeded")
    out = tmp_path / "rec.json"
    monkeypatch.setattr(sys, "argv", ["x", "infra", "--output-dir", str(d), "--log", str(lg), "--kernel", "g1k11", "--attempt", "2", "--out", str(out)])
    S.main()
    r = json.loads(out.read_text())
    assert (r["kind"], r["kernel"], r["attempt"], r["classification"], r["signature"]) == ("screen01_infra_classification", "g1k11", 2, "RUN_LOSS", "WALL_CAP")
    assert r["table_sha256"] == SC.sha256_path(S.ROOT / S.INFRA_REL) and r["evidence_sha256"]["ERROR.txt"] == SC.sha256_path(d / "ERROR.txt") and r["evidence_sha256"]["status"] is None
    with pytest.raises(FileExistsError):
        S.main()
    vl = tmp_path / "verify.log"
    vl.write_text("ValueError: state fields or forces are not finite")
    d2, lg2 = make_infra(tmp_path / "y", done=True)
    r2 = S.infra_record("f32a", 2, d2, lg2, verify_log=vl, verify_failed=True)
    assert (r2["classification"], r2["signature"]) == ("RUN_LOSS", "NONFINITE") and r2["evidence_sha256"]["verify_log"] == SC.sha256_path(vl) and r2["verify_failed"] is True
    with pytest.raises(ValueError, match="needs --kernel"):
        S.infra_record(None, None, d2, lg2)


def test_infra_cli(tmp_path, monkeypatch, capsys):
    d, lg = make_infra(tmp_path, error="Pkg.instantiate failed")
    monkeypatch.setattr(sys, "argv", ["x", "infra", "--output-dir", str(d), "--log", str(lg)])
    S.main()
    assert json.loads(capsys.readouterr().out)["signature"] == "JULIA_INSTALL"


# ---- the harness-table loader --------------------------------------------------------------------------------------------------------------------
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


# ---- the 2026-10-31 reconciliation (registration §5.2, §5.11): branches of crosscheck_reconciliation.md §3.3, each with its expected comparable values ----
def rs_of(r):
    return r["rs"] if "rs" in r else r


def gate_names(T):
    return [g["name"] for g in T["gating"]]


@pytest.mark.parametrize("name", ["rs_duplicate_target_point", "fin_duplicate_target_point"])
def test_a_point_shared_by_two_targets_is_gated_once_and_owned_by_the_first(name):
    T = Y.branch(name)
    r = S.compute(T)
    rs = rs_of(r)
    assert rs["targets"]["1"]["u_star"] == rs["targets"]["1.5"]["u_star"]                    # a slack drag margin: u*_1 = u*_1.5
    shared = Y.sname(rs["targets"]["1"]["u_star"])
    names = gate_names(T)
    assert names.count(shared) == 1 and names[0] == shared and T["gating"][0]["target_index"] == 0 and rs["gated"][0][0] == 0 and len(set(names)) == len(names)
    props = [T["gating"][i] for i in rs["proposals"]]
    assert len({p["name"] for p in props}) == len(props) and shared in {p["name"] for p in props}
    t1 = [p for p in props if p["target_index"] == 1]
    own = [g for g in T["gating"] if g["target_index"] == 1 and g["admissible"]]
    assert t1 and t1[0]["name"] != shared and t1[0]["name"] == max(own, key=lambda g: g["y_pred"])["name"]      # target 1: its own best admissible point
    if name.startswith("fin"):
        assert r["search_complete"] is True and len(r["proposals_from_gating"]) == len(set(r["proposals_from_gating"]))


@pytest.mark.parametrize("name", ["rs_target_no_predicted_gain", "fin_target_no_predicted_gain"])
def test_a_target_without_predicted_gain_contributes_nothing_but_is_reported(name):
    T = Y.branch(name)
    r = S.compute(T)
    rs = rs_of(r)
    t = rs["targets"]
    assert t["1"]["y_pred"] == pytest.approx(0.005, abs=1e-12) and t["1"]["u_star"] == pytest.approx([1.0, -1.5, 0.5])
    assert t["1.5"]["y_pred"] == pytest.approx(0.0018, abs=1e-12) and t["1.5"]["u_star"] == pytest.approx([1.0, -1.5, 0.7])
    assert t["2"]["y_pred"] == pytest.approx(-0.0022, abs=1e-12) and t["2"]["u_star"] == pytest.approx([1.0, -1.5, 0.95]) and t["2"]["z_pred"] <= -2 * P.M_D
    assert {g[0] for g in rs["gated"]} == {0, 1} and {T["gating"][i]["target_index"] for i in rs["proposals"]} <= {0, 1} and rs["proposals"]
    if name.startswith("fin"):
        assert r["search_complete"] is True and len(r["proposals_from_gating"]) >= 2


def test_no_target_with_predicted_gain_means_no_gating_and_a_complete_search():
    rs = res("rs_all_targets_no_predicted_gain")
    assert all(t["y_pred"] < 0 and t["z_pred"] <= -float(k) * P.M_D and t["u_star"] is not None for k, t in rs["targets"].items())
    assert rs["gated"] == [] and rs["stop_after"] == 0 and rs["proposals"] == [] and rs["pool_limited_pre"] is False and rs["rs_not_fit"] is False
    f = res("fin_all_targets_no_predicted_gain")
    assert f["proposals_from_gating"] == [] and f["search_complete"] is True and f["K_opt"] == 15
    assert f["finalist"] is None and f["futility"] == "GAIN_BELOW_MIN_AT_SELECTION" and f["selected_before_futility"] is not None
    m = res("main_all_targets_no_predicted_gain")
    assert (m["outcome"], m["cause"]) == ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN_AT_SELECTION"])           # a complete search: NO_GAIN, not INCOMPLETE
    assert m["G"] is None and m["R3"] is None and m["confirmation"] == {"f32": None, "f48": None}


def test_argmax_ties_go_to_the_first_grid_point_in_lexicographic_order():
    by, bz = np.array(Y.BY_TIE), np.array(Y.BZ_TIE)                                                      # exactly no reflex dependence
    u, y, z = P.constrained_argmax(by, bz, P.M_D, 41, S.get_grid(41))
    assert u[2] == -1.0 and z <= -P.M_D
    r = res("rs_argmax_tie")                                                                              # through the least-squares fit the zeros are ~1e-18: the pick is noise, both implementations must agree
    assert abs(r["fit"]["downforce"]["coef"][2]) < 1e-15 and abs(r["fit"]["drag"]["coef"][2]) < 1e-15 and r["rs_not_fit"] is False and len(r["proposals"]) >= 1


def test_names_registered_at_freeze_1_are_excluded_by_name_not_by_coordinates():
    T = Y.branch("rs_cloud_point_already_evaluated")
    r = S.compute(T)
    ustar = Y.sname(r["targets"]["1"]["u_star"])
    design = {n: x for n, x in T["roles"].items() if x["role"] == "design"}
    assert ustar in design and ustar not in gate_names(T)                                              # a design point sits at u*_1: its name is not a candidate
    assert T["gating"][0]["target_index"] == 0 and T["gating"][0]["name"] != ustar and T["gating"][0]["y_pred"] >= 0.9 * r["targets"]["1"]["y_pred"]   # target 0 starts with its best cloud point
    T = Y.branch("rs_cloud_point_as_random_state")
    r = S.compute(T)
    rnd = next(n for n, x in T["roles"].items() if x["role"] == "random" and x["order"] == 0)
    assert rnd not in gate_names(T) and T["gating"][0]["u"] == pytest.approx(r["targets"]["1"]["u_star"]) and T["gating"][0]["target_index"] == 0     # u*_1 itself is first; the random state's name is excluded


@pytest.mark.parametrize("name", ["rs_target_list_absorbed", "fin_target_list_absorbed"])
def test_a_target_whose_list_is_absorbed_is_ignored_by_the_stop_rule(name):
    T = Y.branch(name)
    r = S.compute(T)
    rs = rs_of(r)
    uc = list(Y.UC)
    assert all(t["u_star"] == pytest.approx(uc) for t in rs["targets"].values())                       # u*_1 = u*_1.5 = u*_2: targets 1 and 2 queue nothing new at position 0
    names = gate_names(T)
    assert names[0] == Y.sname(uc) and names.count(Y.sname(uc)) == 1 and {g[0] for g in rs["gated"]} == {0, 1}      # target 2 has no queued point
    n = rs["stop_after"]
    adm = lambda k, m: sum(g["admissible"] for g in T["gating"][:m] if g["target_index"] == k)   # noqa: E731
    assert (adm(0, n) >= 2 and adm(1, n) >= 2) or n == 36                                               # stopped by targets 0 and 1 alone
    assert not (adm(0, n - 4) >= 2 and adm(1, n - 4) >= 2) or n == 36
    if name.startswith("fin"):
        assert r["search_complete"] is True


def test_residual_sd_undefined_gives_rs_fit_undefined_and_the_search_goes_on():
    Y.check_keep_sets()
    r = res("rs_fit_undefined")
    assert r["fit"]["rank"] == 9 and r["fit"]["cond"] == pytest.approx(8.742441034795732, rel=1e-9) and r["rs_not_fit"] is False
    assert r["fit"]["residual_sd"] == {"downforce": None, "drag": None} and r["rs_fit_poor"] is None and r["rs_fit_label"] == "RS_FIT_UNDEFINED"
    assert np.allclose(r["fit"]["downforce"]["coef"], Y.BY, atol=1e-12) and r["proposals"] and len(r["data_loss"]) == 12
    assert res("rs_base")["rs_fit_label"] == "RS_FIT_OK" and res("rs_fit_poor")["rs_fit_label"] == "RS_FIT_POOR"


def test_rank_nine_with_a_large_condition_number_is_not_fit():
    r = res("rs_not_fit_cond")
    assert r["fit"]["rank"] == 9 and r["fit"]["cond"] == pytest.approx(139.74479340064676, rel=1e-9) and r["rs_not_fit"] is True
    assert r["fit"]["downforce"]["coef"] is None and r["fit"]["drag"]["coef"] is None and r["fit"]["residual_sd"] == {"downforce": None, "drag": None}
    assert r["u_star_1"] is None and r["y_star_1"] is None and r["pool_limited_pre"] is False and r["gated"] == [] and r["proposals"] == []
    assert r["rs_fit_poor"] is None and r["rs_fit_label"] == "RS_FIT_UNDEFINED" and all(t["u_star"] is None for t in r["targets"].values())


def test_an_implausible_or_nonfinite_repeat_is_nondeterminism_and_a_loss():
    r = res("main_repeat_implausible_g1")                                                              # 30 % above the parent: NONDETERMINISM, not a removed check
    assert f"{Y.REPEAT}@g1@11" in r["data_loss"] and (r["outcome"], r["cause"]) == ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"])
    d = r["determinism"]["g1k11"]
    assert d["judged"] is True and d["nondeterminism"] is True and d["max_abs_diff"]["downforce"] == pytest.approx(0.3 * Y.F0["downforce"], rel=1e-9) and d["max_abs_diff"]["drag"] == 0.0
    r = res("main_repeat_nonfinite_g1")                                                                # same bytes, no force: not reproduced
    assert r["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": True, "judged": True}
    assert f"{Y.REPEAT}@g1@11" in r["data_loss"] and (r["outcome"], r["cause"]) == ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"])


def test_an_absent_or_unfinished_repeat_is_not_judged():
    for name, listed in (("main_repeat_not_ok_f32a", True), ("main_repeat_missing_f32a", False)):
        r = res(name)
        assert r["determinism"]["f32a"] == {"max_abs_diff": None, "nondeterminism": False, "judged": False} and r["determinism"]["g1k11"]["judged"] is True
        assert (f"{Y.REPEAT}@f32@13" in r["data_loss"]) is listed and (r["outcome"], r["cause"]) == ("SCREEN01_GAIN", [])


def test_step_3_causes_are_the_list_of_all_that_apply_in_stage_order():
    for name, causes in (("main_incomplete_g1_kernel_and_refine", ["DATA_G1", "DATA_REFINE"]), ("main_incomplete_g1_phase_and_g2", ["DATA_G1", "DATA_G2"]),
                         ("main_incomplete_refine_degenerate_design", ["DATA_REFINE"])):
        r = res(name)
        assert (r["outcome"], r["cause"], r["finalist"], r["search_complete"]) == ("SCREEN01_INCOMPLETE", causes, None, False)
    r = res("main_incomplete_g1_kernel_and_refine")
    assert Y.branch("main_incomplete_g1_kernel_and_refine")["lost_kernels"] == ["g1k12"] and r["rs"]["rs_not_fit"] is True
    assert res("main_incomplete_g1_phase_and_g2")["rs"]["rs_not_fit"] is False                          # the fit is OK: DATA_G2 applies
    r = res("main_incomplete_refine_degenerate_design")
    assert r["data_loss"] == [] and r["rs"]["rs_not_fit"] is True and r["rs"]["fit"]["rank"] < 9          # no loss at all: the refinement step alone failed


def test_r3_paired_labels_use_the_phases_common_to_flow_48_and_flow_32():
    r = res("main_r3_one_f48_phase_paired")
    c = r["confirmation"]
    assert c["f48"]["P"] == 1 and c["f32"]["delta_bar"]["downforce"] == pytest.approx(0.025, abs=1e-9) and c["f32"]["delta_bar"]["drag"] == pytest.approx(-2.75e-3, abs=1e-12)
    # paired (phase 13 only): d32 = 0.020, d48 = 0.0195 -> ratio 0.975, |diff| 5e-4; the unpaired flow_32 mean (0.025, drag -2.75e-3) would give 0.78, 5.5e-3 and an opposite drag sign
    assert r["R3"]["R3_RATIO_IN_BAND"] is True and r["R3"]["R3_E2_EXCEEDED"] is False and r["R3"]["R3_DRAG_SAME_SIGN"] is True and r["R3"]["label"] == "R3_CONFIRMED"
    assert r["R3"]["G48_MARGIN"] == pytest.approx(0.0195 - S.X_STAR, abs=1e-9) and (r["outcome"], r["cause"]) == ("SCREEN01_GAIN", [])
    assert 0.0195 / 0.025 < S.RATIO_BAND[0]
    T = Y.branch("main_r3_one_f48_phase_paired")                                                         # no common phase at all: the three labels are null
    f = S.compute(T)["finalist"]
    for ph in ("13", "14"):
        Y.drop(T, "f32", f, ph)
    Y.set_run(T, "f32", f, "15", ok=True)
    r = S.compute(T)
    assert r["R3"]["R3_RATIO_IN_BAND"] is None and r["R3"]["R3_E2_EXCEEDED"] is None and r["R3"]["R3_DRAG_SAME_SIGN"] is None and r["R3"]["label"] == "R3_CONFIRMED"


def test_both_flow_48_kernels_never_run_is_a_budget_stop():
    r = res("main_budget_f48_not_run")
    assert (r["outcome"], r["cause"]) == ("SCREEN01_INCOMPLETE", ["BUDGET"]) and r["R3"] is None and r["confirmation"]["f48"] is None and r["G"]["decision"] == "PASS"
    assert Y.branch("main_budget_f48_not_run")["lost_kernels"] == []


def test_t_based_labels_with_one_phase_are_null_not_computed():
    assert S.tcrit(1) is None and S.tcrit(0) is None and S.tcrit(2) == pytest.approx(6.313751514675, rel=1e-9)
    e = est_dict(S.X_STAR + 1e-3, 1e-4, p=1)
    assert S.g_rule(e) == {"decision": "PASS", "GAIN_RESOLVED_ABOVE_MIN": None}
    assert S.d_rule(est_dict(-1e-3, 1e-3, p=1)) == {"decision": "PASS", "label": None} and S.d_rule(est_dict(1e-3, 1e-3, p=1)) == {"decision": "VIOLATION", "label": None}
    r = res("main_rbest_single_phase")                                                                  # R-best with one flow_32 phase: estimates only, unresolved comparison, no pass
    rb = r["detail"]["control_estimates"]["r_best"]["f32"]
    assert rb["P"] == 1 and rb["sigma_d"] == {"downforce": None, "drag": None} and rb["se_eff"]["downforce"] == S.FLOOR["downforce"]
    assert r["controls"]["OPT_VS_RANDOM"] == "OPT_RANDOM_UNRESOLVED" and r["controls"]["RANDOM_FEASIBLE_GAIN"] is False


def test_ref_consistent_label_only():
    def run_with(df):
        T = Y.make("finalist", edits={"g1": lambda T, al: Y.set_delta(T, "g1", al.ref, None, ddf=df)}, n_grid=41)
        return S.compute(T)["REF_CONSISTENT"]
    w = 3 * math.hypot(S.FLOOR["downforce"] / math.sqrt(2), S.REF_SIGMA)                               # P = 2 equal phases: SE_eff = floor / sqrt(2)
    assert run_with(S.REF_DF) is True and run_with(S.REF_DF + w - 1e-7) is True and run_with(S.REF_DF + w + 1e-7) is False and run_with(S.REF_DF - w - 1e-7) is False
    assert res("fin_base")["REF_CONSISTENT"] is False                                                   # the synthetic truth is not the FID C1 value


# ---- the INFRA_LOSS signature table (§9, §5.11.17) ----------------------------------------------------------------------------------------------

# ---- the whole study on disk (adoption.md §3.1; registration §10, §5.11.17-20): rs -> finalist -> main through freeze records, campaigns, tables and kernel files ----------
Disk = Y.Disk


def test_pipeline_rs_finalist_main_gain_writes_once(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    f1 = d.freeze("freeze1")["file_sha256"]
    assert Y.UNC_STATES_REL in f1 and f"{S.EV_REL}/states.json" in f1 and len([k for k in f1 if k.endswith("states.json")]) == 2           # two states.json: looked up by repo-relative key
    rs = d.stage_rs()
    assert rs["comparable"]["proposals"] and rs["proposals"] and rs["cross_check"]["discrepancies"] == [] and rs["lost_signatures"] == {} and rs["not_pushed"] == {}
    assert all(g["phi_fortran_sha256"] and g["name"] and "admissible" in g for g in rs["gating"]) and [p["name"] for p in rs["proposals"]] == S.compute(d.T)["proposals_from_gating"]
    assert rs["comparable"]["g1_controls"]["invalid_at_step_2"] is False and rs["groups"]["g1"]["table_sha256"].keys() == {S.rel(t) for t in d.tabs["g1"]}   # table_sha256 keyed by repo-relative path
    fin = d.stage_finalist()
    assert fin["comparable"]["finalist"] == fin["finalist"] == S.compute(d.T)["finalist"] and fin["r_best"] == S.compute(d.T)["r_best"] and fin["pushed"] is True
    assert fin["rs_json_sha256"] == SC.sha256_path(d.args.rs) and fin["comparable"]["g1_controls"] == rs["comparable"]["g1_controls"]
    assert d.freeze("freeze3")["pushed"] is True and set(d.freeze("freeze3")["campaigns"]) == {"screen01_f", "screen01_f48"}
    out = d.stage_main()
    assert [p.name for p in out] == ["analysis.json", "analysis.md", "xv_handoff.json"]
    ana = json.loads(out[d.args.out])
    assert ana["outcome"] == "SCREEN01_GAIN" and ana["cause"] == [] and ana["cross_check"]["discrepancies"] == [] and ana["shape_update_allowed"] is False and ana["g1_controls"]["invalid_at_step_2"] is False
    assert ana["detail"]["I_confirmation"]["f32"]["downforce"] == pytest.approx(ana["confirmation"]["f32"]["delta_bar"]["downforce"] / S.J_B48)
    h = json.loads(out[d.args.out.with_name("xv_handoff.json")])
    assert h["finalist"] == ana["finalist"] and h["analysis_sha256"] == hashlib.sha256(out[d.args.out].encode()).hexdigest() and h["in_camber_extension"] is True
    assert h["admissibility_row"]["name"] == h["finalist"] and h["state"]["direction_raw_sha256"] == "a" * 64 and h["selection_record"]["rs_json_sha256"] == SC.sha256_path(d.args.rs)
    assert "g1_controls" in md_of(out, d) and "invalid_at_step_2: False" in md_of(out, d)
    for p, text in out.items():
        S.write_once(p, text)
    with pytest.raises(ValueError, match="already exists"):
        d.stage_main()
    with pytest.raises(FileExistsError):
        S.write_once(d.args.rs, "again")


def md_of(out, d):
    return out[d.args.out.with_suffix(".md")]


@pytest.mark.parametrize("name,outcome,cause", [("main_no_gain_no_feasible", "SCREEN01_NO_GAIN", ["NO_FEASIBLE_CANDIDATE"]), ("main_incomplete_refine", "SCREEN01_INCOMPLETE", ["DATA_G1", "DATA_REFINE"])])
def test_main_without_a_finalist_binds_freeze_3_and_writes_once(tmp_path, monkeypatch, name, outcome, cause):
    d = Disk(tmp_path, monkeypatch, name)
    d.stage_rs()
    fin = d.stage_finalist()
    f3 = d.freeze("freeze3")
    assert fin["finalist"] is None and fin["pushed"] is False and f3["finalist"] is None and f3["pushed"] is False and "campaigns" not in f3 and f3["finalist_json_sha256"] == SC.sha256_path(d.args.finalist)
    assert set(d.camp) == {"g1", "g2"} or set(d.camp) == {"g1"}                                                                           # no confirmation campaign exists
    out = d.stage_main()                                                                                                                  # no --f32 / --f48 argument
    assert d.args.f32 is None and d.args.f48 is None and [p.name for p in out] == ["analysis.json", "analysis.md"]
    ana = json.loads(out[d.args.out])
    assert (ana["outcome"], ana["cause"]) == (outcome, cause) and ana["confirmation"] == {"f32": None, "f48": None}
    for p, text in out.items():
        S.write_once(p, text)
    with pytest.raises(ValueError, match="already exists"):
        d.stage_main()


def test_main_refuses_freeze_3_that_disagrees_with_finalist_json(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.stage_rs()
    d.stage_finalist()
    f3 = d.freeze("freeze3")
    d.write("freeze3", {**f3, "pushed": False})
    with pytest.raises(ValueError, match="freeze3.json and finalist.json disagree"):
        d.stage_main()
    d.write("freeze3", {**f3, "r_best": "v18__other"})
    with pytest.raises(ValueError, match="freeze3.json and finalist.json disagree"):
        d.stage_main()


def test_lost_kernel_cites_its_classification_record_through_the_pipeline(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "fin_g1k11_lost")
    rs = d.stage_rs()
    fin = d.stage_finalist()
    assert d.args.lost == ["g1k11"] and rs["lost_signatures"] == {"g1k11": "NOT_INFRASTRUCTURE"} and fin["lost_signatures"] == {"g1k11": "NOT_INFRASTRUCTURE"}
    rec = d.ev.parent / "lost_g1k11.json"
    assert rs["lost_records_sha256"] == {"g1k11": SC.sha256_path(rec)} and rs["infra_signatures_sha256"] == SC.sha256_path(d.root / S.INFRA_REL)
    assert rs["lost_kernels"] == ["g1k11"] and fin["comparable"]["search_complete"] is False and fin["comparable"]["g1_controls"]["determinism_g1k11"]["judged"] is False
    assert fin["groups"]["g1"]["kernels_lost"] == ["g1k11"]


def test_lost_declaration_must_cite_a_matching_record(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "fin_g1k11_lost")
    d.declare("rs")
    good = d.args.lost_declarations["g1k11"]["record"]
    rec = json.loads(Path(good).read_text())
    bad = tmp_path / "bad.json"
    table = S.infra_table()
    for change, why in (({"kernel": "g1k12"}, "other kernel"), ({"attempt": 1}, "first attempt"), ({"signature": "WALL_CAP", "classification": "RUN_LOSS"}, "other signature"),
                        ({"table_sha256": "0" * 64}, "other table"), ({"kind": "screen01_budget_decision"}, "other kind")):
        bad.write_text(json.dumps({**rec, **change}))
        with pytest.raises(ValueError, match="not the classification record"):
            S.parse_lost([f"g1k11=NOT_INFRASTRUCTURE:{bad}"], table)
    wall = json.loads(json.dumps(rec))
    wall.update(signature="WALL_CAP", classification="RUN_LOSS")
    bad.write_text(json.dumps(wall))
    assert S.parse_lost([f"g1k11=WALL_CAP:{bad}"], table)["g1k11"]["signature"] == "WALL_CAP"                                           # every table id, not only INFRA_LOSS
    wall["classification"] = "INFRA_LOSS"
    bad.write_text(json.dumps(wall))
    with pytest.raises(ValueError, match="not the classification record"):                                                               # the class is the table's
        S.parse_lost([f"g1k11=WALL_CAP:{bad}"], table)
    for text in ("g1k11", "g1k11=WALL_CAP", "g1k11=NOT_A_SIGNATURE:x", "g9=WALL_CAP:x", "g1k11=:x"):
        with pytest.raises(ValueError, match="expected KERNEL=ID:RECORD"):
            S.parse_lost([text], table)
    d.args.lost_declarations = {}                                                                                                       # a kernel without a table and without a declaration
    d.args.g1 = d.group("g1")
    with pytest.raises(ValueError, match="every --lost declaration must cite"):
        S.run_rs(d.args, d.oracle)


# ---- --not-pushed (§5.11.19, §5.8 step 4) -------------------------------------------------------------------------------------------------------
def test_budget_not_pushed_kernel_gives_incomplete_budget_whatever_the_other_data_show(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "main_budget_with_full_data")
    d.stage_rs()
    d.stage_finalist()
    out = d.stage_main()
    ana = json.loads(out[d.args.out])
    assert (ana["outcome"], ana["cause"]) == ("SCREEN01_INCOMPLETE", ["BUDGET"])
    assert ana["confirmation"]["f32"]["P"] == 4 and ana["confirmation"]["f48"]["P"] == 1 and ana["G"]["decision"] == "PASS" and ana["R3"]["label"] == "R3_CONFIRMED"     # everything else is fine
    rec = d.ev.parent / "budget_f48k14.json"
    assert ana["not_pushed"] == {"f48k14": {"reason": "BUDGET", "record": S.rel(rec), "record_sha256": SC.sha256_path(rec)}} and ana["not_pushed_kernels"] == {"f48k14": "BUDGET"}
    assert [p.name for p in out] == ["analysis.json", "analysis.md"]                                                                                                       # no handoff on INCOMPLETE
    assert d.freeze("freeze3")["pushed"] is True


def test_not_pushed_declarations_are_verified(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "main_budget_with_full_data")
    d.stage_rs()
    d.stage_finalist()
    d.declare("main")
    good = d.ev.parent / "budget_f48k14.json"
    rec = json.loads(good.read_text())
    bad = tmp_path / "bad_budget.json"

    def run(decl):
        d.declare("main")
        d.args.not_pushed = decl
        d.args.g2 = d.group("g2")
        d.args.f32, d.args.f48, d.args.out = d.group("f32"), d.group("f48"), d.ev / "analysis.json"
        return S.run_main(d.args)
    for change, msg in (({"decision": "go"}, "not a §4.3 budget record"), ({"pending_estimate_s": {"f32a": [5000]}}, "not a §4.3 budget record"), ({"kind": "other"}, "not a §4.3 budget record")):
        bad.write_text(json.dumps({**rec, **change}))
        with pytest.raises(ValueError, match=msg):
            run({"f48k14": {"reason": "BUDGET", "record": bad}})
    with pytest.raises(ValueError, match="only .* citing a screen01_budget_decision record"):
        run({"g2": {"reason": "BUDGET", "record": good}})                                                    # BUDGET is for the four confirmation kernels
    with pytest.raises(ValueError, match="only .* citing a screen01_budget_decision record"):
        run({"f48k14": {"reason": "BUDGET", "record": None}})                                                # a BUDGET declaration needs its stop record
    with pytest.raises(ValueError, match="do not report invalid_at_step_2"):
        run({"f48k14": {"reason": "INVALID_G1", "record": None}})                                            # a clean G1: the kernel must be pushed
    with pytest.raises(ValueError, match="have a verified table"):
        both = tmp_path / "both.json"
        both.write_text(json.dumps({**rec, "pending_estimate_s": {"f32a": [5000], "f48k14": [7280]}}))
        run({"f48k14": {"reason": "BUDGET", "record": both}, "f32a": {"reason": "BUDGET", "record": both}})   # a declared kernel with a table
    with pytest.raises(ValueError, match="registered kernel|expected KERNEL=BUDGET"):
        S.parse_not_pushed(["f99=BUDGET:x"])
    with pytest.raises(ValueError, match="expected KERNEL=BUDGET"):
        S.parse_not_pushed(["f48k14=MAYBE:x"])
    assert S.parse_not_pushed(["f48k14=BUDGET:r.json", "g2=INVALID_G1"]) == {"f48k14": {"reason": "BUDGET", "record": Path("r.json")}, "g2": {"reason": "INVALID_G1", "record": None}}
    run({"f48k14": {"reason": "BUDGET", "record": good}})                                                      # the honest declaration passes


def test_invalid_g1_stops_the_push_and_main_writes_the_invalid_outcome(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "main_invalid_g1_without_F")
    rs = d.stage_rs()
    assert rs["comparable"]["g1_controls"]["NC_g1"]["label"] == "NOT_CONSISTENT" and rs["comparable"]["g1_controls"]["invalid_at_step_2"] is True and set(d.camp) == {"g1"}
    assert d.freeze("freeze2_1")["g2"] == "none (invalid_at_step_2)"
    fin = d.stage_finalist()                                                                                   # g2 declared INVALID_G1 against the frozen rs.json; proposals have P = 0
    assert fin["not_pushed"] == {"g2": {"reason": "INVALID_G1", "record": S.rel(d.args.rs), "record_sha256": SC.sha256_path(d.args.rs)}}
    assert fin["pushed"] is False and fin["finalist"] is not None and fin["comparable"]["g1_controls"]["invalid_at_step_2"] is True and d.freeze("freeze3")["pushed"] is False
    assert all(c["P"] == 0 for n, c in fin["comparable"]["candidates"].items() if d.T["roles"][n]["role"] == "proposal") and fin["comparable"]["search_complete"] is False
    out = d.stage_main()
    ana = json.loads(out[d.args.out])
    assert (ana["outcome"], ana["cause"]) == ("SCREEN01_INVALID", ["NC_G1"]) and ana["not_pushed_kernels"] == {k: "INVALID_G1" for k in ("f32a", "f32b", "f48k13", "f48k14", "g2")}
    assert ana["not_pushed"]["f32a"]["record"] == S.rel(d.args.finalist) and [p.name for p in out] == ["analysis.json", "analysis.md"]
    # every un-pushed kernel must be declared; with a clean G1 (above) INVALID_G1 is refused
    del d.T["not_pushed"]["f32b"]
    with pytest.raises(ValueError, match="were not pushed because the G1 chain controls failed"):
        d.stage_main()


def test_not_pushed_invalid_g1_with_a_clean_rs_json_is_refused_at_finalist(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "fin_base")
    d.stage_rs()
    d.declare("finalist")
    d.args.not_pushed = {"g2": {"reason": "INVALID_G1", "record": None}}
    d.args.g2 = d.group("g2")
    with pytest.raises(ValueError, match="do not report invalid_at_step_2"):
        S.run_finalist(d.args)


def test_a_campaign_given_for_an_unneeded_group_and_the_loss_of_both_g1_kernels(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch, "fin_no_proposals")
    d.stage_rs()
    d.declare("finalist")
    d.args.g2 = d.group("g1")
    with pytest.raises(ValueError, match="not needed"):
        S.run_finalist(d.args)
    d.args.g2 = None
    assert S.run_finalist(d.args)["comparable"]["finalist"] is None
    # both G1 kernels lost: `--g1 CAMPAIGN` with no tables is a complete argument; without --g1 the call is refused
    d = Disk(tmp_path / "b", monkeypatch, "main_both_g1_kernels_lost")
    d.declare("rs")
    d.args.g1 = [d.camp["g1"]]
    assert set(d.args.lost) == {"g1k11", "g1k12"}
    rs = S.run_rs(d.args, d.oracle)
    assert rs["comparable"]["rs_not_fit"] is True and rs["comparable"]["g1_controls"]["NC_g1"] == {"z": None, "label": None} and rs["lost_kernels"] == ["g1k11", "g1k12"]
    d.args.g1 = None
    with pytest.raises(ValueError, match="--g1 CAMPAIGN is required"):
        S.run_rs(d.args, d.oracle)
    d.args.g1 = [d.camp["g1"]]
    S.write_once(d.args.rs, S.dumps(rs))
    d.write("freeze2_1", {"kind": "freeze2_1", "file_sha256": {S.rel(d.ev / "freeze2.json"): SC.sha256_path(d.ev / "freeze2.json"), S.rel(d.args.rs): SC.sha256_path(d.args.rs)},
                          "rs_json_sha256": SC.sha256_path(d.args.rs), "g2": "none (no proposal)"})
    fin = d.stage_finalist()
    assert fin["comparable"]["search_complete"] is False and fin["pushed"] is False
    out = d.stage_main()
    ana = json.loads(out[d.args.out])
    assert (ana["outcome"], ana["cause"]) == ("SCREEN01_INCOMPLETE", ["DATA_G1"]) and ana["lost_signatures"] == {"g1k11": "NOT_INFRASTRUCTURE", "g1k12": "NOT_INFRASTRUCTURE"}


# ---- g1_controls (§5.11.18) -----------------------------------------------------------------------------------------------------------------------
def test_g1_controls_are_reported_at_rs_and_finalist():
    z = abs(5e-3 - S.NC_REF) / math.hypot(S.NC_FLOOR / math.sqrt(2), S.NC_SE)
    c = res("rs_nc_g1_not_consistent")["g1_controls"]
    assert c["NC_g1"]["label"] == "NOT_CONSISTENT" and c["NC_g1"]["z"] == pytest.approx(z, rel=1e-9) and c["determinism_g1k11"]["nondeterminism"] is False and c["invalid_at_step_2"] is True
    c = res("rs_repeat_nondeterministic")["g1_controls"]
    assert c["NC_g1"]["label"] == "CONSISTENT" and c["determinism_g1k11"]["nondeterminism"] is True and c["determinism_g1k11"]["max_abs_diff"]["downforce"] == pytest.approx(5e-4, abs=1e-12) and c["invalid_at_step_2"] is True
    c = res("rs_base")["g1_controls"]
    assert c["invalid_at_step_2"] is False and c["NC_g1"]["label"] == "CONSISTENT" and c["determinism_g1k11"] == {"max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "nondeterminism": False, "judged": True}
    f = res("fin_invalid_g1_g2_not_pushed")
    assert f["g1_controls"]["invalid_at_step_2"] is True and f["search_complete"] is False and f["incomplete_causes"] == ["DATA_G2"]
    m = res("main_invalid_g1_without_F")                                                                          # the main-stage blocks are the same functions
    assert m["g1_controls"] == {"NC_g1": m["NC"]["g1"], "determinism_g1k11": m["determinism"]["g1k11"], "invalid_at_step_2": True} and (m["outcome"], m["cause"]) == ("SCREEN01_INVALID", ["NC_G1"])
    assert m["confirmation"] == {"f32": None, "f48": None} and m["G"] is None and m["detail"]["phases_used"]["finalist_confirmation"] == {}
    two = res("main_two_causes_step2")
    assert (two["outcome"], two["cause"]) == ("SCREEN01_INVALID", ["NC_G1", "NONDETERMINISM_G1K11"]) and two["g1_controls"]["invalid_at_step_2"] is True
    two = res("main_two_causes_step5")
    assert (two["outcome"], two["cause"]) == ("SCREEN01_INVALID", ["NC_F", "NONDETERMINISM_F32A"]) and two["g1_controls"]["invalid_at_step_2"] is False
    two = res("main_two_causes_step7")
    assert (two["outcome"], two["cause"]) == ("SCREEN01_INCONCLUSIVE", ["G_UNRESOLVED", "R3_UNRESOLVED"])


def test_a_run_without_a_valid_parent_run_at_its_phase_is_not_listed():
    T = Y.branch("rs_parent_lost_phase_unpaired_runs_not_listed")
    r = S.compute(T)
    assert r["data_loss"] == [f"{Y.PARENT}@g1@12"]                                    # the parent's own lost run is listed; the non-finite design run and the not-ok NC run at 12 are not
    V, _ = S.valid_runs(T)
    assert list(S.diffs(V, "g1", S.names(T["roles"], "design")[0], Y.PARENT)) == ["11"] and S.nc_stage(T, V, "g1")["label"] == "CONSISTENT"
    assert all(e["phases"] == ["11"] for e in S.fit_stage(T, V)["est"].values()) and r["rs_not_fit"] is False


# ---- binding to the freezes (§10): tables, chain, environment, re-derivation ------------------------------------------------------------------------
def edit_json(path, **kw):
    obj = json.loads(Path(path).read_text())
    obj.update(kw)
    Path(path).write_text(json.dumps(obj, sort_keys=True))


def test_a_table_from_another_freeze_or_other_tools_is_refused(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.args.g1 = d.group("g1")
    t0 = d.tabs["g1"][0]
    saved = t0.read_text()
    edit_json(t0, freeze_sha256="0" * 64)
    with pytest.raises(ValueError, match="verified against another prerun freeze"):
        S.run_rs(d.args, d.oracle)
    t0.write_text(saved)
    edit_json(t0, harness_tool_sha256={"harness.py": "c" * 64})
    with pytest.raises(ValueError, match="harness tools differ from freeze 1's"):
        S.run_rs(d.args, d.oracle)
    t0.write_text(saved)
    S.run_rs(d.args, d.oracle)                                                                      # restored: accepted


def test_the_freeze_chain_the_environment_and_the_fingerprint_are_checked(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.args.g1 = d.group("g1")
    monkeypatch.setattr(S.platform, "python_version", lambda: "0.0.0")
    with pytest.raises(ValueError, match="environment .* differs from freeze 1's"):
        S.run_rs(d.args, d.oracle)
    monkeypatch.undo()
    monkeypatch.setattr(S, "ROOT", d.root)
    monkeypatch.setattr(S, "EV", d.ev)
    monkeypatch.setattr(SC, "validate_campaign", lambda c: None)
    monkeypatch.setattr(S, "CHECKER", types.SimpleNamespace(check=lambda t: S.compute(t), compare=lambda a, b, stage: [k for k in a if S.canon(a[k]) != S.canon(b.get(k))]))
    monkeypatch.setattr(P, "fingerprint", lambda: "0" * 64)
    with pytest.raises(ValueError, match="fingerprint\\(\\) differs from the frozen P0 fingerprint"):
        S.run_rs(d.args, d.oracle)                                                                   # no refinement point is gated under other gate-stack code
    monkeypatch.setattr(P, "fingerprint", lambda: Y.FINGERPRINT)
    S.run_rs(d.args, d.oracle)
    fz1 = d.freeze("freeze1")
    d.write("freeze1", {**fz1, "status": "edited after freeze 2"})
    with pytest.raises(ValueError, match="freeze2.json does not bind freeze1.json as it is on disk"):
        S.run_rs(d.args, d.oracle)


def test_a_frozen_file_is_looked_up_by_its_repo_relative_key(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.args.g1 = d.group("g1")
    fz1 = d.freeze("freeze1")
    key = f"{S.EV_REL}/states.json"
    unc = fz1["file_sha256"].pop(Y.UNC_STATES_REL)
    other = dict(fz1["file_sha256"])
    other[key] = unc                                                                                 # the UNC-01 hash under the SCREEN key: not the file
    for tampered, ok in ((other, False), (fz1["file_sha256"], True)):
        fz = {**fz1, "file_sha256": tampered}
        if ok:
            S.check_frozen(fz, key, "states.json")
        else:
            with pytest.raises(ValueError, match="not the states.json frozen"):
                S.check_frozen(fz, key, "states.json")
    with pytest.raises(ValueError, match="not the frozen file"):
        S.check_frozen({"kind": "freeze1", "file_sha256": {}}, "scripts/analyze_unc01.py", "frozen file")
    assert S.rel(d.root / "docs/harness/x.json") == "docs/harness/x.json" and S.rel("/nonexistent/elsewhere.json") == "/nonexistent/elsewhere.json"
    # every file the registration (§10) names is checked, not only the sources
    for f in ("scripts/analyze_unc01.py", "scripts/fid01/fid01_designs.py", "scripts/fid01/fid01_build.py", S.REG_REL, f"{S.EV_REL}/source_review/adoption.md", "scripts/screen01/INTERFACE.md", S.INFRA_REL, S.ROWS_REL):
        assert f in S.FROZEN_FILES
        (d.root / f).write_text((d.root / f).read_text() + " ")
        with pytest.raises(ValueError, match="not the frozen file"):
            S.run_rs(d.args, d.oracle)
        (d.root / f).write_text((d.root / f).read_text()[:-1])
    S.run_rs(d.args, d.oracle)


def test_rederivation_accepts_a_1e10_float_perturbation_and_refuses_a_name_change(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.stage_rs()

    def refreeze():
        fz = d.freeze("freeze2_1")
        sha = SC.sha256_path(d.args.rs)
        fz["rs_json_sha256"], fz["file_sha256"][S.rel(d.args.rs)] = sha, sha
        d.write("freeze2_1", fz)
    orig = d.args.rs.read_text()
    rs = json.loads(orig)
    rs["comparable"]["fit"]["downforce"]["coef"][0] *= 1 + 1e-10
    d.args.rs.write_text(json.dumps(rs, sort_keys=True))
    refreeze()
    assert d.stage_finalist()["comparable"]["finalist"] is not None                                    # within the 1e-9 tolerance
    (d.ev / "finalist.json").unlink()
    rs["comparable"]["fit"]["downforce"]["coef"][0] *= 1 + 1e-6
    d.args.rs.write_text(json.dumps(rs, sort_keys=True))
    refreeze()
    with pytest.raises(ValueError, match="rs does not re-derive|rs.json does not re-derive"):
        d.stage_finalist()
    rs = json.loads(orig)
    rs["proposals"][0]["name"] = "v18__camber_m1_pitch_p1_reflex_p1"
    d.args.rs.write_text(json.dumps(rs, sort_keys=True))
    refreeze()
    with pytest.raises(ValueError, match="proposal states differ"):
        d.stage_finalist()
    assert S.close({"a": [1.0, 2.0], "n": "x", "b": True, "i": 3}, {"a": [1.0 + 1e-10, 2.0], "n": "x", "b": True, "i": 3}) and not S.close({"i": 3}, {"i": 3.0 + 1e-3}) \
        and not S.close({"b": True}, {"b": 1}) and not S.close({"n": "x"}, {"n": "y"}) and not S.close([1.0], [1.0, 2.0]) and not S.close({"a": 1.0}, {"b": 1.0})
    assert not S.close({"i": 3}, {"i": 4}) and S.close({"f": 1e-12}, {"f": 2e-12}) and not S.close({"f": 5.0}, {"f": 5.0 + 1e-6})


# ---- finalists that are axial / design states, the handoff, the gate error row ------------------------------------------------------------------------
@pytest.mark.parametrize("name,role", [("main_axial_finalist", "axial"), ("main_design_finalist", "design")])
def test_handoff_of_an_axial_or_design_finalist_reads_the_p0_rows(tmp_path, monkeypatch, name, role):
    d = Disk(tmp_path, monkeypatch, name)
    out = d.run_all()
    ana = json.loads(out[d.args.out])
    f = ana["finalist"]
    assert d.T["roles"][f]["role"] == role and ana["outcome"] == "SCREEN01_GAIN"
    h = json.loads(out[d.args.out.with_name("xv_handoff.json")])
    assert h["admissibility_row"]["name"] == f and h["admissibility_row"]["slot"] == role and h["admissibility_row"]["phi_fortran_sha256"] == Y.sha_text(f)         # the P0 row, not rs.json
    assert h["spec"] == P.u_to_spec(d.T["roles"][f]["u"]) and h["in_camber_extension"] is (d.T["roles"][f]["u"][1] < -1.0)
    assert ana["detail"]["phases_used"]["finalist_exploration"] == ["11", "12"]                                                            # f_exp = g1


def test_handoff_content_and_its_file_checks(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    out = d.run_all()
    ana, h = json.loads(out[d.args.out]), json.loads(out[d.args.out.with_name("xv_handoff.json")])
    assert h["selection_bias_inputs"] == {"K": 19, "E_max_K": pytest.approx(S.e_max_normals(19)), "sigma_disc": {"central": 5.61e-4, "upper": 1.4474126675928642e-3},
                                          "retention": {"central": 0.655, "pessimistic": 0.57}, "xv_floor": S.XV_FLOOR}
    assert h["chain_controls"] == {"NC": ana["NC"], "determinism": ana["determinism"], "generation_drift": ana["generation_drift"]} and h["selection_bias"] == ana["selection_bias"]
    assert h["topology_policy_sha256"] == d.freeze("freeze1")["file_sha256"][S.POLICY_REL] and h["source_review_record_sha256"] == SC.sha256_path(d.root / f"{S.EV_REL}/source_review/adoption.md")
    assert h["phases_used"] == ana["detail"]["phases_used"] and h["phases_used"]["finalist_confirmation"] == {"f32": ["13", "14", "15", "16"], "f48": ["13", "14"]}
    assert h["phases_used"]["finalist_exploration"] == ["11", "12"] and set(h["phases_used"]) == {"finalist_confirmation", "r_best_confirmation", "manual_confirmation", "finalist_exploration"}
    assert h["phases"]["confirmation_flow_32"] == [13, 14, 15, 16] and h["table_sha256"].keys() == {"g1", "g2", "f32", "f48"}
    # the rows record is checked against freeze 1 before it is read
    d2 = Disk(tmp_path / "b", monkeypatch, "main_axial_finalist")
    d2.stage_rs()
    d2.stage_finalist()
    (d2.root / S.ROWS_REL).write_text((d2.root / S.ROWS_REL).read_text() + "\n")
    with pytest.raises(ValueError, match="not the frozen file"):
        d2.stage_main()


def test_a_gate_row_with_an_error_makes_rs_refuse(tmp_path, monkeypatch):
    d = Disk(tmp_path, monkeypatch)
    d.args.g1 = d.group("g1")

    def bad_oracle(T, workers):
        rows = {}

        def ask(u):
            n = Y.sname(u)
            rows[n] = {"name": n, "admissible": False, "error": "RuntimeError: boom", "phi_fortran_sha256": None}
            return False
        return ask, rows
    with pytest.raises(ValueError, match="gate evaluation of a refinement point raised"):
        S.run_rs(d.args, bad_oracle)
    assert not d.args.rs.exists()


def test_the_amplitude_mismatch_label_on_constructed_sets():
    T = Y.branch("fin_base")
    r = S.compute(T)
    assert set(r["amplitude_median_u_inf"]) == {"opt", "random"} and isinstance(r["AMPLITUDE_MISMATCH"], bool)
    opt = r["amplitude_median_u_inf"]["opt"]
    for st in S.names(T["roles"], "random"):                                                          # every random state at |u|_inf = the optimizer median + 0.2 / + 0.3
        T["roles"][st]["u"] = [opt + 0.2, 0.0, 0.0]
    r = S.compute(T)
    assert r["amplitude_median_u_inf"]["random"] == pytest.approx(opt + 0.2) and r["AMPLITUDE_MISMATCH"] is False                  # |0.2| <= 0.25
    for st in S.names(T["roles"], "random"):
        T["roles"][st]["u"] = [0.0, opt + 0.3, 0.0]
    r = S.compute(T)
    assert r["AMPLITUDE_MISMATCH"] is True                                                                                          # |0.3| > 0.25
    T2 = Y.branch("main_gain_no_manual")                                                              # computed whenever both sets exist, also without a confirmation estimate
    T2["roles"] = {n: x for n, x in T2["roles"].items() if x["role"] != "random"}
    T2["runs"] = {g: {s: v for s, v in by.items() if s in T2["roles"]} for g, by in T2["runs"].items()}
    assert S.compute(T2)["AMPLITUDE_MISMATCH"] is None and S.compute(T2)["amplitude_median_u_inf"]["random"] is None
    mr = res("main_incomplete_f32_kernel")
    assert isinstance(mr["AMPLITUDE_MISMATCH"], bool) and mr["G"] is None                              # ok3 false: the label is there all the same


def test_axial_design_proposal_candidates_report_i_and_the_estimates_report_their_phases():
    r = res("main_gain")
    assert r["I_candidates"].keys() == r["candidates"].keys() and all(v is None or isinstance(v, float) for v in r["I_candidates"].values())
    f = r["finalist"]
    assert r["I_candidates"][f] == pytest.approx(r["candidates"][f]["delta_bar"]["downforce"] / S.J_B48)
    assert r["detail"]["I_confirmation"]["f32"]["downforce"] == pytest.approx(r["confirmation"]["f32"]["delta_bar"]["downforce"] / S.J_B48)
    assert r["detail"]["phases_used"]["finalist_confirmation"] == {"f32": ["13", "14", "15", "16"], "f48": ["13", "14"]} and r["detail"]["phases_used"]["r_best_confirmation"]["f32"] == ["13", "14", "15", "16"]
    lost = res("main_incomplete_f32_kernel")
    assert lost["detail"]["phases_used"]["finalist_confirmation"]["f32"] == ["13", "14"]                  # the phases after DATA_LOSS / kernel loss


def test_cli_main_with_not_pushed_and_lost_arguments(tmp_path, monkeypatch, capsys):
    d = Disk(tmp_path, monkeypatch, "main_budget_with_full_data")
    d.stage_rs()
    d.stage_finalist()
    d.declare("main")
    grp = lambda g: [str(d.camp[g]), *map(str, d.tabs[g])]   # noqa: E731
    rec = d.args.not_pushed["f48k14"]["record"]
    out = d.ev / "analysis.json"
    monkeypatch.setattr(sys, "argv", ["x", "main", "--states", str(d.states), "--g1", *grp("g1"), "--g2", *grp("g2"), "--f32", *grp("f32"), "--f48", *grp("f48"), "--rs", str(d.args.rs),
                                      "--finalist", str(d.args.finalist), "--kernel-root", str(d.kr), "--not-pushed", f"f48k14=BUDGET:{rec}", "--out", str(out)])
    S.main()
    assert json.loads(out.read_text())["cause"] == ["BUDGET"]
    monkeypatch.setattr(sys, "argv", ["x", "main", "--lost", "g1k11", "--out", str(d.ev / "other.json")])
    with pytest.raises(ValueError, match="expected KERNEL=ID:RECORD"):
        S.main()


# ---- the budget record of the G2 push (registration §4.3) -----------------------------------------------------------------------------------------
def test_budget_before_the_g2_push_lists_all_five_unfinished_kernels(tmp_path, monkeypatch, capsys):
    def log(name, wall):
        p = tmp_path / name
        p.write_text(json.dumps([{"time": 1.0, "data": "x"}, {"time": wall, "data": "y"}]))
        return str(p)
    five = ("g2", "f48k13", "f48k14", "f32a", "f32b")
    r = S.budget([("g1k11", log("a", 16100.0)), ("g1k12", log("b", 15900.0))], [(k, None) for k in five])           # the confirmation campaigns do not exist yet: the registered estimates
    assert set(r["pending_estimate_s"]) == set(five) and set(r["finished_session_wall_s"]) == {"g1k11", "g1k12"}
    assert r["pending_estimate_s"] == {"g2": [4410], "f48k13": [7280], "f48k14": [7280], "f32a": [5240], "f32b": [4410]}                   # §4.2 at the registered run counts
    assert r["T_s"] == 16100.0 + 15900.0 + 4410 + 2 * 7280 + 5240 + 4410 and r["decision"] == "go" and r["rule"] == "registration §4.3" and r["cap_s"] == 86400
    out = tmp_path / "budget_g2.json"
    monkeypatch.setattr(sys, "argv", ["x", "budget", "--finished", f"g1k11={log('c', 16100.0)}", f"g1k12={log('d', 15900.0)}", "--pending", *five, "--out", str(out)])
    S.main()
    rec = json.loads(out.read_text())
    assert rec == r and "go" in capsys.readouterr().out
    assert S.REG_RUNS["g2"] == (10, "flow_32") and all(S.REG_RUNS[k][0] * S.EST_S[S.REG_RUNS[k][1]] + S.SETUP_S == v[0] for k, v in r["pending_estimate_s"].items())
    one = S.budget([("g1k11", log("e", 16100.0)), ("g1k12", log("f", 15900.0))], [("g2", None)])                                          # a record listing only g2 is a different record
    assert set(one["pending_estimate_s"]) == {"g2"} and one["T_s"] < r["T_s"]
