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
The v4 optimization campaign subsequently converged at b=4 and stopped after
eight accepted b=8 objective steps because the ninth-step Path B difference
fell below its registered absolute noise floor. A same-state diagnostic
supported a wider centered epsilon without changing that floor. Manifest v5
registers a local-state-dependent continuation from the verified b=8
checkpoint in a new output directory. Its input snapshot and the v4 campaign
output are retained under ignored `work/`, so a fresh checkout cannot resume
without those host-local artifacts. Follow the latest `phase_plan.md` and
immutable v4 outcome/recovery evidence rather than the older snapshot below.
The v5 run subsequently accepted three more b=8 objective steps (11 total)
and stopped at attempt 12: its improvement was below the registered noise
threshold, while the three-step convergence window had not passed. The current
status and next diagnostic are recorded in `phase_plan.md` and
`evidence/pq3_3b_campaign_v5_outcome_2026_09.json`; b=16 was not run.

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

The latest `phase_plan.md` order controls. The post-PQ3.3 bridge criteria are in
[`stage_t_to_stage_s_bridge_plan_2026_09.md`](stage_t_to_stage_s_bridge_plan_2026_09.md);
the PQ3.3a/PQ4.0a/PQ3.3b/PQ4.1 items below are complete and retained as
history.

1. Work F surface-FD contract: implement the matched-Re laminar body-fitted base
   adjoint (separate drag and downforce solvers, `faceSensNormal<response>` for
   both, `require_drag=True`), response-specific immutable manifests, the
   solver-free perturbation preflight, and regression tests. Do not start the
   campaign yet.
2. Register the epsilon ladder, directions, surface basis, displacement cap and
   noise floor before any response value is seen; then run the two base
   adjoints and the shared perturbation catalog (at most 4 directions x 4
   epsilons x 2 signs = 32 primals) and compute centered FD.
3. Judge drag and downforce separately. Only if both pass, register a separate
   one-step manifest; after the small step re-run every geometry, clearance,
   mesh, solver and response gate. On any fail/unresolved keep
   `shape_update_allowed=false` and do not enter HJ evolution or multi-step.
4. PQ2 may run independently, but not concurrently with Work F on the same
   machine; PQ5/PQ6 remain the post-Stage-S independent verification and
   target-physics ladder.

Do not start the FD campaign or a shape update before the contract and
solver-free preflight are registered.

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

## 2026-09-23: post-v5 D0-D3 status (bounded diagnosis executed)

- D0 `docs/evidence/pq3_3b_stopped_state_diagnosis_2026_09.json`: no new
  solver run; stopped parent reconstructed through the oracle cache and every
  registered kappa reproduced exactly. Mechanisms: 9495 active cells frozen at
  exact 0/1; uniform volume correction cancels the sign step at machine scale
  for alphas <= 0.5; alpha=1 leaves a 2.67e-5 step with -3.1e-7 objective dot.
- D1 `docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json`: bounded
  discriminant, 10 fresh primals, parent spread 0.0. Verdicts: d1
  below_threshold (+2.71e-7), d2 objective-only detectable (+0.13399), d3
  exchange detectable (+0.02789), d4 one-sided inward detectable (+8.06e-5).
- D2 `docs/evidence/pq3_3b_d2_change_manifest_2026_09.json`: minimal change
  `objective-oc-inequality-v1` (no equality correction in Phase 2, V<=Vmax,
  1e-8 machine-scale gate, extractability guard).
- v6 manifest `docs/evidence/pq3_3b_campaign_manifest_v6_2026_09.json`
  registered (`registered_preflight_pending`); entry preflight
  `docs/evidence/pq3_3b_v6_entry_preflight_2026_09.json` passed both stages.
- Next: an explicit user go plus a v6 campaign runner (not implemented).
  Stage S remains blocked; do not claim convergence or readiness.

## 2026-09-23: v6/v7 campaign cycles and the cap-constrained stop

- v6 outcome `docs/evidence/pq3_3b_campaign_v6_outcome_2026_09.json`: nine
  accepted b=8 inequality steps, stopped when every alpha exceeded Vmax.
- v7 manifest/preflight/outcome: `pq3_3b_campaign_manifest_v7_2026_09.json`,
  `pq3_3b_v7_entry_preflight_2026_09.json`,
  `pq3_3b_campaign_v7_outcome_2026_09.json`. The cap-corrected policy accepted
  27 more b=8 steps exactly on Vmax; same-level downforce 3.82622378522; the
  registered window missed by one 1.31e-4 delta and attempt 28 rejected every
  alpha at machine scale (<= 5.6e-17), fail-closed.
- Next (not started): a new immutable manifest with a pre-registered
  cap-stationarity exit measured separately from the accepted-step window,
  then the b=16 campaign and terminal evaluation. No convergence claim.
- Still unrun registrations: PQ1 third source grid (128x64x64, needs new grid
  infrastructure + 24 FD rows), PQ1 grid stability, the Stage V domain/boundary
  V2 factor, and the DF2 Stage T grid family. Code repairs pending after the
  campaign path: P20 gap/min-width/calibration, P8 move-limit floor (the v6/v7
  policy already rejects machine-scale no-ops via the 1e-8 gate), P9.

## 2026-09-23: terminal candidate reached and PQ4.1 judged

- The Stage T chain completed: v8 exited b=8 by the pre-registered
  cap-stationarity rule; v9 converged at b=16 (window met) and the
  independent terminal repeat gave downforce 2.92433989091 at projected
  volume 0.0763257. Outcomes:
  `pq3_3b_campaign_v8_outcome_2026_09.json`,
  `pq3_3b_campaign_v9_outcome_2026_09.json`.
- PQ4.1 `docs/evidence/pq4_1_terminal_stage_s_entry_2026_09.json`:
  `ready_for_stage_s=false` — discreteness `mean_nd 0.109` vs `0.01`,
  measured self-intersecting extracted surface, clearance below margin;
  lineage/volume/fidelity/width pass. P19 closed; P20 partially repaired.
- Still unrun: PQ1 third source grid, PQ1 grid stability, Stage V
  domain/boundary V2, DF2 Stage T grid family; Stage S first step and PQ5
  remain after a passing candidate. Do not claim Stage S readiness.

## 2026-09-23: margin mask + b=128 continuation and the PQ4.1 v3 sweep

- v10/v11 outcomes: `pq3_3b_campaign_v10_outcome_2026_09.json` (150 accepted,
  budget exhausted), `pq3_3b_campaign_v11_outcome_2026_09.json` (b=128 window
  met, terminal downforce 3.36972164196, V=Vmax, margin mask).
- PQ4.1 v3 `docs/evidence/pq4_1_terminal_stage_s_entry_v3_2026_09.json`:
  registered iso sweep (0.4/0.5/0.6), no threshold passes. iso 0.5
  non-manifold pinch; 0.4/0.6 feature-shrink / surface-distance / volume
  fidelity failures; every threshold fails discreteness because the terminal
  re-greyed (mean_nd 0.0555 at b=128, started 0.0058).
- Next registered change: a discreteness criterion in the Phase 2 acceptance
  (transform-measured, no extra runs) in a new manifest. Still unrun: PQ1
  third source grid, PQ1 grid stability, Stage V domain/boundary V2, DF2
  grid family.

## 2026-09-23: v12 discreteness-preserving replay registered

- V12 replays from v10 checkpoint 5, the last accepted b=128 checkpoint below
  the registered bound (`mean_nd 0.0085623225`), and preserves its accepted
  count and convergence history. It does not resume the grey v11 terminal.
- The optional Phase 2 v2 gate measures active-cell `rho_projection`
  `mean(4*rho*(1-rho)) <= 0.01`. A failing candidate is rejected before Path B
  and trial OpenFOAM calls; a parent outside the bound stops before its parent
  solve. Older manifests retain the v1 behavior.
- The bounded entry preflight passes: alpha 1.0, 0.5 and 0.25 fail the new gate
  without CFD; alpha 0.125 passes all gates at `mean_nd 0.0097368499`, projected
  volume 0.0684122931 and downforce 2.32152697653.
- Next execution order: run the immutable v12 campaign unchanged, perform its
  independent terminal repeat, then run a new PQ4.1 composite threshold sweep.
  Stage S remains blocked unless that sweep returns `ready_for_stage_s=true`.

## 2026-09-23: v12 stop and v13 constrained-direction pass

- V12 accepted one alpha=0.125 sign step, reaching downforce 2.32152697653,
  projected volume 0.0684122931 and `mean_nd 0.0097368499`. The next attempt
  rejected every registered alpha before CFD because all exceeded 0.01. The
  sealed outcome records one new step, cumulative accepted count 6, no
  convergence and no terminal repeat.
- V13 uses `gD = pullback_from_projected(4*(1-2*rho_projection)/Nactive)` and
  projects the raw objective descent direction onto the free-cell linearized
  D tangent. The solver-free candidate at alpha 1.0 has `mean_nd 0.0097515674`,
  volume 0.0689810584 and predicted `delta J=-0.13488385`.
- The bounded OpenFOAM discriminant passes: `d_adj=-13.4883853`,
  `d_fd=-13.4886897`, fresh candidate downforce 2.45647595951, and all
  transform/response gates true. It starts no campaign.
- Next execution order: integrate the v13-qualified direction into a short
  immutable campaign capped at ten new accepted attempts. Stop and register a
  separate constraint change if volume becomes active. Then run PQ4.1 on a
  terminal candidate; Stage S remains blocked until its full composite pass.

## 2026-09-24: v14 bounded result, PQ4.1 and v15 registration

- V14 accepted five new tangent steps. The last accepted checkpoint has
  downforce `2.61268983854`, projected volume `0.07052783246092366` and
  active projected discreteness `0.009945312188186787`. The sixth attempt
  remained transform-feasible and passed the Path B sign/noise checks
  (`d_adj=-21.1719101`, `d_fd=-0.0884468`) but its trial downforce fell by
  `0.00029093771`; the campaign stopped `objective_rejected`. This is a
  response/nonlinearity stop, not convergence or stationarity.
- PQ4.1 was run on the last accepted v14 checkpoint. No threshold is ready for
  Stage S. Iso 0.5 passes discreteness, extraction profile and volume fidelity
  and fails only the registered clearance gate. Iso 0.4 also fails feature
  shrink; iso 0.6 also fails volume fidelity. The committed artifact's first
  `claims_supported` sentence mistakenly says `v9 terminal candidate`; its
  kind, input checkpoint hashes, fields and numerical rows are the v14-state
  evaluation. Do not use that copied label as lineage evidence.
- The unrun v15 registration starts from a deterministic trim of v14 checkpoint
  5 to the registered support box x `[-0.675,1.675]`, y `[-0.475,0.475]`, z
  `[-0.275,0.275]`. The resulting start measures projected volume
  `0.0620239160551`, `mean_nd=0.0036595159924` and zero projected-solid support
  violations. Because this is a materially changed state, v15 resets accepted
  count and the convergence window; v14 metrics remain provenance only.
- V15 keeps `D<=0.01`, `V<=0.07632566813424899`, the 0.25 m clearance profile,
  response thresholds and all extraction gates. After transform screening it
  may backtrack across alpha `1, 0.5, 0.25, 0.125, 0.0625` only when Path B
  passes and the full trial response fails. A Path B failure stops fail-closed.
  Each fresh attempt is bounded to one parent/adjoint plus at most five
  Path-B-pair/trial groups, 16 evaluator requests total; request freshness is
  recorded separately. The learning run is capped at ten fresh attempts and
  ten accepted steps.
- Current next action: commit the v15 implementation and immutable registration,
  run only its registered entry preflight, inspect the exact alpha/run evidence,
  and start the bounded campaign only if that preflight passes. Stage S remains
  blocked until a later PQ4.1 returns `ready_for_stage_s=true`.

### V15 entry preflight result

- `docs/evidence/pq3_3b_v15_entry_preflight_2026_09.json` passed. The trimmed
  parent is a fresh converged primal/adjoint at downforce `2.00516803057`.
- Alpha 1.0 was transform-feasible and accepted: downforce
  `2.01655864594`, projected volume `0.0621640407738`,
  `mean_nd=0.00348178008471`, support violations 0 and mask drift 0.
- The centered Path B pair was fresh and consistent:
  `d_adj=-1.67506090492`, `d_fd=-1.65081811875`. Two Path B primal requests
  and one trial request were used, all recorded as non-reused with summary
  hashes.
- Since alpha 1.0 passed, no lower-alpha response evaluation was needed. The
  code path is covered by tests, but physical response backtracking remains
  unobserved. The preflight did not start the ten-attempt campaign.

### First campaign invocation: runner selection defect

- The first clean v15 campaign invocation reproduced the preflight's accepted
  alpha-1 candidate and fresh solver evidence, then raised
  `inequality acceptance or rho lineage mismatch` before writing checkpoint 1.
- Root cause: the response-level ledger retains smaller transform-feasible,
  unevaluated rows after an earlier alpha is accepted, while the shared runner
  still selected `candidates[-1]`. The accepted row was index 0 and the final
  row was an untried alpha 0.0625 row. The accepted and payload rho hashes both
  equal `2dc165bd84f45aadf3f3086fa2e9b14814e65146a0978366792c945d606bd163`;
  this was control-flow selection, not a field-lineage mismatch.
- `docs/evidence/pq3_3b_v15_runner_lineage_failure_2026_09.json` records the
  error, request evidence and pre-archive hashes. The failed work directory is
  preserved as `work/pq3_3b_campaign_v15_failed_lineage_2026_09_24` and does
  not count as an accepted step.
- The runner now requires exactly one row with `accepted=true` and selects that
  row independently of ladder position. Restart v15 from a clean output
  directory after committing this repair; do not resume the failed directory.

## 2026-09-24: v15 bounded learning result

- The clean restart ran `work/pq3_3b_campaign_v15` under the immutable manifest
  (SHA-256 `4a46c740dd4fd2f350326b82bab90a67c64e8bb2de1334bc3bb563b2d2e5ceda`)
  and stopped `paused_learning_budget` at the registered budget:
  **10 fresh attempts, 10 accepted** (all at alpha 1.0, so the alpha-below-1
  physical response backtracking path was not exercised).
- Final accepted state: raw downforce `2.10035503533`, projected volume
  `0.06406567400358908` (83.94% of `Vmax`), active projected discreteness
  `mean_nd=0.003213044195919047`, zero support violations. The registered
  convergence window was not observed (`window_accepted=3`,
  `level_converged=false`).
- This is a bounded-budget stop: **not terminal or converged**, and the campaign
  outcome alone does not establish Stage S readiness. Final rho array hash
  `00efe715f32c46f8d55a7ace599936ce61613cdfcaa2b8ff35270db8dd711f31`.
- Outcome
  `docs/evidence/pq3_3b_campaign_v15_outcome_2026_09.json` was verified
  against `work/pq3_3b_campaign_v15` (manifest hash, output hashes
  `campaign_meta_json 71299dbd…`, `events_jsonl dc674955…`,
  `latest_json cdc017ee…`, rho file `52e791d5…`, state `b9b0f10e…`, and the
  41-event chain) and the manifest hash file. No v16 is registered.

## 2026-09-24: PQ4.1 on the v15 checkpoint 10 — verdict

- Command: `scripts/pq4_1_terminal_stage_s_entry_2026_09.py` (fit for
  purpose after two minimal parametrizations: a `--candidate-label` so the
  claims sentences describe their actual input lineage, and the
  `correction`/`supersedes` block made conditional to its own
  `pq4_1_terminal_stage_s_entry_v2` kind; plus a selection-row lookup fix
  because the sweep record communicates the selected threshold as
  `selected_threshold` and the row, not a `selected` key — the first
  invocation could mis-record a passing sweep as `selected=None`).
- Inputs: `--campaign work/pq3_3b_campaign_v15`,
  `--outcome docs/evidence/pq3_3b_campaign_v15_outcome_2026_09.json`,
  `--canonical-state work/pq3_3b_margin_masks/topology_state.json`,
  `--projection-b 128`, `--iso-thresholds 0.4,0.5,0.6`.
- No solver run; the checkpoint rho is re-materialized into the four fields,
  `beta_solver` retained as the solver audit field, extraction from
  `rho_projection`, then the complete fail-closed composite gate.
- Verdict
  (`docs/evidence/pq4_1_v15_state_stage_s_entry_2026_09.json`):
  the range-first rule selects **iso 0.5** and the registered
  `stage_s_entry_v1` composite gate returns **`ready_for_stage_s=true`**.
  Iso 0.4 fails `extraction_profile:feature_shrink_exceeds_profile`; iso 0.6
  fails `volume_fidelity`.
- Iso 0.5 sub-verdicts (all pass): discreteness `mean_nd=0.003213044113334087`
  (bound 0.01); extraction profile with a measured watertight, manifold,
  non-self-intersecting surface (``self_intersection="none"``) and positive
  volume; volume fidelity (`volume_fidelity_v1`); volume constraint
  (V `0.0640656740267299` <= `0.07632566813424899`); width/gap measured;
  lineage artifact hashes; and the `stage_v_clearance_v1` preflight (the
  support-box trim cleared the v14-era failure point).
- Meaning and limits: this is the measured verdict of the registered gate on
  the **paused v15 checkpoint** (10 accepted steps at alpha 1.0, convergence
  window unobserved). It is not a converged-terminal claim, not a claim that
  later optimization states will also pass, not grid independence, and not a
  target-physics or full-vehicle claim (laminar reduced case). The remaining
  P20 scope (volume-calibration artifact shape label, strict minimum width)
  and a solver-execution reconfirmation (P17 closure condition) stay open.
- No Stage S baseline is registered by this record — registration is a
  separate authorized decision. No new OpenFOAM campaign and no v16.

## 2026-09-24: P20 closure and the adopted v16 sequence

- P20 remaining scope is implemented and tested (no solver run):
  `component_boundary_gap_m` (exact axis-aligned cube face distance, calibrated
  on analytic fixtures in `tests/test_stage_s_entry.py`); the declared
  `minimum_solid_width_m` / `minimum_void_width_m` now compare the true
  minimum medial-axis thickness (`thickness_ridge_m_min`) while
  `ridge_width_p5_m` remains a separately named quantile; the volume
  calibration's shape labels are corrected by the append-only
  `docs/evidence/pq4_volume_fidelity_calibration_correction_2026_09.json`
  (original SHA-256 `1e1fc748…` referenced, measurements unchanged, profile
  references the correction); and the direct self-intersection detector has a
  false-positive/true-positive/over-cap audit with a memory-safe AABB stage.
- The v15 checkpoint-10 PQ4.1 pass is a pre-repair record. The next PQ4.1
  judgment (on the v16 terminal) uses the repaired gate.
- Adopted execution order (user-approved 2026-09-24): P20 repairs → v16
  continuation registration and bounded campaign → fresh PQ4.1 on the v16
  terminal → Stage S baseline registration → Stage S Work F. v15 stopped at
  its registered budget while still improving (objective deltas
  `0.0125/0.0133/0.0154`; projected volume `0.0641` of `Vmax 0.0763`), and each
  Stage T attempt is ~20 s on the 8192-cell case versus hours-to-days for
  body-fitted Stage S work.
- Stage S baseline conditions are recorded in `phase_plan.md` (Exit Gate E
  hash binding, `stage_v_clearance_v1` pass, `V <= Vmax`, then Work F
  qualification under `stage_v_qualification_v1` and the `fd_gradient_v1`
  surface-FD profile, at most one shape step).

## 2026-09-24: v16 continuation registration and entry preflight

- Manifest `docs/evidence/pq3_3b_campaign_manifest_v16_2026_09.json`
  (SHA-256 `28e8f7b5fa7a0fc0d67143f7b2f2fa55a8c7ca3c6a7d0cc50c766afb64630751`)
  continues the b=128 margin level from the v15 checkpoint 10 unchanged; no
  bootstrap or state transformation. The cumulative accepted count (10) and
  the last three accepted metrics are carried over, so the registered
  convergence window is evaluated across the v15/v16 boundary. The
  cap-stationarity exit is enabled for the projected-direction policy reasons
  (`machine_scale_update_rejected`, `projected_volume_limit_exceeded`), the
  independent terminal repeat is enabled, and the level budget is 90 attempts
  with at least 10 cumulative accepted steps.
- Entry preflight
  `docs/evidence/pq3_3b_v16_entry_preflight_2026_09.json` passed: start state
  `mean_nd=0.0032130442`, projected volume `0.0640656740`, support violations
  0; alpha 1.0 accepted (`DF 2.10035503533 -> 2.11252824711`, Path B
  `d_adj=-1.29080394` / `d_fd=-1.41661536`, candidate `mean_nd=0.0031861835`,
  projected volume `0.0643333567`). The long campaign has not run in this
  record.
- Contract test `tests/test_pq3_3b_campaign_v16.py` covers the sidecar,
  pinned start state, carryover, enabled exits, budget and inherited inputs.

## 2026-09-24: v16 campaign result and PQ4.1 on the repaired gate

- The v16 continuation accepted 87 steps (cumulative accepted count 97) and
  stopped fail-closed at attempt 88 (`objective_rejected`): the alpha-1.0
  Path B bracket failed as `not_a_descent_direction` (`d_adj=-0.04161669`,
  `d_fd=+0.01716448`), which stops the attempt by the registered policy.
- Final accepted state: raw downforce `2.65056396128`, projected volume
  `0.0719735014` (94.30% of Vmax), active projected discreteness
  `mean_nd=0.0025088808`, zero support violations. Last three objective deltas
  `5.52e-4/1.53e-4/7.33e-4`; the convergence window was not met and no
  independent terminal repeat ran. This is a bounded response/gradient stop,
  not convergence or stationarity.
- Outcome `docs/evidence/pq3_3b_campaign_v16_outcome_2026_09.json` (SHA-256
  `864084348e3c3fae5d2b592eb484d931dccd60502ed0d72e61bfc3881ab5a671`).
- PQ4.1 on the v16 checkpoint with the repaired gate selects iso 0.5 and
  returns **`ready_for_stage_s=true`**:
  `docs/evidence/pq4_1_v16_state_stage_s_entry_2026_09.json` (SHA-256
  `ae6a30c45503a40ddc31c61039c7da1e6670b4bd065b2a4fcbd2e84595cc0663`).
  Iso 0.4 fails feature shrink; iso 0.6 fails volume fidelity. The pass is on
  a blocked-stop checkpoint, not a converged terminal; the Stage S baseline
  registration is the next authorized decision.

## 2026-09-24: Stage S baseline registered on the v16 candidate

- `docs/evidence/stage_s_baseline_v16_2026_09.json` (SHA-256
  `db54601caa3acc02649b5b4b759d30c4e8668d530a614993b5f8c0dd4bef412f`) registers
  the selected iso-0.5 `rho_projection` handoff of the v16 checkpoint 87 as the
  Stage S baseline. The Exit Gate E binding is complete: candidate rho hashes,
  campaign manifest/outcome, the selected handoff manifest and its artifacts
  (surface STL, revoxelized/source density, fidelity report), the four-field
  bundle file hashes plus the `rho_projection`/`beta_solver` array hashes, the
  transform (`r=0.15`, `b=128`, `eta=0.5`, `q=100`) and
  `V=0.0719735015 <= Vmax`.
- The registered `stage_v_clearance_v1` preflight was re-run on the selected
  surface and passes (margin 0.25 m). Work F profiles are pinned:
  `stage_v_qualification_v1` for the body-fitted mesh/solver qualification and
  `fd_gradient_v1` for the drag/downforce surface FD.
- The registration is not a Stage S qualification; Work F (baseline mesh and
  response qualification, then the surface FD, then at most one shape step) is
  the next slice. P17's solver-execution reconfirmation is part of Work F, and
  P2's stricter terminal-state closure rule remains open.

## 2026-09-24: P20 re-audit repair, surface-nets extraction, PQ4.1 v2 and baseline v2

- An independent audit found two reproducible false-negative classes in the
  direct self-intersection detector: coplanar area overlap and shared-vertex
  crossings away from the shared vertex. The topology-aware repair (commit
  `17e80f4`) detects both, permits contact only on the shared simplex, and
  rejects degenerate triangles fail-closed.
- The repaired gate rejected the registered iso-0.5 surface: marching cubes
  emitted 4-8 collinear sliver triangles (area <= 1e-10 m^2, aspect > 1e7)
  that point merging could not remove; edge collapse created new crossings.
  The handoff now extracts the binary cell material with VTK surface nets
  (`contour_labels`, no smoothing): no degenerate triangles, watertight,
  manifold, cell volume reproduced exactly (absolute difference 1.5e-9 m^3 on
  the v16 candidate). `SURFACE_SMOOTHING_ITERATIONS = 0` records the choice.
- PQ4.1 v2 on the v16 checkpoint selects iso 0.5 and returns
  `ready_for_stage_s=true`
  (`docs/evidence/pq4_1_v16_state_stage_s_entry_v2_2026_09.json`, SHA-256
  `db61de5cec6a6058f1880549ad553bc4c2d793d5f569b4d0c6c02f003f0a709c`); iso 0.4
  fails feature shrink, iso 0.6 passes but is not selected.
- Stage S baseline v2
  (`docs/evidence/stage_s_baseline_v16_v2_2026_09.json`, SHA-256
  `a6d40a5c25d9a4ca44aaf1c4d9a7b667d6d33fcfeed45d4b7e2b3cdb049abed6`)
  re-binds the baseline to the v2 judgment and supersedes the v1 record
  append-only. Next slice: Work F0 baseline registration preflight and one V1
  body-fitted baseline qualification (mesh-only first; no adjoint, FD or shape
  update).

## 2026-09-24: Work F0 baseline preparation (registration, preflight, mesh gate)

- Work F manifest `docs/evidence/stage_s_work_f_manifest_2026_09.json`
  (SHA-256 `03b109f15e79036fe31a6ec76cd58831f8f834926aee2c0eaf654ea80b47dfdd`)
  binds the baseline v2, the matched-Re laminar spec
  (`work/stage_sv_laminar/project_matched_re_laminar.yaml`), the V1 voxel size
  `0.05 m`, the case path `work/stage_s_work_f_v1/baseline/V1`, the clearance
  and mesh profiles, the drag/downforce response identities, the mesh-only
  commands and the fail-closed stop rules.
- Solver-free preflight
  `docs/evidence/stage_s_work_f_v1_preflight_2026_09.json` (SHA-256
  `3f850e20dfff91bef91fb676cc84bdcd55710912fa4cfa899fcaf6d46c350f06`): the V1
  case renders from the registered v16 iso-0.5 surface; metadata matches the
  registered operating point (`U=1`, `rho=1`, `mu=1e-2`, laminar, Aref 0.64,
  lRef 0.8, CofR `(0.25,0,0)`, drag `(1,0,0)`, lift `(0,0,1)`, force patch
  `design_candidate`, fixed domain bounds, voxel 0.05); clearance preflight
  passes.
- Mesh-only run `docs/evidence/stage_s_work_f_v1_mesh_2026_09.json` (SHA-256
  `4a257ac608c022479a918e2adb0e2ebba2fe1bb6f3680c7f38ba6efd961d2577`): 39,848
  cells; one failed check line `Concave cells (using face planes) found,
  number of cells: 2441` (fraction 0.06126 <= 0.08); mesh profile qualified;
  `solver_allowed=true`; `simpleFoam` not started.
- Next: the primal baseline run (simpleFoam + `write_stage_v_qualification` +
  the registered profile qualification), which also reconfirms clearance under
  solver execution and closes P17; no adjoint, FD or shape update yet.

## 2026-09-24: Work F V1 primal baseline qualified (P17 reconfirmed)

- `docs/evidence/stage_s_work_f_v1_solver_2026_09.json` (SHA-256
  `3c1e5b437f5a9e425dee8b0e7f0b488365bf5c3ddd971c74fd7aaa2e1657fe4f`): the V1
  body-fitted baseline solved to the registered `stage_v_qualification_v1`
  profile. checkMesh profile pass (39,848 cells, concave fraction 0.06126);
  `residualControl` convergence (final `Ux/Uy/Uz/p`
  `4.91e-7/8.18e-7/9.80e-7/3.11e-6`); force stationarity pass (Cd mean
  `2.52344`, window drift `-1.106e-4`; downforce mean `1.69084`, window drift
  `-6.305e-5`).
- This is the solver-execution clearance reconfirmation for the exact
  registered v16 iso-0.5 surface, so P17's closure condition is met (bounded
  to this candidate and level; new candidates/levels need their own run).
- `surface_fd_allowed=true`; `shape_update_allowed=false`. Next slice: register
  and run the drag/downforce surface FD campaign under `fd_gradient_v1`; at
  most one shape step only if both responses pass.

## 2026-09-24: Work F surface-FD contract, manifests and solver-free preflight

- Contract module `src/cfd_sdf/stage_s_surface_fd.py` owns the response
  identity (drag = `Cd` relative; downforce absolute with objective sign `-1`
  and the `liftDir = -downforce` relation), the `volumetricBSplines` surface
  basis, the fixed outer patches with a `1e-3 m` displacement cap, the
  dimensionless epsilon ladder and the two response-specific FD manifests.
- Registration `docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json`
  (SHA-256 `e4cdbe437eaa32dc752ad603a5d921aa94a4a47511e4a0403ead58ac49d5b4a8`):
  drag and downforce manifests share one perturbation catalog; epsilons
  `1e-4/2.5e-4/5e-4/1e-3 m` from ratios `0.002/0.005/0.01/0.02` of the 0.05 m
  voxel; directions `downforce_gradient_aligned`, `drag_gradient_aligned`,
  `random_seed_11`, `random_seed_2026`.
- Solver-free preflight
  `docs/evidence/stage_s_work_f_surface_fd_preflight_2026_09.json` (SHA-256
  `93c6c6b5007f6ff6741a3bedc4fa2d87ce85d48c5bf8be0b2a0297bff9588efc`): the
  conservative uniform normal offset at every epsilon and both signs is
  watertight, winding-consistent, non-self-intersecting, keeps the `0.05 m`
  minimum solid width and passes clearance (volume change <= 2.1%);
  `campaign_allowed=true`, no solver started.
- `evaluate_fd_campaign_v2` no longer silently passes a below-noise direction:
  gradient-aligned below-noise is `near_zero_gradient_aligned_unresolved`, and
  non-aligned near-zero directions are judged by the registered absolute rule.
- Next: implement and preflight the body-fitted base adjoint case (separate
  drag and downforce solvers, `faceSensNormal` export); no perturbation or
  shape update runs before that passes.

## 2026-09-24: Work F base adjoint case rendered and preflighted

- `src/cfd_sdf/stage_s_adjoint_case.py` renders the v2512
  `adjointOptimisationFoam` dictionaries on a copy of the qualified V1 case:
  `system/optimisationDict` with two adjoint solvers (`adjDownforce` direction
  `(0,0,-1)`, `adjDrag` direction `(1,0,0)`, Aref `0.64`, UInf `1`, rhoInf `1`,
  patch `design_candidate`), `shapeType volumetricBSplines` /
  `sensitivityType surface` / `includeSurfaceArea true`;
  `constant/dynamicMeshDict` with the
  `volumetricBSplinesMotionSolver`, an axis-aligned `8x8x8` control volume and
  `confineBoundaryControlPoints true`.
- Preflight `docs/evidence/stage_s_work_f_adjoint_preflight_2026_09.json`
  (SHA-256 `0f5f94fb50ac566952d384311bd6da91f91d008c0465b8bbfe05a264239e45b4`):
  all structural checks pass and OpenFOAM's own `foamDictionary` reader parses
  both dictionaries (`optimisationManager singleRun;`,
  `solver volumetricBSplinesMotionSolver;`); `adjoint_allowed=true`, no solver
  started.
- Next: run the two base adjoints on `work/stage_s_work_f_v1/adjoint/base`,
  verify their residuals and final-time binding, and export
  `faceSensNormal<adjDownforce>` / `faceSensNormal<adjDrag>`; then compute the
  analytic directional derivatives and run the per-direction perturbation
  preflight before any perturbation primal.

## 2026-09-24: Work F base adjoints converged; analytic derivatives recorded

- `docs/evidence/stage_s_work_f_adjoint_run_2026_09.json` (SHA-256
  `5034dc01b508a4e8e6f6628de7fab67776cdbd23f5640d6b59865c811cc8aeb7`): the base
  adjoint case ran with `returncode=0`; the primal converged in 292
  iterations, `adjDownforce` in 425 and `adjDrag` in 562 (three convergence
  markers). Both solvers wrote design-variable derivative files
  (`optimisation/derivatives/volumetricBSplinesadjDownforceadjDownforceESI425`
  and `...adjDragadjDragESI562`); the `sensitivityType surface` variant also
  wrote `562/faceSensNormaladjDragESI`.
- The renderer now emits `0/pa`, `0/Ua`, `constant/adjointRASProperties`
  (`adjointLaminar`), the suffixed `div(-phi,Ua<adjS>)` fvSchemes entries, the
  regex fvSolution solver entries `(p|pa).*`, `(U|Ua).*`, `(m|ma).*`,
  `(d|da).*` and the adjoint relaxation factors. Diagnostic failure records for
  the four setup defects are retained as
  `docs/evidence/stage_s_work_f_adjoint_{preflight,run}_missing_*_2026_09.json`.
- `adjoint_converged=true`, `analytic_derivatives_ready=true`,
  `perturbation_allowed=false`. The analytic directional derivative for a
  registered direction is `sum_i total_i * direction_i` over the active
  control-point variables.
- Next: implement the morpher-based perturbation runner (prescribed
  control-point displacement, `moveMesh`, primal, response hash/identity) and
  the centered-FD evaluation per response; then the per-pair mesh/solver
  preflight. No shape update before both responses pass.

## 2026-09-25: Slice A — base derivative qualification and directions

- `docs/current_state_and_next_plan_2026_09_25.md` is Codex's adopted plan; its
  Slice A is implemented and passed.
- The active-variable contract is authoritative:
  `NURBS3DVolume::getCPID(i,j,k) = k*nCPUs*nCPVs + j*nCPUs + i`,
  `varID = 3*cp_id + component`, and `confineBoundaryControlPoints true` leaves
  the interior `6x6x6` control points (648 components) active. The qualifier
  verifies the derivative files' `varID` set equals that active set exactly.
- `docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json` (SHA-256
  `f0bec416540d3faf7f78dba09bcd3b2cb647740cf90fb53b4038cf9b2dcea606`):
  per-solver convergence and final residuals (primal `6.2e-8`, `adjDownforce`
  `8.5e-9`, `adjDrag` `9.2e-9`), both derivative schemas (648 rows, sign
  conventions), the committed 648-component unit-infinity-norm direction
  vectors (`drag_gradient_aligned`, `downforce_gradient_aligned`,
  `random_seed_11`, `random_seed_2026`) with hashes, and
  `perturbation_allowed=true`, `shape_update_allowed=false`.
- Doc drift fixed: the phase plan/handoff adjoint-preflight SHA now points at
  the live `0f5f94fb...` artifact and the register P19 summary row is closed.
- Next: Slice B — the morpher-only perturbation runner (prescribed
  control-point displacement with inf-norm epsilon, `moveMesh`, moved-mesh
  hash, geometry/clearance/checkMesh qualification, no `simpleFoam`) and all
  32 pair-side preflights.

## 2026-09-25: Slice B — morpher perturbation sides (32/32 pass)

- `volumetricBSplinesMotionSolver` applies a control-point *movement*
  (`setControlPointsMovement`) that plain `moveMesh` never sets; the repository
  now carries `openfoam_utils/moveControlPoints` (compiled once into
  `work/stage_s_work_f_v1/tools/moveControlPoints`, binary SHA-256
  `976677902709c315ee5edaefa6a382e0f050a56f10ba19c0683edd1bd2d5b39e`) which
  applies the prescribed movement through the registered morpher and writes the
  moved mesh at time 0.
- `docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json` (SHA-256
  `01aeda492f43e76e9dad173599f339ba48f9adb8dc5744de062de7ce47cbc9db`):
  all 32 direction/epsilon/sign sides pass — exact inf-norm movement, moved
  surface watertight/manifold/non-self-intersecting, volume change
  `<= 0.14%`, minimum solid width `0.05 m`, clearance preflight pass,
  registered checkMesh profile pass (concave `0.06101..0.06128`), outer-patch
  displacement exactly `0.0`, 39,848 cells on every side.
- `all_sides_pass=true`, `primal_campaign_allowed=true`, `solver_started=false`.
- Next: Slice C — run the 32 perturbation primals sequentially (both responses
  per run), verify residual and stationarity gates per side, and compute the
  centered FD `(R(+eps) - R(-eps)) / (2 eps)` per response.

## 2026-09-25: Slice C/D — 32-primal centered-FD campaign and judgment

- `docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json` (SHA-256
  `048a2f9307d36a645e76dee7fac26c6325568888cfaa28063cf5685a4acbc9ee`): all 32
  perturbation sides ran `simpleFoam`, converged and passed the registered
  solver, stationarity and checkMesh gates; both responses were read from each
  run.
- Gradient-aligned directional derivatives are within the 5% profile with tight
  plateaus (spread <= 3e-4): downforce response ratios `1.0408`
  (`downforce_gradient_aligned`) and `1.0279` (`drag_gradient_aligned`); drag
  response ratios `1.0266` and `0.9595`. Every sign agrees.
- Registered random-seed directions exceed the 5% relative rule on both
  responses, except drag `random_seed_11`, which passes at `3.76%` (downforce:
  seed 11 `1.0858` fails, seed 2026 `0.8796` fails; drag: seed 11 `1.0376`
  passes, seed 2026 `1.4593` fails). The complete FD qualification is false:
  `both_responses_pass=false`, `shape_update_allowed=false`.
- Fail branch per the plan: keep the shape update blocked and diagnose one
  factor at a time. Candidate factors: morphed movement bounding,
  surface-area weighting (`includeSurfaceArea`) convention, and the
  first-order `upwind` primal discretization behind the continuous adjoint.
  No epsilon/direction/tolerance change is allowed from the observed result.

## 2026-09-25: FD diagnosis D0-D2 — no mapping or semantics defect

- D0: the phase_plan Stage S summary now matches the machine-readable
  pass/fail matrix (gradient-aligned pass; drag `random_seed_11` passes at
  3.76%), and `current_state_and_next_plan_2026_09_25.md` is marked as a
  pre-campaign historical snapshot.
- D1 `docs/evidence/stage_s_work_f_realized_direction_audit_manifest_2026_09.json`
  (SHA-256 `490790f1...`) + audit
  `docs/evidence/stage_s_work_f_realized_direction_audit_2026_09.json`
  (SHA-256 `79da4532...`): 32/32 sides reproduce the prescribed movement
  (max `9.7e-9 m`), boundary fixed, 16/16 pairs pass (cosine `>= 0.99999999`,
  movement difference `<= 4.7e-9 m`, odd symmetry `1e-8 m`, even component
  `5e-9 m`); prescribed vs realized analytic contractions agree to `~4e-6`.
- D2 `docs/evidence/stage_s_work_f_sensitivity_semantics_audit_manifest_2026_09.json`
  (SHA-256 `493c6aa9...`) + audit
  `docs/evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json`:
  response identity, surface-convention record and varID contraction pass; an
  independent minimal parser reproduces the eight analytic derivatives at
  `1e-9` relative.
- Conclusion: the morpher mapping and the sensitivity semantics are not the
  cause. Next: D3 bounded discretization diagnostic (`linearUpwind` factor,
  one registered middle epsilon, 3 directions, 6 primals plus base/adjoint
  lineage). The original verdict and thresholds are unchanged.

## 2026-09-25: D3 bounded discretization diagnostic — mixed, not the sole cause

- Manifest `docs/evidence/stage_s_work_f_discretization_diagnostic_manifest_2026_09.json`
  (SA-256 `5bd182f3...`), preflight
  `docs/evidence/stage_s_work_f_discretization_diagnostic_preflight_2026_09.json`
  (only `div(phi,U)` changed to `bounded Gauss linearUpwind grad(U)`), evidence
  `docs/evidence/stage_s_work_f_discretization_diagnostic_2026_09.json`
  (SHA-256 `f3a85709817aa67d4fee8123d84d524784b403fd944702211c1677af878e67b6`).
- Base primal, both adjoints and all six sides pass. The scheme shifts the
  baseline strongly: Cd `2.5234 -> 2.2333`, downforce `1.6908 -> 1.6659`.
- Ratios at epsilon `5e-4` (upwind -> linearUpwind): downforce
  `downforce_gradient_aligned` `1.0409 -> 1.0418`; downforce `random_seed_11`
  `1.0857 -> 1.0432` (fail -> pass); downforce `random_seed_2026`
  `0.8796 -> 1.0336` (fail -> pass); drag `downforce_gradient_aligned`
  `1.0266 -> 1.0070`; drag `random_seed_11` `1.0376 -> 0.8521` (pass -> fail);
  drag `random_seed_2026` `1.4592 -> 1.2608` (still fail).
- The plan's condition "failing directions approach one and controls do not
  worsen" is not met (`n_improved_across_the_gate=2`, `n_worsened_controls=1`),
  so `supports_discretization_cause=false`: discretization is a contributing
  factor, not the sole cause. The direction-dependent residual points to the
  continuous-adjoint formulation / surface weighting / morpher chain-rule
  terms.
- No D4 requalification and no D5 shape step; the derivative remains
  unqualified and `shape_update_allowed=false`. The original verdict and
  thresholds are unchanged.

## 2026-09-25: D4.0 registration and D4.1 derivative-component audit

- D4.0 manifest
  `docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json`
  (SHA-256 `21dd18d6084258b4dc1f5cf02bc9d91049fb6e8f8aef82ae438bf0cd484a8e52`)
  binds the post-D3 plan, all input evidence hashes, the four direction vector
  hashes, the upwind and linearUpwind derivative-file hashes, the OpenFOAM
  image ID and ten v2512 source-file SHA-256s, the component formula, the
  ablation order, the sole-cause rule and the manifest-hash-derived holdout
  seed rule.
- D4.1 audit
  `docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json`
  (SHA-256 `2cd3f9f102fe49ff80b5d8499416ff61450d245a2c16468850693d8c5b32476c`)
  contracts every derivative column for 32 upwind rows (4 directions x 4
  epsilons x 2 responses) and 6 linearUpwind rows (3 directions at `5e-4`).
  Component closure is exact (max `1.63e-8`, within the file-precision
  tolerance) and the raw contraction reproduces every registered analytic
  exactly (deviation `0.0`).
- No single component drop and no common scalar explains all directions in
  either scheme. Dropping `dxdbVol`, `dndb`, `dxdbDirect` or `dVdb` (all zero
  in the contraction) changes nothing; dropping `dxdbSurf` or `dSdb` destroys
  the signal. The residual is in the values of the two surface terms, with
  cancellation amplification: drag `random_seed_2026` has `dxdbSurf=-0.20195`,
  `dSdb=+0.06770` (cancellation index `2.01`, FD residual `-0.06165`), and
  downforce `random_seed_11` `+0.02465/-0.17737` (index `1.32`). The
  least-squares common scales (`1.0134` upwind, `1.0295` linearUpwind) leave
  max relative errors of `0.44` / `0.22`.
- Docs reconciled: phase_plan Stage S summary now records D0-D3 and the D4.0
  registration; the old Slice C/D paragraph now states that drag
  `random_seed_11` passes at 3.8%; problem_register questions and next action
  are rewritten for the post-D3 sequence.
- Next: D4.2 B-spline geometry-Jacobian audit (solver-free). D4.3 ablations and
  D5-D7 remain conditional; `derivative_qualified=false` and
  `shape_update_allowed=false` stand.
