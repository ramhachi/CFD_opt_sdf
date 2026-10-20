# UNC-01 (#61, M2) registered result: **M2_COMPLETE**

Human summary of `analysis.json` (SHA-256 `ee71c6d6…`, written once by the frozen `scripts/analyze_unc01.py u2`; registration `docs/unc01_registration_2026_10_20.md`, freezes `freeze1.json`, `freeze1_amendment1.json`, `freeze2.json`, `amendment2_u3_local.json`). Every number below is copied from that file; where this summary and the file differ, the file governs.
Scope: v18 analytic plate, Re = 80 reduced-laminar WaterLily (Kaggle T4), in-plane (x, y) placement phases (R2 sequence, k = 1..6 on flow_24/flow_32, 1..4 on flow_48; z not sampled), coarse-mesh OpenFOAM v2512 (local Docker, bitwise-equivalent to Kaggle CPU) with 16 mirror pairs of ±0.5-4 mm 3-axis shifts; uncertified geometry; one amplitude per state. Not: physical downforce, grid convergence, a gradient, other parents, modes or amplitudes. All qualification flags false; `shape_update_allowed=false`.

## Design as run
L = pitch (3.1 deg), L2 = reflex (29.3 mm), L_mid = pitch +1.3 deg (U1 selection, exploratory, not cited). flow_32: parent, D0 +3 mm, pitch ±3.1 deg, pitch +1.3 deg, reflex +29.3 mm, s050 -5 mm, roll +25 mm (8 states x 6 phases); flow_24 (kernel `f24`, budget rule: T = 43,989 s <= 46,800 s): parent, D0, pitch +3.1 (3 x 6); flow_48: parent, pitch +3.1 (2 x 4). All six U2 kernels verified (per-kernel harness checks); no run's half-window drift above 0.002 (largest 2.2e-4). U2 GPU session time 12.2 h (cap 13 h). U3: 256/256 cases completed locally (2.9 h).
Parent phase means (downforce / drag, N): flow_24 0.26173 / 0.27001, flow_32 0.26374 / 0.27471, flow_48 0.26578 / 0.28403; parent placement SD sigma_F (downforce) 1.8e-3, 1.32e-3, 8.2e-4 N.

## Q1: sigma_d (flow_32, P = 6; N)
| state | Delta_bar downforce | sigma_d downforce | |Delta|/SE | r [>= 80 %] | Delta_bar drag | sigma_d drag |
| --- | --- | --- | --- | --- | --- | --- |
| D0 +3 mm | +4.36e-4 | 2.80e-4 | 3.8 | 0.64 [0.28, 2.85] | +2.60e-3 | 7.28e-4 |
| pitch +3.1 deg (L+) | +4.073e-2 | 5.46e-4 | 183 | 0.013 [0.009, 0.028] | +2.966e-2 | 2.27e-3 |
| pitch -3.1 deg (L-) | -4.201e-2 | 4.22e-4 | 244 | 0.010 [0.007, 0.021] | -2.802e-2 | 8.29e-4 |
| pitch +1.3 deg (L_mid) | +1.891e-2 | 2.08e-4 | 223 | 0.011 [0.007, 0.023] | +1.279e-2 | 6.05e-4 |
| reflex +29.3 mm (L2) | -1.335e-2 | 4.46e-4 | 73 | 0.033 [0.022, 0.072] | -9.74e-3 | 5.91e-4 |
| s050 -5 mm | +5.6e-6 | 3.9e-6 | 3.5 | 0.71 [0.30, 3.51] | -3.4e-5 (unresolved) | 6.8e-5 |
| roll +25 mm (control) | -1.648e-3 | 2.09e-4 | 19 | 0.13 | -9.79e-4 | 1.36e-4 |
Common phases remove most of the placement noise: sigma_d / (sqrt(2) sigma_F) = 0.11-0.29 for downforce (0.03-0.50 for drag). flow_24: D0 -6.57e-4 (sigma_d 2.97e-4), pitch +3.1 +4.126e-2 (1.32e-3); flow_48 (P = 4): pitch +3.1 +4.155e-2 (4.97e-4).
sigma_d(Delta) (descriptive OLS of log sigma_d on log |Delta_bar| over the six flow_32 non-control states): slope 0.48 ± 0.11 (downforce), 0.42 ± 0.09 (drag): neither additive (0) nor multiplicative (1). Fitted downforce sigma_d: 9.7e-5 N at |Delta| = 1e-3 N, 2.9e-4 at 1e-2, 5.0e-4 at 3e-2. Even part of L (curvature): -6.4e-4 ± 4.2e-4 N (downforce), small against the odd part 4.1e-2. The native phase was not atypical: (Delta_k0 - Delta_bar)/sigma_d within ±1.8.

## Q2 (descriptive): `NOT_SEPARATED` (downforce), `S050_UNRESOLVED` (drag)
Both D0 and s050 are resolved for downforce (3.8 and 3.5 SE) with overlapping r intervals (0.64 [0.28, 2.85] vs 0.71 [0.30, 3.51]). On v18, D0 +3 mm is a weak downforce lever (and changes sign between flow_24 and flow_32, Q3) but a clear drag lever (r 0.28). The wide analytic arms have r = 0.01-0.03. Confounds as registered (sign, volume +7.6 % vs about 0, 3.0 vs 4.4 mm, support 1.0 vs 0.02). `Q2_OF`: `D0_UNRESOLVED` (downforce; OpenFOAM D0 -1.4e-4 ± 1.1e-4 N), `S050_UNRESOLVED` (drag); not comparable with the WaterLily ordering.

## Q3: flow_32 and flow_48 `EQUIVALENT`; flow_24 `FLOW24_DIFFERENT` (downforce)
- L+ (pitch +3.1 deg), flow_32 / flow_48: R = 0.980, 90 % interval [0.962, 0.999] (downforce), 0.953 [0.873, 1.039] (drag): both inside [0.8, 1.25].
- flow_24 / flow_32: L+ R = 1.013 [0.984, 1.042] (`EQUIVALENT`), but D0 changes sign (flow_24 -6.57e-4 vs flow_32 +4.36e-4, both resolved): `FLOW24_DIFFERENT` for downforce, so the GRID-02 flow_24 outlier persists on v18 for small responses. Drag: `FLOW24_INDETERMINATE` (D0 R = 1.04 [0.77, 1.40]).
- Registered consequence: `EQUIVALENT` supports R3 (optimise on flow_32, confirm on flow_48) for large modes; flow_24 stays demoted.

## Q4: E2 inputs (common phases k = 1..4; J_scale 3.6e-3 N, not binding)
| response | S_b | S_c | S_d | literal E2 gain 2 max(S_b, S_c) | paired gain 2 S_d | I_f(L+) (descriptive) |
| --- | --- | --- | --- | --- | --- | --- |
| downforce | 0.0067 ± 0.0026 | 0.0101 ± 0.0018 | 0.0034 ± 0.0015 | 2.0 % | 0.68 % | 15.6 % |
| drag | 0.0299 ± 0.0064 | 0.0328 ± 0.0106 | 0.0029 ± 0.0049 | 6.6 % | 0.58 % | -11.0 % |
(|·| of noisy differences is biased up by about 0.8 SE; all-phase versions in the file.) On v18 the absolute flow_32/flow_48 shift of the parent is 0.8 % (downforce) and 3.3 % (drag), smaller than v17's 8-10 %.

## U3: OpenFOAM retention (coarse Stage V mesh; 16 mirror pairs, all 256 cases complete)
| state | Delta_bar_OF downforce (SE) | rho downforce [90 % on |rho|] | rho drag |
| --- | --- | --- | --- |
| pitch +3.1 | +2.736e-2 (8.7e-5) | 0.672 [0.663, 0.680] | 0.790 [0.742, 0.842] |
| pitch -3.1 | -2.964e-2 (8.8e-5) | 0.706 [0.699, 0.713] | 0.797 [0.778, 0.817] |
| pitch +1.3 | +1.289e-2 (2.4e-4) | 0.681 [0.655, 0.708] | 0.799 [0.765, 0.835] |
| reflex +29.3 | -8.36e-3 (1.2e-4) | 0.626 [0.602, 0.652] | 0.665 [0.621, 0.712] |
| roll +25 | -6.62e-4 (5.8e-5) | 0.40 [0.33, 0.49] | 0.75 [0.63, 0.89] |
| D0 +3 | -1.4e-4 (1.1e-4), unresolved | — | 1.97 [1.56, 2.48] |
| s050 -5 | +1.14e-4 (1.3e-5) | 20 [11, 38] | unresolved |
Every resolved pair has the WaterLily sign. Limits as registered: local 3-axis shifts (not the WaterLily whole-cell phases); STL extraction differs from the SDF the WaterLily body samples. The coarse mesh gives a 20x larger response to the 4.4 mm local bump than WaterLily: a geometry-representation effect, not a fidelity result.

## Coefficients for M3a (#62) — what M2 provides (M3a decides how to use them)
1. **3-sigma rule**: paired-difference sigma_d on flow_32 with 6 common phases is 2.1-5.5e-4 N for downforce over the wide arms (largest pitch +3.1: 5.46e-4, 90 % upper 1.14e-3; 3 SE at P = 6: 6.7e-4 N), 5.9e-4-2.3e-3 N for drag. sigma_d grows roughly as |Delta|^0.5 (fit above); for planning, phases_needed(r) = ceil(9 r^2) is 1 for the wide analytic arms and 4 (74 at r_hi) for D0.
2. **Grid spread**: flow_32 / flow_48 ratio of the L+ difference 0.980 [0.962, 0.999] (downforce): a 2 % spread, far inside a "0.5 x median" rule; flow_24 disagrees in sign for the small D0 response.
3. **Retention OpenFOAM / WaterLily**: 0.63-0.71 (downforce) and 0.67-0.80 (drag) for the wide analytic arms (pitch, reflex); signs agree; small or local responses (D0, s050) are not usable for retention on the coarse mesh.
4. **E2**: S_b 0.0067, S_c 0.0101, S_d 0.0034 (downforce): the literal rule asks for a 2.0 % gain, the paired analogue 0.68 %.
5. **Negative control**: an exact one-cell x-translation is **not null** in this box: -1.65e-3 ± 0.09e-3 N on flow_32 (-0.62 %), -6.6e-4 N on OpenFOAM. An x-translation control in M3a must be judged against this measured value (and its sigma_d 2.1e-4 N), not against zero.

## Exploratory (U01, not cited)
U0 passed on all three grids (drift < 1e-5). The half-cell bridge moved the v18 parent's flow_32 downforce by -1.27 % (v17 GRID-02: -9.6 %).
