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
| Stage T production optimizer | Bounded 97-step candidate reached; not converged and not qualified | The early PQ3.1–PQ3.3 history is retained in the register: solver-field discreteness without extraction coherence, and an upper volume bound that did not fill the material budget. The later v12–v16 line runs the b=128 margin-mask level with the Phase 2 discreteness gate: v15 accepted 10/10 at its budget and v16 accepted 87 further steps (cumulative 97), reaching raw downforce `2.65056`, projected volume `0.0719735` (94.30% of Vmax) and `mean_nd=0.0025089`, then stopped fail-closed at attempt 88 when the alpha-1.0 Path B bracket was not a descent direction. The registered convergence window was not met and no independent terminal repeat ran, so this is not a converged terminal. Projected-gradient and volume-target OC remain proposal rules; MMA/GCMMA is deferred. |
| Stage S | Superseded reference (SDF-native fork, 2026-09-26): entry gate passes on the v16 candidate, the Work F adjoint derivative qualification failed, and the K=16 reduced-basis FD v2 contract registered with a solver-free S0R/S1R pass; S2 is intentionally not started | PQ4.1 v2 on the v16 checkpoint 87 selects `rho_projection` iso 0.5 and returns `ready_for_stage_s=true` with the topology-aware self-intersection detector and the surface-nets extraction (`evidence/pq4_1_v16_state_stage_s_entry_v2_2026_09.json`). Baseline v2 is registered (`evidence/stage_s_baseline_v16_v2_2026_09.json`), and the Work F V1 body-fitted baseline passed the registered mesh and primal `stage_v_qualification_v1` gates (`evidence/stage_s_work_f_v1_solver_2026_09.json`), which closes P17 for this candidate and level only. The Work F centered-FD campaign then ran all 32 perturbation primals: the gradient-aligned directional derivatives pass within the 5% profile (downforce response `1.0408`/`1.0279`; drag response `1.0266`/`0.9595`) with tight epsilon plateaus, but the registered random-seed directions exceed the relative rule (downforce: `1.0858`/`0.8796`; drag: `1.0376` passes, `1.4593` fails), so the complete derivative qualification is **false** and one accepted body-fitted update remains unauthorized (`evidence/stage_s_work_f_surface_fd_result_2026_09.json`; `shape_update_allowed=false`). The fail branch diagnosis D0-D3 has run: D1 (realized directions) and D2 (sensitivity semantics) passed, and the D3 bounded `linearUpwind` diagnostic was mixed with `supports_discretization_cause=false`. The post-D3 plan ([`stage_s_work_f_post_d3_plan_2026_09_25.md`](stage_s_work_f_post_d3_plan_2026_09_25.md)) is registered through its D4.0 manifest ([`evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json`](evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json), SHA-256 `21dd18d6084258b4dc1f5cf02bc9d91049fb6e8f8aef82ae438bf0cd484a8e52`) and the solver-free D4.1 component audit ([`evidence/stage_s_work_f_derivative_component_audit_2026_09.json`](evidence/stage_s_work_f_derivative_component_audit_2026_09.json), SHA-256 `2cd3f9f102fe49ff80b5d8499416ff61450d245a2c16468850693d8c5b32476c`): component closure is exact and no single term drop or common scale explains the residual. The D4.2 B-spline geometry-Jacobian audit then **passes** ([`evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json`](evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json), SHA-256 `5e3619a8686a96f325f877555b67546e1518977ef4a8f85fccd421fe176b0954`; as-run all-epsilon application preserved at [`evidence/stage_s_work_f_geometry_jacobian_audit_all_epsilon_2026_09.json`](evidence/stage_s_work_f_geometry_jacobian_audit_all_epsilon_2026_09.json), SHA-256 `e184b18aac1f5ec43df086f73dc885feb8494be759c03ac6d3a25569aa15ee72`): the read-only analytic `dxdbFace`/`dSdb`/`dndb` contraction matches the centered differences of the registered moved meshes with L2 ratios `1 +/- 2e-5`, cosines `~1`, an epsilon plateau, zero derivative on every non-design patch, and a per-face residual that scales exactly as `1/epsilon` at the ASCII write precision (`max_error * 2*epsilon` constant at `~1.1e-8`/`~7e-10`/`~1.3e-6` for `Cf`/`Sf`/`n`). The geometry chain rule is therefore not the cause, so the D4.3 adjoint-option ablations were run ([`evidence/stage_s_work_f_adjoint_option_diagnostic_surface_area_2026_09.json`](evidence/stage_s_work_f_adjoint_option_diagnostic_surface_area_2026_09.json), SHA-256 `110ff2a6ae0a82d48da2a8e37ba88ea2d2832d790731d893a1325e6bd49cc14f`; [`evidence/stage_s_work_f_adjoint_option_diagnostic_mesh_movement_2026_09.json`](evidence/stage_s_work_f_adjoint_option_diagnostic_mesh_movement_2026_09.json), SHA-256 `53ba943d03123361561aea96a674f1c7cedd9120b3021b1b57bfffa2e9c7a427`): `includeSurfaceArea false` leaves the design-variable derivative files bit-identical (the option only changes the `faceSensNormal*` output), and `includeMeshMovement false` changes the derivatives but breaks passing controls (drag `random_seed_2026` ratio `1.4592 -> 3.8317`, drag `random_seed_11` `1.0376 -> 1.2299`). No single option satisfies the pre-registered sole-cause rule, so per the post-D3 plan's D4.4 table the OpenFOAM continuous-adjoint route is **fail-closed and unqualified for this Work F profile**: no D5 holdout and no D6/D7 requalification ran, and `derivative_qualified=false` with `shape_update_allowed=false` stand pending an architecture decision. The post-D4.4 plan's §21 then ran the A0 registration ([`evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json`](evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json), SHA-256 `e78d2fb8f40044910b9a80e672c5b0111c22a4741f7f319327a8a52c5ca357ce`) and the bounded A1 native-FI discriminant ([`evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json`](evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json), SHA-256 `de814a57de1a55f8cc1e4cee7039874d80af0f58e24d76692cd76bf914f0ed92`): `sensitivityType surface -> shapeFI` converges with identical primal lineage and derivative schema, but it does not satisfy the registered conditions either (pass controls worsen: downforce gradient-aligned `1.0409 -> 1.1333`, drag downforce-gradient-aligned `1.0266 -> 1.0861`; failing rows remain: downforce seed2026 `0.9094`, drag seed2026 `1.5798`), so `candidate_formulation_supported=false`. Per §21.5/§21.6 the formulation branch is stopped and the 0-run architecture memo ([`stage_s_work_f_architecture_decision_2026_09_25.md`](stage_s_work_f_architecture_decision_2026_09_25.md)) registers exactly two options for a new contract: an alternative sensitivity path, or a reduced-parameterization centered-FD path. Option 2 was then selected: the solver-free S0 contract ([`evidence/stage_s_reduced_basis_fd_manifest_2026_09.json`](evidence/stage_s_reduced_basis_fd_manifest_2026_09.json), SHA-256 `261a20f1ad97c0feddc9641765d8ad3171dfd68d4051317a1b1f69b80e24a0d1`) fixes the versioned reduced-basis ProblemSpec (`maximize downforce / J = -downforce`, drag report-only, no constraints) and the K=16 mode-space design map over the registered `volumetricBSplines` morpher, and the S1 geometry-only preflight ([`evidence/stage_s_reduced_basis_mode_preflight_2026_09.json`](evidence/stage_s_reduced_basis_mode_preflight_2026_09.json), SHA-256 `1942993fbaf306f14932361ec85c71e48230aee8270af10b936c7d92ee1226f9`) selects 16 frequency-ordered y-symmetry-preserving modes (frequencies 3--11) with all plus/minus max-epsilon geometry/mesh/realized-motion gates passing; two invalid preflight attempts were preserved and corrected. No flow solver has run: `original_adjoint_derivative_qualified=false`, `reduced_basis_fd_qualified=pending`, `shape_update_allowed=false`. The old-candidate PQ2 Stage V domain/boundary factor and continuation returned No-Go, and the v16-specific domain-only ladder and mixed far-field treatment also remained outside the registered bounds. That path was superseded by the v2 moving-ground/freestream physical profile, which passed every registered gate on the `[-2.5,-1.2,-0.9] -> [2.5,1.2,0.9]` m domain and then passed the same-profile `+3.5 m` outlet domain-convergence pair (`|Δdownforce|=0.0008034 <= 0.005`, relative Cd `0.0008242 <= 0.02`; [`evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json), SHA-256 `13374c722b4993f941ca6487a305fe2f371551d2eed152f744ef016f5b18b5bf`). The frozen profile is rebound to the exact historical K=16 modes in the reduced-basis FD v2 contract ([`evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json), SHA-256 `b96df520e6a359c206b9ded3c4cb1872220344ba9a46c7a7492d0e1ba47860dd`), and the solver-free S0R/S1R requalification ([`evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json), SHA-256 `3f6cb15eae5b7770640466c89f9c296a383dd152f9f1dc0fedbc95d69acdaf50`) passes 16/16 modes with `flow_campaign_allowed=true`. `reduced_basis_fd_qualified` stays `pending` until S2-S4 pass; `shape_update_allowed=false`. |
| Stage V | v16 physical profile qualified; same-profile two-domain convergence passes; no grid-independent reference | The PQ2 old-candidate factor and continuation line is retained as No-Go only for that candidate (`613637…`) and is superseded for the v16 candidate (`5e6d…`). The v2 moving-ground/freestream physical profile passed all registered gates on the 42,619-cell `[-2.5,-1.2,-0.9] -> [2.5,1.2,0.9]` m domain, and the same-profile daughter with outlet at `+3.5 m` passed the convergence pair (`|Δdownforce|=0.0008034 <= 0.005`, relative Cd `0.0008242 <= 0.02`; [`evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json)). v2 is the frozen Stage S working domain and v3 is the domain-convergence witness. This is not an absolute, grid-independent, high-Re, or full-vehicle downforce qualification, and the raw `checkMesh` concave-cell marker remains visible under the allowed profile. |


### PQ2 domain and boundary factor result (2026-09-25)

The registered V2 factor campaign ran both treatments against the qualified fixed-domain V2 baseline. The run manifest was registered before computation and is unchanged (SHA-256 c492c2016014fb3b360ddd4b0ebd7db4f140d0226ca229e9c73fe11c4f6a957b). Both treatments passed the registered mesh, residual, and force-stationarity qualification profile, so the comparison is a qualified treatment result at V2, not a failed-solver artifact.

The fixed-domain baseline is 187,942 cells with Cd 1.6800880804 and downforce 0.5092669766. The far-field extension uses the declared extended box and has 214,900 cells, Cd 1.1671678778, and downforce 0.2146501052. The top pressure-outlet treatment retains 187,942 cells and has Cd 1.1247330053 and downforce 0.0307615051. The corresponding downforce changes are -0.2946168715 and -0.4785054715; both exceed the registered absolute bound 0.005. The relative Cd changes are -0.3052936382 and -0.3305511667; both exceed the registered 0.02 bound.

The immutable judgment is No-Go for the current Stage S bridge: both factors move the measured response, so the fixed-domain V2 result cannot be used as a stable downforce reference for S2. The evidence supports factor sensitivity at this candidate and V2 level. It does not support a grid-independent downforce value, a Stage V reference qualification, or a full-vehicle/high-Re claim. The next work must register a factor-resolved Stage V contract, explain the large boundary/domain response, and rerun only the minimum required family before any reduced-basis flow campaign.


### PQ2 domain continuation result (2026-09-25)

The first result-driven continuation kept the registered candidate, V2 voxel size, laminar operating point, symmetry side/top boundaries, ground wall, inlet/outlet treatment, and qualification profile unchanged. It extended the inlet, outlet, sideMin, sideMax, and top faces by 1.6 m from the original fixed box. The treatment qualified with 279,993 cells, Cd 1.0254060542, and downforce 0.1741694770.

The adjacent +0.8 m treatment was qualified at Cd 1.1671678778 and downforce 0.2146501052. The +1.6 m transition therefore changes downforce by -0.0404806281 and Cd by -12.1458%, both outside the registered bounds (0.005 absolute downforce and 0.02 relative Cd). The continuation is a numerical No-Go, not a solver failure. Register the next domain continuation or a physically justified far-field boundary contract before S2; do not treat the present value as grid-independent.

The 2026-09-10 effectiveness spike proves only local numerical control inside
the fixed-grid Brinkman model. It does not prove constrained optimization or
the Stage T -> Stage S -> Stage V architecture end to end. The canonical start
is infeasible for the recorded efficiency and active-cell mean-`rho` limits,
and the current T5 output cannot be passed as the same candidate to Stage S/V.

### v16 lineage correction and immediate execution order (2026-09-25)

The registered Stage S v16 candidate and the registered PQ2 continuation candidate
are different objects. The v16 surface is SHA-256
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`; the PQ2
continuation surface is `613637cf0fac8bce8a124a479eb3f18417c06995bdbfbe1c99b792fe1db3686e`.
The PQ2 factor and +1.6 m continuation therefore remain candidate-specific
diagnostic evidence and are not a Stage S v16 absolute-reference judgment.

The authoritative next slice is the solver-free, immutable v16 contract audit
described in [`stage_s_v16_contract_and_execution_plan_2026_09_25.md`](stage_s_v16_contract_and_execution_plan_2026_09_25.md)
and registered at
[`evidence/stage_s_v16_contract_audit_manifest_2026_09.json`](evidence/stage_s_v16_contract_audit_manifest_2026_09.json).
It binds the v16 STL, Work F V1 case, reduced-basis ProblemSpec, six-patch
realized boundary/field contract, domain/mesh inputs, and raw checkMesh semantics;
it starts no solver. A v16-specific factor-resolved Stage V domain/boundary
contract must be registered after this audit. Until that contract passes, keep
`reduced_basis_fd_qualified=pending`, `shape_update_allowed=false`, and do not
start S2, a full optimization campaign, or a shape update. The local reduced-basis
FD path and the absolute Stage V reference path are separate: the former can only
be considered as local Work F evidence, while the latter requires a same-candidate
domain/grid/boundary family. No PQ2 result may be transferred across the candidate
hash mismatch.

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

Current status on 2026-09-23 (historical snapshot; the dated addenda under
items 5--6 carry the later v12--v16, baseline v2 and Work F records):

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

   **V12 discreteness-preserving replay (2026-09-23):** the missing acceptance
   invariant is now implemented and registered in
   [`evidence/pq3_3b_campaign_manifest_v12_2026_09.json`](evidence/pq3_3b_campaign_manifest_v12_2026_09.json).
   It measures `mean(4*rho_projection*(1-rho_projection))` on the active
   transform cells and requires `<= 0.01` before Path B or a trial primal is
   run. The replay begins at v10 checkpoint 5, the last accepted b=128 state
   inside the bound (`mean_nd 0.0085623`), rather than the infeasible v11
   terminal. The bounded entry preflight passed
   ([`evidence/pq3_3b_v12_entry_preflight_2026_09.json`](evidence/pq3_3b_v12_entry_preflight_2026_09.json)):
   alpha 1.0/0.5/0.25 were rejected without solver calls at mean_nd
   0.03123/0.01589/0.01128, while alpha 0.125 passed every existing gate at
   mean_nd 0.00973685, projected volume 0.0684123 and fresh downforce
   2.32152697653. This establishes entry feasibility only. Execute the
   registered v12 campaign without relaxing the bound; then rerun the full
   PQ4.1 threshold sweep on its independent terminal candidate. Stage S may
   start only if that new composite gate returns `ready_for_stage_s=true`.

   **V12 result and v13 direction discriminant (2026-09-23):** v12 accepted
   one new sign step (`DF 2.27551379853 -> 2.32152697653`) while preserving
   `mean_nd=0.00973685`, then stopped fail-closed because every registered
   sign-step alpha exceeded 0.01
   ([`evidence/pq3_3b_campaign_v12_outcome_2026_09.json`](evidence/pq3_3b_campaign_v12_outcome_2026_09.json)).
   This is neither convergence nor proof that all feasible directions are
   exhausted. A bounded v13 discriminant instead projects the raw objective
   gradient onto the linearized active discreteness tangent in design space.
   Its solver-free audit selected alpha 1.0 at `mean_nd=0.00975157` and
   projected volume 0.0689811; the registered one-step OpenFOAM preflight then
   passed Path B (`d_adj=-13.4884`, `d_fd=-13.4887`) and improved downforce to
   2.45647595951
   ([`evidence/pq3_3b_v13_entry_preflight_2026_09.json`](evidence/pq3_3b_v13_entry_preflight_2026_09.json)).
   The next step is a short immutable learning campaign using this direction,
   capped at ten new accepted attempts. If projected volume reaches Vmax, a
   separate volume-tangent change must be registered; the discreteness bound
   must not be relaxed. A passing short campaign still requires a fresh PQ4.1
   composite gate before Stage S.

   **V14 result and v15 registration (2026-09-24):** the bounded v14 campaign
   accepted five further tangent steps and increased downforce from the v13
   entry state to `2.61268983854`, while the final accepted state remained
   inside the registered bounds (`mean_nd=0.00994531219`, projected volume
   `0.07052783246`). Attempt 6 passed the transform gates and the sign/noise
   Path B checks, but its full trial reduced downforce by `0.00029093771`;
   v14 therefore stopped fail-closed and did not establish convergence
   ([`evidence/pq3_3b_campaign_v14_outcome_2026_09.json`](evidence/pq3_3b_campaign_v14_outcome_2026_09.json)).
   PQ4.1 on the last accepted v14 checkpoint found that iso 0.5 passes the
   discreteness, extraction-profile and volume-fidelity sub-gates but still
   fails the registered 0.25 m clearance gate; iso 0.4 and 0.6 have additional
   extraction/fidelity failures
   ([`evidence/pq4_1_v14_state_stage_s_entry_2026_09.json`](evidence/pq4_1_v14_state_stage_s_entry_2026_09.json)).

   V15 is registered as a bounded learning experiment from a deterministic
   clearance-support trim of the v14 checkpoint. Because that trim changes the
   state materially, accepted counts and convergence metrics are reset rather
   than carried over. The unchanged hard gates are `mean_nd<=0.01`, projected
   `V<=Vmax`, the existing response thresholds and the PQ4.1 clearance profile.
   Each attempt may evaluate smaller transform-feasible alphas only after Path
   B passes and the full trial response fails; a Path B failure stops the
   attempt. The immutable budget is at most ten fresh attempts/accepted steps
   and at most 16 evaluator requests per attempt. The registered entry
   preflight subsequently passed at alpha 1.0: parent/trial downforce
   `2.00516803057 -> 2.01655864594`, Path B
   `d_adj=-1.67506090`, `d_fd=-1.65081812`, candidate
   `mean_nd=0.00348178008`, projected volume `0.06216404077`, and zero support
   violations
   ([`evidence/pq3_3b_v15_entry_preflight_2026_09.json`](evidence/pq3_3b_v15_entry_preflight_2026_09.json)).
   Because the first alpha passed, this run did not exercise physical
   response backtracking to a smaller alpha. At that point the bounded v15
   campaign had not started. Its first runner invocation reproduced the same
   successful alpha-1 physics evaluation but stopped before checkpointing due
   to an implementation error: the runner selected the last ledger row rather
   than the row marked `accepted`. The failed output is hash-recorded in
   [`evidence/pq3_3b_v15_runner_lineage_failure_2026_09.json`](evidence/pq3_3b_v15_runner_lineage_failure_2026_09.json),
   archived, and is not counted as a campaign step. The runner now selects the
   sole accepted row explicitly; the clean campaign restart below was required.

   **V15 bounded learning result (2026-09-24):** the clean campaign restart ran
    under the immutable manifest (SHA-256
    `4a46c740dd4fd2f350326b82bab90a67c64e8bb2de1334bc3bb563b2d2e5ceda`) and
    stopped at `paused_learning_budget`: 10 fresh attempts, 10 accepted steps,
    all at alpha 1.0, so the alpha-below-1 physical response backtracking path
    was not exercised. The final accepted state has raw downforce
    `2.10035503533`, projected volume `0.06406567400358908` (83.94% of Vmax),
    active projected discreteness `0.003213044195919047` and zero support
    violations. The registered convergence window was not observed
    (`window_accepted=3`, `level_converged=false`); this is a bounded budget
    stop, not terminal or converged; the campaign evidence alone does not
    establish Stage S readiness. The final rho
    array hash is `00efe715f32c46f8d55a7ace599936ce61613cdfcaa2b8ff35270db8dd711f31`
    and the outcome records verified checkpoint-chain and output hashes in
    [`evidence/pq3_3b_campaign_v15_outcome_2026_09.json`](evidence/pq3_3b_campaign_v15_outcome_2026_09.json)
    (verified against `work/pq3_3b_campaign_v15` and the manifest). No v16 is
    registered. PQ4.1 was then run on this checkpoint
    ([`evidence/pq4_1_v15_state_stage_s_entry_2026_09.json`](evidence/pq4_1_v15_state_stage_s_entry_2026_09.json)):
    the registered iso sweep (0.4/0.5/0.6) selects iso 0.5 and the complete
    composite `stage_s_entry_v1` gate returns **`ready_for_stage_s=true`** at
    `rho_projection` iso 0.5 (discreteness, extraction profile with a measured
    watertight manifold non-self-intersecting surface, volume fidelity, volume
    constraint, width/gap, lineage-hash and the `stage_v_clearance_v1`
    preflight all pass). Iso 0.4 fails feature shrink; iso 0.6 fails volume
    fidelity. This measured gate pass is at the paused v15 checkpoint, not a
    converged terminal candidate: it closes this diagnostic's open clearance
    blocker (P2's v14 failure mode) but proves neither sustained optimization
    behavior, a Stage S-qualified geometry after later states, nor grid-
    independence, and the P20 measurement scope (volume-calibration artifact
    shape label, strict minimum width) remains open. No Stage S baseline is
    registered by this record; registration remains a separate authorized
    decision.

   **Adopted execution order (2026-09-24, user-approved):** P20 remaining
   repairs → a v16 continuation registration and bounded campaign → a fresh
   PQ4.1 judgment on the v16 terminal with the repaired gate → Stage S baseline
   registration → Stage S Work F (surface FD, at most one shape step). The
   order is chosen because v15 stopped at its registered budget while still
   improving (last objective deltas `0.0125/0.0133/0.0154`, projected volume
   `0.0641` of `Vmax 0.0763`) and each Stage T attempt costs ~20 s on the
   8192-cell case, while Stage S Work F is hours-to-days of body-fitted solver
   work; the v15 PQ4.1 pass does not expire, so the Stage S baseline is bound
   to the final v16 terminal instead of the paused checkpoint.

   **P20 closure (2026-09-24):** the remaining Stage S entry measurement scope
   is implemented: calibrated `component_boundary_gap_m`, true-minimum width
   compared against the declared policy (`thickness_ridge_m_min`) with
   `ridge_width_p5_m` kept as a separate quantile, the append-only
   `evidence/pq4_volume_fidelity_calibration_correction_2026_09.json` shape
   label correction, and a false-positive/true-positive/cap audit of the
   self-intersection detector with a memory-safe AABB stage. The v15 PQ4.1
   artifact is a pre-repair record; the next PQ4.1 runs on the repaired gate.

   **Stage S baseline conditions (2026-09-24, adopted):** registration
   requires a `ready_for_stage_s=true` candidate judged by the repaired gate
   (Exit Gate E: selected threshold, source field, transform, candidate,
   surface and revoxelized-volume hashes bound in one handoff manifest, and the
   `beta_solver` vs `rho_projection` difference traceable by name and formula),
   the `stage_v_clearance_v1` preflight pass, and `V(rho_projection) <= Vmax`.
   Work F then qualifies the body-fitted baseline against
   `stage_v_qualification_v1` (mesh, explicit `residualControl`, force
   stationarity), fixes the response identity, and qualifies drag and
   downforce surface derivatives separately with centered FD under the
   registered `fd_gradient_v1` profile; only if both pass is one small shape
   step accepted and every geometry/mesh/solver gate re-run.

   **V16 registration and entry preflight (2026-09-24):** the continuation
   manifest
   [`evidence/pq3_3b_campaign_manifest_v16_2026_09.json`](evidence/pq3_3b_campaign_manifest_v16_2026_09.json)
   (SHA-256 `28e8f7b5fa7a0fc0d67143f7b2f2fa55a8c7ca3c6a7d0cc50c766afb64630751`)
   continues the same b=128 margin level from the v15 checkpoint 10 unchanged,
   carries over the cumulative accepted count (10) and the last three accepted
   metrics, enables the cap-stationarity exit (machine-scale /
   projected-volume rejection reasons) and the independent terminal repeat,
   and registers 90 attempts with at least 10 cumulative accepted steps. Its
   entry preflight
   ([`evidence/pq3_3b_v16_entry_preflight_2026_09.json`](evidence/pq3_3b_v16_entry_preflight_2026_09.json))
   passed: start state `mean_nd=0.0032130442`, projected volume
   `0.0640656740`, support violations 0; alpha 1.0 was accepted
   (`DF 2.10035503533 -> 2.11252824711`, Path B `d_adj=-1.29080394`,
   `d_fd=-1.41661536`, candidate `mean_nd=0.0031861835`, projected volume
   `0.0643333567`).

   **V16 campaign result (2026-09-24):** the registered 90-attempt
   continuation accepted 87 steps (cumulative accepted count 97) and stopped
   fail-closed at attempt 88 with `objective_rejected`: the alpha-1.0 Path B
   bracket failed as `not_a_descent_direction` (`d_adj=-0.04161669`,
   `d_fd=+0.01716448`), which stops the attempt by the registered policy. The
   final accepted state has raw downforce `2.65056396128`, projected volume
   `0.0719735014` (94.30% of Vmax), active projected discreteness
   `mean_nd=0.0025088808` and zero support violations; the last three
   objective deltas are `5.52e-4/1.53e-4/7.33e-4`, so the registered
   convergence window was not met and no independent terminal repeat ran
   ([`evidence/pq3_3b_campaign_v16_outcome_2026_09.json`](evidence/pq3_3b_campaign_v16_outcome_2026_09.json)).
   This is a bounded response/gradient stop, not convergence, stationarity or
   Stage S readiness by itself.

   **PQ4.1 on the v16 state with the repaired gate (2026-09-24):** the
   registered iso sweep (0.4/0.5/0.6) selects iso 0.5 and the composite
   `stage_s_entry_v1` gate returns **`ready_for_stage_s=true`**
   ([`evidence/pq4_1_v16_state_stage_s_entry_2026_09.json`](evidence/pq4_1_v16_state_stage_s_entry_2026_09.json)):
   discreteness `mean_nd=0.0025088807`, extraction profile (watertight,
   manifold, non-self-intersecting), volume fidelity (relative 0.0736,
   revoxelized 0.0783, absolute 0.00951 m3), volume constraint
   (`V=0.0719735015 <= 0.0763256681`), width/gap (measured true minimum solid
   width 0.05 m; the policy declares no minimum), lineage hashes and the
   `stage_v_clearance_v1` preflight all pass. Iso 0.4 fails feature shrink;
   iso 0.6 fails volume fidelity. The candidate is a blocked-stop checkpoint,
   not a converged terminal.

   **Stage S baseline registration (2026-09-24):** the selected iso-0.5
   `rho_projection` handoff is registered as the Stage S baseline
   ([`evidence/stage_s_baseline_v16_2026_09.json`](evidence/stage_s_baseline_v16_2026_09.json),
   SHA-256 `db54601caa3acc02649b5b4b759d30c4e8668d530a614993b5f8c0dd4bef412f`)
   with the Exit Gate E binding: candidate rho hashes, campaign
   manifest/outcome, handoff manifest, surface STL, revoxelized/source density,
   four-field bundle file hashes plus the `rho_projection`/`beta_solver` array
   hashes, transform (`r=0.15`, `b=128`, `eta=0.5`, `q=100`), volume
   (`V=0.0719735015 <= Vmax`), and a re-run `stage_v_clearance_v1` preflight
   pass. Work F profiles are pinned (`stage_v_qualification_v1`,
   `fd_gradient_v1`). Registration is not a Stage S qualification.

   **P20 re-audit repair, PQ4.1 v2 and baseline v2 (2026-09-24):** an
   independent audit found two reproducible false-negative classes in the
   direct self-intersection detector (coplanar area overlap; shared-vertex
   crossings away from the shared vertex). The topology-aware repair (commit
   `17e80f4`) detects both, permits contact only on the shared simplex, and
   rejects degenerate triangles fail-closed. The repaired gate rejected the
   registered iso-0.5 surface: marching cubes emitted 4-8 collinear sliver
   triangles (area <= 1e-10 m^2, aspect > 1e7) that point merging could not
   remove. The handoff now extracts the binary cell material with VTK surface
   nets (`contour_labels`, no smoothing): no degenerate triangles, watertight,
   manifold, and the cell volume is reproduced exactly (measured absolute
   difference 1.5e-9 m^3 on the v16 candidate). The PQ4.1 v2 judgment
   ([`evidence/pq4_1_v16_state_stage_s_entry_v2_2026_09.json`](evidence/pq4_1_v16_state_stage_s_entry_v2_2026_09.json))
   selects iso 0.5 and returns `ready_for_stage_s=true`; the Stage S baseline
   v2
   ([`evidence/stage_s_baseline_v16_v2_2026_09.json`](evidence/stage_s_baseline_v16_v2_2026_09.json),
   SHA-256 `a6d40a5c25d9a4ca44aaf1c4d9a7b667d6d33fcfeed45d4b7e2b3cdb049abed6`)
   re-binds the baseline to that judgment and supersedes the v1 record. The
   volume-fidelity and feature-survival sub-gates pass by construction for the
   exact extractor; they remain guards against future extractor changes.

   **Work F0 baseline preparation (2026-09-24):** the immutable Work F manifest
   ([`evidence/stage_s_work_f_manifest_2026_09.json`](evidence/stage_s_work_f_manifest_2026_09.json),
   SHA-256 `03b109f15e79036fe31a6ec76cd58831f8f834926aee2c0eaf654ea80b47dfdd`)
   binds the baseline v2, the matched-Re laminar problem spec, the V1 voxel size
   (`0.05 m`), the case path, the clearance/mesh profiles, the drag/downforce
   response identities, the mesh-only commands and the fail-closed stop rules.
   The solver-free preflight
   ([`evidence/stage_s_work_f_v1_preflight_2026_09.json`](evidence/stage_s_work_f_v1_preflight_2026_09.json),
   SHA-256 `3f850e20dfff91bef91fb676cc84bdcd55710912fa4cfa899fcaf6d46c350f06`)
   rendered the V1 case from the registered v16 iso-0.5 surface and verified
   the metadata (flow case `matched_re_laminar`, laminar, `U=1`, `rho=1`,
   `mu=1e-2`, Aref `0.64`, lRef `0.8`, CofR `(0.25,0,0)`, drag `(1,0,0)`, lift
   `(0,0,1)`, force patch `design_candidate`, fixed domain bounds, voxel size)
   and the clearance preflight pass. The mesh-only run
   ([`evidence/stage_s_work_f_v1_mesh_2026_09.json`](evidence/stage_s_work_f_v1_mesh_2026_09.json),
   SHA-256 `4a257ac608c022479a918e2adb0e2ebba2fe1bb6f3680c7f38ba6efd961d2577`)
   passed the registered `stage_v_qualification_v1` mesh gate: `39848` cells,
   one failed check line (`Concave cells ... 2441`, fraction `0.06126` below
   the registered `0.08`), `solver_allowed=true`; no solver was started.

   **Work F V1 baseline qualification (2026-09-24):** the primal baseline ran
   ([`evidence/stage_s_work_f_v1_solver_2026_09.json`](evidence/stage_s_work_f_v1_solver_2026_09.json),
   SHA-256 `3c1e5b437f5a9e425dee8b0e7f0b488365bf5c3ddd971c74fd7aaa2e1657fe4f`):
   `residualControl` convergence (final `Ux/Uy/Uz/p` `4.91e-7/8.18e-7/9.80e-7/3.11e-6`),
   force stationarity pass (Cd mean `2.52344`, window drift `-1.106e-4`; downforce
   mean `1.69084`, window drift `-6.305e-5`), and the solver-execution clearance
   reconfirmation for the exact registered surface, which meets P17's closure
   condition (bounded to this candidate and level). `surface_fd_allowed=true`.

   **Work F surface-FD registration and solver-free preflight (2026-09-24):**
   two response-specific immutable FD manifests (drag, downforce) share one
   perturbation catalog
   ([`evidence/stage_s_work_f_surface_fd_catalog_2026_09.json`](evidence/stage_s_work_f_surface_fd_catalog_2026_09.json),
   SHA-256 `e4cdbe437eaa32dc752ad603a5d921aa94a4a47511e4a0403ead58ac49d5b4a8`;
   drag manifest hash `3f8f8e5973f300dd4b27892024486ced4e064bbd3c2682ed66f1279cd77c7f79`,
   downforce `9c19160d078bbc283bc96f9e1a6a7d9a806b3e6bc030348189917602de0c4701`):
   epsilons are registered as dimensionless ratios (0.002/0.005/0.01/0.02 of
   the 0.05 m voxel -> `1e-4/2.5e-4/5e-4/1e-3 m`), the four directions are
   downforce- and drag-gradient-aligned plus random seeds 11/2026, and the
   fixture binds the `volumetricBSplines` surface basis, the fixed outer
   patches, the `1e-3 m` displacement cap, the response identity/sign contract
   and the near-zero rules. The solver-free preflight
   ([`evidence/stage_s_work_f_surface_fd_preflight_2026_09.json`](evidence/stage_s_work_f_surface_fd_preflight_2026_09.json),
   SHA-256 `93c6c6b5007f6ff6741a3bedc4fa2d87ce85d48c5bf8be0b2a0297bff9588efc`)
   checked the conservative uniform normal offset at every epsilon in both
   signs: watertight, winding-consistent, no self-intersection, minimum solid
   width `0.05 m`, volume change `<= 2.1%`, clearance pass;
   `campaign_allowed=true`, no solver started. The v2 FD evaluator's
   below-noise silent pass is fixed: a gradient-aligned derivative below the
   noise floor is unresolved and fails closed, and non-aligned near-zero
   directions use the registered absolute rule.

   **Work F base adjoint case (2026-09-24):** the qualified V1 case was copied
   to `work/stage_s_work_f_v1/adjoint/base` and the OpenFOAM v2512
   `adjointOptimisationFoam` dictionaries were rendered: two adjoint solvers
   (`adjDownforce` direction `(0,0,-1)`, `adjDrag` direction `(1,0,0)`, both
   with the registered Aref `0.64` / UInf `1` / rhoInf `1` and the
   `design_candidate` patch), `shapeType volumetricBSplines` with
   `sensitivityType surface` / `includeSurfaceArea true`, and the
   `volumetricBSplinesMotionSolver` with an
   axis-aligned `8x8x8` control volume whose boundary control points are
   confined (the far-field stays fixed). The structural checks and OpenFOAM's
   own dictionary reader pass
   ([`evidence/stage_s_work_f_adjoint_preflight_2026_09.json`](evidence/stage_s_work_f_adjoint_preflight_2026_09.json),
   SHA-256 `0f5f94fb50ac566952d384311bd6da91f91d008c0465b8bbfe05a264239e45b4`);
   `adjoint_allowed=true`, no solver started. (The earlier `12fb6985...` record
   is a superseded diagnostic from the first render and is not retained.)

   **Work F base adjoint run (2026-09-24):** the base adjoint case ran to
   completion (`returncode=0`; primal 292 iterations, `adjDownforce` 425,
   `adjDrag` 562; three convergence markers). Both solvers wrote their
   design-variable derivative files
   (`optimisation/derivatives/volumetricBSplinesadjDownforceadjDownforceESI425`,
   `...adjDragadjDragESI562`); the `sensitivityType surface` variant also wrote
   `562/faceSensNormaladjDragESI`. The evidence
   ([`evidence/stage_s_work_f_adjoint_run_2026_09.json`](evidence/stage_s_work_f_adjoint_run_2026_09.json),
   SHA-256 `5034dc01b508a4e8e6f6628de7fab67776cdbd23f5640d6b59865c811cc8aeb7`)
   records `adjoint_converged=true`, `analytic_derivatives_ready=true`,
   `perturbation_allowed=false`. The analytic directional derivative for a
   registered direction is the derivative-file inner product
   `sum_i total_i * direction_i` over the active control-point variables.

   **Work F base-adjoint qualification and directions (Slice A, 2026-09-25):**
   the derivative contract is now authoritative, not row-order inferred:
   `NURBS3DVolume::getCPID = k*nCPUs*nCPVs + j*nCPUs + i`, `varID = 3*cp_id +
   component`, and `confineBoundaryControlPoints true` leaves exactly the
   interior `6x6x6` control points (648 components) active; the qualifier
   verified the derivative files' `varID` set equals that active set exactly.
   Both adjoint final-residual maxima are `<= 9.3e-9` (primal `6.2e-8`) and the
   three solvers bind their convergence iterations. The four registered
   directions (`drag_gradient_aligned`, `downforce_gradient_aligned`,
   `random_seed_11`, `random_seed_2026`) are materialized as committed
   unit-infinity-norm vectors with hashes in
   [`evidence/stage_s_work_f_adjoint_qualification_2026_09.json`](evidence/stage_s_work_f_adjoint_qualification_2026_09.json)
   (SHA-256 `f0bec416540d3faf7f78dba09bcd3b2cb647740cf90fb53b4038cf9b2dcea606`).
   `perturbation_allowed=true`, `shape_update_allowed=false`.

   **Work F perturbation sides (Slice B, 2026-09-25):** the registered
   B-spline movement path is implemented and verified. Because
   ``volumetricBSplinesMotionSolver`` consumes a *control-point movement*
   (``setControlPointsMovement``) that plain ``moveMesh`` never sets, the
   repository now carries a small OpenFOAM utility
   ([`openfoam_utils/moveControlPoints`](../openfoam_utils/moveControlPoints))
   that applies the prescribed movement through the registered morpher and
   writes the moved mesh. For every registered direction/epsilon/sign pair the
   runner copies the qualified V1 baseline, writes the exact inf-norm
   `epsilon` control-point movement, applies the morpher, and runs
   `checkMesh`: all **32 sides pass** the pair-side gates (moved surface
   watertight/manifold/non-self-intersecting, volume change `<= 0.14%`,
   minimum solid width `0.05 m`, clearance preflight, registered checkMesh
   profile `concave <= 0.06128`, outer-patch displacement exactly `0.0`).
   Evidence
   ([`evidence/stage_s_work_f_perturbation_sides_2026_09.json`](evidence/stage_s_work_f_perturbation_sides_2026_09.json),
   SHA-256 `01aeda492f43e76e9dad173599f339ba48f9adb8dc5744de062de7ce47cbc9db`)
   records `all_sides_pass=true`, `primal_campaign_allowed=true`,
   `solver_started=false`.

   **Work F centered-FD campaign and judgment (Slice C/D, 2026-09-25):** all
   **32 perturbation primals** ran sequentially and every side converged to the
   registered solver/stationarity/checkMesh profile
   ([`evidence/stage_s_work_f_surface_fd_result_2026_09.json`](evidence/stage_s_work_f_surface_fd_result_2026_09.json),
   SHA-256 `048a2f9307d36a645e76dee7fac26c6325568888cfaa28063cf5685a4acbc9ee`).
   The gradient-aligned directional derivatives are qualified within the 5%
   profile with tight epsilon plateaus: downforce response
   `downforce_gradient_aligned` ratio `1.0408`, `drag_gradient_aligned` `1.0279`;
   drag response `downforce_gradient_aligned` `1.0266`,
   `drag_gradient_aligned` `0.9595` (plateau spread `<= 3e-4`). Every sign
   agrees. However, the registered random-seed directions exceed the 5%
   relative rule (downforce: seed 11 `1.0858`, seed 2026 `0.8796`; drag:
   seed 2026 `1.4593`; drag seed 11 `1.0376` passes at 3.8% but the response
   still fails on seed 2026), so the complete registered FD qualification is
   **false**: `both_responses_pass=false`, `shape_update_allowed=false`. This is a bounded fail-closed verdict, not a
   threshold change; the plan's fail branch applies: keep the shape update
   blocked and diagnose one factor at a time (candidate factors: the morphed
   movement bounding, the surface-area weighting convention, and the
   first-order `upwind` primal discretization behind the continuous adjoint).

   **Work F derivative diagnosis D0--D2 (2026-09-25, solver-free):** the
   diagnosis plan
   ([`stage_s_work_f_fd_diagnosis_plan_2026_09_25.md`](stage_s_work_f_fd_diagnosis_plan_2026_09_25.md))
   was executed through its first checkpoint. **D1 realized-direction audit**
   ([`evidence/stage_s_work_f_realized_direction_audit_2026_09.json`](evidence/stage_s_work_f_realized_direction_audit_2026_09.json))
   passes: all 32 sides reproduce the prescribed movement exactly (max
   `<= 9.7e-9 m`), the boundary control points stay fixed, and all 16 pairs
   show unit cosine similarity with movement difference, odd-symmetry error and
   even component all `<= 1e-8 m`; the prescribed and realized analytic
   contractions agree to `~4e-6` absolute. **D2 semantics audit**
   ([`evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json`](evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json))
   passes: the adjoint objectives, the manifest response identities and the
   primal forceCoeffs identities agree, the contraction joins by `varID` with
   the boundary variables excluded, and an independent minimal parser
   reproduces the eight analytic directional derivatives at `1e-9` relative.
   No mapping or semantics defect was found, so the plan's conditional **D3
   bounded discretization diagnostic** (one registered middle epsilon, three
   directions, `linearUpwind` factor, 6 primals plus base/adjoint lineage) was
   registered and run
   ([`evidence/stage_s_work_f_discretization_diagnostic_2026_09.json`](evidence/stage_s_work_f_discretization_diagnostic_2026_09.json),
   SHA-256 `f3a85709817aa67d4fee8123d84d524784b403fd944702211c1677af878e67b6`):
   the `linearUpwind` base primal, both adjoints and all six sides pass, but the
   scheme shifts the baseline responses strongly (Cd `2.5234 -> 2.2333`,
   downforce `1.6908 -> 1.6659`). The mixed result — two previously failing rows
   cross the 5% gate (downforce `random_seed_11` `1.0857 -> 1.0432`, downforce
   `random_seed_2026` `0.8796 -> 1.0336`) while one control regresses (drag
   `random_seed_11` `1.0376 -> 0.8521`) and drag `random_seed_2026` remains
   `1.2608` — does not satisfy the plan's "controls do not worsen" condition:
   `supports_discretization_cause=false`. Discretization is a contributing
   factor, not the sole cause; the direction-dependent residual points to the
   continuous-adjoint formulation / surface-weighting / morpher chain-rule
   terms. No D4 full requalification and no D5 shape step are registered; the
   derivative remains unqualified and `shape_update_allowed=false`.

   **Work F post-D4.4 architecture decision (2026-09-25):** D4.1 component
   closure and D4.2 geometry Jacobian passed, while both D4.3 option ablations
   failed the sole-cause rule. The current detailed order is now
   [`stage_s_work_f_post_d3_plan_2026_09_25.md` §21](stage_s_work_f_post_d3_plan_2026_09_25.md#21-d44-後の-architecture-decision).
   Preserve the primal, mesh, objective, `volumetricBSplines` parameterization,
   registered directions/epsilons and FD evidence. First register a solver-free
   A0 comparison contract, then run at most one fixed base/primal lineage and
   the two A1 adjoints that change only
   `sensitivityType surface` (E-SI) to the native `sensitivityType shapeFI`
   formulation. `surfacePoints` is not an independent architecture candidate
   because it inherits the same E-SI formulation; a parameterization change is
   deferred because the current B-spline geometry Jacobian passed.    A1 is only
   a diagnostic against the existing FD rows: only a complete no-regression
   pass may enter the existing D5 holdout, then D6 requalification. A mixed or
   failed A1 stops this branch and requires a zero-run architecture memo before
   selecting a discrete-consistent sensitivity path or a new low-dimensional
   FD parameterization. `derivative_qualified=false` and
   `shape_update_allowed=false` remain authoritative throughout A0/A1 and until
   D5/D6 pass plus a separate D7 manifest.

   **A0/A1 executed (2026-09-25).** A0 registered the FI comparison contract
   (`evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json`,
   SHA-256 `e78d2fb8f40044910b9a80e672c5b0111c22a4741f7f319327a8a52c5ca357ce`).
   A1 ran one fixed lineage with `sensitivityType shapeFI`: both adjoints
   converged with `adjointSensitivity type : shapeFI`, the primal lineage and
   the 648-`varID` schema are unchanged, sign/plateau/near-zero gates hold, but
   the pass controls worsen and the failing rows remain, so
   `candidate_formulation_supported=false`
   (`evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json`,
   SHA-256 `de814a57de1a55f8cc1e4cee7039874d80af0f58e24d76692cd76bf914f0ed92`).
   The zero-run memo
   [`stage_s_work_f_architecture_decision_2026_09_25.md`](stage_s_work_f_architecture_decision_2026_09_25.md)
   now registers exactly two options for a future contract (alternative
   sensitivity path, or reduced-parameterization centered-FD path); neither is
   selected and no solver campaign is running.

   **Reduced-basis architecture S0/S1 executed (2026-09-25).** Option 2 was
   selected and the solver-free S0 contract was registered
   (`evidence/stage_s_reduced_basis_fd_manifest_2026_09.json`, SHA-256
   `261a20f1ad97c0feddc9641765d8ad3171dfd68d4051317a1b1f69b80e24a0d1`): the
   versioned reduced-basis ProblemSpec
   (`work/stage_sv_laminar/project_matched_re_laminar_reduced_basis_v1.yaml`,
   SHA-256 `e4b31ad3399ed6934b98192e5d941c871be81b84d28b5bca56bb499a6f771f79`)
   declares `maximize downforce / J = -downforce` with drag report-only and no
   constraints, and the design space is K=16 modes over the registered
   `volumetricBSplines` morpher (`delta_cp = B q`). S1 then generated the
   frequency-ordered y-symmetry-preserving sine modes, normalized each to unit
   maximum normal displacement per unit coefficient, and passed the plus/minus
   max-epsilon geometry/mesh/realized-motion preflight for all 16 selected
   modes (`evidence/stage_s_reduced_basis_mode_preflight_2026_09.json`,
   SHA-256 `1942993fbaf306f14932361ec85c71e48230aee8270af10b936c7d92ee1226f9`;
   modes span frequencies 3--11, efficiencies `0.45--0.95`, cosines `~1`,
   realized `+/-1e-3 m`). Two invalid preflight attempts were preserved and
   corrected (scratch-case reuse plus missing sine frequency factors; rate-gate
   misuse). No flow solver has run: `original_adjoint_derivative_qualified=false`,
   `reduced_basis_fd_qualified=pending` and `shape_update_allowed=false`. The
   registered PQ2 factor and +1.6 m continuation are both No-Go for S2. The
   same-candidate v16 factor screen and its corrected lineage audit are now
   also complete; both v16 outer-condition factors move the response beyond
   the registered band. A v16-specific +1.6 m continuation was registered and
   executed, and its adjacent transition remains outside the band. The final
   planned +3.2 m continuation and a same-domain mixed far-field contract also
   remain outside the band. The next step is solver-free case-construction and
   boundary audit; no further solver run is authorized until it identifies one
   physically justified correction.
6. **Stage S first step (blocked).** Keep the reduced-basis S2 epsilon
   calibration, all shape updates, and full optimization blocked. The
   solver-free v16 lineage audit has passed, but the same-candidate factor
   screen, domain ladder, and mixed far-field contract are all No-Go against
   the registered response bounds. The audit is registered in
   [`evidence/stage_s_v16_contract_audit_manifest_2026_09.json`](evidence/stage_s_v16_contract_audit_manifest_2026_09.json)
   and is contract evidence only. The next action is a solver-free
   case-construction and boundary audit; no new solver campaign is authorized
   until it identifies one physically justified correction and that correction
   is registered as a new contract. After an applicable contract passes, the
   local Work F path may qualify drag and downforce by centered FD; it does not
   establish an absolute or grid-independent downforce reference. Only a full
   S4 holdout pass may authorize at most one body-fitted shape step, followed by
   every geometry, mesh, and solver gate.
7. **PQ2 and v16 outer-condition diagnostics — No-Go for transfer.** The
   registered V2 treatments and the +1.6 m continuation belong to the PQ2
   candidate with STL SHA-256
   `613637cf0fac8bce8a124a479eb3f18417c06995bdbfbe1c99b792fe1db3686e` and
   remain diagnostic only. The Stage S v16 candidate is
   `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
   Its factor contract (`evidence/stage_v_v16_domain_boundary_contract_v2_2026_09.json`)
   was executed against the same Work F V1 baseline: `+0.8 m` domain
   extension gives downforce `0.6498148547` and top pressure-outlet gives
   `0.4379600526`, versus baseline `1.6908432549`; both exceed the registered
   bound, with all treatment-level qualification gates passing. The corrected
   post-processing lineage is independently audited in
   `evidence/stage_v_v16_domain_boundary_lineage_audit_2026_09.json`; the
   earlier reused-history result is diagnostic and is not used.
   The v16 `+1.6 m` continuation (`evidence/stage_v_v16_domain_continuation_2026_09.json`)
   gives downforce `0.5052720696` and remains outside the adjacent bound
   (`delta=-0.1445427850`, relative Cd `-0.1546827787`). Keep
   `reduced_basis_fd_qualified=pending`, `shape_update_allowed=false`, and do
   not start S2 while the solver-free case-construction and boundary audit is
   unresolved.
   The final planned `+3.2 m` continuation is also a No-Go: the adjacent
   transition from `+1.6 m` is downforce `-0.0773044` and relative Cd
   `-0.1952577`. A mixed `freestreamVelocity`/`freestreamPressure` contract
   at the same `+3.2 m` domain was then registered and executed; it changes
   downforce by `-0.0779653` and relative Cd by `-0.1035744` against the
   symmetry/patch baseline, also outside the bound. The candidate, non-boundary
   mesh, patch face ranges, and fresh force-history lineage are audited in
   `evidence/stage_v_v16_far_field_contract_audit_2026_09.json`. The
   domain-only ladder is closed. The subsequent solver-free construction audit
   found that the baseline and mixed case metadata still identify the generated
   ProblemSpec as `...domain_1p6_v2` even though the registered contract is
   `+3.2 m`; all other audited boundary, force-patch, operating-point,
   ground/domain, and final-flux checks pass. This is a provenance blocker,
   not evidence that the response is physical or transferable. The continuation
   runner now fails closed on this identity mismatch. No further solver run is
   authorized until a corrected contract is registered after the audit. Keep S2
   and all shape updates blocked.
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

## 2026-09-25 physical-profile correction registered (solver-free)

The v16 domain ladder exposed a physical confound: extending the inlet while
leaving a no-slip stationary ground changes the upstream boundary-layer
development.  The Stage V body-fitted adapter now consumes the existing
`boundary_conditions`/`motion_profiles` vocabulary, preserves the historical
default when only the legacy inlet/outlet pair is declared, and supports an
explicit `far_field` profile (`freestreamVelocity`/`freestreamPressure`) plus
an explicit translating ground.  Generated case metadata records the
normalized boundary contract, derived ground model, and a `physical_profile`
hash.

The next v16 physical profile is registered in
[`evidence/stage_v_v16_physical_profile_contract_manifest_2026_09.json`](evidence/stage_v_v16_physical_profile_contract_manifest_2026_09.json)
with run-manifest SHA-256
`394378c5cd86684c3eebb3d54b3ac55af0dfe4951aca4a0038c62d6c6297a412` and
profile-spec SHA-256
`3051b089de1642b93525a4d3f7ce89c5755f61fc6931101aa0eec177f2b2f278`.
It keeps the original V1 box and v16 candidate, sets all five outer patches to
`far_field`, and sets `bottom` to `moving_wall` with the `(1,0,0) m/s`
translation profile.  The contract is `registered_not_run`; no mesh, solver,
optimization, or Stage S update has started.  The registration script is
[`scripts/register_stage_v16_physical_profile_contract_2026_09.py`](../scripts/register_stage_v16_physical_profile_contract_2026_09.py).

The contract is a reduced laminar diagnostic and does not qualify an absolute
or grid-independent downforce value, Stage S finite differences, or high-Re
FSAE physics.  Keep `reduced_basis_fd_qualified=pending`,
`shape_update_allowed=false`, and perform the solver-free construction audit
before authorizing one physical-profile solver run.

## 2026-09-25 physical-profile contract v2 (solver-free correction)

The first physical-profile registration is retained as immutable historical
evidence but is superseded before any solver run.  Its renderer used
`movingWallVelocity`, which is a mesh-motion semantic and does not express the
fixed-mesh translating-ground contract required here.  The renderer now emits
`translatingWallVelocity` with an explicit `U (1 0 0)` and fixed `value` on the
bottom patch.

The corrected v2 contract is registered in
[`evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json`](evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json)
with run-manifest SHA-256
`de7068b1719fa9ecf854733e778ae69d7af8d34227b5927e071923b7431952cd` and
physical-profile SHA-256
`a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca`.
The canonical ProblemSpec, design-domain STL, and v16 candidate snapshot are
tracked under
[`evidence/assets/stage_v_v16_physical_profile_v2`](evidence/assets/stage_v_v16_physical_profile_v2),
and the candidate lineage is recorded in
[`evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json`](evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json).

The physical-profile hash now includes the normalized boundary contract, the
OpenFOAM boundary-condition implementation, free-stream velocity and pressure,
motion profiles, and turbulence model.  The metric is split into two gates:
first qualify the new physical profile itself; only then compare at least two
domains with the same physical-profile hash and unchanged physics.  The old
stationary-ground result is not a pass/fail reference for the first run.

Registration and materialization remain solver-free.  Keep
`reduced_basis_fd_qualified=pending`, `shape_update_allowed=false`, and do not
start Stage S or a domain-convergence campaign until the v2 profile passes the
registered physical-profile gates.

## 2026-09-26 physical-profile qualification: V1 No-Go and next contract

The numeric physical-profile gates were registered before computation in
[`evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json)
and its run manifest
[`evidence/stage_v_v16_physical_profile_qualification_run_manifest_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_run_manifest_v1_2026_09.json).
The manifest pins the v2 ProblemSpec, candidate, design-domain surface,
physical-profile hash `a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca`,
the Docker image ID, the existing `stage_v_qualification_v1` mesh/solver/force
profile, and explicit mass, wall-flux, upstream-velocity, outer-backflow and
pressure-disturbance thresholds.  Registration recorded no solver or mesh
execution.

Exactly one controlled OpenFOAM run then used the original V1 box and the
registered v16 candidate.  The run completed normally: `simpleFoam` stopped at
the declared residualControl criterion after 546 iterations.  Mesh
qualification, final residuals, force stationarity, normalized mass imbalance,
moving-ground velocity and zero-normal-flux, candidate flux, clearance, and
upstream velocity all passed.  The raw `checkMesh` output still contains its
allowed concave-cell failed line; the measured concave fraction is `0.06126`
against the registered `0.08` limit.

The physical-profile result is
[`evidence/stage_v_v16_physical_profile_qualification_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_v1_2026_09.json)
(SHA-256 `de500ec9ce7166ef71dee721fbd6d45f548896f381a11880b411e6489c7fb002`).
The outer backflow ratios passed, but the outer kinematic-pressure gate failed:
the inlet maximum was `0.29055 U_inf^2` and the top maximum was `0.05192
U_inf^2`, above the pre-registered `0.05 U_inf^2` limit.  This is a physical
profile/far-field adequacy No-Go, not a solver-convergence failure.  The old
stationary-ground result is not a reference comparison.

The next slice is a new immutable contract with the same candidate, operating
point, laminar model, moving-ground/freestream semantics, force normalization,
and physical-profile hash, changing only the domain bounds to increase
upstream/top/side clearance.  Re-measure the same gates before any
same-profile domain-convergence comparison.  Do not loosen the recorded
pressure threshold after seeing this run.  Stage S, reduced-basis FD,
optimization, PQ5 ranking, and shape updates remain blocked until the
physical-profile gate passes; only then may at least two same-profile domains
be compared using the registered `0.005` downforce and `0.02` relative-Cd
bounds.

## 2026-09-26 physical-profile qualification and same-profile convergence

The numeric physical-profile gates were registered before computation in
[`evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json).
The original V1 box returned a No-Go only for the outer pressure-disturbance
gate: inlet `0.29055416` and top `0.051920264` in `U_inf^2`, against the
immutable `0.05` limit.  Solver convergence, force stationarity, mass
conservation, moving-ground/candidate flux, clearance, upstream velocity, and
mesh qualification all passed.  This result is diagnostic evidence and was
not compared with the old stationary-ground case.

The first same-profile expansion changed only the inlet bound from `-1.5 m` to
`-2.5 m`.  Its controlled outcome
[`evidence/stage_v_v16_physical_profile_expanded_domain_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_expanded_domain_v1_2026_09.json)
still failed only the inlet pressure gate (`0.077604551`), so it cannot count
as a qualified domain.  The next case kept the same physical profile and
passed the outer gate: its outcome is
[`evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json`](evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json),
SHA-256 `8871255838b9666683581a3cb50d949764f6a4b27fb3dab24d6f6f52b4a75e66`.
It measured inlet pressure maximum `0.020346387`, top maximum `0.026347419`,
`42,619` cells, mean `Cd=1.1693991`, and mean downforce `0.7565515`.

The same-profile convergence contract then changed only the downstream bound
from `2.5 m` to `3.5 m`.  The child outcome
[`evidence/stage_v_v16_physical_profile_domain_convergence_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_domain_convergence_v1_2026_09.json)
passed all physical-profile gates with `43,204` cells, mean `Cd=1.1703630`,
and mean downforce `0.7573549`.  The immutable pair evaluation
[`evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json`](evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json),
SHA-256 `13374c722b4993f941ca6487a305fe2f371551d2eed152f744ef016f5b18b5bf`,
passes with `|delta downforce|=0.0008034 <= 0.005` and
`|delta Cd|/|Cd_parent|=0.0008242 <= 0.02`.  Both cases share candidate SHA
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11` and
physical-profile SHA
`a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca`.

This closes the registered reduced-laminar physical-profile and two-domain
convergence gates for this v16 candidate.  It does not establish an absolute,
grid-independent, high-Reynolds-number, or full-vehicle downforce reference;
the raw `checkMesh` concave-cell marker remains visible under the allowed
qualification profile.  The next authorized slice is to freeze this profile
as the Stage V reference, register the K=16 reduced-basis centered-FD
preflight, and run only its prescribed epsilon and holdout gates.  Keep
`shape_update_allowed=false` until the complete S4 holdout and every geometry,
mesh, solver, and clearance gate pass.  PQ5 ranking and production
optimization remain downstream of that qualification.

## 2026-09-26 Stage S reduced-basis FD v2 contract and S0R/S1R

The v2 qualified physical profile is now frozen as the Stage S working
reference and rebound to the exact historical K=16 mode basis.  The
registration was computed without a flow solver and is immutable:
[`evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_manifest_2026_09.json),
SHA-256 `b96df520e6a359c206b9ded3c4cb1872220344ba9a46c7a7492d0e1ba47860dd`.

It binds the v2 Stage V ProblemSpec
(`project_matched_re_laminar_moving_ground_far_field_v2_expanded_domain_v2.yaml`,
SHA-256 `6e41d2bbe9ac6a272f122f7e2556fe2ae9904b0572415eb548f438406885278e`),
the Stage S working ProblemSpec
(`evidence/assets/stage_s_reduced_basis_fd_v2/project_matched_re_laminar_moving_ground_far_field_v2_reduced_basis.yaml`,
SHA-256 `9503400412509be755b7599d1e504b36519a1e33c5599347caf6f0c62e9318ed`),
candidate SHA-256
`5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`,
physical-profile SHA-256
`a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca`,
Docker image ID
`sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319`,
the working domain `[-2.5,-1.2,-0.9] -> [2.5,1.2,0.9]` m (v3 is retained only
as the same-profile domain-convergence witness), the `J = -CDF` downforce
objective with drag report-only and no constraints, the force normalization,
the `8x8x8` control-point catalog, the unchanged morpher, all 16 historical
mode vector hashes, and the epsilon ladder
`1e-4/2.5e-4/5e-4/1e-3 m`.

The objective audit isolates the difference from the Stage V reference to
`problem_id` and `objectives` only: Stage V remains `minimize_drag` (the
expanded-domain spec), while the Stage S spec declares
`maximize_downforce` with canonical `J = -CDF`.  The historical mode
selection is reused byte-for-byte and was not rerun or replaced; no
response-dependent reselection or reserve substitution is allowed.

The solver-free S0R/S1R requalification
([`evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_preflight_2026_09.json),
SHA-256 `3f6cb15eae5b7770640466c89f9c296a383dd152f9f1dc0fedbc95d69acdaf50`)
passed on all counts.  The S0R base-case construction audit passed every
identity, bounds, field, and candidate check on the registered
`42,619`-cell v2 body-fitted case.  S1R applied the registered maximum
epsilon `1e-3 m` to both signs of all 16 modes (32 sides plus 16 morpher
amplitude calibrations) and every side passed: morpher success, outer-patch
CP immobility exactly `0.0`, realized-equals-prescribed (max movement
difference `4.7e-9 m`), realized direction cosines `>= 0.9999999999`, even
component `<= 5.0e-9 m`, unit-normalized amplitude (realized max normal
displacement `1.0000000e-3 m`), watertight/winding/positive-volume surface,
no self-intersection, minimum solid width `>= 0.0466 m` against the declared
`0.01 m` policy, volume change `<= 0.31%` against `2%`, clearance profile
pass, and the registered `checkMesh` profile pass at a concave-cell fraction
of `0.0692--0.0699` (raw concave marker recorded, not a raw clean pass).
The v2 morpher amplitude calibration is recorded per mode
(`0.986--1.044`); the mode directions and historical vector hashes are
unchanged.

`preflight_pass=true`, `n_modes_passed=16/16`, `flow_campaign_allowed=true`.
No flow solver was started and no flow field was evaluated.
`reduced_basis_fd_qualified` remains `pending` and `shape_update_allowed`
remains `false` until S2 epsilon calibration, S3 all-mode centered FD, and
the S4 holdout all pass under the registered rules.  The registered S2 budget
is at most 24 primals for the lowest/middle/highest-frequency modes; every
perturbed shape must additionally pass the v2 physical-profile gates
(mass balance, ground/candidate normal flux, upstream velocity, outer
backflow, outer pressure), and a case that loses far-field adequacy is not a
usable gradient sample.  Epsilon and thresholds must not be changed from the
observed results; S4 failure keeps the shape update blocked.

## 2026-09-26 SDF-native architecture fork (legacy K=16 Stage S superseded)

The checksum-verified handoff bundle `docs/CFD_opt_sdf_SDF_native_handoff/`
is adopted as the subordinate execution plan for the next line;
`phase_plan.md` remains the sole roadmap authority.

**Decision.**

- The canonical design state becomes the SDF field `phi` with the immutable
  convention `phi < 0` solid / `phi > 0` fluid. STL, B-spline control points
  and body-fitted meshes are derived artifacts, never the design variable.
- The K=16 B-spline reduced-basis Stage S v2 contract and its S0R/S1R pass
  are preserved byte-identically as `superseded_reference`; **S2 is
  intentionally not started**. The freeze record is
  [`evidence/stage_s_reduced_basis_fd_v2_supersession_2026_09.json`](evidence/stage_s_reduced_basis_fd_v2_supersession_2026_09.json)
  (SHA-256 `1eee51fdd03bc0402650d45b2d8174f969cbe2216c329c76b7275880f2c4a35d`).
  No existing manifest or evidence was modified.
- WaterLily.jl is the first candidate primal backend only. PR #285 "Reverse
  AD via Enzyme extension" was re-verified open at
  `feed49f480b52047b4e9b8bfacdf3e4f8201106b` on 2026-09-26: CPU reverse mode
  works through full `sim_step!` with a custom implicit Poisson rule; GPU
  reverse remains blocked by a missing Enzyme CUDA rule
  (`cuMemcpyHtoDAsync_v2`); the default Poisson tolerance gives roughly 10%
  disagreement versus ForwardDiff, improving to roughly `2.4e-5` at
  tolerance `1e-10`. WaterLily is not a qualified production reverse-adjoint
  backend, and its license and paper were re-verified (MIT Expat; CPC 315,
  109748, 2025).
- OpenFOAM Stage V remains the independent body-fitted verifier; DAFoam is
  the discrete-adjoint correctness reference; OpenLB/TCLB are fallback
  research backends; centered FD remains the permanent gradient oracle.
- Objective semantics for the new line: minimize `f = -CDF`; division-free
  efficiency constraint `g_R = R_min*CD - CDF <= 0`; normalized volume
  `g_V = V/V_max - 1 <= 0`. The Stage V physical-profile gates are retained
  as the solver-independent semantic contract with per-backend adapter
  identities.

**PR-01 (solver-free, commit `Architect SDF-native optimization core and
freeze legacy Stage S`).** Adds the canonical SDF design-state contract
(`design/sdf_state.py`), solver-neutral oracle/gradient protocols
(`oracles/base.py`, `gradients/base.py`), deterministic runtime identity
(`runtime/fingerprint.py`), the canonical objective/efficiency/volume
semantics (extended `canonical_objective.py`), the repo inventory
([`evidence/repo_inventory_sdf_native_v1.json`](evidence/repo_inventory_sdf_native_v1.json),
SHA-256 `00694da5b33b95893ca256bbd8cd5996686ee266c0e0291b8152ff6c562fa559`),
and the architecture registration
([`evidence/sdf_native_architecture_registration_2026_09.json`](evidence/sdf_native_architecture_registration_2026_09.json),
SHA-256 `743e90cb58dc46e93392ec3283a6d7f549f7ad8597b93c0d109220ecea637cbe`).
All conservative flags stay false: `shape_update_allowed`,
`sdf_gradient_qualified`, `waterlily_reverse_cpu_qualified`,
`waterlily_reverse_cuda_qualified`, `topology_birth_qualified`. No CFD
campaign, no WaterLily run, no topology birth, and no evidence rewrite.

**Next gates, in order:** SDF genesis from the v16 candidate lineage ->
WaterLily primal (GPU) under the physical-profile adapter -> SDF directional
centered-FD qualification -> CPU reverse-AD PoC on a tiny case -> GPU
reverse/custom-adjoint Go/No-Go -> one constrained SDF update -> topology
birth -> OpenFOAM PQ5 verification. No optimization campaign before the
production gradient backend decision, and no high-Re/FSAE claim is implied
by the reduced-laminar physical profile.

## 2026-09-26 SDF genesis slice (v16 lineage) executed; repo inventory v2

The first gate of the SDF-native order is complete as solver-free contract
and capability work:

- `src/cfd_sdf/design/genesis.py` builds the canonical SDFDesignState from
  a registered Stage S handoff directory. Every handoff artifact hash is
  re-verified fail-closed; `phi` is the handoff's own point-grid SDF sample
  (`phi < 0` solid); the geometry masks are the registered fixed-grid cell
  masks under the recorded projection policy `v16_handoff_mask_projection_v1`
  (design = strict all-eight-active interior projection; fixed/forbidden/root
  = permissive any-adjacent projection).
- The v16 genesis ran on the hash-frozen handoff manifest
  (`work/pq4_1_v16_state_v2/sweep/threshold_0.5/handoff_manifest.json`).
  All nine mask contract checks pass, the material volume diagnostic is
  `0.12925000000000003 m^3` (equal to the handoff cell-threshold volume),
  and the state binds `source_sha256` to the registered baseline surface
  STL `5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11`.
  Evidence:
  [`evidence/sdf_native_genesis_v16_2026_09.json`](evidence/sdf_native_genesis_v16_2026_09.json)
  SHA-256 `3c8e241681c80962a7fd62f1926e382d473ec8e9f3e6b9140bea9600d41cf670`;
  canonical state `sdf_design_state.npz`
  `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`
  (`phi_sha256`
  `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`,
  point grid `61x33x25`, spacing `0.05 m`).
- A latent freeze-mechanism defect surfaced: the registered v1 repo
  inventory verified a live glob, so any append-only downstream addition
  failed its `--verify` even though no registered byte changed. The v1
  artifact, generator and sidecar remain untouched and byte-frozen; the
  fixed-set verifier
  [`repo_inventory_sdf_native_v2.json`](evidence/repo_inventory_sdf_native_v2.json)
  (SHA-256
  `8e31d9e30feca97d112a7803d611f926e1e0d8a3f993367f24e043c75a3c5d27`)
  records the same discovery globs with the live-tree defect corrected and
  a recorded supersession reason, and new freeze tests pin both sidecars.
- No solver started; all conservative flags stay false; no existing
  evidence was modified. Next gate: WaterLily primal under the
  physical-profile adapter (Colab T4 primary per the 2026-09-26 execution
  plan), preceded by the Julia/WaterLily environment registration on the
  Colab side and the pinned `julia/CFDSDFWaterLily/` package skeleton.

## 2026-09-26 plan correction v2.1: design-grid/flow-grid separation, SDF volume semantics, topology-policy gate

User-approved correction after the genesis slice.  The research direction
and the SDF-native architecture are unchanged; three contracts and the
WaterLily gate ladder are now explicit before the WaterLily primal gate.

**Contract 1 — design grid and flow grid are separate (permanent).**  The
canonical SDF grid (61x33x25 points, spacing `0.05 m`, origin
`(-1.0, -0.8, -0.6)`, x in [-1, 2], y in [-0.8, 0.8], z in [-0.6, 0.6]) is
a local design-space representation.  The qualified OpenFOAM v2 flow
domain (x in [-2.5, 2.5], y in [-1.2, 1.2], z in [-0.9, 0.9]) is a
different, independent solver box.  No run may claim a grid property by
silently equating the two; `SDFDesignState` must never be used directly as
a WaterLily flow grid.  The WaterLily side must embed the canonical phi
through a world-space adapter (trilinear `sdf_at_world(xyz_m)` over the
canonical grid, e.g. a `GridSDFBody`), with the solver flow grid
(resolution and domain) as an independent variable so the same canonical
phi can be run on coarse/medium/fine flow grids for grid studies.  The W1
adapter qualification must additionally fix, before any solver run:

- **outside-domain semantics**: for world points outside the design box
  the adapter returns a guaranteed positive read-only fluid extension
  (zero-level surface can never exist there), not an extrapolated
  negative value;
- **interface-to-boundary margin hard gate**: the zero-level surface must
  sit at least a registered margin away from the design-box boundary, so
  the constant-exterior extension can never contaminate an interface
  region;
- **world<->solver coordinate contract**: WaterLily typically uses
  solver/scaled coordinates, so the adapter registers the exact
  `x_sol <-> x_world[m]` scale and offset (affine map) with a fail-closed
  probe fixture, and every registered run advertises it in its
  `runtime fingerprint`.

**Contract 2 — SDF sharp volume semantics (registered now; differentiable
implementation deferred until the one-step gate).**  The Stage T density
volume `V_rho` (`0.0719735015` at limit `Vmax = 0.0763256681`) and the
handoff's measured binary sharp volume `V_sharp = 0.12925000000000003`
are different quantities; the ratio `V_sharp/Vmax` is about `1.69`, so a
sharp v16 start under the legacy Stage T `Vmax` would be grossly
infeasible by construction.  In the SDF-native line the constraint volume
is the voxel-equivalent sharp volume of the canonical state under the
registered center-sampling rule,

    V_phi = |{h-cubes with trilinear centre sample < 0}| * h^3,

which is the `epsilon -> 0` limit of the differentiable volume
`V_eps = integral H_eps(-phi) dOmega` under center sampling **at fixed
grid spacing**: letting the indicator sharpen (`epsilon -> 0`) gives the
sharp midpoint occupancy rule on the discrete grid, and the separate
continuum limit `h -> 0` of that discrete measure is what would converge
toward the geometric solid volume of the probability limit; these two
limits are distinct and only the discrete rule is registered.  The
smoothed H_eps implementation arrives with the one-step gate.  The first
SDF volume constraint is `V_phi <= V_phi_0` with `V_phi_0` **re-measured**
on the registered genesis state: 1009 sampled solid centers,
`V_phi_0 = 0.12612500000000004 m^3`.  Three samplings are registered and
explicitly separated in
[`evidence/sdf_native_volume_semantics_v1_2026_09.json`](evidence/sdf_native_volume_semantics_v1_2026_09.json)
(SHA-256 `0142ace4de9419dd73cc27e90135ed1fe1f847b074ca2faa37fdb0962505bbce`):
the contract measure (`0.12612500000000004`, 1009 centers), the
mesh-derived / revoxelized discrete volume of the registered baseline
surface (`0.12925000000000003`, 1034 cells, the handoff physical
cross-check, ratio `1.0248`; a discrete volume, not a continuum exact
volume), and the non-contracted node-occupancy diagnostic
(`0.17750000000000005`, 1420 nodes).  The legacy Stage T `Vmax` is not
carried into SDF Stage S evaluation.  If a physically smaller target were
wanted, it is a separate material-lineage decision requiring a
volume-calibrated offset rebuild, not a contract reuse.  The module
`src/cfd_sdf/design/volume_semantics.py` implements the sampled measure,
the limit semantics and the reporting-only over-volume
(`max(0, V - V_lim)`; contract level; the optimizer-side enforcement — a
signed residual `g_V = V_phi / V_phi_0 - 1` plus
`smoothed_volume_and_gradient(...)` — arrives with the one-step gate).

**Contract 3 — SDFTopologyPolicy v1 is a prerequisite gate for Birth-0
(registration may be later; no Birth-0 work before it).**  The v16
genesis state has empty `fixed_solid`, `forbidden` and `root` masks
(`solid_design_fraction = 1.0`), and the Stage S entry evidence records
`root_connectivity = not_applicable` for this candidate; the legacy
root-connectivity hard gate therefore constrains nothing today, which is
acceptable for the WaterLily primal but not for topology birth.  Before
any Birth-0 work, an SDFTopologyPolicy v1 registration must fix: whether
disconnected aero components are allowed; whether every component must
connect to a designated root region; and which region is the root.

**Updated gate order after genesis (W series).**  The gate ladder replaces
any implication that the WaterLily primal starts directly on v16:

```text
DONE   architecture fork                       (5750da1)
DONE   SDF genesis on the v16 lineage          (a35e687)
REGD   sharp-SDF volume semantics contract     (registration in this slice; enforcement deferred)
NEXT   W0  WaterLily environment registration  (Julia resolve/pin, Manifest, runtime fingerprint)
W1     SDF->WaterLily geometry adapter qualification (GridSDFBody interpolation; analytic sphere vs grid-SDF sphere)
W2     analytic WaterLily primal               (sphere fixture; CPU first, then T4)
W2b    same geometry at three flow-grid resolutions (bug isolation: interpolation / solver / BC)
W3     v16 WaterLily primal + physical-profile adapter
W4     WaterLily grid/domain response qualification
       SDF directional centered-FD qualification
       CPU reverse-AD PoC (Pinned PR #285)
       GPU reverse/custom-adjoint Go/No-Go
       one constrained SDF step (volume contract + all hard gates enforced)
REQD   SDFTopologyPolicy v1                    (registered before Birth-0)
       topology birth (Birth-0 geometry fixture first)
       bounded closed loop
       OpenFOAM PQ5 verification
```

**WaterLily package layout for W0-W4** (per the Colab T4 worker plan):

```text
julia/CFDSDFWaterLily/
  Project.toml
  Manifest.toml
  src/
    GridSDFBody.jl
    Simulation.jl
    Forces.jl
    Runtime.jl
  test/
    test_grid_sdf_body.jl
    test_analytic_vs_grid_sdf.jl
    test_force_sign.jl
scripts/run_waterlily_job.py
colab/worker.ipynb
```

Colab execution sequence: select T4 explicitly, record the runtime
fingerprint, Julia instantiate, then analytic sphere CPU, analytic sphere
T4, grid-SDF sphere T4, and only then the v16 geometry.  Repository
inventory v3 mints at the WaterLily primal gate, not per commit.

No qualified-gradient, shape-update or optimization-campaign claim is
authorized by this correction, and no claim inherits it; all conservative
flags remain false.

## 2026-09-26 W0 executed: Julia environment registered and verified on Colab CPU

- `julia/CFDSDFWaterLily/Project.toml` + `Manifest.toml` are committed as the
  pinned solver environment: WaterLily `1.8.0` resolved under Julia `1.12.6`
  (warning dato: the resolver-printed whole-graph versions are recorded in the
  W0 evidence). The Manifest is the byte-exact resolver output whose every
  uuid/tree-sha/version was cross-checked against the generating runtime;
  SHA-256 `65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c`.
- Verification on the Colab CPU runtime (clone of the committed branch, no
  push from Colab): `Pkg.instantiate()` exit 0 with `[ed894a53] WaterLily
  v1.8.0` and `using WaterLily` loads on a CPU-only runtime without a GPU.
- Evidence: [`evidence/sdf_native_w0_julia_env_2026_09.json`](evidence/sdf_native_w0_julia_env_2026_09.json)
  SHA-256 `9689ed58dfda87414bc1a4be8fce49d86405c2619217540bfe08391b98b3e5e7`.
- No CUDA/Enzyme added yet; no CFDSDFWaterLily package source modules yet
  (they arrive with W1/GridSDFBody); no solver, no force value; all flags
  false. Next gate: W1 GridSDFBody adapter qualification under contract 1
  (outside-domain fluid extension, interface-to-boundary margin, world<->solver
  coordinate map), then W2 analytic sphere primal (CPU first, then T4).

## 2026-09-26 W1 executed: GridSDFBody adapter qualified, v16 margin gate accepted

- Registered criteria: `evidence/sdf_native_w1_adapter_criteria_2026_09.json`
  SHA-256 `6da068fad8c79ba39197377157d4a5172dedf04511b2acbd8f69146aefea70ef`,
  used in correction round 4. Rounds 2/3 had bounded the interface-band sdf
  error at 1.0e-3 m from a Float32-rounding rationale; the deterministic
  fixture then failed fail-closed at 1.250e-3 m. The controlling term is the
  trilinear truncation error of the curved sphere SDF, not input rounding: the
  same run passes affine exactness (1.776e-15 m), round-trip (2.220e-16 m) and
  exact outside extension, and an independent numpy evaluation reproduces the
  band sup (1.2520e-3 m over 200,000 probes). Round 4 registers the analytic
  Kergin/tensor-Newton truncation bound 3.3e-3 m (surface cells cover
  r >= R - band - sqrt(3)h/2 = 0.455699 m; pure-second-derivative 2.057e-3 +
  mixed allowance 1.029e-3 + triple allowance 0.139e-3) and leaves every other
  bound unchanged. This is a documented fail-closed correction, not a
  post-measurement threshold fit; the failed value is carried in the criteria
  history and the evidence.
- Fixture suite: 10/10 registered gates pass under CLI Julia 1.12.6 with the
  pinned Manifest (`65638d8164df7853821ee6cb52b2163df491700c6f96b903b76558bc2bd0ea1c`):
  world<->solver round-trip 2.220e-16 m, affine exactness 1.776e-15 m,
  interface-band error 1.250e-3 m on 5000 explicit band probes (uniform-sampling
  interior diagnostic 1.271e-2 m recorded, not gated), zero-level radius
  1.826e-3 m, exact positive outside extension, margin-gate pass and refusal,
  all-solid refusal.
- Real-data diagnosis: the registered v16 genesis state (canonical state SHA
  `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`, phi SHA
  `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`) is
  accepted by the gate constructor at the registered 0.15 m margin with
  measured conservative clearance 0.34999999399 m, and the world<->solver
  round trip on the genesis grid is exact. Every later registered run must
  advertise the measured affine map (origin (-1.0,-0.8,-0.6) m, h 0.05 m,
  scale 20 m^-1) in its runtime fingerprint.
- Evidence: `evidence/sdf_native_w1_grid_sdf_body_2026_09.json` SHA-256
  `d618b556ec71c638f8d10f201c4ae4c62a2b163f824dd9466dd928e89c725567`. No
  solver run, no force value, no CUDA/Enzyme or Manifest change; all flags
  false. Next gate: W2 analytic sphere primal (CPU first, then T4), then W2b
  three-resolution bug isolation, then W3 v16 primal.
- 2026-09-26 user review of `10c940e`: two W1 prose statements are corrected
  append-only in `evidence/sdf_native_w1_prose_corrections_2026_09.json`
  (SHA-256 `0557cff619be80e1a3057e5048c0047629bcd0ee03fda39ff9a61e4ce3ad3b42`):
  the 0.001 m interface band is 0.02 h, not "ten cells"; the genesis margin
  measure is `d_face - |phi|`, not "gap plus |phi|". No immutable artifact,
  threshold, gate or measured value changes; W1 remains closed.

## 2026-09-26 W2a executed: first WaterLily primal (analytic vs sampled sphere, CPU)

- Registered criteria: `evidence/sdf_native_w2a_sphere_cpu_criteria_2026_09.json`
  SHA-256 `aea91e6cc8de65ef072b3fbb19a3ca50a01b5e75198e62c128fda3fe8849602f`.
  Fixture: WaterLily 96x64x64 solver grid (16 cells per diameter), Re_D = 100
  (U = 1, D = 16 solver units, ν = 0.16), Float32, CLI CPU multi-threaded;
  the sampled geometry is the exact sphere on a 61x33x29 lattice (h = 0.05 m,
  margin 0.2 m) fed through the W1 `GridSDFWaterLilyBody` bridge; t_end = 60
  tU/D, burn-in 40, force on the body `F_body = -total_force`; gates G1-G8
  (completion, finiteness, force finiteness, drag sign, stationarity, cross-
  fixture Cd, lift bound, repeatability).
- Outcome: `evidence/sdf_native_w2a_sphere_cpu_2026_09.json` SHA-256
  `26b6a65f6a2f89dde7e9976b2209b776eeb90d895432707214a582e9192f920b`;
  all 8 gates pass. 2246 steps analytic / 2242 sampled; wall 612 s / 820 s on
  4 Julia threads (excludes kernel warm-up, reported separately); window-mean
  drag 88.425780 vs 88.233538; Cd 0.879587 vs 0.877675 (relative difference
  0.217% against the registered 10% bound); stationarity drift <= 1.9e-7
  (bound 0.02); |lift|/drag <= 3.5e-5; the identical analytic repeat matches
  with relative drag difference 0.0 (bound 1e-6); fields, forces and the
  sampled phi gate (margin 0.199999988 m) all finite/pass; child peak RSS
  580 MB.
- This is capability/numerical evidence for the first solver run, not a Cd
  validation: the compact domain and 16 cells/D rung are not qualified for
  absolute values and blockage is about 5%. No T4/CUDA, no Manifest change,
  no gradient and no v16 physics. Next gates: W0b Colab T4 + CUDA environment,
  then the W2 T4 primal on the identical fixture, then W2b three flow-grid
  resolutions.
- 2026-09-26 append-only semantic clarification:
  `evidence/sdf_native_w2_semantic_clarification_2026_09.json` (SHA-256
  `6a46e63fcf798797d9c7706ac6dcbb1712fd8578010f752d8c94d43ac13850e3`).
  (1) The W2a arithmetic sample mean is a steady-fixture diagnostic only;
  (2) future canonical time-averaged aerodynamic responses use physical
  solver-time weighting `mean(F) = integral(F dt) / integral(dt)` with a
  registered trapezoidal or equivalent rule; (3) the generic solver backend
  returns the Cartesian `F_body = -total_force` and drag/lift/downforce are
  ProblemSpec / physical-profile projections, not fixed components. W1 and
  W2a evidence are unmodified and the W2a verdict stands.

## 2026-09-26 W0b executed: Colab T4 CUDA environment registered

- Registered criteria: `evidence/sdf_native_w0b_t4_cuda_env_criteria_2026_09.json`
  SHA-256 `9f68eb6fae9cf412b1ab9694045fd053b9b7298ba11d2b277394e8526f15d843`.
  The T4 environment is a separate directory `julia/CFDSDFWaterLilyT4` (same
  WaterLily 1.8.0 pin plus CUDA.jl, deps-only Project, no compat block) so
  the W0 CPU environment stays byte-frozen.
- Environment resolved on the explicitly selected Colab T4 runtime:
  Project SHA-256 `e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194`,
  Manifest SHA-256 `c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707`
  (846 lines, resolved under Julia 1.12.6; CUDA v6.3.1 + WaterLily v1.8.0).
- Measured: Tesla T4 (UUID `GPU-1fe89c69-4615-ad3d-88cb-2450c240208e`,
  15360 MiB, compute capability 7.5), driver 580.82.07, CUDA runtime 12.8.0,
  `CUDA.functional() == true`, CuArray and KernelAbstractions CUDA smoke pass,
  `WaterLilyCUDAExt` loads; no `Simulation`/`sim_step!` was constructed
  (registered gate G5). The KernelAbstractions smoke uses the names reexported
  by WaterLily, so the T4 Project needs no additional direct dependency.
- Evidence: `evidence/sdf_native_w0b_t4_cuda_env_2026_09.json` SHA-256
  `4f822429656f36020410bcae6c375591d512ac3f4f58011e263346515f1237e6`; 7/7
  gates. The W0 CPU evidence is unmodified. Next: W2-T4a analytic sphere
  primal on this exact fixture, then W1g GPU GridSDF bridge, W2-T4b sampled
  sphere, W2b three flow grids. No solver step is qualified by W0b.

## 2026-09-26 W2-T4a executed: analytic sphere primal on Colab T4

- Registered criteria: `evidence/sdf_native_w2t4a_analytic_sphere_criteria_2026_09.json`
  SHA-256 `154fec9111737f8cb76579f0a02fd2d6b4c043c30250d1d24b8a5d05b3ea15ad`.
  Identical W2a fixture (96x64x64, 16 cells/D, Re_D=100, Float32, t_end
  60 tU/D, burn-in 40) with `mem=CuArray`; the criteria additionally register
  the trapezoidal physical-time-weighted mean as a diagnostic
  (`integral(F dt)/integral(dt)` over the window samples) next to the W2a
  arithmetic mean used for the CPU/T4 historical comparison.
- Result: `evidence/sdf_native_w2t4a_analytic_sphere_2026_09.json` SHA-256
  `70f747e264bacc9c3360ab9d6445c7bb77e6b11a6a6d521271297780301af754`;
  9/9 registered gates (T0-T8). 2246 steps; wall 27.94 s on the T4 against
  612 s on the 4-thread CPU; 12.45 ms/step with a 21.48 s warm-up excluded;
  polled peak CUDA VRAM 53.8 MB of 15.6 GB. Window-mean drag 88.42577373 on
  T4 versus 88.42577970 on CPU (relative difference 6.75e-8 against the
  registered 1% bound); stationarity drift 1.20e-7; the identical T4 repeat
  reproduces the statistics exactly (relative difference 0.0); the
  time-weighted mean drag is 88.42577367 (diagnostic, nearly identical on
  this steady fixture).
- This qualifies the CUDA solver path for the analytic fixture only. The
  GridSDF bridge on GPU (W1g), the sampled sphere on T4 (W2-T4b) and the
  grid ladder (W2b) remain open; no v16, gradient or reverse-mode claim is
  authorized. Job `scripts/waterlily_w2t4_job.jl` (analytic mode; the
  `gridsdf` mode is reserved for W2-T4b), recorder
  `scripts/register_sdf_native_w2t4a_analytic_sphere_2026_09.py`.
