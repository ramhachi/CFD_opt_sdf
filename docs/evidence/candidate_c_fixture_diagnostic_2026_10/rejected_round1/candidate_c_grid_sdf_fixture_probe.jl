# Bounded CPU diagnostic for the composite Candidate C operator.
# Usage: julia -t auto --project=julia/CFDSDFWaterLily \
#   scripts/candidate_c_grid_sdf_fixture_probe.jl <immutable-plan.json> <output.csv>
# This is a short diagnostic, not W3-C/W4-C or a physics qualification.
using SHA, WaterLily

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end

length(ARGS) == 2 || error("usage: candidate_c_grid_sdf_fixture_probe.jl <plan.json> <output.csv>")
plan_path, output_path = ARGS
isfile(plan_path) || error("immutable diagnostic plan is missing")
!ispath(output_path) || error("refusing to overwrite existing output")
plan_bytes = read(plan_path)
plan_text = String(plan_bytes)
sha(bytes) = bytes2hex(sha256(bytes))
field(name) = begin
    m = match(Regex("\\\"" * name * "\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\""), plan_text)
    m === nothing && error("plan is missing hash field: $name")
    m.captures[1]
end
plan_sha_path = replace(plan_path, r"\.json$" => ".sha256")
isfile(plan_sha_path) || error("plan SHA-256 sidecar is missing")
sha(plan_bytes) == first(split(read(plan_sha_path, String))) || error("plan hash mismatch")
sha(read(@__FILE__)) == field("runner_sha256") || error("diagnostic runner hash mismatch")
manifest_path = joinpath(dirname(plan_path), "runner_sources.sha256")
isfile(manifest_path) || error("runner source manifest is missing")
sha(read(manifest_path)) == field("source_manifest_sha256") || error("source manifest hash mismatch")
for line in eachline(manifest_path)
    expected, source = split(line, "  "; limit=2)
    path = startswith(source, "external:") ? source[10:end] : joinpath(ROOT, source)
    isfile(path) || error("registered source is missing: $source")
    sha(read(path)) == expected || error("registered source hash mismatch: $source")
end

const FLOW_DIMS = (100, 48, 36)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOW_SPACING = 0.05
const FLOW_L = 16.0
const FLOW_U = 1.0
const FLOW_NU = 0.2
const T_END = 0.25
const SAMPLE_BEGIN = 0.10
const N_PER_SOLVER = 1 / 900
const GROUND_Z_SOLVER = 8f0
const GROUND_U_SOLVER = 1f0
const SDF_ORIGIN = (-1.0, -0.8, -0.6)
const SDF_SPACING = (0.05, 0.05, 0.05)
const SDF_SHAPE = (61, 33, 25)
const BODY_CENTER = (0.0, 0.0, -0.2)
const FIXTURES = (
    (id="sphere", shape=:sphere, extents=(0.25, 0.25, 0.25)),
    (id="plate_1cell", shape=:box, extents=(0.25, 0.025, 0.25)),
    (id="plate_2cell", shape=:box, extents=(0.25, 0.05, 0.25)),
    (id="moving_ground_only", shape=:none, extents=(0.0, 0.0, 0.0)),
)

analytic_phi(shape, extents, p) = if shape === :none
    3.0
elseif shape === :sphere
    sqrt(sum((p[i] - BODY_CENTER[i])^2 for i in 1:3)) - extents[1]
else
    q = ntuple(i -> abs(p[i] - BODY_CENTER[i]) - extents[i], 3)
    sqrt(sum(max(q[i], 0.0)^2 for i in 1:3)) + min(maximum(q), 0.0)
end

function sample_grid(fixture)
    phi = Array{Float32}(undef, SDF_SHAPE)
    for k in 1:SDF_SHAPE[3], j in 1:SDF_SHAPE[2], i in 1:SDF_SHAPE[1]
        p = ntuple(d -> SDF_ORIGIN[d] + (d == 1 ? i - 1 : d == 2 ? j - 1 : k - 1) * SDF_SPACING[d], 3)
        phi[i, j, k] = Float32(analytic_phi(fixture.shape, fixture.extents, p))
    end
    grid = GridSDF(phi; origin=SDF_ORIGIN, h=SDF_SPACING,
                   outside_value=3.0, margin_m=0.15)
    return grid, bytes2hex(sha256(reinterpret(UInt8, vec(phi))))
end

function solver_center()
    ntuple(i -> Float32((BODY_CENTER[i] - FLOW_ORIGIN[i]) / FLOW_SPACING), 3)
end

function native_body(fixture)
    fixture.shape === :none && return WaterLily.NoBody()
    c = solver_center()
    local_sdf = if fixture.shape === :sphere
        r = Float32(fixture.extents[1] / FLOW_SPACING)
        (x, t) -> sqrt(sum((x[i] - c[i])^2 for i in 1:3)) - r
    else
        e = ntuple(i -> Float32(fixture.extents[i] / FLOW_SPACING), 3)
        (x, t) -> begin
            q = ntuple(i -> abs(x[i] - c[i]) - e[i], 3)
            sqrt(sum(max(q[i], 0f0)^2 for i in 1:3)) + min(maximum(q), 0f0)
        end
    end
    return WaterLily.AutoBody(local_sdf)
end

function candidate_body(grid)
    base = CFDSDFWaterLily.NormalFloorWaterLilyBody(
        grid, Float32.(FLOW_ORIGIN), Float32(FLOW_SPACING), 0.25f0)
    return base
end

function build_sim(fixture, mode, grid)
    ground = CFDSDFWaterLily.V16MovingGroundBody(GROUND_Z_SOLVER, GROUND_U_SOLVER)
    body = mode === :native ? native_body(fixture) + ground :
        CFDSDFWaterLily.CandidateCWaterLilyBody(candidate_body(grid), ground)
    return WaterLily.Simulation(FLOW_DIMS,
        CFDSDFWaterLily.v16_native_far_field_uBC, FLOW_L;
        U=FLOW_U, ν=FLOW_NU, exitBC=true, body, T=Float32, mem=Array)
end

function flux_at_x(u, ix)
    return sum(Float64, view(u, ix, :, :, 1))
end

function integrate_case(fixture, mode, grid)
    sim = build_sim(fixture, mode, grid)
    sim_step!(sim) # compile and initialize solver path
    samples = NamedTuple[]
    steps = 1
    while sim_time(sim) < T_END
        sim_step!(sim)
        steps += 1
        sim_time(sim) >= SAMPLE_BEGIN || continue
        pressure = CFDSDFWaterLily.pressure_force_on_body(sim) .* N_PER_SOLVER
        viscous = CFDSDFWaterLily.viscous_force_on_body(sim) .* N_PER_SOLVER
        total = CFDSDFWaterLily.force_on_body(sim) .* N_PER_SOLVER
        push!(samples, (; t=Float64(sim_time(sim)), pressure, viscous, total,
            inlet_flux=flux_at_x(sim.flow.u, first(axes(sim.flow.u, 1))),
            outlet_flux=flux_at_x(sim.flow.u, last(axes(sim.flow.u, 1)))))
    end
    isempty(samples) && error("no force samples in diagnostic window")
    closure = maximum(maximum(abs.(s.pressure .+ s.viscous .- s.total)) for s in samples)
    inlet = sum(s.inlet_flux for s in samples) / length(samples)
    outlet = sum(s.outlet_flux for s in samples) / length(samples)
    means(v) = ntuple(i -> sum(s.total[i] for s in samples) / length(samples), 3)
    pmean = ntuple(i -> sum(s.pressure[i] for s in samples) / length(samples), 3)
    vmean = ntuple(i -> sum(s.viscous[i] for s in samples) / length(samples), 3)
    return (; steps, reached=Float64(sim_time(sim)), count=length(samples),
        force_n=means(1), pressure_n=pmean, viscous_n=vmean, closure_n=closure,
        inlet_flux=inlet, outlet_flux=outlet, flux_difference=outlet-inlet,
        finite_u=all(isfinite, sim.flow.u), finite_p=all(isfinite, sim.flow.p))
end

function csvrow(io, fixture, mode, grid_sha, result)
    println(io, join((fixture, mode, grid_sha, result.steps, result.reached, result.count,
        result.force_n..., result.pressure_n..., result.viscous_n..., result.closure_n,
        result.inlet_flux, result.outlet_flux, result.flux_difference,
        result.finite_u, result.finite_p), ","))
end

mkpath(dirname(abspath(output_path)))
open(output_path, "x") do io
    println(io, "fixture,mode,phi_sha256,steps,t_reached,samples,fx_n,fy_n,fz_n,pfx_n,pfy_n,pfz_n,vfx_n,vfy_n,vfz_n,force_closure_n,inlet_flux_solver,outlet_flux_solver,flux_difference_solver,finite_u,finite_p")
    for fixture in FIXTURES
        grid, grid_sha = sample_grid(fixture)
        for mode in (:native, :candidate_c)
            result = integrate_case(fixture, mode, grid)
            csvrow(io, fixture.id, mode, grid_sha, result)
            flush(io)
        end
    end
end
println("CANDIDATE_C_FIXTURE_PROBE_DONE ", output_path)
