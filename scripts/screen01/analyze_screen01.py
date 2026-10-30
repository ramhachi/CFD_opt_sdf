#!/usr/bin/env python3
"""SCREEN-01 (#64, M3b-1) analysis: the rules of docs/screen01_registration_2026_10_30.md §5 (that text governs; a disagreement is a defect here).

    analyze_screen01.py rs       --g1 CAMPAIGN [TABLE...] --kernel-root D [--lost K=ID:RECORD...] [--workers N] --out rs.json                  # after G1, written once
    analyze_screen01.py finalist --g1 C [T...] [--g2 C [T...]] --rs rs.json --kernel-root D [--lost ...] [--not-pushed ...] --out finalist.json   # after G2, written once
    analyze_screen01.py main     --g1 C [T...] [--g2 C [T...]] [--f32 C [T...]] [--f48 C [T...]] --rs R --finalist F --kernel-root D [--lost ...] [--not-pushed ...]
                                 --out analysis.json    # after F, or when F was not pushed: analysis.json, analysis.md and (on GAIN) xv_handoff.json, once
    analyze_screen01.py budget   --finished KERNEL=LOG... --pending KERNEL[=NRUNS]... [--out J]            # §4.3 go / stop (before the G2 push: pending = g2 f48k13 f48k14 f32a f32b)
    analyze_screen01.py infra    --output-dir D --log LOG [--status-file S] [--verify-failed] [--verify-log V] [--kernel K --attempt N --out REC]   # §9 signature table

Kernels (ids for --lost / --not-pushed): g1k11, g1k12 (group g1, phases 11, 12), g2 (phases 11, 12), f32a (13, 14 + replay 11), f32b (15, 16), f48k13, f48k14.  Every kernel of a
needed group has a harness-verified table, a --lost declaration or a --not-pushed declaration; the campaign argument of a needed group is required even then.
--lost KERNEL=ID:RECORD (§5.11.17): ID is an id of `docs/evidence/screen01_2026_10_30/infra_signatures.json` or NOT_INFRASTRUCTURE; RECORD is the classification record
`infra --out` wrote for the failed rerun (attempt >= 2); every formal kernel without a table is rerun once, whatever the cause.
--not-pushed KERNEL=REASON[:RECORD] (§5.11.19): BUDGET (a confirmation kernel; RECORD = a `budget` record with decision stop listing it) or INVALID_G1 (g2 and the confirmation
kernels; the cited frozen rs.json / finalist.json reports invalid_at_step_2); a declared kernel with a table is refused, a kernel without table or declaration is refused.
Binding (§10): every frozen file is looked up in the freeze record by its repo-relative POSIX path (sources, reused code, registration, adoption records, INTERFACE.md, signature
table, P0 rows, states.json, campaigns); each table's `freeze_sha256` equals its campaign record's prerun freeze and its `harness_tool_sha256` freeze 1's; each freeze N holds
the SHA-256 of freeze N-1; python / numpy / scipy / scikit-image equal freeze 1's `environment`; before a refinement point is gated `screen01_pool.fingerprint()` equals the
frozen P0 fingerprint; a re-derived earlier output matches to 1e-9 relative (floats) and exactly otherwise.  `main` binds freeze3.json on every branch, with or without F.

Every decision is a pure function of the normalised input T (scripts/screen01/INTERFACE.md): `compute(T)` is cross-checked against the independent
`screen01_check.check(T)` through `screen01_check.compare` before anything is written; a discrepancy refuses the write.  Dict keys that look numeric
are normalised to "%g" before the comparison (1, 1.0 and "1" are one key).

Comparable schema (INTERFACE.md and registration §5.11 are the authority; shapes as produced here; `canon` hides key spelling only):
  rs: fit.{downforce,drag}.coef, fit.rank, fit.cond (None if rank < 9), fit.residual_sd.{downforce,drag} (None if n <= 9 or not fit); RS_NOT_FIT (rank < 9 or cond > 20): coef,
  residual_sd, u_star_1, y_star_1 and every targets entry None; rs_fit_poor None whenever a residual SD is undefined (label RS_FIT_UNDEFINED in `detail.rs_fit_label`);
  targets["1"|"1.5"|"2"] = {u_star, y_pred, z_pred} for every target with a feasible grid point (also with y_pred <= 0: it then gates nothing); gated = [[target_index of the
  OWNING target, u rounded to 6]] in gating order (a name once), proposals = indices into gated.
  finalist: candidates[name] = {delta_bar, se_eff: {downforce, drag}, P, feasible} for every C_opt member (P = 0, None fields, not feasible without a paired phase); finalist None
  under futility; search_complete = parent, axial, design measured at both phases + fit OK + every proposal at both phases (R, M, ref, NC, repeat do not count).
  main: G = {decision, GAIN_RESOLVED_ABOVE_MIN}, D = {decision PASS|VIOLATION, label}, both None without |Phi_s| >= 3; R3 = {label, R3_RATIO_IN_BAND, G48_ABOVE_MIN, G48_MARGIN,
  R3_E2_EXCEEDED, R3_DRAG_SAME_SIGN} (the three paired labels None without a phase common to Phi_48 and the flow_32 phases within {13, 14}), None without flow_48 data;
  NC = {g1, f32} each {z, label CONSISTENT|NOT_CONSISTENT|None}; determinism = {g1k11, f32a} each {max_abs_diff: {downforce, drag}|None, nondeterminism, judged} (raw runs; repeat
  absent or not ok: judged False; non-finite repeat against a finite ok parent: judged, nondeterminism); generation_drift = {max_abs_diff, drift}; controls = {OPT_VS_RANDOM,
  OPT_VS_MANUAL (None without a finalist), RANDOM_FEASIBLE_GAIN, K_MISMATCH}; selection_bias = {b_K, g_XV_exp, XV_MARGIN} or None; confirmation = {f32, f48} each {P, delta_bar,
  sigma_d, se_eff: {downforce, drag}} or None.  g1_controls = {NC_g1, determinism_g1k11, invalid_at_step_2} at every stage.  cause: lists in the registered spellings and order
  (step 3: all of DATA_G1, DATA_REFINE, DATA_G2 that apply; step 4: BUDGET first, iff a confirmation kernel is in T["not_pushed"] with BUDGET, else DATA_F).  The descriptive blocks
  are computed whenever their data exist, whatever the outcome path; `I`, the phases used per estimate and AMPLITUDE_MISMATCH are in `detail`.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.metadata
import json
import math
import platform
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "scripts/screen01")]
import analyze_unc01 as A  # noqa: E402
import screen01_pool as P  # noqa: E402
from cfd_harness import campaign_schema as SC  # noqa: E402

EV_REL = "docs/evidence/screen01_2026_10_30"
EV = ROOT / EV_REL
REG_REL, INFRA_REL, ROWS_REL = "docs/screen01_registration_2026_10_30.md", f"{EV_REL}/infra_signatures.json", f"{EV_REL}/pool_prescreen_rev1/rows.jsonl"
POLICY_REL = "docs/evidence/geom02_v17_gates_2026_10_14/geom02_resolved_research_policy.json"
FROZEN_FILES = (*(f"scripts/screen01/{s}" for s in ("analyze_screen01.py", "screen01_check.py", "screen01_pool.py")), "scripts/analyze_unc01.py", "scripts/fid01/fid01_designs.py",
                "scripts/fid01/fid01_build.py", REG_REL, f"{EV_REL}/plan_review/adoption.md", f"{EV_REL}/source_review/adoption.md", "scripts/screen01/INTERFACE.md", INFRA_REL, ROWS_REL)
FID_ANALYSIS, M2_ANALYSIS = ROOT / "docs/evidence/fid01_2026_10_21/analysis.json", ROOT / "docs/evidence/unc01_2026_10_20/analysis.json"
FID_SHA = "b89203d0c8ec588bfa83a87d67f81e2a731edd37655265d0a3f8cd6f9d863dd1"
M2_SHA = "ee71c6d6983fee72a171c9188c117a478dafe51e2fd1488f15448321687f8e24"

# ---- registered constants (§6; re-read from the FID / M2 analysis files by `coefficients`) ------------------------------------------------------------
RESP = ("downforce", "drag")
G_MIN, J_B48, X_STAR = 0.027030580470324268, 0.26577921974115387, 7.184166586553256e-3          # x* = g_min J_b,48
FLOOR = {"downforce": 0.00020904201605451784, "drag": 0.000136408347135453}
NC_REF, NC_SE, NC_FLOOR, NC_Z_MAX = -0.0016476407624087992, 8.534104568937632e-05, 3e-4, 3.5
S_D, S_D_OF, E2 = 0.003399676556346094, 0.006337479927119433, 1.8071267650359157e-3             # E2 = 2 S_d J_b,48 (R3_E2_EXCEEDED)
SIGMA_DISC = {"central": 5.61e-4, "upper": 1.4474126675928642e-3}
RETENTION = {"central": 0.655, "pessimistic": 0.57}
XV_FLOOR = 0.012674959854238867
REF_DF, REF_SIGMA = 1.326e-2, 1.0e-4     # §3.5 downforce reference (FID C1) and its model SD
IMPLAUSIBLE, REPEAT_TOL, RATIO_BAND, AMP_TOL = 0.25, FLOOR["downforce"], (0.8, 1.25), 0.25
FIT_COND_MAX, MIN_F32 = 20.0, 3
BUDGET_CAP_S, EST_S, SETUP_S = 86400, {"flow_32": 415, "flow_48": 2340}, 260

PHASES = {"g1": ("11", "12"), "g2": ("11", "12"), "f32": ("11", "13", "14", "15", "16"), "f48": ("13", "14")}
KERNELS = {"g1": ("g1k11", "g1k12"), "g2": ("g2",), "f32": ("f32a", "f32b"), "f48": ("f48k13", "f48k14")}
CAMPAIGN_IDS = {"g1": ("screen01",), "g2": ("screen01_g2",), "f32": ("screen01_f",), "f48": ("screen01_f48",)}
STAGE_GROUPS = {"rs": ("g1",), "finalist": ("g1", "g2"), "main": ("g1", "g2", "f32", "f48")}
REG_RUNS = {"g1k11": (39, "flow_32"), "g1k12": (38, "flow_32"), "g2": (10, "flow_32"), "f48k13": (3, "flow_48"), "f48k14": (3, "flow_48"), "f32a": (12, "flow_32"),
            "f32b": (10, "flow_32")}
GATING_KEYS = ("name", "u", "target_index", "y_pred", "z_pred", "admissible")   # the gating record of T (INTERFACE.md); rs.json adds the whole admissibility row
RANK = {"axial": 0, "design": 1, "proposal": 2}   # registered tie order (§5.4)
CMP = {"rs": ("data_loss", "fit", "rs_fit_poor", "rs_not_fit", "u_star_1", "y_star_1", "pool_limited_pre", "targets", "gated", "stop_after", "proposals", "g1_controls"),
       "finalist": ("data_loss", "candidates", "finalist", "futility", "search_complete", "pool_limited", "r_best", "K_opt", "K_rand", "proposals_from_gating", "g1_controls")}
CMP["main"] = CMP["finalist"] + ("outcome", "cause", "G", "D", "R3", "NC", "determinism", "generation_drift", "controls", "selection_bias", "confirmation")
GRID_N = P.N_GRID     # tests may lower it; the checker always uses 81 per axis
CHECKER = None        # tests inject a checker module; None = scripts/screen01/screen01_check.py
_GRIDS: dict = {}


def coefficients(fid=FID_ANALYSIS, m2=M2_ANALYSIS) -> dict:
    """§6: every constant above is re-read from the FID and M2 analyses (by SHA-256 and by value); a mismatch is a defect."""
    SC.req(SC.sha256_path(fid) == FID_SHA, "the FID-01 analysis.json differs from the registered SHA-256")
    SC.req(SC.sha256_path(m2) == M2_SHA, "the M2 analysis.json differs from the registered SHA-256")
    m2a = SC.jload(m2)
    q, r32 = m2a["Q4_E2"]["downforce"]["common_phases"], m2a["grids"]["flow_32"]["differences"]["v18__roll_p25"]   # S_d, J_b,48, the floors, the NC reference
    a = SC.jload(fid)
    mg, tier_a = a["m3b_min_gain"], a["tiers"]["A"]
    x = np.array([a["wl_flow32"][n]["downforce"]["delta_bar_n"] for n in tier_a])
    y = np.array([a["per_design"][n]["of_levels"]["V1"]["delta_bar_n"] for n in tier_a])
    slope = float(x @ y / (x @ x))
    sd = float(np.sqrt(((y - slope * x) ** 2).sum() / (len(x) - 1)))
    ret = y / x
    got = {"g_min": mg["min_gain_relative"], "x_star": mg["x_star_n"], "J_b48": q["denominator_n"], "S_d": q["S_d"], "S_d_OF": a["S_d_OF"], "g3_residual_sd": a["G3_set"]["residual_sd_n"],
           "floor": (r32["downforce"]["sigma_d_n"], r32["drag"]["sigma_d_n"]), "nc": (r32["downforce"]["delta_bar_n"], r32["downforce"]["se_n"]), "e2": 2 * q["S_d"] * q["denominator_n"]}
    want = {"g_min": G_MIN, "x_star": X_STAR, "J_b48": J_B48, "S_d": S_D, "S_d_OF": S_D_OF, "g3_residual_sd": SIGMA_DISC["upper"], "floor": (FLOOR["downforce"], FLOOR["drag"]),
            "nc": (NC_REF, NC_SE), "e2": 2 * S_D * J_B48}
    SC.req(got == want and abs(E2 - 2 * S_D * J_B48) < 1e-18 and abs(G_MIN * J_B48 - X_STAR) < 1e-17, "FID / M2 coefficients differ from the registered values")
    SC.req(abs(slope - RETENTION["central"]) < 5e-4 and abs(sd - SIGMA_DISC["central"]) < 5e-7 and abs(ret.min() - RETENTION["pessimistic"]) < 5e-3
           and abs(ret.std(ddof=1) - 0.058) < 5e-4 and abs(2 * S_D_OF - XV_FLOOR) < 1e-15
           and abs(a["wl_flow32"]["v18__camber_m11.3_reflex_m11.3"]["downforce"]["delta_bar_n"] - REF_DF) < 5e-6, "the tier-A WaterLily-to-V1 statistics or the C1 reference differ from the registered values")
    return {"fid_analysis_sha256": FID_SHA, "m2_analysis_sha256": M2_SHA, "tier_a_slope": slope, "tier_a_residual_sd_n": sd, "tier_a_retention_min": float(ret.min()),
            "tier_a_retention_sd": float(ret.std(ddof=1))}


# ---- estimators (§5.1) ----------------------------------------------------------------------------------------------------------------------------
def names(roles, role) -> list:
    return sorted((n for n, r in roles.items() if r["role"] == role), key=lambda n: roles[n]["order"])


def parent_of(roles) -> str:
    (n,) = names(roles, "parent")
    return n


def finite_run(r) -> bool:
    return bool(r["ok"]) and all(r[k] is not None and math.isfinite(r[k]) for k in RESP)


def valid_runs(T):
    """§5.1 DATA_LOSS: valid[group][state][phase] = (downforce, drag) of every run kept, and the sorted `state@group@phase` of every run lost (ok false, null /
    non-finite force, or |F - F_parent| > 0.25 |F_parent| for either response against the valid parent run of the same group and phase).  A run without a valid
    parent run at its phase enters no estimator (it has no common phase) and is not listed (§5.11.1); the parent's own lost runs are."""
    par = parent_of(T["roles"])
    valid, loss = {}, []
    for g, runs in T["runs"].items():
        pr = {ph: r for ph, r in runs.get(par, {}).items() if finite_run(r)}
        valid[g] = {}
        for s, by in runs.items():
            for ph, r in by.items():
                bad = (not finite_run(r) and (s == par or ph in pr)) or (finite_run(r) and s != par and ph in pr and any(abs(r[k] - pr[ph][k]) > IMPLAUSIBLE * abs(pr[ph][k]) for k in RESP))
                if bad:
                    loss.append(f"{s}@{g}@{ph}")
                else:
                    valid[g].setdefault(s, {})[ph] = (r["downforce"], r["drag"])
    return valid, sorted(loss)


def diffs(V, g, s, par) -> dict:
    """phase -> (downforce, drag) difference s - parent over the phases common to s and the valid parent runs of group g, in phase order."""
    p, v = V.get(g, {}).get(par, {}), V.get(g, {}).get(s, {})
    return {ph: (v[ph][0] - p[ph][0], v[ph][1] - p[ph][1]) for ph in sorted(set(p) & set(v), key=int)}


def tcrit(n):
    """One-sided t_{0.95, n-1}; None for n < 2 (a t-based label with one phase is null, §5.11.2)."""
    return A.tq(0.95, n - 1) if n >= 2 else None


def est(d, floor) -> dict:
    """Delta_bar, sigma_d (|Phi| - 1 dof, as M2), SE_eff = max(sigma_d, floor) / sqrt(|Phi|); with |Phi| = 1 SE_eff = floor."""
    n = len(d)
    sd = A.stats(list(d))["sigma_d_n"] if n >= 2 else None
    return {"P": n, "delta_bar": sum(d) / n, "sigma_d": sd, "se_eff": max(sd or 0.0, floor) / math.sqrt(n)}


def estimates(V, g, s, par):
    dd = diffs(V, g, s, par)
    return {"phases": list(dd), **{r: est([v[i] for v in dd.values()], FLOOR[r]) for i, r in enumerate(RESP)}} if dd else None


def get_grid(n):
    if n not in _GRIDS:
        _GRIDS[n] = P.grid_u(n)
    return _GRIDS[n]


# ---- §5.2 response surface and the gated refinement -------------------------------------------------------------------------------------------------
def fit_stage(T, V) -> dict:
    roles, par = T["roles"], parent_of(T["roles"])
    pts = [n for n in names(roles, "axial") + names(roles, "design") if estimates(V, "g1", n, par)]
    E = {n: estimates(V, "g1", n, par) for n in pts}
    out = {"points": pts, "est": E, "rank": 0, "cond": None, "ok": False, "by": None, "bz": None, "sd": {r: None for r in RESP}, "pooled": {r: None for r in RESP}}
    if pts:
        U = np.array([roles[n]["u"] for n in pts], float)
        by, sy, rank, cond = P.fit9(U, [E[n]["downforce"]["delta_bar"] for n in pts])
        bz, sz, _, _ = P.fit9(U, [E[n]["drag"]["delta_bar"] for n in pts])
        out.update(rank=rank, cond=cond if rank == 9 else None, ok=bool(rank == 9 and cond <= FIT_COND_MAX), by=by, bz=bz, sd={"downforce": sy, "drag": sz},
                   pooled={r: math.sqrt(sum(E[n][r]["se_eff"] ** 2 for n in pts) / len(pts)) for r in RESP})
    return out


def exclude(T) -> set:
    """Names already evaluated when the refinement ran: every registered G1 state (the proposals are not)."""
    return {n for n, r in T["roles"].items() if r["role"] != "proposal"}


def replay_oracle(gating):
    """propose()'s is_admissible answering from the recorded gating record, in order; a request out of order or beyond the record refuses."""
    pos = {"i": 0}

    def ask(u):
        i = pos["i"]
        SC.req(i < len(gating), "propose() gates more points than the gating record holds")
        SC.req(gating[i]["name"] == P.D.name(P.u_to_spec(u)), f"gating record point {i} is not the point propose() gates")
        pos["i"] += 1
        return bool(gating[i]["admissible"])
    return ask, pos


def rs_gate(T, is_admissible, n_grid=None) -> dict:
    """The G1 -> proposals step: fit, then `screen01_pool.propose` with the injected is_admissible; returns T with the gating record (gated order)."""
    n_grid = n_grid or GRID_N
    V, _ = valid_runs(T)
    fit = fit_stage(T, V)
    gating = []
    if fit["ok"]:
        res = P.propose(fit["by"], fit["bz"], is_admissible, exclude=exclude(T), n_grid=n_grid, grid=get_grid(n_grid))
        gating = [{"name": g["name"], "u": g["u"], "target_index": list(P.TARGETS).index(g["target"]), "y_pred": g["y_pred"], "z_pred": g["z_pred"], "admissible": g["admissible"]}
                  for g in res["gated"]]
    return {**T, "gating": gating}


def rs_part(T, V, fit) -> dict:
    tg = {f"{t:g}": {"u_star": None, "y_pred": None, "z_pred": None} for t in P.TARGETS}
    gated, props, pstates = [], [], []
    if fit["ok"]:
        ask, pos = replay_oracle(T["gating"])
        r = P.propose(fit["by"], fit["bz"], ask, exclude=exclude(T), n_grid=GRID_N, grid=get_grid(GRID_N))
        SC.req(pos["i"] == len(T["gating"]), "the gating record holds points propose() does not gate")
        for rec, g in zip(T["gating"], r["gated"]):
            SC.req(rec["target_index"] == list(P.TARGETS).index(g["target"]) and max(abs(a - b) for a, b in zip(rec["u"], g["u"])) <= 1e-12
                   and abs(rec["y_pred"] - g["y_pred"]) <= 1e-12 and abs(rec["z_pred"] - g["z_pred"]) <= 1e-12, f"gating record {rec['name']} differs from propose()")
        for tau in P.TARGETS:
            a = r["argmax"][f"{tau:g}"]
            if a:
                tg[f"{tau:g}"] = {"u_star": a["u"], "y_pred": a["y_pred"], "z_pred": a["z_pred"]}
        gated = [[list(P.TARGETS).index(g["target"]), [round(x, 6) for x in g["u"]]] for g in r["gated"]]
        for i, p in enumerate(r["proposals"]):
            props.append(next(j for j, g in enumerate(r["gated"]) if g["name"] == p["name"] and g["target"] == p["target"]))
            pstates.append({"name": p["name"], "u": p["u"], "spec": P.u_to_spec(p["u"]), "target_index": list(P.TARGETS).index(p["target"]), "y_pred": p["y_pred"],
                            "z_pred": p["z_pred"], "rank": i})
    else:
        SC.req(not T["gating"], "a gating record exists although the surface is not fit")
    ys = tg["1"]["y_pred"]
    sd = fit["sd"]
    flat = fit["ok"] and None not in sd.values()
    return {"fit": {"downforce": {"coef": fit["by"].tolist() if fit["ok"] else None}, "drag": {"coef": fit["bz"].tolist() if fit["ok"] else None}, "rank": fit["rank"],
                    "cond": fit["cond"], "residual_sd": {r: (sd[r] if fit["ok"] else None) for r in RESP}},
            "rs_fit_poor": any(sd[r] > 3 * fit["pooled"][r] for r in RESP) if flat else None, "rs_not_fit": not fit["ok"],
            "rs_fit_label": "RS_FIT_UNDEFINED" if not flat else "RS_FIT_POOR" if any(sd[r] > 3 * fit["pooled"][r] for r in RESP) else "RS_FIT_OK",
            "u_star_1": tg["1"]["u_star"], "y_star_1": ys, "pool_limited_pre": ys is not None and ys >= X_STAR, "targets": tg, "gated": gated, "stop_after": len(gated),
            "proposals": props, "proposal_states": pstates, "pooled_se_eff": fit["pooled"], "fit_points": fit["points"],
            "lack_of_fit_ratio": {r: (sd[r] / fit["pooled"][r] if flat else None) for r in RESP}, "g1_controls": g1_controls(T, V)}


# ---- §5.4 finalist ----------------------------------------------------------------------------------------------------------------------------------
def pick(cands, roles):
    """The feasible candidate with the largest exploration downforce difference; exact ties go to the registered order."""
    ok = [n for n, c in cands.items() if c["feasible"]]
    return min(ok, key=lambda n: (-cands[n]["delta_bar"]["downforce"], RANK.get(roles[n]["role"], 3), roles[n]["order"])) if ok else None


def confirmation_runs(roles, par, f, rb) -> dict:
    """The F-stage run lists (§2, §3.5): flow_48 phases 13, 14 with parent, finalist, R-best; flow_32 phases 13-16 with parent, finalist, R-best, M, NC, plus the parent
    replay at 11 and a within-kernel parent_repeat at 13 in f32a; R-best / M are dropped when empty."""
    sts = [par, f, *([rb] if rb else []), *names(roles, "manual"), *names(roles, "nc")]
    return {"f48": {"phases": ["13", "14"], "states": [par, f, *([rb] if rb else [])]},
            "f32": {"phases": ["13", "14", "15", "16"], "states": sts, "parent_replay_phase": "11", "parent_repeat": [*names(roles, "parent_repeat"), "13"]}}


def finalist_part(T, V, rs, fit) -> dict:
    roles, par, lost = T["roles"], parent_of(T["roles"]), set(T["lost_kernels"])
    props = names(roles, "proposal")
    SC.req(props == [p["name"] for p in rs["proposal_states"]], "the proposal states differ from the proposals the gating record yields")
    opt, rnd = names(roles, "axial") + names(roles, "design") + props, names(roles, "random")
    cands = {}
    for n in opt + rnd:
        e = estimates(V, "g2" if roles[n]["role"] == "proposal" else "g1", n, par)
        if e:
            cands[n] = {"delta_bar": {r: e[r]["delta_bar"] for r in RESP}, "se_eff": {r: e[r]["se_eff"] for r in RESP}, "P": e["downforce"]["P"], "phases": e["phases"],
                        "feasible": e["drag"]["delta_bar"] <= 0.0}
    none = {"delta_bar": {r: None for r in RESP}, "se_eff": {r: None for r in RESP}, "P": 0, "feasible": False, "phases": []}
    c_opt = {n: cands.get(n, none) for n in opt}
    best = pick(c_opt, roles)
    futility = None
    if best is None:
        futility = "NO_FEASIBLE_CANDIDATE"
    elif c_opt[best]["delta_bar"]["downforce"] < X_STAR - 3 * c_opt[best]["se_eff"]["downforce"]:
        futility = "GAIN_BELOW_MIN_AT_SELECTION"
    g1_full = len(V.get("g1", {}).get(par, {})) == len(PHASES["g1"]) and all(n in fit["est"] and len(fit["est"][n]["phases"]) == len(PHASES["g1"])
                                                                              for n in names(roles, "axial") + names(roles, "design"))
    props_full = all(c_opt[n]["P"] == len(PHASES["g2"]) for n in props)
    g1_kernel = bool(lost & set(KERNELS["g1"]))
    causes = (["DATA_G1"] if g1_kernel or not g1_full else []) + (["DATA_REFINE"] if not fit["ok"] else []) + (["DATA_G2"] if fit["ok"] and not props_full else [])    # §5.11.7
    complete = g1_full and fit["ok"] and props_full
    feas_gain = any(c["feasible"] and c["delta_bar"]["downforce"] >= X_STAR for c in c_opt.values())
    r_best = pick({n: cands[n] for n in rnd if n in cands}, roles)
    ref = estimates(V, "g1", names(roles, "ref")[0], par) if names(roles, "ref") else None
    ref_ok = None if not ref else bool(abs(ref["downforce"]["delta_bar"] - REF_DF) <= 3 * math.hypot(ref["downforce"]["se_eff"], REF_SIGMA))   # §3.5, label only
    amp = lambda ns: float(np.median([max(abs(x) for x in roles[n]["u"]) for n in ns])) if ns else None   # noqa: E731
    a_opt, a_rnd = amp(names(roles, "axial") + names(roles, "design") + props), amp(rnd)
    return {"REF_CONSISTENT": ref_ok, "ref_estimate": ref, "amplitude_median_u_inf": {"opt": a_opt, "random": a_rnd},
            "AMPLITUDE_MISMATCH": None if a_opt is None or a_rnd is None else bool(abs(a_opt - a_rnd) > AMP_TOL),
            "I_candidates": {n: None if c["delta_bar"]["downforce"] is None else c["delta_bar"]["downforce"] / J_B48 for n, c in c_opt.items()}, "candidates": {n: {k: v for k, v in c.items() if k != "phases"} for n, c in c_opt.items()}, "finalist": None if futility else best, "futility": futility,
            "search_complete": complete, "pool_limited": bool(rs["pool_limited_pre"] and not feas_gain), "r_best": r_best, "K_opt": len(opt), "K_rand": len(rnd),
            "proposals_from_gating": [p["name"] for p in rs["proposal_states"]], "selected_before_futility": best, "incomplete_causes": [] if complete else causes,
            "random_estimates": {n: cands[n] for n in rnd if n in cands}, "exploration_phases": {n: c["phases"] for n, c in {**cands, **c_opt}.items()},
            "confirmation_runs": None if futility else confirmation_runs(roles, par, best, r_best)}


# ---- §5.5 - §5.7 confirmation -----------------------------------------------------------------------------------------------------------------------
def nc_stage(T, V, g) -> dict:
    roles, par = T["roles"], parent_of(T["roles"])
    roll = names(roles, "nc")
    d = [v[0] for v in diffs(V, g, roll[0], par).values()] if roll else []
    if not d:
        return {"z": None, "label": None}
    z = abs(sum(d) / len(d) - NC_REF) / math.hypot(NC_FLOOR / math.sqrt(len(d)), NC_SE)
    return {"z": z, "label": "CONSISTENT" if z <= NC_Z_MAX else "NOT_CONSISTENT"}


def raw(T, g, s, ph):
    r = T["runs"].get(g, {}).get(s, {}).get(ph)
    return (r["downforce"], r["drag"]) if r is not None and finite_run(r) else None


def max_diff(a, b):
    return None if a is None or b is None else {r: abs(a[i] - b[i]) for i, r in enumerate(RESP)}


REPEAT_PHASE = {"g1": "11", "f32": "13"}   # g1k11 and f32a


def g1_controls(T, V) -> dict:
    """§5.11.18: the G1 chain controls as `main` computes them for §5.8 step 2 (NC at G1, g1k11 determinism); invalid_at_step_2 decides the INVALID outcome early."""
    nc, det = nc_stage(T, V, "g1"), repeat_check(T, "g1")
    return {"NC_g1": nc, "determinism_g1k11": det, "invalid_at_step_2": bool(nc["label"] == "NOT_CONSISTENT" or det["nondeterminism"])}


def repeat_check(T, g) -> dict:
    """§5.11.10: the parent_repeat of the kernel reproduces the parent run of the same phase within the downforce floor (both responses, strict), judged on the raw runs.
    Repeat absent or not ok (or no finite ok parent run): not judged.  A non-finite repeat force against a finite ok parent run: NONDETERMINISM."""
    par, reps, ph = parent_of(T["roles"]), names(T["roles"], "parent_repeat"), REPEAT_PHASE[g]
    r = T["runs"].get(g, {}).get(reps[0], {}).get(ph) if reps else None
    p = T["runs"].get(g, {}).get(par, {}).get(ph)
    if r is None or not r["ok"] or p is None or not finite_run(p):
        return {"max_abs_diff": None, "nondeterminism": False, "judged": False}
    if not finite_run(r):
        return {"max_abs_diff": None, "nondeterminism": True, "judged": True}
    d = max_diff(raw(T, g, reps[0], ph), raw(T, g, par, ph))
    return {"max_abs_diff": d, "nondeterminism": bool(max(d.values()) > REPEAT_TOL), "judged": True}


def drift_check(T) -> dict:
    par = parent_of(T["roles"])
    d = max_diff(raw(T, "g1", par, "11"), raw(T, "f32", par, "11"))
    return {"max_abs_diff": d, "drift": bool(d and max(d.values()) > REPEAT_TOL)}


def g_rule(e) -> dict:
    d, se = e["downforce"]["delta_bar"], e["downforce"]["se_eff"]
    return {"decision": "PASS" if d >= X_STAR and d > 3 * se else "UNRESOLVED" if d >= X_STAR else "FAIL",
            "GAIN_RESOLVED_ABOVE_MIN": None if (t := tcrit(e["downforce"]["P"])) is None else bool(d - t * se >= X_STAR)}


def d_rule(e) -> dict:
    d, t = e["drag"]["delta_bar"], tcrit(e["drag"]["P"])
    w = None if t is None else t * e["drag"]["se_eff"]
    lab = None if w is None else ("PASS_RESOLVED" if d + w <= 0 else "PASS_UNRESOLVED") if d <= 0 else ("VIOLATION_UNRESOLVED" if d <= w else "VIOLATION_RESOLVED")
    return {"decision": "PASS" if d <= 0 else "VIOLATION", "label": lab}


def r3_rule(e48, e32, V, s, par) -> dict:
    d, se = e48["downforce"]["delta_bar"], e48["downforce"]["se_eff"]
    both = [ph for ph in e48["phases"] if e32 and ph in e32["phases"]]
    d32 = diffs(V, "f32", s, par)
    m32 = [sum(d32[ph][i] for ph in both) / len(both) if both else None for i in (0, 1)]
    ratio = d / m32[0] if both and m32[0] else None
    return {"label": "R3_CONFIRMED" if d > 3 * se else "R3_SIGN_SPLIT" if d <= 0 else "R3_UNRESOLVED",
            "R3_RATIO_IN_BAND": None if ratio is None else RATIO_BAND[0] <= ratio <= RATIO_BAND[1], "G48_ABOVE_MIN": bool(d >= X_STAR), "G48_MARGIN": d - X_STAR,
            "R3_E2_EXCEEDED": None if not both else bool(abs(d - m32[0]) > E2), "R3_DRAG_SAME_SIGN": None if not both else bool(e48["drag"]["delta_bar"] * m32[1] > 0)}


def control_label(V, g_a, a, g_b, b, par, phases, names3) -> str:
    """Per phase e_k = Delta_DF(a) - Delta_DF(b); a beats b if mean - t SE > 0, b beats a if mean + t SE < 0, else unresolved (needs >= 2 common phases)."""
    da, db = diffs(V, g_a, a, par), diffs(V, g_b, b, par)
    e = [da[ph][0] - db[ph][0] for ph in phases if ph in da and ph in db]
    if len(e) < 2:
        return names3[2]
    s = A.stats(e)
    w = s["t"] * s["se_n"]
    return names3[0] if s["delta_bar_n"] - w > 0 else names3[1] if s["delta_bar_n"] + w < 0 else names3[2]


def e_max_normals(K) -> float:
    from scipy import integrate, stats
    return integrate.quad(lambda x: x * K * stats.norm.pdf(x) * stats.norm.cdf(x) ** (K - 1), -12, 12, epsabs=1e-13, epsrel=1e-13, limit=400)[0]


def confirm_est(e) -> dict:
    return {"P": e["downforce"]["P"], **{k: {r: e[r][k] for r in RESP} for k in ("delta_bar", "sigma_d", "se_eff")}}


def passes(V, s, par):
    """Whether a state passes G, D and R3 on its own confirmation data (needs >= 3 flow_32 phases and >= 1 flow_48 phase)."""
    e32, e48 = estimates(V, "f32", s, par), estimates(V, "f48", s, par)
    return bool(e32 and e48 and e32["downforce"]["P"] >= MIN_F32 and g_rule(e32)["decision"] == "PASS" and d_rule(e32)["decision"] == "PASS"
                and r3_rule(e48, e32, V, s, par)["label"] == "R3_CONFIRMED")


CONFIRMATION_KERNELS = ("f32a", "f32b", "f48k13", "f48k14")


def main_part(T, V, rs, fin) -> dict:
    """§5.8 on T.  The descriptive blocks (confirmation, G, D, R3, controls, selection_bias) are computed whenever their data exist, whatever the outcome path:
    confirmation always {f32, f48}; G, D, selection_bias need |Phi_s| >= 3; R3 needs flow_48 data; controls need a finalist (K_MISMATCH is always given)."""
    roles, par = T["roles"], parent_of(T["roles"])
    f, rb, man = fin["finalist"], fin["r_best"], names(roles, "manual")
    nc1, ncf = nc_stage(T, V, "g1"), nc_stage(T, V, "f32")
    det = {"g1k11": repeat_check(T, "g1"), "f32a": repeat_check(T, "f32")}
    e32 = estimates(V, "f32", f, par) if f else None
    e48 = estimates(V, "f48", f, par) if f else None
    ok3 = bool(e32 and e32["downforce"]["P"] >= MIN_F32)
    g, d = (g_rule(e32), d_rule(e32)) if ok3 else (None, None)
    r3 = r3_rule(e48, e32, V, f, par) if e48 else None
    cphases = [ph for ph in PHASES["f32"] if ph != "11"]
    ctl = {"OPT_VS_RANDOM": None if not f else "RANDOM_NO_FEASIBLE" if rb is None else control_label(V, "f32", f, "f32", rb, par, cphases, ("OPT_BEATS_RANDOM", "RANDOM_BEATS_OPT", "OPT_RANDOM_UNRESOLVED")),
           "OPT_VS_MANUAL": None if not f else "MANUAL_NONE" if not man else control_label(V, "f32", f, "f32", man[0], par, cphases, ("OPT_BEATS_MANUAL", "MANUAL_BEATS_OPT", "OPT_MANUAL_UNRESOLVED")),
           "RANDOM_FEASIBLE_GAIN": bool(rb is not None and passes(V, rb, par)), "K_MISMATCH": fin["K_opt"] != fin["K_rand"]}
    sb = None
    ests = lambda n: {gg: e for gg in ("f32", "f48") if (e := estimates(V, gg, n, par))} if n else {}   # noqa: E731
    detail = {"I_confirmation": {gg: {r: e[r]["delta_bar"] / J_B48 for r in RESP} for gg, e in ((("f32", e32), ("f48", e48))) if e},
              "phases_used": {"finalist_confirmation": {gg: e["phases"] for gg, e in ests(f).items()}, "r_best_confirmation": {gg: e["phases"] for gg, e in ests(rb).items()},
                              "manual_confirmation": {gg: e["phases"] for gg, e in ests(man[0] if man else None).items()}, "finalist_exploration": fin["exploration_phases"].get(f) if f else None}}
    if ok3:
        sel = fin["candidates"][f]
        i_s, k = e32["downforce"]["delta_bar"] / J_B48, fin["K_opt"]
        emax = e_max_normals(k)
        b = {c: emax * SIGMA_DISC[c] for c in SIGMA_DISC}
        gx = {"central": RETENTION["central"] * (i_s - b["central"] / J_B48), "pessimistic": RETENTION["pessimistic"] * (i_s - b["upper"] / J_B48)}
        sb = {"b_K": b, "g_XV_exp": gx, "XV_MARGIN": {c: "XV_MARGIN_ADEQUATE" if v >= XV_FLOOR else "XV_MARGIN_THIN" for c, v in gx.items()}}
        w = tcrit(e32["drag"]["P"]) * e32["drag"]["se_eff"]
        f_exp = "g2" if roles[f]["role"] == "proposal" else "g1"
        detail.update({"placement_noise_bias_n": sel["delta_bar"]["downforce"] - e32["downforce"]["delta_bar"], "I_s": i_s, "K_opt": k, "E_max_K": emax,
                       "selection_bias_inputs": {"K": k, "E_max_K": emax, "sigma_disc": dict(SIGMA_DISC), "retention": dict(RETENTION), "xv_floor": XV_FLOOR},
                       "placement_noise_bias_se_n": math.hypot(sel["se_eff"]["downforce"], e32["downforce"]["se_eff"]),
                       "xv_drag_margin": {"delta_bar_drag_n": e32["drag"]["delta_bar"], "interval_90_n": [e32["drag"]["delta_bar"] - w, e32["drag"]["delta_bar"] + w],
                                          "statement": "the finalist's drag neutrality relies on the OpenFOAM drag retention of camber (untested in FID-01; tested 0.58-0.87 for pitch, reflex and combinations)"},
                       "control_estimates": {c: {gg: confirm_est(e) for gg, e in ests(n).items()} for c, n in (("r_best", rb), ("manual", man[0] if man else None)) if n},
                       "exploration_controls": {"OPT_VS_RANDOM": None if rb is None else control_label(V, f_exp, f, "g1", rb, par, PHASES["g1"], ("OPT_BEATS_RANDOM", "RANDOM_BEATS_OPT", "OPT_RANDOM_UNRESOLVED")),
                                                "OPT_VS_MANUAL": None if not man else control_label(V, f_exp, f, "g1", man[0], par, PHASES["g1"], ("OPT_BEATS_MANUAL", "MANUAL_BEATS_OPT", "OPT_MANUAL_UNRESOLVED"))}})
    out = {"NC": {"g1": nc1, "f32": ncf}, "determinism": det, "generation_drift": drift_check(T), "G": g, "D": d, "R3": r3, "controls": ctl, "selection_bias": sb,
           "confirmation": {"f32": confirm_est(e32) if e32 else None, "f48": confirm_est(e48) if e48 else None}, "detail": detail}

    def done(outcome, cause):
        return {"outcome": outcome, "cause": cause, **out}
    if not V.get("g1", {}).get(par) or nc1["label"] is None:                                                                    # step 1
        return done("SCREEN01_INCOMPLETE", ["DATA_G1"])
    inv = [c for c, bad in (("NC_G1", nc1["label"] == "NOT_CONSISTENT"), ("NONDETERMINISM_G1K11", det["g1k11"]["nondeterminism"])) if bad]     # step 2
    if inv:
        return done("SCREEN01_INVALID", inv)
    if f is None:                                                                                                               # step 3
        return done("SCREEN01_INCOMPLETE", fin["incomplete_causes"]) if not fin["search_complete"] else done("SCREEN01_NO_GAIN", [fin["futility"]])
    if any(T.get("not_pushed", {}).get(k) == "BUDGET" for k in CONFIRMATION_KERNELS):                                           # step 4: F not completed first (§5.11.15)
        return done("SCREEN01_INCOMPLETE", ["BUDGET"])
    if not ok3 or e48 is None or ncf["label"] is None:
        return done("SCREEN01_INCOMPLETE", ["DATA_F"])
    inv = [c for c, bad in (("NC_F", ncf["label"] == "NOT_CONSISTENT"), ("NONDETERMINISM_F32A", det["f32a"]["nondeterminism"])) if bad]    # step 5
    if inv:
        return done("SCREEN01_INVALID", inv)
    fails = [c for c, bad in (("GAIN_BELOW_MIN", g["decision"] == "FAIL"), ("DRAG_VIOLATION", d["decision"] != "PASS"), ("GRID_SIGN_SPLIT", r3["label"] == "R3_SIGN_SPLIT")) if bad]   # step 6
    if fails:
        return done("SCREEN01_NO_GAIN", fails)
    unres = [c for c, bad in (("G_UNRESOLVED", g["decision"] == "UNRESOLVED"), ("R3_UNRESOLVED", r3["label"] == "R3_UNRESOLVED")) if bad]   # step 7
    return done("SCREEN01_INCONCLUSIVE", unres) if unres else done("SCREEN01_GAIN", [])                                         # step 8


def compute(T) -> dict:
    """Every quantity of the stage in T["stage"] (comparable keys CMP[stage] plus detail); a pure function of T."""
    V, loss = valid_runs(T)
    fit = fit_stage(T, V)
    rs = {**rs_part(T, V, fit), "data_loss": loss}
    if T["stage"] == "rs":
        return rs
    fin = {**finalist_part(T, V, rs, fit), "data_loss": loss, "g1_controls": rs["g1_controls"]}
    if T["stage"] == "finalist":
        return {**fin, "rs": rs}
    return {**fin, "rs": rs, **main_part(T, V, rs, fin)}


# ---- cross-check against the independent implementation -----------------------------------------------------------------------------------------------
def canon(x):
    """Normalise numeric-looking dict keys (1, 1.0, "1") to "%g" so that key spelling never counts as a discrepancy."""
    if isinstance(x, dict):
        def key(k):
            try:
                return f"{float(k):g}" if not isinstance(k, bool) else str(k)
            except (TypeError, ValueError):
                return k
        return {key(k): canon(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        return x.item()
    return x


def cross_check(mine, T, checker=None) -> dict:
    """Refuse (ValueError) unless screen01_check.check(T) agrees with mine on every comparable key; returns the record to store."""
    chk = checker or CHECKER or importlib.import_module("screen01_check")
    theirs = chk.check(copy.deepcopy(T))
    stage = T["stage"]
    bad = chk.compare(canon({k: mine[k] for k in CMP[stage]}), canon(theirs), stage)
    SC.req(not bad, f"cross-check discrepancies (analyzer or checker defect, nothing written): {list(bad)}")
    path = Path(getattr(chk, "__file__", "") or "")
    return {"checker": "scripts/screen01/screen01_check.py", "checker_sha256": SC.sha256_path(path) if path.is_file() else None, "discrepancies": [], "stage": stage}


# ---- loading ----------------------------------------------------------------------------------------------------------------------------------------
def rel(p) -> str:
    """Repo-relative POSIX path (the key of every freeze record's `file_sha256`); a path outside the repository keeps its absolute POSIX form."""
    p = Path(p).resolve()
    try:
        return p.relative_to(Path(ROOT).resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def freeze(name):
    p = EV / f"{name}.json"
    SC.req(p.exists(), f"{name}.json is missing: the analysis binds to the frozen records (§10)")
    return SC.jload(p)


def check_frozen(fz, path, what="file"):
    """The file's SHA-256 equals the one the freeze record holds under its repo-relative POSIX key (never a basename: freeze 1 also binds the UNC-01 states.json)."""
    key = Path(path).as_posix() if not Path(path).is_absolute() else rel(path)
    full = Path(ROOT) / key
    SC.req(full.is_file() and fz["file_sha256"].get(key) == SC.sha256_path(full), f"{key}: not the {what} frozen in {fz.get('kind', 'the freeze record')}")


def campaign_entry(fz, campaign) -> dict:
    """The campaign record of a freeze (freeze 2: `campaign`; 2.1: `g2`; 3: `campaigns[cid]`) that names this campaign file's SHA-256."""
    sha = SC.sha256_path(campaign)
    cands = [fz.get("campaign"), fz.get("g2"), *(fz.get("campaigns") or {}).values()]
    hits = [r for r in cands if isinstance(r, dict) and r.get("campaign_sha256") == sha]
    SC.req(len(hits) == 1 and hits[0].get("prerun_freeze_sha256"), f"{campaign}: no campaign record with a prerun freeze in {fz.get('kind', 'the freeze record')}")
    return hits[0]


CHAIN = (("freeze2", "freeze1"), ("freeze2_1", "freeze2"), ("freeze3", "freeze2_1"))


def check_chain(fz):
    """Each freeze N holds the SHA-256 of freeze N-1 as it is on disk (§10)."""
    for n, prev in CHAIN:
        if n in fz and prev in fz:
            SC.req(fz[n]["file_sha256"].get(f"{EV_REL}/{prev}.json") == SC.sha256_path(EV / f"{prev}.json"), f"{n}.json does not bind {prev}.json as it is on disk")


def check_environment(fz1):
    """The written-once steps run in the environment frozen at freeze 1 (§5.11.20)."""
    now = {"python": platform.python_version(), **{m: importlib.metadata.version(m) for m in ("numpy", "scipy", "scikit-image")}}
    SC.req(all(fz1["environment"].get(k) == v for k, v in now.items()), f"environment {now} differs from freeze 1's {fz1['environment']}: a scrambled-Sobol or BLAS difference would change the proposals")


def load_group(g, campaign, tables, kernel_root, lost, fz, fz1, not_pushed=()):
    """runs[state][phase] = {downforce, drag, ok} of every run of the verified tables of group g; every kernel is in a table, declared lost or declared not pushed."""
    SC.req(kernel_root is not None, "--kernel-root is required (every kernel file is checked against the verified tables)")
    c = SC.jload(campaign)
    SC.validate_campaign(c)
    check_frozen(fz, campaign, "campaign")
    entry = campaign_entry(fz, campaign)
    SC.req(c["campaign_id"] in CAMPAIGN_IDS[g], f"{campaign}: campaign {c['campaign_id']} is not a {g} campaign")
    csha, runs, present = SC.sha256_path(campaign), {}, set()
    for path in tables:
        t = SC.require_formal_table(SC.jload(path))
        SC.req(t["campaign_sha256"] == csha and t.get("campaign_id", c["campaign_id"]) == c["campaign_id"], f"{path}: table belongs to another campaign")
        SC.req(t.get("freeze_sha256") == entry["prerun_freeze_sha256"], f"{path}: the table was verified against another prerun freeze than its campaign's")
        SC.req(t.get("harness_tool_sha256") == fz1["harness_tool_sha256"], f"{path}: the harness tools differ from freeze 1's")
        for k, forces in t["state_forces_n"].items():
            SC.req(k in KERNELS[g] and k in c["kernels"] and k not in present, f"unknown or duplicated kernel {k} in group {g}")
            present.add(k)
            byname = SC.runs_by_name(c["kernels"][k])
            SC.req(set(forces) == set(byname), f"kernel {k}: table runs differ from the campaign")
            for name, f in forces.items():
                st, ph = byname[name]["state"], name.rsplit("__", 1)[1][1:]
                SC.req(ph in PHASES[g] and ph not in runs.get(st, {}), f"{name}: phase not registered for {g} or duplicated")
                A.run_files(c, kernel_root, {"kernel": k, "name": name, "summary_sha256": f["summary_sha256"], "csv_sha256": f["forces_csv_sha256"]})
                runs.setdefault(st, {})[ph] = {"downforce": f["downforce_n"], "drag": f["drag_n"], "ok": True}
    mine_lost, mine_np = set(lost) & set(KERNELS[g]), set(not_pushed) & set(KERNELS[g])
    SC.req(not (mine_lost | mine_np) & present, f"kernels {sorted((mine_lost | mine_np) & present)} are declared lost / not pushed but have a verified table")
    SC.req(not mine_lost & mine_np, f"kernels {sorted(mine_lost & mine_np)} are declared both lost and not pushed")
    SC.req(set(KERNELS[g]) <= present | mine_lost | mine_np, f"kernels {sorted(set(KERNELS[g]) - present - mine_lost - mine_np)} have no verified table and are neither declared lost nor not pushed")
    return runs, {"campaign_sha256": csha, "table_sha256": {rel(p): SC.sha256_path(p) for p in tables}, "kernels_lost": sorted(mine_lost)}


def load_roles(states_path, fz1, proposals=()):
    check_frozen(fz1, states_path, "states.json")
    st = SC.jload(states_path)
    SC.req(st.get("schema") == "screen01-states-v1", "states.json: unexpected schema")
    roles = {n: {"role": r["role"], "order": r["order"], "u": r.get("u")} for n, r in st["states"].items()}
    roles.update({p["name"]: {"role": "proposal", "order": p["rank"], "u": p["u"]} for p in proposals})
    return roles


def restrict(T, stage) -> dict:
    """The input of an earlier stage, derived from a later one."""
    gs = STAGE_GROUPS[stage]
    ks = {k for g in gs for k in KERNELS[g]}
    roles = {n: r for n, r in T["roles"].items() if stage != "rs" or r["role"] != "proposal"}
    return {**T, "stage": stage, "roles": roles, "runs": {g: T["runs"][g] for g in gs if g in T["runs"]}, "lost_kernels": [k for k in T["lost_kernels"] if k in ks],
            "not_pushed": {k: v for k, v in T.get("not_pushed", {}).items() if k in ks}}


def dumps(obj) -> str:
    return json.dumps(A.clean(obj), indent=1, sort_keys=True, allow_nan=False) + "\n"


def write_once(path, text):
    with Path(path).open("x") as fh:
        fh.write(text)


def sha_text(text) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def split(res, stage) -> dict:
    return {"comparable": {k: res[k] for k in CMP[stage]}, "detail": {**{k: v for k, v in res.items() if k not in CMP[stage] and k not in ("rs", "detail")}, **res.get("detail", {})}}


def close(a, b, tol=1e-9) -> bool:
    """§5.11.20: floats to the cross-check tolerance, names / integers / booleans / labels exactly."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(close(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool) and abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return type(a) is type(b) and a == b


def check_not_pushed(a, stage, fz, rs=None, fin=None) -> dict:
    """§5.11.19: every `--not-pushed KERNEL=REASON[:RECORD]` cites a record that holds; returns {kernel: reason} and fills a.not_pushed_records for the output."""
    decl, allowed = getattr(a, "not_pushed", None) or {}, {k for g in STAGE_GROUPS[stage] for k in KERNELS[g]}
    SC.req(set(decl) <= allowed, f"--not-pushed names kernels outside this stage: {sorted(set(decl) - allowed)}")
    shas = {"rs": fz.get("freeze2_1", {}).get("rs_json_sha256"), "finalist": fz.get("freeze3", {}).get("finalist_json_sha256")}
    out, records = {}, {}
    for k, d in decl.items():
        reason, record = d["reason"], d.get("record")
        if reason == "BUDGET":
            SC.req(k in CONFIRMATION_KERNELS and record is not None, f"--not-pushed {k}=BUDGET: only {CONFIRMATION_KERNELS}, citing a screen01_budget_decision record")
            b = SC.jload(record)
            SC.req(b.get("kind") == "screen01_budget_decision" and b.get("decision") == "stop" and k in b.get("pending_estimate_s", {}),
                   f"{record}: not a §4.3 budget record with decision stop that lists {k} among its pending kernels")
        else:
            SC.req(reason == "INVALID_G1" and (k == "g2" or k in CONFIRMATION_KERNELS), f"--not-pushed {k}={reason}: INVALID_G1 applies to g2 and the confirmation kernels only")
            record = record or (a.finalist if stage == "main" else a.rs)
            sha = SC.sha256_path(record)
            SC.req(sha in (shas["rs"], shas["finalist"] if stage == "main" else None), f"{record}: not the frozen rs.json / finalist.json")
            SC.req(SC.jload(record)["comparable"]["g1_controls"]["invalid_at_step_2"] is True, f"{record}: its G1 chain controls do not report invalid_at_step_2: {k} must be pushed")
        out[k] = reason
        records[k] = {"reason": reason, "record": rel(record), "record_sha256": SC.sha256_path(record)}
    a.not_pushed_records = records
    return out


def stage_input(a, stage, fz, rs=None, fin=None):
    """Roles and T of the stage from the CLI inputs; fz = {freeze name: record}.  A group nobody needs (no proposal, F not pushed) must not be given; a needed group
    needs its campaign argument even when every kernel is lost or not pushed."""
    roles = load_roles(a.states, fz["freeze1"], rs["proposals"] if rs else ())
    inv_rs = bool(rs and rs["comparable"]["g1_controls"]["invalid_at_step_2"])
    pushed = bool(fin and fin["pushed"])
    need = {"g1": True, "g2": bool(rs and rs["proposals"]) and not inv_rs, "f32": pushed, "f48": pushed}
    where = {"g1": "freeze2", "g2": "freeze2_1", "f32": "freeze3", "f48": "freeze3"}
    np_ = check_not_pushed(a, stage, fz, rs, fin)
    required = ({"g2"} if rs and rs["proposals"] and inv_rs and stage in ("finalist", "main") else set()) | (set(CONFIRMATION_KERNELS) if stage == "main" and fin and fin["finalist"] and not pushed else set())
    SC.req(required <= set(np_) and all(np_[k] == "INVALID_G1" for k in required), f"kernels {sorted(required - set(np_))} were not pushed because the G1 chain controls failed: declare --not-pushed KERNEL=INVALID_G1")
    runs, meta = {}, {}
    for g in STAGE_GROUPS[stage]:
        args = getattr(a, g, None)
        if not need[g]:
            SC.req(not args, f"group {g} is not needed at this point (no proposal / F not pushed) but a campaign was given")
            continue
        SC.req(args, f"--{g} CAMPAIGN is required (also when every kernel is lost or not pushed)")
        runs[g], meta[g] = load_group(g, Path(args[0]), [Path(x) for x in args[1:]], a.kernel_root, a.lost, fz[where[g]], fz["freeze1"], set(np_))
    SC.req(not set(a.lost) - {k for g in STAGE_GROUPS[stage] for k in KERNELS[g]}, "--lost names kernels outside this stage")
    return {"schema": "screen01-T-v1", "stage": stage, "roles": roles, "runs": runs, "lost_kernels": sorted(a.lost), "not_pushed": dict(sorted(np_.items())),
            "gating": [{k: g[k] for k in GATING_KEYS} for g in rs["gating"]] if rs else []}, meta


def real_oracle(T, workers, log=print):
    """Full admissibility (gate stack + X1 + STL chain check) of a propose() point, evaluated in parallel rounds: a dry run with every answer False lists the
    queue propose() gates in rounds of 4, so each round's points are evaluated together (answers cached per name; rows keep every gate result)."""
    rows, queue = {}, []
    V, _ = valid_runs(T)
    fit = fit_stage(T, V)

    def dry(u):
        queue.append(np.asarray(u))
        return False
    P.propose(fit["by"], fit["bz"], dry, exclude=exclude(T), n_grid=GRID_N, grid=get_grid(GRID_N))
    n = {"i": 0}

    def ask(u):
        if n["i"] % P.GATE_ROUND == 0:
            todo = {P.D.name(P.u_to_spec(x)): P.u_to_spec(x) for x in queue[n["i"]:n["i"] + P.GATE_ROUND]}
            todo = [sp for nm, sp in todo.items() if nm not in rows]
            for r in (P.admissible_rows(todo, workers, log) if todo else []):
                rows[r["name"]] = r
        n["i"] += 1
        return bool(rows[P.D.name(P.u_to_spec(u))]["admissible"])
    return ask, rows


def common_record(T, meta, fz, states, a=None):
    ld = getattr(a, "lost_declarations", None) or {}
    return {"lost_signatures": {k: v["signature"] for k, v in ld.items()}, "lost_records_sha256": {k: v["record_sha256"] for k, v in ld.items()},
            "infra_signatures_sha256": SC.sha256_path(ROOT / INFRA_REL), "not_pushed": getattr(a, "not_pushed_records", {}), "not_pushed_kernels": T.get("not_pushed", {}),
            "registration": REG_REL, "analyzer_sha256": SC.sha256_path(__file__), "coefficients": coefficients(), "states_sha256": SC.sha256_path(states),
            "freeze_sha256": {n: SC.sha256_path(EV / f"{n}.json") for n in fz}, "groups": meta, "lost_kernels": T["lost_kernels"], "qualification_flags": "all false (unchanged)",
            "shape_update_allowed": False}


def frozen_sources(fz1, a=None):
    """Every file the decision depends on (sources, reused code, registration, adoption records, INTERFACE.md, signature table, P0 rows) hashes as freeze 1 recorded it, in the
    environment of freeze 1; with --lost every declaration cites a signature record."""
    for f in FROZEN_FILES:
        check_frozen(fz1, f, "frozen file")
    check_environment(fz1)
    SC.req(set(getattr(a, "lost", []) or []) <= set(getattr(a, "lost_declarations", {}) or {}), "every --lost declaration must cite a signature and its classification record (KERNEL=ID:RECORD, registration §5.11.17)")


def load_freezes(names):
    fz = {n: freeze(n) for n in names}
    check_chain(fz)
    return fz


def run_rs(a, oracle=real_oracle):
    """oracle(T, workers) -> (is_admissible, rows): injectable (tests); default = the full admissibility of screen01_pool in parallel rounds."""
    fz = load_freezes(("freeze1", "freeze2"))
    frozen_sources(fz["freeze1"], a)
    T, meta = stage_input(a, "rs", fz)
    V, _ = valid_runs(T)
    rows = {}
    if fit_stage(T, V)["ok"]:
        SC.req(P.fingerprint() == fz["freeze1"]["p0"]["fingerprint"], "screen01_pool.fingerprint() differs from the frozen P0 fingerprint: no refinement point is gated (§10)")
        ask, rows = oracle(T, a.workers)

        def checked(u):
            ok = ask(u)
            SC.req("error" not in (rows.get(P.D.name(P.u_to_spec(u))) or {}), f"the gate evaluation of a refinement point raised ({P.D.name(P.u_to_spec(u))}): nothing is written (§3.3)")
            return ok
        T = rs_gate(T, checked)
    res = compute(T)
    return {"kind": "screen01_rs", "stage": "rs", **split(res, "rs"), "proposals": res["proposal_states"],
            "gating": [{**rows.get(g["name"], {}), **g} for g in T["gating"]], "cross_check": cross_check(res, T), **common_record(T, meta, fz, a.states, a)}


def verify_upstream(T, rs_json=None, fin_json=None):
    """A later stage re-derives the earlier written-once outputs from the same tables: floats at the cross-check tolerance, everything else exactly (§5.11.20)."""
    for stage, js in (("rs", rs_json), ("finalist", fin_json)):
        if js is not None:
            mine = compute(restrict(T, stage))
            SC.req(close(json.loads(dumps(js["comparable"])), json.loads(dumps({k: mine[k] for k in CMP[stage]}))), f"{stage}.json does not re-derive from the verified tables")


def run_finalist(a):
    fz = load_freezes(("freeze1", "freeze2", "freeze2_1"))
    frozen_sources(fz["freeze1"], a)
    SC.req(SC.sha256_path(a.rs) == fz["freeze2_1"]["rs_json_sha256"], "rs.json is not the one frozen in freeze2_1.json")
    rs = SC.jload(a.rs)
    T, meta = stage_input(a, "finalist", fz, rs=rs)
    SC.req(rs["groups"]["g1"]["table_sha256"] == meta["g1"]["table_sha256"], "the g1 tables differ from those rs.json was computed from")
    verify_upstream(T, rs_json=rs)
    res = compute(T)
    pushed = bool(res["finalist"]) and not res["g1_controls"]["invalid_at_step_2"]
    return {"kind": "screen01_finalist", "stage": "finalist", "finalist": res["finalist"], "r_best": res["r_best"], "pushed": pushed, **split(res, "finalist"), "cross_check": cross_check(res, T),
            "rs_json_sha256": SC.sha256_path(a.rs), "groups": meta, **common_record(T, meta, fz, a.states, a)}


def handoff(T, res, fj, rs_json, analysis_sha, a, meta, fz):
    """§11 xv_handoff.json: every item by content hash; every file read is checked against its freeze first (campaign: freeze 3; P0 rows: freeze 1)."""
    f32 = Path(a.f32[0])
    check_frozen(fz["freeze3"], f32, "campaign")
    c = SC.jload(f32)
    f = res["finalist"]
    check_frozen(fz["freeze1"], ROWS_REL, "P0 rows record")
    row = next((g for g in rs_json["gating"] if g["name"] == f), None) or next((r for r in map(json.loads, (Path(ROOT) / ROWS_REL).read_text().splitlines()) if r["name"] == f), None)
    SC.req(row is not None, f"no admissibility row of {f} in rs.json or the P0 record")
    SC.req(POLICY_REL in fz["freeze1"]["file_sha256"], f"{POLICY_REL} is not bound by freeze 1: no topology policy hash")
    st = c["states"][f]
    ident = lambda s: {k: s[k] for k in SC.STATE_IDENTITY_KEYS}   # noqa: E731
    prop = next((p for p in rs_json["proposals"] if p["name"] == f), None)
    u = T["roles"][f]["u"]
    return {"kind": "screen01_xv_handoff", "outcome": res["outcome"], "finalist": f, "u": u, "in_camber_extension": bool(u[1] < -1.0),
            "spec": prop["spec"] if prop else SC.jload(a.states)["states"][f].get("spec"),
            "extension_note": "the camber extension (u < -1) has no FID fidelity evidence; XV-01 decides its fidelity",
            "parent": {"name": parent_of(T["roles"]), **ident(c["states"][parent_of(T["roles"])])},
            "state": {"direction": st["direction"], "step_mm": st["step_mm"], "sign": st["sign"], **ident(st), "direction_raw_sha256": c["directions"][st["direction"]]["sha256_fortran_raw"]},
            "admissibility_row": row, "flow_grids": {k: v["case"] for k, v in c["kernels"].items()}, "domain": c["domain"], "baseline": c["baseline"],
            "gate_profile_and_policy_sha256": {k: v for k, v in fz["freeze1"]["file_sha256"].items() if "gate_profile" in k or "policy" in k}, "topology_policy_sha256": fz["freeze1"]["file_sha256"][POLICY_REL],
            "campaign_and_prerun_freeze_sha256": {k: v for n in ("freeze2", "freeze2_1", "freeze3") for k, v in fz[n]["file_sha256"].items() if "campaign" in k},
            "phases": {"exploration": [11, 12], "confirmation_flow_32": [13, 14, 15, 16], "confirmation_flow_48": [13, 14], "z": "z never moves; ride height fixed; no z-lattice phase averaging"},
            "phases_used": res["detail"]["phases_used"],
            "selection_record": {"rs_json_sha256": SC.sha256_path(a.rs), "finalist_json_sha256": SC.sha256_path(a.finalist), "rs": rs_json["comparable"], "finalist": fj["comparable"]},
            "confirmation": res["confirmation"], "labels": {"G": res["G"], "D": res["D"], "R3": res["R3"]}, "controls": res["controls"], "selection_bias": res["selection_bias"],
            "selection_bias_inputs": res["detail"]["selection_bias_inputs"], "chain_controls": {"NC": res["NC"], "determinism": res["determinism"], "generation_drift": res["generation_drift"]},
            "xv_drag_margin": res["detail"]["xv_drag_margin"], "analysis_sha256": analysis_sha, "registration_sha256": SC.sha256_path(Path(ROOT) / REG_REL),
            "adoption_record_sha256": SC.sha256_path(Path(ROOT) / f"{EV_REL}/plan_review/adoption.md"), "source_review_record_sha256": SC.sha256_path(Path(ROOT) / f"{EV_REL}/source_review/adoption.md"),
            "table_sha256": {g: m["table_sha256"] for g, m in meta.items()}}


def summary_md(rec) -> str:
    lines = [f"# SCREEN-01 analysis: {rec['outcome']}", "", f"cause: {rec['cause']}", "", "| item | value |", "| --- | --- |"]
    for k in ("finalist", "futility", "search_complete", "pool_limited", "r_best", "K_opt", "K_rand", "g1_controls", "G", "D", "R3", "NC", "determinism", "generation_drift", "controls", "selection_bias"):
        lines.append(f"| {k} | {json.dumps(A.clean(rec.get(k)), sort_keys=True)} |")
    nj = [k for k, v in rec["determinism"].items() if not v["judged"]]
    lines += ["", f"determinism NOT_JUDGED (repeat absent or not ok): {nj or 'none'}", f"rs_fit_label: {rec['rs_fit_label']}", f"G1 chain controls invalid_at_step_2: {rec['g1_controls']['invalid_at_step_2']}"]
    return "\n".join(lines) + "\n"


def run_main(a) -> dict:
    """{path: text} of the outputs, all built (and the write-once check made) before any is written; on every branch, with or without F."""
    fz = load_freezes(("freeze1", "freeze2", "freeze2_1", "freeze3"))
    frozen_sources(fz["freeze1"], a)
    SC.req(SC.sha256_path(a.rs) == fz["freeze2_1"]["rs_json_sha256"] and SC.sha256_path(a.finalist) == fz["freeze3"]["finalist_json_sha256"], "rs.json or finalist.json is not the frozen one")
    rs, fj = SC.jload(a.rs), SC.jload(a.finalist)
    SC.req(fz["freeze3"]["finalist"] == fj["finalist"] and fz["freeze3"]["r_best"] == fj["r_best"] and fz["freeze3"]["pushed"] == fj["pushed"]
           and fj["pushed"] == (bool(fj["finalist"]) and not fj["comparable"]["g1_controls"]["invalid_at_step_2"]), "freeze3.json and finalist.json disagree on the finalist, R-best or whether F was pushed")
    T, meta = stage_input(a, "main", fz, rs=rs, fin=fj)
    SC.req(rs["groups"]["g1"]["table_sha256"] == meta["g1"]["table_sha256"] and all(fj["groups"][g]["table_sha256"] == meta[g]["table_sha256"] for g in ("g1", "g2") if g in fj["groups"]),
           "the g1 / g2 tables differ from those the frozen outputs were computed from")
    verify_upstream(T, rs, fj)
    res = compute(T)
    sp = split(res, "main")
    rec = {"kind": "screen01_analysis", "stage": "main", **sp["comparable"], "detail": sp["detail"], "rs_fit_label": res["rs"]["rs_fit_label"], "cross_check": cross_check(res, T),
           "rs_json_sha256": SC.sha256_path(a.rs), "finalist_json_sha256": SC.sha256_path(a.finalist), **common_record(T, meta, fz, a.states, a)}
    text = dumps(rec)
    out = {a.out: text, a.out.with_suffix(".md"): summary_md(rec)}
    if res["outcome"] == "SCREEN01_GAIN":
        out[a.out.with_name("xv_handoff.json")] = dumps(handoff(T, res, fj, rs, sha_text(text), a, meta, fz))
    SC.req(not any(p.exists() for p in out), "an output already exists (written once)")
    return out


# ---- budget (§4.3) and infrastructure loss (§9) -------------------------------------------------------------------------------------------------------
def budget(finished, pending) -> dict:
    """T = session walls of the finished formal kernels (attempts summed) + estimates of every unfinished one (reruns included); T > cap stops the pushes."""
    walls = {}
    for k, log in finished:
        SC.req(k in REG_RUNS, f"unknown kernel {k}")
        walls[k] = walls.get(k, 0.0) + A.log_wall(log)
    est_ = {}
    for k, n in pending:
        SC.req(k in REG_RUNS, f"unknown kernel {k}")
        runs, grid = REG_RUNS[k]
        est_.setdefault(k, []).append((runs if n is None else n) * EST_S[grid] + SETUP_S)
    t = sum(walls.values()) + sum(sum(v) for v in est_.values())
    return {"kind": "screen01_budget_decision", "finished_session_wall_s": walls, "pending_estimate_s": est_, "T_s": t, "cap_s": BUDGET_CAP_S,
            "decision": "go" if t <= BUDGET_CAP_S else "stop", "rule": "registration §4.3"}


def infra_table(path=None) -> dict:
    """The frozen §9 signature table (docs/evidence/screen01_2026_10_30/infra_signatures.json): ids, class, evidence sources, regex patterns, evaluation order; default NOT_INFRASTRUCTURE."""
    path = path or Path(ROOT) / INFRA_REL
    t = SC.jload(path)
    ids = [e["id"] for e in t["signatures"]]
    SC.req(t.get("schema") == "screen01-infra-signatures-v1" and len(set(ids)) == len(ids) and t["default"] == "NOT_INFRASTRUCTURE" and ids == t["evaluation_order"]
           and all(e.get("class") in t["classes"] for e in t["signatures"]), f"{path}: malformed signature table")
    return t


def classify_infra(output_dir, log_path, status_text="", verify_failed=False, table=None, verify_text="") -> dict:
    """The signatures of the table in its evaluation order (§9, §5.11.17): NONFINITE and VERIFY_FAILED on the verify result, SESSION_KILL on the output directory (neither DONE nor
    ERROR.txt), the others by regex on ERROR.txt + Kaggle log + status text (JULIA_INSTALL only before any complete state).  The result carries the signature's `class`
    (INFRA_LOSS | RUN_LOSS); a kernel that ended DONE and passed verify is COMPLETE; no match: NOT_INFRASTRUCTURE (a record of the cause, the rerun rule is the same)."""
    table, d = table or infra_table(), Path(output_dir)
    if (d / "DONE").exists() and not verify_failed:
        return {"classification": "COMPLETE", "signature": None}
    err = (d / "ERROR.txt").read_text(errors="replace") if (d / "ERROR.txt").exists() else ""
    text = err + status_text
    try:
        text += "".join(r.get("data", "") for r in json.loads(Path(log_path).read_text()))
    except (ValueError, TypeError, OSError, AttributeError):
        text += Path(log_path).read_text(errors="replace") if Path(log_path).exists() else ""
    idx = d / "harness_index.json"
    done = sum(1 for e in (json.loads(idx.read_text()).get("states") or []) if e.get("complete")) if idx.exists() else 0
    for e in table["signatures"]:
        if e["id"] == "VERIFY_FAILED":
            hit = verify_failed
        elif e["id"] == "SESSION_KILL":
            hit = not (d / "DONE").exists() and not (d / "ERROR.txt").exists()
        elif e["id"] == "NONFINITE":
            hit = bool(verify_failed and e["pattern"] and re.search(e["pattern"], verify_text))
        else:
            hit = bool(e["pattern"] and re.search(e["pattern"], text) and not (e.get("before_any_state") and done))
        if hit:
            return {"classification": e["class"], "signature": e["id"]}
    return {"classification": "NOT_INFRASTRUCTURE", "signature": None}


def infra_record(kernel, attempt, output_dir, log_path, status_file=None, verify_log=None, verify_failed=False, table=None) -> dict:
    """The classification record of one attempt of one kernel (`infra --out`), which a `--lost KERNEL=ID:RECORD` declaration cites."""
    SC.req(kernel in REG_RUNS and isinstance(attempt, int) and attempt >= 1, "infra --out needs --kernel (a registered kernel) and --attempt (1, 2)")
    table, d = table or infra_table(), Path(output_dir)
    status, vtext = (Path(status_file).read_text() if status_file else ""), (Path(verify_log).read_text(errors="replace") if verify_log else "")
    res = classify_infra(d, log_path, status, verify_failed, table, vtext)
    sha = lambda p: SC.sha256_path(p) if p and Path(p).is_file() else None   # noqa: E731
    return {"kind": "screen01_infra_classification", "kernel": kernel, "attempt": attempt, **res,
            "evidence_sha256": {"ERROR.txt": sha(d / "ERROR.txt"), "log": sha(log_path), "status": sha(status_file), "harness_index.json": sha(d / "harness_index.json"), "verify_log": sha(verify_log)},
            "verify_failed": bool(verify_failed), "table_sha256": SC.sha256_path(Path(ROOT) / INFRA_REL)}


def parse_lost(items, table=None) -> dict:
    """--lost KERNEL=ID:RECORD (§5.11.17): ID is a signature id of infra_signatures.json or its default NOT_INFRASTRUCTURE; RECORD the `infra --out` record of the failed rerun
    (attempt >= 2, same kernel, same signature, written against this table)."""
    table = table or infra_table()
    ids = {e["id"]: e["class"] for e in table["signatures"]}
    out = {}
    for x in items:
        k, _, rest = x.partition("=")
        sid, _, record = rest.partition(":")
        SC.req(k in REG_RUNS and (sid in ids or sid == table["default"]) and record, f"--lost {x!r}: expected KERNEL=ID:RECORD with a kernel of {sorted(REG_RUNS)} and an id of {sorted(ids)} or {table['default']}")
        r = SC.jload(record)
        SC.req(r.get("kind") == "screen01_infra_classification" and r["kernel"] == k and r["attempt"] >= 2 and r["table_sha256"] == SC.sha256_path(Path(ROOT) / INFRA_REL)
               and r["signature"] == (sid if sid in ids else None) and r["classification"] == (ids.get(sid) or table["default"]),
               f"{record}: not the classification record of a failed rerun of {k} that matched {sid}")
        out[k] = {"signature": sid, "record": record, "record_sha256": SC.sha256_path(record)}
    return out


def parse_not_pushed(items) -> dict:
    """--not-pushed KERNEL=REASON[:RECORD] (§5.11.19); the citation is verified in `check_not_pushed`."""
    out = {}
    for x in items:
        k, _, rest = x.partition("=")
        reason, _, record = rest.partition(":")
        SC.req(k in REG_RUNS and reason in ("BUDGET", "INVALID_G1"), f"--not-pushed {x!r}: expected KERNEL=BUDGET:RECORD or KERNEL=INVALID_G1[:RECORD]")
        out[k] = {"reason": reason, "record": Path(record) if record else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rs", "finalist", "main", "budget", "infra"])
    for g in ("g1", "g2", "f32", "f48"):
        ap.add_argument(f"--{g}", nargs="+", metavar="CAMPAIGN_THEN_TABLES")
    ap.add_argument("--states", type=Path, default=EV / "states.json")
    ap.add_argument("--rs", type=Path)
    ap.add_argument("--finalist", type=Path)
    ap.add_argument("--kernel-root", type=Path)
    ap.add_argument("--lost", nargs="*", default=[], metavar="KERNEL=ID:RECORD")
    ap.add_argument("--not-pushed", nargs="*", default=[], metavar="KERNEL=REASON[:RECORD]")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--finished", nargs="*", default=[])
    ap.add_argument("--pending", nargs="*", default=[])
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--log", type=Path)
    ap.add_argument("--status-file", type=Path)
    ap.add_argument("--verify-failed", action="store_true")
    ap.add_argument("--verify-log", type=Path)
    ap.add_argument("--kernel")
    ap.add_argument("--attempt", type=int)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    SC.req(a.workers <= 4, "at most 4 workers")
    if a.cmd == "infra":
        if a.out:
            rec = infra_record(a.kernel, a.attempt, a.output_dir, a.log, a.status_file, a.verify_log, a.verify_failed)
            write_once(a.out, dumps(rec))
        else:
            rec = classify_infra(a.output_dir, a.log, a.status_file.read_text() if a.status_file else "", a.verify_failed, verify_text=a.verify_log.read_text(errors="replace") if a.verify_log else "")
        print(json.dumps(rec))
        return
    if a.cmd == "budget":
        res = budget([tuple(x.split("=", 1)) for x in a.finished], [(x.split("=")[0], int(x.split("=")[1]) if "=" in x else None) for x in a.pending])
        if a.out:
            write_once(a.out, dumps(res))
        print(res["decision"], res["T_s"])
        return
    SC.req(a.out is not None, "--out is required")
    a.lost_declarations = parse_lost(a.lost)
    a.lost = sorted(a.lost_declarations)
    a.not_pushed = parse_not_pushed(a.not_pushed)
    if a.cmd == "main":
        for p, text in run_main(a).items():
            write_once(p, text)
        print(a.out)
        return
    write_once(a.out, dumps((run_rs if a.cmd == "rs" else run_finalist)(a)))
    print(a.cmd, a.out)


if __name__ == "__main__":
    main()
