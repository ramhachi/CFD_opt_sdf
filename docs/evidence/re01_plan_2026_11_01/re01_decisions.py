#!/usr/bin/env python3
"""RE-01 decision memo calculations (planning only, nothing registered).

1. Operating characteristics of the primary estimand: through-origin slope b of the rung's flow_32 differences on the
   Re-80 differences over the 8 FID-01 tier-A designs, 90 % t-interval (7 dof), PERSISTS iff lower bound >= 0.3.
   Noise model (chaotic rung): each phase's design and parent time means carry SE_T (percent of the parent force);
   P = 4 phases; the parent run of a phase is shared by every design (common-mode term); optional lognormal
   design-to-design retention spread tau_r.
2. Cost model per rung from the measured Re-80 step counts (SCREEN-01 summaries: 13,600 steps / 120 CU on flow_32,
   26,800 on flow_48) with the numerical review's max-flux corrections (steps per CU flow_32: 70 / 68 / 68 / 73 at
   Re_L 250 / 450 / 800 / 2500; flow_48: 123 / 109 / 109 / 115), 5.2e7 cell-steps/s, +20 % overhead.
"""
import math

import numpy as np
from scipy import stats

J48 = 0.26577921974115387
TIER_A = {  # Re-80 flow_32 paired downforce differences, N (FID-01 analysis.json wl_flow32 delta_bar_n)
    "camber_m11.3": 7.1842e-3, "C1 camber_m11.3_reflex_m11.3": 1.3256e-2, "camber_m19.7": 1.3004e-2,
    "camber_p19.7": -1.0185e-2, "pitch_m0.7": -8.9529e-3, "C4 pitch_m1.3_reflex_p29.3_sweep_p11.3": -3.2044e-2,
    "pitch_p0.7": 1.0606e-2, "reflex_m29.3": 1.5645e-2,
}
X = np.array(list(TIER_A.values())) / J48 * 100.0  # percent of the parent force
RNG = np.random.default_rng(20261101)
N_REP = 40000


def oc(se_t, r, tau_r=0.0, P=4, band=0.3, x=X):
    n = len(x)
    s = se_t / math.sqrt(P)
    ri = r * np.exp(RNG.normal(0, tau_r, (N_REP, n))) if tau_r > 0 else np.full((N_REP, n), r)
    y = ri * x + RNG.normal(0, s, (N_REP, n)) - RNG.normal(0, s, (N_REP, 1))
    sxx = float(x @ x)
    b = (y @ x) / sxx
    res = y - b[:, None] * x
    se_b = np.sqrt((res ** 2).sum(1) / (n - 1) / sxx)
    t = stats.t.ppf(0.95, n - 1)
    lb, ub = b - t * se_b, b + t * se_b
    return {"P_persists": float((lb >= band).mean()), "P_sign": float((lb > 0).mean()), "P_reversed": float((ub < 0).mean()),
            "P_lost": float((ub < band).mean()), "mean_se_b": float(se_b.mean()), "mean_width": float((ub - lb).mean())}


def table():
    print(f"tier-A deltas (% of parent): {np.round(X, 2).tolist()}  sum x^2 = {X @ X:.1f}  signed sum = {X.sum():.2f}")
    print("\nOC of the 8-design slope, P = 4, 90 % t-interval (7 dof), PERSISTS iff LB >= 0.3")
    for tau_r in (0.0, 0.25):
        print(f"\n-- design-to-design retention spread tau_r = {tau_r}")
        print(f"{'SE_T %':>7} | " + " | ".join(f"r={r:<4}" for r in (0.0, 0.3, 0.5, 0.7, 1.0)) + " | mean SE(b) at r=0.5")
        for se_t in (0.1, 0.5, 1.0, 1.5, 1.9, 2.3, 2.7, 3.0, 4.0):
            row = [oc(se_t, r, tau_r) for r in (0.0, 0.3, 0.5, 0.7, 1.0)]
            print(f"{se_t:>7} | " + " | ".join(f"{o['P_persists']:.2f}  " for o in row) + f" | {row[2]['mean_se_b']:.3f}")
    print("\nP(sign resolved: LB > 0) and P(reversed: UB < 0), tau_r 0.25")
    for se_t in (1.0, 1.9, 2.7, 4.0):
        print(f"SE_T {se_t}: " + "  ".join(f"r={r}: sign {oc(se_t, r, 0.25)['P_sign']:.2f} rev {oc(se_t, r, 0.25)['P_reversed']:.2f}"
                                         for r in (-0.5, 0.0, 0.3, 0.5)))
    # viability threshold: largest SE_T with P(PERSISTS | r = 0.5, tau_r 0.25) >= 0.80 and P(PERSISTS | r = 0) <= 0.05
    print("\nViability SE_T* search (P(LB>=0.3 | r=0.5, tau 0.25) >= 0.80):")
    for se_t in np.arange(1.5, 3.6, 0.1):
        p5 = oc(se_t, 0.5, 0.25)["P_persists"]; p0 = oc(se_t, 0.0, 0.25)["P_persists"]; p3 = oc(se_t, 0.3, 0.25)["P_persists"]
        print(f"  SE_T {se_t:.1f}: P(r=0.5) {p5:.3f}  P(r=0.3) {p3:.3f}  P(r=0) {p0:.3f}")
    # 10-design variant (finalist + M added) for reference
    x10 = np.append(X, [4.05, 2.90])
    print("\n10-design slope (finalist + M added) at SE_T 1.9, tau 0.25:",
          {r: round(oc(1.9, r, 0.25, x=x10)["P_persists"], 2) for r in (0.3, 0.5, 0.7)})
    # secondary designs: sign only, finalist 4.05 %, M 2.90 %, R-best 2.20 %, positive controls +-15.5 %
    print("\nSecondary sign checks (one-sided, LB of a single delta > 0; SE_eff = sqrt(2) SE_T / 2)")
    for se_t in (1.0, 1.9, 2.7):
        se_eff = math.sqrt(2) * se_t / 2
        for name, d in (("finalist 4.05", 4.05), ("M 2.90", 2.90), ("R-best 2.20", 2.20), ("pitch +-3.1 (15.5)", 15.5)):
            ps = {r: round(float(stats.norm.sf((stats.t.ppf(0.95, 3) * se_eff - r * d) / se_eff)), 2) for r in (0.5, 1.0)}
            print(f"  SE_T {se_t}: {name:>20}: P(sign resolved) r=0.5 {ps[0.5]}, r=1.0 {ps[1.0]}")


def window(rms, tau, se_t):
    """CU needed so that rms * sqrt(2 tau / W) <= se_t."""
    return 2 * tau * (rms / se_t) ** 2


def cost():
    cells = {"flow_32": 1.382e6, "flow_48": 4.666e6, "flow_64": 11.06e6}
    spc = {"flow_32": {80: 113, 250: 70, 450: 68, 800: 68, 2500: 73}, "flow_48": {80: 223, 250: 123, 450: 109, 800: 109, 2500: 115},
           "flow_64": {800: 150, 2500: 160}}
    thr, ovh = 5.2e7, 1.2

    def run_h(grid, re, cu, factor=1.0):
        return cu * spc[grid][re] * cells[grid] / thr * ovh * factor / 3600

    print("\nPer-run wall (h) incl. 20 % overhead")
    for grid in ("flow_32", "flow_48"):
        for re in (250, 800, 2500):
            print(f"  {grid} Re {re}: 120 CU {run_h(grid, re, 120):.2f}  300 CU {run_h(grid, re, 300):.2f}  480 CU {run_h(grid, re, 480):.2f}  880 CU {run_h(grid, re, 880):.2f}")
    print(f"  flow_64 Re 2500: 300 CU {run_h('flow_64', 2500, 300):.2f} h; 880 CU {run_h('flow_64', 2500, 880):.2f} h")

    print("\nStage 0 (parent only): flow_32 3 phases x (R1 240 CU; 450/800/2500 800 CU) + flow_48 1 phase x 400 CU at 800 and 2500")
    s0 = 3 * run_h("flow_32", 250, 240) + sum(3 * run_h("flow_32", re, 800) for re in (450, 800, 2500)) + run_h("flow_48", 800, 400) + run_h("flow_48", 2500, 400)
    print(f"  Stage 0 GPU h: {s0:.1f}  (+ flow_64 300 CU at 2500 would add {run_h('flow_64', 2500, 300):.1f})")

    print("\nFormal rung run table: flow_32 15 states x 4 phases (parent, 8 tier A, finalist, M, R-best, pitch +3.1, pitch -3.1, roll NC);"
          " flow_48 3 states x 2 phases (parent, C4, reflex -29.3); domain control parent + C4 x 2 phases flow_32 (x1.2 cells);"
          " Poisson control parent + C4 x 1 phase (x1.5)")
    print("  R1 Re 250: steady total 120 CU (burn-in 80 + 40), with parent repeat (16 x 4); fallback 240 CU")
    for cu in (120, 240):
        r1 = 64 * run_h("flow_32", 250, cu) + 6 * run_h("flow_48", 250, cu)
        print(f"    total {cu} CU: {r1:.1f} GPU h")
    for re in (450, 800, 2500):
        print(f"  Re {re} (burn-in 80 + window W):")
        for W in (220, 300, 400, 800):
            cu = 80 + W
            f32 = 60 * run_h("flow_32", re, cu); f48 = 6 * run_h("flow_48", re, cu)
            ctrl = 4 * run_h("flow_32", re, cu, 1.2) + 2 * run_h("flow_32", re, cu, 1.5)
            print(f"    W {W:>3}: flow_32 {f32:.1f} + flow_48 {f48:.1f} + controls {ctrl:.1f} = {f32 + f48 + ctrl:.1f} GPU h")
    print("\nDescriptive probe at a dropped rung: parent + finalist + C4 x 2 phases flow_32, 480 CU:",
          f"{6 * run_h('flow_32', 2500, 480):.1f} GPU h")

    print("\nWindow needed (CU after burn-in) for SE_T targets, SE_T = rms sqrt(2 tau / W)")
    for rms in (5, 10, 20, 35):
        for tau in (2.0, 3.9, 8.0):
            print(f"  rms {rms:>2} %, tau {tau}: SE_T 2.7 % -> {window(rms, tau, 2.7):>6.0f} CU; 1.9 % -> {window(rms, tau, 1.9):>6.0f}; 1.0 % -> {window(rms, tau, 1.0):>6.0f}")

    print("\nParent scan (exploratory): 24 parents x 1 phase x 240 CU flow_32 at Re_L ~2000 (Re_c 3e3) + 2 parents x 10 mode states x 1 phase")
    ps = 24 * run_h("flow_32", 2500, 240) + 20 * run_h("flow_32", 2500, 240)
    print(f"  {ps:.1f} GPU h (flow_48 check of 2 parents x 240 CU adds {2 * run_h('flow_48', 2500, 240):.1f})")

    print("\n2D bridge (exploratory): 2D grid ~1600 x 600 = 0.96 M cells, ~250 steps/CU at 400 cells/chord, 200 CU, 7 states x 3 Re x 2 grids")
    run2d = 200 * 250 * 0.96e6 / thr * ovh / 3600
    print(f"  per run {run2d:.2f} h; 42 runs {42 * run2d:.1f} GPU h")


if __name__ == "__main__":
    table()
    cost()
