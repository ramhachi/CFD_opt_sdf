# Legacy A-K Body-Fitted Adjoint Roadmap

Plan name: `Legacy A-K Body-Fitted Adjoint Roadmap`
Status: historical, superseded
Superseded by: `TSV Roadmap`

> Historical record only. This plan documents the parametric, STL-remeshing,
> and body-fitted adjoint adapter work completed before the roadmap reset on
> 2026-07-02. The authoritative plan is `docs/phase_plan.md`.

## Phase 1: Single-Point CFD Evaluation

Status: implemented with OpenFOAM case preparation, dry-run execution planning, Docker execution, log paths, and forceCoeffs postprocessing.

Verified:
- `cfd-sdf evaluate`
- `cfd-sdf run-openfoam`
- `cfd-sdf postprocess-openfoam`
- `cfd-sdf run-openfoam --backend docker --execute`
- pytest coverage for case generation, dry-run planning, and force coefficient parsing

External dependency model:
- Real OpenFOAM execution requires an external solver backend: Docker/OpenFOAM or WSL/Linux OpenFOAM.
- Binary packaging should ship this tool and call that backend, not bundle OpenFOAM into the executable.

## Phase 2: Low-Dimensional Parametric Optimization

Status: implemented with a parametric front-wing STL generator, mock aerodynamic evaluator, constraint-aware candidate evaluation, run database, and best-candidate export.

Verified:
- `cfd-sdf optimize-parametric`
- `scripts/run_parametric_optimization_demo.ps1`
- pytest coverage for parametric geometry, mock aero, and optimization run database output

Current evaluator modes:
- `mock`
- `openfoam-dry-run`

## Phase 3: Constraint-Hardened Optimization

Status: implemented for parametric optimization.

Implemented:
- Turn current penalties into explicit constraint records per candidate.
- Add candidate rejection modes before CFD.
- Add front/rear downforce ratio bookkeeping.
- Add optimization history CSV.
- Add resume support for parametric runs.

Verified:
- pytest coverage for structured constraint records
- pytest coverage for front/rear ratio enforcement
- pytest coverage for resume reusing existing candidate results

Remaining:
- History plots are not implemented yet; CSV is available for plotting.

## Phase 4: Topology Exploration Pre-Stage

Status: implemented as a geometry-only density-field pre-stage.

Implemented:
- Add density field storage inside the allowed domain.
- Convert density fields to STL/SDF candidate geometry.
- Run geometry-only updates before coupling to CFD.
- Validate generated topology STL candidates with existing SDF constraints.
- Write density VTI, topology history CSV, topology summary, and promoted best candidate.

Verified:
- `cfd-sdf explore-topology`
- `scripts/run_topology_exploration_demo.ps1`
- pytest coverage for density generation, STL extraction, topology run database, and resume

## Phase 5: Topology + Low-Fidelity CFD

Status: implemented as a low-fidelity topology ranking and OpenFOAM dry-run handoff stage.

Implemented:
- Score each topology density candidate with projected-area low-fidelity Cd, downforce, efficiency, and front/rear downforce bookkeeping.
- Use the same enforced constraint record model as the parametric optimizer.
- Rank and promote `best_topology/` by objective among accepted candidates.
- Add `openfoam-dry-run` handoff for accepted topology candidates.
- Keep each final candidate converted back to STL, SDF validation outputs, and body-fitted OpenFOAM case preparation.

Verified:
- `cfd-sdf explore-topology --evaluator low-fi`
- `cfd-sdf explore-topology --evaluator openfoam-dry-run`
- `scripts/run_topology_exploration_demo.ps1`
- pytest coverage for low-fidelity topology scoring, best-candidate selection, resume, and OpenFOAM dry-run handoff

Remaining:
- This is a deterministic ranking surrogate, not a real porous/Brinkman flow solve.
- Real OpenFOAM execution still depends on OpenFOAM availability through Docker or WSL/Linux.

## Phase 6: Practical Optimization Runner

Status: implemented as a resumable practical runner around the parametric and topology engines.

Implemented:
- Add a unified `run-optimization` command for parametric and topology candidate loops.
- Write `run_manifest.json`, `progress.json`, `runner_summary.json`, and `run_summary.md`.
- Reuse existing candidate result files with `--resume`.
- Classify accepted, rejected, and failed candidates by enforced constraint category.
- Export the current best candidate to `best_design/`.
- Add a Phase 6 demo script.

Verified:
- `cfd-sdf run-optimization --mode topology`
- `cfd-sdf run-optimization --mode parametric`
- `scripts/run_practical_optimization_demo.ps1`
- pytest coverage for practical-run monitoring artifacts and best-design export

Remaining:
- Retry policy is classification-ready but not yet an automatic retry scheduler.
- Real OpenFOAM execution scheduling still depends on configured Docker or WSL/Linux OpenFOAM.
- Monitoring is currently JSON/Markdown, not a GUI dashboard.

## Adjoint Phase A: Data Contract

Status: implemented as an explicit data-contract document.

Implemented:
- Define authoritative artifacts for project input, SDF state, density design state, constraint reports, CFD summaries, sensitivity fields, and density updates.
- Define coordinate and sign conventions.
- Define responsibility boundaries for geometry, topology state, CFD, sensitivity, and optimizer layers.
- Document the readiness matrix from Phase A through Phase K.

Verified:
- `docs/adjoint_data_contract.md`

## Adjoint Phase B: Density/SDF Design State

Status: implemented enough for Phase C handoff.

Implemented:
- Add `design_state.json` as the candidate design-variable manifest.
- Standardize `density.vti` as the authoritative density field.
- Keep `density_field.vti` as a compatibility export.
- Keep `geometry/front_wing_initial.stl` as a derived CFD input.

Verified:
- `design_state.json` schema validation is used by the Phase C sensitivity layer.
- Phase C code consumes `design_state.json` and `density.vti` directly.

Remaining:
- Tighten version-migration behavior if schema version 2 is introduced.

## Adjoint Phase C: Sensitivity I/O

Status: initially implemented with mock/analytic sensitivity fields.

Implemented:
- Add `sensitivity.vti` writer and reader with required density-sensitivity arrays.
- Add `sensitivity_summary.json` writer with backend, sign convention, source design state, array list, and statistics.
- Add `density_update.vti` writer and reader for a move-limited gradient-descent preview.
- Add `write-mock-sensitivity` CLI command.
- Add `preview-density-update` CLI command.

Verified:
- pytest coverage for required sensitivity arrays, schema fields, active mask, move-limit clipping, and density bounds.

Remaining:
- Real adjoint output ingestion is not implemented yet.
- Surface-to-grid sensitivity projection is not implemented yet.
- This phase locks the file contract; it is not yet a production optimizer update loop.

## Adjoint Phase D: Density Update Optimizer

Status: initially implemented with mock/analytic sensitivities.

Implemented:
- Add `optimize-density` CLI command.
- Add a resumable density optimizer runner with per-step directories.
- Consume `design_state.json` and `sensitivity.vti` as the update inputs.
- Write per-step `sensitivity.vti`, `sensitivity_summary.json`, `density_update.vti`, updated `density.vti`, derived STL, SDF report, and `density_step_result.json`.
- Enforce move limit, density bounds, and volume fraction bounds.
- Add Gaussian density filtering, a minimum-thickness local-density proxy, root-preservation proxy, and optional Heaviside projection.
- Write `density_optimization_history.csv`, `density_optimization_summary.json`, and `best_design/`.

Verified:
- pytest coverage for density optimizer outputs, move-limit behavior, volume bound, resume, and best export.

Remaining:
- The sensitivities are still mock/analytic, not adjoint CFD.
- Connectivity/root behavior is still a proxy plus SDF constraint validation, not a full differentiable connectivity constraint.
- This loop is not yet coupled to real OpenFOAM primal/adjoint runs.

## Adjoint Phase E: Finite-Difference Gradient Check

Status: initially implemented for the mock/analytic sensitivity contract.

Implemented:
- Add `check-gradient` CLI command.
- Add finite-difference checks for a small set of active density cells.
- Support `auto`, `forward`, and `central` perturbation modes. `auto` falls back
  to one-sided perturbations for density variables on the 0/1 bounds.
- Compare finite-difference derivative against `objective_density_sensitivity`.
- Write `finite_difference_check.json`, `finite_difference_samples.csv`, and
  `finite_difference_check.vti`.
- Classify each sample as `ok`, `sign_mismatch`, `relative_error`, or
  `failed_perturbation`.

Verified:
- pytest coverage for finite-difference output files, sign checks, relative
  error tolerance, and ParaView diagnostic arrays.

Remaining:
- Finite-difference checks currently validate the mock objective, not OpenFOAM
  primal or adjoint results.
- Control-variable perturbations for low-dimensional shape parameters are not
  implemented yet.

## Adjoint Phase F: Real OpenFOAM Runner Coupling

Status: initially implemented for topology candidates.

Implemented:
- Add `openfoam` topology evaluator for actual solver execution.
- Keep `openfoam-dry-run` for case-generation smoke tests.
- Pass `timeout_seconds` from `explore-topology` and `run-optimization` into the OpenFOAM backend runner.
- Capture OpenFOAM timeout and OS execution errors in `openfoam_run_summary.json`.
- Postprocess force coefficients into `cfd_summary.json`.
- Replace low-fidelity aero objective and constraints with parsed CFD Cd,
  downforce, efficiency, and front/rear downforce when execution succeeds.
- Record `cfd_case_dir`, `cfd_run`, `cfd_summary`, and `cfd_error` in
  `topology_result.json`.
- Classify `openfoam_*` failures as `failed_cfd` in the practical runner.
- Preserve resume and best-design export through the existing topology and
  practical runner result files.

Verified:
- pytest coverage for OpenFOAM execution-mode handoff with a mocked solver
  producing `coefficient.dat`.
- pytest coverage for `failed_cfd` classification.
- Existing Docker single-case primal path remains available through
  `cfd-sdf evaluate --backend docker --execute`.

Remaining:
- Full real Docker candidate execution was not rerun for every topology
  candidate in this phase because it is slow.
- Automatic retry scheduling is not implemented.
- Parametric candidates still only support `openfoam-dry-run`; real execution is
  implemented for topology candidates, which is the active adjoint/topology path.

## Adjoint Phase G: Adjoint Solver Selection

Status: implemented.

Decision:
- Select OpenFOAM `adjointOptimisationFoam` as the first real adjoint backend.
- Backend id for future code: `openfoam-adjoint`.
- Keep DAFoam and SU2 as later alternatives.

Implemented:
- Add `docs/adjoint_solver_selection.md`.
- Compare OpenFOAM `adjointOptimisationFoam`, DAFoam, and SU2 discrete adjoint
  against the current SDF/density/OpenFOAM pipeline.
- Verify that the current `opencfd/openfoam-default:2512` Docker image contains
  `adjointOptimisationFoam`.
- Define the Phase H adapter boundary and first implementation path.

Verified:
- `docker run --rm opencfd/openfoam-default:2512 bash -lc "command -v adjointOptimisationFoam && adjointOptimisationFoam -help | head -40"`

Remaining:
- Generate a real adjoint case from our front-wing primal case.
- Identify and parse the exact sensitivity output files produced by
  `adjointOptimisationFoam` for the chosen objective.

## Adjoint Phase H: Adjoint Backend Adapter

Status: initially implemented as an OpenFOAM adapter skeleton.

Implemented:
- Add `run-adjoint` CLI command.
- Add `run_openfoam_adjoint_adapter` API.
- Resolve `design_state.json` to the candidate project and primal OpenFOAM case.
- Generate the primal OpenFOAM case if it does not already exist.
- Create an adjoint adapter case directory beside the primal case by copying the
  primal case skeleton.
- Generate initial `adjointOptimisationFoam` case files:
  `system/optimisationDict`, adjoint `controlDict`, adjoint fv/fa solution
  dictionaries, `constant/adjointRASProperties`, and adjoint initial fields.
- Add an adjoint preflight report that distinguishes case-file readiness from
  mesh readiness before `--execute` is allowed to run the solver.
- Build backend commands for `adjointOptimisationFoam` through local, WSL, or
  Docker execution modes.
- Write `adjoint_adapter_config.json`, `adjoint_run_summary.json`,
  stdout/stderr logs, backend command, timeout/error state, and raw-output list.
- Provide an explicit mock-contract `sensitivity.vti` fallback so downstream
  sensitivity/update/projection code can continue to be tested during dry runs
  before raw adjoint sensitivity parsing is complete.
- Suppress mock fallback during failed `--execute` runs so a solver/preflight
  failure cannot be mistaken for real adjoint sensitivity.
- Parse OpenFOAM `faceSensNormal...` volScalarField output by combining patch
  boundary values with `constant/polyMesh` face centres, then emit normalized
  `surface_sensitivity.csv`.
- Project parsed OpenFOAM face sensitivities to the density grid and write
  `sensitivity.vti`/`sensitivity_summary.json`.

Verified:
- pytest coverage for dry-run adapter summary, command generation, case
  directory creation, and fallback `sensitivity.vti`/`sensitivity_summary.json`.
- pytest coverage for generated adjoint dictionaries and preflight blocking an
  unmeshed case without writing mock sensitivity.
- CLI smoke for `run-adjoint --backend docker` writes generated adjoint files
  and a preflight report.
- CLI smoke for `run-adjoint --execute --backend docker` on an unmeshed case
  exits nonzero with `constant/polyMesh/boundary` as the blocking issue.
- CLI smoke for `run-adjoint --execute --backend docker` on an already meshed
  Phase F candidate returns `returncode: 0`, detects OpenFOAM raw sensitivity
  fields, exports 1201 surface sensitivity samples, and writes projected
  `sensitivity.vti`.

Remaining:
- The generated adjoint case dictionaries need solver-level tuning and
  objective/scaling validation.
- Only the OpenFOAM `faceSensNormal...` scalar surface output is parsed. Vector,
  point, smoothed-volume, and topology-specific output variants are not parsed.
- The fallback `sensitivity.vti` is mock sensitivity and must not be treated as
  real adjoint output; it is only emitted for dry-run adapter tests.

## Adjoint Phase I: Sensitivity Projection

Status: initially implemented for normalized surface-sensitivity CSV input.

Implemented:
- Add `write-mock-surface-sensitivity` CLI command for projection testing.
- Add `project-sensitivity` CLI command.
- Add normalized `surface_sensitivity.csv` reader with required `x`, `y`, `z`,
  and `objective_surface_sensitivity` columns.
- Project surface sensitivities to density-grid arrays using nearest surface
  samples with Gaussian weights inside a narrow band.
- Write common `sensitivity.vti` arrays:
  `objective_density_sensitivity`, `downforce_density_sensitivity`,
  `drag_density_sensitivity`, `constraint_sensitivity`, and `active_mask`.
- Write `projection_diagnostics.vti` with `projection_distance`,
  `projection_weight_sum`, and projected objective sensitivity for ParaView QA.
- Connect `openfoam-adjoint` adapter to surface CSV projection when raw output
  includes a matching surface sensitivity CSV.
- Connect `openfoam-adjoint` adapter to OpenFOAM `faceSensNormal...` parsing
  and density-grid projection for real adjoint smoke runs.
- Verify projected `sensitivity.vti` can be consumed by `density_update.vti`
  preview.

Verified:
- pytest coverage for surface CSV projection outputs and density update handoff.
- pytest coverage for adjoint adapter using surface CSV projection when
  available.

Remaining:
- Additional raw OpenFOAM adjoint output variants still need parsers.
- Volume sensitivity projection is not implemented yet.
- Projection scaling is currently a conservative direct transfer; calibration
  against real adjoint outputs remains future work.

## Adjoint Phase J: Adjoint-Driven Topology Loop

Status: initially implemented with dry-run adjoint adapter support and
adapter-provided sensitivity handoff.

Implemented:
- Add `run-adjoint-topology` CLI command.
- Add `run_adjoint_topology_optimization` API.
- Add optional real primal CFD execution per step with `primal_execute`.
- Generate a per-step OpenFOAM primal case from the current `design_state.json`,
  execute it through the configured backend, postprocess `cfd_summary.json`, and
  pass the meshed case directory into the adjoint adapter.
- Add optional post-update real primal CFD execution with
  `post_update_primal_execute`; when enabled, the updated `design_state.json` is
  evaluated with OpenFOAM and the step objective/status/best ranking use the
  post-update CFD constraints.
- Add optional `stop_on_rejection` / `--stop-on-rejection` guard so rejected
  post-update designs are not fed into the next iteration during real CFD runs.
- Execute the staged loop:
  `design_state.json -> openfoam-adjoint adapter -> surface_sensitivity.csv ->
  project-sensitivity -> density update -> derived STL -> SDF constraints ->
  next design_state.json`.
- Consume adapter-provided `sensitivity.vti` directly when real adjoint
  execution and projection succeed.
- Raise on failed `--execute-adjoint` runs instead of silently continuing with
  mock sensitivity.
- Write per-step `adjoint_topology_step_result.json`.
- Write `adjoint_topology_history.csv` and `adjoint_topology_summary.json`.
- Write `adjoint_topology_summary.md`.
- Export `best_design/`.
- Support resume through existing per-step result files.

Verified:
- pytest coverage for two-step loop output, resume behavior, history, and best
  export.
- pytest coverage for primal CFD execution handoff into the adjoint adapter
  using a mocked OpenFOAM run.
- pytest coverage for post-update primal CFD re-ranking using a mocked
  OpenFOAM run.
- CLI smoke for dry-run topology loop writes JSON, CSV, Markdown, and
  best-design artifacts.
- CLI smoke for one real step:
  `run-adjoint-topology --execute-primal --execute-adjoint --backend docker`
  runs primal OpenFOAM, runs `adjointOptimisationFoam`, parses
  `faceSensNormal...`, writes projected `sensitivity.vti`, updates density, and
  exports best design.
- CLI smoke for one real step with post-update CFD:
  `run-adjoint-topology --execute-primal --execute-adjoint --execute-updated-primal --backend docker`
  runs primal OpenFOAM before and after the density update and uses the
  post-update CFD constraint result for step ranking.
- CLI smoke for a guarded three-iteration request:
  `run-adjoint-topology --iterations 3 --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --backend docker`
  stops after the first post-update CFD rejection and reports
  `completed_iterations` plus `stopped_reason`.
- CLI smoke for `check-adjoint-direction` compares projected real adjoint
  sensitivity against pre/post primal CFD deltas and writes JSON, Markdown, and
  VTI diagnostics.
- CLI smoke for `check-adjoint-paired-directions` writes positive/negative
  direction design states, reuses positive post-update CFD, executes negative
  primal CFD, and records whether a sensitivity sign decision is possible.
- CLI smoke for centered `check-adjoint-paired-directions --centered` executes
  center, positive, and negative primal CFD cases with nonzero density motion
  in both directions and selects the current positive update direction.
- CLI smoke for centered `check-adjoint-paired-directions --centered
  --perturbation-scale 0.5` repeats the real primal comparison at half
  amplitude and selects the same positive update direction.
- CLI smoke for centered `check-adjoint-paired-directions --centered
  --perturbation-scale 0.25` repeats the real primal comparison at quarter
  amplitude and selects the same positive update direction.
- CLI smoke for centered paired directions on a later topology state
  (`adjoint_step_0002`) selects the same positive update direction, increasing
  aggregate calibration evidence across more than one density state.
- CLI smoke for `summarize-adjoint-calibration` aggregates the full- and
  smaller-amplitude centered paired reports, writes JSON/Markdown summaries,
  keeps the current smoke-case update direction, and estimates a derivative
  multiplier near `-0.00232`.
- CLI smoke for `run-adjoint-topology --calibration-summary ... --iterations 2
  --stop-on-rejection` records calibration multipliers in the run summary,
  history, and density-update VTI arrays.
- CLI smoke for a real guarded calibrated request:
  `run-adjoint-topology --iterations 3 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary ... --stop-on-rejection`
  runs primal CFD, adjoint CFD, and post-update primal CFD once, then stops on
  `efficiency_constraint` before step 1.
- CLI smoke for a real guarded feasibility-progress request:
  `run-adjoint-topology --iterations 3 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary ... --stop-on-rejection --continue-on-constraint-improvement`
  completes three real primal/adjoint/post-update-primal steps as
  `improving_infeasible`, with enforced violation decreasing at every step.
- CLI smoke for the same real guarded feasibility-progress request using the
  eight-observation v3 calibration summary records the v3 derivative multiplier
  in the run summary/history and density-update controls while preserving the
  same guarded infeasible-improvement behavior.
- CLI smoke for a v3-calibrated two-step continuation from the later density
  state keeps reducing enforced violation and creates another later density
  state for calibration.
- CLI smoke for centered paired directions on that later continuation state
  again selects the positive update direction.
- CLI smoke for the v4 calibration summary aggregates five centered paired
  reports, ten candidate observations, and recommends the same search direction
  with a derivative multiplier near `-0.00233`.
- CLI smoke for a v4-calibrated two-step real continuation records the v4
  derivative multiplier in the run summary/history and reduces enforced
  violation to roughly `0.505`.
- CLI smoke for `run-adjoint-topology --efficiency-min-override 1.05` verifies
  the real-CFD accepted-step path with two accepted v4-calibrated steps and
  best-design export. This is an acceptance-path smoke only; it does not satisfy
  the default project `efficiency_min: 3.0` target.
- CLI smoke for `run-adjoint-topology --constraint-sensitivity-weight 2.0`
  verifies that normalized `constraint_sensitivity` can be blended into the
  density-update gradient and exported to ParaView-visible update arrays.
- `sensitivity_summary.json` now records `constraint_sensitivity_status` and
  `constraint_sensitivity_diagnostics`, including explicit detection of the
  current zero-drag OpenFOAM adjoint projection.
- Density updates now record requested/effective constraint-blend weights and
  force the effective weight to zero when diagnostics report an unusable
  constraint sensitivity.
- A real OpenFOAM-derived zero-drag sensitivity guard check writes
  `adjoint_phase_l_zero_drag_guard_check/density_update_guarded/` and confirms
  requested weight `2.0` becomes effective weight `0.0`.

Remaining:
- The adjoint adapter is still dry-run by default.
- Dry-run mode still uses generated mock surface sensitivity.
- Real multi-iteration requests can now progress from an infeasible state when
  explicitly guarded by `--continue-on-constraint-improvement`, but the current
  v4-calibrated smoke still has `accepted_count: 0` because the efficiency
  constraint remains positive after the current continuation steps.
- Real multi-iteration requests can also produce accepted steps when an
  explicit run-local `--efficiency-min-override` is used, but the default
  `efficiency_min: 3.0` target is still not feasible in the current smoke.
- Constraint-aware density updates are wired, but the current real adjoint
  projection is diagnosed as `degenerate_zero_drag_sensitivity`, so real
  efficiency reduction remains limited until the adjoint backend exports
  independent drag or direct constraint sensitivity.
- Post-update real primal re-evaluation is optional because it doubles primal
  CFD cost per iteration.
- The first real direction check reports sign mismatch, so `faceSensNormal...`
  sign/scale must be calibrated before unguarded multi-step optimization.
- Centered paired direction selects the current positive update direction for
  the smoke case, but first-order sensitivity prediction still has opposite
  sign from the realized CFD delta.
- Half-amplitude centered paired direction also selects the positive update
  direction. The aggregate calibration summary estimates the derivative
  sign/scale for this smoke case, but the multiplier still needs repeated
  candidate validation before being used as a default for real unguarded runs.
- Quarter-amplitude centered paired directions also select the positive update
  direction and keep the aggregate derivative multiplier stable across the
  initial state and later topology states.

## Adjoint Phase K

Status: initially implemented as a verification report and smoke-test bundle.

Implemented:
- Add `docs/verification_report.md`.
- Record compile, pytest, finite-difference, OpenFOAM Docker primal,
  adjoint-adapter dry-run, real adjoint execute, surface-projection, and
  dry-run and real one-step adjoint-topology smoke evidence.
- Keep a clear confidence/limitations split so mock sensitivity is not confused
  with real adjoint sensitivity.

Verified:
- `.\.venv\Scripts\python.exe -m compileall src tests`
- `.\.venv\Scripts\python.exe -m pytest -q`
- `cfd-sdf project-sensitivity`
- `cfd-sdf run-adjoint-topology --iterations 1 --backend docker`
- `cfd-sdf run-adjoint-topology --iterations 1 --backend docker --execute-primal --execute-adjoint`
- `cfd-sdf run-adjoint-topology --iterations 1 --backend docker --execute-primal --execute-adjoint --execute-updated-primal`
- `cfd-sdf run-adjoint-topology --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection`
- `cfd-sdf check-adjoint-direction <adjoint_topology_step_result.json>`
- `cfd-sdf check-adjoint-paired-directions <adjoint_topology_step_result.json> --execute-primal --backend docker`
- `cfd-sdf check-adjoint-paired-directions <adjoint_topology_step_result.json> --execute-primal --backend docker --centered`
- `cfd-sdf check-adjoint-paired-directions <adjoint_topology_step_result.json> --execute-primal --backend docker --centered --perturbation-scale 0.5`
- `cfd-sdf check-adjoint-paired-directions <adjoint_topology_step_result.json> --execute-primal --backend docker --centered --perturbation-scale 0.25`
- `cfd-sdf summarize-adjoint-calibration <paired_adjoint_direction_check.json> ...`
- `cfd-sdf run-adjoint-topology <design_state.json> --iterations 2 --calibration-summary <adjoint_calibration_summary.json> --stop-on-rejection`
- `cfd-sdf run-adjoint-topology <design_state.json> --iterations 3 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary <adjoint_calibration_summary.json> --stop-on-rejection`
- `cfd-sdf run-adjoint-topology <design_state.json> --iterations 3 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary <adjoint_calibration_summary.json> --stop-on-rejection --continue-on-constraint-improvement`
- `cfd-sdf run-adjoint-topology <later design_state.json> --iterations 2 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary <adjoint_calibration_summary_v4.json> --stop-on-rejection --continue-on-constraint-improvement`
- `cfd-sdf run-adjoint-topology <later design_state.json> --iterations 2 --execute-primal --execute-adjoint --execute-updated-primal --calibration-summary <adjoint_calibration_summary_v4.json> --stop-on-rejection --efficiency-min-override <value>`
- `cfd-sdf run-adjoint-topology <design_state.json> --iterations 1 --calibration-summary <adjoint_calibration_summary_v4.json> --constraint-sensitivity-weight <value>`
- Existing Phase F Docker OpenFOAM primal smoke output in
  `examples/front_wing/runs/front_wing_demo/adjoint_phase_f_check/`.

Remaining:
- Find or generate a feasible post-update real-CFD candidate for the default
  `efficiency_min: 3.0` project target.
- Add centered checks across more independent topology candidates, then decide
  whether to apply the calibrated derivative sign/scale convention
  automatically as a default rather than an explicit calibration-summary input.
