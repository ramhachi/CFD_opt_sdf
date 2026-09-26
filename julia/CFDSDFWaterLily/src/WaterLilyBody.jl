"""
WaterLilyBody — W2 bridge from the W1-qualified `GridSDF` adapter to the
WaterLily `AbstractBody` interface.

The body maps solver coordinates `x_solver` to canonical world coordinates
`x_world_m = world_origin_m + world_per_solver .* x_solver` (meters) and
returns the trilinear SDF value from `GridSDFBody` in solver units
(`d_m / world_per_solver`).  The normal is the normalized analytic gradient
of the same trilinear polynomial (`sdf_value_gradient_at_world`), not a
finite-difference stencil.  Body velocity is zero (static geometry).

The constant exterior extension of `GridSDF` is never reached by the BDIM
kernel support because the registered margin gate keeps the zero level at
least the run margin from the design-box faces (W1).
"""

using WaterLily
using .GridSDFBody

"""
    GridSDFWaterLilyBody(grid, world_origin_m, world_per_solver)

Static WaterLily body backed by the W1 `GridSDF` trilinear adapter.
"""
struct GridSDFWaterLilyBody{A,T} <: WaterLily.AbstractBody
    grid::GridSDF{A,T}
    world_origin_m::NTuple{3,Float64}
    world_per_solver::Float64
end

function canonical_point(body::GridSDFWaterLilyBody, x)
    s = body.world_per_solver
    o = body.world_origin_m
    return (o[1] + s * Float64(x[1]),
            o[2] + s * Float64(x[2]),
            o[3] + s * Float64(x[3]))
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
    (!isfinite(magnitude) || magnitude == 0.0) && return (d, zero(x), zero(x))
    components = (S(grad[1] / magnitude), S(grad[2] / magnitude), S(grad[3] / magnitude))
    n = x isa Array ? collect(components) : typeof(x)(components)
    return (d, n, zero(x))
end
