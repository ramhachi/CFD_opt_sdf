#!/usr/bin/env python3
"""T2-0b (#57, REGISTERED_FROZEN): the registered verdict. Implements section 6 of docs/t20b_registration_2026_10_19.md (that text governs; a disagreement
is a defect here). Reads the downloaded kernel outputs (kernel W, kernel L; a resubmission directory may follow each first run and only fills cases the first
run lacks), the digitised experiment and, for one descriptive label, the T2-0a output. Writes analysis.md and verdict.json once. No solver, no recomputation of
forces: every Cl is the kernel's `forces.Cl.tail_mean`."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data/t20/zerihan_zhang_cl_genua2009_fig6.json"
GENUA = ROOT / "data/t20/reference_genua2009.json"
T20A = ROOT / "docs/evidence/t20a_exploratory_2026_10_16/attempt3_r3/kernel_output"
CHORD = 0.2234
HEIGHTS = (0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09)
INC, SCAN = (0.224, 0.134, 0.09), (0.224, 0.134)
SCAN_DA = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)
INCIDENCE_SHIFT_DEG, PEAK_TOL = 0.15, 0.005
TH = {"G2_mean": 0.05, "G2d": 0.30, "G3a": 0.05, "G3b": 0.25, "G3c": 0.25, "G4": 0.33, "G5_median_min": 15.0, "G5_max_min": 30.0, "G6": 0.25,
      "delta_floor": 0.01, "G6_resolve": 5.0, "LM_stationary": 0.01, "ADJ_tol": 0.30, "ADJ_null": 0.1, "ADJ_residual": 1e-5, "replicated": 0.01}
PREDICTED = {"G2": "pass", "G2d": "uncertain", "G3a": "fail", "G3b": "uncertain", "G3c": "near threshold", "G4": "uncertain", "G5": "pass (non-discriminating)",
             "G6": "uncertain", "LM": "LM_NOT_QUALIFIED", "ADJ": "not ADJ_CONSISTENT"}
SCOPE = "2D single-element section (Tyrrell 026, Zerihan & Zhang), Re_c 4.6e5, moving ground, OpenFOAM v2512 SA wall functions, med30/fine30"
GATES = ("G2", "G2d", "G3a", "G3b", "G3c", "G4", "G5", "G6")
INFRA = {"NOT_RUN_TIME_BUDGET", "RUNNER_EXCEPTION", "DEADLINE_LIMITED"}
MECH = {"GENERATOR_FAILED", "gmshToFoam_FAILED", "gmshToFoam_TIMEOUT", "checkMesh_FAILED", "checkMesh_TIMEOUT", "PARSE_FAILED"}


def cid(model, h, mesh, da):
    return f"{model}_h{h}_{mesh}_da{'0' if da == 0 else format(da, '+g')}"


def _read(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None   # unreadable (e.g. truncated by a kill): the case stays INFRA_LOSS


def load_runs(dirs) -> tuple[dict, dict, dict]:
    """{case id: record} with first-run priority, a later run only replacing an INFRA_LOSS record; {case id: run index}; {input path: sha256}.
    Ids listed only in result.json (no case directory) keep their status."""
    cases, origin, hashes = {}, {}, {}
    for k, d in enumerate(dirs):
        found = {}
        res = Path(d) / "result.json"
        for r in ((_read(res) or {}).get("cases", []) if res.is_file() else []):
            found[r["id"]] = r
        for p in sorted(Path(d).glob("cases/*/case_result.json")):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            r = _read(p)
            if r is not None:
                found[r["id"]] = r
        for i, r in found.items():
            if i.endswith("_smoke") or (i in cases and classify(cases[i]) != "INFRA_LOSS"):
                continue
            cases[i], origin[i] = r, k
    return cases, origin, hashes


def classify(r) -> str:
    if r is None or r.get("status") in INFRA:
        return "INFRA_LOSS"
    cm = r.get("check_mesh") or {}
    if r.get("status") in MECH or (r.get("status") == "COMPLETED" and (not cm.get("mesh_ok") or cm.get("failed_check_counts"))):
        return "MECHANICAL_FAIL"
    if r.get("status") == "COMPLETED" and (r.get("forces") or {}).get("cl_plateau"):
        return "VALID"
    return "SOLVER_FAIL"


class Gate(Exception):
    """Raised inside a gate when an input case is not VALID: value False (a failure) or None (infrastructure)."""
    def __init__(self, value, reason):
        super().__init__(reason)
        self.value, self.reason = value, reason


class Data:
    def __init__(self, cases):
        self.cases = cases

    def cls(self, i):
        return classify(self.cases.get(i))

    def need(self, ids):
        kinds = {i: self.cls(i) for i in ids}
        bad = sorted(i for i, k in kinds.items() if k in ("SOLVER_FAIL", "MECHANICAL_FAIL"))
        if bad:
            raise Gate(False, f"input case(s) not valid: {', '.join(f'{i} ({kinds[i]})' for i in bad)}")
        lost = sorted(i for i, k in kinds.items() if k == "INFRA_LOSS")
        if lost:
            raise Gate(None, f"input case(s) lost to infrastructure: {', '.join(lost)}")

    def cl(self, model, h, mesh, da=0.0):
        return self.cases[cid(model, h, mesh, da)]["forces"]["Cl"]["tail_mean"]

    def d(self, model, mesh, h, s=1.0):
        return (self.cl(model, h, mesh, s) - self.cl(model, h, mesh, -s)) / (2 * s)

    def sigma_mesh(self, h):
        """Residual std of a quadratic fit of Cl(alpha) over the 7 sa-wf med30 incidences (4 dof); at 0.09 the larger of the two scanned heights."""
        if h not in SCAN:
            return max(self.sigma_mesh(x) for x in SCAN)
        self.need([cid("sa-wf", h, "med30", da) for da in SCAN_DA])
        x = list(SCAN_DA)
        y = [self.cl("sa-wf", h, "med30", da) for da in x]
        coef = _polyfit2(x, y)
        ssr = sum((yi - (coef[0] * xi * xi + coef[1] * xi + coef[2])) ** 2 for xi, yi in zip(x, y))
        return math.sqrt(ssr / (len(x) - 3))

    def delta(self, h, s):
        return max(TH["delta_floor"], 3 * self.sigma_mesh(h) / (math.sqrt(2) * s))


def _polyfit2(x, y):
    """Least-squares quadratic (a, b, c) for y = a x^2 + b x + c (normal equations; 7 points)."""
    import numpy as np
    return np.polyfit(x, y, 2).tolist()


def consistent(a, b, tol, delta) -> bool:
    if not all(math.isfinite(v) for v in (a, b, delta)):
        return False
    return abs(a - b) <= max(tol * max(abs(a), abs(b)), delta)


def increments(v: dict) -> list:
    return [v[HEIGHTS[i + 1]] - v[HEIGHTS[i]] for i in range(len(HEIGHTS) - 1)]


def rel_l1(a, b):
    den = sum(abs(x) for x in b)
    return sum(abs(x - y) for x, y in zip(a, b)) / den if den else float("inf")


def d_interp(d: dict, h: float) -> float:
    """d at any sweep height: own value at 0.224/0.134/0.09, linear in h between 0.224 and 0.134 (for 0.179), d(0.224) above 0.224."""
    if h in d:
        return d[h]
    if h > 0.224:
        return d[0.224]
    w = (h - 0.134) / (0.224 - 0.134)
    return d[0.134] + w * (d[0.224] - d[0.134])


def mean_abs_err(cl: dict, exp: dict, shift=None, exp_offset=0.0):
    return statistics.mean(abs((cl[h] + (shift(h) if shift else 0.0)) / (exp[h] + exp_offset) - 1) for h in cl)


# ---- gates ------------------------------------------------------------------------

def g2(D, exp):
    ids = [cid("sa-wf", h, "med30", 0.0) for h in HEIGHTS] + [cid("sa-wf", h, "med30", s) for h in INC for s in (-1.0, 1.0)]
    D.need(ids)
    cl = {h: D.cl("sa-wf", h, "med30") for h in HEIGHTS}
    d = {h: D.d("sa-wf", "med30", h) for h in INC}
    shift = lambda h: INCIDENCE_SHIFT_DEG * d_interp(d, h)
    m0, m1 = mean_abs_err(cl, exp), mean_abs_err(cl, exp, shift)
    peak = cl[0.134] >= (1 - PEAK_TOL) * max(cl[0.179], cl[0.09])
    rising = [h for h, nxt in zip(HEIGHTS[:5], HEIGHTS[1:6]) if not cl[nxt] >= (1 - PEAK_TOL) * cl[h]]
    ok = m0 < TH["G2_mean"] and m1 < TH["G2_mean"] and peak and not rising
    return ok, {"mean_abs_e_nominal": m0, "mean_abs_e_plus_0p15deg": m1, "peak_ok": peak, "rise_breaks_after_h": rising,
                "e_h": {h: cl[h] / exp[h] - 1 for h in HEIGHTS}}


def g2d(D, exp):
    D.need([cid("sa-wf", h, "med30", 0.0) for h in HEIGHTS])
    cl = {h: D.cl("sa-wf", h, "med30") for h in HEIGHTS}
    e = rel_l1(increments(cl), increments(exp))
    return e <= TH["G2d"], {"E_inc_vs_exp": e, "increments_cfd": increments(cl), "increments_exp": increments(exp)}


def g3a(D, exp):
    D.need([cid("sa-wf", h, m, 0.0) for h in HEIGHTS for m in ("med30", "fine30")])
    r = {h: D.cl("sa-wf", h, "fine30") / D.cl("sa-wf", h, "med30") - 1 for h in HEIGHTS}
    worst = max(abs(v) for v in r.values())
    return worst <= TH["G3a"], {"fine30_over_med30_minus_1": r, "max_abs": worst}


def scan_ids():
    """The 14 sa-wf med30 incidence-scan cases behind sigma_mesh: implicit inputs of every gate that uses delta (registration section 6 defines delta from sigma)."""
    return [cid("sa-wf", h, "med30", da) for h in SCAN for da in SCAN_DA]


def g3b(D, exp):
    D.need([cid("sa-wf", h, m, da) for h in INC for m in ("med30", "fine30") for da in (-1.0, 0.0, 1.0)] + scan_ids())
    rows, ok = {}, True
    for h in INC:
        a, b, delta = D.d("sa-wf", "med30", h), D.d("sa-wf", "fine30", h), D.delta(h, 1.0)
        rows[h] = {"d_med30": a, "d_fine30": b, "delta": delta, "pass": consistent(a, b, TH["G3b"], delta)}
        ok &= rows[h]["pass"]
    sign_ok = rows[0.224]["d_med30"] > 0
    return ok and sign_ok, {"per_height": rows, "expected_sign_ok_at_0.224": sign_ok}


def g3c(D, exp):
    D.need([cid("sa-wf", h, m, 0.0) for h in HEIGHTS for m in ("med30", "fine30")])
    med = {h: D.cl("sa-wf", h, "med30") for h in HEIGHTS}
    fine = {h: D.cl("sa-wf", h, "fine30") for h in HEIGHTS}
    e = rel_l1(increments(fine), increments(med))
    return e <= TH["G3c"], {"E_inc_fine30_vs_med30": e}


def g4(D, exp):
    D.need([cid(m, h, "med30", da) for m in ("sa-wf", "sst-wf") for h in SCAN for da in (-1.0, 0.0, 1.0)] + scan_ids())
    rows, ok = {}, True
    for h in SCAN:
        a, b, delta = D.d("sa-wf", "med30", h), D.d("sst-wf", "med30", h), D.delta(h, 1.0)
        rows[h] = {"d_sa": a, "d_sst": b, "delta": delta, "pass": consistent(a, b, TH["G4"], delta)}
        ok &= rows[h]["pass"]
    return ok, {"per_height": rows}


def case_cost_min(r) -> float:
    """Generation + meshing + checkMesh + solver time to the Cl plateau [min] (solver time scales with the iteration count)."""
    f = r["forces"]
    solver = sum(s["wall_s"] for s in r["stages"] if s["stage"] in ("simpleFoam", "simpleFoam_cont"))
    return (r["pre_solver_wall_s"] + solver * f["iterations_to_plateau"] / f["history_rows"]) / 60


def g5(D, exp):
    rs = [r for i, r in D.cases.items() if i.startswith("sa-wf_") and "_med30_" in i and classify(r) == "VALID" and "adjoint" not in r]
    if not rs:
        raise Gate(False, "no valid sa-wf med30 case")
    c = [case_cost_min(r) for r in rs]
    med, mx = statistics.median(c), max(c)
    return med <= TH["G5_median_min"] and mx <= TH["G5_max_min"], {"n_cases": len(c), "median_min": med, "max_min": mx,
                                                                     "capped_wall_median_min": statistics.median(r["total_wall_s"] / 60 for r in rs)}


def g6(D, exp):
    D.need(scan_ids())
    rows, ok = {}, True
    for h in SCAN:
        sig = D.sigma_mesh(h)   # needs the 7 scan cases
        a, b, delta = D.d("sa-wf", "med30", h, 0.25), D.d("sa-wf", "med30", h, 1.0), D.delta(h, 0.25)
        diff = abs(D.cl("sa-wf", h, "med30", 0.25) - D.cl("sa-wf", h, "med30", -0.25))
        resolved = diff >= TH["G6_resolve"] * math.sqrt(2) * sig
        rows[h] = {"d_0.25": a, "d_1": b, "delta": delta, "sigma_mesh": sig, "dCl_pm0.25": diff, "resolved": resolved,
                   "smallest_resolved_incidence_deg": 2 * math.sqrt(2) * sig / abs(b) if b else float("inf"),
                   "pass": consistent(a, b, TH["G6"], delta) and resolved}
        ok &= rows[h]["pass"]
    return ok, {"per_height": rows}


GATE_FN = {"G2": g2, "G2d": g2d, "G3a": g3a, "G3b": g3b, "G3c": g3c, "G4": g4, "G5": g5, "G6": g6}


def verdict_of(g: dict) -> str:
    if all(g[k] for k in GATES):
        return "T20B_GO_2D_SECTION"
    if not g["G3a"] and all(g[k] for k in GATES if k != "G3a"):
        return "T20B_GO_2D_SECTION_DIFFERENCES"
    return "T20B_NO_GO"


def verdict(gates: dict) -> str:
    """Every true/false assignment of the undetermined gates; one common verdict or INCOMPLETE."""
    open_ = [k for k in GATES if gates[k] is None]
    seen = {verdict_of({**gates, **dict(zip(open_, combo))}) for combo in itertools.product((True, False), repeat=len(open_))}
    return seen.pop() if len(seen) == 1 else "T20B_INCOMPLETE"


def evaluate(cases: dict, exp: dict) -> dict:
    D = Data(cases)
    out = {}
    for k in GATES:
        try:
            ok, detail = GATE_FN[k](D, exp)
            out[k] = {"value": bool(ok), "detail": detail}
        except Gate as g:
            out[k] = {"value": g.value, "detail": {"reason": g.reason}}
        except (KeyError, TypeError, ZeroDivisionError, ValueError) as exc:   # an undefined quantity fails
            out[k] = {"value": False, "detail": {"reason": f"undefined quantity: {type(exc).__name__}: {exc}"}}
    return out


# ---- labels -----------------------------------------------------------------------

def labels(cases: dict, lm_cases: dict, exp: dict, gates: dict, t20a: dict | None) -> dict:
    D = Data(cases)
    out = {}
    try:
        D.need([cid("sa-wf", h, "med30", 0.0) for h in HEIGHTS])
        cl = {h: D.cl("sa-wf", h, "med30") for h in HEIGHTS}
        if gates["G2"]["value"] is None:
            out["G2_robustness"] = "UNDETERMINED"
        else:
            d = {h: D.d("sa-wf", "med30", h) for h in INC}
            shift = lambda h: INCIDENCE_SHIFT_DEG * d_interp(d, h)
            robust = all(mean_abs_err(cl, exp, sh, o) < TH["G2_mean"] for o in (-0.005, 0.005) for sh in (None, shift))
            out["G2_robustness"] = "ROBUST" if robust and gates["G2"]["value"] else "MARGINAL"
        dis = statistics.mean(abs(cl[h] / exp[h] - 1) for h in (0.313, 0.179))
        out["G2_disjoint"] = {"mean_abs_e": dis, "label": "G2_DISJOINT_OK" if dis < TH["G2_mean"] else "G2_DISJOINT_NOT_OK"}
        if t20a:
            shared = [h for h in HEIGHTS if h in t20a]
            rep = max(abs(cl[h] / t20a[h] - 1) for h in shared)
            out["replication_vs_T20A"] = {"heights": shared, "max_rel_diff": rep, "label": "REPLICATED" if rep <= TH["replicated"] else "NOT_REPLICATED"}
    except (Gate, KeyError) as g:
        out["G2_robustness"] = f"not computable: {g}"
    for mesh in ("fine30", "coa30"):
        try:
            D.need([cid("sa-wf", h, mesh, 0.0) for h in HEIGHTS])
            c = {h: D.cl("sa-wf", h, mesh) for h in HEIGHTS}
            out[f"{mesh}_vs_exp"] = {"mean_abs_e": mean_abs_err(c, exp), "peak_h": max(c, key=c.get)}
        except Gate as g:
            out[f"{mesh}_vs_exp"] = f"not computable: {g.reason}"
    if isinstance(out.get("fine30_vs_exp"), dict):
        out["agreement_mesh_specific"] = out["fine30_vs_exp"]["mean_abs_e"] >= TH["G2_mean"]
    i = cid("sa-wf", 0.224, "med30", 0.0)
    if classify(cases.get(i)) == "VALID" and classify(lm_cases.get(i)) == "VALID":
        a, b = cases[i]["forces"]["Cl"]["tail_mean"], lm_cases[i]["forces"]["Cl"]["tail_mean"]
        out["negative_control"] = {"case": i, "abs_dCl_kernelL_minus_kernelW": abs(b - a), "rel": abs(b / a - 1)}
    else:
        out["negative_control"] = f"not computable: W {classify(cases.get(i))}, L {classify(lm_cases.get(i))}"
    out["LM"] = lm_label(lm_cases, exp)
    out["ADJ"] = adj_label(cases, lm_cases)
    return out


def lm_label(lm_cases, exp):
    hs = (0.224, 0.134, 0.09)
    recs = {h: lm_cases.get(cid("sst-lm", h, "wr2", 0.0)) for h in hs}
    rows = {}
    for h, r in recs.items():
        f = (r or {}).get("forces")
        rows[h] = {"status": (r or {}).get("status"), "cycle_mean_Cl": f["Cl"]["tail_mean"] if f else None, "osc_std_Cl": f["Cl"]["tail_std"] if f else None,
                   "half_window_rel_diff": f["Cl"]["half_window_rel_diff"] if f else None,
                   "stationary": bool(f and f["Cl"]["half_window_rel_diff"] < TH["LM_stationary"])}
    if any(r is None or r.get("status") in INFRA for r in recs.values()):
        return {"label": "LM_INCOMPLETE", "cases": rows}
    good = all(r["status"] == "COMPLETED" and r["stationary"] for r in rows.values())
    if good:
        cl = {h: rows[h]["cycle_mean_Cl"] for h in hs}
        e = statistics.mean(abs(cl[h] / exp[h] - 1) for h in hs)
        peak = cl[0.134] >= (1 - PEAK_TOL) * max(cl[0.224], cl[0.09])
        return {"label": "LM_DATA_AGREES" if e < TH["G2_mean"] and peak else "LM_NOT_QUALIFIED", "mean_abs_e": e, "peak_ok": peak, "cases": rows}
    return {"label": "LM_NOT_QUALIFIED", "cases": rows}


def adj_label(wf_cases, lm_cases):
    r = lm_cases.get(cid("sa-wf", 0.224, "med30", 0.0))
    a = (r or {}).get("adjoint")
    if a is None:
        return {"label": "ADJ_NOT_RUN", "reason": "no adjoint record: the kernel-L primal case was " + classify(r) + " (" + ((r or {}).get("status") or "missing")
                + "); this is not the registered binary/fatal meaning of ADJ_NOT_RUN"}
    out = {"label": a["status"], "record_status": a["status"], "wall_s": (a.get("stage") or {}).get("wall_s"), "converged_in": a.get("converged_in")}
    res = (a.get("primal") or {}).get("last_initial_residuals") or {}
    out["ADJ_PRIMAL_UNCONVERGED"] = any((res.get(k) or 0) > TH["ADJ_residual"] for k in ("p", "Ux", "Uy", "nuTilda"))
    if a["status"] != "ADJ_RUNS":
        return out
    p = a["projection"]
    out.update(rotation_per_deg=p["rotation_per_deg"], x_translation_per_mm=p["x_translation_per_mm"], y_translation_per_mm=p["y_translation_per_mm"])
    D = Data(wf_cases)
    try:
        fd, sig = D.d("sa-wf", "med30", 0.224), D.sigma_mesh(0.224)
        D.need([cid("sa-wf", 0.224, "med30", s) for s in (-1.0, 1.0)])
        tol = max(TH["ADJ_tol"] * abs(fd), 2 * sig / math.sqrt(2))
        null_ok = abs(p["x_translation_per_mm"]) <= TH["ADJ_null"] * abs(p["rotation_per_deg"])
        close = abs(p["rotation_per_deg"] - fd) <= tol
        out.update(fd_per_deg=fd, tolerance=tol, x_null_ok=null_ok, rotation_close=close)
        if close and null_ok:
            out["label"] = "ADJ_CONSISTENT"
        D.need([cid("sa-wf", h, "med30", 0.0) for h in (0.313, 0.179)])
        out["y_translation_fd_per_mm"] = (D.cl("sa-wf", 0.179, "med30") - D.cl("sa-wf", 0.313, "med30")) / ((0.179 - 0.313) * CHORD * 1e3)
    except (Gate, KeyError) as exc:
        out["fd_comparison"] = f"not computable: {exc}"
    return out


# ---- report -----------------------------------------------------------------------

def descriptive(cases, lm_cases) -> list[str]:
    genua = json.loads(GENUA.read_text())["genua_ride_height_sweep"]["cases"]
    gname = {("sa-wf", "med30"): "Med30SA", ("sa-wf", "fine30"): "Fine30SA", ("sa-wf", "coa30"): "Coa30SA"}
    lines = ["| kernel | case | class | Cl | Cd | Cd Genua | Cl plateau (block rel std) | iters to plateau | cost min | capped wall min | cells | s per cell-iter (x1e6) | RSS MB | y+ airfoil min/avg/max | y+ outside 11-300 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kern, i, r in [("W", i, r) for i, r in sorted(cases.items())] + [("L", i, r) for i, r in sorted(lm_cases.items())]:
        f = r.get("forces") or {}
        cl, cd = (f.get("Cl") or {}).get("tail_mean"), (f.get("Cd") or {}).get("tail_mean")
        g = genua.get(gname.get((r.get("model"), r.get("mesh"))), {}).get(f"{r.get('h_over_c')}") if r.get("delta_alpha_deg") == 0 else None
        solver = sum(s["wall_s"] for s in r.get("stages", []) if s["stage"].startswith("simpleFoam"))
        iters = f.get("history_rows") or 0
        y = (r.get("yplus") or {}).get("airfoil") or {}
        rss = max((s.get("peak_rss_mb_sampled") or 0 for s in r.get("stages", [])), default=0)
        fmt = lambda v, s=".4f": "-" if v is None else format(v, s)
        cost = case_cost_min(r) if classify(r) == "VALID" and "pre_solver_wall_s" in r else None
        per = solver / (iters * r["mesh_cells_3d"]) * 1e6 if iters and r.get("mesh_cells_3d") else None
        lines.append(f"| {kern} | {i} | {classify(r)} | {fmt(cl)} | {fmt(cd)} | {fmt(g and g['Cd'], '.3f')} | {f.get('cl_plateau', '-')} ({fmt(f.get('cl_block_rel_std'), '.2e')}) | "
                     f"{f.get('iterations_to_plateau', '-')} | {fmt(cost, '.1f')} | {fmt(r.get('total_wall_s', 0) / 60, '.1f')} | {r.get('mesh_cells_3d', '-')} | {fmt(per, '.2f')} | "
                     f"{rss:.0f} | {fmt(y.get('min'), '.1f')}/{fmt(y.get('average'), '.1f')}/{fmt(y.get('max'), '.1f')} | "
                     f"{'-' if not y else (y['min'] < 11 or y['max'] > 300)} |")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wf", type=Path, nargs="+", required=True, help="kernel W output dir(s): first run, then an optional resubmission")
    ap.add_argument("--lm", type=Path, nargs="+", required=True, help="kernel L output dir(s)")
    ap.add_argument("--t20a", type=Path, default=T20A)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if (a.out / "verdict.json").exists():
        raise SystemExit("verdict.json exists: the registered analysis is written once")
    exp = {float(h): p["Cl"] for h, p in json.loads(EXP.read_text())["points"].items()}
    wf, wf_origin, wf_hash = load_runs(a.wf)
    lm, lm_origin, lm_hash = load_runs(a.lm)
    t20a = None
    if a.t20a.is_dir():
        t20a = {}
        for p in a.t20a.glob("cases/sa-wf_h*_med30/case_result.json"):
            r = json.loads(p.read_text())
            if r.get("forces"):
                t20a[r["h_over_c"]] = r["forces"]["Cl"]["tail_mean"]
    gates = evaluate(wf, exp)
    v = verdict({k: g["value"] for k, g in gates.items()})
    lab = labels(wf, lm, exp, gates, t20a)
    classes = {}
    for r in [*wf.values(), *lm.values()]:
        classes[classify(r)] = classes.get(classify(r), 0) + 1
    out = {"verdict": v, "scope": SCOPE, "gates": gates, "labels": lab, "predicted": PREDICTED, "thresholds": TH,
           "thresholds_set_after_exploratory_visible": True, "case_classes": classes, "runs_used": {"wf": [str(p) for p in a.wf], "lm": [str(p) for p in a.lm]},
           "cases_from_resubmission": sorted([i for i, k in wf_origin.items() if k] + [i for i, k in lm_origin.items() if k]),
           "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "registration": "docs/t20b_registration_2026_10_19.md",
           "input_sha256": {**wf_hash, **lm_hash, **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (EXP, GENUA, ROOT / "docs/t20b_registration_2026_10_19.md")}},
           "t20a_replication_input": str(a.t20a) if t20a else "MISSING (replication label not computed)",
           "qualification_flags": "unchanged (all false; shape_update_allowed=false)"}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "verdict.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    g = lambda k: {True: "PASS", False: "FAIL", None: "UNDETERMINED"}[gates[k]["value"]]
    md = [f"# T2-0b registered verdict: **{v}**", "", f"Scope: {SCOPE}. Thresholds were set after T2-0a was visible (registration section 2).", "",
          "| gate | result | predicted | detail |", "|---|---|---|---|"]
    md += [f"| {k} | {g(k)} | {PREDICTED[k]} | `{json.dumps(gates[k]['detail'], default=str)[:600]}` |" for k in GATES]
    md += ["", "## Labels (never change the verdict)", "", "```json", json.dumps(lab, indent=1, default=str), "```", "", "## Cases", "", *descriptive(wf, lm), ""]
    (a.out / "analysis.md").write_text("\n".join(md))
    print(v)


if __name__ == "__main__":
    main()
