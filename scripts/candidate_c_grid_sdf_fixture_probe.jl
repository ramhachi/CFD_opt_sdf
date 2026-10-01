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
history_path = output_path * ".history.csv"
manifest_output_path = output_path * ".sha256"
claim_path = output_path * ".claim"
any(ispath, (output_path, history_path, manifest_output_path, claim_path)) &&
    error("refusing to overwrite or concurrently claim an existing output artifact")
plan_bytes = read(plan_path)
plan_sha = bytes2hex(sha256(plan_bytes))
plan_text = String(copy(plan_bytes))
sha(bytes) = bytes2hex(sha256(bytes))
field(name) = begin
    m = match(Regex("\\\"" * name * "\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\""), plan_text)
    m === nothing && error("plan is missing hash field: $name")
    m.captures[1]
end
plan_sha_path = replace(plan_path, r"\.json$" => ".sha256")
isfile(plan_sha_path) || error("plan SHA-256 sidecar is missing")
plan_sha == first(split(read(plan_sha_path, String))) || error("plan hash mismatch")
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
const N_PER_SOLVER = FLOW_SPACING^2 * FLOW_U^2
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
        grid, ntuple(i -> Float32(FLOW_ORIGIN[i]), 3), Float32(FLOW_SPACING), 0.25f0)
    return base
end

function build_sim(fixture, mode, grid)
    ground = CFDSDFWaterLily.V16MovingGroundBody(GROUND_Z_SOLVER, GROUND_U_SOLVER)
    candidate = candidate_body(grid)
    body = if mode === :native
        native_body(fixture) + ground
    elseif mode === :grid_upstream
        candidate + ground
    elseif mode === :candidate_c
        CFDSDFWaterLily.CandidateCWaterLilyBody(candidate, ground)
    else
        error("unknown mode $mode")
    end
    return WaterLily.Simulation(FLOW_DIMS,
        CFDSDFWaterLily.v16_native_far_field_uBC, FLOW_L;
        U=FLOW_U, ν=FLOW_NU, exitBC=true, body, T=Float32, mem=Array)
end

function flux_at_x(u, ix)
    return sum(Float64, view(u, ix, :, :, 1))
end

function interpolate(a, b, t, t0, t1)
    w = (t - t0) / (t1 - t0)
    return a .+ w .* (b .- a)
end

function exact_window_mean(samples, key)
    first(samples).t <= SAMPLE_BEGIN <= last(samples).t || error("window start lacks bracket samples")
    first(samples).t <= T_END <= last(samples).t || error("window end lacks bracket samples")
    function at(target)
        idx = findfirst(i -> samples[i].t <= target <= samples[i+1].t, 1:length(samples)-1)
        idx === nothing && error("missing interpolation bracket at t=$target")
        a, b = samples[idx], samples[idx+1]
        return interpolate(getproperty(a, key), getproperty(b, key), target, a.t, b.t)
    end
    selected = [s for s in samples if SAMPLE_BEGIN < s.t < T_END]
    times = vcat(SAMPLE_BEGIN, [s.t for s in selected], T_END)
    values = vcat([at(SAMPLE_BEGIN)], [getproperty(s, key) for s in selected], [at(T_END)])
    integral = zero.(values[1])
    for i in 1:length(times)-1
        integral = integral .+ (times[i+1] - times[i]) .* (values[i] .+ values[i+1]) ./ 2
    end
    return integral ./ (T_END - SAMPLE_BEGIN), length(selected)
end

function record_sample!(samples, history_io, fixture, mode, sim, step)
    all(isfinite, sim.flow.u) || error("non-finite velocity field at step=$step")
    all(isfinite, sim.flow.p) || error("non-finite pressure field at step=$step")
    pressure = CFDSDFWaterLily.pressure_force_on_body(sim) .* N_PER_SOLVER
    viscous = CFDSDFWaterLily.viscous_force_on_body(sim) .* N_PER_SOLVER
    total = CFDSDFWaterLily.force_on_body(sim) .* N_PER_SOLVER
    closure = maximum(abs.(pressure .+ viscous .- total))
    inlet = flux_at_x(sim.flow.u, first(axes(sim.flow.u, 1)))
    outlet = flux_at_x(sim.flow.u, last(axes(sim.flow.u, 1)))
    t = Float64(sim_time(sim))
    row = (; t, pressure, viscous, total, inlet_flux=inlet, outlet_flux=outlet, closure)
    push!(samples, row)
    println(history_io, join((fixture, mode, step, t, pressure..., viscous..., total...,
        closure, inlet, outlet, all(isfinite, sim.flow.u), all(isfinite, sim.flow.p)), ","))
    flush(history_io)
    closure <= 1e-12 || error("pressure/viscous/total force closure exceeded 1e-12 N")
    return nothing
end

function integrate_case(fixture, mode, grid, history_io)
    sim = build_sim(fixture, mode, grid)
    sim_step!(sim) # compile and initialize solver path
    samples = NamedTuple[]
    steps = 1
    record_sample!(samples, history_io, fixture.id, mode, sim, steps)
    while sim_time(sim) < T_END
        sim_step!(sim)
        steps += 1
        record_sample!(samples, history_io, fixture.id, mode, sim, steps)
    end
    total_n, count = exact_window_mean(samples, :total)
    pressure_n, _ = exact_window_mean(samples, :pressure)
    viscous_n, _ = exact_window_mean(samples, :viscous)
    inlet, _ = exact_window_mean(samples, :inlet_flux)
    outlet, _ = exact_window_mean(samples, :outlet_flux)
    closure = maximum(s.closure for s in samples)
    closure <= 1e-12 || error("pressure/viscous/total force closure exceeded 1e-12 N")
    return (; steps, reached=Float64(sim_time(sim)), count,
        force_n=Tuple(total_n), pressure_n=Tuple(pressure_n), viscous_n=Tuple(viscous_n), closure_n=closure,
        inlet_flux=Float64(inlet), outlet_flux=Float64(outlet), flux_difference=Float64(outlet-inlet),
        finite_u=all(isfinite, sim.flow.u), finite_p=all(isfinite, sim.flow.p))
end

function csvrow(io, fixture, mode, grid_sha, result)
    println(io, join((fixture, mode, grid_sha, result.steps, result.reached, result.count,
        result.force_n..., result.pressure_n..., result.viscous_n..., result.closure_n,
        result.inlet_flux, result.outlet_flux, result.flux_difference,
        result.finite_u, result.finite_p), ","))
end

mkpath(dirname(abspath(output_path)))
# Julia's open modes do not include Python-style "x". An atomic mkdir is the
# exclusive claim; keep it as provenance so repeated runs cannot overwrite data.
mkdir(claim_path)
open(history_path, "w") do history_io
    println(history_io, "fixture,mode,step,t_u_over_l,pfx_n,pfy_n,pfz_n,vfx_n,vfy_n,vfz_n,fx_n,fy_n,fz_n,force_closure_n,inlet_flux_solver,outlet_flux_solver,finite_u,finite_p")
    flush(history_io)
    open(output_path, "w") do io
        println(io, "fixture,mode,phi_sha256,steps,t_reached,window_samples,fx_n,fy_n,fz_n,pfx_n,pfy_n,pfz_n,vfx_n,vfy_n,vfz_n,force_closure_n,inlet_flux_solver,outlet_flux_solver,flux_difference_solver,finite_u,finite_p")
        flush(io)
        for fixture in FIXTURES
            grid, grid_sha = sample_grid(fixture)
            for mode in (:native, :grid_upstream, :candidate_c)
                result = integrate_case(fixture, mode, grid, history_io)
                csvrow(io, fixture.id, mode, grid_sha, result)
                flush(io)
            end
        end
    end
end
manifest = string(
    bytes2hex(sha256(read(plan_path))), "  ", abspath(plan_path), "\n",
    bytes2hex(sha256(read(@__FILE__))), "  ", abspath(@__FILE__), "\n",
    bytes2hex(sha256(read(manifest_path))), "  ", abspath(manifest_path), "\n",
    bytes2hex(sha256(read(output_path))), "  ", abspath(output_path), "\n",
    bytes2hex(sha256(read(history_path))), "  ", abspath(history_path), "\n")
open(manifest_output_path, "w") do io
    write(io, manifest)
end
println("CANDIDATE_C_FIXTURE_PROBE_DONE ", output_path)
