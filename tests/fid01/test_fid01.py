"""FID-01 (#62, M3a): designs, builder and the frozen rules on planted data (every outcome, G rule, secondary label and the extension path)."""
from __future__ import annotations

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

HAS_DESIGNS = (D.OUT / "designs.json").exists() and (D.OUT / "states.json").exists()


# ---- designs ------------------------------------------------------------------------------------------------------------------------------------------
def test_single_modes_reproduce_v18_plate_and_combos_are_joint():
    import mode01_v18_prescreen as P18
    import v18_plate as V
    s, p = P18.load_parent()
    for m, a in [("heave", -31.1), ("pitch", -0.7), ("camber", 19.7), ("reflex", -29.3), ("twist", 2.3), ("sweep", 11.3)]:
        assert np.array_equal(D.design_phi(s, p, {m: a}), V.mode_phi(s, p, m, a)), m
    q = dict(p, zc=p["zc"] + -13.7 / 1000.0, camber=p["camber"] + -11.3 / 1000.0)
    joint = V.plate_phi(s, q, twist=lambda e: math.radians(1.1) * (e ** 2 - 1 / 3))
    assert np.array_equal(D.raw_design(s, p, {"heave": -13.7, "camber": -11.3, "twist": 1.1}), joint)
    with pytest.raises(ValueError):
        D.raw_design(s, p, {"heave": 1.0, "bump_lower": 5.0})


def test_slots_meet_the_issue_and_exclude_m2_openfoam_states():
    fams = {f for st, f, _ in D.SLOTS.values()}
    assert len(D.SLOTS) >= 12 and len(fams) >= 4 and {st for st, _, _ in D.SLOTS.values()} == {"wide", "narrow"}
    m2_of = {"v18__pitch_p3.1", "v18__pitch_m3.1", "v18__pitch_p1.3", "v18__reflex_p29.3", "v18__thickness_D0_p3", "v18__offset_s050_m5"}
    names = [D.name(c) for _, _, cands in D.SLOTS.values() for c in cands]
    assert not m2_of & set(names) and len(names) == len(set(names))
    assert D.name({"camber": -11.3, "reflex": -19.7}) == "v18__camber_m11.3_reflex_m19.7"


def test_coefficients_are_the_m2_values():
    c = F.coefficients()
    assert abs(c["delta_min_n"] - 1.807e-3) < 1e-6 and abs(c["delta_min_literal_n"] - 5.363e-3) < 1e-6


@pytest.mark.skipif(not HAS_DESIGNS, reason="designs.json / states.json not built")
def test_builder_kernels_and_of_layout():
    import fid01_build as B
    from cfd_harness import campaign_schema as SC
    st, wide = B.state_names(), B.wide_names()
    ks = B.kernels()
    for k, phases in B.F32.items():
        runs = ks[k]["runs"]
        assert [r["name"] for r in runs] == [f"{s}__k{ph}" for ph in phases for s in st]          # phase-major, parent first, every pair in one kernel
        assert {r["env"]["W4_CANONICAL_ORIGIN_M"].split(",")[2] for r in runs} == {"-0.6"}
    f48 = [r["state"] for k in ("f48a", "f48b") for r in ks[k]["runs"]]
    assert set(f48) == {B.PARENT, *wide} and f48.count(B.PARENT) == 2
    c = json.loads(B.CAMPAIGN.read_text()) if B.CAMPAIGN.exists() else None
    if c is not None:
        SC.validate_campaign(c)
    ok = B.of_kernels()
    v1 = [cid for k, (lev, cases) in ok.items() if lev == "V1" for cid, *_ in cases]
    assert len(v1) == len(st) * 32 and len(set(v1)) == len(v1)
    idx = {int(cid.rsplit("_", 1)[1][:-1]) for k, (lev, cases) in ok.items() for cid, *_ in cases}
    assert min(idx) == 49 and not idx & set(range(1, 49))
    for k, (lev, cases) in ok.items():
        if lev != "V1":
            assert B.ROLL not in {c[1] for c in cases}
        if lev == "V3":
            assert {c[1] for c in cases if "__r16" in c[1]} == {f"{n}__r16" for n in B.ex_names()}
    for lev, tags in B.EXTENSION_SHIFTS.items():
        assert not set(tags) & set(B.LEVELS[lev]["shifts"]) and len(set(tags)) == len(tags)
    assert dict(B.shifts(["49p", "49m"]))["49m"] == [-x for x in dict(B.shifts(["49p"]))["49p"]]


# ---- planted data -------------------------------------------------------------------------------------------------------------------------------------
WIDE = {"W_r1": ("rigid", 4e-3, 2e-3), "W_r2": ("rigid", -3e-3, -1e-3), "W_s1": ("section", 1.2e-2, 3e-3), "W_s2": ("section", -1.0e-2, -2e-3),
        "W_p1": ("span", 2.5e-3, 1e-3), "C_1": ("combination", 1.5e-2, 4e-3), "C_2": ("combination", 6e-3, 2e-3), "C_3": ("combination", -5e-3, -2e-3),
        "C_4": ("combination", -8e-3, -3e-3), "W_tiny": ("span", 4e-4, 1e-4)}
NARROW = {"N_1": ("local", 2.5e-3, 5e-4), "N_2": ("local", 2e-4, 0.0)}
LEVELS = {"V1": [f"{i}{m}" for i in range(49, 65) for m in "pm"], "V2": ["49p", "49m", "50p", "50m"], "V3": ["49p"]}


def states_rec():
    rec = {F.PARENT: {"slot": None}, F.ROLL: {"slot": None}}
    for i, (n, (fam, _, _)) in enumerate({**WIDE, **NARROW}.items()):
        rec[n] = {"slot": ("W4" if n == "W_s1" else "N1" if n == "N_1" else f"S{i}"), "stratum": "narrow" if n in NARROW else "wide", "family": fam}
    return rec


def planted(rho=None, wl_over=None, nc_wl=-1.648e-3, nc_of=-6.6e-4, drop=None, g5a=None, r48=None, drag_rho=0.75):
    """WaterLily: 4 phases; OpenFOAM: rho * Delta_WL on every level plus small noise.  rho: {(design, level): value}."""
    rng = np.random.default_rng(7)
    rho, wl_over, drop, g5a, r48 = rho or {}, wl_over or {}, drop or set(), g5a or {}, r48 or {}
    allD = {**WIDE, **NARROW}
    base = {"downforce": 0.26 + 1e-3 * rng.standard_normal(4), "drag": 0.27 + 1e-3 * rng.standard_normal(4)}
    forces = {F.PARENT: {r: list(base[r]) for r in F.RESP}}
    for n, (_, d, dg) in allD.items():
        d = wl_over.get(n, d)
        forces[n] = {"downforce": list(base["downforce"] + d + 5e-5 * rng.standard_normal(4)), "drag": list(base["drag"] + dg + 5e-5 * rng.standard_normal(4))}
    forces[F.ROLL] = {"downforce": list(base["downforce"] + nc_wl + 5e-5 * rng.standard_normal(4)), "drag": list(base["drag"] - 1e-3 + 5e-5 * rng.standard_normal(4))}
    wl32 = F.wl_stats(forces)
    wl48 = {"differences": {n: {"downforce": {"delta_bar_n": r48.get(n, wl_over.get(n, d) * 0.98)}} for n, (_, d, _) in WIDE.items()}}
    wlres = {"flow_32": {"P": 4, **wl32}, "flow_48": wl48}
    vals = {}
    for L, tags in LEVELS.items():
        v = vals.setdefault(L, {})
        for t in tags:
            m = t[-1]
            p0 = {"downforce": 0.2 + 3e-4 * rng.standard_normal(), "drag": 0.34 + 3e-4 * rng.standard_normal()}
            v[(F.PARENT, t)] = p0
            for n, (_, d, dg) in allD.items():
                if (n, L, t) in drop:
                    continue
                rr = rho.get((n, L), 0.65)
                e = 4e-5 * rng.standard_normal() if L == "V1" else (1e-4 if m == "p" else -1e-4)   # V2: antithetic, so the level mean is exact
                v[(n, t)] = {"downforce": p0["downforce"] + rr * wl_over.get(n, d) + e, "drag": p0["drag"] + drag_rho * dg + e}
            if L == "V1":
                v[(F.ROLL, t)] = {"downforce": p0["downforce"] + nc_of + 4e-5 * rng.standard_normal(), "drag": p0["drag"] - 7e-4}
            if L == "V3":
                for n in (F.PARENT, "W_s1", "N_1"):
                    v[(f"{n}__r16", t)] = {k: x + 1e-5 for k, x in v[(n, t)].items()}
    for (n, L, t) in drop:
        if n == F.PARENT:
            vals[L].pop((n, t), None)
    export = {f"{n}|r8": {"g5a_pass": g5a.get(n, True)} for n in allD}
    return states_rec(), wlres, vals, export


def run(**kw):
    out, _ = F.evaluate(*planted(**kw), {})
    return out


def test_all_good_is_go_and_secondary_labels():
    out = run()
    assert out["outcome"] == "FID01_GO"
    assert set(out["decision_set"]["D"]) == set(WIDE) - {"W_tiny"} and out["sub_threshold_wide"] == ["W_tiny"]
    assert out["NC"]["consistent"] and out["narrow"]["label"] == "NARROW_PASS" and out["narrow"]["eligible"] == ["N_1"]
    assert not out["R3"]["R3_CHALLENGED"] and out["EX"]["W_s1"]["label"] == "EXPORT_INSENSITIVE"
    assert out["literal_threshold"]["outcome"] == "FID01_INCONCLUSIVE_DESIGN_SET"     # only 6 designs >= 5.363e-3 N
    assert out["improvement_only"]["outcome_descriptive"] == "FID01_GO" and out["correlation_wl_of_V1"] > 0.99


def test_resolved_sign_flip_on_one_level_is_no_go():
    out = run(rho={("C_2", "V3"): -0.6})
    assert out["outcome"] == "FID01_NO_GO" and out["per_design"]["C_2"]["rules"]["G1"] == "FAIL" and out["per_design"]["C_2"]["G1_levels"]["V3"] == "FAIL"


def test_small_opposite_value_is_unresolved_but_its_spread_fails():
    out = run(rho={("W_p1", "V3"): -0.1})                      # V3 slightly negative: G1 unresolved there, but the level spread is a resolved G3 failure
    p = out["per_design"]["W_p1"]
    assert p["G1_levels"]["V3"] == "UNRESOLVED" and p["rules"]["G3"] == "FAIL" and out["outcome"] == "FID01_NO_GO"


def test_unresolved_spread_triggers_the_extension_and_remaining_unresolved_fails():
    out = run(rho={("W_p1", "V3"): 0.25})                        # V3 0.25: range above the tolerance by less than 2 SE
    p = out["per_design"]["W_p1"]
    assert p["rules"]["G3"] == "UNRESOLVED" and out["outcome"] == "EXTENSION_REQUIRED" and "W_p1" in out["extension_plan"]["V3"]
    srec, wlres, vals, export = planted(rho={("W_p1", "V3"): 0.25})
    ext = F.extension_eval(json.loads(json.dumps(out, default=str)), srec, wlres, vals, export)
    assert ext["recomputed"] == ["W_p1"] and ext["per_design"]["W_p1"]["rules"]["G3"] == "FAIL" and ext["outcome"] == "FID01_NO_GO"
    ok = F.extension_eval(json.loads(json.dumps(out, default=str)), *planted()[0:4])   # the added shifts resolve it
    assert ok["outcome"] == "FID01_GO"


def test_retention_band_and_g2():
    low = run(rho={("W_s2", "V1"): 0.3, ("W_s2", "V2"): 0.3, ("W_s2", "V3"): 0.3})
    assert low["per_design"]["W_s2"]["rules"]["G4"] == "FAIL" and low["outcome"] == "FID01_NO_GO"
    high = run(rho={("C_1", "V1"): 2.6, ("C_1", "V2"): 2.6, ("C_1", "V3"): 2.6})
    assert high["per_design"]["C_1"]["rules"]["G4"] == "FAIL"
    flat = run(rho={("W_r1", "V1"): 0.0005})
    assert flat["per_design"]["W_r1"]["rules"]["G2"] == "FAIL" and flat["outcome"] == "FID01_NO_GO"


def test_spread_across_levels():
    out = run(rho={("C_1", "V3"): 1.2})                         # V1 0.65, V2 0.65, V3 1.2: range 0.55 > 0.5 x 0.65
    assert out["per_design"]["C_1"]["rules"]["G3"] == "FAIL"
    ok = run(rho={("C_1", "V3"): 0.9})                           # range 0.25 <= 0.325
    assert ok["per_design"]["C_1"]["rules"]["G3"] == "PASS"


def test_constraints_g5():
    geo = run(g5a={"C_3": False})
    assert geo["per_design"]["C_3"]["rules"]["G5"] == "FAIL" and geo["outcome"] == "FID01_NO_GO"
    drag = run(drag_rho=-0.8)
    assert drag["per_design"]["C_1"]["G5"]["drag_resolved_sign_conflict"] and drag["outcome"] == "FID01_NO_GO"


def test_negative_control_and_minimum_data():
    assert run(nc_wl=-3e-3)["outcome"] == "FID01_INVALID"
    assert run(nc_of=0.0)["outcome"] == "FID01_INVALID"
    gone = {(F.PARENT, "V1", f"{i}p") for i in range(49, 54)}
    out = run(drop=gone)
    assert out["outcome"] == "FID01_INVALID" and not out["minimum_data"]["pass"]
    v3 = run(drop={("C_4", "V3", "49p")})                       # one design loses its only V3 pair -> unresolved, not invalid
    assert v3["per_design"]["C_4"]["G1_levels"]["V3"] == "UNRESOLVED" and v3["outcome"] == "EXTENSION_REQUIRED" and "V3" in v3["extension_plan"]


def test_design_set_validity():
    small = {n: 1e-3 for n in ("W_r1", "W_r2", "W_s2", "C_2", "C_3")}
    out = run(wl_over=small)
    assert len(out["decision_set"]["D"]) < 8 and out["outcome"] == "FID01_INCONCLUSIVE_DESIGN_SET"


def test_r3_and_narrow_labels():
    out = run(r48={"C_2": -3e-3})
    assert out["R3"]["designs"]["C_2"]["label"] == "R3_CONTRADICTED" and out["R3"]["R3_CHALLENGED"] and out["outcome"] == "FID01_GO"
    nf = run(rho={("N_1", "V1"): -0.5, ("N_1", "V2"): -0.5, ("N_1", "V3"): -0.5})
    assert nf["narrow"]["label"] == "NARROW_FAIL" and nf["outcome"] == "FID01_GO"
    nu = run(wl_over={"N_1": 1e-4})
    assert nu["narrow"]["label"] == "NARROW_UNTESTABLE"


def test_se_floor_and_write_once(tmp_path):
    d = F.wl_stats({F.PARENT: {"downforce": [0.0] * 4, "drag": [0.0] * 4}, "x": {"downforce": [2e-3] * 4, "drag": [1e-3] * 4}})["differences"]["x"]
    assert d["downforce"]["sigma_d_n"] == 0 and d["downforce"]["se_eff_n"] == pytest.approx(F.FLOOR["downforce"] / 2)
    p = tmp_path / "a.json"
    F.write_once(p, {"a": 1})
    with pytest.raises(FileExistsError):
        F.write_once(p, {"a": 2})


def test_budget_rule(tmp_path):
    log = tmp_path / "k.log"
    log.write_text(json.dumps([{"time": 10.0}, {"time": 16000.0}]))
    b = F.budget([f"f32a={log}"], {"f32b": 16030}, [16640, 16640])
    assert b["T_s"] == 16000 + 16030 + 33280 and b["push_f48"]
    assert not F.budget([f"f32a={log}"], {"f32b": 40000}, [16640, 16640])["push_f48"]
