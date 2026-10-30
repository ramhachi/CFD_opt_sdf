# SDF-01 host-side raw-vector regression for the trilinear GridSDF normal.
# Run with: julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_sdf01_trilinear_normal.jl
# This one-cell fixture isolates interpolation and normalization; it does not
# qualify coordinate mapping, boundary behavior, or CUDA execution.

using Printf

include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody
using WaterLily

const ORIGIN = (0.25, -0.5, 0.125)
const SPACING = (0.5, 0.25, 0.125)
const FRACTION = (0.25, 0.375, 0.625)

# A general trilinear polynomial is reproduced exactly by its eight corner
# samples, so its world-space gradient is an independent analytic reference.
phi_exact(u, v, w) = 0.125 + 1.5u - 0.75v + 0.5w + 0.25u*v -
    0.125u*w + 0.375v*w + 0.0625u*v*w

function gradient_exact(u, v, w)
    du = 1.5 + 0.25v - 0.125w + 0.0625v*w
    dv = -0.75 + 0.25u + 0.375w + 0.0625u*w
    dw = 0.5 - 0.125u + 0.375v + 0.0625u*v
    return (du / SPACING[1], dv / SPACING[2], dw / SPACING[3])
end

function run_case(::Type{T}) where {T<:AbstractFloat}
    origin = ntuple(i -> T(ORIGIN[i]), 3)
    spacing = ntuple(i -> T(SPACING[i]), 3)
    phi = T[phi_exact(i - 1, j - 1, k - 1) for i in 1:2, j in 1:2, k in 1:2]
    # Raw constructor is intentional: this synthetic scalar field is an
    # interpolation fixture, not a physical SDF subject to the W1 margin gate.
    grid = GridSDF(phi, origin, spacing, (2, 2, 2), T(3), zero(T))

    q64 = ntuple(i -> ORIGIN[i] + FRACTION[i] * SPACING[i], 3)
    q = ntuple(i -> T(q64[i]), 3)
    u = (Float64(q[1]) - ORIGIN[1]) / SPACING[1]
    v = (Float64(q[2]) - ORIGIN[2]) / SPACING[2]
    w = (Float64(q[3]) - ORIGIN[3]) / SPACING[3]
    expected_value = phi_exact(u, v, w)
    expected_gradient = gradient_exact(u, v, w)
    expected_magnitude = sqrt(sum(abs2, expected_gradient))
    expected_normal = ntuple(i -> expected_gradient[i] / expected_magnitude, 3)

    value, gradient = sdf_value_gradient_at_world(grid, q)
    body = CFDSDFWaterLily.GridSDFWaterLilyBody(
        grid, (zero(T), zero(T), zero(T)), one(T))
    distance, normal, _ = WaterLily.measure(
        body, WaterLily.SVector{3,T}(q), zero(T); fastd²=T(Inf))
    magnitude = sqrt(sum(abs2, gradient))
    tolerance = T === Float64 ? 1e-12 : 2e-6
    errors = (
        abs(Float64(value) - expected_value),
        maximum(abs(Float64(gradient[i]) - expected_gradient[i]) for i in 1:3),
        abs(Float64(distance) - expected_value),
        maximum(abs(Float64(normal[i]) - expected_normal[i]) for i in 1:3),
        abs(Float64(magnitude) - expected_magnitude),
    )

    println("SDF01_RAW_VECTOR dtype=$(T) q_world=$(repr(q)) value=$(repr(value)) " *
        "raw_gradient=$(repr(gradient)) gradient_magnitude=$(repr(magnitude)) " *
        "normal=$(repr(normal)) expected_value=$(repr(expected_value)) " *
        "expected_raw_gradient=$(repr(expected_gradient)) " *
        "expected_normal=$(repr(expected_normal)) errors=$(repr(errors))")
    @assert maximum(errors) <= tolerance
    @assert abs(Float64(sqrt(sum(abs2, normal))) - 1.0) <= tolerance
    @printf("RESULT sdf01_trilinear_normal_%s PASS maxerr=%.3e\n", T, maximum(errors))
end

run_case(Float64)
run_case(Float32)
