# Diagnostic-only W3 v16 CPU/T4 body and one-step force reproduction.
# This deliberately does not run the W3 horizon or evaluate W3 qualification gates.

using CUDA
using SHA

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
using WaterLily
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
using .CFDSDFWaterLily.DeviceGridSDF

length(ARGS) == 2 || error("usage: waterlily_w3_v16_cuda_diagnostic_job.jl <phi_fortran.raw> <output_dir>")
phi_raw_path, output_dir = ARGS
mkpath(output_dir)

const EXPECTED_PHI_FORTRAN_SHA256 = "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
const EXPECTED_PHI_C_ORDER_SHA256 = "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
const EXPECTED_SPHERE_PHI_SHA256 = "393d5d7897885d71cda0902129a4aa3db561c59b1a85e8e221d55ce19fca4161"
const FLOW_DIMS = (100, 48, 36)
const SPACING_M = 0.05f0
const FLOW_ORIGIN_M = Float32.((-2.5, -1.2, -0.9))
const TINY_REPETITIONS = 1

@kernel function diagnostic_measure_kernel!(output, body, points, fastd2)
    i = @index(Global)
    d, n, velocity = WaterLily.measure(body, points[i], 0.0f0; fastd²=fastd2)
    output[i, 1] = d
    output[i, 2] = n[1]
    output[i, 3] = n[2]
    output[i, 4] = n[3]
    output[i, 5] = velocity[1]
    output[i, 6] = velocity[2]
    output[i, 7] = velocity[3]
end

json_escape(value::AbstractString) = replace(replace(replace(String(value), "\\" => "\\\\"), "\"" => "\\\""), "\n" => "\\n")
json_value(::Nothing) = "null"
json_value(value::Bool) = value ? "true" : "false"
json_value(value::Integer) = string(value)
json_value(value::AbstractFloat) = isfinite(value) ? repr(Float64(value)) : "null"
json_value(value::AbstractString) = "\"" * json_escape(value) * "\""
json_value(value::Symbol) = json_value(string(value))
json_value(value::NamedTuple) = json_value(Dict(string(k) => v for (k, v) in pairs(value)))
json_value(value::AbstractDict) = "{" * join((json_value(string(k)) * ":" * json_value(v)
    for (k, v) in sort!(collect(pairs(value)); by=pair -> string(first(pair)))), ",") * "}"
json_value(value::Tuple) = "[" * join(json_value.(collect(value)), ",") * "]"
json_value(value::AbstractArray) = "[" * join(json_value.(vec(value)), ",") * "]"

const PROGRESS = Dict{String,Any}("diagnostic_only" => true)
function checkpoint!(stage, values)
    PROGRESS["last_completed_stage"] = stage
    PROGRESS[stage] = values
    path = joinpath(output_dir, "progress.json")
    temporary_path = path * ".tmp"
    write(temporary_path, json_value(PROGRESS) * "\n")
    mv(temporary_path, path; force=true)
    println("W3_DIAGNOSTIC_STAGE ", stage, " ", json_value(values))
end

function load_canonical_grid(path)
    bytes = read(path)
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_FORTRAN_SHA256 || error("canonical phi input SHA mismatch")
    length(bytes) == prod(CFDSDFWaterLily.V16_PROFILE_POINT_SHAPE) * sizeof(Float32) ||
        error("canonical phi byte count mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), CFDSDFWaterLily.V16_PROFILE_POINT_SHAPE)
    c_order_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_order_sha == EXPECTED_PHI_C_ORDER_SHA256 || error("canonical phi C-order SHA mismatch")
    grid = GridSDF(phi; origin=CFDSDFWaterLily.V16_CANONICAL_SDF_ORIGIN_M,
        h=(0.05, 0.05, 0.05), outside_value=3.0, margin_m=0.15)
    return grid, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), c_order_sha,
        zero_level_margin_m(phi, grid.origin, grid.h)
end

flow_point(world) = WaterLily.SVector{3,Float32}(
    (Float32(world[1]) - FLOW_ORIGIN_M[1]) / SPACING_M,
    (Float32(world[2]) - FLOW_ORIGIN_M[2]) / SPACING_M,
    (Float32(world[3]) - FLOW_ORIGIN_M[3]) / SPACING_M,
)

world_point(grid, index::CartesianIndex{3}) = ntuple(axis ->
    Float32(grid.origin[axis] + (index[axis] - 1) * grid.h[axis]), 3)

function v16_representative_probes(grid)
    phi = grid.phi
    solid_index = CartesianIndices(phi)[argmin(vec(phi))]
    surface_index = CartesianIndices(phi)[argmin(abs.(vec(phi)))]
    positive_linear = 0
    positive_value = Inf32
    for linear_index in eachindex(phi)
        value = phi[linear_index]
        if 0f0 < value < positive_value
            positive_value = value
            positive_linear = linear_index
        end
    end
    positive_linear > 0 || error("canonical v16 field has no positive sample")
    positive_index = CartesianIndices(phi)[positive_linear]
    return [
        ("candidate_solid_min_phi", world_point(grid, solid_index)),
        ("candidate_surface_min_abs_phi", world_point(grid, surface_index)),
        ("candidate_nearest_positive_phi", world_point(grid, positive_index)),
        ("registered_world_center", (0.0f0, 0.0f0, 0.0f0)),
        ("outside_x_low", (-1.05f0, 0.0f0, 0.0f0)),
        ("outside_x_high", (2.05f0, 0.0f0, 0.0f0)),
        ("outside_y_low", (0.0f0, -0.85f0, 0.0f0)),
        ("outside_y_high", (0.0f0, 0.85f0, 0.0f0)),
        ("outside_z_low", (0.0f0, 0.0f0, -0.65f0)),
        ("outside_z_high", (0.0f0, 0.0f0, 0.65f0)),
    ]
end

function cpu_measure_rows(body, points; fastd2=Inf32)
    rows = Matrix{Float32}(undef, length(points), 7)
    for i in eachindex(points)
        d, n, velocity = WaterLily.measure(body, points[i], 0.0f0; fastd²=fastd2)
        rows[i, :] .= (d, n[1], n[2], n[3], velocity[1], velocity[2], velocity[3])
    end
    return rows
end

function gpu_measure_rows(body, points; fastd2=Inf32)
    gpu_points = CuArray(points)
    output = CuArray{Float32}(undef, length(points), 7)
    kernel! = diagnostic_measure_kernel!(get_backend(output), 128)
    kernel!(output, body, gpu_points, Float32(fastd2); ndrange=length(points))
    CUDA.synchronize()
    return Array(output)
end

function matrix_stats(rows)
    d = @view rows[:, 1]
    normal_magnitude = [sqrt(sum(abs2, @view rows[i, 2:4])) for i in axes(rows, 1)]
    support = [i for i in eachindex(d) if abs(d[i]) <= 1.0f0]
    return Dict(
        "sample_count" => length(d),
        "finite_count" => count(isfinite, d),
        "negative_sdf_count" => count(<(0.0f0), d),
        "force_support_abs_d_le_1_count" => length(support),
        "bdim_band_abs_d_le_3_count" => count(value -> abs(value) <= 3.0f0, d),
        "min_sdf_solver_units" => minimum(d),
        "max_sdf_solver_units" => maximum(d),
        "support_nonzero_normal_count" => count(i -> normal_magnitude[i] > 0.0f0, support),
        "support_normal_magnitude_min" => isempty(support) ? nothing : minimum(normal_magnitude[support]),
        "support_normal_magnitude_max" => isempty(support) ? nothing : maximum(normal_magnitude[support]),
        "support_normal_magnitude_mean" => isempty(support) ? nothing : sum(normal_magnitude[support]) / length(support),
    )
end

function compare_rows(cpu, gpu; world_scale=Float32(1))
    size(cpu) == size(gpu) || error("CPU/GPU diagnostic arrays differ in shape")
    value_error_m = maximum(abs.(cpu[:, 1] .- gpu[:, 1])) * world_scale
    normal_error = maximum(sqrt.(sum(abs2, cpu[:, 2:4] .- gpu[:, 2:4], dims=2)))
    velocity_error = maximum(sqrt.(sum(abs2, cpu[:, 5:7] .- gpu[:, 5:7], dims=2)))
    sign_compared = [i for i in eachindex(cpu[:, 1]) if abs(cpu[i, 1]) > 1f-5]
    sign_mismatch = count(i -> signbit(cpu[i, 1]) != signbit(gpu[i, 1]), sign_compared)
    return Dict(
        "max_abs_distance_error_m" => value_error_m,
        "max_normal_vector_error" => normal_error,
        "max_body_velocity_error_solver_units" => velocity_error,
        "sign_mismatch_count_outside_1e-5_solver_unit_zero_band" => sign_mismatch,
        "sign_comparison_count" => length(sign_compared),
        "all_cpu_values_finite" => all(isfinite, cpu),
        "all_gpu_values_finite" => all(isfinite, gpu),
    )
end

function flow_grid_points(dims)
    points = Vector{WaterLily.SVector{3,Float32}}(undef, prod(dims))
    linear_index = 0
    for k in 1:dims[3], j in 1:dims[2], i in 1:dims[1]
        linear_index += 1
        # WaterLily pressure-cell centers for storage CartesianIndex (i+1,j+1,k+1).
        points[linear_index] = WaterLily.loc(0,
            CartesianIndex(i + 1, j + 1, k + 1), Float32)
    end
    return points
end

function sim_field_snapshot(sim)
    u = Array(sim.flow.u)
    p = Array(sim.flow.p)
    sigma = Array(sim.flow.σ)
    mu0 = Array(sim.flow.μ₀)
    body_velocity = Array(sim.flow.V)
    return (u=u, p=p, sigma=sigma, mu0=mu0, body_velocity=body_velocity)
end

function field_stats(snapshot)
    return Dict(
        "u_size" => collect(size(snapshot.u)),
        "p_size" => collect(size(snapshot.p)),
        "sigma_negative_count_including_ghosts" => count(<(0.0f0), snapshot.sigma),
        "sigma_abs_le_2_count_including_ghosts" => count(value -> abs(value) <= 2.0f0, snapshot.sigma),
        "mu0_nonzero_count" => count(!iszero, snapshot.mu0),
        "body_velocity_nonzero_count" => count(!iszero, snapshot.body_velocity),
        "u_finite_count" => count(isfinite, snapshot.u),
        "p_finite_count" => count(isfinite, snapshot.p),
        "body_velocity_finite_count" => count(isfinite, snapshot.body_velocity),
        "u_max_abs" => maximum(abs, snapshot.u),
        "p_max_abs" => maximum(abs, snapshot.p),
        "body_velocity_max_abs" => maximum(abs, snapshot.body_velocity),
    )
end

function field_difference(cpu, gpu)
    return Dict(
        "u_max_abs_difference" => maximum(abs.(cpu.u .- gpu.u)),
        "p_max_abs_difference" => maximum(abs.(cpu.p .- gpu.p)),
        "sigma_max_abs_difference" => maximum(abs.(cpu.sigma .- gpu.sigma)),
        "mu0_max_abs_difference" => maximum(abs.(cpu.mu0 .- gpu.mu0)),
        "body_velocity_max_abs_difference" => maximum(abs.(cpu.body_velocity .- gpu.body_velocity)),
    )
end

function raw_force_snapshot(sim, force_body)
    pressure = WaterLily.pressure_force(sim.flow, force_body)
    viscous = WaterLily.viscous_force(sim.flow, force_body)
    total = pressure + viscous
    return Dict(
        "waterlily_pressure_force_raw" => Float64.(pressure),
        "waterlily_viscous_force_raw" => Float64.(viscous),
        "waterlily_total_force_raw" => Float64.(total),
        "registered_drag_plus_fx_from_raw" => Float64(-total[1]),
        "registered_downforce_minus_fz_from_raw" => Float64(total[3]),
    )
end

function write_lattice_csv(path, points, cpu_measures, gpu_measures,
                           cpu_snapshot, gpu_snapshot, dims)
    open(path, "w") do io
        println(io, "i,j,k,flow_x_solver,flow_y_solver,flow_z_solver,",
            "cpu_candidate_d,cpu_candidate_nx,cpu_candidate_ny,cpu_candidate_nz,cpu_candidate_vx,cpu_candidate_vy,cpu_candidate_vz,",
            "gpu_candidate_d,gpu_candidate_nx,gpu_candidate_ny,gpu_candidate_nz,gpu_candidate_vx,gpu_candidate_vy,gpu_candidate_vz,",
            "cpu_ground_d,cpu_ground_nx,cpu_ground_ny,cpu_ground_nz,cpu_ground_vx,cpu_ground_vy,cpu_ground_vz,",
            "gpu_ground_d,gpu_ground_nx,gpu_ground_ny,gpu_ground_nz,gpu_ground_vx,gpu_ground_vy,gpu_ground_vz,",
            "cpu_combined_d,cpu_combined_nx,cpu_combined_ny,cpu_combined_nz,cpu_combined_vx,cpu_combined_vy,cpu_combined_vz,",
            "gpu_combined_d,gpu_combined_nx,gpu_combined_ny,gpu_combined_nz,gpu_combined_vx,gpu_combined_vy,gpu_combined_vz,",
            "cpu_sigma,gpu_sigma,cpu_mu0_sum,gpu_mu0_sum")
        for k in 1:dims[3], j in 1:dims[2], i in 1:dims[1]
            index = i + dims[1] * (j - 1) + dims[1] * dims[2] * (k - 1)
            pidx = CartesianIndex(i + 1, j + 1, k + 1)
            cpu_mu0_sum = sum(@view cpu_snapshot.mu0[i + 1, j + 1, k + 1, :])
            gpu_mu0_sum = sum(@view gpu_snapshot.mu0[i + 1, j + 1, k + 1, :])
            row = Any[i, j, k, points[index]...]
            for body_name in ("candidate", "ground", "combined")
                append!(row, cpu_measures[body_name][index, 1:7])
                append!(row, gpu_measures[body_name][index, 1:7])
            end
            append!(row, (cpu_snapshot.sigma[pidx], gpu_snapshot.sigma[pidx],
                cpu_mu0_sum, gpu_mu0_sum))
            println(io, join(row, ","))
        end
    end
end

function sphere_body_probe()
    canonical = CFDSDFWaterLily.sphere_phi_fixture()
    source_sha = canonical_phi_sha256(canonical.phi)
    source_sha == EXPECTED_SPHERE_PHI_SHA256 || error("W2 sphere control phi hash mismatch")
    cpu_body = CFDSDFWaterLily.GridSDFWaterLilyBody(
        canonical, CFDSDFWaterLily.WORLD_ORIGIN_M, CFDSDFWaterLily.WORLD_PER_SOLVER)
    owner = device_copy(canonical)
    roundtrip_sha = device_roundtrip_sha(owner)
    roundtrip_sha == source_sha || error("W2 sphere control GPU round-trip mismatch")
    gpu_body = CFDSDFWaterLily.GridSDFWaterLilyBody(
        kernel_grid(owner), Float32.(CFDSDFWaterLily.WORLD_ORIGIN_M),
        Float32(CFDSDFWaterLily.WORLD_PER_SOLVER))
    center = Float32.(CFDSDFWaterLily.SOLVER_CENTER)
    radius = Float32(CFDSDFWaterLily.SOLVER_RADIUS)
    solver_points = [
        WaterLily.SVector{3,Float32}(center[1], center[2], center[3]),
        WaterLily.SVector{3,Float32}(center[1] + radius - 0.25f0, center[2], center[3]),
        WaterLily.SVector{3,Float32}(center[1] + radius, center[2], center[3]),
        WaterLily.SVector{3,Float32}(center[1] + radius + 0.25f0, center[2], center[3]),
        WaterLily.SVector{3,Float32}(center[1] + radius + 2.0f0, center[2], center[3]),
    ]
    cpu_rows = cpu_measure_rows(cpu_body, solver_points)
    gpu_rows = gpu_measure_rows(gpu_body, solver_points)
    cpu_sim = CFDSDFWaterLily.build_sphere_sim(cpu_body; T=Float32, mem=Array)
    gpu_sim = CFDSDFWaterLily.build_sphere_sim(gpu_body; T=Float32, mem=CuArray)
    cpu_before = sim_field_snapshot(cpu_sim)
    gpu_before = sim_field_snapshot(gpu_sim)
    WaterLily.sim_step!(cpu_sim)
    WaterLily.sim_step!(gpu_sim)
    CUDA.synchronize()
    cpu_after = sim_field_snapshot(cpu_sim)
    gpu_after = sim_field_snapshot(gpu_sim)
    return owner, Dict(
        "scope" => "one-step GridSDF sphere control; not a W2 requalification",
        "phi_sha256" => source_sha,
        "device_roundtrip_sha256" => roundtrip_sha,
        "probe_comparison" => compare_rows(cpu_rows, gpu_rows; world_scale=Float32(CFDSDFWaterLily.WORLD_PER_SOLVER)),
        "probe_rows" => [Dict("probe_index" => i,
            "cpu_measure" => collect(cpu_rows[i, :]),
            "gpu_measure" => collect(gpu_rows[i, :])) for i in axes(cpu_rows, 1)],
        "cpu_initial_fields" => field_stats(cpu_before),
        "gpu_initial_fields" => field_stats(gpu_before),
        "initial_field_max_difference" => field_difference(cpu_before, gpu_before),
        "cpu_after_one_step" => merge(field_stats(cpu_after), raw_force_snapshot(cpu_sim, cpu_body)),
        "gpu_after_one_step" => merge(field_stats(gpu_after), raw_force_snapshot(gpu_sim, gpu_body)),
        "one_step_field_max_difference" => field_difference(cpu_after, gpu_after),
        "cpu_time_after_one_step" => Float64(WaterLily.sim_time(cpu_sim)),
        "gpu_time_after_one_step" => Float64(WaterLily.sim_time(gpu_sim)),
    )
end

canonical, phi_fortran_sha, phi_c_order_sha, margin = load_canonical_grid(phi_raw_path)
cpu_bodies = CFDSDFWaterLily.v16_physical_profile_bodies(canonical; T=Float32)
device_owner = device_copy(canonical)
phi_roundtrip_sha = device_roundtrip_sha(device_owner)
phi_roundtrip_sha == EXPECTED_PHI_FORTRAN_SHA256 || error("v16 GPU round-trip SHA mismatch")
device_grid = kernel_grid(device_owner)
gpu_bodies = CFDSDFWaterLily.v16_physical_profile_bodies(device_grid; T=Float32)
checkpoint!("input_and_device_identity", Dict(
    "phi_fortran_sha256" => phi_fortran_sha,
    "phi_c_order_sha256" => phi_c_order_sha,
    "device_roundtrip_sha256" => phi_roundtrip_sha,
    "measured_margin_m" => margin,
    "canonical_sdf_origin_m" => collect(canonical.origin),
    "flow_origin_m" => collect(FLOW_ORIGIN_M),
    "flow_dims" => collect(FLOW_DIMS),
    "device_owner_type" => string(typeof(device_owner.grid.phi)),
    "device_kernel_view_type" => string(typeof(device_grid.phi)),
))

checkpoint!("representative_probe_definitions_started", Dict("stage" => "world-space probe construction"))
probe_definitions = v16_representative_probes(canonical)
checkpoint!("representative_probe_definitions_completed",
    Dict("probe_count" => length(probe_definitions)))
probe_names = first.(probe_definitions)
probe_world = last.(probe_definitions)
probe_solver = flow_point.(probe_world)
probe_body_results = Dict{String,Any}()
for (body_name, cpu_body, gpu_body) in (
    ("candidate", cpu_bodies.candidate, gpu_bodies.candidate),
    ("ground", cpu_bodies.ground, gpu_bodies.ground),
    ("combined", cpu_bodies.combined, gpu_bodies.combined),
)
    checkpoint!("$(body_name)_representative_probes_started", Dict("probe_count" => length(probe_names)))
    cpu_rows = cpu_measure_rows(cpu_body, probe_solver)
    gpu_rows = gpu_measure_rows(gpu_body, probe_solver)
    checkpoint!("$(body_name)_representative_probe_measurements_completed", Dict(
        "cpu_measure_rows" => cpu_rows,
        "gpu_measure_rows" => gpu_rows,
    ))
    probe_body_results[body_name] = Dict(
        "comparison" => compare_rows(cpu_rows, gpu_rows; world_scale=SPACING_M),
        "records" => [Dict(
            "name" => probe_names[i],
            "world_m" => collect(probe_world[i]),
            "solver" => collect(probe_solver[i]),
            "cpu_measure" => collect(cpu_rows[i, :]),
            "gpu_measure" => collect(gpu_rows[i, :]),
        ) for i in eachindex(probe_names)],
    )
    checkpoint!("$(body_name)_representative_probes_completed",
        probe_body_results[body_name])
end

all_flow_points = flow_grid_points(FLOW_DIMS)
cpu_candidate = cpu_measure_rows(cpu_bodies.candidate, all_flow_points; fastd2=1.0f0)
checkpoint!("cpu_candidate_flow_lattice_completed", matrix_stats(cpu_candidate))
gpu_candidate = gpu_measure_rows(gpu_bodies.candidate, all_flow_points; fastd2=1.0f0)
checkpoint!("cuda_candidate_flow_lattice_completed", matrix_stats(gpu_candidate))
cpu_ground = cpu_measure_rows(cpu_bodies.ground, all_flow_points; fastd2=1.0f0)
checkpoint!("cpu_ground_flow_lattice_completed", matrix_stats(cpu_ground))
gpu_ground = gpu_measure_rows(gpu_bodies.ground, all_flow_points; fastd2=1.0f0)
checkpoint!("cuda_ground_flow_lattice_completed", matrix_stats(gpu_ground))
cpu_combined = cpu_measure_rows(cpu_bodies.combined, all_flow_points; fastd2=1.0f0)
checkpoint!("cpu_combined_flow_lattice_completed", matrix_stats(cpu_combined))
gpu_combined = gpu_measure_rows(gpu_bodies.combined, all_flow_points; fastd2=1.0f0)
checkpoint!("cuda_combined_flow_lattice_completed", matrix_stats(gpu_combined))
checkpoint!("full_flow_lattice_measurements", Dict(
    "cpu_candidate" => matrix_stats(cpu_candidate),
    "cuda_candidate" => matrix_stats(gpu_candidate),
    "cpu_ground" => matrix_stats(cpu_ground),
    "cuda_ground" => matrix_stats(gpu_ground),
    "cpu_combined" => matrix_stats(cpu_combined),
    "cuda_combined" => matrix_stats(gpu_combined),
))

checkpoint!("simulation_construction_started", Dict("dims" => collect(FLOW_DIMS)))
cpu_sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(cpu_bodies; T=Float32, mem=Array)
checkpoint!("cpu_simulation_constructed", Dict("dims" => collect(FLOW_DIMS)))
gpu_sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(gpu_bodies; T=Float32, mem=CuArray)
checkpoint!("cuda_simulation_constructed", Dict("dims" => collect(FLOW_DIMS)))
WaterLily.measure!(cpu_sim.flow, cpu_sim.body)
checkpoint!("cpu_measure_completed", Dict("method" => "WaterLily.measure!"))
checkpoint!("cuda_measure_started", Dict("method" => "WaterLily.measure!"))
WaterLily.measure!(gpu_sim.flow, gpu_sim.body)
CUDA.synchronize()
checkpoint!("cuda_measure_completed", Dict("method" => "WaterLily.measure!"))
cpu_initial = sim_field_snapshot(cpu_sim)
gpu_initial = sim_field_snapshot(gpu_sim)
cpu_after_diagnostics = raw_force_snapshot(cpu_sim, cpu_bodies.candidate)
gpu_after_diagnostics = raw_force_snapshot(gpu_sim, gpu_bodies.candidate)
checkpoint!("solver_free_measurement", Dict(
    "cpu_fields" => field_stats(cpu_initial),
    "cuda_fields" => field_stats(gpu_initial),
    "cpu_candidate_force" => cpu_after_diagnostics,
    "cuda_candidate_force" => gpu_after_diagnostics,
))

cpu_step_times = Float64[]
gpu_step_times = Float64[]
for _ in 1:TINY_REPETITIONS
    checkpoint!("cpu_one_step_started", Dict("step" => length(cpu_step_times) + 1))
    start = time()
    WaterLily.sim_step!(cpu_sim)
    push!(cpu_step_times, time() - start)
    checkpoint!("cpu_one_step_completed", Dict("steps" => length(cpu_step_times),
        "sim_time" => Float64(WaterLily.sim_time(cpu_sim))))
    checkpoint!("cuda_one_step_started", Dict("step" => length(gpu_step_times) + 1))
    start = time()
    WaterLily.sim_step!(gpu_sim)
    CUDA.synchronize()
    push!(gpu_step_times, time() - start)
    checkpoint!("cuda_one_step_completed", Dict("steps" => length(gpu_step_times),
        "sim_time" => Float64(WaterLily.sim_time(gpu_sim))))
end
cpu_after_one = sim_field_snapshot(cpu_sim)
gpu_after_one = sim_field_snapshot(gpu_sim)
cpu_one_force = raw_force_snapshot(cpu_sim, cpu_bodies.candidate)
gpu_one_force = raw_force_snapshot(gpu_sim, gpu_bodies.candidate)
checkpoint!("one_step_reproducer", Dict(
    "cpu_steps" => TINY_REPETITIONS,
    "cuda_steps" => TINY_REPETITIONS,
    "cpu_time" => Float64(WaterLily.sim_time(cpu_sim)),
    "cuda_time" => Float64(WaterLily.sim_time(gpu_sim)),
    "cpu_fields" => field_stats(cpu_after_one),
    "cuda_fields" => field_stats(gpu_after_one),
    "cpu_candidate_force" => cpu_one_force,
    "cuda_candidate_force" => gpu_one_force,
))

initial_lattice_path = joinpath(output_dir, "v16_flow_lattice.csv")
cpu_lattice_measures = Dict("candidate" => cpu_candidate, "ground" => cpu_ground,
    "combined" => cpu_combined)
gpu_lattice_measures = Dict("candidate" => gpu_candidate, "ground" => gpu_ground,
    "combined" => gpu_combined)
write_lattice_csv(initial_lattice_path, all_flow_points, cpu_lattice_measures,
    gpu_lattice_measures, cpu_initial, gpu_initial, FLOW_DIMS)

surface_world = (0.0f0, 0.0f0, 0.0f0)
surface_solver = flow_point(surface_world)
surface_probe = [surface_solver]
cpu_surface = cpu_measure_rows(cpu_bodies.candidate, surface_probe)
gpu_surface = gpu_measure_rows(gpu_bodies.candidate, surface_probe)
cpu_surface_combined = cpu_measure_rows(cpu_bodies.combined, surface_probe)
gpu_surface_combined = gpu_measure_rows(gpu_bodies.combined, surface_probe)

identity = Dict(
    "julia_version" => string(VERSION),
    "julia_threads" => Threads.nthreads(),
    "waterlily_version" => string(pkgversion(WaterLily)),
    "waterlily_backend" => string(WaterLily.backend),
    "cuda_jl_version" => string(pkgversion(CUDA)),
    "cuda_runtime_version" => string(CUDA.runtime_version()),
    "cuda_driver_version" => string(CUDA.driver_version()),
    "gpu_name" => CUDA.name(CUDA.device()),
    "gpu_uuid" => get(ENV, "W3_DIAGNOSTIC_SELECTED_GPU_UUID", ""),
    "cuda_visible_devices" => get(ENV, "CUDA_VISIBLE_DEVICES", ""),
    "gpu_count_visible" => length(CUDA.devices()),
)

device_array_type = string(typeof(device_grid.phi))
owner_array_type = string(typeof(device_owner.grid.phi))
device_body_isbits = isbitstype(typeof(gpu_bodies.candidate))
device_phi_isbits = isbitstype(typeof(device_grid.phi))

report = Dict{String,Any}(
    "evidence_type" => "diagnostic_only",
    "diagnostic_id" => "w3_v16_cuda_body_force_minimal_diagnostic_2026_09",
    "qualification_evidence" => false,
    "qualification_flags" => Dict(
        "waterlily_v16_primal_qualified" => false,
        "physical_profile_qualified" => false,
        "grid_response_qualified" => false,
        "sdf_gradient_qualified" => false,
        "waterlily_reverse_cpu_qualified" => false,
        "waterlily_reverse_cuda_qualified" => false,
        "topology_birth_qualified" => false,
        "shape_update_allowed" => false,
    ),
    "source_identity" => Dict(
        "w3_source_commit" => get(ENV, "W3_DIAGNOSTIC_W3_SOURCE_COMMIT", ""),
        "diagnostic_source_commit" => get(ENV, "W3_DIAGNOSTIC_SOURCE_COMMIT", ""),
        "diagnostic_job_sha256" => get(ENV, "W3_DIAGNOSTIC_JOB_SHA256", ""),
        "source_w3_job_sha256" => get(ENV, "W3_DIAGNOSTIC_W3_JOB_SHA256", ""),
        "project_sha256" => get(ENV, "W3_DIAGNOSTIC_PROJECT_SHA256", ""),
        "manifest_sha256" => get(ENV, "W3_DIAGNOSTIC_MANIFEST_SHA256", ""),
        "julia_archive_sha256" => get(ENV, "W3_DIAGNOSTIC_JULIA_SHA256", ""),
        "runner_sha256" => get(ENV, "W3_DIAGNOSTIC_RUNNER_SHA256", ""),
        "criteria_sha256" => get(ENV, "W3_DIAGNOSTIC_CRITERIA_SHA256", ""),
        "criteria_sidecar_sha256" => get(ENV, "W3_DIAGNOSTIC_CRITERIA_SIDECAR_SHA256", ""),
        "dataset_id" => get(ENV, "W3_DIAGNOSTIC_DATASET_ID", ""),
        "dataset_manifest_sha256" => get(ENV, "W3_DIAGNOSTIC_DATASET_MANIFEST_SHA256", ""),
    ),
    "input_identity" => Dict(
        "criteria_sha256" => get(ENV, "W3_DIAGNOSTIC_CRITERIA_SHA256", ""),
        "canonical_phi_fortran_sha256" => phi_fortran_sha,
        "canonical_phi_c_order_sha256" => phi_c_order_sha,
        "canonical_phi_column_major_bytes_sha256" => phi_fortran_sha,
        "device_roundtrip_sha256" => phi_roundtrip_sha,
        "cpu_measured_sdf_margin_m" => margin,
        "canonical_origin_m" => collect(canonical.origin),
        "flow_origin_m" => collect(FLOW_ORIGIN_M),
        "spacing_m" => SPACING_M,
        "point_shape" => collect(canonical.shape),
        "flow_dims" => collect(FLOW_DIMS),
        "canonical_state_sha256" => get(ENV, "W3_DIAGNOSTIC_STATE_SHA256", ""),
        "source_surface_sha256" => get(ENV, "W3_DIAGNOSTIC_SOURCE_SURFACE_SHA256", ""),
        "design_domain_sha256" => get(ENV, "W3_DIAGNOSTIC_DESIGN_DOMAIN_SHA256", ""),
    ),
    "runtime_identity" => identity,
    "device_representation" => Dict(
        "owner_type" => owner_array_type,
        "kernel_view_type" => device_array_type,
        "owner_array_isbits" => isbitstype(typeof(device_owner.grid.phi)),
        "kernel_view_isbits" => device_phi_isbits,
        "candidate_body_isbits" => device_body_isbits,
        "owner_kept_alive_across_diagnostic" => true,
        "note" => "The diagnostic explicitly roots the DeviceGridSDF owner while its CuDeviceArray view is queried; W3's run did not use GC.@preserve.",
    ),
    "v16_probe_results" => probe_body_results,
    "v16_flow_lattice" => Dict(
        "sample_count" => prod(FLOW_DIMS),
        "waterlily_location_contract" => "WaterLily.loc(0, CartesianIndex(i+1,j+1,k+1), Float32)",
        "cpu_candidate" => matrix_stats(cpu_candidate),
        "cuda_candidate" => matrix_stats(gpu_candidate),
        "candidate_cpu_cuda_comparison" => compare_rows(cpu_candidate, gpu_candidate; world_scale=SPACING_M),
        "cpu_ground" => matrix_stats(cpu_ground),
        "cuda_ground" => matrix_stats(gpu_ground),
        "ground_cpu_cuda_comparison" => compare_rows(cpu_ground, gpu_ground; world_scale=SPACING_M),
        "cpu_combined" => matrix_stats(cpu_combined),
        "cuda_combined" => matrix_stats(gpu_combined),
        "combined_cpu_cuda_comparison" => compare_rows(cpu_combined, gpu_combined; world_scale=SPACING_M),
        "flow_lattice_csv" => basename(initial_lattice_path),
        "flow_lattice_csv_sha256" => bytes2hex(sha256(read(initial_lattice_path))),
    ),
    "v16_solver_free_measurement" => Dict(
        "solver_steps" => 0,
        "cpu_initial_flow_fields" => field_stats(cpu_initial),
        "cuda_initial_flow_fields" => field_stats(gpu_initial),
        "cpu_cuda_initial_flow_field_difference" => field_difference(cpu_initial, gpu_initial),
        "cpu_candidate_force_before_step" => cpu_after_diagnostics,
        "cuda_candidate_force_before_step" => gpu_after_diagnostics,
        "candidate_world_probe_0_0_0_solver" => collect(surface_solver),
        "candidate_cpu_measure_world_0_0_0" => collect(cpu_surface[1, :]),
        "candidate_cuda_measure_world_0_0_0" => collect(gpu_surface[1, :]),
        "combined_cpu_measure_world_0_0_0" => collect(cpu_surface_combined[1, :]),
        "combined_cuda_measure_world_0_0_0" => collect(gpu_surface_combined[1, :]),
    ),
    "v16_one_step_reproducer" => Dict(
        "cpu_solver_steps" => TINY_REPETITIONS,
        "cuda_solver_steps" => TINY_REPETITIONS,
        "cpu_step_wall_seconds" => cpu_step_times,
        "cuda_step_wall_seconds" => gpu_step_times,
        "cpu_time_after_steps" => Float64(WaterLily.sim_time(cpu_sim)),
        "cuda_time_after_steps" => Float64(WaterLily.sim_time(gpu_sim)),
        "cpu_fields_after_one_step" => field_stats(cpu_after_one),
        "cuda_fields_after_one_step" => field_stats(gpu_after_one),
        "cpu_cuda_field_difference_after_one_step" => field_difference(cpu_after_one, gpu_after_one),
        "cpu_candidate_force_after_one_step" => cpu_one_force,
        "cuda_candidate_force_after_one_step" => gpu_one_force,
    ),
    "w2b_sphere_control" => Dict("status" => "pending"),
    "interpretation" => "Raw CPU/CUDA measurements only. No W3 acceptance gate is evaluated and no solver result is qualified.",
)

GC.@preserve device_owner begin
    checkpoint!("w2b_sphere_control_started", Dict("phi_sha256" => EXPECTED_SPHERE_PHI_SHA256))
    sphere_owner, sphere_report = sphere_body_probe()
    report["w2b_sphere_control"] = sphere_report
    GC.@preserve sphere_owner begin
        checkpoint!("w2b_sphere_control_completed", sphere_report)
        write(joinpath(output_dir, "w3_v16_cuda_diagnostic.json"), json_value(report) * "\n")
    end
end
checkpoint!("diagnostic_report_written", Dict(
    "report_sha256" => bytes2hex(sha256(read(joinpath(output_dir, "w3_v16_cuda_diagnostic.json")))),
    "flow_lattice_csv_sha256" => bytes2hex(sha256(read(initial_lattice_path))),
    "qualification_evidence" => false,
))

println("W3_V16_CUDA_DIAGNOSTIC_DONE ", json_value(Dict(
    "solver_steps_v16" => TINY_REPETITIONS,
    "candidate_force_support_gpu" => report["v16_flow_lattice"]["cuda_candidate"]["force_support_abs_d_le_1_count"],
    "candidate_force_support_cpu" => report["v16_flow_lattice"]["cpu_candidate"]["force_support_abs_d_le_1_count"],
    "diagnostic_json" => joinpath(output_dir, "w3_v16_cuda_diagnostic.json"),
)))
