#!/usr/bin/env python3
"""T2-0d (#57, REGISTERED): the registered verdict. Implements sections 4 and 6 of docs/t20d_registration_2026_10_21.md (that text governs; a disagreement
is a defect here). Reads the downloaded outputs of the six kernels (XP1, XP2, XO1, XO2, F1, F2; a resubmission directory may follow a first run and replaces
whole sets only) and the digitised experiment. Every statistic is computed here from the runs' coefficient files. Writes analysis.md and verdict.json once;
`--completeness` prints only the lost run ids and the class-family counts (registration section 8), no value."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_t20b as B  # noqa: E402  (experiment file, run-record reader and the G2 helpers reused unchanged)
import analyze_t20c as C  # noqa: E402  (the T2-0c consistency rule C / C_P reused unchanged)
import build_t20d_kernel as K  # noqa: E402  (the registered geometry lists, ids and sets, single-sourced from the runner template)
import t20d_case as S  # noqa: E402  (time steps, end times and the transient, single-sourced from the stage module)

ROOT = B.ROOT
REG = ROOT / "docs/t20d_registration_2026_10_21.md"
KERNELS = ("xp1", "xp2", "xo1", "xo2", "f1", "f2")
HEIGHTS, H3 = B.HEIGHTS, (0.224, 0.134, 0.09)
A7 = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)
URANS = ("U", "Udt2", "Udt05", "US1")
U_INF = 30.0
TH = {"theta": 1e-3, "settled_drift": 5e-4, "growth": 1.5, "growth_floor": 1e-4, "drift_floor": 5e-4, "drift_cap": 2e-3, "amp": (0.8, 1.25), "kmin": 3.0,
      "klow": 5.0, "hann_var": math.sqrt(1.5), "se_floor": 1e-6, "plateau": 0.005, "block": 20, "tail": 0.2, "tol_eq": 5e-3, "gt_mean": 2.5e-3, "gt_cap": 1e-2,
      "gt_freq": 0.10, "gt_freq_bins": 1.5, "gt_deriv": 0.10, "tol": 0.25, "resolve": 5.0, "peak_tol": B.PEAK_TOL, "G2_mean": B.TH["G2_mean"], "G2d": B.TH["G2d"],
      "robust": 0.005, "level_step": 0.05, "chi2_q": 0.2, "cost_median_min": 15.0, "cost_max_min": 30.0, "r5_min": 27.5, "blowup": 100.0}
INFRA_ST = {"NOT_RUN_TIME_BUDGET", "RUNNER_EXCEPTION", "DEADLINE_LIMITED", "NOT_RUN"}
MECH_ST = {"GENERATOR_FAILED", "gmshToFoam_FAILED", "gmshToFoam_TIMEOUT", "checkMesh_FAILED", "checkMesh_TIMEOUT", "TOPOLOGY_CHANGED", "BASE_TOPOLOGY_MISSING",
           "STAGE2_PREP_FAILED", "MESH_FAILED", "PARSE_FAILED"}
VALID_U = ("VALID_SETTLED", "VALID_PERIODIC")
INVALID = ("SOLVER_FAIL", "NONSTATIONARY", "TOO_FEW_CYCLES")
# gate outcomes and the precedence orders of registration section 6.3
PASS, FV, FT, FI, MEC, UND, NOISE = "PASS", "FAIL_VALUE", "FAIL_TIMESTEP", "FAIL_INPUT", "MECHANICAL", "UNDETERMINED", "INDETERMINATE_NOISE"
LEVEL_ORDER = (FT, FV, MEC, FI, UND, NOISE, PASS)
DATA_ORDER = (FV, FT, MEC, FI, UND, NOISE, PASS)
DIFF_ORDER = (FT, FV, MEC, FI, UND, PASS)
V_DEF, V_INC, V_Q, V_QU, V_NO = "T20D_PIPELINE_DEFECT", "T20D_INCOMPLETE", "T20D_QUALIFIED_XFINE30_PEAK", "T20D_QUALIFIED_UNAFFORDABLE", "T20D_NO_GO"
PREDICTED = {"Q1": "x09 UNSTEADY_IN_URANS; x134 and f09+1 uncertain; controls OK", "DATA": "G2u(fine30) pass or noise-indeterminate; G2u(xfine30) uncertain",
             "DIFF": "GT134 pass; G6u, G3bu uncertain; G8u fail; GSu pass", "cost": "not affordable",
             "verdict": f"{V_NO} with DIFF FAIL_VALUE most likely; {V_QU} possible; {V_Q} not expected"}
SCOPE = ("2D single-element section (Tyrrell 026), Re_c 4.6e5, moving ground, OpenFOAM v2512 SA wall functions; time-averaged URANS (dt 1e-5 s, 6 T_c transient, "
         "10 T_c window) on fine30/xfine30; differences at h/c 0.134 on xfine30")


def fmt(a: float) -> str:
    return "0" if a == 0 else format(a, "+g")


def gid(h, mesh, a=0.0, morph=False, variant="", mode="incidence"):
    """Geometry ids (T2-0c convention, = the runner's case_id)."""
    return K._case_id("morph" if morph else "remesh", h, mesh, mode, a, variant)


# ---- statistics (registration section 4) -----------------------------------------------

def read_coefficients(paths) -> tuple[np.ndarray, np.ndarray]:
    """Time and Cl of forceCoeffs coefficient files (gzipped), concatenated in the given order; columns from each file's last '#' header line."""
    t, cl = [], []
    for p in paths:
        with gzip.open(p, "rt") as fh:
            text = fh.read()
        header = [l for l in text.splitlines() if l.startswith("#")][-1].lstrip("#").split()
        a = np.loadtxt(text.splitlines(), comments="#", ndmin=2)
        t.append(a[:, header.index("Time")])
        cl.append(a[:, header.index("Cl")])
    return (np.concatenate(t), np.concatenate(cl)) if t else (np.array([]), np.array([]))


def _se(x: np.ndarray, nb: int) -> tuple[float, np.ndarray]:
    m = len(x) // nb
    b = x[len(x) - nb * m:].reshape(nb, m).mean(1)
    return float(b.std(ddof=1) / math.sqrt(nb)), b


def urans_stats(t: np.ndarray, cl: np.ndarray, dt: float, t_a: float, t_b: float) -> dict:
    """Window t_a + dt/2 < t <= t_b + dt/2; the class and the Cl/noise of a U-type run (section 4)."""
    w_t = t[(t > t_a + dt / 2) & (t <= t_b + dt / 2)]
    w = cl[(t > t_a + dt / 2) & (t <= t_b + dt / 2)]
    n, T_w = len(w), t_b - t_a
    if n < 100:
        return {"class": "SOLVER_FAIL", "reason": f"window has {n} rows"}
    mean, std = float(w.mean()), float(w.std())
    h1, h2 = w[:n // 2], w[n // 2:]
    q = np.array_split(w, 4)
    sq = [float(x.std()) for x in q]
    hann = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)
    m_h = float((hann * w).sum() / hann.sum())
    nfft = 8 * n
    p = np.abs(np.fft.rfft((w - mean) * hann, nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, d=dt)
    i0 = int(np.searchsorted(freqs, 1.0 / T_w))
    i = i0 + int(np.argmax(p[i0:]))
    f = float(freqs[i])
    if i0 < i < len(p) - 1 and min(p[i - 1:i + 2]) > 0:
        lp = np.log(p[i - 1:i + 2])
        den = lp[0] - 2 * lp[1] + lp[2]
        if den < 0:
            f += 0.5 * (lp[0] - lp[2]) / den * float(freqs[1] - freqs[0])
    k = f * T_w
    se10, b10 = _se(w, 10)
    se5, _ = _se(w, 5)
    r1 = float(np.corrcoef(b10[:-1], b10[1:])[0, 1]) if b10.std() > 0 else 0.0
    tc = (np.arange(10) + 0.5) * T_w / 10
    X = tc - tc.mean()
    slope = float((X * (b10 - b10.mean())).sum() / (X * X).sum())
    resid = b10 - (b10.mean() + slope * X)
    se_slope = math.sqrt(float((resid ** 2).sum()) / 8 / float((X * X).sum()))
    drift, se_drift = abs(slope) * T_w, se_slope * T_w
    th2 = w_t[n // 2:]
    slope_h2 = float(np.polyfit(th2 - th2.mean(), h2, 1)[0])
    m2 = float(h2.mean())
    out = {"rows": n, "T_w": T_w, "mean": mean, "std": std, "r": std / abs(mean), "m_hann": m_h, "f": f, "k": k, "St_c": f * B.CHORD / U_INF,
           "SE10": se10, "SE5": se5, "lag1": r1, "drift": drift, "se_drift": se_drift, "s_quarters": sq, "s_h1": float(h1.std()), "s_h2": float(h2.std()),
           "r_h2": float(h2.std()) / abs(m2), "drift_h2": abs(slope_h2) * T_w / 2, "mean_h2": m2}
    growth_ok = sq[3] <= TH["growth"] * sq[2] or sq[3] < TH["growth_floor"] * abs(m2)
    if out["r_h2"] < TH["theta"] and out["drift_h2"] <= TH["settled_drift"] * abs(m2) and growth_ok:
        return {**out, "class": "VALID_SETTLED", "m": m2, "se": max(_se(h2, 5)[0], TH["se_floor"] * abs(m2))}
    amp = out["s_h2"] / out["s_h1"] if out["s_h1"] > 0 else float("inf")
    stationary = (drift <= max(3 * se_drift, TH["drift_floor"] * abs(m_h)) and drift <= TH["drift_cap"] * abs(m_h) and TH["amp"][0] <= amp <= TH["amp"][1])
    out["amp_ratio"] = amp
    if not stationary:
        return {**out, "class": "NONSTATIONARY"}
    if k < TH["kmin"]:
        return {**out, "class": "TOO_FEW_CYCLES"}
    b_h = math.sqrt(2) * std / (math.pi * k * (k * k - 1))
    return {**out, "class": "VALID_PERIODIC", "m": m_h, "se": max(TH["hann_var"] * se10, TH["hann_var"] * se5, b_h), "bias_bound": b_h,
            "low_freq": bool(k < TH["klow"])}


def _rel_drift(v: np.ndarray) -> float:
    x = np.arange(len(v)) - (len(v) - 1) / 2
    return abs(float((x * (v - v.mean())).sum() / (x * x).sum() * (len(v) - 1))) / abs(float(v.mean()))


def steady_stats(cl: np.ndarray) -> dict:
    """T2-0b's plateau and the raw tail relative std over the last 20 % (at least 50 rows); CONVERGED = plateau and r_tail < theta."""
    n = min(len(cl), max(50, math.ceil(len(cl) * TH["tail"])))
    tail = cl[-n:]
    blocks = tail[len(tail) % TH["block"]:].reshape(-1, TH["block"]).mean(1)
    ok = len(blocks) > 2
    brs = float(blocks.std() / abs(blocks.mean())) if ok else None
    brd = _rel_drift(blocks) if ok else None
    plateau = bool(ok and brs < TH["plateau"] and brd < TH["plateau"])
    r_tail = float(tail.std() / abs(tail.mean()))
    return {"rows": len(cl), "m": float(tail.mean()), "tail_std": float(tail.std()), "r_tail": r_tail, "block_rel_std": brs, "block_rel_drift": brd,
            "plateau": plateau, "class": "CONVERGED" if plateau and r_tail < TH["theta"] else "NOT_CONVERGED"}


# ---- runs ---------------------------------------------------------------------------------

class Runs:
    """(kernel, run id) -> record, run directory, class and statistics (computed once, on demand)."""

    def __init__(self, recs: dict, dirs: dict):
        self.recs, self.dirs, self._c = recs, dirs, {}

    def rec(self, key):
        return self.recs.get(key)

    def stats(self, key) -> dict:
        if key not in self._c:
            self._c[key] = self._classify(key)
        return self._c[key]

    def cls(self, key) -> str:
        return self.stats(key)["class"]

    def m(self, key) -> float:
        return self.stats(key)["m"]

    def se(self, key) -> float:
        return self.stats(key).get("se", 0.0)

    def _classify(self, key) -> dict:
        r = self.recs.get(key)
        if r is None:
            return {"class": "INFRA_LOSS", "reason": "no record"}
        st = r.get("status", "")
        nan = bool((r.get("solver") or {}).get("nan_in_log"))
        if st in INFRA_ST:
            return {"class": "INFRA_LOSS", "reason": st}
        if st in MECH_ST:
            return {"class": "MECHANICAL_FAIL", "reason": st}
        if st.endswith("_TIMEOUT"):
            return {"class": "SOLVER_FAIL", "reason": f"{st} with NaN"} if nan else {"class": "INFRA_LOSS", "reason": f"TIME_LIMITED ({st})"}
        if st == "SOURCE_NOT_COMPLETED":
            src = self.cls((key[0], r.get("source_run", "")))
            return {"class": src if src in ("MECHANICAL_FAIL", "INFRA_LOSS") else "SOLVER_FAIL", "reason": f"source {r.get('source_run')} {src}"}
        if st != "COMPLETED":
            return {"class": "SOLVER_FAIL", "reason": st}
        files = sorted(self.dirs[key].glob("coefficient*.dat.gz")) if key in self.dirs else []
        try:
            t, cl = read_coefficients(files)
        except (OSError, ValueError, IndexError) as exc:
            return {"class": "SOLVER_FAIL", "reason": f"coefficient file unreadable: {type(exc).__name__}"}
        if len(cl) < 2 or not np.isfinite(cl).all() or np.abs(cl).max() > TH["blowup"]:
            return {"class": "SOLVER_FAIL", "reason": "coefficient history empty, non-finite or |Cl| > 100"}
        kind = r.get("kind")
        if kind in URANS:
            dt, end = S.DT[kind], (r.get("stage2") or {}).get("end_time_s") or S.END_TIME_S[kind]
            if t[-1] < end - dt / 2:
                return {"class": "SOLVER_FAIL", "reason": f"history ends at {t[-1]:.6g} s < {end} s"}
            return urans_stats(t, cl, dt, S.T_TR_S, end)
        return steady_stats(cl)


def lost(r) -> bool:
    """A lost run, from its status alone (no value read): no record, an infrastructure status, or a timeout without NaN."""
    if r is None or r.get("status") in INFRA_ST:
        return True
    st = r.get("status", "")
    return st.endswith("_TIMEOUT") and st not in MECH_ST and not (r.get("solver") or {}).get("nan_in_log")


def load(kdirs: dict) -> tuple[Runs, dict]:
    """First run per kernel, a later run replacing whole sets only where the first run's set has a lost run and the later one's is complete
    (registration section 8). Returns the runs and the provenance."""
    reg = K.registered()
    recs, dirs, prov = {}, {}, {}
    for k in KERNELS:
        runs = []
        for d in kdirs.get(k, []):
            found, where = {}, {}
            res = Path(d) / "result.json"
            for r in ((B._read(res) or {}).get("runs", []) if res.is_file() else []):
                found[r["id"]] = r
            for p in sorted(Path(d).glob("cases/*/case_result.json")):
                r = B._read(p)
                if r is not None:
                    found[r["id"]], where[r["id"]] = r, p.parent
            runs.append((found, where, str(d)))
        sets = {}
        for c, kinds in reg[k]:
            sets.setdefault(K.set_key(c), []).extend(f"{K._case_id(*c)}__{x}" for x in ("S0", *kinds))
        for skey, ids in sets.items():
            pick = next((i for i, (found, _, _) in enumerate(runs) if not any(lost(found.get(j)) for j in ids)), 0)
            if runs:
                found, where, src = runs[pick]
                for j in ids:
                    recs[(k, j)] = found.get(j)
                    if j in where:
                        dirs[(k, j)] = where[j]
                    prov[f"{k}:{j}"] = src
    return Runs(recs, dirs), prov


# ---- gate machinery -------------------------------------------------------------------------

class Out(Exception):
    """A gate whose inputs are not all valid: outcome MECHANICAL, FAIL_INPUT or UNDETERMINED; `bad` = {key: class}."""

    def __init__(self, outcome, bad):
        super().__init__(", ".join(f"{k[0]}:{k[1]} ({v})" for k, v in sorted(bad.items())))
        self.outcome, self.bad = outcome, bad


def need(R: Runs, keys) -> None:
    kinds = {k: R.cls(k) for k in keys}
    for outcome, classes in ((MEC, ("MECHANICAL_FAIL",)), (FI, INVALID), (UND, ("INFRA_LOSS",))):
        bad = {k: c for k, c in kinds.items() if c in classes}
        if bad:
            raise Out(outcome, bad)
    other = {k: c for k, c in kinds.items() if c not in VALID_U}
    if other:
        raise Out(FI, other)


def gate(fn) -> dict:
    """Run a gate function returning (passed, detail, failure outcome); map input problems and undefined quantities to outcomes."""
    try:
        ok, detail, fail = fn()
        return {"outcome": PASS if ok else fail, "detail": detail}
    except Out as o:
        return {"outcome": o.outcome, "detail": {"bad_inputs": {f"{k[0]}:{k[1]}": v for k, v in o.bad.items()}}}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, np.linalg.LinAlgError) as exc:
        return {"outcome": FV, "detail": {"reason": f"undefined quantity: {type(exc).__name__}: {exc}"}}


def worst(outcomes, order) -> str:
    return min(outcomes, key=order.index) if outcomes else PASS


def gt_rule(a: dict, b: dict) -> dict:
    """GT(a, b) of registration section 6.3 on two valid runs' statistics."""
    tol = min(max(TH["gt_mean"] * abs(a["m"]), 3 * math.hypot(a["se"], b["se"])), TH["gt_cap"] * abs(a["m"]))
    out = {"class_a": a["class"], "class_b": b["class"], "m_a": a["m"], "m_b": b["m"], "allowed": tol, "same_class": a["class"] == b["class"],
           "mean_ok": abs(a["m"] - b["m"]) <= tol}
    ok = out["same_class"] and out["mean_ok"]
    if ok and a["class"] == "VALID_PERIODIC":
        out["amp_ratio"] = a["r"] / b["r"]
        out["f_a"], out["f_b"] = a["f"], b["f"]
        out["freq_ok"] = abs(a["f"] - b["f"]) <= max(TH["gt_freq"] * max(a["f"], b["f"]), TH["gt_freq_bins"] / min(a["T_w"], b["T_w"]))
        ok = TH["amp"][0] <= out["amp_ratio"] <= TH["amp"][1] and out["freq_ok"]
    out["pass"] = bool(ok)
    return out


def compare_p(a, b, sda, sdb, tol=TH["tol"]):
    return C.compare(a, b, sda, sdb, tol=tol, power=True)


# ---- keys -------------------------------------------------------------------------------------

def k_u(kernel, geometry, kind="U"):
    return (kernel, f"{geometry}__{kind}")


def g2_key(L: str, h: float, a: float = 0.0):
    """The G2u input of level L at (h, a) (registration section 6.3)."""
    if L == "fine30":
        return k_u("f1", gid(h, "fine30", a))
    if h == 0.134:
        return k_u("xp1", gid(0.134, "xfine30")) if a == 0 else k_u("xo2", gid(0.134, "xfine30", a))
    return k_u("xo1" if h in (0.224, 0.09) else "xo2", gid(h, "xfine30", a))


def scan_key(L: str, a: float, variant: str = ""):
    """The base-B scan (variant "") or the B' scan ("B2") at h/c 0.134 on level L."""
    k = "xp1" if L == "xfine30" else "f2"
    if variant:
        k = "xp2" if L == "xfine30" else "f2"
        return k_u(k, gid(0.134, L, a, morph=True, variant="B2"))
    return k_u(k, gid(0.134, L) if a == 0 else gid(0.134, L, a, morph=True))


def shape_key(mode: str, a: float):
    return k_u("xp2", gid(0.134, "xfine30", a, morph=True, mode=mode))


Q1_TARGETS = {"x09-1": ("xo1", gid(0.09, "xfine30", -1.0)), "x09 0": ("xo1", gid(0.09, "xfine30")), "x09+1": ("xo1", gid(0.09, "xfine30", 1.0)),
              "x134 0": ("xp1", gid(0.134, "xfine30")), "x134+1": ("xp1", gid(0.134, "xfine30", 1.0, morph=True)), "f09+1": ("f1", gid(0.09, "fine30", 1.0))}
Q1_CONTROLS = {"x224 0": ("xo1", gid(0.224, "xfine30")), "x134-1": ("xp1", gid(0.134, "xfine30", -1.0, morph=True)), "f09 0": ("f1", gid(0.09, "fine30"))}
GTD = {"xfine30": ("x224 0", "x134 0", "x09-1", "x09 0", "x09+1"), "fine30": ("f09+1",)}
GTD_COND = {**Q1_TARGETS, **Q1_CONTROLS}
US1_AT = ("x134 0", "x09 0")


# ---- Q1 (registration section 6.2) --------------------------------------------------------------

def gt_at(R: Runs, kernel: str, geometry: str, other: str = "Udt2") -> dict:
    """GT(U, other) on one geometry, with input validity: {'outcome', 'detail'}."""
    def fn():
        a, b = k_u(kernel, geometry), k_u(kernel, geometry, other)
        need(R, [a, b])
        g = gt_rule(R.stats(a), R.stats(b))
        return g["pass"], g, FT
    return gate(fn)


def q1_class(R: Runs, name: str, kernel: str, geometry: str) -> dict:
    u, s0, s1 = k_u(kernel, geometry), (kernel, f"{geometry}__S0"), (kernel, f"{geometry}__S1")
    has_dt2 = k_u(kernel, geometry, "Udt2") in set(expected_keys())
    out = {"U": R.cls(u), "S0": R.cls(s0), "S1": R.cls(s1), "time_step": gt_at(R, kernel, geometry) if has_dt2 else {"outcome": "not registered"}}
    if R.cls(u) in VALID_U:
        st = R.stats(u)
        out.update(m_U=st["m"], r_U=st["r"], St_c=st["St_c"] if st["class"] == "VALID_PERIODIC" else None, se_U=st["se"])
    for k, lab in ((s0, "S0"), (s1, "S1")):
        if R.cls(k) in ("CONVERGED", "NOT_CONVERGED"):
            out[f"Cl_{lab}"] = R.m(k)
    ts = out["time_step"]["outcome"] == PASS
    if name in Q1_CONTROLS:
        ok = (R.cls(u) == "VALID_SETTLED" and R.cls(s0) == "CONVERGED" and R.cls(s1) == "CONVERGED"
              and all(abs(R.m(k) - R.m(u)) <= TH["tol_eq"] * abs(R.m(u)) for k in (s0, s1)))
        out["label"] = "CONTROL_OK" if ok else "CONTROL_NOT_OK"
        return out
    lab = "INDETERMINATE"
    if ts and R.cls(u) == "VALID_SETTLED" and R.cls(s1) in ("CONVERGED", "NOT_CONVERGED"):
        if R.cls(s1) == "NOT_CONVERGED":
            lab = "STEADY_URANS_ONLY"
        else:
            lab = "STEADY_SOLVER_ARTEFACT" if abs(R.m(s1) - R.m(u)) <= TH["tol_eq"] * abs(R.m(u)) else "STEADY_BRANCH_MISMATCH"
    elif ts and R.cls(u) == "VALID_PERIODIC":
        lab = "UNSTEADY_IN_URANS"
    if name in US1_AT:   # an invalid US1 leaves the start dependence unchecked: INDETERMINATE (interpretation recorded at freeze 2)
        us1 = k_u(kernel, geometry, "US1")
        out["US1"] = R.cls(us1)
        if R.cls(u) in VALID_U and R.cls(us1) in VALID_U:
            a, b = R.stats(u), R.stats(us1)
            out["m_US1"] = b["m"]
            if (a["class"] != b["class"] or abs(a["m"] - b["m"]) > max(TH["tol_eq"] * abs(a["m"]), 3 * math.hypot(a["se"], b["se"]))
                    or (a["class"] == "VALID_PERIODIC" and not TH["amp"][0] <= a["r"] / b["r"] <= TH["amp"][1])):
                lab = "START_DEPENDENT"
        else:
            lab = "INDETERMINATE"
    out["label"] = lab
    return out


def q1_labels(R: Runs) -> dict:
    per = {n: q1_class(R, n, *v) for n, v in {**Q1_TARGETS, **Q1_CONTROLS}.items()}

    def form(targets, controls):
        if any(per[c]["label"] != "CONTROL_OK" for c in controls) or any(per[t]["label"] in ("INDETERMINATE", "START_DEPENDENT") for t in targets):
            return "INDETERMINATE"
        if any(per[t]["label"] in ("UNSTEADY_IN_URANS", "STEADY_URANS_ONLY", "STEADY_BRANCH_MISMATCH") for t in targets):
            return "URANS_REQUIRED"
        return "STEADY_RELAXED_SUFFICES"
    return {"per_condition": per, "Q1_FORM_134": form(("x134 0", "x134+1"), ("x134-1", "x224 0")),
            "Q1_FORM_09": form(("x09-1", "x09 0", "x09+1", "f09+1"), ("x224 0", "f09 0"))}


# ---- DATA (registration section 6.3) ------------------------------------------------------------

def realisation_pairs(R: Runs) -> list[tuple]:
    pairs = []
    for L in ("xfine30", "fine30"):
        rem = "xo2" if L == "xfine30" else "f1"
        pairs += [(scan_key(L, a), k_u(rem, gid(0.134, L, a))) for a in (-1.0, 1.0)]
        pairs += [(scan_key(L, a), scan_key(L, a, "B2")) for a in (-1.0, -0.25, 0.25, 1.0)]
    return pairs


def sigma_real80(R: Runs) -> dict:
    d = []
    for a, b in realisation_pairs(R):
        if R.cls(a) in VALID_U and R.cls(b) in VALID_U and (R.rec(a) or {}).get("mesh_msh_sha256") != (R.rec(b) or {}).get("mesh_msh_sha256"):
            d.append(R.m(a) - R.m(b))
    nu = len(d)
    if nu < 2:
        return {"nu": nu, "sigma": None}
    s = math.sqrt(sum(x * x for x in d) / (2 * nu))
    return {"nu": nu, "sigma_point": s, "sigma": s * math.sqrt(nu / chi2.ppf(TH["chi2_q"], nu)), "differences": d}


def g2u(R: Runs, L: str, exp: dict, sreal: dict) -> dict:
    def fn():
        req = [g2_key(L, h) for h in HEIGHTS] + [g2_key(L, h, a) for h in (0.224, 0.134) for a in (-1.0, 1.0)]
        need(R, req)
        m = {h: R.m(g2_key(L, h)) for h in HEIGHTS}
        d = {h: (R.m(g2_key(L, h, 1.0)) - R.m(g2_key(L, h, -1.0))) / 2 for h in (0.224, 0.134)}
        opt = [g2_key(L, 0.09, a) for a in (-1.0, 1.0)]
        unverified = not all(R.cls(k) in VALID_U for k in opt)
        d[0.09] = d[0.134] if unverified else (R.m(opt[1]) - R.m(opt[0])) / 2
        shift = lambda h: B.INCIDENCE_SHIFT_DEG * B.d_interp(d, h)
        e0, e1 = B.mean_abs_err(m, exp), B.mean_abs_err(m, exp, shift)
        if sreal["sigma"] is None:
            raise Out(FI, {("sigma_peak", L): f"fewer than 2 valid realisation pairs ({sreal['nu']})"})
        sp = max(sreal["sigma"], max(R.se(g2_key(L, h)) for h in (0.179, 0.134, 0.09)))
        n = 2 * math.sqrt(2) * sp
        tri = lambda x: "pass" if x >= n else "fail" if x < -n else "noise"
        peak = m[0.134] - (1 - TH["peak_tol"]) * max(m[0.179], m[0.09])
        rise = {f"{h}->{nx}": m[nx] - (1 - TH["peak_tol"]) * m[h] for h, nx in zip(HEIGHTS[:5], HEIGHTS[1:6])}
        tests = {"peak": tri(peak), **{k: tri(v) for k, v in rise.items()}}
        mean_ok = e0 < TH["G2_mean"] and e1 < TH["G2_mean"]
        robust = all(B.mean_abs_err(m, exp, sh, o) < TH["G2_mean"] for o in (-TH["robust"], TH["robust"]) for sh in (None, shift))
        detail = {"m": m, "d_R": d, "SHIFT_UNVERIFIED": unverified, "mean_abs_e_nominal": e0, "mean_abs_e_plus_0p15deg": e1, "e_h": {h: m[h] / exp[h] - 1 for h in HEIGHTS},
                  "G2d_E": B.rel_l1(B.increments(m), B.increments(exp)), "ROBUST": robust, "sigma_peak": sp, "noise_band": n, "peak_margin": peak,
                  "rise_margins": rise, "tests": tests, "peak_h": max(m, key=m.get), "margins_in_band_units": {"peak": peak / n, **{k: v / n for k, v in rise.items()}},
                  "PEAK_NONDIAGNOSTIC": (exp[0.134] - (1 - TH["peak_tol"]) * max(exp[0.179], exp[0.09])) < n}
        fail = not mean_ok or "fail" in tests.values()
        if fail:
            return False, detail, FV
        if "noise" in tests.values():
            return False, detail, NOISE
        return True, detail, FV
    return gate(fn)


def data_verdict(R: Runs, exp: dict) -> dict:
    sreal = sigma_real80(R)
    out = {"sigma_real80": sreal, "G2u": {}, "GTd": {}, "level": {}}
    for L in ("fine30", "xfine30"):
        out["G2u"][L] = g2u(R, L, exp, sreal)
        out["GTd"][L] = {c: gt_at(R, *GTD_COND[c]) for c in GTD[L]}
        out["level"][L] = worst([out["G2u"][L]["outcome"], *(g["outcome"] for g in out["GTd"][L].values())], LEVEL_ORDER)
    out["outcome"] = worst(list(out["level"].values()), DATA_ORDER)
    return out


def g2_action(R: Runs, data: dict) -> dict:
    """Registration section 7."""
    lv = {}
    for L in ("fine30", "xfine30"):
        g, gtd = data["G2u"][L], data["GTd"][L]
        valid = (g["outcome"] in (PASS, FV, NOISE) and "m" in g["detail"] and not g["detail"]["SHIFT_UNVERIFIED"]
                 and all(x["outcome"] == PASS for x in gtd.values()))
        lv[L] = {"valid": valid}
        if valid:
            d = g["detail"]
            lv[L].update(mean_ok=d["mean_abs_e_nominal"] < TH["G2_mean"] and d["mean_abs_e_plus_0p15deg"] < TH["G2_mean"], g2d_ok=d["G2d_E"] <= TH["G2d"],
                         robust=d["ROBUST"], no_fail="fail" not in d["tests"].values())
    step = None
    if all(lv[L]["valid"] for L in lv):
        mf, mx = data["G2u"]["fine30"]["detail"]["m"], data["G2u"]["xfine30"]["detail"]["m"]
        step = max(abs(mx[h] / mf[h] - 1) for h in HEIGHTS)
    stands = any(v["valid"] and not (v["mean_ok"] and v["g2d_ok"] and v["no_fail"]) for v in lv.values())
    nxt = (step is not None and step <= TH["level_step"] and all(v["mean_ok"] and v["g2d_ok"] and v["robust"] and v["no_fail"] for v in lv.values()))
    label = "G2_ACTION_STANDS" if stands else "G2_INDEPENDENT_DATA_NEXT" if nxt else "UNDECIDED"
    return {"label": label, "per_level": lv, "level_step": step}


# ---- DIFF (registration section 6.3) ------------------------------------------------------------

def sigma_eff(R: Runs, L: str) -> dict:
    keys = [scan_key(L, a) for a in A7]
    need(R, keys)
    y = np.array([R.m(k) for k in keys])
    res = lambda deg: math.sqrt(float(((y - np.polyval(np.polyfit(A7, y, deg), A7)) ** 2).sum()) / (len(A7) - deg - 1))
    se = max(R.se(k) for k in keys)
    return {"fit_cubic": res(3), "fit_quadratic": res(2), "se_max": se, "eff": max(res(3), se), "m": dict(zip(A7, y.tolist()))}


def d_scan(R: Runs, L: str, s: float, variant: str = "") -> float:
    return (R.m(scan_key(L, s, variant)) - R.m(scan_key(L, -s, variant))) / (2 * s)


def g6u(R: Runs, L: str = "xfine30"):
    def fn():
        se = sigma_eff(R, L)
        s = se["eff"]
        c = compare_p(d_scan(R, L, 0.25), d_scan(R, L, 1.0), s / (math.sqrt(2) * 0.25), s / math.sqrt(2))
        diff = abs(R.m(scan_key(L, 0.25)) - R.m(scan_key(L, -0.25)))
        res = diff >= TH["resolve"] * math.sqrt(2) * s
        return c["pass"] and res, {"sigma_eff": se, "consistency": c, "dCl_pm0.25": diff, "resolved": res}, FV
    return gate(fn)


def g8u(R: Runs, L: str = "xfine30"):
    def fn():
        b2 = [scan_key(L, a, "B2") for a in (-1.0, -0.25, 0.25, 1.0)]
        need(R, [scan_key(L, a) for a in A7] + b2)
        s = sigma_eff(R, L)["eff"]
        sb = max(s, max(R.se(k) for k in b2))
        out = {str(x): compare_p(d_scan(R, L, x), d_scan(R, L, x, "B2"), s / (math.sqrt(2) * x), sb / (math.sqrt(2) * x)) for x in (1.0, 0.25)}
        return all(c["pass"] for c in out.values()), out, FV
    return gate(fn)


def g3bu(R: Runs):
    def fn():
        keys = [scan_key(L, a) for L in ("fine30", "xfine30") for a in A7] + [scan_key(L, a, "B2") for L in ("fine30", "xfine30") for a in (-1.0, 1.0)]
        need(R, keys)
        sd = {L: max(sigma_eff(R, L)["eff"] / math.sqrt(2), abs(d_scan(R, L, 1.0) - d_scan(R, L, 1.0, "B2")) / math.sqrt(2)) for L in ("fine30", "xfine30")}
        c = compare_p(d_scan(R, "fine30", 1.0), d_scan(R, "xfine30", 1.0), sd["fine30"], sd["xfine30"])
        return c["pass"], {**c, "sd": sd}, FV
    return gate(fn)


def gsu(R: Runs):
    def fn():
        shapes = [shape_key(m, a) for m in ("camber", "flap") for a in (-0.25, 0.25)]
        need(R, [scan_key("xfine30", a) for a in A7] + shapes)
        s = max(sigma_eff(R, "xfine30")["eff"], max(R.se(k) for k in shapes))
        out = {}
        for mode in ("camber", "flap"):
            dcl = R.m(shape_key(mode, 0.25)) - R.m(shape_key(mode, -0.25))
            out[mode] = {"dCl": dcl, "d_per_mm": dcl / 0.5, "expected_sign_ok": dcl > 0, "resolved": abs(dcl) >= TH["resolve"] * math.sqrt(2) * s}
        return all(v["resolved"] for v in out.values()), {"sigma_shape": s, **out}, FV
    return gate(fn)


def gt134(R: Runs):
    def fn():
        geos = [gid(0.134, "xfine30"), gid(0.134, "xfine30", 1.0, morph=True), gid(0.134, "xfine30", -1.0, morph=True)]
        keys = [k for g in geos for k in (k_u("xp1", g), k_u("xp1", g, "Udt2"))]
        need(R, keys)
        per = {g: gt_rule(R.stats(k_u("xp1", g)), R.stats(k_u("xp1", g, "Udt2"))) for g in geos}
        d = {}
        for kind in ("U", "Udt2"):
            p, mn = R.stats(k_u("xp1", geos[1], kind)), R.stats(k_u("xp1", geos[2], kind))
            d[kind] = {"d": (p["m"] - mn["m"]) / 2, "sd": math.hypot(p["se"], mn["se"]) / 2}
        allowed = max(TH["gt_deriv"] * max(abs(d["U"]["d"]), abs(d["Udt2"]["d"])), 3 * math.hypot(d["U"]["sd"], d["Udt2"]["sd"]))
        deriv_ok = abs(d["U"]["d"] - d["Udt2"]["d"]) <= allowed
        return all(g["pass"] for g in per.values()) and deriv_ok, {"per_geometry": per, "derivative": {**d, "allowed": allowed, "pass": deriv_ok}}, FT
    return gate(fn)


def diff_verdict(R: Runs) -> dict:
    out = {"GT134": gt134(R), "G6u": g6u(R), "G8u": g8u(R), "G3bu": g3bu(R), "GSu": gsu(R)}
    out["outcome"] = worst([g["outcome"] for g in out.values()], DIFF_ORDER)
    return out


def cost_rule(R: Runs) -> dict:
    """Evaluation cost of the 15 xfine30 h/c 0.134 U runs of XP1 and XP2 (registration section 6.3)."""
    reg = K.registered()
    costs, missing = {}, []
    for k in ("xp1", "xp2"):
        for c, kinds in reg[k]:
            key = k_u(k, K._case_id(*c))
            r = R.rec(key)
            stage = [s for s in (r or {}).get("stages", []) if s["stage"] == "pimpleFoam"]
            if r and stage and r.get("pre_solver_wall_s") is not None:
                costs[f"{k}:{key[1]}"] = (r["pre_solver_wall_s"] + (r.get("s0_wall_s") or 0.0) + stage[0]["wall_s"]) / 60
            else:
                missing.append(f"{k}:{key[1]}")
    over = any(v > TH["cost_max_min"] for v in costs.values())
    if over or not missing:
        vals = sorted(costs.values())
        ok = (not over) and bool(vals) and statistics.median(vals) <= TH["cost_median_min"]
        label = "AFFORDABLE" if ok else "NOT_AFFORDABLE"
    else:
        label = UND
    return {"label": label, "median_min": statistics.median(costs.values()) if costs else None, "max_min": max(costs.values()) if costs else None,
            "missing": missing, "costs_min": costs}


def verdict(data: str, diff: str, cost: str) -> str:
    if MEC in (data, diff):
        return V_DEF
    if (data == UND and diff in (PASS, UND)) or (diff == UND and data in (PASS, UND)):
        return V_INC
    if data == PASS and diff == PASS:
        return V_INC if cost == UND else V_Q if cost == "AFFORDABLE" else V_QU
    return V_NO


# ---- labels ---------------------------------------------------------------------------------------

def _try(fn):
    try:
        return fn()
    except Out as o:
        return f"not computable: {o}"
    except (KeyError, TypeError, ValueError, ZeroDivisionError, np.linalg.LinAlgError) as exc:
        return f"not computable: {type(exc).__name__}: {exc}"


def labels(R: Runs, data: dict, diff: dict) -> dict:
    out = {"Q1": q1_labels(R), "G2_ACTION": g2_action(R, data)}
    gh = {}
    for name, (k, g) in (("x134 0", Q1_TARGETS["x134 0"]), ("x09 0", Q1_TARGETS["x09 0"])):
        def half(k=k, g=g):
            """dt/2 against dt over the common interval (T_TR_S, END_TIME_S['Udt05']]; the observed order from the three steps on that interval."""
            a, b, c = k_u(k, g, "Udt05"), k_u(k, g), k_u(k, g, "Udt2")
            need(R, [a, b, c])
            sub = {}
            for kind, key in (("Udt2", c), ("U", b)):
                tt, cl = read_coefficients(sorted(R.dirs[key].glob("coefficient*.dat.gz")))
                sub[kind] = urans_stats(tt, cl, S.DT[kind], S.T_TR_S, S.END_TIME_S["Udt05"])
            sub["Udt05"] = R.stats(a)
            res = {x: {y: s.get(y) for y in ("class", "m", "se", "r", "f")} for x, s in sub.items()}
            if all(s.get("class") in VALID_U for s in sub.values()):
                res["GT(U, Udt05) on the common interval"] = gt_rule(sub["U"], sub["Udt05"])
                m2, m1, m05 = sub["Udt2"]["m"], sub["U"]["m"], sub["Udt05"]["m"]
                if m1 != m05 and (m2 - m1) / (m1 - m05) > 0:
                    res["observed_order"] = math.log((m2 - m1) / (m1 - m05)) / math.log(2)
            return res
        gh[name] = _try(half)
    out["GT_HALF"] = gh
    pairs = {}
    for (k, j) in sorted(R.recs):
        if j.endswith("__U") and R.cls((k, j)) in VALID_U:
            g = j[:-3]
            row = {}
            for x in ("S0", "S1"):
                if R.cls((k, f"{g}__{x}")) in ("CONVERGED", "NOT_CONVERGED"):
                    row[f"m_U_minus_Cl_{x}"] = R.m((k, j)) - R.m((k, f"{g}__{x}"))
                    row[x] = R.cls((k, f"{g}__{x}"))
            if row:
                pairs[f"{k}:{g}"] = row
    out["FORMULATION_OFFSET"] = pairs
    out["U_class_map"] = {f"{k}:{j}": R.cls((k, j)) for (k, j) in sorted(R.recs) if j.split("__")[-1] in URANS}
    out["LOW_FREQ_PERIODIC"] = sorted(f"{k}:{j}" for (k, j) in R.recs if j.split("__")[-1] in URANS and R.stats((k, j)).get("low_freq"))
    out["S0_classes"] = {f"{k}:{j}": R.cls((k, j)) for (k, j) in sorted(R.recs) if j.endswith("__S0")}

    def q3_extras():
        e = {}
        for L in ("xfine30", "fine30"):
            s = _try(lambda L=L: sigma_eff(R, L))
            e[L] = {"sigma": s}
            if isinstance(s, dict):
                classes = [R.cls(scan_key(L, a)) for a in A7]
                d1 = d_scan(R, L, 1.0)
                e[L].update(SCAN_KINK=len(set(classes)) > 1, classes=dict(zip(A7, classes)), d1=d1, d025=d_scan(R, L, 0.25),
                            smallest_resolved_deg=2 * math.sqrt(2) * s["eff"] / abs(d1) if d1 else None,
                            MDD_PCT=100 * 2 * math.sqrt(2) * s["eff"] / s["m"][0.0], G6u_rule=g6u(R, L)["outcome"], G8u_rule=g8u(R, L)["outcome"])
                rem = "xo2" if L == "xfine30" else "f1"
                e[L]["morph_vs_remesh_d1"] = _try(lambda L=L, rem=rem: C.compare(d1, (R.m(k_u(rem, gid(0.134, L, 1.0))) - R.m(k_u(rem, gid(0.134, L, -1.0)))) / 2,
                                                                                  s["eff"] / math.sqrt(2), math.hypot(R.se(k_u(rem, gid(0.134, L, 1.0))), R.se(k_u(rem, gid(0.134, L, -1.0)))) / 2,
                                                                                  power=False))
        b = (R.rec(("xp1", f"{gid(0.134, 'xfine30')}__S0")) or {}).get("mesh_msh_sha256")
        b2 = ((R.rec(("xp2", f"{gid(0.134, 'xfine30', 0.25, morph=True, mode='camber')}__S0")) or {}).get("morph") or {}).get("base_mesh_msh_sha256")
        e["B2_NOT_B"] = None if not (b and b2) else b != b2
        return e
    out["Q3_extras"] = _try(q3_extras)
    out["SURVIVES_2SIGMA"] = _try(lambda: survives_2sigma(R))
    out["steady_scans_0179"] = {L: _try(lambda L=L: steady_scan(R, L)) for L in ("xfine30", "fine30")}
    out["cost"] = _try(lambda: cost_labels(R, diff))
    return out


def survives_2sigma(R: Runs) -> dict:
    """Every DIFF gate re-evaluated with every SE doubled (the cubic-fit sigma unchanged)."""
    class R2(Runs):
        def stats(self, key):
            s = super().stats(key)
            return {**s, "se": 2 * s["se"]} if "se" in s else s
    R2_ = R2(R.recs, R.dirs)
    R2_._c = R._c
    return {k: v["outcome"] for k, v in diff_verdict(R2_).items() if k != "outcome"}


def steady_scan(R: Runs, L: str) -> dict:
    k = "xo2" if L == "xfine30" else "f1"
    keys = [(k, f"{gid(0.179, L) if a == 0 else gid(0.179, L, a, morph=True)}__S0") for a in A7]
    classes = {a: R.cls(x) for a, x in zip(A7, keys)}
    if any(c not in ("CONVERGED", "NOT_CONVERGED") for c in classes.values()):
        return {"classes": classes, "G6m_type": "not computable"}
    y = np.array([R.m(x) for x in keys])
    fit = math.sqrt(float(((y - np.polyval(np.polyfit(A7, y, 3), A7)) ** 2).sum()) / 3)
    s = max(fit, max(R.stats(x)["tail_std"] for x in keys))
    dd = lambda x: (y[A7.index(x)] - y[A7.index(-x)]) / (2 * x)
    c = compare_p(dd(0.25), dd(1.0), s / (math.sqrt(2) * 0.25), s / math.sqrt(2))
    res = abs(y[A7.index(0.25)] - y[A7.index(-0.25)]) >= TH["resolve"] * math.sqrt(2) * s
    return {"classes": classes, "all_converged": all(v == "CONVERGED" for v in classes.values()), "sigma_eff": s, "consistency": c, "resolved": bool(res),
            "G6m_type_pass": bool(c["pass"] and res)}


def cost_labels(R: Runs, diff: dict) -> dict:
    out = {"per_run": {}}
    for (k, j), r in sorted(R.recs.items()):
        if r and j.split("__")[-1] in (*URANS, "S1", "S0"):
            st = [s for s in r.get("stages", []) if s["stage"] in ("pimpleFoam", "simpleFoam")]
            if st:
                steps = (r.get("solver") or {}).get("iterations") or 0
                cells = r.get("mesh_cells_3d") or 0
                out["per_run"][f"{k}:{j}"] = {"wall_min": st[-1]["wall_s"] / 60, "s_per_step": st[-1]["wall_s"] / steps if steps else None,
                                              "s_per_step_per_cell": st[-1]["wall_s"] / steps / cells if steps and cells else None,
                                              "courant_max": (r.get("courant") or {}).get("max")}
    try:
        b = scan_key("xfine30", 0.0)
        rec = R.rec(b)
        u_wall = [s for s in rec["stages"] if s["stage"] == "pimpleFoam"][0]["wall_s"]
        per_tc = u_wall / (S.END_TIME_S["U"] / (B.CHORD / U_INF))
        if diff["GT134"]["outcome"] == PASS:
            r2 = R.rec(k_u("xp1", gid(0.134, "xfine30"), "Udt2"))
            per_tc = [s for s in r2["stages"] if s["stage"] == "pimpleFoam"][0]["wall_s"] / (S.END_TIME_S["Udt2"] / (B.CHORD / U_INF))
        se = sigma_eff(R, "xfine30")
        target = abs(R.m(scan_key("xfine30", 0.25)) - R.m(scan_key("xfine30", -0.25))) / (TH["resolve"] * math.sqrt(2))
        if se["fit_cubic"] > target:
            out["COST_MIN"] = "NOT_ACHIEVABLE"
        else:
            batch = max(R.stats(scan_key("xfine30", a)).get("SE10", 0.0) * TH["hann_var"] for a in A7)
            bias = max(R.stats(scan_key("xfine30", a)).get("bias_bound", 0.0) for a in A7)
            tw = 10.0
            t_req = max(1.0, tw * max((batch / target) ** 2 if target else float("inf"), (bias / target) if target else float("inf")))
            pre = (rec["pre_solver_wall_s"] or 0) / 60
            s0 = (rec.get("s0_wall_s") or 0) / 60
            run = (6.0 + t_req) * per_tc / 60
            out["COST_MIN"] = {"T_req_Tc": t_req, "per_Tc_min": per_tc / 60, "with_S0_min": pre + s0 + run, "warm_start_min": pre + run,
                               "R5_budget_min": TH["r5_min"]}
    except (Out, KeyError, TypeError, IndexError, ValueError, ZeroDivisionError) as exc:
        out["COST_MIN"] = f"not computable: {type(exc).__name__}: {exc}"
    return out


# ---- main -------------------------------------------------------------------------------------------

def completeness(R: Runs) -> dict:
    fam = lambda c: "valid" if c in (*VALID_U, "CONVERGED", "NOT_CONVERGED") else "lost" if c == "INFRA_LOSS" else "mechanical" if c == "MECHANICAL_FAIL" else "invalid"
    counts, lost = {}, []
    for key in sorted(R.recs):
        f = fam(R.cls(key))
        counts[f] = counts.get(f, 0) + 1
        if f == "lost":
            lost.append(f"{key[0]}:{key[1]}")
    return {"counts": counts, "lost": lost}


def expected_keys() -> list:
    reg = K.registered()
    return [(k, f"{K._case_id(*c)}__{x}") for k in KERNELS for c, kinds in reg[k] for x in ("S0", *kinds)]


def jkey(x):
    if isinstance(x, dict):
        return {str(k): jkey(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jkey(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for k in KERNELS:
        ap.add_argument(f"--{k}", type=Path, nargs="+", required=True, help=f"kernel {k} output dir(s) (the t20d/ directory): first run, then an optional resubmission")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--completeness", action="store_true", help="print only the lost run ids and the class-family counts")
    a = ap.parse_args(argv)
    R, prov = load({k: getattr(a, k) for k in KERNELS})
    for key in expected_keys():
        R.recs.setdefault(key, None)
    if a.completeness:
        print(json.dumps(completeness(R), indent=1))
        return
    if a.out is None:
        raise SystemExit("--out is required")
    if (a.out / "verdict.json").exists():
        raise SystemExit("verdict.json exists: the registered analysis is written once")
    exp = {float(h): p["Cl"] for h, p in json.loads(B.EXP.read_text())["points"].items()}
    data, diff = data_verdict(R, exp), diff_verdict(R)
    cost = cost_rule(R)
    v = verdict(data["outcome"], diff["outcome"], cost["label"])
    lab = labels(R, data, diff)
    cpu = {}
    for k in KERNELS:
        for d in getattr(a, k):
            res = Path(d) / "result.json"
            cpu[f"{k}:{d}"] = (B._read(res) or {}).get("cpu_model") if res.is_file() else None
    classes = {}
    for key in R.recs:
        classes[R.cls(key)] = classes.get(R.cls(key), 0) + 1
    out = {"verdict": v, "DATA": data, "DIFF": diff, "cost": cost, "labels": lab, "scope": SCOPE, "predicted": PREDICTED, "thresholds": TH,
           "thresholds_set_after_exploratory_visible": True, "thresholds_set_after_t20b_visible": True, "thresholds_set_after_t20c_visible": True,
           "run_classes": classes, "cpu_models": cpu, "provenance": prov, "runs_used": {k: [str(p) for p in getattr(a, k)] for k in KERNELS},
           "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "registration": str(REG.relative_to(ROOT)),
           "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (B.EXP, REG, Path(B.__file__), Path(C.__file__), Path(K.__file__), Path(S.__file__))},
           "qualification_flags": "unchanged (all false; shape_update_allowed=false)"}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "verdict.json").write_text(json.dumps(jkey(out), indent=1, sort_keys=True, default=str) + "\n")
    md = [f"# T2-0d registered verdict: **{v}**", "", f"Scope: {SCOPE}. Thresholds were set after T2-0a, T2-0b and T2-0c were visible (registration section 2).", "",
          f"DATA (Q2): **{data['outcome']}**; DIFF (Q3): **{diff['outcome']}**; cost: **{cost['label']}** (median {cost['median_min']}, max {cost['max_min']} min).",
          f"`G2_ACTION`: **{lab['G2_ACTION']['label']}**; `Q1_FORM_134`: **{lab['Q1']['Q1_FORM_134']}**; `Q1_FORM_09`: **{lab['Q1']['Q1_FORM_09']}**.", "",
          "| gate | outcome | detail |", "|---|---|---|"]
    rows = [(f"G2u({L})", data["G2u"][L]) for L in data["G2u"]] + [(f"GTd {c}", g) for L in data["GTd"] for c, g in data["GTd"][L].items()]
    rows += [(n, g) for n, g in diff.items() if n != "outcome"]
    md += [f"| {n} | {g['outcome']} | `{json.dumps(jkey(g['detail']), default=str)[:900]}` |" for n, g in rows]
    md += ["", "## Q1 per condition", "", "| condition | label | U | S0 | S1 | time step | m_U | r_U | St_c |", "|---|---|---|---|---|---|---|---|---|"]
    for n, q in lab["Q1"]["per_condition"].items():
        md.append(f"| {n} | {q['label']} | {q['U']} | {q['S0']} | {q['S1']} | {q['time_step']['outcome']} | {q.get('m_U')} | {q.get('r_U')} | {q.get('St_c')} |")
    md += ["", "## Labels (never change the verdict; only G2_ACTION feeds a route)", "", "```json", json.dumps(jkey(lab), indent=1, default=str), "```", ""]
    (a.out / "analysis.md").write_text("\n".join(md))
    print(v)


if __name__ == "__main__":
    main()
