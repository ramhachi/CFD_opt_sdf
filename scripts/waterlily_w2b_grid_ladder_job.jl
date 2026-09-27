# W2b: analytic and sampled-sphere primal across the registered flow-grid ladder.
#
# Usage on the registered CUDA/T4 runtime:
#   julia --project=<T4 env> scripts/waterlily_w2b_grid_ladder_job.jl \
#         <params.jl> <output_dir>

using SHA
using CUDA

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using WaterLily

length(ARGS) == 2 || error("usage: waterlily_w2b_grid_ladder_job.jl <params.jl> <output_dir>")
params_path, output_dir = ARGS
include(params_path)

Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
using .CFDSDFWaterLily.DeviceGridSDF

const EXPECTED_CASE_IDS = (
    "analytic_16", "gridsdf_16", "analytic_24", "gridsdf_24", "analytic_32", "gridsdf_32",
)
const PHI_SHA256 = "393d5d7897885d71cda0902129a4aa3db561c59b1a85e8e221d55ce19fca4161"

function assert_case(p)
    n = Int(p.cells_per_diameter)
    @assert n in (16, 24, 32) "unregistered flow-grid rung"
    @assert p.case_id == "$(p.mode)_$(n)" "case id/mode/rung mismatch"
    @assert p.mode in ("analytic", "gridsdf") "unregistered geometry mode"
    @assert Tuple(p.flow_dims) == (6n, 4n, 4n) "dimensionless flow domain drift"
    @assert Tuple(Float64.(p.solver_center)) == (2n, 2n, 2n) "sphere center drift"
    @assert Float64(p.solver_radius) == n / 2 "sphere radius drift"
    @assert Float64(p.u_inf) == 1.0 "freestream drift"
    @assert Float64(p.reynolds) == 100.0 "Reynolds number drift"
    @assert Float64(p.viscosity) == n / 100 "viscosity does not preserve Re_D"
    @assert Tuple(Float64.(p.world_origin_m)) == (-1.75, -2.0, -2.0) "world origin drift"
    @assert Float64(p.world_per_solver) == 1 / n "world/solver scale drift"
    @assert Float64(p.t_end) == 60.0 && Float64(p.burn_in) == 40.0 "time window drift"
    @assert Int(p.sample_every) == 4 "force sampling interval drift"
    return nothing
end

map(p -> assert_case(p), W2B_CASES)
Tuple(p.case_id for p in W2B_CASES) == EXPECTED_CASE_IDS || error("case inventory/order drift")

function json_number(x)
    x isa Bool && return x ? "true" : "false"
    x isa Integer && return string(x)
    return string(Float64(x))
end
json_or_null(x) = x === nothing ? "null" : json_number(x)
json_array(values) = "[" * join(json_number.(values), ",") * "]"

mean_of(rows, i) = sum(row[i] for row in rows) / length(rows)

function time_weighted_mean(rows, column, fallback)
    length(rows) >= 2 || return fallback
    numerator = 0.0
    denominator = 0.0
    for index in 1:(length(rows) - 1)
        dt = rows[index + 1][2] - rows[index][2]
        numerator += 0.5 * (rows[index][column] + rows[index + 1][column]) * dt
        denominator += dt
    end
    denominator > 0.0 ? numerator / denominator : fallback
end

function build_body(p)
    if p.mode == "analytic"
        center = Float32.(p.solver_center)
        radius = Float32(p.solver_radius)
        body = WaterLily.AutoBody((x, t) -> sqrt(sum(abs2, x .- center)) - radius)
        return body, nothing, nothing, nothing, "", ""
    end

    canonical = CFDSDFWaterLily.sphere_phi_fixture()
    measured_margin = zero_level_margin_m(canonical.phi, canonical.origin, canonical.h)
    phi_sha = canonical_phi_sha256(canonical.phi)
    phi_sha == PHI_SHA256 || error("canonical W2b phi hash drift")
    owner = device_copy(canonical)
    roundtrip_sha = device_roundtrip_sha(owner)
    roundtrip_sha == PHI_SHA256 || error("W2b device round-trip hash mismatch")
    grid = kernel_grid(owner)
    body = CFDSDFWaterLily.GridSDFWaterLilyBody(
        grid, Float32.(p.world_origin_m), Float32(p.world_per_solver))
    return body, owner, measured_margin, canonical.margin_m, phi_sha, roundtrip_sha
end

function run_simulation(body, p)
    u = Float32(p.u_inf)
    diameter = Float32(2 * p.solver_radius)
    viscosity = Float32(p.viscosity)
    ubc = (u, 0.0f0, 0.0f0)
    sim = WaterLily.Simulation(
        Tuple(Int.(p.flow_dims)), ubc, diameter;
        ν = viscosity, body = body, T = Float32, mem = CuArray,
    )

    history = Vector{NTuple{7,Float64}}()
    warm_started = time()
    sim_step!(sim)
    first_step_seconds = time() - warm_started
    step = 1
    peak_vram = CUDA.used_memory()
    started = time()
    while sim_time(sim) < p.t_end
        sim_step!(sim)
        step += 1
        if step % p.sample_every == 0
            fp = CFDSDFWaterLily.pressure_force_on_body(sim)
            fv = CFDSDFWaterLily.viscous_force_on_body(sim)
            push!(history, (
                Float64(step), Float64(sim_time(sim)),
                fp[1] + fv[1], fp[2] + fv[2], fp[3] + fv[3], fp[1], fv[1],
            ))
        end
        if step % 50 == 0
            peak_vram = max(peak_vram, CUDA.used_memory())
        end
    end
    wall_seconds = time() - started
    peak_vram = max(peak_vram, CUDA.used_memory())
    finite_u = all(isfinite, sim.flow.u)
    finite_p = all(isfinite, sim.flow.p)
    window = [row for row in history if row[2] >= p.burn_in && row[2] <= p.t_end]
    isempty(window) && error("$(p.case_id): empty measurement window")
    middle = 0.5 * (p.burn_in + p.t_end)
    first_half = [row for row in window if row[2] < middle]
    second_half = [row for row in window if row[2] >= middle]
    (isempty(first_half) || isempty(second_half)) && error("$(p.case_id): empty stationarity half-window")

    mean_drag = mean_of(window, 3)
    mean_lift = mean_of(window, 4)
    mean_side = mean_of(window, 5)
    time_weighted_drag = time_weighted_mean(window, 3, mean_drag)
    area = π * Float64(p.solver_radius)^2
    return (
        history = history,
        steps = step,
        wall_seconds = wall_seconds,
        first_step_seconds = first_step_seconds,
        t_end_reached = Float64(sim_time(sim)),
        finite_u = finite_u,
        finite_p = finite_p,
        finite_forces = all(row -> all(isfinite, row), history),
        window_mean_drag = mean_drag,
        window_mean_lift = mean_lift,
        window_mean_side = mean_side,
        time_weighted_mean_drag = time_weighted_drag,
        time_weighted_mean_lift = time_weighted_mean(window, 4, mean_lift),
        time_weighted_mean_side = time_weighted_mean(window, 5, mean_side),
        first_half_mean_drag = mean_of(first_half, 3),
        second_half_mean_drag = mean_of(second_half, 3),
        cd = mean_drag / (0.5 * Float64(p.u_inf)^2 * area),
        time_weighted_cd = time_weighted_drag / (0.5 * Float64(p.u_inf)^2 * area),
        peak_vram_bytes = peak_vram,
    )
end

function run_case(p, fingerprint, vram_total)
    body, device_owner, measured_margin, margin_gate, phi_sha, roundtrip_sha = build_body(p)
    result = run_simulation(body, p)
    csv_path = joinpath(output_dir, p.case_id * ".forces.csv")
    open(csv_path, "w") do io
        println(io, "step,t_ud,drag,lift,side,pressure_drag,viscous_drag")
        for row in result.history
            println(io, join(row, ","))
        end
    end
    csv_sha = bytes2hex(sha256(read(csv_path)))
    summary = string(
        "{",
        "\"case_id\":\"", p.case_id, "\",",
        "\"mode\":\"", p.mode, "\",",
        "\"cells_per_diameter\":", Int(p.cells_per_diameter), ",",
        "\"flow_dims\":", json_array(p.flow_dims), ",",
        "\"solver_center\":", json_array(p.solver_center), ",",
        "\"solver_radius\":", json_number(p.solver_radius), ",",
        "\"reynolds\":", json_number(p.reynolds), ",",
        "\"viscosity\":", json_number(p.viscosity), ",",
        "\"world_origin_m\":", json_array(p.world_origin_m), ",",
        "\"world_per_solver\":", json_number(p.world_per_solver), ",",
        "\"julia_version\":\"", fingerprint.julia_version, "\",",
        "\"julia_threads\":", fingerprint.julia_threads, ",",
        "\"waterlily_version\":\"", fingerprint.waterlily_version, "\",",
        "\"waterlily_backend\":\"", fingerprint.waterlily_backend, "\",",
        "\"cuda_jl_version\":\"", string(pkgversion(CUDA)), "\",",
        "\"gpu_name\":\"", CUDA.name(CUDA.device()), "\",",
        "\"phi_margin_m\":", json_or_null(measured_margin), ",",
        "\"phi_margin_gate_m\":", json_or_null(margin_gate), ",",
        "\"phi_sha256\":\"", phi_sha, "\",",
        "\"device_roundtrip_sha256\":\"", roundtrip_sha, "\",",
        "\"t_end_target\":", json_number(p.t_end), ",",
        "\"t_end_reached\":", json_number(result.t_end_reached), ",",
        "\"steps\":", result.steps, ",",
        "\"wall_seconds\":", json_number(result.wall_seconds), ",",
        "\"first_step_seconds\":", json_number(result.first_step_seconds), ",",
        "\"ms_per_step\":", json_number(1000 * result.wall_seconds / max(result.steps - 1, 1)), ",",
        "\"force_samples\":", length(result.history), ",",
        "\"finite_u\":", result.finite_u, ",",
        "\"finite_p\":", result.finite_p, ",",
        "\"finite_forces\":", result.finite_forces, ",",
        "\"window_mean_drag\":", json_number(result.window_mean_drag), ",",
        "\"window_mean_lift\":", json_number(result.window_mean_lift), ",",
        "\"window_mean_side\":", json_number(result.window_mean_side), ",",
        "\"time_weighted_mean_drag\":", json_number(result.time_weighted_mean_drag), ",",
        "\"time_weighted_mean_lift\":", json_number(result.time_weighted_mean_lift), ",",
        "\"time_weighted_mean_side\":", json_number(result.time_weighted_mean_side), ",",
        "\"first_half_mean_drag\":", json_number(result.first_half_mean_drag), ",",
        "\"second_half_mean_drag\":", json_number(result.second_half_mean_drag), ",",
        "\"cd\":", json_number(result.cd), ",",
        "\"time_weighted_cd\":", json_number(result.time_weighted_cd), ",",
        "\"peak_vram_bytes\":", result.peak_vram_bytes, ",",
        "\"vram_total_bytes\":", vram_total, ",",
        "\"csv_sha256\":\"", csv_sha, "\",",
        "\"final_force\":", json_array((result.history[end][3], result.history[end][4],
                                             result.history[end][5], result.history[end][6],
                                             result.history[end][7])),
        "}",
    )
    summary_path = joinpath(output_dir, p.case_id * ".summary.json")
    write(summary_path, summary * "\n")
    println("W2B_CASE_DONE ", p.case_id, " ", summary)
    return nothing
end

fingerprint = CFDSDFWaterLily.runtime_fingerprint()
vram_total = last(CUDA.memory_info())
mkpath(output_dir)
for p in W2B_CASES
    run_case(p, fingerprint, vram_total)
    GC.gc()
    CUDA.synchronize()
end
println("W2B_JOB_DONE ", length(W2B_CASES), " cases")
