# Run: julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_candidate_c_body.jl
using Test, WaterLily

const ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
include(joinpath(ROOT, "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end
using .CFDSDFWaterLily.GridSDFBody

const DELTA = Float32(1.1444091796875e-4)
struct SpoofNormalFloorBody <: WaterLily.AbstractBody
    normal_floor::Float32
end

function fixture_grid()
    origin = (-1.0, -1.0, -1.0)
    h = (0.1, 0.1, 0.1)
    phi = Array{Float32}(undef, 21, 21, 21)
    for k in axes(phi, 3), j in axes(phi, 2), i in axes(phi, 1)
        x = origin[1] + (i - 1) * h[1]
        y = origin[2] + (j - 1) * h[2]
        z = origin[3] + (k - 1) * h[3]
        phi[i, j, k] = Float32(sqrt(x^2 + y^2 + z^2) - 0.3)
    end
    return GridSDF(phi; origin, h, outside_value=3.0, margin_m=0.15)
end

@testset "Candidate C composite body" begin
    grid = fixture_grid()
    candidate = CFDSDFWaterLily.NormalFloorWaterLilyBody(
        grid, (-1.0f0, -1.0f0, -1.0f0), 0.1f0, 0.25f0)
    ground = CFDSDFWaterLily.V16MovingGroundBody(-10f0, 1f0)
    body = CFDSDFWaterLily.CandidateCWaterLilyBody(candidate, ground)

    @test body.normal_floor == 0.25f0
    @test body.transition_width == DELTA
    @test WaterLily.measure(body, Float32[10, 10, 10], 0f0)[1] ≈ -3f0 atol=2e-6

    sim = WaterLily.Simulation((32, 24, 24),
        (i, x, t) -> i == 1 ? one(eltype(x)) : zero(eltype(x)), 20f0;
        U=1f0, ν=0.1f0, exitBC=true, body, T=Float32, mem=Array)
    @test all(isfinite, sim.flow.μ₀)
    @test all(isfinite, sim.flow.μ₁)
    @test all(isfinite, sim.flow.V)

    # Candidate C blends with the registered smooth half-cell activation.
    for (face, center) in ((0.5002f0, -0.002f0), (0.5002f0, 0.002f0),
                           (0.5f0, -0.002f0), (-0.7f0, 0.2f0))
        raw = WaterLily.μ₀(face, 1f0)
        weight = CFDSDFWaterLily.candidate_c_smoothstep((abs(face) - 0.5f0) / DELTA)
        mismatch = CFDSDFWaterLily.candidate_c_smoothstep((-sign(face) * center) / DELTA)
        expected = if weight > 0 && mismatch > 0
            alpha = weight * mismatch
            corrected = WaterLily.μ₀(copysign(abs(face), center), 1f0)
            muladd(alpha, corrected - raw, raw)
        else
            raw
        end
        @test CFDSDFWaterLily.candidate_c_mu0(face, center, DELTA, 1f0) == expected
    end
    @test CFDSDFWaterLily.candidate_c_mu0(0.5f0, -0.2f0, DELTA, 1f0) ==
          WaterLily.μ₀(0.5f0, 1f0)
    @test CFDSDFWaterLily.candidate_c_mu0(0.5f0 + DELTA/2, -2DELTA, DELTA, 1f0) ≈
          (WaterLily.μ₀(0.5f0 + DELTA/2, 1f0) +
           0.5f0 * (WaterLily.μ₀(-0.5f0 - DELTA/2, 1f0) -
                    WaterLily.μ₀(0.5f0 + DELTA/2, 1f0))) atol=1e-7
    @test_throws ArgumentError CFDSDFWaterLily.CandidateCWaterLilyBody(
        CFDSDFWaterLily.GridSDFWaterLilyBody(grid, (-1f0, -1f0, -1f0), 0.1f0), ground)
    @test_throws ArgumentError CFDSDFWaterLily.CandidateCWaterLilyBody(
        candidate; normal_floor=0.5f0)
    @test_throws ArgumentError CFDSDFWaterLily.CandidateCWaterLilyBody(
        candidate; transition_width=2DELTA)
    @test_throws ArgumentError CFDSDFWaterLily.CandidateCWaterLilyBody(
        SpoofNormalFloorBody(0.25f0))
    @test_throws ArgumentError CFDSDFWaterLily.CandidateCWaterLilyBody{typeof(candidate),Float32}(
        candidate, 0.25f0, 2DELTA)
end
