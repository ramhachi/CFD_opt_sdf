# OpenCode Handoff: CFD2026_09

Status: repository-local working memory for a fresh OpenCode session
Snapshot date: 2026-09-22
Scope: generic rigid-object external aerodynamics with density/Brinkman topology,
SDF handoff/refinement, and independent body-fitted verification

This document externalizes the current implementation context. It is not a
second roadmap. Read it with the authoritative documents below; do not replace
their decisions with this summary.

## Read Order and Authority

For a fresh terminal, read in this order:

1. [`../AGENTS.md`](../AGENTS.md) for repository-local OpenCode rules.
2. [`README.md`](README.md) for the documentation map and compatibility policy.
3. [`phase_plan.md`](phase_plan.md) for the sole roadmap, status, and execution order.
4. [`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md) for the current post-PQ3.3 execution detail.
5. [`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md) for the adopted detailed downforce architecture.
6. [`problem_register_2026_09.md`](problem_register_2026_09.md) for the P1-P20 issue ledger and artifact semantics.
7. [`problem_resolution_plan_2026_09.md`](problem_resolution_plan_2026_09.md) for detailed implementation slices and older resolution instructions.
8. [`problem_contract_v2.md`](problem_contract_v2.md) and [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) for schemas.
9. [`git_branching_strategy.md`](git_branching_strategy.md) for branch workflow.

The authority split is intentional:

- `docs/phase_plan.md` remains the sole roadmap, status, and execution-order authority.
- `docs/problem_register_2026_09.md` remains the issue ledger, including P1-P20 and the measured contradictions.
- `docs/problem_resolution_plan_2026_09.md` is a detailed implementation record, subordinate to the latest phase-plan order.
- `docs/problem_contract_v2.md` is the user/problem schema authority.
- `docs/fixed_grid_data_contract_v2.md` is the Stage T artifact-schema authority.
- `docs/evidence/*.json` is machine-readable evidence; prose must not broaden its scope.

**2026-09-23 current addendum:** Preflight v5 corrected the b=4 objective-state
carryover into b=8 and the cached-noise-repeat error. It found that b=8 trial
improvement was real but the centered Path B minus perturbation crossed an
exact design box face. Preflight v6 freezes those face cells during Phase 2;
the unchanged centered Path B and real trial accepted one step at each b=4,
b=8 and b=16 level with exact state lineage. This is preflight feasibility,
not multi-iteration convergence or Stage S qualification. The previous v3
manifest remains blocked. Manifest v4 and its runner were registered for a
later long run; read-only preconditions passed at SHA-256
`01d40d48ebe12f73e66ab646ed51c1cce611b28901f6cc7ee7564abed2753484`.
No long optimization run has been started. Follow the
latest `phase_plan.md` and v6 evidence rather than the older snapshot below.

## Snapshot and Git

The base snapshot before this documentation commit was:

| Item | Value |
| --- | --- |
| Active branch | `feat/p0-openfoam-closed-loop` |
| Base snapshot before this documentation commit | `82915e9f778098f4e0b983efdfa5f65a4f3b915b` |
| Short commit | `82915e9` |
| Commit subject | `Qualify V3 and harden Stage V execution` |
| Upstream | `origin/feat/p0-openfoam-closed-loop` at the same commit |

The commit, branch, and upstream values above are historical handoff metadata.
Every fresh session must trust live `git status` and `git log` (and the current
diff) over this table.

Reference and preservation refs observed at handoff creation:

| Ref | Commit | Meaning |
| --- | --- | --- |
| `origin/artifact/pre-cross-platform-architecture-2026-09-09` | `fdc105343c275b9fe80c2c9d8ea6b9eca3cb7287` | Preserved `main` snapshot immediately before the cross-platform architecture decision. |
| `origin/main` and local `main` | `bdf65333f78948068cf0038ed7f099c2f034edbb` | Integration baseline. |
| `origin/feat/cross-platform-lbm-foundation` and local branch | `5e09cb779925fe7286bd861353d45128b9867182` | Separate cross-platform research foundation line. |
| `origin/feat/g2-front-wing-geometry-contract` | `a33753c03ac1414cf4ebe0fbe4af1d06c10b68b7` | Separate historical geometry-contract line. |

The evidence JSON for the latest V3 run has its own historical metadata:
`base_head=938c42b41ec1bad074072f8a5ed9519f3d4115f9` and
`working_tree_dirty_when_recorded=true`. That metadata describes the evidence
recording context, not this current repository snapshot. Do not rewrite it.

For a normal authorized implementation or documentation task, follow
`AGENTS.md`: after validation, commit and push only the intended files to the
current feature branch. Explicit review-only, no-edit, or no-push instructions
are exceptions. Never force-push, reset, checkout, or overwrite unrelated work.
Inspect status and diff before any later implementation work.

## Exact Current Architecture

**2026-09-22 addendum 7 (PQ3.3 complete; Stage S entry still closed).** The live
baseline before this planning update is `db20610`, pushed on
`feat/p0-openfoam-closed-loop`. PQ0.1/PQ0.2 integrated the reduced downforce +
projected-volume path, real parent/trial OpenFOAM oracle, accepted-primal reuse,
Path B centered-FD bracket, rollback and resume. PQ1.1 measured the refined
source mesh gate as pass and retained Path B; canonical-only refinement exposed
design/source-grid coupling, and the registered third source-grid campaign is
not run. PQ3 accepted three real OpenFOAM improvement steps.

PQ3.1 reached solver-field discreteness but failed extraction coherence. PQ3.2
showed that an upper volume bound did not fill material before projection.
PQ3.3 added a raw-design volume-target OC proposal: its b=0 state reached
objective -2.727 and projected volume 0.02745, but b=8/b=16 reduced projected
volume to 0.01469/0.01302 and b=16 accepted no steps. The final solver field
passed the registered global discreteness metrics (mean_nd 0.00388, max
0.94395), while the composite Stage S verdict stayed false.

Before running PQ3.3b, correct a semantic confounder. The adopted geometry and
volume field is pre-RAMP `rho_projection`, while the current handoff contoured
RAMP output `beta_solver` at thresholds 0.4--0.6. With q=100, beta=0.5 means
projection about 0.9902. First reconstruct and hash all four fields, contour
`rho_projection`, and record a correction artifact without overwriting the raw
PQ3.3 evidence. In parallel, repair the self-intersection, component-gap,
minimum-width and volume-calibration measurements in the composite gate. Then
preflight and preregister a projected-volume-target backend. The controlling
plan is `stage_t_to_stage_s_bridge_plan_2026_09.md`; do not start Stage S or a
long PQ3.3b run before its Work A--C exit gates pass.

**2026-09-22 addendum 6 (PQ0/PQ1 implementation complete; superseded by
addendum 7 for current status/order).** The historical baseline is `1d40463`. PQ1 refined the source
grid from 32x16x16 to 64x32x32 and tightened perturbation residuals. The
FD/adjoint ratios are now 1.1504/1.1134/1.1441 with stable epsilon plateaus:
all directions moved toward one, but all still fail the 5% production gate.
This is a Path B bounded exception on one refined grid, not grid convergence;
only two source-grid levels exist and the base mesh gate is unmeasured.

PQ0's component implementation is retained, but code inspection found that
the nonlinear loop does not consume `CompiledProblem.volume_constraint`, its
nominal value/gradient adapter can rerun one primitive evaluator instead of
reusing the accepted primal artifact, and trial adjoint semantics plus the
Path B centered-FD bracket are not integrated. The real P0 audit fixture is an
unconstrained `drag - downforce` problem. It does not qualify the next
downforce-plus-volume reduced problem.

The then-immediate slice was PQ0.1: connect projected volume to the nonlinear path,
split primal and adjoint callbacks with artifact reuse, make trial adjoint
not-applicable and parent adjoint fail-closed, add per-proposal centered FD
bracketing, and disambiguate projection output from solver beta. Then run the
minimal real OpenFOAM oracle smoke (PQ0.2). The registered PQ2 V2
domain/boundary campaign could run independently. This instruction is historical;
the current stop/go order is in addendum 7 and the bridge plan.

**2026-09-21 addendum 5 (DF0--DF6 component implementation and post-implementation
plan; superseded for current status/order by addendum 6).** DF0--DF6 supplied
the P18 audit/re-judgment, ProblemSpec compiler,
DesignTransform, frozen-design P6 campaign, nonlinear merit/trust controller,
restartable loop, extraction sweep, Stage S drag sensitivity ingestion,
required-pair verification algebra and robust-three-field prototype. Treat this
as component/capability completion, not a production OpenFOAM optimiser.

Two measured blockers now control the work. P6 is a stable solver-side
continuous-adjoint/discrete-primal mismatch: FD/analytic is 1.2178 aligned and
1.3764/1.5680 on two random directions; transfer, design movement and primal
residual tolerance are exonerated. In Stage V, `linearUpwind` qualifies drag at
0.364% finest-transition drift, while downforce stays non-monotone at 0.010374
against the 0.005 bound. The registered next Stage V factor is domain/boundary.

P18 is closed only as a fixed-shape diagnostic: the eight-shape downforce set
still passes with candidate-specific bands (25 resolvable pairs, zero
inversions), while the combined 17-shape pool remains unresolved for both
responses. The current detailed plan is PQ0--PQ6 in
`downforce_optimization_architecture_plan_2026_09.md`: integration closure,
gradient qualification, Stage V reference qualification, first real closed
loop, Stage S, independent verification, then production backend/target
physics. Do not resume from the stale "next DF0" instruction below; it is a
historical addendum.

**2026-09-20 addendum 4 (adopted downforce plan and WP6-2 scope audit).**
The retained architecture and its qualification sequence are now specified in
`downforce_optimization_architecture_plan_2026_09.md`; `phase_plan.md` remains
the sole execution-order authority. A repository-level audit found that the
WP6-2 eight-shape no-inversion result is a positive fixed-shape observation,
not yet a universal minimum-width-policy qualification: its manifest mixes
`>=0.15 m` and `>=0.10 m`, composite parts include features below `0.15 m`, the
combined 17-shape machine verdict is `unresolved` for both responses,
extraction sensitivity is unmeasured, and candidate-specific V1-to-V2 drift can
exceed the inherited uncertainty band. P18 records this evidence-applicability
gap. The next slice is DF0 evidence/preregistration repair, followed by the
ProblemSpec compiler and unified DesignTransform; do not start by tuning the
optimizer or replacing Stage T.

**2026-09-20 addendum 3 (WP6-2 reachable-set program; scope corrected by
addendum 4).** A second pre-registered eight-candidate ranking produced exact
downforce ordering agreement with qualified anchor-STL Stage V at V1 and V2
(tau 1.000), and the combined 17-shape pool contained no resolvable sign
inversion (`evidence/reachable_set_cross_fidelity_ranking_2026_09.json`). These
are positive fixed-shape observations. The earlier conclusion that P1 was
fully contained to a sub-policy one-cell thickness axis is superseded by
addendum 4/P18: the registered width boundary is inconsistent, composite
features cross it, combined verdicts remain `unresolved`, and the uncertainty
scope is incomplete. Absolute magnitudes also remain uncalibrated. Composite
analytic shapes (`ShapeDefinition.parts`) remain valid diagnostic assets.

**2026-09-20 addendum 2 (WP4 completion + WP5/WP6 decisive experiment).** Gate 0
is complete for the wired paths: C1 semantic binding now records the response's
global direction, referencing objectives/constraints, canonical objective sign,
and value units into gradient-export provenance and refuses non-force,
direction-less, no-consumer, and mixed-sense responses
(`evidence/` commit "Complete Gate 0 response semantics"; P7 closed earlier).
The decisive WP6 experiment then ran (`evidence/fixed_shape_cross_fidelity_ranking_2026_09.json`,
pre-registered in `evidence/fixed_shape_ranking_manifest_2026_09.json`): 10
analytic binary shapes evaluated same-grid on T1 (alphaMax 2500, q=0, no
transfer/filter/optimizer) against anchor-STL qualified Stage V at V1+V2 with
the fixed domain. At the pre-declared uncertainty (downforce abs 0.0147, Cd rel
0.034 — carried verbatim per the P16 band): **downforce = no_go** (one
resolvable inversion on the thickness axis, surrogate +0.232 vs reference
-0.034) and **drag = unresolved with 37/37 agreeing signs**. Per stop rules,
the optimizer must not be tuned to reverse this; the registered continuation is
a Stage T surrogate reformulation study for the thickness axis (T2 refinement
as one registered factor), not more reduced-case digging. New modules:
`src/cfd_sdf/analytic_candidate_shapes.py` and `src/cfd_sdf/cross_fidelity_ranking.py`.

**2026-09-20 addendum (post-WP1 slices).** WP1 (fixed-domain binding plus the
`stage_v_clearance_v1` pre-mesh clearance preflight) is implemented, tested
(`tests/test_stage_v_domain_preflight.py`), and evidenced in
`evidence/stage_v_domain_clearance_2026_09.json`. A follow-up fixed-domain grid study
plus a pre-declared near-wake refinement family ran on the correct
candidate (`evidence/stage_v_fixed_domain_grid_study_2026_09.json`): V1/V2/V3 are
profile-qualified under the fixed domain, the finest downforce drift improved to
0.01291 / 0.01470 (plain / wake) but the 0.005 bound remains unmet, and the
factor-isolation result refutes wake resolution as the drift driver. All historical
union-box force values, ratios, and P16 drifts are not transferable. Next pre-declared
slice: steady vs time-resolved comparison on the plain fixed-domain V2 mesh
(WP3 fallback). remaining details live in that evidence file and the updated
`phase_plan.md`/`problem_register_2026_09.md`.

The adopted production direction is:

```text
ProblemSpec v2
  geometry roles + flow cases + responses + objectives + constraints + topology policy
        |
        v
Geometry and resolution preflight
        |
        v
OpenFOAM case compilation + requested/generated manifest
        |
        v
Stage T: fixed-grid density/Brinkman topology exploration
        |
        v
Density iso-surface -> SDF rebuild and handoff checks
        |
        v
Stage S: sharp-interface SDF refinement
        |
        v
Stage V: independent body-fitted RANS verification
```

The product profile is deliberately bounded: incompressible low-Mach external
flow, steady or quasi-steady analysis, one rigid material, STL geometry roles,
uniform Cartesian fixed-grid topology, SDF extraction/refinement, and
body-fitted verification. Compressible, fully unsteady, fluid-structure,
free-surface, and production AMR profiles are not current capabilities.

The design variable in Stage T is the cell density field `rho`. An STL is an
input surface or a derived exchange/verification artifact, not the primary
topology design variable.

The current implementation roles are more specific than the architecture
diagram:

- `src/cfd_sdf/problem_spec.py` loads ProblemSpec v2, canonicalizes and hashes it, supports read-only v1 migration, and already accepts explicit `grid.domain_bounds_m` for a uniform Cartesian canonical grid.
- The ProblemSpec contains SI units, a coordinate frame, typed geometry roles (`fixed_solid`, `initial_design`, `design_domain`, `forbidden_region`, `root`), flow cases, responses, objectives, aggregate constraints, and topology policy.
- `src/cfd_sdf/openfoam.py` adapts a v2 spec to the current body-fitted Stage V case generator, maps geometry roles, derives force normalization from declared reference values and response directions, and renders blockMesh/snappyHexMesh/OpenFOAM files.
- The current Stage V adapter still derives the generated field/case bounds from the `FieldBundle`; it does not yet bind the outer CFD box to the ProblemSpec domain or preflight candidate-to-boundary physical clearance.
- Stage T optimization has moved to Python permanently. OpenFOAM is retained as a primal and adjoint evaluator; the native ISQP optimizer is not the production optimizer.
- `scripts/stage_t_filtered_ramp.py` implements the current research prototype for a mask-aware filter, projection, RAMP interpolation, gradient pullback, candidate export, and one-level-at-a-time Stage V execution. Its `selftest` checks filter adjoint identities, a synthetic chain rule, block-filter behavior, and the Stage V preflight artifact. It does not implement the missing far-field clearance gate.
- `src/cfd_sdf/execution.py` supports `local`, `wsl`, and `docker` backends plus `auto` selection. It defaults to a dry run, records `openfoam_run_summary.json`, and removes its exact named Docker container after timeout/error or Ctrl-C.
- A bounded periodic D2Q9 Taylor-Green CPU/Apple Metal reference exists under `research`; it has no walls, aerodynamic force, SDF, adjoint, or topology support and is not a target-aerodynamics solver.

The intended Stage T chain for the verified canonical loop is:

```text
canonical rho (46080 cells)
    -> P @ rho
    -> OpenFOAM source state (8192 cells)
    -> active-cell injection
    -> converged primal and adjoints
    -> topOSens
    -> P.T @ topOSens
    -> canonical gradient (46080 cells)
```

The measured canonical grids are target `60 x 32 x 24`, origin
`(-1.0, -0.8, -0.6)`, spacing `0.05`, and source `32 x 16 x 16`, origin
`(-1.0, -0.8, -0.6)`, spacing `(0.09375, 0.1, 0.075)`. The source and target
cover the same region. The cell-order result was measured with
`writeCellCentres` and was identity for this mesh; it was not assumed without
measurement.

## Evidence Taxonomy

Every result must carry one or more of these evidence classes, with the input
hashes and artifact paths that support the label:

| Evidence class | What it proves | What it does not prove |
| --- | --- | --- |
| Contract | Schemas, IDs, hashes, bindings, and validation agree. | Solver correctness or physical validity. |
| Capability | A backend operation runs on a canonical fixture. | Target physics, optimization quality, or generality. |
| Numerical | Residual, mass-balance, stationarity, gradient, or grid gates pass for the declared case. | Target operating-point qualification or a benchmark ladder. |
| Target physics | The declared operating point and physics pass the required cross-fidelity checks. | Full-vehicle or high-Re extrapolation. |
| Benchmark | A configured geometry family passes its complete pre-registered acceptance set. | Any untested geometry family or later product profile. |

`execution_ready=true` means declarations are complete enough for the contract;
a capability or contract result must never be reported as target-physics
validation.

## Verified Current State

### Contract and canonical loop

- G1 ProblemSpec/artifact contract is complete for the current v2 scope: canonical hashes, multipoint responses, topology policy, v1 read-only migration, and semantic readers exist.
- G2 case compilation and the prior two-flow numerical convergence gate passed under the current specification hash. Native v2 artifact readiness remains blocked by response units, gradient convention, mesh-grid mapping, and topology-policy-value bindings.
- The real OpenFOAM canonical loop was executed and its gradient direction finite-difference check passed at roughly 1% over the recorded converged runs. This is numerical/capability evidence for the reduced fixed-grid fixture, not a qualified production optimizer.
- `top_o_sensitivity_gradient` is the derivative of `+downforce`; project objective `J = -downforce` uses the opposite sign. A consumer must not silently reinterpret the array.
- A generic localized direction retains an approximately 0.90 directional-derivative ratio. The likely non-integer overlap-transfer cause remains unverified; those rows are not a pass/fail production gradient gate.

### Stage T and Stage S

- Native ISQP was diagnosed as unsuitable for the current topology formulation. Python-side optimization is the permanent decision, while the OpenFOAM template remains a primal/adjoint evaluator.
- The original native Stage T template was degenerate: `downforce` was an equality constraint at zero, the volume constraint was unsatisfiable with the forced-fluid buffer, and `function linear` did not sharpen the field. Its zero-material iso-surfaces are historical diagnostic artifacts, not designs.
- Python RAMP plus single ownership of projection produced non-degenerate candidates and an accepted Stage S handoff for a real shape in the recorded experiments. This does not finish Stage S qualification.
- The current V3 candidate record still reports 320 grey physical-beta cells and `mean_nd_4x(1-x)=0.012923593604948222`; therefore this candidate is not evidence that the complete Stage S discreteness gate is closed.
- Stage S currently performs density-to-surface/SDF conversion and diagnostics. Hamilton-Jacobi evolution, reinitialization, curvature control, a shape gradient, and a qualified sharp-interface solver are missing.

### Stage V profile

The registered profile is `stage_v_qualification_v1`:

- `checkMesh -allGeometry -allTopology` is parsed and judged fail-closed except for the pre-registered `Concave cells` marker within the fixed fraction and angle limits.
- `simpleFoam` must report explicit `residualControl` convergence; reaching `endTime` is not convergence.
- Cd uses a relative grid bound of `0.02`; downforce uses an absolute grid bound of `0.005`.
- Force stationarity is checked over the final window, with Cd relative and downforce absolute bounds.

### Correct qualified V3 candidate

The correct candidate is the P15 thickness comparison candidate:
`opt_q100_b0_step0_try0_block`. It is distinct from the rejected `keep_round`
candidate below. The evidence record is
[`docs/evidence/stage_v_v3_requalification_2026_09.json`](evidence/stage_v_v3_requalification_2026_09.json).

The exact V0-V3 force values recorded for the correct candidate are:

| Level | Cells | Voxel size (m) | Cd | Downforce | Stage V qualification |
| --- | ---: | ---: | ---: | ---: | --- |
| V0 | 6387 | 0.1 | 2.6852755538235296 | 0.6144589883823529 | pass |
| V1 | 31710 | 0.05 | 3.013965840967742 | 0.6814595404193549 | pass |
| V2 | 184518 | 0.025 | 3.1401020073469383 | 0.8230957941785714 | pass |
| V3 | 1260201 | 0.0125 | 3.130092692110912 | 0.8530209294007155 | pass |

Exact V3 execution measurements:

| Measurement | Value |
| --- | --- |
| Candidate ID | `opt_q100_b0_step0_try0_block` |
| Solver termination | `residual_control_met` |
| Solver iterations | `2237` |
| Final residual Ux | `1.498624e-07` |
| Final residual Uy | `9.9822172e-07` |
| Final residual Uz | `3.0145397e-07` |
| Final residual p | `6.0918935e-07` |
| Minimum determinant | `0.027125156` |
| Small-determinant cells | `0` |
| Reported raw failed-check count | `1` |
| Raw failed-check line | `Concave cells (using face planes) found, number of cells: 12384` |
| Raw mesh flag | `raw_mesh_ok=false` |
| Registered mesh-profile result | `mesh_profile_qualified=true` |
| V3 Cd | `3.130092692110912` |
| V3 downforce | `0.8530209294007155` |
| Cd final-window standard deviation | `1.8604752067213488e-06` |
| Cd final-window drift | `6.302194224349831e-06` |
| Downforce final-window standard deviation | `9.04532196315453e-07` |
| Downforce final-window drift | `3.0846565806368277e-06` |
| Final-window size | `559` |
| Solver qualification | `true` |
| Force stationarity qualification | `true` |
| Stage V qualification | `true` |

The V3 solver execution time was `4815.07` seconds and the recorded solver
clock was `4847` seconds. Case size was `466` MiB and observed peak case
generation RSS was `9.4` GiB on an Apple M4 with 32 GiB host memory. These are
measurements for this run, not a machine-independent performance guarantee.

The finest transitions are also exact evidence:

- Cd V2 -> V3 relative change: `0.0031875764585377804`, profile status `pass`.
- Downforce V2 -> V3 absolute change: `0.029925135222144128`, profile status `fail` against `0.005`.
- `grid_convergence.Cd.converged=false` because earlier transitions also exceeded their bound.
- `grid_convergence.downforce.converged=false`.
- Decision field: `grid_independent_downforce_reference="not established"`.

The correct V0-V3 raw logs each report `Failed 1 mesh checks.` because the
registered profile allows the concave-cell marker within its pre-registered
bounds. This is a qualification pass under the profile, not a raw clean
`checkMesh` pass. Never shorten it to "mesh clean".

### Distinct rejected wrong candidate

The first V3 attempt used a different candidate:
`opt_q100_b0_step5_try1_block_keep_round`. It is not comparable to the correct
candidate, and P15 ratios must not be assigned to it.

The evidence record reports:

- candidate `zmax_m = 0.4000000059604645` and blockMesh top `z = 0.4 m`;
- all `220` V3 under-determined cells touched the candidate patch;
- `208` of those cells also touched the `top` patch;
- V3 had `220` small-determinant cells, `17936` concave cells, and `1235875` total cells;
- the candidate had the same small-determinant failure at V0/V1/V2: `67`, `123`, and `1046` cells;
- the conclusion was candidate-to-far-field clearance violation, not a reason to waive quality thresholds.

Its diagnostic artifacts are:

- `work/filtered_ramp/wmin_0.2/stage_v_mesh/opt_q100_b0_step5_try1_block_keep_round/V3/log.checkMesh`
- `work/filtered_ramp/wmin_0.2/stage_v_mesh/opt_q100_b0_step5_try1_block_keep_round/V3/stage_v_level_preflight.json`

This historical failure is now caught before meshing by the fixed ProblemSpec
far-field binding and `stage_v_clearance_v1` preflight. The evidence remains a
useful negative fixture; do not "fix" it by relaxing mesh thresholds.

## Implemented Versus Missing

### Implemented or measured

- PQ0.1: compiled projected-volume value/gradient, parent-adjoint/trial-primal
  separation, accepted-primal reuse, Path B centered-FD bracket and semantic
  naming for the reduced downforce problem.
- PQ0.2: real OpenFOAM parent/trial/bracket/rollback/resume capability trace.
- PQ1.1: refined source mesh gate and canonical-parameterization factor.
  Path B remains; the third source-grid campaign is registered but not run.
- PQ3: three accepted real-OpenFOAM improvement steps.
- PQ3.1--PQ3.3: production-regime continuation experiments. PQ3.3 reaches the
  registered solver-field discreteness metrics but no qualified Stage S handoff.
- PQ4.0: composite `ready_for_stage_s` conjunction and fail-closed threshold
  selection.
- Fixed Stage V domain/clearance preflight, qualified fixed-domain grid runs,
  transient screen and convection-scheme factor campaign.
- Drag reference qualification with `linearUpwind` on the measured candidate.

### Missing or not qualified

- A terminal b=16 Stage T candidate with an accepted, converged optimization
  history and stable projected volume.
- Correct Stage S materialization from `rho_projection`; current PQ3.3 handoff
  contoured RAMP `beta_solver` at unmatched thresholds.
- A projected-volume target proposal with explicit active-mask ownership,
  reachability bracketing and final residual verification.
- Fail-closed self-intersection, component-gap and minimum-width measurement,
  plus a volume-fidelity profile supported by its own calibration artifact.
- `ready_for_stage_s=true` on an optimizer-generated candidate and FD-qualified
  drag/downforce Stage S surface derivatives.
- Stage V downforce grid qualification; `linearUpwind` drift is 0.010374 against
  0.005 and non-monotone. The domain/boundary factor is registered but not run.
- Three-grid baseline/T/S required-pair verification, actual MMA/GCMMA,
  robust-three-field closed-loop integration, target-Re/full-vehicle evidence,
  and Windows RTX 4070 Ti CUDA/VRAM qualification.

## P1-P20 Issue Ledger Summary

The detailed and current issue statuses are in
[`problem_register_2026_09.md`](problem_register_2026_09.md). The issues that
control the immediate work are:

| ID | Current status and unresolved point |
| --- | --- |
| P2 | `beta_solver` passes the registered global discreteness metrics, but b=16 has no accepted step and extractable geometry is not established. |
| P4 | Closed for the bounded reduced downforce + projected-volume path; no production or target-physics generalization. |
| P6 | Path B. Refined-source ratios 1.1504/1.1134/1.1441 remain outside 5%; canonical-only refinement exposes design/source-grid coupling. |
| P13 | Parent/trial oracle and artifact-reuse contract is closed for the bounded path. Gradient accuracy remains P6. |
| P16 | Drag drift passes with `linearUpwind`; downforce drift 0.010374 remains above 0.005 and non-monotone. |
| P18 | Closed only for the fixed-shape diagnostic; optimizer-generated ranking remains open. |
| P19 | Open. Raw-design volume target and RAMP-field handoff do not match projected-volume and geometry semantics. |
| P20 | Open. Self-intersection, gap, minimum-width and volume-calibration measurements need fail-closed repair. |

### Contradictions that must remain visible

- Stage T's bounded real closed loop does not imply a production-qualified
  gradient or an optimizer-generated Stage S candidate.
- `discrete_candidate=true` in PQ3.3 is a solver-field scalar-gate result; it is
  not equivalent to spatially coherent, extractable geometry.
- The recorded PQ3.3 beta-field sweep is valid as a diagnostic of that field,
  but not as the adopted `rho_projection` threshold sweep.
- Stage V V0--V3 qualification for one reduced candidate does not imply
  downforce grid convergence, target physics, or ranking qualification.
- Current Stage V evidence is steady incompressible laminar at the reduced
  operating point. Do not call it RANS or extrapolate it to FSAE high-Re vehicle
  aerodynamics.

## Issue-Driven Next Implementation Plan

The latest `phase_plan.md` order controls. The complete post-PQ3.3 criteria are
in [`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md).

1. PQ3.3a: reconstruct and hash all four fields; re-extract from
   `rho_projection`; add an immutable PQ3.3 correction artifact.
2. PQ4.0a: repair and calibrate self-intersection, gap, minimum-width and volume
   measurements.
3. Projected-volume target preflight: implement the correct measure, prove
   move-box reachability at each planned continuation level, and preregister
   targets and stopping criteria.
4. PQ3.3b: run level-local real-OpenFOAM reoptimization only after the preceding
   exit gates pass.
5. PQ4.1: require the full composite gate on the terminal candidate.
6. Only then qualify drag/downforce Stage S surface FD and accept at most one
   shape step.
7. PQ2 may run independently; PQ5/PQ6 remain after the Stage S bridge.

Do not start the long PQ3.3b campaign or Stage S from the current
`ready_for_stage_s=false` artifact.

## 2026-09-23: PQ3.3b preflight v4 / manifest v3 current status

- Evidence retained unmodified: preflight v1/v2/v3, the blocked manifest and
  campaign manifest v2 (all diagnostic).
- Preflight v4 (append-only `docs/evidence/pq3_3b_preflight_v4_2026_09.json`)
  pins the canonical objective route
  `ProblemSpec -> compile_problem -> make_oracle_from_compiled ->
  evaluate_parent -> OracleResult.objective_gradient` (J = -downforce, sense
  sign -1) and forbids passing raw OpenFoamOracle response gradients to
  Phase 2 backends (structurally rejected).
- v4 removed the v3 simulated-decay switch, but its b=8 input used the b=4
  restoration rho rather than the b=4 objective-accepted rho. v5 corrected
  this lineage error.
- Phase 2 uses the registered alpha ladder (1.0/0.5/0.25/0.125/0.0625) with the
  full gate set (Path B centered bracket, real trial primal, canonical
  objective improvement, raw downforce improvement, mask invariance,
  move-box zero-violation, projected volume <= Vmax).
- Measured v4 outcome: b=4 Phase 2 accepted alpha=1.0 (downforce 0.6703 ->
  0.8434 at its fresh parent); b=8 failed and the chain stopped before b=16.
  The per-alpha b=8 ledger was discarded on exception, so its directional
  signs cannot be established from that artifact. See the current addendum
  and v5/v6 evidence for the subsequent diagnosis.
- Manifest v3 `docs/evidence/pq3_3b_campaign_manifest_v3_2026_09.json` is
  registered as `registered_blocked`; the campaign runner
  `scripts/pq3_3b_campaign_2026_09.py` is a static fail-closed implementation
  that refuses `--run` under a blocked manifest.
- P19/P20 remain open. No campaign run and no Stage S-readiness claim.

## Global Stop/Go Rules

- No gradient export or optimizer acceptance from an unqualified primal/adjoint.
- No Stage T/Stage V ranking from a candidate or reference whose mesh, solver, force stationarity, or uncertainty gate failed.
- No use of raw `checkMesh` text as a clean-pass claim; report raw output and profile judgment separately.
- No threshold relaxation after seeing a candidate result. Change a profile only by a pre-registered requalification with a new evidence record.
- No mixing candidate IDs, STL hashes, topology-state hashes, or historical run directories.
- No ranking claim until binary/discrete geometry, fixed operating point, fixed domain, qualified T/V references, and uncertainty margin are all established.
- If the next factor cannot be isolated, stop and record the experiment as diagnostic rather than adding optimizer complexity.
- If downforce remains outside the registered bound after local refinement, compare steady and time-resolved physics on the same mesh before changing the design formulation.

## Setup, Tests, Selftests, and Evidence Inspection

Run from the repository root.

### Environment setup

macOS or Linux CPU environment:

```bash
bash scripts/bootstrap.sh
```

Apple Silicon with the optional bounded Metal reference:

```bash
bash scripts/bootstrap.sh --metal
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

Runtime diagnostics are capability evidence only:

```bash
.venv/bin/cfd-sdf research doctor --output work/runtime.json
```

```powershell
.\.venv\Scripts\cfd-sdf.exe research doctor --output work\runtime.json
```

### Required Python validation

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
.venv/bin/python -m compileall src tests
.venv/bin/python -m pytest -q
git diff --check
```

Windows PowerShell equivalent:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

### Documentation-validation snapshot (2026-09-20)

This handoff pack was validated on 2026-09-20 with the following full-suite,
compile, and diff results:

- `.venv/bin/python -m pytest -q`: `591 passed, 2 skipped, 3521 warnings`.
- `.venv/bin/python -m compileall src tests`: passed.
- `git diff --check`: passed.

The warnings are the existing VTK/NumPy `DeprecationWarning` class warnings,
not test failures.

### Bounded research checks

```bash
.venv/bin/cfd-sdf validate-problem-spec examples/g2_openfoam_compile/project.yaml --output-dir work/g2_contract --require-execution-ready
.venv/bin/cfd-sdf research preflight examples/generic_problem_v2/project.yaml --output work/preflight.json
.venv/bin/cfd-sdf research lbm-benchmark --backend cpu --output work/lbm_cpu.json
.venv/bin/cfd-sdf research lbm-benchmark --backend metal --output work/lbm_metal.json
```

The generic example refers to geometry assets that are not included, so its
preflight can fail as expected. A passing preflight is only the bounded G3
subset; it is not complete geometry, clearance, mesh, or physics qualification.
Metal is Apple Silicon only. CUDA is not implemented as a qualified path.

### Stage T prototype selftest

```bash
FILTER_KIND=cone .venv/bin/python scripts/stage_t_filtered_ramp.py selftest
FILTER_KIND=block .venv/bin/python scripts/stage_t_filtered_ramp.py selftest
```

PowerShell equivalent:

```powershell
$env:FILTER_KIND = "cone"
.\.venv\Scripts\python.exe scripts\stage_t_filtered_ramp.py selftest
$env:FILTER_KIND = "block"
.\.venv\Scripts\python.exe scripts\stage_t_filtered_ramp.py selftest
```

These test both supported filter paths, including the block-filter assertion
regression fix. This is not a production optimization or target-physics test.
A real Stage V single-level rerun, which is expensive and must be preceded by
the new clearance gate after WP1, is invoked by the existing script shape. The
recorded successful invocation used `FILTER_KIND=block`:

```bash
FILTER_KIND=block .venv/bin/python scripts/stage_t_filtered_ramp.py stagev_level 0.2 opt_q100_b0_step0_try0_block V3 0.0125
```

### Inspecting evidence

```bash
.venv/bin/python -m json.tool docs/evidence/stage_v_v3_requalification_2026_09.json
git show --stat --oneline HEAD
git status --short --branch
git diff -- docs/phase_plan.md docs/problem_register_2026_09.md docs/evidence/stage_v_v3_requalification_2026_09.json
```

When inspecting a result, read the machine-readable JSON, raw logs, profile
judgment, hashes, and evidence class together. A report that only says a case
finished is not a solver qualification report.

### OpenCode CLI

Run these commands from the repository root. The installed `opencode run`
subcommand accepts the requested model and maximum variant.

For an authorized, noninteractive implementation or documentation task:

```bash
opencode run --model opencode-go/gpt-5.6-luna --variant max --auto \
  "This is an authorized implementation or documentation task. Read AGENTS.md, docs/opencode_handoff_2026_09.md, docs/README.md, docs/phase_plan.md, docs/problem_register_2026_09.md, and docs/problem_resolution_plan_2026_09.md. Inspect live git status --short --branch, git log -1 --oneline --decorate, and the current diff before editing. Work only on the next issue-driven slice described by those documents, preserve unrelated changes, validate the smallest relevant slice, then follow AGENTS.md by committing and pushing only the intended files to the current feature branch. Never force-push, reset, or overwrite unrelated work."
```

For a safer read-only inspection, omit `--auto` and explicitly prohibit edits:

```bash
opencode run --model opencode-go/gpt-5.6-luna --variant max \
  "Read AGENTS.md, docs/opencode_handoff_2026_09.md, docs/README.md, docs/phase_plan.md, docs/problem_register_2026_09.md, and docs/problem_resolution_plan_2026_09.md. Inspect live git status --short --branch, git log -1 --oneline --decorate, and the current diff. Report the next issue-driven slice and any worktree conflicts. Do not edit files, run destructive commands, commit, or push."
```

These examples use `opencode run`; do not assume that top-level interactive
`opencode` accepts `--variant`. Verify the installed top-level help or use its
model/variant controls before passing any such flag there.

## Hardware and Runtime Constraints

Host memory and GPU memory are separate budgets:

| Host | Host RAM | GPU/VRAM | Current evidence and constraint |
| --- | --- | --- | --- |
| Apple Silicon Mac used for V3 | 32 GiB unified host memory on Apple M4 | No separate VRAM value recorded; Metal shares the unified memory system | V3 case-generation peak RSS was 9.4 GiB, case size 466 MiB, and solver execution was 4815.07 s for the reduced candidate. OS, Docker, solver, and visualization share the host budget. |
| Windows target | 32 GiB host RAM | RTX 4070 Ti, standard 12 GiB VRAM | Host RAM and VRAM must be measured separately. WSL2/Linux plus CUDA is the intended path, but actual CUDA execution, peak VRAM, precision, and solver qualification are pending. |

Planning values in `development_plan_2026_09.md` are provisional budgets, not
measurements: roughly 12-16 GiB Mac solver working set and 8-9 GiB Windows GPU
use. Do not turn them into performance or capacity claims. The 32 GiB Mac host
value must never be conflated with Windows RTX 4070 Ti's 12 GiB VRAM.

## Claims That Must Not Be Made

The following claims are forbidden until separately qualified:

- No grid-independent downforce claim. The correct V3 downforce transition is `0.029925135222144128` against a registered absolute limit of `0.005`.
- No full-vehicle FSAE or high-Re qualification claim. The current V3 run is a reduced, steady, incompressible laminar case at `1.0 m/s` and `nu=0.01 m^2/s`.
- No qualified Stage T/Stage V ranking claim. The architecture's ranking premise remains unresolved; the current binary result is one positive pair with insufficient margin and coverage.
- No raw clean `checkMesh` claim for the correct V0-V3 cases. Their profile qualification allows concave-cell output; raw `checkMesh` reports one failed check.
- No claim that `execution_ready`, an OpenFOAM process exit code, a force file, or an LBM Taylor-Green pass is target-physics qualification.
- No claim that the Brinkman surrogate is generally valid or generally impossible.

## Fresh-Session Checklist

1. `cd /Users/sota/projects/FomulaTMU/CFD2026_09`.
2. Read `AGENTS.md`, then the handoff and the authoritative documents in the order above.
3. Run `git status --short --branch`, `git log -1 --oneline --decorate`, and inspect the current diff.
4. Confirm the issue ID and evidence class for the requested slice before editing.
5. Confirm whether the task is contract, capability, numerical, target-physics, or benchmark work.
6. Inspect the relevant JSON, raw logs, hashes, and current implementation before changing code.
7. For the immediate slice (WP1, implemented 2026-09-20): the Stage V path now
   binds `grid.domain_bounds_m` and runs the `stage_v_clearance_v1` pre-mesh
   preflight; new solver work starts at WP's next slice — re-qualify the correct
   candidate under the fixed domain, then the predeclared local-refinement grid
   study (WP3).
8. Add or update the smallest relevant tests, including fail-closed and no-launch behavior.
9. Run the smallest relevant test, then `.venv/bin/python -m compileall src tests`, `.venv/bin/python -m pytest -q`, and `git diff --check` when the task requires full validation.
10. Check that only intended files changed and that no evidence JSON or authoritative decision was overwritten.
11. Report measured facts, artifact paths/hashes, evidence class, claims allowed, claims still forbidden, and any uncertainty.
12. For an authorized implementation or documentation task, commit and push only the intended files after validation, unless an explicit review-only, no-edit, or no-push instruction applies.

## Completion and Reporting Template

Use this compact template at the end of each implementation slice:

```text
Slice:
- Issue(s): P__ / G__ / C__
- Work package:
- Evidence class: contract | capability | numerical | target physics | benchmark

Changes:
- Files changed:
- Contract/profile/schema changes:
- Fail-closed conditions added:

Validation:
- Commands:
- Results:
- Environment/container and solver version:

Artifacts:
- Input paths and hashes:
- Output paths and hashes:
- Candidate/spec/grid/transfer/profile IDs and hashes:

Decision:
- Stop/go status:
- Measured result:
- Claims supported:
- Claims explicitly not supported:

Uncertainty and follow-up:
- Unresolved issue:
- Next dependency:
- Not run:

Git:
- Branch:
- Commit before work:
- Worktree status:
- Commit/push performed: record the actual result; follow `AGENTS.md` for the standing policy
```

## Known Documentation Uncertainty

`docs/cross_platform_research.md` references
`scripts/build_porous_force_objective.sh`, while the current repository listing
contains the PowerShell form `scripts/build_porous_force_objective.ps1`. Verify
the intended platform command before using it; this handoff does not silently
repair that unrelated documentation mismatch.
