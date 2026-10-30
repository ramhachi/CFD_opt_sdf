# #44 Round 8 surface-flux method preparation

Status: source/method preparation only; **not preregistered and not measured**.
Parent review is required before turning this proposal into immutable criteria
or constructing any WaterLily simulation. This note and its synthetic method
tests do not qualify Candidate C, mass conservation, no-penetration, or force
closure.

## Bounded diagnostic scope

The proposed follow-up reuses the existing 12 short-window arms unchanged:
four fixtures (`sphere`, `plate_1cell`, `plate_2cell`, `moving_ground_only`)
times the three existing modes (`candidate_c`, `grid_upstream`, `native`). The
solver/window remain the existing `FLOW_DIMS=(100,48,36)`, spacing 0.05 m,
and `tU/L=[0.10,0.25]`. This is only a bounded operator diagnostic; no new
shape, window, physical cutoff, or closure verdict is introduced here.

For the three body fixtures, the primary measured surface is the exact zero
set of the sampled Float32 canonical GridSDF's trilinear interpolant. The
analytic shape is kept as a separate control. Existing
`export_zero_surface(FieldBundle, ...)` provides a VTK contour seed; that seed
is not treated as the canonical zero set. Before area weights are formed,
subdivide the seed mesh at fixed levels 0, 1, and 2 and project all resulting
vertices to the canonical trilinear zero set. Use the exact gradient returned
by `GridSDFBody.sdf_value_gradient_at_world` for projection and geometric
normals. Project each three-point triangle-quadrature location separately for
field evaluation, but calculate its weight from the area of the already
projected triangle vertices. The new `SurfaceFluxQuadrature.jl` helper
implements this geometry-only portion and rejects any failed/non-finite
projection, zero gradient, degenerate triangle, or incomplete sample set.
It does not discard invalid points. Its fixed method parameters are a
`1e-10 m` projection tolerance and 20 iterations; these are numerical
projection validity checks against the 0.05 m flow-cell scale, not physical
acceptance limits. `|Q(level 2)-Q(level 1)|` is reported only as a refinement
indicator, not an upper error bound or response-resolution floor.

The future input-preparation step must stage the exact sampled Float32 `phi`,
its array order/origin/spacing and SHA, plus the VTK PLY seed SHA and parsed
vertex/face payload hashes. `trimesh` must validate the seed is watertight and
consistently wound, and record signed-volume orientation; the prep stage
rejects a failure and does not repair or silently flip it. Seed winding does
not set flux direction: the measured outward geometric normal is independently
set by the canonical trilinear gradient. Bind the run source manifest/runtime
identity, input-grid identity, mesh seed identity, refinement level and resulting projected
quadrature-point/weight hashes. The moving-ground rectangle is intentionally
open and is recorded as its own patch, not passed through the closed-body mesh
gate.

At each fully covered quadrature point, retain both the unit geometric normal
from the trilinear gradient and the operator normal returned by the actual
body's `WaterLily.measure`; never substitute one for the other. Sample the
staggered velocity with the pinned `WaterLily.interp(SVector(x_solver),
sim.flow.u)` path, after explicitly rejecting points outside its unclamped
interpolation domain. The velocity query is mapped from metres to solver
coordinates with the registered flow origin and 0.05 m scale. For a fixed
body, report signed relative flux
`rho*sum(w*((u-V) dot n_geom))`, absolute flux
`rho*sum(w*abs((u-V) dot n_geom))`, area-weighted RMS slip and maximum slip.
The geometric normal points from solid to fluid. Keep Candidate C operator
normal-based counterparts as separate diagnostics. The density is the
registered unit density in the existing solver contract; flux units are kg/s
and slip units are m/s. Keep quadrature locations, weights, both normals,
velocity, body velocity and sample coverage in the retained output.

The moving-ground-only fixture is a separate horizontal rectangle at the
registered ground height, bounded by solver `x=[2,97]`, `y=[2,45]`,
`z=8` (world `x=[-2.4,2.35] m`, `y=[-1.1,1.05] m`, `z=-0.5 m`). It is a
patch diagnostic only, not the whole ground boundary or a closed fluid
control volume. Its geometric normal is `+z`; the corresponding fluid-cutout
normal points `-z`. Ground velocity is `(+1,0,0)` in solver coordinates.
Report its body-relative normal flux and tangential velocity separately. The
full outer Cartesian boundary flux is a separate telescoping/domain
observable; it is not labeled fluid-region mass closure. No car/ground
control-volume force-closure residual or physical cutoff is registered by
this proposal.

For each arm, derive fixed fluid (`d_union>0`) and transition
(`0<d_union<=1 solver cell`) masks from the pre-step geometry and reuse the
same masks at every sample. Report post-boundary-condition divergence norms
on these masks separately. Also retain `sim.pois.levels[1].r` after each step
as WaterLily's cached finest-level **scaled-system solver residual**. Do not
call a fresh `residual!` on the live solver after the step: the solver's
pressure has been unscaled while its Poisson source remains scaled, and a
fresh residual would combine mismatched quantities. This cached residual and
the separately recomputed velocity divergence are diagnostics, not physical
mass-balance acceptance gates.

## Synthetic method controls and limits

`julia/CFDSDFWaterLily/test/test_surface_flux_quadrature.jl` exercises the
vertex-projection-before-area ordering on an exact plane, nested triangle
subdivision/projection on an analytic sphere, constant-velocity flux
integration, and fail-closed zero-gradient handling. These controls test only
the geometry/quadrature method. They use exact analytic controls and are not
reused as measurements of the sampled Float32 GridSDF or a WaterLily solve.

No limits are set for body-relative flux, divergence, the cached Poisson
residual, mass closure, or force closure. Any later acceptance thresholds and
how independently estimated surface, interpolation, temporal and solver
uncertainties relate to them must be reviewed and registered before a solver
measurement. All six qualification flags remain false.

## Current verification status

No simulation was constructed and no `sim_step!` was called for this
preparation. Commands/results and source hashes will be appended after the
method review and focused test run; no measurement artifacts exist.
