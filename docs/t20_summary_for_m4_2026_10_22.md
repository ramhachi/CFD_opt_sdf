# T2-0 summary for M4 (#66 item 1): the body-fitted high-Re RANS evaluator on a 2D ground-effect wing section

Date 2026-10-22. Track #57 (T2-0, parallel to the Re 80 WaterLily line). This summary closes the registered part of T2-0: the T2-0c registration capped T2-0 at one
more registered study, and T2-0d was it. Every number below comes from the cited records; their evidence classes are stated. All qualification flags stay false;
`shape_update_allowed=false`. Scope of every statement: one 2D single-element section (Tyrrell 026, Zerihan & Zhang wing in ground effect), Re_c 4.6e5, moving
ground, OpenFOAM v2512, SA with wall functions unless stated, Genua's wall-function mesh family (fixed 0.6 mm first layer), Kaggle CPU. Nothing here covers 3D,
finite span, end plates, tip vortices, multi-element wings, other Reynolds numbers, the full vehicle, FSAE ride heights or the SDF-to-mesh interface.

## 1. The four studies

| study | status | question | outcome | record |
| --- | --- | --- | --- | --- |
| T2-0a (2026-10-16) | `EXPLORATORY_COMMITTED` | can the case run on Kaggle CPU and land near the data? | SA-WF med30 within about 5 % of the experiment at h/c 0.224 and 0.09, peak at 0.134; SST-WF +9/-11 %; SST->LM about 2.4 h per case, not plateaued | `docs/evidence/t20a_exploratory_2026_10_16/` (not citable for claims) |
| T2-0b (2026-10-19) | `REGISTERED_FROZEN` | is the steady SA-WF evaluator a go on med30 (data, mesh, model, cost, small steps)? | **`T20B_NO_GO`**: G2 fails (peak at 0.179; mean abs e 4.24 %, 5.45 % with the 0.15 deg incidence ambiguity), G3b fails (0.09 derivative 0.055 vs 0.082 per deg), G6 fails (+-0.25 deg not resolved at 0.134); G2d 0.288, G3a 4.46 %, G3c 0.236, G4 (SA vs SST) and G5 (cost) pass; LM agrees in its limit-cycle mean (4.77 %) at about 3.5 h per case; adjoint `ADJ_FAILED`; DAFoam not attempted | `docs/evidence/t20b_registered_2026_10_19/` |
| T2-0c (2026-10-21) | `REGISTERED_FROZEN` | do fixed-topology morphs remove the remeshing noise, and what does a four-level series show? | **`T20C_MORPH_NO_GO`** (row 5): at h/c 0.224 every gate passes on fine30 (morph noise 24x below remeshing, +-0.25 deg resolved, derivative consistent with xfine30, a second base mesh and the remeshed cases); at 0.134 the derivative depends on the base mesh by 26-29 % and xfine30 does not settle for incidence >= 0; at 0.09 xfine30 never settles | `docs/evidence/t20c_registered_2026_10_20/` |
| T2-0d (2026-10-22) | `REGISTERED_FROZEN` | is the non-settling physical (URANS) or numerical; with time-averaged values, does G2 hold on fine30/xfine30 and are small differences resolved at the peak? | **`T20D_NO_GO`** (DATA `FAIL_INPUT`, DIFF `FAIL_VALUE`, cost `NOT_AFFORDABLE`): the URANS settles to a steady state wherever the steady solver did not (no oscillation in 58 valid runs); h/c 0.09 +1 deg still drifts after 16 T_c; the G2 peak test is non-diagnostic under the realisation noise; on xfine30 at 0.134 +-0.25 deg and +-0.25 mm camber/flap are resolved, consistent between time steps and two base meshes, but not certifiable against fine30; 92 min per evaluation | `docs/evidence/t20d_registered_2026_10_21/` |

## 2. What the evaluator can and cannot do (registered evidence unless marked)

| role | finding | usable for M4? |
| --- | --- | --- |
| Absolute downforce level vs ride height (G2) | med30 puts the peak at 0.179 (T2-0b). Time-averaged fine30 / xfine30: mean abs e 3.0 % / 3.4 % against the digitised curve, peak at 0.134 / at 0.179 by 0.0008 (T2-0d). The level falls with every refinement (h/c 0.224: 1.345, 1.308, 1.271 for med30, fine30, xfine30 in T2-0c; xfine30 7.2 % below fine30 at 0.134 in T2-0d) and xfine30 is 5.6 % / 8.1 % low at 0.134 / 0.09. The realisation noise of a remeshed Cl at 0.134 (sigma 0.020) exceeds the curve's own peak margin (0.022), so the peak location cannot be tested at this noise. The reference is a secondary digitisation of a finite-span, end-plate, blunt-TE wing | **No.** G2 is not established on any level; `G2_ACTION` UNDECIDED, so T2-0b's G2 action (a wall-resolved/LM evaluator study or another validation case) stays the default |
| Ride-height increments (G2d) | med30 0.288 (pass, T2-0b); fine30 URANS 0.363 (fails the 0.30 bound), xfine30 0.267 (T2-0d labels) | No (mesh dependent) |
| Small incidence/shape differences, attached (h/c 0.224) | steady SA-WF with fixed-topology morphs on fine30: every T2-0c gate passes (sigma_eff 0.00043; +-0.25 deg resolved; derivative within the band against xfine30, a second base and the remeshed cases) | Descriptive only (T2-0c's verdict is NO_GO; one height, one section) |
| Small incidence differences, h/c 0.179 | steady S0 morph scan on xfine30 converges and passes the G6m-type rule (sigma 0.00047); fine30 unresolved (T2-0d labels, one base) | Descriptive only |
| Small differences at the downforce peak (h/c 0.134) | steady SA-WF on xfine30 does not converge and its pseudo-means are 1.4-6.2 % high (T2-0d); on fine30 it converges but the derivative depends on the base mesh by 26-29 % (T2-0c; T2-0d 0.066 vs 0.088). The time-averaged URANS on xfine30 resolves +-0.25 deg (sigma 0.00058, smallest resolved 0.02 deg) and +-0.25 mm camber/flap, consistent between 2 dt and dt and between two base meshes (6-8 %), but the fine30 comparison is unresolved and one evaluation costs 1.5-2.2 h | **No** (DIFF fails; cost far above R5) |
| Separated flow (h/c 0.09) | steady never settles on xfine30; the URANS at +1 deg still drifts after 16 T_c on both levels | No |
| Model form | SA and SST incidence derivatives agree within 33 % (T2-0b G4); SST-WF levels off by +9/-11 % (T2-0a, exploratory); LM's limit-cycle mean agrees with the curve (4.77 %) but oscillates by 8-9 % at 0.134/0.09 and costs about 3.5 h per case (T2-0b label) | A model band exists; LM is not an in-loop option |
| Gradients | `adjointOptimisationFoam` (frozen turbulence, wall functions) `ADJ_FAILED` (SIGFPE in the adjoint pressure solve, T2-0b); DAFoam not attempted (no Docker on Kaggle; R5 and #23 make gradient-free screening the default) | No adjoint route from T2-0 |
| Steady-solver behaviour | SIMPLEC 0.9 and SIMPLE 0.7 fail to converge at the peak and in separation on the finest level; time marching (PIMPLE, dt 1e-5 s) converges there to a steady state independent of the start state; the PIMPLE and SIMPLEC steady limits differ by 0.25-0.91 %; the settled value moves by about 0.18 % per halving of dt with no sign of convergence (T2-0d) | A cheaper time-marching form (local time stepping) is plausible but untested |
| Mesh family and reproducibility | not a grid-convergence family (fixed first layer); remeshing noise 0.2-0.9 % of Cl, removed by morphs at attached heights, not near the peak (base realisation); gmsh writes numbering variants run to run and its meshes of rotated geometries depend on the platform (LOCAL-OF-01 `LOCAL_ENV_FAIL`); OpenFOAM itself is deterministic on one mesh | Any reuse needs a fixed mesh-generation path |

## 3. Cost (Kaggle CPU, one of 4 concurrent workers)

| evaluator | cost per evaluation | source |
| --- | --- | --- |
| steady SA-WF, med30 (~15k cells) | about 15 s to the Cl plateau incl. meshing; 5.5 min for the capped 5000 iterations | T2-0b G5 |
| steady SA-WF, fine30 (~25k cells) | 0.6 min to the plateau; 6-11 min capped | T2-0c |
| steady SA-WF, xfine30 (~50k cells) | 13-21 min per 5000 iterations; does not converge at the peak | T2-0c, T2-0d |
| time-averaged URANS, xfine30 (S0 + 16 T_c at dt 1e-5 s) | median 92 min, maximum 134 min (0.31-0.71 s per URANS step, AMD and Intel) | T2-0d (cost rule) |
| same, warm-started, 2 dt, 7 T_c (label, untested) | about 24 min | T2-0d `COST_MIN` |
| LM (wr2, ~130k cells) | about 3.5 h per case | T2-0b |
| R5's budget | 27.5 min per evaluation (about 96 evaluations in one 11 h session on 4 workers) | T2-0b section 6 |

Kaggle allows 5 concurrent batch CPU sessions per account (T2-0d's sixth kernel waited about 2.5 h).

## 4. Input to #66 item 1 (evaluator choice)

- **Registered go/no-go from #57: NO-GO.** T2-0b (`T20B_NO_GO`), T2-0c (`T20C_MORPH_NO_GO`) and T2-0d (`T20D_NO_GO`) are all registered NO-GO outcomes. #66 item 1
  requires a registered #57 GO to adopt a high-Re evaluator, so **"OpenFOAM RANS (T2-0 line)" cannot be adopted as the optimisation evaluator on this evidence.**
  This does not depend on M3a.
- **The M3a NO-GO branch** ("smooth-advection-scheme WaterLily test first, then move to the T2-0 evaluator", STATE.md) has no registered T2-0 evaluator to move to;
  M4 has to record that the second step is unavailable unless it opens new evaluator work.
- **If M4 still wants a high-Re evaluator, the open items are new work outside T2-0** (each needs its own registration): (a) the G2 route: by the registered
  default, a wall-resolved/LM evaluator study or another validation case (G2 against independent data in any case, T2-0c section 7); (b) a cheaper steady-by-time-
  marching form and a registered test of differences at the peak that includes base-mesh ensembles and a finer-level comparison that can be certified; (c) a
  mesh-generation path that is reproducible across platforms (or fixed meshes as inputs); (d) the SDF-to-mesh interface; (e) B5 ProblemSpec; (f) the compute
  backend (a 1.5-2.2 h evaluator does not fit R5's one-session budget on Kaggle CPU).
- **What M4 may cite:** the gates, labels and verdicts above with their numbers, within the 2D-section scope, with their evidence classes; the exploratory T2-0a
  numbers only as context. Not citable: grid or time-step convergence, real-flow unsteadiness (T2-0d's Q1 is a statement about the 2D SA model), drag accuracy,
  FSAE suitability.

## 5. State of #57

The #57 deliverables (a registered feasibility record with timing, mesh sensitivity, model spread and data comparison, DAFoam feasibility, and a go/no-go) are
recorded: timing (T2-0b G5, T2-0c, T2-0d cost), mesh sensitivity (T2-0b G3a-c, T2-0c series and morphs, T2-0d level step and realisation noise), model spread
(T2-0b G4 and the LM label, T2-0a), data comparison (T2-0b G2/G2d, T2-0d G2u), DAFoam (not attempted, reasons recorded; the in-package adjoint failed), go/no-go
(NO-GO). No further registered T2-0 study is allowed by the cap. #57 is ready to be closed with this summary as its final record.
