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
projection, zero gradient, non-finite triangle or incomplete sample set.
For a closed body only, an exactly zero-area projected triangle can have
zero measure after exact-coordinate vertex identification. No positive-area
face is discarded by tolerance. All remaining oriented edges must have
exactly two oppositely directed incident faces; otherwise coverage rejects.
Every removed exact-zero face and vertex mapping is retained at every level.
Open ground patches do not use this quotient. Its fixed method parameters are a
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
same masks at every sample. Allocate these at the actual pressure-array
shape `(102,50,38) = FLOW_DIMS + 2`, including false ghost entries; use
`inside(p)` indices `2:(FLOW_DIMS+1)` and pressure locations `I-1.5`.
The original geometry-only attempt used a cropped mask at `FLOW_DIMS` and
is preserved under its original source snapshot; it is not a full fluid mask
and is not reused as the new measurement mask. Report post-boundary-condition divergence norms
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
preparation. Initial geometry-only staging is preserved in
`docs/evidence/candidate_c_round8_geometry_prep_attempt_001.json` and its
source/raw snapshot directory. The sphere VTK seed's 866 faces include 50
exactly zero-area faces after projection. Parent exact-coordinate coverage
audit retains all 816 positive-area faces, merges 435 vertices to 410 exact
coordinates, and confirms a closed consistently wound quotient. No coordinate
shift, finite-area cutoff or shape change is used. This is numerical-method
evidence, not a physical geometry or CFD qualification.

`scripts/candidate_c_surface_flux_round8.jl` is the new **unregistered** short
CPU measurement source. It copies the immutable Round7 primitive solver
definitions without editing Round7, measures canonical geometric versus actual
operator normals, independently records ground patches and fixed-mask
divergence, and reads the cached scaled-system solver residual without
mutating the primal solver. It stores aggregate histories and final point
fields for host recomputation. Float32 interpolation queries and their
component shifts are checked before calling the pinned staggered interpolator
so clamping cannot silently change a query. This source is not execution
authorization: geometry/source inventory, immutable plan, independent host
checks and parent preregistration still precede any solver measurement.

All arms sample the same registered canonical trilinear surface for a common
diagnostic comparison. For the native arm that surface can differ from the
native analytic body's own zero set. Its flux therefore describes the native
flow evaluated on the canonical comparison surface; it is not a native-wall
no-penetration measurement. Native-versus-grid differences include the geometry
sampling difference. Grid-upstream versus C holds that sampling and floor fixed.
