# FID-01 (#62, M3a) registered result: **FID01_GO**

Human summary of `analysis.json` (SHA-256 `b89203d0…`), written once by the frozen `scripts/fid01/analyze_fid01.py main` (SHA-256 `d826413e…`, as recorded in freeze 1 amendment 1). Registration `docs/fid01_registration_2026_10_21.md` (revision 3, SHA-256 `4d692af6…`, amendments 1-3). Freezes: `freeze1.json` (`50107db5…`), `freeze2.json` (`db7ee0e2…`), `freeze3.json` (`a0e83d59…`). Every number below is copied from `analysis.json`; where this summary and the file differ, the file governs. This summary is written once (registration §10); later readings go in separate dated notes.

Claim ceiling (registration §1): Re = 80 reduced-laminar WaterLily (Kaggle T4, flow_32 placement-phase mean, confirmed on flow_48) against laminar steady OpenFOAM v2512 (local Docker, three snappy meshes, not grid-converged). The designs are the registered ones: one analytic v18 parent, one amplitude each (two for camber and heave), uncertified geometry, in-plane placement phases only (z, the ride height, is not sampled). The result is about **differences** between these pre-registered designs. It says nothing about designs an optimizer selects; XV-01 verifies those. It is not physical downforce, not FSAE and not high Re. All qualification flags stay false; `shape_update_allowed=false`.

## As run
- **WaterLily flow_32**: four kernels (phases k = 7..10 of the R2 sequence), 18 states each (parent, 13 wide designs including the sub-threshold heave −13.7, 3 narrow designs, and the roll control). All four were verified per kernel by the harness (`wl/verify/table_f32k*.json`). Session wall: 30,653 s.
- **WaterLily flow_48**: one kernel at phase 7 covering the d_set run set (parent, the 4 tier-B designs and 2 tier-A controls, C4 and reflex −29.3), verified (`table_f48.json`), about 4.4 h. Total WaterLily GPU time is about 12.9 h against the 18 h cap. The budget rule (§4.3) gave T = 47,293 s ≤ 64,800 s, so flow_48 was pushed. No INFRA_LOSS and no rerun.
- **OpenFOAM** (local Docker, U3/X3 pipeline, LOCAL-OF-01 lock), 733 cases, every one valid and converged, with no timeout, no lost kernel and no rerun:
  - V1: 4 kernels × 168 = 672 cases. Every state is run at 16 mirror pairs (Halton 49-64), including the EX r = 4 exports.
  - V2: 4 kernels × 13 = 52 cases (pairs 49-50).
  - V3: 9 cases, the parent and the 8 tier-A designs at shift 49 +.
  - Kernel wall times: V1 about 4.9 h, V2 about 6.1 h, V3 about 18.3 h for a two-case kernel. Kernels within a level ran in parallel.
- **Minimum data**: pass.

## Decision set (from flow_32 alone, `d_set.json`, frozen in freeze 3 before any V2/V3 or flow_48 run)
- **Tier A** (|Δ32| ≥ Δ_lit = 5.363e-3 N and > 3 SE_eff): 8 designs, covering 3 families (rigid, section, combination), 5 of them positive. The set is valid (§6.2).
- **Tier B** (between Δ_min = 1.807e-3 N and Δ_lit): heave −31.1, heave +31.1, heave −31.1 + pitch +0.7, and twist +2.3.
- **Eligible support designs**: none. Every narrow design had |Δ32| < Δ_min.
- **Sub-threshold wide design**: heave −13.7.

## Tier A and tier B (downforce, N; SE in parentheses)
Column notes:
- V3 SE is the leave-one-out residual SD of the tier-A V3-on-V1 fit (§6.1).
- ρ = Δ_OF / Δ32.
- Rule codes: P = PASS, U = UNRESOLVED_STAT, **F** = FAIL (resolved).

| slot | design | family | Δ32 (SE_eff) | V1 (SE) | V2 (SE) | V3 (SE) | ρ V1 [90 %] | ρ V2 / V3 | G1 G2 G3 G4 G5 | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A: W4b | camber -11.3 | section | +7.184e-03 (1.0e-04) | +5.535e-03 (1.9e-04) | +4.031e-03 (1.4e-04) | +5.081e-03 (1.5e-03) | 0.77 [0.71, 0.84] | 0.56 / 0.71 | P P P P P | PASS |
| A: C1 | camber -11.3, reflex -11.3 | combination | +1.326e-02 (1.0e-04) | +8.592e-03 (3.1e-04) | +7.740e-03 (1.4e-04) | +9.330e-03 (1.6e-03) | 0.65 [0.59, 0.71] | 0.58 / 0.70 | P P P P P | PASS |
| A: W4 | camber -19.7 | section | +1.300e-02 (1.7e-04) | +7.957e-03 (3.2e-04) | +6.782e-03 (1.4e-04) | +1.211e-02 (5.3e-04) | 0.61 [0.55, 0.68] | 0.52 / 0.93 | P P P P P | PASS |
| A: W5 | camber +19.7 | section | -1.018e-02 (1.2e-04) | -5.847e-03 (2.1e-04) | -7.930e-03 (1.4e-04) | -6.801e-03 (1.6e-03) | 0.57 [0.53, 0.63] | 0.78 / 0.67 | P P P P P | PASS |
| A: W3 | pitch -0.7 | rigid | -8.953e-03 (1.2e-04) | -5.923e-03 (1.6e-04) | -6.969e-03 (1.4e-04) | -5.622e-03 (1.5e-03) | 0.66 [0.62, 0.71] | 0.78 / 0.63 | P P P P P | PASS |
| A: C4 | pitch -1.3, reflex +29.3, sweep +11.3 | combination | -3.204e-02 (1.7e-04) | -2.146e-02 (8.9e-05) | -2.249e-02 (1.4e-04) | -2.238e-02 (1.5e-03) | 0.67 [0.66, 0.68] | 0.70 / 0.70 | P P P P P | PASS |
| A: W8 | pitch +0.7 | rigid | +1.061e-02 (1.2e-04) | +7.182e-03 (1.0e-04) | +6.291e-03 (1.4e-04) | +7.636e-03 (1.6e-03) | 0.68 [0.65, 0.71] | 0.59 / 0.72 | P P P P P | PASS |
| A: W6 | reflex -29.3 | section | +1.565e-02 (1.8e-04) | +9.766e-03 (1.8e-04) | +8.835e-03 (1.4e-04) | +1.070e-02 (1.6e-03) | 0.62 [0.59, 0.66] | 0.56 / 0.68 | P P P P P | PASS |
| B: W1 | heave -31.1 | rigid | -3.537e-03 (3.7e-04) | -2.678e-04 (1.7e-04) | -1.303e-03 (1.4e-04) | — | 0.08 [0.02, 0.36] | 0.37 / — | P U **F** **F** **F** | FAIL |
| B: C2 | heave -31.1, pitch +0.7 | combination | +5.150e-03 (3.5e-04) | +6.075e-03 (7.2e-05) | +5.412e-03 (1.4e-04) | — | 1.18 [1.00, 1.39] | 1.05 / — | P P P P P | PASS |
| B: W2 | heave +31.1 | rigid | +5.214e-03 (7.7e-04) | -1.148e-03 (1.6e-04) | -1.925e-04 (1.4e-04) | — | -0.22 | -0.04 / — | **F** U **F** **F** P | FAIL |
| B: W7 | twist +2.3 | span | +3.622e-03 (1.0e-04) | +2.940e-03 (9.9e-05) | +1.991e-03 (1.4e-04) | — | 0.81 [0.73, 0.90] | 0.55 / — | P P P P P | PASS |

- **G3-set** (tier A, V3 on V1 through the origin, n = 8): slope 1.086, 90 % interval [0.992, 1.181], inside [0.6, 1.67], so **PASS**. Residual SD 1.45e-3 N.
- **G5**:
  - Geometry (X1, the STL volume band, and the STL-SDF volume chain ≤ 0.01) passes for every judged design.
  - Drag is tested where |ΔD32| ≥ 2e-3 N:
    - Tier A: ρ_drag on V1 is 0.58 (C1), 0.87 (pitch −0.7), 0.73 (C4), 0.84 (pitch +0.7) and 0.69 (reflex −29.3). The other three tier-A designs are below the tested size.
    - Tier B: heave −31.1 + pitch +0.7 has 1.92 [1.52, 2.43] (PASS, ρ ≤ 2). Heave −31.1 has −0.38, a resolved opposite sign (WaterLily −3.23e-3 N, OpenFOAM V1 +1.22e-3 N), so G5 FAILs.

## Controls
- **NC (x-translation by one cell, roll +25 mm)**:
  - WaterLily flow_32: −1.718e-3 N (SE 1.5e-4) against M2's −1.648e-3, z = 0.41.
  - OpenFOAM V1: −8.07e-4 N (SE 8.1e-5, 16 pairs) against M2's −6.61e-4, z = 1.45.
  - Both are CONSISTENT (z ≤ 3.5): the chain reproduces M2's measured non-null translation.
- **EX (STL export resolution r = 4 vs r = 8 on V1)**:
  - W4 camber −19.7: δ_EX −6.0e-6 N (SE 7.0e-6), tolerance 8.0e-4.
  - W6 reflex −29.3: −3.1e-7 N (SE 8.1e-6), tolerance 9.8e-4.
  - Both are `EXPORT_INSENSITIVE`. The parent's absolute change from r = 8 to r = 4 is −1.18e-5 N.

## Outcome (§6.7, in order)
1. Minimum data pass.
2. NC CONSISTENT on both solvers.
3. Decision set valid (8 designs, 3 families, 5 positive).
4. Neither a tier-A design nor G3-set FAILs.
5. Every tier-A design and G3-set PASS, so the outcome is **`FID01_GO`**. No extension was required (`extension_plan` null). Cause: none.

## Registered secondary labels (no effect on the outcome)
- **Tier B: `TIER_B_FAIL`**:
  - The two pure-heave designs FAIL. On heave −31.1, OpenFOAM keeps 8 % (ρ_V1 0.08 [0.02, 0.36]). On heave +31.1, OpenFOAM has the opposite sign on V1 (−1.15e-3 N against WaterLily +5.21e-3 N).
  - The other two pass: heave −31.1 + pitch +0.7 (ρ 1.18) and twist +2.3 (ρ 0.81).
- **Heave sub-label**: heave −31.1 FAIL, heave +31.1 FAIL, heave −31.1 + pitch +0.7 PASS. Descriptively, the sub-threshold heave −13.7 also has the opposite sign on V1 (WaterLily −1.15e-3, OpenFOAM +1.21e-3 N).
  - On V1, OpenFOAM's heave response is small and not odd in the amplitude: −2.7e-4 N at −31.1, −1.15e-3 N at +31.1, +1.21e-3 N at −13.7.
  - WaterLily's heave response is odd and larger, and it depends on the grid (flow_48/flow_32 at k7: 1.49 and 0.62).
  - This is the registered caveat (§1, §6.9): heave moves the body against the z lattice, which is never phased.
- **Support: `SUPPORT_UNTESTABLE`** (no narrow design reached Δ_min). Descriptive values, not judged:

| slot | design | support | Δ32 (SE_eff) | V1 (SE) | why not judged |
| --- | --- | --- | --- | --- | --- |
| W1b | heave -13.7 | 0.962 | -1.152e-03 (2.8e-04) | +1.207e-03 (2.3e-04) | below Delta_min |
| N1 | bump_lower -15 | 0.062 | -1.499e-03 (1.0e-04) | +4.155e-04 (3.9e-05) | below Delta_min |
| N2 | bump_upper -15 | 0.062 | +5.242e-04 (1.0e-04) | +1.239e-03 (2.7e-05) | below Delta_min |
| N3 | bump_small +20 | 0.010 | -3.940e-04 (1.0e-04) | -3.879e-05 (3.6e-06) | below Delta_min |

  The narrow design with the largest WaterLily difference (N1, −1.50e-3 N) has the opposite sign on V1 (+4.2e-4 N). As in M2, the coarse mesh does not represent the local bumps the way WaterLily does. Local modes stay out of M3b in any case (§6.4).
- **R3 (flow_48 vs flow_32 at phase k7)**:
  - All six designs are `R3_CONFIRMED` (same sign), so R3 is **not challenged**.
  - Ratios Δ48/Δ32:
    - Non-heave designs: 0.98 (C4), 0.89 (reflex −29.3), 0.96 (C2), 1.06 (twist +2.3).
    - Pure-heave designs: 1.49 (heave −31.1) and 0.62 (heave +31.1).
  - `R3_E2_EXCEEDED` is true: for heave +31.1 at k7, Δ32 = +6.82e-3 and Δ48 = +4.21e-3 N, so |Δ48 − Δ32| = 2.6e-3 N, above Δ_min.
- **EX**: `EXPORT_INSENSITIVE` (W4, W6).
- **Aggregate (S4)**:
  - The slope of Δ_V1 on Δ32 through the origin is 0.648, consistent with M2's wide-arm retention of 0.63-0.71.
  - Kendall's τ is 0.848 over all judged designs and 1.0 over the positive tier-A designs.
- **Improvement-only subset of tier A**: camber −11.3, C1, camber −19.7, pitch +0.7 and reflex −29.3 all PASS.
- **S_d,OF** (median over tier A of |ΔV3 − ΔV2| / |F_parent,V3|) = 0.00634.

## Consequences fixed by the registration (§8, `FID01_GO`)
- M3b may be registered, SCREEN-01 #64 first.
- **M3b minimum gain** g_min = max(2 S_d, x* / |J_b,48|) = max(0.68 %, 7.184e-3 / 0.265779) = **2.70 %** of the parent's flow_48 downforce.
  - x* = 7.184e-3 N is camber −11.3. It is the smallest |Δ32| of a PASSing tier-A or tier-B design that is larger than every non-passing tier-B design. The largest non-passing tier-B design is heave +31.1 at 5.214e-3 N.
  - The two passing tier-B designs (5.15e-3 and 3.62e-3 N) lie below that design, so they do not lower x*.
- **XV-01 (OpenFOAM side)**:
  - The G rules and coefficients of §6.3 and the OpenFOAM procedure of §5 (levels, shifts, validity) apply.
  - The OpenFOAM minimum gain is 2 max(S_d, S_d,OF) = 2 × 0.00634 = **1.27 %**.
- **R3**: not challenged and flow_48 was measured, so no mandatory flow_48 confirmation with P ≥ 2 is imposed on M3b. `R3_E2_EXCEEDED` is reported.
- **EX**: insensitive, so XV-01 has no registered export-resolution obligation.
- Flags unchanged: all qualification flags false, `shape_update_allowed=false`.

## What this shows and what it does not
- **Shows**: on fixed, pre-registered, wide-support analytic-mode designs of the v18 parent, every WaterLily flow_32 difference of at least 2.0 % of the parent downforce persisted in OpenFOAM.
  - The sign was the same on all three meshes.
  - OpenFOAM kept 0.57-0.77 of the magnitude on V1, and the V3/V1 slope was 1.09.
  - The ranking agreed (τ 1.0 among the positive tier-A designs).
  - Drag, where large enough, behaved the same way.
  - The 8 tier-A designs cover the rigid (pitch), section (camber, reflex) and combination families. The span family entered only through twist +2.3 in tier B, where it passed.
- **Does not show**:
  - Selected designs (the argmax bias of an optimizer; XV-01).
  - Local or narrow modes (untestable here, and descriptively opposite in sign on the coarse mesh).
  - Heave, the ride height: the pure-heave WaterLily responses did not persist. They are unphased in z and grid-sensitive in WaterLily. This is a registered secondary result. The M3b registration has to decide how heave enters its search space; nothing here fixes that.
  - Differences below 2.70 %.

## Descriptive note (not part of the registered analysis)
The production parent at 49 + reproduced the pre-registration probe's statuses exactly: 1562 iterations and 212,822 cells on V2; 4548 iterations and 1,461,141 cells on V3; same STL. No bitwise statement is possible: the probe's force files were removed by the sanitiser, and the compressed files differ by hash because the gzip headers carry a write time.
