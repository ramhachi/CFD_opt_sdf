# GRAD-00 software checks only; no flow solve or GPU import.
# julia --project=julia/CFDSDFWaterLily scripts/grad00_selftest.jl
using WaterLily, Test
const FD = WaterLily.ForwardDiff
Base.include(WaterLily, joinpath(@__DIR__, "quick_nobound.jl"))

@testset "GRAD-00 convection schemes" begin
    @test isdefined(WaterLily, :cds)
    @test isdefined(WaterLily, :vanLeer)
    for T in (Float32, Float64)
        @testset "$T" begin
            # Exact binary values: outer interpolation selected in both schemes.
            @test WaterLily.quick_nobound(T(1), T(2), T(3)) === T(2.5)
            @test WaterLily.quick(T(1), T(2), T(3)) === T(2.5)
            # QUICK's inner median clips at 10c-9u=10; #358 removes that bound.
            @test WaterLily.quick(T(0), T(1), T(32)) === T(10)
            @test WaterLily.quick_nobound(T(0), T(1), T(32)) === T(11.5)
            DT = FD.Dual{Nothing,T,1}
            dual(v, p) = DT(T(v), FD.Partials((T(p),)))
            for triple in ((1, 2, 3), (0, 1, 32), (1, 1, 1), (0, 0, 0))
                args = ntuple(i -> dual(triple[i], i), 3)
                out = WaterLily.quick_nobound(args...)
                @test isfinite(FD.value(out))
                @test isfinite(FD.partials(out, 1))
                @test FD.value(out) === WaterLily.quick_nobound(T.(triple)...)
            end
        end
    end
end
