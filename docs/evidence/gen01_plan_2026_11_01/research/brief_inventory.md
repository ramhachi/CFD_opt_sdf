# Brief: implementation inventory (read-only)

Repository: /Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/github-local-status-review-66bea1
Read-only. Do not write anything. Do not read any .kicad_* files. Search breadth: very thorough.

This is an SDF-based aerodynamic shape-optimization research repo (Python `src/`, `scripts/`, Julia WaterLily kernels under `infra/kaggle/`, OpenFOAM pipelines run through Docker).

Goal: an engineering inventory that a planner can use to design a GENERIC whole-vehicle optimizer (SDF representation of many components, hundreds-to-thousands of design variables, gradients from an adjoint RANS solver on body-fitted meshes generated from the SDF). The planner needs to know what exists today, its interfaces and hard-coded assumptions, and which parts would have to be replaced.

Report, with file paths and line references, concise but complete (under ~2500 words; prefer tables):

1. SDF representation and genesis: how the canonical SDF is stored (array shape, spacing h, domain, dtype, npz schema), how v18 "analytic stadium plate" is generated, how analytic modes (camber/pitch/reflex/heave/twist/surge) deform it, how the SDF is re-derived (analytic vs. re-initialisation), single-object / single-component assumptions (one closed body, fixed bounding box, symmetry).
2. Geometry gates: the 13 GEOM-02 v2 gates (names, checks, thresholds), P22-v2 volume count, smoothed-volume band, clearance, min_feature_width; where implemented; which assume a single body or a grid resolution.
3. STL export and OpenFOAM pipeline: marching cubes / STL export; the V1/V2/V3 case builders (snappyHexMesh settings, background mesh, refinement levels, cell counts, domain size, boundary conditions, solver settings, turbulence model if any, Re, convergence criteria, force extraction); the Docker local runner (`scripts/local_openfoam.py`), image/version pins; how results are hashed/verified. Note the T2-0 2D RANS pipeline (gmsh, k-ω SST, SA, adjointOptimisationFoam attempt) and where the `ADJ_FAILED` SIGFPE record is.
4. WaterLily kernel path: how a design state becomes a WaterLily run (Kaggle kernels, campaign JSON, harness verify, placement phases), flow_32/48 definitions, Re definition (Re_L 80), dt rule, memory per cell; the AD/FD attempts (FD-05..08, DIAG1-5, tie-averaged AD): where code and evidence are and the final status.
5. Optimizer / proposer code: what exists for proposing designs (response surface SCREEN-01, LOWDIM, historical Stage T density/Brinkman optimizer, B-spline Stage S), their interfaces, and whether any gradient-based optimizer loop (projected gradient, SLSQP, MMA) exists.
6. Harness and registration machinery: campaign schema, freeze records, evidence directories, SHA256SUMS conventions, tests layout, CI workflow (what it installs and runs), Python/Julia environment pins.
7. Known limits recorded in docs that bear on a generic system: single parent, one object, fixed far-field domain, clearance preflight, "R0 occupancy alias", flow_24 demotion, Poisson confounding, multi-body or ground/moving-ground handling, wheel rotation, symmetry planes.

For each area: what exists, key interfaces (function/CLI names), hard-coded assumptions, and your judgment of reuse vs. replace for the generic system.
