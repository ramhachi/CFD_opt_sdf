# Adjoint Solver Selection

Date: 2026-06-24
Roadmap scope updated: 2026-07-02
Current roadmap: `TSV Roadmap`
Historical source: `Legacy A-K Body-Fitted Adjoint Roadmap`

## Decision

Use OpenFOAM `adjointOptimisationFoam` as the first real adjoint backend for this
project's body-fitted Stage V verification path and early Stage S
shape-adjoint prototype.

Backend id: `openfoam-adjoint`.

This is the lowest-friction path because the project already generates and runs
OpenFOAM cases through Docker/WSL/local backends, already postprocesses
OpenFOAM force coefficients, and already treats OpenFOAM as an external solver
backend for future binary distribution.

This decision does not select the Stage T fixed-grid density/Brinkman topology
backend. Stage T requires volume derivatives with respect to density/porosity,
fixed-mesh updates, separate downforce and drag sensitivities, and a path to
connectivity constraints. That backend decision is reopened in T0 of
the `TSV Roadmap` in `docs/phase_plan.md`.

## Verified Local Availability

The current Docker image used by this project includes the adjoint executable:

```powershell
docker run --rm opencfd/openfoam-default:2512 bash -lc "command -v adjointOptimisationFoam && adjointOptimisationFoam -help | head -40"
```

Observed executable:

```text
/usr/lib/openfoam/openfoam2512/platforms/linux64GccDPInt32Opt/bin/adjointOptimisationFoam
```

Observed version:

```text
OpenFOAM-2512 (2512)
```

## Requirements For The Existing Body-Fitted Adapter

- Windows host workflow must stay one-command friendly.
- Solver runtime should remain external, not bundled into the app binary.
- First operating point is single-point.
- First geometry is a front-wing density candidate exported to STL for
  body-fitted verification.
- Existing body-fitted OpenFOAM primal cases should remain reusable.
- The adapter must eventually produce `sensitivity.vti` on the density/SDF grid.
- The first real adapter may start with surface sensitivity and project it onto
  the density grid in Phase I.

## Candidate Comparison

| Candidate | Fit | Strengths | Main Cost/Risk |
| --- | --- | --- | --- |
| OpenFOAM `adjointOptimisationFoam` | Best first backend | Same solver family, same Docker image, OpenFOAM v2312+ topology capability, shape/topology workflow is closest to current case generation | Requires new adjoint case dictionaries and sensitivity-output parsing |
| DAFoam | Strong future backend | Discrete adjoint with OpenFOAM, Python interface, OpenMDAO/MACH ecosystem, high-fidelity MDO | Heavier environment and workflow; current v5 site indicates active migration; more setup than needed for first adapter |
| SU2 discrete adjoint | Good alternate backend | Mature discrete adjoint tooling, Python scripts for direct/adjoint/finite-difference workflows, explicit surface/design-variable sensitivity tools | Requires SU2 mesh/config generation and likely FFD/surface parameterization; less direct fit for current STL/snappy/OpenFOAM pipeline |

## Historical Phase H Path

Phase H should implement an `openfoam-adjoint` adapter with this initial shape:

1. Accept an existing topology candidate `design_state.json`.
2. Locate or generate its OpenFOAM primal case.
3. Prepare an adjoint case directory beside the primal case.
4. Run `adjointOptimisationFoam` through the same backend abstraction used by
   `simpleFoam`.
5. Collect sensitivity outputs into an adapter-specific raw directory.
6. Convert raw surface or volume sensitivities to the common
   `sensitivity.vti` schema.
7. Write `adjoint_run_summary.json` with command, backend, return code,
   timeout/error state, raw outputs, and conversion status.

The first implementation should be conservative: single objective, single
operating point, front-wing candidate only, and no automatic topology update
until Phase I/J.

## Adapter Boundary

The adapter should not own density updates. It should only translate solver
outputs into the project sensitivity contract:

- `objective_density_sensitivity`
- `downforce_density_sensitivity`, if available or projectable
- `drag_density_sensitivity`, if available or projectable
- `constraint_sensitivity`, when synthesized
- `active_mask`

Phase I will own surface-to-grid projection and filtering.

## Sources Checked

- OpenFOAM `adjointOptimisationFoam` v2312 user manual:
  https://www.openfoam.com/documentation/files/adjointOptimisationFoamManual_v2312.pdf
- OpenFOAM v2312 numerics announcement, including topology optimisation:
  https://www.openfoam.com/news/main-news/openfoam-v2312/numerics
- DAFoam current site:
  https://dafoam.github.io/
- DAFoam older ReadTheDocs site:
  https://dafoam.readthedocs.io/en/latest/
- SU2 execution documentation:
  https://su2code.github.io/docs_v7/Execution/
- SU2 software components documentation:
  https://su2code.github.io/docs/Software-Components/
