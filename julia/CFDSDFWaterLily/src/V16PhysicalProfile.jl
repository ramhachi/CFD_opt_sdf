"""
V16PhysicalProfile — WaterLily adapter for the registered v16 laminar profile.

The geometry and dimensional scales follow the registered OpenFOAM profile.
The outer boundary discretization does not: WaterLily 1.8.0 applies normal
velocity Dirichlet and tangential zero-Neumann ghost conditions, with an
optional convective exit in +x, and has no per-patch freestream-pressure
boundary argument. The adapter therefore records an explicit native-boundary
approximation and must not be described as an equivalent OpenFOAM profile or
as a physical qualification.
"""

using WaterLily
using .GridSDFBody: GridSDF

const V16_PROFILE_CELL_DIMS = (100, 48, 36)
const V16_PROFILE_POINT_SHAPE = (61, 33, 25)
const V16_CANONICAL_SDF_ORIGIN_M = (-1.0, -0.8, -0.6)
const V16_PROFILE_FLOW_ORIGIN_M = (-2.5, -1.2, -0.9)
const V16_PROFILE_FLOW_UPPER_M = (2.5, 1.2, 0.9)
const V16_PROFILE_SPACING_M = 0.05
const V16_PROFILE_FREESTREAM_MPS = (1.0, 0.0, 0.0)
const V16_PROFILE_DENSITY_KG_M3 = 1.0
const V16_PROFILE_DYNAMIC_VISCOSITY_PA_S = 0.01
const V16_PROFILE_REFERENCE_LENGTH_M = 0.8
const V16_PROFILE_REFERENCE_AREA_M2 = 0.64
const V16_PROFILE_REYNOLDS = 80.0
const V16_PROFILE_SOLVER_LENGTH = V16_PROFILE_REFERENCE_LENGTH_M / V16_PROFILE_SPACING_M
const V16_PROFILE_SOLVER_TIME_UNIT_S = V16_PROFILE_SPACING_M / V16_PROFILE_FREESTREAM_MPS[1]
const V16_PROFILE_SOLVER_U = 1.0
const V16_PROFILE_SOLVER_VISCOSITY =
    (V16_PROFILE_DYNAMIC_VISCOSITY_PA_S / V16_PROFILE_DENSITY_KG_M3) *
    V16_PROFILE_SOLVER_TIME_UNIT_S / V16_PROFILE_SPACING_M^2
const V16_PROFILE_GROUND_VELOCITY_SOLVER = (1.0, 0.0, 0.0)

"""
    V16MovingGroundBody(z_plane, velocity_x) <: WaterLily.AbstractBody

Planar half-space representing the profile's bottom wall. Fluid has positive
signed distance (`x[3] > z_plane`); the solid occupies the lower half-space.
The plane is stationary in shape and carries the registered +x wall velocity
in solver units, equivalent to +1 m/s under the adapter's space/time scales.
"""
struct V16MovingGroundBody{T<:Real} <: WaterLily.AbstractBody
    z_plane::T
    velocity_x::T
end

function WaterLily.measure(
    body::V16MovingGroundBody,
    x::AbstractVector{T},
    t;
    fastd² = T(Inf),
) where {T<:Real}
    d = x[3] - T(body.z_plane)
    d * d > fastd² && return (d, zero(x), zero(x))
    n = x .* zero(T) .+ (zero(T), zero(T), one(T))
    velocity = x .* zero(T) .+ (T(body.velocity_x), zero(T), zero(T))
    return (d, n, velocity)
end

"""Native WaterLily inflow and side/top normal velocity prescription."""
v16_native_far_field_uBC(i, x, t) = i == 1 ? one(eltype(x)) : zero(eltype(x))

"""
    v16_physical_profile_bodies(grid::GridSDF; T=Float32)

Return the candidate body for force integration, the moving ground, and their
union for the flow solver. `grid` must be the CPU-gated canonical v16 SDF;
device copies are derived only after this constructor has accepted it.
"""
function v16_physical_profile_bodies(grid::GridSDF; T = Float32,
                                     flow_origin_m = V16_PROFILE_FLOW_ORIGIN_M,
                                     point_shape = V16_PROFILE_POINT_SHAPE,
                                     sdf_spacing_m = V16_PROFILE_SPACING_M)
    # The design-lattice shape/spacing are canonical-state identity (v16 by default);
    # the flow spacing and solver map stay V16_PROFILE_SPACING_M.
    grid.shape == Tuple(point_shape) ||
        throw(ArgumentError("canonical SDF point shape drift: $(grid.shape)"))
    # DeviceGridSDF stores map fields as Float32. Compare at that declared
    # precision so the registered Float64 origin survives the intentional
    # CPU -> CUDA representation without a false identity failure.
    Tuple(Float32.(grid.origin)) == Tuple(Float32.(V16_CANONICAL_SDF_ORIGIN_M)) ||
        throw(ArgumentError("v16 SDF origin drift: $(grid.origin)"))
    Tuple(Float32.(grid.h)) == Tuple(Float32.((sdf_spacing_m, sdf_spacing_m, sdf_spacing_m))) ||
        throw(ArgumentError("v16 SDF spacing drift: $(grid.h)"))

    candidate = GridSDFWaterLilyBody(
        grid,
        T.(flow_origin_m),
        T(V16_PROFILE_SPACING_M),
    )
    ground = V16MovingGroundBody(T(0), T(V16_PROFILE_GROUND_VELOCITY_SOLVER[1]))
    return (candidate = candidate, ground = ground, combined = candidate + ground)
end

"""
    build_v16_physical_profile_simulation(bodies; T=Float32, mem=Array)

    Build the registered 100x48x36, Re=80 first-primal fixture. The +x maximum
uses WaterLily's convective exit. The side and top faces have its native
zero-normal-velocity / tangential-zero-Neumann treatment; these are a declared
finite-box approximation to the source profile's freestream patches.
"""
function build_v16_physical_profile_simulation(bodies; T = Float32, mem = Array)
    return WaterLily.Simulation(
        V16_PROFILE_CELL_DIMS,
        v16_native_far_field_uBC,
        T(V16_PROFILE_SOLVER_LENGTH);
        U = T(V16_PROFILE_SOLVER_U),
        ν = T(V16_PROFILE_SOLVER_VISCOSITY),
        exitBC = true,
        body = bodies.combined,
        T = T,
        mem = mem,
    )
end

"""Machine-readable statement of mapped and non-equivalent profile semantics."""
v16_physical_profile_adapter_contract() = (
    source_profile = "stage_v_v16_project_matched_re_laminar_moving_ground_far_field_v2",
    solver = "WaterLily 1.8.0 BDIM on uniform Cartesian grid",
    geometry = "canonical v16 GridSDF candidate plus a translating bottom half-space",
    flow_cell_dims = V16_PROFILE_CELL_DIMS,
    flow_origin_m = V16_PROFILE_FLOW_ORIGIN_M,
    flow_upper_m = V16_PROFILE_FLOW_UPPER_M,
    canonical_sdf_origin_m = V16_CANONICAL_SDF_ORIGIN_M,
    ground_velocity_mps = V16_PROFILE_FREESTREAM_MPS,
    native_uBC_reference_velocity_mps = V16_PROFILE_FREESTREAM_MPS,
    solver_time_unit_s = V16_PROFILE_SOLVER_TIME_UNIT_S,
    solver_viscosity = V16_PROFILE_SOLVER_VISCOSITY,
    x_max_boundary = "WaterLily convective exit",
    side_top_normal_velocity = "zero",
    side_top_tangential_condition = "zero-Neumann",
    pressure_boundary = "WaterLily projection pressure; no per-patch freestreamPressure input",
    source_profile_equivalent = false,
    physical_profile_qualified = false,
)
