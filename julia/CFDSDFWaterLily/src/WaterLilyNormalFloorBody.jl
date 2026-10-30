"""
WaterLilyNormalFloorBody (#37, FD-06) — `GridSDFWaterLilyBody` with the normal
`g / max(|g|, normal_floor)` instead of `g / |g|`.

Where the trilinear gradient vanishes (source faces lying on lattice planes) the
normalised normal flips under any perturbation; flooring |g| keeps the normal a
continuous function of phi.  Everything else (value, coordinate map, zero body
velocity, allocation-free measure) is identical to `GridSDFWaterLilyBody`.  The
historical `WaterLilyBody.jl` is deliberately untouched so registered contracts
that pin its hash stay valid; include this file only where the floor is wanted.
Included into the `CFDSDFWaterLily` module scope (after `WaterLilyBody.jl`).
"""

using WaterLily
using .GridSDFBody

struct NormalFloorWaterLilyBody{A,T,S} <: WaterLily.AbstractBody
    grid::GridSDF{A,T}
    world_origin_m::NTuple{3,S}
    world_per_solver::S
    normal_floor::S
end

function WaterLily.measure(
    body::NormalFloorWaterLilyBody,
    x::AbstractVector{S},
    t;
    fastd² = S(Inf),
) where {S}
    s = body.world_per_solver
    o = body.world_origin_m
    x_m = (o[1] + s * x[1], o[2] + s * x[2], o[3] + s * x[3])
    d = S(sdf_at_world(body.grid, x_m) / s)
    d * d > fastd² && return (d, zero(x), zero(x))
    _, grad = sdf_value_gradient_at_world(body.grid, x_m)
    magnitude = sqrt(grad[1] * grad[1] + grad[2] * grad[2] + grad[3] * grad[3])
    (!isfinite(magnitude) || magnitude == zero(magnitude)) && return (d, zero(x), zero(x))
    magnitude = max(magnitude, body.normal_floor)
    components = (S(grad[1] / magnitude), S(grad[2] / magnitude), S(grad[3] / magnitude))
    n = x isa Array ? collect(components) : typeof(x)(components)
    return (d, n, zero(x))
end
