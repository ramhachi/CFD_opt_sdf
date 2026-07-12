# TSV Roadmap: Generalized Fixed-Grid Topology, SDF Refinement, Body-Fitted Verification

Date: 2026-07-10
Plan name: `TSV Roadmap`
Status: authoritative, revised for generic-object expansion
Supersedes: `Legacy A-K Body-Fitted Adjoint Roadmap`

This is the authoritative implementation plan for a topology-changing external
aerodynamic optimization tool. The front wing is the first complex integration
benchmark, not the definition of the product scope. It follows the architecture
in `docs/deep-research-report.md` and `docs/sdf_cfd_optimization_thread.md`.

## 1. Direction

The project is not a parametric front-wing optimizer. Its primary purpose is to
allow material and topology to appear, disappear, join, and separate inside a
fixed design domain while satisfying aerodynamic, geometric, and optional
manufacturing constraints.

The first generic-product scope is deliberately bounded:

- Rigid, single-material designs.
- Incompressible, low-Mach, steady or quasi-steady external flow.
- A bounded design domain with fixed geometry and explicit boundary conditions.
- Arbitrary input geometry and allowed topology policies within that domain.

Compressible flow, fully unsteady flow, fluid-structure interaction, free
surfaces, and moving-body physics are separate capability profiles. A moving
ground or rotating wheel may be enabled by an external-flow profile; it is not
silently assumed for every object.

The required pipeline is:

```text
Problem specification: geometry roles, flow cases, QoIs, constraints, topology policy
         |
         v
Geometry Service and fixed density grid
         |
         v
Stage G: generic contract, case compilation, geometry/resolution gates
         |
         v
Stage T: fixed-grid density/Brinkman topology optimization
        |
        v
Density iso-surface extraction and SDF rebuild
        |
        v
Stage S: SDF sharp-interface shape refinement
        |
        v
Stage V: body-fitted RANS verification
```

The design variable in Stage T is the grid density field `rho`, not an STL and
not a low-dimensional set of wing parameters. STL or other supported surface
input is geometry input or a derived exchange/verification artifact.

## 2. Non-Negotiable Rules

- The main optimizer must not return to low-dimensional parametric geometry.
- Every problem must declare its coordinate frame, reference values, flow cases,
  boundary conditions, responses, objectives, constraints, and topology policy.
- Stage T must compile the declared flow case into the actual solver case and
  write a manifest proving the values used by the solver.
- Topology-stage CFD uses a fixed mesh inside each mesh epoch. The current v1
  profile is uniform Cartesian only; Octree/AMR is not claimed until its grid
  contract and epoch-transfer maps are implemented.
- Topology-stage aerodynamic derivatives must be volume derivatives with
  respect to density/porosity, not only projected surface-shape derivatives.
- Allowed, forbidden, fixed-solid, anchor/root, and optional void-policy regions
  remain independent fields.
- Forbidden and outside-allowed cells use hard projection.
- Connectivity is an explicit policy, not a universal assumption. Supported
  policies will include disabled, single component, root connected, required
  root groups, and bounded component count.
- When a root-connected policy and minimum-width requirement are enabled,
  nominal and eroded designs both receive differentiable connectivity checks.
- Flood fill and SDF morphology remain final discrete validation checks, not
  substitutes for differentiable constraints.
- An erosion or dilation claim is invalid when its physical radius is smaller
  than the represented cell size. Minimum solid width, void width, and gap
  requirements must pass a resolution gate before optimization.
- The front-wing objective is `minimize -C_DF` subject to
  `E_min * C_D - C_DF <= 0`. Generic problems instead use named response IDs
  and configured objective/constraint expressions.
- The first execution of a profile may use one operating condition, but the
  schema must retain `(flow_case_id, response_id)` on every flow-dependent value
  and gradient. Flow-independent topology gradients instead retain
  `(scope=topology, constraint_id)` and must not invent a flow-case ID.
- Body-fitted remeshing is verification work. It must not occur at every inner
  Stage T optimization iteration.
- An `efficiency_min` override can test control flow, but it is never evidence
  that the configured project target has been achieved.

## 3. Stage Ownership

### Geometry Service

Owns:

- Surface ingestion with unit, watertightness, orientation, self-intersection,
  and degeneracy preflight.
- SDF generation for design, fixed, allowed, forbidden, and root roles.
- Grid definition and feature-resolution checks.
- Erosion, dilation, closest-point, normal, and morphology operations.
- Density/SDF/STL conversion.
- ParaView exports.

### Stage G: Generic Problem And Case Compilation

Owns:

- Project/data-contract v2 and a v1 front-wing migration adapter.
- Generic named quantities of interest (force, moment, pressure loss, flow
  rate, and future response plugins).
- Flow-case compilation: physical properties, boundary conditions, turbulence
  model, force directions, reference quantities, and motion profiles.
- Uniform-Cartesian and future Octree/AMR grid contracts.
- Solver-manifest, convergence, and resolution gates.

### Stage T: Fixed-Grid Topology

Owns:

- Density/phase field `rho`.
- Brinkman/Darcy interpolation `alpha(rho)`.
- Fixed-grid primal flow.
- Named response volume derivatives and configured objective/constraint
  derivatives.
- Topology-policy constraints, including root-connected virtual diffusion where
  selected, on nominal and eroded density fields.
- Density filtering, Heaviside projection, and continuation.
- GCMMA or an equivalent constrained optimizer after target-physics and
  gradient gates pass.
- Mesh epochs and optimizer restart at epoch boundaries.

### Stage S: SDF Sharp Interface

Owns:

- Density iso-surface extraction.
- SDF rebuild and reinitialization.
- A body-fitted-first refinement path.
- A separately selected ghost-node IBM or implicit cut-cell research backend.
- Hamilton-Jacobi normal-velocity updates.
- Curvature and surface regularization.
- Output-based mesh adaptation.

### Stage V: Body-Fitted Verification

Owns:

- SDF/STL-derived body-fitted meshing.
- Boundary-layer-capable RANS verification for the declared flow case.
- Pressure, skin friction, force, moment, geometry, and mesh-quality checks.
- Cross-fidelity comparison with Stage T and Stage S.

The existing `simpleFoam`, `snappyHexMesh`, and
`adjointOptimisationFoam` adapter work belongs primarily to Stage V and to an
early Stage S adapter prototype. It is not the Stage T topology solver.

## 4. Current Position

| Area | Status | Evidence or Gap |
| --- | --- | --- |
| Geometry Service | Implemented prototype | Role-specific SDFs, density VTI, STL extraction, morphology checks, ParaView output; robust arbitrary-CAD preflight and scalable sparse/AMR storage are pending |
| Stage G contract | G1 contract layer implemented | Generic v2 problem model, canonical snapshot/hash, legacy migration, CLI validation, generic example, and scoped fixed-grid artifact readers/semantic validators exist; this is contract evidence, not solver execution |
| Stage G case compiler | G2 missing | The T2 adapter copies a fixed OpenFOAM template; compiling project operating conditions, reference quantities, responses, motion, and generic boundary conditions is **implementation required** |
| Stage T data state | v2 schema/reader/validation complete | Multipoint response/objective/scoped-constraint summaries and gradient bindings are readable and semantically validated; v2 solver writers, G2 integration, and AMR field support are **implementation required** |
| Stage T fixed-grid primal | T2 capability complete | Density VTI runs on a fixed mesh without remeshing; completed cases are solver-template capability evidence, not target-physics front-wing evidence |
| Stage T Brinkman model | T0a verified | `topOSource` and porous-force capability cases run in Docker |
| Target turbulent external-flow qualification | T0b missing | Physical properties, turbulence/wall-distance treatment, target boundary conditions, and porous/body-fitted comparison are not yet qualified |
| Stage T volume adjoint | T3 canonical cellwise validated | Canonical drag/downforce/efficiency checks pass; filtered-random, target-physics, and generic-response validation are pending |
| Virtual-diffusion connectivity | T4 finite-difference reference implemented | State fields and diagnostic derivatives exist; production analytic/adjoint derivatives and topology-policy variants are pending |
| Constrained optimizer | T5 linearized backends implemented | Projected-gradient and linearized SLSQP validate plumbing; production nonlinear iteration, acceptance, and GCMMA remain pending |
| Stage S SDF conversion | Partial | Density iso-surface/STL/SDF handoff exists; quantitative fidelity gate is missing |
| Stage S sharp-interface solver | Missing | No selected/validated ghost-node IBM or cut-cell adjoint backend |
| Stage V primal/adjoint | Implemented prototype | Docker/OpenFOAM paths exist; target-profile convergence, grid convergence, and cross-fidelity qualification are pending |
| Reproducible Windows workflow | Partial | PowerShell and Docker profiles exist; real-solver CI, lockfiles, and image digests are pending |

The previous Adjoint Phases A-K remain useful evidence for orchestration,
artifact contracts, body-fitted primal/adjoint execution, post-update
verification, and failure handling. They do not prove fixed-grid topology
optimization. Their original roadmap is retained only as
`docs/phase_plan_legacy_body_fitted.md`.

## 5. Generic Expansion And Target-Physics Gates

These gates are intentionally ahead of production T5/T6 work. The existing
T0--T5 evidence remains valuable, but it does not establish a physical
front-wing result or generic-object support.

### G0. Scope And Evidence Classification

Status: core scope and evidence classification complete. Conventional
bibliography cleanup remains pending before external publication.

- Keep the bounded generic-product scope in Section 1.
- Label T0a--T5 outputs as capability, plumbing, canonical-gradient, or
  target-physics evidence; never use one type as a substitute for another.
- Split TSV evidence from legacy body-fitted calibration evidence in future
  verification reports.
- Replace non-resolvable internal citation markers in research documents with a
  conventional bibliography before external publication.

Gate:

- The plan, README, reports, and CLI help identify the front wing as a
  benchmark profile rather than the core problem definition.
- Capability, plumbing, canonical-gradient, and target-physics claims remain
  explicitly separated. Existing T0--T5 and body-fitted results are not
  generic target-physics proof.

### G1. Project And Fixed-Grid Contract v2

Status: implemented contract layer. Solver compilation and v2 artifact writing
remain in G2 and Stage T integration. **Implementation required there.**

The implemented generic problem specification provides:

- `coordinate_frame` and explicit units.
- `flow_cases[]` with freestream vector, material properties, turbulence
  profile, boundary conditions, and optional motion profiles.
- Reference area, length, moment centre, and force/moment axes.
- Named `responses[]`, `objectives[]`, and `constraints[]`; the front-wing
  downforce/drag efficiency constraint becomes one profile expression.
- `topology_policy`, including root groups, component-count limits, optional
  solid/void connectivity, and minimum solid/void/gap requirements.
- `grid.kind`, with `uniform_cartesian` as the current executable profile and
  `octree_amr` reserved for a future profile with stable cell IDs and epoch
  transfer maps.
- A flow-case ID and response ID on every flow-dependent primal value and
  gradient artifact; topology-only values/gradients use a constraint ID and
  topology scope.
- A v1 front-wing migration adapter so existing evidence remains readable.

Gate:

- A rotated force direction, a moment response, and two flow cases can be
  represented without source-code changes. This gate passes in the generic v2
  example.
- Canonical problem content is hash-bound to v2 primal and sensitivity summary
  namespaces, including aggregate and topology constraint scopes.

Gate evidence:

- `docs/problem_contract_v2.md`
- `docs/fixed_grid_data_contract_v2.md`
- `src/cfd_sdf/problem_spec.py`
- `src/cfd_sdf/fixed_grid_artifacts.py`
- `tests/test_problem_spec.py`
- `tests/test_fixed_grid_artifacts.py`
- `src/cfd_sdf/cli.py`, command `validate-problem-spec`
- `examples/generic_problem_v2/project.yaml`

### G2. Solver Case Compiler And Target-Physics Bridge

Status: missing. **Implementation required.**

Replace template-only Stage T preparation with a compiler from G1 to the solver
case. It must write and validate:

- Freestream velocity and fluid properties.
- Turbulence model and any porous-aware wall-distance/turbulence treatment.
- Inlet, outlet, far-field, symmetry, stationary wall, moving ground, and
  optional rotating-wall conditions.
- Force/moment objective directions and reference quantities.
- A machine-readable manifest of requested and generated solver values.

Qualify this bridge first on simple geometries by comparing porous and
body-fitted pressure force, skin friction, total force, and gradient direction.
The current laminar OpenFOAM capability case is retained as T0a; it is not this
target-physics gate.

Gate:

- The solver case and recorded manifest exactly match the selected G1 flow case.
- Residual, mass-balance, force-stationarity, and adjoint-residual thresholds
  all pass before a result is marked converged.

### G3. Geometry And Resolution Gates

Status: missing. **Implementation required.**

- Validate input units, watertightness, orientation, self-intersection, and
  degenerate faces. Critical role masks must fail closed.
- Reject a morphology claim when `erosion_radius_m < min(cell_spacing)`.
- Require every active minimum solid width, void width, and gap to span a
  documented minimum number of cells for the selected profile.
- Either introduce local refinement/AMR before claiming a physical 10 mm
  front-wing feature, or explicitly use a coarser Stage T feature size and
  defer the final requirement to Stage S/V.
- Add density-to-SDF measurements: volume difference, surface/Hausdorff error,
  hard-mask violations, component/root preservation, and feature survival.

Gate:

- A one-cell bridge fails a width policy, a sufficiently wide bridge passes,
  and a no-op erosion cannot be reported as manufacturing evidence.

### G4. Benchmark Ladder

Status: missing. **Implementation required.**

Use configuration and geometry swaps, not new core code, to advance through:

1. B0 geometry/SDF: sphere, box, thin plate, multiple components, and invalid
   input fixtures.
2. B1 numerical topology: manufactured/Brinkman cases, detached islands, and
   bridges spanning two to six cells; validate cellwise and filtered-random
   directions.
3. B2 two-dimensional laminar: channel/cylinder/NACA cases with grid
   convergence, topology changes, and density-to-SDF comparison.
4. B3 turbulent bridge: flat plate and NACA validation, then porous versus
   body-fitted force and gradient comparison.
5. B4 generic three-dimensional: finite wing, bluff body, and multi-component
   cases with arbitrary force directions and topology policies.
6. B5 front wing: isolated wing plus moving ground, then root/endplate, then
   vehicle and rotating-tire profiles where required.

Generic acceptance gate:

- At least three geometry families run by YAML/STL replacement only.
- Every profile records three-grid evidence, random filtered gradient checks,
  grey-density fraction, extracted-geometry constraint status, and
  reproducibility data.

## 6. Stage T Implementation Plan

### T0a. Fixed-Grid Backend Capability Decision

Status: capability complete. OpenFOAM v2512 passed the fixed-mesh density, Brinkman,
volume-adjoint, constrained-update, field-export, and Docker checks. The
canonical 3D centered checks pass for drag, strict `-Z` downforce, and the
efficiency derivative. OpenFOAM is selected for the first Stage T adapter.

This status is intentionally limited to the canonical capability case. It does
not qualify the configured front-wing operating point, turbulent external flow,
moving-wall physics, or arbitrary response definitions. Those belong to G2 and
the B3--B5 benchmark gates.

Evaluate the current OpenFOAM Docker image first because existing solver
capabilities should be preferred over new research code.

Candidates:

1. OpenFOAM porosity/level-set topology support through
   `adjointOptimisationFoam`.
2. DAFoam topology optimization if OpenFOAM's built-in path cannot expose the
   required density derivatives and constraints.
3. AMReX or a dedicated fixed-grid research solver only if neither existing
   adjoint stack satisfies the contract.

Required capability spike:

- Fixed mesh throughout repeated density changes.
- Cell density or porosity as the actual design variable.
- Brinkman/Darcy momentum penalization.
- Separate directional-force functionals.
- Sensitivity of each selected functional with respect to density.
- Exportable volume fields.
- Docker/WSL automation.
- A path to turbulence-model continuation for the target Reynolds number.

Deliverables:

- `docs/fixed_grid_backend_decision.md`
- A minimal fixed-grid wind-tunnel case.
- Raw and normalized density, porosity, primal, and sensitivity VTI outputs.
- A pass/fail table for every required capability.

Gate:

- Do not extend the current surface-adjoint calibration as the main optimizer
  until this backend decision is complete.

### T1. Fixed-Grid Data Contract v1

Status: capability complete. Schema version 1 is implemented in
`docs/fixed_grid_data_contract.md`. The OpenFOAM adapter generated and
validated all required artifacts on the 8192-cell canonical 3D grid.

The v1 contract remains authoritative only for the current uniform-Cartesian,
front-wing response profile. G1 has delivered the v2 schema, readers, and
semantic validation; solver writers and G2 integration must be implemented
before generic-object or multipoint production work begins.

Add authoritative Stage T artifacts:

- `topology_state.json`
- `density.vti`
- `fixed_grid_case_summary.json`
- `fixed_grid_primal_summary.json`
- `fixed_grid_sensitivity.vti`
- `fixed_grid_sensitivity_summary.json`
- `connectivity_state.vti`
- `topology_iteration_result.json`

Required density-grid arrays:

- `rho`
- `rho_filtered`
- `rho_projected`
- `alpha`
- `allowed_mask`
- `forbidden_mask`
- `fixed_solid_mask`
- `root_mask`
- `active_design_mask`

Required sensitivity arrays:

- `d_downforce_d_rho`
- `d_drag_d_rho`
- `d_efficiency_constraint_d_rho`
- `d_connectivity_nominal_d_rho`
- `d_connectivity_eroded_d_rho`
- `active_design_mask`

Gate:

- All fields share one fixed grid and include schema, sign, units, and source
  solver metadata.

### T2. Fixed-Grid Brinkman Primal

Status: capability complete for the first OpenFOAM fixed-grid adapter. The canonical
suite and a front-wing legacy-density seed execute through Docker with no STL
extraction or remeshing inside the primal solve.

The completed front-wing seed is a density/contract plumbing check. Until G2
compiles its declared physical properties, turbulence model, boundary
conditions, and reference values into the solver case, it is not target-physics
front-wing evidence.

Implement or adapt a fixed-grid external-flow solve with:

- `alpha(rho) u` momentum penalization.
- Density filtering and projection.
- Hard masks for regulation and fixed geometry.
- Force/moment response extraction from declared response IDs.
- One or more configured flow cases compiled by G2.
- No STL extraction or remeshing inside the primal iteration.

Verification sequence:

1. All-fluid field.
2. Fixed canonical solid represented only by density.
3. Existing front-wing density seed.
4. One filtered non-parametric density perturbation.

Gate:

- Density changes alter the flow and aerodynamic outputs on the same mesh.
- Residual, mass-balance, and force histories are written.
- Repeated identical states reproduce the same outputs within a documented
  tolerance.

Evidence:

- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/fixed_grid_primal_suite_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t1_from_legacy/topology_state.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_primal_summary.json`

### T3. Aerodynamic Volume Adjoint

Status: canonical cellwise validated. The T3 adapter extracts OpenFOAM `topOSensas1` and
`topOSensdownforce` volume fields from completed T2 fixed-grid cases, maps them
from OpenFOAM cell-label order back to the contract `vtk-x-fastest` order, and
writes `fixed_grid_sensitivity.vti` plus `fixed_grid_sensitivity_summary.json`.
The plus/minus density-direction suite and finite-difference comparator are
implemented. The initial mismatch came from using the T2 primal-minimal
`adjoint_iterations=1` case as the sensitivity source. A converged-adjoint
baseline passes the canonical cellwise sign/scale checks for drag, downforce,
and the efficiency constraint.

Implement separate derivatives for:

- `J = -C_DF`
- `C_D`
- `g_E = E_min * C_D - C_DF`

The constraint derivative is:

```text
d_g_E/d_rho = E_min * d_C_D/d_rho - d_C_DF/d_rho
```

Verification:

- Cellwise finite differences on a small fixed-grid case.
- Random filtered directional derivatives.
- Centered positive/negative density checks.
- Objective and constraint sign/scale reports kept separate.

Gate:

- Non-degenerate drag sensitivity.
- Objective and constraint directional derivatives pass documented sign and
  relative-error tolerances before optimization uses them.

Implemented evidence:

- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/seed/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/seed/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_drag_execute/fixed_grid_sensitivity_direction_suite_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_baseline_seed_adjoint_4000/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_drag_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_downforce_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_efficiency_constraint_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`

Remaining T3 work before production use:

- Run filtered-random direction checks to catch ordering, filter, and chain-rule
  mistakes that a single-cell perturbation cannot expose.
- Repeat the validation on target-physics cases after G2 and G3 pass.
- Record explicit design-variable metadata for `rho`/`alphaTilda`/`beta`
  continuation before production optimizer runs.
- Generalize the v1 drag/downforce arrays to G1 response IDs while retaining a
  compatibility reader for the existing evidence.

### T4. Root Connectivity And Minimum Connection Width

Status: state evaluator and finite-difference reference derivatives
implemented. The `evaluate-fixed-grid-connectivity` command writes nominal and
eroded virtual-diffusion potential/violation fields and discrete root-component
diagnostics. The `differentiate-fixed-grid-connectivity` command writes
connectivity derivative arrays into `fixed_grid_sensitivity.vti`.

Implement the root-connected virtual-diffusion PDE for the topology policies
that select it, on:

1. The nominal projected density.
2. An eroded density corresponding to configurable minimum connection width.

Also retain:

- Hard regulation projection.
- Flood-fill component count.
- SDF erosion/dilation validation.
- Root-region change tolerance through data-driven masks.

Gate:

- A detached island violates the nominal constraint.
- A thin bridge passes nominal connectivity but fails eroded connectivity.
- A sufficiently thick root connection passes both.
- The erosion radius and bridge width both satisfy G3's physical-resolution
  gate; otherwise the result is explicitly `not_resolved` rather than `pass`.
- Finite-difference reference connectivity derivatives match independent
  central-difference checks.
- Production analytic or adjoint connectivity derivatives pass the same
  finite-difference checks before large optimizer runs.

Implemented evidence:

- `examples/fixed_grid_backend_spike/report/3d/t4_connectivity_seed_no_root/connectivity_state.vti`
- `examples/fixed_grid_backend_spike/report/3d/t4_connectivity_seed_no_root/fixed_grid_connectivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t1_from_legacy_root_fixed/topology_state.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_root_fixed/fixed_grid_connectivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_derivatives_sampled/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_derivatives_sampled/fixed_grid_connectivity_derivative_summary.json`

Historical note: the canonical seed initially reported `missing_root`, then a
touch-cell SDF rule produced 110 front-wing root cells. This proves role-mask
plumbing only. A root or minimum-width claim remains invalid until the G3
resolution gate is satisfied.

### T5. Constrained Density Optimizer

Status: projected-gradient and SLSQP linearized backends implemented;
production optimizer loop and GCMMA backend pending.

Use GCMMA as the first choice for many density variables and few global
constraints. Keep the optimizer behind an adapter so an augmented-Lagrangian
or other method can be compared later.

The generic optimizer consumes G1 named response/constraint definitions.
The following v1 front-wing constraints remain its compatibility profile:

- Efficiency.
- Nominal root connectivity.
- Eroded root connectivity.
- Volume or material fraction.
- Regulation hard projection.
- Optional front/rear balance when its force convention is validated.

Continuation:

- Increase Brinkman penalization.
- Increase Heaviside sharpness.
- Tighten connectivity and minimum-width enforcement.
- Reduce move limit near constraint boundaries.

Gate:

- No fixed manually tuned constraint-gradient blend is required.
- Every candidate runs `primal -> adjoint -> connectivity -> optimizer ->
  candidate primal -> nonlinear acceptance/rejection -> checkpoint`.
- Every accepted update satisfies the linearized constraints and the nonlinear
  primal, topology-policy, and G3 geometry/resolution checks.
- Production GCMMA or an equivalent conservative optimizer is introduced only
  after G2, G3, and the T3/T4 production-gradient gates pass.

Implemented evidence:

- `src/cfd_sdf/fixed_grid_optimizer.py`
- `tests/test_fixed_grid_optimizer.py`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/fixed_grid_constrained_step_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/fixed_grid_constrained_update.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_slsqp_sampled/fixed_grid_constrained_step_summary.json`

The current T5 backends consume the same objective/constraint values and
gradients a GCMMA adapter will consume, reject sampled connectivity derivatives
by default, and record linearized accept/reject decisions. The
projected-gradient backend is a conservative smoke fallback. The SLSQP backend
solves the same linearized constrained subproblem with SciPy and skips the
solve when move bounds make the linearized constraints impossible. Neither
backend is the production GCMMA optimizer.

### T6. Generic Three-Dimensional And Front-Wing Acceptance

Status: pending G2--G4, v2 solver-writer integration, and production T5.

T6 is not the first proof of generality. First pass B4 generic 3D profiles with
configuration-only changes. Then use the front wing as a complex integration
profile without wing shape parameters.

Front-wing execution levels:

1. Isolated wing plus the declared ground-motion condition.
2. Wing, root, and endplate with physical reference values.
3. Vehicle/tire profile, including moving-ground and rotating-wall conditions
   when that profile declares them.
4. Single-point topology run, then a multipoint ride-height/pitch/yaw/velocity
   profile after the single point is qualified.

Required outputs per iteration:

- Density and porosity fields plus grey-density metrics.
- Primal convergence, aerodynamic response, and solver-case manifest.
- Named objective/constraint sensitivities and filtered-random validation.
- Selected topology-policy states and extracted-geometry validation.
- Optimizer, nonlinear acceptance/rejection, rollback, and checkpoint state.
- JSON, CSV, Markdown, and ParaView artifacts.

Stage T completion gate:

- The topology changes without remeshing inside an epoch and produces multiple
  nonlinear accepted, feasible iterations.
- Every declared response/constraint is solver-derived and uses no override.
- G3 feature, hard-mask, and topology-policy checks pass before and after SDF
  extraction.
- Target-physics porous results are compared with body-fitted results on three
  grids, with force, pressure, skin friction, and gradient differences recorded.
- A repeated run resumes from serialized optimizer and field state with the
  same acceptance decision.

## 7. Stage S Plan

### S0. Density To SDF Handoff

- Extract a controlled iso-surface from the Stage T result.
- Rebuild a signed-distance field.
- Remove sub-resolution components only through documented rules.
- Reapply allowed, forbidden, fixed, and root projections.
- Validate the selected topology policy, nominal/eroded connectivity where
  applicable, volume change, surface/Hausdorff error, and feature survival.

### S1. Body-Fitted-First Refinement

- Use density-to-SDF output to create a body-fitted mesh epoch.
- Re-evaluate the declared primal responses and, where useful, use the existing
  body-fitted shape-adjoint adapter for local refinement.
- Treat this as the first usable sharp-wall path while the dedicated fixed-grid
  sharp-interface backend remains a research decision.

### S1D. Sharp-Interface Backend Decision

- Compare ghost-node IBM, implicit cut-cell, and the body-fitted-first path on
  accuracy, adjoint convergence, geometry robustness, and implementation cost.
- Select at most one fixed-grid sharp-interface backend after this comparison.

### S2. Hamilton-Jacobi Shape Refinement

- Filter the augmented shape derivative.
- Add curvature regularization.
- Update SDF by normal velocity.
- Reinitialize the SDF and reapply hard masks.
- Use mesh epochs instead of remeshing every inner iteration.

## 8. Stage V Plan

The current OpenFOAM pipeline is retained here.

- Generate body-fitted mesh from the Stage S SDF/STL.
- Run mesh-quality checks.
- Run RANS with boundary-layer resolution and boundary conditions appropriate
  to the declared target profile.
- Compare pressure, skin friction, force, moment, and every declared response
  with Stage T/S values.
- Demonstrate grid convergence on at least three grids before treating a final
  response as a benchmark value.
- Treat the current body-fitted adjoint loop as a shape-adjoint comparison
  tool, not the primary topology optimizer.

## 9. Distribution Plan

- Windows-native orchestrator and future GUI.
- Docker or WSL2 solver profiles selected by one command.
- Solver runtime remains external to the application binary.
- CPU public profile first.
- GPU geometry/AMReX profile only after G2--G4 and Stage T are numerically
  validated.
- Pin Python dependencies and solver images, retain source for custom solver
  extensions, and add real-solver CI before claiming reproducibility.

## 10. Immediate Next Execution

T0a, T1 v1, and T2 capability work are complete. T3 canonical extraction and
cellwise checks are complete for the current drag/downforce profile. They do
not yet qualify target-physics front-wing optimization.

G0 core scope/evidence classification and the G1 contract layer are complete.
The next implementation cycle is G2--G4, then production T5:

1. **Implement G2**: compile the declared operating point, reference values,
   turbulence model, and boundary conditions into fixed-grid OpenFOAM cases;
   add manifest and convergence gates. **Implementation required.**
2. **Implement G3**: input preflight plus mandatory physical-resolution and
   density-to-SDF fidelity gates. A 10 mm feature must not be claimed on the
   current coarse grid. **Implementation required.**
3. **Implement G4 B0--B2**: geometry, connectivity, and low-cost topology
   benchmarks with three-grid and filtered-random gradient evidence.
   **Implementation required.**
4. **Complete v2 writer integration and T3/T4 for production**: emit the G1
   artifact schema from real solver runs, add generic-response derivatives,
   target-physics validation, and analytic/adjoint connectivity derivatives.
   **Implementation required.**
5. **Implement the production T5 driver**: nonlinear primal re-evaluation,
   acceptance/rollback, checkpoint/resume, and then a GCMMA or equivalent
   backend behind the same interface. **Implementation required.**
6. **Advance through B3--B5/T6** only after the above gates pass; the front
   wing remains the final complex integration benchmark.

No new parametric candidate generation is part of this cycle.
