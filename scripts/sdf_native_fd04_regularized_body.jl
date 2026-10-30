# Diagnostic-only body for FD-04 (#36): identical to GridSDFWaterLilyBody except that the
# normal is n = g / max(|g|, TAU).  TAU is declared here, before any response is seen, inside
# the empty gradient band (1e-6, 0.25) measured on canonical v16.  The production bridge is
# not modified.  Expects `sdf_at_world`, `sdf_value_gradient_at_world` and `GridSDF` in scope.

const TAU = 0.1

struct RegularizedBody{A,T,S} <: WaterLily.AbstractBody
    grid::GridSDF{A,T}
    world_origin_m::NTuple{3,S}
    world_per_solver::S
end

function WaterLily.measure(body::RegularizedBody, x::AbstractVector{S}, t; fastd² = S(Inf)) where {S}
    s = body.world_per_solver
    o = body.world_origin_m
    x_m = (o[1] + s * x[1], o[2] + s * x[2], o[3] + s * x[3])
    d = S(sdf_at_world(body.grid, x_m) / s)
    d * d > fastd² && return (d, zero(x), zero(x))
    _, g = sdf_value_gradient_at_world(body.grid, x_m)
    m = max(sqrt(g[1] * g[1] + g[2] * g[2] + g[3] * g[3]), S(TAU))
    n = collect((S(g[1] / m), S(g[2] / m), S(g[3] / m)))
    return (d, n, zero(x))
end

