# OpenCode Handoff: CFD2026_09

Status: repository-local working memory for a fresh OpenCode session
Snapshot date: 2026-09-20
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
4. [`problem_register_2026_09.md`](problem_register_2026_09.md) for the P1-P17 issue ledger and artifact semantics.
5. [`problem_resolution_plan_2026_09.md`](problem_resolution_plan_2026_09.md) for detailed implementation slices and older resolution instructions.
6. [`problem_contract_v2.md`](problem_contract_v2.md) and [`fixed_grid_data_contract_v2.md`](fixed_grid_data_contract_v2.md) for schemas.
7. [`git_branching_strategy.md`](git_branching_strategy.md) for branch workflow.

The authority split is intentional:

- `docs/phase_plan.md` remains the sole roadmap, status, and execution-order authority.
- `docs/problem_register_2026_09.md` remains the issue ledger, including P1-P17 and the measured contradictions.
- `docs/problem_resolution_plan_2026_09.md` is a detailed implementation record, subordinate to the latest phase-plan order.
- `docs/problem_contract_v2.md` is the user/problem schema authority.
- `docs/fixed_grid_data_contract_v2.md` is the Stage T artifact-schema authority.
- `docs/evidence/*.json` is machine-readable evidence; prose must not broaden its scope.

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

The missing implementation is to reject this physical clearance violation
before meshing, using a fixed ProblemSpec far-field box and a declared physical
margin. Do not "fix" it by relaxing the registered mesh thresholds.

## Implemented Versus Missing

### Implemented or measured

- v2 generic ProblemSpec loading, canonical hash/snapshot, v1 read-only migration, typed geometry roles, responses, objectives, constraints, and topology policy.
- Generic OpenFOAM case compilation, deterministic manifests, supported force-response rendering, patch mapping, execution assets, and fail-closed numerical convergence extraction.
- Local, WSL, and Docker execution planning; Docker timeout/Ctrl-C cleanup; structured run summaries.
- Canonical fixed-grid state transfer `source = P @ target` and gradient pullback `P.T @ source`, with measured cell ordering and finite-difference evidence for the recorded direction.
- Candidate binding and provenance checks for the current Stage T contract path, plus a response-ID guard. Full semantic response/solver/direction/units binding is not complete.
- Python-side RAMP/filter prototype, density-to-SDF handoff diagnostics, candidate export, Stage V single-level execution, mesh preflight, residual-control gate, force-stationarity gate, and profile-based mesh qualification.
- Correct candidate V0-V3 Stage V execution qualification on the reduced steady laminar case.
- Bounded CPU and Apple Metal Taylor-Green research reference, clearly separated from aerodynamic claims.

### Missing or not qualified

- Fixed ProblemSpec far-field binding and candidate-to-boundary physical-clearance preflight before `blockMesh`/`snappyHexMesh`.
- Complete G3 geometry/resolution gates: self-intersections, actual shape thickness, full mask/connectivity checks, fixed-domain binding, and density-to-SDF fidelity.
- Native v2 artifact semantic bindings for response units, rho-gradient convention, solver/canonical grid mapping, and topology policy values.
- Full provenance generation and stale-array prevention for every candidate state (`rho`, `rho_filtered`, `rho_projected`, and `alpha`).
- Same-grid and refined-grid Stage T force convergence, non-integer transfer bias resolution, and a qualified alphaMax study.
- Production optimizer with physical volume constraints, nonlinear acceptance/rollback, checkpoint/resume, continuation baselines, feasible-seed restoration, and GCMMA-equivalent constrained updates.
- Stage S quantitative handoff qualification and actual SDF shape evolution.
- Stage V downforce grid convergence, local wake/wall refinement, and complete pressure/viscous/cross-fidelity ranking evidence.
- G4 B0-B5 benchmark ladder and any target-Re or full-vehicle qualification.
- Windows RTX 4070 Ti CUDA runtime and VRAM qualification; current evidence does not establish it.

## P1-P17 Issue Ledger Summary

This table summarizes the current status without deleting the older contradictory
observations. The detailed measurements remain in
[`problem_register_2026_09.md`](problem_register_2026_09.md).

| ID | Current status and unresolved point |
| --- | --- |
| P1 | Unresolved. The old grey-candidate test showed ranking inversion against an unqualified reference; the later binary-candidate test produced one positive pair sign across qualified V0-V2, but the pair count, margin, and downforce convergence are insufficient for ranking qualification. Do not call the surrogate pass or No-Go. |
| P2 | Partially addressed, not closed. Python-owned RAMP/projection produced non-degenerate material and removed the old double-projection defect in its measured path, but the recorded V3 candidate still has 320 grey physical-beta cells and the full handoff/discreteness contract is not qualified. |
| P3 | Unresolved. Stage T resolution and the 46080-to-8192 transfer may affect the result; same-grid/further-refined force convergence is not complete. |
| P4 | Partially addressed. P4a wrong objective/constraint declaration, P4b infeasible volume formulation, and P4e reduced-Re versus declared target-condition mismatch remain. P4c sign convention has a guard. P4d response membership has a guard, but full semantic binding to solver, direction, sign, units, and objective is incomplete. |
| P5 | Diagnosed and avoided, not a production optimizer solution. Native ISQP line-search behavior led to the permanent Python-optimizer decision; the Python optimizer still lacks production qualification. |
| P6 | Unresolved. Gradient-aligned directions are near 1% error, while localized filtered-random directions remain around 0.90. Non-integer overlap redistribution is a hypothesis, not a confirmed cause. |
| P7 | Closed 2026-09-20 (WP4): injection now refreshes `rho`, `rho_filtered`, `rho_projected`, and `alpha` in the same generation when the contract provably satisfies the C3 identity contract (beta_max decoded from the recorded alpha/rho ratio), and refuses (fail-closed, no stale carry-over) any contract whose filter/projection/Brinkman state is not identity. Three mutation tests added. |
| P8 | Partially addressed in the filtered prototype, which has a move floor and no-op detection. A production acceptance rule, reset policy, and evidence-backed optimizer closure remain missing. |
| P9 | Unresolved. Stage S must remove zero-extent/domain-boundary components from iso-surface output; the old 5120-face six-component signature is a writer behavior, not a design. |
| P10 | Unimplemented by design. No Hamilton-Jacobi update, reinitialization, shape-gradient normal velocity, or curvature control exists. It must wait until the density surrogate/ranking gates are passed. |
| P11 | Closed as an independent diagnosis and retained as a P2 symptom. The measured beta-band leakage showed alphaMax=2500 already blocks beta above about 0.1; behavior for beta 0.7-1.0 remains an explicit caveat because those cells were not generated in the original runs. |
| P12 | Partially closed. The correct step0 candidate has qualified V0-V3 mesh-profile, solver, and force-stationarity gates. Other candidates, target physics, and grid-independent downforce remain unqualified. |
| P13 | Closed for the guarded current path. Fail-closed adjoint gates were added and the historical P13 record reports 581 passing tests. The current validation snapshot is recorded below. Any new optimizer evidence must still show the requested adjoints converged before consuming gradients. |
| P14 | Closed for the measured RAMP path. Python owns projection, OpenFOAM regularisation is disabled/identity as recorded, and the injected/solver field difference was `1.9e-9`. Do not generalize this closure to unbound historical artifacts. |
| P15 | The original "thin geometry alone explains non-convergent downforce" causal claim was refuted for the correct thick candidate: geometry and mesh quality passed, yet downforce remained non-converged. The remaining numerical question is tracked by P16 and the latest local-refinement/transient plan. |
| P16 | Updated 2026-09-20 under the fixed domain: finest downforce drift improved 0.02993 (union box) -> 0.01291 (plain fixed-domain family), 0.01470 with the pre-declared wake-refinement family, still above the 0.005 bound. A factor-isolation experiment showed near-wake level-3 refinement moves forces by only ~0.003, so wake resolution is not the drift driver; the pre-declared next action is a steady vs time-resolved comparison on the same plain-V2 mesh. All union-box force values/ratios/drifts are not transferable to the fixed-domain reference. |
| P17 | Closed as gate implementation (2026-09-20). WP1 binds the Stage V far-field box to `grid.domain_bounds_m` and runs a declared `stage_v_clearance_v1` (0.25 m) pre-mesh clearance preflight; the recorded wrong candidate is rejected with a no-launch artifact, and the correct candidate passes. Real re-meshing under the fixed domain has not been re-run yet. Evidence: `evidence/stage_v_domain_clearance_2026_09.json`, `tests/test_stage_v_domain_preflight.py` (601 passed). |

### Contradictions that must remain visible

- "Stage V V0-V3 qualified" means mesh-profile, residual-control, and force-stationarity gates passed for one reduced candidate. It does not mean downforce grid convergence, target-physics qualification, or ranking qualification.
- `raw_mesh_ok=false` and `stage_v_qualified=true` coexist by design in the registered profile. Concave-cell output is the only allowed raw failed marker within numeric limits; it is not a raw clean pass.
- The old grey-candidate negative ranking and the later binary-candidate positive sign are results for different physical candidates and different qualification states. Neither result alone settles P1.
- The thick-candidate V3 result refutes the first P15 causal explanation, but it does not solve P16. A smaller downforce drift is still above the pre-registered bound.
- The `keep_round` V3 failure must not be combined with the `step0` V3 force sequence. They are different candidate IDs and different artifacts.
- Current Stage V evidence is steady incompressible laminar at the reduced operating point. Do not call it RANS or extrapolate it to FSAE high-Re vehicle aerodynamics.

## Issue-Driven Next Implementation Plan

The latest `phase_plan.md` order controls. The older resolution plan still
provides useful contract tests, but it must not reorder the immediate Stage V
qualification slice. Do not start a long optimizer run to answer a geometry or
reference-quality question.

| Package | Dependencies | Acceptance criteria | Stop/go rule | Required evidence |
| --- | --- | --- | --- | --- |
| WP0: preserve and classify | None | Current branch, commit, spec hash, candidate IDs, and existing evidence paths are recorded; historical artifacts are immutable. | Stop if the input candidate or evidence hash is unclear. Go only with a reproducible baseline. | Baseline manifest, `git status`, commit, environment report, input SHA-256 list. |
| WP1: fixed domain and clearance preflight | v2 ProblemSpec, Stage V adapter, candidate STL | A fixed ProblemSpec far-field box is required; case generation uses it rather than candidate union bounds. A physical candidate-to-six-boundary clearance is computed against a declared margin, recorded, and checked before meshing. | Stop before any mesh command if domain is missing/invalid, candidate is outside, clearance is non-finite or below margin, or candidate/spec hashes do not bind. | Versioned domain/clearance profile, `stage_v_domain_preflight.json`, updated case metadata, candidate/spec hashes, negative and positive unit fixtures. |
| WP2: requalify the two distinct candidates | WP1 | The correct `step0` candidate is evaluated with the fixed domain; the wrong `keep_round` candidate fails the new preflight before `blockMesh` or `snappyHexMesh`. No threshold is relaxed to rescue it. | Stop if the wrong candidate reaches meshing, or if the correct candidate's domain differs from the recorded manifest. Go to grid study only with a preflight-passing candidate. | Per-candidate preflight, no-launch failure artifact for wrong candidate, mesh logs, profile qualification JSON, solver summary, force history, hashes. |
| WP3: settle the reduced Stage V reference one factor at a time | WP2 and correct candidate fixed | Freeze candidate, operating point, numerics, force normalization, and profile. Use predeclared local refinement around body/wake; require three qualified levels and Cd relative <= 0.02 plus downforce absolute <= 0.005. If steady downforce still fails, compare steady and time-resolved runs on the same mesh. | Stop ranking if any level is unqualified, force stationarity fails, downforce misses the bound, or the model comparison changes the question. Do not auto-add global V4 without a predeclared experiment. | Experiment manifest, local-refinement meshes, all raw/profile mesh records, solver residual/continuity records, force components/history, grid convergence JSON, steady/transient comparison. |
| WP4: restore Gate 0 before new optimizer evidence | WP3 for ranking use; individual contract tests can run earlier | Complete C0-C3 and P7/P14 checks: converged requested adjoints, semantic response/solver/direction/sign/unit binding, candidate-specific immutable provenance, four-array generation consistency, and one projection/filter owner. | Stop gradient export, candidate acceptance, and ranking if any binding or convergence check fails. Historical diagnostic artifacts remain diagnostic-only. | Mutation tests, binding artifact, candidate manifest, array/hash lineage, projection profile, finite-difference report, failure reports. |
| WP5: fixed-shape numerical separation | WP4 for any ranking conclusion; fixed analytic shapes may be used to debug | Run pre-registered binary shapes on same-grid T and V, then isolate extraction threshold, Stage T resolution, alphaMax/leakage, and transfer factors one at a time. Resolve P3/P6/P11 without mixing optimizer changes. | Stop if the experiment changes geometry, physics, grid, projection, and transfer simultaneously, or if a failure is attributed to an unisolated factor. | Geometry/occupancy/STL shared IDs, same-grid T reports, V reports, alphaMax sweep, transfer FD suites, extraction metrics, uncertainty table. |
| WP6: ranking qualification | WP3, WP4, WP5 | Use at least eight pre-registered candidates. Report Spearman, Kendall, every required pair sign, uncertainty, extraction sensitivity, and response-specific pass/unresolved/No-Go. Only count a difference when it exceeds the declared uncertainty. | Stop and report unresolved or response-specific No-Go; do not tune the optimizer to reverse a fixed-shape result. | Cross-fidelity ranking JSON/Markdown, all candidate manifests and hashes, qualified T/V runs, uncertainty and pair-sign table. |
| WP7: production optimizer and Stage S | WP6 pass for surrogate-dependent work; G3/G4 gates | Add physical beta volume, nonlinear re-evaluation/rollback, checkpoint/resume, feasible seed restoration, production constrained backend, quantitative density-to-SDF fidelity, P9 cleanup, then SDF evolution. | Stop if Gate 4 is unresolved/No-Go or if a candidate lacks independent qualification. Do not advance to FSAE/full vehicle from reduced laminar evidence. | Immutable iteration history, accepted/rejected candidate artifacts, constraints, SDF fidelity metrics, Stage S qualification, independent Stage V report. |

### Immediate next slice: fixed domain plus pre-mesh clearance

**Status 2026-09-20: WP1 is implemented and validated** (commits after
`8be881d` on `feat/p0-openfoam-closed-loop`). The fixed-domain binding
(`grid.domain_bounds_m` -> `problem_spec_to_project_config` -> `build_fields` ->
blockMesh/case_metadata) and the fail-closed pre-mesh clearance preflight
(`stage_v_clearance_v1`, declared 0.25 m margin) exist in
`src/cfd_sdf/stage_v_domain_preflight.py`, are wired into
`scripts/stage_t_filtered_ramp.py` (`mesh_sweep`, `phase_stagev_level`), and
cover the original 8 required behaviors including both recorded candidate IDs
(`tests/test_stage_v_domain_preflight.py`). The recorded wrong candidate
`opt_q100_b0_step5_try1_block_keep_round` is rejected before meshing with a
no-launch artifact
(`work/filtered_ramp/wmin_0.2/stage_v_mesh/<cid>/<level>/stage_v_domain_preflight.json`);
the correct candidate passes (minimum clearance 0.37396 m at `top`).
Evidence: `evidence/stage_v_domain_clearance_2026_09.json`. What remains from
WP1 is only re-running actual Stage V meshing/solving under the fixed domain
(WP2), which now belongs to the WP3 grid study below.

Original specification of the slice (kept for context; do not weaken its
fail-closed requirements):

After WP1 (implemented 2026-09-20), the next slices in order are WP2 (re-run
actual meshing/solving for the correct candidate under the fixed domain) and
WP3 (grid study). The bounded Stage V profile uses the existing v2
`grid.domain_bounds_m` as the explicit fixed outer box for this case, rather
than inventing bounds from the candidate's union bounds. If future profiles need
different canonical and CFD boxes, add a versioned explicit contract field; do
not silently reinterpret or infer one from geometry.

The implementation must:

1. Require finite lower/upper bounds with positive extents and a valid grid alignment for the selected Stage V resolution.
2. Carry those bounds from ProblemSpec through `problem_spec_to_project_config`, field generation, blockMesh rendering, and `case_metadata.json`.
3. Declare the physical clearance margin in the versioned ProblemSpec/profile used by the run. Do not use a result-dependent or silently cell-count-derived threshold.
4. Compute candidate clearance to each axis-aligned far-field plane from the candidate surface bounds: `xmin-lower_x`, `upper_x-xmax`, `ymin-lower_y`, `upper_y-ymax`, `zmin-lower_z`, and `upper_z-zmax`.
5. Fail closed if any candidate point is outside the fixed box or any clearance is below the declared physical margin. Record the limiting patch and all six values.
6. Run this preflight before `blockMesh`, `surfaceFeatureExtract`, `snappyHexMesh`, and `simpleFoam`. A failed preflight may write a diagnostic artifact but must not write a solver-launch artifact claiming permission.
7. Bind the preflight to the ProblemSpec SHA-256, candidate STL SHA-256, selected flow case, voxel size, margin/profile ID, and domain bounds.
8. Add tests for missing/invalid domain, exact boundary contact, below-margin clearance, just-passing clearance, and the two recorded candidate IDs. The wrong candidate must be rejected at this preflight layer.

The expected evidence is a new versioned clearance/profile report, not a
rewrite of `stage_v_v3_requalification_2026_09.json`. The existing V3 JSON is
the historical record of what was measured; the new report must show that the
same class of boundary failure is caught earlier.

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
