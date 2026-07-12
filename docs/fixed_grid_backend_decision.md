# Fixed-Grid Topology Backend Decision

Date: 2026-07-02
Status: selected; OpenFOAM v2512 passed T0
Roadmap: `TSV Roadmap`
Roadmap phase: T0

Scope note, 2026-07-10: the evidence in this decision is a front-wing/solver
capability benchmark. It supports backend selection and implementation
plumbing, not generic-object target-physics validation.

## Purpose

Select the backend for Stage T fixed-grid density/Brinkman topology
optimization using executable evidence. The body-fitted
`adjointOptimisationFoam` adapter is already retained for Stage V and early
Stage S work; this decision is specifically about volume design variables and
volume derivatives on a fixed mesh.

## Required Capabilities

Every accepted backend must demonstrate:

1. A cell density or porosity design field on a fixed mesh.
2. Brinkman/Darcy momentum penalization controlled by that field.
3. Downforce and drag evaluated from the same fixed-grid primal state.
4. Separate `dC_DF/d_rho` and `dC_D/d_rho` fields.
5. Construction of
   `d(E_min*C_D-C_DF)/d_rho`.
6. Exportable volume fields with stable cell indexing.
7. Repeated density updates without STL extraction or remeshing.
8. Docker or WSL2 automation from the Windows orchestrator.
9. A credible path from the capability case to turbulent external flow.
10. License and distribution terms compatible with a public orchestrator.

## Candidate Order

Evaluate candidates in this order:

1. OpenFOAM v2512 built-in porosity/level-set topology path.
2. DAFoam topology optimization.
3. AMReX or a dedicated fixed-grid research solver.

This order minimizes new solver code. AMReX remains attractive for later GPU
and embedded-boundary work, but it should not be selected merely because it is
architecturally clean if an existing adjoint backend already meets the Stage T
contract.

## Capability Matrix

| Capability | OpenFOAM v2512 | DAFoam | AMReX/custom |
| --- | --- | --- | --- |
| Fixed-mesh density design variable | Pass | Not evaluated | Achievable, likely custom |
| Brinkman/Darcy primal | Pass | Not evaluated | Achievable, likely custom |
| External downforce functional | Pass: strict 3D `-Z` centered check | Not evaluated | Custom |
| External drag functional | Pass: custom porous reaction objective | Not evaluated | Custom |
| Density volume adjoint | Pass for installed objectives | Not evaluated | Custom |
| Separate drag/downforce derivatives | Pass: both 3D fields exported and checked | Not evaluated | Custom |
| Efficiency-constraint derivative | Pass on canonical 3D case | Not evaluated | Custom |
| Turbulence path | Tutorials installed, not executed | Not evaluated | Significant custom work |
| Constrained update | Pass: ISQP tutorial, MMA source installed | Not evaluated | Custom |
| Helmholtz regularisation | Pass | Not evaluated | Custom |
| Docker automation | Pass | New environment | New build environment |
| Windows one-command path | Pass for probe/tutorial | To verify | To build |
| Implementation risk | Medium: production front-wing adapter and turbulence continuation remain | To measure | High |

## Evidence Collected

Command:

```powershell
.\.venv\Scripts\cfd-sdf.exe run-openfoam examples\fixed_grid_backend_spike\openfoam\porosity_based_R10x_init --backend docker --execute --timeout-seconds 600
.\.venv\Scripts\cfd-sdf.exe probe-fixed-grid-backend examples\fixed_grid_backend_spike\openfoam\porosity_based_R10x_init --output-dir examples\fixed_grid_backend_spike\report
```

Observed:

- Docker image: `opencfd/openfoam-default:2512`
- OpenFOAM version: `v2512`
- Official porosity-based tutorial completed through
  `adjointOptimisationFoam`.
- Fixed-mesh density field: `alpha`, reconstructed `alphaTilda`, and `beta`.
- Optimisation iterations: `49`
- Objective: `1.0 -> 0.799525`
- Final volume constraint: `-1.19414e-06`
- Runtime log contains `Postprocessing Brinkman sensitivities for field U`.
- `foamToVTK` produced `alphaTilda`, `beta`, `U`, and `p` ParaView fields.
- Source inspection found `topOSource`, `topODesignVariables`,
  `sensitivityTopO`, MMA, GCMMA line search, and Helmholtz regularisation.
- Installed `objectiveForce` remains boundary-patch based.
- `openfoam_extensions/porousDirectionalForce` now integrates directional
  Brinkman reaction over the internal porous design field and supplies both
  velocity and direct density derivatives.
- The custom library builds as
  `libcfdSdfPorousObjectives.so` in the OpenFOAM v2512 Docker image.
- A linear-projection centered check with `epsilon=0.005` produced:
  - drag: finite difference `0.0386`, adjoint `0.0353097`, error `8.52%`;
  - 2D -Y force, dual adjoint: finite difference `0.01341`, adjoint
    `0.0105658`, error `21.21%`;
  - `3*C_D-C_DF`: finite difference `0.10239`, adjoint `0.0953634`, error
    `6.86%`.
- Drag and the combined efficiency derivative pass the current `10%` gate.
  The 2D -Y force does not, so it is not accepted as downforce validation.
- The replacement canonical 3D case uses `direction (0 0 -1)`, `nu=1e-2`,
  and a fixed 8192-cell mesh. Its centered checks produced:
  - drag: finite difference `1.753287`, adjoint `1.752494`, error `0.045%`;
  - `-Z` downforce: finite difference `0.234106`, adjoint `0.253052`,
    error `7.49%`;
  - `3*C_D-C_DF`: finite difference `5.025756`, adjoint `5.004429`,
    error `0.424%`.
- The primal, drag adjoint, and downforce adjoint converged in `152`, `663`,
  and `1074` iterations respectively.

Evidence:

- `examples/fixed_grid_backend_spike/report/backend_environment.json`
- `examples/fixed_grid_backend_spike/report/capability_matrix.json`
- `examples/fixed_grid_backend_spike/report/fixed_grid_backend_probe_summary.json`
- `examples/fixed_grid_backend_spike/report/fixed_grid_backend_probe_summary.md`
- `examples/fixed_grid_backend_spike/report/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/downforce2d/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/efficiency/efficiency_constraint_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/efficiency/fixed_grid_sensitivity.vtu`
- `examples/fixed_grid_backend_spike/report/3d/fixed_grid_backend_probe_summary.json`
- `examples/fixed_grid_backend_spike/report/3d/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/downforce/porous_force_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/efficiency/efficiency_constraint_gradient_validation.json`
- `examples/fixed_grid_backend_spike/report/3d/efficiency/fixed_grid_sensitivity.vtu`
- `examples/fixed_grid_backend_spike/openfoam/porosity_based_R10x_init/VTK/case_50.vtm`

## OpenFOAM Evidence Tasks

1. Record the exact Docker image and solver version.
2. Search installed tutorials, source, and runtime-selection tables for:
   - porosity topology design variables;
   - level-set topology design variables;
   - density/porosity interpolation;
   - topology sensitivities;
   - force objectives and multiple adjoint objectives.
3. Copy the smallest relevant tutorial into
   `examples/fixed_grid_backend_spike/openfoam/`.
4. Run the tutorial unchanged and preserve logs.
5. Replace its objective with a minimal external-flow force objective.
6. Export density/porosity and sensitivity volume fields.
7. Apply one deterministic density perturbation without changing the mesh.
8. Compare primal and adjoint directional derivatives with centered finite
   differences.

Required evidence:

- `backend_environment.json`
- `capability_matrix.json`
- `primal_baseline_summary.json`
- `primal_perturbed_summary.json`
- `density.vti`
- `sensitivity.vti`
- `direction_check.json`
- raw solver dictionaries and logs

## Pass/Fail Rules

OpenFOAM passes T0 only if:

- density changes do not trigger remeshing;
- both downforce and drag respond to density;
- both density derivatives can be exported;
- the efficiency-constraint derivative is non-degenerate;
- at least one centered directional check has the correct sign for both
  objective and constraint;
- the case can be launched through the existing Docker execution layer.

OpenFOAM fails T0 if its available topology path is restricted to an
incompatible objective, cannot expose density derivatives, or requires
surface/mesh parameterization instead of a volume density field.

If OpenFOAM fails, repeat the same evidence tasks for DAFoam. Select
AMReX/custom only after documenting why both existing adjoint stacks fail.

## Final Decision

Select OpenFOAM v2512 for the first Stage T adapter and close T0. The
directional porous-force objective, separate 3D drag/downforce adjoints, and
efficiency-gradient construction all pass centered checks. DAFoam and a
custom AMReX backend remain fallback options, not immediate implementation
tasks.

## First Integration Boundary

The backend spike must remain isolated from the existing body-fitted runner.
Once selected, the first production adapter will implement:

```text
topology_state.json
    -> fixed-grid case
    -> primal volume fields
    -> downforce/drag volume sensitivities
    -> fixed_grid_sensitivity.vti
```

It will not emit an STL until the Stage T run reaches the density-to-SDF
handoff.

## Non-Goals For T0

- No parametric wing generation.
- No full three-dimensional optimization loop.
- No GUI work.
- No custom boundary-layer mesh generation.
- No claim of production accuracy.
- No extension of the current empirical surface-sensitivity multiplier.
