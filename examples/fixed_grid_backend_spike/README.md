# Fixed-Grid Backend Spike

This directory contains executable T0 evidence for the authoritative
`TSV Roadmap`.

## Scope

The copied OpenFOAM v2512 tutorial demonstrates:

- fixed-mesh density topology variables;
- Brinkman penalisation;
- volume topology sensitivity;
- a volume constraint;
- constrained design updates;
- reconstructed density/interpolation fields;
- ParaView export.

It also contains the custom `porousDirectionalForce` objective, separate
directional adjoints, centered finite-difference cases, and an efficiency
constraint sensitivity export. The canonical validation case is fully
three-dimensional and uses physical downforce direction `-Z`.

## Run

```powershell
.\.venv\Scripts\cfd-sdf.exe run-openfoam examples\fixed_grid_backend_spike\openfoam\porosity_based_R10x_init --backend docker --execute --timeout-seconds 600
```

The copied tutorial adds the two OpenMPI root-confirmation variables required
inside the current Docker image.

Reconstruct and export:

```powershell
$case = (Resolve-Path examples\fixed_grid_backend_spike\openfoam\porosity_based_R10x_init).Path
docker run --rm --entrypoint bash --mount "type=bind,source=$case,target=/case" -w /case opencfd/openfoam-default:2512 -lc 'source /usr/lib/openfoam/openfoam2512/etc/bashrc >/dev/null 2>&1; reconstructPar -latestTime; foamToVTK -latestTime -fields "(alphaTilda beta U p)"'
```

Generate capability evidence:

```powershell
.\scripts\run_porous_force_validation.ps1
```

## Result

- Actual solver completion: `true`
- Fixed-mesh updates observed: `true`
- Optimisation iterations: `49`
- Objective reduction: `0.200475`
- 3D drag gradient error: `0.045%` (`pass`, tolerance `10%`)
- 3D `-Z` downforce gradient error: `7.49%` (`pass`, tolerance `10%`)
- 3D efficiency gradient error: `0.424%` (`pass`, tolerance `10%`)
- Overall status: `pass_t0`
- T1 contract validation: `pass` on one 8192-cell Cartesian grid
- Active design cells: `2979`
- T2 canonical primal suite: `pass`, including all-fluid, threshold-solid,
  seed, filtered perturbation, and exact seed-repeat reproducibility
- T2 front-wing legacy-density seed: `converged` after conversion to the
  fixed-grid contract
- Next phase: T3 aerodynamic volume adjoint on the T2 fixed-grid states

Open this file in ParaView:

```text
examples/fixed_grid_backend_spike/openfoam/porosity_based_R10x_init/VTK/case_50.vtm
```

Open the canonical 3D primal and adjoint fields in ParaView:

```text
examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base/VTK/porous_force_3d_fd_base_1/internal.vtu
```

Open the combined efficiency sensitivity fields in ParaView:

```text
examples/fixed_grid_backend_spike/report/3d/efficiency/fixed_grid_sensitivity.vtu
```

Open the authoritative T1 density and sensitivity fields in ParaView:

```text
examples/fixed_grid_backend_spike/report/3d/t1_contract/density.vti
examples/fixed_grid_backend_spike/report/3d/t1_contract/fixed_grid_sensitivity.vti
```

Open the T2 primal input fields in ParaView:

```text
examples/fixed_grid_backend_spike/report/3d/t2_primal_suite_execute/seed/fixed_grid_input_density.vti
examples/fixed_grid_backend_spike/report/3d/front_wing_t2_seed_execute/fixed_grid_input_density.vti
```
