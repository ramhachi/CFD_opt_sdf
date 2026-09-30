"""
WaterLilyBody — W2 bridge from the W1-qualified `GridSDF` adapter to the
WaterLily `AbstractBody` interface.

The body maps solver coordinates `x_solver` to canonical world coordinates
`x_world_m = world_origin_m + world_per_solver .* x_solver` and returns the
trilinear SDF value from `GridSDFBody` in solver units
(`d_m / world_per_solver`).  The normal is the normalized analytic gradient
of the same trilinear polynomial (`sdf_value_gradient_at_world`), not a
finite-difference stencil.  Body velocity is zero (static geometry).

The arithmetic follows the constructed scalar type: a body constructed with
Float64 map fields uses the Float64 CPU path (W2a), while a body constructed
with Float32 fields over a device phi executes entirely in Float32 inside
CUDA kernels (W1g).  No type coercion happens in the measurement path, and
the measurement allocates nothing.

The constant exterior extension of `GridSDF` is never reached by the BDIM
kernel support because the registered margin gate keeps the zero level at
least the run margin from the design-box faces (W1); the margin gate remains
a CPU-side pre-launch check.
"""

using WaterLily
using .GridSDFBody

"""
    GridSDFWaterLilyBody(grid, world_origin_m, world_per_solver[, normal_floor])

Static WaterLily body backed by the W1 `GridSDF` trilinear adapter.  The map
field type (Float64 or Float32) selects the measurement arithmetic.

`normal_floor` (default 0) replaces the normal `g/|g|` by `g/max(|g|, normal_floor)`
(#37): where the trilinear gradient vanishes the normal is otherwise
discontinuous under any perturbation.  0 keeps the historical bridge exactly.
"""
struct GridSDFWaterLilyBody{A,T,S} <: WaterLily.AbstractBody
    grid::GridSDF{A,T}
    world_origin_m::NTuple{3,S}
    world_per_solver::S
    normal_floor::S
end

GridSDFWaterLilyBody(grid, world_origin_m, world_per_solver) =
    GridSDFWaterLilyBody(grid, world_origin_m, world_per_solver, zero(world_per_solver))

function canonical_point(body::GridSDFWaterLilyBody, x)
    s = body.world_per_solver
    o = body.world_origin_m
    return (o[1] + s * x[1],
            o[2] + s * x[2],
            o[3] + s * x[3])
end

function WaterLily.measure(
    body::GridSDFWaterLilyBody,
    x::AbstractVector{S},
    t;
    fastd² = S(Inf),
) where {S}
    x_m = canonical_point(body, x)
    d_m = sdf_at_world(body.grid, x_m)
    d = S(d_m / body.world_per_solver)
    d * d > fastd² && return (d, zero(x), zero(x))
    _, grad = sdf_value_gradient_at_world(body.grid, x_m)
    magnitude = sqrt(grad[1] * grad[1] + grad[2] * grad[2] + grad[3] * grad[3])
    (!isfinite(magnitude) || magnitude == zero(magnitude)) && return (d, zero(x), zero(x))
    magnitude = body.normal_floor > 0 ? max(magnitude, body.normal_floor) : magnitude
    components = (S(grad[1] / magnitude), S(grad[2] / magnitude), S(grad[3] / magnitude))
    n = x isa Array ? collect(components) : typeof(x)(components)
    return (d, n, zero(x))
end
