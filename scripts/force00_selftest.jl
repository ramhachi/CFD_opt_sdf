#!/usr/bin/env julia
# CPU software checks only; no GPU solver or engineering gate is run here.
using Test
using LinearAlgebra: norm, tr
using WaterLily
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
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
        box = ntuple(_ -> 7:27, D)
        @test validate_force_box(sim, box) == box
        sim.flow.p .= one(T)
        sim.flow.u .= zero(T)
        # measure! fills only the narrow band: far interior stays zero and
        # far exterior stays one (excluding solver boundary-condition faces).
        @test all(sim.flow.μ₀[CartesianIndex(ntuple(_ -> 17, D)), :] .== 0)
        @test all(sim.flow.μ₀[CartesianIndex(ntuple(_ -> 7, D)), :] .== 1)
        @test all(I -> sim.flow.σ[I] > T(3) ?
            all(isone, sim.flow.μ₀[I, :]) : sim.flow.σ[I] < T(-3) ?
            all(iszero, sim.flow.μ₀[I, :]) : true,
            WaterLily.inside(sim.flow.p; buff=2))
        n = nds_telescoping(sim, box)
        @test all(I -> all(i -> n[I, i] ==
            Float64(sim.flow.μ₀[I + WaterLily.δ(i, I), i]) - Float64(sim.flow.μ₀[I, i]),
            1:D), CartesianIndices(box))
        @test all(I -> I in CartesianIndices(box) || all(iszero, n[I, :]),
            CartesianIndices(sim.flow.p))
        @test norm(pressure_force_nds(sim; box)) <= 1e-12
        @test iszero(norm(viscous_force_nds(sim; box)))
        @test norm(force_on_body_nds(sim; box)) <= 1e-12
        # For q = 1-μ₀ with q=0 on both end faces, summation by parts gives
        # Σ p[I](μ₀[I+δᵢ,i]-μ₀[I,i]) = ∂ᵢp Σ q[I,i]. Binary coefficients
        # make the prescribed pressure exact even in Float32.
        gradp = [T(2.0^(i - 4)) for i in 1:D]
        WaterLily.apply!(x -> sum(gradp .* x) + T(2), sim.flow.p)
        expected = [Float64(gradp[i]) * sum(I ->
            1.0 - Float64(sim.flow.μ₀[I, i]), CartesianIndices(box)) for i in 1:D]
        @test pressure_force_nds(sim; box) ≈ expected atol=1e-12 rtol=1e-14
        @test force_on_body_nds(sim; box) ≈ -expected atol=1e-12 rtol=1e-14
    end
end

@testset "explicit box and exact boundary moment preconditions" begin
    sim = sphere_sim(Val(2))
    box = (7:27, 7:27)
    @test_throws MethodError nds_telescoping(sim)
    @test_throws UndefKeywordError pressure_force_nds(sim)
    @test_throws UndefKeywordError viscous_force_nds(sim)
    @test_throws UndefKeywordError force_on_body_nds(sim)
    @test_throws MethodError force_readouts(sim)
    @test_throws ArgumentError nds_telescoping(sim, nothing)
    @test_throws ArgumentError pressure_force_nds(sim; box=nothing)
    @test_throws ArgumentError viscous_force_nds(sim; box=nothing)
    @test_throws ArgumentError force_on_body_nds(sim; box=nothing)
    @test_throws ArgumentError control_volume_force(sim, nothing)
    @test_throws ArgumentError force_readouts(sim, nothing)
    for axis in 1:2, side in (-1, 1)
        I = CartesianIndex(ntuple(i -> i == axis ?
            (side < 0 ? first(box[i]) : last(box[i]) + 1) : first(box[i]), 2))
        @test sim.flow.μ₀[I, axis] == 1.0
        # The geometry remains valid; only the stored closure precondition
        # changes, by one ulp. A distance-based proxy would miss this.
        sim.flow.μ₀[I, axis] = prevfloat(1.0)
        @test_throws ArgumentError validate_force_box(sim, box)
        sim.flow.μ₀[I, axis] = 1.0
    end
    @test validate_force_box(sim, box) == box
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
    box = (7:27, 7:27) # Bottom face at 5: four cells above the ground at 1.
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

@testset "solved cylinder nested-box diagnostic (descriptive)" begin
    # Re100, D16 CPU fixture. This probes the solver's end-of-step pressure
    # and u⁰ time levels; it is not a project-parent or benchmark qualification.
    diameter = 16f0
    center = WaterLily.SA[48.3f0, 48.7f0]
    body = AutoBody((x, t) -> sqrt(sum(abs2, x - center)) - diameter / 2)
    sim = Simulation((192, 96), (1f0, 0f0), diameter;
        ν=diameter / 100, body, T=Float32)
    boxes = [(32:66, 32:66), (24:90, 20:78), (16:140, 12:86)]
    foreach(box -> validate_force_box(sim, box), boxes)
    for _ in 1:1500
        sim_step!(sim)
    end
    function sample()
        first_box = force_readouts(sim, boxes[1]; validate_box=false)
        cv = hcat(first_box.cv,
            (control_volume_force(sim, box) for box in boxes[2:end])...)
        return (; cur=first_box.cur, nds=first_box.nds, cv)
    end
    previous = sample()
    initial_time = previous_time = Float64(WaterLily.time(sim.flow))
    cur_integral, nds_integral, cv_integral = zeros(2), zeros(2), zeros(2, 3)
    lift_difference_integral = 0.0
    for step in 1:800
        sim_step!(sim)
        step % 8 == 0 || continue
        current_time = Float64(WaterLily.time(sim.flow))
        current = sample()
        dt = current_time - previous_time
        cur_integral .+= dt / 2 .* (previous.cur + current.cur)
        nds_integral .+= dt / 2 .* (previous.nds + current.nds)
        cv_integral .+= dt / 2 .* (previous.cv + current.cv)
        lift_difference_integral += dt / 2 *
            ((previous.cv[2, 1] - previous.cv[2, 3])^2 +
             (current.cv[2, 1] - current.cv[2, 3])^2)
        previous, previous_time = current, current_time
    end
    window = previous_time - initial_time
    cur_mean, nds_mean, cv_mean = cur_integral / window,
        nds_integral / window, cv_integral / window
    @test all(isfinite, vcat(cur_mean, nds_mean, vec(cv_mean)))
    @test window > 0
    # Record spread, without inventing a precision threshold for instantaneous
    # box agreement. Storage and pressure time-level offsets average differently.
    drag_means = cv_mean[1, :]
    relative_spread = (maximum(drag_means) - minimum(drag_means)) /
        abs(sum(drag_means) / length(drag_means))
    println("FORCE00_CYLINDER_BOX_DIAGNOSTIC ", (; diameter_cells=16, reynolds=100,
        warmup_steps=1500, sampled_steps=800, sample_interval_steps=8,
        window_solver_time=window, boxes, cur_mean, nds_mean,
        cv_means=collect(eachcol(cv_mean)), cv_drag_relative_spread=relative_spread,
        cv_vs_cur_relative=drag_means ./ cur_mean[1] .- 1,
        instantaneous_box1_box3_lift_rms=sqrt(lift_difference_integral / window)))
end

println("FORCE00_SELFTEST_PASS (CPU only)")
