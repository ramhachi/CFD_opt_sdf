# Authoritative Roadmap: Generic Aerodynamic Topology Optimization

Date: 2026-07-14
Status: authoritative
Scope: generic rigid-object external aerodynamics with topology change

This is the only implementation roadmap for the project. Historical
body-fitted, parametric, and front-wing-specific work is capability evidence,
not a second development plan. The front wing remains the final complex
benchmark; it does not define the product architecture.

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
- a localized uniform-Cartesian canonical design grid with explicit transfer
  to the outer CFD grid;
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
Localized canonical topology design state + explicit CFD transfer
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
| G0 scope/evidence model | Complete | Generic rigid-object scope and evidence classes are established. `AGENTS.md` requires a bounded `sol_<topic>` sub-agent review before any decision that materially affects physical correctness, numerical validation, OpenFOAM semantics, artifact provenance, public contracts, or the roadmap. |
| G1 ProblemSpec/artifact contract | Complete | v2 parsing, canonical hash, multipoint responses, topology policy, v1 read-only migration, and semantic readers exist. |
| G2 case compiler | Numerical runtime qualification, canonical transfer, and both-flow FD direction checks passed; target-physics bridge remains | The front-wing-role/domain ProblemSpec hash `54619a571b08a447e484856fa8e9c0d4c66d2fae2a89e58ab9660e4522a0d08a` passed the named-adjoint, absolute-linear-tolerance two-flow Docker OpenFOAM v2512 qualification. Straight: primal `7.28932450665e-09`, adjoint max `6.98776718537e-10`, normalized mass `3.4188037016180413e-11`; yawed: primal `7.99508862341e-09`, adjoint max `9.79649119374e-10`, normalized mass `2.61841637267506e-11`. The generated, ignored evidence bundle is `examples/g2_openfoam_compile/runs/g2_front_wing_roles_named_adjoint_absolute_requalification_20260714/`. Canonical gradient transfer passed with full coverage for both flows. Straight FD passed in N at ε=`0.005`: `28.1184973209` versus `28.8034576418` (2.378%), and ε=`0.01`: `28.0971302028` versus the same adjoint (2.452%). Yawed FD also passed: ε=`0.005` had 11.04% relative error and ε=`0.01` had 7.72%; both have the same sign as the adjoint. The declared tolerance remains 25%. Native v2 response/provenance/topology bindings and porous/body-fitted comparisons remain unqualified. |
| G3 geometry/resolution gates | In progress — localized reference state is built; its first topology evaluation is rejected | The existing front-wing STL assets are declared as G2 semantic roles. The 0.02 m, 1,170,000-cell canonical mask build and its hash-bound manifest verification passed: active 82,160 cells, forbidden 39,060, fixed 46,388, and root 576; this is G2 CFD-transfer-grid evidence, not physical topology-resolution evidence. The selected physical-policy path is a 2 mm localized canonical design grid over `allowed_front_box` (87,543,750 cells). Its generated, ignored geometry snapshot passed independent verification: active 85,967,750, fixed 1,576,000, root 729,000, forbidden 0. The hash-bound localized reference state is published at `examples/g2_openfoam_compile/runs/localized_reference_state_surface_v2_20260730_3b5ef30/`. Its first topology report is rejected: the evaluator incorrectly included non-root fixed `vehicle_nose` geometry in the design connectivity solid, and independently found minimum-solid-width and minimum-gap failures. The rejected evidence is retained while the role-aware evaluator is corrected; no localized finite-difference check may run until re-evaluation passes. Native v2 therefore remains unqualified. |
| G4 benchmark ladder | Missing — implementation required | No complete three-family, three-grid generic acceptance set exists. |
| Stage T canonical backend | Capability complete | Fixed-grid Brinkman primal, canonical volume sensitivities, reference connectivity derivatives, and linearized constrained steps exist. |
| Stage T production optimizer | Missing — implementation required | Fail-closed native v2 writer/readiness diagnostics exist. The real G2 two-flow FD checks qualify the current transferred force-sensitivity chains, but native v2 remains blocked on explicit response-unit/provenance, `rho`-gradient convention, mesh-grid mapping, and topology-value bindings from the new localized canonical design state. Generic-response gradients, production connectivity derivatives, nonlinear acceptance/rollback, checkpoint/resume, and GCMMA-equivalent iteration remain. |
| Stage S | Handoff prototype only | Density-to-STL/SDF conversion exists; quantitative fidelity and a qualified sharp-interface solver do not. |
| Stage V | Prototype | Body-fitted OpenFOAM execution exists; target-profile grid convergence and cross-fidelity acceptance remain. |

### Current front-wing blocker

The localized 2 mm front-wing state has no qualified feasible initializer under
the unchanged policy. The raw repair reached a fixed point; the subsequent
filter-support repair correctly rejected a 7,130-cell solid/void support
conflict. Therefore localized front-wing native-v2, FD, and optimizer work is
stopped until a separately approved initializer produces a full-checker-success
derived state, provenance/difference evidence, and a fresh alpha binding. This
does not block generic topology infrastructure or a separately qualified simple
benchmark. See
[`2026-07-30-localized-feasible-derived-starting-state.md`](decisions/2026-07-30-localized-feasible-derived-starting-state.md).

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

Status: numerical runtime qualification passed for the current front-wing-role/
domain contract; canonical transfer and two-flow FD direction validation
passed; native artifact binding and target-physics qualification remain
incomplete.

The existing front-wing STL files are the canonical geometry source for the G2
benchmark. G2 declares their semantic roles directly; it does not create a
second, copied-and-renamed geometry set. This keeps the benchmark an explicit
consumer of the generic STL-role contract while preserving a single source of
truth for the assets.

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
  primitives; domain-bound transfer of both qualified G2 flow fields passed
  with full coverage of all 1,170,000 canonical indices.
- direct declaration of the existing front-wing STL assets as G2 semantic
  roles, with a passed 0.02 m, 1,170,000-cell canonical geometry-mask build
  and hash-bound manifest verification: 82,160 active, 39,060 forbidden,
  46,388 fixed, and 576 root cells.
- Docker OpenFOAM v2512 numerical runtime qualification for the front-wing-role/
  domain ProblemSpec hash
  `54619a571b08a447e484856fa8e9c0d4c66d2fae2a89e58ab9660e4522a0d08a`, using
  native v2512 adjoint sources with named-adjoint absolute linear tolerances.
  The generated, ignored evidence bundle is
  `examples/g2_openfoam_compile/runs/g2_front_wing_roles_named_adjoint_absolute_requalification_20260714/`.
  Straight flow measured primal `7.28932450665e-09`, adjoint max
  `6.98776718537e-10`, and normalized mass `3.4188037016180413e-11`; yawed
  flow measured primal `7.99508862341e-09`, adjoint max
  `9.79649119374e-10`, and normalized mass `2.61841637267506e-11`.
- canonical gradient transfer from both qualified flow fields, with full
  coverage of all 1,170,000 canonical indices.
- real finite-difference direction validation of the transferred `topOSens` to
  `rho` chain in N for both configured flows. Straight flow: at ε=`0.005`, FD
  was `28.1184973209` versus adjoint `28.8034576418` (2.378%); at ε=`0.01`,
  FD was `28.0971302028` versus the same adjoint (2.452%). Yawed flow: at
  ε=`0.005`, the relative error was 11.04%; at ε=`0.01`, it was 7.72%. Both
  yawed checks have the same sign as the adjoint. All four checks pass the
  unchanged declared 25% tolerance.

Current supported response compilation is force-only. Moment, pressure loss,
flow rate, rotating-wall motion, and plugin responses must be rejected
explicitly until implemented.

Remaining implementation:

1. Implement the localized 2 mm canonical topology design-state and explicit
   CFD sensitivity-transfer contracts selected in
   [`localized_design_grid_decision.md`](localized_design_grid_decision.md).
   The current 20 mm G2 transfer grid cannot supply topology-policy values.
   **Implementation required.**
   The direct-STL localized state is now published and its role-aware topology
   evaluation correctly rejects real minimum-width/gap violations. Implement
   the separate forward-only feasible derived starting-state initializer
   selected in
   [`2026-07-30-localized-feasible-derived-starting-state.md`](decisions/2026-07-30-localized-feasible-derived-starting-state.md), then require a
   new successful full-resolution topology report and alpha binding before
   localized FD can begin. **Implementation required.**
2. Supply and qualify semantic bindings for native v2 primal and sensitivity
   artifacts from the real runs, including response unit/provenance,
   `rho`-gradient convention, mesh-grid mapping, and topology-policy values
   from the localized canonical state. For localized raw-alpha FD, this now
   requires a version-pinned OpenCFD v2512 solver/adjoint patch which emits a
   response-specific total derivative after the complete
   `alpha -> alphaTilda -> beta -> response` chain. Existing direct
   `dJ/dbeta`, `topOSens`, and `topologySens` fields remain audit-only and
   must not be relabelled by metadata. The artifact must remain refused until
   the pinned source, patch/build provenance, alpha/grid/order binding, and
   filter/projection-enabled directional-FD evidence exist. See
   [`2026-07-30-localized-g2-native-raw-alpha-gradient-path.md`](decisions/2026-07-30-localized-g2-native-raw-alpha-gradient-path.md).
   **Implementation required.**
3. Qualify wall-distance/turbulence treatment; current `meshWave` metadata is
   not porous-aware and remains unqualified.
4. Compare porous and body-fitted pressure force, skin friction, total force,
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

Status: the G2 fixture geometry masks and their manifest are verified. The
localized 2 mm canonical design-grid path has a verified geometry-mask
snapshot and tested state/alpha-reference artifact contracts; physical-state,
OpenFOAM transfer, and density-to-SDF gates remain unqualified.

The existing front-wing STL source is declared directly in the G2 role
configuration. Its full 0.02 m canonical-grid mask build contains 1,170,000
cells and passed manifest verification with 82,160 active, 39,060 forbidden,
46,388 fixed, and 576 root cells. The current G2 front-wing-role/domain
ProblemSpec has passed native-v2512 named-adjoint absolute-tolerance runtime
qualification and canonical gradient transfer for both flows, with full
coverage of all 1,170,000 canonical indices. Real finite-difference direction
checks passed for straight and yawed flow. This 20 mm grid is retained as the
G2 outer CFD-transfer grid; it is not physically fine enough for the declared
10 mm solid-width, 12 mm void-width, 8 mm gap, and 4 mm erosion policy.

The selected G3 path is the localized 2 mm uniform canonical design grid over
the `allowed_front_box` (`575 x 725 x 210 = 87,543,750` cells), described in
[`localized_design_grid_decision.md`](localized_design_grid_decision.md). The
outer 20 mm OpenFOAM grid remains separate. Native v2 is not ready until the
localized topology design state and explicit transfer are implemented and
qualified.

The first real localized geometry snapshot is generated output, deliberately
ignored by Git, at
`examples/g2_openfoam_compile/runs/local_design_geometry_snapshot_v3_20260730/`.
It independently verifies under schema v3 with snapshot identifier
`381423ea5d095017756beff729bdc1dea2da38afe730b1d9c11e539cfaf37f64`,
ProblemSpec SHA-256
`0fb37503b272080a3b773649023370b8283087a410cc297b64bdbc233500fb43`, and
localized-grid SHA-256
`3c612b5e77804f2a36bb07e4cbb73ed453f84ee5c5d655d83e5a0cd3afceba01`.
The 87,543,750 cells contain 85,967,750 active, 1,576,000 fixed, 729,000
root, and zero forbidden cells. Zero forbidden cells is geometrically correct:
the `tire_clearance` volumes begin at `y = +/-0.740 m`, while
`allowed_front_box` ends at `y = +/-0.725 m`, leaving about 15 mm separation.
The global 20 mm forbidden region is consequently outside this localized
design domain. This is contract/geometry evidence only, not a topology result.

The localized alpha-reference contract is implemented and focused-tested. It
permits only the one-way, unclipped relation
`alpha = alpha_reference + E @ (rho_projected - rho_projected_reference)` and
hash-binds the two reference artifacts. A strict `0.orig/alpha` codec and a
fresh-case stager now write and reread a grid-bound alpha only after its value,
current-state, reference-binding, canonical `x-fastest` order, and parsed
`blockMeshDict` grid hashes agree. This is unit-level prepared/not-run
evidence, not a full localized reference-state write to a compiled G2 case and
not a localized finite-difference direction check; native v2 stays fail-closed
until those qualifications are complete.

The Sol-reviewed initializer is also fixed: `front_wing_initial.stl` is the
only geometric source for `rho_raw`. Each active local cell uses the union of
the ten watertight STL components at the deterministic `2 x 2 x 2` subcell
offsets `{0.25, 0.75}^3`; inactive cells remain exactly zero. The raw-density
memmap writer, its source/grid/mask-hash manifest, and small-grid rejection
tests are implemented. Filter/projection, the full 87,543,750-cell reference
artifact, and its topology validation are still implementation/qualification
work.

The next state transform is now specified and implemented in small-grid tests:
an active-mask-normalized 4 mm Euclidean cone filter followed by a tanh
Heaviside projection (`beta=2`, `eta=0.5`). Its exact transpose and projection
derivative are implemented for the future sensitivity chain. Schema-v2 state
manifests bind canonical filter/projection JSON bytes; v1 remains readable but
cannot provide a full-resolution alpha-reference state. The 0.5 topology-solid
threshold is intentionally separate from the projection center.

Implement:

- unit and coordinate-frame validation;
- watertightness, orientation, self-intersection, and degenerate-face checks;
- fail-closed voxelization for critical roles;
- cells-per-feature checks for minimum solid width, void width, and gap, with
  at least three cells per declared feature;
- rejection when erosion/dilation radius has fewer than two represented cells;
- explicit, hash-bound CFD density/sensitivity transfer between the localized
  design grid and outer CFD grid, with no inverse reconstruction of fine
  topology state from coarse solver `alpha`;
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
3. B2 laminar 2D/2.5D: B2.0 channel then cylinder with three grids; B2.1
   NACA follows the B2.0 gates. See
   [`2026-08-04-g4-b2-laminar-scope.md`](decisions/2026-08-04-g4-b2-laminar-scope.md).
   B2.0 **channel-only gate passed**. The immutable v2 OpenFOAM v2512 runtime
   was re-qualified by v4 source-bound evidence: three-grid analytic
   profile/bulk/pressure-gradient, runtime health, final field/mesh bindings,
   and independent v2512 `postProcess` `U` component/cell-centre checks
   passed. The next implementation is the B2.0 cylinder porous/body-fitted
   cross-fidelity comparison on three grids. This does not qualify cylinder,
   NACA, arbitrary external bodies, turbulent flow, adjoints, or the
   optimizer. The superseded v2/v3 provenance artifacts remain retained and
   must not be cited as a pass. This work is governed by
   [`2026-08-04-g4-b2-channel-evidence-extraction.md`](decisions/2026-08-04-g4-b2-channel-evidence-extraction.md).
   Only the two compact v4 JSON evidence records are tracked; the raw
   OpenFOAM bundle is generated, ignored local evidence, so a repository clone
   alone cannot rerun or independently reproduce this solver result. A future
   external archive must be a complete raw bundle with manifest and checksums
   published as an immutable release asset.
   Execution completion alone is not B2.0 qualification.
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

1. Implement the localized canonical topology design state, its G3
   representability preflight, and explicit CFD density/sensitivity transfer.
2. Qualify real-run semantic bindings for the implemented fail-closed native
   v2 primal/sensitivity writer using that state.
3. Generic response/objective/aggregate derivative assembly.
4. Production analytic/adjoint nominal and eroded connectivity derivatives.
5. Filter/projection continuation with explicit chain-rule metadata.
6. Nonlinear iteration with primal re-evaluation, acceptance/rollback, move
   bounds, checkpoints, resume, and deterministic artifacts.
7. GCMMA or equivalent constrained backend behind the existing optimizer
   interface.
8. Mesh epochs and conservative state/gradient transfer only after the
   localized canonical fixed-grid profile is qualified.

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

1. Implement the selected localized 2 mm canonical design-grid/state,
   representability preflight, and explicit CFD density/sensitivity transfer.
   Do not change the declared physical policy or reconstruct fine state from
   coarse solver `alpha`. **Implementation required.**
2. Bind response units/provenance, gradient convention, mesh-grid mapping, and
   topology-policy values from that state for native v2 artifacts; write the
   artifacts and run the readiness gate. **Implementation required.**
3. Qualify simple porous versus body-fitted cases. **Implementation required.**
4. Implement the remaining G3 density-to-SDF gates. **Implementation
   required.**
5. Execute G4 B0–B2 before production optimizer work. **Implementation
   required.**
6. Implement production Stage T derivatives and nonlinear optimizer.
   **Implementation required.**
7. Advance through B3–B5, then Stage S and Stage V.

No new parametric candidate generator belongs to this execution sequence.

## 12. Document authority

- `docs/phase_plan.md`: only roadmap and status source.
- `docs/problem_contract_v2.md`: authoritative user problem schema.
- `docs/fixed_grid_data_contract_v2.md`: authoritative Stage T artifact schema.
- `docs/fixed_grid_backend_decision.md`: selected-backend decision record.
- `docs/localized_design_grid_decision.md`: selected physical-resolution
  design-grid decision record.
- `docs/git_branching_strategy.md`: repository workflow.

If another document conflicts with this roadmap, this file wins and the
conflicting document must be corrected or removed.
