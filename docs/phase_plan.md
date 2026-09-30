# Authoritative Roadmap: Generic Aerodynamic Topology Optimization

Date: 2026-09-29
Status: authoritative
Scope: generic rigid-object aerodynamic topology and shape optimization
Architecture decision: SDF-native production research direction adopted on 2026-09-26

This is the only implementation roadmap for the project. Historical
density/Brinkman, B-spline, body-fitted, and front-wing-specific work is
retained capability and evidence context, not a second development plan. The
front wing remains a later complex benchmark; it does not define the product
architecture.

## Current SDF-native production research direction

The current design state is a bounded Cartesian signed-distance field `phi`.
The WaterLily immersed-boundary fixed-grid solver is being qualified as a
candidate low-cost primal and optimization oracle. Body-fitted OpenFOAM remains
the independent Stage V verifier. The old Stage T/S/V work and its evidence are
preserved, but the density-to-iso-surface-to-B-spline sequence is no longer the
production optimization route.

The earlier [32 GB development design](development_plan_2026_09.md) and
[cross-platform architecture review](architecture_review_2026_09.md) remain
supporting history. Their CPU/Metal D2Q9 Taylor–Green probe has no aerodynamic
walls, force integration, SDF coupling, adjoint, or 3D support, and is not part
of the current production solver path.

Kaggle is an execution substrate for reproducible T4 batch runs, exact
source/runtime binding, and evidence capture. Colab-to-Kaggle migration is an
infrastructure decision; Kaggle is not a solver or optimizer component in the
architecture below. Operational details are in
[`kaggle_batch_runbook_2026_09.md`](kaggle_batch_runbook_2026_09.md).

The current gate order is maintained only in
[section 11](#11-current-sdf-native-execution-order). Older plans linked from
this page are subordinate historical context and do not replace that order.

## 1. Product objective

Build a configuration-driven optimizer for an arbitrary rigid object whose
canonical design state is a bounded Cartesian SDF `phi`. It must support
material addition and removal, merging and splitting components, and shape
refinement under aerodynamic, geometric, connectivity, and manufacturing
constraints. Continuous SDF deformation does not by itself create a detached
new solid; topology birth therefore requires an explicit nucleation or other
birth mechanism, which remains a separate unqualified research slot.

The first supported product profile is deliberately bounded:

- incompressible low-Mach external flow;
- steady or quasi-steady analysis;
- one rigid material;
- STL geometry roles for exchange and verification;
- bounded Cartesian SDF design state;
- immersed-boundary fixed-grid primal and qualified gradient path;
- geometry, connectivity, and manufacturing hard gates;
- independent body-fitted verification.

Compressible flow, fully unsteady flow, fluid-structure interaction, free
surfaces, and production AMR are future capability profiles.

## 2. Authoritative architecture

```text
ProblemSpec v2
  geometry roles + flow cases + responses + constraints + topology policy
        |
        v
Geometry / domain / resolution preflight
        |
        v
Canonical Cartesian SDF phi
        |
        v
WaterLily immersed-boundary fixed-grid primal (candidate)
        |
        v
Primal and grid/domain numerical qualification
        |
        v
Centered finite-difference gradient oracle
        |
        v
Qualified production gradient backend
  (reverse AD / discrete adjoint / other method; decision pending)
        |
        v
Constrained SDF update
        |
        v
Explicit topology birth / nucleation when required
        |
        v
SDF reinitialization + geometry / connectivity / manufacturing hard gates
        |
        v
Independent body-fitted OpenFOAM Stage V verification
```

The canonical optimization variable is SDF `phi` (`phi < 0` is solid,
`phi > 0` is fluid). STL and body-fitted meshes are derived artifacts for
exchange, geometry checks, or independent verification. The SDF volume
contract is registered; optimizer-side enforcement is still pending.

The explicit topology-birth slot may use a topological derivative, nucleation
operator, a retained density/Brinkman proposer, or another explicit birth
operator. No candidate has been selected or qualified. A topology policy that
defines disconnected-component and root-connectivity rules is required before
Birth-0.

WaterLily remains in qualification. Centered FD is the permanent independent
numerical gradient oracle; it is not the production gradient backend. Reverse
AD, discrete adjoint, and other gradient methods remain candidates until
qualified against that oracle. A WaterLily scratch reverse experiment is not
an adoption decision.

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

| Workstream | Current status | Evidence scope / next gate |
| --- | --- | --- |
| Canonical design state | SDF `phi` | Bounded Cartesian SDF is the canonical optimization variable. The genesis and sampled-volume contract are registered; optimizer-side volume enforcement is still pending. |
| WaterLily fixed-grid primal | Candidate primal/oracle under qualification; registered v16 finite-box primal contract passed | W0/W1 and sphere runs remain capability evidence. W3 round 4 qualifies only the canonical v16 integrity/force/stationarity contract on the registered WaterLily finite-box approximation; it does not qualify OpenFOAM equivalence or broader physical aerodynamics. |
| W3 primal | v16 round 4 and v17 round 1 registered finite-box primal contracts PASS; broader physical qualification remains false | v16 exact kernel `/5` and v17 exact kernel `/1` passed their own host-verified T0-T10 contracts. The v17 result is bound to its own state and criteria; neither result qualifies physical aerodynamics. The unresolved W3 v4 all-zero root cause is not retroactively closed. |
| W4 grid/domain sensitivity | v16 round 4 and canonical v17 round 1 sensitivity matrices passed exact-version host verification | v17 criteria SHA `5eceb62c…`, result SHA `25297c46…`, source `4c20787c`. Private dataset v1 inventory and exact kernel `/1` were verified; all four cases passed T0-T10. Resolution changes are large (flow16→24: drag 31.61%, downforce 23.43%; flow24→32: 6.77%, 8.37%), while the x+1 m domain change is below 0.26%. This remains finite-box sensitivity evidence, not grid/domain convergence or target-physics qualification. |
| Centered-FD SDF directional oracle | v16 round 5 terminal FAIL; v17 FD-05 round 1 terminal FAIL | Exact v17 / flow_24 kernel `/1` completed all 33 fresh primals. T0-T9 passed; T10-T11 failed the registered 5% N-based plateau gate in all six direction/response combinations. Strict host verification failed closed on `ERROR` / missing `DONE`; supplemental exact-source host recomputation is diagnostic only. See [`37_fd05_result.md`](issues/37_fd05_result.md). FD/gradient/reverse/optimizer/topology/shape-update flags remain false. |
| Production gradient backend | Undecided and unqualified | Reverse AD, discrete adjoint, or another method remains a candidate. Select only after qualification against the centered-FD oracle. |
| Constrained SDF update | Blocked | `shape_update_allowed=false`; first update requires the primal, grid/domain, gradient, volume, and geometry gates. |
| Topology birth | Unqualified; P23 policy is a prerequisite | SDF shape deformation alone does not create detached material. Register the topology policy and qualify an explicit birth mechanism before Birth-0. |
| Geometry / connectivity / manufacturing gates | Required at every update | Genesis and adapter checks are bounded contract evidence; the complete evolving-shape gate set is not qualified. |
| Stage V body-fitted OpenFOAM | Retained as independent verifier | The registered v16 physical profile and same-profile two-domain comparison passed for that candidate/profile. This is not grid-independent, high-Re, or full-vehicle qualification. |
| Historical Stage T density/Brinkman | Retained capability and evidence | Not the current production optimization path. Its optimizer, artifacts, and candidate-generation research may inform a future topology-birth proposer, which is not selected. |
| Historical Stage S / Work F | Retained derivative and geometry evidence | The B-spline/Work F route is not the current SDF production update path. |
| Kaggle / Colab | Execution infrastructure | Used for exact-source GPU batches and evidence capture; neither is a solver or optimizer architecture component. |

### Historical density/Brinkman Stage T and B-spline Stage S status snapshot (through 2026-09-25)

The following table preserves the earlier Stage T/S/V status and evidence
record. Its architecture and execution-order language is superseded by
sections 1, 2, and 11 and the current SDF-native addenda below; its historical
measurements and verdicts remain scoped to their original artifacts.

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

> **Scope note (2026-09-28):** Sections 5–8 retain common ProblemSpec/geometry
> contracts and earlier OpenFOAM qualification detail. OpenFOAM case compilation
> and the G2 physical checks serve the later independent Stage V verifier; they
> are not the current WaterLily primal or optimization path. The current W3/W4,
> FD, gradient, update, and topology order is only in section 11.

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

## 9. Retained density/Brinkman Stage T assets

Stage T density/Brinkman optimization is not the current production path. Keep
its research results as historical capability evidence and preserve its
candidate-generation, Python optimizer, artifact, and provenance infrastructure
for possible reuse. A density/Brinkman method may later be evaluated as one
candidate topology-birth proposer, but no such role or backend is currently
selected. It is not a mandatory SDF handoff or an active execution workstream.

## 10. Retained Stage S evidence and current Stage V role

The old B-spline / Work F Stage S route is retained as historical geometry and
derivative-qualification evidence. It is not the production SDF shape-update
path, and its K=16 campaign remains frozen; do not resume it as the current
optimizer.

Body-fitted OpenFOAM Stage V remains in the production architecture as an
independent verifier and cross-fidelity judge. It is not the optimization
engine. Existing physical-profile and domain-comparison evidence applies only
to its registered candidate and conditions; it does not establish
grid-independent downforce, high-Re or full-vehicle qualification.

## 11. Current SDF-native execution order

`phase_plan.md` is the sole current roadmap and order authority. The older
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
and [`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md)
are retained historical plans; neither controls current execution.

**2026-09-30 checkpoint (supersedes the FD items below where they conflict):** FD-04 (#36) traced the FD-02 non-smoothness to 66 flat force-band cells in canonical v16 (1-cell-thick plates on h=0.05 nodes). Genesis v17 (#43, h=0.025, same source surface) removes those exact-zero-gradient cells; W3 v17 passed its registered T0-T10 contract, and W4 v17 passed the registered four-case sensitivity contract on Kaggle T4. W4 shows a large response to flow resolution and a small response to the tested x+ domain extension; it does not establish convergence. v17 is the adopted canonical state. See [`session_handoff_2026_09_30.md`](session_handoff_2026_09_30.md) and [`issues/43_result.md`](issues/43_result.md).

**2026-09-30 FD-05 (#37) terminal result (supersedes the prior pending-FD-05 status and sequence items below where they conflict):** The registered v17 / flow_24 criteria ran once on Kaggle kernel `/1`; all 33 fresh primals completed. T0-T9 passed, while T10 and T11 failed the unchanged N-based 5% plateau gate in all six direction/response combinations. Strict host verification failed closed (`KernelWorkerStatus.ERROR`, no `DONE`); supplemental source-bound recomputation is diagnostic only. See [`issues/37_fd05_result.md`](issues/37_fd05_result.md) and its append-only evidence. No retry was run. FD, gradient, optimizer, topology, and shape-update qualification remain false; stop after this result.

**2026-10-01 FD-05 solver-free diagnosis (diagnostic only; registered T10/T11 FAIL unchanged):** Re-analysis of the 33 raw force histories shows fully steady flow (window std ≤ 2.5e-6 N) and a viscous-force offset that does not vanish as ε→0 (D1/D2 +ε and −ε both shift by about −0.002 to −0.003 N at ε = 0.5 mm, almost unchanged up to 10 mm). A numpy re-evaluation of the `measure()` normal on the flow_24 band finds 348 samples with φ≈0 and |∇φ|≈0 (all on ≥2 v17 node planes where source faces lie on the lattice); any perturbation reverses their normal independently of ε. flow_16 has 377 such samples, flow_32 has 0. The causal link to the force jump is a hypothesis, not qualified. See [`issues/37_fd05_solver_free_diagnosis.md`](issues/37_fd05_solver_free_diagnosis.md). FD-06 is not registered; it needs a user decision between normal regularization and breaking sample-plane/face-plane coincidence.

**2026-10-01 FD-06 (#37) result (supplements the FD-05 entries; diagnostic scope as stated):** FD-06 is the FD-05 contract with one change, body normal floor `n = g/max(|g|, 0.25)` (new `NormalFloorWaterLilyBody`; `WaterLilyBody.jl` untouched). The registered v17 / flow_24 kernel `/1` completed all 33 primals; T10/T11 still fail closed, but only 4 of 6 combinations miss the unchanged 5% plateau gate, now by 5.2–8.7% instead of FD-05's 83–150%, with ε-proportional pair signals; D2 drag and D0 downforce pass. Strict host verification failed closed (no `DONE`, as any gate failure implies); an independent raw-data recomputation matches the runner. FD oracle and all gradient/optimizer/topology/shape-update flags remain false. See [`issues/37_fd06_result.md`](issues/37_fd06_result.md). No retry; any further change is a new preregistered round.

Current gates and immediate sequence as of 2026-09-30 after the FD-05 terminal result:

1. **Retain the closed W3 owner-lifetime diagnosis.** Exact owner-lifetime
   diagnostic `/2` completed and passed host verification under immutable
   criteria round 3. The backing `owner.grid.phi` owner was collected at step 1
   in both natural-GC B replicas; each later developed non-finite forces while
   the retained A controls completed the horizon with finite, nonzero forces.
   This confirms an implementation lifetime defect, but not the exact W3 v4
   full-horizon all-zero symptom.
2. **W3 round 4 finite-box primal contract passed.** `OwnedV16Run` retains the
   owner, bodies and simulation through `run_primal`. Immutable criteria round
   4 SHA-256 is
   `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`,
   bound to source commit `ee6298e843e130b121d918ca9a321b707dcd4ae0`. Exact
   private kernel `/5` passed host verification for T0-T10. The supported
   claim is only the registered WaterLily finite-box primal contract.
3. **W4 v16 round 4 and canonical v17 round 1 finite-box sensitivity matrices
   passed.** The v16 round-4 record remains immutable and historical. W4 v17
   criteria SHA-256 is
   `5eceb62c17e347679cdadc88c68266e7fe00b392da40a8029ed3544a002e0f01`,
   tied to source commit `4c20787c1ab55ea45f98631e6e78ba6d5502a1a2` and W3
   v17 PASS. Private dataset version 1's five-file remote inventory was
   verified (inventory SHA-256
   `d3cbdfb385f443e5f8b413fc07675d79f319250b8e01bb617476041c651bc6fb`);
   exact private kernel `/1` completed. Strict host verification at the exact
   registered source commit passed T0-T10. The append-only result is
   [`kaggle_w4_v17_sensitivity_result_2026_09.json`](evidence/kaggle_w4_v17_sensitivity_result_2026_09.json),
   SHA-256 `25297c4646d048050974d6beccbb90ac672c910eeb558a99c1006226bdd59933`.
   All four cases passed the 2% stationarity gate. Flow16→24 changed total drag
   by `+0.103140 N` (`31.61%`) and downforce by `+0.077547 N` (`23.43%`);
   flow24→32 changed them by `+0.023684 N` (`6.77%`) and `+0.030232 N`
   (`8.37%`). Extending x+ by 1 m changed drag by `-0.000201 N` (`0.09%`)
   and downforce by `+0.000651 N` (`0.26%`). Pressure and viscous splits are
   recorded in the issue result and machine-readable evidence. These are
   sensitivity observations, not grid/domain convergence or physical
   aerodynamics.
4. **Keep broader qualification scoped.** The W3 v4 all-zero force root cause
   remains unresolved. Physical-profile equivalence, absolute downforce,
   grid/domain convergence, gradient/reverse, topology, optimizer and shape
   update remain false. Do not modify historical W3/W4 criteria or evidence.
5. **FD-05 ran once and is terminal FAIL** (see the 2026-09-30 FD-05 and
   2026-10-01 diagnosis checkpoints above). Do not retry FD-05 or edit its
   criteria. Before any FD-06 registration, the user selects the geometric
   remedy for the flat-normal samples, and a solver-free normal census plus a
   short CPU FD check must show ε-proportional behaviour.
6. **Repair the FD runner/host-verifier contract before a future authorized
   execution.** Round 5 is terminal failed evidence; preserve its immutable
   criteria, dataset v5, exact kernel `/4`, outputs, and diagnostics. The source
   fix must reconcile the six integrated pressure/viscous metrics between
   runner `outcome.json` and per-run summaries, and the host verifier must
   compare the agreed schema. Also repair the statically identified `evaluate()`
   name shadowing before it can be reached. Investigate the measured
   non-plateau directional responses under the unchanged registered 5% threshold;
   do not relabel them as qualified or edit rounds 1-5. Register any retry as a
   new immutable round with fresh 33-run outputs. Centered FD remains the
   permanent independent numerical gradient oracle.
7. **Select a production gradient backend** only after comparing candidate
   reverse AD, discrete-adjoint, or other methods against the qualified FD
   oracle. No production backend is selected or qualified.
8. **Take the first constrained SDF update** only after the primal, grid/domain,
   gradient, SDF-volume, and geometry hard gates pass.
9. **Qualify topology birth** as a separate mechanism. Register SDFTopologyPolicy
   v1 before Birth-0; the method (topological derivative, nucleation, a retained
   density/Brinkman proposer, or another explicit operator) is not selected.
10. **Run multi-step optimization** only after the one-step and topology gates
   pass, with reinitialization and geometry/connectivity/manufacturing gates
   applied to every accepted shape.
11. **Verify independently in Stage V** with body-fitted OpenFOAM and registered
    cross-fidelity/grid checks. Stage V remains a verifier, not the optimizer.

Post-FD-05 status remains deliberately scoped: the v17 / flow_24 FD-05 run is terminal FAIL under T10/T11, and strict host verification failed closed; its supplemental recomputation is diagnostic only. W3 v16 and v17 registered finite-box
primal contracts passed, and W4 v16 and v17 registered finite-box sensitivity
matrices passed (`w4_sensitivity_matrix_passed=true`). The W3 v4 all-zero force root-cause
mapping remains open. `physical_profile_qualified=false`,
`absolute_downforce_qualified=false`,
`grid_or_domain_convergence_qualified=false`,
`sdf_gradient_qualified=false`, `waterlily_reverse_cpu_qualified=false`,
`waterlily_reverse_cuda_qualified=false`, `topology_birth_qualified=false`,
and `shape_update_allowed=false`. W0/W1/sphere fixtures are capability evidence
only. The registered v16 Stage V profile, its two-domain comparison, and the
WaterLily W4 sensitivity matrix do not imply grid-independent or target-vehicle
downforce qualification.

Kaggle and Colab provide reproducible execution, exact source/runtime binding,
and evidence capture. They remain outside the solver/optimizer architecture.

### 2026-09-30 W4 canonical v17 exact kernel `/1` PASS

See [`issues/43_result.md`](issues/43_result.md) for the four-case force and
pressure/viscous tables, pairwise deltas, the diagnostic-only comparison with
W4 v16, and all artifact hashes. The registered result SHA-256 is
`25297c4646d048050974d6beccbb90ac672c910eeb558a99c1006226bdd59933`;
the strict host verifier passed T0-T10 at the registered source commit.

The normal verifier CLI's first attempt failed closed because the optional
`remote_inventory_sha256` parameter shadows the helper with the same name. The
unchanged verifier function was then run at the same source commit through an
external driver that supplied the existing hash helper as that parameter; the
full host recomputation passed. This invocation issue is preserved in
[`kaggle_w4_v17_sensitivity_host_cli_attempt_diagnostic_2026_09.json`](evidence/kaggle_w4_v17_sensitivity_host_cli_attempt_diagnostic_2026_09.json)
(SHA-256 `6a520b17db979021bca68f345bc5f99f71f4204f3eeda30aa7df58247c5e8508`)
and should be repaired before the verifier's next CLI use. No W4 source,
criteria, threshold, or output was changed after registration.

W4 v17 observed `flow16→flow24` and `flow24→flow32` response changes of
`31.61%/23.43%` and `6.77%/8.37%` for drag/downforce, respectively, and a
`0.09%/0.26%` change for the tested x+ domain extension. These support
resolution sensitivity in the registered cases, not convergence, absolute
force accuracy, or physical-profile qualification. `fd05_execution_authorized`
is false; FD-05 remained unregistered at the time of this W4 entry (superseded: FD-05 ran on 2026-09-30, see [`issues/37_fd05_result.md`](issues/37_fd05_result.md)).

### 2026-09-29 FD round-5 dataset v5 and exact kernel `/4` terminal FAIL

Round 5 kept the registered 3 directions, 30 perturbations, 33-run order, T4
backend, and numeric criteria unchanged. Exact private dataset version 5 was
remote-inventory verified and its mounted host-input preflight passed before
GPU discovery. The dataset verification record is
[`sdf_directional_fd_v16_dataset_round5_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round5_verification_2026_09.json),
SHA-256 `fe6159799cd23a4b44d83b5b89b616159a9f128cb34c0a373b0d0f4e981af55e`.
The source/criteria identity remained bound to commit
`a07bba2fd1dcf0d3d28b211eef58d91309a24a75` and criteria file SHA-256
`2aad32922b2746d9ee7b170b590673779e60f032b238c29d1bc7ca6b2779ee17`.

Exact private T4 kernel
`ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/4` ended in
`KernelWorkerStatus.ERROR`. Its log records 33/33 solver calls returned to
`tU/L >= 120`; `FD_JOB_DONE` is present and the outer `DONE` marker is absent.
The runner gates were T0-T5 PASS, T6-T7 FAIL, T8-T9 PASS, T10-T11 FAIL, and
runner T12 PASS. Aggregate solver wall time was `970.7994556427002 s` against
the registered `7200 s` limit. The strict exact-version host verifier failed
closed with `ValueError: FD Kaggle output has no DONE marker`; this is not a
host PASS.

Two append-only records separate terminal status from diagnostic recomputation:

- Strict kernel diagnostic
  [`sdf_directional_fd_v16_round5_kernel4_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round5_kernel4_diagnostic_2026_09.json),
  SHA-256 `0b49997661d059a23e4a3cde4952d5cc2a8176468bf3726c42758ff7a65322f8`.
- Raw CSV postmortem
  [`sdf_directional_fd_v16_round5_kernel4_postmortem_2026_09.json`](evidence/sdf_directional_fd_v16_round5_kernel4_postmortem_2026_09.json),
  SHA-256 `e17ae5eb9aabd1f29d92638756197dcafe5fd3b44802f84e93605ef7d1e56dcb`.

The diagnostic postmortem independently parsed all 33 force CSVs, checked all
87 output-manifest hashes, verified force-component closure and physics
identity for all runs, and recomputed 660 metrics that matched the runner's
`outcome.json`. All 14 recomputed fields present in each per-run summary also
matched. Each summary omits the same six integrated pressure/viscous fields
that `close_summary()` compares. In the pinned runner, that schema mismatch
makes the shared summary comparison false in both T6 and T7. Separately, the
registered response-resolution check found all five epsilons resolved for each
direction/response and stable signs over the selected first three epsilons,
but the maximum plateau deviations were:

| Direction | Drag derivative at selected epsilons (`N/m`) | Drag max deviation | Downforce derivative (`N/m`) | Downforce max deviation |
| --- | --- | ---: | --- | ---: |
| D0 interface offset | `-5.009319, -2.517892, -1.034651` | `98.95%` | `-0.197284, -0.071772, -0.020327` | `174.87%` |
| D1 filtered seed 11 | `4.265878, 2.030319, 0.688382` | `110.11%` | `2.095685, 1.075749, 0.465460` | `94.81%` |
| D2 filtered seed 2026 | `0.810939, 0.483772, 0.289585` | `67.63%` | `2.881399, 1.567029, 0.784102` | `83.88%` |

All six deviations exceed the unchanged 5% plateau limit, so T10 and T11
remain genuine measurement failures even after accounting for the summary
schema problem. The three repeated baselines were identical: drag
`0.3360177299176748 N`, downforce `0.3533732402215731 N`; each registered
noise floor is `1e-8 N`. Maximum relative half-window stationarity drift was
`3.25496e-5` for drag and `1.91534e-5` for downforce. These are diagnostics
for this registered finite-box run only.

Strict host verification stopped before raw-run verification. Static review
also found that its raw-summary check expects those six missing component
integrals, and `evaluate()` shadows the helper name `runner_metrics_match`
before the first call in that function. Neither static issue caused the
recorded missing-`DONE` rejection. Any repair or retry belongs to a new
immutable round; do not change criteria or qualification flags. Directional
FD, gradient, reverse, optimizer, topology, and shape update remain false;
`shape_update_allowed=false`.

### Historical Stage T/S/V execution record (retained; not current instructions)

The following dated campaign notes preserve their original reasoning and
measurements. Their roadmap and "next step" language is historical. Use the
current order above for all new work; do not infer a current Stage T campaign
or old Stage S execution from this record.


The historical Stage T/S/V architecture plan is
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md).
The historical post-PQ3.3 Stage T-to-Stage S execution detail is
[`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md).
Both retain their original Stage T -> Stage S -> Stage V record; neither is
current execution guidance. Follow the SDF-native order in section 11.

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

Historical execution order at that snapshot (superseded; do not use as the current roadmap):

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

- `docs/phase_plan.md`: only current roadmap, status, and execution order.
- `docs/problem_register_2026_09.md`: issue ledger; it does not set roadmap order.
- `docs/problem_contract_v2.md`: authoritative user problem schema.
- `docs/fixed_grid_data_contract_v2.md`: retained Stage T artifact schema; it
  does not define the canonical SDF design state.
- `docs/CFD_opt_sdf_SDF_native_handoff/00_HANDOFF_MASTER.md`: frozen supporting
  architecture rationale, subordinate to this roadmap.
- `docs/downforce_optimization_architecture_plan_2026_09.md` and
  `docs/stage_t_to_stage_s_bridge_plan_2026_09.md`: historical Stage T/S/V
  plans and evidence context; neither defines current execution order.
- `docs/kaggle_batch_runbook_2026_09.md`: execution procedure only.
- `docs/git_branching_strategy.md`: repository workflow.

If another document conflicts with this roadmap, this file wins and the
conflicting current-status or execution-order wording must be corrected. Keep
historical measurements, artifact interpretations, and their recorded scope.

The dated sections following this authority statement preserve the chronology
of implementation and evidence. Their local "next" notes are snapshots, not
current instructions, when they conflict with sections 1, 2, 4, or 11. The
current W3 owner-lifetime state is the latest dated entry below.

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

**Contract 2 — SDF sharp volume semantics (registered; P22-01 smooth primitive
implemented, shape update still gated).**  The Stage T density
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
limits are distinct and only the discrete rule is registered.  The P22-01
smooth primitive is specified in
[`sdf_native_smoothed_volume_contract_v1_2026_09.md`](sdf_native_smoothed_volume_contract_v1_2026_09.md):
it uses a one-sided cosine transition of width one design-grid cell and
reports the smooth value separately from sharp `V_phi`. This software
capability does not authorize a shape update or move the one-step gate. The
first SDF volume constraint is `V_phi <= V_phi_0` with `V_phi_0` **re-measured**
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
`src/cfd_sdf/design/volume_semantics.py` implements the sampled sharp
measure, reporting-only sharp over-volume (`max(0, V - V_lim)`), and the
separate P22-01 smooth value/gradient API with signed residual
`g_V = V_epsilon / V_phi_0 - 1`. This is a contract/software result only;
the finite-width one-sided smoothing underestimates sharp volume inside its
transition band, so `g_V <= 0` is not a conservative feasibility certificate
and cannot admit an optimizer step or shape update by itself. Acceptance must
independently require the registered sharp residual `V_phi - V_phi_0 <= 0`.
The result reports this signed sharp residual and positive violation separately.
The one-step gate still requires its full solver, gradient, volume, and
hard-gate preconditions.

**Contract 3 — SDFTopologyPolicy v1 contract registered; v16 binding
unresolved.** The immutable registration is
[`evidence/sdf_topology_policy_v1_2026_09.json`](evidence/sdf_topology_policy_v1_2026_09.json)
and the semantics are described in
[`sdf_topology_policy_v1_2026_09.md`](sdf_topology_policy_v1_2026_09.md).
It reuses the ProblemSpec v2 root groups, connectivity modes, and exact
minimum-feature lengths by content hash. Its component checker follows the
existing Stage S 26-neighbour convention; disconnected solids are allowed
only if every component has a designated root owner. Birth and whole-component
deletion are disabled, merge is conditional on all gates, and split is
conditional on every resulting component retaining a root owner. Forbidden,
fixed-solid, root, design, and minimum solid/void-width rules are explicit.

The v16 genesis state has empty `fixed_solid`, `forbidden` and `root` masks
(`solid_design_fraction = 1.0`), and the Stage S entry evidence records
`root_connectivity = not_applicable` for this candidate. The tracked Stage V
v16 ProblemSpec has root connectivity disabled and null minimum solid/void
widths; it is not a topology-policy source. The v16 genesis lineage has no
bound ProblemSpec v2 topology-policy digest, per-group root-mask provenance,
or registered minimum-feature values. Empty-root `not_applicable` is
unresolved, not evidence of a passing root rule. The registration records
these omissions and keeps `topology_birth_qualified=false`;
Birth-0 remains blocked. Per-group masks passed to the checker are external
registered evidence; the checker validates their IDs, shape, union with the
state root mask, and material occupancy, while callers must independently
verify the geometry-mask manifest provenance.

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
REGD   SDFTopologyPolicy v1 contract           (v16 root/feature binding OPEN)
BLOCKED topology birth                         (birth disabled; P23 unresolved)
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
- 2026-09-26 append-only hygiene before W1g:
  `evidence/sdf_native_w0b_driver_metadata_clarification_2026_09.json`
  (SHA-256 `801c5800ec1fe146991251217e2286d1f7975e0f5f779f04984f9a6330151505`)
  separates the three W0b version fields (nvidia-smi NVIDIA driver 580.82.07,
  `CUDA.driver_version()` 13.3.0, CUDA runtime 12.8.0); W0b verdict unchanged.
  `scripts/t4_backend_identity.py` (with pytest coverage) now fail-closes any
  future T4 job whose GPU/UUID/compute capability/versions or T4
  Project/Manifest hashes drift from the W0b record.

## 2026-09-27 Kaggle background GPU migration: K0 passed

The GPU execution route for the **next** SDF-native slices is now the private
Kaggle background script kernel, operated and collected through the Kaggle CLI
without an interactive notebook. The registered K0 contract is
[`evidence/kaggle_k0_criteria_2026_09.json`](evidence/kaggle_k0_criteria_2026_09.json)
(SHA-256 `5978460903fa193ec667c36ff86603d3cb7b067714d124c72094c94f2e3d30ac`).
Its outcome is
[`evidence/kaggle_k0_result_2026_09.json`](evidence/kaggle_k0_result_2026_09.json)
(SHA-256 `0f9176083c2cb2503101b7f69fd48ef9bc24f15f63d7d187e32bc8eef4cda719`);
the exact commands and retrieval check are in
[`kaggle_batch_runbook_2026_09.md`](kaggle_batch_runbook_2026_09.md).

K0-A--F passed: private version 1 completed a two-T4 background smoke;
version 2 instantiated the unchanged Julia 1.12.6 Project/Manifest, passed
CUDA/WaterLily smoke, then ran the original W2-T4a analytic job once on a
single T4 and concurrently in two Julia processes pinned to separate T4s.
All three runs reached 2246 steps and returned the same window-mean drag
`88.42577373189188` as the existing Colab reference, within the
pre-registered cross-backend relative bound `1e-4`; the dual processes
overlapped. CLI retrieval by exact version and SHA-256 verification passed
for 19 output files. This is execution and analytic-fixture numerical evidence,
not new aerodynamic or optimizer qualification.

The Kaggle GPU UUIDs changed between versions 1 and 2. The Colab W0b UUID
cannot be a Kaggle hard gate. The next authorized slice is a **new, immutable
Kaggle W1g backend/geometry criteria round**, registered before running the
existing GPU GridSDF fixture. Require hardware class, compute capability,
package/Manifest identity and per-run UUID recording; do not silently relax
the old Colab G9 or overwrite its evidence. After a passing W1g, continue
W2-T4b sampled sphere and W2b flow-grid ladder in that order. Colab evidence
remains the historical reference, not the active execution route.
`shape_update_allowed=false`, `sdf_gradient_qualified=false`, and no v16
optimization or topology work is authorized by this migration.

### 2026-09-27 Kaggle W1g round 1 retained as diagnostic

Kaggle private-kernel version 3 completed and reported G1–G9 true, but the
result is not accepted: its pinned fixture source checked finiteness only for
the x component of each normal while the registered G3 required the complete
normal vector. Preserve the exact version-3 download under
`work/kaggle_w1g_version3_diagnostic`; see
[`evidence/kaggle_w1g_round1_diagnostic_2026_09.json`](evidence/kaggle_w1g_round1_diagnostic_2026_09.json)
for the source, criteria, and output hashes. No W1g or downstream gate is
qualified by this run.

Before the next GPU measurement, the fixture was corrected to check all three
CPU/GPU normal components, then round-2 criteria were registered at
[`evidence/kaggle_w1g_criteria_2026_09_round2.json`](evidence/kaggle_w1g_criteria_2026_09_round2.json)
(SHA-256 `717053a2e4cb32d16cbbc2e3de2007371c1046f365f76a404cb166322adaadcb`).
The next authorized slice is a fresh private Kaggle W1g run pinned to source
`f01462a44bf8b8cbefb0f5f7977916be94687b6c`; only a verified pass proceeds to
W2-T4b. No bound was relaxed. `shape_update_allowed=false` and
`sdf_gradient_qualified=false` remain in force.

### 2026-09-27 Kaggle W1g round 2 passed

The private Kaggle kernel version 4 passed the preregistered W1g round 2 and
was independently verified after version-specific output retrieval. Evidence:
[`evidence/kaggle_w1g_round2_result_2026_09.json`](evidence/kaggle_w1g_round2_result_2026_09.json),
SHA-256 `bb233f72068b5c6681b9f3f9b4dba180b538f945f8283312fb521c24ac802eb8`.
All 11 manifested files passed SHA-256 checks; all nine gates passed over
200,012 probes. Maximum world-distance error was `3.5762787e-7 m` (bound
`1e-5 m`), maximum unit-normal error was `2.4211522e-7` (bound `1e-3`), and
there were zero sign violations among 199,321 gated probes. The kernel ran
source `f01462a44bf8b8cbefb0f5f7977916be94687b6c` on two Tesla T4s with driver
`580.159.04`, CUDA runtime `13.3.0`, Julia `1.12.6`, CUDA.jl `6.3.1`, and
WaterLily `1.8.0`; the selected ephemeral GPU UUID is recorded in the result.

This qualifies only the GPU GridSDF geometry bridge. It does not qualify a
WaterLily sampled-sphere CUDA step or force. At this W1g completion checkpoint,
the next slice is W2-T4b; before its GPU run, implement the smallest
sampled-sphere CUDA entry point and register its numerical/force criteria. The
current T4 job still enables only `analytic`, and no W2-T4b GPU criteria were
registered yet. Continue to keep
`shape_update_allowed=false`, `sdf_gradient_qualified=false`, and
`waterlily_reverse_cuda_qualified=false`.

### 2026-09-27 W2-T4b Kaggle sampled-sphere criteria registered

Before the first sampled-sphere CUDA measurement, the W2-T4b criteria were
registered at
[`evidence/kaggle_w2t4b_criteria_2026_09.json`](evidence/kaggle_w2t4b_criteria_2026_09.json),
SHA-256 `4617f98ca2cd95e60baba4c86d78f66aa8dff2261ff688e17f06a00ab06fc444`.
They pin implementation source `99c013a089b196975c190d413e4b4103ccbe755e`,
the existing W2a CPU sampled-sphere result, the W2-T4a analytic T4 result, the
Kaggle K0 result, the W1g round-2 result, and the T4 Project/Manifest. The
registered Kaggle sampled drag must agree with the W2a CPU sampled drag within
1%; its Cd must remain within the existing 10% W2a cross-geometry bound of the
T4 analytic reference. The sampled solver run has not started. Next: switch
the private Kaggle runner from the W1g fixture to the registered single-T4
W2-T4b job, add independent artifact verification, then submit a fresh
version. All gradient, reverse-mode, topology, and shape-update flags remain
false.

### 2026-09-27 W2-T4b version 5 retained as diagnostic; round 2 registered

Private Kaggle version 5 fetched source
`99c013a089b196975c190d413e4b4103ccbe755e`, completed the sampled-sphere
primal, and returned all 14 manifested files with locally verified hashes.
The worker exited `ERROR` because T9 failed; T0–T8, T10, and T11 passed. The
append-only diagnostic record is
[`evidence/kaggle_w2t4b_round1_diagnostic_2026_09.json`](evidence/kaggle_w2t4b_round1_diagnostic_2026_09.json),
SHA-256 `1836a4a7e33fa14c4c959560c712637e9706771ab13457715ad9b3753a623781`.
The exact download remains host-local under
`work/kaggle_w2t4b_version5/w2t4b`; it has no `DONE` marker and does not qualify
W2-T4b.

The failure is a reporting error, not a relaxation of T9 or evidence of a
changed grid. Version 5's phi and device-round-trip hashes both equal the
canonical phi hash, but its `phi_margin_m` was `0.15`. In the `GridSDF`
constructor, `margin_m` is the caller's configured gate; the measured
clearance is calculated separately with `zero_level_margin_m`. The job had
serialized the stored gate as the measurement. The byte-identical canonical
CPU fixture reports measured margin `0.19999998807907104 m` in the existing
W2a evidence. The job now reports measured `phi_margin_m` and configured
`phi_margin_gate_m` separately in source commit
`2da94a92ffb9af55dfc159068ace8f25c55c0e6c`.

Before another sampled-sphere GPU measurement, round-2 criteria were
registered at
[`evidence/kaggle_w2t4b_criteria_2026_09_round2.json`](evidence/kaggle_w2t4b_criteria_2026_09_round2.json),
SHA-256 `85bd5ba4f6ff0a13c7f0509b1ba86b74cfeb7bc346fc590b27a819ce3f228e66`.
Every numerical threshold is identical to round 1. T9 now also verifies the
reported gate field against its already registered `0.15 m` value while
checking the measured margin against the same expected value and tolerance.
Validation after the correction: the W2-T4b runner tests pass (`4 passed`),
Python compilation and Julia parser checks pass, and `git diff --check` passes.
The full suite reports `1043 passed, 37 failed, 4 skipped`; all 37 failures are
missing ignored `work/` campaign inputs in this fresh worktree, not failures in
the W2-T4b slice. The full suite limitation is the same missing-artifact class
seen on the earlier migration checkpoint.

At this registration checkpoint, the next action was to push the
runner/verifier update and independently verify a fresh Kaggle run. The
version-6 outcome is recorded below; reverse CUDA, gradients, topology, and
shape updates remain unauthorized.

### 2026-09-27 Kaggle W2-T4b round 2 passed

The private Kaggle kernel version 6 ran the repaired source
`2da94a92ffb9af55dfc159068ace8f25c55c0e6c` against immutable round-2 criteria
`85bd5ba4f6ff0a13c7f0509b1ba86b74cfeb7bc346fc590b27a819ce3f228e66`.
Kaggle reported T0–T11 true; after collecting version-specific outputs, the
host verifier independently checked all 13 manifested files, the `DONE`
marker, force CSV values/schema/hash, source and runner identity, preregistered
inputs, and recomputed T0–T12. All gates passed.

The measured zero-level clearance is `0.19999998807907104 m`; the configured
constructor gate is separately recorded as `0.15 m`. Both canonical phi and
device-round-trip hashes match
`393d5d7897885d71cda0902129a4aa3db561c59b1a85e8e221d55ce19fca4161`. The
window-mean drag is `88.2360589943`, with relative difference `2.86e-5` from
the registered W2a CPU sampled sphere. `Cd=0.8777003092`, with relative
difference `0.00215` from the analytic T4 reference; stationarity drift is
`2.65e-8` and relative lift/drag is `9.50e-6`. The run took `26.71 s`
after warm-up and sampled `54.1 MB` peak VRAM on one selected T4 from a
two-T4 inventory.

Append-only result:
[`evidence/kaggle_w2t4b_round2_result_2026_09.json`](evidence/kaggle_w2t4b_round2_result_2026_09.json),
SHA-256 `737ea3f6946b0eb3867902ea2b1db8bc6c92ccb8f45de30f664cd34dd2fb4b82`.
This closes W2-T4b only for the registered Re_D=100, Float32, 16-cells/D
sampled-sphere primal and its numerical agreement gates. It does not qualify
grid convergence, absolute/literature Cd, gradients, reverse CUDA, topology,
v16, optimizer readiness, or target aerodynamics. The next planned slice is
W2b, with a 16/24/32-cells/D flow-grid ladder; preregister that matrix and its
acceptance rules before any W2b GPU measurement.

### 2026-09-27 W2b six-case criteria registered; runner preflight

Before the first W2b solver measurement, the analytic/GridSDF matrix at 16,
24, and 32 cells/D and all numerical bounds were registered in
`evidence/kaggle_w2b_criteria_2026_09_round1.json` (SHA-256
`eab8213461d95a714910a2055a957d3614f1e257dcc79197f6068cd35a04b1bd`). The
round-1 criteria initially recorded the solver source as
`5482310d9778229fe692cdc6799c2e1c31cc9982`; version 7 later confirmed that
transcription was invalid, as recorded below. The 3% 24-to-32 cells/D response
is only the explicitly proposed PoC bound from the WaterLily deep dive; this
ladder is not registered as formal GCI or absolute-Cd qualification.

The standalone Kaggle runner and host verifier are ready for the next private
kernel version. Preflight review found two prerequisite file hashes
transcribed incorrectly in the runner, which would have failed T0 before any
case started. The values are corrected to match the immutable criteria. The
host verifier also recomputes reported force means and time-weighted Cd from
the retrieved CSV history, and both runner and verifier check the registered
one-thread identity. These checks do not change any registered CFD threshold.
Validation: `tests/test_kaggle_w2b.py` reports 4 passed; `compileall src tests`,
Python syntax checks, metadata JSON parsing, Julia parser, the criteria/input
hash checks, and `git diff --check` pass. The full suite reports 1047 passed,
37 failed, 4 skipped; all 37 failures are `FileNotFoundError` for pre-existing
ignored `work/` CFD fixtures absent from this fresh managed worktree. W2b was
submitted to its dedicated private Kaggle kernel
`ramhachi888/cfd-opt-sdf-w2b-flow-grid-ladder`, version 7, but failed in T0
before source checkout or solver execution: Kaggle's Git server refused a fetch
of the mistyped, nonexistent raw commit SHA. The immutable diagnostic is
`evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json` (SHA-256
`5df35a54ea1755ea12cf70b180618fdfc99700c6958334312a2b43e48f38ec91`). The
correct job commit is `548231050fc6ca22bc1c0394272564f81571dbbc`. Append-only
round-2 criteria are registered at
`evidence/kaggle_w2b_criteria_2026_09_round2.json` (SHA-256
`36c4cc138af4c30e022ddad9993798dfea6c8432cc72c4d216fb4cc569ce4cb5`); only
the source pin changed, with all fixture values, source-input hashes and
numerical thresholds equal to round 1. A depth-8 fetch of the advertised
feature branch followed by detached checkout of the corrected commit was
verified locally, including the registered job hash. This infrastructure
retry does not constitute a W2b solver measurement. After registering round 2,
all 20 registered source, Project, and Manifest file hashes also verified at
the pinned checkout. The 4 focused W2b tests, Python compile/syntax checks,
Julia parser, criteria and diagnostic sidecars, and `git diff --check` pass; the full suite was rerun
with the same 1047 passed, 37 missing-`work/` failures, and 4 skipped. The next
submission used the dedicated kernel's version 8. That run passed source
fetch, registered file hashes and package instantiation, then stopped in CUDA
smoke before a WaterLily solver step because runtime 12.8.0 differed from the
round-2 13.3.0 pin. See the round-3 checkpoint below. T4 selection, evidence
scope limits, and `shape_update_allowed=false` remain unchanged.

### 2026-09-27 W2b version 8 CUDA identity diagnostic; round 3 registered

Kaggle version 8 retrieved all 8 files in its failure manifest, and each
downloaded hash verifies. Source checkout at
`548231050fc6ca22bc1c0394272564f81571dbbc`, all 20 registered source/Project/
Manifest hashes, Julia 1.12.6 package instantiation, and the T4 CUDA, CuArray,
and KernelAbstractions smoke passed. The smoke observed CUDA driver API
`13.3.0` and CUDA runtime `12.8.0`; NVIDIA driver `580.159.04` and compute
capability `7.5.0` matched the registration. Version 8 stopped because round 2
had pinned CUDA runtime `13.3.0`. The append-only diagnostic is
`evidence/kaggle_w2b_version8_runtime_diagnostic_2026_09.json` (SHA-256
`08385ba971be70ad08fa73fa6d5f6587fa89b4137d3fded4c922ab15d6fc000d`). No
WaterLily simulation or solver step began.

Round 3 criteria are registered at
`evidence/kaggle_w2b_criteria_2026_09_round3.json` (SHA-256
`3573b903c2ff025db62cb184ba328f81c48da70f72d4393e3623bd3bbb58bf1c`). They
record the observed CUDA runtime `12.8.0` separately from driver API `13.3.0`.
The source commit, fixture, inputs, and every numerical threshold remain equal
to rounds 1 and 2. This registers the actual T4 runtime identity before the
first W2b solver measurement; it does not relax CFD acceptance. Next is
dedicated Kaggle kernel version 9. Before submission, the 4 focused W2b tests,
Python compilation/syntax and JSON checks, the criteria-chain and sidecar
hashes, all 8 version-8 output hashes and kernel-log hash, CUDA identity
binding, the Julia parser, and `git diff --check` passed. The full suite
reported 1047 passed, 37 failed, and 4 skipped. Re-running its 37 failures
confirmed they depend on ignored `work/` evidence artifacts absent from this
fresh managed worktree (including an STL load after its registered file is
missing); none is a W2b contract test. `shape_update_allowed=false` remains in
force.

### 2026-09-27 W2b version 9 partial-run diagnostic; round 4 registered

Kaggle version 9 fetched the round-3 source and verified the registered input
hashes, instantiated Julia dependencies, and passed the registered T4 CUDA
smoke. `analytic_16` then completed through `t_end=60.0000228882` with finite
fields and forces; its 561-sample force CSV reproduces the reported
time-weighted drag and Cd `0.879587436031` under host recomputation. Before
case 2, Julia stopped at the top-level `case_count += 1` with
`UndefVarError: case_count not defined in local scope`; no
`W2B_JOB_DONE` marker or remaining five cases exist. The exact 12 downloaded
output hashes and kernel log are retained in
`work/kaggle_w2b_version9/`; its append-only diagnostic is
`evidence/kaggle_w2b_version9_partial_failure_diagnostic_2026_09.json`
(SHA-256 `43ffa63058606638cd70f2bfbd18c68c8521a3fa67c81ad9bf03ebd8f7b3f35e`),
kernel-log SHA-256
`d12a2e07f65bdfe5c7a8811fa8fd5fbd4d29239a5790014abe045b7322a21ee3`. The
one-case response is diagnostic only; it does not satisfy any complete-matrix
claim and will not be reused as round-4 acceptance evidence.

The minimal source fix removes the top-level mutable counter and prints the
registered tuple length after the loop; source commit
`a29e282982a923e0a93ed31d3643e59c7ec6e42e`, job SHA-256
`cc351f6eb5f8ca8f2bc210100f82b46481335003a818d45466757f588ffd0440`. Julia
parser and a top-level execution of the corrected completion-marker pattern
passed. Append-only round-4 criteria are registered at
`evidence/kaggle_w2b_criteria_2026_09_round4.json` (SHA-256
`4b5789d4dcf2e9b79b10eb5e388d5a56951df5c835f0c993903527463b6a82d0`); only the
source pin and job hash change for the implementation fix. Backend identity,
fixture, all other inputs, and every numerical threshold remain the same as
round 3. The 5 focused W2b
tests, compile/syntax and JSON checks, criteria and diagnostic sidecars, all
12 version-9 output hashes, kernel-log hash, Julia parser and marker check,
and `git diff --check` passed. Full pytest reports 1048 passed, 37 failed,
and 4 skipped; rerunning the 37 confirms dependence on absent ignored `work/`
evidence artifacts. Next is dedicated Kaggle kernel version 10.
`shape_update_allowed=false` remains in force.

### 2026-09-27 W2b version 10 diagnostic; round 5 registered

Kaggle version 10 used the round-4 pin, passed the registered Tesla T4 CUDA
smoke, and completed `analytic_16` through `t_end=60.0000228882`. Its
561-sample force CSV reproduces the reported time-weighted drag and Cd
`0.8795874360307699` under host recomputation. `gridsdf_16` stopped during
`build_body`, before solver integration, because `zero_level_margin_m` was
defined in `CFDSDFWaterLily.GridSDFBody` but referenced unqualified from
`Main`. The 12 retrieved output hashes and kernel log were verified. The
append-only diagnostic is
`evidence/kaggle_w2b_version10_partial_failure_diagnostic_2026_09.json`
(SHA-256 `b2df282a40d776abeaf3ec63b086c4e297e6ffe1bafdd1de3b44d17a415f7cec`),
kernel-log SHA-256
`1ce4d69aec373c4d20e86937b2868b771f8a58390f1209289e2579481ba2ed97`. The
single completed case is diagnostic only and is not reused as acceptance
evidence; the other five cases and all T1-T12 gates remain incomplete.

The minimal fix qualifies the already-existing helper with
`CFDSDFWaterLily.GridSDFBody.zero_level_margin_m`; it changes neither the
helper nor fixture or solver settings. The source commit is
`65dbb015994e34669ec5d22f671b97128eaf87d2`, and the W2b job SHA-256 is
`eaedc02478ee1b966dce3ecb24bc9b8bb2b41223706f9ea1a71c070619c53e15`.
Append-only round-5 criteria were registered before measurement at
`evidence/kaggle_w2b_criteria_2026_09_round5.json` (SHA-256
`32c1fb8a80658a9ea37713c477c6ededcc0808d5cbb8bbd07d91a2b83ed1eb47`). Only
the source/job pin changes from round 4; runtime identity, fixture, all other
registered inputs, and every numerical threshold remain unchanged. Before
version 11, all 6 focused W2b tests, Python `compileall`, version-10 artifact
and kernel-log hashes, and `git diff --check` pass. Full pytest reports 1049
passed, 37 failed, and 4 skipped. Re-running only those 37 failures reproduces
the same missing ignored `work/` evidence paths (FileNotFoundError); none is a
W2b contract test. `shape_update_allowed=false` remains in force.

### 2026-09-27 W2b version 11 round 5 passed

The dedicated Kaggle T4 kernel completed all six registered cases at 16, 24,
and 32 cells per diameter. The exact version-11 download contains 23 files;
the host verifier confirmed each SHA-256, recomputed all force-window metrics
from the six raw CSVs, and passed T0-T13. The immutable result is
`evidence/kaggle_w2b_round5_result_2026_09.json` (SHA-256
`8edf0d36cb706e9f6862faf7ea44845b100c3213433e94ae334251c16c94cccc`), with
output-manifest SHA-256
`6c6c940605c76007f171bb8b5ffcf21b50d060ef9ec6b8cfd2514d258fd3bb87` and
Kaggle-log SHA-256
`cc65a38d805b74bf920f41371b542cc674ad919c3be9a7d413757796573cc44d`.
Analytic versus GridSDF time-weighted Cd differs by 0.209-0.243% at the three
resolutions. The 24-to-32 cells/D response is 1.903% analytic and 1.869%
GridSDF, within the preregistered 3% PoC candidate bound; both changes are
smaller than the corresponding 16-to-24 changes. This is the registered
sphere-fixture flow-grid response result, not a formal GCI/asymptotic-order or
absolute-Cd qualification. The target-vehicle, gradient, reverse-mode,
topology, and optimizer gates remain closed; `shape_update_allowed=false`.

The next roadmap gate is W3, the v16 WaterLily primal with its physical-profile
adapter. Before that solver measurement, register its separate input, geometry,
profile, force, runtime, and acceptance contracts against the canonical v16
state. Do not inherit W2b sphere thresholds as W3 acceptance criteria.

### 2026-09-27 Kaggle W3 version 1 stopped before the primal

W3 criteria were immutably registered at SHA-256
`3c54f3867d9eb9a5960b4c153bd1bffbfc4ca3a547456ecd51b340f808476de3`
against source commit `b46ef4270df0c76d91922b8f1b2455fabad62418`. The private
dataset reached `ready` and its five registered input files were listed. The
kernel's committed metadata includes that dataset as a source, but Kaggle
version 1 could not find `w3_v16_criteria.json` at the configured input path.
It stopped in criteria loading before GPU inventory, source checkout, Julia
setup, CUDA smoke, or any solver step. The exact diagnostic and downloaded
artifact hashes are recorded in
[`evidence/kaggle_w3_v16_primal_version1_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version1_diagnostic_2026_09.json).

This does not identify whether `/kaggle/input` was empty or the dataset was
available at another path. The unchanged kernel was pushed as version 2 after
the dataset reported ready. Until input loading and all preregistered gates
pass, W3 remains open and all qualification/update flags remain false.

## 2026-09-27 execution-order adjustment: W3/W4 qualification plus parallel reverse scratch

The architecture is unchanged. WaterLily is the optimization oracle; OpenFOAM
is the independent physical verifier. WaterLily 1.8.0's outer boundary is not
equivalent to the registered OpenFOAM per-patch freestream profile, so W3 will
not force the two solvers into an artificial identical problem. W3 retains its
registered profile and criteria.

W3 version 2 remains the next qualification run. Its current Kaggle state is
`QUEUED`; version 1 stopped at criteria loading before backend inventory or a
solver step. No W3 primal evidence exists yet. The mandatory formal order is:

1. W3: first v16 primal under the registered WaterLily profile.
2. W4: v16 flow-grid resolution and domain response under that same profile.
3. Local SDF perturbations and centered finite differences.
4. CPU reverse-gradient correctness against the registered finite differences.
5. GPU reverse/custom-adjoint Go/No-Go.
6. P22 SDF volume enforcement.
7. One constrained SDF update.
8. P23 topology policy.
9. Birth-0.

In parallel, a diagnostic-only Enzyme track has started on
`exp/w3-enzyme-reverse-spike`; it has no preregistered qualification criteria
and cannot open any formal gate. On Julia 1.12.6 / Enzyme 0.13.205, the tiny
sphere's primal runs on CPU. In both the current WaterLily 1.8.0 environment
and WaterLily PR #285 (`feed49f480b52047b4e9b8bfacdf3e4f8201106b`, version
1.6.1), reverse through the full time step stops at
`MixedDuplicated(Flow, Flow)`, even with static-body remeasurement disabled.
PR #285's isolated Poisson VJP does execute, but its directional derivative
was `1.0658` times the centered finite difference in this small test; this is
diagnostic only and the default Poisson solve tolerance is not a qualified
gradient setting. The WaterLily 1.8.0 project currently loads no Enzyme
extension.

The exact package pair Enzyme 0.13.205 + CUDA.jl 6.3.1 does not resolve under
Julia Pkg because the required GPUCompiler ranges do not intersect. The
separate scratch environment resolves with CUDA.jl 6.2.1 and PR #285; it does
not change the W2/W3 environment. A private T4 reverse-spike kernel was pushed
as version 1 and is currently `QUEUED`; its output is pending. Track commands
and package pins are in
[reverse-spike README at experiment commit 7aa9c61](https://github.com/ramhachi/CFD_opt_sdf/blob/7aa9c61/infra/kaggle/kernel_enzyme_reverse_spike/README.md).

These scratch findings do not qualify CPU or GPU reverse mode, SDF gradients,
or an optimizer update. Keep `waterlily_reverse_cuda_qualified=false`,
`sdf_gradient_qualified=false`, and `shape_update_allowed=false`. The existing
W2b sphere resolution result remains PoC-only; W4 stays ahead of formal FD.

### W4 v16 sensitivity design draft (not yet preregistered)

> **Superseded matrix note (2026-09-28):** The small-box dimensions in this
> historical draft predate the expanded-domain W3 round-4 PASS. Do not use
> them for registration. The current matrix is the post-round-4 matrix in
> `julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl` and the mutable criteria
> draft: `flow_16/24/32` use `100x48x36`, `150x72x54`, and `200x96x72` on
> `[-2.5,2.5] x [-1.2,1.2] x [-0.9,0.9] m`; `domain_xplus1m_16` uses
> `120x48x36` on `[-2.5,3.5] x [-1.2,1.2] x [-0.9,0.9] m`. The canonical
> design SDF remains unchanged. All four cases are reexecuted; the W3 baseline
> result is compared and reported separately.

Prepare the W4 matrix from the W3 profile while holding the canonical v16 phi,
its hashes, Re=80, physical force definitions, and dimensionless measurement
window fixed. Treat the canonical design lattice (`h=0.05 m`) and WaterLily
flow grid as separate inputs. The baseline physical flow box is
`[-1,2] x [-0.8,0.8] x [-0.6,0.6] m`; refine only the flow lattice using
`world_per_solver_m = 0.8 / N_D`, with `N_D` the cells per 0.8 m reference
length:

| Cells per reference length | Flow spacing | WaterLily cells |
| --- | --- | --- |
| 16 (W3 baseline) | 0.0500 m | 60 x 32 x 24 |
| 24 | 0.0333 m | 90 x 48 x 36 |
| 32 | 0.0250 m | 120 x 64 x 48 |

For every rung, set the solver reference length to `N_D` and recalculate
`nu_solver = (mu_physical / rho) * (dx / U_physical) / dx^2`, preserving
Re=80; this yields `nu_solver` 0.20, 0.30, and 0.40 for 16, 24, and 32 cells
per reference length. Keep `tU/L=[80,120]`, physical force integration, and
reference area fixed. The canonical SDF stays at 0.05 m spacing; only its
world-to-solver scale and the flow lattice change.

Add one independent domain case at 16 cells per reference length by extending
the +x outlet 3.5 m while keeping the canonical v16 SDF, inlet, side/top
bounds, ground, flow spacing, and native WaterLily boundary treatment fixed;
this gives a 130 x 32 x 24 flow grid. The 3.5 m extension is a sensitivity
perturbation in WaterLily's declared approximation, not an OpenFOAM-equivalence
claim or a transferred acceptance result. This minimum matrix estimates the
domain effect at the W3 resolution; if it is comparable to or larger than the
resolution response, add an extended-domain fine-grid case before FD to check
for a resolution/domain interaction. Reuse the passing W3 baseline only if
its registered gates pass. Register every W4 case, thresholds, runtime/VRAM
limits, and output contract before its first GPU measurement. Until those
criteria exist and W4 is independently verified, centered-FD execution stays
closed.

The W4 source/harness preparation after W3 round 4 now has structural owner
retention through the complete case solve using the existing `OwnedV16Run`
contract, and keeps its canonical device owner reachable across all four cases.
Each case computes exact endpoint-clipped trapezoidal means over `[80,100]`,
`[100,120]`, and `[80,120]`; host and Kaggle runner independently recompute
drag/downforce drift with the inherited `0.02` gate. This is the W3 round-4
stationarity precedent, ultimately inherited from the registered W2 sphere
convention; it was not chosen from W3 v3 or W4 measurements. This preparation
does not register criteria or authorize measurement by itself.

### 2026-09-28 live queue recheck and W4 preparation

After `git fetch origin codex/kaggle-batch-migration`, local HEAD and the
remote feature ref both resolved to `fe1552770e1e27ab49fedf44c53f5248b475d3f0`;
the worktree was clean before W4 edits. At 2026-09-27 15:23:35 UTC, the
version-bound Kaggle status command reported W3
`ramhachi888/cfd-opt-sdf-w3-v16-primal/2` as `QUEUED`; its logs were empty.
The reverse diagnostic
`ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1` was also `QUEUED` with empty
logs. Neither run has retrievable terminal output at this check, so no solver
start, reverse failure locus, or new measurement is inferred. W3 qualification
and all gradient/reverse/update flags remain false.
The local W3 dataset staged at
`work/kaggle_w3_v16_dataset_registered_3c54f386` is available: the criteria,
sidecar, canonical state NPZ, Fortran phi, and dataset manifest hashes match
their registrations: criteria `3c54f3867d9eb9a5960b4c153bd1bffbfc4ca3a547456ecd51b340f808476de3`,
sidecar `9268906c5c5aadab69be30ef579fdc6bdee51a2b7e1078302633202d51042c2f`,
state NPZ `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`,
Fortran phi `9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`,
and dataset manifest `f01176977c3c15cb93d5a164e0b7d166adbb750143ee49ac62114968575c868f`.

Unexecuted W3 source-review risk: the pinned Julia job calls names such as
`V16_PROFILE_POINT_SHAPE` and `v16_physical_profile_bodies` without module
qualification after including `V16PhysicalProfile.jl` into
`CFDSDFWaterLily`. That parent module declares no exports, and a Julia 1.12
namespace probe confirmed that plain `using .ModuleName` does not import
non-exported bindings. If version 2 reaches this job, an `UndefVarError` before
the first `sim_step!` is plausible. This is a source-level hypothesis, not an
observed failure; preserve the submitted v2 source/criteria and resolve it
from its exact terminal log before registering any changed-source retry.

W4 local preparation is tracked separately from W3's pinned source and
criteria. `julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl` encodes the fixed
four-case physical-grid matrix, and
`scripts/waterlily_w4_v16_sensitivity_job.jl` is the CUDA job draft. The
non-immutable criteria sketch is
[`evidence/w4_v16_sensitivity_criteria_draft_2026_09.json`](evidence/w4_v16_sensitivity_criteria_draft_2026_09.json);
it is explicitly not registered and cannot authorize a GPU run. It keeps the
canonical phi at 0.05 m while changing only the flow-grid spacing and box,
preserves Re=80 and the [80,120] tU/L window, and defines the extended-domain
follow-up rule by comparing the absolute physical-force response of the
domain and 24-to-32 resolution changes. Its integrity checks are not
grid/domain-convergence gates.

Local checks completed: Julia's standalone case builder returned the
registered dimensions `(60,32,24)`, `(90,48,36)`, `(120,64,48)`, and
`(130,32,24)` with solver viscosities `0.2`, `0.3`, `0.4`, and `0.2`; the
W4 job parsed with `Meta.parseall`; `git diff --check` passed. Loading the
local T4 Project failed because its CUDA package is not installed in this
managed worktree. No package installation or GPU run was attempted. W2b's
registered 32-grid GridSDF case took 327.4 s for its 60 tU/D window; this is
planning context only, not a runtime prediction or acceptance result for the
v16 W4 cases.

### 2026-09-28 W3 v2 recheck and W4 execution-shell preparation

Starting from branch `codex/kaggle-batch-migration` at
`62f5150de2b0c8ebe1c5f920492999569f4e7639`, the remote feature ref was fetched
and matched that commit. The exact-version Kaggle status recheck returned W3
`ramhachi888/cfd-opt-sdf-w3-v16-primal/2` as `QUEUED`; its logs were empty.
The reverse diagnostic
`ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1` also remained `QUEUED`. No
terminal output was available, so no W3 solver start/failure or reverse locus
is inferred. A second version-bound recheck after harness validation returned
the same statuses and empty logs. W3 v2 criteria, runner, and submitted source
remain unchanged.
All W3, physical-profile, gradient, reverse, topology, optimizer, and shape
update qualification flags remain false.

The W4 implementation shell is now present, still strictly unregistered:

- `infra/kaggle/kernel_w4/runner.py` discovers the staged criteria by filename
  under `/kaggle/input`, verifies the immutable criteria, dataset manifest,
  source and input hashes, bound host-verified W3 PASS evidence, canonical
  NPZ/raw phi identity and independently measured CPU SDF margin; it then
  verifies T4 inventory/smoke, records execution stage and per-case solver-step
  markers, and hashes the retrieved output inventory.
- `scripts/verify_kaggle_w4_v16.py` independently recomputes the exact-window
  force metrics, 3-axis pressure/viscous closure, drag/downforce projections,
  physical N conversion, backend/source identity and T0-T9 integrity gates.
  It also independently compares the domain and 24-to-32 resolution response
  and emits the registered extended-domain fine-grid follow-up decision.
- `scripts/waterlily_w4_v16_sensitivity_job.jl` now emits explicit solver
  progress markers and captures a terminal force sample at or after tU/L=120.
  Julia and host both linearly interpolate bracketing raw samples to exact 80
  and 120 endpoints before trapezoidal physical-time integration. The CSV
  retains pressure, viscous and total force components for x/y/z.
- `tests/test_kaggle_w4.py` contains eight contract tests. The mutable W4
  criteria draft now states the point shape, physical constants and endpoint
  sampling semantics, but remains `immutable:false` and
  `registered_before_computation:false`.
- `infra/kaggle/kernel_w4/kernel-metadata.json` is private T4 metadata for the
  future W4 dataset; it has not been submitted to Kaggle. No final W4 criteria
  or private dataset has been registered, and no W4 CFD measurement has been
  submitted.

Before eventual registration, the W3 prerequisite must bind both the immutable
W3 criteria and append-only PASS result. The result record must carry the exact
criteria SHA, version, source commit, `host_verification_passed: true`, and
observed backend identity including WaterLily's backend string. W4 criteria
must copy that backend identity exactly; the selected GPU UUID is recorded per
W4 run rather than assumed stable between Kaggle sessions.

Checks completed: eight focused W4 tests passed; project `.venv` Python
`compileall src tests`, Julia `Meta.parseall` for the W4 job, standalone W4
case-builder output, criteria and kernel-metadata JSON parsing, and
`git diff --check` passed. Full project pytest reported `1064 passed, 37
failed, 4 skipped`; rerunning only the 37 failures reproduced missing ignored
`work/` solver/evidence files (`FileNotFoundError`, with one missing-mesh-file
`ValueError`). None of the failures is a W4 test; the seven W4 tests present in
that full run passed. The current eight-test W4 suite also passes focused.
These checks validate the harness and available repository slice only; they do
not qualify or measure W4. After W3 reaches a terminal state,
collect its exact version-bound logs/output first and run its existing host
verifier before any W3 retry or W4 registration.

### 2026-09-28 W3 version 2 terminal diagnostic and bounded retry correction

The exact-version recheck and collection changed W3 version 2 from the
previously recorded `QUEUED` state to `KernelWorkerStatus.ERROR`. The Kaggle
2.2.4 command was bound to
`ramhachi888/cfd-opt-sdf-w3-v16-primal/2`. Its traceback ends in
`read_criteria()` with `registered W3 criteria missing from the attached
private dataset`. The downloaded `w3_v16/ERROR.txt` SHA is
`adb716bff1b5b48becb415440290c4be917d27e8509d35f68f42ad3644f821fb`; its
output `sha256.json` SHA is
`b42d39774c19a43c31d381c371956c944bc2b73b5d060d4d4a6070bed74c978e`, and the
version-bound Kaggle log SHA is
`2c669c91e88c0fbf1f53639c8270b0b4cbfaaa8823230edc0ab87a2f6c91e89a`. The
append-only record is
[`evidence/kaggle_w3_v16_primal_version2_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version2_diagnostic_2026_09.json).

The Kaggle dataset API currently reports the registered private input dataset
as `ready`, and its file listing includes `w3_v16_criteria.json` and its SHA
sidecar. The v2 runner did not record `/kaggle/input` inventory, so evidence
establishes a fixed-path lookup failure but cannot distinguish a differently
named mount directory from a runtime attachment failure. The traceback occurs
before GPU inventory, source fetch, Julia setup, CUDA smoke, and the Julia job;
solver started is false, solver steps are zero, and no T4 identity or force
measurement was captured. Version 2 therefore adds no W3 qualification.

The minimal next-round source correction is prepared but not submitted:

- W3 now discovers exactly one `w3_v16_criteria.json` under `/kaggle/input`,
  verifies its bound dataset ID, and saves the top-level input-mount inventory
  before lookup so a repeated infrastructure failure is attributable.
- The W3 Julia job now explicitly imports the non-exported profile constants
  and helper functions. This is a latent static risk found before the retry,
  not the observed version 2 failure.
- The W3 registrar can create append-only criteria rounds and accept the
  canonical state NPZ path from the already staged round-1 dataset. Round 2
  will bind the changed runner and job with the existing acceptance limits.
- No round-2 criteria or Kaggle dataset version has been registered, and no
  retry has been submitted yet.

The reverse diagnostic remains
`ramhachi888/cfd-opt-sdf-enzyme-reverse-spike/1` `QUEUED` with no new logs. W4
remains an unregistered sensitivity shell; its final criteria and dataset stay
gated on host-verified W3 PASS, and no W4 CFD measurement has been submitted.

Current checks: the focused W3/W4 contract set passes (19 tests), Python
`compileall src tests`, Julia parsing of both W3/W4 jobs, all four standalone
W4 case mappings, draft/diagnostic/metadata JSON parsing, and `git diff
--check`. The full repository run returned `1067 passed, 37 failed, 4
skipped`; rerunning the 37 failures reproduced missing ignored `work/`
artifacts (primarily `FileNotFoundError`, plus STL `ValueError`). The current
focused W3/W4 set also passes after adding the latest W4 staged-dataset
inventory check. These software checks do not constitute a GPU or physics
qualification.

### 2026-09-28 gated W3 retry and W4 registration tooling

Following the version-2 diagnostic above, the smallest W3 retry source change
is prepared on the local feature worktree. Criteria lookup now searches for
the unique `w3_v16_criteria.json` under `/kaggle/input` and records top-level
mount entries before lookup. The W3 Julia job explicitly imports the
non-exported profile symbols identified in source review. The registrar can
write a separate immutable criteria round and accept the already staged
round-1 NPZ path. A builder probe confirmed that round 2 preserves the exact
round-1 acceptance and measurement objects while binding the changed runner,
Julia job and host verifier hashes. The round has not yet been written or
submitted; no W3 threshold has changed.

The W3 host verifier now emits a PASS result object with exact criteria path
and SHA, source commit, kernel version, `host_verifier_sha256`, T0-T9 results,
and an observed backend identity including the WaterLily backend string. This
gives the future W4 registration a machine-checkable backend prerequisite.
W4 tooling is also prepared: the immutable-criteria registrar refuses W3
diagnostics or non-PASS output and binds the W3 criteria/result plus exact W4
source inputs; the dataset stager accepts only immutable criteria, verifies
canonical state and phi identities, and creates the registered private input
inventory. The W4 private dataset is not staged or uploaded, its draft remains
mutable, and no W4 run has been submitted.

Latest exact-version Kaggle check: W3 v2 remains `ERROR`; reverse spike v1
remains `QUEUED` and its logs are empty. Current focused W3/W4 contract tests
pass (21 tests); project Python `compileall`, Julia parsing for both jobs, W3
round-2 builder invariance probe, and `git diff --check` pass. The full suite
run immediately before the last two focused-test additions reported `1067
passed, 37 failed, 4 skipped`; the 37 failures were independently rerun and
all refer to missing ignored `work/` CFD files. All 21 current task-focused
tests pass. W3 round-2 criteria, the updated W3 dataset version, and kernel
version 3 remain unregistered/unsubmitted until the current source changes are
committed and pushed.

### 2026-09-28 final source-preparation verification

The W3 host verifier now independently requires the observed Julia archive
SHA-256 and `CUDA_VISIBLE_DEVICES` value in `fingerprint.json` to match the
immutable backend criteria before it can report T4 PASS. The result evidence
exports those observed values for exact W4 backend binding. The test fixture
uses the registered Julia archive identity. The W3/W4 focused contract set
passes (21 tests), Python compilation passes, both Julia jobs parse, the four
W4 case mappings match 60x32x24 / 90x48x36 / 120x64x48 / 130x32x24 with the
registered spacing and viscosity, the W4 draft remains mutable, and
`git diff --check` passes.

The W3 round-2 builder probe binds the new runner (`e84b4a50...`), host
verifier (`1e06142a...`), and Julia job (`c5da2f04...`) hashes while preserving
the original round-1 `acceptance` and `measurement` objects exactly. The full
repository suite completed with 1,070 passed, 37 failed, and 4 skipped; a
failure-only rerun reproduced the same 37 missing ignored `work/` artifacts
(including absent registered specs, checkpoints, meshes, and solver outputs).
None is in the W3/W4 focused set. The private v16 state NPZ needed to stage the
next W3 dataset is present under the worktree's ignored `work/` directory.

The latest exact-version Kaggle checks still show W3 v2 `ERROR` and reverse
spike v1 `QUEUED`; reverse v1 log retrieval and output download returned no
artifacts. W3 v2 remains an infrastructure diagnostic with zero solver steps.
No W3 round-2 criteria, dataset version, or retry kernel has been registered
or submitted yet. W4 remains unregistered and unrun pending exact host-verified
W3 PASS. OpenCode remains frozen; no OpenCode CLI or worker was used.

### 2026-09-28 W3 immutable round 2 submitted

The source preparation was committed and pushed as `abb0aee8351095d13a7166ea72556e0fff474242`.
W3 immutable criteria round 2 was generated only after that source commit, with
SHA-256
`0624c3498cddc40db0b21144cd818b3cd5837bbb8e735d3d84f8b78782a1fb2e`, then
committed and pushed as `9daaa55`. It preserves round 1 acceptance and
measurement criteria exactly; no threshold changed. The private input dataset
staging manifest binds the canonical NPZ
`3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`, C-order
phi `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`, and
Fortran phi
`9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`. After
Kaggle reported the dataset `ready`, the remote dataset was downloaded again;
its exact five-file inventory and all file hashes, including manifest SHA
`84ed2cde5bc22647592c74ecc81511e25f5d014774f93eb9afda5b2dbb821c12`, match
the local staged dataset.

The existing private W3 kernel was pushed to Kaggle as version 3 with
`NvidiaTeslaT4`, timeout 7200 seconds, and the registered round-2 dataset.
The first exact status check reports `KernelWorkerStatus.QUEUED`; no v3 logs or
solver result are available yet. Version 2 remains preserved as the
pre-solver criteria-path diagnostic. W4 remains blocked on v3 completing and
passing its exact-version host verifier; no W4 criteria, dataset, or GPU run
has been created.

### 2026-09-28 W3 version 3 completed as a T7 diagnostic; W4 remains blocked

This is the latest execution checkpoint and supersedes the preceding `QUEUED`
status without modifying any earlier evidence or immutable criteria.

- **Implemented:** the W3 input-discovery and Julia explicit-import source
  changes are bound to source commit
  `abb0aee8351095d13a7166ea72556e0fff474242`. The W4 case builder, solver
  harness, runner, host verifier, registrar/stager and contract tests remain
  implemented.
- **Submitted:** W3 kernel version 3 used immutable round-2 criteria SHA-256
  `0624c3498cddc40db0b21144cd818b3cd5837bbb8e735d3d84f8b78782a1fb2e` and the
  registered private dataset. Its terminal Kaggle worker status is
  `KernelWorkerStatus.ERROR`.
- **Measured:** the W3 primal reached 10,600 solver steps and `tU/L=120.0103759766`;
  it wrote 1,325 finite force rows and 441 samples in `[80,120]`. The registered
  time-weighted `+Fx` drag is `-23.45292019493048` solver units
  (`-0.05863230048732621 N`), so the preregistered positive-drag T7 gate is
  false. Wall time was `94.272037 s`, peak VRAM `7,132,408` bytes. No criterion,
  sign convention or threshold was changed after measurement.
- **Verified:** the append-only execution diagnostic
  [`evidence/kaggle_w3_v16_primal_version3_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version3_diagnostic_2026_09.json)
  has SHA-256 `fa278d11d7f2dfcde134671fea35580955d542447a51646864fc14ddad2fbe1f`.
  Its exact Kaggle log SHA-256 is
  `7e12fbec7c2c1e850fad9faad05f776162dbab5a3112f8ee28946d10e143a57a`; the
  downloaded output-manifest SHA is
  `305e829d315b88381843e4db010a2288d66dc8b0afe35914b56604c683bdd393` and all
  19 listed file hashes match. Registered source and dataset identities,
  canonical state/phi and round-trip hashes, CPU SDF margin, two-T4/Julia/CUDA/
  WaterLily identity, force-row arithmetic and time-weighted recomputation,
  recorded x-force component closure, completion, runtime, VRAM, and T0-T9
  values were independently inspected. T0-T6, T8, T9 are true; T7 is false.
  The success-only host verifier was not run against `ERROR.txt`/missing `DONE`,
  so `formal_host_verification_passed=false`. The v3 force CSV has separate
  pressure/viscous x components only; y/z component closure cannot be
  independently recomputed from these registered outputs.
- **Qualified:** no new qualification. In particular,
  `waterlily_v16_primal_qualified=false`,
  `physical_profile_qualified=false`, `grid_response_qualified=false`,
  `sdf_gradient_qualified=false`, `waterlily_reverse_cpu_qualified=false`,
  `waterlily_reverse_cuda_qualified=false`, `topology_birth_qualified=false`,
  and `shape_update_allowed=false`. No OpenFOAM equivalence, absolute-downforce,
  stationarity, grid/domain convergence, gradient, reverse, topology or
  optimizer claim follows.
- **Open:** diagnose the negative registered drag and any force-contract or
  fixture issue without changing round-2 criteria. The current evidence does
  not establish a source-code sign bug, so do not blindly flip force signs or
  repeat under the same criteria. Any justified source/measurement change
  needs a new immutable W3 round. W4 criteria and dataset are still
  unregistered, and no W4 measurement or formal FD measurement may begin until
  an exact W3 result passes its formal host verifier.

The diagnostic-only Enzyme reverse spike version 1 is now terminal: Kaggle
reports `KernelWorkerStatus.COMPLETE`, but its output contains `ERROR.txt`.
The append-only record is
[`evidence/kaggle_enzyme_reverse_spike_version1_diagnostic_2026_09.json`](evidence/kaggle_enzyme_reverse_spike_version1_diagnostic_2026_09.json)
(SHA-256 `9d969272bd3730b6d7cd5609a93bd3748d3fe9698dcf5597c3ee8def755e0e67`).
GPU inventory and Julia archive extraction succeeded; `Pkg.instantiate()` then
failed with `EROFS` while attempting to write a manifest under read-only
`/kaggle/src/julia`. This is a Julia setup/project-path failure. Package
resolution outcome is unverified, and no CUDA initialization or reverse test
was reached. It is not evidence of Enzyme/CUDA incompatibility or a reverse
failure; all reverse and gradient qualification flags remain false. If retried
for diagnosis, use a writable temporary copy of the pinned scratch project and
keep the CUDA.jl 6.2.1 scratch environment isolated from production W2/W3/W4.

### 2026-09-28 W3 expanded-domain round-3 preparation

This checkpoint preserves W3 v3 and reverse spike v1 as historical diagnostics.
The negative v3 `+Fx` drag is an acceptance failure, but it does not by itself
establish a force-sign implementation bug. The registered sign is unchanged.
The v3 first/second-half diagnostics were approximately drag `-8.73/-37.27`
and downforce `-196.19/-254.50` solver units, showing a strongly changing
response. Those measurements were not registered as a stationarity gate and
were not used to choose round 3's threshold.

- **Implemented:** W3 round-3 source uses the expanded WaterLily finite box
  `[-2.5,2.5] x [-1.2,1.2] x [-0.9,0.9] m`, flow origin
  `[-2.5,-1.2,-0.9] m`, and `100x48x36` cells at `dx=0.05 m`. It keeps the
  canonical design SDF at origin `[-1,-0.8,-0.6] m`, spacing `0.05 m`, and
  point shape `61x33x25`; the body map uses the flow origin while GridSDF keeps
  its canonical origin. Candidate world location and moving ground at the
  flow-domain bottom are covered by the Julia adapter test.
- **Implemented:** the W3 raw force CSV records total, pressure and viscous
  `Fx/Fy/Fz`, plus `drag=+Fx` and `downforce=-Fz`. Runner and host verifier
  independently enforce all-axis component closure, exact `[80,120]` endpoint
  interpolation/trapezoidal weighting, half-window integration and the hard
  stationarity gate. T10 inherits relative half-window drift `<=0.02` from the
  preregistered W2 sphere capability convention; this threshold was fixed
  independently of the W3 v3 measurement. Positive +x drag remains T7; no
  downforce sign/magnitude threshold was introduced.
- **Implemented:** round-3 fixture selection binds three existing Stage V
  records: original small-box failure on
  `outer_patch_backflow_and_pressure_disturbance`, expanded-box physical-profile
  pass, and same-candidate parent/child domain-convergence pass. The OpenFOAM
  values `Cd=1.16939914/1.17036295` and downforce `0.75655147/0.75735487` are
  retained solely as fixture-selection evidence, not WaterLily targets or an
  equivalence claim. The W2 round-5 sphere's positive-drag gate is also bound
  as a sign-convention precedent.
- **Implemented:** W4 remains mutable and unregistered, but its draft, case
  builder, solver, runner, host verifier and dataset preparer now use the
  expanded W3 baseline. The four cases are `100x48x36` at `dx=.05`,
  `150x72x54` at `dx=.033333...`, `200x96x72` at `dx=.025`, and the matched
  `[-2.5,3.5]x[-1.2,1.2]x[-.9,.9] m` domain case at `120x48x36`; all retain
  Re=80 and the canonical SDF unchanged. No W4 criteria are frozen and no W4
  measurement has run.
- **Implemented:** the diagnostic-only reverse spike runner copies its pinned
  Project/Manifest to writable `/kaggle/working`, checks the copied input
  hashes, then instantiates and runs from that copy. CUDA.jl 6.2.1, Enzyme and
  WaterLily PR #285 pins remain scratch-only and unchanged. This corrects v1's
  read-only-project EROFS failure without claiming a reverse result.
- **Registered:** no W3 round-3 criteria yet. The criteria may be frozen only
  after source, tests and draft are complete, committed and pushed, then
  regenerated from the clean exact source commit. W4 criteria remain
  unregistered and gated on a formally host-verified W3 PASS.
- **Submitted:** no W3 round-3 or reverse-spike v2 kernel has been submitted at
  this checkpoint.
- **Measured:** no W3 round-3, W4, or reverse-spike v2 measurement exists.
- **Verified:** 19 focused W3/W4 pytest tests pass; all 16 Julia adapter checks
  pass without advancing a solver step; W3/W4 Julia jobs parse; W4 case mapping
  yields the registered 100x48x36 / 150x72x54 / 200x96x72 / 120x48x36 grids at
  Re=80; Python compileall, W4-draft JSON parsing, round-3 criteria preview,
  and `git diff --check` pass. These are harness/contract checks only and do
  not qualify a solver or gradient.
- **Qualified:** W2 sphere primal/grid response remains qualified. W3 v3 remains
  unqualified (T7 false); W3 expanded-domain primal, physical profile,
  stationarity, grid response, gradient, CPU/GPU reverse, topology, optimizer
  and shape update remain unqualified.
- **Open:** complete requested syntax/tests and documentation, commit/push W3
  source before immutable round-3 registration, stage and remotely re-verify
  its private dataset, then submit the next exact W3 kernel version. Collect
  its version-bound log/output and host-verify all T0-T10. W4 may freeze only
  after that exact PASS; reverse spike v2 is a parallel diagnostic only.

### 2026-09-28 W3 expanded-domain round 3 submitted; exact run active

This checkpoint supersedes the round-3 preparation status above. The W3 v3
diagnostic, criteria, force sign, and measurement thresholds remain unchanged.

- **Implemented:** expanded-domain W3 runner/job, independent host verifier,
  round-3 contract tests, and the rebased mutable W4 shell are bound to source
  commit `5e985fa3395a01228c18910d96e09ecbc5497628`.
- **Registered:** immutable W3 round-3 criteria
  `docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json` has SHA-256
  `f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`. The
  corresponding private dataset is `ready`; its remote download has the same
  five-file inventory and hashes as the staged dataset. The manifest SHA-256
  is `17f0db110af5e989905e43b83ac7a003efe9b0587f127d5633b8910e7a0e8e9b`.
- **Submitted:** `ramhachi888/cfd-opt-sdf-w3-v16-primal/4` was pushed with a
  T4 and 7200-second timeout. The latest exact-version status is
  `KernelWorkerStatus.RUNNING`.
- **Measured:** no round-3 force or solver result has been recovered. The
  exact-version log retrieval is one newline byte (SHA-256
  `01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b`), and
  the output endpoint has not exposed an artifact. This is not evidence that
  Julia or the solver has started.
- **Verified:** round-3 registration check reproduces the criteria SHA;
  W3/W4 focused pytest passes 19 tests; Python `compileall` passes; the W3
  Julia adapter reports 16 checks passed without a solver step. The local
  `.venv` is absent from this managed worktree, so Python validation used the
  compatible interpreter at
  `/Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python`. These are
  contract/preflight checks, not primal measurement or host verification.
- **Qualified:** W2 sphere primal/grid response remain qualified. W3 v3
  remains a T7 diagnostic; W3 round 3, physical profile, stationarity, grid
  response, gradient, CPU/GPU reverse, topology, optimizer, and shape update
  remain unqualified. All W4 and formal FD gates remain closed.
- **Open:** continue polling only exact W3 version 4, retrieve its exact logs
  and output at terminal status, then run the registered host verifier. If any
  criterion fails, preserve an append-only diagnostic and do not proceed to
  W4. Diagnostic-only Enzyme reverse spike version 3 is independently
  `RUNNING`; it does not affect the qualification sequence.

### 2026-09-28 W3 round 3 version 4 terminal diagnostic; reverse spike version 3

This checkpoint supersedes the preceding “exact run active” checkpoint. Exact
W3 kernel version 4 is terminal `KernelWorkerStatus.ERROR`; reverse-spike
version 3 is terminal `KernelWorkerStatus.COMPLETE` with an internal
`ERROR.txt`. Both records remain diagnostic-only. W3 v3 evidence, registered
round-3 acceptance criteria, force projections, and thresholds are unchanged.

- **Implemented:** expanded-domain W3 source, runner, host verifier, and tests
  remain pinned to source commit
  `5e985fa3395a01228c18910d96e09ecbc5497628`. The registered fixture keeps
  flow origin `[-2.5,-1.2,-0.9] m`, dimensions `100x48x36`, and the canonical
  GridSDF origin `[-1.0,-0.8,-0.6] m`. The short host-side follow-up probe
  found the candidate interface on that mapped lattice and nonzero raw
  WaterLily forces in a 100-step CPU smoke. This does not establish the remote
  T4 body field or explain its zero force history.
- **Registered:** W3 round-3 criteria remain immutable at SHA-256
  `f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`; the
  five-file private dataset manifest SHA-256 remains
  `17f0db110af5e989905e43b83ac7a003efe9b0587f127d5633b8910e7a0e8e9b`. No
  threshold or force sign changed after measurement. Round-3 criteria SHA-256
  sidecar is `dcb5a919575f495d53e67cb950bd4f5a3326e85d9be5131e68c6c892d6a04b05`.
- **Submitted:** exact kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-primal/4` reached terminal
  `KernelWorkerStatus.ERROR`. The exact Kaggle log SHA-256 is
  `c1217626c24d099c850c79378c42771ed235ad392393d3b8098e51cee3544ab3`; the
  status response SHA-256 is
  `368662655f7cc049a9f53b4e73c2db1e674c8d6dc20fd026940603cbe300f115`.
- **Measured:** the T4 solver reached 3,841 steps and `tU/L=120.015625` with
  finite velocity and pressure. It recorded 481 force rows, including 160 in
  `[80,120]`; every total, pressure, and viscous `Fx/Fy/Fz` value is exactly
  signed zero. The raw CSV SHA-256 is
  `cf20d9ccf0c685500819801be9a6925346d15a2c881031a09cba599135ea8d9c`. The
  run used Julia 1.12.6, CUDA.jl 6.3.1, WaterLily 1.8.0 on
  `KernelAbstractions`, and the selected Tesla T4 UUID
  `GPU-3adff65b-4908-2981-c7a1-cfd5b5a5bd3c`; wall time was 31.033535 s and
  peak VRAM was 24,741,180 bytes. Exact-window drag/downforce and physical N
  projections recompute to zero. T10 evaluates true only because both
  half-window signals are zero; it is a degenerate stationarity diagnostic,
  not evidence of a stationary nonzero response.
- **Verified:** all 19 output artifacts match the version-4 SHA-256 manifest;
  the exact output-bundled log is the Kaggle log without its final newline.
  Remote dataset inventory and all five payload hashes match the staged
  dataset. The independent host diagnostic recomputation matches the runner
  gate map: T0-T6 true, T7 false, T8-T10 true. Formal success-only host
  verification did not pass: it refused the output because `ERROR.txt` is
  present and the required `DONE` marker is absent. The append-only primary
  diagnostic is
  [`kaggle_w3_v16_primal_version4_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version4_diagnostic_2026_09.json)
  (SHA-256 `1a22808509795a2735589743817fe2287014d7fbce7944492cd7e19bf4d4f51d`);
  the host CPU follow-up is
  [`kaggle_w3_v16_primal_version4_followup_diagnostic_2026_09.json`](evidence/kaggle_w3_v16_primal_version4_followup_diagnostic_2026_09.json)
  (SHA-256 `360f7b12f4090fe9447d9aa3b1a13cce9d3e7fc58998329cb1a9884faddf2ac5`).
  Validation: `python -m compileall src tests` passed; focused W3/W4 pytest
  passed 19 tests; both W3/W4 Julia jobs parsed; the W3 adapter test passed 16
  checks without solver steps; all three evidence JSON/sidecar pairs matched.
  The full pytest suite reported 1,068 passed, 37 failed, and 4 skipped; the
  failure tracebacks are `FileNotFoundError` for historical solver fixtures
  and state files under ignored `work/` paths absent from this managed
  worktree. The changed W3/W4 slice passes independently.
- **Qualified:** no new qualification. W2 sampled-sphere primal and W2b
  sphere grid-response evidence remain qualified. W3 round 3 remains
  unqualified: T7 failed the registered positive `+Fx` drag gate. The
  all-zero response does not establish a force-sign bug. It also does not
  establish physical-profile equivalence, absolute downforce correctness,
  grid/domain response, gradient, reverse mode, topology, optimizer, or a
  shape update. Fixture selection was separately audited against the existing
  Stage V evidence: the original `[-1,2]x[-0.8,0.8]x[-0.6,0.6] m` OpenFOAM
  box failed `outer_patch_backflow_and_pressure_disturbance` (inlet normalized
  pressure mean absolute disturbance `0.153719` against `0.05`, maximum
  `0.290554`); the registered expanded `[-2.5,2.5]x[-1.2,1.2]x[-0.9,0.9] m`
  box passed. Its same-candidate child with only the +x limit extended to
  `3.5 m` also passed the registered domain-pair gate: parent/child Cd
  `1.16939914/1.17036295`, downforce `0.75655147/0.75735487`, absolute
  downforce delta `0.00080340 <= 0.005`, and relative Cd delta
  `0.00082419 <= 0.02`. W2b round 5's `T4_drag_sign` gate and positive sampled
  sphere drag support the unchanged `drag=+Fx` convention. These independent
  records justify fixture/sign selection only; their OpenFOAM or sphere values
  are not WaterLily v16 targets, nor do they establish solver equivalence or
  absolute aerodynamics.
- **Reverse diagnostic:** version 3 fixed the prior read-only Julia project
  setup issue: the writable Project/Manifest copy hash-checked, instantiation
  completed, and CUDA initialized on two T4 devices. Basic Enzyme reverse of a
  CuArray then stopped with `EnzymeRuntimeActivityError` in
  `GPUArrays._mapreduce`; the continued WaterLily Flow construction failed
  compiling `llvm.nvvm.shfl.sync.down.f32` before `WATERLILY_PRIMAL_BEGIN`.
  No primal, Poisson VJP, or timestep reverse ran. Append-only evidence is
  [`kaggle_enzyme_reverse_spike_version3_diagnostic_2026_09.json`](evidence/kaggle_enzyme_reverse_spike_version3_diagnostic_2026_09.json)
  (SHA-256 `71323038d1ff5404ec23e5b695f6ea2102116ca7f9406a27074aaa2a87b41185`);
  this remains diagnostic-only and changed no production dependencies.
- **Open:** isolate why the remote T4 path returns an all-zero candidate-force
  history before another W3 qualification attempt. Any code or diagnostic
  change requires an append-only new immutable criteria round and matching
  dataset before another T4 measurement; keep T7 and stationarity thresholds
  unchanged unless a pre-measurement scientific basis justifies a new round.
  W4 criteria/dataset/measurement and formal FD remain blocked. Keep WaterLily
  as the optimization oracle and OpenFOAM as an independent physical verifier.

### 2026-09-28 W3 all-zero-force CUDA implementation diagnostic versions 1-2

These are private implementation diagnostics, separate from W3 qualification.
W3 round-3 criteria, positive `+Fx` drag gate, stationarity limit, old W3 v4
output, and qualification status were not changed.

- **Implemented:** local CPU reference and private T4 diagnostic kernel scan
  the expanded-domain candidate, ground, and union SDF; exercise representative
  CPU/CUDA body measurements; attempt one CPU/CUDA primal step and W2b sphere
  controls. Diagnostic-only source fixes are pinned per Kaggle kernel version.
  The version-3 source uses Julia's valid `1f-5` Float32 threshold, saves the
  representative CPU/CUDA rows before comparison, and fingerprints immutable
  input/backend/source identity before entering the diagnostic job.
- **Registered:** no new W3 qualification criteria. Diagnostic versions reuse
  round-3 input identity only and cannot set any qualification flag.
- **Submitted:** private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/1` and `/2` both reached
  terminal `KernelWorkerStatus.ERROR`; exact status, logs, outputs, and their
  SHA-256 manifests were retrieved version-bound.
- **Measured:** version 1 passed the T4 runtime/CUDA smoke, immutable input
  checks, and device round-trip, then stopped in representative probe-list
  construction at `UndefVarError: f` caused by a malformed diagnostic literal.
  Solver steps: 0. Version 2 again passed setup, matched canonical phi hashes
  and the `0.3499999939931499 m` margin, and constructed 10 candidate probes.
  The candidate CPU and CUDA `WaterLily.measure` calls returned; the following
  comparison stopped at `UndefVarError: f0` from `1e-5f0`. Probe matrices were
  not persisted in that version; no ground/union probe, full-grid scan,
  simulation construction, or solver step was reached. These findings do not
  explain the earlier full W3 run's all-zero force history.
- **Verified:** exact-version artifacts passed host output/input hash checks.
  Version-1 and version-2 evidence plus append-only correction records are
  [`v1`](evidence/kaggle_w3_v16_cuda_diagnostic_version1_2026_09.json),
  [`v1 stage correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version1_correction_2026_09.json),
  [`v2`](evidence/kaggle_w3_v16_cuda_diagnostic_version2_2026_09.json), and
  [`v2 source identity correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version2_identity_correction_2026_09.json).
  The corrections preserve the original records and clarify that v1's failing
  stage was probe construction and that v2 executed source commit
  `9a2f0950ef9d320f7290581203e7ca102d8ef2a6` with Julia job SHA-256
  `f731d86cab15b17aaded24b8dfdbb565b1ee24e359babf0af997c974e959b998`.
  The focused W3/W4/diagnostic slice passes 29 tests; Python compileall,
  diagnostic Julia parsing, and `git diff --check` pass.
- **Qualified:** nothing new. W3 v16 primal remains unqualified; the source of
  its zero-force T4 history is still open. Physical profile, grid response,
  gradient, reverse, topology, optimizer, and shape update remain unqualified
  or disallowed. W4 and formal FD remain blocked.
- **Open:** push the version-3 diagnostic source/runner/verifier changes, submit
  only the private minimal diagnostic kernel, and host-verify that exact
  version's result or failure checkpoint. Do not rerun full W3, freeze W4, or
  start formal FD based on these diagnostics. Keep all W3 gates and force
  projection fixed.

### 2026-09-28 W3 all-zero-force CUDA implementation diagnostic version 3

This checkpoint supersedes the versions 1-2 diagnostic progress entry. It
does not change the immutable W3 round-3 criteria or qualify the W3 primal.

- **Implemented:** the private diagnostic job scans all 172,800 pressure-cell
  centers for candidate, ground, and combined SDFs on CPU and T4 CUDA; runs
  solver-free body measurements; constructs v16 CPU/CUDA simulations; takes
  one primal step on each; and runs a one-step sphere control. The owner of the
  non-owning CUDA SDF view is explicitly rooted during this diagnostic. The
  host verifier now returns geometry-contract checks, accepts the observed
  Float32 representation of pinned flow origin/spacing within representation
  roundoff, maps the report's CUDA naming correctly, and uses a diagnostic
  recomputation tolerance of `5e-8 m` for CPU/CUDA distance arithmetic.
- **Registered:** no new qualification criteria or thresholds. W3 round-3
  criteria remain SHA-256
  `f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2`.
- **Submitted:** private diagnostic kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/3` reached
  `KernelWorkerStatus.COMPLETE`. Exact status SHA-256 is
  `e728d1ce05074fee394cf33e6f060f6a09a02868dbd21c289b90701744c0f763`; exact
  Kaggle log SHA-256 is
  `4113bfa739c118ec231681e27a2fed95388e2b0f25aef1f720f37c35ede2d216`.
- **Measured:** runtime was Julia 1.12.6, CUDA.jl 6.3.1, CUDA runtime 12.8.0,
  CUDA driver API 13.3.0, NVIDIA driver 580.159.04, WaterLily 1.8.0 on
  `KernelAbstractions`; the selected device was a Tesla T4
  (`GPU-d5fd398c-ae72-ef9e-54ae-c229cf2ea025`). The expanded flow grid was
  `100x48x36`, with flow origin `[-2.5,-1.2,-0.9] m`; the unchanged canonical
  SDF remained `61x33x25` at `[-1,-0.8,-0.6] m`. Candidate CPU/CUDA negative
  cell counts were `1009/1009`, support counts (`|d|<=1` solver unit) were
  `2481/2476`, and distance sign mismatches outside the zero band were zero.
  The maximum CPU/CUDA candidate distance difference was
  `4.76837158203125e-7 m`. The ground scan matched its registered plane.
  At initial state both candidate force snapshots were zero; after one step,
  CPU and CUDA repository-projected drag were `3485.0465` and `3485.1330`
  solver units, respectively. Raw total force vectors were
  `[-3485.0465,-22.4661,4627.1703]` and
  `[-3485.1330,-22.2581,4627.4747]`; pressure-plus-viscous closure held on all
  three axes to floating-point roundoff. The CUDA candidate normal comparison
  still has a maximum vector error of `1.338` against the independent NumPy
  reference; pointwise normal/gradient parity is not qualified by this scan.
- **Verified:** the exact output manifest, inputs, source/job/runner identity,
  full lattice CSV, host-recomputed SDF statistics, force closure, and exact
  Kaggle status/log were independently checked. The append-only host record is
  [`v3 diagnostic`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_2026_09.json);
  the interpretation/source-audit supplement is
  [`v3 interpretation`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_interpretation_2026_09.json).
  Focused W3/W4/diagnostic tests pass (30), Python compileall and py_compile
  pass, the diagnostic Julia job parses, and `git diff --check` passes. The
  repository-wide pytest run reports 1,079 passed, 37 failed, and 4 skipped;
  the inspected failures are `FileNotFoundError` for historical, ignored
  `work/` artifacts absent from this managed worktree. The focused changed
  slice passes.
- **Interpretation:** the full W3 v4 T4 run still completed 3,841 steps at
  `tU/L=120.015625` with every total, pressure, and viscous force component
  exactly zero, and T7 failed. The diagnostic's nonzero one-step CUDA force
  shows that the candidate geometry and force path can produce a nonzero
  response when the CUDA grid owner remains rooted. The pinned W3 source
  creates `device_owner`, derives a non-owning `CuDeviceArray` view, builds the
  bodies/simulation, then does not explicitly preserve the owner during
  `run_primal`; the adapter contract says the owner must remain live while a
  kernel uses that view. Premature owner collection is therefore a strong
  source-level hypothesis, but no forced-GC retained/unrooted A/B has yet
  confirmed it. The full-horizon zero-force cause remains unlocalized.
- **Qualified:** nothing new. W3 remains unqualified; physical profile, grid
  response, gradient, CPU/GPU reverse, topology, optimizer, and shape update
  remain false. W4 and formal FD remain blocked. Force sign and registered
  thresholds remain unchanged.
- **Open:** the next minimum experiment is a diagnostic-only T4 A/B with the
  exact same round-3 fixture and backend: one arm explicitly roots the owner
  through body measurement and a tiny number of steps; the other constructs
  view-backed objects in a helper scope, forces full GC before measurement,
  and records a weak reference to the owner. Record whether collection
  occurred, fixed-point/full-grid geometry summaries, fields, force components,
  and exact identities. Treat a difference as support for the hypothesis
  only if it repeats and coincides with confirmed owner collection. Do not
  launch another full W3, W4, or FD measurement before that diagnosis and a
  new immutable qualification round if source changes.

### 2026-09-28 W3 diagnostic force-projection clarification

The diagnostic CSV names retain the unmodified WaterLily API force as
`waterlily_*_force_raw`; these components have the opposite sign from the
repository's force-on-body vectors. The registered W3 job negates the
WaterLily pressure and viscous vectors first, then applies
`drag=+Fx_body_total` and `downforce=-Fz_body_total`. The diagnostic snapshot
stores raw WaterLily force, so its equivalent projected values are
`drag=-Fx_WaterLily_raw` and `downforce=+Fz_WaterLily_raw`. The W2b
`pressure_force_on_body`/`viscous_force_on_body` wrappers use the same negation.

Therefore the v3 one-step projected drag of `3485.0465/3485.1330` solver units
on CPU/CUDA is consistent with the registered body-force sign convention. It
is a valid one-step implementation observation, but it is not an exact-window
time-weighted result, a stationarity result, or W3 qualification. This
clarification is recorded append-only in
[`v3 force-projection correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version3_force_projection_correction_2026_09.json).
No force sign, threshold, measurement, or qualification state changed. The
owner-lifetime hypothesis remains unconfirmed and the next minimum test stays
the retained-versus-forced-GC T4 A/B described above.

### 2026-09-28 owner-lifetime diagnostic kernel version 4: runner workspace error

This entry supersedes the preceding `RUNNING` checkpoint for exact kernel
version 4. It preserves both that version's original evidence and a
host-verification correction; neither is a W3 or owner-lifetime pass.

- **Implemented:** version 4 successfully passed dataset/input identity,
  Julia 1.12.6 package setup, CUDA smoke, T4 inventory, canonical SDF device
  round-trip, CPU/CUDA geometry scan, and the existing one-step W3 diagnostic.
  The owner-lifetime A/C/B process sequence did not start. `run_owner_lifetime_arms`
  attempted to launch A only after leaving the `TemporaryDirectory` that held
  Julia and the fetched project. A minimal runner correction now keeps base
  output validation and all four arm subprocesses within that directory's
  lifetime. The host verifier accepts an explicit exact-version runner source
  and distinguishes this wrapper failure from Julia/WaterLily failures.
- **Registered:** round-2 owner criteria remain byte-identical and unchanged:
  SHA-256
  `8530e084ed33807b67b175f2234266cae34f74ccf510ea31130a199f30a0bec9`.
  The v4 failure occurred before any owner arm measurement, so no owner
  observation or acceptance threshold was changed.
- **Submitted:** private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/4` reached
  `KernelWorkerStatus.ERROR`. T4 identity was 2 × Tesla T4, selected UUID
  `GPU-7685ef41-8af8-4f82-39ba-0609f744d9ba`, Julia 1.12.6, CUDA.jl 6.3.1,
  runtime 12.8.0, driver API 13.3.0, and WaterLily 1.8.0.
- **Measured:** the separate base diagnostic completed one v16 CUDA step at
  `t=0.015625`; its projected candidate drag was `3485.132996` solver units
  after that step. This reproduces a tiny one-step observation only. Owner A
  was not spawned, so owner solver steps are zero and there are no A/C/B
  geometry, field, force, GC, or normal-comparison measurements.
- **Verified:** the first append-only record is
  [`version 4 diagnostic`](evidence/kaggle_w3_v16_cuda_diagnostic_version4_2026_09.json),
  SHA-256
  `c3bf3b4e64503996cde1e138d56dbe448b0fccef03cbe945d687f9c653a54480`.
  Its correction is
  [`version 4 runner correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version4_runner_correction_2026_09.json),
  SHA-256
  `5928c8388ae455376a1ed055802f86b4a307ccf238b05acc0e8201b104d6766c`.
  The correction verified source/input/backend identity and the complete
  output manifest, then classified the exact exception as
  `owner_lifetime_runner_workspace_expired` at Julia process launch before A.
  Kaggle log SHA-256 is
  `cb474ff4890348dd2f15de7d2a7506c5b127030f838b0416e4868642948d8862`,
  status SHA-256 is
  `b0fc55f87e13b86a9fb93993640d490630b7ee3606d09b5f4ef2970e757344c7`,
  output SHA-manifest SHA-256 is
  `a2984ba02b056999b1a73bc3ec26ac835d14db91acb7dd9fe1644987cf4f8488`, and
  `ERROR.txt` SHA-256 is
  `f3dc9101d5880c49027a197e9d330befb4a5f6cd34f94e67846dfceed2127575`.
  The exact uploaded v4 runner is recovered from commit `6fe9752` and has SHA-256
  `609a86f40424a83ab4ed870d1fe2c321c9c0994ff5e27077e821c01457f36378`.
  The overall owner diagnostic is incomplete and its hypothesis remains
  unresolved.
- **Qualified:** nothing. W3 v4 remains failed/unqualified; no W3 gate,
  physical profile, grid response, gradient, reverse, topology, optimizer, or
  shape-update status changed. The v4 one-step sample does not establish a
  cause for the full W3 v4 all-zero force history.
- **Open:** submit a new diagnostic kernel version with only the workspace
  lifetime correction and the host verifier update. Reuse the unchanged
  registered owner criteria, then retrieve exact logs/output and verify the
  A/C controls plus both B collection brackets. No production fix or new W3
  qualification run is authorized by version 4.

### 2026-09-28 owner-lifetime diagnostic version 5 submitted

- **Implemented:** runner workspace lifetime correction, exact runner-source
  override for historical host verification, and a regression test for the
  version-4 missing Julia executable classification are committed at
  `a5022c8`. Runner SHA-256:
  `fbecc7093ef3fe05ca637a0bf4e4d5e993bd4beca29087b2ebd6ef02c8842ee1`.
- **Registered:** unchanged criteria round 2, SHA-256
  `8530e084ed33807b67b175f2234266cae34f74ccf510ea31130a199f30a0bec9`, and
  unchanged owner Julia job SHA
  `7fa98a26105f1a2938ab85550931a22cb1020bd27d687d6f4dedb99c1b5572ea`.
- **Submitted:** private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5` was submitted with T4.
  Its first exact-version check returned `KernelWorkerStatus.RUNNING`.
- **Measured:** version 5 is not terminal; no owner arm result has been
  recovered.
- **Verified:** local focused W3/W4/diagnostic slice passes 38 tests; Python
  compileall/py_compile, Julia syntax parsing, criteria/evidence JSON and
  sidecar checks, and `git diff --check` pass. Remote host verification remains
  open.
- **Qualified:** nothing new. All qualification flags remain false.
- **Open:** retrieve only exact version 5 status, logs, and outputs after it
  reaches a terminal state; verify A/C agreement, actual owner collection in
  both B replicates, geometry/field/force differences, and exception class.

### 2026-09-28 owner-lifetime diagnostic version 5 submitted

- **Implemented:** runner workspace lifetime correction, exact runner-source
  override for historical host verification, and a regression test for the
  version-4 missing Julia executable classification are committed at
  `a5022c8`. Runner SHA-256:
  `fbecc7093ef3fe05ca637a0bf4e4d5e993bd4beca29087b2ebd6ef02c8842ee1`.
- **Registered:** unchanged criteria round 2, SHA-256
  `8530e084ed33807b67b175f2234266cae34f74ccf510ea31130a199f30a0bec9`, and
  unchanged owner Julia job SHA
  `7fa98a26105f1a2938ab85550931a22cb1020bd27d687d6f4dedb99c1b5572ea`.
- **Submitted:** private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5` was submitted with T4.
  Its first exact-version check returned `KernelWorkerStatus.RUNNING`.
- **Measured:** version 5 is not terminal; no owner arm result has been
  recovered.
- **Verified:** local focused W3/W4/diagnostic slice passes 38 tests; Python
  compileall/py_compile, Julia syntax parsing, criteria/evidence JSON and
  sidecar checks, and `git diff --check` pass. Remote host verification remains
  open.
- **Qualified:** nothing new. All qualification flags remain false.
- **Open:** retrieve only exact version 5 status, logs, and outputs after it
  reaches a terminal state; verify A/C agreement, actual owner collection in
  both B replicates, geometry/field/force differences, and exception class.

### 2026-09-28 diagnostic-only CUDA owner-lifetime A/B/C round 2 prepared

This controlled implementation diagnostic follows the exact W3 round-3
fixture and existing private W3 CUDA diagnostic kernel. It does not alter the
W3 production source, round-3 criteria, force projection, T7/T10 gates, or any
qualification flag.

- **Implemented:** `scripts/waterlily_w3_v16_cuda_owner_lifetime_job.jl`
  compares explicitly retained owner (A), structurally owned components (C),
  and two helper-scoped unrooted replicas (B1/B2), each in a separate Julia
  process. Every arm records forced-GC/WeakRef checkpoints, representative
  probes, full 172,800-point candidate/combined CPU and CUDA geometry scans,
  simulation fields, raw pressure/viscous/total force, body-force projections,
  and two primal steps. The Kaggle runner and host verifier now capture and
  independently check the arm artifacts and failure classes. Focused tests
  cover immutable criteria/job hashes, owner/GC schema, force closure and
  projections, A/C/B comparison, binary artifact order/hash, process failure
  classification, and append-only evidence.
- **Registered:** immutable diagnostic-only criteria round 2 is
  [`kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round2.json`](evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round2.json),
  SHA-256
  `8530e084ed33807b67b175f2234266cae34f74ccf510ea31130a199f30a0bec9`; its
  sidecar SHA-256 is
  `ef9df9f54f4408783a243f3b92f014722a3131da7bccc86f5b34b24100538b43`. It
  supersedes round 1 before any measurement because a representative positive
  phi probe differed from the v3-compatible minimum-positive selection. The
  fixture, arms, GC procedure, tolerances, and causal decision rules did not
  change. Owner job SHA-256 is
  `7fa98a26105f1a2938ab85550931a22cb1020bd27d687d6f4dedb99c1b5572ea`.
- **Submitted:** private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/4` was submitted with the
  NvidiaTeslaT4 accelerator after source commit
  `885ae7558012da43e6310e2ffb04db4230150f5b` was pushed. At this checkpoint
  its exact version-bound Kaggle status is `KernelWorkerStatus.RUNNING`. The
  uploaded runner SHA-256 is
  `609a86f40424a83ab4ed870d1fe2c321c9c0994ff5e27077e821c01457f36378`.
- **Measured:** no terminal owner-lifetime measurements are available yet.
  Local Julia syntax parsing,
  Python `compileall`, Python `py_compile`, focused owner diagnostic tests
  (18 passed), and `git diff --check` pass. The related W3/W4/diagnostic
  slice passes 37 tests. The required repository-wide run reports 1,086
  passed, 37 failed, and 4 skipped; the reported failures are attempts to read
  ignored historical `work/` artifacts absent from this managed worktree
  (including Stage-S and Stage-V fixtures), not failures in the changed slice.
  Remote CUDA execution is still required.
- **Verified:** no remote owner-lifetime result exists yet. The host verifier
  records an unresolved result if the owner experiment was not reached and
  rejects unregistered artifact identities or a non-append-only evidence
  target.
- **Qualified:** nothing. This experiment can only support, weaken, or leave
  unresolved the implementation-layer owner-lifetime hypothesis. It cannot
  qualify W3 primal, physical profile, grid response, gradients, reverse mode,
  topology, optimizer, or shape update.
- **Open:** submit and collect one exact private Kaggle kernel version, then
  host-verify its exact status, logs, output manifest, runner/job/criteria
  identities, A/C agreement, both B collection brackets, geometry, fields,
  forces, and process outcomes. Preserve failed outputs and append a
  diagnostic result. Do not modify the production W3 path or restart full W3,
  W4, or formal FD from this scratch experiment.

### 2026-09-28 owner-lifetime diagnostic version 5 terminal diagnosis and round 3

- **Implemented:** host failure classification now reads each exact arm report
  and distinguishes the repeated missing-import failure from a CUDA/lifetime
  arm failure. The owner job uses explicit imports for
  `v16_physical_profile_bodies` and
  `build_v16_physical_profile_simulation`; the W3 production job is unchanged.
- **Registered:** immutable owner-lifetime criteria round 3 was frozen before
  another measurement at
  [`kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round3.json`](evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round3.json),
  SHA-256
  `906fda6a3991d7a37ea29f50ccc851f3788cde9a6bb90dfcc5b11279fb3f4274`; sidecar
  SHA-256
  `23033b9601f6f38932e08c3c5e994651f71559da6b0966f7e0bc4172fe166c03`. It
  binds owner job SHA-256
  `b952aae000f6a2047b050ca5d46bd8fdd1a5c320ebc222bd380b70c0924c8cac` and
  supersedes round 2 only because version 5 reached no owner/body construction,
  GC bracket, geometry/field/force measurement, or owner primal step. All
  fixture values, arm order, GC procedure, tolerances, sample points and
  causal rules remain identical.
- **Submitted:** version 5 of the private owner-lifetime kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/5` terminated as
  `KernelWorkerStatus.ERROR`. Exact runner SHA-256 was
  `fbecc7093ef3fe05ca637a0bf4e4d5e993bd4beca29087b2ebd6ef02c8842ee1` and the
  runner fetched source commit `885ae7558012da43e6310e2ffb04db4230150f5b`.
- **Measured:** the base CUDA diagnostic reached one v16 step. Each of A, C,
  B1 and B2 launched a separate Julia process, but all four stopped at
  `canonical_input_load_started` with
  `UndefVarError: v16_physical_profile_bodies not defined in Main` before
  candidate body construction. The base diagnostic's candidate drag was
  `3485.132996418866` solver units after that single step. No owner was
  constructed or collection-tested; the owner experiment has no geometry,
  simulation-field, force, GC, or normal measurements.
- **Verified:** exact version 5 log SHA-256 is
  `500306c3c4e0f7ca31dfe7a3c4191b5180ec7a8ad0fd8a154cb008a5581cb8f3`, status
  SHA-256 is
  `2341886fe14bda95b1cf663ab933c531b25e6cba8b281d9b6fd6c4cd6d8c5f16`, output
  manifest SHA-256 is
  `c95d0836fee46c74334599fd7ff00d98559495b19d26224d8cde61ad6525a91e`, and
  `ERROR.txt` SHA-256 is
  `01f5ccc61439cb579aba16c988da9a51381fbf6084d20033b5d0396f74b6eb81`. The
  original append-only evidence is
  [`version 5 diagnostic`](evidence/kaggle_w3_v16_cuda_diagnostic_version5_2026_09.json),
  SHA-256
  `6e125c47a252fcbbf5c2e78c8342cc16e352a1edea7674bf1510d75a0832e19e`; its
  host-classification correction is
  [`version 5 host correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version5_host_correction_2026_09.json),
  SHA-256
  `907babecef7f5ee9547e3c74a1f18d4bf751e9187a7a078de9bc67f9dd47a823`. Both
  verify the output artifacts, but the owner diagnostic is incomplete and the
  exact failure class is `owner_lifetime_julia_missing_import`.
- **Local validation:** focused command
  `PYTHONPATH=src:scripts /Users/sota/projects/FomulaTMU/CFD2026_09/.venv/bin/python -m pytest -q tests/test_kaggle_w3.py tests/test_kaggle_w4.py tests/test_kaggle_w3_cuda_diagnostic.py`
  passed 39 tests. `python -m compileall src tests`, Python `py_compile` for
  the runner/verifier/tests, Julia `Meta.parseall` for the owner job, criteria
  JSON/sidecar/job hash checks, and `git diff --check` passed. Repository-wide
  pytest reported 1,088 passed, 37 failed, 4 skipped; the failures are
  historical tests requiring ignored `work/` artifacts absent from this
  worktree (for example PQ0.2/PQ3 checkpoints and Stage-S/Stage-V solver logs).
- **Qualified:** nothing new. The owner-lifetime hypothesis remains unresolved;
  the v5 import failure does not explain W3 v4's 3,841-step all-zero force
  history. W3 v4 remains unqualified, and W4, FD, gradient, reverse, topology,
  optimizer, and shape update remain unqualified/disallowed.
- **Open:** push the frozen round-3 source and submit a new exact private
  kernel version. Recollect its exact status/log/output and host-verify A/C
  agreement, both B owner-collection brackets, and the registered geometry,
  fields, forces, and normal diagnostics before interpreting causality.

### 2026-09-28 owner-lifetime diagnostic version 6 measured; causal result unresolved

- **Implemented:** version 6 used the round-3 owner job and runner pinned to
  source commit `22137e2c7e15e4bb4f62806e29e221a5965f64b2`. The four arms ran
  in separate Julia processes on one selected T4. The verifier was corrected
  after the first host pass attempt exposed two latent host-only issues: the
  Julia archive SHA is bound under criteria inputs, and completed arm arrays
  must be kept internal while compact report summaries are serialized. A/C/B
  measurements and registered conditions were not changed.
- **Registered:** version 6 used immutable round-3 criteria SHA
  `906fda6a3991d7a37ea29f50ccc851f3788cde9a6bb90dfcc5b11279fb3f4274` and owner
  job SHA
  `b952aae000f6a2047b050ca5d46bd8fdd1a5c320ebc222bd380b70c0924c8cac`.
- **Submitted:** exact private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/6` completed. Diagnostic
  runner SHA-256 is
  `deb12c2b9a9a72993f9a8967f12385d935022306ac25b8c30cd9cd07c3e5bc4e`; the
  selected GPU is `GPU-a66ae48d-3270-ed38-0d97-a68246cf09ec` from an inventory
  of 2 × Tesla T4. Runtime identity: Julia 1.12.6, CUDA.jl 6.3.1, CUDA runtime
  12.8.0, driver API 13.3.0, WaterLily 1.8.0, backend `KernelAbstractions`.
- **Measured:** A, C, B1 and B2 each completed two primal steps. Full 172,800
  point candidate/combined CPU and CUDA geometry artifacts were captured. All
  four arms had identical geometry arrays; candidate negative cells were
  1,009 CPU and CUDA, CPU/CUDA distance error was at most
  `4.7683716e-7 m`, and the pre-existing maximum normal-vector discrepancy
  stayed `1.3379748`. A/C final flow-field arrays were byte-identical. Both B
  replicates matched A through step 1 and diverged in final step-2 flow fields
  and force: A/C drag/downforce were `707.1370 / 847.9948`, B1
  `720.2276 / 854.9039`, and B2 `712.4746 / 853.7397` solver units. The
  A/C host comparison passed and both B replicates had host divergence classes
  `simulation_fields` and `force_history`.
- **Verified:** exact `/6` log SHA-256 is
  `0e300babad42276fcf18f6d9b11d2b6fd5f05802e906bd9c98c5e0becabf4b95`, status
  SHA-256 is
  `2f547f8fea5f9f2cc6b6c1d9bf11669c39105cb8dc194699c6d6398fc068a2b1`, output
  manifest SHA-256 is
  `f4944ddac2b19b6e1ba680964ed587e81c173a3544b8f3a189bd90a6b03b46ac`, and
  `DONE` SHA-256 is
  `c3ae0c1108a07ac153b0ee13893bc731b7e210607850bbb5c7956f02c3fc2525`. The
  first host record is
  [`version 6 result`](evidence/kaggle_w3_v16_cuda_diagnostic_version6_2026_09.json),
  SHA-256
  `68cf588200b84edf056a815e7d7f35683e113e21533a8819f641d7f17354482d`; its
  appended host correction is
  [`version 6 host correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version6_host_correction_2026_09.json),
  SHA-256
  `ad7e930eda5aa0ade067ed8797cacf03de256c31ddb7390383460e44652b25fb`. Base
  source/input/backend and raw output artifact verification passed. Owner
  behavioral verification is false because C and both B wrapper WeakRefs were
  already clear before the forced-GC bracket.
- **Causal interpretation:** source inspection shows round-3 code made
  `WeakRef(owner)` where `owner` is immutable `DeviceGridSDF`, rather than
  weak-referencing `owner.grid.phi`, the backing `CuArray`. The captured clear
  state therefore does not prove backing-array collection. C has the same
  wrapper WeakRef issue and nevertheless matches A exactly; B1/B2 share a
  step-2 field/force divergence, but their collection was not bracketed at the
  registered GC boundary. The owner-lifetime hypothesis remains **unresolved**;
  this is not a root-cause confirmation and does not explain W3 v4's complete
  all-zero force history.
- **Qualified:** nothing. All W3 primal/physical/grid/gradient/reverse/topology
  and shape-update qualification flags remain false. No production W3 path,
  force convention, or acceptance threshold changed.
- **Open:** register the next diagnostic round with `WeakRef(owner.grid.phi)`
  for A/C/B and record the weak-reference target path/type explicitly. Keep the
  same fixture, process isolation, GC procedure, force/field/geometry probes,
  tolerances and causal rules; rerun only after that immutable round is pushed.

### 2026-09-28 owner-lifetime diagnostic round 4 submitted; version 7 running

- **Implemented:** the diagnostic now weak-references the backing
  `owner.grid.phi` `CuArray` directly for A/C/B1/B2 and records the target path
  and runtime type. B1/B2 disable automatic GC at the noinline helper boundary
  after creating the WeakRef, verify GC was initially enabled, and re-enable it
  immediately before each of the two registered full collections. Automatic GC
  is disabled again between the two forced collections and remains enabled
  after the second. The existing shared body/simulation path, arm order, full
  geometry scan, field/force snapshots, fixture, tolerances, and causal rules
  are unchanged. No production W3 source, force convention, or acceptance gate
  changed.
- **Registered:** immutable criteria
  [`round 4`](evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round4.json)
  SHA-256
  `58867bf2e68e989200edb39b401f8db2f52df340db2d84534853dad01679530e`; sidecar
  SHA-256
  `0637966ce609c452797241e42498e6503a02dde6ba09298b93e692ac5373f3c0`. It
  supersedes round 3 only because v6 showed that `WeakRef(owner)` targeted the
  immutable wrapper and B's references cleared before the registered GC
  bracket. The W3 fixture, owner hypotheses, acceptance thresholds, and
  causal decision rules are not relaxed. Owner job SHA-256 is
  `3676babc3b7516690a813acb84fa324a46a75e8b98b39c447b755394a80c6212`; the
  runner SHA-256 is
  `5e004a1e32529271b1b45a7f65086e173ca8246b5df57e8ea127b40f834ea710`; the
  source checkout to be used by the pinned runner is commit
  `ffb5cc7edc4d3a598d420ef6c065d10c5c8bbc07`.
- **Submitted:** after source-pin commit `dec3e2f0728ba03df2d3951d6c5972bdb41c7d1a`
  was pushed, private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7` was submitted with the
  registered T4 runtime. Its first exact-version status was
  `KernelWorkerStatus.RUNNING`; the captured status file SHA-256 is
  `172bce72b56e63812fe433424e62e85da4677860437b57b598d5db11ec53048c`.
- **Measured:** no round-4 GPU observations exist. Version 6 remains the latest
  measurement and its owner-lifetime result remains unresolved; it does not
  explain W3 v4's 3,841-step all-zero force history.
- **Verified:** focused W3/W4/diagnostic tests pass 40/40; Python `compileall`,
  targeted `py_compile`, Julia `Meta.parseall` of the owner job, criteria JSON
  and sidecar verification, and `git diff --check` pass. These are local
  contract checks only. Repository-wide pytest completed with 1,089 passed,
  37 failed, and 4 skipped. The 37 failures match the known managed-worktree
  limitation: historical PQ/Stage S/V tests read ignored `work/` checkpoints,
  logs, and case files absent from this checkout. The changed W3/W4/diagnostic
  slice passes independently.
- **Qualified:** nothing new. W3 v4 remains failed/unqualified; WaterLily
  primal, physical profile, grid response, gradient, reverse, topology,
  optimizer, and shape update remain unqualified.
- **Open:** continue checking only exact Kaggle version 7; when terminal,
  retrieve its exact logs/output and run host verification before making any
  causal interpretation.

### 2026-09-28 owner-lifetime diagnostic version 7 complete; host-verified

- **Measured:** exact private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic/7` reached
  `KernelWorkerStatus.COMPLETE`. Version-bound terminal status SHA-256 is
  `15530f04c1915580ac9ef78acb78a48b4c5dff418243add0aa9cd2620920f27a`; exact
  Kaggle log SHA-256 is
  `a8e9b9481de43bcdfd246e33885fa3aea9ce1d02c396fba1d35c07540e4eab88`; output
  `sha256.json` SHA-256 is
  `5a44a351600f56226cf07234a4ce6eb9ac8ccf426c3b2ebd98f22f2603d16adb`.
  The run performed four isolated arms (A, C, B1, B2), each with two primal
  steps and 172,800-point geometry scans, on a Tesla T4 with Julia 1.12.6,
  CUDA.jl 6.3.1, CUDA runtime 12.8.0, driver API 13.3.0, and WaterLily 1.8.0.
- **Verified:** the host verifier independently checked input/source/runtime
  identity and every output artifact. Immutable criteria SHA-256 is
  `58867bf2e68e989200edb39b401f8db2f52df340db2d84534853dad01679530e`; owner
  job SHA-256 is
  `3676babc3b7516690a813acb84fa324a46a75e8b98b39c447b755394a80c6212`; runner
  SHA-256 is
  `5e004a1e32529271b1b45a7f65086e173ca8246b5df57e8ea127b40f834ea710`; host
  verifier SHA-256 is
  `20484ef7d1c885d3f163ae721292181264085f13889dca94a722f2178f97ad68`. The
  primary append-only result is
  [`version-7 diagnostic evidence`](evidence/kaggle_w3_v16_cuda_diagnostic_version7_2026_09.json),
  SHA-256
  `66dd9396967f95ef92cb682b24ed14ac4a56345b12cfb2d38f67d4e5bbbb63c3`.
  After the host correction, focused W3/W4/diagnostic tests pass 42/42 and
  `python -m compileall src tests` passes. Repository-wide `pytest -q` reports
  1,091 passed, 37 failed, and 4 skipped; the 37 failures read ignored
  historical `work/` case, checkpoint, or log artifacts absent from this
  managed checkout. `git diff --check` passes.
- **Interpretation:** A/C retained the direct `owner.grid.phi` backing-array
  WeakRef through both full GCs and agreed exactly in fields and force through
  step2. B1/B2 were alive immediately before the registered forced-GC bracket,
  cleared after both collections, agreed with controls through step1, then
  reproduced the same simulation-field and force-history divergence class at
  step2. Their viscous and total raw force components were JSON `null` on all
  axes; these values remain invalid observations, so no force closure is
  claimed on those axes. The result strongly supports owner-lifetime
  sensitivity in this two-step fixture but does not explain W3 v4's complete
  3,841-step all-zero force history.
- **Host correction:** the initial verifier attempt stopped because it rejected
  the registered post-GC B-step2 null force observations and wrote no result
  evidence. The correction permits those nulls only under the measured B-step2
  owner-collection bracket and checks null masks plus finite components. The
  append-only correction record is
  [`version-7 host correction`](evidence/kaggle_w3_v16_cuda_diagnostic_version7_host_correction_2026_09.json),
  SHA-256
  `53900176b17b0f91a0513c40b531ad538ae028da0b13034244d7fe6ea939ba6c`.
- **Identity limitation:** the registered type label is
  `CuArray{Float32, 3, CUDA.DeviceMemory}`, while every arm reports the exact
  runtime string `CuArray{Float32, 3, CUDACore.DeviceMemory}`. The primary
  verifier records the mismatch and assumes no alias equivalence. The arms
  still report the same observed runtime type; resolving the label is open.
- **Qualified:** nothing new. The W3 v16 primal, physical profile, grid/domain
  response, gradient, CPU/GPU reverse, topology, and shape update remain
  unqualified; `shape_update_allowed=false`. No production owner-lifetime fix
  is authorized by this diagnostic.
- **Open:** freeze a new immutable W3 qualification round against the committed
  structural owner fix, update and remotely re-verify the private dataset, then
  submit and host-verify the exact T4 kernel version. W4 remains blocked on a
  passing host-verified W3 primal.

### 2026-09-28 full-horizon owner diagnostic closed; W3 owner fix implemented

- **Measured:** exact private kernel
  `ramhachi888/cfd-opt-sdf-w3-owner-full-horizon-diagnostic/2` reached
  `KernelWorkerStatus.COMPLETE` on the registered two-T4 Kaggle inventory,
  selected UUID `GPU-594bac6d-f97e-246d-4962-065f751ba972`, Julia 1.12.6,
  CUDA.jl/CUDACore 6.3.1, CUDA runtime 12.8.0, driver API 13.3.0, and
  WaterLily 1.8.0. Registered criteria SHA-256 is
  `2b28c0284833cdc3b360fe2f55e6babb435394b69ea001fcb677fe94c5b40000`;
  source commit `a8ce5a8104b8d115ed9d706257f0e0b5956c7db3`; exact log SHA-256
  `763c53bfd5b5fe234da74e2a475ca8dc1a7b73d7befa46566b9a640e7a4ac239`;
  terminal status SHA-256
  `b460246279ec24d862be48d472007531d1b16c7e49584c98fe9fc862fdd28c35`;
  output `sha256.json` SHA-256
  `58b7265cfe8f9e53997683e966ec00fadc5d9986ab83201472a03ab5b692324c`.
- **Verified:** A-natural and A-forced each retained the backing owner and
  completed 4,808 steps to `tU/L=120.0019378662`, with finite, nonzero forces;
  their 601 force samples matched exactly. B-natural-1 and B-natural-2 both
  observed the backing `owner.grid.phi` WeakRef clear at step 1 and completed
  the horizon. Their first sampled non-finite force was step 16 at
  `tU/L=0.3506548703` and step 128 at `tU/L=3.0178484917`, respectively.
  The registered first-collection and endpoint velocity/pressure snapshots
  remained finite. The type probe result
  [`owner type round 2`](evidence/kaggle_w3_owner_type_probe_result_2026_09.json)
  SHA-256 `91667c7dc783bd7f8f05dd8b2b596ec6242c2c887f60c8f7d142f4c53ea67fb6`
  confirms `CUDA.DeviceMemory === CUDACore.DeviceMemory` on the exact Julia
  1.12.6/CUDA.jl 6.3.1 T4 runtime.
- **Host correction:** the first local verifier attempt completed artifact and
  arm validation but stopped at final evidence assembly with
  `KeyError: qualification_flags`; the immutable schema stores the flags under
  `evidence_output`. The corrected host verifier reads that registered
  location and records its actual hash versus the registered hash. It does not
  change the criteria, measurement, or thresholds. Primary result evidence
  SHA-256 is `72e887e02b406b964bf7b6c617dcf111fc51dc9e1d275fc827689e80e29c9aeb`;
  host-correction evidence SHA-256 is
  `a56590757b46b176102d7c3e92517bbac57d7d9740ca41036c72fd28bbe29ccb`.
  The corrected verifier hash differs from the criteria-bound verifier hash;
  this discrepancy is explicitly recorded in the correction evidence.
- **Interpretation:** the preregistered rule classifies this as
  `owner_lifetime_implementation_bug_confirmed_exact_v4_zero_force_symptom_unresolved`
  and sets `production_fix_gate_met=true`. It does not reproduce W3 v4's
  complete all-zero force history: B forces became non-finite rather than
  remaining finite exact zero. Owner lifetime is the confirmed defect; the
  exact v4 symptom's complete root cause remains open.
- **Implemented:** `OwnedV16Run` holds the owner, body tuple, and simulation;
  production `run_primal` preserves that wrapper for its entire solver call.
  Geometry/source hashes, grid, profile, force projection, burn-in, sample
  stride, runtime and acceptance thresholds are unchanged. A CPU adapter test
  forces GC and verifies the wrapper still strongly retains its owner. Focused
  W2b/W3/W4/diagnostic pytest: 62 passed; Julia adapter test: 16 checks passed
  with no solver step; W3 Julia syntax, Python compileall, py_compile, and
  `git diff --check` pass. Full pytest: 1,109 passed, 37 failed, 4 skipped;
  all 37 failures read ignored historical `work/` artifacts absent from this
  managed worktree.
- **Registered:** not yet. New immutable W3 qualification round 4 will bind
  this owner fix and the exact owner diagnostic prerequisite after the source
  commit is pushed. Existing round-3 criteria/evidence remain unchanged.
- **Submitted / qualified:** no new W3 qualification kernel has been
  submitted, and W3 remains unqualified. W4, formal FD, gradient/reverse,
  topology, optimizer, and shape update remain blocked/false.
- **Open:** commit and push the tested source, diagnostic result/correction,
  and status refresh; register W3 round 4; stage/upload/re-download and verify
  its private dataset; submit the next exact W3 T4 kernel version. Do not
  start W4 or formal FD before exact host-verified W3 PASS.

### 2026-09-28 W3 owner-fix qualification round 4 registered

- **Implemented:** the production W3 run now structurally retains its CUDA SDF
  owner with `OwnedV16Run` for the full `run_primal` lifetime. The fix changes
  owner reachability only; canonical SDF bytes, grid/profile, force signs,
  measurement window, sampling, runtime limit and thresholds are unchanged.
- **Registered:** immutable W3 round-4 criteria are
  [`round 4`](evidence/kaggle_w3_v16_primal_criteria_2026_09_round4.json),
  SHA-256
  `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`;
  sidecar SHA-256 is the same. The registrar `--round 4 --check` passed.
  Criteria bind production source commit
  `ee6298e843e130b121d918ca9a321b707dcd4ae0`, the owner-diagnostic criteria,
  result and host correction by their registered hashes, and the existing W3
  measurement contract. The unchanged 2% drag/downforce half-window drift gate
  is inherited from registered W2 sphere capability precedent.
- **Submitted:** no W3 round-4 kernel has been submitted at this checkpoint.
- **Measured / verified:** no round-4 primal measurement or host-verification
  result exists yet.
- **Qualified:** W3 remains unqualified. This round does not qualify physical
  profile equivalence, absolute aerodynamics, grid/domain response, gradients,
  reverse mode, topology, optimizer, or shape update. All corresponding flags
  remain false.
- **Open:** commit/push the immutable criteria and status, stage the canonical
  input dataset in a new ignored work directory, publish and re-download the
  private Kaggle dataset, compare complete file inventory and hashes, then
  submit the next exact W3 T4 version. Do not start W4 or formal FD before
  exact round-4 host verification passes.

### 2026-09-28 W3 round 4 dataset verified; exact version 5 running

- **Registered:** round-4 criteria remain immutable at SHA-256
  `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`,
  source commit `ee6298e843e130b121d918ca9a321b707dcd4ae0`; criteria and status
  were pushed in commit `94add3ada878c9931dfb5593c9cb32611a327d9f`.
- **Dataset staged/submitted:** canonical dataset staging used
  `work/kaggle_w3_v16_dataset_round4/`. Kaggle private dataset
  `ramhachi888/cfd-opt-sdf-v16-genesis-state` reports version 4, status
  `ready`. The five uploaded data files match the re-downloaded inventory and
  SHA-256 values exactly. Manifest SHA-256 is
  `995d3e3aa931f28e8fb4dadcc9cb9e17fe8235d57190a188b75939505d4eacad`;
  host dataset audit SHA-256 is
  `88733b10c8f62c58ab252e7982c89aa7222990d79a7f8e2a8aeb1cded19f13d0`.
  Canonical NPZ SHA-256 is
  `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`,
  C-order phi SHA-256 is
  `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`,
  and Fortran-order phi SHA-256 is
  `9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`.
  Kaggle's metadata endpoint returns a server API envelope rather than the
  upload `dataset-metadata.json` file; ID, owner, slug, private status, title,
  and license were compared semantically.
- **Submitted:** exact private T4 kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-primal/5` was pushed with a 7200-second
  timeout. Its captured initial status is `KernelWorkerStatus.RUNNING`; the
  status-file SHA-256 is
  `7b50a5e1f6646832eca3f3040bc89b9931761c92f83cb599be88fd6ca4487098`.
  The round-4 runner, Julia job, host verifier, Project and Manifest hashes
  match both the registered values and source commit `ee6298e`.
- **Measured / verified / qualified:** no terminal primal output or W3
  host-verification verdict exists yet. W3 and all downstream qualification
  flags remain false.
- **Open:** no additional W3 run is open. W4 criteria registration is the next
  separate phase; formal FD remains gated on W4. Do not reinterpret this W3
  result as OpenFOAM equivalence, absolute downforce correctness, stationarity
  beyond the registered window, grid/domain convergence, or gradient evidence.

### 2026-09-28 W3 round 4 exact version 5 PASS and host-verified

- **Measured:** exact private kernel
  `ramhachi888/cfd-opt-sdf-w3-v16-primal/5` reached
  `KernelWorkerStatus.COMPLETE`. Terminal status SHA-256 is
  `59e3f698703e6684b7d9e7acdb92c1c9bc593a0d02e35da6824610547e75d771`;
  exact Kaggle log SHA-256 is
  `011b878cf20ee47c70cfde67e7d636eb0f96dbcdf2fed9a08f9b3f5901f643d4`;
  output `sha256.json` SHA-256 is
  `6973f1facb6ba1b8241d97601dc4d74a17e7df91d894dcccdfde2f240391595e`.
  Registered criteria SHA-256 is
  `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`.
- **Verified:** append-only result
  [`round-4 result`](evidence/kaggle_w3_v16_primal_result_round4_2026_09.json)
  SHA-256
  `d00949d0ea2f2ddcd222f0f376449d9d7aba9b634a650cf75822c640b9e6f4a8`;
  its sidecar contains the same digest. All T0-T10 passed. The independently
  checked output contains 18 files plus the `DONE` marker. Backend identity is
  two Tesla T4 GPUs, selected UUID
  `GPU-9a967f15-342d-f7c4-fad3-2da5ddc7c609`, `CUDA_VISIBLE_DEVICES=0`, driver
  `580.159.04`, CUDA driver API `13.3.0`, runtime `12.8.0`, Julia `1.12.6`,
  one Julia thread, CUDA.jl `6.3.1`, WaterLily `1.8.0`, backend
  `KernelAbstractions`.
- **Raw measurements:** canonical state SHA-256
  `3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe`, C-order
  phi SHA-256
  `45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785`,
  Fortran-order/device-roundtrip phi SHA-256
  `9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7`, and
  measured CPU margin `0.3499999939931499 m` against `0.15 m`. Flow grid is
  `100×48×36`, flow origin `[-2.5,-1.2,-0.9] m`, canonical SDF origin
  `[-1.0,-0.8,-0.6] m`, spacing `0.05 m`, `Re=80`, and `tU/L=120.0019378662`
  after 4,808 steps. Velocity, pressure and candidate force history are finite;
  601 force samples were recorded. The exact `[80,120]` window contains 200
  samples. Host-recomputed time-weighted drag is `+0.3360177299 N`, downforce
  is `+0.3533732402 N`, and `Cd=1.0500554060`. Half-window relative drift is
  `8.16e-6` for drag and `4.17e-6` for downforce, below the registered `0.02`.
  Three-axis pressure-plus-viscous force closure, projections, exact-window
  interpolation/integration and host recomputation passed T7. Raw force CSV
  SHA-256 is `3e53ad09fd3d88bf1d8c71feb5f5de9dad05efcc5dce3dcbd54d19f89f5ff5bb`.
  Solver wall time is `35.2219 s`; peak VRAM is `24,941,544 bytes` out of
  `15,636,037,632 bytes`.
- **Host-only correction:** the first direct verifier invocation reached final
  evidence assembly but raised `NameError: HOST_VERIFIER is not defined` and
  wrote no result. Its exact log SHA-256 is
  `783fd332d98f9bbbe0eb59d36ec22f4d330fde5ce87ad5404cbdb9c7c3ae9d7e`. The
  compatibility entrypoint supplies that missing path global and invokes the
  unchanged registered verifier; its SHA-256 is
  `d3ee66e9b4c045d214dd420d28a19dcacd53f7f34de7da737b7b12b8531c2472`.
  The result records the exact registered verifier SHA, which matches round 4.
  Append-only correction evidence
  [`round-4 host correction`](evidence/kaggle_w3_v16_primal_result_round4_host_correction_2026_09.json)
  SHA-256 is
  `27f0f60bbfbffd111259ecb988bec9b6e8cb1f9498d3a8ba46c04c8d79bddb9b`.
- **Qualified:** only the registered canonical v16 primal integrity/force/
  stationarity contract on the registered WaterLily finite-box approximation
  passed (`primal_contract_qualified=true`). No OpenFOAM profile equivalence,
  absolute downforce correctness, grid/domain response, gradient, reverse,
  topology, optimizer or shape-update claim follows. The exact W3 v4 all-zero
  force root cause remains unresolved; `shape_update_allowed=false`.
- **Open:** W4 is the next separately scoped phase but was not started here.
  Its immutable criteria and measurement remain open. Formal centered FD,
  reverse qualification and all optimization work remain gated on later
  evidence; do not run them from this W3 result alone.
- **Validation:** focused W3/W4/owner/reverse-diagnostic pytest passed 56 tests;
  `compileall`, host compatibility-entrypoint `py_compile`, evidence/sidecar
  chain checks and `git diff --check` passed. Full repository pytest reported
  1,109 passed, 37 failed and 4 skipped. All 37 failures are the known
  historical tests requiring ignored `work/` checkpoints, cases or solver logs
  absent from this managed worktree; no W3/W4 task test failed.

### W4 round 1 pre-computation inventory defect and round 2 correction

- **Implemented:** round-1 local preflight found that the runner and host
  verifier keyed expected dataset files by logical criterion names
  (`canonical_state_npz`, `canonical_phi_fortran_raw`) instead of each
  registered physical filename (`sdf_design_state.npz`,
  `canonical_v16_phi_f4_fortran.raw`). Both verifiers now derive filenames
  from `inputs[*].path`; a focused regression test requires the runner and
  host implementations to agree. The existing round-1 staging passes the
  corrected local host preflight, including canonical state/phi hashes and
  measured margin. This is a contract check only.
- **Registered:** immutable round-1 W4 criteria remain unchanged at
  [`kaggle_w4_v16_sensitivity_criteria_2026_09.json`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json),
  SHA-256
  `5bdfb819ff9512dcc3ca85f8919e5cff236de4706240cbdf09a577d56183a9ea`.
  They bind the prior verifier/runner source and are retained as historical
  pre-computation evidence. Corrected immutable round 2 is now registered at
  [`kaggle_w4_v16_sensitivity_criteria_2026_09_round2.json`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round2.json),
  SHA-256 `5e41ffd790b64638659136bfba5b0abfda7325c3578f15fe4d16fa610a7123da`
  (sidecar contains the same digest). It binds source commit
  `97a5bcaedcc8f171cda3710a763a22e6210cfbb5`, W3 round-4 criteria SHA
  `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb`, and
  W3 host-PASS result SHA
  `d00949d0ea2f2ddcd222f0f376449d9d7aba9b634a650cf75822c640b9e6f4a8`.
- **Submitted:** private Kaggle dataset
  `ramhachi888/cfd-opt-sdf-v16-w4-sensitivity` version 1 reports `ready`.
  Staging is under `work/kaggle_w4_v16_dataset_round2/`; exact download and
  server inventory are under `work/kaggle_w4_v16_dataset_round2_remote/`.
- **Verified:** runner-mounted inventory and independent host checks pass
  locally. The downloaded remote inventory contains the exact five registered
  files with matching SHA-256 values; remote NPZ/phi identity and CPU SDF
  margin also pass. Manifest SHA-256 is
  `3d505dfa1ee55d935f7123aa30cf8e665471e91105a5ce968f5de6aa509d7f42`; remote
  audit SHA-256 is
  `20503ff4e6492b1acc23ef46813f1999e42a86f082a93aa45b88ea8934c53b9f`.
- **Measured / qualified:** no W4 primal measurement or result exists. Exact
  kernel version 1 was submitted, but returned `ERROR` before a solver step.
  The earlier host preflight failure remains preserved by immutable round 1;
  neither criteria round was edited.
- **Validation:** source-fix commit
  `f69c56e6306d30f6e6590da898088e4af7606c00` is pushed to the canonical branch.
  Focused W4/W3/owner-regression tests pass (38); `compileall`, the required
  W4 Python `py_compile`, Julia syntax parsing and four-case mapping/Re=80
  assertions, round-1 JSON/sidecar check, and `git diff --check` pass. The full
  repository run reports 1,114 passed, 37 failed, and 4 skipped. The 37
  failures are historical Stage T/S/V tests whose tracebacks read absent,
  ignored `work/` checkpoints, cases, meshes, or solver logs; no W3/W4 task
  test failed.
- **Open:** preserve the version-1 diagnostic, make only the pre-solver Julia
  tuple-materialization correction, add regression coverage, then register
  immutable round 3 and a new private dataset version before retrying. Formal
  FD, reverse/adjoint qualification, shape update and topology birth remain
  out of scope.

### W4 round-2 kernel version 1: pre-solver case-inventory diagnostic

- **Registered:** W4 immutable round 2 remains unchanged at SHA-256
  `5e41ffd790b64638659136bfba5b0abfda7325c3578f15fe4d16fa610a7123da`, bound
  to source `97a5bcaedcc8f171cda3710a763a22e6210cfbb5`; private dataset version 1
  remains ready with its exact remote inventory verified.
- **Submitted:** exact kernel
  `ramhachi888/cfd-opt-sdf-w4-v16-sensitivity/1` ended with
  `KernelWorkerStatus.ERROR`. Terminal status SHA-256 is
  `f784304d00893b3509b023e2636407faa6cdcb335eebd6a2563c4504c8fc6b82`; exact
  `kernels logs` response SHA-256 is
  `93464d8f48672b3ad98552d87adf9eff400a42bb219842524b7ce74d3e44d329`; the
  downloaded kernel log SHA-256 is
  `1079cb67af44cbc9a545d1c13143ff5404eb9085ba196f3a784574638e5cab73`.
- **Diagnostic:** append-only evidence is
  [`kaggle_w4_v16_sensitivity_version1_diagnostic_2026_09.json`](evidence/kaggle_w4_v16_sensitivity_version1_diagnostic_2026_09.json),
  SHA-256 `30e4a3444e07570cff70ad40feff653ffe9858e30d7eea693213d09b610a8df3`
  (sidecar contains the same digest). Kaggle input/source identity, package
  instantiation, Julia 1.12.6/CUDA.jl 6.3.1/WaterLily 1.8.0 CUDA smoke, and
  two-T4 inventory passed. The Julia job failed at source line 300 with
  `W4 case inventory drift`: `tuple(generator)` wraps the generator as one
  tuple element, while `Tuple(generator)` materializes the four registered
  case IDs. The corrected expression was reproduced locally against the exact
  four IDs.
- **Solver / host verification:** `solver_started=false`;
  `solver_steps=0`; both `solver_step_invoked` and `solver_step_returned` are
  empty. SDF load/device round-trip, body construction, simulation, force
  integration and all four primal runs were not reached. The 14 payload files
  in Kaggle's output manifest match their hashes; the full host verifier
  rejects this incomplete output because `DONE`, `outcome.json`,
  `fingerprint.json` and case measurements are absent. No T0-T10 gate or W4
  result was evaluated; all qualification flags remain false.
- **Implemented:** `scripts/waterlily_w4_v16_sensitivity_job.jl` now uses
  `Tuple(case.case_id for case in V16W4_CASES)` before comparing the four
  registered case IDs. A focused regression test prevents reintroducing
  `tuple(generator)`.
- **Registered:** immutable W4 criteria round 3 is
  [`kaggle_w4_v16_sensitivity_criteria_2026_09_round3.json`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round3.json),
  SHA-256 `6cbe15769a8728c4f3ceba165ef75d6d11543c633c6651daafb8d6c901f8dfc6`
  (matching sidecar). It binds source snapshot
  `6d4608f39d2937ced96dd934b6be1cf61b4aa150`, exact W3 round-4 host-PASS
  criteria/result, and the observed T4 cohort. No case, force, time-window or
  threshold criteria were relaxed or changed from round 2.
- **Validation:** focused W4/W3/owner pytest passed 39 tests; `compileall`,
  targeted Python `py_compile`, Julia job `Meta.parseall`, and an executable
  four-case ID/dimension/Re=80 assertion pass. Full repository pytest reported
  1,115 passed, 37 failed and 4 skipped. All 37 failures are the known
  historical Stage T/S/V tests requiring ignored `work/` checkpoints, meshes,
  cases or solver logs absent from this managed worktree; no W4/W3 test failed.
- **Submitted:** private dataset
  `ramhachi888/cfd-opt-sdf-v16-w4-sensitivity` version 2 reports `ready`.
  The downloaded five-file payload exactly matches the round-3 manifest;
  manifest SHA-256 is
  `0215f60cbb9ab567ae2b79d2f03d29b3e1eb532adc060f96af71e289f49e49e7` and
  remote audit SHA-256 is
  `e281ab7ad3e3025d89f4084b18b5ad900365f608d8a51bfc9109583608271a56`.
- **Verified:** independent host and runner-mount dataset checks pass; canonical
  state, C-/Fortran-order phi, criteria/sidecar, CPU SDF margin
  (`0.3499999939931499 m`) and all payload hashes match.
- **Measured:** exact kernel `/2` reached tU/L=120 in `flow_16`, `flow_24`,
  `flow_32` and `domain_xplus1m_16`; total solver time was `515.3048713 s`.
  All raw CSVs passed independent host component closure and time-weighted
  recomputation. Numerical values are diagnostic only because T3/T4 failed.
- **Verified:** source, criteria, dataset, output manifest, runtime/backend,
  raw force recomputation and gates T0-T2/T5-T10 were independently checked.
  The pinned full host verifier rejects the run because the runner did not emit
  top-level `DONE` after T3/T4 failed. W4 remains unqualified.
- **Diagnostic:** append-only evidence is
  [`kaggle_w4_v16_sensitivity_round3_kernel2_diagnostic_2026_09.json`](evidence/kaggle_w4_v16_sensitivity_round3_kernel2_diagnostic_2026_09.json),
  SHA-256 `cde5c72b7a9996bd47933ec76ac3ce9990a57921256d96d6c5341de257458681`
  (sidecar matches). It records exact kernel/log/output hashes, solver progress,
  raw data, independent recomputation, T3/T4 failures and false qualification
  flags.
- **Implemented:** commit `52a50e488cb01f93c971dc29b5fc29f1670e36a5` fixes the
  T3 xyz maximum comparison in both runner and host verifier and aligns the
  summary-only T4 ground descriptor with the registered wording. The physical
  ground, cases and criteria were not changed. Regression tests prove both
  gate parity and rejection of wrong values.
- **Validation:** focused W4/W3/owner pytest passed 41 tests; Python `compileall`,
  targeted `py_compile`, Julia job `Meta.parseall`, and `git diff --check` pass.
  Full pytest reports 1,117 passed, 37 failed and 4 skipped. All 37 failures
  require ignored historical `work/` artifacts absent from this managed
  worktree; no W4/W3 test failed.
- **Registered:** immutable round 4 is
  [`kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json),
  SHA-256 `3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f`,
  bound to source `b9ae43b540a94b52fdb8a05051fba6f250034a6f` and exact W3
  round-4 host PASS. Cases, physical conditions, time window, force semantics,
  stationarity limit and response follow-up rule equal round 3 exactly.
- **Implemented / local stage verified:** fresh inputs are staged at
  `work/kaggle_w4_v16_dataset_round4/`. Host and runner-mount checks pass;
  manifest SHA-256 is
  `d5093b23be0a26c5cf5ce1030e42189a71b58f834160bcbd15c272d00561e8a7`.
  Canonical state/phi hashes are unchanged and measured CPU margin is
  `0.3499999939931499 m`.
- **Submitted:** private dataset `ramhachi888/cfd-opt-sdf-v16-w4-sensitivity`
  version 3 reports `ready`. The downloaded five-file payload exactly matches
  the round-4 manifest; manifest SHA-256 is
  `d5093b23be0a26c5cf5ce1030e42189a71b58f834160bcbd15c272d00561e8a7`, and
  remote inventory audit SHA-256 is
  `81a477314cf7a34f8f157a703ed11b63f912747e0c82446c61d327044ad687e4`.
- **Verified:** remote inventory, criteria/sidecar, NPZ/raw phi, host dataset
  verifier, runner mount, canonical hashes and margin all pass.
- **Open:** verify kernel metadata and submit the next exact private T4 kernel
  version. Preserve round-3 criteria and kernel `/2` evidence.


### 2026-09-29 W4 round 4 exact kernel version 3 PASS and host-verified

This checkpoint supersedes the preceding W4 round-4 “submit the next exact
kernel version” status. It closes W4 host verification only; it does not start
formal FD or any reverse/optimizer work.

- **Registered:** immutable round-4 criteria remain
  [`kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json`](evidence/kaggle_w4_v16_sensitivity_criteria_2026_09_round4.json),
  SHA-256
  `3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f`, bound
  to source snapshot `b9ae43b540a94b52fdb8a05051fba6f250034a6f` and the exact
  W3 round-4 host-verified PASS. No criteria, measurement window or threshold
  changed after measurement.
- **Submitted:** private dataset
  `ramhachi888/cfd-opt-sdf-v16-w4-sensitivity` version 3 was `ready`; its
  manifest SHA-256 is
  `d5093b23be0a26c5cf5ce1030e42189a71b58f834160bcbd15c272d00561e8a7`, and
  remote inventory audit SHA-256 is
  `81a477314cf7a34f8f157a703ed11b63f912747e0c82446c61d327044ad687e4`. Exact
  private kernel
  `ramhachi888/cfd-opt-sdf-w4-v16-sensitivity/3` ended
  `KernelWorkerStatus.COMPLETE`. Terminal status SHA-256 is
  `80449770970ace3350548b96005931282c52a791555986628382897e930fb1af`;
  `kaggle kernels logs` response SHA-256 is
  `380f53ba8a0ad08c5fdf7c6266ebd63d041d40d6be2ff9e7f56ffa11db7b25fe`, and
  downloaded Kaggle log SHA-256 is
  `3f42c3a9041e8baa8c2ee248fc7cc6be71df9dabab4d5e6441b2cee057e38dee`.
- **Measured:** all four cases completed to `tU/L >= 120` on the registered
  T4 backend. Exact-window `[80,120]` time-weighted physical force results are:

  | Case | Grid | Steps | `tU/L` | Wall (s) | Peak VRAM (bytes) | Drag (N) | Downforce (N) | Cd | Drag drift | Downforce drift |
  | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | `flow_16` | 100×48×36 | 4,808 | 120.001938 | 35.6669 | 24,934,924 | 0.336017730 | 0.353373240 | 1.050055406 | 8.16e-6 | 4.17e-6 |
  | `flow_24` | 150×72×54 | 8,741 | 120.009331 | 95.8426 | 81,567,020 | 0.357619959 | 0.356747660 | 1.117562371 | 2.06e-6 | 1.17e-5 |
  | `flow_32` | 200×96×72 | 13,536 | 120.005043 | 311.2219 | 184,412,116 | 0.410305278 | 0.411820160 | 1.282203995 | 1.99e-6 | 1.41e-6 |
  | `domain_xplus1m_16` | 120×48×36 | 4,808 | 120.000877 | 29.8522 | 29,631,500 | 0.336375219 | 0.353220289 | 1.051172558 | 1.98e-5 | 1.08e-5 |

- **Verified:** independent host verifier
  `scripts/verify_kaggle_w4_v16.py` (SHA-256
  `139d45ef1edc5c7a04d250a88ce7e71710a6c07e2b10062c96db78bf86698aa0`)
  checked 24 output-manifest files, input/source/backend identity, canonical
  SDF hashes and margin, GPU round-trip, all raw force rows and x/y/z
  pressure-plus-viscous closure, force projections, endpoint interpolation,
  time-weighted force/Cd recomputation, runtime/VRAM and T0-T10. Host verifier
  JSON SHA-256 is
  `77e5a2fe93c817b206a0f65a3a02039db1eb8e1fe5a387fdfcc34d12c3e384dd`; the
  output `sha256.json` manifest SHA-256 is
  `1a72ab72cf16a35e0828636c03ef86602e35d32589d28c4898aaf9c1a909b710`.
- **Response:** host-recomputed 24→32 absolute deltas are `0.0526853195 N`
  drag and `0.0550725000 N` downforce. The 16-cell baseline→extended-domain
  deltas are `0.0003574887 N` drag and `0.0001529516 N` downforce. Domain
  deltas are smaller than their corresponding resolution deltas, so the
  registered extended-domain fine-grid follow-up is not required. W4 flow_16
  and W3 round 4 have zero observed delta in drag, downforce, Cd, stationarity,
  steps, and `tU/L`; the criteria did not register a numerical repeatability
  gate, so this comparison remains descriptive.
- **Evidence:** append-only result
  [`kaggle_w4_v16_sensitivity_result_round4_2026_09.json`](evidence/kaggle_w4_v16_sensitivity_result_round4_2026_09.json),
  SHA-256
  `87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae`;
  its sidecar matches. Output manifest SHA-256 is
  `1a72ab72cf16a35e0828636c03ef86602e35d32589d28c4898aaf9c1a909b710`.
- **Qualified:** `w4_sensitivity_matrix_passed=true` only for the registered
  finite-box WaterLily sensitivity matrix. `physical_profile_equivalence_qualified`,
  `absolute_downforce_qualified`, `stationarity_qualified`,
  `grid_or_domain_convergence_qualified`, `gradient_qualified`,
  `reverse_mode_qualified`, `topology_qualified`, `optimizer_qualified`, and
  `shape_update_allowed` remain false. No OpenFOAM equivalence, absolute
  aerodynamics or grid/domain convergence claim follows.
- **Open:** formal FD entry gate is `OPEN` because the registered domain
  follow-up condition is false and W3/W4 drag signs agree. Formal centered FD
  measurement has not started; this checkpoint stops after W4 host
  verification. W3 v4 all-zero-force root cause remains unresolved.
- **Validation:** focused W4/W3-owner tests passed (`45 passed`); Python
  `compileall`, the registered W4 Python `py_compile` set, Julia `Meta.parseall`,
  the standalone four-case/Re=80/origin mapping check, and `git diff --check`
  passed. Full repository pytest reported `1,117 passed, 37 failed, 4 skipped`
  in `196.88 s`. Traceback review confirmed the 37 failures are historical
  Stage T/S/V checks blocked by missing ignored `work/` artifacts (mostly
  `FileNotFoundError`; one audit test reports the missing prerequisite); no
  W4, W3-owner or focused task test failed. Captured log:
  `work/kaggle_w4_version3/final_pytest.log`, SHA-256
  `60bdff0c767d3e043847d04ea072371cffd47f875dabed89c5c5af33284406b8`.

## 2026-09-29: centered directional-FD oracle implementation status

This checkpoint advances the FD work from the W4 entry gate without starting a
measurement. It supersedes the preceding statement that the task stops at W4
verification, while preserving W3/W4 evidence and all qualification limits.

- **Implemented locally:** solver-neutral scalar directional-FD contracts;
  three deterministic frozen directions; the five-level epsilon ladder; all
  30 direct `phi0 +/- epsilon*d` states and margin preflight; a 33-run fixed
  order; fresh WaterLily `flow_16` primals with retained CUDA SDF ownership;
  raw three-axis pressure/viscous/total force capture; endpoint-clipped
  trapezoidal physical-force recomputation; stationarity/noise/plateau rules;
  Kaggle runner, host verifier, dataset preparer, and mutable criteria draft.
- **Prerequisite verified:** W3 round 4 criteria/result SHAs remain
  `eeae43e8930f1dc4bb8d3a1099edce76e75390fba24176c9ad70c8248ac1eebb` /
  `d00949d0ea2f2ddcd222f0f376449d9d7aba9b634a650cf75822c640b9e6f4a8`; W4
  round 4 criteria/result SHAs remain
  `3efc8133c8d1b7d306041ee3f49ec5a708024f189095bdb0f13646fe329b578f` /
  `87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae`.
  The FD entry gate is open and W4 says no extended-domain fine-grid follow-up
  is required.
- **Registered:** no immutable FD criteria round exists yet. The checked-in
  draft remains mutable and measurement thresholds are not frozen.
- **Submitted / measured:** no FD private dataset or kernel has been created
  or submitted; no FD solver step has run.
- **Host verified:** prerequisite W3/W4 evidence only. FD outputs, host report,
  and result evidence do not exist.
- **Qualified:** `sdf_directional_fd_oracle_qualified=false`,
  `sdf_directional_fd_flow16_qualified=false`,
  `sdf_gradient_field_qualified=false`, `gradient_qualified=false`,
  `reverse_mode_qualified=false`, and `shape_update_allowed=false`.
- **Open:** commit and push the validated source/harness; only then freeze
  criteria, stage and remotely verify the private dataset, submit the exact T4
  kernel version, and host-verify that exact version. Stop after the FD host
  result. Do not run reverse/adjoint, optimization, or shape updates in this
  work item.

## 2026-09-29: centered directional-FD round 1 registered

The FD source/harness and validation were committed before registration. The
registrar initially failed with an undefined local W4 backend binding before
writing either criteria file. The binding was repaired in
`d0ac7163d86b4f5db5ba99c8113c767669365312`, pushed, and the registrar was
rerun from the clean pushed branch. No measurement occurred in that attempt.

- **Implemented:** source/harness commit `167dc992339d8edf9f368cbeff97963cca969deb`;
  registration repair commit `d0ac7163d86b4f5db5ba99c8113c767669365312`.
- **Registered:** immutable FD criteria round 1 at
  `docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round1.json`, file
  and sidecar SHA-256
  `ad0bd7dcc6f8e2f0927799fe1c9818e58c43fbc4205312a5ad4c397d61f6fdc6`;
  internal canonical criteria SHA-256
  `a110132ff6df6859fe4e38b5e4cb634c8ef2ac0015cfb6fbc5562d63c5bc292c`.
  It is `registered_not_run`, has `immutable=true`,
  `registered_before_computation=true`, and binds source commit `d0ac716…`.
  Registrar `--check` passed.
- **Frozen identities:** 24 exact source-repository inputs, 35 raw dataset
  payload inputs, canonical state SHA `44507748…`; D0/D1/D2 SHA-256 values
  `fb74a1e7…`, `26964bfa…`, and `e6ad0912…`; all 30 plus/minus states are
  bound and their minimum measured SDF margin is `0.33999999370425943 m`.
  The run order has 33 fresh primals with baseline A/B/C at beginning, middle,
  and end. The exact W3/W4 criteria and result SHAs are bound, including the
  W4 observed-runtime identity SHA.
- **Submitted / measured:** private dataset is not staged or uploaded; no FD
  kernel submitted; `formal_measurement_started=false`; no FD `sim_step!`
  invoked.
- **Host verified:** only the prerequisite W3/W4 evidence and premeasurement
  registration hashes. No FD output or host result exists.
- **Qualified:** directional FD oracle, 3D gradient field, gradient backend,
  reverse mode, topology and shape update remain unqualified/false.
- **Open:** prepare the exact private dataset from the immutable criteria,
  verify local inventory, upload, wait for `ready`, redownload and hash-compare
  the exact remote version, then submit the private T4 kernel. Stop after
  exact-version host verification; no reverse/adjoint or shape work in this
  task.
- **Validation:** 22 focused FD tests passed. Python `compileall src tests
  scripts`, runner `py_compile`, Julia parse plus exact flow_16 dims/origin/
  Re=80 assertion, both JSON parses, 30 canonical-state perturbation
  regenerations, and canonical margin checks passed. Full pytest reported
  `1,139 passed, 37 failed, 4 skipped` in `206.53 s`; the FD tests passed in
  that run. The 37 failures are pre-existing Stage T/S/V tests blocked by
  ignored historical `work/` ProblemSpec, STL, checkpoint, mesh, or solver
  artifacts missing from this managed worktree. Full log SHA-256:
  `17bb1c99705602b5c9dd5d499ffa3595d3cdf94cdb859c3b2de64123f0c8fd6f`.

### 2026-09-29 centered directional-FD round 1 submission diagnostic

Immutable FD criteria round 1 remains unchanged and unmeasured. The private
input dataset version 1 is `ready`; its 38-file remote inventory and hashes
match the local manifest. Five kernel submission requests using the registered
kernel ID returned HTTP 409 before a kernel version was created. The exact
latest Kaggle response body is preserved under ignored `work/` with SHA-256
`e4e5bd0dd4f0f27f19783d675a1483c8301817d2f4c9c25fe5676f234e452d7c`; its
message says the requested title is already in use by a dataset. The exact
post-failure kernel search returned `Not found` (SHA-256
`493fda53120050f85836032324409be6c6484f90a0755ae0c6a673ba7626818b`).

The submitted kernel ID equals the registered input dataset ID. This is a
Kaggle title/slug namespace conflict, not a solver or criteria failure. The
append-only diagnostic is
[`sdf_directional_fd_v16_round1_kernel_submission_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round1_kernel_submission_diagnostic_2026_09.json),
SHA-256 `3cabf32761785ac1f9cf1bf353b92e80649259a36197ba88e89f644b62edb9b8`.

- **Implemented:** round-1 source, runner, verifier, frozen directions and
  perturbations are unchanged.
- **Registered:** round 1 criteria and its sidecar are unchanged; its exact
  kernel slug cannot be submitted because of the API conflict.
- **Submitted:** no kernel version was created. Dataset version 1 is ready and
  remotely hash-verified.
- **Measured / verified:** no solver, CUDA, or host-result verification ran.
  `formal_measurement_started=false`, `solver_started=false`, and
  `solver_steps=0` remain true.
- **Qualified:** no FD or gradient qualification is granted.
- **Open:** minimally change only the kernel ID/title to a unique slug, add
  immutable round-2 criteria binding that metadata/source commit and the
  unchanged dataset ID and measurement contract, publish a new dataset
  version, verify it, then submit and verify that exact kernel version.

Do not edit or reuse round-1 criteria to accommodate the submission failure.

### 2026-09-29 centered directional-FD round 2 retry implementation

The Kaggle API conflict was isolated to a kernel ID/title that reused the
input dataset slug. The round-1 registered source, criteria, sidecar and
dataset version remain preserved. The minimal retry changes the kernel ID to
`ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel` and uses title
`CFD Opt SDF v16 Directional FD Oracle Kernel`; its input dataset ID and source
remain unchanged.

- **Implemented:** the metadata and mutable draft use the distinct kernel ID.
  The registrar accepts round 2 only when round-1 criteria/sidecars and the
  no-measurement HTTP 409 diagnostic match their exact hashes. It binds that
  diagnostic into round-2 source inputs and machine-checks that geometry,
  responses, directions, all 30 perturbations, run order, force/stationarity,
  noise and plateau rules, backend, gates and dataset payload are identical to
  round 1.
- **Registered:** round 1 remains immutable and `registered_not_run`; round 2
  is not yet registered. No existing evidence file was changed.
- **Submitted:** private dataset version 1 remains `ready` and host-side
  inventory/hash verified. Round-2 dataset version and kernel do not yet exist.
- **Measured / verified:** focused FD validation passed 24 tests; Python
  compileall, py_compile, JSON parsing and `git diff --check` passed. No Julia
  or GPU measurement was launched. Full pytest reported `1,141 passed,
  37 failed, 4 skipped` in `205.73 s`. All 37 failures are historical
  Stage T/S/V checks that require ignored `work/` artifacts absent from this
  managed worktree; no FD test failed. Full log SHA-256:
  `c15194356f71c095af09cac4767fe15fad139c20ec7a5d3ac44c19a8868662f1` at
  `work/sdf_directional_fd_v16_round2_retry_implementation/full_pytest.log`.
- **Qualified:** directional FD, field gradient, reverse mode, optimizer and
  shape update remain false/unqualified.
- **Open:** run the full suite, commit/push the retry source, register immutable
  round 2 from that clean source commit, stage and remotely verify dataset v2,
  then submit and host-verify one exact private T4 kernel version.

### 2026-09-29 centered directional-FD round 2 registered

This checkpoint supersedes the preceding implementation checkpoint's
`round 2 is not yet registered` status; that entry is retained as the prior
state.

The source retry commit `178792e9065df87d87ea1d445baaedace404304e` is pushed to
the canonical branch. From that clean pushed source, the registrar created
immutable round 2 before any FD primal ran:

- Criteria:
  [`sdf_directional_fd_v16_criteria_2026_09_round2.json`](evidence/sdf_directional_fd_v16_criteria_2026_09_round2.json),
  file/sidecar SHA-256
  `150a60232f1adb413fa7021833943c8effe5b91ef068909d4d9364112c248e1b`,
  canonical criteria SHA-256
  `91756109ce69fbe7c77cb0f18417f6d48619bb0020585db1aab7f8e891d19bfa`.
- Registered source commit: `178792e9065df87d87ea1d445baaedace404304e`.
- Kernel: `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel`.
- Input dataset identity remains
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle`.
- Round 2 references round-1 criteria file SHA `ad0bd7dc…` and submission
  diagnostic SHA `3cabf327…`. The registrar `--check` passed.
- A machine comparison reported no changes across geometry, primary responses,
  directions and their hashes, all 30 perturbations, run order, force and
  stationarity conditions, noise/plateau rules, backend, gates, or registered
  dataset payload. Round 2 only changes kernel identity/source binding and
  adds the explicit supersedes record.

**Status:**

- **Implemented:** the slug-conflict retry metadata, fail-closed round-2
  registrar, tests and documentation are committed/pushed.
- **Registered:** round 2 is immutable, `registered_not_run`, and bound to
  source commit `178792e…`; it precedes any GPU measurement.
- **Submitted:** dataset v1 remains ready; dataset v2 and the new kernel do not
  yet exist.
- **Measured:** no FD primal or `sim_step!` has run.
- **Verified:** registrar `--check` and the round-1/round-2 contract comparison
  passed. Focused tests: 24 passed. Full pytest: 1,141 passed, 37 failed,
  4 skipped; the 37 failures are existing checks blocked by missing ignored
  historical `work/` artifacts. Captured log SHA-256 is
  `c15194356f71c095af09cac4767fe15fad139c20ec7a5d3ac44c19a8868662f1`.
- **Qualified:** no directional-FD or gradient claim is granted.
- **Open:** commit this append-only round-2 criteria record, prepare the exact
  dataset from round 2, publish and remotely verify the new version, then
  submit one exact private T4 kernel and collect/host-verify that exact version.

### 2026-09-29 FD round-2 kernel version 1 host-preflight diagnostic

This entry supersedes the preceding round-2 registered checkpoint's
“dataset v2 and the new kernel do not yet exist” status. Round 2 remains
immutable and unchanged. Private dataset version 2 is `ready`; its remote
38-file payload was downloaded and all names, sizes and SHA-256 values matched
the round-2 local manifest. The remote inventory audit SHA-256 is
`223876dcef040be82ab80f5e6036220da38d21232efd1a0c134c928126b56e26`.

Exact private kernel
`ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/1` ended in
`KernelWorkerStatus.ERROR`. Kaggle fetched and checked out exact source commit
`178792e9065df87d87ea1d445baaedace404304e`; dataset criteria, sidecar and
manifest were present and verified by the runner. The runner reached
`host_input_preflight`, then raised:

```text
NameError: name 'phi_sha256' is not defined
```

The missing import occurs while assembling the canonical state identity
summary in `run_main`, before GPU inventory, Julia installation, CUDA smoke,
Julia job start or the first `sim_step!`. Runner execution state records
`solver_started=false`, an empty invoked-step list and stage
`host_input_preflight`. This is a runner/source integration failure, not an FD
measurement or a numerical gate result.

Exact captured artifacts (all under ignored `work/`):

- Status file SHA-256:
  `88172e3e7f3b67a7250a9e2621f23f0a57ac32d8d14122897884eb065196cfc9`.
- `kaggle kernels logs` response SHA-256:
  `f9dfe268c59efc836d6cd72641b459fca4f69cb538b62f85dc100096b2174563`.
- Downloaded raw kernel log SHA-256:
  `00e2811704d8bb560bf938b0b52ffd3e1ee36107f22ab025ecbf247ab76fb710`.
- `ERROR.txt` SHA-256:
  `1311692cc5419f0d4ac45682d1a43bf4514f516942fa32abcff21fd059fb1ca2`.
- Runner output manifest SHA-256:
  `41bbafba85e9ebea4a8d2726db574d1a45ef67b978c1fb58eb69d5311187812f`; all
  downloaded output files matched it.
- Execution-state SHA-256:
  `86bf0ed3e5b0d3f97dcfc913240b0e86f054f6b4c6699d579a0429108c17b5e2`.
- Mount inventory SHA-256:
  `73e3dc66c814f380c7e78f44060541200fbbd42eb463eb3a763edddb5498b0a5`.
- Output-download command capture SHA-256:
  `041f94f82ed412b8b91716a737964c50dbeaeb9793d2cda4d4ef2f3b4862ed2e`.
- Host verifier rejected the incomplete output for missing `DONE` and wrote
  append-only diagnostic
  [`sdf_directional_fd_v16_round2_kernel1_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round2_kernel1_diagnostic_2026_09.json),
  file/sidecar SHA-256
  `1c39d56953ef6e15979ea84bd2a5cca209af8689bb491be777d50e6f16a6d06a`.

- **Implemented:** round-2 runner source was the registered source; its missing
  `phi_sha256` import is isolated. No fix has been applied yet.
- **Registered:** round 2 criteria and dataset v2 remain immutable/preserved.
- **Submitted:** exact kernel `/1` ended `ERROR`; exact status, logs and output
  are recovered. No subsequent kernel version exists yet.
- **Measured / verified:** no Julia/CUDA setup, GPU inventory, solver step,
  FD response or host PASS occurred. The host diagnostic keeps all
  qualification flags false.
- **Qualified:** directional oracle, gradient field, reverse mode, optimizer,
  topology and shape update remain false.
- **Open:** add the missing import and a regression test; validate, commit/push
  the minimal fix, preregister round 3 against this diagnostic and unchanged
  numerical contract, upload/verify dataset v3, submit the next exact kernel
  version, and resume host verification.

### 2026-09-29 FD round-3 pre-registration runner repair

This checkpoint supersedes the preceding “add the missing `phi_sha256` import”
work instruction with a complete host-input identity scope repair. Round 2 and
its exact kernel `/1` diagnostic remain immutable.

- **Implemented locally:** `verify_canonical_and_preflight()` now returns one
  canonical identity object containing C-order phi SHA, Fortran-order phi SHA,
  measured canonical margin, and all four mask hashes. The new
  `build_state_identity_payload()` assembles that verified object with NPZ SHA,
  direction audit, and all 30 perturbation preflight rows. `run_main()` calls
  `host_input_preflight()` and writes the JSON payload before `gpu_inventory()`.
  It no longer reaches into local names from the nested preflight function.
- **Latent scope audit:** besides the observed `phi_sha256` failure, `run_main()`
  also previously referenced `zero_level_margin_m` and `mask_hashes` outside
  their defining function scope. These are returned through the same canonical
  identity object; this is not an import-only patch.
- **Regression / local preflight:** executable payload tests cover C/F hashes,
  margin, four mask hashes, direction audit, and perturbation details. An AST
  check requires host preflight and identity serialization before GPU inventory;
  a `symtable` audit finds no unresolved module-global names in runner function
  scopes. Using the exact round-2 dataset and a source archive at registered
  commit `178792e9065df87d87ea1d445baaedace404304e`, local criteria/dataset,
  source, W3/W4 prerequisite, canonical NPZ/C/F phi, margin, mask, three
  direction, 30 perturbation, and JSON assembly checks all completed. The
  helper stopped before GPU inventory.
- **Validation:** focused FD tests passed (`29 passed`). Python
  `compileall src tests scripts`, the four targeted `py_compile` files, Julia
  FD-job `Meta.parseall`, JSON parsing, and `git diff --check` passed. Full
  repository pytest reported `1,146 passed, 37 failed, 4 skipped` in `207.26 s`.
  The 37 failures are historical Stage T/S/V tests whose ignored `work/`
  checkpoints, meshes, solver logs, or case files are absent from this managed
  worktree; neither FD test file failed. Full log:
  `work/sdf_directional_fd_round3_source_validation/full_pytest.log`,
  SHA-256 `35b3ad1e7d8e3376679a975b486daa669594c4aefceb4db88d78ea2d5a5fc916`.
- **Registered:** immutable round 3 is registered at
  `docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round3.json`, file
  SHA `45fb570bc3628ff083d5cd34f496e352f6ec0834ac93f381909bef1c4d13f6c5`,
  sidecar SHA
  `517e9f5650f706ccfab84f1d8ca8812918197c158d81e74847e29c2b2edea3b7`, and
  canonical criteria SHA
  `fe49a91e5800460dc4560f453b72fd25f12158ecd4a099a1e940cbf434db8d52`. It
  binds source commit `9978eb4f19c716b9666c50c18261738edd978e4f`, round-2
  criteria canonical SHA
  `91756109ce69fbe7c77cb0f18417f6d48619bb0020585db1aab7f8e891d19bfa`, and
  exact round-2 `/1` diagnostic SHA
  `1c39d56953ef6e15979ea84bd2a5cca209af8689bb491be777d50e6f16a6d06a`.
  The registrar's machine comparison found the full measurement contract
  identical to round 2.
- **Dataset verified:** private dataset version 3 is `ready`. The staged
  manifest contains 37 registered payload files; the exact redownloaded
  mounted inventory has those 37 plus the manifest, and every path, size, and
  SHA-256 matches. Remote inventory SHA-256 is
  `1b74127038a414c39de72a681bc02f44661e27dfcae56e789cadf40091da3466`;
  dataset-verification evidence is
  `docs/evidence/sdf_directional_fd_v16_dataset_round3_verification_2026_09.json`,
  SHA-256 `aad6667f391543d78a338d089daf737203222e7ec54b4ffe871ffd740745d48c`.
  Running the exact round-3 `read_criteria`, `verify_dataset`, `verify_source`,
  `verify_prerequisites`, and `host_input_preflight` on that remote payload
  passed. It checked canonical state SHA
  `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`, C/F
  phi identity, four masks, three directions, and 30 perturbations, and stopped
  before `gpu_inventory()`.
- **Submitted:** the exact registered private T4 kernel
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/2` was returned by
  Kaggle and is `KernelWorkerStatus.RUNNING` (observed at
  `2026-09-29T07:56:16Z`). The push used the registered 14,400-second timeout.
  Append-only submission checkpoint
  `docs/evidence/sdf_directional_fd_v16_round3_kernel2_submission_2026_09.json`
  has SHA-256
  `379ad6ac7968109bbb7962afbfc03f5a1be8f8e9d6a7e6eed3f15d90c3db4629`.
- **Measured / verified:** solver start/progress is not yet observable from
  the current status/log/output response; do not infer `solver_started` from
  `RUNNING`. No terminal logs/output or host verdict are available yet. Round-2
  kernel `/1` remains preserved as `ERROR` with `solver_started=false`.
- **Qualified:** all FD-oracle, field-gradient, reverse, optimizer, topology,
  and shape-update flags remain false.
- **Source commit:** runner, tests, registrar round-3 support, and mutable
  draft identity are committed and pushed as
  `86087b888e7ea42033476bfcee9c8c7e888bb3cb`. The source tree is clean at that
  commit before the current documentation update.
- **Open:** collect terminal status, logs, and output for exact kernel `/2`,
  verify its output with the host verifier, and append a round-3 result or
  diagnostic. Stop at that verification boundary; reverse/adjoint, optimizer,
  shape update, and topology birth remain outside this work slice.

### 2026-09-29 FD round-3 kernel `/2` terminal pre-primal diagnostic

This terminal checkpoint supersedes only the earlier `/2` `RUNNING` status.
The round-3 criteria, round-2 diagnostic, and round-3 dataset verification
evidence remain immutable.

- **Registered:** exact round-3 criteria file SHA-256
  `45fb570bc3628ff083d5cd34f496e352f6ec0834ac93f381909bef1c4d13f6c5`,
  canonical SHA-256
  `fe49a91e5800460dc4560f453b72fd25f12158ecd4a099a1e940cbf434db8d52`,
  source commit `9978eb4f19c716b9666c50c18261738edd978e4f`; private dataset
  version 3 was ready and its 37 registered files matched by path/size/SHA.
- **Submitted:** Kaggle returned exact private T4 kernel
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/2`; it ended in
  `KernelWorkerStatus.ERROR` after about 328 seconds. Status SHA-256
  `87263620a40ab44e2deafcb0d99b5b15a7b0de047373bde7d6402e645d104174`.
- **Reached:** registered source commit was fetched and checked out. The full
  33-row run queue was read and validated; canonical NPZ/C/F hashes, CPU margin,
  masks, three directions and 30 perturbations were emitted. Julia project
  instantiate passed. The no-solver T4 smoke passed with Julia 1.12.6,
  CUDA.jl 6.3.1, CUDA runtime 12.8.0, driver API 13.3.0, WaterLily 1.8.0 and
  Tesla T4 inventory.
- **Failure locus:** exact `fd_v16.log` SHA-256
  `4632902eed4ebc6aad21f0100b4c81a13a7e9c883a5625d8351dbdda1dd2c3f8`
  reports `ArgumentError: 'src' and 'dst' refer to the same file/dir. This is
  not supported.` The registered Julia job attempted to copy
  `/kaggle/working/sdf_directional_fd_v16/run_queue.tsv` onto itself at line
  304, before `CUDA.memory_info()`, body/simulation construction, or the first
  `sim_step!`. Runner state is `stage=julia_job`, `solver_started=false`, with
  empty invoked/returned step lists and no Julia run/step markers. This is a
  Julia job pre-primal harness initialization failure, not package resolution,
  CUDA initialization, SDF transfer, WaterLily construction, force integration,
  or long-horizon integration.
- **Exact artifacts:** round-3 diagnostic
  `docs/evidence/sdf_directional_fd_v16_round3_kernel2_diagnostic_2026_09.json`,
  SHA-256 `4044e4f01508590f622e89194427af47c599d00959cf721a0f143b136d746fae`;
  exact `ERROR.txt` SHA-256
  `968da5e0f673790b2c250b60da07025c177525cb52a4ddc48ca868762c9a0dcf`;
  output `sha256.json` file SHA-256
  `51e1d939d4aeee1bb9eb1be6137be113f785252517de27d18ba4b6ba48a7be1f`;
  downloaded Kaggle kernel log SHA-256
  `b77bf9f207be08236ed90d9b4ed155257b7b936fdbac3cbbd87297ceccbd024d`;
  Kaggle logs-command response SHA-256
  `0201d4054bff91dea7f6ee03d8f1a9fc09e03d126bd6c976cc57db30af4e1822`;
  download response SHA-256
  `cb6330b63a951b06a3bf48da889f8cd555a0e1f79a14f04a7016c03add533c7d`.
  The output manifest is consistent; there are no force CSVs or `DONE` marker.
- **Host verified:** the strict verifier was run against exact dataset version 3
  and kernel `/2`; it failed closed before gate evaluation with
  `ValueError: FD Kaggle output has no DONE marker`. The verifier correctly
  grants no PASS. Append-only failure analysis
  `docs/evidence/sdf_directional_fd_v16_round3_kernel2_failure_analysis_2026_09.json`,
  SHA-256 `faf0f9b8100b02f303b029a3644cbf5c3df4e3e0a18d935014401142936c8596`,
  binds the exact Julia exception, stage and hashes.
- **Qualified:** FD oracle, flow16 FD, full gradient, reverse, optimizer,
  topology and shape update remain false. Round 3 is a pre-primal diagnostic;
  it is not a measurement result.
- **Open:** preserve this terminal diagnostic, move only the queue input file
  to the already available temporary `base` directory so it differs from
  `OUT/run_queue.tsv`, add a focused regression, validate and push the source,
  then register immutable round 4 against this exact round-3 diagnostic. Keep
  the 33-run contract, thresholds and all measurement semantics unchanged.
  Do not retry round 3 or submit a new kernel under its criteria.

### 2026-09-29 FD round-4 queue-path fix and immutable preregistration

This checkpoint closes the round-3 pre-primal queue-path defect and registers
the next immutable FD round. It does not start a dataset upload, Kaggle kernel,
or primal measurement.

- **Implemented:** the runner now writes the run-queue input to the existing
  temporary `base` directory. The Julia job continues copying that input to
  `OUT/run_queue.tsv`, so source and destination differ while the output
  snapshot remains available. Queue row serialization and registered run
  order are unchanged.
- **Regression:** an executable test builds baseline and perturbation rows in
  a temporary input directory and confirms the input path differs from the
  Julia output-snapshot path. Registrar tests bind the exact round-3 criteria,
  `/2` submission, terminal diagnostic, dataset verification, and failure
  analysis. A machine comparison requires the full round-4 measurement
  contract to equal round 3 and rejects a changed noise-resolution gate.
- **Validation:** focused FD tests passed (`32 passed`); Python `compileall
  src tests scripts`, targeted `py_compile`, Julia FD-job `Meta.parseall`, JSON
  parsing, and `git diff --check` passed. Full pytest reported `1,149 passed,
  37 failed, 4 skipped` in `211.37 s`. The 37 failures are historical tests
  whose ignored `work/` fixtures are absent in this managed worktree; all
  reported tracebacks are missing paths under `work/`, and no FD test failed.
  Full log is `work/sdf_directional_fd_round4_source_validation/full_pytest.log`,
  SHA-256 `54a56120fbbf9caf0ad84712a65e039027a27f101bda5dcaf186aef29130a805`.
- **Source commit:** the runner, tests, round-4 registrar, and mutable draft
  are committed and pushed as `8bf88756791213ac75b3c36ab6316323653d5c9a`.
- **Registered:** immutable criteria
  [`sdf_directional_fd_v16_criteria_2026_09_round4.json`](evidence/sdf_directional_fd_v16_criteria_2026_09_round4.json)
  has file and sidecar-content SHA-256
  `ace4e53963ee7d37d7806f48ef1ef449380294c0a5216043e50558f1d31192fd`,
  sidecar-file SHA-256
  `8e0ef570cba16e6964bc7d8763b41fe1fed8d2d69dcba841047e16f0b745494a`,
  canonical criteria SHA-256
  `949d998bb9e5b83ddbb2a24efc25b57754f4db29568e0a0f6e8b062647206db9`,
  and binds source commit `8bf88756791213ac75b3c36ab6316323653d5c9a`. Registrar
  `--check --round 4` passed. The exact round-3 criteria, submission, diagnostic,
  dataset verification, and failure-analysis hashes are bound in its
  `supersedes` record. Contract comparison passed: 3 directions, 30
  perturbations, 33 runs, and all registered measurement/gate semantics are
  unchanged.
- **Dataset / kernel:** private dataset version 4 has not been staged or
  uploaded. No new kernel version has been submitted, and there is no round-4
  primal measurement or host verification.
- **Qualified:** centered-FD oracle, flow16 FD, gradient field, reverse mode,
  optimizer, topology, and shape update remain false; `shape_update_allowed`
  remains false. Round 3 remains an exact pre-primal diagnostic.
- **Open:** prepare and remotely verify the next dataset version against
  round-4 criteria before submitting an exact T4 kernel. Preserve the round-3
  criteria and diagnostic; do not modify any measurement threshold.

### 2026-09-29 FD round-4 dataset verification and exact kernel `/3` submission

This checkpoint supersedes the preceding round-4 preregistration section's
dataset-not-uploaded and kernel-not-submitted state. Round-4 criteria remain
immutable and unchanged; this is an execution checkpoint, not a primal result.

- **Dataset v4:** private dataset
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle` reports `ready`. The
  redownloaded inventory contains 38 files (37 registered payload files plus
  the manifest). Every downloaded file matches the staged file by path, size
  and SHA-256, and the authenticated Kaggle file listing matches all names and
  sizes. Remote inventory SHA-256 is
  `ec9871eeaf6b95dec7f82b4a5eae902b649dd27cb6c81b1262cb450ec01738b5`; listing
  SHA-256 is
  `71b4a458676157f8172b152a0b0c9ccbe5093a639d02b4451dc737ccc10b770e`.
- **Host input preflight:** round-4 criteria and all 32 pinned source inputs,
  including the exact W3/W4 host-PASS prerequisites, verified. The downloaded
  dataset passed canonical state identity, C/F `phi` hashes, mask hashes,
  three direction hashes and all 30 perturbation checks. Canonical state SHA is
  `44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8`; its
  measured CPU margin is `0.3499999939931499 m`. Host GPU inventory was not
  called. Append-only dataset verification evidence is
  [`sdf_directional_fd_v16_dataset_round4_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round4_verification_2026_09.json),
  file SHA-256
  `e3f4fecde25f4161595deda684a2db7a9bd5d83298d299cf22f4745dda4831aa`,
  sidecar-file SHA-256
  `a6c306c572597d60217acb4f6150c79da67fe89a57d151f60de6790761a59c81`.
- **Submitted:** exact private T4 kernel
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/3` was submitted
  with the registered 14,400-second timeout. The append-only submission
  checkpoint is
  [`sdf_directional_fd_v16_round4_kernel3_submission_2026_09.json`](evidence/sdf_directional_fd_v16_round4_kernel3_submission_2026_09.json),
  file SHA-256
  `7906199306835e1da529b52313e7f27b7e18bf3665c091e6c4d099b340ee52bb`,
  sidecar-file SHA-256
  `af200d5aa3aced2e178b00fbef13ed96a2156c012962004b6cc1b10c19a153cb`.
  Exact-version status was `RUNNING` at `2026-09-29T09:35:27Z`; its logs
  response contained one newline byte. An earlier queued snapshot is preserved
  with its provenance, but its exact observation time was not captured. Solver
  start/progress remains unknown from these status and log responses.
- **Measured / verified:** no terminal kernel output has been collected, no
  primal measurement has been host-verified, and no round-4 result or
  diagnostic is yet recorded. Continue monitoring only exact `/3`; after it
  reaches a terminal state, collect that version's status, logs and output and
  run the registered host verifier. Do not submit a substitute version.
- **Qualified:** directional-FD oracle, flow16 FD, full gradient field, reverse
  mode, optimizer, topology and shape update remain unqualified; all registered
  qualification flags remain false.

### 2026-09-29 FD round-4 kernel `/3` terminal host-recompute failure

This checkpoint supersedes the prior `/3` `RUNNING` observation. Keep the
round-4 criteria and the exact `/3` terminal artifacts unchanged. Its 33
primal outputs are execution evidence from a failed runner invocation, not a
host-verified FD result and not a reusable fresh-primal run.

- **Exact terminal evidence:** private T4 kernel
  `ramhachi888/cfd-opt-sdf-v16-directional-fd-oracle-kernel/3` ended in
  `KernelWorkerStatus.ERROR` at `2026-09-29T09:51:47Z`. Kaggle terminal-log
  SHA-256 is
  `60c5b6d95f7522b8f868293424d3e5a78a99abe63030863c0e93157f7f185a3e`;
  exact status SHA-256 is
  `a41990c17fc9854c822b3459124dfa5b3139aed4edea17bfc51ee2eb92ee7836`.
  The immutable download contains 33 force CSVs, 33 summary JSONs, all 33
  ordered start/finish/step-invoked/step-returned markers, and no `DONE` file.
  The output SHA manifest is consistent. Aggregate solver wall time was
  `988.253036737442 s`; total job wall time was `1064.1104481220245 s`.
  These counts and timings describe completed calls only; they do not establish
  the registered output gates or a qualification result.
- **Host verification:** strict verification of those exact `/3` artifacts
  exited 1 with `ValueError: FD Kaggle output has no DONE marker`. The
  append-only diagnostic is
  [`sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json`](evidence/sdf_directional_fd_v16_round4_kernel3_diagnostic_2026_09.json),
  SHA-256 `f53ce0cf2784db810cdec39ba05448795010210e5e39e664810ae9f84527ded8`;
  its sidecar file SHA-256 is
  `01fe41f9c0dac90b43c64aacf75462af2fb2874143654f460bb72a48e7b47f4d`. The
  downloaded output-manifest file SHA-256 is
  `b23ed08c5692076d7532a210678d86a319cb1e2e098bd1643fb86cb15e4ec498`; the
  Kaggle output-download command response SHA-256 is
  `867001bb057671a403ff6e2fcec0b387466774d31256f9c91575c03bed5dea5f`.
- **Failure cause:** the exact source commit
  `8bf88756791213ac75b3c36ab6316323653d5c9a` includes the registered W4 result
  at SHA-256
  `87a881784dd42ef9c2c43ee78be761e8165e727f01df7d544765006d9c1b2fae`.
  Dataset v4's exact files, manifest and API listing were verified; source
  identity checks and the W3/W4 prerequisite checks passed in the kernel.
  In `infra/kaggle/kernel_sdf_directional_fd_v16/runner.py`, the `source`
  checkout lived inside `TemporaryDirectory`. The code left that context after
  Julia completed, then called `verify_runner(source, ...)`, which tried to
  reopen the W4 JSON beneath the now-deleted source directory. The resulting
  `FileNotFoundError` happened at `host_inside_runner_recompute`, after all 33
  solver calls.
- **Local repair / registration:** the runner now retains the already SHA-verified W4 result
  object in memory and passes it into `verify_runner`, so final recomputation no
  longer reads from a deleted temporary path. A focused regression copies the
  W3/W4 prerequisite files into a temporary checkout, verifies them, removes
  that checkout, and confirms the parsed W4 result remains usable. Round-5
  registrar plumbing binds the exact round-4 `/3` failure and requires its
  33-run evidence, but asserts that its outputs cannot satisfy a fresh run.
  Round-5 inputs retain the same state, masks, three directions, 30
  perturbations, 33-run order, T4 backend and numeric thresholds; no scientific
  criterion is changed. Focused FD tests passed (`22 passed`); `compileall
  src tests scripts` and `git diff --check` passed. Full pytest reported
  `1,151 passed, 37 failed, 4 skipped` in `199.91 s`; the 37 failures are
  existing tests requiring ignored `work/` evidence absent from this worktree,
  including PQ0/PQ3 and Stage S/V fixtures. No FD test failed.
- **Round 5 preregistration:** immutable criteria are locally registered at
  [`sdf_directional_fd_v16_criteria_2026_09_round5.json`](evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json),
  file/sidecar-content SHA-256
  `2aad32922b2746d9ee7b170b590673779e60f032b238c29d1bc7ca6b2779ee17`,
  canonical criteria SHA-256
  `afb87dc75538c1970cc332711ae638f33fe417df68e018e61f70824e77b7a4ac`,
  bound source commit `a07bba2fd1dcf0d3d28b211eef58d91309a24a75`. It supersedes
  the exact round-4 `/3` failure evidence without editing round 4.
- **Local dataset v5 candidate:** staged at
  `work/kaggle_sdf_directional_fd_dataset_round5/`. All 35 canonical-state,
  phi, direction and perturbation inputs are byte-identical to the locally
  staged v4 inputs whose manifest SHA matches the remote-verified round-4
  record. Exact criteria, source inputs, W3/W4 prerequisites, canonical state,
  three directions and 30 perturbations passed host checks against a simulated
  mounted inventory; GPU discovery was not called. Candidate manifest SHA-256
  is `c2aa1360263d04bd8d61d9079b7d3e644fd35e2551d1715d91bf0199e09f003e`.
  Append-only local-stage record
  [`sdf_directional_fd_v16_dataset_round5_candidate_verification_2026_09.json`](evidence/sdf_directional_fd_v16_dataset_round5_candidate_verification_2026_09.json)
  SHA-256 is
  `079581ea1f9df6cca37b44223b1f0f1d79f9c961569daf70d29a56ef833235ae`.
- **Dataset/run gate:** dataset v5 has not been uploaded or remotely verified,
  and no successor kernel has been submitted. Both remain gated on the user's
  explicit answer about versioning the append-only registration/source identity
  update. Do not overwrite/relabel `/3`, modify rounds 1–4, or reuse `/3`
  outputs for a new 33-primal execution.
- **Qualified:** round 4 remains failed, and the directional-FD oracle,
  flow16 FD, field gradient, reverse mode, optimizer, topology and shape update
  remain false. `shape_update_allowed=false` remains a hard stop.
