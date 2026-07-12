# Adjoint Topology Data Contract

This document defines the data contract for moving from the current SDF/density
topology exploration code through the existing body-fitted adjoint adapter.

Roadmap note, 2026-07-02: this contract covers reusable Geometry Service,
orchestration, and Stage V/early Stage S artifacts developed under the
`Legacy A-K Body-Fitted Adjoint Roadmap`. It does not define the Stage T
fixed-grid Brinkman primal, volume adjoint, virtual-diffusion connectivity, or
GCMMA state. The authoritative Stage T schema is now
`docs/fixed_grid_data_contract.md`.

The current implementation can generate SDF-validated density candidates, export
STL geometry, run body-fitted OpenFOAM through Docker, summarize force
coefficients, and run an initial OpenFOAM adjoint smoke case on an already
meshed candidate. OpenFOAM `faceSensNormal...` output can be normalized to
`surface_sensitivity.csv` and projected to `sensitivity.vti`, but this is still
an early adapter path rather than a calibrated production adjoint optimizer.

## Coordinate And Sign Conventions

- Coordinates use the project STL/OpenFOAM coordinate frame.
- Flow direction is `+x`.
- Span direction is `y`.
- Vertical direction is `z`.
- OpenFOAM `Cl` uses `liftDir (0 0 1)`.
- Downforce coefficient is `-Cl`.
- The scalar objective used by minimizers is `objective = -downforce + penalty`.
- A negative objective change is an improvement.
- A positive density sensitivity means increasing density increases the scalar
  objective unless an adapter explicitly documents a different convention.

## Authoritative Artifacts

### Project Input

`project.yaml` is the authoritative user input for one design run.

Required roles:
- `geometry.design_geometry`: current design STL used for body-fitted CFD.
- `geometry.design_domains`: allowed design region.
- `geometry.forbidden_regions`: keep-out regions.
- `roots`: root/mount regions.
- `grid`: SDF grid definition.
- `constraints`: geometry and aero-balance constraints.
- `objective`: scalar objective configuration.
- `operating_point`: single-point CFD operating condition.

### SDF State

`sdf_fields.vti` is the visualization/export artifact for SDF and derived
constraint arrays.

Current expected arrays:
- `design_phi`
- `design_narrow_band`
- `allowed_phi`
- `forbidden_phi`
- `root_phi`
- `violation_rule`
- `violation_forbidden`
- `connectivity_components`
- `connectivity_unrooted`
- `eroded_solid`
- `eroded_unrooted`

The SDF grid origin, spacing, and dimensions must match any density or
sensitivity grid used for density updates.

### Design State

`design_state.json` is the authoritative machine-readable design variable
manifest for topology/adjoint phases.

Required fields:
- `schema_version`
- `kind`
- `design_variable`
- `density_vti`
- `density_array`
- `grid`
- `bounds`
- `iso_value`
- `derived_geometry`
- `source_project`
- `created_by`

`density.vti` is the authoritative density field file for topology update and
adjoint sensitivity projection.

Expected arrays:
- `density`: float density design variable in `[0, 1]`.
- `allowed_mask`: `1` where density may be active.

`geometry/front_wing_initial.stl` is a derived artifact generated from density
for body-fitted CFD and SDF validation. It is not the primary design variable in
adjoint topology phases.

### Constraint Report

`runs/front_wing_demo/report.json` records SDF constraint evaluation for the
candidate. Constraint records in `topology_result.json` are the optimizer-facing
projection of this report plus aero constraints.

Hard enforced geometry constraints:
- rule violation cells must be zero.
- forbidden intersection cells must be zero.
- nominal unrooted components must be zero.
- eroded unrooted components must be zero when enabled.

### CFD Case And Summary

`runs/front_wing_demo/openfoam_front_wing/` is the body-fitted OpenFOAM case.

Current primal CFD path:
- `blockMesh`
- `surfaceFeatureExtract`
- `snappyHexMesh -overwrite`
- `checkMesh -allGeometry -allTopology`
- `simpleFoam`
- force coefficient postprocessing

`cfd_summary.json` is the scalar CFD summary consumed by optimizers.

Required fields:
- `source`
- `latest`
- `drag_coefficient`
- `lift_coefficient`
- `downforce_coefficient`
- `efficiency`
- `efficiency_constraint`
- `ok`

For `run-adjoint-topology --efficiency-min-override`, `efficiency_constraint`
is computed with the run-local override instead of the project YAML value. The
top-level `adjoint_topology_summary.json` records `efficiency_min_override` so
accepted/rejected status can be interpreted correctly.

OpenFOAM v2512 writes `postProcessing/forceCoeffs/0/coefficient.dat`; older
variants may write `forceCoeffs.dat`. Both are supported.

### Sensitivity State

`sensitivity.vti` is the authoritative sensitivity field once a sensitivity
backend has generated it.

Required arrays:
- `objective_density_sensitivity`: `d objective / d density`.
- `downforce_density_sensitivity`: `d downforce / d density`, when available.
- `drag_density_sensitivity`: `d Cd / d density`, when available.
- `constraint_sensitivity`: combined active constraint sensitivity, when used.
- `active_mask`: cells considered by the update rule.

`sensitivity_summary.json` records:
- backend name and version.
- objective name.
- sign convention.
- source primal case.
- source adjoint case.
- projection method.
- min/max/norm statistics.
- failed or missing sensitivity arrays.
- `constraint_sensitivity_status`: machine-readable diagnosis for whether the
  projected constraint sensitivity is usable for efficiency-constraint updates.
- `constraint_sensitivity_diagnostics`: active-cell norms, objective/constraint
  cosine, drag-sensitivity availability, and a short diagnostic note.

Current status values:
- `available`: required arrays exist and `drag_density_sensitivity` is nonzero
  on active cells.
- `degenerate_zero_drag_sensitivity`: the constraint array exists but the drag
  component is zero, so the efficiency constraint is not independent from
  downforce.
- `zero_constraint_sensitivity`: the projected constraint sensitivity is
  numerically zero.
- `missing_arrays`: required sensitivity arrays are absent.
- `no_active_cells`: no active cells were available for diagnosis.

`density_update.vti` records proposed update arrays:
- `density_old`
- `density_new`
- `density_delta`
- `objective_density_sensitivity`: effective sensitivity used by the density
  update after any update-direction multiplier and optional constraint blend.
- optional `base_objective_density_sensitivity`: objective-only effective
  sensitivity before constraint blending.
- optional `raw_objective_density_sensitivity`: raw backend/projection field
  before calibration.
- optional `raw_constraint_sensitivity`: projected constraint derivative before
  normalization.
- optional `effective_constraint_sensitivity`: normalized constraint derivative
  blended into the update direction.
- optional `combined_update_sensitivity`: final objective-plus-constraint
  gradient used by the update rule; equal to `objective_density_sensitivity`
  when constraint blending is active.
- optional `objective_derivative_sensitivity`: raw field multiplied by the
  derivative multiplier from adjoint calibration.
- `active_mask`
- optional filter/projection arrays.

`density_step_result.json` stores the requested
`constraint_sensitivity_weight`, the
`effective_constraint_sensitivity_weight`, and
`constraint_sensitivity_blend_policy`. When
`sensitivity_summary.json` reports `usable_for_efficiency_constraint_update:
false`, the effective weight is forced to `0.0` and constraint-blend arrays are
not emitted to `density_update.vti`.

`finite_difference_check.json` records gradient-check diagnostics:
- sampled density cell indices.
- perturbation method: `central`, `forward`, or `backward`.
- finite-difference derivative.
- analytic `objective_density_sensitivity`.
- absolute and relative error.
- sign match.
- classification: `ok`, `sign_mismatch`, `relative_error`, or
  `failed_perturbation`.

`finite_difference_check.vti` records ParaView diagnostic arrays:
- `sampled_mask`
- `analytic_sensitivity`
- `finite_difference_sensitivity`
- `relative_error`

`adjoint_direction_check.json` records real-adjoint direction diagnostics for a
completed topology step with both pre-update and post-update primal CFD:
- source `adjoint_topology_step_result.json`.
- source `density_update.vti` and `sensitivity.vti`.
- predicted objective delta from
  `sum(objective_density_sensitivity * density_delta)`.
- actual objective delta from pre/post primal `-downforce_coefficient`.
- optional predicted and actual `efficiency_constraint` delta.
- sign match, scale ratio, and classification.

`adjoint_direction_check.vti` records ParaView diagnostic arrays:
- `density_delta`
- `objective_density_sensitivity`
- `objective_direction_contribution`
- optional `constraint_sensitivity`
- optional `constraint_direction_contribution`
- `active_mask`

`paired_adjoint_direction_check.json` records positive/negative direction
diagnostics for a completed topology step:
- perturbation mode: `as_updated` or `centered`.
- perturbation scale applied to the stored density update.
- optional centered baseline `design_state.json`, `density.vti`, STL, and
  primal CFD summary.
- generated positive and negative `design_state.json` paths.
- generated positive and negative `density_update.vti` paths.
- predicted objective and constraint deltas for each direction.
- optional primal CFD summaries for each direction.
- actual objective and constraint deltas when primal CFD is available.
- recommended feasible direction.
- sensitivity sign decision. This remains unresolved when either direction is
  clipped to near-zero `density_delta_l2`.
- `classification_code`

`adjoint_calibration_summary.json` records aggregate calibration diagnostics
from one or more paired direction reports:
- source `paired_adjoint_direction_check.json` paths.
- valid candidate observation count.
- per-candidate predicted and actual objective/constraint deltas.
- objective and constraint scale-ratio statistics.
- recommended sensitivity multiplier for gradient-descent updates.
- recommended derivative multiplier for interpreting the raw projected field as
  `d objective / d density`.
- calibration status.

`adjoint_topology_calibration.json` records the calibration settings actually
applied by an adjoint-topology run:
- source `adjoint_calibration_summary.json`, when used.
- source observation count and calibration status.
- applied sensitivity multiplier for density-update direction.
- applied derivative multiplier for interpreting raw sensitivity values.

`adjoint_topology_step_result.json` may use status `improving_infeasible` when
post-update real CFD still violates an enforced constraint but the total
enforced violation decreases relative to the step's pre-update primal CFD. This
status is not accepted and does not increment `accepted_count`; it is only a
guarded continuation state when explicitly enabled. In that mode the step and
history CSV also record:
- `continuation_reason`
- `constraint_violation_before`
- `constraint_violation_after`

`surface_sensitivity.csv` is the normalized surface-sensitivity handoff used by
the first adjoint projection layer.

Required columns:
- `x`
- `y`
- `z`
- `objective_surface_sensitivity`

Optional columns:
- `downforce_surface_sensitivity`
- `drag_surface_sensitivity`

For current OpenFOAM `faceSensNormal...` ingestion, the scalar adjoint output is
treated as the negative-lift objective sensitivity. The normalizer writes
`downforce_surface_sensitivity = -objective_surface_sensitivity` and zero-fills
`drag_surface_sensitivity` because that field is not provided by
`faceSensNormal...`. The projected `sensitivity_summary.json` therefore reports
`constraint_sensitivity_status: degenerate_zero_drag_sensitivity` for these real
adjoint runs until a drag or direct constraint sensitivity source is added.

`projection_diagnostics.vti` records projection QA arrays:
- `active_mask`
- `projection_distance`
- `projection_weight_sum`
- `objective_density_sensitivity`

## Responsibility Boundaries

### SDF Geometry Layer

Owns:
- STL loading.
- SDF grid construction.
- role-specific SDF arrays.
- geometry constraints.
- VTK/ParaView exports.

Must not own:
- CFD solver execution policy.
- adjoint solver implementation.
- optimization update policy.

### Topology State Layer

Owns:
- density design state.
- density VTI export.
- density-to-STL derived geometry.
- design state manifest.
- candidate result records.

Must not treat STL as the primary adjoint design variable.

### CFD Layer

Owns:
- OpenFOAM case generation.
- backend execution: local, WSL, Docker.
- force coefficient parsing.
- primal CFD summary.

Must not own:
- density updates.
- sensitivity filtering.
- optimizer history.

### Sensitivity Layer

Owns:
- sensitivity file schema.
- mock/analytic sensitivities.
- adjoint output ingestion.
- surface-to-grid projection.
- finite-difference comparison data.

The file schema and mock/analytic grid sensitivity writer are implemented.
Surface-to-grid projection and finite-difference comparison are implemented for
the normalized CSV/mock sensitivity contract. Initial OpenFOAM
`faceSensNormal...` ingestion is implemented with explicit zero-drag
diagnostics; broader raw output variants, direct drag/constraint sensitivities,
and calibration are still incomplete.

### Optimizer Layer

Owns:
- update rule.
- move limits.
- bounds.
- filtering/projection.
- history.
- best design export.
- resume and failure classification.

It consumes `design_state.json`, `sensitivity.vti`, constraint records, and CFD
summaries.

## Phase Readiness Matrix

| Phase | Status | Evidence |
| --- | --- | --- |
| A: data contract | Implemented | This document |
| B: density design state | Implemented enough for Phase C/D | `density.vti`, `design_state.json`, schema read/validation |
| C: sensitivity I/O | Initially implemented | Mock `sensitivity.vti`, `sensitivity_summary.json`, and `density_update.vti` preview |
| D: density update optimizer | Initially implemented | Mock-sensitivity density optimizer with history and best export |
| E: finite-difference gradient check | Initially implemented | Mock objective finite-difference checker with JSON/CSV/VTI diagnostics |
| F: real OpenFOAM runner coupling | Initially implemented | topology candidates can execute OpenFOAM backend and postprocess CFD summary |
| G: adjoint solver selection | Implemented | OpenFOAM `adjointOptimisationFoam` selected as first backend |
| H: adjoint adapter | Initially implemented | Generated adjoint dictionaries, preflight, real Docker adjoint smoke, `faceSensNormal` normalization, and dry-run fallback |
| I: sensitivity projection | Initially implemented | Surface CSV and OpenFOAM `faceSensNormal` output can project to density-grid VTI with ParaView diagnostics |
| J: adjoint topology loop | Initially implemented | Optional real primal CFD, adapter dry-run or real adjoint sensitivity, density update, optional post-update primal CFD ranking, rejection guard, infeasible-improvement continuation, calibration-summary multiplier handoff, constraints, history, Markdown summary, best export |
| K: verification | Initially implemented | `docs/verification_report.md` records tests, primal/adjoint smoke demos, dry-run and real one-step topology demos including post-update primal re-evaluation, guarded multi-step request, gradient checks, real-adjoint direction diagnostics, paired-direction diagnostics, aggregate calibration summaries, calibrated dry and real progress loops, and remaining calibration gaps |

## Immediate Implementation Rule

From Phase B onward, new topology code should read and write density through
`design_state.json` plus `density.vti`. STL remains a derived CFD input.
