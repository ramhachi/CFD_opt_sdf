# DF4 record — extraction sweep and Stage S drag sensitivity path (2026-09-21)

Status: DF4 partial deliverable, subordinate to
[`downforce_optimization_architecture_plan_2026_09.md`](downforce_optimization_architecture_plan_2026_09.md)
DF4 and to `problem_register_2026_09.md` (P10/P18-adjacent handoff claims).

## Implemented in this slice

1. **Pre-registered extraction sweep** `src/cfd_sdf/extraction_sweep.py` and CLI
   `cfd-sdf sweep-density-extraction`:
   - every registered threshold is evaluated through
     `build_density_to_sdf_handoff`; failed thresholds stay as explicit rows
     with their error text;
   - selection uses a registered rule and range
     (`registered_range_min_abs_volume_error` or
     `registered_range_first_that_passes`), never an observed best;
   - each row records volume error, watertightness, component count,
     revoxelized geometry metrics (component count and supersampled feature
     size), manifest path and SHA-256;
   - `require_ready_for_stage_s` may be registered for campaigns where a real
     design must already pass the handoff gate.
2. **Stage S drag surface sensitivity**: `export_openfoam_surface_sensitivity_to_csv`
   now consumes a separate drag-adjoint `faceSensNormal<drag-solver>` file with a
   declared sign, records the mode
   (`faceSensNormal-of-drag-adjoint-solver`), and `require_drag=True` turns the
   historical zero-fill into a hard failure so Stage S refinement cannot run on
   a zero drag sensitivity.

## First real sweep (evidence)

`docs/evidence/stage_t_handoff_threshold_sweep_2026_09.json` — sweep of the
existing `work/ramp_interp/fixture` candidate over `[0.45, 0.5, 0.55]` with the
registered volume-error rule inside `[0.45, 0.55]`:

| threshold | status | measured |
| --- | --- | --- |
| 0.45 | ok | volume relative difference 0.716, not `ready_for_stage_s` |
| 0.50 | error | iso value not strictly inside the interpolated density range |
| 0.55 | error | connectivity validation failed |

This is a measurement, not a handoff success: it confirms the standing picture
that this candidate is not a qualified design (grey/marginal material), and it
demonstrates that extraction sensitivity is now measured per threshold instead
of being reported as an empty block.

## Registered, not yet run

- Stage S baseline selection: OpenFOAM `sensitivityType volumetricBSplines` with
  the body-fitted morpher (architecture plan section 9 order); its surface
  sensitivity must be FD-qualified (via the fd_gradient_v1 profile) before it
  drives an accepted shape step.
- A real T-to-S handoff on a candidate that passes `ready_for_stage_s=true`
  (DF3 output candidate), with the registered sweep applied to that candidate.

## Not claimed

- No sharp-interface refinement was executed; DF4's acceptance condition
  (`ready_for_stage_s=true` real candidate + FD-consistent Stage S first step)
  is not yet met.
- No surface gradient sign/scale is qualified for production until the FD
  campaign runs.
