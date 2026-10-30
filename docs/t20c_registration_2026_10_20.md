# T2-0c registered study (#57): fixed-topology morphing and a four-level mesh series for the 2D ground-effect wing-section RANS evaluator

Registration status (PROC-01): `DRAFT` -> `DRAFT_FROZEN_PLAN` at freeze 1 (SHA-256 of this file posted on #57) -> **`REGISTERED_FROZEN`** at freeze 2
(source commit and hashes of the kernel template, builder, analyzer, generator and morph files posted on #57 and in
`docs/evidence/t20c_registered_2026_10_20/freeze.json`). Evidence class of the result: descriptive numerical evidence for one 2D section.
All qualification flags stay false; `shape_update_allowed=false`. **This text governs; a disagreement between it and the frozen analyzer is a defect of the analyzer.**

## 1. Question, origin and scope

T2-0b (`docs/t20b_registration_2026_10_19.md`, verdict `T20B_NO_GO`, `docs/evidence/t20b_registered_2026_10_19/`) failed G2 (data level), G3b (incidence
derivative between med30 and fine30 at h/c 0.09: 0.055 vs 0.082 per deg) and G6 (+-0.25 deg not resolved at h/c 0.134: sigma_mesh 0.0048). Its pre-agreed
next action for G3b/G6 is this study: a mesh-family / remeshing-noise study with fixed-topology morphing instead of remeshing. Questions:

- **Q1 (verdict).** If incidence is changed by moving the nodes of one baseline mesh (same connectivity) instead of remeshing, how far does the difference noise
  fall, and do the T2-0b difference gates G6 (+-0.25 deg) and G3b (incidence derivative agreement between meshes) pass? Also: is the morphed derivative biased
  against geometry-identical remeshed cases (G7m), and does it depend on which baseline mesh realisation was morphed (G8m)?
- **Q2 (registered labels).** On a four-level series (coa30, med30, fine30 and a new xfine30), do the Cl level, the location of the Cl maximum and the incidence
  derivative show a converging trend, and is the Cl maximum at h/c 0.134 on the finer levels (the G2 peak failure of med30)?
- **Q3 (descriptive labels).** If small shape changes (camber, a trailing-edge flap, heave) are applied by the same morph, is the Cl change resolved above the
  incidence-scan noise, and does it agree with geometry-identical remeshed cases? A touchstone for the evaluator an optimiser needs; never a verdict input.

Why a morph: for differences, a fixed topology plays the role of common random numbers (as the paired same-phase differences of M2): designs evaluated on one
topology share its discretisation error, so that error cancels in a difference; G8m measures the part that does not cancel. T2-0c measures this for a
fixed-topology node mapping of the analytic section (section 4). It makes **no claim about the noise of the eventual SDF pipeline's own deformation or
remeshing** (the SDF-to-mesh/deformation interface is an M4/L3 item).

Out of scope (decided at registration): LM (about 3.5 h per case with a limit cycle in T2-0b), any adjoint retry, other turbulence models (T2-0b G4 passed),
OpenFOAM's own mesh-motion solvers. Whether a wall-resolved/LM evaluator study or a different validation case is needed for the G2 failure is **decided at the
next stage with this study's results**, by the rule in section 7, not here. Trigger: T2-0c runs now as the parallel-track hedge decided on 2026-10-16 (T2-0 is
the M3a NO-GO branch target), not after M3a. Cap: at most one more registered T2-0 study after this one before a T2-0 summary is written as M4 input.

## 2. What was visible before this registration (and how it is used)

- **All T2-0a and T2-0b results.** The gate tolerances are T2-0b's (consistency tol 0.25, delta floor 0.01 per deg, resolution factor 5 sqrt(2), the 0.5 %
  peak tolerance, the Cl plateau); they were chosen in T2-0b after T2-0a and **are applied here after T2-0b's numbers were visible**: `verdict.json` carries
  `thresholds_set_after_exploratory_visible: true` and `thresholds_set_after_t20b_visible: true`, and both must accompany any citation. Changed from T2-0b after
  seeing it (plan review, section 10): sigma from a cubic fit with an iterative floor (sigma_eff), delta from the root-sum-square of the two derivative noises,
  the power requirement, the UNSTEADY class. New elements (G7m, G8m, the verdict levels, xfine30, the morph, the Q2/Q3 labels) were designed knowing T2-0b's
  numbers. In particular: **fine30 is the GO level knowing that T2-0b's fine30 fits the experiment better** (mean |e| 2.90 %, peak at 0.134), and **xfine30 was
  designed after the 0.09 G3b failure** (section 3).
- **The T2-0b G3b failure at 0.09 rests on an unsteady case** (plan review N1): `sa-wf_h0.09_fine30_da+1` passed the block-mean plateau (0.32 %) but its raw tail
  Cl had a relative std of 1.88 % (range 5.3 % of Cl), the only one of T2-0b's 60 wall-function cases above 0.1 %; with the fine30 -1..0 deg slope instead of the
  +-1 deg secant, G3b at 0.09 would have passed. The draft's statement that the difference was a resolution effect is withdrawn; T2-0c adds the UNSTEADY class.
- **Pre-determined by T2-0b (if the pipeline reproduces bit for bit, as T2-0b showed for identical geometries on the same Kaggle image and CPU model):** every
  coa30/med30/fine30 remeshed quantity that T2-0b computed: the G2-by-level labels for coa30, med30, fine30 (fine30 already passes the G2 rule on T2-0b's numbers:
  mean |e| 2.90 % nominal, 3.79 % with the +0.15 deg shift, peak at 0.134 with a 3.8 % margin, rise unbroken; so the peak label depends on xfine30 alone), the
  remeshed +-1 deg derivatives at med30 and fine30, the med30 remeshed scans at 0.224 and 0.134. A bitwise replication adds a determinism statement, no evidence.
  **New:** all morphed quantities, all xfine30 quantities, the remeshed scans at fine30 (all heights) and med30 at 0.09, the second-baseline and blend controls,
  the shapes.
- **Local mesh-only prototype (2026-10-20, no solver, no force)**: the morph of section 4 on coa30/med30/fine30/xfine30 at h/c 0.224/0.134/0.09 and +-1 deg, and on
  med30/fine30 for the shape modes, a +0.5 deg base and the linear blend: no inverted cell, cell-area ratios 0.84-1.16, the local checkMesh proxy
  (`t20_case.mesh_quality`) passes with essentially the baseline values, the morphed contour equals the generator's target contour to 2e-16 m, a zero morph
  rewrites a byte-identical mesh. xfine30 variants (1-4 layers) were meshed locally for quality only (section 3). The plan reviewers reproduced these checks.
- **No T2-0c solver output exists at registration.** The development smoke (section 8) removes every force-derived value.
- **Predictions at registration** (in `verdict.json` as `predicted`): G6m pass at fine30 and med30 (morphing removes the remeshing jumps); at h/c 0.09 the +1 deg
  cases (fine30, likely xfine30) are UNSTEADY again (same geometry), so the full GO is unlikely; G3bm, G7m, G8m at 0.224/0.134 pass; verdict
  `T20C_MORPH_GO_FINE30_ATTACHED` most likely, NO_GO second; coa30/med30/fine30 remeshed cases `REPLICATED_BITWISE`; peak label uncertain; shapes resolved.
- **Data reuse.** No T2-0a or T2-0b output file is read by the analyzer except for the replication label. Every gate input is a T2-0c run.

## 3. Case (generators reused by hash)

`scripts/t20_case.py` and `scripts/t20_foam.py` (pinned, unchanged) generate every baseline and every remeshed case exactly as in T2-0b (Tyrrell026S, chord
0.2234 m, U 30 m/s, Re_c 4.6e5, moving ground, Tu 0.3 %, domain 2c/5c/6.8c, steady simpleFoam, 5000 iterations, schemes and relaxation as T2-0b;
incidence = rotation about the LE, LE toward the ground positive, then h re-imposed at the lowest suction-surface point; Cl = downforce coefficient).
A new module `scripts/t20c_case.py` (a) registers the mesh level **xfine30**, (b) implements the morph (section 4) and (c) meshes the remeshed shape cases by
handing the shaped contour to the pinned generator (its `airfoil_points` patched for that call only); it does not modify the pinned files.
**Every case, remeshed or morphed, starts from the generator's uniform initial fields** (no mapping, restart or field transfer; a morphed case copies the
baseline's unsolved `0/`); a unit test asserts it.

Mesh levels (Genua's wall-function family: fixed first layer y1 = 0.6 mm, growth 1.2, sharp-TE fan; the surface spacing halves per level):
coa30 8 mm, med30 4 mm, fine30 2 mm, **xfine30 1 mm** (new). The family's last-layer rule (0.433 ds, equal area with the triangles)
cannot be met at ds = 1 mm (0.43 mm < y1). xfine30 takes `last = 0.65`, i.e. **two layers (0.6 + 0.72 = 1.32 mm) at every height**; every cell is then at least as
fine as fine30's (fine30: four layers 0.6-1.04 mm, 3.22 mm, then 2 mm triangles; xfine30: two layers, then 1 mm triangles), so xfine30 refines in every direction
with the first layer fixed; the remaining difference is the cell type between 1.3 and 3.2 mm from the wall (quads vs triangles of similar size), disclosed as a
confound of the fine30 -> xfine30 step. Chosen on force-free mesh quality only (local proxy over the 25 remeshed xfine30 geometries): fine30's own four-layer stack
(`last = 1.0`) gives non-orthogonality up to 75 deg at the LE (the LE ball is ds/3 = 0.33 mm against a 3.22 mm stack) and fails the proxy in 8 of 25 geometries,
three layers in 3 of 25, two layers in none (maximum 48.5 deg, 49.3-52.7k cells); one layer (the draft) puts the boundary layer in triangles. Layer stacks:
coa30 up to 11 (capped by 0.4 gap at low heights: 7 at h/c 0.09), med30 7, fine30 4, xfine30 2.
The series is **not a systematic refinement** (fixed first layer; the stack changes with ds): Q2 labels describe trends of this family, never grid convergence.

## 4. Morph (fixed topology)

For each (mesh, h) a **baseline** mesh is generated by the pinned generator. A morphed case takes the baseline `mesh.msh` (gmsh 2.2 ascii, canonical node
order) and rewrites only the x, y of every node (z untouched, both extrusion planes alike); the node numbering, the element list and the physical groups are
byte-identical. The OpenFOAM dictionaries are the baseline's (they do not depend on geometry).

Displacement D(p) of a node p (2D), for a base generated at incidence alpha_b (0 deg unless stated):
- **Incidence (target alpha):** the generator's own transformation, p -> T1 + Rot(alpha - alpha_b)(p - T0), with T0, T1 the trailing-edge points of the
  generator contours `airfoil_points(h, alpha_b)` and `airfoil_points(h, alpha)` and Rot the generator's rotation. The mapped base contour equals the target
  contour: the morphed and the remeshed case have the same section geometry and differ only in the mesh.
- **Shape modes** (Q3; 0-deg base), in the chord frame of the baseline contour (LE = contour point of the LE, TE = contour point 0, c_hat = unit LE->TE,
  n_hat = c_hat turned +90 deg, i.e. away from the ground; xi(p) = (p - LE).c_hat / |TE - LE|):
  `camber`: D_s = -a 4 xi (1 - xi) n_hat for 0 <= xi <= 1, 0 otherwise (a > 0: mid-chord toward the ground);
  `flap`: D_s = +a g(xi) n_hat, g = ((xi - 0.7)/0.3)^2 on [0.7, 1], 1 for xi > 1, 0 for xi < 0.7 (a > 0: trailing edge away from the ground);
  in both, a > 0 increases the inverted camber (expected: more downforce); suction and pressure surfaces move equally (thickness unchanged); then h is re-imposed:
  D = D_s + (0, s), s = h - min over the suction contour points of (q + D_s(q))_y. `heave`: D = (0, a) (ride height h + a; no re-imposition). Amplitudes a in
  {-0.5, -0.25, +0.25, +0.5} mm. The remeshed shape case meshes the contour {q + D(q)} with the pinned generator (camber, flap) or the generator at h + a (heave).
- **Blending:** p' = p + w(p) D(p), with d_a = distance to the base contour polyline, b = the base mesh's layer-stack thickness (manifest `bl_thickness_m`;
  it is both the airfoil stack and the ground-block height), r = max(d_a - b, 0), d_f = max(min(y - b, x - x_inlet, x_outlet - x, y_top - y), 0),
  phi = r / (r + d_f), **w = 1 - phi^2 (3 - 2 phi)** (registered; the blend label of section 6 also uses the linear w = 1 - phi); w = 0 for y <= b. The airfoil
  layer stack moves rigidly with the section, the ground block and the outer boundaries do not move, the triangles in between absorb the motion. The
  wake-refinement line of the size field stays where the base put it (the TE moves about 3 mm at +-1 deg); G7m and the blend label measure the consequence.
- **Asserted per morph (failure = `GENERATOR_FAILED`, a MECHANICAL_FAIL):** no 2D cell changes the sign of its area; ground-block, inlet, outlet and top nodes are
  unmoved; every airfoil-patch node has w = 1 (within 1e-9), i.e. moves exactly with the section; the mapped base contour equals the target contour within
  1e-9 m (incidence). **Asserted per morphed case after gmshToFoam (failure = `TOPOLOGY_CHANGED`, a MECHANICAL_FAIL):** `constant/polyMesh/faces`, `owner`,
  `neighbour` and the patch-fixed `boundary` have the SHA-256 of the baseline's (only `points` differs). Recorded: min/max cell-area ratio, the local quality
  proxy, TE displacement, the base mesh SHA-256.
- After freeze 1 this section may change only for a mesh-validity defect found in a force-free diagnostic (recorded on #57 with the diagnostic), never toward a
  Cl or derivative result.

## 5. Kernels and cases (OpenFOAM v2512, Kaggle CPU, 4 concurrent cases, as T2-0b)

Notation: Cl_R(M, h, alpha) = remeshed, Cl_M(M, h, alpha) = morphed from the kernel's 0-deg baseline (alpha = 0: that baseline itself), Cl_M'(M, h, alpha) =
morphed from a **second baseline** B' (the generator mesh at +0.5 deg, a different mesh realisation of nearly the same geometry), M in {coa30, med30, fine30,
xfine30}, scan heights H = {0.224, 0.134, 0.09}, scan incidences A7 = {-1, -0.5, -0.25, 0, +0.25, +0.5, +1} deg. Every kernel lists its xfine30 cases first.

| kernel | slug | cases | content | estimate (4 workers) |
| --- | --- | --- | --- | --- |
| R | `cfd-opt-sdf-t20c-remesh` | 82 | sweep {coa30, med30, fine30, xfine30} x 7 heights {0.671, 0.448, 0.313, 0.224, 0.179, 0.134, 0.09} at 0 deg (28); remeshed scans {med30, fine30, xfine30} x H x 6 nonzero incidences (54) | 4 h |
| M | `cfd-opt-sdf-t20c-morph` | 93 | base stage: 9 baselines {med30, fine30, xfine30} x H at 0 deg and 6 bases B' {med30, fine30} x H at +0.5 deg; the 9 baselines solved; morphed scans {med30, fine30, xfine30} x H x 6 (54); from B': {med30, fine30} x H x {-1, -0.25, +0.25, +1} (24); linear blend fine30 x H x {-1, +1} (6) | 4.2 h |
| S | `cfd-opt-sdf-t20c-shape` | 96 | base stage: 6 baselines {med30, fine30} x H; the 6 solved; morphed shapes {camber, flap, heave} x {+-0.25, +-0.5} mm x {med30, fine30} x H (72); remeshed shapes {camber, flap, heave} x {+-0.5} mm x fine30 x H (18) | 3.4 h |

Kernel budget 11 h (the estimates plus about 2 h allowance for continuations), per-case cap 2.5 h; a smoke stage first (infrastructure gate as T2-0b, sa-wf
coa30 h/c 0.224, 200 iterations). Case records, the Cl plateau (20-iteration block means over the last 20 %, relative std and drift < 0.5 %), the one
continuation to 15000 iterations, y+ and costs are T2-0b's (runner fork). coa30 enters only the sweep (labels): it is outside Genua's usable range for SA.

## 6. Rules (fail-closed; computed by the frozen `scripts/analyze_t20c.py`)

**Case classes** as T2-0b section 6 (VALID / SOLVER_FAIL / MECHANICAL_FAIL / INFRA_LOSS; `TOPOLOGY_CHANGED` and `GENERATOR_FAILED` are MECHANICAL_FAIL), plus
**UNSTEADY**: a case VALID by T2-0b's rule whose raw tail Cl relative std (`forces.Cl.tail_rel_std`, the judged run) exceeds 0.5 %; it fails every gate that lists
it, like SOLVER_FAIL, and is named separately. A failed input fails the gate; an infrastructure loss alone makes it undetermined; any undefined quantity fails.

**Noise.** For a 7-incidence scan (X in {R, M}): sigma_fit,X(M, h) = residual standard deviation of a **cubic** fit of Cl over A7 (3 dof);
sigma_iter,X(M, h) = the largest raw tail Cl std (`forces.Cl.tail_std`) of its 7 cases; **sigma_eff = max(sigma_fit, sigma_iter)** is the only sigma used in a
gate. d_X(M, h, s) = (Cl_X(M, h, +s) - Cl_X(M, h, -s)) / (2 s) per deg; its noise sigma_d = sigma / (sqrt(2) s).
**Consistency rule** C(a, b; tol, sigma_d,a, sigma_d,b): |a - b| <= max(tol max(|a|, |b|), delta), delta = max(0.01 per deg, 3 sqrt(sigma_d,a^2 + sigma_d,b^2));
with the **power requirement** (C_P): additionally 3 sqrt(sigma_d,a^2 + sigma_d,b^2) <= 0.5 tol max(|a|, |b|), otherwise the comparison is `UNRESOLVED` and
fails (a noisy measurement cannot certify agreement). Every comparison reports its margin (|a - b| - allowed) / allowed.

Gates, **per height** (each gate value per height is true, false or undetermined; its inputs are listed per height and include all 7 cases of every scan whose
sigma it uses). With L = fine30, L+ = xfine30:
- **G6m(h)**, h in {0.224, 0.134} (as T2-0b G6): C_P(d_M(L, h, 0.25), d_M(L, h, 1); 0.25, sigma_eff,M(L, h) at s = 0.25 and s = 1) AND
  |Cl_M(L, h, +0.25) - Cl_M(L, h, -0.25)| >= 5 sqrt(2) sigma_eff,M(L, h).
- **G3bm(h)**, h in H (as T2-0b G3b): C_P(d_M(L, h, 1), d_M(L+, h, 1); 0.25, sigma_eff,M(L, h), sigma_eff,M(L+, h)); at h = 0.224 also the registered sign
  d_M(L, 0.224, 1) > 0.
- **G7m(M, h)**, M in {fine30, xfine30}, h in H: C(d_M(M, h, 1), d_R(M, h, 1); 0.25, sigma_eff,M(M, h), sigma_eff,R(M, h)) **without** the power requirement:
  a bias screen against a reference that carries the remeshing noise by design; its allowed band is reported as the bias it cannot exclude, and d_M - d_R is
  also reported in units of the remeshed sigma_d.
- **G8m(h)**, h in H, s in {1, 0.25} (both must pass): C_P(d_M(L, h, s), d_M'(L, h, s); 0.25, sigma_eff,M(L, h), max(sigma_eff,M(L, h), sigma_iter of the 4 B'
  cases)). A morphed derivative that depends on which mesh realisation was morphed by more than the band fails here.

**Verdict** (exactly one), with full = all heights of every gate and attached = only h/c 0.224 and 0.134:
- `T20C_MORPH_GO_FINE30`: G6m, G3bm, G7m(fine30), G7m(xfine30), G8m pass at every height.
- `T20C_MORPH_GO_FINE30_ATTACHED`: not the above, and all of them pass at 0.224 and 0.134 (scope h/c >= 0.134 of this section).
- `T20C_MORPH_NO_GO`: otherwise.
- `T20C_INCOMPLETE`: the verdict is not the same for every true/false assignment of the undetermined per-height gate values.
Meaning of a GO: on fine30, morphed rigid incidence changes of 0.25-1 deg at h/c 0.224 and 0.134 are resolved above the morph noise, and the morphed incidence
derivative at the heights in scope agrees within the band with xfine30 (the next finer level), with a second baseline realisation (s = 1 and 0.25), and with the
geometry-identical remeshed cases on fine30 and xfine30. It says nothing about the absolute level (G2), shape changes (Q3), any other section or the SDF pipeline.
med30 (T2-0b's primary mesh) is reported by the same rules as labels (`MED30`, section 6 labels), never as a verdict.

**Next actions** (pre-agreed; the first matching row applies, reading the fine30/xfine30 gates):
| order | condition | next action |
| --- | --- | --- |
| 1 | MECHANICAL_FAIL in any gate input | generator/morph defect: fix and re-register (a new study); no route is inferred from this one |
| 2 | INCOMPLETE | one resubmission per section 8; if still incomplete, #66 item 1 stays blocked |
| 3 | GO_FINE30 | section 7 (what M4 may take; the G2 route) |
| 4 | GO_FINE30_ATTACHED | section 7 for h/c 0.224 and 0.134 only; the 0.09 failures are routed by rows 5-9 applied to 0.09 alone |
| 5 | a failing gate has an UNSTEADY or SOLVER_FAIL input | steady RANS does not settle at that (mesh, h, alpha): an unsteady/solver-convergence study there; no mesh-dependence or morph conclusion |
| 6 | G7m fails | the morph biases the derivative: revise the morph and re-register; the revised morph may not be tuned on d_R or on any T2-0c force value |
| 7 | G8m fails | the morphed derivative depends on the baseline realisation: an ensemble-of-baselines study (or a smoother mesh family) before reuse |
| 8 | G6m fails | the difference noise is not (only) remeshing: a solver-side convergence study (iterations, plateau, schemes) |
| 9 | G3bm fails | mesh dependence of the derivative beyond the band without remeshing noise: a near-wall/first-layer family study, together with the G2 route |
| 10 | anything else | stop; no route is inferred; the next step is a recorded decision |

**Registered labels** (computed by the analyzer, reported with the verdict, never changing it; only the peak/G2 labels feed a route, section 7):
- *Noise:* sigma_fit (cubic), the quadratic-fit sigma (T2-0b's estimator; `NONLINEAR` if quadratic/cubic > 2), sigma_iter, sigma_eff for R and M at every
  (M, h) of the scans; the 90 % chi-square upper bound of sigma_fit (x 2.27 for 3 dof); the pooled noise reduction (geometric mean of sigma_eff,R / sigma_eff,M
  over the 9 (M, h) pairs) and its per-pair values; `SURVIVES_2SIGMA` per gate (re-evaluated with every sigma doubled); d at s = 0.5 for both methods; the
  smallest resolved incidence 2 sqrt(2) sigma_eff / |d(1)| for both methods ("relative to the morph's smoothness only; accuracy is bounded by G7m's band").
  `G6M_009`: the G6m rule at 0.09. `G6R(M)`, `G3bR(M)`: the G6 and G3b rules on the remeshed scans (does refinement alone fix T2-0b's failures?).
  `BLEND(h)`: |d_M,linear - d_M| on fine30 at s = 1 in units of the G3bm band. `MED30(full)`, `MED30(attached)`: the four gates at med30 (G3bm against fine30 and
  against xfine30, G7m(med30), G8m on med30's B').
- *Mesh series (Q2):* for each quantity X (Cl_R(., h, 0) at the 7 heights; d_M(., h, 1) and d_R(., h, 1) at H): e2 = X_fine30 - X_med30, e3 = X_xfine30 -
  X_fine30, R = e3 / e2; `NOT_RESOLVED` if max(|e2|, |e3|) <= 2 sqrt(2) sigma (for Cl the largest sigma_eff,R at that height over the levels, at an unscanned height
  the largest over all remeshed scans; for d the root-sum-square of the two sigma_d at s = 1), else `MONOTONE` (0 <= R < 1), `OSCILLATORY` (-1 < R < 0),
  `DIVERGENT` (|R| >= 1). Per level: the T2-0b G2 rule (mean |e| nominal and with +0.15 deg x d_R(M, h, 1) interpolated as T2-0b, peak with 0.5 % tolerance,
  unimodal rise) and G2d, against the same digitised curve. Peak margin m(M) = Cl(0.134) - (1 - 0.005) max(Cl(0.179), Cl(0.09)) and noise n(M) = 2 sqrt(2) times the
  largest sigma_eff,R of M's scans: `PEAK_AT_FINER_LEVELS` if m >= n and the rise holds on both fine30 and xfine30; `PEAK_NOT_AT_FINER_LEVELS` if on fine30 or
  xfine30 m <= -n or the rise breaks; else `PEAK_INDETERMINATE_NOISE`. Layer stack, cells, non-orthogonality and y+ per level.
- *Replication:* kernel-R coa30/med30/fine30 cases vs the T2-0b cases of the same id: `REPLICATED_BITWISE` if the mesh SHA-256 are identical and Cl agrees to
  1e-12 relative, else `NOT_BITWISE` with the largest difference and the CPU models. `CROSS_KERNEL_IDENTICAL`: kernel-M/S baselines vs the kernel-R 0-deg cases
  (mesh SHA-256 and Cl); a difference with a different CPU model is reported, not a defect.
- *Shape modes (Q3):* per (mode, mesh, h): dCl(s) = Cl(+s) - Cl(-s) for s = 0.25 and 0.5 mm, d_mode(s) = dCl(s) / (2 s) per mm, the expected sign (d > 0 for
  camber and flap); `resolved` if |dCl(0.25 mm)| >= 5 sqrt(2) sigma_eff,M(M, h) of the incidence scan (fine30; med30's own scan for med30); linearity
  C(d(0.25), d(0.5); 0.25, ...) without a floor; med30 vs fine30 agreement of d(0.5) (tol 0.25, no floor); morph vs remesh on fine30, C(d_M(0.5), d_R(0.5); 0.25,
  ...) without a floor and with the remeshed sigma_eff,R(fine30, h); a pooled 5-point sigma per mode scan. `SHAPE_RESOLVED_CONSISTENT` if all four hold for every
  mode at every height, `SHAPE_SMOOTH_RESOLVED` if only resolution holds everywhere, else `SHAPE_NOT_RESOLVED`.
- *Descriptive:* morph mesh diagnostics (area ratios, proxy quality, checkMesh against the baseline), cells, cost to the Cl plateau and capped wall time per level,
  seconds per cell-iteration, RSS, y+, the UNSTEADY cases with their raw tail statistics.

## 7. What M4 (#66) may take, the G2 route, and the claim ceiling

- A T2-0c GO **does not change #66 item 1** (still NO-GO under T2-0b's G2) and **does not trigger** the M3a NO-GO branch's "move to the T2-0 evaluator" step.
  It is a statement about noise, mesh consistency, baseline realisation and morph bias of rigid incidence differences on one section, at fine30, in the stated
  height scope. Before M4 may rely on a morph-based evaluator it additionally needs: the G2 route resolved on data not used in T2-0b or T2-0c; a registered test of
  shape differences (Q3 is descriptive); the SDF-to-mesh/deformation interface.
- **G2 route (rule fixed now, applied at the next stage):** `PEAK_AT_FINER_LEVELS` and the xfine30 G2 rule passing -> the next G2 step is a registered data-level
  test on the finer levels against **independent data** (a different validation case or the primary Zerihan & Zhang data, not the 7 digitised points used
  here), before any wall-resolved/LM study. `PEAK_NOT_AT_FINER_LEVELS` or the xfine30 G2 rule failing -> the T2-0b G2 action (wall-resolved/LM evaluator study or
  another validation case) stands. `PEAK_INDETERMINATE_NOISE` -> this study makes no G2 routing decision (T2-0b's action stays the default until a recorded
  decision). No other label may be used to pick or justify a route.
- Allowed: the gates, labels and verdict with their numbers for this 2D single-element section (Tyrrell 026, Re_c 4.6e5, moving ground), SA wall functions,
  the four levels of this family, rigid incidence changes, and, descriptively, the three shape modes at +-0.25/0.5 mm (`SHAPE_*` may be cited only as "the
  morphed response exceeds the incidence-scan noise" and "agrees/disagrees with remeshed shapes at +-0.5 mm on fine30", never as evaluator evidence).
- Not allowed: grid independence or convergence (family with a fixed first layer), any level or drag accuracy statement beyond the G2-by-level label, other shape
  modes, thickness changes, multi-element wings, 3D, finite span, end plates, other Reynolds numbers, the full vehicle, FSAE suitability or FSAE ride heights,
  the SDF-to-mesh interface, the SDF optimiser or the Re 80 track. T2-0b's verdict is not changed by this study.

## 8. Freeze, review, budget and stop rules

- Order: draft -> one plan review (three independent adversarial angles: numerical, controls, strategy; sonnet) -> revision recorded in section 10 -> **freeze 1**
  -> implementation (`scripts/t20c_case.py`, `scripts/build_t20c_kernel.py`, `scripts/analyze_t20c.py`, `tests/test_t20c.py`, `infra/kaggle/kernel_t20c_cpu/`
  only; T2-0b files forked, not edited; the analyzer tested on synthetic fixtures covering every gate, every verdict branch, UNSTEADY, the power requirement and
  the undetermined enumeration) -> development smoke on Kaggle (mode `smoke`, at most 3 submissions) -> one source review -> **freeze 2** -> kernels R, M, S
  submitted once each.
- Development smoke: a mesh-only pass (generator or morph, gmshToFoam, boundary fix, checkMesh, the topology hash check, no solver) over every registered geometry
  of the three kernels, plus each solver path at <= 200 iterations (a remeshed xfine30 case, a morphed xfine30 incidence case, a B' morph, a shape morph, a
  remeshed shape, the plateau continuation). Removed before output: the `forces` block of every case record (values, the plateau flag, iterations to plateau),
  `postProcessing/` and `coefficient.dat`, every log line matching the force filter (forces, forceCoeffs, Cl/Cd/Cm and objective lines), and `mesh.msh`. Kept:
  statuses, iteration counts, wall times, residual lines, checkMesh output, morph diagnostics, mesh and topology SHA-256 (determinism is checked by digests only).
- Reading order: the registered kernel outputs are not opened for case values before all three are downloaded and `analyze_t20c.py` has run once; before that
  only DONE/ERROR files, artifact manifests, kernel status/log lines and per-case `status` fields are read.
- Resubmission: one identical resubmission per kernel, only for INFRA_LOSS (first-run priority, as T2-0b; cases from different runs are flagged if the CPU model
  or gmsh version differs). Amendment (`REGISTERED_AMENDED`): only for a harness or infrastructure defect (not the morph, the generator or a rule) that prevents a
  pre-specified quantity from being computed, filed on #57 before verdict-relevant output is read, at most one per kernel. A MECHANICAL_FAIL from a morph,
  topology or checkMesh assertion in a registered kernel is a result (row 1), never an amendment. A case-level result is never a reason to rerun.
- Compute: Kaggle CPU only; at most 3 smoke + 3 registered + 3 resubmission + 3 amendment sessions. Kaggle CPU is shared with the M2 UNC-01 session (its U3
  OpenFOAM part): a concurrency limit is waited out, never worked around. If a registered kernel cannot fit a Kaggle session, stop and report a backend trigger.
- Analysis: `scripts/analyze_t20c.py` (frozen at freeze 2) is run once; `analysis.md` and `verdict.json` are committed unchanged; any later reading is a dated note.

## 9. Outputs

`docs/evidence/t20c_registered_2026_10_20/`: `freeze.json`, the smoke record, kernel logs, the downloaded outputs (copied from a fresh empty download directory; mesh
files excluded with their SHA-256 listed), `SHA256SUMS` (checked with `scripts/check_sha256sums_tracked.py`), `analysis.md`, `verdict.json`, a Japanese note;
updates to `docs/STATE.md` (T2-0 row), `docs/phase_plan.md`, and a result comment on #57.

## 10. Plan review record

One plan review, three independent adversarial sonnet subagents on draft a19c1e44 (2026-10-20): numerical (12 findings), controls (14), strategy (12).
Accepted (A), partly accepted (P) or rejected (R); the change is in the text above.

Numerical:
- N1 P (blocking): the T2-0b 0.09 case behind the G3b failure was a limit cycle (raw tail std 1.88 %); UNSTEADY class added with its own next-action row and the
  "resolution difference" rationale withdrawn (section 2). Tightening the block plateau to 5e-4 rejected: the raw-std floor in sigma_eff and the power requirement
  already stop a fluctuating case from certifying anything.
- N2 A: the gates use the cubic-fit sigma (3 dof); the quadratic sigma is a label with a `NONLINEAR` flag.
- N3 A: G7m at fine30 and xfine30 (the comparator), both required for a GO.
- N4 P: Richardson extrapolation and observed order dropped; the peak labels renamed; xfine30 re-defined with two layers (section 3) instead of adding a
  one-layer control; fine30's own four-layer stack was tried and rejected on mesh quality, so a cell-type confound remains and is disclosed.
- N5 P: 0.09 stays in the full GO (the registered question is T2-0b's G3b, which includes 0.09); a pre-registered scope-restricted verdict GO_FINE30_ATTACHED
  added, and the UNSTEADY row keeps a 0.09 limit cycle from being read as mesh dependence; no small-step gate at 0.09 (`G6M_009` label).
- N6 A: the peak label requires a margin beyond 2 sqrt(2) sigma, else `PEAK_INDETERMINATE_NOISE`, which makes no G2 routing decision.
- N7 A: the raw tail std is the iterative floor of sigma_eff; the noise reduction is pooled; the smallest resolved incidence is annotated.
- N8 A: delta from the root-sum-square of the two derivative noises; the GO meaning reworded to the next finer level (med30 left the verdict, C11).
- N9 A: per-case polyMesh topology hashes equal to the baseline's (`TOPOLOGY_CHANGED`) and airfoil nodes with w = 1 are asserted.
- N10 P: dCl defined, the sign meaning stated (a > 0 increases inverted camber in both modes, expected-sign label), floors removed, a pooled shape sigma label,
  remeshed shapes on fine30 (rather than med30, the GO level), labels renamed.
- N11 P: the bitwise prediction is conditional on the same image and CPU model, recorded per kernel; a cross-kernel difference with another CPU model is not a
  defect. Regenerating a failed baseline rejected: the generator is deterministic on one host, so a regenerated mesh is the same mesh.
- N12 A: about 2 h continuation allowance in the kernel budget.

Controls:
- C1 A: section 7 (a GO does not change #66 item 1 or trigger the M3a NO-GO branch; what M4 additionally needs).
- C2 A: section 2 lists the pre-determined and the new quantities. Removing the bitwise duplicates rejected: gate inputs must be T2-0c runs, and the remeshed
  scans are the G7m and sigma_R inputs in the same environment.
- C3 P: sigma_eff with an iterative floor, the chi-square bound, `SURVIVES_2SIGMA`, the annotation; the baseline-replicate control is a gate (G8m, s = 1 and 0.25)
  rather than a label.
- C4 P: the power requirement on G6m, G3bm, G8m; not on G7m, whose reference carries the remeshing noise by design (its band is reported as the undetectable
  bias, S11); the 0.01 per deg floor kept as an absolute floor.
- C5 A: uniform initial fields for every case, unit-tested.
- C6 P: zero-morph identity (unit test, smoke digest) and the alternative blend (label, fine30) accepted; s = 0.5 secants reported; the round trip rejected (the
  blend is evaluated on base positions; the contour, airfoil-node and topology assertions cover the map).
- C7 P: shape wording and citation limited, remeshed shapes added; the word "touchstone" kept as the study's purpose (the request's own framing), never a verdict
  input.
- C8 A: peak labels renamed; any G2 follow-up must use independent data; the routing labels are fixed in section 7.
- C9 A: a precedence table with UNSTEADY/SOLVER_FAIL, a catch-all row and a ban on tuning a revised morph on d_R or T2-0c forces.
- C10 A: a morph/topology MECHANICAL_FAIL is a result; the reading order; a CPU-model flag on mixed runs.
- C11 P: the scope-restricted level is a pre-registered verdict (N5, S2) rather than a label; GO_MED30 dropped (med30 reported as labels); xfine30 cases first;
  the med30 prediction margin stated.
- C12 P: xfine30 re-defined (two layers, a refinement in every direction) and its design history disclosed; the stack is not identical to fine30's (quality).
- C13 A: the smoke scrub list, digests only, the section 4 change rule.
- C14 A: `REPLICATED_BITWISE`, `NOT_RESOLVED`, Richardson dropped; the gate sigma is fixed (cubic, N2) and the quadratic one is a label.

Strategy:
- S1 A: section 7.
- S2 P: GO_FINE30_ATTACHED added and GO_MED30 dropped; 0.09 kept in the full GO (N5); FSAE ride heights are not claimed.
- S3 P: xfine30 re-defined (two layers, not fine30's stack, which fails on quality; not a y1 change, which leaves the wall-function family); the mesh-only smoke
  covers its mechanics; fail-closed kept (an xfine30 failure is not made undetermined).
- S4 P: remeshed camber/flap/heave at +-0.5 mm on fine30 and the heave mode added; Q3 stays descriptive (fixed by the request), so no shape verdict tier.
- S5 P: the common-random-numbers rationale and the no-claim statement for the SDF pipeline in section 1; an OpenFOAM mesh-motion arm rejected (scope; its
  dictionaries would be untested, and the node mapping already is a fixed-topology deformation).
- S6 P: coa30 scans dropped; staging rejected (three kernels instead, and every gate needs kernel M's cases); reuse of T2-0b cases rejected (C2).
- S7 A: the peak margin in sigma units, Richardson dropped, the shape floor removed.
- S8 A: the complete precedence table.
- S9 A: trigger and cap in section 1.
- S10 P: three kernels; the UNC-01 sentence kept (its U3 part uses OpenFOAM on Kaggle CPU); an early plateau stop rejected (5000 iterations kept for
  comparability and replication).
- S11 A: G7m's band reported as the bias it cannot exclude, d_M - d_R in remeshed sigma_d units.
- S12 A: section 2 disclosures.
