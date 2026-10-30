# T2-0b registered feasibility study (#57): 2D ground-effect wing-section RANS evaluator go/no-go

Registration status (PROC-01): `DRAFT` -> `DRAFT_FROZEN_PLAN` at freeze 1 (SHA-256 of this file posted on #57) -> **`REGISTERED_FROZEN`** at freeze 2
(source commit and hashes of the kernel template, builder, analyzer, adjoint module and generator files posted on #57 and in
`docs/evidence/t20b_registered_2026_10_19/freeze.json`). Evidence class of the result: descriptive numerical and capability evidence for one 2D section.
The verdict feeds M4 (#66) and L3 (#67) only within the scope in section 7. All qualification flags stay false; `shape_update_allowed=false`.
**This text governs; a disagreement between it and the frozen analyzer is a defect of the analyzer.**

## 1. Question and hypotheses

Question: for the Zerihan & Zhang single-element wing in ground effect (Tyrrell 026, Re_c = 4.6e5, moving ground), is a body-fitted 2D steady RANS evaluator
(OpenFOAM v2512 on Kaggle CPU, Spalart-Allmaras with wall functions) cheap enough, close enough to the published experiment in level and in ride-height differences,
and consistent enough between two meshes, between two turbulence models and between step sizes, to be a candidate evaluator for M4?

- Candidate: **sa-wf** (SpalartAllmaras, nutUSpaldingWallFunction). **Comparator** (model form): sst-wf (kOmegaSST, wall functions). The comparator is not a
  candidate; it enters only gate G4. (T2-0a already showed SST-WF off the experiment by +9/-11 %; it is kept because model spread is a #57 deliverable.)
- H1 data: Cl(h/c) on med30 meets Genua's Green criterion and reproduces the experimental ride-height increments.
- H2 mesh: Cl differs by <= 5 % between med30 and fine30; the incidence derivative and the ride-height increments differ by <= 25 %.
- H3 model: the SST incidence derivative agrees with SA within 33 %.
- H4 step and noise: the derivative from +-0.25 deg agrees with that from +-1 deg within 25 %, i.e. small changes are resolved above the remeshing noise.
- H5 cost: one evaluation (mesh + solve to a force plateau) takes <= 15 min (median) on one of four concurrent Kaggle CPU workers.
Secondary, labelled but never changing the verdict: kOmegaSSTLM data agreement, adjoint (adjointOptimisationFoam) feasibility; DAFoam is not attempted (section 5).

## 2. What was visible before this registration (and how it is used)

- T2-0a (EXPLORATORY_COMMITTED, 242e4bd, `docs/evidence/t20a_exploratory_2026_10_16/`) was fully visible: SA-WF med30 Cl within about 5 % of the
  experiment at h/c 0.224 and 0.09, peak at 0.134; SST-WF +9/-11 %; SST->LM in a limit cycle (Cl std 1.2 %, 9.7 %, 8.7 % of the mean at 0.224, 0.134, 0.09);
  wall-function cases about 6 min with Cl settled within 0.2 % after 62-145 of 5000 iterations; LM about 2.4 h per case.
- **All thresholds were chosen after seeing T2-0a** (`thresholds_set_after_exploratory_visible: true` is written into `verdict.json` and must accompany any
  citation). Anchors: G2 = Genua's Green criterion (Genua 2009, thesis PDF p. 10 = paper 1 p. 8: a grid is Green if it meets the four requirements, which are
  average and maximum error, a downforce maximum at h = 0.134c and no oscillation, and its average error is below 5 %; recorded with the page in
  `data/t20/genua2009_green_criterion.json`). "Average error" is implemented as mean |e| (at least as strict as |mean e|). Genua states no maximum-error number, so
  none is used. G2d = the Genua grid categories: with the digitised curve his Green grids have a relative increment error of 0.12-0.21 and his Red grids 0.32-1.73
  (Fine30SA 0.32), so 0.30 separates them. The 25 %/33 % consistency tolerances and the 15 min cost are registrant choices: 25 % is the order of the slope
  variation that made the Re 80 track fail (GRID-02: 50-100 %), halved; 33 % for model form is a conventional factor-1.5 band; 15 min follows from section 6, G5.
- **Predictions at registration** (also in `verdict.json` as `predicted`): G2 pass (T2-0a SA-WF on 5 heights: mean |e| 4.0 %, max 5.5 %); G2d uncertain; G3a fail
  (Genua's Fine30SA/Med30SA - 1 = +3.7 ... +12.5 %); G3b, G4, G6 uncertain; G3c near its threshold (Genua's Fine30/Med30 increment difference is 0.26); G5 pass
  (non-discriminating: T2-0a cost is far below); LM label `LM_NOT_QUALIFIED` (limit cycle); adjoint `ADJ_CONSISTENT` unlikely (the Stage S laminar precedent gave
  FD/adjoint ratios 0.88-1.46). Gates predicted with near certainty (G2, G3a, G5) carry little information; the information is in G2d, G3b, G3c, G4 and G6.
- **No T2-0a number enters any gate.** The gates use only cases run by the frozen T2-0b kernels. 5 of the 7 med30 heights repeat T2-0a's conditions: this is a
  registered replication, not disjoint data, so the T2-0a statement itself stays non-citable; the disjoint data are h/c 0.313 and 0.179, the fine30 and coa30 meshes,
  the incidence scan and the LM/adjoint items, and G2 is also reported on the two disjoint heights alone (label below). A descriptive replication label compares the
  5 shared heights with T2-0a.
- No T2-0b solver output exists at registration. The development smoke (section 8) suppresses all force, coefficient and derivative values.

## 3. Case (generator reused by hash, not edited)

`scripts/t20_case.py` and `scripts/t20_foam.py` (the T2-0a files, pinned by SHA-256, not modified) generate every case: Tyrrell026S coordinates (Genua 2009
Table 1, sharpened TE), chord c = 0.2234 m, U = 30 m/s, nu = 1.457e-5 m2/s, Tu 0.3 %, length scale 1 cm, ground moving at U, domain 2c/5c/6.8c, one-cell extrusion;
h = distance from the lowest suction-surface point to the ground. Incidence change `--delta-alpha-deg` rotates the section counter-clockwise about the LE (LE toward the
ground = +) and then re-imposes h: a rigid rotation at fixed ride height (rotation convention and shift checked numerically in the plan review; a unit test asserts
it). Meshes: Genua's wall-function family with a fixed 0.6 mm first layer, coa30 (8 mm surface spacing), **med30 (4 mm, primary)**, fine30 (2 mm); med30 is primary
because it is Genua's Green Med30 family and the family T2-0a ran, i.e. chosen knowing it matched. Wall resolved: wr2 (0.6 mm / 10 um). Steady simpleFoam, 5000
iterations, schemes and relaxation as in T2-0a. Cl = downforce coefficient, Cd drag, per unit span.

## 4. Experimental reference (frozen input; secondary source)

`data/t20/zerihan_zhang_cl_genua2009_fig6.json` from `scripts/t20b_digitize_genua_fig6.py` (Genua 2009 Fig. 6 red "Experimental" series; PDF SHA-256
f41cd300...0d41, not in the repository): h/c 0.671 0.9027, 0.448 1.0090, 0.313 1.1450, 0.224 1.2856, 0.179 1.3614, 0.134 1.3854, 0.09 1.3701.
Checks: the tabulated 1.286 and 1.371 are reproduced within 0.001; the two hidden markers (0.179, 0.134) agree to 0.0002 between the adjacent segments; Genua's
own grids then have mean errors (Med30SA 1.6 %, NFine35SA 1.8 %, Med40SA 3.7 %) that match his text (below 2 %, below 4 %). Uncertainty carried: +-0.005 Cl.
Limits: Genua re-plots Zerihan & Zhang; the experiment is a blunt-TE, finite-span wing with end plates; whether the plotted Cl is a balance or a mid-span pressure
value and which incidence the experiment used were not verified (the table's chord line is at about 3.45 deg, the listing is labelled 3.6 deg). No experimental Cp or
Cd is used. G2 is "agreement with the digitised Genua Fig. 6 curve", not with the primary experiment.

## 5. Kernels and cases

Per case (`case_result.json`): Cl, Cd tail statistics over the last 20 % of iterations; the **Cl plateau** = relative std and relative linear drift of the
20-iteration block means over that window both < 0.5 % (a period-2 alternation of the wall-function runs is averaged out); Cd plateau descriptive; checkMesh;
generator/mesh time and solver time; iterations to plateau (first iteration after which Cl stays within 0.2 % of the tail mean) and the time to it; y+ min/mean/max on
`airfoil` and `ground` (`simpleFoam -postProcess -func yPlus -latestTime`; outside 11-300 flagged, descriptive); cells, solver seconds per cell-iteration, peak RSS.
If the Cl plateau fails at 5000 iterations the case is continued once to 15000 (startFrom latestTime) and judged on the continuation.
d(mesh, h, s) = (Cl(+s) - Cl(-s)) / (2 s) per degree, each geometry meshed separately.

Kernel **W** (`cfd-opt-sdf-t20b-wf`, 4 concurrent cases, kernel budget 11 h, per-case cap 2.5 h). Smoke stage first (sa-wf and sst-wf on coa30 at h/c 0.224,
200 iterations, infrastructure gate as T2-0a), then 60 cases ordered by expected cost (fine30 first):
1. sa-wf sweep: {coa30, med30, fine30} x h/c {0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09}, 0 deg: 21.
2. sa-wf incidence: {coa30, med30, fine30} x h/c {0.224, 0.134, 0.09} x {-1, +1} deg: 18.
3. sa-wf step scan: med30 x h/c {0.224, 0.134} x {-0.5, -0.25, +0.25, +0.5} deg: 8 (with 0 and +-1 above: 7 incidences per height).
4. sst-wf (comparator): med30 sweep at the 7 heights (7) and med30 x {0.224, 0.134, 0.09} x {-1, +1} deg (6): 13.

Kernel **L** (`cfd-opt-sdf-t20b-lm`, 4 concurrent cases, kernel budget 11.5 h, per-case cap 11 h). Smoke stage: sa-wf on coa30, 200 iterations (gate only).
1. sst-lm on wr2 at h/c {0.224, 0.134, 0.09}: two stages in one case (2000 kOmegaSST iterations, then kOmegaSSTLM to iteration 14000 = 12000 LM iterations; the
   T2-0a period was 267-308 iterations, so the 2400-iteration tail holds about 8 cycles).
2. sa-wf on med30 at h/c 0.224, 0 deg (a second, separately meshed run of the kernel-W case: the negative control for the remeshing and session noise, |dCl| reported),
   followed by the adjoint: `adjointOptimisationFoam` singleRun on a copy started from the converged fields (300 primal + 5000 adjoint iterations), objective =
   downforce coefficient (direction (0 -1 0), Aref and UInf as forceCoeffs), frozen turbulence (`adjointLaminar`), `volumetricBSplines` box x in [-0.15c, 1.15c],
   y in [h/2, h + 0.4c], z one cell plus margins, 10 x 6 x 3 control points, degrees 3/3/2, no confinement (every control point with support on the section must be
   active), `sensitivityType surface`. Projections of the per-control-point derivatives (varID = 3 cp + component) onto rigid fields: rotation V = (-(y - y_LE), x - x_low)
   per radian (x_low from the manifest `x_lowest_m`, y_LE from `t20_case.airfoil_points`), x-translation (1, 0), y-translation (0, 1). The box is asserted to contain
   every section point and the derivative varIDs to cover every control point.

DAFoam: **not attempted** (`DAFOAM_NOT_ATTEMPTED`). Primary reason: R5 makes gradient-free screening the default and #23 parks gradient backends off the critical path;
#66 states that an adjoint is not a completion condition unless the chosen method needs it. Secondary (desk check from prior knowledge on 2026-10-19, no installation
attempted): DAFoam is distributed as a Docker image or built from source with its own patched OpenFOAM, PETSc and pyOptSparse; Kaggle offers no Docker and no
hash-locked binary package was identified. The adjoint item above (shipped in the locked v2512 packages) is the registered adjoint feasibility test. The narrowing of
T2-0 ("DAFoam feasibility" in the 2026-10-16 entry) is recorded in phase_plan with the result.

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20b.py`)

**Case classes** (analyzer): `VALID` (status COMPLETED, checkMesh reports no failed check, Cl plateau holds); `SOLVER_FAIL` (solver failure or timeout at the per-case
cap, NaN, no Cl plateau after the continuation); `MECHANICAL_FAIL` (generator, gmshToFoam or checkMesh failure: a defect of our pipeline, failing like SOLVER_FAIL
but named separately in the text); `INFRA_LOSS` (no `case_result.json`, `NOT_RUN_TIME_BUDGET`, `RUNNER_EXCEPTION`, kernel killed). A gate whose inputs include a
SOLVER_FAIL or MECHANICAL_FAIL case **fails**; one whose inputs include an INFRA_LOSS case (and no failure) is **undetermined**. A gate never uses a case it does not list.

**Consistency rule** for two derivatives or two increment sets (a, b): pass iff |a - b| <= max(tol * max(|a|, |b|), delta) with delta = max(0.01 per degree, 3 sigma_d);
any undefined quantity fails. sigma_mesh(h) = residual standard deviation of a quadratic fit of Cl(alpha) to the 7 sa-wf med30 incidences at h (h in {0.224, 0.134},
4 degrees of freedom); sigma_mesh at 0.09 = the larger of the two; sigma_d(h, s) = sigma_mesh(h) / (sqrt(2) s).

Gates (candidate sa-wf; e_h = Cl(h)/Cl_exp(h) - 1, med30, 0 deg):
- **G2 data level** (7 med30 sweep cases): mean |e_h| < 5.0 % AND the same with Cl_h + 0.15 deg x d(med30, h, 1) (experiment possibly at 3.6 deg; d interpolated
  linearly in h between 0.224, 0.134 and 0.09 and held at d(0.224) above 0.224; needs the 6 med30 +-1 deg cases) AND the peak: Cl(0.134) >= (1 - 0.005)
  max(Cl(0.179), Cl(0.09)) AND unimodal rise: Cl(h_next) >= (1 - 0.005) Cl(h) for each step from 0.671 down to 0.134. ("No oscillation" = the Cl plateau of VALID.)
- **G2d data differences** (same 7 cases): E = sum over the 6 adjacent-height increments |dCl_cfd - dCl_exp| / sum |dCl_exp| <= 0.30.
- **G3a mesh, level** (med30 and fine30 sweeps, 14 cases): max_h |Cl_fine30 / Cl_med30 - 1| <= 5.0 %.
- **G3b mesh, incidence derivative** (med30 and fine30, +-1 deg and 0 deg at h in {0.224, 0.134, 0.09}, 18 cases): consistency rule with tol 0.25 at each h; and
  the registered expected sign d(med30, 0.224, 1) > 0 (more incidence toward the ground, more downforce while attached); a wrong sign fails G3b.
- **G3c mesh, ride-height differences** (14 sweep cases): sum |dCl_fine30 - dCl_med30| / sum |dCl_med30| over the 6 increments <= 0.25.
- **G4 model** (sst-wf and sa-wf med30, +-1 deg and 0 deg at h in {0.224, 0.134}, 12 cases): consistency rule with tol 0.33 at each h. h/c 0.09 descriptive
  (excluded from the gate because separation there makes a wall-function model-form comparison the least meaningful; disclosed: T2-0a's largest SA-SST gap is at 0.09).
- **G5 cost** (valid sa-wf med30 cases): median over cases of (generation + meshing + checkMesh time + solver time to the Cl plateau) <= 15 min and maximum <= 30 min.
  Rationale: R5 needs about 32 designs (17 screening + 15 response-surface states) at about 3 ride heights, 96 evaluations, inside one 11 h session on 4 workers:
  <= 27.5 min each. The capped 5000-iteration wall time is reported but is not the evaluator cost.
- **G6 small step** (med30, h in {0.224, 0.134}, the 7-incidence scans): consistency rule with tol 0.25 between d(med30, h, 0.25) and d(med30, h, 1), with
  delta from sigma_d(h, 0.25), AND the +-0.25 deg change is resolved: |Cl(+0.25) - Cl(-0.25)| >= 5 sqrt(2) sigma_mesh(h). Also reported: sigma_mesh, sigma_d and the smallest incidence change resolved at 2 sqrt(2) sigma_mesh (E2-type) for M2/M3a/M4.

**Verdict** (exactly one). Gates are true, false or undetermined; the analyzer evaluates the verdict for every true/false assignment of the undetermined gates:
if all assignments give the same verdict it is reported, otherwise the verdict is `T20B_INCOMPLETE`.
- `T20B_GO_2D_SECTION`: G2, G2d, G3a, G3b, G3c, G4, G5, G6 all pass.
- `T20B_GO_2D_SECTION_DIFFERENCES`: all of them pass except G3a. Meaning: on med30, rigid incidence changes of 0.25-1 deg and ride-height changes between the 7
  heights are reproduced consistently across two meshes and two models and match the experiment's ride-height increments; the absolute Cl level is mesh dependent
  and not claimed. It says nothing about local or non-rigid shape modes and registers no minimum detectable gain.
- `T20B_NO_GO`: any other combination.
- `T20B_INCOMPLETE`: treated as not GO; #66 item 1 (high-Re evaluator) stays **blocked**, not NO-GO.

**Next actions** (pre-agreed, chosen by the first failing gates; recorded with the verdict):
| outcome | next action |
| --- | --- |
| GO_2D_SECTION or GO_2D_SECTION_DIFFERENCES | M4 may consider OpenFOAM SA-WF RANS for 2D-section scope; L3 additionally needs B5 (ProblemSpec), an SDF-to-mesh interface study and a scope decision on multi-element/3D |
| NO_GO with G2 or G2d failing | data agreement not reached: a wall-resolved or transition (LM) evaluator study, or a different validation case, before any high-Re evaluator |
| NO_GO with G3b, G3c or G6 failing | mesh-family or remeshing-noise problem: a y+/mesh-family study (fixed-topology morphing instead of remeshing) before reuse |
| NO_GO with only G4 failing | model-form uncertainty dominates: report a model band; M4 decides with it explicitly |
| NO_GO with G5 failing | cost: raise the backend trigger in STATE.md |
| MECHANICAL_FAIL in any gate input | generator defect: fix and re-register (a new study), not an amendment of the physics result |
| INCOMPLETE | one resubmission per section 8; if still incomplete, #66 item 1 stays blocked |

**Labels** (reported with the verdict, never changing it):
- G2 robustness: `ROBUST` if G2's mean-error parts also pass with the experiment shifted by -0.005 and +0.005 Cl, else `MARGINAL`. `G2_DISJOINT_OK` if mean |e_h| < 5 %
  on h/c 0.313 and 0.179 alone. `AGREEMENT_MESH_SPECIFIC` if the fine30 mean |e_h| >= 5 %. Fine30 and coa30 mean |e_h| and peak location are always printed.
- Replication (descriptive): max over the 5 shared heights |Cl_T2-0b / Cl_T2-0a - 1| (`REPLICATED` if <= 1 %).
- LM (kernel L): per case, the tail (last 20 % of the LM stage) cycle mean, the half-window means (stationary if they differ by < 1 %), the oscillation std.
  `LM_DATA_AGREES` if all 3 cases complete and are stationary, mean |e_h| over the 3 heights < 5 % and Cl(0.134) >= (1 - 0.005) max(Cl(0.224), Cl(0.09));
  `LM_NOT_QUALIFIED` otherwise; `LM_INCOMPLETE` for infrastructure. Single mesh, no mesh claim; its cost (about 2.4 h per case in T2-0a) excludes in-loop use.
- Adjoint: `ADJ_NOT_RUN` (binary missing or fatal before the first adjoint iteration), `ADJ_FAILED` (no finite derivative file or the box/varID assertions fail),
  `ADJ_RUNS` (finite; wall time reported), `ADJ_CONSISTENT` (ADJ_RUNS and |adj - FD| <= max(0.30 |FD|, 2 sigma_d(0.224, 1)) against d(med30, 0.224, 1) of kernel W,
  and the x-translation projection per mm is <= 0.1 x |rotation projection| per degree). Flag `ADJ_PRIMAL_UNCONVERGED` if the final initial residual of p, U or nuTilda
  in the adjoint's primal is above 1e-5. The y-translation projection is compared descriptively with (Cl(0.179) - Cl(0.313)) / ((0.179 - 0.313) c) from kernel W.
  The labels describe this implementation (frozen turbulence, wall functions, these dictionaries), not the capability of OpenFOAM's adjoint.
- Descriptive: coa30 values; Cd against Genua's CFD (no experimental Cd exists); absolute model spread max_h |Cl_sa - Cl_sst| / Cl_exp; curvature Cl(+1) - 2 Cl(0) + Cl(-1);
  y+; cells, cost per cell-iteration and RSS for each mesh (for 2.5D/3D extrapolation by M4); the negative-control |dCl|.

## 7. Claim ceiling and what #66/#67 may take

Allowed: the gates, labels and verdict with the numbers that produced them, for this 2D single-element section, this wing, Re_c 4.6e5, the stated meshes and models.
A GO satisfies only "2D single-element section evaluator candidacy at Re_c 4.6e5" in #66/#67. It is **not** the L3 evaluator prerequisite until B5 fixes the target
ProblemSpec (U, L, Re), it does not cover the SDF-to-mesh interface (the analytic coordinates here bypass the SDF; an extraction study is an M4/L3 prerequisite), and
it does not cover multi-element wings, slot flows, end plates, tip vortices, 3D, other Reynolds numbers or the full vehicle.
Not allowed: grid independence or convergence (two meshes of one family with a fixed first layer), any drag accuracy statement (Cd is compared with Genua's CFD only;
2D Cd has no induced drag), transition physics beyond the LM label, adjoint correctness beyond the ADJ labels, any statement about the SDF optimizer, Stage T/V rankings
or the Re 80 track, and any citation of T2-0a's own numbers.

## 8. Freeze, review, budget and stop rules

- Order: draft -> one plan review (three independent adversarial angles: numerical, controls, strategy) -> revision recorded in section 10 -> **freeze 1** ->
  implementation (`scripts/`, `tests/`, `infra/kaggle/kernel_t20b_cpu/` only; T2-0a files untouched; the analyzer tested on synthetic fixtures covering every gate,
  every verdict branch and the undetermined enumeration) -> development smoke on Kaggle (mode `smoke`, at most 3 submissions) -> one source review -> **freeze 2** ->
  kernels W and L submitted once each.
- Development smoke: a mesh-only pass (generator, gmshToFoam, boundary fix, checkMesh, no solver) over every registered geometry of both kernels, plus each solver path
  at <= 200 iterations (sa-wf at a non-zero incidence, sst-wf, sst-lm with the stage switch, the plateau continuation, yPlus, and an adjoint mini-run with its box and
  varID assertions). Force, coefficient and derivative values are deleted on the kernel before output; only statuses, iteration counts, wall times, checkMesh results
  and assertion outcomes are kept. A smoke failure is a pre-freeze defect, fixed before freeze 2.
- Resubmission: one identical resubmission (same commit, same rendered kernel) per kernel, only for INFRA_LOSS. The analyzer then takes each case from the first run if
  present there, otherwise from the second; both runs are archived and reported.
- Amendment (`REGISTERED_AMENDED`): only for a defect that prevents a pre-specified quantity from being computed, filed on #57 before any verdict-relevant output is
  read, never touching a rule or threshold; at most one per kernel; the original run's verdict (or INCOMPLETE) is kept and published beside the amended one.
  A case-level result (no plateau, divergence, a slow case, an unexpected value) is a result, never a reason to rerun or amend.
- Compute budget, Kaggle CPU only: at most 3 smoke + 2 registered + 2 resubmission + 2 amendment sessions. If a registered run class cannot fit a Kaggle session
  (a case at its cap with the rest of the kernel not finishing), stop and report it as a backend trigger (STATE.md) instead of changing the run.
- Analysis: `scripts/analyze_t20b.py` (frozen at freeze 2) is run once on the downloaded outputs; its `analysis.md` and `verdict.json` are committed unchanged; any later
  reading is a dated, separate note.

## 9. Outputs

`docs/evidence/t20b_registered_2026_10_19/`: `freeze.json`, the smoke record, kernel logs, the downloaded outputs (copied from a fresh empty download directory),
`SHA256SUMS` (checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`; updates to `docs/STATE.md` (T2-0 row), `docs/phase_plan.md`, and a
result comment on #57.

## 10. Plan review record

One plan review, three independent adversarial sonnet subagents on draft 8b01545b (2026-10-19): numerical (14 findings), controls (15), strategy (12).
Accepted (A), partly accepted (P) or rejected (R); the change is in the text above.

Numerical:
- N1 A: validity on the Cl plateau of 20-iteration block means (T2-0a Cd rel. std was 0.2-0.33 % from a period-2 alternation); Cd descriptive; a failed case fails only the gates that list it.
- N2 A: 7-incidence scans at h/c 0.224 and 0.134 (sa-wf med30); sigma_mesh from the quadratic-fit residual (gmsh's own run-to-run change is about 4 cells in 14.7k, so remeshing at a new incidence is the noise that matters). Resubmission keeps the first run's cases (N14).
- N3 A: one continuous consistency rule with delta = max(0.01, 3 sigma_d) replaces the near-zero cliff.
- N4 A: G5 on the time to the Cl plateau (plus meshing); capped time reported only.
- N5 A: LM shortened to 12000 LM iterations at 3 heights, judged on cycle-mean stationarity (half-window means), oscillation reported.
- N6 A: adjoint mini-run in the development smoke with box/varID assertions; `confineWMovement` dropped. The adjoint moved to kernel L (also S6).
- N7 A: ADJ_PRIMAL_UNCONVERGED flag, tolerance max(0.30 |FD|, 2 sigma_d), x-translation null check, y-translation descriptive check.
- N8 A: +-0.25/0.5 deg steps; G6 compares the +-0.25 and +-1 deg derivatives and requires the +-0.25 deg change to be resolved.
- N9 A: G4 tolerance 33 % with the continuous rule.
- N10 A: projection inputs pinned (x_low from the manifest, y_LE from airfoil_points), box containment and varID coverage asserted.
- N11 A: yPlus post-processing, descriptive flag outside 11-300.
- N12 A: peak with a 0.5 % tolerance and a unimodal-rise check; "no oscillation" mapped to the Cl plateau.
- N13 A: +-0.005 digitisation band as the ROBUST/MARGINAL label; incidence handled in G2 itself (C12/S8).
- N14 A: see N2 and section 8.

Controls:
- C1 A: case classes, explicit gate inputs, true/false/undetermined gates and the enumeration rule for INCOMPLETE; undefined quantities fail.
- C2 A: verdict renamed and its meaning restricted to rigid incidence and ride-height differences; ride-height increments added as G2d (data) and G3c (mesh); h/c 0.09 added to G3b; no minimum detectable gain registered.
- C3 A: sa-wf is the sole candidate, sst-wf a comparator (no OR over candidates, no tie-break); predictions per gate recorded; G5 made binding (15 min) on a stated need; the 10 % maximum-error rule dropped; tolerances labelled as registrant choices with their basis.
- C4 A: Genua's criterion recorded with page in `data/t20/genua2009_green_criterion.json`; G2 now mean |e| plus peak plus no oscillation, no invented maximum.
- C5 A: tolerance form of the peak (with N12).
- C6 A: T2-0a stays non-citable; G2_DISJOINT_OK label; descriptive replication label; `thresholds_set_after_exploratory_visible` in verdict.json.
- C7 A: med30 choice disclosed; AGREEMENT_MESH_SPECIFIC label; fine30/coa30 errors always printed.
- C8 P: negative control as one separately meshed duplicate in kernel L; expected sign registered at h/c 0.224 only (separation at 0.134/0.09 makes a prior sign unsafe); the rotation geometry is checked by a unit test, not per case (it is a pure function of the pinned generator); curvature stays descriptive (G6 covers linearity); analyzer fixtures for every branch required.
- C9 A: smoke suppresses all force/derivative values; mesh-only pass over every geometry; adjoint mini-run; ADJ labels describe this implementation.
- C10 A: resubmission fill-in rule, amendment limits, amendment sessions in the budget, DRAFT_FROZEN_PLAN until freeze 2, the text governs.
- C11 A: verdict names carry the 2D-section scope; "what #66/#67 may take" paragraph; H2 reworded.
- C12 A: G2 must pass also with the +0.15 deg incidence shift; ROBUST/MARGINAL label for the digitisation band; G2 titled as agreement with the digitised secondary curve.
- C13 P: 0.09 stays descriptive in G4 with the reason stated (not hidden).
- C14 A: LM labels renamed (LM_DATA_AGREES / LM_NOT_QUALIFIED); tie-break removed with the single candidate.
- C15 A: G5 over valid cases only; CPU model recorded per kernel.

Strategy:
- S1 A: G2d (increments against the experiment) gates both GO levels.
- S2 A: step scan and sigma_d (with N2/N8); the smallest resolved incidence is reported for M2/M3a/M4.
- S3 R (scope): no SDF extraction control in T2-0b; the GO explicitly excludes the SDF-to-mesh interface and names it an M4/L3 prerequisite (section 7).
- S4 P: mesh-only pass over every geometry in the smoke (accepted); plateau continuation to 15000 iterations (accepted); MECHANICAL_FAIL named separately (accepted) but still failing its gates (fail-closed).
- S5 A: next-action table; INCOMPLETE keeps #66 item 1 blocked.
- S6 P: the adjoint moved to kernel L so it cannot cost kernel W; LM and the adjoint stay registered as secondary labels (rejected moving them to exploratory) because #57's deliverable names the adjoint feasibility and LM convergence, and labels do not touch the verdict.
- S7 A: scope in the verdict names; cells, cost per cell-iteration and RSS reported per mesh; multi-element named as untested.
- S8 A: incidence handled inside G2 (with C12).
- S9 P: G3b extended to 0.09 and G4 tightened (accepted); a monotone coa30-med30-fine30 requirement rejected (coa30 is outside Genua's usable range for SA and the family refines only surface and core at a fixed first layer); coa30 incidence cases kept descriptive.
- S10 A: G5 tied to the R5 design count at 3 ride heights.
- S11 A: DAFoam reason rewritten (R5, #23, #66) with a dated desk check; the narrowing goes into phase_plan.
- S12 A: drafts of `scripts/t20b_adjoint.py`, `scripts/build_t20b_kernel.py` and `infra/kaggle/kernel_t20b_cpu/` existed uncommitted during the review; they are first committed after freeze 1 and changed to this text.
