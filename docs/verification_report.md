# Verification Report

Date: 2026-07-09

Scope note, 2026-07-10: the results below are front-wing and solver-capability
benchmarks. They demonstrate geometry, data, orchestration, primal, and
gradient plumbing only where stated; they are not proof of generic-object
target physics or arbitrary-topology aerodynamic optimality.

This report records the current verification state for the front-wing
SDF/density topology optimization path through the initial adjoint-solver
adapter boundary.

Roadmap note, 2026-07-02: the Phase A-K results below verify the Geometry
Service, body-fitted OpenFOAM primal/adjoint adapter, projection, calibration,
and orchestration path documented by the
`Legacy A-K Body-Fitted Adjoint Roadmap`. They do not verify the fixed-grid
density/Brinkman topology optimizer now defined by the authoritative
`TSV Roadmap` in `docs/phase_plan.md`.

## TSV T0 Fixed-Grid Evidence

OpenFOAM v2512 fixed-grid topology capability is now executable through
Docker. The official porosity tutorial completed 49 design updates on one
mesh, and the custom `porousDirectionalForce` library compiled and loaded
through OpenFOAM runtime selection.

Validated artifacts:

- `examples/fixed_grid_backend_spike/report/3d/fixed_grid_backend_probe_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/downforce/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/efficiency/efficiency_constraint_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/efficiency/fixed_grid_sensitivity.vtu`

Centered direction results on the linear-projection capability case:

| Quantity | Finite difference | Adjoint | Relative error | Result |
| --- | ---: | ---: | ---: | --- |
| 3D drag | 1.753287 | 1.752494 | 0.045% | Pass at 10% |
| 3D `-Z` downforce | 0.234106 | 0.253052 | 7.49% | Pass at 10% |
| 3D `3*C_D-C_DF` | 5.025756 | 5.004429 | 0.424% | Pass at 10% |

All checks have matching signs, converged primal solves, and separate nonzero
topology sensitivity fields. The backend probe reports `pass_t0`.

## TSV T1 Fixed-Grid Data Contract

The cell-centred Stage T schema is implemented in
`docs/fixed_grid_data_contract.md`. The OpenFOAM adapter generated all eight
roadmap artifacts from the canonical 3D case and the standalone validator
reported `pass`.

Evidence:

- `examples/fixed_grid_backend_spike/report/3d/t1_contract/topology_state.json`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/density.vti`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_case_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_primal_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/connectivity_state.vti`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/topology_iteration_result.json`
- `examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_contract_validation.json`

Result:

- Grid: `32 x 16 x 16`, 8192 cells.
- Spacing: `(0.09375, 0.1, 0.075) m`.
- Active design cells: `2979`.
- All 9 density/mask arrays are present.
- All 6 sensitivity arrays are present.
- Density, sensitivity, and connectivity fields share one grid.
- Schema, units, signs, array sources, and solver metadata are present.
- Connectivity arrays are explicit T1 placeholders; T4 remains responsible
  for the virtual-diffusion solve and nonzero derivatives.

## TSV T2 Fixed-Grid Brinkman Primal

The T2 adapter consumes `topology_state.json` and cell-data `density.vti`,
generates OpenFOAM fixed-grid topO cases, writes `alpha` directly from the
density field, creates mask-derived fixed-zero cell zones, and runs without STL
extraction, `setFields`, `snappyHexMesh`, or any remeshing inside the primal
solve.

Evidence:

- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/fixed_grid_primal_suite_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/fixed_grid_primal_suite_history.csv`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t1_from_legacy/fixed_grid_contract_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_primal_summary.json`

Executed canonical suite result:

| Case | Status | Drag | Downforce | Efficiency constraint |
| --- | --- | ---: | ---: | ---: |
| all-fluid | completed | 0.000000 | 0.000000 | 0.000000 |
| threshold-solid | converged | 4.046193 | 0.687250 | 11.451330 |
| seed | converged | 3.410215 | 0.624258 | 9.606387 |
| filtered perturbation | converged | 10.496224 | -1.073458 | 32.562132 |
| seed repeat | converged | 3.410215 | 0.624258 | 9.606387 |

The seed repeat reproduced drag, downforce, objective, and efficiency
constraint with zero recorded delta at tolerance `1e-10`.

Executed front-wing legacy-density seed:

- Contract conversion status: `pass` on a `26 x 22 x 8` cell grid.
- Active design cells: `496`.
- Fixed-zero cells: `3238`.
- Primal status: `converged`.
- Drag: `16.7999147108`.
- Downforce: `-11.4173833331`.
- Efficiency constraint: `61.8171274655`.

These T2 values are not yet optimized or production-calibrated aerodynamic
results. They verify that density and role masks can drive a fixed-grid
Brinkman primal solve and produce repeatable solver-derived force outputs.

## TSV T3 Fixed-Grid Aerodynamic Sensitivity Extraction

The T3 adapter extracts OpenFOAM topology sensitivity volScalarFields from
fixed-grid cases and writes the Stage T sensitivity contract arrays in
cell-data VTI form. It reads `topOSensas1` for drag and `topOSensdownforce`
for positive `-Z` downforce, maps OpenFOAM cell-label order back to the
contract `vtk-x-fastest` order, zeros inactive cells, and composes the
efficiency constraint derivative.

Evidence:

- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/seed/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/seed/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_drag_execute/fixed_grid_sensitivity_direction_suite_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_drag_execute/validation/fixed_grid_sensitivity_direction_check.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_baseline_seed_adjoint_4000/fixed_grid_primal_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_baseline_seed_adjoint_4000/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_drag_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_downforce_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`
- `examples/fixed_grid_backend_spike/report/3d/t3_direction_seed_efficiency_constraint_adjoint_4000/validation/fixed_grid_sensitivity_direction_check.json`

Original T2-minimal canonical seed extraction:

- Active design cells: `2979`.
- `d_drag_d_rho` active range: `-1.118293` to `5.874486`.
- `d_downforce_d_rho` active range: `-2.095405` to `2.234672`.
- `d_efficiency_constraint_d_rho` active range: `-3.175078` to `17.833174`.

Converged-adjoint canonical seed extraction:

- Baseline case: `t3_baseline_seed_adjoint_4000`.
- Primal status: `converged`.
- Drag adjoint: converged in `663` iterations.
- Downforce adjoint: converged in `1074` iterations.
- Active design cells: `2979`.
- `d_drag_d_rho` active range: `-0.875845` to `8.803026`.
- `d_downforce_d_rho` active range: `-6.814601` to `4.995909`.
- `d_efficiency_constraint_d_rho` active range: `-2.365809` to `27.958857`.

Front-wing seed extraction:

- Active design cells: `496`.
- `d_drag_d_rho` active range: `-0.053350` to `3.152538`.
- `d_downforce_d_rho` active range: `-0.825372` to `0.074415`.
- `d_efficiency_constraint_d_rho` active range: `-0.176536` to `10.282985`.

The direction-check comparator is implemented as
`validate-fixed-grid-sensitivity-direction`, and the suite command now
generates plus/minus density contracts and OpenFOAM cases. The first executed
canonical drag direction check, sourced from the T2-minimal
`adjoint_iterations=1` case, did not pass the scale gate:

- Direction: cellwise drag, `epsilon = 0.01`.
- Plus and minus primal solves: both `converged`.
- Finite-difference derivative: `0.0646995395`.
- Adjoint directional derivative: `0.3005556280`.
- Finite-difference / adjoint ratio: `0.2152664381`.
- Sign match: `true`.
- Relative error: `78.47%`, with tolerance `25%`.

This was a useful failure: the sign was consistent, but the adjoint field was
not converged. Re-running the same canonical seed with `adjoint_iterations =
4000` resolves the scale mismatch for the tested cellwise directions:

| Objective | Finite difference | Adjoint | FD/adjoint | Relative error | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Drag | 0.0646995395 | 0.0611741146 | 1.0576293577 | 5.45% | Pass |
| Downforce | 0.0365289651 | 0.0373771318 | 0.9773078697 | 2.27% | Pass |
| `3*C_D-C_DF` | 0.1794246634 | 0.1680593080 | 1.0676270514 | 6.33% | Pass |

These checks use the current density field directly as the fixed-grid design
variable. Broader filtered-random direction checks and front-wing-seed checks
remain necessary before production optimizer runs.

## TSV T4 Fixed-Grid Connectivity State And Derivative Evaluation

The T4 implementation generates nominal and eroded fixed-grid connectivity
fields from `topology_state.json` and `density.vti`. It solves a root-connected
virtual-diffusion system, writes potential and violation arrays to
`connectivity_state.vti`, and records discrete 6-neighbor component diagnostics
in `fixed_grid_connectivity_summary.json`.

T4 also writes finite-difference reference derivatives for the scalarized
nominal and eroded `violation_l1` objectives into
`fixed_grid_sensitivity.vti`. Full active-cell runs can be used as the current
small-grid optimizer gradient source. Runs with `--max-cells` are intentionally
sampled diagnostics and are not optimizer-ready.

Evidence:

- `examples/fixed_grid_backend_spike/report/3d/t4_connectivity_seed_no_root/connectivity_state.vti`
- `examples/fixed_grid_backend_spike/report/3d/t4_connectivity_seed_no_root/fixed_grid_connectivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t1_from_legacy_root_fixed/topology_state.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_root_fixed/connectivity_state.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_root_fixed/fixed_grid_connectivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_derivatives_sampled/fixed_grid_sensitivity.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_derivatives_sampled/fixed_grid_sensitivity_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t4_connectivity_derivatives_sampled/fixed_grid_connectivity_derivative_summary.json`

Canonical seed result:

- Status: `missing_root`.
- Root cells: `0`.
- Material cells: `112`.
- Nominal components: `1`.
- Nominal unrooted components: `1`.
- Eroded unrooted components: `1`.

This is the expected blocker for the current canonical contract: the density
has material, but no root cells.

Front-wing root-mask repair:

- Regenerated contract: `front_wing_t1_from_legacy_root_fixed`.
- Root cells: `110`.
- Contract validation: `pass`.
- T4 connectivity status: `pass`.
- Nominal components: `1`, unrooted components: `0`.
- Eroded components: `1`, unrooted components: `0`.

The repair changes root STL cellization only. Allowed, forbidden, and fixed
solid role masks retain the existing majority-occupancy conversion.

Front-wing sampled derivative run:

- Command: `differentiate-fixed-grid-connectivity`.
- Base density: `front_wing_t1_from_legacy_root_fixed`.
- Base aerodynamic sensitivity: `front_wing_t2_seed_execute/fixed_grid_sensitivity.vti`.
- Candidate cells: `387`.
- Selected/evaluated cells: `16`.
- Connectivity derivative status: `finite_difference_reference_sampled`.
- Optimizer-ready: `false`, because this run intentionally used `--max-cells`.
- Nominal base `violation_l1`: `623.5165895614039`.
- Eroded base `violation_l1`: `681.2748482731008`.

The implementation also has a unit test that builds a small connected grid,
writes full active-cell derivatives, and compares the generated nominal and
eroded derivative entries against an independent central-difference objective
calculation.

## TSV T5 Fixed-Grid Constrained Density Step

The first T5 implementation adds a constrained density-step adapter. It reads
the fixed-grid density contract and a `fixed_grid_sensitivity.vti` containing
T3 aerodynamic and T4 connectivity derivatives, builds scalar linearized
constraints, and projects the objective descent step into move-limited density
bounds.

The available backends are:

- `projected-gradient`: conservative smoke fallback.
- `slsqp-linearized`: SciPy SLSQP solve of the same linearized constrained
  subproblem.

Both are deliberately behind the same value/gradient interface a production
GCMMA backend will use, but neither is itself GCMMA. The SLSQP backend first
checks whether every linearized constraint is feasible inside the current move
bounds; impossible subproblems are rejected quickly with a diagnostic report.

Evidence:

- `src/cfd_sdf/fixed_grid_optimizer.py`
- `tests/test_fixed_grid_optimizer.py`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/fixed_grid_constrained_update.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/fixed_grid_constrained_step_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/density.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_sampled/topology_state.json`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_slsqp_sampled/fixed_grid_constrained_update.vti`
- `examples/fixed_grid_backend_spike/report/3d/front_wing_t5_constrained_step_slsqp_sampled/fixed_grid_constrained_step_summary.json`

Unit checks:

- A downforce-improving gradient moves density in the expected direction.
- The volume-fraction constraint projects a move back to the allowed linearized
  limit.
- The SLSQP backend respects an active linearized efficiency constraint.
- Sampled connectivity derivatives are rejected unless explicitly allowed for
  diagnostics.

Front-wing diagnostic run:

- Command: `run-fixed-grid-constrained-step`.
- Input density: `front_wing_t1_from_legacy_root_fixed`.
- Sensitivity: `front_wing_t4_connectivity_derivatives_sampled`.
- Move limit: `0.01`.
- Sampled connectivity derivatives were explicitly allowed.
- Status: `linearized_reject`.
- Reason: the current front-wing T2 result is still far outside the efficiency
  constraint; predicted efficiency violation remains `61.48443394302725`.
- The command still wrote the diagnostic density/update artifacts for ParaView
  inspection.

Front-wing SLSQP diagnostic run:

- Command: `run-fixed-grid-constrained-step --optimizer-backend slsqp-linearized`.
- Status: `linearized_reject`.
- SLSQP status: `infeasible_move_bounds`.
- Impossible constraint: `efficiency`.
- Minimum predicted efficiency violation inside move bounds:
  `61.48431162497684`.
- The command skipped SLSQP iterations and wrote diagnostic artifacts.

## Verified Commands

### Python Compile Check

Command:

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
```

Result:
- Passed.
- The local Windows Python launcher emitted the existing non-fatal warning
  `Could not find platform independent libraries <prefix>`.

### Unit And Integration Tests

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Result:
- Passed: `67 passed`.
- Warnings: 2434 VTK/numpy `DeprecationWarning` entries from
  `vtkmodules.util.numpy_support`; no test failures.
- Coverage includes SDF constraints, topology candidates, OpenFOAM case
  preparation, practical runner output, sensitivity I/O, density update,
  finite-difference checks, surface-sensitivity projection, adjoint adapter
  projection handoff, T4 connectivity derivatives, T5 constrained density-step
  adapter checks including SLSQP linearized backend coverage, the initial
  adjoint-topology loop, post-update primal CFD re-ranking,
  rejection-guarded stopping, and real-adjoint direction plus paired-direction
  diagnostics, T2 fixed-grid primal case generation, and T3 fixed-grid
  sensitivity extraction and direction-check plumbing.

### Finite-Difference Gradient Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-gradient examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --sample-count 8 --epsilon 1e-4 --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_e_check
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_e_check/finite_difference_check.json`

Result:
- `sample_count`: 8
- `ok_count`: 8
- `sign_mismatch_count`: 0
- `relative_error_count`: 0
- `failed_perturbation_count`: 0
- `max_relative_error`: about `2.16e-4`

This validates the current mock/analytic sensitivity contract. It does not
validate OpenFOAM primal or adjoint sensitivities.

### Real OpenFOAM Docker Smoke

Command family:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-optimization examples\front_wing\project.yaml --mode topology --iterations 1 --evaluator openfoam --backend docker --timeout-seconds 360
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_f_check/topology_0000/runs/front_wing_demo/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_f_practical_check/progress.json`

Result:
- OpenFOAM Docker execution completed and force coefficients were parsed.
- Example parsed values:
  - `drag_coefficient`: `0.275307452`
  - `downforce_coefficient`: `0.261215938`
  - `efficiency`: `0.9488153557136549`
  - `ok`: `true`
- Practical-run classification rejected the example by `efficiency_constraint`
  rather than by solver failure.

This verifies the real primal CFD path for a small topology candidate. It does
not verify real adjoint execution.

### Adjoint Adapter Dry Run

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --backend docker --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_h_check
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_check/adjoint_run_summary.json`

Result:
- Backend id: `openfoam-adjoint`
- Solver backend: `docker`
- Command generated for `adjointOptimisationFoam`
- Dry run succeeded.
- Initial adjoint case files were generated:
  - `system/optimisationDict`
  - `system/finite-area/faSchemes`
  - `system/finite-area/faSolution`
  - `constant/adjointRASProperties`
  - `0/Ua`
  - `0/pa`
  - `0/nuTilda`
  - `0/nuaTilda`
- Mock-contract `sensitivity.vti` fallback was written for downstream tests.
- Preflight reported `case_files_ready: true` and `mesh_ready: false` for the
  current unmeshed dry-run case.

### Adjoint Execute Preflight

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --backend docker --execute --adjoint-case-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_h_execute_preflight_check
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_execute_preflight_check/adjoint_run_summary.json`

Result:
- Exit code: 1, as expected for an unmeshed case.
- `ok`: `false`
- `conversion_mode`: `execution-failed-no-conversion`
- Blocking issue: `constant/polyMesh/boundary`
- No mock `sensitivity.vti` was written.

This verifies that failed real-adjoint execution cannot silently fall back to
mock sensitivity.

### Real OpenFOAM Adjoint Smoke

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --backend docker --execute --timeout-seconds 180 --primal-case-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_f_check\topology_0000\runs\front_wing_demo\openfoam_front_wing --adjoint-case-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_h_real_execute_check
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_real_execute_check/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_real_execute_check/surface_sensitivity.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_real_execute_check/sensitivity.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_h_real_execute_check/sensitivity_summary.json`

Result:
- `returncode`: 0
- `preflight.executable_ready`: true
- `conversion_mode`: `openfoam-faceSensNormal-projection`
- Parsed raw source:
  `400/faceSensNormalfaceBased-RMult_2`
- Exported surface samples: 1201
- Raw scalar sensitivity range: about `-31.05` to `40.85`
- Projected density-grid sensitivity was written to `sensitivity.vti`.

This verifies the first real solver connection:
`adjointOptimisationFoam -> faceSensNormal -> surface_sensitivity.csv ->
sensitivity.vti`. It still needs objective/sign calibration before being used
as trusted optimization data.

### Surface Sensitivity Projection

Commands:

```powershell
.\.venv\Scripts\cfd-sdf.exe write-mock-surface-sensitivity examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --output-csv examples\front_wing\runs\front_wing_demo\adjoint_phase_i_check\surface_sensitivity.csv --max-points 300
.\.venv\Scripts\cfd-sdf.exe project-sensitivity examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json examples\front_wing\runs\front_wing_demo\adjoint_phase_i_check\surface_sensitivity.csv --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_i_check\projection --smoothing-radius-cells 0.5
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_i_check/projection/sensitivity.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_i_check/projection/sensitivity_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_i_check/projection/projection_diagnostics.vti`

Result:
- `surface_point_count`: 184
- `projected_active_cell_count`: 480
- Required density sensitivity arrays were written:
  - `objective_density_sensitivity`
  - `downforce_density_sensitivity`
  - `drag_density_sensitivity`
  - `constraint_sensitivity`
  - `active_mask`

### Initial Adjoint-Driven Topology Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 1 --backend docker --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_j_check --move-limit 0.03
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_check/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_check/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_check/best_design/`

Result:
- `iterations`: 1
- `accepted_count`: 1
- Step status: `accepted`
- Constraints passed for the enforced geometry and aero constraints.
- Density update artifacts, derived STL, history, summary, and best-design
  export were written.

This smoke uses the default adjoint adapter dry run plus generated mock surface
sensitivity. The runner now consumes adapter-provided `sensitivity.vti` when it
exists, but this command does not yet run real primal CFD and real adjoint CFD
inside the topology iteration.

### Real Primal Plus Real Adjoint Topology Step

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 1 --backend docker --execute-primal --execute-adjoint --primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_j_real_check --move-limit 0.02
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_step_0000/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_step_0000/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_step_0000/adjoint/sensitivity.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_check/adjoint_step_0000/density_update/density_update.vti`

Result:
- `iterations`: 1
- `accepted_count`: 1
- Primal OpenFOAM `returncode`: 0
- Primal parsed `downforce_coefficient`: `0.261215938`
- Adjoint OpenFOAM `returncode`: 0
- Adjoint `conversion_mode`: `openfoam-faceSensNormal-projection`
- Exported OpenFOAM surface sensitivity samples: 1201
- Density update used the projected real adjoint `sensitivity.vti`.

This verifies the requested single-step path:
`density state -> STL/OpenFOAM case -> primal CFD -> adjoint -> sensitivity.vti
-> density update -> constraints -> next design_state.json`.

### Real Primal Plus Real Adjoint Plus Updated Primal Topology Step

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 1 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_j_real_post_update_check --move-limit 0.02
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_step_0000/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_step_0000/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_step_0000/adjoint/sensitivity.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_step_0000/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_j_real_post_update_check/adjoint_step_0000/density_update/density_update.vti`

Result:
- `iterations`: 1
- `accepted_count`: 0
- Initial primal OpenFOAM `returncode`: 0
- Initial primal parsed `downforce_coefficient`: `0.261215938`
- Adjoint OpenFOAM `returncode`: 0
- Adjoint `conversion_mode`: `openfoam-faceSensNormal-projection`
- Updated primal OpenFOAM `returncode`: 0
- Updated primal parsed `downforce_coefficient`: `0.266577561`
- Updated primal parsed `efficiency_constraint`: `0.557110065`
- Step `objective_source`: `post_update_primal_cfd`
- Step status: `rejected`
- Rejection reason: `efficiency_constraint`

This verifies the full single-step execution path:
`density state -> STL/OpenFOAM case -> primal CFD -> adjoint -> sensitivity.vti
-> density update -> updated STL/OpenFOAM case -> updated primal CFD -> CFD
objective/constraint ranking`.

### Guarded Multi-Iteration Request With Stop On Rejection

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check --move-limit 0.02
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_stop_on_rejection_check/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_stop_on_rejection_check/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_stop_on_rejection_check/adjoint_step_0000/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested `iterations`: 3
- `completed_iterations`: 1
- `accepted_count`: 0
- `stopped_reason`: `step_0000_rejected:efficiency_constraint`
- `stopped_step_index`: 0
- `adjoint_step_0001` was not created.
- Step `objective_source`: `post_update_primal_cfd`
- Updated primal parsed `downforce_coefficient`: `0.266577561`
- Updated primal parsed `efficiency_constraint`: `0.557110065`

This verifies that guarded multi-step real CFD requests do not feed a rejected
post-update design into the next iteration.

### Real Adjoint Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-direction examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_direction_check
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_direction_check/adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_direction_check/adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_direction_check/adjoint_direction_check.vti`

Result:
- Active cells: 480
- Density delta L2: `0.4218418031592839`
- Initial downforce coefficient: `0.261215938`
- Updated downforce coefficient: `0.266577561`
- Objective metric predicted delta:
  `2.291776070206885`
- Objective metric actual delta:
  `-0.0053616230000000376`
- Objective metric classification:
  `sign_mismatch`
- Efficiency-constraint metric predicted delta:
  `2.291776070206885`
- Efficiency-constraint metric actual delta:
  `-0.007596352999999945`
- Efficiency-constraint metric classification:
  `sign_mismatch`

This verifies that the direction-check instrumentation works on real
OpenFOAM-derived adjoint output. It also shows that the current projected
`faceSensNormal...` field is not yet calibrated as
`d(objective)/d(density)`: the realized primal CFD delta improved raw
downforce and efficiency constraint, while the stored first-order prediction
has the opposite sign.

### Paired Real Adjoint Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_paired_direction_check --execute-primal --backend docker --timeout-seconds 300
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_paired_direction_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_paired_direction_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_paired_direction_check/positive/density_update.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_paired_direction_check/negative/density_update.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_paired_direction_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Recommended feasible direction: `positive`
- Sensitivity sign decision: `insufficient_symmetric_density_motion`
- Positive direction density delta L2: `0.4218418031592839`
- Positive direction actual objective delta:
  `-0.0053616230000000376`
- Positive direction objective classification:
  `sign_mismatch`
- Negative direction density delta L2: `0.0`
- Negative direction actual objective delta:
  `0.0`
- Negative direction objective classification:
  `indeterminate`

This verifies paired-direction tooling and one additional real primal CFD
execution. It does not settle the adjoint sign convention because the negative
direction was clipped by density lower bounds and produced no geometry change.
The next calibration check needs a centered perturbation or a design state with
nonzero density headroom in both directions.

### Centered Paired Real Adjoint Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_check --execute-primal --backend docker --timeout-seconds 300 --centered
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_check/center/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_check/positive/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Perturbation mode: `centered`
- Center primal OpenFOAM `returncode`: 0
- Positive primal OpenFOAM `returncode`: 0
- Negative primal OpenFOAM `returncode`: 0
- Center downforce coefficient: `0.266577561`
- Positive direction density delta L2: `0.4218418031592839`
- Positive direction predicted objective delta:
  `2.291776070206885`
- Positive direction actual objective delta:
  `-0.005309485000000003`
- Negative direction density delta L2: `0.4218418031592839`
- Negative direction predicted objective delta:
  `-2.291776070206885`
- Negative direction actual objective delta:
  `0.0053616230000000376`
- Recommended direction: `positive`
- Sensitivity sign decision:
  `paired_direction_selected`
- Suggested sensitivity multiplier for gradient descent:
  `1.0`

This verifies that both perturbation directions can be evaluated without
density-bound clipping. For this smoke case the current update direction should
not be inverted. However, both directions still report `sign_mismatch` between
the stored first-order sensitivity prediction and the realized primal CFD
delta, so the raw `objective_density_sensitivity` field remains an uncalibrated
search direction rather than a reliable derivative.

### Smaller-Amplitude Centered Paired Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_stop_on_rejection_check\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale05_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.5
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale05_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale05_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale05_check/center/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale05_check/positive/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale05_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Perturbation mode: `centered`
- Perturbation scale: `0.5`
- Center primal OpenFOAM `returncode`: 0
- Positive primal OpenFOAM `returncode`: 0
- Negative primal OpenFOAM `returncode`: 0
- Center downforce coefficient: `0.263877615`
- Positive direction density delta L2: `0.21092090157964194`
- Positive direction predicted objective delta:
  `1.1458880351034424`
- Positive direction actual objective delta:
  `-0.0026999460000000086`
- Negative direction density delta L2: `0.21092090157964194`
- Negative direction predicted objective delta:
  `-1.1458880351034424`
- Negative direction actual objective delta:
  `0.002661677000000029`
- Recommended direction: `positive`
- Sensitivity sign decision:
  `paired_direction_selected`
- Suggested sensitivity multiplier for gradient descent:
  `1.0`

This repeats the centered paired check at half amplitude. The realized CFD
response stays directionally consistent with the full-amplitude check and is
approximately half the size, but the stored first-order sensitivity prediction
still has the opposite sign and a much larger magnitude.

### Quarter-Amplitude Centered Paired Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_loop\adjoint_step_0000\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale025_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale025_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale025_check/center/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale025_check/positive/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_centered_paired_direction_scale025_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Perturbation mode: `centered`
- Perturbation scale: `0.25`
- Center, positive, and negative primal OpenFOAM `returncode`: 0
- Center downforce coefficient: `0.262560532`
- Positive direction density delta L2: `0.10546045078982097`
- Positive direction predicted objective delta:
  `0.5729440175517212`
- Positive direction actual objective delta:
  `-0.0013170829999999967`
- Negative direction predicted objective delta:
  `-0.5729440175517212`
- Negative direction actual objective delta:
  `0.0013445940000000323`
- Recommended direction: `positive`
- Suggested sensitivity multiplier for gradient descent:
  `1.0`

This adds a third centered amplitude. The actual CFD response remains
directionally consistent with the previous full- and half-amplitude checks.

### Later-State Quarter-Amplitude Centered Paired Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_progress_loop\adjoint_step_0002\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_progress_step2_centered_paired_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_progress_step2_centered_paired_scale025_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_progress_step2_centered_paired_scale025_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_progress_step2_centered_paired_scale025_check/center/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_progress_step2_centered_paired_scale025_check/positive/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_progress_step2_centered_paired_scale025_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Perturbation mode: `centered`
- Perturbation scale: `0.25`
- Center, positive, and negative primal OpenFOAM `returncode`: 0
- Center downforce coefficient: `0.271887046`
- Positive direction density delta L2: `0.10409999599579124`
- Positive direction predicted objective delta:
  `0.6035584315361481`
- Positive direction actual objective delta:
  `-0.0013779879999999967`
- Positive direction actual constraint delta:
  `-0.0019044129999999937`
- Negative direction predicted objective delta:
  `-0.6035584303702298`
- Negative direction actual objective delta:
  `0.0013727960000000095`
- Negative direction actual constraint delta:
  `0.0019078190000000328`
- Recommended direction: `positive`
- Suggested sensitivity multiplier for gradient descent:
  `1.0`

This repeats the centered quarter-amplitude diagnostic on a later density state
after two guarded infeasible-improvement steps. The same positive search
direction is selected, while the raw first-order derivative sign still needs the
calibration multiplier.

### Aggregate Adjoint Calibration Summary

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe summarize-adjoint-calibration examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale05_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale025_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_progress_step2_centered_paired_scale025_check\paired_adjoint_direction_check.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v3
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibration_summary_v3/adjoint_calibration_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibration_summary_v3/adjoint_calibration_summary.md`

Result:
- Paired reports summarized: 4
- Valid candidate observations: 8
- Objective scale-ratio median:
  `-0.00231978139972467`
- Objective scale-ratio mean:
  `-0.00231731212276678`
- Objective scale-ratio range:
  `-0.002356204024554875` to `-0.002274503893778636`
- Constraint scale-ratio median:
  `-0.00326117987580046`
- Recommended sensitivity multiplier for gradient descent:
  `1.0`
- Recommended derivative multiplier:
  `-0.00231978139972467`
- Calibration status:
  `search_direction_consistent_derivative_opposite_sign`

This aggregates the full-, half-, and quarter-amplitude centered paired checks
from the initial state plus one quarter-amplitude check from a later topology
state. The result is internally consistent enough to keep the current smoke-case
update direction for guarded gradient-descent steps, but it confirms that the
raw projected adjoint values need a negative scale multiplier before being
treated as physical derivatives.

### Calibrated Adjoint-Topology Dry Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 2 --backend docker --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_dry_loop --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary\adjoint_calibration_summary.json --stop-on-rejection --move-limit 0.02
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_dry_loop/adjoint_topology_calibration.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_dry_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_dry_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_dry_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_dry_loop/adjoint_step_0000/density_update/density_update.vti`

Result:
- Requested iterations: 2
- Completed iterations: 2
- Accepted count: 2
- Stop-on-rejection state: not stopped
- Applied sensitivity update multiplier: `1.0`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- Calibration status:
  `search_direction_consistent_derivative_opposite_sign`
- `density_update.vti` contains:
  - `objective_density_sensitivity`
  - `raw_objective_density_sensitivity`
  - `objective_derivative_sensitivity`

This verifies that the aggregate calibration summary is now connected back into
the adjoint-topology runner. This command is a dry-run adapter smoke; it does
not replace the real primal plus real adjoint plus updated-primal runs recorded
below.

### Calibrated Real Guarded Adjoint-Topology Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_loop_v2 --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v2\adjoint_calibration_summary.json
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_topology_calibration.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_step_0000/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_step_0000/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_loop_v2/adjoint_step_0000/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_direction_check_v2/adjoint_direction_check.json`

Result:
- Requested iterations: 3
- Completed iterations: 1
- Accepted count: 0
- Stopped reason:
  `step_0000_rejected:efficiency_constraint`
- Step 1 directory was not created.
- Primal OpenFOAM `returncode`: 0
- Adjoint OpenFOAM `returncode`: 0
- Post-update primal OpenFOAM `returncode`: 0
- Adjoint conversion mode:
  `openfoam-faceSensNormal-projection`
- Applied sensitivity update multiplier: `1.0`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- Downforce coefficient changed from `0.261215938` to `0.266577561`.
- Efficiency constraint changed from `0.564706418` to `0.557110065`, still
  above the enforced `0.0` limit.
- Direction check actual objective delta:
  `-0.0053616230000000376`
- Direction check predicted objective delta:
  `2.291776070206885`
- Direction check scale ratio:
  `-0.00233950562173207`

This verifies the guarded real loop with calibration-summary handoff. The smoke
update improves downforce and efficiency constraint value, but the updated
candidate remains infeasible, so the runner correctly stops before feeding it
into a second real adjoint step.

### Calibrated Real Feasibility-Progress Adjoint-Topology Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --continue-on-constraint-improvement --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_progress_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v2\adjoint_calibration_summary.json
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_topology_calibration.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0000/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0000/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0000/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0001/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0001/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0001/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0002/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0002/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_progress_loop/adjoint_step_0002/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested iterations: 3
- Completed iterations: 3
- Accepted count: 0
- Stopped reason: none
- Step statuses: all `improving_infeasible`
- Applied sensitivity update multiplier: `1.0`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- Step 0 downforce coefficient changed from `0.261215938` to `0.266577561`.
- Step 0 enforced violation changed from `0.564706418` to `0.557110065`.
- Step 1 downforce coefficient changed from `0.266577561` to `0.271887046`.
- Step 1 enforced violation changed from `0.557110065` to `0.549778853`.
- Step 2 downforce coefficient changed from `0.271887046` to `0.277367546`.
- Step 2 enforced violation changed from `0.549778853` to `0.541860547`.
- Primal CFD, adjoint CFD, and post-update primal CFD completed with
  `returncode` 0 for all three steps.

This verifies the guarded continuation path from an infeasible state: the loop
does not count these candidates as accepted, but it can keep walking while the
enforced constraint violation decreases and non-aero constraints remain
satisfied. It is therefore evidence that the real primal plus real adjoint plus
post-update primal loop is connected, not evidence of a feasible accepted
optimum yet.

### V3-Calibrated Real Feasibility-Progress Adjoint-Topology Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json --iterations 3 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --continue-on-constraint-improvement --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_progress_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v3\adjoint_calibration_summary.json
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_topology_calibration.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0000/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0000/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0000/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0001/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0001/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0001/post_update_primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0002/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0002/adjoint/adjoint_run_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_progress_loop/adjoint_step_0002/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested iterations: 3
- Completed iterations: 3
- Accepted count: 0
- Stopped reason: none
- Step statuses: all `improving_infeasible`
- Applied sensitivity update multiplier: `1.0`
- Applied sensitivity derivative multiplier:
  `-0.00231978139972467`
- Calibration status:
  `search_direction_consistent_derivative_opposite_sign`
- `density_update.vti` point data contains:
  - `objective_density_sensitivity`
  - `raw_objective_density_sensitivity`
  - `objective_derivative_sensitivity`
- Step 0 downforce coefficient changed from `0.261215938` to `0.266577561`.
- Step 0 enforced violation changed from `0.564706418` to `0.557110065`.
- Step 1 downforce coefficient changed from `0.266577561` to `0.271887046`.
- Step 1 enforced violation changed from `0.557110065` to `0.549778853`.
- Step 2 downforce coefficient changed from `0.271887046` to `0.277367546`.
- Step 2 enforced violation changed from `0.549778853` to `0.541860547`.
- Adjoint OpenFOAM `returncode`: 0 for all three steps.

This was the first v3 handoff proof: the eight-observation v3 calibration
summary is consumed by the real guarded loop, the derivative multiplier is
recorded in the run summary/history and density-update controls, and the loop
still progresses only under the explicit infeasible-improvement guard.
`accepted_count` remains zero, so this is not yet a feasible accepted
optimization run.

### V3-Calibrated Real Continuation Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_progress_loop\adjoint_step_0002\density_update\design_state.json --iterations 2 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --continue-on-constraint-improvement --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_continuation_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v3\adjoint_calibration_summary.json
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_continuation_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_continuation_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_continuation_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v3_continuation_loop/adjoint_step_0001/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested iterations: 2
- Completed iterations: 2
- Accepted count: 0
- Step statuses: all `improving_infeasible`
- Downforce coefficient changed from `0.277367546` to `0.288500742`.
- Enforced violation changed from `0.541860547` to `0.527130528`.

This extends the v3-calibrated real trajectory two more guarded steps and
creates a later density state for independent centered paired diagnostics.

### Later-State V3 Continuation Centered Paired Direction Check

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe check-adjoint-paired-directions examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_continuation_loop\adjoint_step_0001\adjoint_topology_step_result.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check --execute-primal --backend docker --timeout-seconds 300 --centered --perturbation-scale 0.25
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check/paired_adjoint_direction_check.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check/paired_adjoint_direction_check.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check/center/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check/positive/primal/openfoam_front_wing/cfd_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check/negative/primal/openfoam_front_wing/cfd_summary.json`

Result:
- Perturbation mode: `centered`
- Perturbation scale: `0.25`
- Center downforce coefficient: `0.283352259`
- Center efficiency constraint: `0.5342483130000002`
- Positive direction density delta L2: `0.1034576919124267`
- Positive direction predicted objective delta:
  `0.6024097701942018`
- Positive direction actual objective delta:
  `-0.0014191900000000146`
- Positive direction actual constraint delta:
  `-0.0018823390000002327`
- Negative direction actual objective delta:
  `0.0014158280000000079`
- Negative direction actual constraint delta:
  `0.0018882109999998065`
- Recommended direction: `positive`
- Suggested sensitivity multiplier for gradient descent:
  `1.0`

This adds another later-density-state diagnostic. It again selects the positive
search direction while classifying the raw first-order derivative sign as
opposite to the realized CFD response.

### Aggregate Adjoint Calibration Summary V4

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe summarize-adjoint-calibration examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale05_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_centered_paired_direction_scale025_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_progress_step2_centered_paired_scale025_check\paired_adjoint_direction_check.json examples\front_wing\runs\front_wing_demo\adjoint_phase_k_v3_continuation_step1_centered_paired_scale025_check\paired_adjoint_direction_check.json --output-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibration_summary_v4/adjoint_calibration_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibration_summary_v4/adjoint_calibration_summary.md`

Result:
- Paired reports summarized: 5
- Valid candidate observations: 10
- Objective scale-ratio median:
  `-0.002331156420320667`
- Objective scale-ratio mean:
  `-0.00232446258337398`
- Objective scale-ratio range:
  `-0.002356204024554875` to `-0.002274503893778636`
- Constraint scale-ratio median:
  `-0.0032281845055358973`
- Recommended sensitivity multiplier for gradient descent:
  `1.0`
- Recommended derivative multiplier:
  `-0.002331156420320667`
- Calibration status:
  `search_direction_consistent_derivative_opposite_sign`

The v4 summary keeps the same search direction decision across five centered
paired reports and ten candidate observations. The derivative scale remains
near `-0.00232`.

### V4-Calibrated Real Continuation Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v3_continuation_loop\adjoint_step_0001\density_update\design_state.json --iterations 2 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --continue-on-constraint-improvement --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v4_continuation_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v4_continuation_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v4_continuation_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v4_continuation_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_calibrated_real_v4_continuation_loop/adjoint_step_0001/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested iterations: 2
- Completed iterations: 2
- Accepted count: 0
- Step statuses: all `improving_infeasible`
- Applied sensitivity update multiplier: `1.0`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- `density_update.vti` point data contains:
  - `objective_density_sensitivity`
  - `raw_objective_density_sensitivity`
  - `objective_derivative_sensitivity`
- Downforce coefficient changed from `0.288500742` to `0.300838854`.
- Enforced violation changed from `0.527130528` to `0.505011498`.
- Primal CFD, adjoint CFD, and post-update primal CFD completed with
  `returncode` 0 for both steps.

This confirms that the latest ten-observation v4 calibration summary can be
consumed by the guarded real loop. The loop is still infeasible and does not
produce accepted candidates, but it continues to reduce the enforced violation.

### V4-Calibrated Acceptance-Path Smoke With Efficiency Override

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibrated_real_v4_continuation_loop\adjoint_step_0001\density_update\design_state.json --iterations 2 --backend docker --execute-primal --execute-adjoint --execute-updated-primal --stop-on-rejection --primal-timeout-seconds 300 --updated-primal-timeout-seconds 300 --timeout-seconds 240 --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_k_acceptance_smoke_eff105_v4_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json --efficiency-min-override 1.05
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_acceptance_smoke_eff105_v4_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_acceptance_smoke_eff105_v4_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_acceptance_smoke_eff105_v4_loop/adjoint_topology_history.csv`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_acceptance_smoke_eff105_v4_loop/best_design/density_update/design_state.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_k_acceptance_smoke_eff105_v4_loop/adjoint_step_0001/post_update_primal/openfoam_front_wing/cfd_summary.json`

Result:
- Requested iterations: 2
- Completed iterations: 2
- Accepted count: 2
- Stopped reason: none
- Step statuses: both `accepted`
- Efficiency min override: `1.05`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- Downforce coefficient changed from `0.300838854` to `0.317567713`.
- Post-update step 1 efficiency: `1.0869445383590561`.
- Post-update step 1 efficiency constraint under the override:
  `-0.01079392014999997`
- Primal CFD, adjoint CFD, and post-update primal CFD completed with
  `returncode` 0 for both steps.

This verifies the real-CFD accepted-step code path and best-design export under
an explicit run-local threshold. It is not evidence that the default project
target `efficiency_min: 3.0` has been satisfied.

### Constraint-Sensitivity Blended Density Update Dry Loop

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-adjoint-topology examples\front_wing\runs\front_wing_demo\adjoint_phase_k_acceptance_smoke_eff105_v4_loop\adjoint_step_0001\density_update\design_state.json --iterations 1 --backend docker --run-dir examples\front_wing\runs\front_wing_demo\adjoint_phase_l_constraint_blend_dry_loop --move-limit 0.02 --calibration-summary examples\front_wing\runs\front_wing_demo\adjoint_phase_k_calibration_summary_v4\adjoint_calibration_summary.json --constraint-sensitivity-weight 2.0 --stop-on-rejection
```

Evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_constraint_blend_dry_loop/adjoint_topology_summary.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_constraint_blend_dry_loop/adjoint_topology_summary.md`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_constraint_blend_dry_loop/adjoint_step_0000/density_update/density_update.vti`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_constraint_blend_dry_loop/adjoint_step_0000/density_update/density_step_result.json`

Result:
- Requested iterations: 1
- Completed iterations: 1
- Accepted count: 1 in dry low-fidelity status
- Constraint sensitivity weight: `2.0`
- Applied sensitivity derivative multiplier:
  `-0.002331156420320667`
- `density_update.vti` point data contains:
  - `objective_density_sensitivity`
  - `base_objective_density_sensitivity`
  - `raw_objective_density_sensitivity`
  - `raw_constraint_sensitivity`
  - `effective_constraint_sensitivity`
  - `combined_update_sensitivity`
  - `objective_derivative_sensitivity`

This verifies the update-rule plumbing needed to move from downforce-only
updates toward explicit efficiency-constraint reduction. It is a dry-run
handoff check; real `adjointOptimisationFoam` currently provides no independent
drag sensitivity, so a real constraint-aware improvement still needs drag or
constraint sensitivity from the adjoint backend.

The sensitivity summaries now include `constraint_sensitivity_status` and
`constraint_sensitivity_diagnostics`. The density update records an
`effective_constraint_sensitivity_weight` and disables constraint blending when
those diagnostics mark the constraint sensitivity unusable. Current OpenFOAM
`faceSensNormal...` conversion zero-fills drag sensitivity, so real projected
summaries are diagnosed as `degenerate_zero_drag_sensitivity` until a drag or
direct constraint-sensitivity adjoint source is parsed.

Additional zero-drag guard check evidence:
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_zero_drag_guard_check/density_update_guarded/density_step_result.json`
- `examples/front_wing/runs/front_wing_demo/adjoint_phase_l_zero_drag_guard_check/density_update_guarded/density_update.vti`

Result:
- Requested `constraint_sensitivity_weight`: `2.0`
- Effective `constraint_sensitivity_weight`: `0.0`
- Blend policy mode: `disabled_unusable_constraint_sensitivity`
- `density_update.vti` contains objective/raw/base sensitivity arrays but does
  not emit `raw_constraint_sensitivity`, `effective_constraint_sensitivity`, or
  `combined_update_sensitivity`.

## Current Confidence

Reliable enough for continued implementation:
- STL to SDF/density design-state handoff.
- Constraint records and SDF validation for topology candidates.
- Real Docker/OpenFOAM primal execution and force coefficient postprocessing on
  a small case.
- Stable sensitivity file contract for density updates.
- Density update loop with move limit, bounds, smoothing, volume bounds,
  root-preservation proxy, and minimum-thickness proxy.
- Surface CSV to density-grid projection path.
- Initial adjoint-topology runner structure, history, resume, and best export.
- Initial `adjointOptimisationFoam` case-file generation and preflight failure
  classification before real solver execution.
- Real `adjointOptimisationFoam` execution on an already meshed candidate,
  including scalar face sensitivity normalization and density-grid projection.
- Real one-step topology runner execution with primal CFD, adjoint CFD,
  projected sensitivity, density update, optional post-update primal CFD
  re-evaluation, JSON/CSV/Markdown history, and best export.
- Rejection-guarded real topology requests through `--stop-on-rejection`,
  including `completed_iterations` and `stopped_reason` reporting.
- Real-adjoint direction diagnostics comparing projected sensitivity,
  density update, and pre/post primal CFD response.
- Paired direction diagnostic generation, including reusable positive CFD,
  generated positive/negative design states, and one additional Docker primal
  run for the negative direction.
- Centered paired direction diagnostics with real primal CFD for center,
  positive, and negative cases; the current smoke selects the positive update
  direction.
- Smaller-amplitude centered paired diagnostics at `perturbation_scale=0.5`,
  which select the same positive update direction with smaller realized CFD
  deltas.
- Quarter-amplitude centered paired diagnostics at `perturbation_scale=0.25`,
  which again select the positive update direction with still smaller realized
  CFD deltas.
- Aggregate adjoint calibration summary over five centered paired checks across
  the initial density state and later density states, including ten candidate
  observations and a stable derivative multiplier estimate.
- Calibration-summary multiplier handoff into a two-step guarded dry
  adjoint-topology loop, including calibration record, history fields, and
  ParaView-visible raw/effective/derivative sensitivity arrays.
- Calibration-summary multiplier handoff into a real guarded topology loop with
  primal CFD, adjoint CFD, post-update primal CFD, rejection stop, and direction
  diagnostics.
- Explicit infeasible-improvement continuation for real guarded topology loops,
  including three primal/adjoint/post-update-primal OpenFOAM steps that reduce
  enforced violation while keeping `accepted_count` at zero.
- V4 calibration-summary multiplier handoff into the real guarded
  infeasible-improvement loop, including the ten-observation derivative
  multiplier `-0.002331156420320667` recorded in the run summary/history and
  density-update controls.
- Run-local `efficiency_min_override` handoff into real primal postprocessing
  and acceptance checks, including a two-step accepted v4-calibrated smoke at
  `efficiency_min_override=1.05`.
- Constraint-sensitivity diagnostics in `sensitivity_summary.json`, including
  active-cell norms, objective/constraint cosine, and explicit detection of the
  current zero-drag OpenFOAM adjoint projection.
- Constraint-blend guarding in density updates: requested weight is preserved,
  but `effective_constraint_sensitivity_weight` is forced to zero when the
  sensitivity summary reports an unusable constraint field.
- T2 fixed-grid Brinkman primal case generation, execution, reproducibility
  reports, and front-wing seed conversion.
- T3 fixed-grid sensitivity extraction from OpenFOAM `topOSens*` volume fields,
  plus/minus direction-check case generation, and canonical converged-adjoint
  cellwise validation for drag, downforce, and efficiency constraint.
- T4 fixed-grid connectivity state evaluation, including nominal/eroded
  virtual-diffusion fields and root-component diagnostics.
- T4 finite-difference reference connectivity derivatives for nominal and
  eroded scalarized violation fields, including an independent small-grid
  central-difference unit check and a sampled front-wing artifact.
- T5 constrained fixed-grid density-step adapter, including objective descent,
  volume projection, sampled-connectivity guardrails, SLSQP linearized backend
  checks, and front-wing diagnostic reject artifacts.
- Front-wing fixed-grid root-mask reconstruction for small STL roots on coarse
  grids.

Not yet reliable as production CFD optimization:
- T3 still needs broader filtered-random direction checks and front-wing-seed
  validation after the root mask is repaired.
- T4 production-scale analytic or adjoint connectivity derivatives are not yet
  implemented. Sampled finite-difference runs are diagnostic only; use full
  active-cell finite differences only on small grids until the adjoint form is
  available.
- T5 uses projected-gradient and SLSQP linearized backends, not a production
  GCMMA implementation. They verify the optimizer contract but do not replace
  GCMMA for large runs.
- The default topology loop still runs dry unless `--execute-primal` and
  `--execute-adjoint` are set.
- The generated adjoint dictionaries still need to be run against a meshed case
  across more than one candidate and tuned from actual solver logs.
- The current update direction should not be inverted for the smoke case. The
  derivative multiplier is consistent across three amplitudes and multiple
  later density states, but it still needs more independent real-CFD candidates
  before being used as an unguarded default.
- Post-update real primal re-evaluation is optional because it doubles primal
  CFD cost per topology iteration.
- When `accepted_count` is zero, `best_design/` is the best attempted step and
  must not be interpreted as an accepted design.
- Accepted-step smoke with `efficiency_min_override` proves the acceptance path,
  but it must not be interpreted as satisfying the default project
  `efficiency_min: 3.0`.
- Real OpenFOAM `faceSensNormal...` projection currently produces
  `constraint_sensitivity_status: degenerate_zero_drag_sensitivity`, so
  `--constraint-sensitivity-weight` should be treated as plumbing/diagnostic
  work until an independent drag or direct constraint sensitivity is available.
- Front/rear aero balance is recorded, but the current front-wing-only demo
  still needs sign convention and rear-downforce calibration before enforcing
  balance constraints.

## Required Next Work

1. Add full active-cell T4 derivative runs for the front-wing grid or replace
   the finite-difference reference with an analytic/adjoint derivative.
2. Calibrate the eroded minimum-width behavior against the 10 mm requirement
   and the current grid spacing.
3. Replace the current T5 linearized SLSQP backend with a production GCMMA
   adapter.
4. Run a three-iteration fixed-grid topology smoke with nonlinear primal and
   connectivity rechecks.
