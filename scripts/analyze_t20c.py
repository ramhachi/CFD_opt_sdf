#!/usr/bin/env python3
"""T2-0c (#57, REGISTERED): the registered verdict. Implements section 6 of docs/t20c_registration_2026_10_20.md (that text governs; a disagreement is a
defect here). Reads the downloaded outputs of kernels R (remesh), M (morph) and S (shape) (a resubmission directory may follow each first run and only fills
cases the first run lacks), the digitised experiment and, for the replication label only, the T2-0b kernel-W output. Writes analysis.md and verdict.json once.
Every Cl is the kernel's `forces.Cl.tail_mean`; no recomputation of forces."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_t20b as B  # noqa: E402  (run loading, G2 helpers and the cost definition reused unchanged)

ROOT = B.ROOT
REG = ROOT / "docs/t20c_registration_2026_10_20.md"
T20B_W = ROOT / "docs/evidence/t20b_registered_2026_10_19/kernel_wf_run1/t20b"
HEIGHTS, H, ATT = B.HEIGHTS, (0.224, 0.134, 0.09), (0.224, 0.134)
A7 = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)
LEVELS = ("med30", "fine30", "xfine30")
SHAPES, SHAPE_MESHES = ("camber", "flap", "heave"), ("med30", "fine30")
B2_TARGETS = (-1.0, -0.25, 0.25, 1.0)
TH = {"tol": 0.25, "delta_floor": 0.01, "resolve": 5.0, "power": 0.5, "unsteady": 0.005, "nonlinear": 2.0, "chi2_90_3dof": math.sqrt(3 / 0.5844),
      "peak_tol": B.PEAK_TOL, "G2_mean": B.TH["G2_mean"], "G2d": B.TH["G2d"], "bitwise": 1e-12}
INFRA = B.INFRA
MECH = B.MECH | {"TOPOLOGY_CHANGED", "BASE_TOPOLOGY_MISSING"}
FAILING = ("SOLVER_FAIL", "MECHANICAL_FAIL", "UNSTEADY")
V_GO, V_ATT, V_NO, V_INC = "T20C_MORPH_GO_FINE30", "T20C_MORPH_GO_FINE30_ATTACHED", "T20C_MORPH_NO_GO", "T20C_INCOMPLETE"
PREDICTED = {"G6m": "pass", "G3bm": "pass at 0.224/0.134; 0.09 likely fails through UNSTEADY +1 deg cases", "G7m": "pass at 0.224/0.134, uncertain at 0.09",
             "G8m": "uncertain", "verdict": f"{V_ATT} most likely, {V_NO} second", "replication": "REPLICATED_BITWISE", "peak": "uncertain", "shapes": "resolved"}
SCOPE = "2D single-element section (Tyrrell 026), Re_c 4.6e5, moving ground, OpenFOAM v2512 SA wall functions; morph at fine30 against xfine30"
NEXT = {1: "generator/morph defect: fix and re-register (a new study); no route is inferred from this one",
        2: "one resubmission per section 8; if still incomplete, #66 item 1 stays blocked",
        3: "section 7 (what M4 may take; the G2 route)",
        4: "section 7 for h/c 0.224 and 0.134 only; the 0.09 failures are routed by rows 5-9 applied to 0.09 alone",
        5: "steady RANS does not settle at that (mesh, h, alpha): an unsteady/solver-convergence study there; no mesh-dependence or morph conclusion",
        6: "the morph biases the derivative: revise the morph and re-register; the revised morph may not be tuned on d_R or on any T2-0c force value",
        7: "the morphed derivative depends on the baseline realisation: an ensemble-of-baselines study (or a smoother mesh family) before reuse",
        8: "the difference noise is not (only) remeshing: a solver-side convergence study (iterations, plateau, schemes)",
        9: "mesh dependence of the derivative beyond the band without remeshing noise: a near-wall/first-layer family study, together with the G2 route",
        10: "stop; no route is inferred; the next step is a recorded decision"}


def fmt(a: float) -> str:
    return "0" if a == 0 else format(a, "+g")


def rid(h, mesh, da=0.0):                      # kernel R incidence (T2-0b id), kernel M/S 0-deg baselines
    return f"sa-wf_h{h}_{mesh}_da{fmt(da)}"


def mid(h, mesh, da, variant=""):              # kernel M morphs
    return f"sa-wf_h{h}_{mesh}_morph{ {'': '', 'B2': 'B2', 'lin': 'Lin'}[variant]}-da{fmt(da)}"


def sid(h, mesh, mode, a, morph=True):         # kernel S shapes
    return f"sa-wf_h{h}_{mesh}_{'morph-' if morph else ''}{mode}{fmt(a)}mm"


def classify(r) -> str:
    if r is None or r.get("status") in INFRA:
        return "INFRA_LOSS"
    cm = r.get("check_mesh") or {}
    if r.get("status") in MECH or (r.get("status") == "COMPLETED" and (not cm.get("mesh_ok") or cm.get("failed_check_counts"))):
        return "MECHANICAL_FAIL"
    f = r.get("forces") or {}
    if r.get("status") == "COMPLETED" and f.get("cl_plateau"):
        return "UNSTEADY" if f["Cl"]["tail_rel_std"] > TH["unsteady"] else "VALID"
    return "SOLVER_FAIL"


class Gate(Exception):
    """An input case is not VALID: value False (failed input) or None (infrastructure); `bad` = {kernel:id: class}."""
    def __init__(self, value, bad):
        super().__init__(", ".join(f"{k} ({v})" for k, v in sorted(bad.items())))
        self.value, self.bad = value, bad


def scan_keys(X, mesh, h):
    """The 7 cases of a scan: kernel R remeshed (0 deg = the sweep case) or kernel M morphed (0 deg = the kernel-M baseline)."""
    return [(X, rid(h, mesh, a) if X == "R" or a == 0 else mid(h, mesh, a)) for a in A7]


def b2_keys(h, mesh):
    return [("M", mid(h, mesh, a, "B2")) for a in B2_TARGETS]


class Data:
    def __init__(self, kernels: dict, sigma_scale: float = 1.0):
        self.k, self.scale = kernels, sigma_scale

    def rec(self, key):
        return self.k[key[0]].get(key[1])

    def need(self, keys):
        kinds = {f"{k}:{i}": classify(self.rec((k, i))) for k, i in keys}
        bad = {i: c for i, c in kinds.items() if c in FAILING}
        if bad:
            raise Gate(False, bad)
        lost = {i: c for i, c in kinds.items() if c == "INFRA_LOSS"}
        if lost:
            raise Gate(None, lost)

    def cl(self, key):
        return self.rec(key)["forces"]["Cl"]["tail_mean"]

    def sigma(self, X, mesh, h) -> dict:
        keys = scan_keys(X, mesh, h)
        self.need(keys)
        y = np.array([self.cl(k) for k in keys])
        res = lambda deg: math.sqrt(float(((y - np.polyval(np.polyfit(A7, y, deg), A7)) ** 2).sum()) / (len(A7) - deg - 1))
        it = max(self.rec(k)["forces"]["Cl"]["tail_std"] for k in keys)
        fit, quad = res(3), res(2)
        return {"fit_cubic": fit, "fit_quadratic": quad, "iter": it, "eff": self.scale * max(fit, it), "nonlinear": bool(quad > TH["nonlinear"] * fit)}

    def d(self, X, mesh, h, s, variant=""):
        k = (lambda a: (X, rid(h, mesh, a))) if X == "R" else (lambda a: ("M", mid(h, mesh, a, variant)))
        self.need([k(s), k(-s)])
        return (self.cl(k(s)) - self.cl(k(-s))) / (2 * s)


def compare(a, b, sda, sdb, tol=TH["tol"], power=True, floor=TH["delta_floor"]) -> dict:
    """Registration section 6 consistency rule; `power` adds the power requirement (UNRESOLVED fails)."""
    noise = 3 * math.hypot(sda, sdb)
    big = max(abs(a), abs(b))
    allowed = max(tol * big, floor, noise)
    finite = all(math.isfinite(v) for v in (a, b, noise))
    unresolved = bool(power and noise > TH["power"] * tol * big)
    ok = finite and abs(a - b) <= allowed and not unresolved
    return {"a": a, "b": b, "allowed": allowed, "noise_3rss": noise, "margin": (abs(a - b) - allowed) / allowed if allowed else float("inf"),
            "unresolved": unresolved, "pass": bool(ok)}


# ---- gates (per height) --------------------------------------------------------------

def g6m(D, h, mesh="fine30"):
    s = D.sigma("M", mesh, h)["eff"]
    c = compare(D.d("M", mesh, h, 0.25), D.d("M", mesh, h, 1.0), s / (math.sqrt(2) * 0.25), s / math.sqrt(2))
    diff = abs(D.cl(("M", mid(h, mesh, 0.25))) - D.cl(("M", mid(h, mesh, -0.25))))
    resolved = diff >= TH["resolve"] * math.sqrt(2) * s
    return c["pass"] and resolved, {"sigma_eff": s, "consistency": c, "dCl_pm0.25": diff, "resolved": resolved}


def g3bm(D, h, mesh="fine30", finer=("xfine30",)):
    sa = D.sigma("M", mesh, h)["eff"]
    out, ok = {}, True
    for m2 in finer:
        sb = D.sigma("M", m2, h)["eff"]
        out[m2] = compare(D.d("M", mesh, h, 1.0), D.d("M", m2, h, 1.0), sa / math.sqrt(2), sb / math.sqrt(2))
        ok &= out[m2]["pass"]
    if h == 0.224:
        out["sign_ok"] = D.d("M", mesh, h, 1.0) > 0
        ok &= out["sign_ok"]
    return ok, out


def g7m(D, h, mesh):
    sm, sr = D.sigma("M", mesh, h)["eff"], D.sigma("R", mesh, h)["eff"]
    dm, dr = D.d("M", mesh, h, 1.0), D.d("R", mesh, h, 1.0)
    c = compare(dm, dr, sm / math.sqrt(2), sr / math.sqrt(2), power=False)
    return c["pass"], {**c, "undetectable_bias": c["allowed"], "dM_minus_dR_in_remesh_sigma_d": (dm - dr) / (sr / math.sqrt(2)) if sr else float("inf")}


def g8m(D, h, mesh="fine30"):
    sa = D.sigma("M", mesh, h)["eff"]
    keys = b2_keys(h, mesh)
    D.need(keys)
    sb = max(sa, D.scale * max(D.rec(k)["forces"]["Cl"]["tail_std"] for k in keys))
    out = {s: compare(D.d("M", mesh, h, s), D.d("M", mesh, h, s, "B2"), sa / (math.sqrt(2) * s), sb / (math.sqrt(2) * s)) for s in (1.0, 0.25)}
    return all(c["pass"] for c in out.values()), {str(s): c for s, c in out.items()}


def atoms_spec(mesh="fine30", finer=("xfine30",), g7_meshes=("fine30", "xfine30")):
    """(name, h) -> (gate function, every input case) of the verdict's per-height gate values. All inputs are checked before anything is computed, so a
    failed input fails the gate even when another input is lost (registration section 6 input rule)."""
    S = scan_keys
    spec = {("G6m", h): ((lambda D, h=h: g6m(D, h, mesh)), S("M", mesh, h)) for h in ATT}
    spec |= {("G3bm", h): ((lambda D, h=h: g3bm(D, h, mesh, finer)), S("M", mesh, h) + [k for m2 in finer for k in S("M", m2, h)]) for h in H}
    spec |= {(f"G7m_{m}", h): ((lambda D, h=h, m=m: g7m(D, h, m)), S("M", m, h) + S("R", m, h)) for m in g7_meshes for h in H}
    spec |= {("G8m", h): ((lambda D, h=h: g8m(D, h, mesh)), S("M", mesh, h) + b2_keys(h, mesh)) for h in H}
    return spec


def evaluate(D, spec) -> dict:
    out = {}
    for key, (fn, inputs) in spec.items():
        try:
            D.need(inputs)
            ok, detail = fn(D)
            out[key] = {"value": bool(ok), "detail": detail}
        except Gate as g:
            out[key] = {"value": g.value, "detail": {"reason": str(g), "bad_inputs": g.bad}}
        except (KeyError, TypeError, ZeroDivisionError, ValueError, np.linalg.LinAlgError) as exc:   # an undefined quantity fails
            out[key] = {"value": False, "detail": {"reason": f"undefined quantity: {type(exc).__name__}: {exc}"}}
    return out


def verdict_of(values: dict) -> str:
    if all(values.values()):
        return V_GO
    if all(v for (g, h), v in values.items() if h in ATT):
        return V_ATT
    return V_NO


def verdict(gates: dict) -> str:
    vals = {k: g["value"] for k, g in gates.items()}
    open_ = [k for k, v in vals.items() if v is None]
    seen = {verdict_of({**vals, **dict(zip(open_, combo))}) for combo in itertools.product((True, False), repeat=len(open_))}
    return seen.pop() if len(seen) == 1 else V_INC


def _comparisons(detail):
    """Every consistency-rule result inside a gate detail."""
    if isinstance(detail, dict):
        if "unresolved" in detail and "pass" in detail:
            yield detail
        for v in detail.values():
            yield from _comparisons(v)


def failure_row(name: str, g: dict) -> int:
    """Rows 5-9 for one failing per-height gate. Interpretation recorded at freeze 2 (freeze.json): a gate that fails only through noise (every failing
    comparison UNRESOLVED, or G6m's resolution test) is a noise failure, row 8, whichever gate it is; rows 6, 7, 9 need a resolved disagreement."""
    d = g["detail"]
    if set((d.get("bad_inputs") or {}).values()) & {"UNSTEADY", "SOLVER_FAIL"}:
        return 5
    failed = [c for c in _comparisons(d) if not c["pass"]]
    if d.get("sign_ok") is False or d.get("bad_inputs") or "reason" in d:
        noise = False
    else:
        noise = (bool(failed) and all(c["unresolved"] for c in failed)) or (name == "G6m" and not failed and d.get("resolved") is False)
    if noise:
        return 8
    return next(r for r, pre in ((6, "G7m"), (7, "G8m"), (8, "G6m"), (9, "G3bm")) if name.startswith(pre))


def next_action(gates: dict, v: str, mechanical_elsewhere=()) -> dict:
    """Registration section 6 next-action table: the first matching row (rows 5-9 by failure_row). `mechanical_elsewhere`: MECHANICAL_FAIL cases that are
    not gate inputs (shape, blend, coa30 sweep), reported with the row (section 8: a result, never an amendment)."""
    flag = {"mechanical_fail_outside_gate_inputs": sorted(mechanical_elsewhere)} if mechanical_elsewhere else {}
    bad = {c for g in gates.values() for c in (g["detail"].get("bad_inputs") or {}).values()}
    if "MECHANICAL_FAIL" in bad:
        return {"row": 1, "action": NEXT[1], **flag}
    if v == V_INC:
        return {"row": 2, "action": NEXT[2], **flag}
    if v == V_GO:
        return {"row": 3, "action": NEXT[3], **flag}
    failing = {k: g for k, g in gates.items() if g["value"] is False and (v != V_ATT or k[1] == 0.09)}
    rows = {f"{k[0]}@{k[1]}": failure_row(k[0], g) for k, g in failing.items()}
    row = min(rows.values(), default=10)
    if v == V_ATT:
        return {"row": 4, "action": NEXT[4], "row_for_0.09": row, "action_for_0.09": NEXT[row], "failing_at_0.09": rows, **flag}
    return {"row": row, "action": NEXT[row], "failing": rows, **flag}


# ---- labels -------------------------------------------------------------------------

def _try(fn):
    try:
        return fn()
    except Gate as g:
        return f"not computable: {g}"
    except (KeyError, TypeError, ZeroDivisionError, ValueError) as exc:
        return f"not computable: {type(exc).__name__}: {exc}"


def noise_labels(D) -> dict:
    out, ratios = {}, []
    for X in ("R", "M"):
        for m in LEVELS:
            for h in H:
                def one(X=X, m=m, h=h):
                    s = D.sigma(X, m, h)
                    d = {str(x): D.d(X, m, h, x) for x in (1.0, 0.5, 0.25)}
                    return {**s, "chi2_90_upper_fit": s["fit_cubic"] * TH["chi2_90_3dof"], "d": d,
                            "smallest_resolved_incidence_deg": 2 * math.sqrt(2) * s["eff"] / abs(d["1.0"]) if d["1.0"] else float("inf"),
                            "note": "relative to the scan's smoothness only; accuracy is bounded by G7m's band"}
                out[f"{X}:{m}:{h}"] = _try(one)
    for m in LEVELS:
        for h in H:
            r, mm = out[f"R:{m}:{h}"], out[f"M:{m}:{h}"]
            if isinstance(r, dict) and isinstance(mm, dict) and mm["eff"] > 0:
                ratios.append((f"{m}:{h}", r["eff"] / mm["eff"]))
    out["pooled_noise_reduction_R_over_M"] = math.exp(statistics.mean(math.log(x) for _, x in ratios)) if ratios else None
    out["per_pair_ratio_R_over_M"] = dict(ratios)
    return out


def remesh_gate_labels(D) -> dict:
    """G6R(M) and G3bR(M): the T2-0b G6 and G3b rules (with this registration's sigma_eff, delta and power requirement) on the remeshed scans."""
    out = {}
    for m in LEVELS:
        for h in H:
            def g6r(m=m, h=h):
                s = D.sigma("R", m, h)["eff"]
                c = compare(D.d("R", m, h, 0.25), D.d("R", m, h, 1.0), s / (math.sqrt(2) * 0.25), s / math.sqrt(2))
                diff = abs(D.cl(("R", rid(h, m, 0.25))) - D.cl(("R", rid(h, m, -0.25))))
                return {"pass": c["pass"] and diff >= TH["resolve"] * math.sqrt(2) * s, "consistency": c, "resolved": diff >= TH["resolve"] * math.sqrt(2) * s}
            out[f"G6R:{m}:{h}"] = _try(g6r)
    for m, m2 in (("med30", "fine30"), ("fine30", "xfine30")):
        for h in H:
            def g3br(m=m, m2=m2, h=h):
                sa, sb = D.sigma("R", m, h)["eff"], D.sigma("R", m2, h)["eff"]
                c = compare(D.d("R", m, h, 1.0), D.d("R", m2, h, 1.0), sa / math.sqrt(2), sb / math.sqrt(2))
                if h == 0.224:
                    c["sign_ok"] = D.d("R", m, h, 1.0) > 0
                    c["pass"] = c["pass"] and c["sign_ok"]
                return c
            out[f"G3bR:{m}-{m2}:{h}"] = _try(g3br)
    return out


def series_labels(D, exp) -> dict:
    out = {"Cl": {}, "d_M": {}, "d_R": {}, "G2_by_level": {}, "level_stats": {}}
    sig_r = {}
    for m in LEVELS:
        for h in H:
            s = _try(lambda m=m, h=h: D.sigma("R", m, h)["eff"])
            if isinstance(s, float):
                sig_r[(m, h)] = s

    def cl_noise(h):
        """2 sqrt(2) x the largest sigma_eff,R at h over the levels (unscanned h: over all remeshed scans); a missing scan makes it undefined."""
        need = [(m, h) for m in LEVELS] if h in H else [(m, x) for m in LEVELS for x in H]
        if any(k not in sig_r for k in need):
            raise ValueError(f"remeshed sigma missing for {[k for k in need if k not in sig_r]}")
        return 2 * math.sqrt(2) * max(sig_r[k] for k in need)

    def trend(v, n):
        e2, e3 = v["fine30"] - v["med30"], v["xfine30"] - v["fine30"]
        R = e3 / e2 if e2 else float("inf")
        lab = "NOT_RESOLVED" if max(abs(e2), abs(e3)) <= n else "MONOTONE" if 0 <= R < 1 else "OSCILLATORY" if -1 < R < 0 else "DIVERGENT"
        return {"values": v, "e2": e2, "e3": e3, "R": R, "noise": n, "label": lab}

    for h in HEIGHTS:
        def cl_h(h=h):
            D.need([("R", rid(h, m)) for m in LEVELS])
            v = {m: D.cl(("R", rid(h, m))) for m in LEVELS}
            res = trend(v, cl_noise(h))
            c = D.rec(("R", rid(h, "coa30")))
            res["coa30"] = c["forces"]["Cl"]["tail_mean"] if classify(c) == "VALID" else classify(c)
            return res
        out["Cl"][h] = _try(cl_h)
    for X in ("M", "R"):
        for h in H:
            def d_h(X=X, h=h):
                v, sd = {}, {}
                for m in LEVELS:
                    v[m] = D.d(X, m, h, 1.0)
                    sd[m] = D.sigma(X, m, h)["eff"] / math.sqrt(2)
                n = 2 * math.sqrt(2) * max(math.hypot(sd["med30"], sd["fine30"]), math.hypot(sd["fine30"], sd["xfine30"]))
                return trend(v, n)
            out[f"d_{X}"][h] = _try(d_h)
    peaks = {}
    for m in ("coa30", *LEVELS):
        def g2(m=m):
            D.need([("R", rid(h, m)) for h in HEIGHTS])
            cl = {h: D.cl(("R", rid(h, m))) for h in HEIGHTS}
            res = {"mean_abs_e_nominal": B.mean_abs_err(cl, exp), "e_h": {h: cl[h] / exp[h] - 1 for h in HEIGHTS}, "peak_h": max(cl, key=cl.get),
                   "G2d_E": B.rel_l1(B.increments(cl), B.increments(exp))}
            margin = cl[0.134] - (1 - TH["peak_tol"]) * max(cl[0.179], cl[0.09])
            rise = [h for h, nxt in zip(HEIGHTS[:5], HEIGHTS[1:6]) if not cl[nxt] >= (1 - TH["peak_tol"]) * cl[h]]
            res.update(peak_margin=margin, rise_breaks_after_h=rise, peak_ok=margin >= 0, G2d_pass=res["G2d_E"] <= TH["G2d"])
            if m != "coa30":
                d = {h: D.d("R", m, h, 1.0) for h in H}
                res["mean_abs_e_plus_0p15deg"] = B.mean_abs_err(cl, exp, lambda h: B.INCIDENCE_SHIFT_DEG * B.d_interp(d, h))
                res["G2_pass"] = res["mean_abs_e_nominal"] < TH["G2_mean"] and res["mean_abs_e_plus_0p15deg"] < TH["G2_mean"] and res["peak_ok"] and not rise
                if any((m, h) not in sig_r for h in H):
                    raise ValueError(f"remeshed sigma missing at {m}")
                res["peak_noise"] = 2 * math.sqrt(2) * max(sig_r[(m, h)] for h in H)
                res["peak_margin_in_noise"] = margin / res["peak_noise"] if res["peak_noise"] else float("inf")
                peaks[m] = res
            return res
        out["G2_by_level"][m] = _try(g2)
    fx = [peaks.get(m) for m in ("fine30", "xfine30")]
    if all(fx):
        if all(p["peak_margin"] >= p["peak_noise"] and not p["rise_breaks_after_h"] for p in fx):
            out["PEAK"] = "PEAK_AT_FINER_LEVELS"
        elif any(p["peak_margin"] <= -p["peak_noise"] or p["rise_breaks_after_h"] for p in fx):
            out["PEAK"] = "PEAK_NOT_AT_FINER_LEVELS"
        else:
            out["PEAK"] = "PEAK_INDETERMINATE_NOISE"
        out["xfine30_G2_pass"] = peaks["xfine30"]["G2_pass"]
    else:
        out["PEAK"] = "not computable (an input case of fine30 or xfine30 is not valid)"
    for m in ("coa30", *LEVELS):
        rs = [D.rec(("R", rid(h, m))) for h in HEIGHTS]
        rs = [r for r in rs if classify(r) in ("VALID", "UNSTEADY")]
        if rs:
            out["level_stats"][m] = {"n_layers": sorted({r.get("n_layers") for r in rs}, key=str), "cells": [min(r["mesh_cells_3d"] for r in rs), max(r["mesh_cells_3d"] for r in rs)],
                                     "max_non_orthogonality": max(float(r["check_mesh"]["max_non_orthogonality"] or 0) for r in rs),
                                     "yplus_airfoil_avg": [min(r["yplus"]["airfoil"]["average"] for r in rs if r.get("yplus")), max(r["yplus"]["airfoil"]["average"] for r in rs if r.get("yplus"))]
                                     if any(r.get("yplus") for r in rs) else None,
                                     "median_cost_to_plateau_min": statistics.median(B.case_cost_min(r) for r in rs if "pre_solver_wall_s" in r)}
    return out


def shape_labels(D) -> dict:
    out, holds = {}, {"resolved": True, "linear": True, "mesh": True, "remesh": True}
    S = lambda h, m, mode, a, morph=True: ("S", sid(h, m, mode, a, morph))
    for mode in SHAPES:
        for h in H:
            row = {}
            for m in SHAPE_MESHES:
                def one(m=m):
                    keys = [S(h, m, mode, a) for a in (-0.5, -0.25, 0.25, 0.5)] + [("S", rid(h, m))]
                    D.need(keys)
                    cl = {a: D.cl(S(h, m, mode, a)) for a in (-0.5, -0.25, 0.25, 0.5)}
                    cl[0.0] = D.cl(("S", rid(h, m)))
                    sig = D.sigma("M", m, h)["eff"]
                    dcl = {s: cl[s] - cl[-s] for s in (0.25, 0.5)}
                    d = {s: dcl[s] / (2 * s) for s in (0.25, 0.5)}
                    xs = sorted(cl)
                    ys = np.array([cl[x] for x in xs])
                    fit5 = math.sqrt(float(((ys - np.polyval(np.polyfit(xs, ys, 2), xs)) ** 2).sum()) / 2)
                    return {"dCl": dcl, "d_per_mm": d, "sigma_eff_incidence_scan": sig, "fit5_quadratic_sigma": fit5,
                            "expected_sign_ok": (d[0.5] > 0) if mode in ("camber", "flap") else None,
                            "resolved": abs(dcl[0.25]) >= TH["resolve"] * math.sqrt(2) * sig,
                            "linearity": compare(d[0.25], d[0.5], sig / (math.sqrt(2) * 0.25), sig / (math.sqrt(2) * 0.5), power=False, floor=0.0)}
                row[m] = _try(one)

            def agree():
                a, b = row["med30"], row["fine30"]
                return compare(a["d_per_mm"][0.5], b["d_per_mm"][0.5], a["sigma_eff_incidence_scan"] / (math.sqrt(2) * 0.5),
                               b["sigma_eff_incidence_scan"] / (math.sqrt(2) * 0.5), power=False, floor=0.0)

            def vs_remesh():
                keys = [S(h, "fine30", mode, a, False) for a in (-0.5, 0.5)]
                D.need(keys)
                dr = (D.cl(keys[1]) - D.cl(keys[0])) / 1.0
                sr = D.sigma("R", "fine30", h)["eff"]
                f = row["fine30"]
                return compare(f["d_per_mm"][0.5], dr, f["sigma_eff_incidence_scan"] / (math.sqrt(2) * 0.5), sr / (math.sqrt(2) * 0.5), power=False, floor=0.0)

            row["med30_vs_fine30"] = _try(agree) if all(isinstance(row[m], dict) for m in SHAPE_MESHES) else "not computable"
            row["morph_vs_remesh_fine30"] = _try(vs_remesh) if isinstance(row["fine30"], dict) else "not computable"
            ok = lambda x, k=None: isinstance(x, dict) and bool(x[k] if k else x["pass"])
            holds["resolved"] &= all(ok(row[m], "resolved") for m in SHAPE_MESHES)
            holds["linear"] &= all(isinstance(row[m], dict) and row[m]["linearity"]["pass"] for m in SHAPE_MESHES)
            holds["mesh"] &= ok(row["med30_vs_fine30"])
            holds["remesh"] &= ok(row["morph_vs_remesh_fine30"])
            out[f"{mode}:{h}"] = row
    out["label"] = ("SHAPE_RESOLVED_CONSISTENT" if all(holds.values()) else "SHAPE_SMOOTH_RESOLVED" if holds["resolved"] else "SHAPE_NOT_RESOLVED")
    out["holds"] = holds
    return out


def replication_labels(D, t20b_dir: Path | None, cpu: dict) -> dict:
    out = {}
    if t20b_dir and t20b_dir.is_dir():
        import gzip
        rows = []
        for p in sorted(t20b_dir.glob("cases/sa-wf_h*/case_result.json")):
            old = json.loads(p.read_text())
            new = D.k["R"].get(old["id"])
            man = p.parent / "case_manifest.json.gz"
            if new is None or old.get("forces") is None or not man.is_file():
                continue
            old_sha = json.loads(gzip.decompress(man.read_bytes()))["mesh_msh_sha256"]
            if classify(new) in ("VALID", "UNSTEADY"):
                rows.append((old["id"], old_sha == new.get("mesh_msh_sha256"), abs(new["forces"]["Cl"]["tail_mean"] / old["forces"]["Cl"]["tail_mean"] - 1)))
        if rows:
            bit = all(s and r <= TH["bitwise"] for _, s, r in rows)
            out["vs_T20B"] = {"cases": len(rows), "identical_mesh_sha": sum(s for _, s, _ in rows), "max_rel_dCl": max(r for _, _, r in rows),
                              "label": "REPLICATED_BITWISE" if bit else "NOT_BITWISE", "cpu_models": cpu}
    rows = []
    for k in ("M", "S"):
        for i, r in D.k[k].items():
            ref = D.k["R"].get(i)
            if "_da0" in i and "morph" not in i and ref and classify(r) in ("VALID", "UNSTEADY") and classify(ref) in ("VALID", "UNSTEADY"):
                rows.append((f"{k}:{i}", r.get("mesh_msh_sha256") == ref.get("mesh_msh_sha256"), r["forces"]["Cl"]["tail_mean"] == ref["forces"]["Cl"]["tail_mean"]))
    out["cross_kernel"] = {"cases": len(rows), "identical_mesh_sha": sum(s for _, s, _ in rows), "identical_Cl": sum(c for _, _, c in rows),
                           "label": "CROSS_KERNEL_IDENTICAL" if rows and all(s and c for _, s, c in rows) else "CROSS_KERNEL_DIFFERENT",
                           "cpu_models": cpu, "note": "a difference with a different CPU model is reported, not a defect"}
    return out


def blend_labels(D, gates) -> dict:
    out = {}
    for h in H:
        def one(h=h):
            dl, dm = D.d("M", "fine30", h, 1.0, "lin"), D.d("M", "fine30", h, 1.0)
            band = gates[("G3bm", h)]["detail"]["xfine30"]["allowed"]
            return {"d_linear": dl, "d_smoothstep": dm, "abs_diff_in_G3bm_bands": abs(dl - dm) / band}
        out[h] = _try(one)
    return out


# ---- report -------------------------------------------------------------------------

def jkey(d):
    return {f"{k[0]}@{k[1]}" if isinstance(k, tuple) else str(k): v for k, v in d.items()}


def descriptive(kernels) -> list[str]:
    lines = ["| kernel | case | class | Cl | Cd | Cl raw tail rel std | Cl block rel std | iters to plateau | cost min | capped wall min | cells | layers | max non-orth | "
             "morph area ratio | s per cell-iter (x1e6) | RSS MB | y+ airfoil min/avg/max |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    fmt_ = lambda v, s=".4f": "-" if v is None else format(v, s)
    for k in ("R", "M", "S"):
        for i, r in sorted(kernels[k].items()):
            f = r.get("forces") or {}
            cl, cd = f.get("Cl") or {}, f.get("Cd") or {}
            mo, y = r.get("morph") or {}, ((r.get("yplus") or {}).get("airfoil") or {})
            cost = B.case_cost_min(r) if classify(r) in ("VALID", "UNSTEADY") and "pre_solver_wall_s" in r else None
            solver = sum(s["wall_s"] for s in r.get("stages", []) if s["stage"].startswith("simpleFoam"))
            per = solver / (f["history_rows"] * r["mesh_cells_3d"]) * 1e6 if f.get("history_rows") and r.get("mesh_cells_3d") else None
            rss = max((s.get("peak_rss_mb_sampled") or 0 for s in r.get("stages", [])), default=0)
            lines.append(f"| {k} | {i} | {classify(r)} | {fmt_(cl.get('tail_mean'))} | {fmt_(cd.get('tail_mean'))} | {fmt_(cl.get('tail_rel_std'), '.2e')} | "
                         f"{fmt_(f.get('cl_block_rel_std'), '.2e')} | {f.get('iterations_to_plateau', '-')} | {fmt_(cost, '.1f')} | {fmt_((r.get('total_wall_s') or 0) / 60, '.1f')} | "
                         f"{r.get('mesh_cells_3d', '-')} | {r.get('n_layers', '-')} | {(r.get('check_mesh') or {}).get('max_non_orthogonality', '-')} | "
                         f"{fmt_(mo.get('area_ratio_min'), '.3f')}-{fmt_(mo.get('area_ratio_max'), '.3f')} | {fmt_(per, '.2f')} | {rss:.0f} | "
                         f"{fmt_(y.get('min'), '.1f')}/{fmt_(y.get('average'), '.1f')}/{fmt_(y.get('max'), '.1f')} |")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("remesh", "morph", "shape"):
        ap.add_argument(f"--{k}", type=Path, nargs="+", required=True, help=f"kernel {k} output dir(s): first run, then an optional resubmission")
    ap.add_argument("--t20b", type=Path, default=T20B_W, help="T2-0b kernel-W output (replication label only)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if (a.out / "verdict.json").exists():
        raise SystemExit("verdict.json exists: the registered analysis is written once")
    exp = {float(h): p["Cl"] for h, p in json.loads(B.EXP.read_text())["points"].items()}
    loaded = {k: B.load_runs(getattr(a, n)) for k, n in (("R", "remesh"), ("M", "morph"), ("S", "shape"))}
    kernels = {k: v[0] for k, v in loaded.items()}
    cpu = {}
    for k, n in (("R", "remesh"), ("M", "morph"), ("S", "shape")):
        for d in getattr(a, n):
            res = d / "result.json"
            cpu[f"{k}:{d}"] = (B._read(res) or {}).get("cpu_model") if res.is_file() else None
    D = Data(kernels)
    spec = atoms_spec()
    gates = evaluate(D, spec)
    v = verdict(gates)
    inputs = {f"{k}:{i}" for _, keys in spec.values() for k, i in keys}
    mech = [f"{k}:{i}" for k, cs in kernels.items() for i, r in cs.items() if classify(r) == "MECHANICAL_FAIL" and f"{k}:{i}" not in inputs]
    act = next_action(gates, v, mech)
    D2 = Data(kernels, 2.0)
    g2s = evaluate(D2, atoms_spec())
    med = evaluate(D, atoms_spec("med30", ("fine30", "xfine30"), ("med30",)))
    labels = {"noise": noise_labels(D), "SURVIVES_2SIGMA": {f"{k[0]}@{k[1]}": g["value"] for k, g in g2s.items()},
              "G6M_009": _try(lambda: {"pass": g6m(D, 0.09)[0], **g6m(D, 0.09)[1]}), "remeshed_rules": remesh_gate_labels(D), "BLEND": blend_labels(D, gates),
              "MED30": {"full": verdict_of({k: bool(g["value"]) for k, g in med.items()}) == V_GO,
                        "attached": verdict_of({k: bool(g["value"]) for k, g in med.items()}) in (V_GO, V_ATT), "gates": jkey(med)},
              "series": series_labels(D, exp), "replication": replication_labels(D, a.t20b, cpu), "shapes": shape_labels(D),
              "UNSTEADY_cases": {f"{k}:{i}": {"tail_rel_std": r["forces"]["Cl"]["tail_rel_std"], "tail_min": r["forces"]["Cl"]["tail_min"], "tail_max": r["forces"]["Cl"]["tail_max"]}
                                 for k, cs in kernels.items() for i, r in cs.items() if classify(r) == "UNSTEADY"}}
    classes = {}
    for cs in kernels.values():
        for r in cs.values():
            classes[classify(r)] = classes.get(classify(r), 0) + 1
    hashes = {p: h for _, _, hs in loaded.values() for p, h in hs.items()}
    out = {"verdict": v, "next_action": act, "scope": SCOPE, "gates": jkey(gates), "labels": labels, "predicted": PREDICTED, "thresholds": TH,
           "thresholds_set_after_exploratory_visible": True, "thresholds_set_after_t20b_visible": True, "case_classes": classes,
           "runs_used": {n: [str(p) for p in getattr(a, n)] for n in ("remesh", "morph", "shape")},
           "cases_from_resubmission": sorted(f"{k}:{i}" for k, v_ in loaded.items() for i, o in v_[1].items() if o),
           "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "registration": str(REG.relative_to(ROOT)),
           "input_sha256": {**hashes, **{str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (B.EXP, REG, Path(B.__file__))}},
           "qualification_flags": "unchanged (all false; shape_update_allowed=false)"}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "verdict.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    word = {True: "PASS", False: "FAIL", None: "UNDETERMINED"}
    md = [f"# T2-0c registered verdict: **{v}**", "", f"Scope: {SCOPE}. Thresholds were set after T2-0a and T2-0b were visible (registration section 2).", "",
          f"Next action (registration section 6, row {act['row']}): {act['action']}" + (f" For h/c 0.09: row {act['row_for_0.09']}: {act['action_for_0.09']}" if "row_for_0.09" in act else ""),
          "", "| gate @ h/c | result | detail |", "|---|---|---|"]
    md += [f"| {k[0]} @ {k[1]} | {word[g['value']]} | `{json.dumps(g['detail'], default=str)[:700]}` |" for k, g in gates.items()]
    md += ["", "## Labels (never change the verdict)", "", "```json", json.dumps(labels, indent=1, default=str), "```", "", "## Cases", "", *descriptive(kernels), ""]
    (a.out / "analysis.md").write_text("\n".join(md))
    print(v)


if __name__ == "__main__":
    main()
