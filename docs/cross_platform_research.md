# Mac / Windows research foundation

This work package makes the existing repository usable for bounded numerical
checks on 32 GB machines. It does not yet implement the full SDF optimizer.
The [roadmap](phase_plan.md) owns progress and the
[accepted design](development_plan_2026_09.md) owns the acceptance criteria.

## Setup

Use Python 3.12 for the initial environment. On macOS / Linux:

```bash
bash scripts/bootstrap.sh
# Apple Silicon, with optional Metal support:
bash scripts/bootstrap.sh --metal
.venv/bin/cfd-sdf research doctor --output work/runtime.json
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
.\.venv\Scripts\cfd-sdf.exe research doctor --output work/runtime.json
```

The CPU commands share the same CLI. Replace `.venv/bin/cfd-sdf` with
`.\.venv\Scripts\cfd-sdf.exe` on Windows. Diagnostic tool presence and Docker
reachability do not prove solver or GPU qualification. The optional `metal`
extra uses MLX on Apple Silicon; Windows does not require that dependency.
CUDA acceleration remains a later implementation step.

## Bounded checks

```bash
.venv/bin/cfd-sdf research preflight examples/generic_problem_v2/project.yaml --output work/preflight.json
.venv/bin/cfd-sdf research lbm-benchmark --backend cpu --output work/lbm_cpu.json
.venv/bin/cfd-sdf research lbm-benchmark --backend metal --output work/lbm_metal.json
```

The generic example refers to geometry assets that are not included. A failed
preflight on that example is expected. Supply real assets and a declared voxel
size that resolves the declared smallest feature. The preflight reports its
limited coverage; file validity and declared resolution do not establish all
clearance, thickness, connectivity or mesh-convergence requirements.

The planned XLB evaluation is still pending. The small NumPy reference and
Metal kernel added here isolate arithmetic/streaming parity on the Mac; they
are not a replacement CFD framework. Avoid extending them into a second
general solver before evaluating reusable libraries for the next boundary
and physics requirements.

The benchmark is a periodic, two-dimensional D2Q9 BGK Taylor–Green vortex.
CPU populations use FP64; Metal populations use FP32. All values are lattice
units. It checks decay against the analytical incompressible solution and
compares the complete final GPU velocity field after the same number of steps
with the CPU reference. Compilation
warmup is separated from GPU stepping time. Peak Metal allocation is not total
process memory. Small grids can be dominated by dispatch overhead.

There are no walls, aerodynamic forces, SDF boundaries, turbulence models,
adjoints or topology changes in this benchmark. Its `pass` status applies only
to the reported numerical checks. It is not evidence of a useful optimized
shape or of performance at target Reynolds number.

## OpenFOAM on macOS

With Docker running, build the existing custom objective library inside the
same image used by the solver:

```bash
bash scripts/build_porous_force_objective.sh
```

This uses OpenFOAM v2512 and writes platform-specific build products under
`openfoam_extensions/porousDirectionalForce/`; those files are ignored by Git.
Rebuild on another architecture. Availability of a library does not establish
correct generic-domain mesh, boundary, objective or sensitivity semantics.

## Verification record

The implementation is tested on an Apple M4 Mac with 32 GB unified memory.
Windows and Linux have a CPU CI matrix; actual RTX 4070 Ti execution and VRAM
measurement require a separate runtime qualification. Record exact results
below after the checks complete.

### OpenFOAM numerical convergence (2026-09-07)

On the ARM64 `opencfd/openfoam-default:2512` image, the existing G2 two-flow
example completed successfully. The existing extractor and convergence gate
produced [this qualification report](evidence/openfoam_convergence_2026_09.json).
The problem-spec hash in that report binds the requested conditions.

| Check | straight | yawed | Threshold |
| --- | ---: | ---: | ---: |
| Maximum final primal residual | 9.9568e-9 | 1.0163e-8 | 1e-6 |
| Normalized open-patch flux imbalance | 3.0035e-11 | 3.1780e-12 | 1e-4 |
| Response relative range, last 20 samples | 8.4153e-8 | 4.2078e-5 | 1e-3 |
| Maximum final adjoint residual | 3.4631e-8 | 8.8267e-9 | 1e-6 |

The primal solver took 129 iterations in each case. The selected adjoint took
169 and 228 iterations respectively. The open-patch flux artifact was generated
with `produce-openfoam-normalized-mass-imbalance`; log continuity errors were
not substituted for it. Reproduction commands after building the library:

```bash
.venv/bin/cfd-sdf compile-openfoam-problem-cases examples/g2_openfoam_compile/project.yaml examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base work/g2_runtime --adjoint-iterations 1500 --overwrite
.venv/bin/cfd-sdf run-openfoam work/g2_runtime/flow_straight --backend docker --execute --timeout-seconds 600
.venv/bin/cfd-sdf run-openfoam work/g2_runtime/flow_yawed --backend docker --execute --timeout-seconds 600
.venv/bin/cfd-sdf produce-openfoam-normalized-mass-imbalance work/g2_runtime/flow_straight --backend docker
.venv/bin/cfd-sdf produce-openfoam-normalized-mass-imbalance work/g2_runtime/flow_yawed --backend docker
.venv/bin/cfd-sdf extract-openfoam-convergence-evidence work/g2_runtime work/g2_runtime/convergence_evidence.json
.venv/bin/cfd-sdf qualify-openfoam-convergence examples/g2_openfoam_compile/project.yaml work/g2_runtime/convergence_evidence.json work/g2_runtime/convergence_qualification.json
```

Solver warnings remain about ISQP without a constraint adjoint and an unused
`momSource` for adjoint fields. Residual convergence is not a finite-difference
sensitivity check. No target-aerodynamics, optimized-shape, physical-model or
complete native-artifact qualification is inferred from this report.

### LBM numerical reference (2026-09-07)

The [numerical evidence snapshot](evidence/lbm_reference_2026_09.json) records
three square grids with fixed `Re = UL/nu = 3.2` and fixed viscous time
`nu*t/L² = 0.009765625`. Refinement reduces lattice velocity and increases
step count; simply changing grid size at fixed lattice velocity/time would
not compare the same physical problem.

| Grid | Steps | Lattice velocity | Relative analytical velocity error |
| --- | ---: | ---: | ---: |
| 16 × 16 | 25 | 0.02 | 2.0078e-2 |
| 32 × 32 | 100 | 0.01 | 4.9971e-3 |
| 64 × 64 | 400 | 0.005 | 1.2450e-3 |

Observed orders are 2.006 and 2.005. At 32 × 32 and 100 steps, the Metal/CPU
velocity-field relative L2 error is 1.5646e-5 and Metal relative mass drift
is 1.0187e-6. These pass the predeclared benchmark tolerances. The small-grid
GPU loop was not faster than the CPU reference in the recorded run; timings
also include different validation overhead and concurrent host workloads.

### Native artifact readiness remains blocked

`assess-native-openfoam-v2-artifact-readiness` reports `execution_ready: true`
and `ready: false` for the same two-flow bundle. The
[readiness snapshot](evidence/native_readiness_2026_09.json) records these reasons:

- `missing_native_artifact_binding`
- `response_value_unit_provenance_not_bound`
- `rho_gradient_convention_not_bound`
- `mesh_grid_mapping_not_bound`
- `topology_constraint_values_not_available`

Both meshes cover `(-1,-0.8,-0.6)` to `(2,0.8,0.6)` metres. The canonical
20 mm grid is 150 × 80 × 60 (720,000 cells), while the executed OpenFOAM mesh
is 32 × 16 × 16 (8,192 cells), with 93.75/100/75 mm spacing. Matching domain
bounds therefore does not prove matching discretizations. Conservative grid
transfer and its transpose for sensitivities need explicit provenance and
verification before these fields can drive the generic optimizer.

The next integration work must establish force-coefficient to newton
conversion, validate the complete `alpha → alphaTilda → beta → topOSens`
chain against finite differences and the canonical `rho` convention, bind
the mesh transfer, and evaluate the five requested topology constraints.
The writer correctly refuses export until those requirements are supplied;
creating metadata declarations alone would not constitute validation.
