#!/usr/bin/env python3
"""SCREEN-01 (#64, M3b-1) operating characteristics of the registered selection and decision rules on synthetic data (registration §6.9).
Solver-free numpy/scipy; a planning statement about the rules, not evidence about the physics.

Model (sources in the registration): K candidates with true paired flow_32 downforce differences Delta_i and drag differences d_i (N); WaterLily
placement noise per phase sigma(Delta) = 9.7e-5 (|Delta|/1e-3)^0.48 N (M2 fit; floor 2.09e-4 N in SE_eff), drag noise 7e-4 N per phase (FID tier-A
range 4.6e-4..9.4e-4); exploration P_SEL = 2 phases, sealed P_SEAL = 4 phases, flow_48 P48 = 2 phases with ratio 0.98 and noise 5e-4 N.
Selection: feasible = d_hat <= -sel_margin (registered: 0; the RS *targets* -M_D, so the finalist's true drag is placed at about -M_D);
finalist = argmax Delta_hat over the feasible set.  Decision (sealed, fresh phases): GAIN iff Delta_s - t_{0.95,P-1} SE_eff >= g_min J_b48 and
d_s <= 0 and R3 confirmed.  Rule B (reported only): point >= g_min J and > 3 SE_eff.  Both selection filters (0 and -M_D) are reported.

    python scripts/screen01/screen01_oc.py --reps 20000 --out docs/evidence/screen01_2026_10_30/oc.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

J_B48, G_MIN = 0.26577921974115387, 0.027030580470324268
D_MIN = G_MIN * J_B48                      # 7.184e-3 N
FLOOR_DF, SIG_DRAG, SIG48, RATIO48 = 2.09e-4, 7e-4, 5e-4, 0.98
P_SEL, P_SEAL, P48 = 2, 4, 2
M_D = 1.0e-3                               # response-surface drag target margin (N); the measured selection filter is d_hat <= -SEL_MARGIN
K = 22                                     # optimizer candidates (10 + 9 + 3)
T_SEAL, T48 = stats.t.ppf(0.95, P_SEAL - 1), stats.t.ppf(0.95, P48 - 1)


def sig(d):
    return 9.7e-5 * (np.abs(d) / 1e-3) ** 0.48


def phases(rng, true, s, P):
    """P phase values -> (mean, sample sd)."""
    x = true[..., None] + s[..., None] * rng.standard_normal(true.shape + (P,))
    return x.mean(-1), x.std(-1, ddof=1)


def run(rng, deltas, drags, reps, sel_margin=0.0):
    deltas, drags = np.broadcast_to(deltas, (reps, K)), np.broadcast_to(drags, (reps, K))
    dh, _ = phases(rng, deltas, sig(deltas), P_SEL)
    gh, _ = phases(rng, drags, np.full(drags.shape, SIG_DRAG), P_SEL)
    feas = gh <= -sel_margin
    score = np.where(feas, dh, -np.inf)
    f = score.argmax(1)
    has = feas.any(1)
    r = np.arange(reps)
    td, tg = deltas[r, f], drags[r, f]
    ds, sd = phases(rng, td, sig(td), P_SEAL)
    se = np.maximum(sd, FLOOR_DF) / math.sqrt(P_SEAL)
    gs, _ = phases(rng, tg, np.full(reps, SIG_DRAG), P_SEAL)
    d48, s48 = phases(rng, RATIO48 * td, np.full(reps, SIG48), P48)
    se48 = np.maximum(s48, FLOOR_DF) / math.sqrt(P48)
    r3 = d48 > 3 * se48
    gain_ok = ds - T_SEAL * se >= D_MIN
    gain_ok_b = (ds >= D_MIN) & (ds > 3 * se)
    drag_ok = gs <= 0
    gain = has & gain_ok & drag_ok & r3
    cause = np.where(~has, "NO_FEASIBLE", np.where(~gain_ok, "GAIN_BELOW_MIN", np.where(~drag_ok, "DRAG_VIOLATION", np.where(~r3, "R3_NOT_CONFIRMED", "GAIN"))))
    best_true = deltas.max(1)
    return {"P_GAIN": float(gain.mean()), "P_GAIN_rule_B_point": float((has & gain_ok_b & drag_ok & r3).mean()),
            "causes": {c: float((cause == c).mean()) for c in np.unique(cause)},
            "P_no_feasible": float((~has).mean()),
            "P_selected_is_true_best_delta": float((td >= best_true - 1e-12).mean()),
            "selection_phase_bias_n": float((dh[r, f] - td)[has].mean()) if has.any() else None,
            "sealed_bias_n": float((ds - td)[has].mean()) if has.any() else None,
            "mean_true_delta_of_finalist_n": float(td[has].mean()) if has.any() else None}


def scenarios(rng):
    out = {}
    def spread(best, lo=0.0):
        d = rng.uniform(lo, best, size=K)
        d[0] = best
        return d
    others_drag = lambda n: rng.uniform(-2e-3, 2e-3, size=n)  # noqa: E731
    for label, best in (("null_all_zero", 0.0), ("best_0.5_gmin", 0.5 * D_MIN), ("best_gmin", D_MIN), ("best_1.2_gmin", 1.2 * D_MIN), ("best_1.5_gmin", 1.5 * D_MIN), ("best_2_gmin", 2 * D_MIN)):
        for dlabel, dbest in (("drag_best_at_-m_D", -M_D), ("drag_best_at_0", 0.0), ("drag_best_at_-2m_D", -2 * M_D)):
            d = spread(best) if best > 0 else np.zeros(K)
            g = others_drag(K)
            g[0] = dbest
            out[f"{label}|{dlabel}"] = (d, g)
    # pure selection: everything at the threshold, every candidate feasible at the margin (worst case for the curse)
    out["all_at_gmin|all_drag_-m_D"] = (np.full(K, D_MIN), np.full(K, -M_D))
    out["all_at_0.9_gmin|all_drag_-m_D"] = (np.full(K, 0.9 * D_MIN), np.full(K, -M_D))
    out["all_at_0|all_drag_0"] = (np.zeros(K), np.zeros(K))
    return out


def emax(k):
    """E[max of k iid standard normals] by quadrature."""
    x = np.linspace(-9, 9, 200001)
    return float(np.trapezoid(x * k * stats.norm.pdf(x) * stats.norm.cdf(x) ** (k - 1), x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20000)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(20261030)
    sc = scenarios(rng)
    res = {f"sel_filter_{lab}": {name: run(rng, d, g, a.reps, m) for name, (d, g) in sc.items()} for lab, m in (("0", 0.0), ("-m_D", M_D))}
    for v, rr in res.items():
        print(v)
        for n, r in rr.items():
            print(f"  {n:45s} P_GAIN {r['P_GAIN']:.3f}  ruleB {r['P_GAIN_rule_B_point']:.3f}  best_selected {r['P_selected_is_true_best_delta']:.2f}  {r['causes']}")
    curse = {}
    for k in (10, 22, 30):
        e = emax(k)
        curse[str(k)] = {"E_max_k_std_normal": e, **{f"bias_fraction_of_J_sigma_disc_{s:g}N": e * s / J_B48 for s in (7e-4, 1.0e-3, 1.45e-3)}}
    rec = {"kind": "screen01_operating_characteristics", "reps": a.reps, "seed": 20261030, "K": K, "P_sel": P_SEL, "P_sealed": P_SEAL, "P48": P48, "m_D_n": M_D, "selection_filter_registered": "d_hat <= 0 (point, exploration phases); the -m_D variant is reported for comparison",
           "g_min": G_MIN, "J_b48_n": J_B48, "delta_min_n": D_MIN, "t_seal": float(T_SEAL),
           "noise_model": "sigma_d(Delta) = 9.7e-5 (|Delta|/1e-3)^0.48 N (M2 fit), SE_eff floor 2.09e-4 N; drag 7e-4 N per phase; flow_48 ratio 0.98, noise 5e-4 N",
           "scenario_note": "'best_x' = one candidate at x with the other 21 true gains uniform in [0, x] and drags uniform in [-2e-3, 2e-3] N; the best candidate's drag as labelled",
           "decision": "GAIN iff Delta_s - t_{0.95,3} SE_eff >= g_min J_b48 and d_s <= 0 and R3 confirmed (sealed, fresh phases); rule B = point >= g_min J and > 3 SE_eff (reported)",
           "optimizers_curse_upper_bound": curse, "scenarios": res}
    a.out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
