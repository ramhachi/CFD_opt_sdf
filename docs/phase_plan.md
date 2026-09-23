# Authoritative Roadmap: Generic Aerodynamic Topology Optimization

Date: 2026-09-22
Status: authoritative
Scope: generic rigid-object external aerodynamics with topology change
Architecture decision: adopted on 2026-09-09

This is the only implementation roadmap for the project. Historical
body-fitted, parametric, and front-wing-specific work is capability evidence,
not a second development plan. The front wing remains the final complex
benchmark; it does not define the product architecture.

## September 2026 cross-platform implementation

The accepted [32 GB development design](development_plan_2026_09.md) and
[critical architecture review](architecture_review_2026_09.md) specify the
Mac/Windows extension. This page remains the authoritative progress record.
The existing G1–G4 gates below remain mandatory; the P0–P5 milestones in the
design are work packages, not substitutes for those gates.

The project adopts this architecture as its production direction: one shared
ProblemSpec and evidence contract, density/Brinkman topology exploration, SDF
sharp-interface refinement, and independent body-fitted verification. Backend
promotion remains conditional on the numerical and physical gates below. In
particular, adopting the architecture does not promote the current periodic
LBM probe to a target-aerodynamics solver.

The `main` snapshot immediately before this decision is preserved as
`artifact/pre-cross-platform-architecture-2026-09-09` at commit `fdc1053`.

The first implementation adds bounded `research` commands for runtime
inspection, STL/declared-feature preflight, and a periodic D2Q9 Taylor–Green
reference with an optional Apple Silicon Metal backend. These are P0/P1
foundations. CPU execution is portable; Metal acceleration requires Apple
Silicon. Windows CUDA acceleration is still pending. A working RTX 4070 Ti
must be qualified against its separate VRAM budget, not 32 GB host RAM.

The geometry preflight checks only its explicitly listed subset. Periodic
LBM has no wall treatment, force integration, SDF coupling, adjoint, or 3D
support. Neither its passing benchmark nor a successful OpenFOAM process
qualifies target aerodynamics or a complete optimization pipeline.

The current execution order is maintained only in [section 11](#11-immediate-execution-order).
The early cross-platform steps above remain product-level gates; they do not
override the measured PQ0/PQ1 state or the next issue-driven slice.

See [cross-platform commands and evidence](cross_platform_research.md).

## 1. Product objective

Build a configuration-driven optimizer that can add, remove, join, and split
material inside a bounded design domain for an arbitrary STL-defined rigid
object, subject to aerodynamic, geometric, connectivity, and manufacturing
constraints.

The first supported product profile is deliberately bounded:

- incompressible low-Mach external flow;
- steady or quasi-steady analysis;
- one rigid material;
- STL-only geometry roles;
- uniform Cartesian fixed-grid topology optimization;
- SDF extraction/refinement followed by body-fitted verification.

Compressible flow, fully unsteady flow, fluid-structure interaction, free
surfaces, and production AMR are future capability profiles.

## 2. Authoritative architecture

```text
ProblemSpec v2
  geometry roles + flow cases + responses + constraints + topology policy
        |
        v
Geometry and resolution preflight
        |
        v
OpenFOAM case compilation + requested/generated manifest
        |
        v
Stage T: fixed-grid density/Brinkman topology optimization
        |
        v
Density iso-surface -> SDF rebuild
        |
        v
Stage S: sharp-interface SDF refinement
        |
        v
Stage V: body-fitted RANS verification
```

The Stage T design variable is the cell density field `rho`. STL is an input
surface or a derived exchange/verification artifact; it is not the main
topology design variable.

## 3. Evidence rules

Every result must be labelled as one of the following:

| Evidence class | Meaning |
| --- | --- |
| Contract | Schemas, IDs, hashes, and validation agree. No solver claim. |
| Capability | A backend operation can run on a canonical fixture. |
| Numerical | Residual, mass-balance, stationarity, and gradient gates pass. |
| Target physics | The declared operating point and physics pass cross-fidelity checks. |
| Benchmark | A configured geometry family passes the complete acceptance set. |

Capability or contract evidence must never be reported as target-physics
validation. An `execution_ready` ProblemSpec means the declarations are
complete; it does not mean the mesh, fields, solver, or result are qualified.

## 4. Current position

| Workstream | Status | Current evidence and gap |
| --- | --- | --- |
| G0 scope/evidence model | Complete | Generic rigid-object scope and evidence classes are established. |
| G1 ProblemSpec/artifact contract | Complete | v2 parsing, canonical hash, multipoint responses, topology policy, v1 read-only migration, and semantic readers exist. |
| G2 case compiler | Current-spec numerical convergence passed; physical/native-artifact qualification pending | On 2026-09-07 both freshly compiled flows passed the declared primal, response, adjoint and normalized-mass convergence gates under the current specification hash. See `evidence/openfoam_convergence_2026_09.json`. Response-unit, gradient and grid-transfer semantics plus porous/body-fitted comparisons remain unqualified. |
| G3 geometry/resolution gates | Partial — bounded STL/declared-resolution preflight; fixed far-field domain + clearance preflight implemented | `research preflight` checks STL metadata and declared feature/grid ratios. The 2026-09-19 V3 diagnosis localized all 220 under-determined cells of one rejected candidate to its wall/outer-boundary contact, so clearance is a measured hard-gate requirement. On 2026-09-20 WP1 implemented it: the Stage V far-field box is bound to the ProblemSpec's `grid.domain_bounds_m`, and a declared-margin pre-mesh clearance preflight (profile `stage_v_clearance_v1`, 0.25 m) refuses candidates before `blockMesh`/`snappyHexMesh` — the recorded wrong candidate is rejected with a no-launch artifact (`evidence/stage_v_domain_clearance_2026_09.json`). Self-intersection, actual shape thickness, complete mask/connectivity and density-to-SDF fidelity qualification remain. |
| G4 benchmark ladder | Missing — implementation required | No complete three-family, three-grid generic acceptance set exists. |
| Stage T canonical backend | Path B bounded exception on the refined source grid | The 64x32x32 source-grid campaign with perturbation residual `5e-9` gives FD/adjoint ratios `1.1504 / 1.1134 / 1.1441`; all registered directions are epsilon-stable and keep their sign, but all fail the 5% production gate. The refined-source `checkMesh` gate is measured pass. Canonical-only refinement gives `1.1172 / 2.2454 / 1.8916`, showing design/source-grid coupling; the registered third source-grid level is unrun, so there is no grid-convergence claim. |
| Stage T canonical closed loop | Bounded real-OpenFOAM path implemented | PQ0.1 connected the compiled projected-volume value/gradient, separated parent adjoint from trial primal, reused accepted primal artifacts and integrated the Path B centered-FD bracket. PQ0.2 exercised the real parent/trial/bracket/rollback/resume path. PQ3 then accepted three real OpenFOAM improvement steps. This is capability and bounded Path B evidence, not production-gradient or target-physics qualification. |
| Stage T production optimizer | Candidate formation in progress; not qualified | PQ3.1 reached solver-field discreteness but not extraction coherence; PQ3.2 showed that an upper volume bound alone does not fill the material budget; PQ3.3 reached `beta_solver` mean_nd 0.00388 and max 0.94395, but the `b=16` level accepted no steps and projected volume fell from 0.02745 to 0.01302. The present volume-target backend constrains raw design mean rather than projected volume. Projected-gradient and volume-target OC remain proposal rules; MMA/GCMMA is deferred. |
| Stage S | Composite entry gate implemented; no qualified handoff candidate | The current verdict is `ready_for_stage_s=false`. The PQ3.3 handoff contoured RAMP output `beta_solver` at 0.4–0.6 even though the adopted geometry field is `rho_projection`; at q=100, beta=0.5 corresponds to projection about 0.9902. Re-materialization on the correct field and fail-closed repairs to self-intersection, gap, minimum-width and volume-calibration measurements precede PQ4.1. Downforce surface-gradient qualification and one accepted body-fitted update remain missing. |
| Stage V | Drag bounded; downforce reference unresolved | With `linearUpwind`, drag finest-transition drift is 0.364% and passes its 2% bound. Downforce remains non-monotone with 0.010374 drift against the 0.005 absolute bound. The preregistered domain/boundary V2 factor campaign is not run; there is no downforce GCI or grid-independent claim. |

The 2026-09-10 effectiveness spike proves only local numerical control inside
the fixed-grid Brinkman model. It does not prove constrained optimization or
the Stage T -> Stage S -> Stage V architecture end to end. The canonical start
is infeasible for the recorded efficiency and active-cell mean-`rho` limits,
and the current T5 output cannot be passed as the same candidate to Stage S/V.

### Stage T has never produced a design — 2026-09-12

This invalidates every prior Stage T optimization result and every Stage S
handoff attempt. Three separate defects were measured, not inferred.

1. **The declared problem was degenerate.** The repository template
   `examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base/system/optimisationDict`
   declares `downforce` with `isConstraint true; target 0;` and `drag` as the
   only weighted objective. The problem actually solved was "minimize drag
   subject to downforce == 0 and volume fraction == 0.462". Any material
   creates vertical force and violates the equality, so the optimizer stays at
   zero material. This is the repository's own template, not a stray work
   artifact.
2. **The volume constraint does not engage.** Reformulating `downforce` as a
   `weight -1` maximization objective did not help. Across a 40-cycle run and a
   20-cycle run the design converged to the same fixed point: beta histogram
   `[8080, 2, 110, 0, 0, 0]` over bins `[0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]`, mean
   0.0070, **zero cells above 0.5**, realized volume fraction approximately
   0.007 against the 0.462 target. The `vol` objective value is frozen near
   1.1493 in both runs and its Lagrange multiplier is pinned at approximately
   1.99999999, which equals the ISQP penalty parameter `c = 2`.
3. **The iso-surfaces handed to Stage S were not design surfaces.** Every
   `topOIsoSurface*.stl` from every cycle of every run is identical: 5120 faces,
   2822 vertices, not watertight, 6 connected components sized
   `[1024, 1024, 1024, 1024, 512, 512]`, bounds exactly equal to the domain box.
   That is the six flat boundary patches of the 32x16x16 domain. A 0.5
   iso-surface of a field that never reaches 0.5 has nothing to trace.

### Root cause, and the optimizer decision — 2026-09-12

The native ISQP path was diagnosed against the OpenFOAM v2512 sources. Three
independent faults, detailed in `stage_t_optimizer_diagnosis_2026_09.md`:

- `topOVolume`'s `percentage` is a **fluid-fraction cap over the whole mesh**,
  `J = (1 - <beta>_V - percentage)/percentage`. With the template's 0.462 and
  the 5283 forced-fluid buffer cells out of 8192, the minimum attainable `J` is
  `+0.396 > 0`: the constraint is **unsatisfiable by construction**. The
  observed frozen value 1.1497 matches the formula exactly.
- The multiplier pinned at the ISQP penalty `c` is the genuine elastic-variable
  signature of that infeasibility, not a red herring. The volume sensitivity is
  ~4000x smaller than the drag sensitivity, so it is invisible in the QP.
- `function linear` makes the projection the identity, so no 0.5 crossing can
  form at all. The tutorials use `tanh; b 20`.

With those repaired, the native path does produce real watertight design
components (one run reached downforce 1.029 against a 0.636 baseline), but it
still oscillates: an Armijo line search hits its iteration cap every cycle,
showing the ISQP direction is not a descent direction for the projected
problem. This is not a gradient error.

**Decision: optimization moves to Python permanently.** Optimality-criteria
updates on the same verified adjoint gradient advanced monotonically from the
first attempt (see below). The OpenFOAM template is retained as a primal and
adjoint evaluator only; its `vol` constraint solver and its `downforce`-as-
constraint solver should be removed, keeping `drag` and `downforce` as
independent adjoint solvers.

Also recorded: the 5120-face / 6-component STL signature arises because the
iso-surface writer always emits the domain boundary patches. **Stage S must
strip zero-extent components**, or a real design component stays buried among
them.

### Stage T produced its first design — 2026-09-12

Driving the update from Python with the verified canonical gradient and an
optimality-criteria step (volume by bisection, move limit, reject-on-worse),
`downforce_coefficient` rose monotonically from the 0.775975568032 baseline to
0.821317856508 over 12 iterations, every step accepted on its first attempt,
with the iteration-0 sign check agreeing to three digits. The resulting 0.5
iso-surface is 968 faces, 488 vertices, **watertight, 2 connected components**,
volume 0.0249 — not the degenerate signature — and `build_density_to_sdf_handoff`
accepts it with all mask and connectivity checks passing. An empty design
(`rho = 0`) returns `drag = downforce = 0.0` exactly, confirming the objective
carries no geometry-independent offset.

The known limit is structural: a multiplicative OC update cannot lift a cell off
exact zero, so achievable volume caps near 3.2% on this seed without an epsilon
floor.

### The surrogate's ranking did not transfer — 2026-09-12

The architecture only works if the cheap Stage T surrogate **ranks** candidates
the way body-fitted verification does. Absolute agreement is not required: a
Brinkman volumetric-force integral and a surface integral of pressure and shear
are different quantities. The ordering is what must hold.

Both candidates were meshed body-fitted at three resolutions and run at matched
conditions (1 m/s, the Stage T case's own viscosity, `Aref` 0.64, laminar):

| ratio B/A | Stage T | coarse (5.5k) | medium (30k) | fine (180k) |
| --- | --- | --- | --- | --- |
| drag | 2.582 | 0.849 | 0.901 | 0.905 |
| downforce | 3.882 | 3.167 | 0.896 | 0.918 |
| L/D | 1.503 | 3.728 | 0.995 | 1.015 |

The drag ranking is **inverted at every grid**. The downforce ranking agrees
only on the coarsest mesh and flips at both finer ones. A turbulence-model
confound was ruled out: laminar and `kOmegaSST` runs agree to within 0.02% on
drag at Re around 300, so the earlier `kOmegaSST` comparison was valid.

**This must not be over-read as "the Brinkman surrogate is unusable".** Two
concrete defects make the comparison a test of something other than the
surrogate's fidelity, and both are fixable:

- **The designs are not binary.** Candidate A peaks at `rho` 0.62 and candidate
  B at 0.55, with **zero cells above 0.9** in either. Stage T optimized a
  semi-permeable blob; Stage S extracted a solid body at the 0.5 contour and
  Stage V solved that. These are physically different objects. The cause is the
  `function linear` projection defect above.
- **The Stage T grid may be too coarse to resolve what it optimizes.** Its 8192
  cells are comparable to the 5534-cell coarse body-fitted mesh, and that is
  precisely the resolution at which the two fidelities agree; agreement
  disappears as the body-fitted mesh is refined.

These are distinct claims and the present data does not separate them.

**Consequence for the roadmap: a discreteness gate becomes a precondition for
the Stage S handoff.** A grey density field must not be passed downstream, and
no cross-fidelity ranking claim is meaningful until the design is near-binary
and the surrogate grid is shown to be adequate. Whether the surrogate ranks
correctly for a binarized, adequately resolved design is **untested**.

### The haze was the optimum, and why — 2026-09-12

An external audit (`problem_resolution_plan_2026_09.md`) prompted a measurement
that changes the diagnosis from "the optimizer is broken" to "the objective's
optimum is a haze, and the optimizer found it".

Holding the material budget `integral(rho dV)` fixed and spreading it from a
compact body outward, the linear interpolation this project has always used
scores the haze **4.3x better** than the solid, monotonically better the thinner
it gets. Under RAMP penalization the ordering inverts and the compact body wins
by roughly a hundredfold.

The mechanism is worse than an unpenalized interpolation. **The Brinkman force
saturates near `alpha = 25`, which is 1% of the `alphaMax = 2500` in use**, so
99% of the density range is already fully blocking and a material budget buys
the most blocking at the lowest density it can be smeared to. Penalization alone
cannot overcome that: matching the economics at `alphaMax = 2500` would need
`q` around 3000. Lowering `alphaMax` to the saturation knee **and** applying
RAMP with `q = 8 -> 30 -> 100`, re-baselining at each `q`, does.

With that, plus single ownership of projection (OpenFOAM regularisation off) and
gradients from converged adjoints bound to a declared response:

| | before | after |
| --- | ---: | ---: |
| solver-side `beta` max | 0.436 | **1.0** |
| cells above 0.9 | 0 | **1034** |
| `mean(4b(1-b))` | — | **0.005** (gate 0.01) |
| downforce carried by `[0.9, 1]` | 0% (band empty) | **103%** |
| downforce carried by `beta < 0.1` | 77% | **-4%** |
| injected field vs solver field | up to 0.11 apart | **1.9e-9** |
| predicted vs actual step ratio | 0.21 | **0.80-0.97** |
| 0.5 iso-surface | 5120 faces, 6 components, domain box | **2810 faces, watertight, 1 component** |

The chain rule is verified rather than assumed: finite differences against the
analytic directional derivative give **0.965** with the interpolation derivative
included and 0.117 without it.

**Stage S now receives the same object Stage T computed forces on** — the
precondition the earlier ranking test lacked.

### Stage V is now a qualified reference — 2026-09-12

`checkMesh -allGeometry -allTopology`, explicit `residualControl`, and force
stationarity over a final window are hard gates. On the grey candidates, V0/V1/V2
pass every gate (`residual_control_met`, stationary forces), and **V3 at ~1.28M
cells is correctly refused** (`iteration_cap`, `solver_qualified: false`) rather
than silently used.

On that qualified reference the grey-candidate ranking result is unchanged: drag
B/A is 0.849 / 0.901 / 0.905 against Stage T's 2.582. The negative finding
survives qualification — **for grey candidates**, which we now know were the
wrong test. Downforce also remains un-converged (candidate A: 0.0358, 0.0449,
0.0407 across V1/V2/V3), and the grid that would settle it is the one that will
not converge.

### Thick-candidate V3 closes execution, not grid convergence — 2026-09-20

The P15 thickness experiment was requalified on its actual comparison candidate,
`opt_q100_b0_step0_try0_block`. Its V3 mesh has 1,260,201 cells, no
small-determinant failure, and passes the registered mesh profile. The conservatively
relaxed `simpleFoam` run met residual control at iteration 2237; the final residuals
were `Ux=1.50e-7`, `Uy=9.98e-7`, `Uz=3.01e-7`, and `p=6.09e-7`, and both Cd and
downforce passed the final-window stationarity gate. This establishes that a qualified
V3 body-fitted reference is executable on the 32 GiB Mac for this reduced case. The
candidate binding, V0–V3 gates, raw artifact hashes, and runtime are recorded in
`evidence/stage_v_v3_requalification_2026_09.json`.

The force sequence is Cd `2.68528, 3.01397, 3.14010, 3.13009` and downforce
`0.61446, 0.68146, 0.82310, 0.85302` on V0–V3. The finest Cd transition changes by
0.319% and passes the 2% bound. The finest downforce transition changes by 0.02993,
which is still about six times the registered absolute bound of 0.005. The architecture
therefore executes and rejects claims correctly; it has not yet produced a grid-independent
downforce reference for ranking.

### Fixed-domain grid study and wake-refinement family — 2026-09-20

With WP1 in place, the correct candidate was re-evaluated under the declared fixed
domain. Two measured results change the standing picture:

1. **The union-box reference carried an unmeasured ground coupling.** The old cases
   took their outer box from the geometry union bounds, whose bottom sat ~0.19 m below
   the body. Under the declared fixed domain (bottom at z=-0.6 m) the same candidate
   gives Cd ~1.63–1.74 instead of ~3.14 and downforce ~0.51–0.52 instead of ~0.82.
   Union-box force values, ratios, and P16 drifts measured through old V3 are therefore
   not transferable and are superseded for reference purposes
   (`evidence/stage_v_fixed_domain_grid_study_2026_09.json`).
2. **The pre-declared wake-refinement family did not settle the bounds and isolated the
   factor.** The plain fixed-domain family qualified V1/V2/V3 (33k/188k/1.35M cells;
   V0 refused by the mesh profile at 9.57% concave > 8%, no solver launch). Finest
   downforce drift improved to 0.01291 (2.3x better than union box) but remained above
   the 0.005 bound, and Cd still changes ~3% per transition. A pre-declared level-3
   near-wake refinement box produced three *further* qualified levels (V3 via a
   declared endTime continuation 3000→6000; the endTime cap itself correctly refused
   the first attempt) and moved forces by only ~0.003 — downforce still misses the
   bound (V2→V3: 0.0147). Conclusion: near-wake local refinement is not the dominant
   factor behind the drift.
3. **The steady reference is a valid time-mean of the laminar physics.** The WP3
   pre-declared fallback — pimpleFoam, 15 s = 5 flow times on the same plain V2 mesh —
   reproduced the steady point (Δdownforce -8.6e-5, ΔCd -0.09%, final-window std ~8e-8,
   no shedding) and rules out unsteady contamination
   (`evidence/stage_v_transient_check_2026_09.json`). The residual V2→V3 drift is a
   refinement-family discretization effect; no further factor remains inside the
   pre-declared WP3 program. The honest continuations are a newly registered
   discretization factor, or WP4 contract work followed by the 8-candidate ranking
   experiment with the measured uncertainty band stated explicitly.

An earlier V3 attempt targeted the wrong 1,600-cell `keep_round` candidate. That candidate
failed the determinant gate at every level. All 220 V3 under-determined cells touched the
candidate wall and 208 also touched the outer top patch; the candidate `zmax` equaled the
far-field top. This exposed a separate G3 contract gap: candidate-to-far-field clearance and
fixed outer-domain binding must be checked before Stage V generation. Quality thresholds are
unchanged.

The next qualification slice is deliberately one factor at a time:

1. ~~bind the outer CFD domain to the ProblemSpec and fail before meshing when candidate clearance
   is below a declared physical margin~~ — **implemented 2026-09-20 (WP1)**: fixed
   `grid.domain_bounds_m` binding plus the `stage_v_clearance_v1` pre-mesh preflight
   (0.25 m declared margin); the recorded wrong candidate is refused before any mesh
   command (`evidence/stage_v_domain_clearance_2026_09.json`);
2. freeze the qualified `step0` geometry, operating point, numerics, and force normalization;
3. replace another global halving with a predeclared local-refinement family around the body and
   wake, then require three qualified levels and the same Cd/downforce bounds;
4. if downforce still misses the 0.005 bound or steady residuals stop decaying, compare steady
   RANS with a time-resolved run on the same mesh before changing the design formulation;
5. resume cross-fidelity ranking only after the body-fitted downforce reference passes. No FSAE
   full-vehicle or high-Re claim inherits qualification from this laminar reduced case.

## 5. G1 — generic problem and artifact contract

Status: complete.

The contract provides:

- coordinate frame and SI units;
- typed STL geometry roles;
- one or more flow cases with fluid, turbulence, boundary, and motion data;
- named force, moment, pressure-loss, flow-rate, and plugin responses;
- weighted objectives and aggregate constraints;
- solid/void connectivity and minimum-feature topology policies;
- deterministic snapshots and SHA-256 problem binding;
- flow-scoped and topology-scoped artifact keys;
- non-destructive v1 migration/read support.

G1 completion is contract evidence only.

## 6. G2 — solver compiler and target-physics bridge

Status: prior-spec numerical convergence gate passed; current canonical-domain
specification requires runtime requalification before physics qualification.

Implemented:

- `compile-openfoam-problem-cases` CLI;
- deterministic per-flow OpenFOAM cases and bundle metadata;
- incompressible Newtonian fluid properties;
- laminar and `k_omega_sst` profiles;
- freestream, pressure outlet, symmetry, stationary wall, and moving wall BCs;
- translation motion profiles;
- force-response adjoint managers and reference quantities;
- `Allrun`/`Allclean` and custom objective-library staging;
- fail-fast execution scripts;
- mesh patch-type compilation and requested/generated validation;
- primal/adjoint residual, normalized mass balance, response stationarity, and
  fatal-log convergence qualification.
- OpenFOAM v2512 Docker smoke execution for both configured G2 flow cases;
- real log extraction with response-to-adjoint context and provenance-bound,
  fail-closed convergence evidence.
- explicit boundary-`phi` mass-flux measurement and normalized-mass artifacts;
  raw continuity-error text is never converted into that metric.
- fail-closed native v2 primal/sensitivity writer and readiness CLI. It writes
  only when an explicit semantic binding proves response units, `rho` gradient
  convention, mesh-grid correspondence, and topology-policy values.
- fail-closed reconstruction of final decomposed `topOSens`, `alphaTilda`,
  `beta`, and raw-`alpha` provenance in OpenFOAM global-cell-label order;
  raw `topologySens` remains audit-only.
- source-grid reconstruction for one ungraded, axis-aligned `blockMesh` hex,
  plus hash-bound canonical-grid snapshots and exact-overlap transfer
  primitives. These contracts do not yet perform a real G2 transfer.

Current supported response compilation is force-only. Moment, pressure loss,
flow rate, rotating-wall motion, and plugin responses must be rejected
explicitly until implemented.

Remaining implementation:

1. Supply and qualify semantic bindings for native v2 primal and sensitivity
   artifacts from real runs. Both G2 flows were recompiled, rerun and numerically
   qualified under the current hash on 2026-09-07. Native export still requires
   evidence for the following semantic issues: its
   `porousDirectionalForce` output is a coefficient rather than proven `N`,
   its final `topOSens` to `rho` chain has not passed finite-difference
   validation, its reconstructed mesh fields have not been transferred to a
   canonical-grid snapshot, and it has no topology-policy values.
2. Qualify wall-distance/turbulence treatment; current `meshWave` metadata is
   not porous-aware and remains unqualified.
3. Compare porous and body-fitted pressure force, skin friction, total force,
   and gradient direction on simple geometries.

G2 smoke gate:

- compilation is `compile_ready=true`;
- requested/generated values and patch types match exactly;
- all setup applications and solver initialization complete without fatal
  errors;
- a run artifact is written even when the deliberately short smoke run is not
  numerically converged.

G2 qualification gate:

- all configured flow cases pass residual, normalized mass-balance, response
  stationarity, and adjoint-residual thresholds;
- porous/body-fitted comparisons are within documented tolerances;
- execution qualification is never inferred from an end marker alone.

## 7. G3 — geometry and physical-resolution gates

Status: partial — bounded STL and declared-resolution preflight implemented.
The full gate below remains required; the new command reports omitted checks.

Implement:

- unit and coordinate-frame validation;
- watertightness, orientation, self-intersection, and degenerate-face checks;
- fail-closed voxelization for critical roles;
- cells-per-feature checks for minimum solid width, void width, and gap;
- rejection when erosion/dilation radius is smaller than represented spacing;
- density-to-SDF volume error, surface/Hausdorff error, hard-mask violations,
  component/root preservation, and feature-survival metrics.

Acceptance fixtures must prove that a one-cell bridge fails, a sufficiently
wide bridge passes, and a no-op erosion cannot be reported as manufacturing
evidence.

## 8. G4 — benchmark ladder

Status: missing — implementation required.

Advance using YAML/STL replacement rather than benchmark-specific core code:

1. B0 geometry: sphere, box, thin plate, multiple components, invalid STL.
2. B1 numerical topology: islands and two-to-six-cell bridges; cellwise and
   filtered-random derivative checks.
3. B2 laminar 2D/2.5D: channel, cylinder, and NACA with three grids.
4. B3 turbulent bridge: flat plate and NACA porous/body-fitted comparison.
5. B4 generic 3D: finite wing, bluff body, and multi-component object.
6. B5 front wing: isolated wing, moving ground, roots/endplates, then optional
   vehicle and rotating-tire profiles.

Generic acceptance requires at least three geometry families, three-grid
evidence, filtered-random gradient checks, grey-density reporting,
extracted-geometry constraint status, and reproducibility metadata.

## 9. Stage T — production topology optimizer

Begin production T work only after G2 runtime qualification and the relevant
G3/G4 gates pass.

Implementation order:

1. Qualify real-run semantic bindings for the implemented fail-closed native
   v2 primal/sensitivity writer.
2. Generic response/objective/aggregate derivative assembly.
3. Production analytic/adjoint nominal and eroded connectivity derivatives.
4. Filter/projection continuation with explicit chain-rule metadata.
5. Nonlinear iteration with primal re-evaluation, acceptance/rollback, move
   bounds, checkpoints, resume, and deterministic artifacts.
6. GCMMA or equivalent constrained backend behind the existing optimizer
   interface.
7. Mesh epochs and conservative state/gradient transfer only after the uniform
   fixed-grid profile is qualified.

The existing projected-gradient and linearized SLSQP backends validate
plumbing; they are not the production nonlinear optimizer.

## 10. Stage S and Stage V

Stage S implementation order:

1. Quantify density-to-surface/SDF fidelity.
2. Use body-fitted-first refinement as the baseline.
3. Select ghost-node IBM or cut-cell research backend only after an explicit
   accuracy, adjoint, and implementation-cost comparison.
4. Add Hamilton–Jacobi updates, reinitialization, curvature control, and
   output-based adaptation.

Stage V acceptance requires three-grid body-fitted RANS evidence, pressure and
skin-friction decomposition, force/moment agreement, mesh-quality checks, and
cross-fidelity comparison with Stage T/Stage S.

## 11. Immediate execution order

The adopted architecture plan is
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md).
The current post-PQ3.3 execution detail is
[`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md).
Both retain Stage T -> Stage S -> Stage V and are subordinate to this roadmap.

Current status on 2026-09-23:

- PQ0.1 closed the nonlinear integration defects for the reduced problem:
  compiled projected volume, parent/trial oracle separation, accepted-primal
  reuse, fail-closed parent adjoint, Path B centered-FD bracket and semantic
  names are integrated. PQ0.2 exercised the real OpenFOAM oracle path with a
  correct rollback and deterministic resume. These are bounded capability
  results, not a production-gradient claim.
- PQ1 remains a **Path B bounded exception**. The refined source grid gives
  FD/adjoint ratios `1.1504 / 1.1134 / 1.1441` with stable epsilon plateaus.
  PQ1.1 measured the refined source mesh gate as pass, but canonical-only
  refinement changed the ratios to `1.1172 / 2.2454 / 1.8916`; the mismatch
  depends on design/source-grid coupling. The registered third source-grid
  campaign remains unrun. No magnitude correction is allowed.
- PQ3 demonstrated three accepted real-OpenFOAM steps. PQ3.1 reached solver-
  field discreteness but not extraction coherence. PQ3.2 failed because an
  upper volume bound did not fill the design. PQ3.3's raw-design volume target
  grew the b=0 state, then b=8/b=16 reduced projected volume from 0.02745 to
  0.01302; b=16 accepted no steps.
- The PQ3.3 extraction used RAMP output `beta_solver` as the geometry field.
  The adopted geometry/volume field is the pre-RAMP `rho_projection`. With
  q=100, beta threshold 0.5 corresponds to projection about 0.9902, so the
  recorded empty/sparse extraction is not yet a valid 0.5-projection verdict.
  The current global verdict remains fail-closed at `ready_for_stage_s=false`.
- PQ4.0 restored `ready_for_stage_s` as a conjunction and made threshold
  selection fail-closed. Its self-intersection, component-gap, minimum-width
  semantics and volume-profile calibration still require correction before a
  qualified PQ4.1 verdict.
- Stage V `linearUpwind` qualifies drag at 0.364% finest-transition drift.
  Downforce remains non-monotone at 0.010374 against the 0.005 bound. The
  preregistered domain/boundary factor remains unrun.
- No optimizer-generated candidate has `ready_for_stage_s=true`.

Execute in this order:

1. **PQ3.3a — semantic re-materialization.** Without more CFD, reconstruct
   `rho_design`, `rho_filtered`, `rho_projection` and `beta_solver` from the
   saved PQ3.3 candidate; bind their hashes; contour `rho_projection`; verify
   the exact RAMP threshold mapping; and add an immutable correction artifact
   for the PQ3.3 evidence ID. This re-judgment is diagnostic because the b=16
   level has no accepted step.
2. **PQ4.0a — repair the entry measurements.** Replace the invalid self-
   intersection probe, measure actual inter-component gap, align minimum-width
   semantics with ProblemSpec, and calibrate volume fidelity on analytic binary
   shapes. Required but unmeasured checks fail closed.
3. **PQ3.3b preflight and implementation.** Make the proposal target
   `V(rho_projection)` over the declared design-active mask, reject unreachable
   targets, verify the final residual, and test b=8/b=16 reachability from the
   saved state. Use a projected target no larger than Vmax; do not reuse the raw
   design target 0.10 as a projected-volume target.
   **Current status (2026-09-23):** the raw-design target basis was abandoned
   after preflight v1 (diagnostic evidence) showed measurably sub-threshold
   material; the multiplicative OC family was measured locally infeasible for
   the projected target 0.018 inside a single step's move box at every level
   (preflight v2/v3 evidence and the blocked manifest are registered as
   diagnostics). The registered two-phase policy (projected-volume restoration
   backend + volume-corrected objective backend) reached the target in 1/3/7
   steps in preflight v3 at b=4/8/16. Preflight v4 accepted only b=4, but its
   b=8 failure ledger was lost and it carried the b=4 restoration state rather
   than the objective-accepted state. Preflight v5 corrected that lineage and
   repeated the identical baseline as two independent uncached OpenFOAM runs.
   It accepted b=4 and restored b=8 projected volume to 0.018 in three steps.
   All five b=8 trial candidates improved canonical J and raw downforce, but
   none could form the registered centered Path B pair: design-active cells
   sat exactly at rho=1 and moved inward, so the minus perturbation exceeded
   the box. No b=8 candidate was accepted and b=16 was not evaluated. This is
   a bracket-feasibility failure, not measured evidence that the directions
   are non-descent. At that preflight point, the v3 manifest remained
   `registered_blocked`; the later v4 campaign result is recorded below.

   **Preflight v6 result:** exact box-face cells were frozen in the Phase 2
   proposal and its projected-volume correction; the centered Path B rule was
   unchanged. With objective-accepted rho passed exactly between levels,
   b=4/b=8/b=16 each restored projected volume to 0.018 and accepted alpha=1.0
   after a signed adjoint/FD bracket and an improving real trial. The b=16
   parent/trial raw downforce was 0.316591/0.319135. All 13 referenced solver
   summaries in the v6 artifact were present and matched their recorded SHA-256.
   This is **preflight feasibility only**: it proves neither ten accepted
   iterations and level convergence nor extractable Stage S geometry.

   **Preparation completed before the long run:** campaign manifest v4 fixes
   the input, compiled-problem, Python source, runner, solver-image, template
   and v6 evidence hashes. Its runner's read-only `--verify-preconditions`
   passed for manifest SHA-256
   `01d40d48ebe12f73e66ab646ed51c1cce611b28901f6cc7ee7564abed2753484`.
   It checkpoints accepted rho, verifies the checkpoint chain on resume,
   requires ten accepted steps and the registered stability window per level,
   and makes an independent final primal check. The real multi-iteration
   campaign was then run under the registered v4 manifest. The b=4 level
   converged after 23 accepted objective steps. The b=8 level restored
   projected volume to 0.018 and accepted eight objective steps, but its ninth
   attempt stopped: every alpha's centered pair had an objective difference
   near `7.2e-7`, below the registered `1e-6` absolute noise floor. All five
   trial primals improved downforce; this does not waive the Path B bracket.
   The b=16 level and terminal check were not run. The immutable result is
   [`evidence/pq3_3b_campaign_v4_outcome_2026_09.json`](evidence/pq3_3b_campaign_v4_outcome_2026_09.json).

   A separate diagnostic at the exact b=8 stopped rho repeated the parent
   primal and tested centered epsilons `2e-4`, `4e-4` and `8e-4` with the same
   `1e-6` floor. All three formed acceptable brackets with stable negative
   FD slopes; see [`evidence/pq3_3b_bracket_recovery_v1_2026_09.json`](evidence/pq3_3b_bracket_recovery_v1_2026_09.json).
   Manifest v5 registers `epsilon=8e-4` and a verified continuation from the
   eighth accepted b=8 checkpoint in a separate output directory, preserving
   the b=4 and b=8 histories. It is locally qualified at the stopped b=8
   parent only; all future proposals retain fail-closed brackets. The user's
   2026-09-23 instruction authorizes starting this bounded optimization.
   The v5 run accepted three more b=8 steps (11 in total), raising same-level
   downforce from the v4 stop value `0.579504694421` to `0.579818003757`.
   Attempt 12 then rejected every alpha. At alpha=1, the centered bracket
   passed, but the trial improvement was `2.7124e-7`, below the registered
   `1e-6` improvement threshold. Smaller corrected updates collapsed to
   machine-scale or zero. The last three accepted objective changes were
   `1.0881e-4`, `1.0734e-4`, and `9.7168e-5`, so the registered requirement
   that all three be at most `1e-4` was **not met**. The immutable result is
   [`evidence/pq3_3b_campaign_v5_outcome_2026_09.json`](evidence/pq3_3b_campaign_v5_outcome_2026_09.json).
   Stop the current campaign here. Before registering any v6 run, diagnose
   box-face saturation, volume-correction cancellation, actual corrected-step
   norms, and independent objective repeatability at this checkpoint. A
   normalized FD direction built from a machine-scale corrected step must
   not be treated as evidence of an effective optimizer update. Define an
   explicit measurable-stationarity rule or a justified proposal change in a
   new manifest before another long run; do not retroactively relax v5.
   Stage S remains blocked until campaign convergence, terminal evaluation
   and PQ4.1 pass.
4. **PQ3.3b stopped-state diagnosis, then bounded continuation if justified.**
   Preserve v4/v5 artifacts. Measure why the volume-corrected Phase 2 update
   collapses at the v5 b=8 checkpoint and verify objective repeatability.
   The bounded diagnostic and decision rules are specified in
   [`pq3_3b_post_v5_plan_2026_09.md`](pq3_3b_post_v5_plan_2026_09.md).
   Only a new immutable manifest with a justified stopping/proposal rule may
   resume the campaign. Each b/q level must recompute its parent and pass
   Path B brackets, real trial primals, projected-volume feasibility, minimum
   iteration counts and objective/field stability. A terminal b=16 candidate
   needs level convergence and an independent feasible evaluation under the
   original upper-bound problem.

   **Current status (2026-09-23, D0--D3 executed):** D0
   ([`evidence/pq3_3b_stopped_state_diagnosis_2026_09.json`](evidence/pq3_3b_stopped_state_diagnosis_2026_09.json))
   reconstructed the stopped parent from verified saved artifacts with no new
   solver run and reproduced every registered alpha kappa exactly: 9495 active
   cells are frozen at exact 0/1 box faces (9263 at zero), and the uniform
   volume correction cancels the objective sign step at machine scale for
   alphas <= 0.5; only alpha=1 leaves a 2.67e-5 inf-norm corrected update whose
   objective dot is -3.1e-7. D1
   ([`evidence/pq3_3b_d1_discriminant_outcome_2026_09.json`](evidence/pq3_3b_d1_discriminant_outcome_2026_09.json))
   ran the pre-registered bounded discriminant (10 fresh primals, budget
   respected, parent spread 0.0): the registered corrected step improved only
   +2.71e-7 (below threshold), while the objective-only direction without the
   equality volume pullback improved +0.13399 and the orthogonal
   volume-exchange direction +0.02789 with the projected volume held near
   0.018. D2 registered the minimal change
   ([`evidence/pq3_3b_d2_change_manifest_2026_09.json`](evidence/pq3_3b_d2_change_manifest_2026_09.json)):
   policy `objective-oc-inequality-v1` drops the equality volume correction,
   enforces the original `V<=Vmax`, rejects machine-scale corrected updates
   (1e-8 inf-norm gate) and adds an extractability guard against the recorded
   stop-state occupancy (explicitly not a PQ4.1 substitute). The immutable v6
   campaign manifest
   ([`evidence/pq3_3b_campaign_manifest_v6_2026_09.json`](evidence/pq3_3b_campaign_manifest_v6_2026_09.json))
   is registered as `registered_preflight_pending`. The two-stage entry
   preflight passed
   ([`evidence/pq3_3b_v6_entry_preflight_2026_09.json`](evidence/pq3_3b_v6_entry_preflight_2026_09.json)):
   one inequality step at the b=8 stop point accepted +0.13399 downforce; the
   b=16 transition lowered the projected volume by only 1.06e-6, the formation
   target was maintained, and one b=16 inequality step accepted +0.02556. The
   long v6 campaign is NOT started; a campaign runner is not implemented and an
   explicit user go is required. Stage S remains blocked.

   **Campaign cycles run (2026-09-23):** the v6 inequality campaign accepted
   nine b=8 steps (same-level downforce 0.579818003757 upward; projected
   volume reached 99.1% of Vmax) and stopped fail-closed when every alpha
   exceeded the volume bound
   ([`evidence/pq3_3b_campaign_v6_outcome_2026_09.json`](evidence/pq3_3b_campaign_v6_outcome_2026_09.json)).
   The registered alternative was implemented as the minimal active-set
   change: `volume_cap_correction` projects the sign step back onto the
   feasible set. The v7 manifest resumed at the v6 checkpoint
   ([`evidence/pq3_3b_campaign_manifest_v7_2026_09.json`](evidence/pq3_3b_campaign_manifest_v7_2026_09.json))
   after its entry preflight passed
   ([`evidence/pq3_3b_v7_entry_preflight_2026_09.json`](evidence/pq3_3b_v7_entry_preflight_2026_09.json)),
   then accepted 27 more b=8 steps exactly on the Vmax boundary; same-level
   downforce reached 3.82622378522. The registered convergence window was not
   met (one accepted delta 1.31e-4 above the 1e-4 bound) before attempt 28
   rejected every alpha on the machine-scale corrected-update gate, so the
   level stopped fail-closed
   ([`evidence/pq3_3b_campaign_v7_outcome_2026_09.json`](evidence/pq3_3b_campaign_v7_outcome_2026_09.json)).
   The measured state is a cap-constrained near-stationary point of the
   registered policy; no convergence or stationarity certificate is claimed.
   A further level exit or the b=16 transition requires a new pre-registered
   rule (for example a stationarity exit measured separately from the
   accepted-step window) in a new immutable manifest; the long campaign
   remains unstarted for that path and Stage S stays blocked.
5. **PQ4.1 — complete T-to-S handoff.** Extract `rho_projection`, retain
   `beta_solver` as solver audit state, and require the full composite gate.
   Only `ready_for_stage_s=true` may register a Stage S baseline.

   **Current status (2026-09-23):** the Stage T chain reached its first
   converged terminal candidate (v9: b=8 exited by the pre-registered
   cap-stationarity rule, b=16 met the convergence window, independent
   terminal repeat downforce 2.92433989091 at projected volume 0.0763257).
   The composite gate was run on the `rho_projection` iso-0.5 handoff
   ([`evidence/pq4_1_terminal_stage_s_entry_2026_09.json`](evidence/pq4_1_terminal_stage_s_entry_2026_09.json)):
   `ready_for_stage_s=false` with three measured reasons — discreteness
   `mean_nd 0.109` against `0.01`, a measured self-intersecting extracted
   surface, and the clearance preflight below the declared margin. Lineage,
   the projected-volume constraint, volume fidelity (5.97% relative) and the
   width/gap measurement pass. The semantic path (target, backend and geometry
   all on `rho_projection`) is exercised end to end, so P19's semantic
   mismatch is closed; the remaining failures are the physical extraction
   issues tracked under P2/P17/P20 (grey design at the volume cap, surface
   self-intersection, clearance). No Stage S baseline is registered.

   **Margin-mask and b=128 continuation (2026-09-23):** the self-intersection
   reason was a detector bug (barycentric formula) and is fixed (P20); the
   corrected PQ4.1 v2 keeps discreteness and clearance as the two real
   failures. The v10/v11 campaigns then resumed the terminal rho under a
   clearance margin mask (`allowed_mask` restricted to `|y_center| <= 0.475`)
   and a b=128 continuation. The b=128 level accepted 256 steps in total, met
   the registered convergence window (last deltas 3.57e-5 / 3.37e-5 / 2.30e-5)
   and the independent terminal repeat gave downforce `3.36972164196` at
   projected volume `0.0763257`. The PQ4.1 judgment on the registered
   iso-threshold sweep (0.4/0.5/0.6) with the registered
   range-first-that-passes rule selects no threshold: the terminal field
   re-greyed during the campaign (`mean_nd 0.0555` at b=128 against the 0.01
   bound, started at 0.0058), the iso-0.5 surface pinches (non-manifold,
   handoff rejected) and iso 0.4/0.6 fail feature shrink / surface distance
   and volume fidelity. Conclusion: the Phase 2 acceptance lacks a
   discreteness criterion (the extractability guard only prevents an
   occupancy collapse). The next registered change is a discreteness gate in
   the acceptance (transform-measured, no extra solver runs); no Stage S
   baseline is registered.
6. **Stage S first step.** Qualify drag and downforce surface derivatives by
   centered FD, then accept at most one body-fitted shape step and re-run every
   geometry, mesh and solver gate.
7. **PQ2 — Stage V downforce reference.** This may run in parallel with steps
   1--5. Execute the registered V2 domain/boundary campaign unchanged, then
   register only one result-driven factor at a time.
8. **PQ5 — independent Stage V verification.** Evaluate baseline, Stage T and
   Stage S candidates on at least three qualified grids. Preregister
   baseline-to-T and T-to-S required pairs and candidate-specific uncertainty.
9. **PQ6 — production backend and target physics.** Only after PQ5, integrate
   robust fields/connectivity, add actual MMA/GCMMA if warranted, and advance
   through turbulence, finite-wing, moving-ground/multipoint,
   vehicle-interference and physical-validation gates.

PQ7 is not defined by the current authoritative roadmap. Do not create a PQ7
status or use it as an implicit gate without a separate roadmap revision.

No new parametric candidate generator belongs to this execution sequence.
Fixed-shape generators may be used only as registered diagnostics. A stronger
optimiser, robust projection, control-volume post-processing or custom
sharp-interface solver must not be used to bypass PQ0.1--PQ5.

## 12. Document authority

- `docs/phase_plan.md`: only roadmap and status source.
- `docs/problem_contract_v2.md`: authoritative user problem schema.
- `docs/fixed_grid_data_contract_v2.md`: authoritative Stage T artifact schema.
- `docs/fixed_grid_backend_decision.md`: selected-backend decision record.
- `docs/downforce_optimization_architecture_plan_2026_09.md`: adopted detailed
  downforce implementation and qualification plan, subordinate to this roadmap.
- `docs/stage_t_to_stage_s_bridge_plan_2026_09.md`: current post-PQ3.3 bridge
  plan and gate detail, subordinate to this roadmap.
- `docs/git_branching_strategy.md`: repository workflow.

If another document conflicts with this roadmap, this file wins and the
conflicting document must be corrected or removed.
