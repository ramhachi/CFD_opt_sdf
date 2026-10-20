"""UNC-01 (#61): builder (phases, campaigns, state identities) and the frozen analysis on planted data: every label, interval and INCOMPLETE path."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import analyze_unc01 as A  # noqa: E402
import unc01_build as B  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402
from fd08_v2_campaign_io import FORCE_COLUMNS  # noqa: E402

REC = json.loads((B.OUT / "states.json").read_text())
PAIRS = [("pitch", "camber"), ("camber", "pitch"), ("reflex", "twist"), ("twist", "pitch"), ("sweep", "reflex")]


# ---- builder ------------------------------------------------------------------------------------------------------------------------------------------
def test_phases_disjoint_from_native_and_z_fixed():
    assert B.phase_fraction(0) == (0.0, 0.0)
    for g, ks in B.U2_PHASES.items():
        assert 0 not in ks and tuple(ks) == A.U2_PHASES[g]
        fr = [B.phase_fraction(k) for k in ks]
        assert all(0 < x < 1 and 0 < y < 1 for x, y in fr) and len(set(fr)) == len(fr)
        assert {B.origin(g, k).split(",")[2] for k in ks} == {"-0.6"}
    assert B.origin(None, half=True) == "-0.9875,-0.7875,-0.6"            # the GRID-02 / JOB-02 bridge placement
    assert B.origin("flow_32", 1) == "-0.9811280583,-0.7857539927,-0.6"


def test_constants_agree_between_builder_and_analyzer():
    assert A.WIDE == B.WIDE and A.FAMILY == B.FAMILY and A.L_MID == B.L_MID
    est = {k: len(v["runs"]) * {"flow_24": 180, "flow_32": 415, "flow_48": 2340}[v["case"]["case_id"]] for k, v in B.kernels_u2("pitch", "camber").items()}
    assert est == A.EST_S


def test_l_mid_rule_from_prescreen():
    per = json.loads(B.PRESCREEN.read_text())["basis"]["per_mode"]
    for m, a in B.WIDE.items():
        both = [float(x) for x, sg in per[m]["gate_clean_signs"].items() if sorted(sg) == [-1, 1] and float(x) < a]
        mid = min(both, key=lambda x: (abs(x - a / 2), x)) if both else None
        assert B.L_MID.get(m) == mid


def test_u01_campaign_rederives_and_validates():
    c = B.campaign("unc01_u01", B.kernels_u01(), REC)
    SC.validate_campaign(c)
    assert json.dumps(c, indent=1, sort_keys=True) + "\n" == (B.HARNESS / "unc01_u01_campaign.json").read_text()
    assert [r["name"] for r in c["kernels"]["f48"]["runs"]] == ["v18__parent__k0"]
    assert c["job_env_common"]["W4_CANONICAL_STATE_LABEL"] == "v18" and c["job_env_common"]["W4_SOURCE_SURFACE_SHA256"] == REC["parent"]["source_sha256"]


@pytest.mark.parametrize("L,L2", PAIRS)
def test_u2_campaign_pairs_inside_one_kernel(L, L2):
    c = B.campaign("unc01_u2", B.kernels_u2(L, L2), REC)
    SC.validate_campaign(c)
    seen = {}
    for k, kern in c["kernels"].items():
        assert kern["runs"][0]["state"] == "v18__parent"
        for r in kern["runs"]:
            key = (kern["case"]["case_id"], r["state"], r["name"].rsplit("__", 1)[1])
            if k != "f24r":
                assert key not in seen
                seen[key] = k
    for (g, s, tag), k in seen.items():
        assert seen[(g, "v18__parent", tag)] == k
    st = B.u2_states(L, L2)
    assert len(set(st["flow_32"])) == 8 and "v18__roll_p25" in st["flow_32"]
    assert sum(g == "flow_32" for g, _, _ in seen) == 48 and sum(g == "flow_48" for g, _, _ in seen) == 8 and sum(g == "flow_24" for g, _, _ in seen) == 18
    with pytest.raises(SystemExit):
        B.u2_states("camber", "reflex")                                        # same family


def test_states_record_matches_prescreen_and_roll_is_a_lattice_roll():
    import numpy as np
    import step01_states as S
    pre = {(r["mode"], r["amplitude"]): r for r in json.loads(B.PRESCREEN.read_text())["states"]}
    for n, r in REC["states"].items():
        ref = pre.get((r["mode"], r["amplitude"]))
        assert (ref is None) == (n == "v18__roll_p25")
        if ref is not None:
            assert r["phi_fortran_order_sha256"] == ref["phi_fortran_sha256"]
        if r["direction"]:
            assert B.sha(ROOT / B.dir_rel(n)) == r["direction_sha256_fortran_raw"]
    par = S.read_f4(ROOT / B.PARENT_RAW)
    r = REC["states"]["v18__roll_p25"]
    roll = S.perturb(par, S.read_f4(ROOT / B.dir_rel("v18__roll_p25")), r["step_mm"], 1).astype(np.float64)
    import mode01_modes as M
    act = M.active_mask(B.load_parent()[0])
    both = act[1:] & act[:-1]                                                     # inactive nodes keep the parent bytes by construction
    assert np.abs(roll[1:] - par[:-1].astype(np.float64))[both].max() < 1e-8


# ---- planted data -----------------------------------------------------------------------------------------------------------------------------------
SEL = {"L": "pitch", "L2": "camber", "L_mid": "v18__pitch_p1.3", "scores_n": {}}
EFFECT = {"v18__D0_p3": 3e-3, "v18__pitch_p3.1": 2e-2, "v18__pitch_m3.1": -1.8e-2, "v18__pitch_p1.3": 8e-3, "v18__camber_p19.7": 6e-3,
          "v18__s050_m5": 2e-5, "v18__roll_p25": 1e-5}
BASE = {"flow_24": 0.33, "flow_32": 0.36, "flow_48": 0.365}


def planted(rel=0.02, g24=1.0, g48=1.0, extra=None):
    """F = base + parent wobble(k) + effect (1 + rel cos) [+ extra(s, k)]; s050 carries a small additive wobble so it is unresolved."""
    def value(g, s, k, r, tag="k"):
        base = BASE[g] * (1 if r == "downforce" else 0.97) + 5e-3 * math.sin(2.3 * k + {"flow_24": 0.1, "flow_32": 0.7, "flow_48": 1.3}[g])
        eff = EFFECT.get(s, 0.0) * {"flow_24": g24, "flow_48": g48}.get(g, 1.0)
        v = base + eff * (1 + rel * math.cos(1.7 * k + len(s))) + (1e-4 * math.sin(2.0 * k + 0.5) if s == "v18__s050_m5" else 0.0)
        return v + (extra(g, s, k, r) if extra else 0.0)
    return value


def table(c, cpath, kernels, value):
    sf = {}
    for k in kernels:
        kern = c["kernels"][k]
        sf[k] = {r["name"]: {f"{q}_n": value(kern["case"]["case_id"], r["state"], 0 if r["name"].endswith("half") else int(r["name"].rsplit("__k", 1)[1]), q,
                                            "half" if r["name"].endswith("half") else "k") for q in A.RESP} for r in kern["runs"]}
    return {"kind": SC.TABLE_KIND, "harness_version": SC.HARNESS_VERSION, "smoke": False, "integrity": {"pass": True, "failures": []},
            "campaign_id": c["campaign_id"], "campaign_sha256": SC.sha256_path(cpath), "state_forces_n": sf}


ALL = ("f48a", "f48b", "f32a", "f32b", "f32c", "f24")


def setup(tmp_path, kernels=ALL, value=None, push="f24", sel=SEL):
    tmp_path.mkdir(parents=True, exist_ok=True)
    c = B.campaign("unc01_u2", B.kernels_u2(sel["L"], sel["L2"]), REC)
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(c))
    tabs = []
    for k in kernels:
        p = tmp_path / f"t_{k}.json"
        p.write_text(json.dumps(table(c, cpath, [k], value or planted())))
        tabs.append(p)
    k0 = {s: {q: 0.0 for q in A.RESP} for s in REC["states"] if s != "v18__parent"}
    spath = tmp_path / "sel.json"
    spath.write_text(json.dumps({"kind": "unc01_u1_selection", "verdict": "SELECTED", "selection": sel, "k0_differences_flow32": k0}))
    bpath = tmp_path / "budget.json"
    bpath.write_text(json.dumps({"kind": "unc01_budget_decision", "push": push}))
    return cpath, spath, bpath, tabs


def run(tmp_path, **kw):
    cpath, spath, bpath, tabs = setup(tmp_path, **kw)
    return A.u2(cpath, spath, bpath, tabs, None, None, None)


def test_stats_by_hand():
    s = A.stats([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert s["delta_bar_n"] == 3.5 and abs(s["sigma_d_n"] - math.sqrt(3.5)) < 1e-12 and abs(s["se_n"] - math.sqrt(3.5 / 6)) < 1e-12
    assert abs(s["sigma_d_90"][0] / s["sigma_d_n"] - 0.672) < 1e-3 and abs(s["sigma_d_90"][1] / s["sigma_d_n"] - 2.089) < 1e-3 and abs(s["t"] - 2.015) < 1e-3
    assert s["resolved"] == (3.5 > 2.015 * math.sqrt(3.5 / 6)) and s["above_3se"] == (3.5 > 3 * math.sqrt(3.5 / 6))
    z = A.stats([1e-6, -1e-6, 2e-6, -2e-6, 0.0, 0.0])
    assert not z["resolved"] and z["r_80"][1] == math.inf and math.isfinite(z["r_80"][0])
    four = A.stats([1.0, 1.1, 0.9, 1.05])
    assert abs(four["sigma_d_90"][1] / four["sigma_d_n"] - 2.920) < 1e-3 and abs(four["t"] - 2.353) < 1e-3


def test_ratio_label_branches():
    mk = lambda m, se, P=6: {"delta_bar_n": m, "se_n": se, "P": P, "resolved": abs(m) > A.tq(0.95, P - 1) * se}  # noqa: E731
    assert A.ratio_label(mk(1.0, 0.01), mk(1.0, 0.01, 4))["label"] == "EQUIVALENT"
    assert A.ratio_label(mk(2.0, 0.01), mk(1.0, 0.01, 4))["label"] == "DIFFERENT"
    assert A.ratio_label(mk(1.0, 0.2), mk(1.0, 0.2, 4))["label"] == "INDETERMINATE"
    assert A.ratio_label(mk(1.0, 0.01), mk(-1.0, 0.01, 4))["label"] == "DIFFERENT"
    assert A.ratio_label(mk(1.0, 0.01), mk(0.01, 0.01, 4))["label"] == "UNRESOLVED"


def test_u2_planted_complete(tmp_path):
    res = run(tmp_path)
    assert res["outcome"] == {"label": "M2_PARTIAL", "missing": ["U3"]}             # no U3 output given here
    g32 = res["grids"]["flow_32"]
    assert g32["P"] == 6 and not g32["P_reduced"] and set(g32["differences"]) == set(B.u2_states("pitch", "camber")["flow_32"][1:])
    d0 = g32["differences"]["v18__D0_p3"]["downforce"]
    assert abs(d0["delta_bar_n"] - 3e-3) < 1e-4 and d0["resolved"] and d0["sigma_d_over_sqrt2_sigma_F"] < 0.1
    assert res["Q2"]["downforce"]["label"] == "S050_UNRESOLVED" and "confounds" in res["Q2"]["downforce"]
    assert res["Q3"]["downforce"]["flow32_vs_flow48_Lplus"]["label"] == "EQUIVALENT"
    assert res["Q3"]["downforce"]["flow24_vs_flow32"]["label"] == "FLOW24_EQUIVALENT"
    e2 = res["Q4_E2"]["downforce"]
    assert e2["status"] == "COMPLETE" and e2["common_phases"]["phases"] == [1, 2, 3, 4] and e2["common_phases"]["S_d"] < 1e-3 and e2["J_scale_n"] == 3.6e-3
    assert e2["common_phases"]["implied_min_gain_paired"] == 2 * e2["common_phases"]["S_d"]
    m = res["M3a_tables"]["downforce"]
    assert set(m["planning"]) == {"v18__D0_p3", "v18__pitch_p3.1", "v18__pitch_m3.1", "v18__pitch_p1.3", "v18__camber_p19.7"}
    assert m["roll_null_control"]["delta_bar_n"] > 0 and m["sigma_d_vs_delta_fit"]["n"] == 6
    assert res["u3"]["status"] == "INCOMPLETE" and res["Q2"]["OF_downforce"]["label"] == "INCOMPLETE"
    json.dumps(A.clean(res), allow_nan=False)


def test_q2_label_branches(tmp_path):
    def s050_big(g, s, k, r):           # s050 large and clean, D0 small and noisy -> S050_LOWER_R
        return (5e-3 if s == "v18__s050_m5" else 0) + ((-2e-3 + 3e-4 * math.sin(2.9 * k)) if s == "v18__D0_p3" else 0)
    assert run(tmp_path / "a", value=planted(extra=s050_big))["Q2"]["downforce"]["label"] == "S050_LOWER_R"
    def s050_clean(g, s, k, r):         # both resolved, D0 cleaner -> D0_LOWER_R
        return (5e-3 + 1.5e-3 * math.sin(2.9 * k) if s == "v18__s050_m5" else 0)
    assert run(tmp_path / "b", value=planted(extra=s050_clean))["Q2"]["downforce"]["label"] == "D0_LOWER_R"
    def d0_zero(g, s, k, r):
        return (-3e-3 * (1 + 0.02 * math.cos(1.7 * k + len(s))) + 1e-4 * math.sin(2.9 * k) if s == "v18__D0_p3" else 0)
    assert run(tmp_path / "c", value=planted(extra=d0_zero))["Q2"]["downforce"]["label"] == "D0_UNRESOLVED"
    def similar(g, s, k, r):
        return (3e-3 - 1e-4 * math.sin(2.0 * k + 0.5) + 6e-5 * math.cos(1.7 * k + 13) if s == "v18__s050_m5" else 0)   # same noise level as D0
    assert run(tmp_path / "d", value=planted(extra=similar))["Q2"]["downforce"]["label"] == "NOT_SEPARATED"


def test_q3_flow24_outlier_and_flow48_different(tmp_path):
    res = run(tmp_path, value=planted(g24=0.3, g48=1.6))
    assert res["Q3"]["downforce"]["flow24_vs_flow32"]["label"] == "FLOW24_DIFFERENT"
    assert res["Q3"]["downforce"]["flow32_vs_flow48_Lplus"]["label"] == "DIFFERENT"
    res = run(tmp_path / "n", value=planted(rel=0.4))
    assert res["Q3"]["downforce"]["flow32_vs_flow48_Lplus"]["label"] in ("INDETERMINATE", "UNRESOLVED")


def test_incomplete_partial_and_reduced(tmp_path):
    res = run(tmp_path / "a", kernels=("f48a", "f32a", "f32b", "f32c", "f24"))
    assert res["outcome"]["label"] == "M2_PARTIAL" and "flow_48" in res["outcome"]["missing"]
    assert res["Q3"]["downforce"]["flow32_vs_flow48_Lplus"]["label"] == "INCOMPLETE" and res["Q4_E2"]["downforce"]["status"] == "INCOMPLETE"
    res = run(tmp_path / "b", kernels=("f48a", "f48b", "f32a", "f32c", "f24"))            # flow_32 P = 4 (reduced)
    g32 = res["grids"]["flow_32"]
    assert g32["complete"] and g32["P"] == 4 and g32["P_reduced"] and g32["phases_used"] == [1, 2, 5, 6]
    assert res["outcome"]["label"] == "M2_PARTIAL" and res["outcome"]["missing"][0] == "flow_32 full phase set"
    assert res["Q4_E2"]["downforce"]["common_phases"]["phases"] == [1, 2]
    res = run(tmp_path / "c", kernels=("f48a", "f48b", "f32a", "f24"))                    # flow_32 P = 2
    assert res["outcome"]["label"] == "M2_INCOMPLETE" and res["Q2"]["downforce"]["label"] == "INCOMPLETE"
    res = run(tmp_path / "d", kernels=("f48a", "f48b", "f32a", "f32b", "f32c", "f24r"), push="f24r")
    assert res["grids"]["flow_24"]["variant"] == "f24r" and set(res["Q3"]["downforce"]["flow24_vs_flow32"]["detail"]) == {"v18__pitch_p3.1"}
    assert res["outcome"]["label"] == "M2_PARTIAL" and res["outcome"]["missing"] == ["U3"]
    res = run(tmp_path / "e", kernels=("f48a", "f48b", "f32a", "f32b", "f32c"), push=None)  # flow_24 not pushed by the budget rule
    assert res["Q3"]["downforce"]["flow24_vs_flow32"]["label"] == "NOT_MEASURED" and "flow_24" not in res["outcome"]["missing"]
    res = run(tmp_path / "f", kernels=("f48a", "f48b", "f32a", "f32b", "f32c"), push="f24")  # pushed but no verified table
    assert res["Q3"]["downforce"]["flow24_vs_flow32"]["label"] == "INCOMPLETE" and "flow_24" in res["outcome"]["missing"]
    with pytest.raises(ValueError, match="did not push"):
        run(tmp_path / "g", kernels=ALL + ("f24r",), push="f24")


def test_tables_and_selection_must_match(tmp_path):
    cpath, spath, bpath, tabs = setup(tmp_path, kernels=("f32a",))
    t = json.loads(tabs[0].read_text())
    t["campaign_sha256"] = "0" * 64
    tabs[0].write_text(json.dumps(t))
    with pytest.raises(ValueError, match="another campaign"):
        A.u2(cpath, spath, bpath, tabs, None, None, None)
    t["campaign_sha256"], t["smoke"] = SC.sha256_path(cpath), True
    tabs[0].write_text(json.dumps(t))
    with pytest.raises(ValueError):
        A.u2(cpath, spath, bpath, tabs, None, None, None)
    sel = json.loads(spath.read_text())
    sel["selection"] = {**SEL, "L2": "twist"}
    spath.write_text(json.dumps(sel))
    with pytest.raises(ValueError, match="does not match the U1 selection"):
        A.u2(cpath, spath, bpath, tabs[:0], None, None, None)


def test_u2_cli_written_once(tmp_path):
    cpath, spath, bpath, tabs = setup(tmp_path)
    out = tmp_path / "analysis.json"
    out.write_text("{}")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/analyze_unc01.py"), "u2", "--campaign", str(cpath), "--u1", str(spath), "--budget", str(bpath),
                        "--tables", *map(str, tabs), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode != 0 and "written once" in r.stderr


def test_budget_decision(tmp_path):
    logs = []
    for i, w in enumerate((9800, 9900, 7000, 7100)):
        p = tmp_path / f"l{i}.log"
        p.write_text(json.dumps([{"stream_name": "stdout", "time": 1.0, "data": ""}, {"stream_name": "stdout", "time": float(w), "data": ""}]))
        logs.append(p)
    d = A.budget(logs, ["f32c"])
    assert d["push"] == "f24" and d["T_f24_s"] == 33800 + 6640 + 260 + 3240 + 260
    big = tmp_path / "big.log"
    big.write_text(json.dumps([{"time": 43500.0}]))
    assert A.budget([big], [])["push"] == "f24r"
    big.write_text(json.dumps([{"time": 46000.0}]))
    assert A.budget([big], [])["push"] is None


# ---- U3 -----------------------------------------------------------------------------------------------------------------------------------------------
def u3_files(tmp_path, states, fail=(), wl=0.8):
    import unc01_u3_prepare as U
    order = U.case_order(states)
    kpath = tmp_path / "crit.json"
    kpath.write_text(json.dumps({"states": {s: {} for s in states}, "case_order": order, "not_run_export_gate": []}))
    cases = []
    for spec in order:
        j = int(spec["id"].rsplit("_", 1)[1][:-1])
        val = 0.25 + 1e-4 * math.sin(7 * j) + wl * EFFECT.get(spec["state"], 0) * (1 + 0.03 * math.cos(j)) + (2e-4 * math.sin(5.1 * j) if spec["state"] == "v18__s050_m5" else 0)
        cases.append({"id": spec["id"], "status": "snappyHexMesh_FAILED" if spec["id"] in fail else "COMPLETED",
                      "forces": {"downforce_n": {"window_mean": val}, "drag_n": {"window_mean": 0.37 + val / 10}}})
    rpath = tmp_path / "res.json"
    rpath.write_text(json.dumps({"criteria_sha256": SC.sha256_path(kpath), "cases": cases}))
    return rpath, kpath


def test_u3_pairs_retention_and_labels(tmp_path):
    import unc01_u3_prepare as U
    states = B.u2_states("pitch", "camber")["flow_32"]
    order = U.case_order(states)
    assert len(order) == 8 * 32 and order[0]["id"] == "u3_v18__parent_33p" and order[1]["id"] == "u3_v18__D0_p3_33p" and order[8]["id"] == "u3_v18__parent_33m"
    cpath, spath, bpath, tabs = setup(tmp_path)
    rpath, kpath = u3_files(tmp_path, states, fail=("u3_v18__s050_m5_40m",))
    res = A.u2(cpath, spath, bpath, tabs, None, rpath, kpath)
    u3 = res["u3"]
    assert u3["status"] == "COMPLETE" and 40 not in u3["pairs_used"] and len(u3["pairs_used"]) == 15        # the mirror is dropped too
    d0 = u3["differences"]["v18__D0_p3"]["downforce"]
    assert d0["P"] == 15 and abs(d0["retention_vs_flow32"] - 0.8) < 0.02 and d0["retention_90"][0] < 0.8 < d0["retention_90"][1] and d0["sign_agrees_with_flow32"]
    assert res["Q2"]["OF_downforce"]["label"] == "S050_UNRESOLVED" and res["outcome"]["label"] == "M2_COMPLETE"
    many = [f"u3_v18__parent_{i}p" for i in range(33, 38)]
    rpath, kpath = u3_files(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path, states, fail=many)
    assert A.u2(cpath, spath, bpath, tabs, None, rpath, kpath)["u3"]["status"] == "INCOMPLETE"             # 11 whole pairs < 12
    no_s050 = [s for s in states if s != "v18__s050_m5"]
    (tmp_path / "y").mkdir()
    rpath, kpath = u3_files(tmp_path / "y", no_s050)
    assert A.u2(cpath, spath, bpath, tabs, None, rpath, kpath)["Q2"]["OF_downforce"]["label"] == "NOT_MEASURED"


def test_strip_smoke(tmp_path):
    import unc01_u3_prepare as U
    src = tmp_path / "result.json"
    src.write_text(json.dumps({"cases": [{"id": "a", "status": "COMPLETED", "forces": {"drag_n": {}}, "mesh": {"cells": 1}}]}))
    out = U.strip_smoke(src, tmp_path / "stripped.json")
    assert "forces" not in json.dumps(out["cases"]) and out["cases"][0]["mesh"] == {"cells": 1} and out["forces_removed_from"]["sha256"] == B.sha(src)


# ---- U0 / U1 --------------------------------------------------------------------------------------------------------------------------------------------
def write_run(root, c, kernel, name, downforce_solver, slope=0.0):
    case = c["kernels"][kernel]["case"]["case_id"]
    d = root / SC.out_dir_name(c, kernel) / "states" / name
    d.mkdir(parents=True)
    (d / SC.summary_name(case)).write_text(json.dumps({"finite_u": True, "finite_p": True, "finite_forces": True}))
    lines = [",".join(FORCE_COLUMNS)]
    for i in range(1, 260):
        t = i * 0.5
        dn = downforce_solver * (1 + slope * (t - 100))
        row = {"step": i, "t_u_l": t, "fx_solver": 2.0, "fy_solver": 0.0, "fz_solver": -dn, "drag_solver": 2.0, "downforce_solver": dn, "pressure_fx_solver": 1.5,
               "pressure_fy_solver": 0.0, "pressure_fz_solver": -dn, "viscous_fx_solver": 0.5, "viscous_fy_solver": 0.0, "viscous_fz_solver": 0.0}
        lines.append(",".join(repr(float(row[k])) for k in FORCE_COLUMNS))
    (d / SC.forces_name(case)).write_text("\n".join(lines) + "\n")


def u01(tmp_path, score, drop=None):
    c = B.campaign("unc01_u01", B.kernels_u01(), REC)
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps(c))

    def value(g, s, k, r, tag="k"):
        v = BASE[g] if r == "downforce" else 0.35
        for m, sc in score.items():
            if s.startswith(f"v18__{m}_"):
                v += sc if s.rsplit("_", 1)[1].startswith("p") else -sc
        return v + (2e-3 if tag == "half" else 0) + (1e-3 if s == "v18__D0_p3" else 0)
    t = table(c, cpath, ["f24", "f32", "f48"], value)
    if drop:
        del t["state_forces_n"]["f32"][drop]
    tpath = tmp_path / "t.json"
    tpath.write_text(json.dumps(t))
    return c, cpath, tpath


def test_u0_gate_and_u1_selection(tmp_path):
    c, cpath, tpath = u01(tmp_path, {"pitch": 1e-2, "camber": 3e-2, "reflex": 3e-2, "twist": 1e-3, "sweep": 1e-3})
    for k, g in (("f24", "flow_24"), ("f32", "flow_32"), ("f48", "flow_48")):
        write_run(tmp_path, c, k, "v18__parent__k0", BASE[g] / SC.force_scale_n(c["kernels"][k]["case"]))
    out = A.u1(cpath, tpath, tmp_path)
    assert out["u0"]["verdict"] == "U0_PASS" and out["verdict"] == "SELECTED"
    sel = out["selection"]
    assert sel["L"] == "camber" and sel["L2"] == "pitch" and sel["L_mid"] == "v18__camber_p11.3"   # camber = reflex tie -> WIDE order; L2 from another family
    assert abs(out["bridge"]["flow_32"]["downforce"]["parent_half_minus_k0_n"] - 2e-3) < 1e-12 and set(out["k0_differences_flow32"]) >= {"v18__D0_p3", "v18__sweep_m11.3"}
    (tmp_path / "t2").mkdir()
    c2, cpath2, tpath2 = u01(tmp_path / "t2", {"pitch": 1e-3, "camber": 1e-3, "reflex": 1e-3, "twist": 5e-2, "sweep": 1e-2})
    sel = A.u1(cpath2, tpath2, tmp_path)["selection"]                            # same campaign bytes: kernel outputs reusable
    assert sel["L"] == "twist" and sel["L2"] == "pitch" and sel["L_mid"] == "v18__pitch_m3.1"         # twist has no mid point -> L2 at -A*
    (tmp_path / "bad").mkdir()
    for k in ("f24", "f32", "f48"):
        write_run(tmp_path / "bad", c, k, "v18__parent__k0", 0.3 / SC.force_scale_n(c["kernels"][k]["case"]), slope=2e-3)
    g = A.u0_gate(cpath, tpath, tmp_path / "bad")
    assert g["verdict"] == "U0_FAIL" and not g["grids"]["flow_32"]["tests"]["drift_downforce"] and g["rows_read"] == "v18__parent__k0 only"
    assert A.u1(cpath, tpath, tmp_path / "bad")["verdict"] == "U0_FAIL"


def test_smoke_table_is_a_u0_input_only(tmp_path):
    c, cpath, tpath = u01(tmp_path, {"pitch": 1e-2}, drop=None)
    t = json.loads(tpath.read_text())
    t["smoke"] = True                                                             # a smoke table is never a U1 input
    tpath.write_text(json.dumps(t))
    for k, g in (("f24", "flow_24"), ("f32", "flow_32"), ("f48", "flow_48")):
        write_run(tmp_path, c, k, "v18__parent__k0", BASE[g] / SC.force_scale_n(c["kernels"][k]["case"]))
    with pytest.raises(ValueError):
        A.u1(cpath, tpath, tmp_path)
    g = A.u0_gate(cpath, tpath, tmp_path, smoke=True)                            # but it is the U0 smoke input (flow_24 only)
    assert g["verdict"] == "U0_PASS" and list(g["grids"]) == ["flow_24"]
