#!/usr/bin/env python3
"""FID-01 (#62, M3a) analysis: the rules of docs/fid01_registration_2026_10_21.md §6 (that text governs; a disagreement is a defect here).

    analyze_fid01.py budget --finished KERNEL=LOG... --pending KERNEL... [--out J]        # §4.3 flow_48 push decision from session times only
    analyze_fid01.py main --campaign C --tables T... --kernel-root D --of OF_DIR... --out J   # written once
    analyze_fid01.py extension --main J --campaign C --tables T... --kernel-root D --of OF_DIR... --out J2   # §6.8, written once

OF_DIR: a local OpenFOAM output directory (`<out>/openfoam_xfid_gridphase_x3/result.json`) of a FID-01 OpenFOAM kernel; its criteria are the
tracked file docs/evidence/fid01_2026_10_21/of/criteria/<kernel>.json whose SHA-256 the result records.
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
DELTA_MIN, DELTA_MIN_LIT = 2 * S_D * J_B48, 2 * max(S_B, S_C) * J_B48
FLOOR = {"downforce": 0.00020904201605451784, "drag": 0.000136408347135453}
NC_REF = {"wl": (-0.0016476407624087992, 8.534104568937632e-05), "of": (-0.0006614761397334482, 5.792182318004298e-05)}
RHO_BAND = (0.5, 2.0)
SPREAD_MAX = 0.5
MIN_D, MIN_FAMILIES, MIN_POSITIVE = 8, 3, 3
WIDE_FAMILIES = ("rigid", "section", "span", "combination")
MIN_SHIFTS = {"V1": 24, "V2": 2, "V3": 1}
MIN_WL_P = 3
F48_CAP_S = 79200
EST_S = {"flow_32": 415, "flow_48": 2340}
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
    SC.req(SC.sha256_path(path).startswith(M2_ANALYSIS_SHA) and got == {k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in want.items()},
           "M2 coefficients differ from the registered values")
    return {"m2_analysis_sha256": SC.sha256_path(path), **got, "delta_min_n": DELTA_MIN, "delta_min_literal_n": DELTA_MIN_LIT}


# ---- WaterLily --------------------------------------------------------------------------------------------------------------------------------------
def wl(campaign_path, tables, kernel_root):
    """flow_32 paired statistics (P = phases present for every state) and flow_48 single-phase differences."""
    c, rows, kernels = A.load_rows(campaign_path, tables, campaign_id="fid01")
    out = {}
    for g in ("flow_32", "flow_48"):
        runs = [r for k, kern in c["kernels"].items() if kern["case"]["case_id"] == g for r in kern["runs"]]
        states = list(dict.fromkeys(r["state"] for r in runs))
        tags = sorted({r["name"].rsplit("__", 1)[1] for r in runs}, key=lambda t: int(t[1:]))
        full = [t for t in tags if all((g, s, t) in rows for s in states)]
        e = {"states": states, "phases_registered": tags, "phases_used": full, "P": len(full), "kernels_verified": sorted(k for k in kernels if c["kernels"][k]["case"]["case_id"] == g)}
        if full:
            for t in full:
                for s in states:
                    if kernel_root is not None:
                        A.run_files(c, kernel_root, rows[(g, s, t)])   # every file read was hashed by the verified table
            e.update(wl_stats({s: {r: [rows[(g, s, t)][r] for t in full] for r in RESP} for s in states}))
        out[g] = e
    return c, out


def wl_stats(forces: dict) -> dict:
    """forces: state -> response -> per-phase values (same phases for every state).  Paired differences vs the parent (§6.1)."""
    out = {"parent_n": forces[PARENT], "differences": {}}
    for s, f in forces.items():
        if s == PARENT:
            continue
        out["differences"][s] = {}
        for r in RESP:
            d = [a - b for a, b in zip(f[r], forces[PARENT][r])]
            if len(d) >= 2:
                st = A.stats(d)
                st["se_eff_n"] = max(st["sigma_d_n"], FLOOR[r]) / math.sqrt(len(d))
            else:
                st = {"P": len(d), "deltas_n": d, "delta_bar_n": d[0], "sigma_d_n": None, "se_n": None, "se_eff_n": None}
            out["differences"][s][r] = st
    return out


# ---- OpenFOAM ---------------------------------------------------------------------------------------------------------------------------------------
def of_values(of_dirs):
    """level -> {(state, tag): {downforce, drag}} over valid cases (§5.4), plus per-kernel records."""
    vals, recs = {}, {}
    for d in of_dirs:
        res = SC.jload(Path(d) / "openfoam_xfid_gridphase_x3/result.json")
        crit_path = next((p for p in (EVID / "of/criteria").glob("*.json") if SC.sha256_path(p) == res["criteria_sha256"]), None)
        SC.req(crit_path is not None, f"{d}: result belongs to no registered FID-01 criteria")
        crit = SC.jload(crit_path)
        SC.req(crit["registered_before_run"], f"{crit_path.name}: development smoke criteria")
        local = Path(d) / "local_run.json"
        lr = SC.jload(local) if local.exists() else None
        SC.req(lr is not None and lr.get("returncode") == 0 and lr.get("dpkg_after_matches_lock") is True, f"{d}: invalid local run record (INFRA_LOSS)")
        lev = crit["level"]
        cases = {c["id"]: c for c in res["cases"]}
        counts = {}
        for spec in crit["case_order"]:
            c = cases.get(spec["id"], {"status": "MISSING"})
            ok = c.get("status") == "COMPLETED" and (c.get("solver") or {}).get("converged_in") is not None
            counts["valid" if ok else c.get("status", "MISSING") if c.get("status") != "COMPLETED" else "NOT_CONVERGED"] = \
                counts.get("valid" if ok else c.get("status", "MISSING") if c.get("status") != "COMPLETED" else "NOT_CONVERGED", 0) + 1
            if ok:
                key = (spec["state"], spec["id"].rsplit("_", 1)[1])
                SC.req(key not in vals.setdefault(lev, {}), f"duplicate OpenFOAM case {lev} {key}")
                vals[lev][key] = {r: c["forces"][f"{r}_n"]["window_mean"] for r in RESP}
        recs[crit_path.stem] = {"level": lev, "criteria_sha256": res["criteria_sha256"], "case_counts": counts}
    return vals, recs


def pairs_of(val: dict, state: str, ref: str = PARENT) -> list[int]:
    """Halton pairs where the state and the reference are valid at both mirror shifts (matched whole pairs, per design; §5.4)."""
    idx = sorted({int(t[:-1]) for (s, t) in val if s == state})
    return [i for i in idx if all((x, f"{i}{m}") in val for x in (state, ref) for m in "pm")]


def level_stats(vals: dict, states: list[str], ref: str = PARENT) -> dict:
    """Per level and state: matched-shift differences.  V1 by mirror-pair means (M2 estimator); V2 and V3 by the mean over matched shifts with
    SE = sigma_pool,V2 / sqrt(n) (V2 pooled over every design; V3 has one shift and uses the V2 value as its proxy, §6.1)."""
    out = {}
    for lev, val in vals.items():
        e = {}
        for s in states:
            if s == ref:
                continue
            pr = pairs_of(val, s, ref) if lev == "V1" else None
            tags = [f"{i}{m}" for i in pr for m in "pm"] if lev == "V1" else sorted(t for (x, t) in val if x == s and (ref, t) in val)
            e[s] = {}
            for r in RESP:
                per = {t: val[(s, t)][r] - val[(ref, t)][r] for t in tags}
                e[s][r] = {"shifts": tags, "per_shift_n": per, "n_shifts": len(per), "pairs": pr}
                if lev == "V1" and len(pr) >= 2:
                    e[s][r].update(A.pair_stats(per, pr))
                elif lev != "V1" and per:
                    e[s][r]["delta_bar_n"] = sum(per.values()) / len(per)
        out[lev] = e
    for r in RESP:
        res, dof = 0.0, 0
        for v in out.get("V2", {}).values():
            if v[r]["n_shifts"] >= 2:
                res += sum((x - v[r]["delta_bar_n"]) ** 2 for x in v[r]["per_shift_n"].values())
                dof += v[r]["n_shifts"] - 1
        sig = math.sqrt(res / dof) if dof else None
        for lev in ("V2", "V3"):
            for v in out.get(lev, {}).values():
                v[r].update(sigma_pool_v2_n=sig, pool_dof=dof)
                if "delta_bar_n" in v[r]:
                    v[r]["se_n"] = sig / math.sqrt(v[r]["n_shifts"]) if sig is not None else None
    return out


# ---- rules ------------------------------------------------------------------------------------------------------------------------------------------
def worst(*xs):
    return "FAIL" if "FAIL" in xs else "UNRESOLVED" if "UNRESOLVED" in xs else "PASS"


def lev_ok(lev_stat, lev, r="downforce"):
    return lev_stat is not None and lev_stat[r]["n_shifts"] >= MIN_SHIFTS[lev] and lev_stat[r].get("se_n") is not None


def g_rules(wl32, ofs, design, exp_rec):
    """§6.3 for one design: G1-G5 with PASS / FAIL / UNRESOLVED."""
    w = wl32[design]["downforce"]
    s = 1.0 if w["delta_bar_n"] > 0 else -1.0
    lev = {L: (ofs.get(L, {}).get(design) if lev_ok(ofs.get(L, {}).get(design), L) else None) for L in ("V1", "V2", "V3")}
    x = {L: (v["downforce"]["delta_bar_n"], v["downforce"]["se_n"]) for L, v in lev.items() if v is not None}
    g1 = {}
    for L in ("V1", "V2", "V3"):
        if L not in x:
            g1[L] = "UNRESOLVED"
        else:
            d, se = x[L]
            g1[L] = "PASS" if (d > 0) == (s > 0) and d != 0 else "FAIL" if abs(d) > 2 * se else "UNRESOLVED"
    G1 = worst(*g1.values())
    G2 = "PASS" if "V1" in x and s * x["V1"][0] > 3 * x["V1"][1] else "FAIL" if "V1" in x else "UNRESOLVED"
    if len(x) == 3:
        vals = [x[L][0] for L in ("V1", "V2", "V3")]
        m, hi, lo = statistics.median(vals), max(vals), min(vals)
        Lhi, Llo = max(x, key=lambda L: x[L][0]), min(x, key=lambda L: x[L][0])
        R = hi - lo
        tol = SPREAD_MAX * abs(m)
        G3 = "PASS" if R <= tol else "FAIL" if R - 2 * math.hypot(x[Lhi][1], x[Llo][1]) > tol else "UNRESOLVED"
        g3 = {"median_n": m, "range_n": R, "tolerance_n": tol, "levels_max_min": [Lhi, Llo]}
    else:
        G3, g3 = "UNRESOLVED", {"missing_levels": [L for L in ("V1", "V2", "V3") if L not in x]}
    if "V1" in x:
        d, se = x["V1"]
        rho = d / w["delta_bar_n"]
        if rho <= 0:
            G4, iv = "FAIL", None
        else:
            t = A.tq(0.95, min(w["P"], len(lev["V1"]["downforce"]["pairs"])) - 1)
            wd = t * math.hypot(se / d, w["se_eff_n"] / w["delta_bar_n"])
            iv = [rho * math.exp(-wd), rho * math.exp(wd)]
            G4 = "PASS" if RHO_BAND[0] <= rho <= RHO_BAND[1] else "FAIL" if iv[1] < RHO_BAND[0] or iv[0] > RHO_BAND[1] else "UNRESOLVED"
        g4 = {"rho_V1": rho, "rho_V1_90": iv, **{f"rho_{L}": x[L][0] / w["delta_bar_n"] for L in x}}
    else:
        G4, g4 = "UNRESOLVED", {}
    g5a = bool(exp_rec["g5a_pass"])
    wd_, od = wl32[design]["drag"], (lev["V1"] or {}).get("drag")
    drag_conflict = (od is not None and abs(wd_["delta_bar_n"]) > 3 * wd_["se_eff_n"] and abs(od["delta_bar_n"]) > 3 * od["se_n"]
                     and (wd_["delta_bar_n"] > 0) != (od["delta_bar_n"] > 0))
    G5 = "FAIL" if not g5a or drag_conflict else "PASS"
    rules = {"G1": G1, "G2": G2, "G3": G3, "G4": G4, "G5": G5}
    return {"sign_wl": s, "rules": rules, "status": worst(*rules.values()), "G1_levels": g1, "G3": g3, "G4": g4,
            "G5": {"g5a_geometry": g5a, "drag_resolved_sign_conflict": drag_conflict}, "of_levels": {L: {"delta_bar_n": v[0], "se_n": v[1]} for L, v in x.items()}}


def decision_set(wl32, states_rec, threshold, names):
    """§6.2: wide designs with |Delta_bar| >= threshold and > 3 SE_eff (WaterLily only)."""
    D = [n for n in names if abs(wl32[n]["downforce"]["delta_bar_n"]) >= threshold and abs(wl32[n]["downforce"]["delta_bar_n"]) > 3 * wl32[n]["downforce"]["se_eff_n"]]
    fams = sorted({states_rec[n]["family"] for n in D})
    pos = [n for n in D if wl32[n]["downforce"]["delta_bar_n"] > 0]
    valid = len(D) >= MIN_D and len(set(fams) & set(WIDE_FAMILIES)) >= MIN_FAMILIES and len(pos) >= MIN_POSITIVE
    return {"D": D, "families": fams, "positive": pos, "valid": valid}


def verdict(ds, per_design, invalid_reason=None):
    """§6.7 steps 3-6 (steps 1-2 are passed in as invalid_reason)."""
    if invalid_reason:
        return "FID01_INVALID"
    if not ds["valid"]:
        return "FID01_INCONCLUSIVE_DESIGN_SET"
    st = [per_design[n]["status"] for n in ds["D"]]
    return "FID01_NO_GO" if "FAIL" in st else "FID01_GO" if all(x == "PASS" for x in st) else "EXTENSION_REQUIRED"


def stratum_label(per_design, eligible):
    if not eligible:
        return "NARROW_UNTESTABLE"
    st = [per_design[n]["status"] for n in eligible]
    return "NARROW_FAIL" if "FAIL" in st else "NARROW_PASS" if all(x == "PASS" for x in st) else "NARROW_UNRESOLVED"


def nc(wl32, ofs):
    w = wl32.get(ROLL, {}).get("downforce")
    o = ofs.get("V1", {}).get(ROLL, {}).get("downforce")
    out = {}
    for key, est, (ref, ref_se) in (("wl", w, NC_REF["wl"]), ("of", o, NC_REF["of"])):
        if est is None or est.get("se_n") is None:
            out[key] = {"label": "MISSING"}
            continue
        z = abs(est["delta_bar_n"] - ref) / math.hypot(est["se_n"], ref_se)
        out[key] = {"label": "CONSISTENT" if z <= 3 else "INCONSISTENT", "delta_bar_n": est["delta_bar_n"], "se_n": est["se_n"], "reference_n": ref, "z": z}
    out["consistent"] = all(out[k]["label"] == "CONSISTENT" for k in ("wl", "of"))
    return out


def r3_labels(wl32, wl48, D):
    out = {}
    for n in D:
        d32, sd = wl32[n]["downforce"]["delta_bar_n"], wl32[n]["downforce"]["sigma_d_n"]
        d48 = (wl48 or {}).get(n, {}).get("downforce", {}).get("delta_bar_n")
        if d48 is None:
            out[n] = {"label": "NOT_MEASURED"}
            continue
        lab = "R3_CONFIRMED" if (d48 > 0) == (d32 > 0) else "R3_CONTRADICTED" if abs(d48) > 2 * max(sd, FLOOR["downforce"]) else "R3_UNRESOLVED"
        out[n] = {"label": lab, "delta_48_n": d48, "ratio_48_32": d48 / d32, "paired_E2_term": abs(d48 - d32) / J_B48}
    return {"designs": out, "R3_CHALLENGED": any(v["label"] == "R3_CONTRADICTED" for v in out.values())}


def ex_labels(vals, ex_states):
    """§6.6 EX on V3: shift-matched change of the difference between the r = 16 and the r = 8 exports."""
    v3 = vals.get("V3", {})
    out = {}
    tags = sorted({t for (s, t) in v3 if s == f"{PARENT}__r{EX_R}"})
    for n in ex_states:
        r16, ok = f"{n}__r{EX_R}", True
        common = [t for t in tags if all((x, t) in v3 for x in (n, PARENT, r16, f"{PARENT}__r{EX_R}"))]
        if not common:
            out[n] = {"label": "NOT_MEASURED"}
            continue
        if n == PARENT:
            out[n] = {"absolute_change_n": {r: sum(v3[(r16, t)][r] - v3[(n, t)][r] for t in common) / len(common) for r in RESP}, "shifts": common}
            continue
        d8 = [v3[(n, t)]["downforce"] - v3[(PARENT, t)]["downforce"] for t in common]
        d16 = [v3[(r16, t)]["downforce"] - v3[(f"{PARENT}__r{EX_R}", t)]["downforce"] for t in common]
        delta = sum(b - a for a, b in zip(d8, d16)) / len(common)
        m8 = sum(d8) / len(d8)
        out[n] = {"delta_EX_n": delta, "delta_V3_r8_n": m8, "shifts": common, "ok": ok}
    return out


def ex_finish(ex, ofs):
    se3 = None
    for v in ofs.get("V3", {}).values():
        se3 = v["downforce"].get("sigma_pool_v2_n")
        break
    for n, e in ex.items():
        if "delta_EX_n" in e:
            se = se3 / math.sqrt(len(e["shifts"])) if se3 else None
            ins = abs(e["delta_EX_n"]) <= 0.1 * abs(e["delta_V3_r8_n"]) or (se is not None and abs(e["delta_EX_n"]) <= 2 * math.sqrt(2) * se)
            e["label"] = "EXPORT_INSENSITIVE" if ins else "EXPORT_SENSITIVE"
    return ex


def evaluate(states_rec, wlres, vals, export_rec, ofrecs):
    wl32, wl48 = wlres["flow_32"].get("differences", {}), wlres["flow_48"].get("differences", {})
    designs = [n for n, r in states_rec.items() if r.get("slot")]
    wide = [n for n in designs if states_rec[n]["stratum"] == "wide"]
    narrow = [n for n in designs if states_rec[n]["stratum"] == "narrow"]
    ofs = level_stats(vals, [PARENT, *designs, ROLL])
    # §6.7 step 1: minimum data
    invalid = []
    if wlres["flow_32"]["P"] < MIN_WL_P:
        invalid.append(f"flow_32 P = {wlres['flow_32']['P']} < {MIN_WL_P}")
    for L in ("V1", "V2", "V3"):
        tags = sorted(t for (s, t) in vals.get(L, {}) if s == PARENT)
        n = len(pairs_of(vals[L], PARENT, PARENT)) * 2 if L == "V1" and L in vals else len(tags)
        if n < MIN_SHIFTS[L]:
            invalid.append(f"{L}: parent has {n} valid shifts{' (whole pairs)' if L == 'V1' else ''} < {MIN_SHIFTS[L]}")
    out = {"minimum_data": {"pass": not invalid, "failures": invalid}}
    if invalid:
        out.update(outcome=verdict(None, None, "minimum data"))
        return out, ofs
    ncr = nc(wl32, ofs)
    out["NC"] = ncr
    per = {n: g_rules(wl32, ofs, n, export_rec[f"{n}|r8"]) for n in designs}
    ds = decision_set(wl32, states_rec, DELTA_MIN, wide)
    out.update(decision_set=ds, per_design=per)
    out["outcome"] = verdict(ds, per, None if ncr["consistent"] else "NC inconsistent")
    out["NC_reason"] = None if ncr["consistent"] else "FID01_INVALID: negative control inconsistent with M2"
    out["extension_plan"] = extension_plan(per, ds["D"]) if out["outcome"] == "EXTENSION_REQUIRED" else None
    # secondary labels (§6.4-§6.6, §6.9)
    elig_n = [n for n in narrow if abs(wl32[n]["downforce"]["delta_bar_n"]) >= DELTA_MIN and abs(wl32[n]["downforce"]["delta_bar_n"]) > 3 * wl32[n]["downforce"]["se_eff_n"]]
    out["narrow"] = {"eligible": elig_n, "label": stratum_label(per, elig_n)}
    out["R3"] = r3_labels(wl32, wl48, ds["D"])
    out["EX"] = ex_finish(ex_labels(vals, [s for s in states_rec if states_rec[s].get("slot") in ("W4", "N1")] + [PARENT]), ofs)
    lit = decision_set(wl32, states_rec, DELTA_MIN_LIT, wide)
    out["literal_threshold"] = {"delta_min_n": DELTA_MIN_LIT, "decision_set": lit, "outcome": verdict(lit, per, None if ncr["consistent"] else "NC")}
    dplus = {**ds, "D": ds["positive"], "valid": len(ds["positive"]) >= MIN_POSITIVE}
    out["improvement_only"] = {"D_plus": ds["positive"], "statuses": {n: per[n]["status"] for n in ds["positive"]}, "outcome_descriptive": verdict(dplus, per)}
    out["sub_threshold_wide"] = [n for n in wide if n not in ds["D"]]
    pts = [(wl32[n]["downforce"]["delta_bar_n"], ofs["V1"][n]["downforce"]["delta_bar_n"]) for n in designs if "delta_bar_n" in ofs.get("V1", {}).get(n, {}).get("downforce", {})]
    out["correlation_wl_of_V1"] = A.corr([a for a, _ in pts], [b for _, b in pts]) if len(pts) > 2 else None
    out["of_kernels"] = ofrecs
    return out, ofs


def extension_plan(per, D):
    """§6.8: level -> designs whose unresolved rule involves that level."""
    plan = {}
    for n in D:
        p = per[n]
        if p["status"] != "UNRESOLVED":
            continue
        levs = set()
        levs |= {L for L, v in p["G1_levels"].items() if v == "UNRESOLVED"}
        if p["rules"]["G3"] == "UNRESOLVED":
            levs |= set(p["G3"].get("levels_max_min", [])) or set(p["G3"].get("missing_levels", []))
        if p["rules"]["G4"] == "UNRESOLVED" or p["rules"]["G2"] == "UNRESOLVED":
            levs.add("V1")
        for L in sorted(levs):
            plan.setdefault(L, []).append(n)
    return plan


def main_analysis(campaign, tables, kernel_root, of_dirs):
    states_rec = SC.jload(EVID / "states.json")["states"]
    export = SC.jload(EVID / "of/export.json")
    SC.req(export["states_sha256"] == SC.sha256_path(EVID / "states.json"), "export.json does not belong to states.json")
    coef = coefficients()
    c, wlres = wl(campaign, tables, kernel_root)
    SC.req(set(wlres["flow_32"]["states"]) == set(states_rec), "flow_32 states differ from states.json")
    vals, ofrecs = of_values(of_dirs)
    res, ofs = evaluate(states_rec, wlres, vals, export["exports"], ofrecs)
    return {"kind": "fid01_analysis", "registration": "docs/fid01_registration_2026_10_21.md", "analyzer_sha256": SC.sha256_path(__file__),
            "campaign_sha256": SC.sha256_path(campaign), "table_sha256": {Path(t).name: SC.sha256_path(t) for t in tables}, "coefficients": coef,
            "wl": wlres, "of": ofs, **res, "qualification_flags": "all false (unchanged)", "shape_update_allowed": False}


def extension_analysis(main_path, campaign, tables, kernel_root, of_dirs):
    """§6.8: the UNRESOLVED designs recomputed once with all shifts; remaining UNRESOLVED counts as FAIL; outcome re-evaluated."""
    main = SC.jload(main_path)
    SC.req(main["outcome"] == "EXTENSION_REQUIRED", "the main analysis did not require the extension")
    states_rec = SC.jload(EVID / "states.json")["states"]
    export = SC.jload(EVID / "of/export.json")["exports"]
    _, wlres = wl(campaign, tables, kernel_root)
    vals, ofrecs = of_values(of_dirs)
    res = extension_eval(main, states_rec, wlres, vals, export)
    return {"kind": "fid01_extension_analysis", "main_sha256": SC.sha256_path(main_path), "analyzer_sha256": SC.sha256_path(__file__), **res, "of_kernels": ofrecs}


def extension_eval(main, states_rec, wlres, vals, export):
    designs = [n for n, r in states_rec.items() if r.get("slot")]
    ofs = level_stats(vals, [PARENT, *designs, ROLL])
    per = dict(main["per_design"])
    redo = sorted({n for ns in main["extension_plan"].values() for n in ns})
    for n in redo:
        r = g_rules(wlres["flow_32"]["differences"], ofs, n, export[f"{n}|r8"])
        r["rules"] = {k: ("FAIL" if v == "UNRESOLVED" else v) for k, v in r["rules"].items()}
        r["status"] = worst(*r["rules"].values())
        r["extension"] = True
        per[n] = r
    return {"recomputed": redo, "per_design": per, "outcome": verdict(main["decision_set"], per), "of": ofs}


def budget(finished, pending, f48_estimates_s):
    walls = {k: A.log_wall(p) for k, p in (x.split("=", 1) for x in finished)}
    T = sum(walls.values()) + sum(pending.values()) + sum(f48_estimates_s)
    return {"kind": "fid01_budget_decision", "finished_session_wall_s": walls, "pending_estimates_s": pending, "f48_estimates_s": f48_estimates_s, "T_s": T,
            "cap_s": F48_CAP_S, "push_f48": T <= F48_CAP_S, "logs_sha256": {x.split("=", 1)[0]: SC.sha256_path(x.split("=", 1)[1]) for x in finished}, "rule": "registration §4.3"}


def write_once(path, obj):
    with Path(path).open("x") as f:
        f.write(json.dumps(A.clean(obj), indent=1, sort_keys=True, allow_nan=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["budget", "main", "extension"])
    ap.add_argument("--campaign", type=Path)
    ap.add_argument("--tables", nargs="*", type=Path, default=[])
    ap.add_argument("--kernel-root", type=Path)
    ap.add_argument("--of", nargs="*", type=Path, default=[])
    ap.add_argument("--main", type=Path)
    ap.add_argument("--finished", nargs="*", default=[])
    ap.add_argument("--pending", nargs="*", default=[], help="KERNEL=ESTIMATE_S")
    ap.add_argument("--f48", nargs="*", type=int, default=[], help="estimates (s) of the f48 kernels incl. setup")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "budget":
        write_once(a.out, budget(a.finished, {k: int(v) for k, v in (x.split("=", 1) for x in a.pending)}, a.f48))
        return
    SC.req(a.campaign is not None and a.kernel_root is not None and a.tables and a.of, "main/extension need --campaign, --tables, --kernel-root and --of")
    res = main_analysis(a.campaign, a.tables, a.kernel_root, a.of) if a.cmd == "main" else extension_analysis(a.main, a.campaign, a.tables, a.kernel_root, a.of)
    write_once(a.out, res)
    print(res["outcome"])


if __name__ == "__main__":
    main()
