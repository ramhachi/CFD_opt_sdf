#!/usr/bin/env python3
"""SCREEN-01 (#64) revision 1: end-to-end operating characteristics of the registered procedure on a visible-data surrogate (registration §5.10).
Solver-free numpy/scipy.  A planning statement about the procedure and its rules, not evidence about the physics.

Surrogate: per-mode polynomials in u (pitch cubic, camber quadratic, reflex quadratic, all through the origin) fitted to the visible flow_32 paired
differences (M2: pitch +-3.1, +1.3, reflex +29.3; FID-01: pitch +-0.7, camber +-19.7, -11.3, reflex -29.3) and two interaction terms from the visible
combinations C1 (camber x reflex) and C4 (pitch x reflex); the pitch x camber interaction is unknown (0 centrally).  Each replicate draws a "truth":
every coefficient x (1 + 0.10 N(0,1)), plus random interaction/cubic terms of SD s_mis (central 1e-3 N, misfit-heavy 3e-3 N); drag is tied to
downforce through the same structure (a frontier, not an independent draw).  Placement noise per phase: sigma_d(S) = max(9.7e-5 (S/1e-3)^0.48, 2.09e-4) N
with S = max(|Delta|, 0.5 sum |per-mode contributions|) (cancelling combinations carry constituent noise); drag sigma = max(3e-4 (S_D/1e-3)^0.4, 4e-4) N.
Admissibility of a new geometry = Bernoulli(p_adm) (P0 measured fraction), independent per point.

Procedures: `rev0` = the revision-0 registration (box [-1,1]^3, hull-restricted pool proposals, lower-bound rule, 10 axial incl. twist/sweep);
`rev1` = this registration (extended camber box, gated refinement `propose()`, point rule, fixed subset).  Variants in `main`.

    python scripts/screen01/screen01_oc.py --reps 2000 --out docs/evidence/screen01_2026_10_30/oc.json   # the recorded run (about 4 min)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/screen01")]
import screen01_pool as P  # noqa: E402

J, G_MIN = 0.26577921974115387, 0.027030580470324268
XSTAR = G_MIN * J
FLOOR_DF, FLOOR_DRAG_NOISE, SIG48 = 2.09e-4, 4e-4, 5e-4
RATIO48 = 0.98
P_SEL, P_SEAL, P48 = 2, 4, 2
T_SEAL = float(stats.t.ppf(0.95, P_SEAL - 1))
BOX_REV0 = {"pitch": (-1.0, 1.0), "camber": (-1.0, 1.0), "reflex": (-1.0, 1.0)}
BOX_REV1 = dict(P.BOX)

# visible flow_32 paired differences (N): (u, downforce, drag); u = amplitude / A*
VIS = {"pitch": [(1.0, 4.073e-2, 2.966e-2), (-1.0, -4.201e-2, -2.802e-2), (1.3 / 3.1, 1.891e-2, 1.279e-2), (0.7 / 3.1, 1.061e-2, 6.893e-3), (-0.7 / 3.1, -8.953e-3, -6.383e-3)],
       "camber": [(1.0, -1.018e-2, -1.558e-5), (-1.0, 1.300e-2, 1.998e-3), (-11.3 / 19.7, 7.184e-3, 1.208e-3)],
       "reflex": [(-1.0, 1.565e-2, 1.247e-2), (1.0, -1.335e-2, -9.74e-3)]}
COMBOS = {"C1": ((0.0, -11.3 / 19.7, -11.3 / 29.3), 1.326e-2, 5.831e-3), "C4": ((-1.3 / 3.1, 0.0, 1.0), -3.204e-2, -2.221e-2)}
DEG = {"pitch": 3, "camber": 2, "reflex": 2}


def fit_surrogate():
    """Per-mode polynomial coefficients [a1, a2, (a3)] for downforce and drag, and the two interaction coefficients."""
    co = {}
    for k, r in (("y", 1), ("z", 2)):
        c = {}
        for m, pts in VIS.items():
            u = np.array([p[0] for p in pts]); v = np.array([p[r] for p in pts])
            X = np.column_stack([u ** d for d in range(1, DEG[m] + 1)])
            c[m], *_ = np.linalg.lstsq(X, v, rcond=None)
        add = lambda uu: sum(float(np.polyval(np.r_[c[m][::-1], 0.0], uu[i])) for i, m in enumerate(P.SUBSET))  # noqa: E731
        c1 = COMBOS["C1"]; c4 = COMBOS["C4"]
        c["c_cr"] = (c1[r] - add(c1[0])) / (c1[0][1] * c1[0][2])
        c["c_pr"] = (c4[r] - add(c4[0])) / (c4[0][0] * c4[0][2])
        c["c_pc"] = 0.0
        co[k] = c
    return co


SURR = fit_surrogate()


class Truth:
    """A perturbed surrogate: coefficients x (1 + rel N(0,1)) + random cubic (camber, reflex) and interaction terms; scale multiplies the downforce response."""
    def __init__(self, rng, s_mis, rel=0.10, scale=1.0, null=False):
        self.c = {}
        for k in ("y", "z"):
            c = {m: np.array(SURR[k][m]) * (1 + rel * rng.standard_normal(len(SURR[k][m]))) for m in P.SUBSET}
            for m in ("camber", "reflex"):
                c[m] = np.r_[c[m], s_mis * (0.5 if k == "z" else 1.0) * rng.standard_normal()]   # extra cubic
            c["c_cr"] = SURR[k]["c_cr"] * (1 + rel * rng.standard_normal()) + s_mis * (0.5 if k == "z" else 1.0) * rng.standard_normal()
            c["c_pr"] = SURR[k]["c_pr"] * (1 + rel * rng.standard_normal()) + s_mis * (0.5 if k == "z" else 1.0) * rng.standard_normal()
            c["c_pc"] = s_mis * (0.5 if k == "z" else 1.0) * rng.standard_normal()
            self.c[k] = c
        self.scale_y = 0.0 if null else scale

    def parts(self, U, k):
        U = np.atleast_2d(U)
        c = self.c[k]
        per = np.stack([np.polyval(np.r_[c[m][::-1], 0.0], U[:, i]) for i, m in enumerate(P.SUBSET)], 1)
        inter = c["c_pc"] * U[:, 0] * U[:, 1] + c["c_pr"] * U[:, 0] * U[:, 2] + c["c_cr"] * U[:, 1] * U[:, 2]
        tot = per.sum(1) + inter
        return (tot * self.scale_y if k == "y" else tot), np.abs(per).sum(1) + np.abs(inter)

    def y(self, U):
        return self.parts(U, "y")

    def z(self, U):
        return self.parts(U, "z")


def sig_df(delta, absum, noise=1.0):
    S = np.maximum(np.abs(delta), 0.5 * absum)
    return noise * np.maximum(9.7e-5 * (S / 1e-3) ** 0.48, FLOOR_DF)


def sig_dr(delta, absum, noise=1.0):
    S = np.maximum(np.abs(delta), 0.5 * absum)
    return noise * np.maximum(3e-4 * (S / 1e-3) ** 0.4, FLOOR_DRAG_NOISE)


def measure(rng, truth, U, P_, noise):
    """Paired differences at P_ phases: mean and sample SD for downforce and drag (shape (n,))."""
    y, ay = truth.y(U); z, az = truth.z(U)
    ey = y[:, None] + sig_df(y, ay, noise)[:, None] * rng.standard_normal((len(y), P_))
    ez = z[:, None] + sig_dr(z, az, noise)[:, None] * rng.standard_normal((len(z), P_))
    sd = (lambda e: e.std(1, ddof=1) if P_ > 1 else np.full(len(e), np.nan))
    return ey.mean(1), sd(ey), ez.mean(1), sd(ez)


def se_eff(sd, P_, floor):
    return np.maximum(np.nan_to_num(sd, nan=0.0), floor) / math.sqrt(P_)


def hull_inside(points, Q):
    from scipy.spatial import Delaunay
    try:
        return Delaunay(points).find_simplex(Q) >= 0
    except Exception:  # noqa: BLE001
        return np.zeros(len(Q), bool)


def replicate(rng, rev, truth, p_adm, m_d, targets, noise, n_prop=4, box=None):
    P.BOX = dict(box)
    grid = P.grid_u(41)
    # pool (frozen before any force): Sobol in the box, Bernoulli admissibility; design = 6 axial + 9 D-optimal
    n_pool = 64
    Upool = P.sobol_u(n_pool, int(rng.integers(1 << 30)))
    adm = rng.random(n_pool) < p_adm
    while adm.sum() < 12 and n_pool < 256:
        more = P.sobol_u(64, int(rng.integers(1 << 30)))
        Upool = np.vstack([Upool, more]); adm = np.r_[adm, rng.random(64) < p_adm]; n_pool += 64
    Uadm = Upool[adm]
    idx, _ = P.d_optimal9(Uadm, 9)
    Udes = Uadm[idx]
    axial = P.AXIAL_U
    U1 = np.vstack([axial, Udes])
    if rev == "rev0":   # 4 null-ish twist/sweep axial states (visible: +-1.6e-3, ~1e-4 N) enter the candidate set
        extra_y = np.array([1.6e-3, -1.2e-3, 1e-4, -1e-4]); extra_z = np.array([6e-4, -4e-4, 1e-4, -1e-4])
    ym, ysd, zm, zsd = measure(rng, truth, U1, P_SEL, noise)
    by, _, rank_y, cond = P.fit9(U1, ym)
    bz, *_ = P.fit9(U1, zm)
    ystar = P.constrained_argmax(by, bz, m_d, grid=grid)[1]
    pool_limited_pred = ystar is not None and ystar >= XSTAR
    # proposals
    if rev == "rev0":
        rest = ~adm.copy(); rest[:] = True
        cand = np.array([i for i in range(len(Upool)) if adm[i] and i not in set(np.where(adm)[0][idx])])
        Uc = Upool[cand] if len(cand) else np.zeros((0, 3))
        inside = hull_inside(np.vstack([np.zeros((1, 3)), U1]), Uc) if len(Uc) else np.zeros(0, bool)
        yp, zp = P.predict9(by, Uc) if len(Uc) else np.zeros(0), P.predict9(bz, Uc) if len(Uc) else np.zeros(0)
        ok = inside & (zp <= -m_d)
        order = np.argsort(-yp[ok])[:3]
        Uprop = Uc[ok][order]
        n_gated = 0
    else:
        res = P.propose(by, bz, lambda u: rng.random() < p_adm, m_d=m_d, targets=targets, n_prop=n_prop, n_grid=41, grid=grid, seed=int(rng.integers(1 << 30)))
        Uprop = np.array([p["u"] for p in res["proposals"]]) if res["proposals"] else np.zeros((0, 3))
        n_gated = res["n_gated"]
    if len(Uprop):
        ym2, ysd2, zm2, zsd2 = measure(rng, truth, Uprop, P_SEL, noise)
        Uall = np.vstack([U1, Uprop]); YM = np.r_[ym, ym2]; ZM = np.r_[zm, zm2]; YSD = np.r_[ysd, ysd2]
    else:
        Uall, YM, ZM, YSD = U1, ym, zm, ysd
    if rev == "rev0":
        YM = np.r_[YM, extra_y + 2.5e-4 * rng.standard_normal(4)]; ZM = np.r_[ZM, extra_z + 5e-4 * rng.standard_normal(4)]; YSD = np.r_[YSD, np.full(4, 2.5e-4)]
        Uall = np.vstack([Uall, np.zeros((4, 3))])
    ty, _ = truth.y(Uall); tz, _ = truth.z(Uall)
    # random control (rev1 only): 19 admissible Sobol points, measured at P_SEL
    rand_label = None
    if rev == "rev1":
        Ur = []
        while len(Ur) < 19:
            c = P.sobol_u(16, int(rng.integers(1 << 30)))
            Ur += [u for u in c if rng.random() < p_adm]
        Ur = np.array(Ur[:19])
        rym, rysd, rzm, _ = measure(rng, truth, Ur, P_SEL, noise)
        rf = rzm <= 0
        rand_label = "RANDOM_NO_FEASIBLE" if not rf.any() else ("RANDOM_FEASIBLE_GAIN_AT_SELECTION" if np.max(np.where(rf, rym, -np.inf)) >= XSTAR else "RANDOM_BELOW_MIN")
    feas = ZM <= 0
    out = {"n_gated": n_gated, "fit_cond": cond, "y_star_pred_over_J": None if ystar is None else ystar / J, "rand": rand_label, "best_true_feasible_gain_over_J": None}
    tf = (tz <= 0)
    out["best_true_feasible_gain_over_J"] = float(np.max(np.where(tf, ty, -np.inf)) / J) if tf.any() else None
    if not feas.any():
        out.update(outcome="NO_GAIN", cause="NO_FEASIBLE_CANDIDATE", pool_limited=bool(pool_limited_pred))
        return out
    score = np.where(feas, YM, -np.inf)
    f = int(np.argmax(score))
    se_sel = se_eff(YSD[f], P_SEL, FLOOR_DF)
    if YM[f] < XSTAR - 3 * se_sel:
        out.update(outcome="NO_GAIN", cause="GAIN_BELOW_MIN_AT_SELECTION", pool_limited=bool(pool_limited_pred), finalist_true_gain_over_J=float(ty[f] / J), finalist_true_drag_n=float(tz[f]))
        return out
    # sealed stage
    Uf = Uall[f:f + 1]
    ys, ysd_s, zs, zsd_s = measure(rng, truth, Uf, P_SEAL, noise)
    se = se_eff(ysd_s, P_SEAL, FLOOR_DF)[0]
    y48 = RATIO48 * ty[f] + SIG48 * rng.standard_normal(P48)
    se48 = max(y48.std(ddof=1), FLOOR_DF) / math.sqrt(P48)
    g_b = bool(ys[0] >= XSTAR and ys[0] > 3 * se)                  # rule B (registered rev. 1)
    g_a = bool(ys[0] - T_SEAL * se >= XSTAR)                        # rule A (rev. 0, reported)
    d_ok = bool(zs[0] <= 0)
    r3 = "CONFIRMED" if y48.mean() > 3 * se48 else ("SIGN_SPLIT" if y48.mean() <= 0 else "UNRESOLVED")
    if rev == "rev0":
        gain_rule = g_a
        r3_fail = y48.mean() < -3 * se48
    else:
        gain_rule = g_b
        r3_fail = r3 == "SIGN_SPLIT"
    if not gain_rule and ys[0] < XSTAR:
        oc, cause = "NO_GAIN", "GAIN_BELOW_MIN"
    elif not d_ok:
        oc, cause = "NO_GAIN", "DRAG_VIOLATION"
    elif r3_fail:
        oc, cause = "NO_GAIN", "GRID_SIGN_SPLIT"
    elif not gain_rule or r3 == "UNRESOLVED":
        oc, cause = "INCONCLUSIVE", "GAIN_UNRESOLVED" if not gain_rule else "R3_UNRESOLVED"
    else:
        oc, cause = "GAIN", None
    out.update(outcome=oc, cause=cause, pool_limited=bool(pool_limited_pred and oc != "GAIN"), finalist_true_gain_over_J=float(ty[f] / J), finalist_true_drag_n=float(tz[f]),
               sealed_minus_true_n=float(ys[0] - ty[f]), selection_minus_true_n=float(YM[f] - ty[f]), rule_a=g_a, rule_b=g_b, finalist_camber_u=float(Uall[f][1]),
               finalist_in_extension=bool(Uall[f][1] < -1.0))
    return out


def summarize(rows):
    n = len(rows)
    oc = {}
    for r in rows:
        k = r["outcome"] + ("" if r["cause"] is None else f":{r['cause']}")
        oc[k] = oc.get(k, 0) + 1
    g = [r for r in rows if r["outcome"] == "GAIN"]
    sel = [r for r in rows if "finalist_true_gain_over_J" in r]
    fin = [r for r in rows if "sealed_minus_true_n" in r]
    return {"P_GAIN": len(g) / n, "outcomes": {k: v / n for k, v in sorted(oc.items())}, "P_pool_limited_label": sum(bool(r.get("pool_limited")) for r in rows) / n,
            "P_rule_A_given_sealed": (sum(r["rule_a"] for r in fin) / len(fin)) if fin else None, "P_rule_B_given_sealed": (sum(r["rule_b"] for r in fin) / len(fin)) if fin else None,
            "mean_finalist_true_gain_over_J": float(np.mean([r["finalist_true_gain_over_J"] for r in sel])) if sel else None,
            "P_finalist_true_drag_positive": float(np.mean([r["finalist_true_drag_n"] > 0 for r in sel])) if sel else None,
            "mean_sealed_minus_true_n": float(np.mean([r["sealed_minus_true_n"] for r in fin])) if fin else None,
            "mean_selection_minus_true_n": float(np.mean([r["selection_minus_true_n"] for r in fin])) if fin else None,
            "mean_best_true_feasible_gain_over_J": float(np.mean([r["best_true_feasible_gain_over_J"] for r in rows if r["best_true_feasible_gain_over_J"] is not None])),
            "mean_y_star_pred_over_J": float(np.mean([r["y_star_pred_over_J"] for r in rows if r["y_star_pred_over_J"] is not None])) if any(r["y_star_pred_over_J"] is not None for r in rows) else None,
            "mean_n_gated": float(np.mean([r["n_gated"] for r in rows])), "P_finalist_in_extension": float(np.mean([r.get("finalist_in_extension", False) for r in g])) if g else None,
            "random_control": {k: sum(r["rand"] == k for r in rows) / n for k in sorted({r["rand"] for r in rows if r["rand"]})}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--p-adm", type=float, default=0.42)
    a = ap.parse_args()
    base = dict(rev="rev1", s_mis=1e-3, p_adm=a.p_adm, m_d=1.5e-3, targets=(1.0, 1.5, 2.0), noise=1.0, scale=1.0, null=False, box=BOX_REV1)   # registered m_D = 1.5e-3 N
    variants = {
        "rev0_registered": dict(base, rev="rev0", box=BOX_REV0),
        "rev0_misfit_heavy": dict(base, rev="rev0", box=BOX_REV0, s_mis=3e-3),
        "rev1_registered": dict(base),
        "rev1_box_unextended": dict(base, box=BOX_REV0),
        "rev1_m_d_1.0e-3": dict(base, m_d=1.0e-3),
        "rev1_single_target": dict(base, targets=(1.0,)),
        "rev1_noise_x1.5": dict(base, noise=1.5),
        "rev1_misfit_heavy": dict(base, s_mis=3e-3),
        "rev1_p_adm_0.25": dict(base, p_adm=0.25),
        "rev1_null_downforce": dict(base, null=True),
        "rev1_space_scaled_0.6": dict(base, scale=0.6),
        "rev1_space_scaled_0.8": dict(base, scale=0.8),
    }
    rng = np.random.default_rng(20261031)
    res = {}
    for name, v in variants.items():
        t0 = time.time()
        rows = []
        for _ in range(a.reps):
            truth = Truth(rng, v["s_mis"], scale=v["scale"], null=v["null"])
            rows.append(replicate(rng, v["rev"], truth, v["p_adm"], v["m_d"], v["targets"], v["noise"], box=v["box"]))
        res[name] = {"params": {k: (list(x) if isinstance(x, tuple) else x) for k, x in v.items()}, **summarize(rows), "wall_s": round(time.time() - t0, 1)}
        print(f"{name:26s} P_GAIN {res[name]['P_GAIN']:.3f} pool_limited {res[name]['P_pool_limited_label']:.3f} {res[name]['outcomes']}", flush=True)
    # the surrogate itself: fitted constrained optimum in both boxes
    byc = np.array(sum(([*SURR['y'][m]] + [0.0] * (3 - DEG[m]) for m in P.SUBSET), []))
    opt = {}
    for lab, box in (("box_rev0", BOX_REV0), ("box_rev1", BOX_REV1)):
        P.BOX = dict(box)
        T = Truth(np.random.default_rng(0), 0.0, rel=0.0)
        G = P.grid_u(81)
        y, _ = T.y(G); z, _ = T.z(G)
        for lab2, md in (("drag_le_0", 0.0), ("drag_le_-m_D", 1e-3)):
            ok = z <= -md
            j = int(np.argmax(np.where(ok, y, -np.inf)))
            opt[f"{lab}|{lab2}"] = {"u": G[j].tolist(), "gain_over_J": float(y[j] / J), "gain_over_g_min": float(y[j] / XSTAR), "feasible_fraction_ge_gmin": float(((y >= XSTAR) & ok).mean())}
    rec = {"kind": "screen01_operating_characteristics_rev1", "reps": a.reps, "seed": 20261031, "surrogate": {k: {m: np.asarray(c).tolist() for m, c in d.items()} for k, d in SURR.items()},
           "surrogate_check": {"C1_pred": None, "C4_pred": None}, "surrogate_optimum": opt, "x_star_n": XSTAR, "J_n": J, "t_seal": T_SEAL, "variants": res}
    T0 = Truth(np.random.default_rng(0), 0.0, rel=0.0)
    for k, (u, yv, zv) in COMBOS.items():
        rec["surrogate_check"][f"{k}_pred"] = {"downforce": float(T0.y(np.array(u))[0][0]), "drag": float(T0.z(np.array(u))[0][0]), "measured": [yv, zv]}
    a.out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
