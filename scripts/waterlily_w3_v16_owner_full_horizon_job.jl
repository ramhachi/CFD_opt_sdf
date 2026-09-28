"""Diagnostic-only W3 full-horizon comparison of backing CUDA owner lifetime."""

using CUDA
using SHA
using WaterLily

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
using .CFDSDFWaterLily: V16_CANONICAL_SDF_ORIGIN_M, V16_PROFILE_POINT_SHAPE,
    V16_PROFILE_SPACING_M, V16_PROFILE_CELL_DIMS, V16_PROFILE_FLOW_ORIGIN_M,
    V16_PROFILE_FLOW_UPPER_M, V16_PROFILE_REYNOLDS, V16_PROFILE_SOLVER_LENGTH,
    V16_PROFILE_SOLVER_VISCOSITY, V16_PROFILE_REFERENCE_AREA_M2,
    V16_PROFILE_DENSITY_KG_M3, V16_PROFILE_FREESTREAM_MPS,
    build_v16_physical_profile_simulation, runtime_fingerprint, v16_physical_profile_bodies
using .CFDSDFWaterLily.DeviceGridSDF: device_copy, device_roundtrip_sha, kernel_grid

length(ARGS) == 3 || error("usage: owner_full_horizon_job.jl <phi_fortran.raw> <output_dir> <arm_id>")
const PHI_PATH = ARGS[1]
const OUTPUT_DIR = ARGS[2]
const ARM_ID = ARGS[3]
ARM_ID in ("A-natural", "A-forced", "B-natural-1", "B-natural-2", "B-forced-1", "B-forced-2") ||
    error("unknown owner-lifetime arm: $ARM_ID")
mkpath(OUTPUT_DIR)

const T_END = 120.0
const BURN_IN = 80.0
const SAMPLE_EVERY = 8
const MEMORY_EVERY = 50
const MAX_STEPS = 5000
const FIELD_DIAGNOSTIC_CAPACITY = 2
const CANDIDATE_PROBE_CAPACITY = 4 * FIELD_DIAGNOSTIC_CAPACITY
const MEMORY_SAMPLE_CAPACITY = MAX_STEPS ÷ MEMORY_EVERY + 4
const EXPECTED_PHI_SHA256 = "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
const EXPECTED_PHI_C_SHA256 = "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
const EXPECTED_STATE_SHA256 = "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
const EXPECTED_SOURCE_SURFACE_SHA256 = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
const FORCE_HEADER = "step,t_u_l,fx_solver,fy_solver,fz_solver,drag_solver,downforce_solver,pressure_fx_solver,pressure_fy_solver,pressure_fz_solver,viscous_fx_solver,viscous_fy_solver,viscous_fz_solver"
const ForceRow = NTuple{13,Float64}

json_escape(value::AbstractString) = replace(replace(replace(String(value), "\\" => "\\\\"), "\"" => "\\\""), "\n" => "\\n")
json_value(::Nothing) = "null"
json_value(value::Bool) = value ? "true" : "false"
json_value(value::Integer) = string(value)
json_value(value::AbstractFloat) = isfinite(value) ? repr(Float64(value)) : "null"
json_value(value::AbstractString) = "\"" * json_escape(value) * "\""
json_value(value::Symbol) = json_value(string(value))
json_value(value::AbstractDict) = "{" * join((json_value(string(k)) * ":" * json_value(v)
    for (k, v) in sort!(collect(pairs(value)); by=pair -> string(first(pair)))), ",") * "}"
json_value(value::Tuple) = "[" * join(json_value.(collect(value)), ",") * "]"
json_value(value::AbstractArray) = "[" * join(json_value.(vec(value)), ",") * "]"
write_json(path, value) = write(path, json_value(value), "\n")

struct OwnedFullHorizon{O,B,S,W,I}
    owner::O
    bodies::B
    sim::S
    weakref::W
    owner_info::I
end

struct OwnerInfo{T,M}
    owner_array_type::T
    memory_type::M
    view_array_type::DataType
    roundtrip_sha256::String
    runtime::Dict{String,Any}
end

struct RunBuffers{K,G,O,H}
    probe_names::NTuple{4,String}
    probe_worlds::NTuple{4,NTuple{3,Float32}}
    probe_solver_points::NTuple{4,NTuple{3,Float32}}
    probe_kernel::K
    gpu_points::G
    gpu_probe_output::O
    host_probe_output::H
    progress::Matrix{Float64}
    fields::Matrix{Float64}
    probes::Matrix{Float64}
    memory::Matrix{Float64}
end

mutable struct RunCapture
    progress_count::Int
    field_count::Int
    probe_count::Int
    memory_count::Int
    first_collected_step::Int
    last_owner_alive::Bool
    forces::Vector{ForceRow}
    diagnostic_forces::Vector{Tuple{String,ForceRow}}
    forced_gc_events::Vector{Dict{String,Any}}
    measurement_errors::Vector{String}
end

RunCapture(owner_alive) = RunCapture(0, 0, 0, 0, 0, owner_alive,
    ForceRow[], Tuple{String,ForceRow}[], Dict{String,Any}[], String[])

function load_canonical_grid(path)
    Base.ENDIAN_BOM == 0x04030201 || error("registered phi bytes require little-endian Julia")
    bytes = read(path)
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_SHA256 || error("canonical Fortran phi SHA mismatch")
    length(bytes) == prod(V16_PROFILE_POINT_SHAPE) * sizeof(Float32) || error("canonical phi byte length mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), V16_PROFILE_POINT_SHAPE)
    c_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_sha == EXPECTED_PHI_C_SHA256 || error("canonical C-order phi SHA mismatch")
    grid = GridSDF(phi; origin=V16_CANONICAL_SDF_ORIGIN_M,
        h=(V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M),
        outside_value=3.0, margin_m=0.15)
    margin = zero_level_margin_m(phi, V16_CANONICAL_SDF_ORIGIN_M,
        (V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M))
    return grid, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), c_sha, margin
end

function owner_runtime_info(owner, view, roundtrip)
    owner_type = typeof(owner.grid.phi)
    memory_type = typeof(owner.grid.phi).parameters[3]
    memory_module = parentmodule(memory_type)
    package_id = Base.PkgId(memory_module)
    memory_package_version = try Base.pkgversion(memory_module) catch; nothing end
    cuda_has_device_memory = isdefined(CUDA, :DeviceMemory)
    cuda_memory_type = cuda_has_device_memory ? getfield(CUDA, :DeviceMemory) : nothing
    profile_runtime = runtime_fingerprint()
    return OwnerInfo(owner_type, memory_type, typeof(view.phi), roundtrip, Dict(
        "julia_version" => string(VERSION),
        "julia_threads" => Threads.nthreads(),
        "cuda_jl_version" => string(pkgversion(CUDA)),
        "waterlily_backend" => profile_runtime.waterlily_backend,
        "blas_threads" => profile_runtime.blas_threads,
        "cuda_driver_api_version" => string(CUDA.driver_version()),
        "cuda_runtime_version" => string(CUDA.runtime_version()),
        "waterlily_version" => string(pkgversion(WaterLily)),
        "gpu_name" => CUDA.name(CUDA.device()),
        "gpu_uuid" => get(ENV, "W3_OWNER_FULL_SELECTED_GPU_UUID", ""),
        "cuda_visible_devices" => get(ENV, "CUDA_VISIBLE_DEVICES", ""),
        "owner_array_type" => string(owner_type),
        "owner_memory_parameter" => string(memory_type),
        "owner_memory_parameter_type" => string(typeof(memory_type)),
        "owner_memory_module" => string(memory_module),
        "owner_memory_package" => package_id.name,
        "owner_memory_package_uuid" => string(package_id.uuid),
        "owner_memory_package_version" => memory_package_version === nothing ? nothing : string(memory_package_version),
        "kernel_view_type" => string(typeof(view.phi)),
        "cuda_device_memory_defined" => cuda_has_device_memory,
        "cuda_device_memory_is_owner_parameter" => cuda_has_device_memory ? cuda_memory_type === memory_type : nothing,
        "cuda_device_memory_is_memory_module_binding" =>
            cuda_has_device_memory && isdefined(memory_module, :DeviceMemory) ?
                cuda_memory_type === getfield(memory_module, :DeviceMemory) : nothing,
    ))
end

function build_owned(canonical, do_forced_gc)
    owner = device_copy(canonical)
    view = kernel_grid(owner)
    roundtrip = device_roundtrip_sha(owner)
    bodies = v16_physical_profile_bodies(view; T=Float32)
    sim = build_v16_physical_profile_simulation(bodies; T=Float32, mem=CuArray)
    info = owner_runtime_info(owner, view, roundtrip)
    weak = WeakRef(owner.grid.phi)
    gc_was_enabled = do_forced_gc ? GC.enable(false) : true
    do_forced_gc && !gc_was_enabled && error("automatic GC was already disabled before retained arm setup")
    return OwnedFullHorizon(owner, bodies, sim, weak, info), gc_was_enabled
end

# A returned object intentionally omits `owner` and the `DeviceGridSDF` wrapper.
# The exact non-owning view remains reachable through `bodies` / `sim`.
Base.@noinline function build_unrooted(canonical, do_forced_gc)
    owner = device_copy(canonical)
    view = kernel_grid(owner)
    roundtrip = device_roundtrip_sha(owner)
    bodies = v16_physical_profile_bodies(view; T=Float32)
    sim = build_v16_physical_profile_simulation(bodies; T=Float32, mem=CuArray)
    info = owner_runtime_info(owner, view, roundtrip)
    weak = WeakRef(owner.grid.phi)
    gc_was_enabled = do_forced_gc ? GC.enable(false) : true
    do_forced_gc && !gc_was_enabled && error("automatic GC was already disabled before unrooted arm setup")
    return bodies, sim, weak, info, gc_was_enabled
end

function world_probe_points(grid)
    phi = grid.phi
    linear = (argmin(vec(phi)), argmin(abs.(vec(phi))))
    nearest_positive = 0
    positive_value = Inf32
    for index in eachindex(phi)
        value = phi[index]
        if 0.0f0 < value < positive_value
            positive_value = value
            nearest_positive = index
        end
    end
    nearest_positive > 0 || error("canonical SDF lacks positive values")
    indices = CartesianIndices(phi)
    solid_ci = indices[linear[1]]
    surface_ci = indices[linear[2]]
    positive_ci = indices[nearest_positive]
    world(ci) = ntuple(axis -> Float32(grid.origin[axis] + (ci[axis] - 1) * grid.h[axis]), 3)
    return ("candidate_min_phi", "candidate_surface_min_abs_phi", "candidate_nearest_positive", "world_origin"),
        (world(solid_ci), world(surface_ci), world(positive_ci), (0.0f0, 0.0f0, 0.0f0))
end

flow_point(world) = WaterLily.SVector{3,Float32}(
    (world[1] - Float32(V16_PROFILE_FLOW_ORIGIN_M[1])) / Float32(V16_PROFILE_SPACING_M),
    (world[2] - Float32(V16_PROFILE_FLOW_ORIGIN_M[2])) / Float32(V16_PROFILE_SPACING_M),
    (world[3] - Float32(V16_PROFILE_FLOW_ORIGIN_M[3])) / Float32(V16_PROFILE_SPACING_M))

function prepare_buffers(grid)
    names, worlds = world_probe_points(grid)
    points = flow_point.(worlds)
    solver_points = Tuple(Tuple(point) for point in points)
    gpu_points = CuArray(collect(points))
    gpu_output = CuArray{Float32}(undef, length(names), 7)
    host_output = Matrix{Float32}(undef, length(names), 7)
    probe_kernel = candidate_probe_kernel!(get_backend(gpu_output), 128)
    buffers = RunBuffers(names, worlds, solver_points, probe_kernel, gpu_points, gpu_output, host_output,
        fill(NaN, MAX_STEPS, 3), fill(NaN, FIELD_DIAGNOSTIC_CAPACITY, 11),
        fill(NaN, CANDIDATE_PROBE_CAPACITY, 10),
        fill(NaN, MEMORY_SAMPLE_CAPACITY, 2))
    return buffers
end

@kernel function candidate_probe_kernel!(output, body, points)
    i = @index(Global)
    d, n, velocity = WaterLily.measure(body, points[i], 0.0f0; fastd²=Inf32)
    output[i, 1] = d
    output[i, 2] = n[1]
    output[i, 3] = n[2]
    output[i, 4] = n[3]
    output[i, 5] = velocity[1]
    output[i, 6] = velocity[2]
    output[i, 7] = velocity[3]
end

function force_row(step, sim, candidate)
    pressure = -WaterLily.pressure_force(sim.flow, candidate)
    viscous = -WaterLily.viscous_force(sim.flow, candidate)
    total = pressure + viscous
    return (Float64(step), Float64(sim_time(sim)), Float64(total[1]), Float64(total[2]),
        Float64(total[3]), Float64(total[1]), Float64(-total[3]), Float64(pressure[1]),
        Float64(pressure[2]), Float64(pressure[3]), Float64(viscous[1]),
        Float64(viscous[2]), Float64(viscous[3]))
end

function record_progress!(capture, buffers, step, sim, weak)
    alive = weak.value !== nothing
    capture.progress_count += 1
    capture.progress_count <= size(buffers.progress, 1) || error("progress buffer overflow")
    buffers.progress[capture.progress_count, 1] = step
    buffers.progress[capture.progress_count, 2] = Float64(sim_time(sim))
    buffers.progress[capture.progress_count, 3] = alive ? 1.0 : 0.0
    if !alive && capture.last_owner_alive && capture.first_collected_step == 0
        capture.first_collected_step = step
    end
    capture.last_owner_alive = alive
    return alive
end

function record_memory!(capture, buffers, step)
    capture.memory_count += 1
    capture.memory_count <= size(buffers.memory, 1) || error("memory buffer overflow")
    buffers.memory[capture.memory_count, 1] = step
    buffers.memory[capture.memory_count, 2] = Float64(CUDA.used_memory())
end

function field_summary_row(step, sim, alive)
    u = sim.flow.u
    p = sim.flow.p
    return Float64[step, sim_time(sim), alive ? 1.0 : 0.0,
        all(isfinite, u) ? 1.0 : 0.0, all(isfinite, p) ? 1.0 : 0.0,
        Float64(minimum(u)), Float64(maximum(u)), Float64(sum(u) / length(u)),
        Float64(minimum(p)), Float64(maximum(p)), Float64(sum(p) / length(p))]
end

function capture_diagnostics!(capture, buffers, step, sim, bodies, weak; reason=nothing)
    alive = weak.value !== nothing
    capture.field_count += 1
    capture.field_count <= size(buffers.fields, 1) || error("field buffer overflow")
    buffers.fields[capture.field_count, :] .= field_summary_row(step, sim, alive)
    buffers.probe_kernel(buffers.gpu_probe_output, bodies.candidate, buffers.gpu_points;
        ndrange=length(buffers.probe_names))
    CUDA.synchronize()
    copyto!(buffers.host_probe_output, buffers.gpu_probe_output)
    for i in eachindex(buffers.probe_names)
        capture.probe_count += 1
        capture.probe_count <= size(buffers.probes, 1) || error("probe buffer overflow")
        buffers.probes[capture.probe_count, :] .= (step, Float64(sim_time(sim)), i,
            Float64(buffers.host_probe_output[i, 1]), Float64(buffers.host_probe_output[i, 2]),
            Float64(buffers.host_probe_output[i, 3]), Float64(buffers.host_probe_output[i, 4]),
            Float64(buffers.host_probe_output[i, 5]), Float64(buffers.host_probe_output[i, 6]),
            Float64(buffers.host_probe_output[i, 7]))
    end
    if reason !== nothing
        try
            push!(capture.diagnostic_forces, (String(reason), force_row(step, sim, bodies.candidate)))
        catch err
            push!(capture.measurement_errors, "diagnostic step=$step: " * sprint(showerror, err, catch_backtrace()))
            push!(capture.diagnostic_forces, (String(reason), ntuple(_ -> NaN, 13)))
        end
    end
end

function forced_gc_bracket!(capture, weak, sim)
    before = weak.value !== nothing
    CUDA.synchronize()
    old = GC.enable(true)
    !old || error("forced-GC arm entered bracket with automatic GC enabled")
    GC.gc(true)
    CUDA.synchronize()
    after_first = weak.value !== nothing
    push!(capture.forced_gc_events, Dict("call" => 1, "after_warmup_step" => 1,
        "t_u_l" => Float64(sim_time(sim)), "weakref_before" => before,
        "weakref_after" => after_first, "gc_enable_previous_state" => old))
    GC.enable(false)
    was_enabled = GC.enable(true)
    was_enabled && error("automatic GC unexpectedly enabled between forced collections")
    GC.gc(true)
    CUDA.synchronize()
    after_second = weak.value !== nothing
    push!(capture.forced_gc_events, Dict("call" => 2, "after_warmup_step" => 1,
        "t_u_l" => Float64(sim_time(sim)), "weakref_before" => after_first,
        "weakref_after" => after_second, "gc_enable_previous_state" => was_enabled))
end

function prepare_capture()
    capture = RunCapture(true)
    sizehint!(capture.diagnostic_forces, 16)
    sizehint!(capture.measurement_errors, 8)
    sizehint!(capture.forced_gc_events, 2)
    return capture
end

function run_solver_steps!(capture, buffers, sim, bodies, weak, setup_owner_alive, gc_suppressed_at_setup)
    warm_started = time()
    WaterLily.sim_step!(sim)
    first_step_seconds = time() - warm_started
    step = 1
    alive = record_progress!(capture, buffers, step, sim, weak)
    record_memory!(capture, buffers, step)
    if gc_suppressed_at_setup
        forced_gc_bracket!(capture, weak, sim)
        alive_after_gc = weak.value !== nothing
        if alive && !alive_after_gc
            capture.first_collected_step == 0 && (capture.first_collected_step = step)
        end
        if !alive_after_gc
            record_memory!(capture, buffers, step)
            capture_diagnostics!(capture, buffers, step, sim, bodies, weak;
                reason="after_forced_owner_collection")
        end
    elseif !alive
        capture_diagnostics!(capture, buffers, step, sim, bodies, weak;
            reason=setup_owner_alive ? "owner_collection_during_warmup_step1" :
                "owner_collection_before_or_during_warmup_step1")
    end
    wall_started = time()
    while WaterLily.sim_time(sim) < T_END
        WaterLily.sim_step!(sim)
        step += 1
        step <= MAX_STEPS || error("solver exceeded registered MAX_STEPS")
        official_force = step % SAMPLE_EVERY == 0 || WaterLily.sim_time(sim) >= T_END
        if official_force
            try
                push!(capture.forces, force_row(step, sim, bodies.candidate))
            catch err
                push!(capture.measurement_errors, "official force step=$step: " * sprint(showerror, err, catch_backtrace()))
                push!(capture.forces, ntuple(_ -> NaN, 13))
            end
        end
        if step % MEMORY_EVERY == 0 || WaterLily.sim_time(sim) >= T_END
            record_memory!(capture, buffers, step)
        end
        alive = record_progress!(capture, buffers, step, sim, weak)
        owner_lost = capture.progress_count >= 2 &&
            buffers.progress[capture.progress_count - 1, 3] == 1.0 && !alive
        if owner_lost
            capture_diagnostics!(capture, buffers, step, sim, bodies, weak;
                reason="first_observed_owner_collection")
        elseif WaterLily.sim_time(sim) >= T_END
            capture_diagnostics!(capture, buffers, step, sim, bodies, weak;
                reason="full_horizon_endpoint")
        end
    end
    return first_step_seconds, wall_started, step
end

function interpolate_row(left, right, t)
    left[2] <= t <= right[2] || error("force samples do not bracket tU/L=$t")
    left[2] == right[2] && return left
    alpha = (t - left[2]) / (right[2] - left[2])
    return ntuple(i -> i == 2 ? Float64(t) : left[i] + alpha * (right[i] - left[i]), 13)
end

function clipped_window(rows, first_t, last_t)
    l0 = findlast(row -> row[2] <= first_t, rows)
    r0 = findfirst(row -> row[2] >= first_t, rows)
    l1 = findlast(row -> row[2] <= last_t, rows)
    r1 = findfirst(row -> row[2] >= last_t, rows)
    all(!isnothing, (l0, r0, l1, r1)) || error("force samples do not bracket exact [$first_t,$last_t]")
    start = interpolate_row(rows[l0], rows[r0], first_t)
    finish = interpolate_row(rows[l1], rows[r1], last_t)
    interior = [row for row in rows if first_t < row[2] < last_t]
    return vcat([start], interior, [finish])
end

function time_weighted_mean(rows, column)
    numerator = 0.0
    duration = 0.0
    for i in 1:(length(rows) - 1)
        dt = rows[i + 1][2] - rows[i][2]
        numerator += 0.5 * (rows[i][column] + rows[i + 1][column]) * dt
        duration += dt
    end
    duration > 0 || error("empty time-weighted window")
    return numerator / duration
end

function force_metrics(rows)
    window = clipped_window(rows, BURN_IN, T_END)
    first_half = clipped_window(rows, BURN_IN, (BURN_IN + T_END) / 2)
    second_half = clipped_window(rows, (BURN_IN + T_END) / 2, T_END)
    drag = time_weighted_mean(window, 6)
    downforce = time_weighted_mean(window, 7)
    first_drag = time_weighted_mean(first_half, 6)
    second_drag = time_weighted_mean(second_half, 6)
    first_downforce = time_weighted_mean(first_half, 7)
    second_downforce = time_weighted_mean(second_half, 7)
    area_solver = V16_PROFILE_REFERENCE_AREA_M2 / V16_PROFILE_SPACING_M^2
    force_scale = V16_PROFILE_DENSITY_KG_M3 * V16_PROFILE_FREESTREAM_MPS[1]^2 * V16_PROFILE_SPACING_M^2
    return Dict(
        "window_time_weighted_drag_solver" => drag,
        "window_time_weighted_downforce_solver" => downforce,
        "first_half_time_weighted_drag_solver" => time_weighted_mean(first_half, 6),
        "second_half_time_weighted_drag_solver" => time_weighted_mean(second_half, 6),
        "first_half_time_weighted_downforce_solver" => time_weighted_mean(first_half, 7),
        "second_half_time_weighted_downforce_solver" => time_weighted_mean(second_half, 7),
        "stationarity_relative_half_window_drift_drag" =>
            abs(first_drag - second_drag) / max(abs(drag), eps(Float64)),
        "stationarity_relative_half_window_drift_downforce" =>
            abs(first_downforce - second_downforce) / max(abs(downforce), eps(Float64)),
        "window_samples" => count(row -> BURN_IN <= row[2] <= T_END, rows),
        "cd_time_weighted" => drag / (0.5 * area_solver),
        "drag_time_weighted_n" => drag * force_scale,
        "downforce_time_weighted_n" => downforce * force_scale,
    )
end

function run_horizon!(capture, sim, bodies, weak, setup_owner_alive, owner_guard, owner_info, buffers,
                      c_sha, margin, gc_initially_enabled, gc_suppressed_at_setup)
    capture.last_owner_alive = setup_owner_alive
    first_step_seconds = NaN
    wall_started = NaN
    step = 0
    run_error = nothing
    try
        if owner_guard === nothing
            first_step_seconds, wall_started, step = run_solver_steps!(capture, buffers, sim, bodies,
                weak, setup_owner_alive, gc_suppressed_at_setup)
        else
            GC.@preserve owner_guard begin
                first_step_seconds, wall_started, step = run_solver_steps!(capture, buffers, sim, bodies,
                    weak, setup_owner_alive, gc_suppressed_at_setup)
            end
        end
    catch err
        run_error = sprint(showerror, err, catch_backtrace())
    end
    CUDA.synchronize()
    wall_seconds = isnan(wall_started) ? 0.0 : time() - wall_started
    finite_u = try all(isfinite, sim.flow.u) catch; false end
    finite_p = try all(isfinite, sim.flow.p) catch; false end
    peak_vram = capture.memory_count == 0 ? 0.0 : maximum(@view buffers.memory[1:capture.memory_count, 2])
    metrics = try force_metrics(capture.forces) catch err
        Dict{String,Any}("metrics_error" => sprint(showerror, err, catch_backtrace()))
    end
    report = Dict{String,Any}(
        "arm_id" => ARM_ID,
        "owner_mode" => startswith(ARM_ID, "A-") ? "retained" : "unrooted",
        "gc_mode" => occursin("forced", ARM_ID) ? "registered_forced_after_warmup_step1" : "natural_only",
        "status" => run_error === nothing ? "completed" : "operation_error",
        "exact_exception" => run_error,
        "force_measurement_errors" => capture.measurement_errors,
        "solver_started" => capture.progress_count > 0,
        "solver_steps" => capture.progress_count,
        "t_u_l_reached" => capture.progress_count == 0 ? 0.0 : buffers.progress[capture.progress_count, 2],
        "t_u_l_target" => T_END,
        "warmup_step_seconds" => first_step_seconds,
        "wall_seconds_excluding_warmup" => wall_seconds,
        "force_sample_every_steps" => SAMPLE_EVERY,
        "owner_weakref_sampling" => "once after every production sim_step!, following the registered force sampling and memory sampling operations",
        "field_and_candidate_probe_sampling" => "only at first observed owner collection and full-horizon endpoint to minimize perturbation",
        "force_rows" => length(capture.forces),
        "first_observed_owner_collection_step" => capture.first_collected_step == 0 ? nothing : capture.first_collected_step,
        "owner_alive_at_setup_return" => setup_owner_alive,
        "owner_alive_after_warmup_step1" => capture.progress_count == 0 ? nothing : buffers.progress[1, 3] == 1.0,
        "weakref_target_path" => "owner.grid.phi",
        "owner_array_type" => string(owner_info.owner_array_type),
        "owner_memory_parameter" => string(owner_info.memory_type),
        "kernel_view_type" => string(owner_info.view_array_type),
        "runtime_identity" => owner_info.runtime,
        "forced_gc_events" => capture.forced_gc_events,
        "gc_was_enabled_before_setup" => gc_initially_enabled,
        "automatic_gc_suppressed_during_setup_and_warmup" => gc_suppressed_at_setup,
        "finite_u_at_end" => finite_u,
        "finite_p_at_end" => finite_p,
        "canonical_phi_fortran_sha256" => EXPECTED_PHI_SHA256,
        "canonical_phi_c_order_sha256" => c_sha,
        "canonical_state_sha256" => EXPECTED_STATE_SHA256,
        "source_surface_sha256" => EXPECTED_SOURCE_SURFACE_SHA256,
        "device_roundtrip_sha256" => owner_info.roundtrip_sha256,
        "canonical_phi_margin_m" => margin,
        "flow_dims" => collect(V16_PROFILE_CELL_DIMS),
        "flow_origin_m" => collect(V16_PROFILE_FLOW_ORIGIN_M),
        "flow_upper_m" => collect(V16_PROFILE_FLOW_UPPER_M),
        "canonical_sdf_origin_m" => collect(V16_CANONICAL_SDF_ORIGIN_M),
        "spacing_m" => V16_PROFILE_SPACING_M,
        "reynolds" => V16_PROFILE_REYNOLDS,
        "solver_length" => V16_PROFILE_SOLVER_LENGTH,
        "solver_viscosity" => V16_PROFILE_SOLVER_VISCOSITY,
        "freestream_mps" => collect(V16_PROFILE_FREESTREAM_MPS),
        "physical_reference_area_m2" => V16_PROFILE_REFERENCE_AREA_M2,
        "physical_force_scale_n_per_solver_unit" => V16_PROFILE_DENSITY_KG_M3 *
            V16_PROFILE_FREESTREAM_MPS[1]^2 * V16_PROFILE_SPACING_M^2,
        "peak_vram_bytes_sampled" => peak_vram,
        "measurement_metrics" => metrics,
        "qualification" => false,
        "physical_profile_qualified" => false,
        "claim_scope" => "diagnostic-only full-horizon owner-lifetime comparison; no W3 primal, physical-profile, gradient, or shape-update qualification",
    )
    write_arm_outputs(report, capture, buffers)
    println("W3_OWNER_FULL_HORIZON_ARM ", ARM_ID, " ", json_value(Dict(
        "status" => report["status"], "solver_steps" => report["solver_steps"],
        "t_u_l_reached" => report["t_u_l_reached"],
        "first_observed_owner_collection_step" => report["first_observed_owner_collection_step"],
        "finite_u_at_end" => finite_u, "finite_p_at_end" => finite_p)))
    return report
end

function write_force_csv(path, rows)
    open(path, "w") do io
        println(io, FORCE_HEADER)
        for row in rows
            println(io, join(row, ","))
        end
    end
end

function write_matrix_csv(path, header, matrix, count)
    open(path, "w") do io
        println(io, header)
        for i in 1:count
            println(io, join(@view(matrix[i, :]), ","))
        end
    end
end

function write_arm_outputs(report, capture, buffers)
    write_matrix_csv(joinpath(OUTPUT_DIR, "progress.csv"),
        "step,t_u_l,owner_weakref_alive", buffers.progress, capture.progress_count)
    write_matrix_csv(joinpath(OUTPUT_DIR, "field_diagnostics.csv"),
        "step,t_u_l,owner_weakref_alive,finite_u,finite_p,u_min,u_max,u_mean,p_min,p_max,p_mean",
        buffers.fields, capture.field_count)
    write_matrix_csv(joinpath(OUTPUT_DIR, "candidate_probes.csv"),
        "step,t_u_l,probe_index,distance_solver,nx,ny,nz,velocity_x,velocity_y,velocity_z",
        buffers.probes, capture.probe_count)
    write_matrix_csv(joinpath(OUTPUT_DIR, "cuda_memory.csv"),
        "step,cuda_used_memory_bytes", buffers.memory, capture.memory_count)
    write_force_csv(joinpath(OUTPUT_DIR, "v16.forces.csv"), capture.forces)
    open(joinpath(OUTPUT_DIR, "force_diagnostic.csv"), "w") do io
        println(io, "sample_reason,", FORCE_HEADER)
        for (reason, row) in capture.diagnostic_forces
            println(io, reason, ",", join(row, ","))
        end
    end
    write_json(joinpath(OUTPUT_DIR, "candidate_probe_world_points.json"), Dict(
        "names" => collect(buffers.probe_names),
        "world_m" => [collect(world) for world in buffers.probe_worlds],
        "flow_solver" => [collect(point) for point in buffers.probe_solver_points],
        "flow_origin_m" => collect(V16_PROFILE_FLOW_ORIGIN_M),
        "canonical_sdf_origin_m" => collect(V16_CANONICAL_SDF_ORIGIN_M)))
    write_json(joinpath(OUTPUT_DIR, "arm_summary.json"), report)
end

function main()
    prior_gc_state = GC.enable(true)
    canonical, phi_sha, c_sha, margin = load_canonical_grid(PHI_PATH)
    buffers = prepare_buffers(canonical)
    capture = prepare_capture()
    forced_arm = occursin("forced", ARM_ID)
    if startswith(ARM_ID, "A-")
        owned, gc_was_enabled = build_owned(canonical, forced_arm)
        setup_owner_alive = owned.weakref.value !== nothing
        return run_horizon!(capture, owned.sim, owned.bodies, owned.weakref, setup_owner_alive, owned,
            owned.owner_info, buffers, c_sha, margin, prior_gc_state, forced_arm)
    end
    bodies, sim, weak, owner_info, gc_was_enabled = build_unrooted(canonical, forced_arm)
    setup_owner_alive = weak.value !== nothing
    return run_horizon!(capture, sim, bodies, weak, setup_owner_alive, nothing,
        owner_info, buffers, c_sha, margin, prior_gc_state, forced_arm)
end

try
    main()
catch err
    write_json(joinpath(OUTPUT_DIR, "arm_summary.json"), Dict(
        "arm_id" => ARM_ID, "status" => "setup_error",
        "exact_exception" => sprint(showerror, err, catch_backtrace()),
        "solver_started" => false, "solver_steps" => 0, "qualification" => false,
        "claim_scope" => "diagnostic-only full-horizon owner-lifetime comparison; no qualification"))
    println("W3_OWNER_FULL_HORIZON_ARM_ERROR ", ARM_ID, " ", sprint(showerror, err, catch_backtrace()))
end
