# Fixed-Grid Topology Data Contract

Date: 2026-07-02
Last verified: 2026-07-09
Schema version: 1
Roadmap: `TSV Roadmap`
Roadmap phase: T1
Status: authoritative

## Purpose

This contract defines the machine-readable boundary between the Geometry
Service, the fixed-grid CFD backend, the volume adjoints, connectivity, and
the constrained optimizer.

It does not replace `design_state.json` or `sensitivity.vti` in the legacy
body-fitted adapter. Those artifacts remain available for Stage V and early
Stage S regression work. Stage T uses the artifacts defined here.

## Grid Convention

- Coordinates use metres in the project/OpenFOAM frame.
- Flow is `+X`, span is `Y`, and positive downforce is `-Z`.
- All Stage T VTI arrays are cell data.
- Cartesian grids may have different spacing in `X`, `Y`, and `Z`.
- Cell order is `vtk-x-fastest`:
  `i + nx*j + nx*ny*k`.
- `origin` is the minimum grid-point corner, not the first cell centre.
- Every density, sensitivity, and connectivity field in one iteration must
  have identical origin, spacing, and cell shape.

OpenFOAM float32 VTK coordinates are normalized to `1e-7 m` when the contract
grid is reconstructed. Cell-field values are not rounded.

## Artifacts

| Artifact | Kind | Purpose |
| --- | --- | --- |
| `topology_state.json` | `fixed_grid_topology_state` | Authoritative design-state manifest |
| `density.vti` | `fixed_grid_density` | Density, projection, penalization, and role masks |
| `fixed_grid_case_summary.json` | `fixed_grid_case_summary` | Grid, solver, interpolation, and artifact mapping |
| `fixed_grid_primal_summary.json` | `fixed_grid_primal_summary` | Aerodynamic values, signs, units, and convergence |
| `fixed_grid_sensitivity.vti` | `fixed_grid_sensitivity` | Aerodynamic and connectivity derivatives |
| `fixed_grid_sensitivity_summary.json` | `fixed_grid_sensitivity_summary` | Per-array metadata, statistics, and validation evidence |
| `connectivity_state.vti` | `fixed_grid_connectivity` | Nominal and eroded connectivity fields |
| `topology_iteration_result.json` | `topology_iteration_result` | One optimizer-iteration result and artifact links |

`fixed_grid_contract_validation.json` is generated as verification evidence.

Each VTI stores these field-data values:

- `schema_version`
- `kind`
- `cell_order`

## Density Fields

`density.vti` requires:

| Array | Units | Meaning |
| --- | --- | --- |
| `rho` | `1` | Raw design variable; `0` fluid, `1` solid material |
| `rho_filtered` | `1` | Spatially regularized density |
| `rho_projected` | `1` | Projected/interpolated material fraction |
| `alpha` | `1/s` | Non-negative Brinkman momentum penalization |
| `allowed_mask` | `1` | Material/design is allowed |
| `forbidden_mask` | `1` | Material is prohibited |
| `fixed_solid_mask` | `1` | Material is fixed at solid |
| `root_mask` | `1` | Root attachment cells |
| `active_design_mask` | `1` | `rho` may be updated |

Mask values are binary. The active mask must be a subset of the allowed mask
and must not overlap forbidden or fixed-solid cells.

For the OpenFOAM v2512 adapter:

- OpenFOAM `alpha` maps to contract `rho`.
- OpenFOAM `alphaTilda` maps to `rho_filtered`.
- OpenFOAM `beta` maps to `rho_projected`.
- Contract `alpha` is `betaMax * beta`.
- `fixedZeroPorousZones` are removed from `active_design_mask`.

## Sensitivity Fields

`fixed_grid_sensitivity.vti` requires:

| Array | Units | Sign convention |
| --- | --- | --- |
| `d_downforce_d_rho` | `1` | Positive increases positive `-Z` downforce |
| `d_drag_d_rho` | `1` | Positive increases positive `+X` drag |
| `d_efficiency_constraint_d_rho` | `1` | Positive increases `E_min*C_D-C_DF` violation |
| `d_connectivity_nominal_d_rho` | `1` | Positive increases nominal connectivity violation |
| `d_connectivity_eroded_d_rho` | `1` | Positive increases eroded connectivity violation |
| `active_design_mask` | `1` | Cells included in an optimizer update |

The aerodynamic constraint derivative is:

```text
d_efficiency_constraint_d_rho
    = efficiency_min*d_drag_d_rho - d_downforce_d_rho
```

All sensitivities must be zero outside `active_design_mask`.

T1 reserves both connectivity derivative arrays and writes explicit zero
fields with status `not_evaluated_t1_contract_only`. This is not connectivity
evidence. T4 replaces them with virtual-diffusion derivatives.

## Source Metadata

Case, primal, and sensitivity summaries require:

- backend
- solver name
- solver version
- Docker image
- source case
- initial and final VTK paths
- fixed-mesh/remeshing policy

Every required array has:

- units
- cell location
- source
- sign convention

The sensitivity summary also records centered finite-difference evidence for
drag, downforce, and the efficiency constraint.

## Validation

Build from a completed OpenFOAM canonical case:

```powershell
.\.venv\Scripts\cfd-sdf.exe build-fixed-grid-contract `
  examples\fixed_grid_backend_spike\openfoam\porous_force_3d_fd_base `
  --output-dir examples\fixed_grid_backend_spike\report\3d\t1_contract `
  --drag-validation-json examples\fixed_grid_backend_spike\report\3d\porous_force_gradient_validation.json `
  --downforce-validation-json examples\fixed_grid_backend_spike\report\3d\downforce\porous_force_gradient_validation.json `
  --efficiency-validation-json examples\fixed_grid_backend_spike\report\3d\efficiency\efficiency_constraint_gradient_validation.json
```

Convert an existing legacy point-data `density_design_state` into the same
cell-data contract:

```powershell
.\.venv\Scripts\cfd-sdf.exe build-fixed-grid-contract-from-density `
  examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\design_state.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy `
  --project-yaml examples\front_wing\runs\front_wing_demo\adjoint_phase_b_check\topology_0000\project.yaml
```

This conversion averages legacy point-data density to cell data and rebuilds
allowed, forbidden, fixed-solid, and root masks from the project SDF roles when
`--project-yaml` is provided. Aerodynamic and connectivity sensitivity fields
remain explicit zero placeholders until T3/T4.

Extract aerodynamic sensitivities from a completed T2 fixed-grid primal case:

```powershell
.\.venv\Scripts\cfd-sdf.exe extract-fixed-grid-sensitivity `
  examples\fixed_grid_backend_spike\report\3d\t2_primal_suite_execute\seed
```

This reads OpenFOAM `topOSensas1` and `topOSensdownforce` volScalarField files
from the latest time directory, maps OpenFOAM cell-label order back to
`vtk-x-fastest`, writes `d_drag_d_rho` and `d_downforce_d_rho`, and composes:

```text
d_efficiency_constraint_d_rho
    = efficiency_min*d_drag_d_rho - d_downforce_d_rho
```

The current T3 extractor still writes zero connectivity derivative arrays.
Those arrays remain T4-owned.

Compare an extracted sensitivity against paired plus/minus fixed-grid primal
cases:

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

This writes plus/minus density contracts, plus/minus fixed-grid OpenFOAM cases,
the direction VTI, and the validation report. To compare already executed
plus/minus cases directly:

```powershell
.\.venv\Scripts\cfd-sdf.exe validate-fixed-grid-sensitivity-direction `
  <baseline-case> <plus-case> <minus-case> `
  --sensitivity-vti <baseline-case>\fixed_grid_sensitivity.vti `
  --objective efficiency_constraint `
  --epsilon 0.001
```

The comparator expects the plus/minus cases to contain
`fixed_grid_input_density.vti` and `fixed_grid_primal_summary.json`, then
checks the centered finite-difference direction against the corresponding
sensitivity dot product.

The canonical converged-adjoint cellwise validation evidence is:

- `t3_direction_seed_drag_adjoint_4000`: relative error `5.45%`.
- `t3_direction_seed_downforce_adjoint_4000`: relative error `2.27%`.
- `t3_direction_seed_efficiency_constraint_adjoint_4000`: relative error
  `6.33%`.

Evaluate T4 fixed-grid connectivity fields:

```powershell
.\.venv\Scripts\cfd-sdf.exe evaluate-fixed-grid-connectivity `
  examples\fixed_grid_backend_spike\report\3d\t1_contract\topology_state.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\t4_connectivity_seed_no_root `
  --min-connection-width-mm 10.0
```

This writes `connectivity_state.vti` and
`fixed_grid_connectivity_summary.json`.

Generate T4 finite-difference reference connectivity derivatives:

```powershell
.\.venv\Scripts\cfd-sdf.exe differentiate-fixed-grid-connectivity `
  examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy_root_fixed\topology_state.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t4_connectivity_derivatives_sampled `
  --base-sensitivity-vti examples\fixed_grid_backend_spike\report\3d\front_wing_t2_seed_execute\fixed_grid_sensitivity.vti `
  --max-cells 16 `
  --epsilon 1.0e-4 `
  --min-connection-width-mm 10.0
```

This writes `fixed_grid_sensitivity.vti`,
`fixed_grid_sensitivity_summary.json`, and
`fixed_grid_connectivity_derivative_summary.json`. Without `--max-cells`, the
command differentiates every candidate active cell and is optimizer-ready for
small fixed grids. With `--max-cells`, the output is a bounded diagnostic
sample and must not be treated as a complete optimizer gradient.

Run one T5 constrained density-step adapter:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-constrained-step `
  examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy_root_fixed\topology_state.json `
  --sensitivity-vti examples\fixed_grid_backend_spike\report\3d\front_wing_t4_connectivity_derivatives_sampled\fixed_grid_sensitivity.vti `
  --sensitivity-summary-json examples\fixed_grid_backend_spike\report\3d\front_wing_t4_connectivity_derivatives_sampled\fixed_grid_sensitivity_summary.json `
  --primal-summary-json examples\fixed_grid_backend_spike\report\3d\front_wing_t2_seed_execute\fixed_grid_primal_summary.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t5_constrained_step_sampled `
  --move-limit 0.01 `
  --allow-sampled-connectivity-derivatives
```

This writes `density.vti`, `topology_state.json`,
`fixed_grid_constrained_update.vti`, and
`fixed_grid_constrained_step_summary.json`. The command rejects sampled T4
connectivity derivatives by default; `--allow-sampled-connectivity-derivatives`
is only for explicit diagnostic runs. A step is accepted only when all
linearized constraints are satisfied.

Use the SLSQP linearized subproblem backend with:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-constrained-step `
  examples\fixed_grid_backend_spike\report\3d\front_wing_t1_from_legacy_root_fixed\topology_state.json `
  --sensitivity-vti examples\fixed_grid_backend_spike\report\3d\front_wing_t4_connectivity_derivatives_sampled\fixed_grid_sensitivity.vti `
  --sensitivity-summary-json examples\fixed_grid_backend_spike\report\3d\front_wing_t4_connectivity_derivatives_sampled\fixed_grid_sensitivity_summary.json `
  --primal-summary-json examples\fixed_grid_backend_spike\report\3d\front_wing_t2_seed_execute\fixed_grid_primal_summary.json `
  --output-dir examples\fixed_grid_backend_spike\report\3d\front_wing_t5_constrained_step_slsqp_sampled `
  --move-limit 0.01 `
  --allow-sampled-connectivity-derivatives `
  --optimizer-backend slsqp-linearized
```

The SLSQP backend first checks whether every linearized constraint is feasible
inside the current move bounds. If not, it writes a fast diagnostic reject
instead of spending optimizer iterations on an impossible subproblem.

For small STL root regions on coarse grids, root cells are reconstructed with a
touch-cell SDF rule instead of strict cell-majority occupancy. This prevents
root mounts from disappearing when no cell has at least half of its vertices
inside the root STL.

Validate existing artifacts:

```powershell
.\.venv\Scripts\cfd-sdf.exe validate-fixed-grid-contract `
  examples\fixed_grid_backend_spike\report\3d\t1_contract\topology_state.json
```

Validation fails on:

- missing files or arrays;
- schema or VTI field-metadata mismatch;
- non-finite values;
- density bounds violations;
- non-binary or conflicting masks;
- nonzero sensitivity outside the active design domain;
- grid origin, spacing, or shape mismatch;
- missing units, sign conventions, array sources, or solver metadata.

## T2 Handoff

T2 consumes `topology_state.json` and `density.vti`, creates a fixed-grid
OpenFOAM case without STL extraction or remeshing, and writes a new
`fixed_grid_primal_summary.json`.

The first T2 adapter is implemented. The executed canonical suite is:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-fixed-grid-primal-suite `
  examples\fixed_grid_backend_spike\report\3d\t1_contract\topology_state.json `
  --run-dir examples\fixed_grid_backend_spike\report\3d\t2_primal_suite_execute `
  --template-case-dir examples\fixed_grid_backend_spike\openfoam\porous_force_3d_fd_base `
  --backend docker --execute --timeout-seconds 300 --overwrite
```

It runs all-fluid, threshold-solid, seed, filtered perturbation, and seed-repeat
cases on fixed meshes. The repeated seed case reproduced drag, downforce,
objective, and efficiency constraint exactly within the recorded `1e-10`
tolerance.
