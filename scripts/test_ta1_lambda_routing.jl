# GRAD-TA1 Amendment 2: in WaterLily 1.8.0 the convective scheme reaches the solver ONLY through `Simulation(...; λ=λ)` (stored in `sim.flow.λ`);
# `sim_step!(sim; λ)` forwards kwargs to udf! only and ignores it.  CPU, small plain Float32 sim.
using WaterLily, Test

mutable struct Counting{F}
    f::F
    n::Int
end
(c::Counting)(u, v, w) = (c.n += 1; c.f(u, v, w))
struct Boom end
(::Boom)(u, v, w) = error("Boom called")

mksim(; kw...) = WaterLily.Simulation((16, 16), (1f0, 0f0), 8f0; ν=0.01f0, T=Float32, kw...)

@testset "lambda routing" begin
    c = Counting(WaterLily.quick, 0)
    sim = mksim(λ=c)                                   # constructor: reached
    @test sim.flow.λ === c
    sim_step!(sim); @test c.n > 0
    s2 = mksim()                                       # kwarg of sim_step!: NOT reached (default quick stays)
    @test s2.flow.λ === WaterLily.quick
    sim_step!(s2; λ=Boom())                            # would throw if routed
    @test s2.flow.λ === WaterLily.quick
    c2 = Counting(WaterLily.quick, 0)
    s3 = mksim(); sim_step!(s3; λ=c2); @test c2.n == 0
    @test_throws Exception sim_step!(mksim(λ=Boom()))  # the constructor route does reach it
end
