# T2-0b registered feasibility study (#57): 2D ground-effect wing RANS evaluator go/no-go

Registration status (PROC-01): **REGISTERED_FROZEN** once the freeze record (SHA-256 of this file, posted on #57 and in
`docs/evidence/t20b_registered_2026_10_19/freeze.json`) exists; until then DRAFT. Evidence class of the result: descriptive numerical and
capability evidence for a 2D section; the verdict is a feasibility go/no-go that feeds M4 (#66) and L3 (#67). All qualification flags stay false;
`shape_update_allowed=false`; nothing here changes them.

## 1. Question and hypotheses

Question: can a body-fitted 2D steady RANS evaluator (OpenFOAM v2512, Kaggle CPU) of the Zerihan & Zhang single-element wing in ground effect
(Tyrrell 026, Re_c = 4.6e5, moving ground) serve as a candidate evaluator for an FSAE-physics optimizer: is it fast enough, close enough to the
published experiment, stable under mesh refinement and turbulence-model change, and does a design change (rigid incidence change) move it consistently?

- H1 (data): with a wall-function model on the registered primary mesh, Cl(h/c) at 7 ride heights agrees with the experiment by Genua's own "Green"
  criterion (mean |error| < 5 %, maximum downforce at h/c = 0.134, no oscillation).
- H2 (mesh): the absolute Cl changes by <= 5 % from the primary mesh (med30) to the finer surface mesh (fine30), and the design derivative
  dCl/dalpha changes by <= 25 %.
- H3 (model): SA and k-omega SST (both wall functions) give the same sign and a magnitude within a factor 2 for dCl/dalpha.
- H4 (cost): one case costs <= 30 min (median) on one of four concurrent Kaggle CPU workers.
Secondary, reported with their own pre-set labels but never changing the verdict: transition-model (kOmegaSSTLM) convergence and data agreement,
adjoint (adjointOptimisationFoam) feasibility, DAFoam feasibility.

## 2. What was visible before this registration (and what is used)

- T2-0a (EXPLORATORY_COMMITTED, 242e4bd, `docs/evidence/t20a_exploratory_2026_10_16/`) was fully visible: SA-WF med30 Cl within about 5 % of the
  experiment at h/c 0.224 and 0.09, peak at 0.134; SST-WF +9/-11 %; SST->LM not plateaued; about 6 min per wall-function case, about 2.4 h per LM case.
  **The thresholds below were chosen after seeing T2-0a.** To limit tuning, the data thresholds are Genua's published Green criterion (Genua 2009, paper 1,
  section on the second-stage categorisation: average error below 5 %, maximum at h = 0.134c, no oscillation), the mesh and model thresholds are round
  numbers set from the size of a usable design signal, and the cost threshold from the Kaggle 12 h session (below).
- Applied to T2-0a med30 (5 heights, against the digitised curve of section 4): SA-WF mean |e| 4.0 % (max 5.5 %), peak at 0.134; SST-WF mean 7.8 %
  (max 10.9 %); LM (not plateaued, 3 heights) 4.6 % (max 8.9 % at 0.134). So H1 is expected to be close to its threshold for SA-WF and to fail for SST-WF.
- Genua's own appendix table (visible): Fine30SA / Med30SA - 1 = +3.7 ... +12.5 % over the 7 heights (+7.9 % at 0.224). If our gmsh meshes behave like
  his, **H2 (absolute) is expected to fail**; the verdict scheme below therefore separates an absolute-level GO from a differences-only GO before any run.
- **No T2-0a number enters any rule.** The verdict uses only cases run by the frozen T2-0b kernels. 5 of the 7 med30 heights repeat T2-0a's
  conditions (a registered replication, not disjoint data); h/c 0.313, 0.179, the coa30/fine30 meshes, the incidence changes, the LM length and the adjoint are new.
- No T2-0b solver output exists at registration. Development smoke runs before the code freeze (section 8) run at most 200 iterations and their force
  values are neither tabulated nor read.

## 3. Case (unchanged from T2-0a; generator reused by hash, not edited)

`scripts/t20_case.py` and `scripts/t20_foam.py` (the T2-0a files, pinned by SHA-256 in the new kernel, not modified) generate every case:
Tyrrell026S coordinates (Genua 2009 Table 1, sharpened TE), chord 0.2234 m, U = 30 m/s, nu = 1.457e-5 m2/s, Tu 0.3 %, length scale 1 cm, ground moving
at U, domain 2c/5c/6.8c, one-cell extrusion; h = distance from the lowest suction-surface point to the ground. Incidence change `--delta-alpha-deg`
rotates the section counter-clockwise about the LE (LE toward the ground = +) and then re-imposes h (so the design change is a rigid rotation at fixed ride height).
Meshes (Genua's wall-function family, fixed first layer 0.6 mm, y+ about 30): coa30 (8 mm surface spacing), **med30 (4 mm, primary)**, fine30 (2 mm);
wall resolved: wr2 (0.6 mm / 10 um). Steady simpleFoam, schemes and relaxation as in T2-0a; Cl = downforce coefficient, Cd drag, per unit span.

## 4. Experimental reference (frozen input)

`data/t20/zerihan_zhang_cl_genua2009_fig6.json`, produced by `scripts/t20b_digitize_genua_fig6.py` from Genua 2009 Figure 6 (red "Experimental" series;
PDF SHA-256 f41cd300...0d41, not in the repository). Values (Cl): h/c 0.671 0.9027, 0.448 1.0090, 0.313 1.1450, 0.224 1.2856, 0.179 1.3614,
0.134 1.3854, 0.09 1.3701. Checks: the two tabulated values (1.286, 1.371) are reproduced within 0.001; the two markers hidden under black symbols
(0.179, 0.134) are taken from the adjacent red segments, which agree to 0.0002; with these values Genua's own Med30SA mean error is 1.6 %, NFine35SA 1.8 %,
Med40SA 3.7 %, matching his text ("below 2 %", "below 4 %"). Limits: secondary source (Genua re-plots Zerihan & Zhang); the experiment is a blunt-TE,
finite-span wing with end plates; whether the plotted Cl is a balance or a mid-span pressure value was not verified; the incidence used in the experiment
was not verified from the primary source (the coordinate table is at about 3.45 deg chord-line angle, the listing is labelled 3.6 deg). No experimental
Cp or Cd is used (Genua plots no experimental Cp in a usable form and has no experimental Cd).

## 5. Measured quantities and cases

Per case (kernel `case_result.json`): Cl, Cd tail mean over the last 20 % of iterations (at least 50 rows); force plateau = relative std and relative
linear drift over that window both < 0.5 % for Cl and Cd; checkMesh result; wall time (generator start to solver end) per case; iterations.
dCl/dalpha = (Cl(+1 deg) - Cl(-1 deg)) / 2 per degree (central difference, same mesh spec, each geometry meshed separately).

Kernel **W** (`cfd-opt-sdf-t20b-wf`, wall functions, 4 concurrent cases, 5000 iterations each, kernel budget 11 h, per-case solver cap 2.5 h):
1. Sweep: {sa-wf, sst-wf} x {coa30, med30, fine30} x h/c {0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09} at delta alpha 0: 42 cases.
2. Incidence: {sa-wf, sst-wf} x {coa30, med30, fine30} x h/c {0.224, 0.134} x delta alpha {-1, +1} deg: 24 cases.
3. Adjoint: after sa-wf / med30 / h/c 0.224 / 0 deg completes, `adjointOptimisationFoam` (singleRun) on a copy restarted from that converged primal
   (300 more primal iterations, 5000 adjoint iterations), objective = downforce coefficient (direction (0 -1 0), same Aref/UInf as forceCoeffs), frozen
   turbulence (`adjointLaminar`), design variables `volumetricBSplines` (box around the section, z movement confined, boundary control points not confined,
   `sensitivityType surface`). The rigid-rotation derivative is the projection of the per-control-point derivatives onto the rigid velocity field
   V(x, y) = (-(y - y_LE), x - x_low) per radian (rotation about the LE plus the vertical shift that keeps the lowest point at h; exact for a rigid motion of
   the section because the B-spline basis is a partition of unity), converted to per degree.
Order: smoke stage first (sa-wf and sst-wf on coa30 at h/c 0.224, 200 iterations; infrastructure gate as in T2-0a), then the 66 cases ordered by expected
cost (fine30 first), then the adjoint.

Kernel **L** (`cfd-opt-sdf-t20b-lm`, 4 concurrent cases, kernel budget 11.5 h, per-case cap 11 h): sst-lm on wr2 at h/c {0.224, 0.179, 0.134, 0.09},
two stages in one case as in T2-0a (2000 kOmegaSST iterations, then kOmegaSSTLM to iteration 20000, i.e. 18000 LM iterations; T2-0a ran 8000);
plateau and tail statistics over the last 20 % of the LM stage. Smoke stage: sa-wf on coa30, 200 iterations (infrastructure gate only).

DAFoam: **not attempted** (needs its own compiled OpenFOAM/PETSc/pyOptSparse stack or Docker; no hash-lockable Kaggle-installable package was identified). The adjoint item above,
which ships in the locked v2512 packages, is the registered adjoint feasibility test. This is recorded as `DAFOAM_NOT_ATTEMPTED`, not as a failure of DAFoam.

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20b.py`, written before any registered run)

Notation: e_h = Cl(h)/Cl_exp(h) - 1 on med30 at delta alpha 0; d(mesh, h) = dCl/dalpha per degree. A case is **valid** if its status is COMPLETED,
checkMesh reports no failed check, and the force plateau holds. Near-zero guard for a derivative pair (a, b): if |a| < 0.02 and |b| < 0.02 per degree
the pair passes iff |a - b| <= 0.01 per degree, otherwise the ratio rule applies.

Per candidate C in {sa-wf, sst-wf}:
- **G1 completion**: every case of C on med30 and fine30 (7 sweep + 4 incidence each, 22 cases) is valid. An invalid case (no plateau, checkMesh failure,
  solver failure) fails G1; a missing case caused by infrastructure makes the study INCOMPLETE (below).
- **G2 data** (med30, 7 heights): mean |e_h| < 5.0 %, max |e_h| <= 10.0 %, and argmax_h Cl(h) = 0.134.
- **G3a mesh, absolute**: max over the 7 heights of |Cl_fine30(h) / Cl_med30(h) - 1| <= 5.0 %.
- **G3b mesh, design derivative**: for h in {0.224, 0.134}: sign d(fine30, h) = sign d(med30, h) and |d(fine30, h) / d(med30, h) - 1| <= 0.25.
- **G5 cost**: over C's 11 med30 cases, median wall time <= 30 min and maximum <= 45 min (four concurrent cases on the Kaggle CPU image).
  Rationale: a 12 h session then holds at least 4 x 11 h / 0.5 h = 88 evaluations, enough for one screening plus response-surface round of the R5 type.
- Candidate label: `PASS_FULL` if G1, G2, G3a, G3b, G5 pass; `PASS_DIFFERENCES` if G1, G2, G3b, G5 pass and G3a fails; `FAIL` otherwise.

Global:
- **G4 model**: for h in {0.224, 0.134} on med30: sign d(sst-wf, h) = sign d(sa-wf, h) and 0.5 <= d(sst-wf, h) / d(sa-wf, h) <= 2.0 (near-zero guard
  applies). Requires the 8 med30 incidence cases and the 4 matching sweep cases of both models to be valid; otherwise G4 fails.

Verdict (exactly one):
- `T20B_GO`: G4 passes and at least one candidate is PASS_FULL.
- `T20B_GO_DIFFERENCES_ONLY`: G4 passes, no candidate is PASS_FULL, at least one is PASS_DIFFERENCES. Meaning: the evaluator may be used for paired
  differences (design ranking) on the registered mesh; its absolute Cl level is mesh dependent and is not claimed.
- `T20B_NO_GO`: all required data present and neither of the above.
- `T20B_INCOMPLETE`: a required case is missing for an infrastructure reason after the one permitted resubmission (section 8). Treated as not GO.
Recommended evaluator for M4 (only on a GO verdict): the passing candidate with the better label (FULL over DIFFERENCES), ties broken by the smaller mean |e_h|.

Secondary labels (reported, never change the verdict):
- LM (kernel L): `LM_VERIFY_CANDIDATE` if all 4 cases are valid, mean |e_h| over the 4 heights < 5.0 % and argmax over the 4 heights = 0.134;
  `LM_NOT_QUALIFIED` otherwise; `LM_INCOMPLETE` for infrastructure. Its cost alone excludes it from the in-loop evaluator role if a case exceeds 45 min.
  Single mesh only: no mesh sensitivity is claimed for LM.
- Adjoint: `ADJ_NOT_RUN` (binary missing or fatal before the first adjoint iteration), `ADJ_FAILED` (no finite derivative file),
  `ADJ_RUNS` (finite derivatives; wall time reported), `ADJ_CONSISTENT` (ADJ_RUNS and the projected derivative has the sign of the central FD
  d(med30, 0.224) of sa-wf and |adjoint / FD - 1| <= 0.30). Frozen turbulence and wall functions make a disagreement plausible; it is reported, not interpreted.
- Incidence ambiguity: 0.15 deg x |d(med30, h)| / Cl(h) at h in {0.224, 0.134} is reported; if it exceeds 2.5 % the G2 result is labelled "incidence-limited" (verdict unchanged).
- Descriptive only: coa30 values, Cd versus Genua (no experimental Cd exists), absolute model spread max_h |Cl_sa - Cl_sst| / Cl_exp, curvature
  Cl(+1) - 2 Cl(0) + Cl(-1), timing of every mesh and of LM and adjoint.

## 7. Claim ceiling

Allowed after the run: the labels and verdict above with the numbers that produced them, for this 2D section, this wing, Re_c 4.6e5, the stated meshes and models.
Not allowed: any 3D, finite-span, end-plate, tip-vortex, multi-element or full-vehicle statement; FSAE qualification; grid independence or grid convergence
(the wall-function family fixes the first layer, so med30 -> fine30 refines only the surface and core); any drag accuracy statement (Cd is compared with
Genua's CFD only, never with experiment; 2D Cd has no induced drag); transition physics beyond the LM label; adjoint correctness beyond the ADJ label;
any statement about the SDF optimizer, Stage T/V rankings, or the Re 80 track. A GO is an input to M4, not an adoption decision.

## 8. Freeze, review, budget and stop rules

- Order: this draft -> one plan review (three independent adversarial angles: numerical, controls, strategy) -> revision with each finding accepted or
  rejected in section 10 -> **freeze 1** (this file's SHA-256 on #57) -> implementation (`scripts/`, `tests/`, `infra/kaggle/kernel_t20b_cpu/` only;
  T2-0a files untouched) -> development smoke on Kaggle (mode `smoke`, at most 3 submissions, <= 200 iterations, force values not read) -> one source review
  -> **freeze 2** (source commit and SHA-256 of the kernel template, builder, analyzer, adjoint module, generator files on #57) -> kernels W and L submitted once each.
- Resubmission: one identical resubmission (same commit, same rendered kernel) per kernel, only for an infrastructure failure (Kaggle error, install or
  network failure, kernel killed). Any code change after freeze 2 is `REGISTERED_AMENDED`, recorded on #57 with its reason before the rerun, at most one
  amendment per kernel; a case-level result (no plateau, divergence, slow case) is a result, never a reason to rerun.
- Compute budget: at most 3 smoke + 2 registered + 2 resubmitted kernel sessions, Kaggle CPU only. If a registered run class cannot fit a Kaggle
  session (a case at its cap with the rest of the kernel not finishing), stop and report it as a backend trigger (STATE.md) instead of changing the run.
- Analysis: `scripts/analyze_t20b.py` is frozen at freeze 2 and run once on the downloaded outputs; its `analysis.md` and `verdict.json` are committed
  unchanged. Any later reading is added as a dated, clearly separate note.

## 9. Outputs

`docs/evidence/t20b_registered_2026_10_19/`: `freeze.json`, the kernel logs, the downloaded kernel outputs (copied from a fresh empty download directory),
`SHA256SUMS` (checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`; updates to `docs/STATE.md` (T2-0 row), `docs/phase_plan.md`, and a result comment on #57.

## 10. Plan review record

(filled after the plan review, before freeze 1)
