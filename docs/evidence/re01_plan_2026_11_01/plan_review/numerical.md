# RE-01 plan (rev 0): adversarial numerical review

Reviewer role: numerical. Plan under review: `docs/re01_plan_2026_11_01.md` (cited as "plan:LINE"), with `docs/evidence/re01_plan_2026_11_01/fable_analysis.md` ("fable:LINE") and `re_ladder.py`. The repository was read-only for me. Everything I computed is in the scratchpad (`calc/power.py`, `grid_gate.py`, `gate.py`, `cost.py`, `slope.py`, `wlenv/cfl2d.jl`); the 2D WaterLily probe is my own, uses WaterLily 1.8.0 on CPU, and is a proxy, not 3D evidence. Where a number is mine rather than the repo's I say so.

## Verdict: GO_AFTER_FIXES

The idea (a fixed-grid Re ladder on registered v18 designs, WaterLily-first, Stage 0 before registration) is sound and cheap enough. R1 (Re_L 250) is a well-posed rung. The decision machinery for R2/R3 is not: as written, a persisting effect would most likely come back as an unlabelled or UNRESOLVED rung, and the two-estimator gate would mislabel R1 itself. Four P1 items need a rewrite of the rules before registration (N1-N4). No redesign of the study concept is needed.

## Findings at a glance

| ID | Sev | One line |
| --- | --- | --- |
| N1 | P1 | SE target 1.9 % gives 3 SE_eff = 4.03 % vs finalist 4.05 %: the finalist gate has 21-58 % power at retention 0.5-1.0; use a pooled retention slope |
| N2 | P1 | The rung label set is not exhaustive (sign kept but unresolved, tau in [0.3, 0.6), OpenFOAM out of band have no label) |
| N3 | P1 | STAT_INCONSISTENT gate [0.5, 2] fires on the benign CRN case and on every steady rung (R1); 3 dof gives a 15 % false-fail rate; estimator B cannot be formed at the stopping time |
| N4 | P1 | Stage 0 (1 phase, 400 CU, parent only) cannot measure what the registration needs; its cost is 7-11 GPU h, not 3 |
| N5 | P2 | sigma_d from P = 4 phases is a 3-dof estimate; "3 SE_eff" is a t_3 test (p = 0.058); the roll floor has the same 3 dof |
| N6 | P2 | Adaptive window: optional-stopping bias, undefined per-run vs per-pair stopping, incompatible with the frozen-kernel budget and timeout rules |
| N7 | P2 | "Cheaper per convective unit" is unmeasured; a 2D probe says 1.3-1.5x, not 2x; R2/R3 steps are about 20 % / 40-45 % above the plan's table |
| N8 | P2 | T4 session and memory: memory is measured (not unknown); flow_64 at the 880-CU cap is 7.8-11.6 h; R4 is uncosted and unrunnable |
| N9 | P2 | flow_32/48 sign gate is weak (P = 2, sign only): 10-23 % false RESOLUTION_LIMITED at r 0.7-0.5; flow_64 at one phase cannot arbitrate |
| N10 | P2 | Leading-edge boundary layer is already below one cell at R1 on flow_32; section 9 over-reads BREAK labels |
| N11 | P2 | Outlet-domain control has a 46 % false-trigger rate and tests only the outlet, not the 10 % lateral/top blockage |
| N12 | P2 | Poisson probe (cap-hit above 10 %) is about 40x too insensitive; the repo's own GRIDRES-01 lesson says residual level is the discriminator |
| N13 | P2 | OpenFOAM leg: first-order upwind template, iteration count vs endTime, pimpleFoam CPU hours understated 3x, retention band [0.3, 3.0] vacuous |
| N14 | P2 | Re-80 anchor: a 12-state same-phase anchor is not needed; a 1-run byte-identity regression of the new case contract is |
| N15 | P2 | Rungs: R1 to R2 straddles the steady-to-unsteady switch; R3 is the costliest and least decidable rung |
| N16-N23 | P3 | allocation, Kendall tau, drift rule at R1, label inventory, citations, Re_w definition, arithmetic mismatches |

---

## P1 findings

### N1 (P1) The SE target is calibrated to retention 1.0, not to the plan's own hypothesis; the finalist gate is underpowered

Evidence
- plan:100 stops at SE_T <= 1.9 % of the parent force. With P = 4 and no CRN, SE_eff = sqrt(2) SE_T / sqrt(P) = 1.34 % of parent. 3 SE_eff = 4.03 % of parent (fable:133 states the same: "4 % gain at 3 SE_eff needs SE_T <= 1.9 %").
- The finalist gain is +1.077e-2 N = 4.05 % of 0.2658 N (`docs/evidence/screen01_2026_10_30/README.md`). So the target resolves the finalist only if retention is at least 1.0, and then with about 50 % probability.
- The plan's own hypothesis (fable:79, H1 at fable:232) is retention 0.3-1.0 at R1/R2 and "unresolved or reversed" at R3.
- Simulation (`calc/power.py`; Re-80 deltas of the 10 designs from FID-01 and SCREEN-01; SE_T = 1.9 %, P = 4, sigma_d estimated with 3 dof; uniform true retention r):

| r | P(cond 1: finalist sign right and >= 3 SE_eff) | P(cond 1+2+4) | P(cond 2 sign rule) | P(cond 4 tau >= 0.6) |
| --- | --- | --- | --- | --- |
| 1.3 | 0.78 | 0.78 | 1.00 | 1.00 |
| 1.0 | 0.58 | 0.57 | 1.00 | 0.99 |
| 0.7 | 0.34 | 0.32 | 1.00 | 0.93 |
| 0.5 | 0.21 | 0.17 | 0.97 | 0.81 |
| 0.3 | 0.11 | 0.06 | 0.86 | 0.56 |

  With SE_T = 0.95 % (4x the window): 0.98 / 0.83 / 0.58 / 0.28 at r = 1.0 / 0.7 / 0.5 / 0.3. Condition 1 is the only binding condition; conditions 2 and 4 pass almost whenever any effect survives (the Re-80 deltas are spread over -12 % to +6 %, mostly two sign clusters, so tau is easy). Under no effect (r = 0) cond 1 passes 3 %, so the rule is conservative on the null side and blind on the signal side.
- Required window for SE_T = 0.95 %: 864 CU at rms 10 % and tau_int 3.9 CU, 3,457 CU at rms 20 % (formula of fable:132, `calc/power.py`). That is beyond the 800-CU cap and beyond the GPU budget (N7).
- plan:16 (section 0, item 4) claims a resolvable difference of "2-4 %"; the registered target gives 4.0 % only.
- Consequence: `RE_PERSISTS` needs R2 and R3 both PASS. Even for true retention 0.7 the joint probability is about 0.1 (0.32 squared), and for r = 0.5 about 0.03.

Fix (the retention statistic, not the window)
1. Make the per-rung primary statistic the through-origin slope b_k of the rung deltas on the Re-80 deltas over the 10 designs, with a 90 % t-interval (9 dof). This is the FID-01 S4 / G3-set construction already used in this repository (`docs/evidence/fid01_2026_10_21/analysis.md`, "Aggregate (S4)"). In `calc/slope.py`: sum of squared Re-80 deltas is 303 (%^2), so SE(b) = 0.063 at SE_T = 1.9 %; the parent's common-mode error cancels (signed sum / sum of squares = 0.034); P(lower 90 % bound > 0.3) is 0.81 at r = 0.5, 0.99 at r = 0.7, 0.03 at r = 0.3, 0 at r = 0. With 25 % design-to-design spread in retention: 0.70 / 0.97 at r = 0.5 / 0.7. This is a different order of power per GPU hour than the finalist gate.
2. Keep the finalist as a secondary check: require only the right sign (one-sided, with the pooled SE), not 3 SE_eff.
3. State the minimum detectable retention per rung in the registration (a table from Stage 0 measurements) and write the claim ceiling from it.
4. If the finalist 3 SE_eff gate stays, set the target from a pre-registered r* (say 0.5), which needs SE_T <= 0.95 % and the window of N6/N7, not 1.9 %.

### N2 (P1) The decision tree has holes; some outcomes get no label

Evidence (plan:106-124)
- RUNG_PASS needs conditions 1-4; RUNG_BREAK needs a resolved sign flip on both grids or tau < 0.3; RUNG_UNRESOLVED is defined only as UNRESOLVED_STAT (SE target not met), RESOLUTION_LIMITED, or STAT_INCONSISTENT.
- Not covered: (a) SE target met, finalist sign preserved, but |Delta| < 3 SE_eff (the most likely outcome at R2/R3 by N1); (b) tau between 0.3 and 0.6 with everything else passing; (c) PASS conditions 1-3 met, but R1 OpenFOAM retention outside [0.3, 3.0] or OpenFOAM sign mismatch; (d) condition 2 failing (fewer than 3/4 of resolvable designs keep sign) without a resolved finalist reversal.
- The overall label is then undefined: RE_UNRESOLVED requires "no BREAK, some UNRESOLVED", and a rung of type (a)-(d) is neither.
- Related: UNRESOLVED_NUM appears only in section 3.6 (plan:140), not in the section 3.5 label list; "an UNRESOLVED design hits the cap" (plan:100) does not say whether one design at the cap makes the rung UNRESOLVED_STAT or only that design.
- Condition 3 lists "parent" among the flow_48 states whose sign must match (plan:113); the parent is the reference and has no delta.

Fix
- Replace the three-way split by an exhaustive partition on the retention interval (N1): `PERSISTS` (CI inside the band), `WEAKENED` (CI below the band but above 0), `BREAK` (CI includes or is below 0 with the finalist sign flipped, or reversed), `INDETERMINATE` (CI too wide to place against the band, pre-stated width), plus the existing `RESOLUTION_LIMITED` and `STAT_INCONSISTENT`. Give a precedence order and a "fail closed to INDETERMINATE" default. Write the outcome table with one row per combination before freezing.
- State per-design versus per-rung scope for UNRESOLVED_STAT; define OpenFOAM mismatch as its own qualifier of PASS, not a silent failure of PASS.

### N3 (P1) The two-estimator consistency gate is contradictory, low-power, and unformable at the stopping time

Evidence
1. It contradicts the plan's own expectation. plan:99 says "ratio outside [0.5, 2] gives STAT_INCONSISTENT, do not judge", and in the same sentence calls the ratio a descriptor of how much CRN benefit remains. Fable's expected ratio is 0.1-0.3 at Re 80 moving toward 1 at chaos (fable:177, H4 at fable:232). A ratio below 0.5 is the benign case (the paired design is better than the independent-sum prediction). As written R1 will be unjudgeable if it behaves like Re 80.
2. R1 steady: estimator B (within-run batch means of a steady signal) is about 0 (the Re-80 half-window drifts are 6.6e-9 to 3.9e-5, `screen01_f_f32*/flow_32.summary.json`), so sigma_d,pred is about 0 and the ratio is large or undefined. The gate fires "inconsistent" on every steady rung. Estimator B cannot see placement (discretisation) variance at all; estimator A contains it. The expected relation is A >= B whenever placement noise exists, not A = B.
3. Degrees of freedom. A is the SD of 4 phase deltas, 3 dof. Even when the two estimators agree exactly (`calc/gate.py`): P(A/B < 0.5) = 0.139, P(A/B > 2) = 0.007, total 0.146; with B itself noisy (19 + 19 dof) 0.154. If the gate is evaluated per design (11 designs) the chance that at least one design fails is 0.84. The 90 % interval of s/sigma at 3 dof is [0.34, 1.61].
4. Estimator B needs "20 or more batches, each at least 5 tau_int" (plan:98), i.e. T >= 100 tau_int: 390 CU at the plan's tau = 3.9 CU, 800 CU at tau = 8. The adaptive rule stops at about 216 CU (fable:132: SE_T = 1.9 % at 216 CU for rms 10 %, tau 3.9). B is not computable when the window stops.
5. Common-mode structure: all designs at a phase share the same parent run, so per-design ratios are not independent and one noisy parent run moves every ratio the same way.

Fix
- Regime-conditional contract, decided by pre-registered tests (drift rule, spectral peak/line test): steady regime uses A only with the Re-80 machinery; B is not formed. Chaotic regime uses pooled A (see N5) as the decision SE; B is a diagnostic with a window long enough to form it (state the minimum, e.g. T >= 100 tau_int from Stage 0, otherwise "not formed", not "inconsistent").
- Make the gate one-sided where it protects the decision: STAT_INCONSISTENT only if pooled A / pooled B > 2 (unmodelled variance), in which case use A (the larger) instead of refusing to judge. A/B < 0.5 is reported as CRN retained.
- Evaluate per rung on pooled quantities (dof 33), never per design.

### N4 (P1) Stage 0 cannot measure the numbers the registration is supposed to fix, and is mis-costed

Evidence (plan:161-171)
- Parent only, one phase, window 400 CU. One phase gives no between-phase SD, hence no placement SD, no A-versus-B comparison and no CRN-ratio test: the very estimators N3 needs to validate. A single 400-CU run is half the 800-CU cap, so it cannot show whether SE_T keeps falling like 1/sqrt(T) up to the cap.
- The SE assumption (fable:132, "tau_int about one period", "rms 10-20 % is an assumption", fable:249) is not conservative in either direction. For narrowband shedding the zero-frequency spectral density S(0) is far below sigma^2 times one period; low-frequency wake modulation pushes the other way. My own 2D probe (below, N7): at Re_L 2500, 2D, flow_32, 300 CU, batch means give SE_T = 3.1 / 2.3 / 1.8 / 0.7 % of the mean at 5 / 10 / 20 / 40-CU windows, against 17 % at 20 CU from the plan's formula (rms 35 %, tau = one period 2.4 CU). At 2D Re 250 and 800 the SE_T at any window above 5 CU is about 0.3 %. 2D is not 3D (a 3D AR 0.72 wake has a broad spectrum), but the one-period assumption is untested and can be off by 10x.
- Cost: plan:153 says Stage 0 is "about 3 GPU h". Using Fable's own wall-per-120-CU column (fable:108-117): Re 250 (0.08 + 0.44), 800 (0.06 + 0.32), 2500 (0.06 + 0.29 + flow_64 0.93) = 2.18 h per 120 CU, so 7.3 h at 400 CU (8.7 h at 480 CU incl. burn-in). With my 2D-corrected step counts 11 h (`calc/cost.py`). About 3x understated.
- No Poisson or max-flux quantity is requested explicitly beyond "反復数"; no V2 OpenFOAM parent probe (N13).

Fix
- Stage 0 per rung: parent at 3 phases on flow_32 with a window of at least 800 CU after a measured burn-in (R1: 240 CU is enough if steady). That costs about 1.5-3 GPU h in total and gives: S(0) by batch means at 5 window lengths and by spectrum; the between-phase SD of parent time means versus B (this is the A/B test, and it needs no design runs); drift; Strouhal/rms; steps per CU and max flux (N7); Poisson residual quantiles (N12). One flow_48 run at 400 CU per rung and at most one flow_64 run of 300 CU (N8). Add a V2 parent OpenFOAM case at Re 250 (N13).
- Pre-register the window and SE target as explicit functions of the Stage 0 S(0) (with its uncertainty), not as 1.9 % / 800 CU constants.
- Correct the Stage 0 cost line.

---

## P2 findings

### N5 (P2) sigma_d from P = 4 phases is a 3-dof estimate; the "3 SE_eff" rule is a t_3 test

Evidence
- plan:97, plan:110-111, plan:103. SE_eff = SD(Delta_k) / sqrt(P) with P = 4 has 3 dof. `calc/gate.py`: P(|t_3| >= 3) = 0.058 (z = 3 would be 0.003); P = 2 (flow_48) is a 1-dof estimate, P(|t_1| >= 3) = 0.20; at pooled 33 dof 0.005. The 90 % interval of the estimated SD is [0.34, 1.61] of the truth at 3 dof, so a 3-sigma claim can be a 1-sigma claim with 5 % probability.
- The per-rung floor "roll control's sigma_d" (plan:103) is also a 3-dof estimate (relative error about 41 %), and the roll delta is not null (x-translation, -1.65e-3 N at Re 80; `docs/evidence/unc01_2026_10_20/analysis.md`).
- At Re 80 sigma_d grows like |Delta|^0.48 (UNC-01), so pooling there is not valid; in the chaotic regime sigma_d is about sqrt(2) SE_T, independent of |Delta|, and pooling across the 11 non-parent designs (33 dof) is valid. The regime has to be established first (N3).

Fix
- Use pooled sigma_d (all designs, plus roll) in the chaotic regime and a t-quantile with the pooled dof; keep per-design sigma_d (Re-80 rule) in the steady regime. For flow_48 (P = 2) use the pooled flow_32 sigma_d scaled by the run-length ratio (SCREEN-01 effectively did this: 4.46e-4 N at P = 2 vs 2.92e-4 N at P = 4).
- Take the floor as the pooled roll plus parent-pair sigma_d, not the 4-point roll SD alone.

### N6 (P2) The adaptive window as specified is biased, ill-defined across the pair, and incompatible with the frozen-kernel budget rules

Evidence (plan:100-102, fable:178)
- Optional stopping: stopping at the first 100-CU block where the estimated SE_T drops below 1.9 % selects downward noise in the estimate. With 10 batches the SE has 24 % relative error. The realised SE_T is then larger than the target, and the paired mean is mildly biased by data-dependent stopping. The estimator SE in N3/N5 inherits this.
- Per-run stopping: each design run at each phase stops on its own SE, but Delta_k is design minus the same-phase parent. Parent and design windows then differ and the parent run (shared by 11 designs) would have to run to the longest requirement. The plan does not say which.
- The adaptive logic needs online batch-means code and a wall-clock guard inside the Julia job. SCREEN-01/FID-01 kernels are frozen with per-state and kernel timeouts and a budget check `T = finished wall + estimate of unfinished` (`docs/screen01_registration_2026_10_30.md:90`). An adaptive run has no predictable wall, so the budget check has to use the cap, which for R2+R3 is 146 GPU h in my model (N7) against the 90 h cap: the check would refuse to push.
- The existing harness constants (per-state timeout 900 s for flow_32, `src/cfd_sdf/grid02_contract.py` KERNELS) assume 350-440 s runs; 880 CU at R2 is 1,300-2,400 s per run on flow_32.

Fix
- Replace the adaptive rule by a window T_k fixed per rung and per grid, derived from the Stage 0 S(0) and frozen at registration. If the frozen window misses the SE target the label is UNRESOLVED_STAT; no in-kernel decisions, no stopping bias, a computable budget and timeouts, and bit-identical repeats still possible.
- If adaptivity is kept: blocks fixed in advance, SE computed only from data before the block, minimum window of the B estimator (N3), same stop for parent and all designs of the phase, written output per block so a session kill keeps the last complete block.

### N7 (P2) "WaterLily gets cheaper per convective unit at higher Re" is only qualitatively right; magnitudes are optimistic

Evidence
- The step rule is `dt = min(10, 1 / (max flux_out + 5 nu))` in WaterLily 1.8.0 `Flow.jl:234-237` (`~/.julia/packages/WaterLily/yOkji/src/Flow.jl`). The plan/Fable cite `.../4Wr0g/src/Flow.jl:166-169`, which is version 1.6.1 (project uses 1.8.0, `julia/CFDSDFWaterLily/Manifest.toml`); the formula is identical, only the citation is wrong (P3).
- Measured at Re 80 (22 flow_32 runs, 6 flow_48 runs; `screen01_*/states/*/flow_*.summary.json`): 13,464-13,651 steps per 120 CU (flow_32), 26,360-27,310 (flow_48); implied max flux 1.53 and 1.58. Fable's table (fable:104-121) holds the max flux at 1.55 for all Re. The flux is a maximum over the whole domain of the summed outflow of a cell; it is a viscous-attached-flow value at Re 80 and grows as the leading-edge suction peak and shed vortices sharpen at higher Re. `re_ladder.py:15` even carries an unused "1.8 pessimistic" comment.
- My 2D WaterLily 1.8.0 probe (inclined stadium plate, v18 proportions, slip bottom as ground proxy, n = 32/48, 60 CU, second-half means; `wlenv/cfl2d.jl`):

| n | Re_L | steps per CU | mean max flux (2nd half) | rms/mean of force |
| --- | --- | --- | --- | --- |
| 32 | 80 | 133 | 2.15 | 0.000 |
| 32 | 250 | 91 | 2.15 | 0.17 |
| 32 | 800 | 93 | 2.69 | 0.45 |
| 32 | 2500 | 101 | 3.11 | 0.35 |
| 48 | 80 | 250 | 2.19 | 0.000 |
| 48 | 250 | 154 | 2.20 | 0.18 |
| 48 | 800 | 150 | 2.81 | 0.40 |
| 48 | 2500 | 164 | 3.34 | 0.38 |

  The Re 80 / Re 800 step ratio is 1.44 (n = 32) and 1.67 (n = 48), against 2.0 in the plan's model; Re 80 / Re 2500 is 1.32 and 1.53, against 2.2. Applying the measured max-flux ratios (1.0, 1.0, 1.25, 1.45 for Re 80, 250, 800, 2500) to the 3D Re-80 baseline gives steps per CU at flow_32 of 70 / 68 / 73 (R1 / R2 / R3) against the plan's 70 / 56 / 52, and at flow_48 of 123 / 109 / 115 against 121 / 89 / 79: about 20 % more at R2 and 40-45 % more at R3. 2D is not 3D (tip vortices, no ground boundary layer); the 3D max flux may be higher still.
- GPU hours with the proxy-corrected steps, 12 states x 4 phases flow_32, 4 x 2 flow_48, 2 x 1 flow_64, burn-in 80 CU, +20 % overhead, 5.2e7 cell-steps/s (`calc/cost.py`):

| window after burn-in | R1 (120 CU) | R2 | R3 | total |
| --- | --- | --- | --- | --- |
| 220 CU | 7.1 | 23 | 24 | 54 |
| 400 CU | 7.1 | 37 | 39 | 83 |
| 800 CU (cap) | 7.1 | 68 | 71 | 146 |

  The plan states 60 typical / 125 worst against a cap of 90 (plan:157). With max flux fixed at 2.5 (not unreasonable at Re 2500 in 3D): 98 h at the 400-CU window, 172 h at the cap. A 400-CU window already consumes 92 % of the cap; the cap is the binding constraint, and R3 is the rung that gets truncated.
- The "cheaper per CU" sentence is in section 0, item 3 as a fact (plan:13). It is a hypothesis to be measured in Stage 0.

Fix
- State it as a Stage-0 measurement (steps per CU and max flux at each Re and grid; both are in `flow_*.summary.json` already: `steps` and `t_end_reached`). Budget with measured steps per CU. Write the cap rule so R3 is the rung allowed to truncate, and say so in the labels (INCOMPLETE per rung, not per ladder).

### N8 (P2) GPU memory and the T4 12-hour session

Evidence
- Memory is not unknown, contrary to plan:224 and fable:96/247. `peak_vram_bytes` is recorded in every summary: 185.7 MB for flow_32 (1.382 M cells, 134 B/cell) and 612 MB for flow_48 (4.666 M cells, 131 B/cell) (`CUDA.used_memory()`, `scripts/waterlily_grid02_job.jl:155-178`). This gives flow_64 1.45-1.49 GB, flow_96 4.9-5.0 GB, flow_128 11.6-11.9 GB of 15.6 GB. Memory is not a constraint to flow_96.
- Session time: flow_64 at burn-in 80 + window 800 CU costs 7.8 h per run with the plan's dt, 9.6 h with the proxy step count, 11.6 h at max flux 2.5. The project's own kernel timeouts are at most 27,600 s = 7.7 h (`docs/screen01_registration_2026_10_30.md:85`). Two flow_64 runs cannot share a 12 h session at the cap. Fable's "flow_64 1-3 h" (fable:125) holds only for 120-400 CU.
- R4 (plan:66, fable:156): flow_96 at Re 8000 costs 4.5 h per 120 CU (fable:120), so a 300-CU run is about 11 h and four runs about 45 h, against Fable's "20 h" in the R4 row; one run is at the session limit. R4 is neither costed in plan:151-157 nor runnable without checkpointing. flow_96 also has the same coarsest multigrid level as flow_48 (77x11x29, 6 levels; my count with the 1.8.0 semi-coarsening rule in `MultiLevelPoisson.jl:52-54`, which reproduces the repo's 4/6/4/5 levels for flow_24/32/40/48), unlike flow_64 (7 levels, coarsest 27x5x11, same as flow_32).

Fix
- Cap flow_64 at 300 CU and call it descriptive; move R4 out of the plan or cost it honestly (flow_96 at 120 CU is already 4.5-6 h). Replace "GPU メモリは未確認" with the measured 131-135 B/cell.

### N9 (P2) The flow_32 / flow_48 sign gate is weak; flow_64 cannot arbitrate

Evidence
- Condition 3 (plan:113) and RESOLUTION_LIMITED (plan:118) use sign only, with flow_48 at P = 2 (plan:63: 4 states x 2 pairs/phases) and "flow_64 for parent and finalist" at one phase (plan:138, fable:153).
- Simulation (`calc/grid_gate.py`; finalist, M, W4 at the same true retention r on both grids, SE_T 1.9 %, flow_32 P = 4, flow_48 P = 2): P(all three flow_48 signs right) = 0.92 / 0.81 / 0.68 and P(RESOLUTION_LIMITED) = 0.02 / 0.10 / 0.23 at r = 1.0 / 0.7 / 0.5, with no grid effect at all. So at the plan's central hypothesis a quarter of runs would be labelled resolution-limited by noise alone.
- flow_64 as arbiter: one phase pair has SE = sqrt(2) x 1.9 = 2.7 % against a 4.05 % gain: P(sign right) = 0.93 at r = 1 and 0.77 at r = 0.5. It cannot adjudicate a flow_32/48 disagreement, yet it takes 5-15 GPU h per rung (28 % of R2's budget).
- Sign agreement is not a convergence test and does not check magnitude. At Re 80 UNC-01 and SCREEN-01 gated the Delta ratio flow_32/flow_48 in a band ([0.8, 1.25]; R = 0.980 [0.962, 0.999]). Here the plan reports "retention" (a magnitude) as its result but only gates sign. Two grids that share the same BDIM-smeared leading edge (N10) will agree in sign for the wrong reason.

Fix
- Primary: the flow_32 and flow_48 retention slopes (N1) with intervals, plus the ratio b_48/b_32 reported against a band. flow_48 should be parent + finalist + two large designs (C4, W6) at P = 4, not four states at P = 2 (same 8 runs, SE of the finalist delta 1.34 % instead of 1.9 %). Drop flow_64 at R2/R3 or move its budget into longer flow_32/48 windows.

### N10 (P2) Leading-edge resolution and BDIM: R1 is already affected, and section 9 over-reads BREAK

Evidence
- Plan:137 says the leading-edge boundary layer is below one cell for Re_L >= 800. My table (delta_LE = r / sqrt(Re_r), r = t/2 = 57.65 mm, Re_r = Re_L r / L, cells of 0.8/n m): Re_L 80: 0.96 / 1.44 / 1.92 cells (n = 32 / 48 / 64); 250: 0.54 / 0.81 / 1.09; 800: 0.30 / 0.46 / 0.61 (0.91 at n = 96); 2500: 0.17 / 0.26 / 0.34 (0.52 at n = 96). R1 on flow_32 and flow_48 is already below one cell; the Re-80 baseline is borderline resolved on flow_32 only.
- WaterLily's BDIM kernel is about two cells wide; a boundary layer thinner than one cell is replaced by the kernel, so the leading-edge flow on a grid behaves as if Re_r is capped near (r / dx)^2 = 5.3 / 12 / 21 / 48 for n = 32 / 48 / 64 / 96, whatever Re_L is. Holding delta_LE / dx at the Re-80 flow_32 value would need n = 57 / 101 / 179 at R1 / R2 / R3. The ladder is therefore a fixed-grid, increasingly under-resolved measurement; the plan states that ceiling (plan:38), but section 9 does not carry it.
- plan:210-213 reads BREAK as physics ("Re 80 gain is a low-Re effect"; "breaks when it separates"). In this solver a BREAK, a PERSISTS, or an UNRESOLVED can each be a leading-edge artefact shared by flow_32 and flow_48 (N9). The natural reference scale for the wake is the projected width w = 0.533 m: 21 / 32 / 43 cells at n = 32 / 48 / 64. WaterLily's own validation uses 88-168 cells per sphere diameter at Re 3700 and about 21 per cylinder diameter at Re 7620 for one integrated quantity (fable:127); the plan's phrase "range where WaterLily iLES is validated" for R3 (plan:65) is supported by the cylinder case only, on w.
- The registered geometry is a 0.025 m phi lattice interpolated onto each flow grid (`docs/gridres01_plan_2026_10_20.md:84`), so flow_48/64/96 refine the flow, not the leading-edge shape (radius 2.3 design cells).

Fix
- Rewrite section 9 so each reading is "in this solver family on this grid sequence" and add the leading-edge caveat to every row. Add the R1 leading-edge numbers to the claim ceiling. Change plan:137 to "R1 and above".

### N11 (P2) The outlet-domain control is underpowered and tests the wrong thing

Evidence (plan:139)
- Rule: +1 m outlet at R3, parent only; "force changes by 2 % or more" marks the rung domain-sensitive. The two runs are independent chaotic means with SE_T 1.9 % each: noise of the difference 2.7 %. `calc/gate.py`: P(|diff| > 2 % | no domain effect) = 0.46 at P = 1; 0.29 at P = 2; 0.14 at P = 4. A true 3 % effect is detected with probability 0.68 at P = 1.
- It tests only the outlet (1.95 m = 3.7 projected widths, 1.6 chords; extended 5.5 w). The 10 % lateral/top blockage (frontal area 0.4375 m^2 in 2.4 x 1.8 m; `docs/evidence/v18_genesis_2026_10_19/README.md:21`; slip walls at 0.76 m from each tip and 0.65 m above the plate) is untouched, and the quantity of interest is the design delta, not the parent force.
- Different dims change the multigrid hierarchy (the GRIDRES-01 lesson); +40 cells at flow_32 (240 = 16 x 15) happens to be no worse (6 levels, coarsest 17x5x11 by my count), but the plan does not check it.

Fix
- Control on the finalist delta (finalist minus parent, same phase) at flow_32 with P = 4 at the Stage 0 window, with an equivalence margin tied to the pooled SE, in R2 as well as R3; report a lateral/top extension as a second control or state blockage as uncontrolled.

### N12 (P2) The Poisson probe is insensitive to the failure mode the repository already found

Evidence
- plan:140 reports only if more than 10 % of steps hit the 32-iteration cap.
- GRIDRES-01 (`docs/issues/gridres01_result_2026_10_21.md`, "Correction"): cap-hit fractions were 0.015 %, 0.17 % and at most 0.24 % on flow_32, flow_24 and flow_40, while the final residual p50 on flow_40 was about 20 times flow_32's (maximum 0.076-0.081 versus 3.9e-5), and flow_40 was concluded to be Poisson-confounded. The 10 % threshold is about 40x above anything seen, and the stated lesson is "the cap-hit fraction is not a sufficient confound test".
- The convergence criterion is `L2(p) = p.r . p.r < 1e-4`, an absolute sum of squares over all cells (`Poisson.jl:189`, `MultiLevelPoisson.jl:108-127`), so the per-cell RMS tolerance shrinks with grid size (8.5e-6 at flow_32, 3.0e-6 at flow_64). Residual level, not cap hits, is the comparable quantity across grids.
- `UNRESOLVED_NUM` appears only in plan:140 (N2); the SCREEN-01 jobs record no Poisson data (no key in `flow_*.summary.json`), so the probe is new instrumentation.

Fix
- Record final residual p50/p95/max and iteration counts per grid at every sample; compare grids by residual level (a ratio gate, e.g. flow_48 and flow_64 p50 within 3x of flow_32) plus the cap fraction; add a tight-tolerance control (tol 1e-5 or itmx 64) on parent and finalist at flow_32 at R3.

### N13 (P2) OpenFOAM leg: numerics, iteration count, cost, and the band

Evidence
- The registered case template uses `div(phi,U) bounded Gauss upwind` (`infra/kaggle/kernel_openfoam_xfid_v16_jammy_round5/case_template/system/fvSchemes:14`) and snappy surface levels (2 3) on a 0.2 m background (V1 surface cells 0.05-0.025 m; V2 and V3 halve and quarter that). First-order upwind adds a numerical viscosity of order U dx / 2 (times a direction factor of about 0.3-1 for a plate at 20 degrees to the grid). Order-of-magnitude (not measured) numerical-to-molecular viscosity ratio at Re 250: 1.3-7.8 (V1), 0.6-3.9 (V2), 0.3-2.0 (V3); at Re 800: 4-25, 2-12.5, 1-6. The OpenFOAM response to Re is therefore damped between 80 and 250 (effective viscosity falls by roughly 20-50 % instead of 68 %), and "ν changed only" (fable:235) does not give an Re-250 solution on V1/V2.
- Convergence: iterations at Re 80 are 572 (V1, 39,706 cells; `docs/evidence/fid01_2026_10_21/of/smoke/output/smoke_v1/.../result.json`), 1,562 (V2) and about 4,550 (V3) (`of_levels.json`), growing roughly like N^0.6; `endTime 3000` (`case_template/system/controlDict:24`), relaxation U 0.5 / p 0.2. If the iteration count to the residual criterion (p 1e-5, U 1e-6) grows 2-3x from Re 80 to 250, V2 (3,100-4,700 iterations) would exceed endTime and be an invalid case under the registered rule. Stage 0 tests only a V1 parent at one shift (plan:168); a V2 parent and more than one shift are needed.
- CPU cost: plan:155 lists R2 CPU 40 h. Fable:140 gives 21 CPU h per pimpleFoam case (`re_ladder.py:39`: 0.213e6 cells x 40,000 steps x 6 us x 1.5 = 77 ks) and "6.7 h at 4 cores"; six cases are 128 CPU h, not 40 (40 is wall hours with 4 cores per case, which also contradicts the serial, deterministic local gate that the registration relies on). R1 50-65 plus R2 128 is 178-193 CPU h against the cap of 100 (plan:144). A first-order-upwind V2 pimpleFoam at Re_L 800 (viscosity ratio 2-12) would not shed in any case.
- Retention band: [0.3, 3.0] (plan:114) is a factor 10 wide against the Re-80 retention of 0.57-0.77 (FID-01 V1). It cannot fail on anything but gross error. The finalist lies in the camber extension where FID-01 has no fidelity evidence (screen01 README, "Two limits from the handoff"); XV-01 decides that at Re 80. An absolute band at R1 conflates that with Re dependence.

Fix
- Compare the R1 OpenFOAM retention to the XV-01 Re-80 retention of the same design: rho(250) / rho(80) in a band set from XV-01's own interval (for example [0.67, 1.5]). Add one V2 parent and finalist case at Re 250 with `linearUpwind grad(U)` as a scheme-sensitivity probe in Stage 0, and decide whether OpenFOAM at R1 is a retention check or only a sign check. Drop pimpleFoam at R2 or cost it at 128 CPU h and test a second-order scheme first. Recompute the CPU cap with the measured V1/V2 iteration counts.

### N14 (P2) The Re-80 baseline: the same-phase 12-state anchor is not needed; a regression anchor is

Evidence (plan:92-93, open question)
- Re-80 estimates come from phases 13-16 (finalist, M; SCREEN-01) and 7-10 (tier A; FID-01). The Re-80 SE_eff is 1-3e-4 N (SCREEN-01 2.92e-4, FID-01 1.0-1.8e-4 N); at a chaotic rung SE_eff is about 3.6e-3 N (12-36x larger), so a different phase set at Re 80 adds at most 8 % to the rung noise and 1-4 % to a retention of a 7e-3 to 3e-2 N delta even at a steady R1. It is far inside the sign and band gates. The 12-state anchor (about 6 GPU h) is not worth it.
- What is missing: the case validator asserts `REYNOLDS = 80` and n/80 (`src/cfd_sdf/grid02_contract.py`, `solver_viscosity: n / REYNOLDS`), so RE-01 needs a new, Re-parameterised source. Nothing in the plan checks that it reproduces the old bytes at Re 80.

Fix
- Replace the anchor by one run: the new job at Re 80, parent, phase 13, flow_32, compared byte for byte with the stored SCREEN-01 f32a parent k13 force CSV (about 0.12 GPU h; the repository has shown cross-session bit identity, `determinism ... max_abs_diff 0.0`). That validates the new contract; a failure blocks registration. In the retention formula keep the Re-80 deltas in newtons (see N19).

### N15 (P2) The rung placement: R1 to R2 straddles the regime switch; R3 is costly and least decidable

Evidence
- The Re-80 steady regime has strong CRN (sigma_d about 0.1-0.3 of the independent value); chaos has none. The first Hopf/3D onset quoted by Fable is Re_w 160-234 (fable:67, with Re_w defined by c sin(alpha), N21), i.e. Re_L about 300-440. R1 (250) is below and R2 (800) is well above, so a break or an UNRESOLVED at R2 cannot be assigned to physics versus loss of CRN versus leading-edge resolution (N10). My 2D probe is periodic at Re_L 250 (rms 17 %) and steady at 80, so the switch may be near R1 even in 3D if the AR 0.72 stabilisation is weaker than assumed; Stage 0 tests it.
- R3 (Re_L 2500) is the most expensive rung (up to 71 GPU h), the least resolvable (N1), has the thinnest leading-edge boundary layer (0.17-0.26 cells), is the only rung with the domain control, and is the one the plan expects to be "weakened or unresolved" (fable:79, H3 "exploratory, not a pass condition", yet plan:121 makes it a PASS condition of RE_PERSISTS).

Fix
- Insert a rung near Re_L 450 (Re_c about 690; periodic window cheap to average) and make Re_L 2500 a descriptive rung on flow_32/48 with a smaller budget and no vote in RE_PERSISTS (consistent with Fable's own H3), or drop it. If R3 stays in RE_PERSISTS, state its minimum detectable retention (N1).

---

## P3 findings

- **N16 Allocation.** Every delta shares the same-phase parent run, so the parent's noise is common mode. For 11 designs the efficient parent window is about sqrt(11) = 3.3x a design window, which cuts Var(delta) by about 35 % for about 19 % more cost. The parent repeat (a bit-identity control, plan:135) adds nothing in a chaotic rung if it is bit identical (one exact copy) and costs 1/12 of flow_32; run it at Stage 0/R1 only, and say what happens if a chaotic repeat is not bit identical (plan:135 is silent).
- **N17 Kendall tau.** `calc/power.py`: tau >= 0.6 passes 0.986 at r = 1.0 and 0.81 at r = 0.5 with SE_T 1.9 % (design noise only; a common-mode parent offset is rank neutral); P(tau < 0.3) = 0.005. It protects against nothing the sign rule does not, and is mostly the sign clusters plus the single large C4 delta. The slope of N1 is the better single number. The permutation p-value (plan:104) adds nothing at n = 10 with two sign clusters.
- **N18 Drift rule at R1.** The UNC-01 half-window drift threshold 0.002 relative is 5.3e-4 N of a 0.266 N force; observed Re-80 drifts are 6.6e-9 to 3.9e-5 (not "1e-8 to 2.5e-5", fable:59). At a steady R1 with SE_eff 1-3e-4 N, a run could pass the rule with a residual drift of 2-5 SE_eff; near criticality the relaxation slows. Tighten to about 1e-4 for the steady regime or test drift against the rung's SE_eff.
- **N19 Units of retention and of the target.** The SE target is in percent of the parent force, which changes with Re (C_L 0.50 at Re 80); Delta(Re) / Delta(80) is in newtons (the reported "retention curve"). State which; the finalist's 1.077e-2 N is not 4.05 % of a different parent.
- **N20 Label and text inventory.** `UNRESOLVED_NUM` missing from the 3.5 label list; "800 CU cap" does not say whether burn-in is included (fable says window plus 80); section 0 says R1 is 7 GPU h and 40-50 CPU h (plan:14), section 3.8 says 9/15 and 50-65 (plan:153; the former is Fable's 9-state number); the drag SE target is not stated; the repeated Re-80 sign convention of "reflex +16.1 mm" is flagged unverified in fable:252 and should be checked before a table mixes designs.
- **N21 Re_w definition.** Fable defines w = c sin(alpha) + t cos(alpha) = 0.533 m (fable:57), which gives Re_w = 53 at Re_L 80 and 167 / 533 / 1,665 at R1-R3, but quotes Re_w 42 / 133 / 425 / 1,328 (computed with c sin(alpha), `re_ladder.py:29`). With the thickness-inclusive width R1 (Re_w 167) is inside the quoted 3D-onset band (159.7-234.2). The literature value's definition has to be checked before R1 is called "probably steady".
- **N22 Citations.** The Fable `Flow.jl` citation is version 1.6.1 (N7); fable's phase list "k = 17-20" includes 20, which SCREEN-01 used (the plan already corrects this); the Kaggle 30 GPU h/week quota is treated as operative in the registrations (`docs/screen01_registration_2026_10_30.md:90`), so "not official" (plan:225) does not change the plan.
- **N23 Geometry.** flow_48/64/96 sample the 0.025 m design lattice by interpolation; they refine the flow, not the shape. A flow_64 versus flow_32 difference at the leading edge is therefore a flow-resolution difference only; say so when R2/R3 results are read.

---

## Checked against the repository and found correct

| Item | Source | Status |
| --- | --- | --- |
| flow_32 steps 13,464-13,651, walls 344-368 s, flow_48 26,360-27,310 steps and 2,382-2,655 s, 5.1-5.4e7 cell-steps/s | 22 + 6 `flow_*.summary.json`, `cost.py` | OK |
| dt rule `1/(max flux + 5 nu)`, nu = n/Re, Float32 | `Flow.jl:234-237` (1.8.0), `waterlily_grid02_job.jl:335` | OK (formula); citation is 1.6.1 |
| dims 200x96x72 / 300x144x108, dx = 0.8/n, nu = n/80 | `grid02_contract.py` | OK |
| Domain 5 x 2.4 x 1.8 m, ground at z = -0.9, outlet 1.95 m (1.6 chords) behind the trailing edge, blockage 10.1 % | `v18_genesis_2026_10_19/README.md`, `summary.json` flow_origin and box | OK |
| Stadium section t = 0.1153, radius 2.3 / 3.5 / 4.6 cells, thickness 4.6 / 6.9 / 9.2 cells | genesis README | OK |
| Finalist +1.077e-2 N (4.05 %), drag -1.99e-3 N; flow_48 4.46e-4 N SE; floor 2.09e-4 N; sigma_d 2.1-5.5e-4 N; retention 0.57-0.77; tier A 8 designs, 5 positive; tau 0.848 | SCREEN-01 README, UNC-01 and FID-01 analyses | OK |
| Memory 128 B/cell (paper) vs measured 131-135 B/cell | `peak_vram_bytes` in summaries | OK (measured, see N8) |
| flow_64 / flow_96 multigrid hierarchy | my count with the 1.8.0 semi-coarsening rule, matching the repository's 4/6/4/5 for 24/32/40/48 | flow_64: 7 levels (deeper than flow_32); flow_96: 6, same coarsest level as flow_48 |
| Re_c 381 / 1,219 / 3,810, laminar leading-edge boundary layer 7.6 mm at Re_L 800 | arithmetic | OK |

## Method notes for reproduction (all in the scratchpad)

- `calc/power.py`: Monte Carlo of the plan's PASS conditions, 40,000 draws per cell; design deltas (percent of 0.265779 N): finalist 4.05, M 2.90, camber -11.3 2.70, C1 4.99, camber -19.7 4.89, camber +19.7 -3.83, pitch -0.7 -3.37, C4 -12.06, pitch +0.7 3.99, reflex -29.3 5.89. Noise model: design mean SE = SE_T / sqrt(P), shared parent mean SE the same, sigma_d estimated from P - 1 = 3 chi-square dof.
- `calc/slope.py`: through-origin slope with 9-dof t-interval, same noise model.
- `calc/gate.py`, `calc/grid_gate.py`, `calc/cost.py`: A/B ratio false-fail rates, flow_32 vs flow_48 sign confirmation, domain control, GPU hours.
- `wlenv/cfl2d.jl` (+ `cfl2d_long.jl`): 2D inclined plate, WaterLily 1.8.0 CPU Float32, slip bottom (not a moving-ground no-slip body, no spanwise extent). The max flux ratios and the SE-versus-window behaviour are proxies for Stage 0, not a prediction for 3D.
