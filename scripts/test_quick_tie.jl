# GRAD-TA1 CPU tests of scripts/quick_tie.jl (plan Amendment 1, C6).  usage: julia --project=julia/CFDSDFWaterLily scripts/test_quick_tie.jl
# (the 20-step sim bit-identity is the bridge's own preflight: tests/test_grad_ta1_quick_tie.py runs it with TA1_PREFLIGHT_ONLY=1 on CPU).
using WaterLily, Test, Random
const FD = WaterLily.ForwardDiff
Base.include(WaterLily, joinpath(@__DIR__, "quick_tie.jl"))
const QT = WaterLily.QuickTie
const quick = WaterLily.quick
dual(V, v, t) = FD.Dual{Nothing,V,1}(V(v), FD.Partials((V(t),)))
bits(x::Float32) = reinterpret(UInt32, x)
bits(x::Float64) = reinterpret(UInt64, x)

@testset "QuickTie" begin
    @testset "value is bit-identical to quick (ties, signed zeros, NaN, Inf, random)" begin
        q = QT(1f-5)
        rng = MersenneTwister(1)
        triples = Tuple{Float32,Float32,Float32}[]
        specials = Float32[0f0, -0f0, 1f0, NaN32, Inf32, -Inf32]
        for u in specials, c in specials, d in specials
            push!(triples, (u, c, d))
        end
        for _ in 1:100_000
            push!(triples, ntuple(_ -> Float32(rand(rng, -8:8)) / 4f0, 3))      # coarse grid: many exact ties
            push!(triples, ntuple(_ -> randn(rng, Float32), 3))
            push!(triples, ntuple(_ -> 1f0 + 4f-6 * randn(rng, Float32), 3))    # everything within a few tau
        end
        bad = 0
        for (u, c, d) in triples
            tu, tc, td = randn(rng, Float32, 3)
            m = q(dual(Float32, u, tu), dual(Float32, c, tc), dual(Float32, d, td))
            r = quick(dual(Float32, u, tu), dual(Float32, c, tc), dual(Float32, d, td))
            bits(FD.value(m)) == bits(FD.value(r)) || (bad += 1)
            bits(q(u, c, d)) == bits(quick(u, c, d)) || (bad += 1)             # value-only arguments
        end
        @test bad == 0
    end

    @testset "away from ties the partial is the selected branch's (= quick's)" begin
        q = QT(1f-5)
        rng = MersenneTwister(2)
        checked = 0
        for _ in 1:50_000
            u, c, d = randn(rng, Float32, 3); tu, tc, td = randn(rng, Float32, 3)
            vC = 10c - 9u; vA = (5c + 2d - u) / 6
            mi = sort([vC, c, d])[2]
            gap = minimum(abs, (vC - c, vC - d, c - d, vA - c, vA - mi, c - mi))
            gap > 1f-3 || continue
            m = q(dual(Float32, u, tu), dual(Float32, c, tc), dual(Float32, d, td))
            r = quick(dual(Float32, u, tu), dual(Float32, c, tc), dual(Float32, d, td))
            @test FD.partials(m, 1) ≈ FD.partials(r, 1) rtol = 2f-5 atol = 1f-5
            checked += 1
        end
        @test checked > 1000
    end

    @testset "at a 2-way tie the partial is the centered finite difference" begin
        q = QT(1e-5)
        tu, tc, td = 0.3, -0.7, 1.1
        # A = (5c+2d-u)/6 equals the inner median d; c lies on one side (below / above), the candidate C = 10c-9u is far
        for (u, c, d) in ((0.5, 1.0, 1.125), (1.5, 1.0, 0.875))
            @test (5c + 2d - u) / 6 == d && sort([10c - 9u, c, d])[2] == d
            m = q(dual(Float64, u, tu), dual(Float64, c, tc), dual(Float64, d, td))
            h = 1e-4
            cfd = (quick(u + h * tu, c + h * tc, d + h * td) - quick(u - h * tu, c - h * tc, d - h * td)) / 2h
            @test FD.partials(m, 1) ≈ cfd atol = 1e-9
            pA, pd = (5tc + 2td - tu) / 6, td
            @test FD.partials(m, 1) ≈ (pA + pd) / 2
            r = quick(dual(Float64, u, tu), dual(Float64, c, tc), dual(Float64, d, td))
            @test abs(FD.partials(r, 1) - cfd) > 0.5               # the selected-branch partial is a one-sided slope: the dispatch matters here
        end
    end

    @testset "the Dual method is dispatched; mixed arguments and width > 1 are errors" begin
        D1 = FD.Dual{Nothing,Float32,1}
        q = QT(1f-5)
        sig = string(which(q, Tuple{D1,D1,D1}).sig)
        @test occursin("Dual", sig)
        @test_throws ErrorException q(dual(Float32, 1, 1), 1f0, 2f0)                                     # Dual with plain floats
        @test_throws ErrorException q(dual(Float32, 1, 1), dual(Float32, 2, 1), dual(Float64, 3, 1))     # mixed Dual types
        D2 = FD.Dual{Nothing,Float32,2}
        w = D2(1f0, FD.Partials((1f0, 2f0)))
        @test_throws ErrorException q(w, w, w)                                                            # width 2
        @test q(1f0, 2f0, 3f0) === quick(1f0, 2f0, 3f0)                                                   # all plain floats: the original limiter
    end
end
