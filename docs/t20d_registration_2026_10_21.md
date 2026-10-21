# T2-0d registered study (#57): time-averaged URANS and steady-solver controls where steady SA-WF RANS does not settle, the G2 peak on fine30/xfine30, and small differences at the downforce peak

Registration status (PROC-01): `DRAFT` -> `DRAFT_FROZEN_PLAN` at freeze 1 (SHA-256 of this file posted on #57) -> **`REGISTERED_FROZEN`** at freeze 2
(source commit and hashes of the kernel template, builder, analyzer, stage module and pinned generators posted on #57 and in
`docs/evidence/t20d_registered_2026_10_21/freeze.json`). Evidence class of the result: descriptive numerical evidence for one 2D section.
All qualification flags stay false; `shape_update_allowed=false`. **This text governs; a disagreement between it and the frozen analyzer is a defect of the analyzer.**
This is the **last registered T2-0 study** (cap of `docs/t20c_registration_2026_10_20.md` section 1); a T2-0 summary for M4 (#66) follows it.

## 1. Question, origin and scope

T2-0c (`T20C_MORPH_NO_GO`, `docs/evidence/t20c_registered_2026_10_20/`) ended in its next-action row 5: the steady SA wall-function RANS (simpleFoam, SIMPLEC,
relaxation 0.9) does not settle on xfine30 at h/c 0.09 (no Cl plateau after 15000 iterations, raw tail Cl std 2.7-5.4 %) and at h/c 0.134 for incidence >= 0
(raw std 0.7-2.0 %), nor on fine30 at h/c 0.09, +1 deg (1.9 %); row 5 asks for "an unsteady/solver-convergence study there; no mesh-dependence or morph conclusion".
Neither the G2 peak label nor the G2-by-level rule on fine30/xfine30 could be computed (UNSTEADY/SOLVER_FAIL inputs). Questions:

- **Q1 (registered labels).** Is the non-settling at those (mesh, h, alpha) an unsteadiness of the model's time-dependent solution (2D URANS with the same SA-WF
  model, schemes and mesh sustains a stationary oscillation, e.g. from separation or shedding), or a convergence failure of the steady solver (a time-accurate
  solution settles, and a conservatively relaxed steady solver converges to it)? Decided per condition by a URANS run (pimpleFoam, time averaged), a time-step
  control, a relaxed steady control and, at two conditions, a dt/2 run and a second start state (section 6.2). "Physical" is claimed only at the model level:
  a sustained URANS oscillation of this 2D SA model is not shown to exist in the real flow.
- **Q2 (sub-verdict DATA).** With the time-averaged Cl, does the T2-0b G2 rule (level, incidence ambiguity, peak at h/c 0.134, unimodal rise; peak and rise read
  with a realisation-noise band) pass on fine30 **and** on xfine30? This feeds the decision whether T2-0b's G2 action (a wall-resolved/LM evaluator study or
  another validation case) still stands (label `G2_ACTION`, section 7).
- **Q3 (sub-verdict DIFF).** At the downforce peak (h/c 0.134), on xfine30 (the level at which the steady solver fails there), are small differences (+-0.25 deg
  incidence, camber and flap +-0.25 mm) resolved above the time-averaging, morph and base-realisation noise, consistent between time steps, between fine30 and
  xfine30 and between two base mesh realisations; and what does one such evaluation cost against R5's budget?

Out of scope (decided here): LM and any wall-resolved mesh (whether T2-0b's G2 action stands is an output, not run here); adjoint; turbulence models other than
SA; scheme or wall-function variants (they change the discrete solution or the model, not its convergence: the URANS keeps the steady case's spatial schemes and
wall function, so the S1 control isolates the steady solver's relaxation); 3D, span, end plates; differences at h/c 0.09 (separated, beyond the peak; 0.09 enters
Q1 and G2). Trigger: T2-0c row 5 and the 2026-10-16 parallel-track decision (T2-0 is the M3a NO-GO branch target). Cap: the last registered T2-0 study.

## 2. What was visible before this registration (and how it is used)

- **All T2-0a, T2-0b and T2-0c results**, including T2-0c's per-case records (its analysis was written once before this text). Read for design: the T2-0c
  unsteady cases oscillate in pseudo-time with a period of 12-17 SIMPLE iterations (raw Cl ranges up to +-7 %); the T2-0c steady VALID cases have raw tail
  relative std 1e-5 to 5e-4 (a period-2 alternation of the SIMPLEC wall-function runs), all below 1e-3; no T2-0c case met its residual controls; the T2-0c morph
  scans at h/c 0.134 (fine30 cubic residuals up to 0.0023; xfine30 jump of 0.045 in Cl between -0.25 deg (steady) and 0 deg (unsteady pseudo-mean)); the T2-0c
  0-deg sweep values; the base-realisation spread at 0.134 (B vs B' 26-29 % of the derivative on med30/fine30); the T2-0c remeshing sigmas; the T2-0c costs per
  SIMPLE iteration (xfine30 0.25 s Intel Xeon / 0.16 s AMD EPYC, fine30 0.13 / 0.07 s, 4 concurrent cases); the digitised curve's own peak margin
  (1.3854 at 0.134 against 1.3701 at 0.09 and 1.3614 at 0.179: 0.022 above the 0.5 % band).
- **Thresholds.** The consistency tolerance (0.25), delta floor (0.01 per deg), power requirement (0.5), resolution factor (5 sqrt(2)), sigma_eff (cubic fit with a
  floor), the G2 rule (5 %, +0.15 deg shift, 0.5 % peak tolerance, unimodal rise), G2d (0.30), the ROBUST band (+-0.005), G3a (5 %) and the cost bounds (15/30 min)
  are T2-0b's or T2-0c's, **applied after their numbers were visible**. New and chosen knowing them (no out-of-sample check of any of them): theta = 1e-3 (above
  every T2-0c steady VALID case, below every T2-0c UNSTEADY case), the drift, amplitude and cycle rules, the Hann-weighted mean and its bias bound, the time-step
  tolerances, the agreement tolerance 5e-3, the S1 settings, the transient and window lengths, the realisation-noise band of the peak, the verdict structure.
  `verdict.json` carries `thresholds_set_after_exploratory_visible`, `thresholds_set_after_t20b_visible` and `thresholds_set_after_t20c_visible` (all true).
- **Pre-determined if the URANS reproduces the steady solution where S0 converges (the Q1 controls test this; disclosed):** on xfine30 the G2 inputs at h/c
  0.671-0.179 and at 0.224 +-1 deg and the negative incidences at 0.134; on fine30 every G2 input except 0.09 +1 deg (T2-0b fine30 sweep: mean |e| 2.90 %, peak at
  0.134), the 0.134 morph scans (T2-0c fine30 G6m UNRESOLVED, G8m 0.063 vs 0.086 per deg: hence fine30 is not the Q3 verdict level) and the 0.179 steady scans in
  part. **New:** every URANS, time-step, dt/2, second-start and relaxed-steady value; every xfine30 input at 0.134 for incidence >= 0 and at 0.09; every Q3 input.
- **Local force-free timing pilot (2026-10-21; scripts and logs in `docs/evidence/t20d_registered_2026_10_21/prefreeze_pilot/`):** one xfine30 h/c 0.09, 0-deg
  mesh generated locally (49,725 cells), 400 SIMPLEC iterations with no force function object, then pimpleFoam (PIMPLE, 2 outer correctors), 1 CPU in the local
  Docker image: an adaptive step at Courant number 1 settles at 2.45e-6 s (the sharp-TE fan cells set the maximum Courant number); fixed 1e-5 s gives a maximum
  Courant number of 4.1 and 2e-5 s 8.2, both stable for 100 steps (1-2 ms); 0.81 and 0.74 s per step against 0.285 s per SIMPLE iteration on the same host. Read:
  step counts, Courant numbers, time steps, timing, the last pressure and velocity residual lines and the continuity line. No force, coefficient or field
  statistic was computed or read. The pilot sets the time step and the cost estimate only.
- **No T2-0d solver output exists at registration.** The development smoke (section 8) removes every force-derived value.
- **Predictions at registration** (in `verdict.json` as `predicted`): Q1: xfine30 h/c 0.09 `UNSTEADY_IN_URANS` (large pseudo-time amplitude), xfine30 0.134 and
  fine30 0.09 +1 deg uncertain; controls OK. DATA: G2u(fine30) pass or noise-indeterminate at the peak; G2u(xfine30) uncertain (the T2-0c pseudo-means put Cl(0.09)
  above Cl(0.134)). DIFF: GT134 pass; G6u, G3bu uncertain; **G8u fail** (the T2-0c prior: 26-29 % between base realisations at 0.134); GSu pass. Cost: **above
  R5** (near certain: about 1.5-2.6 h per xfine30 evaluation). Verdict: `T20D_NO_GO` with DIFF = FAIL_VALUE most likely; `T20D_QUALIFIED_UNAFFORDABLE` possible;
  `T20D_QUALIFIED_XFINE30_PEAK` not expected.
- **Data reuse.** No T2-0a/b/c output file is read by the analyzer. Every gate and label input is a T2-0d run.

## 3. Case and evaluator protocol

Geometry, meshes and the steady case are T2-0c's, generated by the pinned files unchanged: `scripts/t20_case.py`, `scripts/t20_foam.py` (T2-0a/b),
`scripts/t20c_case.py` (xfine30, the incidence/shape morph and the remeshed cases), Tyrrell026S, chord 0.2234 m, U 30 m/s, Re_c 4.6e5, moving ground,
Tu 0.3 %, domain 2c upstream / 5c downstream / 6.8c above the ground, SA with `nutUSpaldingWallFunction`, levels fine30 (2 mm surface spacing, four layers from a
0.6 mm first layer) and xfine30 (1 mm, two layers). Incidence = rotation about the LE (LE toward the ground positive), h re-imposed; morphs are T2-0c section 4
(smoothstep blend, asserted per morph: no inverted cell, fixed nodes unmoved, airfoil nodes with weight 1, contour within 1e-9 m, polyMesh topology hashes equal to
the base's). Cl = downforce coefficient. T_c = c/U = 7.4467e-3 s. A new module `scripts/t20d_case.py` writes the stage-2 dictionaries and copies a solved
case into a stage-2 case; it does not modify the pinned files.

Every geometry runs **S0**; most then run one or more **stage-2 runs**, each in its own copy of the source case (same mesh file, the source's final fields; no
mapping or interpolation):
- **S0 (steady, T2-0c's evaluator):** the generator's case unchanged: simpleFoam, SIMPLEC (`consistent yes`), relaxation 0.9 on U and nuTilda, bounded steady
  schemes, 5000 iterations from the generator's uniform initial fields; **no continuation**. Its latest time directory is the start of every stage-2 run.
- **U (time-averaged URANS, the evaluator under test):** pimpleFoam from the source's latest U, p, nuTilda, nut and phi moved to time 0 (no `uniform/`
  information); the same spatial schemes with `bounded` removed (`div(phi,U) Gauss linearUpwind grad(U)`, `div(phi,nuTilda) Gauss upwind`, gradients,
  laplacians and wall distance unchanged), `ddt backward` (its first step is Euler); PIMPLE with `momentumPredictor yes`, 2 outer correctors, 2 pressure
  correctors, 1 non-orthogonal corrector, no under-relaxation (turbulence solved on the final outer corrector); p GAMG (tolerance 1e-7, relTol 0.01; final 0), U
  and nuTilda smoothSolver (1e-8, relTol 0.1; final 0); `adjustTimeStep no`, **dt = 1e-5 s** (T_c/745; pilot maximum Courant number about 4 in the sharp-TE fan
  cells, mean far below 1); **end time 0.1192 s** (16.0 T_c, 11,920 steps); forceCoeffs (S0's function objects) every step; fields written only at the end.
  **Transient** t <= 0.0447 s (6.0 T_c: about one flush of the 5c wake region, discarded); **window** 0.0447 < t <= 0.1192 s (10.0 T_c, 7,450 rows).
- **Udt2 (time-step control):** as U with dt = 2e-5 s (pilot maximum Courant number about 8), same transient and window (3,725 rows).
- **Udt05 (dt/2 control, two conditions):** as U with dt = 5e-6 s to end time 0.0819 s (11.0 T_c); window 0.0447 < t <= 0.0819 s (5.0 T_c), compared with U over
  the same interval (U's sub-window).
- **S1 (relaxed steady control):** simpleFoam from S0's latest state to iteration 15000: SIMPLE (`consistent no`), relaxation p 0.3, U 0.7, nuTilda 0.7, the S0
  schemes and residual controls (no T2-0c case ever met them; an early stop is read from the log). Its statistics use only its own rows.
- **US1 (second start state, two conditions):** a U run whose source is the S1 run's final state instead of S0's (runs after its S1).

A unit test asserts the copy (mesh and source fields byte-identical, the source's `postProcessing/` and `uniform/` not copied) and the dictionary text.

## 4. Statistics of a run (computed by the frozen analyzer from the run's `coefficient.dat`)

Rows are selected by time with a half-step guard on both ends: the window is t_a + dt/2 < t <= t_b + dt/2; a U, Udt2 or Udt05 history whose last time is below
t_end - dt/2 is incomplete. For a window of n rows and length T_w:
- raw mean and std, r = std / |mean|; quarters Q1..Q4 and halves H1, H2 of the window by row count, with their std s_Q, s_H.
- **Hann-weighted mean** m_H = sum(w Cl) / sum(w), w = 0.5 - 0.5 cos(2 pi j / n), j = 0..n-1.
- **dominant frequency** f*: peak of the periodogram of the Hann-weighted, 8x zero-padded Cl - mean, refined by a parabola through the log power of the peak bin
  and its neighbours; cycles k* = f* T_w; St_c = f* c / U.
- **batch-means SE**: SE10 and SE5 = std of the 10 (5) equal batch means (leading remainder rows dropped), ddof 1, / sqrt(10) (sqrt(5)); lag-1 autocorrelation of the
  10 batch means (label).
- **drift**: least-squares slope of the 10 batch means against their centre times, Delta = |slope| T_w, and its standard error SE_Delta (8 dof) x T_w.

**Classes of a U, Udt2, Udt05 or US1 run** (in this order):
- `VALID_SETTLED`: over H2, r_H2 < theta = 1e-3, H2 drift (least-squares slope of Cl over H2's rows x T_w/2) <= 5e-4 |mean_H2|, and no growth (s_Q4 <= 1.5 s_Q3,
  or s_Q4 < 1e-4 |mean_H2|).
  Its Cl m = mean over H2; its noise SE_run = max(SE5 over H2, 1e-6 |m|).
- `VALID_PERIODIC`: not settled; drift Delta <= max(3 SE_Delta, 5e-4 |m_H|) and Delta <= 2e-3 |m_H|; amplitude stability 0.8 <= s_H2 / s_H1 <= 1.25; k* >= 3.
  Its Cl m = m_H; SE_run = max(1.22 SE10, 1.22 SE5, b_H) with the Hann bias bound b_H = sqrt(2) std / (pi k* (k*^2 - 1)) (1.22 = sqrt(1.5), the Hann variance
  factor). `LOW_FREQ_PERIODIC` (label) if 3 <= k* < 5.
- `TOO_FEW_CYCLES` (k* < 3, otherwise as VALID_PERIODIC) and `NONSTATIONARY` (otherwise): invalid inputs.
For S0 and S1: T2-0b's plateau (20-iteration block means over the last 20 % of the run, relative std and drift < 0.5 %) and the raw tail relative std r_tail (last
20 %); **CONVERGED** = plateau and r_tail < theta; its Cl = the tail mean (T2-0b).

## 5. Kernels, cases, backend and cost

Ids (T2-0c): remeshed `sa-wf_h{h}_{mesh}_da{a}`; morph from the kernel's 0-deg base `..._morph-da{a}`, `..._morph-{camber|flap}{a}mm`; morph from a second base
B' (generator at +0.5 deg, not solved) `..._morphB2-da{a}`; run ids append `__S0`, `__U`, `__Udt2`, `__Udt05`, `__S1`, `__US1`. A6 = {-1, -0.5, -0.25, +0.25,
+0.5, +1} deg, A7 = A6 and 0. **Q1 conditions** (x = xfine30, f = fine30): targets x09-1, x09 0, x09+1 (remeshed), x134 0 (base B), x134+1 (morph from B),
f09+1 (remeshed); controls x224 0, x134-1 (morph from B), f09 0.

| kernel | slug | geometries (S0 for all; U for all except the S0-only scans) | further stage-2 runs | Intel / AMD estimate |
| --- | --- | --- | --- | --- |
| XP1 | `cfd-opt-sdf-t20d-xp1` | xfine30 h/c 0.134: base B (0 deg) and the six A6 morphs from it (7) | Udt2 at B, +1, -1; Udt05 at B; S1 at B, +1, -1; US1 at B | 30 core-h, 8.4 / 5.3 h |
| XP2 | `cfd-opt-sdf-t20d-xp2` | xfine30 h/c 0.134: B' (+0.5 deg, not solved) -> -1, -0.25, +0.25, +1 deg; own 0-deg base B2 (not solved) -> camber, flap +-0.25 mm (8) | none | 22 core-h, 6.2 / 4.0 h |
| XO1 | `cfd-opt-sdf-t20d-xo1` | xfine30: 0 and +-1 deg (remeshed) at h/c 0.224 and 0.09 (6) | Udt2 at 0.224 0, 0.09 -1, 0, +1; S1 at the same four; Udt05 and US1 at 0.09 0 | 29 core-h, 8.3 / 5.3 h |
| XO2 | `cfd-opt-sdf-t20d-xo2` | xfine30: 0 deg at 0.671, 0.448, 0.313; 0.179 0 deg as a base and the six A6 morphs from it (**S0 only**); +-1 deg (remeshed) at 0.134 (6 U + 6 S0-only) | none | 18 core-h, 6.1 / 3.9 h |
| F1 | `cfd-opt-sdf-t20d-f1` | fine30: 0 deg at the 7 heights (0.179 as a base: the six A6 morphs from it **S0 only**); +-1 deg (remeshed) at 0.224, 0.134, 0.09 (13 U + 6 S0-only) | Udt2 at 0.09 +1; S1 at 0.09 0, +1 | 20 core-h, 6.0 / 3.8 h |
| F2 | `cfd-opt-sdf-t20d-f2` | fine30 h/c 0.134: base B_f (0 deg) and the six A6 morphs; B'_f (+0.5 deg, not solved) -> -1, -0.25, +0.25, +1 deg (11) | none | 15 core-h, 4.4 / 2.8 h |

Per kernel: environment, pinned source, gmsh, hash-locked OpenFOAM v2512 (T2-0c's install), the infrastructure smoke (sa-wf coa30 h/c 0.224, 200 iterations, as
T2-0c), bases generated once, **phase 1** = every S0 (4 concurrent), **phase 2** = every stage-2 run (4 concurrent; S1 runs that feed a US1 first, then longest
first; a US1 starts when its S1 has finished). Kernel budget 11 h, per-run solver cap 5.5 h. Outputs leave as one tar (T2-0c). Totals: 51 U, 8 Udt2, 2 Udt05,
9 S1, 2 US1, 63 S0 (12 S0-only), about 134 core-h (Intel). Unit costs (from the T2-0c per-iteration costs and the pilot's PIMPLE/SIMPLE step ratio 2.84 at dt,
2.6 at 2 dt), Intel / AMD per run: xfine30 S0 0.35 / 0.22 h, U and US1 2.35 / 1.5 h, Udt2 1.1 / 0.7 h, Udt05 3.4 / 2.2 h, S1 0.7 / 0.44 h; fine30 half.

**Backend: Kaggle CPU for every stage (option (a)).** The user's 2026-10-20 decision moved OpenFOAM to the local Docker environment behind the LOCAL-OF-01 gate; that
gate failed for this pipeline (`LOCAL_ENV_FAIL`: gmsh meshes of rotated or displaced geometries differ between the local image and Kaggle in 86 of 262 geometries),
so T2-0d stays on Kaggle CPU, as T2-0c did. Option (b) (meshes generated once, hashed and shipped as inputs, solver-only locally) would need its own mesh-shipping
path and a new environment-gate round before any registered run, with no evidence to gain. Within one kernel every paired comparison shares its mesh (stage-2 runs
copy their source case; a morph scan and its base are in one kernel; each geometry is meshed once per kernel), so gmsh's run-to-run numbering variants cannot
enter a paired comparison; comparisons across kernels (B vs B', fine30 vs xfine30, heights, the realisation pairs) are between different meshes by design, and
their CPU models are recorded (`CPU_MIXED` label per gate). Contingent, not decisive: the local machine (10 cores: 4 performance + 6 efficiency, 32 GB, OpenFOAM
under Rosetta) was at load average 48-102 with 8.9-11.7 GB of 10-12 GB swap in use during the pilot and is shared with the M3a FID-01 session's local OpenFOAM
runs; the ~134 core-h would take about 19 h on 8 local cores. Kaggle CPU sessions are shared with other sessions' kernels (M3a uses T4 GPU sessions); a
concurrency limit is waited out, never worked around.

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20d.py`)

### 6.1 Run classes and gate outcomes
- `MECHANICAL_FAIL`: generator, morph assertion, topology, checkMesh or stage-2 preparation failure (T2-0c's statuses and `STAGE2_PREP_FAILED`).
- `INFRA_LOSS`: no record, `NOT_RUN_TIME_BUDGET`, `RUNNER_EXCEPTION`, `DEADLINE_LIMITED`, kernel killed, and a run stopped at the per-run cap without NaN or a
  solver failure (`TIME_LIMITED`).
- `SOLVER_FAIL`: the source run failed (S0 crash or NaN; an unconverged S0 is not a failure), or the run crashed, produced NaN or |Cl| > 100, or its history is
  incomplete for any other reason.
- U-type runs: `VALID_SETTLED`, `VALID_PERIODIC`, `TOO_FEW_CYCLES`, `NONSTATIONARY` (section 4). S0/S1: `CONVERGED`, `NOT_CONVERGED`.
A gate input must be VALID_SETTLED or VALID_PERIODIC. Each gate has exactly one outcome: `PASS`; `FAIL_VALUE` (every input valid and the rule fails on values;
UNRESOLVED comparisons are value failures, named `noise`); `FAIL_INPUT` (an input is SOLVER_FAIL, NONSTATIONARY or TOO_FEW_CYCLES; the classes are named);
`MECHANICAL` (an input is MECHANICAL_FAIL); `UNDETERMINED` (an input is INFRA_LOSS and no input fails); `INDETERMINATE_NOISE` (G2u only, section 6.3). A
time-step gate failing on values is named `FAIL_TIMESTEP`. Any undefined quantity is FAIL_VALUE.

### 6.2 Q1 classification (registered labels, per Q1 condition)
Agreement tolerance tol_eq = 5e-3 |m_U| (the steady limits of SIMPLEC 0.9, SIMPLE 0.7 and PIMPLE differ by their Rhie-Chow/ddtCorr terms; the observed
offsets are reported as `FORMULATION_OFFSET` at every S0/S1/U pair). Time-step check at a condition = the GT rule (section 6.3) between U and Udt2.
- `STEADY_SOLVER_ARTEFACT`: U VALID_SETTLED, the time-step check passes, S1 CONVERGED and |Cl_S1 - m_U| <= tol_eq (a time-accurate solution settles and a relaxed
  steady solver reaches it: the T2-0c oscillation was the SIMPLEC-0.9 iteration's).
- `STEADY_URANS_ONLY`: as above but S1 NOT_CONVERGED.
- `STEADY_BRANCH_MISMATCH`: U VALID_SETTLED, time-step check passes, S1 CONVERGED but beyond tol_eq.
- `UNSTEADY_IN_URANS`: U VALID_PERIODIC and the time-step check passes (a sustained, stationary oscillation of the model's time-dependent solution; St_c, r and m
  reported).
- `START_DEPENDENT`: at x134 0 and x09 0, U and US1 differ in class, or in m beyond max(tol_eq, 3 sqrt(SE_U^2 + SE_US1^2)), or (periodic) in r beyond the ratio
  band [0.8, 1.25]; overrides the classes above.
- `INDETERMINATE`: otherwise (an invalid U, Udt2 or S1; a failed time-step check).
Controls: `CONTROL_OK` iff U VALID_SETTLED, S0 and S1 CONVERGED and both within tol_eq of m_U.
`Q1_FORM_134` (targets x134 0, x134+1, controls x134-1, x224 0) and `Q1_FORM_09` (targets x09-1, 0, +1, f09+1, controls x224 0, f09 0): `INDETERMINATE` if a control
is not OK or a target is INDETERMINATE or START_DEPENDENT; else `URANS_REQUIRED` if a target is UNSTEADY_IN_URANS, STEADY_URANS_ONLY or STEADY_BRANCH_MISMATCH;
else `STEADY_RELAXED_SUFFICES`. Also reported: the class of every U-type run of the study, m_U - Cl_S0 at every geometry, the Udt05 comparison at x134 0 and
x09 0 (`GT_HALF`: mean, amplitude and frequency differences of dt/2 vs dt over the common interval, and the observed order from the three steps where defined),
and the S0 class against the T2-0c class of the same id where one exists. Every Q1 class is "at dt 1e-5 s, from the stated start state(s)".

### 6.3 Gates
**Time-step rule GT(a, b)** between two U-type runs of one geometry: both valid with the same class; |m_a - m_b| <= min(max(2.5e-3 |m_a|, 3 sqrt(SE_a^2 + SE_b^2)),
1e-2 |m_a|); for VALID_PERIODIC also 0.8 <= r_a / r_b <= 1.25 and |f*_a - f*_b| <= max(0.10 max(f*_a, f*_b), 1.5 / T_w). With an observed order p in [1, 2] the
error of the dt run is at most |m_a - m_b| / (2^p - 1).
**Consistency rule C_P** (T2-0c): |a - b| <= max(tol max(|a|, |b|), 0.01, 3 sqrt(sd_a^2 + sd_b^2)), and 3 sqrt(sd_a^2 + sd_b^2) <= 0.5 tol max(|a|, |b|), else
`UNRESOLVED`. d(s) = (m(+s) - m(-s)) / (2 s) per deg; sigma_eff(L) = max(sigma_fit,cubic of the 7-point U scan at (L, 0.134) [base and six A6 morphs], max
SE_run of those 7 runs); sd of a derivative from a scan = sigma_eff / (sqrt(2) s).

**DATA gates** (Q2):
- **GTd**: GT(U, Udt2) at x224 0, x134 0, x09-1, x09 0, x09+1 (xfine30) and f09+1 (fine30).
- **G2u(L)**, L in {fine30, xfine30} (13 U inputs: the 7 heights at 0 deg; +-1 deg remeshed at 0.224, 0.134, 0.09; xfine30 0.134 0 deg = base B (XP1), +-1 deg from
  XO2; fine30 from F1): with Cl = m, e_h = m_h / Cl_exp,h - 1 against `data/t20/zerihan_zhang_cl_genua2009_fig6.json`:
  (i) mean |e_h| < 5 % nominal and with m_h + 0.15 deg x d_R(L, h, 1) (d_R from the remeshed +-1 deg, interpolated as T2-0b); if d_R at 0.09 is not computable the
  value at 0.134 is used there (`SHIFT_UNVERIFIED`); (ii) peak margin M = m(0.134) - (1 - 0.005) max(m(0.179), m(0.09)); (iii) rise margins
  M_i = m(h_{i+1}) - (1 - 0.005) m(h_i) for the four steps from 0.671 to 0.179 and the step 0.179 -> 0.134. With the noise band n(L) = 2 sqrt(2) sigma_peak(L),
  each of these tests passes if its margin >= n(L), fails if its margin < -n(L), and is otherwise noise-indeterminate. **G2u = FAIL_VALUE** if (i) fails or the peak or any rise test fails; **PASS** if (i) passes and the peak and every rise test pass;
  otherwise **INDETERMINATE_NOISE**. sigma_peak(L) = max(sigma_real80, the largest SE_run of L's inputs at 0.179, 0.134, 0.09), where sigma_real80 is the 80 %
  upper bound sqrt(nu / chi2_{0.2, nu}) x sqrt(sum D^2 / (2 nu)) over the nu same-geometry pairs of both levels at h/c 0.134 whose two mesh files differ
  (xfine30: B-morph vs remeshed at +-1 deg, B-morph vs B'-morph at -1, -0.25, +0.25, +1; fine30: the same with B_f and B'_f): realisation noise of a remeshed Cl,
  pooled, with the morph-path difference included (conservative).
- **DATA sub-verdict:** per level, the worst of G2u(L) and the GTd outcomes at L's conditions (xfine30: x224 0, x134 0, x09-1, 0, +1; fine30: f09+1) in the order
  FAIL_TIMESTEP > FAIL_VALUE > MECHANICAL > FAIL_INPUT > UNDETERMINED > INDETERMINATE_NOISE > PASS (a time-step failure makes the level's values unusable); across
  the two levels the worst in the order FAIL_VALUE > FAIL_TIMESTEP > MECHANICAL > FAIL_INPUT > UNDETERMINED > INDETERMINATE_NOISE > PASS.

**DIFF gates** (Q3; xfine30, h/c 0.134):
- **GT134**: GT(U, Udt2) at B, +1 and -1 (all three), and the derivative: |d_U(1) - d_Udt2(1)| <= max(0.10 max(|d_U|, |d_Udt2|), 3 sqrt(sd_U^2 + sd_Udt2^2)) with
  sd = sqrt(SE(+1)^2 + SE(-1)^2) / 2.
- **G6u**: C_P(d(0.25), d(1); 0.25, sigma_eff / (sqrt(2) 0.25), sigma_eff / sqrt(2)) AND |m(+0.25) - m(-0.25)| >= 5 sqrt(2) sigma_eff.
- **G8u**, s in {1, 0.25}, both: C_P(d_B(s), d_B'(s); 0.25, sigma_eff / (sqrt(2) s), max(sigma_eff, max SE_run of the 4 B' runs) / (sqrt(2) s)). A weak control: the
  25 % band would admit part of the T2-0c 26-29 % spread.
- **G3bu**: C_P(d_F(1), d_X(1); 0.25, sd_F, sd_X) with sd_L = max(sigma_eff(L) / sqrt(2), |d_B(L, 1) - d_B'(L, 1)| / sqrt(2)) on the base-B scans of fine30 (F2) and
  xfine30 (XP1): the base-realisation spread of each level enters its noise.
- **GSu**, camber and flap, both: |m(+0.25 mm) - m(-0.25 mm)| >= 5 sqrt(2) sigma_shape, sigma_shape = max(sigma_eff(xfine30), max SE_run of the 4 shape runs).
- **DIFF sub-verdict:** precedence FAIL_TIMESTEP (GT134) > FAIL_VALUE > MECHANICAL > FAIL_INPUT > UNDETERMINED > PASS.

**Cost (verdict-relevant, deterministic):** over the 15 xfine30 h/c 0.134 U runs of XP1 and XP2, the evaluation cost = generation or morph + gmshToFoam + checkMesh
+ S0 + U wall time on one of 4 concurrent workers; `AFFORDABLE` iff median <= 15 min and maximum <= 30 min (T2-0b G5; R5 needs about 96 evaluations in one 11 h
session on 4 workers); a failed or lost run counts with its observed time when that already exceeds 30 min. Predicted (near certain): not affordable.

### 6.4 Verdict (exactly one; precedence top to bottom)
- `T20D_PIPELINE_DEFECT`: DATA or DIFF is MECHANICAL (no route is inferred from it).
- `T20D_INCOMPLETE`: DATA or DIFF is UNDETERMINED and the other is PASS or UNDETERMINED.
- `T20D_QUALIFIED_XFINE30_PEAK`: DATA and DIFF PASS and the cost is AFFORDABLE.
- `T20D_QUALIFIED_UNAFFORDABLE`: DATA and DIFF PASS, cost not affordable ("qualified but not adoptable under R5").
- `T20D_NO_GO`: otherwise; the DATA and DIFF sub-verdicts (with failing gates, classes and noise/realisation/time-step reasons) are part of the verdict record.
The full gate matrix is printed whatever the verdict. Meaning of QUALIFIED: on this 2D section the time-averaged URANS SA-WF evaluator on xfine30 meets the T2-0b G2
rule on fine30 and xfine30 with a noise-banded peak, and at h/c 0.134 resolves +-0.25 deg and +-0.25 mm camber/flap changes with a derivative consistent between
time steps, with fine30 (including each level's base-realisation spread) and with a second base mesh. Nothing about h/c 0.09 differences, other shapes, drag, 3D
or the SDF pipeline.

### 6.5 Next actions (pre-agreed; the last registered T2-0 study, so every row is an input to M4 #66 item 1, never a new T2-0 study)
| outcome | input to M4 (#66 item 1) |
| --- | --- |
| QUALIFIED_XFINE30_PEAK | 2D-section high-Re evaluator candidacy (time-averaged URANS on xfine30, with the Q1 forms); before adoption still: G2 on independent data (T2-0c section 7), the SDF-to-mesh interface, B5 ProblemSpec |
| QUALIFIED_UNAFFORDABLE | as above, plus a backend trigger in STATE.md: the evaluator does not fit R5's one-session budget |
| NO_GO, DIFF not PASS | no optimisation evaluator near the peak from T2-0 (the DIFF reason is stated); T2-0c's 0.224 result is descriptive, a single height and not an evaluator input; the 0.179 steady-scan labels are descriptive |
| NO_GO, DATA not PASS | the G2 route is `G2_ACTION` (section 7) |
| PIPELINE_DEFECT | a pipeline defect: no route is inferred; T2-0 cannot re-register (cap): M4 records it |
| INCOMPLETE | one resubmission per section 8; if still incomplete, item 1 stays blocked |
`Q1_FORM_*` routes nothing: if a form is STEADY_RELAXED_SUFFICES, the relaxed steady evaluator is a candidate that T2-0 has not gated (M4 decides).

### 6.6 Registered labels (computed by the analyzer, never changing the verdict; only `G2_ACTION` feeds a route)
- **Q1** (section 6.2), `GT_HALF`, `FORMULATION_OFFSET`, the U-class map, `LOW_FREQ_PERIODIC`, `SCAN_KINK` (the U classes change within a 7-point scan; the cubic
  and a two-piece linear fit split at the class change are both reported).
- **G2**: per level mean |e| (nominal, shifted), e_h, G2d (T2-0b, <= 0.30), ROBUST (T2-0b: the mean-error parts also pass with the curve shifted by +-0.005), peak
  height, all margins in units of n(L); `PEAK_NONDIAGNOSTIC` if the digitised curve's own peak margin (0.0221) is below n(L); the level step
  max_h |m_xfine30 / m_fine30 - 1| (G3a-type); `G2_ACTION` (section 7).
- **Q3 extras**: sigma_fit cubic and quadratic, SE_run maximum, `SURVIVES_2SIGMA` per DIFF gate, the smallest resolved incidence 2 sqrt(2) sigma_eff / |d(1)|,
  `MDD_PCT` = 2 sqrt(2) sigma_eff / m at 0.134 on both levels (against M2's E2: 0.68 % paired, 2.0 % literal), morph vs remesh d(1) on both levels (G7-type, C without
  the power requirement, SE only: the remeshing noise is not in it), shape d per mm and its sign (expected positive), d_R(L, h, 1) at the three heights, base B vs B2
  mesh identity (`B2_NOT_B`), the fine30 base-B scan gates (G6u, G8u rules on F2: reported, pre-determined in part).
- **Steady scans at h/c 0.179** (XO2, F1; S0 only): S0 classes and the G6m-type rule on the S0 values (T2-0c rule with sigma_eff from S0 tail stds): does the steady
  evaluator converge and resolve +-0.25 deg there (descriptive; no URANS, no second base).
- **Cost**: per run and stage wall times, seconds per step per cell, maximum Courant number, S1 cost, CPU model; `COST_MIN` = pre-solver + transient + T_req at the
  per-T_c cost of U (or of Udt2 if GT134 passes), where T_req is the shortest window at which 5 sqrt(2) SE_run,max(T) <= |m(+0.25) - m(-0.25)| on the B scan, with
  SE_run(T) scaled as T^-1/2 for its batch part and T^-1 for its Hann-bias part (not below 1 T_c); `NOT_ACHIEVABLE` if sigma_fit alone fails the resolution test;
  reported with and without S0 (a warm start from a neighbouring design), against R5's 27.5 min.
- **Descriptive**: y+, cells, layer stacks, mesh SHA-256, CPU models (`CPU_MIXED` per gate), the batch-means lag-1 autocorrelations.

## 7. What M4 (#66) may take, the G2 action, and the claim ceiling

- The verdict, the DATA and DIFF sub-verdicts and `G2_ACTION` are the T2-0d inputs to the T2-0 summary (`docs/t20_summary_for_m4_*.md`). QUALIFIED does not by
  itself adopt an evaluator: #66 item 1 still needs the prerequisites in section 6.5. A NO_GO ends T2-0's search for a high-Re evaluator on this section with the
  recorded reason; any further evaluator study is an M4 decision.
- **`G2_ACTION`** (agreement with 7 digitised points of a thesis figure that re-plots a blunt-TE, finite-span, end-plate wing; not validation of the section's level):
  - `G2_ACTION_STANDS` iff on fine30 or xfine30, with every G2u input of that level valid and its GTd conditions passing, the mean |e| (nominal or shifted) is >= 5 %,
    or G2d > 0.30, or the peak or a rise test fails beyond the noise band -> T2-0b's G2 action (wall-resolved/LM evaluator study or another validation case) stands.
  - `G2_INDEPENDENT_DATA_NEXT` iff on both levels every input is valid, GTd passes, mean |e| < 5 % (both forms), G2d <= 0.30, ROBUST holds, no peak or rise test fails
    beyond the band, and the level step is <= 5 % -> the level and increments agree on the two finest levels of this family; the next G2 step is a data-level test
    against independent data (T2-0c section 7) before any wall-resolved/LM study.
  - `UNDECIDED` otherwise -> T2-0b's G2 action stays the default until a recorded M4 decision (T2-0c's convention).
  No other label may be used to pick or justify a G2 route. Neither outcome attributes T2-0b's med30 failure to a cause (no med30 URANS is run).
- Allowed: the gates, labels and verdict with their numbers for this 2D single-element section (Tyrrell 026, Re_c 4.6e5, moving ground), SA wall functions, fine30
  and xfine30 of Genua's family, the stated time steps and windows, rigid incidence changes and the two shape modes at +-0.25 mm at h/c 0.134, and Q1 as a statement
  about this discrete model at dt 1e-5 s from the stated start states.
- Not allowed: real-flow unsteadiness, a "limit cycle of the real flow" or a physical shedding frequency (St_c and the Q1 labels describe the 2D SA URANS model);
  grid or time-step convergence (the time-step rules are a two-step sensitivity check at the stated conditions and a dt/2 check at two); drag accuracy; any statement
  at h/c 0.09 beyond Q1 and G2; other shape modes, thickness, multi-element wings, 3D, finite span, end plates, other Reynolds numbers, the full vehicle, FSAE
  suitability or FSAE ride heights; the SDF-to-mesh interface, the SDF optimiser or the Re 80 track; using `COST_MIN`, St_c, `Q1_FORM_*` or `MDD_PCT` to justify a
  route. T2-0b's and T2-0c's verdicts are not changed by this study.

## 8. Freeze, review, budget and stop rules

- Order: draft -> one plan review (three independent adversarial angles: numerical, controls, strategy; sonnet) -> revision recorded in section 10 -> **freeze 1**
  -> implementation (`scripts/t20d_case.py`, `scripts/build_t20d_kernel.py`, `scripts/analyze_t20d.py`, `tests/test_t20d.py`, `infra/kaggle/kernel_t20d_cpu/`;
  T2-0c files forked, not edited; the analyzer tested on synthetic fixtures covering every run class (drift, decay, growth, low frequency, few cycles), the
  statistics, every gate outcome, both sub-verdicts, every verdict branch) -> development smoke on Kaggle (mode `smoke`, at most 3 submissions) -> one source
  review -> **freeze 2** -> the six kernels submitted once each.
- Development smoke: a mesh-only pass over every registered geometry of the six kernels (generator or morph, gmshToFoam, boundary fix, topology check, checkMesh),
  plus the solver paths on 4 concurrent workers: xfine30 h/c 0.09 0 deg (S0 1000 iterations, then U 3000 steps, Udt2 1500 steps, Udt05 1000 steps, S1 200
  iterations, US1 500 steps), the xfine30 0.134 +1 deg morph (S0 1000, U 3000 steps), a B' morph and a shape morph (S0 100, U 200 steps), fine30 0.09 +1 deg (S0 100,
  U 200 steps, S1 200 iterations). Removed before output: every coefficient and force file, every force-derived value, every log line matching the T2-0c force
  filter, the mesh files. Kept: statuses, step and iteration counts, wall times, seconds per step, Courant numbers, residual lines, checkMesh output, morph
  diagnostics, digests. **Cost-model check:** if the smoke's xfine30 U seconds per step exceed 1.3x the plan (0.92 s Intel, 0.59 s AMD), or Udt2 is unstable, the
  kernels are re-partitioned (same runs, more kernels) or Udt2's role is revised before freeze 2, recorded in `freeze.json`; no rule or threshold changes.
- Reading order: the registered outputs are not opened for case values before all six are downloaded and `analyze_t20d.py` has run once. Before that only DONE/ERROR
  files, artifact manifests, kernel status/log lines and `analyze_t20d.py --completeness` (the INFRA_LOSS run ids and the counts per class family
  valid/invalid/lost, no values) are read; resubmission and amendment decisions use only that.
- Resubmission: one per kernel, only for INFRA_LOSS: the same commit and template, rendered for the registered mode restricted to the **sets** with a lost run (a
  set = a geometry with all its stage-2 runs; a morph scan with its base; bases regenerated in the resubmission). The analyzer takes each set whole from the first
  run if it is complete there, otherwise whole from the resubmission (never mixed within a set); runs from a resubmission are flagged with their CPU model.
  Amendment (`REGISTERED_AMENDED`): only for a harness or infrastructure defect that prevents a pre-specified quantity from being computed, filed on #57 before
  verdict-relevant output is read, at most one per kernel. An analyzer crash that writes no `verdict.json` and prints no value does not count as the one analysis;
  its fix is recorded on #57 before the rerun. A case-level result (a NONSTATIONARY or failing run, a slow run) is a result, never a reason to rerun.
- Compute: Kaggle CPU only; at most 3 smoke + 6 registered + 6 resubmission + 6 amendment sessions. If a registered kernel cannot fit a Kaggle session, stop and
  report a backend trigger.
- Analysis: `scripts/analyze_t20d.py` (frozen at freeze 2) is run once; `analysis.md` and `verdict.json` are committed unchanged; any later reading is a dated note.

## 9. Outputs

`docs/evidence/t20d_registered_2026_10_21/`: `freeze.json`, `prefreeze_pilot/`, the smoke record, kernel logs, the downloaded outputs (copied from a fresh empty
download directory; mesh files and the full solver logs of U-type runs excluded with their SHA-256 listed; every run keeps its record, coefficient file and log tail),
`SHA256SUMS` (split per directory, checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`, a Japanese note; updates to `docs/STATE.md`
(T2-0 row), `docs/phase_plan.md`, and a result comment on #57. Then the T2-0 summary for M4 and comments on #57 and #66.

## 10. Plan review record

One plan review, three independent adversarial sonnet subagents on draft bc9dc3d2 (2026-10-21): numerical (14 findings), controls (12), strategy (14).
Accepted (A), partly accepted (P) or rejected (R); the change is in the text above.

Numerical:
- N1 P (blocking): Udt2 at all six Q1 targets and at x224 0 and x134-1; Udt05 (dt/2) at x134 0 and x09 0 over a common interval (`GT_HALF`); the error bound is
  |Delta| / (2^p - 1) with p in [1, 2]; a crashed Udt2 is an invalid input (FAIL_INPUT), not a time-step failure, and time steps no longer take top precedence
  (DATA/DIFF sub-verdicts). Making dt vs dt/2 the primary pair everywhere rejected (3.4 h per xfine30 run); it is a label at the two key conditions.
- N2 A: zero-padded parabolic frequency; tolerance max(0.10 f, 1.5 / T_w).
- N3 A: Hann-weighted mean and its bias bound inside SE_run (rather than whole-period truncation).
- N4 P: SE_run uses max(SE10, SE5) with the Hann variance factor; the lag-1 autocorrelation is a label, not a class (a coherent low-frequency run would be rejected).
- N5 A: transient 6 T_c; settled judged on the window's second half; drift floor 5e-4.
- N6 P: growth check for settled runs; second start state (US1) at the two key conditions; the seeded velocity perturbation rejected (needs cell centres and a field
  rewrite, an untested path); "settled within the protocol" stated.
- N7 A: tol_eq 5e-3, `FORMULATION_OFFSET`, S1 judged on its own rows, early stop read from the log.
- N8 A: k* >= 3 with the bias bound; `LOW_FREQ_PERIODIC`.
- N9 P: sigma_real pooled over both levels with an 80 % upper bound (A); the two-piece fit is the label `SCAN_KINK` (sigma_eff unchanged: the max of both fits can
  only equal the cubic one at a kink).
- N10 A: development smoke with U 3000 steps at x09 0 and x134+1 and Udt2 1500 steps under 4-concurrent load; cost-model check and re-partition rule; fields
  written only at the end; `adjustTimeStep no`.
- N11 A: GT mean tolerance 2.5e-3 (capped at 1e-2 with SE); Udt2 on the +-1 morphs at x134 with a derivative check (GT134).
- N12 A: the cost rule is deterministic, predicted to fail and named in the verdict; `COST_MIN` with the transient and the T^-1 bias scaling.
- N13 A: half-step guards on both window ends; latest time directory; Euler first step and the `bounded` removal noted.
- N14 A: disclosed; US1 and `START_DEPENDENT`.

Controls:
- C1 A (blocking): drift from the batch-mean regression with its standard error and a 2e-3 cap; amplitude band [0.8, 1.25]; synthetic drift/decay/growth tests.
- C2 A (blocking): gate outcomes PASS / FAIL_VALUE / FAIL_INPUT / MECHANICAL / UNDETERMINED / INDETERMINATE_NOISE; `T20D_PIPELINE_DEFECT`; a cap hit without NaN is
  INFRA_LOSS (TIME_LIMITED); `G2_ACTION_STANDS` needs valid inputs. A separate NO_GO_INPUTS verdict rejected: the sub-verdict names FAIL_INPUT and routes nothing.
- C3 P (blocking): labels renamed; ROBUST and a level step (T2-0b's G3a, max 5 %, not the suggested 2.5 % mean) required for `G2_INDEPENDENT_DATA_NEXT`; pooled
  sigma_real with an 80 % bound; the med30 attribution removed; the secondary-source wording added.
- C4 P (blocking): Udt2 at every target, amplitude ratio and frequency in GT, GT134 derivative, Udt05 at two conditions, "two-step sensitivity check" wording, a
  Udt2 crash is FAIL_INPUT, Udt2 1500 steps in the smoke. Rejected: an external positive control (a known shedding case needs a geometry and generator outside the
  pinned pipeline); the targets' T2-0c pseudo-time oscillations, the dt/2 runs and the second start are the internal checks, and the limit is stated in section 7.
  Rejected: Udt05 restarted from U at 4 T_c (a run-to-run dependency inside a phase); it runs from S0 and is compared on the common interval.
- C5 P: tol_eq fixed at 5e-3 with the offsets reported (a tolerance calibrated on the controls would be set by outcomes); `STEADY_BRANCH_MISMATCH` split; Udt2 at
  x224 0.
- C6 P: transient 6 T_c (not 7: the 5c downstream region flushes in 5 T_c and the drift test catches an unfinished transient); US1 at x09 0 and x134 0.
- C7 A: frequency refinement; 1e-2 cap on the mean tolerance; GT134 (DIFF) separate from GTd (DATA).
- C8 A: sigma_shape; `B2_NOT_B`; CPU model per kernel and `CPU_MIXED`; set-level resubmission; G8u stated as a weak control. Normalising the cost rule by host
  rejected (Kaggle assigns the CPU; the CPU model is reported).
- C9 A: set-restricted resubmission; the smoke's cost-model check.
- C10 A: `--completeness`; the analyzer-crash rule; the smoke conditions stated.
- C11 P: pre-determined inputs listed in section 2 (text, not a per-gate list in `verdict.json`); pilot scripts and logs committed with what was read; threshold
  provenance stated.
- C12 A: the 0.224 row wording; `Q1_FORM_*` route nothing; label-use ban; cost prediction and failed-run cost; the x134+1 target is the morph from B.

Strategy:
- S1 A (blocking): invalid inputs give FAIL_INPUT, never a G2 conclusion.
- S2 P (blocking): `PEAK_NONDIAGNOSTIC`; `G2_ACTION` rests on mean |e|, G2d, ROBUST, the level step and "no peak or rise failure beyond the band". Rejected: "UNDECIDED
  means LM is not the default" (T2-0c section 7 fixed the convention that T2-0b's action stays the default; changing it here would pick a route by argument, M4 decides).
- S3 A: peak and rise read with the realisation-noise band (three-valued).
- S4 P: transient 6 T_c, window 10 T_c, k* >= 3 with the bias bound. Rejected: 24 T_c for every 0.134/0.09 xfine30 run (+30 core-h) and a runner-side extension
  (classification would move into the runner).
- S5 P: GT split (GT134 in DIFF, GTd in DATA); frequency rule; full gate matrix always printed. Kept: GTd gates DATA (an unverified time step at 0.09 cannot support a
  G2 pass).
- S6 P: fine30 B' scan (F2); base-realisation spread inside G3bu's noise; G8u predicted to fail. Rejected: a conditional XP2 wave (a sequential dependency; the B' runs
  also feed sigma_real).
- S7 P: `Q1_FORM_134`, `Q1_FORM_09`. Rejected: an S1 scan with S1-form gates (where the x134 targets are STEADY_SOLVER_ARTEFACT, S1 equals U within tol_eq at B and
  +-1; the relaxed form is reported as an ungated candidate).
- S8 A: `T20D_QUALIFIED_UNAFFORDABLE`; `COST_MIN` with a warm start and the Udt2 cost.
- S9 P: steady S0 scans at h/c 0.179 on both levels as labels. Rejected: U at 0.179 +-1 and an ATTACHED_RANGE claim (no second base there).
- S10 A: `MDD_PCT`.
- S11 A: dt/2 at x134 0 and x09 0; every Q1 class qualified by time step and start state.
- S12 A: cap 5.5 h; a cap hit without NaN is INFRA_LOSS; the smoke measures seconds per step; S1 runs feeding US1 first.
- S13 A: `SHIFT_UNVERIFIED`.
- S14 A: the attribution removed; the secondary-source wording.
