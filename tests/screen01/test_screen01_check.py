"""SCREEN-01 independent checker (scripts/screen01/screen01_check.py) on small synthetic T tables with closed-form expectations.

Every expected value below is derived by hand from the registration text (s5.1-s5.9, s6), not by calling the checker's own helpers.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/screen01")]
import screen01_check as C  # noqa: E402

PAR = (1.0, 0.5)                          # parent downforce, drag (N) at every kernel and phase
X_STAR = 7.184166586553256e-3             # g_min J_b,48
J48 = 0.26577921974115387
FL_DF, FL_DR = 2.0904201605451784e-4, 1.36408347135453e-4
NC_REF, NC_SE = -1.6476407624087992e-3, 8.534104568937632e-5
T3 = 2.3533634348018233                   # t_{0.95, 3}
AX = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
DS = [(a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)] + [(0, .5, -.5)]
RNG = np.random.default_rng(7)
U_RAND = [list(map(float, RNG.uniform([-1, -1.5, -1], [1, 1, 1]))) for _ in range(19)]


def feat(u):
    p, c, r = u
    return np.array([p, c, r, p * p, c * c, r * r, p * c, p * r, c * r], float)


def rn(df, dr, ok=True):
    return {"downforce": df, "drag": dr, "ok": ok}


def setd(T, kernel, state, phase, df=0.0, dr=0.0, ok=True):  # a run = the parent forces + (df, dr)
    T["runs"][kernel].setdefault(state, {})[str(phase)] = rn(PAR[0] + df, PAR[1] + dr, ok)


def delta(T, kernel, state, dfs, drs, phases):
    for k, a, b in zip(phases, dfs, drs):
        setd(T, kernel, state, k, a, b)


def base(n_prop=0, n_rand=3):
    """Complete, loss-free tables; every non-parent state has downforce difference 0 and drag +1e-3 (infeasible); NC sits on its reference."""
    role = lambda r, o, u=None: {"role": r, "order": o, "u": None if u is None else [float(x) for x in u]}
    R = {"P": role("parent", 0), "REP": role("parent_repeat", 0)}
    R.update({f"A{i}": role("axial", i, u) for i, u in enumerate(AX)})
    R.update({f"D{i}": role("design", i, u) for i, u in enumerate(DS)})
    R.update({"M": role("manual", 0, [0.3, -1.1, 0.2]), "REF": role("ref", 0, [-0.574, 0, -0.386]), "NC": role("nc", 0)})
    R.update({f"R{i}": role("random", i, U_RAND[i]) for i in range(n_rand)})
    R.update({f"X{i}": role("proposal", i, [0.9, -0.1 * i, 0.5 + 0.1 * i]) for i in range(n_prop)})
    T = {"schema": "screen01-T-v1", "stage": "main", "roles": R, "runs": {"g1": {}, "g2": {}, "f32": {}, "f48": {}}, "lost_kernels": [], "gating": []}
    for k in (11, 12):
        setd(T, "g1", "P", k)
        for s, r in R.items():
            if r["role"] not in ("parent", "parent_repeat", "proposal"):
                setd(T, "g1", s, k, NC_REF if s == "NC" else 0.0, 0.0 if s == "NC" else 1e-3)
        for i in range(n_prop):
            setd(T, "g2", "P", k)
            setd(T, "g2", f"X{i}", k, 0.0, 1e-3)
    setd(T, "g1", "REP", 11)
    for k in (11, 13, 14, 15, 16):
        setd(T, "f32", "P", k)
    setd(T, "f32", "REP", 13)
    for k in (13, 14):
        setd(T, "f48", "P", k)
    ys = [0.020, 0.018, 0.016, 0.014]
    T["gating"] = [{"name": f"X{i}", "u": R[f"X{i}"]["u"], "target_index": [0, 1, 2, 0][i], "y_pred": ys[i], "z_pred": -0.002, "admissible": True}
                   for i in range(n_prop)]
    return T


def happy():
    """A GAIN scenario: A0 is the finalist (exploration 0.012 / -0.002), R0 the R-best, K_opt = K_rand = 19."""
    T = base(n_prop=4, n_rand=19)
    delta(T, "g1", "A0", [0.0121, 0.0119], [-0.0021, -0.0019], (11, 12))
    delta(T, "g1", "R0", [0.0041, 0.0039], [-0.0011, -0.0009], (11, 12))
    P4 = (13, 14, 15, 16)
    delta(T, "f32", "A0", [0.0101, 0.0099, 0.0101, 0.0099], [-0.0021, -0.0019, -0.0021, -0.0019], P4)
    delta(T, "f32", "R0", [0.0041, 0.0039, 0.0040, 0.0040], [-0.0011, -0.0009, -0.0010, -0.0010], P4)
    delta(T, "f32", "M", [0.003] * 4, [-0.0005] * 4, P4)
    delta(T, "f32", "NC", [NC_REF] * 4, [0.0] * 4, P4)
    delta(T, "f48", "A0", [0.0100, 0.0098], [-0.0020, -0.0020], (13, 14))
    delta(T, "f48", "R0", [0.0040, 0.0040], [-0.0010, -0.0010], (13, 14))
    return T


def view(T, stage):
    T = copy.deepcopy(T)
    T["stage"] = stage
    T["runs"] = {k: v for k, v in T["runs"].items() if k in {"rs": ("g1",), "finalist": ("g1", "g2"), "main": ("g1", "g2", "f32", "f48")}[stage]}
    return T


def run(T, stage="main"):
    return C.check(view(T, stage))


# ---- s5.8 outcome steps ----------------------------------------------------------------------------------------------------------------------------
def test_happy_gain_every_label():
    o = run(happy())
    assert set(o) == set(C.SPECS["main"]) and not C.compare(o, copy.deepcopy(o), "main")
    assert (o["outcome"], o["cause"], o["finalist"], o["futility"], o["r_best"]) == ("SCREEN01_GAIN", [], "A0", None, "R0")
    assert (o["K_opt"], o["K_rand"], o["search_complete"], o["pool_limited"], o["data_loss"]) == (19, 19, True, False, [])
    assert o["proposals_from_gating"] == ["X0", "X1", "X2", "X3"]
    assert o["G"] == {"decision": "PASS", "GAIN_RESOLVED_ABOVE_MIN": True}
    assert o["D"] == {"decision": "PASS", "label": "PASS_RESOLVED"}
    assert o["R3"]["label"] == "R3_CONFIRMED" and o["R3"]["R3_RATIO_IN_BAND"] and o["R3"]["G48_ABOVE_MIN"] and not o["R3"]["R3_E2_EXCEEDED"]
    assert o["R3"]["R3_DRAG_SAME_SIGN"] and o["R3"]["G48_MARGIN"] == pytest.approx(0.0099 - X_STAR, abs=1e-12)
    assert o["NC"]["g1"] == {"z": pytest.approx(0, abs=1e-9), "label": "CONSISTENT"}
    assert o["determinism"] == {k: {"max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "nondeterminism": False, "judged": True} for k in ("g1k11", "f32a")}
    assert o["generation_drift"] == {"max_abs_diff": {"downforce": 0.0, "drag": 0.0}, "drift": False}
    assert o["generation_drift"]["drift"] is False
    assert o["controls"] == {"OPT_VS_RANDOM": "OPT_BEATS_RANDOM", "OPT_VS_MANUAL": "OPT_BEATS_MANUAL", "RANDOM_FEASIBLE_GAIN": False, "K_MISMATCH": False}
    c = o["confirmation"]["f32"]
    assert c["P"] == 4 and c["delta_bar"]["downforce"] == pytest.approx(0.0100, abs=1e-12) and c["delta_bar"]["drag"] == pytest.approx(-0.0020, abs=1e-12)
    assert c["sigma_d"]["downforce"] == pytest.approx(math.sqrt(4 * 1e-8 / 3), rel=1e-6)
    assert c["se_eff"]["downforce"] == pytest.approx(FL_DF / 2, rel=1e-12) and c["se_eff"]["drag"] == pytest.approx(FL_DR / 2, rel=1e-12)  # sigma_d below the floors
    assert o["confirmation"]["f48"]["P"] == 2 and o["confirmation"]["f48"]["se_eff"]["downforce"] == pytest.approx(FL_DF / math.sqrt(2), rel=1e-12)


def test_step1_minimum_data():
    T = happy()
    del T["runs"]["g1"]["NC"]
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INCOMPLETE", ["DATA_G1"])
    T = happy()
    for k in "11", "12":
        T["runs"]["g1"]["P"][k]["ok"] = False
    assert run(T)["cause"] == ["DATA_G1"]


def test_step2_invalid_g1():
    dev = 3.5 * math.sqrt((3e-4 / math.sqrt(2)) ** 2 + NC_SE ** 2)  # the z = 3.5 boundary at P = 2 (8.0e-4 N)
    for d, label, oc in ((dev - 1e-5, "CONSISTENT", "SCREEN01_GAIN"), (dev + 1e-5, "NOT_CONSISTENT", "SCREEN01_INVALID"), (-dev - 1e-5, "NOT_CONSISTENT", "SCREEN01_INVALID")):
        T = happy()
        delta(T, "g1", "NC", [NC_REF + d] * 2, [0, 0], (11, 12))
        o = run(T)
        assert o["NC"]["g1"]["label"] == label and o["outcome"] == oc
        assert o["NC"]["g1"]["z"] == pytest.approx(abs(d) / math.sqrt((3e-4 / math.sqrt(2)) ** 2 + NC_SE ** 2), rel=1e-9)
    T = happy()
    delta(T, "g1", "NC", [NC_REF + 2 * dev] * 2, [0, 0], (11, 12))
    assert run(T)["cause"] == ["NC_G1"]
    T = happy()
    setd(T, "g1", "REP", 11, 2.5e-4, 0.0)
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"])


def test_step3_no_finalist_causes():
    T = happy()
    for k in "11", "12":
        T["runs"]["g1"]["A0"][k]["drag"] = PAR[1] + 1e-3  # no feasible candidate anywhere
    o = run(T)
    assert (o["finalist"], o["futility"], o["search_complete"]) == (None, "NO_FEASIBLE_CANDIDATE", True)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_NO_GAIN", ["NO_FEASIBLE_CANDIDATE"])
    T = happy()
    delta(T, "g1", "A0", [0.004, 0.004], [-0.001, -0.001], (11, 12))  # feasible, but 0.004 < x* - 3 SE_eff
    o = run(T)
    assert (o["finalist"], o["futility"]) == (None, "GAIN_BELOW_MIN_AT_SELECTION")
    assert (o["outcome"], o["cause"]) == ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN_AT_SELECTION"])
    # one lost G1 kernel (phase 12 everywhere): the NO_GAIN becomes INCOMPLETE (DATA_G1)
    T = happy()
    for s in T["runs"]["g1"]:
        T["runs"]["g1"][s].pop("12", None)
    delta(T, "g1", "A0", [0.004], [-0.001], (11,))
    o = run(T)
    assert (o["search_complete"], o["outcome"], o["cause"]) == (False, "SCREEN01_INCOMPLETE", ["DATA_G1"])
    # RS_NOT_FIT (both phases lost for 8 design points) and no finalist: the design points lack phases AND the fit failed -> both causes, stage order (s5.11.7)
    T = base(n_prop=0)
    for i in range(1, 9):
        T["runs"]["g1"].pop(f"D{i}")
    o = run(T)
    assert (o["search_complete"], o["outcome"], o["cause"]) == (False, "SCREEN01_INCOMPLETE", ["DATA_G1", "DATA_REFINE"])
    # G2 kernel lost, G1 complete, no feasible candidate -> DATA_G2
    T = base(n_prop=4)
    T["runs"]["g2"] = {}
    o = run(T)
    assert (o["search_complete"], o["outcome"], o["cause"]) == (False, "SCREEN01_INCOMPLETE", ["DATA_G2"])
    # one G1 kernel lost (phase 12) and the G2 kernel lost, the fit still OK: DATA_G1 then DATA_G2; the first entry is the primary cause
    T = base(n_prop=4)
    T["runs"]["g2"] = {}
    for s_ in T["runs"]["g1"]:
        T["runs"]["g1"][s_].pop("12", None)
    T["lost_kernels"] = ["g1k12", "g2"]
    assert run(T)["cause"] == ["DATA_G1", "DATA_G2"]
    # DATA_G2 needs the fit OK: with RS_NOT_FIT and lost proposals the list is DATA_G1 (design lost), DATA_REFINE only
    T = base(n_prop=4)
    T["runs"]["g2"] = {}
    for i in range(1, 9):
        T["runs"]["g1"].pop(f"D{i}")
    assert run(T)["cause"] == ["DATA_G1", "DATA_REFINE"]
    # a declared-lost G1 kernel is DATA_G1 even when every search state still has both phases (reported only while search_complete is false)
    T = base(n_prop=4)
    T["runs"]["g2"] = {}
    T["lost_kernels"] = ["g1k11"]
    assert run(T)["cause"] == ["DATA_G1", "DATA_G2"]
    # G2 lost but a finalist exists among the measured states: the study continues (finalist from measured states)
    T = happy()
    T["runs"]["g2"] = {}
    o = run(T)
    assert (o["search_complete"], o["finalist"], o["outcome"]) == (False, "A0", "SCREEN01_GAIN")


def test_step4_confirmation_data():
    T = happy()
    for k in "15", "16":
        del T["runs"]["f32"]["A0"][k]  # |Phi_s| = 2
    o = run(T)
    assert (o["outcome"], o["cause"], o["G"], o["D"]) == ("SCREEN01_INCOMPLETE", ["DATA_F"], None, None)
    T = happy()
    T["runs"]["f32"]["A0"].pop("15")  # |Phi_s| = 3 suffices
    assert run(T)["outcome"] == "SCREEN01_GAIN"
    T = happy()
    T["runs"]["f48"] = {}
    assert run(T)["cause"] == ["BUDGET"]  # flow_48 never run
    T["lost_kernels"] = ["f48k13", "f48k14"]
    assert run(T)["cause"] == ["DATA_F"]  # both kernels declared lost
    T = happy()
    for s_ in list(T["runs"]["f32"]):  # f32b never pushed (budget): F not completed even though 2 + ... phases exist
        for k in "15", "16":
            T["runs"]["f32"][s_].pop(k, None)
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INCOMPLETE", ["BUDGET"])
    T["lost_kernels"] = ["f32b"]  # declared lost: the same missing data is DATA_F
    assert run(T)["cause"] == ["DATA_F"]
    T = happy()
    del T["runs"]["f48"]["A0"]["14"]  # one f48 kernel lost (the parent row stays: the kernel ran): P = 1, floor SE, continues
    o = run(T)
    assert o["outcome"] == "SCREEN01_GAIN" and o["confirmation"]["f48"]["P"] == 1 and o["confirmation"]["f48"]["se_eff"]["downforce"] == FL_DF
    T = happy()
    del T["runs"]["f32"]["NC"]  # NC lost at every confirmation phase: cannot be judged
    o = run(T)
    assert (o["outcome"], o["cause"], o["NC"]["f32"]) == ("SCREEN01_INCOMPLETE", ["DATA_F"], {"z": None, "label": None})


def test_step5_invalid_f():
    dev = 3.5 * math.sqrt((3e-4 / 2) ** 2 + NC_SE ** 2)  # z = 3.5 at P = 4
    T = happy()
    delta(T, "f32", "NC", [NC_REF + dev - 1e-5] * 4, [0] * 4, (13, 14, 15, 16))
    assert run(T)["outcome"] == "SCREEN01_GAIN"
    delta(T, "f32", "NC", [NC_REF + dev + 1e-5] * 4, [0] * 4, (13, 14, 15, 16))
    o = run(T)
    assert (o["outcome"], o["cause"], o["NC"]["f32"]["label"]) == ("SCREEN01_INVALID", ["NC_F"], "NOT_CONSISTENT")
    T = happy()
    setd(T, "f32", "REP", 13, 0.0, -3e-4)  # the drag differs by more than the downforce floor 2.09e-4
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INVALID", ["NONDETERMINISM_F32A"])
    setd(T, "f32", "REP", 13, 0.0, -1.5e-4)  # within the floor
    assert run(T)["outcome"] == "SCREEN01_GAIN"


def test_step6_no_gain_causes_in_order():
    T = happy()
    delta(T, "f32", "A0", [0.006] * 4, [-0.002] * 4, (13, 14, 15, 16))
    o = run(T)
    assert (o["outcome"], o["cause"], o["G"]["decision"]) == ("SCREEN01_NO_GAIN", ["GAIN_BELOW_MIN"], "FAIL")
    T = happy()
    delta(T, "f32", "A0", [0.0100] * 4, [0.0003] * 4, (13, 14, 15, 16))
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_NO_GAIN", ["DRAG_VIOLATION"])
    T = happy()
    delta(T, "f48", "A0", [-0.0005, 0.0005], [-0.002] * 2, (13, 14))  # point mean 0 -> sign split (<= 0)
    delta(T, "f48", "A0", [-0.0005, -0.0001], [-0.002] * 2, (13, 14))
    o = run(T)
    assert (o["outcome"], o["cause"], o["R3"]["label"]) == ("SCREEN01_NO_GAIN", ["GRID_SIGN_SPLIT"], "R3_SIGN_SPLIT")
    delta(T, "f32", "A0", [0.006] * 4, [0.0003] * 4, (13, 14, 15, 16))  # all three failing rules are listed, in registered order
    assert run(T)["cause"] == ["GAIN_BELOW_MIN", "DRAG_VIOLATION", "GRID_SIGN_SPLIT"]
    T = happy()  # step 6 precedes step 7: an unresolved G with a drag violation is NO_GAIN
    delta(T, "f32", "A0", [0.0075, 0.0075, 0.0075, 0.0075], [0.0003] * 4, (13, 14, 15, 16))
    assert run(T)["outcome"] == "SCREEN01_NO_GAIN"


def test_step7_inconclusive():
    a = 5e-3  # SD = 5.77e-3, 3 SE = 8.66e-3 >= 0.0075 >= x*
    T = happy()
    delta(T, "f32", "A0", [0.0075 + a, 0.0075 - a, 0.0075 + a, 0.0075 - a], [-0.002] * 4, (13, 14, 15, 16))
    o = run(T)
    assert (o["outcome"], o["cause"], o["G"]) == ("SCREEN01_INCONCLUSIVE", ["G_UNRESOLVED"], {"decision": "UNRESOLVED", "GAIN_RESOLVED_ABOVE_MIN": False})
    T = happy()
    delta(T, "f48", "A0", [3e-4, 3e-4], [-0.002] * 2, (13, 14))  # 0 < 3e-4 <= 3 SE_eff,48 = 4.43e-4
    o = run(T)
    assert (o["outcome"], o["cause"], o["R3"]["label"]) == ("SCREEN01_INCONCLUSIVE", ["R3_UNRESOLVED"], "R3_UNRESOLVED")


# ---- s5.5 rules -----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("m,a,dec,res", [(0.0100, 1e-4, "PASS", True), (0.0073, 1e-4, "PASS", False), (0.0075, 5e-3, "UNRESOLVED", False), (0.0060, 1e-4, "FAIL", False),
                                         (0.0075, 1e-4, "PASS", True)])
def test_G_rule_and_resolved_label(m, a, dec, res):
    T = happy()
    delta(T, "f32", "A0", [m + a, m - a, m + a, m - a], [-0.002] * 4, (13, 14, 15, 16))
    assert run(T)["G"] == {"decision": dec, "GAIN_RESOLVED_ABOVE_MIN": res}


@pytest.mark.parametrize("m,dec,label", [(-2e-3, "PASS", "PASS_RESOLVED"), (-3e-4, "PASS", "PASS_UNRESOLVED"), (-1e-6, "PASS", "PASS_UNRESOLVED"),
                                         (1e-6, "VIOLATION", "VIOLATION_UNRESOLVED"), (3e-4, "VIOLATION", "VIOLATION_UNRESOLVED"), (2e-3, "VIOLATION", "VIOLATION_RESOLVED")])
def test_D_labels(m, dec, label):  # SD 5.77e-4, SE 2.89e-4, t SE = 6.79e-4 (t_{0.95,3} = 2.3534)
    a = 5e-4
    T = happy()
    delta(T, "f32", "A0", [0.0100] * 4, [m + a, m - a, m + a, m - a], (13, 14, 15, 16))
    assert run(T)["D"] == {"decision": dec, "label": label}


def test_R3_labels():
    T = happy()
    delta(T, "f48", "A0", [0.0130, 0.0130], [0.001, 0.001], (13, 14))  # ratio 1.30, margin 5.8e-3, |48-32| = 3e-3 > 1.807e-3, drag sign differs
    r = run(T)["R3"]
    assert r["label"] == "R3_CONFIRMED" and r["R3_RATIO_IN_BAND"] is False and r["R3_E2_EXCEEDED"] is True and r["R3_DRAG_SAME_SIGN"] is False
    assert r["G48_ABOVE_MIN"] is True and r["G48_MARGIN"] == pytest.approx(0.0130 - X_STAR, abs=1e-12)
    delta(T, "f48", "A0", [0.0070, 0.0070], [-0.002] * 2, (13, 14))  # ratio 0.70, below the minimum gain
    r = run(T)["R3"]
    assert r["R3_RATIO_IN_BAND"] is False and r["G48_ABOVE_MIN"] is False and r["G48_MARGIN"] < 0 and r["R3_E2_EXCEEDED"] is True  # |0.007 - 0.010| = 3e-3


def test_selection_bias_numbers_and_boundaries():
    # K = 19: E[max] = 1.8444815116; central boundary I = 2.32 %, pessimistic 3.23 % (registration s5.7)
    E = 1.8444815116038256
    for I, lc, lp in ((0.0235, "ADEQUATE", "THIN"), (0.0230, "THIN", "THIN"), (0.0325, "ADEQUATE", "ADEQUATE"), (0.0320, "ADEQUATE", "THIN")):
        T = happy()
        delta(T, "f32", "A0", [I * J48] * 4, [-0.002] * 4, (13, 14, 15, 16))
        s = run(T)["selection_bias"]
        gc, gp = 0.655 * (I - E * 5.61e-4 / J48), 0.57 * (I - E * 1.4474126675928642e-3 / J48)
        assert s["b_K"]["central"] == pytest.approx(E * 5.61e-4, rel=1e-9) and s["b_K"]["upper"] == pytest.approx(E * 1.4474126675928642e-3, rel=1e-9)
        assert s["g_XV_exp"]["central"] == pytest.approx(gc, rel=1e-8) and s["g_XV_exp"]["pessimistic"] == pytest.approx(gp, rel=1e-8)
        assert s["XV_MARGIN"] == {"central": "XV_MARGIN_" + lc, "pessimistic": "XV_MARGIN_" + lp}
    assert C._emax(1) == 0.0 and C._emax(2) == pytest.approx(1 / math.sqrt(math.pi), rel=1e-10) and C._emax(19) == pytest.approx(E, rel=1e-10)


def test_controls_labels():
    T = happy()
    delta(T, "f32", "R0", [0.0100, 0.0100, 0.0101, 0.0099], [-0.001] * 4, (13, 14, 15, 16))  # e = (0.0001, -0.0001, 0, 0): mean 0 -> unresolved
    assert run(T)["controls"]["OPT_VS_RANDOM"] == "OPT_RANDOM_UNRESOLVED"
    delta(T, "f32", "R0", [0.0151, 0.0149, 0.0151, 0.0149], [-0.001] * 4, (13, 14, 15, 16))  # e = -0.005 (+-1e-4): RANDOM_BEATS_OPT; R-best passes G, D and R3 (f48 0.004 > 3 SE)
    c = run(T)["controls"]
    assert c["OPT_VS_RANDOM"] == "RANDOM_BEATS_OPT" and c["RANDOM_FEASIBLE_GAIN"] is True
    delta(T, "f48", "R0", [-0.001, -0.001], [-0.001] * 2, (13, 14))                  # R3 sign split: no longer passes
    assert run(T)["controls"]["RANDOM_FEASIBLE_GAIN"] is False
    delta(T, "f48", "R0", [0.004, 0.004], [-0.001] * 2, (13, 14))
    delta(T, "f32", "R0", [0.0151, 0.0149, 0.0151, 0.0149], [0.001] * 4, (13, 14, 15, 16))  # drag violation: no longer passes D
    assert run(T)["controls"]["RANDOM_FEASIBLE_GAIN"] is False
    T = happy()
    for k in "11", "12":  # no feasible random member
        T["runs"]["g1"]["R0"][k]["drag"] = PAR[1] + 1e-3
    c = run(T)["controls"]
    assert (c["OPT_VS_RANDOM"], c["RANDOM_FEASIBLE_GAIN"]) == ("RANDOM_NO_FEASIBLE", False) and run(T)["r_best"] is None
    T = happy()
    del T["roles"]["M"]
    assert run(T)["controls"]["OPT_VS_MANUAL"] == "MANUAL_NONE"
    T = happy()
    for k in "15", "16", "14":  # M left with one confirmation phase: UNRESOLVED
        del T["runs"]["f32"]["M"][k]
    assert run(T)["controls"]["OPT_VS_MANUAL"] == "OPT_MANUAL_UNRESOLVED"
    T = base(n_rand=3)
    assert run(T)["controls"]["K_MISMATCH"] is True


def test_determinism_judged_on_raw_runs():
    T = happy()
    setd(T, "g1", "REP", 11, 1.5e-4, 0.0)  # within the downforce floor 2.09e-4
    d = run(T)["determinism"]["g1k11"]
    assert d["nondeterminism"] is False and d["judged"] is True and d["max_abs_diff"]["downforce"] == pytest.approx(1.5e-4, abs=1e-12)
    setd(T, "g1", "REP", 11, 2.5e-4, 0.0)  # strictly above the floor
    assert run(T)["determinism"]["g1k11"]["nondeterminism"] is True
    setd(T, "g1", "REP", 11, 0.0, 2.5e-4)  # drag counts, against the same (downforce) floor
    assert run(T)["determinism"]["g1k11"]["nondeterminism"] is True
    setd(T, "g1", "REP", 11, 0.3, 0.0)  # 30 % off: DATA_LOSS (listed, uniform rule) AND NONDETERMINISM (raw runs): the check is not removed by the loss
    o = run(T)
    assert o["determinism"]["g1k11"]["nondeterminism"] is True and o["data_loss"] == ["REP@g1@11"]
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INVALID", ["NONDETERMINISM_G1K11"])
    T["runs"]["g1"]["REP"]["11"]["downforce"] = None  # ok, but a non-finite force against a finite ok parent run: not reproduced
    o = run(T)
    assert o["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": True, "judged": True} and o["data_loss"] == ["REP@g1@11"]
    T["runs"]["g1"]["REP"]["11"]["ok"] = False  # not ok: NOT_JUDGED, no outcome effect
    o = run(T)
    assert o["determinism"]["g1k11"] == {"max_abs_diff": None, "nondeterminism": False, "judged": False} and o["outcome"] == "SCREEN01_GAIN"
    del T["runs"]["g1"]["REP"]  # absent: NOT_JUDGED
    assert run(T)["determinism"]["g1k11"]["judged"] is False
    T = happy()  # the parent run at that phase is invalid: nothing to compare with
    T["runs"]["g1"]["P"]["11"]["ok"] = False
    assert run(T)["determinism"]["g1k11"]["judged"] is False
    T = happy()  # f32a: the repeat at phase 13 only
    setd(T, "f32", "REP", 13, 3e-4, 0.0)
    assert run(T)["determinism"]["f32a"] == {"max_abs_diff": {"downforce": pytest.approx(3e-4, abs=1e-12), "drag": 0.0}, "nondeterminism": True, "judged": True}
    T["runs"]["f32"]["REP"] = {"14": T["runs"]["f32"]["REP"]["13"]}  # a repeat row at another phase is not the f32a check
    assert run(T)["determinism"]["f32a"]["judged"] is False


def test_generation_drift_raw_and_null():
    T = happy()  # drift: f32 parent at phase 11 against the g1 parent at phase 11, label only
    setd(T, "f32", "P", 11, 3e-4, 0.0)
    o = run(T)
    assert o["generation_drift"]["drift"] is True and o["generation_drift"]["max_abs_diff"]["downforce"] == pytest.approx(3e-4, abs=1e-12) and o["outcome"] == "SCREEN01_GAIN"
    setd(T, "f32", "P", 11, 0.0, 1e-4)
    assert run(T)["generation_drift"]["drift"] is False
    setd(T, "f32", "P", 11, 0.0, 3e-4)  # drag differences count against the downforce floor too
    assert run(T)["generation_drift"]["drift"] is True
    T["runs"]["f32"]["P"]["11"]["downforce"] = None  # either run invalid: null and false
    assert run(T)["generation_drift"] == {"max_abs_diff": None, "drift": False}
    T = happy()
    del T["runs"]["g1"]["P"]["11"]
    assert run(T)["generation_drift"] == {"max_abs_diff": None, "drift": False}


# ---- s5.1 data loss and estimators ------------------------------------------------------------------------------------------------------------------------
def test_data_loss_triggers_and_effect():
    T = happy()
    T["runs"]["g1"]["A0"]["11"]["downforce"] = None            # non-finite force
    T["runs"]["g1"]["A1"]["12"]["ok"] = False                  # verify failed / cap / unfinished
    T["runs"]["g1"]["A2"]["11"]["downforce"] = 1.3             # |dF| = 0.3 > 0.25 |F_parent|
    T["runs"]["g1"]["A3"]["12"]["downforce"] = 1.25            # exactly 0.25 |F_parent|: kept
    T["runs"]["g1"]["A4"]["11"]["drag"] = PAR[1] + 0.13        # drag bound 0.125
    T["runs"]["g1"]["A5"]["11"]["drag"] = float("inf")
    o = run(T, "finalist")
    assert o["data_loss"] == ["A0@g1@11", "A1@g1@12", "A2@g1@11", "A4@g1@11", "A5@g1@11"]
    assert [o["candidates"][s]["P"] for s in ("A0", "A1", "A2", "A3", "A4", "A5")] == [1, 1, 1, 2, 1, 1]
    assert o["candidates"]["A0"]["delta_bar"]["downforce"] == pytest.approx(0.0119, abs=1e-12)  # only phase 12 left
    assert o["search_complete"] is False


def test_parent_lost_removes_the_phase_for_everyone():
    T = happy()
    T["runs"]["g1"]["P"]["11"]["drag"] = None
    o = run(T, "finalist")
    assert o["data_loss"] == ["P@g1@11"] and o["candidates"]["A0"]["P"] == 1 and o["candidates"]["A0"]["delta_bar"]["downforce"] == pytest.approx(0.0119, abs=1e-12)
    assert o["search_complete"] is False


def test_P1_floor_and_two_phase_sd():
    T = happy()
    del T["runs"]["g1"]["A0"]["12"]
    c = run(T, "finalist")["candidates"]["A0"]
    assert c["P"] == 1 and c["se_eff"] == {"downforce": FL_DF, "drag": FL_DR}  # |Phi| = 1 -> SE_eff = floor
    T = happy()  # |Phi| = 2: SD = |d1 - d2| / sqrt 2 = 0.0042 / sqrt 2 > floor -> SE_eff = SD / sqrt 2 = 0.0021
    delta(T, "g1", "A1", [0.0021, 0.0063], [0.0, 0.0], (11, 12))
    c = run(T, "finalist")["candidates"]["A1"]
    assert c["delta_bar"]["downforce"] == pytest.approx(0.0042, abs=1e-12) and c["se_eff"]["downforce"] == pytest.approx(0.0021, abs=1e-12)
    assert c["se_eff"]["drag"] == pytest.approx(FL_DR / math.sqrt(2), abs=1e-15)


def test_replay_and_lost_marker_stage_names():
    T = happy()
    T["runs"]["f32"]["R0"]["13"]["ok"] = False
    T["runs"]["f48"]["A0"]["14"]["downforce"] = 1.9  # > 0.25 F_parent
    o = run(T)
    assert o["data_loss"] == ["A0@f48@14", "R0@f32@13"]


# ---- s5.4 finalist / futility / ties / POOL_LIMITED -------------------------------------------------------------------------------------------------------
def test_exact_ties_follow_registered_order():
    T = base(n_prop=2)
    for s in ("D0", "A1", "A0", "X0"):
        delta(T, "g1" if s[0] != "X" else "g2", s, [0.0100, 0.0100], [-0.001, -0.001], (11, 12))
    assert run(T, "finalist")["finalist"] == "A0"                       # axial in mode order, + before -
    delta(T, "g1", "A0", [0.0099] * 2, [-0.001] * 2, (11, 12))
    assert run(T, "finalist")["finalist"] == "A1"
    delta(T, "g1", "A1", [0.0099] * 2, [-0.001] * 2, (11, 12))
    assert run(T, "finalist")["finalist"] == "D0"                       # a design point before a proposal
    delta(T, "g1", "D0", [0.0099] * 2, [-0.001] * 2, (11, 12))
    assert run(T, "finalist")["finalist"] == "X0"                       # the proposal wins only when strictly larger


def test_feasibility_is_the_point_sign_and_infeasible_gain_is_ignored():
    T = base()
    delta(T, "g1", "A0", [0.05] * 2, [1e-9] * 2, (11, 12))             # the largest gain, drag marginally positive: infeasible
    delta(T, "g1", "A1", [0.0100] * 2, [-1e-9] * 2, (11, 12))
    o = run(T, "finalist")
    assert o["candidates"]["A0"]["feasible"] is False and o["candidates"]["A1"]["feasible"] is True and o["finalist"] == "A1"


def test_futility_threshold_is_x_star_minus_3_se():
    se3 = 3 * FL_DF / math.sqrt(2)  # two identical phases: SD 0 -> SE_eff = floor / sqrt 2
    for d, fin in ((X_STAR - se3 + 1e-6, "A0"), (X_STAR - se3 - 1e-6, None)):
        T = base()
        delta(T, "g1", "A0", [d] * 2, [-0.001] * 2, (11, 12))
        o = run(T, "finalist")
        assert o["finalist"] == fin and o["futility"] == (None if fin else "GAIN_BELOW_MIN_AT_SELECTION")


def test_search_complete_conditions():
    T = happy()
    assert run(T, "finalist")["search_complete"] is True
    for s in ("R5", "M", "REF", "NC"):  # R, M, ref, NC losses have no effect on search_complete (s5.9)
        del T["runs"]["g1"][s]["12"]
    assert run(T, "finalist")["search_complete"] is True
    del T["runs"]["g2"]["X2"]["12"]
    assert run(T, "finalist")["search_complete"] is False
    T = happy()
    del T["runs"]["g1"]["D3"]["11"]
    assert run(T, "finalist")["search_complete"] is False
    T = happy()
    del T["runs"]["g1"]["P"]["12"]
    assert run(T, "finalist")["search_complete"] is False


def surface_T(by, bz, eps=1e-4, scale=1.0, gating=None, n_rand=3):
    """A rs-stage T whose 15 design points carry the exact quadratic surfaces by, bz (mean of the two phases), phases = f +- eps."""
    T = base(n_rand=n_rand)
    for s, r in T["roles"].items():
        if r["role"] in ("axial", "design"):
            u = np.array(r["u"]) * scale
            r["u"] = [float(x) for x in u]
            f, g = float(feat(u) @ by), float(feat(u) @ bz)
            delta(T, "g1", s, [f + eps, f - eps], [g + eps, g - eps], (11, 12))
    T["gating"] = gating or []
    T["stage"] = "rs"
    return T


BY_FULL = np.array([0.02, -0.013, 0.007, -0.011, 0.004, -0.002, 0.003, -0.005, 0.001])
BZ_FULL = np.array([-0.004, 0.009, -0.006, 0.002, -0.001, 0.003, -0.007, 0.004, 0.0015])
BY_S = np.array([0.04, 0.0, -0.002, -0.02, -0.004, 0, 0, 0, 0])   # y = 0.04 p - 0.002 r - 0.02 p^2 - 0.004 c^2
BZ_S = np.array([0, 0, -0.0031, 0, 0, 0, 0, 0, 0.0])               # z = -0.0031 r


def test_fit_recovers_exact_quadratic_coefficients():
    o = C.check(surface_T(BY_FULL, BZ_FULL))
    assert o["fit"]["downforce"]["coef"] == pytest.approx(list(BY_FULL), abs=1e-10)
    assert o["fit"]["drag"]["coef"] == pytest.approx(list(BZ_FULL), abs=1e-10)
    assert o["fit"]["rank"] == 9 and o["fit"]["cond"] == pytest.approx(3.6115, abs=1e-3) and o["rs_not_fit"] is False
    assert abs(o["fit"]["residual_sd"]["downforce"]) < 1e-9 and abs(o["fit"]["residual_sd"]["drag"]) < 1e-9 and o["rs_fit_poor"] is False
    assert o["data_loss"] == []


def test_fit_poor_flag_and_not_fit_flags():
    T = surface_T(BY_FULL, BZ_FULL)
    for k in "11", "12":
        T["runs"]["g1"]["D2"][k]["downforce"] += 0.02  # a misfit of 0.02 >> 3 x RMS SE_eff (1.5e-4)
    o = C.check(T)
    assert o["rs_fit_poor"] is True and o["fit"]["residual_sd"]["downforce"] > 3 * FL_DF and o["rs_not_fit"] is False
    T = surface_T(BY_FULL, BZ_FULL)  # drag alone is poor: either response suffices
    for k in "11", "12":
        T["runs"]["g1"]["D2"][k]["drag"] += 0.02
    o = C.check(T)
    assert o["rs_fit_poor"] is True and o["fit"]["residual_sd"]["drag"] > 3 * FL_DR
    assert C.check(surface_T(BY_FULL, BZ_FULL))["rs_fit_poor"] is False
    T = surface_T(BY_FULL, BZ_FULL)
    for i in range(1, 9):  # 6 axial + 1 design point left: rank < 9 -> everything null, rs_fit_poor null
        T["runs"]["g1"].pop(f"D{i}")
    o = C.check(T)
    assert (o["rs_not_fit"], o["fit"]["rank"], o["fit"]["cond"], o["fit"]["downforce"]["coef"], o["fit"]["drag"]["coef"], o["fit"]["residual_sd"], o["rs_fit_poor"], o["gated"], o["stop_after"],
            o["proposals"], o["u_star_1"], o["y_star_1"], o["pool_limited_pre"]) == (True, 7, None, None, None, {"downforce": None, "drag": None}, None, [], 0, [], None, None, False)
    assert all(v == {"u_star": None, "y_pred": None, "z_pred": None} for v in o["targets"].values())
    # rank 9 but cond > 20: RS_NOT_FIT exactly as for rank < 9 (coefficients, residual SDs, rs_fit_poor, optimum null); cond is reported
    o = C.check(surface_T(BY_FULL, BZ_FULL, scale=0.05))
    assert o["fit"]["rank"] == 9 and o["fit"]["cond"] > 20 and o["rs_not_fit"] is True and o["u_star_1"] is None and o["y_star_1"] is None and o["targets"]["1"]["u_star"] is None
    assert o["fit"]["downforce"]["coef"] is None and o["fit"]["drag"]["coef"] is None and o["fit"]["residual_sd"] == {"downforce": None, "drag": None} and o["rs_fit_poor"] is None
    assert o["gated"] == [] and o["proposals"] == [] and o["pool_limited_pre"] is False
    # n = 9 (rank 9, cond <= 20): fit OK, coefficients reported, the residual SD has no dof -> null, rs_fit_poor null (RS_FIT_UNDEFINED)
    T = surface_T(BY_FULL, BZ_FULL)
    for i in (0, 1, 2, 4, 7, 8):
        T["runs"]["g1"].pop(f"D{i}")  # design points D3, D5, D6 stay: cond 9.08
    o = C.check(T)
    assert o["fit"]["rank"] == 9 and o["fit"]["cond"] == pytest.approx(9.0823, abs=1e-3) and o["rs_not_fit"] is False
    assert o["fit"]["downforce"]["coef"] == pytest.approx(list(BY_FULL), abs=1e-10) and o["fit"]["residual_sd"] == {"downforce": None, "drag": None} and o["rs_fit_poor"] is None
    assert o["u_star_1"] is not None  # the optimum is still reported on a fitted surface


def test_g1_kernel_losses():
    T = surface_T(BY_FULL, BZ_FULL, eps=0.0)
    for s_ in T["runs"]["g1"]:
        T["runs"]["g1"][s_].pop("12", None)  # one G1 kernel (phase 12) lost: the fit proceeds on single-phase differences
    o = C.check(T)
    assert o["fit"]["downforce"]["coef"] == pytest.approx(list(BY_FULL), abs=1e-10) and o["rs_not_fit"] is False and o["data_loss"] == []
    f = run(copy.deepcopy(T) | {"stage": "finalist"}, "finalist")
    assert f["candidates"]["A0"]["P"] == 1 and f["candidates"]["A0"]["se_eff"] == {"downforce": FL_DF, "drag": FL_DR} and f["search_complete"] is False
    T = happy()
    T["runs"]["g1"] = {}  # both G1 kernels lost: nothing to fit
    o = run(T)
    assert (o["outcome"], o["cause"], o["search_complete"]) == ("SCREEN01_INCOMPLETE", ["DATA_G1"], False)


def test_a_point_is_dropped_only_if_both_phases_are_lost():
    T = surface_T(BY_FULL, BZ_FULL, eps=0.0)
    for k in "11", "12":
        T["runs"]["g1"]["D8"][k]["ok"] = False  # 14 points: still rank 9, cond <= 20
    T["runs"]["g1"]["D1"]["11"]["ok"] = False   # a single lost phase keeps the point (P = 1)
    o = C.check(T)
    assert o["fit"]["rank"] == 9 and o["rs_not_fit"] is False and o["fit"]["downforce"]["coef"] == pytest.approx(list(BY_FULL), abs=1e-10)
    assert o["data_loss"] == ["D1@g1@11", "D8@g1@11", "D8@g1@12"]


def test_constrained_optimum_on_the_81_grid():
    o = C.check(surface_T(BY_S, BZ_S))
    # tau = 1: z <= -1.5e-3 needs r >= 0.4839 -> grid 0.5; tau 1.5: r >= 0.7258 -> 0.75; tau 2: r >= 0.9677 -> 0.975; p = 1, c = 0 (camber grid is exact)
    for tau, r in (("1", 0.5), ("1.5", 0.75), ("2", 0.975)):
        t = o["targets"][tau]
        assert t["u_star"] == pytest.approx([1.0, 0.0, r], abs=1e-12)
        assert t["y_pred"] == pytest.approx(0.02 - 0.002 * r, abs=1e-12) and t["z_pred"] == pytest.approx(-0.0031 * r, abs=1e-12)
    assert o["u_star_1"] == pytest.approx([1.0, 0.0, 0.5], abs=1e-12) and o["y_star_1"] == pytest.approx(0.019, abs=1e-12) and o["pool_limited_pre"] is True
    # unreachable target: z = -0.0028 r -> tau = 2 needs r >= 1.07: no grid point, contributes nothing; pool_limited_pre false when y* < g_min J
    o = C.check(surface_T(BY_S, np.array([0, 0, -0.0028, 0, 0, 0, 0, 0, 0.0])))
    assert set(o["targets"]) == {"1", "1.5", "2"} and o["targets"]["2"] == {"u_star": None, "y_pred": None, "z_pred": None} and o["targets"]["1.5"]["u_star"][2] == pytest.approx(0.825, abs=1e-12)
    o = C.check(surface_T(BY_S * 0.1, BZ_S))
    assert o["y_star_1"] == pytest.approx(0.0019, abs=1e-12) and o["pool_limited_pre"] is False


def gating_for(T, adm, by=BY_S, bz=BZ_S):
    """Two passes: an all-inadmissible dummy gating reveals the regenerated order (up to the cap); then a real gating with adm(position, target_index), cut at the stop."""
    T = copy.deepcopy(T)
    T["gating"] = [{"name": f"d{i}", "u": [9, 9, 9], "target_index": 0, "y_pred": 0.0, "z_pred": 0.0, "admissible": False} for i in range(40)]
    first = C.check(T)["gated"]
    T["gating"] = [{"name": f"g{i}", "u": u, "target_index": ti, "y_pred": float(feat(u) @ by), "z_pred": float(feat(u) @ bz), "admissible": adm(i, ti)}
                   for i, (ti, u) in enumerate(first)]
    T["gating"] = T["gating"][:C.check(T)["stop_after"]]
    return T


def test_gating_regeneration_and_round_robin_stopping():
    T = surface_T(BY_S, BZ_S)
    T["roles"]["R0"]["u"] = [1.0, 0.0, 0.5]          # an already-evaluated name is excluded from the candidate lists (here u*_1)
    T = gating_for(T, lambda i, ti: True)
    o = C.check(T)
    assert "gating_mismatch" not in o and o["stop_after"] == 8                        # (0,1,2,0) then (1,2,0,1): counts (3,3,2) after round 2
    ts = [g[0] for g in o["gated"]]
    assert ts == [0, 1, 2, 0, 1, 2, 0, 1] and o["gated"][0][1] != [1.0, 0.0, 0.5]    # R0 excluded the first candidate of target 0
    assert o["gated"][1][1] == [1.0, 0.0, 0.75] and o["gated"][2][1] == [1.0, 0.0, 0.975]
    for ti, u in o["gated"]:
        tau, us = (1.0, 1.5, 2.0)[ti], np.array(o["targets"][("1", "1.5", "2")[ti]]["u_star"])
        y, z = float(feat(u) @ BY_S), float(feat(u) @ BZ_S)
        assert max(abs(np.array(u) - us)) <= 0.25 + 1e-6 and z <= -tau * 1.5e-3 + 1e-12 and np.all(np.array(u) >= [-1, -1.5, -1]) and np.all(np.array(u) <= 1)
        assert y >= 0.9 * (0.02 - 0.002 * us[2]) - 1e-9
    # within a target the cloud members follow in decreasing predicted downforce
    for t in (0, 1, 2):
        ys = [float(feat(u) @ BY_S) for ti, u in o["gated"] if ti == t][1:]
        assert ys == sorted(ys, reverse=True)
    # proposals: per target the admissible point with the largest y, then the rest by y, at most 4
    yv = [float(feat(u) @ BY_S) for _, u in o["gated"]]
    first = [max((i for i, (ti, _) in enumerate(o["gated"]) if ti == t), key=lambda i: yv[i]) for t in (0, 1, 2)]
    rest = sorted((i for i in range(8) if i not in first), key=lambda i: -yv[i])
    assert o["proposals"] == first + rest[:1]
    # the cloud of target 0 (seed 20261032, radius 0.25, clipped, filter, order) re-derived here
    from scipy.stats import qmc
    cu = np.clip(np.array([1.0, 0.0, 0.5]) + 0.25 * (2 * qmc.Sobol(d=3, scramble=True, seed=20261032).random(256) - 1), [-1, -1.5, -1], [1, 1, 1])
    yy = np.array([float(feat(u) @ BY_S) for u in cu])
    zz = np.array([float(feat(u) @ BZ_S) for u in cu])
    keep = (zz <= -1.5e-3) & (yy >= 0.9 * 0.019)
    best = cu[keep][np.argmax(yy[keep])]
    assert o["gated"][0][1] == [round(float(x), 6) for x in best]


def test_target_without_predicted_gain_contributes_nothing():
    # y = 0.01 p - 0.012 r - 0.004 c^2, z = -0.0031 r: y*(tau) = 0.01 - 0.012 r*: 0.004 (r 0.5), 0.001 (r 0.75), -0.0017 (r 0.975)
    by = np.array([0.01, 0, -0.012, 0, -0.004, 0, 0, 0, 0.0])
    T = surface_T(by, BZ_S)
    o = C.check(T)
    assert o["targets"]["2"]["u_star"] == pytest.approx([1.0, 0.0, 0.975], abs=1e-12) and o["targets"]["2"]["y_pred"] == pytest.approx(-0.0017, abs=1e-12)  # still reported
    assert o["targets"]["2"]["z_pred"] == pytest.approx(-0.0030225, abs=1e-12) and o["y_star_1"] == pytest.approx(0.004, abs=1e-12) and o["pool_limited_pre"] is False
    o = C.check(gating_for(T, lambda i, ti: True, by=by))
    assert [g[0] for g in o["gated"]] == [0, 1, 0, 1] and o["stop_after"] == 4  # target 2 is not queued, so it is not waited for
    assert o["gated"][0][1] == [1.0, 0.0, 0.5] and o["gated"][1][1] == [1.0, 0.0, 0.75]
    o = C.check(gating_for(T, lambda i, ti: False, by=by))
    assert 2 not in {g[0] for g in o["gated"]} and o["proposals"] == []
    # a target whose argmax has no predicted gain but a feasible grid point is distinct from one with no grid point (both empty lists)
    o = C.check(surface_T(by, np.array([0, 0, -0.0028, 0, 0, 0, 0, 0, 0.0])))
    assert o["targets"]["2"] == {"u_star": None, "y_pred": None, "z_pred": None} and o["targets"]["1.5"]["u_star"] is not None


def test_shared_point_is_gated_once_and_stop_rule_counts_queued_targets():
    # bowl: y = 0.05 (2 u.u* - |u|^2), z = -c y with u* = (0.3, 0, 0.3), y* = 0.009, z* = -0.00301: the same u* for all three targets (slack drag margin);
    # tau = 2 (z <= -0.003) keeps only y >= 0.9967 y*, so its cloud is empty: its list is {u*}, a duplicate of target 0's -> no queued point of its own
    us, ky = np.array([0.3, 0, 0.3]), 0.05
    by = np.zeros(9)
    by[:3], by[3:6] = 2 * ky * us, -ky
    bz = -(0.00301 / (ky * us @ us)) * by
    T = surface_T(by, bz)
    o = C.check(T)
    assert o["data_loss"] == [] and not o["rs_not_fit"]
    for k in ("1", "1.5", "2"):
        assert o["targets"][k]["u_star"] == pytest.approx([0.3, 0.0, 0.3], abs=1e-12) and o["targets"][k]["y_pred"] == pytest.approx(0.009, abs=1e-12)
        assert o["targets"][k]["z_pred"] == pytest.approx(-0.00301, abs=1e-12)
    full = C.check(gating_for(T, lambda i, ti: False, by=by, bz=bz))
    ts = [g[0] for g in full["gated"]]
    assert full["gated"][0] == [0, [0.3, 0.0, 0.3]] and ts[:3] == [0, 0, 1]      # u* once, owned by target 0; target 1's copy of u* is skipped
    assert 2 not in ts and len({tuple(g[1]) for g in full["gated"]}) == len(ts) == 36   # nothing gated twice; target 2 queued nothing; no admissible point -> the 36 cap
    o = C.check(gating_for(T, lambda i, ti: True, by=by, bz=bz))
    # queue u*(0), c1(0), c1(1), c2(0) | c2(1), c3(0), c3(1), c4(0): counts (3, 1) after round 1, (5, 3) after round 2: stop at 8. Waiting for target 2 (a candidate before the dedup) would never stop.
    assert [g[0] for g in o["gated"]] == [0, 0, 1, 0, 1, 0, 1, 0] and o["stop_after"] == 8
    yv = [float(feat(u) @ by) for _, u in o["gated"]]
    assert o["proposals"][0] == 0 and yv[0] == max(yv)                          # target 0's best is u* itself
    t1_best = max((i for i, (ti, _) in enumerate(o["gated"]) if ti == 1), key=lambda i: yv[i])
    assert o["proposals"][1] == t1_best
    rest = sorted((i for i in range(8) if i not in (0, t1_best)), key=lambda i: -yv[i])
    assert o["proposals"] == [0, t1_best] + rest[:2]


def test_stopping_cap_and_targets_without_candidates():
    T = surface_T(BY_S, BZ_S)
    o = C.check(gating_for(T, lambda i, ti: ti != 2))                              # target 2 never reaches 2 admissible points: runs to the 36 cap
    assert o["stop_after"] == 36 and "gating_mismatch" not in o
    assert all(o["gated"][i][0] in (0, 1, 2) for i in range(36)) and all(i < 36 for i in o["proposals"]) and len(o["proposals"]) == 4
    assert {o["gated"][i][0] for i in o["proposals"][:2]} == {0, 1} and 2 not in {o["gated"][i][0] for i in o["proposals"]}  # target 2 contributes nothing
    o = C.check(gating_for(T, lambda i, ti: False))
    assert o["stop_after"] == 36 and o["proposals"] == []
    T = surface_T(BY_S, np.array([0, 0, -0.0028, 0, 0, 0, 0, 0, 0.0]))            # target 2 has no grid point: only targets 0 and 1 are counted
    T2 = copy.deepcopy(T)
    T2["gating"] = [{"name": f"d{i}", "u": [9, 9, 9], "target_index": 0, "y_pred": 0.0, "z_pred": 0.0, "admissible": True} for i in range(40)]
    o = C.check(T2)
    assert o["stop_after"] == 4 and [g[0] for g in o["gated"]] == [0, 1, 0, 1] and "gating[4]" in o["gating_mismatch"]


def test_gating_mismatch_is_reported():
    T = gating_for(surface_T(BY_S, BZ_S), lambda i, ti: True)
    assert C.check(T).get("gating_mismatch") is None
    T["gating"][2]["u"] = [0.0, 0.0, 0.0]
    T["gating"][3]["target_index"] = 2
    T["gating"][1]["y_pred"] += 1e-3
    o = C.check(T)
    assert o["gating_mismatch"] == ["gating[1].y_pred", "gating[2].u", "gating[3].target_index"]
    other = {k: v for k, v in o.items() if k != "gating_mismatch"}
    assert C.compare(other, other, "rs") == [] and C.compare(o, other, "rs") == o["gating_mismatch"]
    T = gating_for(surface_T(BY_S, BZ_S), lambda i, ti: True)
    T["gating"] = T["gating"][:5]                                                    # shorter than the regenerated record
    assert C.check(T)["gating_mismatch"] == ["gating[5]"]
    T = gating_for(surface_T(BY_S, BZ_S), lambda i, ti: True)
    T["gating"].append(dict(T["gating"][0], name="extra"))                           # longer
    assert C.check(T)["gating_mismatch"] == ["gating[8]"]
    T["gating"][-1]["name"] = T["gating"][0]["name"]                                 # INTERFACE: every name at most once
    assert C.check(T)["gating_mismatch"] == ["gating[8]", "gating[8].name"]


def test_proposal_selection_from_gating():
    # target 0: g 0.0105 beats a 0.010 and d 0.009; target 1: e 0.013 (b 0.012); target 2: f 0.008 (c is inadmissible); first the three best, then the rest by y
    rows = [("a", 0, 0.010, True), ("b", 1, 0.012, True), ("c", 2, 0.011, False), ("d", 0, 0.009, True), ("e", 1, 0.013, True), ("f", 2, 0.008, True), ("g", 0, 0.0105, True)]
    T = base()
    T["gating"] = [{"name": n, "u": [0, 0, 0], "target_index": t, "y_pred": y, "z_pred": -0.002, "admissible": a} for n, t, y, a in rows]
    T["roles"].update({n: {"role": "proposal", "order": i, "u": [0.1 * i, 0, 0]} for i, n in enumerate("gefb")})
    o = run(T, "finalist")
    assert o["proposals_from_gating"] == ["g", "e", "f", "b"] and "gating_mismatch" not in o
    T["roles"].pop("b")
    assert run(T, "finalist")["gating_mismatch"] == ["roles.proposals"]
    T = base()  # a target without an admissible point contributes nothing; fewer than 4 proposals are fine
    T["gating"] = [{"name": "p", "u": [0, 0, 0], "target_index": 1, "y_pred": 0.01, "z_pred": 0, "admissible": True},
                   {"name": "q", "u": [0, 0, 0], "target_index": 0, "y_pred": 0.02, "z_pred": 0, "admissible": False}]
    T["roles"]["p"] = {"role": "proposal", "order": 0, "u": [0.5, 0, 0]}
    assert run(T, "finalist")["proposals_from_gating"] == ["p"]


def test_pool_limited():
    # y = 0.04 p - 0.04 p^2 peaks at p = 0.5 (0.010 >= x*, interior, not a design point); every candidate sits at y <= 0 or off the peak; drag z = -0.004 r (feasible)
    by, bz = np.array([0.04, 0, 0, -0.04, 0, 0, 0, 0, 0]), np.array([0, 0, -0.004, 0, 0, 0, 0, 0, 0.0])
    T = surface_T(by, bz)
    delta(T, "g1", "D8", [0.0, 0.0], [-0.001, -0.001], (11, 12))
    o = C.check(T)
    assert o["pool_limited_pre"] is True and o["y_star_1"] == pytest.approx(0.01, abs=1e-12)
    f = run(T, "finalist")
    assert f["pool_limited"] is True and f["search_complete"] is True
    delta(T, "g1", "A0", [0.0100, 0.0100], [-0.001] * 2, (11, 12))                   # a feasible candidate reaches >= x*: no longer pool limited
    assert run(T, "finalist")["pool_limited"] is False
    # without a predicted feasible gain >= x* (flatter surface) the label is false
    assert run(surface_T(by * 0.5, bz), "finalist")["pool_limited"] is False


def test_R3_paired_labels_use_the_common_phases():
    T = happy()  # f48k13 lost: Phi_48 = {14}; the finalist's flow_32 phases 13 / 14 / 15 / 16 are 0.0140 / 0.0099 / 0.0140 / 0.0140
    for s_ in T["runs"]["f48"]:
        T["runs"]["f48"][s_].pop("13")
    T["lost_kernels"] = ["f48k13"]
    delta(T, "f32", "A0", [0.0140, 0.0099, 0.0140, 0.0140], [-0.002] * 4, (13, 14, 15, 16))
    delta(T, "f48", "A0", [0.0098], [-0.002], (14,))
    o = run(T)
    r = o["R3"]
    # common = {14}: Delta_bar_32 = 0.0099 (not the 13-14 mean 0.01195 and not the 14-16 mean): ratio 0.99, |48 - 32| = 1e-4 <= 1.807e-3, drag signs equal
    assert (r["label"], r["R3_RATIO_IN_BAND"], r["R3_E2_EXCEEDED"], r["R3_DRAG_SAME_SIGN"], r["G48_ABOVE_MIN"]) == ("R3_CONFIRMED", True, False, True, True)
    assert r["G48_MARGIN"] == pytest.approx(0.0098 - X_STAR, abs=1e-12) and o["outcome"] == "SCREEN01_GAIN"
    assert o["confirmation"]["f48"]["P"] == 1 and o["confirmation"]["f48"]["delta_bar"]["downforce"] == pytest.approx(0.0098, abs=1e-12)
    delta(T, "f32", "A0", [0.0140, 0.0099, 0.0140, 0.0140], [0.002] * 4, (13, 14, 15, 16))  # f32 drag at the common phase +0.002 vs f48 -0.002: signs differ
    assert run(T)["R3"]["R3_DRAG_SAME_SIGN"] is False
    T = happy()  # f48k14 lost (Phi_48 = {13}) and the finalist's flow_32 phase 13 lost: no common phase -> the three labels null, the rest stays
    for s_ in T["runs"]["f48"]:
        T["runs"]["f48"][s_].pop("14")
    T["lost_kernels"] = ["f48k14"]
    del T["runs"]["f32"]["A0"]["13"]
    o = run(T)
    assert o["R3"] == {"label": "R3_CONFIRMED", "R3_RATIO_IN_BAND": None, "G48_ABOVE_MIN": True, "G48_MARGIN": pytest.approx(0.0100 - X_STAR, abs=1e-12),
                       "R3_E2_EXCEEDED": None, "R3_DRAG_SAME_SIGN": None} and o["outcome"] == "SCREEN01_GAIN"
    T["runs"]["f48"].pop("A0")  # no flow_48 phase at all for the finalist: R3 null, step 4
    o = run(T)
    assert o["R3"] is None and (o["outcome"], o["cause"]) == ("SCREEN01_INCOMPLETE", ["DATA_F"]) and o["confirmation"]["f48"] is None


def test_budget_is_any_run_row_of_the_kernel():
    T = happy()  # f32b's parent rows are missing but A0's rows exist: the kernel was run -> DATA_F (A0 unpaired at 15, 16: |Phi_s| = 2), not BUDGET
    for k in "15", "16":
        del T["runs"]["f32"]["P"][k]
    o = run(T)
    assert (o["outcome"], o["cause"]) == ("SCREEN01_INCOMPLETE", ["DATA_F"]) and o["data_loss"] == []
    for s_ in T["runs"]["f32"]:
        for k in "15", "16":
            T["runs"]["f32"][s_].pop(k, None)  # now no row at all: never run
    assert run(T)["cause"] == ["BUDGET"]
    T["runs"]["f32"]["R0"]["15"] = rn(1.0, 0.5)  # a single row of any state at the kernel's phases is enough
    assert run(T)["cause"] == ["DATA_F"]


def test_data_loss_is_uniform_and_unpaired_runs_are_not_listed():
    T = happy()
    T["runs"]["g1"]["NC"]["11"]["downforce"] = 1.3                   # the bound applies to NC, R, M, ref and the repeat like every other run
    T["runs"]["g1"]["R1"]["12"]["ok"] = False
    T["runs"]["g1"]["M"]["11"]["drag"] = PAR[1] + 0.13
    T["runs"]["g1"]["REF"]["12"]["downforce"] = float("nan")
    setd(T, "g1", "REP", 11, 0.0, 0.2)
    assert run(T, "rs")["data_loss"] == ["M@g1@11", "NC@g1@11", "R1@g1@12", "REF@g1@12", "REP@g1@11"]
    T = happy()  # the parent is lost at phase 11: it is listed, the other states' phase-11 runs are unpaired (even an invalid one): not listed
    T["runs"]["g1"]["P"]["11"]["downforce"] = None
    T["runs"]["g1"]["A1"]["11"]["ok"] = False
    T["runs"]["g1"]["A2"]["12"]["ok"] = False                          # paired phase: listed
    o = run(T, "finalist")
    assert o["data_loss"] == ["A2@g1@12", "P@g1@11"] and o["candidates"]["A1"]["P"] == 1 and o["candidates"]["A0"]["P"] == 1
    T = happy()  # no parent row at all at phase 12: every phase-12 run is unpaired, none listed
    del T["runs"]["g1"]["P"]["12"]
    T["runs"]["g1"]["A3"]["12"]["downforce"] = None
    assert run(T, "finalist")["data_loss"] == []


# ---- compare ----------------------------------------------------------------------------------------------------------------------------------------
def tiny():
    return {"data_loss": ["a@g1@11"], "fit": {"downforce": {"coef": [1.0, 2.0]}, "drag": {"coef": [0.5]}, "rank": 9, "cond": 3.6, "residual_sd": {"downforce": 1e-4, "drag": None}},
            "rs_fit_poor": False, "rs_not_fit": False, "u_star_1": [0.1, 0.2, 0.3], "y_star_1": 0.01, "pool_limited_pre": True,
            "targets": {"1.0": {"u_star": [1, 0, 0], "y_pred": 0.1, "z_pred": -0.1}, "1.5": {"u_star": None, "y_pred": None, "z_pred": None}},
            "gated": [[0, [1.0, 0.0, 0.5]]], "stop_after": 1, "proposals": [0]}


def test_compare_tolerance_and_types():
    a = tiny()
    assert C.compare(a, copy.deepcopy(a), "rs") == []
    b = copy.deepcopy(a)
    b["y_star_1"] = 0.01 + 5e-10           # within 1e-9 * max(1, |x|)
    b["fit"]["downforce"]["coef"] = [1.0 + 5e-10, 2.0 - 5e-10]
    b["extra_key"] = 1                     # only the stage's keys are compared
    assert C.compare(a, b, "rs") == []
    b["y_star_1"] = 0.01 + 2e-9
    b["fit"]["downforce"]["coef"][1] = 2.0 + 3e-9
    assert C.compare(a, b, "rs") == ["fit.downforce.coef[1]", "y_star_1"]
    b = copy.deepcopy(a)
    b["rank"] = 9
    b["fit"]["rank"] = 9.0                 # int vs float is a number comparison
    b["fit"]["cond"] = 3.6 * (1 + 1e-6)
    b["rs_fit_poor"] = 0                   # bool vs int: exact types
    b["fit"]["residual_sd"]["drag"] = 0.0  # None vs 0.0
    b["gated"] = [[0, [1.0, 0.0, 0.5]], [1, [0, 0, 0]]]
    b["proposals"] = []
    b["data_loss"] = ["a@g1@12"]
    assert sorted(C.compare(a, b, "rs")) == sorted(["data_loss[0]", "fit.cond", "fit.residual_sd.drag", "rs_fit_poor", "gated", "proposals"])


def test_compare_missing_keys_and_tau_spelling():
    a = tiny()
    b = copy.deepcopy(a)
    del b["rs_not_fit"]
    del b["fit"]["drag"]["coef"]
    b["targets"] = {"1": b["targets"]["1.0"], "1.5": b["targets"]["1.5"], "2": {"u_star": None, "y_pred": None, "z_pred": None}}
    assert sorted(C.compare(a, b, "rs")) == ["fit.drag.coef", "rs_not_fit", "targets.2.0"]
    assert sorted(C.compare(b, a, "rs")) == ["fit.drag.coef", "rs_not_fit", "targets.2.0"]
    b = {k: v for k, v in a.items() if k != "u_star_1"}
    assert C.compare(a, b, "rs") == ["u_star_1"]
    n = {"data_loss": [], "x": np.float64(1.0), "rs_fit_poor": np.bool_(False)}
    m = {"data_loss": [], "rs_fit_poor": False}
    assert C.compare(n, m, "rs") == []  # numpy bool normalised; keys missing on both sides agree


def test_compare_stage_keys_main():
    o = run(happy())
    p = copy.deepcopy(o)
    p["outcome"] = "SCREEN01_NO_GAIN"
    p["controls"]["K_MISMATCH"] = True
    p["candidates"]["A0"]["P"] = 3
    p["selection_bias"]["g_XV_exp"]["central"] += 1e-6
    assert sorted(C.compare(o, p, "main")) == ["candidates.A0.P", "controls.K_MISMATCH", "outcome", "selection_bias.g_XV_exp.central"]
    q = {k: v for k, v in o.items() if k != "NC"}
    assert C.compare(o, q, "main") == ["NC"]
    assert C.compare(o, q, "finalist") == []   # NC is not a finalist-stage key
