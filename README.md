# CFD SDF Optimization Prototype

Research tool for external-aerodynamic optimization of rigid objects with
arbitrary topology, using fixed-grid density/Brinkman search, SDF refinement,
and body-fitted verification. The front wing is the first complex integration
benchmark, not a hard-coded definition of the final problem class.

This density/Brinkman → SDF → independent body-fitted verification architecture
is the adopted project direction as of 2026-09-09. Each solver backend still
has to pass the numerical and physical gates in `docs/phase_plan.md` before it
is qualified for target aerodynamics.

Current status: G1 is complete. The G2 generic OpenFOAM case compiler,
requested/generated manifest, execution-asset staging, patch mapping, and
convergence evaluator are implemented. The current two-flow G2 specification
passed numerical convergence gates on ARM64 OpenFOAM v2512. Native artifact
semantics and target-physics qualification remain pending; see the roadmap
for the exact evidence scope.

## macOS / Windows research foundation

The portable CPU reference, runtime diagnostics and geometry preflight are
available through `cfd-sdf research`. Apple Silicon can also run the bounded
periodic LBM benchmark on Metal. CUDA and full LBM aerodynamic optimization
are not implemented yet. See [setup and evidence](docs/cross_platform_research.md)
and the [implementation roadmap](docs/phase_plan.md).

## Generic v2 Contract Quick Check

The generic example declares two flow cases, arbitrary response directions,
five response kinds, weighted aggregates, and typed topology policies:

```powershell
.\.venv\Scripts\cfd-sdf.exe validate-problem-spec examples\generic_problem_v2\project.yaml --output-dir examples\generic_problem_v2\contract_output --require-execution-ready
```

This validates and fingerprints the contract. It does not compile or run a CFD
case and does not replace the later geometry/resolution preflight. See
`docs/problem_contract_v2.md` and `docs/fixed_grid_data_contract_v2.md`.

## Authoritative Documentation

- `docs/phase_plan.md` is the only roadmap and status source.
- `docs/problem_contract_v2.md` is the active problem schema.
- `docs/fixed_grid_data_contract_v2.md` is the active Stage T artifact schema.
- `docs/README.md` is the documentation index and compatibility policy.

Historical v1 artifacts remain readable, but there is no separate active v1
roadmap or specification for new development.

The target architecture in the authoritative roadmap is:

```text
fixed-grid density/Brinkman topology search
    -> SDF sharp-interface refinement
    -> body-fitted RANS verification
```

The repository currently contains a reusable Geometry Service, a body-fitted
OpenFOAM verification prototype, and an executable fixed-grid OpenFOAM topO
capability spike with a custom porous-force objective.

Existing geometry capabilities include:

- STL-only input for the first demo.
- Separate SDFs for design geometry, fixed solids, allowed regions, forbidden regions, and root mounts.
- Narrow-band masks for each SDF role, configurable with `grid.band_width_m`.
- Rule-margin checks, tire-clearance checks, root connectivity checks, and eroded-shape thickness checks.
- VTK/ParaView output for visual inspection.

## Goal Command Text

Use this as the goal-command objective:

```text
Implement the arbitrary-topology external-aerodynamic optimizer defined in
docs/phase_plan.md, using the front wing as a complex integration benchmark
rather than the problem definition. Preserve STL-only fixed, design-domain,
forbidden, root, and initial geometry roles. Build on the completed G1 contract
and implemented G2 compiler foundation. Finish G2 runtime and target-physics
qualification, then implement G3 geometry and physical-resolution preflight,
G4 benchmark qualification, and the production Stage T optimizer. Convert
qualified density results to SDF for Stage S sharp-interface refinement and use
Stage V body-fitted OpenFOAM for final verification. Keep canonical JSON,
CSV, Markdown, ParaView, hash/snapshot, and reproducible Windows Docker/WSL
artifacts throughout.
```

## Quick Start

These commands exercise the Geometry Service and compatibility body-fitted
utilities. They are not the active Stage T production sequence; use
`docs/phase_plan.md` for the current implementation order.

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\cfd-sdf.exe init examples\front_wing
.\.venv\Scripts\cfd-sdf.exe build-sdf examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe check-constraints examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe export-vtk examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe validate-outputs examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe prepare-openfoam examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe run-openfoam examples\front_wing\runs\front_wing_demo\openfoam_front_wing
.\.venv\Scripts\cfd-sdf.exe evaluate examples\front_wing\project.yaml
.\.venv\Scripts\cfd-sdf.exe explore-topology examples\front_wing\project.yaml --iterations 3 --evaluator low-fi
.\.venv\Scripts\cfd-sdf.exe write-mock-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json
.\.venv\Scripts\cfd-sdf.exe preview-density-update examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json
.\.venv\Scripts\cfd-sdf.exe optimize-density examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --iterations 2
.\.venv\Scripts\cfd-sdf.exe check-gradient examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --sample-count 8
.\.venv\Scripts\cfd-sdf.exe run-adjoint examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --backend docker
.\.venv\Scripts\cfd-sdf.exe write-mock-surface-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json
.\.venv\Scripts\cfd-sdf.exe project-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\surface_sensitivity.csv
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --iterations 1 --backend docker
```

Run the Stage T0 verification and Stage T1 contract build:

```powershell
.\scripts\run_porous_force_validation.ps1
```

The current OpenFOAM v2512 result is `pass_t0`. The canonical three-dimensional
case passes centered checks for drag, strict `-Z` downforce, and
`3*C_D-C_DF`; the relative errors are `0.045%`, `7.49%`, and `0.424%`
respectively. Stage T1 also passes: all fixed-grid density, mask, primal,
sensitivity, connectivity-placeholder, and iteration artifacts validate on
one 8192-cell grid. Stage T2 now also runs fixed-grid Brinkman primal cases
from `density.vti` without STL extraction or remeshing. Stage T3 now extracts
drag/downforce OpenFOAM topology sensitivity fields from completed T2 cases
into the fixed-grid sensitivity contract and can generate plus/minus T2 cases
for finite-difference direction checks. With converged adjoints, the canonical
cellwise checks now pass for drag, downforce, and `3*C_D-C_DF`; T3 aero
sensitivities are usable for the next fixed-grid optimizer plumbing step.

Run the executed T2 canonical suite:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-primal-suite `
  examples\fixed_grid_backend_spike\report\3d\t1_contract\topology_state.json `
  --run-dir examples\fixed_grid_backend_spike\report\3d\t2_primal_suite_execute `
  --template-case-dir examples\fixed_grid_backend_spike\openfoam\porous_force_3d_fd_base `
  --backend docker --execute --timeout-seconds 300 --overwrite
```

Convert and run the current front-wing density seed through the same fixed-grid
path:

```powershell
.\.venv\Scripts\cfd-sdf.exe build-fixed-grid-contract-from-density `
  examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy `
  --project-yaml examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\project.yaml

.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-primal `
  examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy\topology_state.json `
  --case-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t2_seed_execute `
  --template-case-dir examples\fixed_grid_backend_spike\openfoam\porous_force_3d_fd_base `
  --density-variant seed --backend docker --execute --timeout-seconds 300 --overwrite
```

Extract T3 aerodynamic sensitivities from the completed fixed-grid cases:

```powershell
.\.venv\Scripts\cfd-sdf.exe extract-fixed-grid-sensitivity `
  examples\fixed_grid_backend_spike\report\3d\t2_primal_suite_execute\seed

.\.venv\Scripts\cfd-sdf.exe extract-fixed-grid-sensitivity `
  examples\fixed_grid_backend_spike\report\3d\front_wing_t2_seed_execute
```

Generate and execute a T3 plus/minus finite-difference direction suite:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-primal `
  examples\fixed_grid_backend_spike\report\3d\t1_contract\topology_state.json `
  --case-dir examples\fixed_grid_backend_spike\report\3d\t3_baseline_seed_adjoint_4000 `
  --template-case-dir examples\fixed_grid_backend_spike\openfoam\porous_force_3d_fd_base `
  --density-variant seed --backend docker --execute --timeout-seconds 1800 `
  --overwrite --adjoint-iterations 4000

.\.venv\Scripts\cfd-sdf.exe extract-fixed-grid-sensitivity `
  examples\fixed_grid_backend_spike\report\3d\t3_baseline_seed_adjoint_4000

.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-sensitivity-direction-suite `
  examples\fixed_grid_backend_spike\report\3d\t3_baseline_seed_adjoint_4000 `
  --run-dir examples\fixed_grid_backend_spike\report\3d\t3_direction_seed_drag_adjoint_4000 `
  --sensitivity-vti examples\fixed_grid_backend_spike\report\3d\t3_baseline_seed_adjoint_4000\fixed_grid_sensitivity.vti `
  --objective drag `
  --direction-mode cellwise `
  --epsilon 0.01 `
  --backend docker --execute --timeout-seconds 300 --overwrite
```

Recorded canonical cellwise checks with the converged-adjoint baseline:

| Objective | Finite difference | Adjoint | Relative error | Result |
| --- | ---: | ---: | ---: | --- |
| drag | 0.0646995395 | 0.0611741146 | 5.45% | Pass |
| downforce | 0.0365289651 | 0.0373771318 | 2.27% | Pass |
| efficiency constraint | 0.1794246634 | 0.1680593080 | 6.33% | Pass |

Build the current Stage T cell-density to surface/SDF handoff:

```powershell
.\.venv\Scripts\cfd-sdf.exe build-density-sdf-handoff `
  work\architecture_effectiveness_20260910\t5_update_local\topology_state.json `
  --output-dir work\minimal_tv_closed_loop\p1_t5_handoff
```

The first implementation records the density field, threshold, interpolation,
grid, masks, components, root availability, volume mismatch, SDF convention,
and artifact hashes. Its output is `geometry_handoff_capability_only` and
`ready_for_stage_s=false` until the quantitative fidelity gates in the
[FSAE readiness execution plan](docs/fsae_readiness_execution_plan.md) pass.

Or run setup and the full demo from a single PowerShell command:

```powershell
.\scripts\run_front_wing_demo.ps1
```

## Historical Prototype Utilities

The parametric and low-fidelity candidate runners remain available for
regression testing, orchestration tests, and comparison only. They are not the
main optimization route.

Run the historical parametric demo:

```powershell
.\scripts\run_parametric_optimization_demo.ps1
```

Run the geometry-only density/STL handoff demo:

```powershell
.\scripts\run_topology_exploration_demo.ps1
```

Run the historical practical runner demo:

```powershell
.\scripts\run_practical_optimization_demo.ps1
```

Resume a historical parametric run:

```powershell
.\.venv\Scripts\cfd-sdf.exe optimize-parametric examples\front_wing\project.yaml --iterations 8 --resume --reject-before-cfd
```

Each candidate writes a structured `candidate_result.json` with:

- enforced and non-enforced constraint records
- rejection reasons
- front/rear downforce bookkeeping
- objective, penalty, Cd, downforce, and efficiency

The run directory also contains `history.csv`, `optimization_summary.json`, and a
promoted `best/` candidate copy.

Topology exploration writes density-driven candidates under:

```text
examples/front_wing/runs/front_wing_demo/topology_exploration/
```

Each topology candidate contains:

- `design_state.json`
- `density.vti`
- legacy-compatible `density_field.vti`
- density iso-surface STL at `geometry/front_wing_initial.stl`
- SDF constraint report and ParaView exports
- low-fidelity Cd, downforce, efficiency, objective, and rejection status
- `topology_result.json`

The topology run writes `topology_history.csv`, `topology_summary.json`, and
`best_topology/`. The best topology is selected by the lowest objective among
accepted candidates, falling back to the lowest objective if every candidate is
rejected.

For Phase C sensitivity I/O, generate mock/analytic sensitivity fields for any
topology candidate:

```powershell
.\.venv\Scripts\cfd-sdf.exe write-mock-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json
.\.venv\Scripts\cfd-sdf.exe preview-density-update examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --move-limit 0.05
```

This writes:

- `sensitivity.vti`
- `sensitivity_summary.json`
- `density_update.vti`

The mock sensitivity uses the documented sign convention:
`objective_density_sensitivity = d objective / d density`, where negative
values favor increasing density during gradient descent. It is not an adjoint
CFD sensitivity yet; it exists to lock the file schema and optimizer handoff.

Run the initial Phase D density optimizer loop from a topology candidate:

```powershell
.\.venv\Scripts\cfd-sdf.exe optimize-density examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --iterations 2 --move-limit 0.05 --volume-fraction-max 0.55
```

This writes `density_step_0000/`, `density_step_0001/`, a
`density_optimization_history.csv`, `density_optimization_summary.json`, and
`best_design/`. Each step contains the input sensitivity, proposed update,
updated density field, derived STL, SDF constraint report, and low-fidelity
aero score. This is still a mock-sensitivity optimizer loop, not an adjoint
solver loop.

Check the mock sensitivity sign and magnitude with finite differences:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-gradient examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --sample-count 8 --epsilon 1e-4
```

This writes `finite_difference_check.json`, `finite_difference_samples.csv`,
and `finite_difference_check.vti`. The check perturbs a small set of active
density cells, compares the finite-difference derivative with
`objective_density_sensitivity`, and classifies each sample as `ok`,
`sign_mismatch`, `relative_error`, or `failed_perturbation`.

Prepare the initial OpenFOAM adjoint adapter work directory:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --backend docker
```

By default this is a dry-run that writes `adjoint_run_summary.json`, an adapter
case directory, initial `adjointOptimisationFoam` dictionaries, adjoint initial
fields, and a preflight report. It also writes a mock-contract
`sensitivity.vti` fallback during dry runs when no raw adjoint sensitivity output
is present, so downstream sensitivity I/O can be tested.

Use `--execute` only with a meshed primal case. If the copied case is missing
`constant/polyMesh/boundary`, the adapter exits nonzero and does not write mock
sensitivity.

When executed on an already meshed case, the adapter can run
`adjointOptimisationFoam`, parse OpenFOAM `faceSensNormal...` output into
`surface_sensitivity.csv`, and project it to `sensitivity.vti` for density
updates. This path is implemented as a smoke-level connection; sensitivity
scaling and objective calibration still need validation.

Project a normalized surface sensitivity CSV onto the density grid:

```powershell
.\.venv\Scripts\cfd-sdf.exe write-mock-surface-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json
.\.venv\Scripts\cfd-sdf.exe project-sensitivity examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\surface_sensitivity.csv
```

`project-sensitivity` writes `sensitivity.vti`, `sensitivity_summary.json`, and
`projection_diagnostics.vti`. The expected CSV columns are `x`, `y`, `z`, and
`objective_surface_sensitivity`; optional columns are
`downforce_surface_sensitivity` and `drag_surface_sensitivity`. The projection
uses nearest surface samples with Gaussian weights inside a narrow band, then
produces the same density sensitivity arrays consumed by density updates.
`sensitivity_summary.json` also records `constraint_sensitivity_status` and
`constraint_sensitivity_diagnostics`; use these fields before trusting
`constraint_sensitivity` for efficiency-constraint updates.

Run the initial adjoint-driven topology loop:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --iterations 1 --backend docker
```

The current dry-run loop performs: density state -> OpenFOAM adjoint adapter
dry-run -> generated surface sensitivity CSV -> density-grid projection ->
density update -> SDF constraint validation -> next design state. It writes
`adjoint_topology_history.csv`, `adjoint_topology_summary.json`,
`adjoint_topology_summary.md`, per-step `adjoint_topology_step_result.json`, and
`best_design/`. If the adapter produces a real projected `sensitivity.vti`, the
loop consumes that instead of generating mock surface sensitivity.

Run a one-step real primal plus real adjoint smoke demo, including real
post-update primal re-evaluation for step ranking:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\topology_exploration\topology_0000\design_state.json --iterations 1 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240
```

This performs: density state -> OpenFOAM primal case -> `simpleFoam` ->
`cfd_summary.json` -> `adjointOptimisationFoam` -> `faceSensNormal...` ->
`surface_sensitivity.csv` -> `sensitivity.vti` -> density update -> updated
OpenFOAM primal case -> post-update `cfd_summary.json` -> CFD objective and
constraint ranking. Omit `--execute-updated-primal` to stop after the density
update and use the low-fidelity density-update score. Use `--stop-on-rejection`
for real CFD runs so a rejected post-update design is not fed into the next
iteration. The summary records `completed_iterations`, `stopped_reason`, and
`stopped_step_index`; if `accepted_count` is zero, `best_design/` is only the
best attempted step, not an accepted design. Keep real runs at one iteration or
guarded multi-step requests until sensitivity sign/scale calibration is
complete.

Check a completed real adjoint-topology step against its post-update primal CFD
response:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-direction examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_direction_check
```

This writes `adjoint_direction_check.json`, `adjoint_direction_check.md`, and
`adjoint_direction_check.vti`. The check compares
`sum(objective_density_sensitivity * density_delta)` with the realized
pre/post primal CFD change in `-downforce_coefficient`. It is a sign/scale
diagnostic, not a proof that the adjoint field is calibrated.

Compare the positive and negative density-update directions for a completed
step:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_paired_direction_check --execute-primal --backend docker --timeout-seconds 300
```

This writes `paired_adjoint_direction_check.json` and
`paired_adjoint_direction_check.md`. By default it reuses the step's
post-update primal CFD as the positive direction and runs primal CFD only for
the negative direction. If a candidate has near-zero `density_delta_l2`, treat
the result as a feasibility/bounds diagnostic rather than a calibrated
sensitivity sign decision.

Use `--centered` to create a centered baseline first, then evaluate both
directions with nonzero density motion:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_check --execute-primal --backend docker --timeout-seconds 300 --centered
```

This runs primal CFD for the centered baseline, positive direction, and
negative direction. The current smoke result selects the positive update
direction, but the reported `sign_mismatch` classifications still mean the raw
`objective_density_sensitivity` values are not calibrated derivatives.
Use `--perturbation-scale 0.5` or smaller to repeat the same check at lower
amplitude:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale05_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.5
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_loop\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_progress_loop\adjoint_step_0002\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_progress_step2_centered_paired_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_continuation_loop\adjoint_step_0001\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
```

Aggregate repeated paired checks into a calibration summary:

```powershell
.\.venv\Scripts\cfd-sdf.exe summarize-adjoint-calibration examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale05_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale025_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_progress_step2_centered_paired_scale025_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check\paired_adjoint_direction_check.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4
```

This writes `adjoint_calibration_summary.json` and
`adjoint_calibration_summary.md`. The current multi-state smoke has ten valid
observations. It recommends keeping the current search direction for
gradient-descent updates and reports a median derivative scale ratio of
`-0.002331156420320667`, so raw `faceSensNormal...`-projected values still need
the recorded derivative multiplier before being interpreted as
`d objective / d density`.
Some recorded smoke loops below used earlier v2/v3 summaries before the later
topology-state samples were added. For the next fresh validation run, prefer
the v4 summary path above unless reproducing historical evidence exactly.

Pass a calibration summary into a guarded adjoint-topology loop:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 2 --backend docker --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_dry_loop_v4 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json --stop-on-rejection --move-limit 0.02
```

The loop writes `adjoint_topology_calibration.json`, records
`sensitivity_update_multiplier` and `sensitivity_derivative_multiplier` in the
run summary/history, and writes `raw_objective_density_sensitivity` plus
optional `objective_derivative_sensitivity` arrays in `density_update.vti`.
For a guarded real-CFD loop, add `--execute-primal --execute-adjoint
--execute-updated-primal` and keep `--stop-on-rejection`.
Use `--constraint-sensitivity-weight <w>` to blend normalized
`constraint_sensitivity` into the density-update gradient. With `w=0` the loop
keeps objective-only behavior. With `w>0`, `density_update.vti` also exposes
`base_objective_density_sensitivity`, `raw_constraint_sensitivity`,
`effective_constraint_sensitivity`, and `combined_update_sensitivity` as point
data when the sensitivity summary marks the constraint sensitivity usable.
`density_step_result.json` records both the requested
`constraint_sensitivity_weight` and `effective_constraint_sensitivity_weight`;
if diagnostics report an unusable constraint sensitivity, the effective weight
is forced to `0.0`. This is the path for moving from downforce-only updates
toward explicit efficiency-constraint reduction. For current real OpenFOAM
adjoint output,
`faceSensNormal...` provides a scalar negative-lift sensitivity only; the CSV
normalizer zero-fills `drag_surface_sensitivity`, and the projected summary
flags this as `constraint_sensitivity_status:
degenerate_zero_drag_sensitivity`. In that status, constraint blending is only
a plumbing/diagnostic path, not a validated efficiency-constraint optimizer.

A dry-run smoke for the blended update is:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_acceptance_smoke_eff105_v4_loop\adjoint_step_0001\density_update\design_state.json --iterations 1 --backend docker --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_l_constraint_blend_dry_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json --constraint-sensitivity-weight 2.0 --stop-on-rejection
```

The corresponding real-CFD guarded smoke is:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_loop_v2 --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v2\adjoint_calibration_summary.json
```

It executed primal CFD, adjoint CFD, and post-update primal CFD once, then
stopped by `efficiency_constraint` before creating step 1. The update improved
downforce in the smoke case but did not satisfy the configured efficiency
constraint.

To continue from an infeasible design only while enforced constraint violation
is decreasing, add `--continue-on-constraint-improvement`:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_continuation_loop\adjoint_step_0001\density_update\design_state.json --iterations 2 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --continue-on-constraint-improvement --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v4_continuation_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json
```

This keeps `accepted_count` at zero, marks the steps as
`improving_infeasible`, and records constraint violation before/after each
post-update CFD evaluation. In the recorded v4 smoke, both primal/adjoint/
post-update-primal OpenFOAM steps returned 0, the applied derivative multiplier
was `-0.002331156420320667`, `density_update.vti` exposes the raw/effective/
derivative sensitivity arrays as point data, downforce increased from
`0.288500742` to `0.300838854`, and enforced violation decreased
`0.527130528 -> 0.510072085 -> 0.505011498`.

For an explicit acceptance-path smoke, use `--efficiency-min-override`. This
does not change the project target and must not be reported as satisfying the
default `efficiency_min: 3.0`; it only verifies that real-CFD accepted steps,
best-design export, and stop-on-rejection behavior are wired correctly under a
documented run-local threshold:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v4_continuation_loop\adjoint_step_0001\density_update\design_state.json --iterations 2 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_acceptance_smoke_eff105_v4_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json --efficiency-min-override 1.05
```

The recorded smoke has `accepted_count=2`, `stopped_reason=null`, and
`efficiency_min_override=1.05`; downforce increased from `0.300838854` to
`0.317567713`.

Use `--evaluator openfoam-dry-run` to also generate an OpenFOAM case and dry-run
summary for accepted topology candidates:

```powershell
.\.venv\Scripts\cfd-sdf.exe explore-topology examples\front_wing\project.yaml --iterations 3 --evaluator openfoam-dry-run
```

Use `--evaluator openfoam` to execute accepted topology candidates with the
configured OpenFOAM backend and postprocess `cfd_summary.json`:

```powershell
.\.venv\Scripts\cfd-sdf.exe explore-topology examples\front_wing\project.yaml --iterations 1 --evaluator openfoam --backend docker --timeout-seconds 360
.\.venv\Scripts\cfd-sdf.exe run-optimization examples\front_wing\project.yaml --mode topology --iterations 1 --evaluator openfoam --backend docker --timeout-seconds 360
```

These historical candidate commands extract STL and remesh each candidate.
They test orchestration and Stage V verification; they are not the fixed-grid
Stage T topology solver.

Real OpenFOAM candidate runs write `openfoam_run_summary.json`,
`cfd_summary.json`, and the parsed CFD values into `topology_result.json`.
Timeouts, nonzero solver exits, and force-coefficient postprocess failures are
recorded as `failed_cfd` by the practical runner. Keep `--iterations` small
until the case setup is stable.

Those candidate cases are written under each candidate directory at:

```text
runs/front_wing_demo/openfoam_front_wing/
```

The practical runner wraps the parametric or topology loop with resumable run
artifacts:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-optimization examples\front_wing\project.yaml --mode topology --iterations 8 --resume --evaluator openfoam-dry-run
```

It writes:

- `run_manifest.json`
- `progress.json`
- `runner_summary.json`
- `run_summary.md`
- `best_design/`

Use `progress.json` or `run_summary.md` as the first place to monitor long
runs. `best_design/` is a copy of the current best candidate, including the
candidate project, STL, SDF outputs, and any generated OpenFOAM dry-run case.

For current topology development, the v2 problem binding and fixed-grid
artifacts are authoritative. STL is an input role or a derived exchange and
verification artifact. Start from the documentation index:

```text
docs/README.md
docs/phase_plan.md
docs/problem_contract_v2.md
docs/fixed_grid_data_contract_v2.md
```

Outputs are written under:

```text
examples/front_wing/runs/front_wing_demo/
```

Open `sdf_fields.vti` and `zero_surface.ply` in ParaView.
The sample project uses `grid.voxel_size_m: 0.04` so the demo runs quickly.
For a more detailed visual check, reduce it to `0.025` or smaller in
`examples/front_wing/project.yaml` and rebuild the SDF.

Useful ParaView arrays include `design_phi`, `design_narrow_band`, `allowed_phi`,
`forbidden_phi`, `root_phi`, `violation_rule`, `violation_forbidden`,
`connectivity_components`, `connectivity_unrooted`, `eroded_solid`, and
`eroded_unrooted`.

The generated OpenFOAM preparation case is written to:

```text
examples/front_wing/runs/front_wing_demo/openfoam_front_wing/
```

It contains `blockMeshDict`, `snappyHexMeshDict`, `controlDict` with a
`forceCoeffs` function object, `Allrun`, `Allrun.ps1`, and
`postprocess_forces.py`. On a WSL/OpenFOAM machine, run the case from the case
directory with `./Allrun`, or from Windows PowerShell with `.\Allrun.ps1`.
By default, `run-openfoam` and `evaluate` are dry-runs that write the command
plan and logs without launching OpenFOAM. Add `--execute` to run OpenFOAM:

```powershell
.\.venv\Scripts\cfd-sdf.exe evaluate examples\front_wing\project.yaml --execute --backend wsl
```

Docker is also supported and is the easiest Windows setup path when Docker
Desktop is already running:

```powershell
docker run --rm opencfd/openfoam-default:2512 bash -lc "simpleFoam -help | head"
.\.venv\Scripts\cfd-sdf.exe run-openfoam examples\front_wing\runs\front_wing_demo\openfoam_front_wing --backend docker --execute --timeout-seconds 300
```

The Docker image defaults to `opencfd/openfoam-default:2512`. Override
it with:

```powershell
$env:CFD_SDF_OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
```

For binary distribution, the intended packaging model is to ship this tool as a
Windows executable plus project files, while treating OpenFOAM as an external
solver backend. Bundling OpenFOAM into the app binary is not practical because
the solver runtime is large, Linux-oriented, and version-sensitive. Docker is
best for development and reproducibility; WSL/OpenFOAM is the likely production
backend for users who do not want Docker Desktop as a runtime dependency.

The single-point evaluation summary is written to:

```text
examples/front_wing/runs/front_wing_demo/openfoam_front_wing/evaluation_summary.json
```

After OpenFOAM has produced `postProcessing/forceCoeffs.../forceCoeffs.dat`,
summarize drag, downforce, and efficiency with:

```powershell
.\.venv\Scripts\cfd-sdf.exe postprocess-openfoam examples\front_wing\runs\front_wing_demo\openfoam_front_wing --efficiency-min 3.0
```

OpenFOAM v2512 writes `coefficient.dat`; older variants may write
`forceCoeffs.dat`. The postprocessor supports both.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The tests cover the normal front-wing demo, missing-root connectivity failure,
forbidden-region intersection failure, VTK/report validation, and OpenFOAM case
generation, OpenFOAM dry-run execution planning, and force-coefficient
postprocessing, plus the parametric geometry, mock optimization loop, constraint
records, front/rear ratio enforcement, history CSV, resume behavior,
density-field topology pre-stage, low-fidelity topology scoring, best-topology
promotion, topology OpenFOAM dry-run handoff, practical run manifests, progress
summaries, failed/rejected candidate classification, best-design export,
sensitivity VTI/schema I/O, density update preview output, and the initial
resumable density optimizer loop, finite-difference checks for the mock
sensitivity contract, surface-to-density projection, adjoint adapter dry-run
handoff, the initial one-step adjoint topology loop, T4 fixed-grid
connectivity state evaluation, and finite-difference reference connectivity
derivatives.

Historical capabilities are retained in tests and summarized in the current
roadmap; there is no separate active legacy verification report.

## Current Scope

Implemented and reusable:

- G1 v2 generic problem and fixed-grid artifact contracts, canonical
  hash/snapshot binding, v1 non-destructive migration/readers, semantic
  validation, the `validate-problem-spec` CLI, and a generic two-flow-case
  example.
- Front-wing project generation and STL role handling.
- Design, fixed, allowed, forbidden, and root SDF fields.
- Density-grid state, iso-surface extraction, SDF validation, and ParaView
  output.
- Rule, clearance, nominal-connectivity, and eroded-connectivity validation.
- JSON/CSV/Markdown histories, resume, failure classification, and best-result
  export infrastructure.
- Real Docker/OpenFOAM body-fitted primal execution and force postprocessing.
- Real OpenFOAM surface-adjoint adapter, sensitivity projection, direction
  checks, calibration records, and guarded body-fitted smoke loops.
- T2 fixed-grid Brinkman primal execution, T3 extraction of aerodynamic
  density sensitivity fields from OpenFOAM topO results, and T3 plus/minus
  direction-check case generation.
- T3 converged-adjoint cellwise direction validation for drag, downforce, and
  the efficiency constraint on the canonical fixed-grid case.
- T4 first-slice fixed-grid connectivity evaluation: nominal and eroded
  virtual-diffusion potential/violation fields plus discrete root-component
  diagnostics. The front-wing legacy conversion now preserves small STL root
  regions on the coarse fixed grid.
- T4 finite-difference reference derivatives for the scalarized nominal and
  eroded connectivity violation fields. Full active-cell runs can populate
  optimizer input arrays on small grids; sampled runs are diagnostic only.
- T5 constrained density-step adapter: T3/T4 gradients are combined into
  linearized efficiency, connectivity, and volume constraints. The adapter now
  supports both the original projected-gradient smoke backend and an
  SLSQP-based linearized constrained subproblem backend.
- G2 generic OpenFOAM case compilation for the currently supported force-only
  profile, including multipoint manifests, turbulence/BC rendering, execution
  asset staging, mesh patch mapping, and fail-closed convergence evaluation.

Implemented but not part of the main topology route:

- Parametric front-wing generator and optimizer.
- Deterministic low-fidelity topology ranking.
- Normalized-gradient density update prototype.
- Surface-shape sensitivity projected back to the density grid.

Missing from the intended optimizer:

- G2 runtime qualification: complete field/mesh boundary compatibility, real
  history extraction, porous-aware turbulence/wall-distance qualification,
  simple porous/body-fitted comparisons, and real-solver v2 writers.
- G3 STL quality, geometry-role, feature-resolution, and density-to-SDF
  preflight gates.
- G4 benchmark ladder from manufactured/simple cases through generic 3D and
  the front-wing complex integration benchmark.
- T3 broader validation beyond cellwise checks: filtered-random directions,
  front-wing-seed checks, and explicit continuation/chain-rule metadata before
  production runs.
- Production-scale analytic or adjoint connectivity derivatives and final
  optimizer-ready constraint linearizations.
- Production GCMMA or an equivalent constrained optimizer backend.
- SDF sharp-interface IBM/cut-cell refinement.
- Mesh-epoch adaptation.

The next task is to finish G2 runtime qualification, starting with generated
field/mesh boundary compatibility and an OpenFOAM smoke run. Complete G3
preflight and G4 B0--B2 qualification before replacing the linearized smoke
backend with production GCMMA or an equivalent constrained optimizer.
