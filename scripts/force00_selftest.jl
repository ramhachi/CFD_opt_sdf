#!/usr/bin/env julia
# CPU software checks only; no GPU solver or engineering gate is run here.
using Test
using LinearAlgebra: norm, tr
using WaterLily
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily: nds_telescoping, pressure_force_nds, viscous_force_nds,
    force_on_body_nds, control_volume_terms, control_volume_force, force_readouts,
    validate_force_box

function sphere_sim(::Val{D}, ::Type{T}=Float64; solver=false) where {D,T}
    center = WaterLily.SVector{D,T}(ntuple(i -> T(16) + T((0.3, 0.7, -0.4)[i]), D))
    body = AutoBody((x, t) -> sqrt(sum(abs2, x - center)) - T(4))
    dims = ntuple(_ -> 32, D)
    uBC = ntuple(i -> i == 1 ? one(T) : zero(T), D)
    solver && return Simulation(dims, uBC, T(8); body, T, ν=T(0.2))
    flow = WaterLily.Flow(dims, uBC; T, ν=T(0.2))
    WaterLily.measure!(flow, body)
    return (; flow, body)
end

@testset "stored mu0 telescoping, off-grid 2D/3D" begin
    for D in (2, 3), T in (Float32, Float64)
        sim = sphere_sim(Val(D), T)
        sim.flow.p .= one(T)
        sim.flow.u .= zero(T)
        # measure! fills only the narrow band: far interior stays zero and
        # far exterior stays one (excluding solver boundary-condition faces).
        @test all(sim.flow.μ₀[CartesianIndex(ntuple(_ -> 17, D)), :] .== 0)
        @test all(sim.flow.μ₀[CartesianIndex(ntuple(_ -> 7, D)), :] .== 1)
        n = nds_telescoping(sim)
        @test all(I -> all(i -> n[I, i] ==
            Float64(sim.flow.μ₀[I + WaterLily.δ(i, I), i]) - Float64(sim.flow.μ₀[I, i]),
            1:D), WaterLily.inside(sim.flow.p))
        @test norm(pressure_force_nds(sim)) <= 1e-12
        @test iszero(norm(viscous_force_nds(sim)))
        @test norm(force_on_body_nds(sim)) <= 1e-12
        # A linear pressure probes the sign and rejects artificial domain-wall
        # terms that a unit-pressure closure alone would conceal.
        WaterLily.apply!(x -> T(0.125) * x[1], sim.flow.p)
        @test pressure_force_nds(sim)[1] > 0
    end
end

@testset "Cartesian CV affine-field momentum balance" begin
    for D in (2, 3)
        sim = sphere_sim(Val(D))
        box = ntuple(_ -> 7:27, D)
        A = [0.02 * (i + 2j) for i in 1:D, j in 1:D]
        A[D, D] -= tr(A) # divergence-free affine velocity
        b = [0.2 * i for i in 1:D]
        accel = [0.03 * (-1)^i for i in 1:D]
        gradp = [0.04 * i for i in 1:D]
        dt = 0.125
        WaterLily.apply!((i, x) -> (A * x)[i] + b[i], sim.flow.u)
        WaterLily.apply!((i, x) -> (A * x)[i] + b[i] - dt * accel[i], sim.flow.u⁰)
        WaterLily.apply!(x -> sum(gradp .* x) + 3.0, sim.flow.p)
        push!(sim.flow.Δt, 0.25) # previous, not proposed, time step is used
        sim.flow.Δt[end - 1] = dt
        terms = control_volume_terms(sim, box)
        lengths = length.(box)
        volume = prod(lengths)
        center = [0.5 * (first(r) - 2 + last(r) - 1) for r in box]
        velocity_at_center = A * center + b
        @test terms.advection ≈ -volume * (A * velocity_at_center) atol=1e-9 rtol=1e-12
        @test terms.pressure ≈ -volume * gradp atol=1e-9 rtol=1e-12
        @test terms.viscous ≈ zeros(D) atol=1e-10
        @test terms.storage ≈ -volume * accel atol=1e-9 rtol=1e-12
        @test control_volume_force(sim, box) == terms.total
        @test terms.total ≈ terms.advection + terms.pressure + terms.viscous + terms.storage
        # A pressure gauge shift cannot change a closed-box force.
        sim.flow.p .+= 5.0
        @test control_volume_force(sim, box) ≈ terms.total atol=1e-9
        # A nonzero manufactured viscous balance rejects an implementation
        # that silently drops the viscous term (affine strain sums to zero).
        coefficients = [0.01 * i for i in 1:D]
        WaterLily.apply!((i, x) -> coefficients[i] * x[i]^2, sim.flow.u)
        sim.flow.u⁰ .= sim.flow.u
        sim.flow.p .= 0
        viscous = control_volume_terms(sim, box).viscous
        @test viscous ≈ 4 * sim.flow.ν * volume * coefficients atol=1e-10 rtol=1e-12
        @test_throws ArgumentError control_volume_force(sim, ntuple(_ -> 2:27, D))
        @test_throws ArgumentError control_volume_force(sim, ntuple(_ -> 13:22, D))
        fresh = sphere_sim(Val(D))
        @test_throws ArgumentError control_volume_force(fresh, box)
    end
end

@testset "legacy bit identity and observational readouts" begin
    for D in (2, 3)
        sim = sphere_sim(Val(D), Float32; solver=true)
        control = deepcopy(sim)
        sim_step!(sim)
        sim_step!(control)
        box = ntuple(_ -> 7:27, D)
        snapshot = copy(sim.flow.f)
        expected = -(WaterLily.total_force(sim))
        sim.flow.f .= snapshot
        result = force_readouts(sim, box)
        @test reinterpret(UInt8, result.cur) == reinterpret(UInt8, expected)
        @test sim.flow.f == snapshot
        @test result.nds == force_on_body_nds(sim; box)
        @test result.cv == control_volume_force(sim, box)
        @test validate_force_box(sim, box) == box
        @test_throws ArgumentError force_readouts(sim, ntuple(_ -> 4:8, D))
        @test sim.flow.f == snapshot
        sim_step!(sim)
        sim_step!(control)
        @test sim.flow.u == control.flow.u
        @test sim.flow.p == control.flow.p
        @test sim.flow.μ₀ == control.flow.μ₀
    end
end

@testset "candidate enclosure and ground exclusion" begin
    candidate_sim = sphere_sim(Val(2))
    candidate = candidate_sim.body
    ground = AutoBody((x, t) -> x[2] - 1.0)
    scene = candidate + ground
    flow = deepcopy(candidate_sim.flow)
    WaterLily.measure!(flow, scene)
    sim = (; flow, body=scene)
    box = (7:27, 7:27) # bottom face at5: fourcellsabovegroundat1
    push!(flow.Δt, 0.25)
    WaterLily.apply!(x -> 0.1 * x[1] + 0.2 * x[2], flow.p)
    @test validate_force_box(sim, box; body=candidate) == box
    # Passing the fused candidate+ground as the target cannot pass enclosure.
    @test_throws ArgumentError validate_force_box(sim, box)
    @test_throws ArgumentError validate_force_box(sim, (4:8, 4:8); body=candidate)
    @test_throws ArgumentError validate_force_box(sim, box; body=WaterLily.NoBody())
    candidate_sim.flow.p .= flow.p
    @test pressure_force_nds(sim; box) == pressure_force_nds(candidate_sim; box)
    expected = -(WaterLily.pressure_force(flow, candidate)) +
               -(WaterLily.viscous_force(flow, candidate))
    snapshot = copy(flow.f)
    result = force_readouts(sim, box; body=candidate)
    @test reinterpret(UInt8, result.cur) == reinterpret(UInt8, expected)
    @test flow.f == snapshot
    @test result == force_readouts(sim, box; body=candidate, validate_box=false)
end

println("FORCE00_SELFTEST_PASS (CPU only)")
