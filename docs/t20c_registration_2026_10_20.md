# T2-0c registered study (#57): fixed-topology morphing and a four-level mesh series for the 2D ground-effect wing-section RANS evaluator

Registration status (PROC-01): `DRAFT` -> `DRAFT_FROZEN_PLAN` at freeze 1 (SHA-256 of this file posted on #57) -> **`REGISTERED_FROZEN`** at freeze 2
(source commit and hashes of the kernel template, builder, analyzer, generator and morph files posted on #57 and in
`docs/evidence/t20c_registered_2026_10_20/freeze.json`). Evidence class of the result: descriptive numerical evidence for one 2D section.
The verdict feeds M4 (#66) and the M3a NO-GO branch only within the scope in section 7. All qualification flags stay false; `shape_update_allowed=false`.
**This text governs; a disagreement between it and the frozen analyzer is a defect of the analyzer.**

## 1. Question, origin and scope

T2-0b (`docs/t20b_registration_2026_10_19.md`, verdict `T20B_NO_GO`, `docs/evidence/t20b_registered_2026_10_19/`) failed G2 (data level), G3b (incidence
derivative between med30 and fine30 at h/c 0.09: 0.055 vs 0.082 per deg) and G6 (+-0.25 deg not resolved at h/c 0.134: sigma_mesh 0.0048). Its pre-agreed
next action for G3b/G6 is this study: a mesh-family / remeshing-noise study with fixed-topology morphing instead of remeshing. Questions:

- **Q1 (verdict).** If incidence is changed by moving the nodes of one baseline mesh (same connectivity) instead of remeshing, how far does the difference noise
  sigma fall, and do the T2-0b difference gates G6 (+-0.25 deg) and G3b (incidence derivative agreement between meshes) pass?
- **Q2 (registered labels).** On a four-level series (coa30, med30, fine30 and a new xfine30), do the Cl level, the location of the Cl maximum and the incidence
  derivative show a converging trend, and can the G2 peak failure of med30 be attributed to mesh resolution?
- **Q3 (descriptive labels).** If small camber-type shape changes are applied by the same morph, is the Cl change resolved (a touchstone for an optimiser's
  evaluator)?

Out of scope (decided at registration): LM (about 3.5 h per case with a limit cycle in T2-0b) and any adjoint retry. Whether a wall-resolved/LM evaluator study or
a different validation case is needed for the G2 failure is **decided at the next stage with this study's results** (Q2 labels), not here.
Candidate: SA with wall functions (sa-wf), as T2-0b. No other turbulence model runs (T2-0b G4 passed).

## 2. What was visible before this registration (and how it is used)

- **All T2-0a and T2-0b results.** The gate tolerances below are T2-0b's, reused unchanged (consistency tol 0.25, delta floor 0.01 per deg, resolution factor
  5 sqrt(2), the sigma estimator, the 0.5 % peak tolerance); they were chosen in T2-0b after T2-0a, and **are applied here after T2-0b's numbers were visible**
  (`thresholds_set_after_t20b_visible: true` is written into `verdict.json` and must accompany any citation). New elements (G7m, the level structure of the
  verdict, the xfine30 level, the morph definition, the Q2/Q3 labels) were designed knowing T2-0b's numbers.
- **Local mesh-only morph prototype (2026-10-20, no solver, no force).** The morph of section 4 was tried locally (gmsh 4.15.2, macOS) on coa30/med30/fine30/xfine30
  at h/c 0.224/0.134/0.09 and +-1 deg: no inverted cell, cell-area ratios 0.84-1.16, the local checkMesh proxy (`t20_case.mesh_quality`) passes on every morphed
  mesh with essentially the baseline values, the morphed contour equals the generator's target contour to 2e-16 m, xfine30 has 47.8-49.3k cells. The
  blending design was not changed after this check.
- **No T2-0c solver output exists at registration.** The development smoke (section 8) suppresses all force and coefficient values.
- **Predictions at registration** (also in `verdict.json` as `predicted`): G6m pass on med30 and fine30 (morphing removes the remeshing jumps that made
  sigma_mesh 0.0023-0.0048); G3bm(med30) **fail** at h/c 0.09 (the T2-0b difference 0.026 per deg was 7.7 sigma_d of the remeshing noise, so it is a resolution
  difference that morphing does not remove); G3bm(fine30) uncertain; G7m pass at 0.224/0.134, uncertain at 0.09; verdict GO_FINE30 or NO_GO with roughly equal
  odds, GO_MED30 unlikely; the remeshed coa30/med30/fine30 cases reproduce T2-0b bit for bit (deterministic pipeline); PEAK label uncertain; shape modes
  resolved at +-0.25 mm.
- **Data reuse.** No T2-0a or T2-0b number enters any gate or label input except the descriptive replication label (section 6). The coa30/med30/fine30 remeshed
  cases repeat T2-0b conditions; they are new runs, and their agreement with T2-0b is a replication label, not evidence of anything else.

## 3. Case (generators reused by hash)

`scripts/t20_case.py` and `scripts/t20_foam.py` (pinned, unchanged) generate every baseline and every remeshed case exactly as in T2-0b (Tyrrell026S, chord
0.2234 m, U 30 m/s, Re_c 4.6e5, moving ground, Tu 0.3 %, domain 2c/5c/6.8c, steady simpleFoam, 5000 iterations, schemes and relaxation as T2-0b;
incidence = rotation about the LE, LE toward the ground positive, then h re-imposed at the lowest suction-surface point; Cl = downforce coefficient).
A new module `scripts/t20c_case.py` (a) registers the mesh level **xfine30** and (b) implements the morph (section 4); it does not modify the pinned files.

Mesh levels (Genua's wall-function family: fixed first layer y1 = 0.6 mm, growth 1.2, sharp-TE fan; surface spacing halves per level):
coa30 8 mm, med30 4 mm, fine30 2 mm, **xfine30 1 mm** (new). The family's last layer follows the equal-area rule 0.433 ds, which for ds = 1 mm (0.43 mm) is below
the fixed first layer; xfine30 therefore has a single wall layer (`last = 0.6`, i.e. y1/ds). Layer stacks at h/c 0.09: coa30 7 (capped by 0.4 gap), med30 7,
fine30 4, xfine30 1. The series is **not a systematic refinement** (fixed first layer, the layer stack changes with ds): Q2 labels describe trends of this family,
never grid convergence.

## 4. Morph (fixed topology)

For each (mesh, h) one **baseline** mesh is generated at delta alpha = 0 by the pinned generator. A morphed case takes the baseline `mesh.msh` (gmsh 2.2 ascii,
canonical node order) and rewrites only the x, y of every node (z untouched, both extrusion planes alike); the node numbering, the element list and the physical
groups are byte-identical, so gmshToFoam produces the same cells, faces and patches. The OpenFOAM dictionaries are the baseline's (they do not depend on geometry).

Displacement D(p) of a node p (2D):
- **Incidence delta alpha:** the generator's own transformation, p -> T1 + Rot(delta alpha)(p - T0), with T0, T1 the trailing-edge points of the generator contours
  `airfoil_points(h, 0)` and `airfoil_points(h, delta alpha)` and Rot the generator's rotation. The mapped baseline contour equals the target contour (asserted
  <= 1e-9 m): the morphed and the remeshed case have the same section geometry and differ only in the mesh.
- **Camber-type shape modes** (Q3), in the chord frame of the baseline contour (LE = contour point of the LE, TE = contour point 0, c_hat = unit LE->TE,
  n_hat = c_hat turned +90 deg, i.e. away from the ground; xi(p) = (p - LE).c_hat / |TE - LE|):
  `camber`: D_s = -a 4 xi (1 - xi) n_hat for 0 <= xi <= 1, 0 otherwise (a > 0: mid-chord toward the ground, more inverted camber);
  `flap`: D_s = +a g(xi) n_hat, g = ((xi - 0.7)/0.3)^2 on [0.7, 1], 1 for xi > 1, 0 for xi < 0.7 (a > 0: trailing edge away from the ground).
  Both move suction and pressure surfaces equally (thickness unchanged). Then h is re-imposed: D = D_s + (0, s), s = h - min over the suction contour points of
  (q + D_s(q))_y. Amplitudes a in {-0.5, -0.25, +0.25, +0.5} mm.
- **Blending:** p' = p + w(p) D(p), with d_a = distance to the baseline contour polyline, b = the base mesh's layer-stack thickness (manifest `bl_thickness_m`;
  it is both the airfoil stack and the ground-block height), r = max(d_a - b, 0), d_f = max(min(y - b, x - x_inlet, x_outlet - x, y_top - y), 0),
  phi = r / (r + d_f), w = 1 - phi^2 (3 - 2 phi); w = 0 for y <= b. The airfoil layer stack moves rigidly with the section, the ground block and the outer
  boundaries do not move, the triangles in between absorb the motion. The wake-refinement line of the size field stays where the baseline put it (the TE moves
  about 3 mm at +-1 deg); G7m measures the consequence.
- **Asserted per morph (failure = `GENERATOR_FAILED`, i.e. MECHANICAL_FAIL):** no 2D cell changes the sign of its area; ground-block, inlet, outlet and top nodes
  are unmoved; contour error <= 1e-9 m (incidence). Recorded: min/max cell-area ratio, the local quality proxy, TE displacement, the baseline mesh SHA-256.

## 5. Kernels and cases (OpenFOAM v2512, Kaggle CPU, 4 concurrent cases, as T2-0b)

Notation: Cl_R(M, h, delta) = remeshed (kernel R), Cl_M(M, h, delta) = morphed from the kernel-M baseline (delta = 0: that baseline itself), M in
{coa30, med30, fine30, xfine30}, scan heights H = {0.224, 0.134, 0.09}, scan incidences {-1, -0.5, -0.25, 0, +0.25, +0.5, +1} deg.

Kernel **R** (`cfd-opt-sdf-t20c-remesh`, 100 cases, kernel budget 11 h, per-case cap 2.5 h): sweep 4 meshes x 7 heights {0.671, 0.448, 0.313, 0.224, 0.179,
0.134, 0.09} at 0 deg (28); remeshed scans 4 meshes x H x 6 nonzero incidences (72). Estimated 4.1 h on 4 workers (xfine30 about 20 min per 5000 iterations).
Kernel **M** (`cfd-opt-sdf-t20c-morph`, 132 cases, budget 11 h, cap 2.5 h): a base stage generates the 12 baseline meshes (4 meshes x H) once; then the 12
baselines are solved, 72 morphed incidence cases (4 x H x 6), 48 shape cases (2 modes x 4 amplitudes x {med30, fine30} x H). Estimated 5.1 h.
Smoke stage in each kernel first (infrastructure gate as T2-0b, sa-wf coa30 h/c 0.224, 200 iterations). Case records, the Cl plateau (20-iteration block means
over the last 20 %, relative std and drift < 0.5 %), the one continuation to 15000 iterations, y+ and costs are T2-0b's (runner fork).

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20c.py`)

**Case classes** and **gate input rule** exactly as T2-0b section 6 (VALID / SOLVER_FAIL / MECHANICAL_FAIL / INFRA_LOSS; a failed input fails the gate, an
infrastructure loss alone makes it undetermined; the verdict is enumerated over undetermined gates; any undefined quantity fails).
sigma_X(M, h) = residual standard deviation of a quadratic fit of Cl_X(M, h, .) over the 7 scan incidences (4 dof), X in {R, M}; sigma_d = sigma / (sqrt(2) s);
d_X(M, h, s) = (Cl_X(M, h, +s) - Cl_X(M, h, -s)) / (2 s) per deg. **Consistency rule** C(a, b; tol, sigma, s): |a - b| <= max(tol max(|a|, |b|), delta),
delta = max(0.01 per deg, 3 sigma / (sqrt(2) s)). Every gate that uses a sigma lists all 7 cases of that scan as inputs.

Gates, for level L in {med30, fine30} with L+ the next finer level:
- **G6m(L) small step under morphing** (h in {0.224, 0.134}, as T2-0b G6): C(d_M(L, h, 0.25), d_M(L, h, 1); 0.25, sigma_M(L, h), 0.25) AND
  |Cl_M(L, h, +0.25) - Cl_M(L, h, -0.25)| >= 5 sqrt(2) sigma_M(L, h).
- **G3bm(L) derivative across meshes under morphing** (h in H, as T2-0b G3b): C(d_M(L, h, 1), d_M(L+, h, 1); 0.25, max(sigma_M(L, h), sigma_M(L+, h)), 1),
  and the registered sign d_M(L, 0.224, 1) > 0.
- **G7m(L) morph vs remesh** (h in H): C(d_M(L, h, 1), d_R(L, h, 1); 0.25, max(sigma_M(L, h), sigma_R(L, h)), 1). A morph that is smooth but biased
  relative to the remeshed geometry-identical cases fails here.

**Verdict** (exactly one):
- `T20C_MORPH_GO_MED30`: G6m(med30), G7m(med30), G3bm(med30) and G3bm(fine30) pass (the med30 derivative agrees with fine30, and fine30 with xfine30).
- `T20C_MORPH_GO_FINE30`: not GO_MED30, and G6m(fine30), G7m(fine30), G3bm(fine30) pass.
- `T20C_MORPH_NO_GO`: otherwise.
- `T20C_INCOMPLETE`: the enumeration over undetermined gates does not give one verdict.
Meaning of a GO: on that mesh level, morphed rigid incidence changes of 0.25-1 deg at h/c 0.224 and 0.134 are resolved above the morph noise, the incidence
derivative at h/c 0.224/0.134/0.09 agrees within 25 % with every finer level of the family and with the geometry-identical remeshed cases. It says nothing about
the absolute level (G2), shape changes (Q3 is descriptive) or any other section.

**Next actions** (pre-agreed; for NO_GO chosen by the gates failing at fine30, the last level):
| outcome | next action |
| --- | --- |
| GO_MED30 or GO_FINE30 | the morph-based 2D SA-WF evaluator at that level is a candidate for rigid-difference evaluation in M4 (scope section 7); the G2 route is decided at the next stage with the Q2 labels: if `PEAK_EXPLAINED_BY_RESOLUTION` and the xfine30 G2 label passes, a registered data-level confirmation on the finer levels comes before any wall-resolved/LM study; otherwise the T2-0b G2 action (wall-resolved/LM study or another validation case) stands |
| NO_GO, G6m(fine30) fails | the difference noise is not (only) remeshing: a solver-side convergence study (iteration count, plateau, schemes) before reuse |
| NO_GO, G3bm(fine30) fails, G6m passes | the derivative is mesh dependent beyond 25 % without remeshing noise: a near-wall/first-layer family study (wall-resolved family), together with the G2 route |
| NO_GO, only G7m(fine30) fails | the morph biases the derivative: revise the morph (OpenFOAM displacement solver, refinement that follows the wake) and re-register |
| MECHANICAL_FAIL in any gate input | generator/morph defect: fix and re-register (a new study) |
| INCOMPLETE | one resubmission per section 8; if still incomplete, #66 item 1 stays blocked |

**Registered labels** (computed by the analyzer, reported with the verdict, never changing it):
- *Noise:* sigma_R and sigma_M for every (M, h) of the 4 x 3 scans, their ratio, the smallest resolved incidence 2 sqrt(2) sigma / |d(1)| for both methods; a cubic-fit
  residual std (3 dof) for the morph scans (nonlinearity indicator: a quadratic residual dominated by a real cubic response inflates sigma_M). `G6M_009`: the G6m
  rule at h/c 0.09 per level. `G6R(M)`, `G3bR(M)`: the G6 and G3b rules on the remeshed scans of every level (does refinement alone fix T2-0b's failures?).
- *Mesh series (Q2):* for each quantity X (Cl_R(., h, 0) at the 7 heights; d_M(., h, 1) and d_R(., h, 1) at H): e2 = X_fine30 - X_med30, e3 = X_xfine30 -
  X_fine30, R = e3 / e2; `FLAT` if max(|e2|, |e3|) <= 2 sqrt(2) sigma (sigma: for Cl the largest sigma_R at that height over the 4 levels, at an unscanned height
  the largest over all scans; for d the corresponding sigma_d at s = 1), else `MONOTONE` (0 <= R < 1), `OSCILLATORY` (-1 < R < 0), `DIVERGENT` (|R| >= 1);
  where MONOTONE, the Richardson estimate X_xfine30 + e3^2 / (e2 - e3) and the observed order ln(e2/e3)/ln 2 (descriptive). Per level: the T2-0b G2 rule (mean |e|
  nominal and with +0.15 deg x d_R(M, h, 1) interpolated as T2-0b, peak with 0.5 % tolerance, unimodal rise) and G2d, against the same digitised curve.
  `PEAK_EXPLAINED_BY_RESOLUTION` if the peak test and the rise pass on both fine30 and xfine30; `PEAK_NOT_EXPLAINED` if they fail on xfine30; `PEAK_MIXED` otherwise.
- *Replication:* kernel-R coa30/med30/fine30 cases vs the T2-0b cases of the same id (max |dCl/Cl|, `REPLICATED` if <= 1 %, and the count of identical mesh SHA-256);
  kernel-M baselines vs kernel-R 0-deg cases (mesh SHA-256 and Cl identical: `CROSS_KERNEL_IDENTICAL`).
- *Shape modes (Q3):* per (mode, mesh, h): dCl(+-0.25 mm), dCl(+-0.5 mm), d_mode(s) per mm; `resolved` if |dCl(+-0.25 mm)| >= 5 sqrt(2) sigma_M(M, h); linearity
  C(d(0.25), d(0.5); 0.25, sigma_M(M, h), s) with the floor 0.01 per mm; med30 vs fine30 agreement of d(0.5) with tol 0.25. `SHAPE_RESOLVED_CONSISTENT` if all
  three hold for both modes at all three heights on both meshes, `SHAPE_RESOLVED` if only resolution holds everywhere, else `SHAPE_NOT_RESOLVED`.
- *Descriptive:* morph mesh diagnostics (area ratios, proxy quality, checkMesh against the baseline), cells, cost to the Cl plateau and capped wall time per level,
  seconds per cell-iteration, RSS, y+.

## 7. Claim ceiling

Allowed: the gates, labels and verdict with their numbers for this 2D single-element section (Tyrrell 026, Re_c 4.6e5, moving ground), SA wall functions,
the four levels of this mesh family, rigid incidence changes (and, descriptively, the two camber-type modes at +-0.25/0.5 mm).
Not allowed: grid independence or convergence (family with a fixed first layer), any level or drag accuracy statement beyond the G2-by-level label, any
statement about other shape modes, non-camber (thickness) changes, multi-element wings, 3D, finite span, end plates, other Reynolds numbers, the full vehicle,
FSAE suitability, the SDF-to-mesh interface, the SDF optimiser or the Re 80 track. T2-0b's verdict is not changed by this study.

## 8. Freeze, review, budget and stop rules

- Order: draft -> one plan review (three independent adversarial angles: numerical, controls, strategy; sonnet) -> revision recorded in section 10 -> **freeze 1**
  -> implementation (`scripts/t20c_*`, `scripts/build_t20c_kernel.py`, `scripts/analyze_t20c.py`, `tests/test_t20c_*`, `infra/kaggle/kernel_t20c_cpu/` only;
  T2-0b files forked, not edited; the analyzer tested on synthetic fixtures covering every gate, every verdict branch and the undetermined enumeration)
  -> development smoke on Kaggle (mode `smoke`, at most 3 submissions) -> one source review -> **freeze 2** -> kernels R and M submitted once each.
- Development smoke: a mesh-only pass (generator or morph, gmshToFoam, boundary fix, checkMesh, no solver) over every registered geometry of both kernels (232),
  plus each solver path at <= 200 iterations (a remeshed xfine30 case, a morphed xfine30 incidence case, a shape case, the plateau continuation). Force and
  coefficient values are removed before output; only statuses, iteration counts, wall times, checkMesh results and morph diagnostics are kept.
- Resubmission: one identical resubmission per kernel, only for INFRA_LOSS (first-run priority, as T2-0b). Amendment (`REGISTERED_AMENDED`): only for a defect
  that prevents a pre-specified quantity from being computed, filed on #57 before verdict-relevant output is read, never a rule or threshold, at most one per
  kernel. A case-level result is a result, never a reason to rerun.
- Compute: Kaggle CPU only; at most 3 smoke + 2 registered + 2 resubmission + 2 amendment sessions. Kaggle CPU is shared with the M2 UNC-01 session: a
  concurrency limit is waited out, never worked around. If a registered kernel cannot fit a Kaggle session, stop and report a backend trigger (STATE.md).
- Analysis: `scripts/analyze_t20c.py` (frozen at freeze 2) is run once; `analysis.md` and `verdict.json` are committed unchanged; any later reading is a dated note.

## 9. Outputs

`docs/evidence/t20c_registered_2026_10_20/`: `freeze.json`, the smoke record, kernel logs, the downloaded outputs (copied from a fresh empty download directory; mesh
files excluded with their SHA-256 listed), `SHA256SUMS` (checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`, a Japanese note;
updates to `docs/STATE.md` (T2-0 row), `docs/phase_plan.md`, and a result comment on #57.

## 10. Plan review record

(to be filled after the plan review)
