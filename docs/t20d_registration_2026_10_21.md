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
  model, schemes and mesh sustains an oscillation, e.g. from separation or shedding), or a convergence failure of the steady solver (a time-accurate solution
  settles to a steady state, and a conservatively relaxed steady solver converges to it)? Decided per condition by a URANS run (pimpleFoam, time averaged), a
  time-step control and a relaxed steady control (section 6.2). "Physical" is claimed only at the model level: a sustained URANS oscillation in 2D SA is not
  shown to exist in the real flow.
- **Q2 (verdict).** With the time-averaged Cl, does the T2-0b G2 rule (level, incidence ambiguity, peak at h/c 0.134, unimodal rise) pass on fine30 **and** on
  xfine30? This decides whether T2-0b's G2 action (a wall-resolved/LM evaluator study or another validation case) is still needed (section 7).
- **Q3 (verdict).** At the downforce peak (h/c 0.134), on xfine30 (the level at which the steady solver fails there), are small differences (+-0.25 deg incidence,
  camber and flap +-0.25 mm) resolved above the time-averaging and morph noise, consistent between step sizes, between fine30 and xfine30 and between two base
  mesh realisations; and what does one such evaluation cost against the R5 budget?

Out of scope (decided here): LM and any wall-resolved mesh (T2-0b G2 action: the decision whether it is needed is the output of Q2, not run here); adjoint;
turbulence models other than SA; scheme or wall-function variants (they change the discrete solution or the model, not its convergence: the URANS keeps the
steady case's spatial schemes and wall function, so the S1 control isolates the steady solver's relaxation); 3D, span, end plates; h/c 0.09 for Q3 (separated,
beyond the peak; it enters Q1 and G2). Trigger: T2-0c row 5 and the 2026-10-16 parallel-track decision (T2-0 is the M3a NO-GO branch target). Cap: this is
the last registered T2-0 study.

## 2. What was visible before this registration (and how it is used)

- **All T2-0a, T2-0b and T2-0c results**, including T2-0c's per-case records (its analysis was written once before this text). In particular, read for design:
  the T2-0c unsteady cases oscillate in pseudo-time with a period of 12-17 SIMPLE iterations (raw Cl ranges up to +-7 %); the T2-0c steady VALID cases have raw
  tail relative std 1e-5 to 5e-4 (a period-2 alternation of the SIMPLEC wall-function runs), all below 1e-3; the T2-0c morph scans at h/c 0.134 (fine30 cubic
  residuals up to 0.0023; xfine30 jump of 0.045 in Cl between -0.25 deg (steady) and 0 deg (unsteady pseudo-mean)); the T2-0c 0-deg sweep values (section 7 of
  the T2-0c note); the T2-0c costs per SIMPLE iteration (xfine30 0.25 s Intel Xeon / 0.16 s AMD EPYC, fine30 0.13 / 0.07 s, 4 concurrent cases).
- **Thresholds.** The consistency tolerance (0.25), delta floor (0.01 per deg), power requirement (0.5), resolution factor (5 sqrt(2)), sigma_eff (cubic fit with a
  floor), the G2 rule (5 %, +0.15 deg shift, 0.5 % peak tolerance, unimodal rise) and the G5 cost bounds (15/30 min) are T2-0b's or T2-0c's, **applied after their
  numbers were visible**. New and chosen knowing them: the settling threshold theta = 1e-3 (above every T2-0c steady VALID case, below every T2-0c UNSTEADY case),
  the stationarity and cycle rules, the time-step tolerance, the S1 settings, the window lengths, the verdict levels. `verdict.json` carries
  `thresholds_set_after_exploratory_visible`, `thresholds_set_after_t20b_visible` and `thresholds_set_after_t20c_visible` (all true); they accompany any citation.
- **Pre-determined (disclosed).** fine30 at h/c 0.134 is steady under the T2-0c steady solver (every fine30 0.134 case VALID, raw std <= 2.6e-4); if the URANS
  reproduces the steady solution there (the Q1 controls test this), T2-0c's fine30 G6m (UNRESOLVED, sigma_eff 0.0021) and G8m (0.063 vs 0.086 per deg) results
  stand for fine30, which is why fine30 is not the Q3 verdict level. T2-0b's fine30 sweep (mean |e| 2.90 %, peak at 0.134) pre-determines most of the fine30 G2
  inputs if the URANS settles there; its +1 deg case at 0.09 limit-cycled. **New:** every URANS, time-step and relaxed-steady value; every xfine30 G2 input at
  0.134 and 0.09; every Q3 input.
- **Local force-free timing pilot (2026-10-21, `work/`, not evidence):** one xfine30 h/c 0.09, 0-deg mesh generated locally (49,725 cells), 400 SIMPLEC iterations
  without any force function object, then pimpleFoam (PIMPLE, 2 outer correctors) for 100-113 steps, 1 CPU in the local Docker image: with an adaptive step at
  Courant number 1 the step settles at 2.45e-6 s (the sharp-TE fan cells set the maximum Courant number); at a fixed 1e-5 s the maximum Courant number is 4.1
  and at 2e-5 s 8.2, both stable over 100 steps, 0.81 and 0.74 s per step against 0.285 s per SIMPLE iteration on the same host. No force, coefficient or field
  statistic was computed or read; the pilot sets the time step and the cost estimate (section 5) only.
- **No T2-0d solver output exists at registration.** The development smoke (section 8) removes every force-derived value.
- **Predictions at registration** (in `verdict.json` as `predicted`): Q1: xfine30 h/c 0.09 `UNSTEADY_IN_URANS` (large pseudo-time amplitude), xfine30 0.134
  and fine30 0.09 +1 deg uncertain; controls OK. G2u(fine30) pass; G2u(xfine30) uncertain (the T2-0c pseudo-means put Cl(0.09) above Cl(0.134)); GT pass;
  G6u, G3bu, G8u uncertain; GSu pass; **G5u fail** (near certain from the pilot: about 1.5-2.4 h per xfine30 evaluation). Verdict: `T20D_NO_GO_DIFFERENCES` or
  `T20D_NO_GO_DATA` most likely; `T20D_GO_XFINE30_PEAK_COSTLY` possible; `T20D_GO_XFINE30_PEAK` not expected (G5u).
- **Data reuse.** No T2-0a/b/c output file is read by the analyzer. Every gate and label input is a T2-0d run.

## 3. Case and evaluator protocol

Geometry, meshes and the steady case are T2-0c's, generated by the pinned files unchanged: `scripts/t20_case.py`, `scripts/t20_foam.py` (T2-0a/b),
`scripts/t20c_case.py` (xfine30, the incidence/shape morph and the remeshed cases), Tyrrell026S, chord 0.2234 m, U 30 m/s, Re_c 4.6e5, moving ground,
Tu 0.3 %, domain 2c/5c/6.8c, SA with `nutUSpaldingWallFunction`, levels fine30 (2 mm surface spacing, four 0.6 mm-first layers) and xfine30 (1 mm, two layers).
Incidence = rotation about the LE (LE toward the ground positive), h re-imposed; morphs are T2-0c section 4 (smoothstep blend, asserted per morph: no inverted
cell, fixed nodes unmoved, airfoil nodes with weight 1, contour within 1e-9 m, polyMesh topology hashes equal to the base's). Cl = downforce coefficient.
T_c = c/U = 7.4467e-3 s. A new module `scripts/t20d_case.py` writes the stage-2 dictionaries and copies a solved S0 case into a stage-2 case; it does not
modify the pinned files.

Every geometry runs **stage S0** and then one or more **stage-2 runs**, each in its own copy of the S0 case (same mesh file, same S0 final fields):
- **S0 (steady, T2-0c's evaluator):** the generator's case unchanged: simpleFoam, SIMPLEC (`consistent yes`), relaxation 0.9 on U and nuTilda, bounded
  steady schemes, 5000 iterations from the generator's uniform initial fields; **no continuation**. Its final fields are the initial condition of stage 2.
- **U (time-averaged URANS, the evaluator under test):** pimpleFoam from S0's final U, p, nuTilda, nut and phi (moved to time 0); the same spatial schemes with
  `bounded` removed (`div(phi,U) Gauss linearUpwind grad(U)`, `div(phi,nuTilda) Gauss upwind`, gradients, laplacians and wall distance unchanged), `ddt
  backward`; PIMPLE with `momentumPredictor yes`, 2 outer correctors, 2 pressure correctors, 1 non-orthogonal corrector, no under-relaxation; p GAMG
  (tolerance 1e-7, relTol 0.01; final relTol 0), U and nuTilda smoothSolver (1e-8, relTol 0.1; final 0); **fixed time step dt = 1e-5 s** (T_c/745; pilot
  maximum Courant number about 4 in the sharp-TE fan cells, mean far below 1); **end time 0.1043 s** (14.0 T_c, 10,430 steps); forceCoeffs written every step.
  **Transient** t <= 0.0298 s (4.0 T_c, discarded); **averaging window** 0.0298 < t <= 0.1043 s (10.0 T_c, 7,450 rows).
- **Udt2 (time-step control):** as U with dt = 2e-5 s (pilot maximum Courant number about 8), same transient and window in physical time (3,725 rows). With a
  second-order scheme, agreement of dt and 2 dt within the tolerance bounds the error of the dt run by about a third of it.
- **S1 (relaxed steady control):** simpleFoam from S0's final state (iteration 5000) to iteration 15000: SIMPLE (`consistent no`), relaxation p 0.3, U 0.7,
  nuTilda 0.7, the S0 schemes and residual controls (a run that meets them stops early and is judged on what it ran).

A stage-2 run never maps or interpolates fields: it continues on the S0 mesh. A unit test asserts the copy (mesh and S0 fields byte-identical, S0's
`postProcessing/` and time-information files removed) and the dictionary text.

## 4. Statistics of a run (computed by the frozen analyzer from the run's `coefficient.dat`)

For U and Udt2, over the averaging window (rows with t > 0.0298 s + dt/2; fixed dt, so rows are equally spaced): m = mean Cl, s = std Cl, r = s / |m|;
**SE** = batch-means standard error with 10 equal batches (leading remainder rows dropped), std of the batch means (ddof 1) / sqrt(10); half-window means and
standard deviations (m1, s1), (m2, s2); dominant cycle count k* = the index (>= 1) of the largest periodogram value of Cl - m over the window (k* cycles in the
window; frequency f* = k* / 0.0745 s, Strouhal number St_c = f* c / U).
- **settled:** r < theta = 1e-3.
- **stationary:** |m1 - m2| <= max(6 SE, 2e-4 |m|), and for a run that is not settled also 2/3 <= s2 / s1 <= 3/2.
- **enough cycles:** settled, or k* >= 10.
For S0 and S1: T2-0b's plateau (20-iteration block means over the last 20 % of the run, relative std and drift < 0.5 %) and the raw tail relative std r_tail
(last 20 %); **converged** = plateau and r_tail < theta. Cl of a steady run = the tail mean (T2-0b).

## 5. Kernels, cases, backend and cost

Notation (T2-0c ids): remeshed `sa-wf_h{h}_{mesh}_da{a}`; morph from the kernel's 0-deg base `..._morph-da{a}` and `..._morph-{camber|flap}{a}mm`; morph from the
second base B' (generator at +0.5 deg, not solved) `..._morphB2-da{a}`; run ids append `__S0`, `__U`, `__Udt2`, `__S1`. A7 = {-1, -0.5, -0.25, 0, +0.25, +0.5,
+1} deg. Q1 conditions: **targets** x09-1, x09 0, x09+1, x134 0, x134+1 (remeshed), f09+1; **controls** x224 0, x134-1 (remeshed), f09 0 (x = xfine30, f = fine30).

| kernel | slug | geometries (S0 + U each) | extra stage-2 runs | estimate (Intel / AMD, 4 workers) |
| --- | --- | --- | --- | --- |
| XP1 | `cfd-opt-sdf-t20d-xp1` | xfine30 h/c 0.134: base B (0 deg), morphs at the six nonzero A7, remeshed +-1 deg (9) | Udt2 at B; S1 at B, +1, -1 (remeshed) | 25 core-h, 7.7 h / 4.9 h |
| XP2 | `cfd-opt-sdf-t20d-xp2` | xfine30 h/c 0.134: own 0-deg base B2 (not solved) -> camber, flap +-0.25 mm (4); base B' (+0.5 deg, not solved) -> -1, -0.25, +0.25, +1 deg (4) | none | 20 core-h, 5.2 h / 3.3 h |
| XO | `cfd-opt-sdf-t20d-xo` | xfine30: 0 deg at h/c 0.671, 0.448, 0.313, 0.179; 0 and +-1 deg (remeshed) at 0.224 and 0.09 (10) | Udt2 at 0.09 0; S1 at 0.09 -1, 0, +1 and 0.224 0 | 28 core-h, 7.7 h / 4.9 h |
| F | `cfd-opt-sdf-t20d-f` | fine30: 0 deg at the 7 heights, +-1 deg (remeshed) at 0.224, 0.134, 0.09, morphs at the six nonzero A7 from the 0.134 0-deg case (19) | Udt2 at 0.09 +1; S1 at 0.09 0, +1 | 25 core-h, 6.5 h / 4.1 h |

Per kernel: environment, pinned source, gmsh, hash-locked OpenFOAM v2512 (T2-0c's install), the infrastructure smoke (sa-wf coa30 h/c 0.224, 200 iterations,
as T2-0c), bases generated once, **phase 1** = every S0 (4 concurrent), **phase 2** = every stage-2 run (4 concurrent, longest first). Kernel budget 11 h, per-run
solver cap 4 h. Outputs leave as one tar (T2-0c). 46 geometries, 46 U, 3 Udt2, 9 S1: about 98 core-h.
Unit costs used (from the T2-0c per-iteration costs and the pilot's PIMPLE/SIMPLE ratio 2.84 at dt, 2.6 at 2 dt): xfine30 S0 0.35 / 0.22 h, U 2.06 / 1.30 h,
Udt2 0.94 / 0.59 h, S1 0.69 / 0.44 h; fine30 about half.

**Backend: Kaggle CPU for every stage (option (a)).** Reasons: (1) LOCAL-OF-01 failed for this pipeline (`LOCAL_ENV_FAIL`: gmsh meshes of rotated or displaced
geometries differ between the local image and Kaggle in 86 of 262 geometries); option (b) (meshes generated once, hashed and shipped as inputs, solver-only
locally) would need its own mesh-shipping path and a new environment-gate round before any registered run, with no evidence to gain. (2) Within one kernel every
compared pair shares its mesh (U, Udt2 and S1 copy the S0 case; morphs share their base; each geometry is meshed once per kernel), so gmsh's run-to-run
numbering variants cannot enter a paired comparison; comparisons across kernels (B vs B', fine30 vs xfine30, heights) are between different meshes by design.
(3) Throughput and isolation: four kernels run concurrently on 16 vCPU of Kaggle in about 8 h (or about 16 h if only three sessions run at once), while
the local machine (10 cores: 4 performance + 6 efficiency, 32 GB, OpenFOAM under Rosetta) was at load average 48-102 with 8.9-11.7 GB of 10-12 GB swap in use
during the pilot and is shared with the M3a FID-01 session's local OpenFOAM runs; the pilot's local SIMPLE iteration (0.285 s under that load) is 1.14x Kaggle's
Intel Xeon, so the ~98 core-h would take about 14 h on 8 local cores while blocking M3a. Kaggle CPU sessions are shared with other sessions' kernels (M3a uses
T4 GPU sessions); a concurrency limit is waited out, never worked around.

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20d.py`)

### 6.1 Run classes
- `MECHANICAL_FAIL`: generator, morph assertion, topology or checkMesh failure of the geometry (T2-0c's statuses).
- `INFRA_LOSS`: no record, `NOT_RUN_TIME_BUDGET`, `RUNNER_EXCEPTION`, `DEADLINE_LIMITED` (cut by the kernel budget), kernel killed.
- `SOLVER_FAIL`: S0 failed (crash, NaN, timeout; an unconverged S0 is not a failure), or the stage-2 solver crashed, produced NaN or |Cl| > 100, hit the
  per-run cap, or its history ends before the end time (U, Udt2) or before the S1 end without meeting the residual controls.
- For U and Udt2: `VALID_SETTLED` (settled and stationary), `VALID_PERIODIC` (not settled, stationary, enough cycles), `NONSTATIONARY` (otherwise).
- For S0 and S1: `CONVERGED` or `NOT_CONVERGED` (section 4).
A gate input must be VALID_SETTLED or VALID_PERIODIC; NONSTATIONARY, SOLVER_FAIL and MECHANICAL_FAIL inputs fail the gate; an INFRA_LOSS input (and no failing
input) makes it undetermined; any undefined quantity fails. The Cl of a U input is m; its noise is SE.

### 6.2 Q1 classification (registered labels, per Q1 condition)
- `STEADY_SOLVER_ARTEFACT`: U VALID_SETTLED, S1 CONVERGED and |Cl_S1 - m_U| <= 1e-3 |m_U| (a time-accurate solution settles and a relaxed steady solver
  reaches it: the T2-0c oscillation was the SIMPLEC-0.9 iteration's).
- `STEADY_URANS_ONLY`: U VALID_SETTLED, but S1 not CONVERGED or not within 1e-3 (the flow settles, the steady solver does not reach it).
- `UNSTEADY_IN_URANS`: U VALID_PERIODIC, and where a Udt2 run exists its time-step check (GT rule) passes (a sustained, stationary oscillation of the model's
  time-dependent solution; St_c, amplitude r and m reported).
- `INDETERMINATE`: otherwise.
Controls: `CONTROL_OK` iff U VALID_SETTLED, S0 and S1 CONVERGED and both within 1e-3 |m_U| of m_U.
`Q1_FORM`: `INDETERMINATE` if a control is not OK or a target is INDETERMINATE; else `URANS_REQUIRED` if a target is UNSTEADY_IN_URANS or STEADY_URANS_ONLY;
else `STEADY_RELAXED_SUFFICES`. Also reported: the U class of every run of the study (where the URANS is unsteady), and m_U - Cl_S0 at every geometry (the
steady pseudo-mean's bias).

### 6.3 Gates
With sigma_eff(L) = max(sigma_fit,cubic of the 7-point U scan at (L, 0.134) [B, the six A7 morphs], max SE over those 7 runs); d(s) = (m(+s) - m(-s)) / (2 s)
per deg; the consistency rule C_P(a, b; tol, sd_a, sd_b): |a - b| <= max(tol max(|a|, |b|), 0.01, 3 sqrt(sd_a^2 + sd_b^2)), and 3 sqrt(sd_a^2 + sd_b^2) <= 0.5 tol
max(|a|, |b|) else `UNRESOLVED` (fails) (T2-0c).
- **G2u(L)**, L in {fine30, xfine30} (13 U inputs: the 7 heights at 0 deg, +-1 deg remeshed at 0.224, 0.134, 0.09): T2-0b's G2 with Cl = m: mean |e_h| < 5 %
  nominal and with m_h + 0.15 deg x d_R(L, h, 1) (d_R from the remeshed +-1 deg, interpolated as T2-0b) against the digitised curve
  (`data/t20/zerihan_zhang_cl_genua2009_fig6.json`), peak m(0.134) >= (1 - 0.005) max(m(0.179), m(0.09)), unimodal rise m(h_next) >= (1 - 0.005) m(h) from 0.671 to
  0.134. T2-0b's "no oscillation" requirement is read as the input validity of section 6.1 (a stationary time mean), a disclosed change.
- **GT** (3 Udt2 conditions: x09 0, x134 0, f09+1): at each, U and Udt2 VALID with the same class, |m_U - m_Udt2| <= max(5e-3 |m_U|, 3 sqrt(SE_U^2 + SE_Udt2^2)),
  and for VALID_PERIODIC |f*_U / f*_Udt2 - 1| <= 0.10. Passes iff all three pass.
- **G6u** (xfine30, 0.134): C_P(d(0.25), d(1); 0.25, sigma_eff / (sqrt(2) 0.25), sigma_eff / sqrt(2)) AND |m(+0.25) - m(-0.25)| >= 5 sqrt(2) sigma_eff.
- **G3bu** (0.134): C_P(d_F(1), d_X(1); 0.25, sigma_eff(fine30) / sqrt(2), sigma_eff(xfine30) / sqrt(2)) on the two morph scans.
- **G8u** (xfine30, 0.134), s in {1, 0.25}, both: C_P(d_B(s), d_B'(s); 0.25, sigma_eff / (sqrt(2) s), max(sigma_eff, max SE of the 4 B' runs) / (sqrt(2) s)).
- **GSu** (xfine30, 0.134), camber and flap, both: |m(+0.25 mm) - m(-0.25 mm)| >= 5 sqrt(2) sigma_eff(xfine30).
- **G5u** (cost): over the 17 xfine30 h/c 0.134 U runs of XP1 and XP2, the evaluation cost (generation or morph + gmshToFoam + checkMesh + S0 + U wall time on one
  of 4 concurrent workers) has median <= 15 min and maximum <= 30 min (T2-0b G5; R5 needs about 96 evaluations in one 11 h session on 4 workers).

### 6.4 Verdict (exactly one; precedence top to bottom)
- `T20D_INCOMPLETE`: the verdict below is not the same for every true/false assignment of the undetermined gate values.
- `T20D_NO_GO_TIMESTEP`: GT fails (the time-averaged values depend on the time step beyond the tolerance at a registered condition).
- `T20D_NO_GO_DATA`: G2u(fine30) or G2u(xfine30) fails.
- `T20D_NO_GO_DIFFERENCES`: G2u passes on both levels, and G6u, G3bu, G8u or GSu fails.
- `T20D_GO_XFINE30_PEAK_COSTLY`: all of the above pass, G5u fails.
- `T20D_GO_XFINE30_PEAK`: every gate passes.
Meaning of a GO: on this 2D section, the time-averaged URANS SA-WF evaluator on xfine30 meets the T2-0b G2 rule on fine30 and xfine30, and at h/c 0.134 resolves
+-0.25 deg and +-0.25 mm camber/flap changes with a derivative consistent between step sizes, with fine30 and with a second base mesh, with time-step-consistent
means. It says nothing about h/c 0.09 differences, other shapes, drag, 3D or the SDF pipeline.

### 6.5 Next actions (pre-agreed; this is the last registered T2-0 study, so every row is an input to M4 #66 item 1, not a new T2-0 study)
| verdict | input to M4 (#66 item 1) |
| --- | --- |
| GO_XFINE30_PEAK | 2D-section high-Re evaluator candidacy (time-averaged URANS on xfine30, with the Q1 form); still required before adoption: G2 on independent data (T2-0c section 7), the SDF-to-mesh interface, B5 ProblemSpec |
| GO_XFINE30_PEAK_COSTLY | as GO, and a backend trigger (STATE.md): the evaluator does not fit R5's one-session budget |
| NO_GO_DIFFERENCES | no optimisation evaluator near the peak from T2-0; level and peak usable descriptively; attached-height differences per T2-0c (h/c 0.224); item 1 stays NO-GO for the peak |
| NO_GO_DATA | item 1 NO-GO; the T2-0b G2 action (wall-resolved/LM evaluator or another validation case) is needed before any high-Re evaluator; T2-0 runs none (cap): M4 decides |
| NO_GO_TIMESTEP | item 1 NO-GO; a temporal-discretisation study would be needed; T2-0 runs none: M4 decides |
| INCOMPLETE | one resubmission per section 8; if still incomplete, item 1 stays blocked |
A MECHANICAL_FAIL in a gate input is reported with the verdict as a pipeline defect (no route is inferred from that gate).

### 6.6 Registered labels (computed by the analyzer, never changing the verdict)
- **Q1** (section 6.2): per condition the S0, U, Udt2 and S1 classes and statistics; `Q1_FORM`; the U class map of all runs; m_U - Cl_S0 per geometry.
- **G2 action** (`G2_ACTION`): `NOT_NEEDED` iff GT and G2u pass on both levels and, on both, the peak margin m(0.134) - (1 - 0.005) max(m(0.179), m(0.09)) is
  >= 2 sqrt(2) sigma_peak(L); `NEEDED` iff G2u fails on either level (GT passing); else `UNDECIDED` (T2-0b's action stays the default). sigma_peak(L) =
  max(sigma_real(L), the largest SE of the three peak-height inputs), with sigma_real(L) the realisation noise of a remeshed Cl at the peak height: sqrt(mean of
  D^2 / 2) over the same-geometry pairs of level L at h/c 0.134 (xfine30: B-morph vs remeshed at +-1 deg and B-morph vs B'-morph at -1, -0.25, +0.25, +1 deg, 6
  pairs; fine30: morph vs remeshed at +-1 deg, 2 pairs). Also per level: mean |e|, e_h, G2d (T2-0b), peak height, the rise breaks.
- **Q3 extras**: sigma_fit cubic and quadratic, max SE, `SURVIVES_2SIGMA` per gate, the smallest resolved incidence 2 sqrt(2) sigma_eff / |d(1)|, the morph vs
  remesh derivative at 1 deg on both levels (G7-type, C without the power requirement, with SE only: the remeshing noise is not in it), shape d per mm and its sign
  (expected positive), d_R(L, h, 1) at the three heights on both levels.
- **Cost**: per run and stage wall times, seconds per step per cell, maximum Courant number, S1 cost, and `COST_TO_RESOLVE` = the evaluation cost if the window
  were scaled to the shortest one that still resolves +-0.25 deg at 0.134 on xfine30 (T_req = 10 T_c x (SE_max / (|m(+0.25) - m(-0.25)| / (5 sqrt(2))))^2, not
  below 1 T_c; `NOT_ACHIEVABLE` if sigma_fit alone fails the resolution test), against R5's 27.5 min per evaluation.
- **Descriptive**: y+, cells, layer stacks, mesh SHA-256 (base B vs B2 identity), every S0 class against the T2-0c class of the same id where one exists (not bitwise:
  gmsh variants).

## 7. What M4 (#66) may take, the G2 action, and the claim ceiling

- The verdict and the `G2_ACTION` label are the T2-0d inputs to the T2-0 summary (`docs/t20_summary_for_m4_*.md`). A GO does not by itself adopt an evaluator for
  M4: #66 item 1 still needs the prerequisites in the GO row of section 6.5. A NO-GO closes T2-0's search for a high-Re evaluator on this section with the
  recorded reason; any further evaluator study is an M4 decision, not T2-0.
- **G2 action (decided by `G2_ACTION`):** NOT_NEEDED -> T2-0b's wall-resolved/LM or other-validation-case action is not needed to fix the level/peak failure (it was a
  med30 and steady-solver artefact); the remaining G2 step is a data-level test against independent data (T2-0c section 7). NEEDED -> T2-0b's G2 action stands.
  UNDECIDED -> T2-0b's G2 action stays the default until a recorded decision. No other label may be used to pick or justify a G2 route.
- Allowed: the gates, labels and verdict with their numbers for this 2D single-element section (Tyrrell 026, Re_c 4.6e5, moving ground), SA wall functions, fine30
  and xfine30 of Genua's family, the stated time step and window, rigid incidence changes and the two shape modes at +-0.25 mm at h/c 0.134, and Q1 as a statement
  about this discrete model.
- Not allowed: real-flow unsteadiness (only the 2D SA URANS model's), grid or time-step convergence beyond the GT check, drag accuracy, any statement at h/c 0.09
  beyond Q1 and G2, other shape modes, thickness, multi-element wings, 3D, finite span, end plates, other Reynolds numbers, the full vehicle, FSAE suitability or
  FSAE ride heights, the SDF-to-mesh interface, the SDF optimiser or the Re 80 track. T2-0b's and T2-0c's verdicts are not changed by this study.

## 8. Freeze, review, budget and stop rules

- Order: draft -> one plan review (three independent adversarial angles: numerical, controls, strategy; sonnet) -> revision recorded in section 10 -> **freeze 1**
  -> implementation (`scripts/t20d_case.py`, `scripts/build_t20d_kernel.py`, `scripts/analyze_t20d.py`, `tests/test_t20d.py`, `infra/kaggle/kernel_t20d_cpu/`;
  T2-0c files forked, not edited; the analyzer tested on synthetic fixtures covering every run class, the statistics, every gate, every verdict branch and the
  undetermined enumeration) -> development smoke on Kaggle (mode `smoke`, at most 3 submissions) -> one source review -> **freeze 2** -> kernels XP1, XP2, XO, F
  submitted once each.
- Development smoke: a mesh-only pass over every registered geometry of the four kernels (generator or morph, gmshToFoam, boundary fix, topology check, checkMesh),
  plus each solver path shortened (S0 100 iterations, then U 200 steps, Udt2 100 steps, S1 100 iterations) on an xfine30 remeshed, an xfine30 morphed, a B' morph,
  a shape morph and a fine30 geometry. Removed before output: every coefficient and force file, every force-derived value, every log line matching the T2-0c force
  filter, and the mesh files. Kept: statuses, step and iteration counts, wall times, Courant numbers, residual lines, checkMesh output, morph diagnostics, digests.
- Reading order: the registered kernel outputs are not opened for case values before all four are downloaded and `analyze_t20d.py` has run once; before that only
  DONE/ERROR files, artifact manifests, kernel status/log lines and per-run `status` fields are read.
- Resubmission: one identical resubmission per kernel, only for INFRA_LOSS (first-run priority; runs from a resubmission are flagged with their CPU model).
  Amendment (`REGISTERED_AMENDED`): only for a harness or infrastructure defect that prevents a pre-specified quantity from being computed, filed on #57 before
  verdict-relevant output is read, at most one per kernel. A case-level result (a NONSTATIONARY or failing run, a slow run) is a result, never a reason to rerun.
- Compute: Kaggle CPU only; at most 3 smoke + 4 registered + 4 resubmission + 4 amendment sessions. If a registered kernel cannot fit a Kaggle session, stop and
  report a backend trigger.
- Analysis: `scripts/analyze_t20d.py` (frozen at freeze 2) is run once; `analysis.md` and `verdict.json` are committed unchanged; any later reading is a dated note.

## 9. Outputs

`docs/evidence/t20d_registered_2026_10_21/`: `freeze.json`, the smoke record, kernel logs, the downloaded outputs (copied from a fresh empty download directory;
mesh files and full solver logs of the U/Udt2 stages excluded with their SHA-256 listed; every run keeps its record, coefficient file and log tail),
`SHA256SUMS` (split per directory, checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`, a Japanese note; updates to `docs/STATE.md`
(T2-0 row), `docs/phase_plan.md`, and a result comment on #57. Then the T2-0 summary for M4 and comments on #57 and #66.

## 10. Plan review record

(filled after the plan review)
