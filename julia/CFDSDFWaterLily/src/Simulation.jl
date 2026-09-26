"""
Simulation — registered W2a flow-past-sphere fixtures.

Two fixtures solve the same physical sphere on the same flow grid:

- `analytic_sphere_body()`: WaterLily `AutoBody` with the exact sphere SDF in
  solver coordinates;
- `grid_sdf_sphere_body()`: the W1 `GridSDF` trilinear adapter fed with the
  exact sphere sampled to Float32 on the registered canonical lattice, mapped
  to solver coordinates by the registered affine map.

Solver coordinates are WaterLily grid units (1 cell = 1 unit).  The
registered physical anchor is the sphere diameter D = 1.0 m, so the affine
map scale is D / (2 R_solver) m per unit.  The flow-grid resolution is an
independent variable; W2a runs the 16 cells/D rung.
"""

using .GridSDFBody

const SPHERE_RADIUS_M = 0.5
const SPHERE_CENTER_M = (0.25, 0.0, 0.0)

const FLOW_DIMS = (96, 64, 64)
const SOLVER_CENTER = (32.0, 32.0, 32.0)
const SOLVER_RADIUS = 8.0
const FREESTREAM = 1.0
const REYNOLDS = 100.0
const SOLVER_VISCOSITY = FREESTREAM * 2 * SOLVER_RADIUS / REYNOLDS
const WORLD_ORIGIN_M = (
    SPHERE_CENTER_M[1] - (SPHERE_RADIUS_M / SOLVER_RADIUS) * SOLVER_CENTER[1],
    SPHERE_CENTER_M[2] - (SPHERE_RADIUS_M / SOLVER_RADIUS) * SOLVER_CENTER[2],
    SPHERE_CENTER_M[3] - (SPHERE_RADIUS_M / SOLVER_RADIUS) * SOLVER_CENTER[3],
)
const WORLD_PER_SOLVER = SPHERE_RADIUS_M / SOLVER_RADIUS

const SPHERE_PHI_ORIGIN = (-1.0, -0.8, -0.7)
const SPHERE_PHI_SPACING = 0.05
const SPHERE_PHI_SHAPE = (61, 33, 29)
const OUTSIDE_VALUE_M = 3.0
const RUN_MARGIN_M = 0.15

"""
    sphere_phi_fixture() -> GridSDF

Registered synthetic fixture: exact Float64 sphere SDF on the canonical
lattice (`SPHERE_PHI_*`), cast to Float32 exactly as the genesis state
stores phi, built through the fail-closed gate constructor at the registered
run margin.  The zero level keeps 0.2 m to the z faces.
"""
function sphere_phi_fixture()
    o = SPHERE_PHI_ORIGIN
    h = SPHERE_PHI_SPACING
    n = SPHERE_PHI_SHAPE
    c = SPHERE_CENTER_M
    r = SPHERE_RADIUS_M
    phi = Array{Float32,3}(undef, n)
    @inbounds for k in 1:n[3], j in 1:n[2], i in 1:n[1]
        x = o[1] + (i - 1) * h
        y = o[2] + (j - 1) * h
        z = o[3] + (k - 1) * h
        phi[i, j, k] = Float32(
            sqrt((x - c[1])^2 + (y - c[2])^2 + (z - c[3])^2) - r
        )
    end
    return GridSDF(phi;
        origin = o,
        h = (h, h, h),
        outside_value = OUTSIDE_VALUE_M,
        margin_m = RUN_MARGIN_M,
    )
end

"""
    analytic_sphere_body(; T=Float32) -> WaterLily.AutoBody

Exact sphere SDF in solver coordinates (no interpolation).
"""
function analytic_sphere_body(; T = Float32)
    c = T.(SOLVER_CENTER)
    r = T(SOLVER_RADIUS)
    return WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- c)) - r)
end

"""
    grid_sdf_sphere_body() -> GridSDFWaterLilyBody

The sampled sphere through the W1 adapter and the registered affine map.
"""
function grid_sdf_sphere_body()
    return GridSDFWaterLilyBody(sphere_phi_fixture(), WORLD_ORIGIN_M, WORLD_PER_SOLVER)
end

"""
    build_sphere_sim(body; T=Float32, mem=Array) -> WaterLily.Simulation

Registered flow-past-sphere simulation: uniform inflow `FREESTREAM` along
+x, `REYNOLDS` based on the solver diameter, initial condition equal to the
boundary condition, length scale equal to the solver diameter so
`sim_time` is in `tU/D` units.
"""
function build_sphere_sim(body; T = Float32, mem = Array)
    u = T(FREESTREAM)
    ν = T(SOLVER_VISCOSITY)
    ubc = (u, zero(T), zero(T))
    return WaterLily.Simulation(
        FLOW_DIMS,
        ubc,
        T(2 * SOLVER_RADIUS);
        ν = ν,
        body = body,
        T = T,
        mem = mem,
    )
end

"""
    sphere_reference_area() -> Float64

Frontal area of the solver sphere in solver units squared.
"""
sphere_reference_area() = π * SOLVER_RADIUS^2
