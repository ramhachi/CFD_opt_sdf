#!/usr/bin/env python3
"""UNC-01 (#61, M2) analysis: the rules of docs/unc01_registration_2026_10_20.md §5 (that text governs; a disagreement is a defect here).

    analyze_unc01.py u0 --campaign C --table T --kernel-root D [--smoke] [--out J]       # U0 gate (§5.1) from the native parent rows only; exit 1 on U0_FAIL
    analyze_unc01.py u1 --campaign C --table T --kernel-root D --out J                   # U0 gate again, then the L / L2 / L_mid selection (§3); exit 1 unless selected
    analyze_unc01.py budget --finished LOG... --pending KERNEL... [--out J]              # §4 flow_24 decision from session times only
    analyze_unc01.py u2 --campaign C --u1 SEL --budget B --tables T... --kernel-root D --u3 R --u3-criteria K --out J   # the registered analysis, written once

Kernel outputs: <kernel-root>/<out_prefix><kernel>/states/<run name>/<case_id>.{summary.json,forces.csv}.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from cfd_harness import campaign_schema as SC  # noqa: E402
from fd08_v2_campaign_io import clipped_window, read_force_history, time_weighted_mean  # noqa: E402

RESP = ("downforce", "drag")
WIDE = {"pitch": 3.1, "camber": 19.7, "reflex": 29.3, "twist": 1.1, "sweep": 11.3}          # = unc01_build.WIDE (order = tie order)
FAMILY = {"pitch": "rigid", "camber": "section", "reflex": "section", "twist": "span", "sweep": "span"}
L_MID = {"pitch": 1.3, "camber": 11.3, "reflex": 11.3}
V17_NATIVE_PARENT_DOWNFORCE_N = {"flow_24": 0.33188, "flow_32": 0.36178, "flow_48": 0.36435}
U0_DRIFT_MAX, RUN_DRIFT_FLAG, RATIO_BAND, Q3_BAND, J_SCALE_N = 0.02, 0.002, (0.5, 2.0), (0.8, 1.25), 3.6e-3
U2_PHASES = {"flow_24": (1, 2, 3, 4, 5, 6), "flow_32": (1, 2, 3, 4, 5, 6), "flow_48": (1, 2, 3, 4)}
MIN_P = {"flow_24": 6, "flow_32": 4, "flow_48": 4}
U3_MIN_PAIRS = 12
EST_S = {"f48a": 9360, "f48b": 9360, "f32a": 6640, "f32b": 6640, "f32c": 6640, "f24": 3240, "f24r": 2160}
SETUP_S, CAP_S = 260, 46800
CONFOUNDS = "D0 outward +3 mm (smoothed volume +7.6 %), s050 inward -5 mm (nearly volume-neutral); max change 3.0 vs 4.4 mm; support 1.0 vs 0.02"


def clean(x):
    """JSON-safe: numpy scalars to Python, inf to 'inf', nan to null."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None if math.isnan(x) else ("inf" if x > 0 else "-inf")
    return x


def tq(p, dof):
    from scipy import stats as st
    return float(st.t.ppf(p, dof))


# ---- loading ----------------------------------------------------------------------------------------------------------------------------------------
def load_rows(campaign_path, tables, smoke=False, campaign_id=None):
    """(case_id, state, tag) -> {downforce, drag, kernel, name}; every table belongs to this campaign, passes integrity, and is formal unless smoke."""
    c, csha = SC.jload(campaign_path), SC.sha256_path(campaign_path)
    SC.validate_campaign(c)
    SC.req(campaign_id is None or c["campaign_id"] == campaign_id, f"campaign must be {campaign_id}")
    rows, kernels = {}, set()
    for path in tables:
        t = SC.jload(path)
        if smoke:
            SC.req(t.get("kind") == SC.TABLE_KIND and t.get("smoke") is True and t.get("integrity") == {"pass": True, "failures": []}, "not a passed smoke table")
        else:
            SC.require_formal_table(t)
        SC.req(t["campaign_sha256"] == csha and t.get("campaign_id", c["campaign_id"]) == c["campaign_id"], "table belongs to another campaign")
        for k, forces in t["state_forces_n"].items():
            SC.req(k in c["kernels"] and k not in kernels, f"unknown or duplicated kernel {k}")
            kernels.add(k)
            names = SC.runs_by_name(c["kernels"][k])
            SC.req(smoke or set(forces) == set(names), f"kernel {k}: table runs differ from the campaign")
            for name, f in forces.items():
                rows[(c["kernels"][k]["case"]["case_id"], names[name]["state"], name.rsplit("__", 1)[1])] = {
                    "downforce": f["downforce_n"], "drag": f["drag_n"], "kernel": k, "name": name}
    return c, rows, kernels


def run_files(c, kernel_root, kernel, name):
    case = c["kernels"][kernel]["case"]["case_id"]
    d = Path(kernel_root) / SC.out_dir_name(c, kernel) / "states" / name
    return d / SC.summary_name(case), d / SC.forces_name(case)


def drift(csv_path, window=(80.0, 120.0)):
    """|m(a,mid) - m(mid,b)| / |m(a,b)|, m = clipped trapezoidal time mean of the force CSV column (registration §5.1)."""
    rows = read_force_history(csv_path)
    a, b = window
    mid = 0.5 * (a + b)
    out = {}
    for r, col in (("downforce", "downforce_solver"), ("drag", "drag_solver")):
        whole = time_weighted_mean(clipped_window(rows, a, b), col)
        out[r] = abs(time_weighted_mean(clipped_window(rows, a, mid), col) - time_weighted_mean(clipped_window(rows, mid, b), col)) / max(abs(whole), sys.float_info.epsilon)
    return out


# ---- U0 ---------------------------------------------------------------------------------------------------------------------------------------------
def u0_gate(campaign_path, table, kernel_root, smoke=False):
    c, rows, _ = load_rows(campaign_path, [table], smoke, "unc01_u01")
    checks, ok = {}, True
    for g in (("flow_24",) if smoke else ("flow_24", "flow_32", "flow_48")):
        row = rows.get((g, "v18__parent", "k0"))
        if row is None:
            checks[g], ok = {"pass": False, "reason": "native parent row missing"}, False
            continue
        summary_path, csv_path = run_files(c, kernel_root, row["kernel"], row["name"])
        s, d = SC.jload(summary_path), drift(csv_path)
        ratio = row["downforce"] / V17_NATIVE_PARENT_DOWNFORCE_N[g]
        tests = {"finite": all(s.get(f) is True for f in SC.SUMMARY_FLAG_KEYS), "drift_downforce": d["downforce"] <= U0_DRIFT_MAX, "drift_drag": d["drag"] <= U0_DRIFT_MAX,
                 "downforce_positive": row["downforce"] > 0, "gross_error_ratio_to_v17": RATIO_BAND[0] <= ratio <= RATIO_BAND[1]}
        checks[g] = {"pass": all(tests.values()), "tests": tests, "drift": d, "downforce_n": row["downforce"], "drag_n": row["drag"],
                     "ratio_to_v17_native_parent": ratio, "v17_reference_n": V17_NATIVE_PARENT_DOWNFORCE_N[g]}
        ok &= checks[g]["pass"]
    return {"kind": "unc01_u0_gate", "smoke": smoke, "campaign_sha256": SC.sha256_path(campaign_path), "table_sha256": SC.sha256_path(table),
            "verdict": "U0_PASS" if ok else "U0_FAIL", "grids": checks, "rows_read": "v18__parent__k0 only",
            "rule": "registration §5.1: finite flags, relative half-window drift <= 0.02 (drag, downforce), downforce > 0, gross-error check 0.5 <= F/F_v17 <= 2"}


# ---- U1 ---------------------------------------------------------------------------------------------------------------------------------------------
def pm(m):
    return f"v18__{m}_p{WIDE[m]:g}", f"v18__{m}_m{WIDE[m]:g}"


def u1(campaign_path, table, kernel_root):
    gate = u0_gate(campaign_path, table, kernel_root)
    out = {"kind": "unc01_u1_selection", "evidence_tier": "EXPLORATORY_COMMITTED", "u0": gate, "table_sha256": SC.sha256_path(table),
           "analyzer_sha256": SC.sha256_path(__file__), "selection": None}
    if gate["verdict"] != "U0_PASS":
        out["verdict"] = "U0_FAIL"
        return out
    _, rows, _ = load_rows(campaign_path, [table], campaign_id="unc01_u01")
    need = [("flow_32", s, "k0") for m in WIDE for s in pm(m)] + [("flow_32", "v18__parent", "k0"), ("flow_32", "v18__D0_p3", "k0")]
    if any(k not in rows for k in need):
        out["verdict"] = "U1_INCOMPLETE"
        return out
    F = lambda g, s, t, r: rows[(g, s, t)][r]  # noqa: E731
    score = {m: abs(F("flow_32", pm(m)[0], "k0", "downforce") - F("flow_32", pm(m)[1], "k0", "downforce")) for m in WIDE}
    L = max(WIDE, key=lambda m: (score[m], -list(WIDE).index(m)))
    others = [m for m in WIDE if FAMILY[m] != FAMILY[L]]
    L2 = max(others, key=lambda m: (score[m], -list(WIDE).index(m)))
    k0 = {s: {r: F("flow_32", s, "k0", r) - F("flow_32", "v18__parent", "k0", r) for r in RESP} for m in WIDE for s in pm(m)}
    k0["v18__D0_p3"] = {r: F("flow_32", "v18__D0_p3", "k0", r) - F("flow_32", "v18__parent", "k0", r) for r in RESP}
    bridge = {g: {r: {"parent_half_minus_k0_n": F(g, "v18__parent", "half", r) - F(g, "v18__parent", "k0", r),
                      "parent_half_minus_k0_rel": F(g, "v18__parent", "half", r) / F(g, "v18__parent", "k0", r) - 1,
                      "D0_difference_k0_n": F(g, "v18__D0_p3", "k0", r) - F(g, "v18__parent", "k0", r),
                      "D0_difference_half_n": F(g, "v18__D0_p3", "half", r) - F(g, "v18__parent", "half", r)} for r in RESP} for g in ("flow_24", "flow_32")}
    out.update(verdict="SELECTED", selection={"L": L, "L2": L2, "L_mid": f"v18__{L}_p{L_MID[L]:g}" if L in L_MID else pm(L2)[1], "scores_n": score,
                                              "rule": "registration §3: L = argmax |F32(m+,k0) - F32(m-,k0)| (downforce); L2 = argmax over other families; ties in WIDE order"},
               k0_differences_flow32=k0, bridge=bridge, bridge_reference_v17_grid02="parent downforce change at the same placement: flow_24 +1.7 %, flow_32 -9.6 % (GRID-02)")
    return out


# ---- budget (§4) ----------------------------------------------------------------------------------------------------------------------------------
def log_wall(path):
    """Session wall time of a Kaggle kernel log: the last record's 'time' (s since the session start)."""
    return max(float(r["time"]) for r in json.loads(Path(path).read_text()))


def budget(finished_logs, pending):
    done = sum(log_wall(p) for p in finished_logs)
    pend = sum(EST_S[k] + SETUP_S for k in pending)
    t24, t24r = done + pend + EST_S["f24"] + SETUP_S, done + pend + EST_S["f24r"] + SETUP_S
    push = "f24" if t24 <= CAP_S else "f24r" if t24r <= CAP_S else None
    return {"kind": "unc01_budget_decision", "finished_session_wall_s": done, "pending": list(pending), "pending_estimate_s": pend,
            "T_f24_s": t24, "T_f24r_s": t24r, "cap_s": CAP_S, "push": push, "rule": "registration §4"}


# ---- U2 statistics ------------------------------------------------------------------------------------------------------------------------------------
def stats(deltas):
    from scipy import stats as st
    P = len(deltas)
    mean = sum(deltas) / P
    sd = math.sqrt(sum((d - mean) ** 2 for d in deltas) / (P - 1))
    se = sd / math.sqrt(P)
    t = tq(0.95, P - 1)
    lo, hi = sd * math.sqrt((P - 1) / float(st.chi2.ppf(0.95, P - 1))), sd * math.sqrt((P - 1) / float(st.chi2.ppf(0.05, P - 1)))
    am = abs(mean)
    return {"P": P, "deltas_n": list(deltas), "delta_bar_n": mean, "sigma_d_n": sd, "se_n": se, "t": t, "sigma_d_90": [lo, hi], "delta_bar_90": [mean - t * se, mean + t * se],
            "abs_over_se": am / se if se > 0 else math.inf, "resolved": am > t * se, "above_3se": am > 3 * se, "r": sd / am if am > 0 else math.inf,
            "r_80": [lo / (am + t * se) if am + t * se > 0 else math.inf, hi / (am - t * se) if am > t * se else math.inf]}


def ratio_label(a, b):
    """§5.4: a tested, b reference."""
    if not (a["resolved"] and b["resolved"]):
        return {"label": "UNRESOLVED"}
    if (a["delta_bar_n"] > 0) != (b["delta_bar_n"] > 0):
        return {"label": "DIFFERENT", "R": a["delta_bar_n"] / b["delta_bar_n"], "reason": "opposite signs"}
    R = a["delta_bar_n"] / b["delta_bar_n"]
    t = tq(0.95, min(a["P"], b["P"]) - 1)
    w = t * math.hypot(a["se_n"] / a["delta_bar_n"], b["se_n"] / b["delta_bar_n"])
    lo, hi = R * math.exp(-w), R * math.exp(w)
    lab = "EQUIVALENT" if Q3_BAND[0] <= lo and hi <= Q3_BAND[1] else "DIFFERENT" if hi < Q3_BAND[0] or lo > Q3_BAND[1] else "INDETERMINATE"
    return {"label": lab, "R": R, "R_90": [lo, hi], "t": t}


def grid_tables(c, rows, kernels, kernel_root, f24_pushed):
    """f24_pushed: the flow_24 kernel the §4 budget decision pushed (f24, f24r or None = NOT_MEASURED); a table of the other one is an error."""
    SC.req(f24_pushed in ("f24", "f24r", None) and not ({"f24", "f24r"} - {f24_pushed}) & kernels, "a flow_24 table that the budget decision did not push")
    out = {}
    for g, phases in U2_PHASES.items():
        runs = [r for k, kern in c["kernels"].items() if kern["case"]["case_id"] == g and (g != "flow_24" or k == f24_pushed) for r in kern["runs"]]
        states = list(dict.fromkeys(r["state"] for r in runs))
        full = [p for p in phases if states and all((g, s, f"k{p}") in rows for s in states)]
        variant = f24_pushed if g == "flow_24" else None
        e = {"states": states, "phases_registered": list(phases), "phases_used": full, "P": len(full), "complete": len(full) >= MIN_P[g],
             "P_reduced": 0 < len(full) < len(phases), "variant": variant, "kernels": sorted(k for k in kernels if c["kernels"][k]["case"]["case_id"] == g)}
        if e["complete"]:
            F = {s: {p: rows[(g, s, f"k{p}")] for p in full} for s in states}
            e["parent_forces_n"] = {r: [F["v18__parent"][p][r] for p in full] for r in RESP}
            e["parent_mean_n"] = {r: sum(e["parent_forces_n"][r]) / len(full) for r in RESP}
            e["sigma_F_n"] = {r: stats(e["parent_forces_n"][r])["sigma_d_n"] for r in RESP}
            e["state_forces_n"] = {s: {r: [F[s][p][r] for p in full] for r in RESP} for s in states}
            e["differences"] = {}
            for s in states[1:]:
                e["differences"][s] = {}
                for r in RESP:
                    d = [F[s][p][r] - F["v18__parent"][p][r] for p in full]
                    st_ = stats(d)
                    st_["sigma_d_over_sqrt2_sigma_F"] = st_["sigma_d_n"] / (math.sqrt(2) * e["sigma_F_n"][r]) if e["sigma_F_n"][r] > 0 else math.inf
                    st_["corr_with_parent_F"] = corr(d, e["parent_forces_n"][r])
                    e["differences"][s][r] = st_
            e["corr_between_differences"] = {r: {f"{a}|{b}": corr(e["differences"][a][r]["deltas_n"], e["differences"][b][r]["deltas_n"])
                                                 for i, a in enumerate(states[1:]) for b in states[i + 2:]} for r in RESP}
            if kernel_root is not None:
                e["drift"] = {F[s][p]["name"]: drift(run_files(c, kernel_root, F[s][p]["kernel"], F[s][p]["name"])[1]) for s in states for p in full}
                e["drift_flagged"] = sorted(n for n, v in e["drift"].items() if max(v.values()) > RUN_DRIFT_FLAG)
        out[g] = e
    return out


def corr(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy, sxx, syy = sum((a - mx) * (b - my) for a, b in zip(x, y)), sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def roles(sel):
    L, L2 = sel["L"], sel["L2"]
    Lp, Lm = pm(L)
    return {"D0": "v18__D0_p3", "Lp": Lp, "Lm": Lm, "mid": sel["L_mid"], "L2p": pm(L2)[0], "s050": "v18__s050_m5", "roll": "v18__roll_p25"}


def q2_label(D0, s050):
    if not D0["resolved"]:
        return "D0_UNRESOLVED"
    if not s050["resolved"]:
        return "S050_UNRESOLVED"
    return "D0_LOWER_R" if D0["r_80"][1] < s050["r_80"][0] else "S050_LOWER_R" if s050["r_80"][1] < D0["r_80"][0] else "NOT_SEPARATED"


def q2(grids, ro, r, U3=None):
    if U3 is not None:
        d = U3.get("differences", {})
        if U3["status"] != "COMPLETE":
            return {"label": "INCOMPLETE"}
        if ro["D0"] not in d or ro["s050"] not in d:
            return {"label": "NOT_MEASURED"}
        return {"label": q2_label(d[ro["D0"]][r], d[ro["s050"]][r]), "note": "local 3-axis shift ensemble; not comparable with the WaterLily ordering"}
    g = grids["flow_32"]
    if not g["complete"]:
        return {"label": "INCOMPLETE"}
    diffs = g["differences"]
    maxchg = MAX_CHANGE_MM
    rep = {s: {"r": d[r]["r"], "r_80": d[r]["r_80"], "resolved": d[r]["resolved"], "sigma_d_over_sqrt2_sigma_F": d[r]["sigma_d_over_sqrt2_sigma_F"],
               "sigma_d_per_mm_max_change_n": d[r]["sigma_d_n"] / maxchg[s] if s in maxchg else None} for s, d in diffs.items()}
    return {"label": q2_label(diffs[ro["D0"]][r], diffs[ro["s050"]][r]), "flow32": rep, "confounds": CONFOUNDS,
            "claim_limit": "descriptive ordering; confounds support with response size, sign and volume; no decision depends on it"}


def q3(grids, ro, r):
    g24, g32, g48 = grids["flow_24"], grids["flow_32"], grids["flow_48"]
    main = ratio_label(g32["differences"][ro["Lp"]][r], g48["differences"][ro["Lp"]][r]) if g32["complete"] and g48["complete"] else {"label": "INCOMPLETE"}
    if g24["variant"] is None:
        f24 = {"label": "NOT_MEASURED"}
    elif g24["complete"] and g32["complete"]:
        modes = [ro["Lp"]] + ([] if g24["variant"] == "f24r" else [ro["D0"]])
        res = {m: ratio_label(g24["differences"][m][r], g32["differences"][m][r]) for m in modes}
        labs = [v["label"] for v in res.values()]
        f24 = {"label": "FLOW24_DIFFERENT" if "DIFFERENT" in labs else "FLOW24_EQUIVALENT" if all(x == "EQUIVALENT" for x in labs)
               else "FLOW24_UNRESOLVED" if "UNRESOLVED" in labs else "FLOW24_INDETERMINATE", "detail": res}
    else:
        f24 = {"label": "INCOMPLETE"}
    return {"flow32_vs_flow48_Lplus": main, "flow24_vs_flow32": f24, "band": list(Q3_BAND)}


def q4(grids, ro, r):
    g32, g48 = grids["flow_32"], grids["flow_48"]
    if not (g32["complete"] and g48["complete"]):
        return {"status": "INCOMPLETE"}
    Lp = ro["Lp"]

    def block(phases):
        i32 = [g32["phases_used"].index(p) for p in phases]
        i48 = [g48["phases_used"].index(p) for p in phases]
        pick = lambda xs, ii: [xs[i] for i in ii]  # noqa: E731
        b32, b48 = pick(g32["parent_forces_n"][r], i32), pick(g48["parent_forces_n"][r], i48)
        c32, c48 = pick(g32["state_forces_n"][Lp][r], i32), pick(g48["state_forces_n"][Lp][r], i48)
        d32, d48 = [c - b for c, b in zip(c32, b32)], [c - b for c, b in zip(c48, b48)]
        mean, sem = (lambda x: sum(x) / len(x)), (lambda x: stats(x)["se_n"] if len(x) > 1 else math.inf)
        den = max(abs(mean(b48)), J_SCALE_N)
        sign = -1.0 if r == "downforce" else 1.0   # J = -downforce (minimised) or drag
        return {"phases": list(phases), "denominator_n": den,
                "S_b": abs(mean(b48) - mean(b32)) / den, "S_b_se": math.hypot(sem(b48), sem(b32)) / den,
                "S_c": abs(mean(c48) - mean(c32)) / den, "S_c_se": math.hypot(sem(c48), sem(c32)) / den,
                "S_d": abs(mean(d48) - mean(d32)) / den, "S_d_se": math.hypot(sem(d48), sem(d32)) / den,
                "I_f_Lplus_descriptive": sign * (mean(b48) - mean(c48)) / den}
    common = [p for p in g48["phases_used"] if p in g32["phases_used"]]
    if len(common) < 2:
        return {"status": "INCOMPLETE", "reason": "fewer than two common phases"}
    main = block(common)
    main.update(implied_min_gain_literal_E2=2 * max(main["S_b"], main["S_c"]), implied_min_gain_paired=2 * main["S_d"])
    allp = {"S_b": abs(g48["parent_mean_n"][r] - g32["parent_mean_n"][r]) / main["denominator_n"],
            "S_c": abs(sum(g48["state_forces_n"][Lp][r]) / g48["P"] - sum(g32["state_forces_n"][Lp][r]) / g32["P"]) / main["denominator_n"],
            "S_d": abs(g48["differences"][Lp][r]["delta_bar_n"] - g32["differences"][Lp][r]["delta_bar_n"]) / main["denominator_n"]}
    return {"status": "COMPLETE", "J_scale_n": J_SCALE_N, "common_phases": main, "all_phases_descriptive": allp,
            "note": "|.| of a noisy difference is biased up (about 0.8 SE under equality); S_b and S_c are expected to be dominated by the parent's placement noise"}


# ---- U3 ---------------------------------------------------------------------------------------------------------------------------------------------
def pair_stats(per_shift, pairs):
    """§5.6: the unit is the mean over a mirror pair; per_shift[j] = Delta at shift j ('33p', '33m', ...)."""
    means = [(per_shift[f"{i}p"] + per_shift[f"{i}m"]) / 2 for i in pairs]
    s = stats(means)
    allv = [per_shift[f"{i}{x}"] for i in pairs for x in "pm"]
    mu = sum(allv) / len(allv)
    s["sigma_d_shifts_n"] = math.sqrt(sum((v - mu) ** 2 for v in allv) / (len(allv) - 1))
    s["unit"] = "mirror-pair mean"
    return s


def u3(result_path, criteria_path, grids, ro):
    if criteria_path is None or result_path is None:
        return {"status": "INCOMPLETE", "reason": "no U3 output"}
    crit, res = SC.jload(criteria_path), SC.jload(result_path)
    SC.req(res["criteria_sha256"] == SC.sha256_path(criteria_path), "U3 result belongs to other criteria")
    states = list(crit["states"])
    if "v18__parent" not in states:
        return {"status": "INCOMPLETE", "reason": "parent STL failed the export gate", "not_run_export_gate": crit.get("not_run_export_gate", [])}
    cases = {c["id"]: c for c in res["cases"]}
    val = {}
    for spec in crit["case_order"]:
        c = cases.get(spec["id"], {"status": "MISSING"})
        if c.get("status") == "COMPLETED":
            val[(spec["state"], spec["id"].rsplit("_", 1)[1])] = {r: c["forces"][f"{r}_n"]["window_mean"] for r in RESP}
    pairs_reg = sorted({int(spec["id"].rsplit("_", 1)[1][:-1]) for spec in crit["case_order"]})
    pairs = [i for i in pairs_reg if all((s, f"{i}{x}") in val for s in states for x in "pm")]
    counts = {}
    for c in res["cases"]:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    out = {"status": "COMPLETE" if len(pairs) >= U3_MIN_PAIRS else "INCOMPLETE", "states": states, "pairs_used": pairs, "pairs_registered": len(pairs_reg),
           "case_status_counts": counts, "not_run_export_gate": crit.get("not_run_export_gate", []),
           "limits": "local shifts 0.5-4 mm on x, y, z (about 10 % of a surface cell) vs WaterLily whole-cell x, y phases; STL extraction differs from the SDF the WaterLily body samples"}
    if out["status"] != "COMPLETE":
        return out
    out["parent_mean_n"] = {r: sum(val[("v18__parent", f"{i}{x}")][r] for i in pairs for x in "pm") / (2 * len(pairs)) for r in RESP}
    out["differences"] = {}
    g32 = grids["flow_32"]
    for s in states[1:]:
        out["differences"][s] = {}
        for r in RESP:
            d = pair_stats({f"{i}{x}": val[(s, f"{i}{x}")][r] - val[("v18__parent", f"{i}{x}")][r] for i in pairs for x in "pm"}, pairs)
            wl = g32["differences"].get(s, {}).get(r) if g32["complete"] else None
            if wl is not None and wl["resolved"] and d["resolved"]:
                rho = d["delta_bar_n"] / wl["delta_bar_n"]
                w = tq(0.95, wl["P"] - 1) * math.hypot(d["se_n"] / d["delta_bar_n"], wl["se_n"] / wl["delta_bar_n"])
                d.update(retention_vs_flow32=rho, retention_90=sorted([rho * math.exp(-w), rho * math.exp(w)]), sign_agrees_with_flow32=rho > 0)
            else:
                d.update(retention_vs_flow32=None, retention_90=None, sign_agrees_with_flow32=None)
            out["differences"][s][r] = d
    return out


# ---- M3a tables, overall outcome --------------------------------------------------------------------------------------------------------------------
MAX_CHANGE_MM = {}   # filled from states.json (maximum pointwise phi change, mm)


def load_max_change():
    rec = SC.jload(ROOT / "docs/evidence/unc01_2026_10_20/states.json")
    MAX_CHANGE_MM.update({n: 1000 * r["maximum_pointwise_change_m"] for n, r in rec["states"].items() if r["maximum_pointwise_change_m"] > 0})


def loglog(points):
    """OLS of log sigma_d on log |Delta_bar|: slope, intercept and their standard errors (None below 3 points)."""
    pts = [(math.log(a), math.log(s)) for a, s in points if a > 0 and s > 0]
    n = len(pts)
    if n < 3:
        return None
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    a = my - b * mx
    s2 = sum((y - a - b * x) ** 2 for x, y in pts) / (n - 2)
    return {"n": n, "slope": b, "slope_se": math.sqrt(s2 / sxx), "intercept": a, "intercept_se": math.sqrt(s2 * (1 / n + mx * mx / sxx)),
            "reading": "slope near 0: additive noise; near 1: multiplicative"}


def m3a(grids, ro, U3, Q3):
    out = {}
    g32 = grids["flow_32"]
    wide = [ro[k] for k in ("D0", "Lp", "Lm", "mid", "L2p")]
    for r in RESP:
        e = {"per_state": {g: {s: {k: d[r][k] for k in ("sigma_d_n", "sigma_d_90", "r", "r_80", "abs_over_se", "resolved", "above_3se", "delta_bar_n", "se_n", "P")}
                               for s, d in grids[g]["differences"].items()} for g in grids if grids[g]["complete"]}}
        if g32["complete"]:
            d = g32["differences"]
            e["planning"] = {s: {"r": d[s][r]["r"], "r_hi": d[s][r]["r_80"][1], "phases_needed_at_r": math.ceil(9 * d[s][r]["r"] ** 2) if math.isfinite(d[s][r]["r"]) else math.inf,
                                 "phases_needed_at_r_hi": math.ceil(9 * d[s][r]["r_80"][1] ** 2) if math.isfinite(d[s][r]["r_80"][1]) else math.inf} for s in wide}
            e["largest_r_hi_wide"] = max(d[s][r]["r_80"][1] for s in wide)
            e["roll_null_control"] = {k: d[ro["roll"]][r][k] for k in ("delta_bar_n", "sigma_d_n", "se_n", "resolved")}
            e["sigma_d_vs_delta_fit"] = loglog([(abs(d[s][r]["delta_bar_n"]), d[s][r]["sigma_d_n"]) for s in wide + [ro["s050"]]])
        e["grid_ratio_Lplus_32_over_48"] = Q3[r]["flow32_vs_flow48_Lplus"]
        if U3.get("status") == "COMPLETE":
            e["retention"] = {s: {k: v[r][k] for k in ("retention_vs_flow32", "retention_90", "sign_agrees_with_flow32", "delta_bar_n", "se_n", "resolved")} for s, v in U3["differences"].items()}
        out[r] = e
    return out


def outcome(grids, U3):
    missing = [g for g in ("flow_48",) if not grids[g]["complete"]] + ([] if grids["flow_24"]["variant"] is None or grids["flow_24"]["complete"] else ["flow_24"])
    missing += [] if U3.get("status") == "COMPLETE" else ["U3"]
    if not grids["flow_32"]["complete"]:
        return {"label": "M2_INCOMPLETE", "missing": ["flow_32"] + missing}
    if grids["flow_32"]["P"] < 6:
        missing.insert(0, "flow_32 full phase set")
    return {"label": "M2_COMPLETE" if not missing else "M2_PARTIAL", "missing": missing}


def u2(campaign_path, sel_path, budget_path, tables, kernel_root, u3_result, u3_criteria):
    load_max_change()
    sel = SC.jload(sel_path)
    SC.req(sel.get("kind") == "unc01_u1_selection" and sel.get("verdict") == "SELECTED", "u2 needs a SELECTED U1 record")
    c, rows, kernels = load_rows(campaign_path, tables, campaign_id="unc01_u2")
    ro = roles(sel["selection"])
    SC.req(set(dict.fromkeys(r["state"] for k in ("f32a", "f32b", "f32c") for r in c["kernels"][k]["runs"]))
           == {"v18__parent", *(ro[k] for k in ("D0", "Lp", "Lm", "mid", "L2p", "s050", "roll"))}, "the U2 campaign does not match the U1 selection")
    bud = SC.jload(budget_path)
    SC.req(bud.get("kind") == "unc01_budget_decision", "u2 needs the §4 budget decision record")
    grids = grid_tables(c, rows, kernels, kernel_root, bud["push"])
    if grids["flow_32"]["complete"]:
        k0 = sel["k0_differences_flow32"]
        grids["flow_32"]["native_phase_atypicality"] = {s: {r: (k0[s][r] - d[r]["delta_bar_n"]) / d[r]["sigma_d_n"] if d[r]["sigma_d_n"] > 0 else None for r in RESP}
                                                         for s, d in grids["flow_32"]["differences"].items() if s in k0}
    U3 = u3(u3_result, u3_criteria, grids, ro)
    Q3 = {r: q3(grids, ro, r) for r in RESP}
    return {"kind": "unc01_u2_analysis", "evidence_tier": "REGISTERED_FROZEN", "registration": "docs/unc01_registration_2026_10_20.md", "campaign_sha256": SC.sha256_path(campaign_path),
            "u1_selection_sha256": SC.sha256_path(sel_path), "budget_decision": bud, "analyzer_sha256": SC.sha256_path(__file__), "selection": sel["selection"], "roles": ro,
            "outcome": outcome(grids, U3), "grids": grids, "u3": U3,
            "Q2": {"downforce": q2(grids, ro, "downforce"), "drag": q2(grids, ro, "drag"), "OF_downforce": q2(grids, ro, "downforce", U3), "OF_drag": q2(grids, ro, "drag", U3)},
            "Q3": Q3, "Q4_E2": {r: q4(grids, ro, r) for r in RESP}, "M3a_tables": m3a(grids, ro, U3, Q3),
            "notes": ["intervals treat the deterministic R2 phases as exchangeable samples; r intervals cover at least about 80 %",
                      "z (ride height) is not sampled; sigma_d holds for the measured states and amplitudes only"],
            "qualification_flags": "all false (unchanged)", "shape_update_allowed": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["u0", "u1", "budget", "u2"])
    ap.add_argument("--campaign")
    ap.add_argument("--table")
    ap.add_argument("--tables", nargs="*")
    ap.add_argument("--u1")
    ap.add_argument("--budget")
    ap.add_argument("--kernel-root")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--u3")
    ap.add_argument("--u3-criteria")
    ap.add_argument("--finished", nargs="*", default=[])
    ap.add_argument("--pending", nargs="*", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "u0":
        res = u0_gate(a.campaign, a.table, a.kernel_root, a.smoke)
    elif a.cmd == "u1":
        res = u1(a.campaign, a.table, a.kernel_root)
    elif a.cmd == "budget":
        res = budget(a.finished, a.pending)
    else:
        SC.req(bool(a.out) and not Path(a.out).exists(), "u2 is written once: --out must name a new file")
        res = u2(a.campaign, a.u1, a.budget, a.tables, a.kernel_root, a.u3, a.u3_criteria)
    res = clean(res)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({k: res[k] for k in ("verdict", "selection", "push", "outcome") if k in res}, indent=1))
    if a.cmd == "u0" and res["verdict"] != "U0_PASS" or a.cmd == "u1" and res["verdict"] != "SELECTED":
        sys.exit(1)


if __name__ == "__main__":
    main()
