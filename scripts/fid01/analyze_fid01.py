#!/usr/bin/env python3
"""FID-01 (#62, M3a) analysis: the rules of docs/fid01_registration_2026_10_21.md §6 (that text governs; a disagreement is a defect here).

    analyze_fid01.py dset --campaign C --tables T... --kernel-root D --out d_set.json                 # §6.2 tiers and run sets from flow_32 only (written once)
    analyze_fid01.py budget --finished KERNEL=LOG... --out J                                            # §4.3 flow_48 push decision from session times only
    analyze_fid01.py main --dset S --campaign C --tables T... --campaign48 C48 --tables48 T... --kernel-root D --of OF_DIR... --out J    # written once
    analyze_fid01.py extension --main J --campaign ... --of OF_DIR... --out J2                          # §6.8, written once

OF_DIR: a local OpenFOAM output directory (`<out>/openfoam_xfid_gridphase_x3/result.json` + `local_run.json`) of a FID-01 OpenFOAM kernel; its criteria
are the tracked file docs/evidence/fid01_2026_10_21/of/criteria/<kernel>.json whose SHA-256 the result records; the accepted set of criteria is the one
frozen in freeze2.json / freeze3.json (`of_criteria_sha256`), every one of them exactly once.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/fid01")]
import analyze_unc01 as A  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402

RESP = ("downforce", "drag")
PARENT, ROLL = "v18__parent", "v18__roll_p25"
EVID = ROOT / "docs/evidence/fid01_2026_10_21"
# §7.1, read from docs/evidence/unc01_2026_10_20/analysis.json (checked by `coefficients`)
M2_ANALYSIS_SHA = "ee71c6d6"   # prefix; the full value is checked against the file
S_D, S_B, S_C, J_B48 = 0.003399676556346094, 0.006690411667275657, 0.010090088223621752, 0.26577921974115387
DELTA_MIN, DELTA_MIN_LIT = 2 * S_D * J_B48, 2 * max(S_B, S_C) * J_B48           # tier B lower edge (paired E2), tier A lower edge (literal E2)
FLOOR = {"downforce": 0.00020904201605451784, "drag": 0.000136408347135453}   # M2 flow_32 sigma_d of the roll
NC_REF = {"wl": (-0.0016476407624087992, 8.534104568937632e-05), "of": (-0.0006614761397334482, 5.792182318004298e-05)}
NC_FLOOR, NC_Z, NC_MIN_PAIRS = 3e-4, 3.5, 12
RHO_BAND = (0.5, 2.0)
SPREAD_MAX = 0.5
V3_SLOPE_BAND = (0.6, 1 / 0.6)    # two levels within the G3 tolerance <=> ratio in [0.6, 1.67]
DRAG_MIN = 2e-3                   # G5b tested only where |Delta drag_WL| >= 2e-3 N (about twice the roll's drag difference)
VOLUME_BAND, CHAIN_TOL = 0.10, 0.01
MIN_A, MIN_FAMILIES, MIN_POSITIVE = 6, 3, 2
WIDE_FAMILIES = ("rigid", "section", "span", "combination")
MIN_UNITS = {"V1": 12, "V2": 1, "V3": 1}   # V1/V2: whole mirror pairs; V3: shifts
MIN_WL_P = 3
WL_CAP_S = 64800
EST_S = {"flow_32": 415, "flow_48": 2340}
SETUP_S = 260
EX_R = 16


def coefficients(path=ROOT / "docs/evidence/unc01_2026_10_20/analysis.json") -> dict:
    """§7.1: every coefficient above is re-read from the M2 analysis; a mismatch is a defect."""
    a = SC.jload(path)
    q = a["Q4_E2"]["downforce"]["common_phases"]
    r32 = a["grids"]["flow_32"]["differences"][ROLL]
    of = a["u3"]["differences"][ROLL]["downforce"]
    got = {"S_d": q["S_d"], "S_b": q["S_b"], "S_c": q["S_c"], "J_b48": q["denominator_n"], "floor_downforce": r32["downforce"]["sigma_d_n"],
           "floor_drag": r32["drag"]["sigma_d_n"], "nc_wl": (r32["downforce"]["delta_bar_n"], r32["downforce"]["se_n"]), "nc_of": (of["delta_bar_n"], of["se_n"])}
    want = {"S_d": S_D, "S_b": S_B, "S_c": S_C, "J_b48": J_B48, "floor_downforce": FLOOR["downforce"], "floor_drag": FLOOR["drag"], "nc_wl": NC_REF["wl"], "nc_of": NC_REF["of"]}
    SC.req(SC.sha256_path(path).startswith(M2_ANALYSIS_SHA) and got == want, "M2 coefficients differ from the registered values")
    return {"m2_analysis_sha256": SC.sha256_path(path), **got, "delta_min_n": DELTA_MIN, "delta_min_literal_n": DELTA_MIN_LIT}


# ---- WaterLily --------------------------------------------------------------------------------------------------------------------------------------
def wl_load(campaign_path, tables, kernel_root, campaign_id):
    """state -> phase tag -> {downforce, drag} for every verified run (files checked against the tables' hashes)."""
    c, rows, _ = A.load_rows(campaign_path, tables, campaign_id=campaign_id)
    out = {}
    for (case, state, tag), row in rows.items():
        if kernel_root is not None:
            A.run_files(c, kernel_root, row)
        out.setdefault(state, {})[tag] = {r: row[r] for r in RESP}
    return out


def wl_diffs(forces: dict) -> dict:
    """Paired differences vs the parent over each design's common phases (§6.1); fewer than MIN_WL_P common phases is a data loss."""
    out = {}
    for s, f in forces.items():
        if s == PARENT:
            continue
        common = sorted(set(f) & set(forces.get(PARENT, {})), key=lambda t: int(t[1:]))
        e = {"phases": common}
        if len(common) < MIN_WL_P:
            e["data_loss"] = True
        else:
            for r in RESP:
                st = A.stats([f[t][r] - forces[PARENT][t][r] for t in common])
                st["se_eff_n"] = max(st["sigma_d_n"], FLOOR[r]) / math.sqrt(st["P"])
                e[r] = st
        out[s] = e
    return out


def tiers(diffs: dict, states_rec: dict) -> dict:
    """§6.2 from WaterLily only: tier A (|Delta| >= literal E2) decides; tier B (paired E2 <= |Delta| < literal) validates the M3b range; support
    designs (narrow/mid) with |Delta| >= Delta_min are judged for the support label.  Both signs count; every member must clear 3 SE_eff."""
    def ok(n, lo, hi=math.inf):
        d = diffs.get(n, {})
        return "downforce" in d and lo <= abs(d["downforce"]["delta_bar_n"]) < hi and abs(d["downforce"]["delta_bar_n"]) > 3 * d["downforce"]["se_eff_n"]
    designs = [n for n, r in states_rec.items() if r.get("slot")]
    wide = [n for n in designs if states_rec[n]["stratum"] == "wide"]
    support = [n for n in designs if states_rec[n]["stratum"] != "wide"]
    a = [n for n in wide if ok(n, DELTA_MIN_LIT)]
    b = [n for n in wide if ok(n, DELTA_MIN, DELTA_MIN_LIT)]
    fams = sorted({states_rec[n]["family"] for n in a} & set(WIDE_FAMILIES))
    pos = [n for n in a if diffs[n]["downforce"]["delta_bar_n"] > 0]
    return {"A": a, "B": b, "support": [n for n in support if ok(n, DELTA_MIN)], "A_families": fams, "A_positive": pos,
            "A_valid": len(a) >= MIN_A and len(fams) >= MIN_FAMILIES and len(pos) >= MIN_POSITIVE,
            "wl_data_loss": [n for n in designs + [ROLL] if diffs.get(n, {}).get("data_loss")],
            "sub_threshold_wide": [n for n in wide if n not in a and n not in b]}


def run_sets(t: dict, diffs: dict) -> dict:
    """§4.1/§5.2: V2 = parent + A + B + eligible support designs; V3 = parent + A; flow_48 = parent + B + the largest positive and the largest
    negative tier-A design (by flow_32 Delta_bar)."""
    a = sorted(t["A"], key=lambda n: diffs[n]["downforce"]["delta_bar_n"])
    ctrl = [x for x in (a[-1] if a and diffs[a[-1]]["downforce"]["delta_bar_n"] > 0 else None,
                        a[0] if a and diffs[a[0]]["downforce"]["delta_bar_n"] < 0 else None) if x]
    return {"V2": [PARENT, *t["A"], *t["B"], *t["support"]], "V3": [PARENT, *t["A"]], "flow_48": [PARENT, *t["B"], *ctrl]}


# ---- OpenFOAM ---------------------------------------------------------------------------------------------------------------------------------------
def of_values(of_dirs, accepted=None):
    """level -> {(state, tag): {downforce, drag}} over valid cases (§5.4), plus per-kernel records.  `accepted` = the frozen set of criteria SHA-256;
    every accepted criteria file must be covered exactly once and nothing else may be given (C8)."""
    vals, recs, seen = {}, {}, set()
    for d in of_dirs:
        res = SC.jload(Path(d) / "openfoam_xfid_gridphase_x3/result.json")
        crit_path = next((p for p in (EVID / "of/criteria").glob("*.json") if SC.sha256_path(p) == res["criteria_sha256"]), None)
        SC.req(crit_path is not None, f"{d}: result belongs to no registered FID-01 criteria")
        SC.req(res["criteria_sha256"] not in seen, f"{d}: a second output of the same criteria (the first valid output is authoritative)")
        seen.add(res["criteria_sha256"])
        crit = SC.jload(crit_path)
        SC.req(crit["registered_before_run"], f"{crit_path.name}: development smoke criteria")
        lr = SC.jload(Path(d) / "local_run.json") if (Path(d) / "local_run.json").exists() else None
        SC.req(lr is not None and lr.get("returncode") == 0 and lr.get("dpkg_after_matches_lock") is True, f"{d}: invalid local run record (INFRA_LOSS)")
        lev, cases, counts = crit["level"], {c["id"]: c for c in res["cases"]}, {}
        for spec in crit["case_order"]:
            c = cases.get(spec["id"], {"status": "MISSING"})
            ok = c.get("status") == "COMPLETED" and (c.get("solver") or {}).get("converged_in") is not None
            key = "valid" if ok else ("NOT_CONVERGED" if c.get("status") == "COMPLETED" else c.get("status", "MISSING"))
            counts[key] = counts.get(key, 0) + 1
            if ok:
                k = (spec["state"], spec["id"].rsplit("_", 1)[1])
                SC.req(k not in vals.setdefault(lev, {}), f"duplicate OpenFOAM case {lev} {k}")
                vals[lev][k] = {r: c["forces"][f"{r}_n"]["window_mean"] for r in RESP}
        recs[crit_path.stem] = {"level": lev, "criteria_sha256": res["criteria_sha256"], "case_counts": counts}
    if accepted is not None:
        SC.req(seen == set(accepted), f"OpenFOAM outputs {sorted(seen)} differ from the frozen criteria set {sorted(accepted)}")
    return vals, recs


def pairs_of(val: dict, state: str, ref: str = PARENT) -> list[int]:
    """Halton pairs where the state and the reference are valid at both mirror shifts (whole pairs, per design; §5.4)."""
    idx = sorted({int(t[:-1]) for (s, t) in val if s == state})
    return [i for i in idx if all((x, f"{i}{m}") in val for x in (state, ref) for m in "pm")]


def level_stats(vals: dict, states: list[str], ref: str = PARENT) -> dict:
    """Per level and design, matched-shift differences.  V1: mirror-pair means, the M2 estimator (SE from the design's own pair means).
    V2: mirror-pair means, SE = sigma_pair / sqrt(n_pairs) with sigma_pair pooled over the designs' pair means.  V3 (one shift, 49 +): the mean over the
    design's matched shifts; its SE is set by `g3_set` from the residual SD of the tier-A V3-on-V1 regression (§6.1)."""
    out = {}
    for lev, val in vals.items():
        e = {}
        for s in states:
            if s == ref or not any(x == s for (x, _) in val):
                continue
            if lev == "V3":
                tags = sorted(t for (x, t) in val if x == s and (ref, t) in val)
                pr = None
            else:
                pr = pairs_of(val, s, ref)
                tags = [f"{i}{m}" for i in pr for m in "pm"]
            e[s] = {}
            for r in RESP:
                per = {t: val[(s, t)][r] - val[(ref, t)][r] for t in tags}
                units = [(per[f"{i}p"] + per[f"{i}m"]) / 2 for i in pr] if pr is not None else list(per.values())
                e[s][r] = {"pairs": pr, "shifts": tags, "per_shift_n": per, "units_n": units, "n": len(units),
                           "delta_bar_n": sum(units) / len(units) if units else None, "se_n": None}
                if lev == "V1" and len(pr) >= 2:
                    e[s][r].update(A.pair_stats(per, pr))
        if lev == "V2":
            for r in RESP:
                ss = sum((x - v[r]["delta_bar_n"]) ** 2 for v in e.values() if v[r]["n"] >= 2 for x in v[r]["units_n"])
                dof = sum(v[r]["n"] - 1 for v in e.values() if v[r]["n"] >= 2)
                sig = math.sqrt(ss / dof) if dof else None
                for v in e.values():
                    v[r].update(sigma_pool_n=sig, pool_dof=dof, se_n=sig / math.sqrt(v[r]["n"]) if sig is not None and v[r]["n"] else None)
        out[lev] = e
    return out


# ---- per-design rules --------------------------------------------------------------------------------------------------------------------------
def worst(*xs):
    for x in ("FAIL", "UNRESOLVED_DATA", "UNRESOLVED_STAT"):
        if x in xs:
            return x
    return "PASS"


def lev_value(ofs, lev, n, r="downforce", need_se=True):
    v = ofs.get(lev, {}).get(n, {}).get(r)
    return v if v is not None and v["n"] >= MIN_UNITS[lev] and (v.get("se_n") is not None or not need_se) else None


def ratio_rule(num, se_num, den, se_den, dof):
    """rho = num / den against RHO_BAND (§6.3 G4, G5b).  With s = sign(den) and t = t_0.95(dof): FAIL if the OpenFOAM upper bound lies below 0.5 x the
    WaterLily lower bound (s num + t se_num < 0.5 (|den| - t se_den); this covers a resolved opposite sign) or the OpenFOAM lower bound above 2 x the
    WaterLily upper bound; PASS if the point rho is in the band; else UNRESOLVED_STAT.  The M2 interval on |rho| is reported when rho > 0."""
    t, s = A.tq(0.95, max(dof, 1)), (1.0 if den > 0 else -1.0)
    rho = num / den
    if s * num + t * se_num < RHO_BAND[0] * (abs(den) - t * se_den) or s * num - t * se_num > RHO_BAND[1] * (abs(den) + t * se_den):
        lab = "FAIL"
    else:
        lab = "PASS" if RHO_BAND[0] <= rho <= RHO_BAND[1] else "UNRESOLVED_STAT"
    w = t * math.hypot(se_num / num, se_den / den) if rho > 0 else None
    return lab, rho, ([rho * math.exp(-w), rho * math.exp(w)] if w is not None else None)


def g_rules(n, wl, ofs, levels, exp_rec):
    """§6.3 for one design: G1-G5 with PASS / FAIL (resolved) / UNRESOLVED_STAT / UNRESOLVED_DATA."""
    w = wl[n]["downforce"]
    s = 1.0 if w["delta_bar_n"] > 0 else -1.0
    x = {L: lev_value(ofs, L, n) for L in levels}
    g1 = {}
    for L, v in x.items():
        if v is None:
            g1[L] = "UNRESOLVED_DATA"
        else:
            d = v["delta_bar_n"]
            g1[L] = "PASS" if d * s > 0 else "FAIL" if abs(d) > 2 * v["se_n"] else "UNRESOLVED_STAT"
    v1, v2 = x.get("V1"), x.get("V2")
    G2 = "UNRESOLVED_DATA" if v1 is None else "PASS" if s * v1["delta_bar_n"] > 3 * v1["se_n"] else "UNRESOLVED_STAT"
    if v1 is None or v2 is None:
        G3, g3 = "UNRESOLVED_DATA", {}
    else:
        m, R = (v1["delta_bar_n"] + v2["delta_bar_n"]) / 2, abs(v1["delta_bar_n"] - v2["delta_bar_n"])
        sr, tol = math.hypot(v1["se_n"], v2["se_n"]), SPREAD_MAX * abs(m)
        G3 = "PASS" if R <= tol else "FAIL" if R - 2 * sr > tol else "UNRESOLVED_STAT"
        g3 = {"mean_n": m, "range_n": R, "tolerance_n": tol, "se_range_n": sr}
    if v1 is None:
        G4, g4 = "UNRESOLVED_DATA", {}
    else:
        G4, rho, iv = ratio_rule(v1["delta_bar_n"], v1["se_n"], w["delta_bar_n"], w["se_eff_n"], min(w["P"], v1["n"]) - 1)
        g4 = {"rho_V1": rho, "rho_V1_90": iv, **{f"rho_{L}": v["delta_bar_n"] / w["delta_bar_n"] for L, v in x.items() if v is not None}}
    geo = {"x1_pass": bool(exp_rec["pass"]), "stl_volume_band": abs(exp_rec["stl_volume_vs_parent"]) <= VOLUME_BAND,
           "stl_vs_sdf_volume_chain": abs(exp_rec["stl_volume_vs_parent"] - exp_rec["sdf_smoothed_volume_vs_parent"]) <= CHAIN_TOL}
    wd, od = wl[n]["drag"], lev_value(ofs, "V1", n, "drag")
    if not all(geo.values()):
        G5, g5b = "FAIL", "not evaluated"
    elif abs(wd["delta_bar_n"]) < DRAG_MIN or abs(wd["delta_bar_n"]) <= 3 * wd["se_eff_n"]:
        G5, g5b = "PASS", "drag change below the tested size (reported)"
    elif od is None:
        G5, g5b = "UNRESOLVED_DATA", None
    else:
        G5, rho_d, iv_d = ratio_rule(od["delta_bar_n"], od["se_n"], wd["delta_bar_n"], wd["se_eff_n"], min(wd["P"], od["n"]) - 1)
        g5b = {"rho_drag_V1": rho_d, "rho_drag_V1_90": iv_d}
    rules = {"G1": worst(*g1.values()), "G2": G2, "G3": G3, "G4": G4, "G5": G5}
    return {"sign_wl": s, "rules": rules, "status": worst(*rules.values()), "G1_levels": g1, "G3": g3, "G4": g4, "G5": {"geometry": geo, "drag": g5b},
            "of_levels": {L: {"delta_bar_n": v["delta_bar_n"], "se_n": v["se_n"]} for L, v in x.items() if v is not None}}


def g3_set(names, ofs):
    """§6.3 G3-set (tier A, V3): slope b of Delta_V3 on Delta_V1 through the origin; PASS if b in V3_SLOPE_BAND, FAIL if its 90 % interval lies outside.
    The V3 standard error of design i is the leave-one-out residual SD of that fit (noise plus design-to-design spread, dof n - 2) / sqrt(n_shifts) (§6.1)."""
    pts = {n: (lev_value(ofs, "V1", n)["delta_bar_n"], lev_value(ofs, "V3", n, need_se=False)["delta_bar_n"]) for n in names
           if lev_value(ofs, "V1", n) is not None and lev_value(ofs, "V3", n, need_se=False) is not None}
    if len(pts) < 3:
        return {"label": "UNRESOLVED_DATA", "n": len(pts)}
    xy = list(pts.values())
    sxx = sum(a * a for a, _ in xy)
    b = sum(a * c for a, c in xy) / sxx
    sr = math.sqrt(sum((c - b * a) ** 2 for a, c in xy) / (len(xy) - 1))
    se, t = sr / math.sqrt(sxx), A.tq(0.95, len(xy) - 1)
    iv = [b - t * se, b + t * se]
    lab = "PASS" if V3_SLOPE_BAND[0] <= b <= V3_SLOPE_BAND[1] else "FAIL" if iv[1] < V3_SLOPE_BAND[0] or iv[0] > V3_SLOPE_BAND[1] else "UNRESOLVED_STAT"
    loo = {}
    for n in pts:   # leave-one-out residual SD: a design's own departure cannot inflate its standard error
        rest = [v for m, v in pts.items() if m != n]
        bb = sum(a * c for a, c in rest) / sum(a * a for a, _ in rest)
        loo[n] = math.sqrt(sum((c - bb * a) ** 2 for a, c in rest) / max(len(rest) - 1, 1))
        v3 = ofs["V3"][n]["downforce"]
        v3["se_n"] = loo[n] / math.sqrt(v3["n"])
    return {"label": lab, "slope": b, "slope_90": iv, "residual_sd_n": sr, "loo_residual_sd_n": loo, "n": len(xy), "designs": sorted(pts)}


# ---- outcome ----------------------------------------------------------------------------------------------------------------------------------------
def nc(wl, ofs):
    """§6.6: the roll against M2's measured values; WaterLily SE floored at 3e-4 / sqrt(P); OpenFOAM needs >= 12 pairs; |z| <= 3.5."""
    out = {}
    w = wl.get(ROLL, {}).get("downforce")
    if w is None:
        out["wl"] = {"label": "MISSING"}
    else:
        se = max(w["sigma_d_n"], NC_FLOOR) / math.sqrt(w["P"])
        z = abs(w["delta_bar_n"] - NC_REF["wl"][0]) / math.hypot(se, NC_REF["wl"][1])
        out["wl"] = {"label": "CONSISTENT" if z <= NC_Z else "INCONSISTENT", "delta_bar_n": w["delta_bar_n"], "se_n": se, "z": z}
    o = ofs.get("V1", {}).get(ROLL, {}).get("downforce")
    if o is None or o["n"] < NC_MIN_PAIRS:
        out["of"] = {"label": "MISSING", "pairs": 0 if o is None else o["n"]}
    else:
        z = abs(o["delta_bar_n"] - NC_REF["of"][0]) / math.hypot(o["se_n"], NC_REF["of"][1])
        out["of"] = {"label": "CONSISTENT" if z <= NC_Z else "INCONSISTENT", "delta_bar_n": o["delta_bar_n"], "se_n": o["se_n"], "z": z}
    out["consistent"] = all(out[k]["label"] == "CONSISTENT" for k in ("wl", "of"))
    return out


def cause(per, names, g3s):
    """§8: WL_OF if a tier-A design fails G1 on V1, G4 or G5; else OF_MESH (G1 on V2/V3, G3 or G3-set)."""
    wl_of = any(per[n]["G1_levels"].get("V1") == "FAIL" or per[n]["rules"]["G4"] == "FAIL" or per[n]["rules"]["G5"] == "FAIL" for n in names)
    return "WL_OF" if wl_of else "OF_MESH"


def decide(t, per, g3s, extension_done=False):
    """§6.7 steps 3-7 on tier A."""
    if not t["A_valid"]:
        return "FID01_INCONCLUSIVE_DESIGN_SET", None
    st = [per[n]["status"] for n in t["A"]] + [g3s["label"]]
    if "FAIL" in st:
        return "FID01_NO_GO", cause(per, t["A"], g3s)
    if all(x == "PASS" for x in st):
        return "FID01_GO", None
    if "UNRESOLVED_STAT" in [per[n]["status"] for n in t["A"]] and not extension_done:
        return "EXTENSION_REQUIRED", None
    return ("FID01_INCONCLUSIVE_PRECISION" if "UNRESOLVED_STAT" in st else "FID01_INCOMPLETE"), None


def m3b_min_gain(t, per, wl):
    """§8: the validated range [x*, inf): x* = the smallest |Delta_WL| of a PASSing design (A or B) above every non-PASSing tier-B design."""
    size = lambda n: abs(wl[n]["downforce"]["delta_bar_n"])  # noqa: E731
    bad = max((size(n) for n in t["B"] if per[n]["status"] != "PASS"), default=0.0)
    ok = [size(n) for n in t["A"] + t["B"] if per[n]["status"] == "PASS" and size(n) > bad]
    if not ok:
        return {"x_star_n": None, "min_gain_relative": None}
    x = min(ok)
    return {"x_star_n": x, "largest_non_passing_tier_B_n": bad, "min_gain_relative": max(2 * S_D, x / J_B48), "paired_E2_floor": 2 * S_D}


def evaluate(states_rec, wl, vals, export_rec, levels=("V1", "V2", "V3"), wl48=None, wl32_k7=None):
    """The whole §6 on loaded data.  wl: wl_diffs of flow_32; wl48: {state: {resp: value}} at k7; wl32_k7: same for flow_32 at k7."""
    t = tiers(wl, states_rec)
    designs = [n for n, r in states_rec.items() if r.get("slot")]
    ofs = level_stats(vals, [PARENT, *designs, ROLL])
    out = {"tiers": t, "levels": list(levels)}
    invalid = []
    if any(PARENT not in {s for s, _ in vals.get(L, {})} for L in levels):
        invalid.append("a level without any parent case")
    for L in levels:
        n = len({t for (s, t) in vals.get(L, {}) if s == PARENT}) if L == "V3" else len(pairs_of(vals.get(L, {}), PARENT, PARENT))
        if n < MIN_UNITS[L]:
            invalid.append(f"{L}: parent has {n} valid {'shifts' if L == 'V3' else 'pairs'} < {MIN_UNITS[L]}")
    out["minimum_data"] = {"pass": not invalid, "failures": invalid}
    ncr = nc(wl, ofs)
    out["NC"] = ncr
    judged = t["A"] + t["B"] + t["support"]
    g3s = g3_set(t["A"], ofs) if "V3" in levels else {"label": "PASS", "note": "V3 removed (V3_NOT_CONVERGED); G3-set not applied"}
    per = {n: g_rules(n, wl, ofs, [L for L in levels if n in t["A"] or L != "V3"], export_rec[f"{n}|r8"]) for n in judged}
    out.update(per_design=per, G3_set=g3s)
    if invalid:
        out["outcome"], out["cause"] = "FID01_INVALID", "minimum data"
    elif not ncr["consistent"]:
        out["outcome"], out["cause"] = "FID01_INVALID", "negative control"
    else:
        out["outcome"], out["cause"] = decide(t, per, g3s)
    out["extension_plan"] = extension_plan(per, t["A"]) if out["outcome"] == "EXTENSION_REQUIRED" else None
    out["m3b_min_gain"] = m3b_min_gain(t, per, wl) if out["outcome"] == "FID01_GO" else None
    out.update(secondary(states_rec, t, per, wl, ofs, vals, wl48, wl32_k7))
    return out, ofs


def extension_plan(per, names):
    """§6.8: level -> tier-A designs whose UNRESOLVED_STAT involves that level."""
    plan = {}
    for n in names:
        p = per[n]
        if p["status"] != "UNRESOLVED_STAT":
            continue
        levs = {L for L, v in p["G1_levels"].items() if v == "UNRESOLVED_STAT"}
        if p["rules"]["G3"] == "UNRESOLVED_STAT":
            levs |= {"V1", "V2"}
        if "UNRESOLVED_STAT" in (p["rules"]["G2"], p["rules"]["G4"], p["rules"]["G5"]):
            levs.add("V1")
        for L in sorted(levs):
            plan.setdefault(L, []).append(n)
    return plan


def extension_eval(main, states_rec, wl, vals, export_rec):
    """§6.8: the plan's designs recomputed once with every shift; remaining UNRESOLVED stays unresolved (no FAIL by default)."""
    t, levels = main["tiers"], main["levels"]
    designs = [n for n, r in states_rec.items() if r.get("slot")]
    ofs = level_stats(vals, [PARENT, *designs, ROLL])
    if "V3" in levels:
        g3_set(t["A"], ofs)   # V3 standard errors from the (unchanged-rule) residual SD with every shift; the G3-set label stays the main one
    per = dict(main["per_design"])
    redo = sorted({n for ns in main["extension_plan"].values() for n in ns})
    for n in redo:
        per[n] = {**g_rules(n, wl, ofs, levels, export_rec[f"{n}|r8"]), "extension": True}
    outcome, why = decide(t, per, main["G3_set"], extension_done=True)
    return {"recomputed": redo, "per_design": per, "outcome": outcome, "cause": why, "of": ofs,
            "m3b_min_gain": m3b_min_gain(t, per, wl) if outcome == "FID01_GO" else None}


# ---- secondary labels (§6.4-§6.6, §6.9) --------------------------------------------------------------------------------------------------------
def secondary(states_rec, t, per, wl, ofs, vals, wl48, wl32_k7):
    out = {}
    sup = t["support"]
    st = [per[n]["status"] for n in sup]
    out["support_label"] = ("SUPPORT_UNTESTABLE" if not sup else "SUPPORT_FAIL" if "FAIL" in st else "SUPPORT_PASS" if all(x == "PASS" for x in st)
                            else "SUPPORT_UNRESOLVED")
    stb = [per[n]["status"] for n in t["B"]]
    out["tier_B_label"] = ("TIER_B_EMPTY" if not stb else "TIER_B_FAIL" if "FAIL" in stb else "TIER_B_PASS" if all(x == "PASS" for x in stb) else "TIER_B_UNRESOLVED")
    out["R3"] = r3_labels(wl48, wl32_k7, [n for n in (wl48 or {}) if n != PARENT])
    out["EX"] = ex_labels(vals, [n for n, r in states_rec.items() if r.get("slot") in ("W4", "W6")])
    heave = [n for n in t["A"] + t["B"] if "heave" in (states_rec[n].get("spec") or {})]
    out["heave_sublabel"] = {n: per[n]["status"] for n in heave}
    dplus = [n for n in t["A"] if wl[n]["downforce"]["delta_bar_n"] > 0]
    out["improvement_only"] = {n: per[n]["status"] for n in dplus}
    pts = {n: (wl[n]["downforce"]["delta_bar_n"], lev_value(ofs, "V1", n)["delta_bar_n"]) for n in t["A"] + t["B"] + t["support"] if lev_value(ofs, "V1", n)}
    xy = list(pts.values())
    out["aggregate"] = {"slope_V1_on_WL_through_origin": (sum(a * b for a, b in xy) / sum(a * a for a, _ in xy)) if xy else None,
                        "kendall_tau_all": kendall(xy), "kendall_tau_tier_A_positive": kendall([pts[n] for n in dplus if n in pts])}
    terms = [abs(lev_value(ofs, "V3", n, need_se=False)["delta_bar_n"] - lev_value(ofs, "V2", n)["delta_bar_n"]) for n in t["A"]
             if lev_value(ofs, "V2", n) and lev_value(ofs, "V3", n, need_se=False)]
    pv3 = parent_mean(vals, "V3")
    out["S_d_OF"] = statistics.median(terms) / pv3 if terms and pv3 else None   # §8: median over tier A of |Delta_V3 - Delta_V2| / |F_parent,V3|
    return out


def parent_mean(vals, lev, r="downforce"):
    xs = [v[r] for (s, _), v in vals.get(lev, {}).items() if s == PARENT]
    return abs(sum(xs) / len(xs)) if xs else None


def kendall(pts):
    n = len(pts)
    if n < 3:
        return None
    c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (pts[i][0] - pts[j][0]) * (pts[i][1] - pts[j][1])
            c, d = c + (s > 0), d + (s < 0)
    return (c - d) / (n * (n - 1) / 2)


def r3_labels(wl48, wl32_k7, names):
    """§6.5: same-phase comparison at k7: Delta_48(k7) vs Delta_32(k7)."""
    if not wl48:
        return {"label": "NOT_MEASURED", "consequence": "M3b confirms every candidate on flow_48 with P >= 2"}
    out = {}
    for n in names:
        d48 = wl48[n]["downforce"] - wl48[PARENT]["downforce"]
        d32 = wl32_k7[n]["downforce"] - wl32_k7[PARENT]["downforce"]
        lab = "R3_CONFIRMED" if d48 * d32 > 0 else "R3_CONTRADICTED" if abs(d48) > 2 * FLOOR["downforce"] * math.sqrt(2) else "R3_UNRESOLVED"
        out[n] = {"label": lab, "delta_48_k7_n": d48, "delta_32_k7_n": d32, "ratio": d48 / d32 if d32 else None, "E2_exceeded": abs(d48 - d32) > DELTA_MIN}
    return {"designs": out, "R3_CHALLENGED": any(v["label"] == "R3_CONTRADICTED" for v in out.values()),
            "R3_E2_EXCEEDED": any(v["E2_exceeded"] for v in out.values())}


def ex_labels(vals, names):
    """§6.6 EX on V1: the paired change of the difference between r = 16 and r = 8 exports, by mirror pairs; three labels."""
    v1 = vals.get("V1", {})
    out = {}
    for n in names:
        r16, p16 = f"{n}__r{EX_R}", f"{PARENT}__r{EX_R}"
        pr = [i for i in pairs_of(v1, n) if all((x, f"{i}{m}") in v1 for x in (r16, p16) for m in "pm")]
        if len(pr) < 2:
            out[n] = {"label": "NOT_MEASURED", "pairs": len(pr)}
            continue
        u = [sum((v1[(r16, f"{i}{m}")]["downforce"] - v1[(p16, f"{i}{m}")]["downforce"]) - (v1[(n, f"{i}{m}")]["downforce"] - v1[(PARENT, f"{i}{m}")]["downforce"])
                 for m in "pm") / 2 for i in pr]
        d8 = [sum(v1[(n, f"{i}{m}")]["downforce"] - v1[(PARENT, f"{i}{m}")]["downforce"] for m in "pm") / 2 for i in pr]
        st = A.stats(u)
        ref = 0.1 * abs(sum(d8) / len(d8))
        m, se = abs(st["delta_bar_n"]), st["se_n"]
        lab = "EXPORT_SENSITIVE" if m - 2 * se > ref else "EXPORT_INSENSITIVE" if m + 2 * se <= ref else "EXPORT_UNRESOLVED"
        out[n] = {"label": lab, "delta_EX_n": st["delta_bar_n"], "se_n": se, "tolerance_n": ref, "minimum_detectable_n": 2 * se, "pairs": len(pr),
                  "parent_absolute_change_n": sum(v1[(p16, f"{i}{x}")]["downforce"] - v1[(PARENT, f"{i}{x}")]["downforce"] for i in pr for x in "pm") / (2 * len(pr))}
    return out


# ---- I/O --------------------------------------------------------------------------------------------------------------------------------------------
def dset(campaign, tables, kernel_root):
    states_rec = SC.jload(EVID / "states.json")["states"]
    c = SC.jload(campaign)
    SC.req(c["campaign_id"] == "fid01", "dset needs the flow_32 campaign")
    diffs = wl_diffs(wl_load(campaign, tables, kernel_root, "fid01"))
    SC.req(set(diffs) | {PARENT} == set(states_rec), "flow_32 states differ from states.json")
    t = tiers(diffs, states_rec)
    return {"kind": "fid01_d_set", "registration": "docs/fid01_registration_2026_10_21.md §6.2", "analyzer_sha256": SC.sha256_path(__file__),
            "campaign_sha256": SC.sha256_path(campaign), "table_sha256": {Path(x).name: SC.sha256_path(x) for x in tables},
            "tiers": t, "run_sets": run_sets(t, diffs), "wl_flow32": diffs, "coefficients": coefficients()}


def frozen_criteria():
    acc = []
    for f in ("freeze2.json", "freeze3.json"):
        p = EVID / f
        if p.exists():
            acc += SC.jload(p).get("of_criteria_sha256", [])
    return acc or None


def main_analysis(a):
    states_rec = SC.jload(EVID / "states.json")["states"]
    export = SC.jload(EVID / "of/export.json")
    SC.req(export["states_sha256"] == SC.sha256_path(EVID / "states.json"), "export.json does not belong to states.json")
    ds = SC.jload(a.dset)
    f32 = wl_load(a.campaign, a.tables, a.kernel_root, "fid01")
    wl = wl_diffs(f32)
    SC.req(tiers(wl, states_rec) == ds["tiers"], "d_set.json does not re-derive from the flow_32 tables")
    wl48 = None
    if a.campaign48:
        f48 = wl_load(a.campaign48, a.tables48, a.kernel_root, "fid01_f48")
        wl48 = {s: f["k7"] for s, f in f48.items() if "k7" in f}
    vals, recs = of_values(a.of, frozen_criteria())
    levels = SC.jload(EVID / "freeze2.json").get("of_levels", ["V1", "V2", "V3"]) if (EVID / "freeze2.json").exists() else ["V1", "V2", "V3"]
    res, ofs = evaluate(states_rec, wl, vals, export["exports"], tuple(levels), wl48, {s: f["k7"] for s, f in f32.items() if "k7" in f})
    return {"kind": "fid01_analysis", "registration": "docs/fid01_registration_2026_10_21.md", "analyzer_sha256": SC.sha256_path(__file__),
            "dset_sha256": SC.sha256_path(a.dset), "coefficients": coefficients(), "wl_flow32": wl, "wl_flow48_k7": wl48, "of": ofs, "of_kernels": recs, **res,
            "qualification_flags": "all false (unchanged)", "shape_update_allowed": False}


def extension_analysis(a):
    main = SC.jload(a.main)
    SC.req(main["outcome"] == "EXTENSION_REQUIRED", "the main analysis did not require the extension")
    states_rec = SC.jload(EVID / "states.json")["states"]
    export = SC.jload(EVID / "of/export.json")["exports"]
    wl = wl_diffs(wl_load(a.campaign, a.tables, a.kernel_root, "fid01"))
    vals, recs = of_values(a.of, None)
    return {"kind": "fid01_extension_analysis", "main_sha256": SC.sha256_path(a.main), "analyzer_sha256": SC.sha256_path(__file__),
            **extension_eval(main, states_rec, wl, vals, export), "of_kernels": recs}


def budget(finished, f48_estimate_s):
    walls = {k: A.log_wall(p) for k, p in (x.split("=", 1) for x in finished)}
    T = sum(walls.values()) + f48_estimate_s
    return {"kind": "fid01_budget_decision", "finished_session_wall_s": walls, "f48_estimate_s": f48_estimate_s, "T_s": T, "cap_s": WL_CAP_S,
            "push_f48": T <= WL_CAP_S, "logs_sha256": {x.split("=", 1)[0]: SC.sha256_path(x.split("=", 1)[1]) for x in finished}, "rule": "registration §4.3"}


def write_once(path, obj):
    with Path(path).open("x") as f:
        f.write(json.dumps(A.clean(obj), indent=1, sort_keys=True, allow_nan=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["dset", "budget", "main", "extension"])
    ap.add_argument("--campaign", type=Path)
    ap.add_argument("--tables", nargs="*", type=Path, default=[])
    ap.add_argument("--campaign48", type=Path)
    ap.add_argument("--tables48", nargs="*", type=Path, default=[])
    ap.add_argument("--kernel-root", type=Path)
    ap.add_argument("--dset", type=Path)
    ap.add_argument("--of", nargs="*", type=Path, default=[])
    ap.add_argument("--main", type=Path)
    ap.add_argument("--finished", nargs="*", default=[])
    ap.add_argument("--f48-estimate", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "budget":
        res = budget(a.finished, a.f48_estimate)
    elif a.cmd == "dset":
        res = dset(a.campaign, a.tables, a.kernel_root)
    elif a.cmd == "main":
        res = main_analysis(a)
    else:
        res = extension_analysis(a)
    write_once(a.out, res)
    print(res.get("outcome", res.get("kind")))


if __name__ == "__main__":
    main()
