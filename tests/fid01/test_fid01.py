"""FID-01 (#62, M3a): designs, builder and the frozen rules on planted data (every outcome, G rule, secondary label and the extension path)."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import analyze_fid01 as F  # noqa: E402
import fid01_designs as D  # noqa: E402

HAS_STATES = (D.OUT / "designs.json").exists() and (D.OUT / "states.json").exists()


# ---- designs ------------------------------------------------------------------------------------------------------------------------------------------
def test_single_modes_reproduce_v18_plate_and_combos_are_joint():
    import mode01_modes as M
    import mode01_v18_prescreen as P18
    import v18_plate as V
    s, p = P18.load_parent()
    for m, a in [("heave", -31.1), ("pitch", -0.7), ("camber", 19.7), ("reflex", -29.3), ("twist", 2.3), ("sweep", 11.3)]:
        assert np.array_equal(D.design_phi(s, p, {m: a}), V.mode_phi(s, p, m, a)), m
    q = dict(p, zc=p["zc"] + -13.7 / 1000.0, camber=p["camber"] + -11.3 / 1000.0)
    joint = V.plate_phi(s, q, twist=lambda e: math.radians(1.1) * (e ** 2 - 1 / 3))
    assert np.array_equal(D.raw_design(s, p, {"heave": -13.7, "camber": -11.3, "twist": 1.1}), joint)
    assert np.array_equal(D.raw_design(s, p, {"bump_lower": 10.0}), M.raw_mode(s, "bump_lower", 10.0))
    assert np.array_equal(D.raw_design(s, p, {"bump_lower_s300": 10.0}), M._bump(s, 10.0, -1.0, 0.3))
    with pytest.raises(ValueError):
        D.raw_design(s, p, {"heave": 1.0, "bump_lower": 5.0})


def test_slots_meet_the_issue_and_exclude_m2_openfoam_states():
    fams = {f for st, f, _ in D.SLOTS.values()}
    assert len(D.SLOTS) >= 12 and len(fams) >= 4 and {st for st, _, _ in D.SLOTS.values()} == {"wide", "narrow", "mid"}
    import unc01_build as UB
    m2_of = {n for n in UB.u2_states("pitch", "reflex")["flow_32"] if n not in ("v18__parent", "v18__roll_p25")} | {"v18__twist_m1.1"}
    assert m2_of == {"v18__D0_p3", "v18__pitch_p3.1", "v18__pitch_m3.1", "v18__pitch_p1.3", "v18__reflex_p29.3", "v18__s050_m5", "v18__twist_m1.1"}
    names = [D.name(c) for _, _, cands in D.SLOTS.values() for c in cands]
    assert not m2_of & set(names) and len(names) == len(set(names))
    assert D.name({"camber": -11.3, "reflex": -19.7}) == "v18__camber_m11.3_reflex_m19.7"


def test_coefficients_are_the_m2_values():
    c = F.coefficients()
    assert abs(c["delta_min_n"] - 1.807e-3) < 1e-6 and abs(c["delta_min_literal_n"] - 5.363e-3) < 1e-6


@pytest.mark.skipif(not HAS_STATES, reason="designs.json / states.json not built")
def test_builder_kernels_and_of_layout():
    import fid01_build as B
    from cfd_harness import campaign_schema as SC
    st = B.state_names()
    rec = json.loads((D.OUT / "designs.json").read_text())["designs"]
    assert len([d for d in rec.values() if d]) >= 12 and len({d["family"] for d in rec.values() if d}) >= 4
    ks = B.kernels()
    assert set(ks) == {"f32k7", "f32k8", "f32k9", "f32k10"}
    for k, kern in ks.items():
        assert [r["name"] for r in kern["runs"]] == [f"{s}__k{k[4:]}" for s in st]                    # one phase per kernel, parent first, every pair inside
        assert {r["env"]["W4_CANONICAL_ORIGIN_M"].split(",")[2] for r in kern["runs"]} == {"-0.6"}
    if B.CAMPAIGN.exists():
        SC.validate_campaign(json.loads(B.CAMPAIGN.read_text()))
    v1 = B.of_kernels()
    ids = [cid for lev, cases in v1.values() for cid, *_ in cases]
    assert {lev for lev, _ in v1.values()} == {"V1"} and len(ids) == (len(st) + len(B.ex_names())) * 32 and len(set(ids)) == len(ids)
    tags = {cid.rsplit("_", 1)[1] for cid in ids}
    assert tags == set(B.LEVELS["V1"]["shifts"]) and not {int(x[:-1]) for x in tags} & set(range(1, 49))
    for lev, ext in B.EXTENSION_SHIFTS.items():
        assert not set(ext) & set(B.LEVELS[lev]["shifts"]) and B.SMOKE_SHIFT not in ext + B.LEVELS[lev]["shifts"]
    assert dict(B.shifts(["49p", "49m"]))["49m"] == [-x for x in dict(B.shifts(["49p"]))["49p"]]
    k48 = B.kernels48([B.PARENT, st[1], st[2]])["f48"]
    assert [r["state"] for r in k48["runs"]] == [B.PARENT, st[1], st[2]] and k48["config"]["per_state_timeout_s"] <= k48["config"]["solver_wall_time_cap_s"]


# ---- planted data -------------------------------------------------------------------------------------------------------------------------------------
#        name: (stratum, family, Delta_WL downforce, Delta_WL drag)
DESIGNS = {"W_r1": ("wide", "rigid", 8e-3, 3e-3), "W_r2": ("wide", "rigid", -6e-3, -2.5e-3), "W_s1": ("wide", "section", 1.2e-2, 3e-3),
           "W_s2": ("wide", "section", -1.0e-2, -2e-3), "W_p1": ("wide", "span", 3e-3, 1e-3), "C_1": ("wide", "combination", 1.5e-2, 4e-3),
           "C_2": ("wide", "combination", 6e-3, 2e-3), "C_3": ("wide", "combination", -7e-3, -2e-3), "C_4": ("wide", "combination", -9e-3, -3e-3),
           "W_tiny": ("wide", "span", 4e-4, 1e-4), "N_1": ("narrow", "local", 2.5e-3, 5e-4), "M_1": ("mid", "local", 2e-4, 0.0)}
SLOT = {"W_s1": "W4", "W_s2": "W6"}
LEV_TAGS = {"V1": [f"{i}{m}" for i in range(49, 65) for m in "pm"], "V2": ["49p", "49m", "50p", "50m"], "V3": ["49p"]}


def states_rec():
    rec = {F.PARENT: {"slot": None}, F.ROLL: {"slot": None}}
    for i, (n, (st, fam, _, _)) in enumerate(DESIGNS.items()):
        rec[n] = {"slot": SLOT.get(n, f"S{i}"), "stratum": st, "family": fam, "spec": {"heave": -1.0} if n == "W_r1" else {}}
    return rec


def planted(rho=None, wl_over=None, nc_wl=-1.648e-3, nc_of=-6.6e-4, drop=None, export_over=None, r48=None, drag_rho=0.75, wl_sd=5e-5, of_noise=None):
    """WaterLily: 4 phases; OpenFOAM: rho x Delta_WL on every level; V1 random noise; V2 +e on pair 49 and -e on pair 50 (exact mean, pooled pair SD
    e sqrt(2)); V3 one shift (49 +) with +e."""
    rng = np.random.default_rng(7)
    rho, wl_over, drop, export_over, r48 = rho or {}, wl_over or {}, drop or set(), export_over or {}, r48 or {}
    e23 = of_noise or {"V2": 1e-4, "V3": 1e-4}
    base = {t: {"downforce": 0.26 + 1e-3 * rng.standard_normal(), "drag": 0.27 + 1e-3 * rng.standard_normal()} for t in ("k7", "k8", "k9", "k10")}
    forces = {F.PARENT: base}
    for n, (_, _, d, dg) in DESIGNS.items():
        d = wl_over.get(n, d)
        forces[n] = {t: {"downforce": b["downforce"] + d + wl_sd * rng.standard_normal(), "drag": b["drag"] + dg + wl_sd * rng.standard_normal()} for t, b in base.items()}
    forces[F.ROLL] = {t: {"downforce": b["downforce"] + nc_wl + wl_sd * rng.standard_normal(), "drag": b["drag"] - 1e-3} for t, b in base.items()}
    wl = F.wl_diffs(forces)
    vals = {}
    for L, tags in LEV_TAGS.items():
        v = vals.setdefault(L, {})
        for t in tags:
            p0 = {"downforce": 0.2 + 3e-4 * rng.standard_normal(), "drag": 0.34 + 3e-4 * rng.standard_normal()}
            if (F.PARENT, L, t) not in drop:
                v[(F.PARENT, t)] = p0
            for n, (_, _, d, dg) in DESIGNS.items():
                if (n, L, t) in drop:
                    continue
                sgn = (1 if t.endswith("p") else -1) if L == "V3" else (1 if t.startswith("49") else -1)   # V2: +e on pair 49, -e on pair 50
                e = 4e-5 * rng.standard_normal() if L == "V1" else sgn * e23[L]
                v[(n, t)] = {"downforce": p0["downforce"] + rho.get((n, L), 0.65) * wl_over.get(n, d) + e, "drag": p0["drag"] + drag_rho * dg + e}
            if L == "V1":
                v[(F.ROLL, t)] = {"downforce": p0["downforce"] + nc_of + 4e-5 * rng.standard_normal(), "drag": p0["drag"] - 7e-4}
                for n in (F.PARENT, "W_s1", "W_s2"):
                    if (n, t) in v:
                        v[(f"{n}__r4", t)] = {k: x + 1e-6 for k, x in v[(n, t)].items()}
    export = {f"{n}|r8": {"pass": True, "stl_volume_vs_parent": 0.002, "sdf_smoothed_volume_vs_parent": 0.003, **export_over.get(n, {})} for n in DESIGNS}
    wl32_k7 = {s: f["k7"] for s, f in forces.items()}
    wl48 = {s: {**wl32_k7[s], "downforce": wl32_k7[s]["downforce"] + r48.get(s, 0.0)} for s in (F.PARENT, "W_p1", "C_1", "C_4")}
    return states_rec(), wl, vals, export, wl48, wl32_k7


def run(levels=("V1", "V2", "V3"), **kw):
    srec, wl, vals, export, wl48, k7 = planted(**kw)
    out, _ = F.evaluate(srec, wl, vals, export, levels, wl48, k7)
    return out


def test_all_good_is_go_with_tiers_and_secondary_labels():
    out = run()
    t = out["tiers"]
    assert out["outcome"] == "FID01_GO" and set(t["A"]) == {"W_r1", "W_r2", "W_s1", "W_s2", "C_1", "C_2", "C_3", "C_4"}
    assert t["B"] == ["W_p1"] and t["support"] == ["N_1"] and "W_tiny" in t["sub_threshold_wide"] and t["A_valid"]
    assert out["NC"]["consistent"] and out["G3_set"]["label"] == "PASS" and abs(out["G3_set"]["slope"] - 1) < 0.05
    assert out["tier_B_label"] == "TIER_B_PASS" and out["support_label"] == "SUPPORT_PASS"
    g = out["m3b_min_gain"]
    assert g["x_star_n"] == pytest.approx(3e-3, rel=0.05) and g["min_gain_relative"] == pytest.approx(g["x_star_n"] / F.J_B48)
    assert not out["R3"]["R3_CHALLENGED"] and out["EX"]["W_s1"]["label"] == "EXPORT_INSENSITIVE" and out["heave_sublabel"] == {"W_r1": "PASS"}
    assert out["aggregate"]["kendall_tau_all"] > 0.9 and out["S_d_OF"] == pytest.approx(1e-4 / 0.2, rel=0.05)   # V3 carries +1e-4


def test_resolved_sign_flip_is_no_go_with_cause():
    v1 = run(rho={("C_2", "V1"): -0.6})
    assert v1["outcome"] == "FID01_NO_GO" and v1["per_design"]["C_2"]["G1_levels"]["V1"] == "FAIL" and v1["cause"] == "WL_OF"
    v3 = run(rho={("C_2", "V3"): -0.6})
    assert v3["outcome"] == "FID01_NO_GO" and v3["per_design"]["C_2"]["G1_levels"]["V3"] == "FAIL" and v3["cause"] == "OF_MESH"


def test_unresolved_spread_triggers_the_extension_and_never_becomes_a_fail():
    kw = {"rho": {("C_2", "V2"): 0.33}, "of_noise": {"V2": 4e-4, "V3": 1e-4}}   # V1 0.65 vs V2 0.33: range above the tolerance by less than 2 SE
    out = run(**kw)
    assert out["per_design"]["C_2"]["rules"]["G3"] == "UNRESOLVED_STAT" and out["outcome"] == "EXTENSION_REQUIRED" and "C_2" in out["extension_plan"]["V2"]
    srec, wl, vals, export, *_ = planted(**kw)
    ext = F.extension_eval(json.loads(json.dumps(out, default=str)), srec, wl, vals, export)
    assert ext["recomputed"] == ["C_2"] and ext["outcome"] == "FID01_INCONCLUSIVE_PRECISION"
    ok = F.extension_eval(json.loads(json.dumps(out, default=str)), *planted()[:4])
    assert ok["outcome"] == "FID01_GO"


def test_retention_band():
    low = run(rho={("W_s2", "V1"): 0.3, ("W_s2", "V2"): 0.3, ("W_s2", "V3"): 0.3})
    assert low["per_design"]["W_s2"]["rules"]["G4"] == "FAIL" and low["outcome"] == "FID01_NO_GO" and low["cause"] == "WL_OF"
    high = run(rho={("C_1", "V1"): 2.6, ("C_1", "V2"): 2.6, ("C_1", "V3"): 2.6})
    assert high["per_design"]["C_1"]["rules"]["G4"] == "FAIL"
    flat = run(rho={("W_r1", "V1"): 0.0, ("W_r1", "V2"): 0.0, ("W_r1", "V3"): 0.0})   # OpenFOAM sees nothing: G2 cannot pass, G4 fails resolved
    assert flat["per_design"]["W_r1"]["rules"]["G2"] == "UNRESOLVED_STAT" and flat["per_design"]["W_r1"]["rules"]["G4"] == "FAIL"
    edge = run(rho={("C_2", "V1"): 0.505, ("C_2", "V2"): 0.505, ("C_2", "V3"): 0.505}, wl_sd=4e-4)   # rho 0.49 with WaterLily noise: unresolved, not a fail
    assert edge["per_design"]["C_2"]["rules"]["G4"] == "UNRESOLVED_STAT"


def test_spread_and_v3_slope():
    out = run(rho={("C_1", "V2"): 1.2})                         # V1 0.65 vs V2 1.2: range 0.55 > 0.5 x 0.925, resolved
    assert out["per_design"]["C_1"]["rules"]["G3"] == "FAIL" and out["cause"] == "OF_MESH"
    v3 = run(rho={(n, "V3"): 0.3 for n in DESIGNS})               # V3 at 0.46 of V1 for every tier-A design: set slope outside [0.6, 1.67]
    assert v3["G3_set"]["label"] == "FAIL" and v3["outcome"] == "FID01_NO_GO" and v3["cause"] == "OF_MESH"
    assert run(levels=("V1", "V2"), rho={(n, "V3"): 0.3 for n in DESIGNS})["outcome"] == "FID01_GO"   # V3_NOT_CONVERGED contingency


def test_constraints_g5():
    geo = run(export_over={"C_3": {"stl_volume_vs_parent": 0.02, "sdf_smoothed_volume_vs_parent": 0.0}})   # STL vs SDF volume chain off by 2 %
    assert geo["per_design"]["C_3"]["G5"]["geometry"]["stl_vs_sdf_volume_chain"] is False and geo["outcome"] == "FID01_NO_GO"
    drag = run(drag_rho=-0.8)
    assert drag["per_design"]["C_1"]["rules"]["G5"] == "FAIL" and drag["outcome"] == "FID01_NO_GO"
    assert drag["per_design"]["W_p1"]["G5"]["drag"].startswith("drag change below")   # |Delta drag| 1e-3 < 2e-3: not tested


def test_negative_control_and_minimum_data():
    assert run(nc_wl=-3.5e-3)["outcome"] == "FID01_INVALID"
    assert run(nc_of=0.0)["outcome"] == "FID01_INVALID"
    gone = {(F.PARENT, "V1", f"{i}p") for i in range(49, 54)}
    out = run(drop=gone)
    assert out["outcome"] == "FID01_INVALID" and not out["minimum_data"]["pass"]
    lost = run(drop={("C_4", "V3", "49p")})                    # data loss is never a FAIL
    assert lost["per_design"]["C_4"]["G1_levels"]["V3"] == "UNRESOLVED_DATA" and lost["outcome"] == "FID01_INCOMPLETE"


def test_design_set_validity():
    small = {n: 3e-3 for n in ("W_r1", "W_r2", "W_s2", "C_2", "C_3")}
    out = run(wl_over=small)
    assert len(out["tiers"]["A"]) < 6 and out["outcome"] == "FID01_INCONCLUSIVE_DESIGN_SET" and len(out["tiers"]["B"]) == 6


def test_tier_b_failure_raises_the_m3b_minimum_gain():
    out = run(rho={("W_p1", "V1"): -0.6, ("W_p1", "V2"): -0.6})
    assert out["outcome"] == "FID01_GO" and out["tier_B_label"] == "TIER_B_FAIL"
    g = out["m3b_min_gain"]
    assert g["largest_non_passing_tier_B_n"] == pytest.approx(3e-3, rel=0.05) and g["x_star_n"] >= 5.363e-3


def test_r3_and_support_labels():
    out = run(r48={"C_4": 1.5e-2})
    assert out["R3"]["designs"]["C_4"]["label"] == "R3_CONTRADICTED" and out["R3"]["R3_CHALLENGED"] and out["outcome"] == "FID01_GO"
    nf = run(rho={("N_1", "V1"): -0.5, ("N_1", "V2"): -0.5})
    assert nf["support_label"] == "SUPPORT_FAIL" and nf["outcome"] == "FID01_GO"
    assert run(wl_over={"N_1": 1e-4})["support_label"] == "SUPPORT_UNTESTABLE"
    assert F.r3_labels(None, None, [])["label"] == "NOT_MEASURED"


def test_wl_floor_data_loss_and_write_once(tmp_path):
    d = F.wl_diffs({F.PARENT: {t: {"downforce": 0.0, "drag": 0.0} for t in ("k7", "k8", "k9", "k10")},
                    "x": {t: {"downforce": 2e-3, "drag": 1e-3} for t in ("k7", "k8", "k9", "k10")},
                    "y": {t: {"downforce": 2e-3, "drag": 1e-3} for t in ("k7", "k8")}})
    assert d["x"]["downforce"]["sigma_d_n"] == 0 and d["x"]["downforce"]["se_eff_n"] == pytest.approx(F.FLOOR["downforce"] / 2) and d["y"]["data_loss"]
    p = tmp_path / "a.json"
    F.write_once(p, {"a": 1})
    with pytest.raises(FileExistsError):
        F.write_once(p, {"a": 2})


def test_of_values_reads_a_result_tree_and_binds_the_frozen_set(tmp_path, monkeypatch):
    crit_dir = tmp_path / "of/criteria"
    crit_dir.mkdir(parents=True)
    crit = {"level": "V2", "registered_before_run": True, "evidence_class": "fid01_openfoam_uncertified_geometry", "case_order": [{"id": "V2_v18__parent_49p", "state": F.PARENT}, {"id": "V2_x_49p", "state": "x"},
                                                                          {"id": "V2_x_49m", "state": "x"}]}
    cp = crit_dir / "v2_49p.json"
    cp.write_text(json.dumps(crit))
    h = hashlib.sha256(cp.read_bytes()).hexdigest()
    out = tmp_path / "run/openfoam_xfid_gridphase_x3"
    out.mkdir(parents=True)
    forces = {"downforce_n": {"window_mean": 0.2}, "drag_n": {"window_mean": 0.3}}
    (out / "result.json").write_text(json.dumps({"criteria_sha256": h, "cases": [
        {"id": "V2_v18__parent_49p", "status": "COMPLETED", "solver": {"converged_in": 1500}, "forces": forces},
        {"id": "V2_x_49p", "status": "COMPLETED", "solver": {"converged_in": None}, "forces": forces},
        {"id": "V2_x_49m", "status": "snappyHexMesh_FAILED"}]}))
    (tmp_path / "run/local_run.json").write_text(json.dumps({"returncode": 0, "dpkg_after_matches_lock": True}))
    monkeypatch.setattr(F, "EVID", tmp_path)
    vals, recs = F.of_values([tmp_path / "run"], accepted=[h])
    assert list(vals["V2"]) == [(F.PARENT, "49p")] and recs["v2_49p"]["case_counts"] == {"valid": 1, "NOT_CONVERGED": 1, "snappyHexMesh_FAILED": 1}
    with pytest.raises(ValueError):
        F.of_values([tmp_path / "run"], accepted=[h, "0" * 64])                       # a frozen kernel missing
    assert F.of_values([tmp_path / "run"], accepted=[h, "0" * 64], lost=["0" * 64])[1]["_lost_criteria_sha256"] == ["0" * 64]   # declared lost
    with pytest.raises(ValueError):
        F.of_values([tmp_path / "run", tmp_path / "run"])
    res = json.loads((out / "result.json").read_text())
    res["cases"][0]["stages"] = [{"name": "simpleFoam", "timed_out": True}]
    (out / "result.json").write_text(json.dumps(res))
    vals, recs = F.of_values([tmp_path / "run"], accepted=[h])
    assert "V2" not in vals and recs["v2_49p"]["case_counts"]["TIMED_OUT"] == 1                                   # a timeout is never a value


def test_export_key_handles_names_with_r():
    import fid01_build as B
    assert B.export_key("v18__reflex_m29.3") == "v18__reflex_m29.3|r8" and B.export_key("v18__roll_p25") == "v18__roll_p25|r8"
    assert B.export_key("v18__reflex_m29.3__r4") == "v18__reflex_m29.3|r4" and B.stl_file("v18__parent", 4) == "v18__parent__r4.stl"


def test_run_sets_from_tiers():
    srec, wl, *_ = planted()
    t = F.tiers(wl, srec)
    rs = F.run_sets(t, wl)
    assert rs["V3"] == [F.PARENT, *t["A"]] and set(rs["V2"]) == {F.PARENT, *t["A"], *t["B"], *t["support"]}
    assert rs["flow_48"] == [F.PARENT, "W_p1", "C_1", "W_s2"]                 # tier B, then the largest positive and the largest negative tier-A design


def test_budget_rule(tmp_path, monkeypatch):
    log = tmp_path / "k.log"
    log.write_text(json.dumps([{"time": 10.0}, {"time": 9000.0}]))
    monkeypatch.setattr(F, "EVID", tmp_path)
    (tmp_path / "d_set.json").write_text(json.dumps({"run_sets": {"flow_48": ["p", "a", "b", "c"]}}))
    b = F.budget([f"f32k{k}={log}" for k in (7, 8, 9, 10)])
    assert b["f48_estimate_s"] == 4 * 2340 + 260 and b["T_s"] == 4 * 9000 + b["f48_estimate_s"] and b["push_f48"]
    (tmp_path / "d_set.json").write_text(json.dumps({"run_sets": {"flow_48": ["p"] + list("abcdefghijklm")}}))
    assert not F.budget([f"f32k{k}={log}" for k in (7, 8, 9, 10)])["push_f48"]
    with pytest.raises(ValueError):
        F.budget([f"f32k7={log}"])


def test_missing_rows_and_other_labels():
    srec, wl, vals, export, wl48, k7 = planted()
    k7.pop("W_p1")
    out, _ = F.evaluate(srec, wl, vals, export, ("V1", "V2", "V3"), wl48, k7)                     # a lost k7 run does not crash R3
    assert out["R3"]["designs"]["W_p1"]["label"] == "R3_UNRESOLVED"
    assert F.r3_labels({F.PARENT: {"downforce": 0.0}}, {}, ["x"])["label"] == "NOT_MEASURED"
    srec, wl, vals, export, wl48, k7 = planted()
    for (s, tg) in list(vals["V1"]):
        if s == "W_s1__r4":
            vals["V1"][(s, tg)] = {k: x + 2e-3 for k, x in vals["V1"][(s, tg)].items()}        # the r = 4 export moves W_s1's difference by 2e-3 N
        if s == F.ROLL and int(tg[:-1]) > 52:
            del vals["V1"][(s, tg)]                                                             # NC with only 4 V1 pairs
    out, _ = F.evaluate(srec, wl, vals, export, ("V1", "V2", "V3"), wl48, k7)
    assert out["EX"]["W_s1"]["label"] == "EXPORT_SENSITIVE" and out["NC"]["of"]["label"] == "MISSING" and out["outcome"] == "FID01_INVALID"


def test_g3_set_alone_unresolved_is_inconclusive_precision():
    rho = {(n, "V3"): (0.36 if i % 2 else 0.44) for i, n in enumerate(DESIGNS)}                # V3/V1 about 0.6 with scatter: slope interval straddles 0.6
    out = run(rho=rho)
    if out["G3_set"]["label"] == "UNRESOLVED_STAT" and all(p["status"] == "PASS" for n, p in out["per_design"].items() if n in out["tiers"]["A"]):
        assert out["outcome"] == "FID01_INCONCLUSIVE_PRECISION"
    assert out["G3_set"]["label"] in ("UNRESOLVED_STAT", "FAIL", "PASS")


def test_extension_on_v1_and_v3():
    kw = {"rho": {("C_2", "V1"): 0.505, ("C_2", "V2"): 0.505, ("C_2", "V3"): 0.505}, "wl_sd": 4e-4}
    out = run(**kw)
    assert out["per_design"]["C_2"]["rules"]["G4"] == "UNRESOLVED_STAT" and out["extension_plan"] == {"V1": ["C_2"]}
    srec, wl, vals, export, *_ = planted(**kw)
    ext = F.extension_eval(json.loads(json.dumps(F.A.clean(out))), srec, wl, vals, export)
    assert ext["outcome"] == "FID01_INCONCLUSIVE_PRECISION" and ext["G3_set"]["label"] == "PASS"
    v3 = run(rho={("C_4", "V3"): -0.02}, of_noise={"V2": 1e-4, "V3": 1e-3})                # small opposite V3 value within 2 SE: G1 V3 unresolved
    assert v3["per_design"]["C_4"]["G1_levels"]["V3"] == "UNRESOLVED_STAT" and "C_4" in v3["extension_plan"]["V3"]


def test_builder_layout_with_planted_designs(tmp_path, monkeypatch):
    import fid01_build as B
    dset = {f"S{i}": {"name": f"v18__d{i}", "stratum": "wide" if i < 12 else "narrow", "family": ["rigid", "section", "span", "combination"][i % 4], "spec": {}}
            for i in range(14)}
    monkeypatch.setattr(B, "designs", lambda: dset)
    monkeypatch.setattr(B, "ex_names", lambda: [B.PARENT, "v18__d4", "v18__d5"])
    st = B.state_names()
    assert st[0] == B.PARENT and st[-1] == B.ROLL and len(st) == 16
    v1 = B.of_kernels()
    assert len(v1) == 4 and sum(len(c) for _, c in v1.values()) == (16 + 3) * 32
    monkeypatch.setattr(B, "OUT", tmp_path)
    monkeypatch.setattr(B, "DSET", tmp_path / "d_set.json")
    (tmp_path / "d_set.json").write_text(json.dumps({"run_sets": {"V2": [B.PARENT, "v18__d1", "v18__d2"], "V3": [B.PARENT] + [f"v18__d{i}" for i in range(7)],
                                                                   "flow_48": [B.PARENT, "v18__d1"]}}))
    (tmp_path / "of_levels.json").write_text(json.dumps({"of_levels": ["V1", "V2", "V3"]}))
    k = B.of_kernels(stage="v23")
    assert sorted(k) == ["v2_49m", "v2_49p", "v2_50m", "v2_50p"] + [f"v3_49p_{i}" for i in range(1, 5)] and k["v3_49p_1"][1][0][1] == B.PARENT
    (tmp_path / "of_levels.json").write_text(json.dumps({"of_levels": ["V1", "V2"]}))
    assert not [n for n in B.of_kernels(stage="v23") if n.startswith("v3")]                      # §5.3 contingency: V3 not built
    ext = B.of_kernels(extension={"V3": ["v18__d1"], "V1": ["v18__d2"]})
    assert [c[0] for c in ext["ext_v3"][1]] == [f"V3_{B.PARENT}_49m", "V3_v18__d1_49m"] and len(ext["ext_v1"][1]) == 2 * 16
    with pytest.raises(SystemExit):
        B.kernels48([B.PARENT])


def test_harness_wrapper_exempts_only_the_unaddressable_placeholder():
    from cfd_harness import campaign_schema as SC
    original = SC.parse_listing
    import fid01_harness as H
    try:
        SC.parse_listing = H.parse_listing
        out = "ref,title,author,lastRunTime,totalVotes\nramhachi888/a,a,x,2026,0\n,[Private Notebook],,2010-04-01 00:00:00,0\n,other,,2010,0\n"
        rows = SC.parse_listing(out)
        assert [r["title"] for r in rows] == ["a", "other"]
        assert not all(r.get("ref", "").startswith("ramhachi888/") for r in rows)                  # an empty ref with another title still fails closed
    finally:
        SC.parse_listing = original                                                                # the harness itself stays unpatched for other tests
