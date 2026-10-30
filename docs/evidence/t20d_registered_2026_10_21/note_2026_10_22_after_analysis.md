# T2-0d: reading after the registered analysis (dated note, 2026-10-22; not part of the verdict)

Written after `analysis.md` and `verdict.json` (written once, unchanged). Computed with the frozen `scripts/analyze_t20d.py` functions on the committed outputs and,
for item 1, with `scripts/analyze_t20c.classify` on the committed T2-0c records (the comparison freeze 2 moved out of the analyzer because registration section 2
forbids reading T2-0c output there). Descriptive only.

1. **S0 against T2-0c (same id, 43 geometries).** S0 CONVERGED where T2-0c was VALID (34), NOT_CONVERGED where T2-0c was UNSTEADY (7) or SOLVER_FAIL (2): no
   disagreement. The non-settling of the steady solver reproduced in the new kernels.
2. **The 5 NONSTATIONARY URANS runs are slow transients, not oscillations.** Over the 10 T_c window (5 T_c for Udt05), relative linear drift and amplitude ratio
   s_H2/s_H1: xfine30 0.09 +1 U 4.5 % / 0.36, Udt2 4.3 % / 0.40; fine30 0.09 +1 U 1.6 % / 0.74, Udt2 1.3 % / 0.79; xfine30 0.09 0 Udt05 0.6 % / 0.20 (its U, over
   the longer window, settles in the second half). The registered window is too short at h/c 0.09, +1 deg; a longer transient there would cost more.
3. **Time-step dependence of the settled value.** At x134 0: Cl 1.30615 (2 dt), 1.30851 (dt), 1.31086 (dt/2) over the common interval: equal steps of +0.18 % per
   halving, observed order about 0. A PIMPLE steady limit that depends on dt (the flux interpolation's time-step term) fits this; the dt run is not "converged in
   time" in the usual sense. The derivative d(1) at 0.134 moves by 0.5 % between 2 dt and dt, so differences at one dt are much less affected than levels.
4. **Formulation offset.** Where S0 converges, the settled URANS Cl is 0.25-0.91 % (median 0.52 %) above S0; the 0.5 % agreement tolerance of the Q1 controls was
   at the edge of this offset (x134 -1 missed it by 0.02 %).
5. **What a cheaper form would need (not tested).** Every valid URANS run settles to a steady state, so the evaluator is a time-marching route to a steady solution
   that SIMPLEC 0.9 and SIMPLE 0.7 do not reach. A pseudo-transient (local time stepping) or a shorter warm-started URANS could be cheaper; `COST_MIN` (24 min
   warm-started at 2 dt) is a label, not a tested protocol.
