# optimizer-generated shape preregistration v1 — 2026-09-21

Status: draft schema (DF0 deliverable), subordinate to
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
Applies to: any candidate produced by an optimizer (Stage T density field, Stage S
sharp-interface update, or a diagnostic generator) that will be promoted to a
later stage, ranked against another candidate, or used as an accepted iterate.

The historical WP6/WP6-2 shapes were declared before measurement and their
application scope was audited afterwards (`wp6_2_evidence_audit_2026_09.json`).
This schema makes that impossible for future optimizer output: the geometry
facts below must be measured and recorded **before** the candidate is used,
and a missing or violated field is fail-closed.

## Required record

```json
{
  "kind": "optimizer_shape_preregistration",
  "schema_version": 1,
  "created": "<ISO date>",
  "candidate": {
    "candidate_id": "<stable id>",
    "parent_candidate_id": "<id or null>",
    "iteration": 0,
    "produced_by": "stage_t | stage_s | diagnostic_generator",
    "problem_spec_sha256": "<hash>",
    "design_hash": "<hash of the design variable array>",
    "transform_hash": "<hash of filter/projection/interpolation/transfer stack>"
  },
  "declared_policy": {
    "minimum_solid_width_m": 0.0,
    "minimum_void_width_m": 0.0,
    "minimum_gap_m": null
  },
  "measured_geometry": {
    "spacing_m": 0.05,
    "min_feature_size_m": 0.0,
    "min_feature_size_cells": 0.0,
    "quantization_tolerance_m": 0.025,
    "n_components_26": 1,
    "component_cells": [0],
    "thin_fraction_below_policy": 0.0,
    "self_intersection_cells": 0,
    "clearance_to_domain_m": 0.0,
    "volume_m3": 0.0
  },
  "extraction": {
    "method": "iso_surface_vti | analytic_definition | none",
    "threshold": 0.5,
    "threshold_range": [0.45, 0.5, 0.55],
    "threshold_selection_rule": "pre-registered rule text, not an observed best",
    "volume_error_m3": null,
    "surface_distance_error_m": null
  },
  "uncertainty": {
    "stage_t_grid_abs": null,
    "stage_v_grid_abs": null,
    "extraction_abs": null,
    "candidate_specific_abs": null
  },
  "gates": {
    "required_pairs": ["baseline->candidate"],
    "acceptance_rule": "improvement > candidate-specific combined uncertainty",
    "stop_conditions": ["..."]
  },
  "provenance": {
    "evidence_artifacts": ["<path>"],
    "code_commit": "<sha>"
  }
}
```

## Fail-closed rules

1. `measured_geometry` is measured from the actual occupancy/mask, not copied
   from the generating parameters. Declared `minimum_solid_width_m` compared
   with `min_feature_size_m` uses the recorded `quantization_tolerance_m`;
   `under_resolved` (feature below policy beyond quantization) rejects the
   candidate from any ranking or handoff claim.
2. An empty or absent `extraction.volume_error_m3` / `surface_distance_error_m`
   is recorded as `not_measured` and is never interpreted as zero. A verdict
   that depends on extraction sensitivity remains provisional until measured.
3. `threshold_selection_rule` must be a rule, not "the best observed"; results
   seen before the rule was fixed invalidate the registration.
4. `uncertainty.candidate_specific_abs` must be at least the maximum of the
   registered band and the candidate's own measured drift; a shared band may
   not be inherited silently (see P18 audit drift table).
5. Any change to thresholds, candidate set, required pairs, or uncertainty
   after a run starts closes the campaign; a new registration is required.
