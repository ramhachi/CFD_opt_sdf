# Diagnostic-only retained / unrooted / structurally-owned v16 CUDA fixture.
# One arm per Julia process so a dangling-view CUDA failure cannot erase prior
# arm artifacts or prevent the second unrooted replicate from running.

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
using .CFDSDFWaterLily: build_v16_physical_profile_simulation,
    v16_physical_profile_bodies

length(ARGS) == 3 || error("usage: owner_lifetime_job.jl <phi_fortran.raw> <output_dir> <arm_id>")
phi_raw_path, output_dir, arm_id = ARGS
arm_id in ("A", "C", "B1", "B2") || error("unknown arm id: $arm_id")
mkpath(output_dir)

const FLOW_DIMS = (100, 48, 36)
const SPACING_M = 0.05f0
const FLOW_ORIGIN_M = Float32.((-2.5, -1.2, -0.9))
const EXPECTED_PHI_SHA256 = "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
const EXPECTED_PHI_C_ORDER_SHA256 = "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
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

function write_json_atomic(path, value)
    temporary = string(path, ".tmp")
    write(temporary, json_value(value), "\n")
    mv(temporary, path; force=true)
end

const REPORT = Dict{String,Any}()
function checkpoint!(stage, values=Dict{String,Any}())
    REPORT["last_stage"] = stage
    REPORT["checkpoint_values"] = values
    write_json_atomic(joinpath(output_dir, "w3_v16_cuda_owner_progress_$(arm_id).json"), REPORT)
    write_json_atomic(joinpath(output_dir, "w3_v16_cuda_owner_lifetime_$(arm_id).json"), REPORT)
    println("W3_OWNER_LIFETIME_STAGE ", arm_id, " ", stage, " ", json_value(values))
end

function load_canonical_grid(path)
    bytes = read(path)
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_SHA256 || error("canonical phi SHA mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), CFDSDFWaterLily.V16_PROFILE_POINT_SHAPE)
    c_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_sha == EXPECTED_PHI_C_ORDER_SHA256 || error("canonical C-order phi SHA mismatch")
    grid = GridSDF(phi; origin=CFDSDFWaterLily.V16_CANONICAL_SDF_ORIGIN_M,
        h=(0.05, 0.05, 0.05), outside_value=3.0, margin_m=0.15)
    return grid, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), c_sha,
        zero_level_margin_m(phi, grid.origin, grid.h)
end

function build_components(canonical)
    owner = device_copy(canonical)
    roundtrip_sha = device_roundtrip_sha(owner)
    device_grid = kernel_grid(owner)
    bodies = v16_physical_profile_bodies(device_grid; T=Float32)
    sim = build_v16_physical_profile_simulation(bodies; T=Float32, mem=CuArray)
    return owner, device_grid, bodies, sim, roundtrip_sha
end

struct OwnedV16Diagnostic{O,B,S}
    owner::O
    bodies::B
    sim::S
end

# Keep the helper boundary real: B must not return a strong owner/view reference.
Base.@noinline function build_unrooted_components(canonical)
    owner, device_grid, bodies, sim, roundtrip_sha = build_components(canonical)
    owner_weakref = WeakRef(owner.grid.phi)
    info = Dict(
        "owner_type" => string(typeof(owner.grid.phi)),
        "weakref_target_path" => "owner.grid.phi",
        "weakref_target_type" => string(typeof(owner.grid.phi)),
        "kernel_view_type" => string(typeof(device_grid.phi)),
        "owner_array_isbits" => isbitstype(typeof(owner.grid.phi)),
        "kernel_view_isbits" => isbitstype(typeof(device_grid.phi)),
        "candidate_body_isbits" => isbitstype(typeof(bodies.candidate)),
        "gpu_phi_roundtrip_sha256" => roundtrip_sha,
        "unrooted_automatic_gc_disabled_until_forced_gc" => true,
    )
    # Suppress only automatic GC until the registered forced-GC bracket.
    # The owner itself is not returned and remains unrooted.
    gc_was_enabled = GC.enable(false)
    gc_was_enabled || error("automatic GC was already disabled before unrooted bracket")
    info["automatic_gc_was_enabled_before_unrooted_bracket"] = gc_was_enabled
    return bodies, sim, owner_weakref, info
end

function representative_probes(grid)
    phi = grid.phi
    solid_idx = CartesianIndices(phi)[argmin(vec(phi))]
    surface_idx = CartesianIndices(phi)[argmin(abs.(vec(phi)))]
    positive_linear = 0
    positive_value = Inf32
    for linear_index in eachindex(phi)
        value = phi[linear_index]
        if 0.0f0 < value < positive_value
            positive_value = value
            positive_linear = linear_index
        end
    end
    positive_linear > 0 || error("canonical phi has no positive sample")
    positive_ci = CartesianIndices(phi)[positive_linear]
    world(index) = ntuple(axis -> Float32(grid.origin[axis] + (index[axis] - 1) * grid.h[axis]), 3)
    return [
        ("candidate_solid_min_phi", world(solid_idx)),
        ("candidate_surface_min_abs_phi", world(surface_idx)),
        ("candidate_nearest_positive_phi", world(positive_ci)),
        ("registered_world_center", (0.0f0, 0.0f0, 0.0f0)),
        ("outside_x_low", (-1.05f0, 0.0f0, 0.0f0)),
        ("outside_x_high", (2.05f0, 0.0f0, 0.0f0)),
        ("outside_y_low", (0.0f0, -0.85f0, 0.0f0)),
        ("outside_y_high", (0.0f0, 0.85f0, 0.0f0)),
        ("outside_z_low", (0.0f0, 0.0f0, -0.65f0)),
        ("outside_z_high", (0.0f0, 0.0f0, 0.65f0)),
    ]
end

flow_point(world) = WaterLily.SVector{3,Float32}(
    (Float32(world[1]) - FLOW_ORIGIN_M[1]) / SPACING_M,
    (Float32(world[2]) - FLOW_ORIGIN_M[2]) / SPACING_M,
    (Float32(world[3]) - FLOW_ORIGIN_M[3]) / SPACING_M)

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

function cpu_measure_rows(body, points)
    rows = Matrix{Float32}(undef, length(points), 7)
    for i in eachindex(points)
        d, n, velocity = WaterLily.measure(body, points[i], 0.0f0; fastd²=Inf32)
        rows[i, :] .= (d, n[1], n[2], n[3], velocity[1], velocity[2], velocity[3])
    end
    return rows
end

function gpu_measure_rows(body, points)
    gpu_points = CuArray(points)
    output = CuArray{Float32}(undef, length(points), 7)
    kernel! = diagnostic_measure_kernel!(get_backend(output), 128)
    kernel!(output, body, gpu_points, Inf32; ndrange=length(points))
    CUDA.synchronize()
    return Array(output)
end

function row_stats(rows)
    d = @view rows[:, 1]
    norms = [sqrt(sum(abs2, @view rows[i, 2:4])) for i in axes(rows, 1)]
    support = findall(value -> abs(value) <= 1.0f0, d)
    return Dict(
        "sample_count" => length(d),
        "finite_value_count" => count(isfinite, d),
        "negative_distance_count" => count(<(0.0f0), d),
        "support_abs_d_le_1_count" => length(support),
        "bdim_abs_d_le_3_count" => count(value -> abs(value) <= 3.0f0, d),
        "min_distance_solver_units" => minimum(d),
        "max_distance_solver_units" => maximum(d),
        "nonzero_normal_count" => count(value -> value > 0.0f0, norms),
        "normal_magnitude_min" => minimum(norms),
        "normal_magnitude_max" => maximum(norms),
        "normal_magnitude_mean" => sum(norms) / length(norms),
        "all_values_finite" => all(isfinite, rows),
    )
end

function probe_rows(cpu_bodies, gpu_bodies, probe_list)
    points = [flow_point(point[2]) for point in probe_list]
    records = Dict{String,Any}()
    for name in ("candidate", "combined")
        cpu = cpu_measure_rows(getproperty(cpu_bodies, Symbol(name)), points)
        gpu = gpu_measure_rows(getproperty(gpu_bodies, Symbol(name)), points)
        records[name] = [Dict(
            "name" => probe_list[i][1],
            "world_m" => collect(probe_list[i][2]),
            "flow_solver" => collect(points[i]),
            "cpu_measure" => collect(cpu[i, :]),
            "cuda_measure" => collect(gpu[i, :]),
        ) for i in eachindex(probe_list)]
    end
    return records
end

function flow_grid_points()
    points = Vector{WaterLily.SVector{3,Float32}}(undef, prod(FLOW_DIMS))
    n = 0
    for k in 1:FLOW_DIMS[3], j in 1:FLOW_DIMS[2], i in 1:FLOW_DIMS[1]
        n += 1
        points[n] = WaterLily.loc(0, CartesianIndex(i + 1, j + 1, k + 1), Float32)
    end
    return points
end

function normal_error_examples(grid, points, cpu, gpu; n=5)
    errors = [sqrt(sum(abs2, cpu[i, 2:4] .- gpu[i, 2:4])) for i in eachindex(points)]
    selected = sortperm(errors; rev=true)[1:min(n, length(errors))]
    examples = Dict{String,Any}[]
    for row in selected
        solver = points[row]
        world = ntuple(axis -> Float32(FLOW_ORIGIN_M[axis] + SPACING_M * solver[axis]), 3)
        coord = ntuple(axis -> (world[axis] - Float32(grid.origin[axis])) / Float32(grid.h[axis]), 3)
        inside = all(axis -> 0.0f0 <= coord[axis] <= Float32(grid.shape[axis] - 1), 1:3)
        neighborhood = nothing
        cell = nothing
        distance_to_zero_m = Float32(abs(cpu[row, 1]) * SPACING_M)
        if inside
            base = ntuple(axis -> clamp(floor(Int, coord[axis]) + 1, 1, grid.shape[axis] - 1), 3)
            cell = collect(base)
            neighborhood = [[[Float32(grid.phi[base[1] + i, base[2] + j, base[3] + k])
                for k in 0:1] for j in 0:1] for i in 0:1]
        end
        push!(examples, Dict(
            "flow_solver" => collect(solver),
            "world_m" => collect(world),
            "distance_m" => Float64(cpu[row, 1] * SPACING_M),
            "distance_to_zero_level_m" => Float64(distance_to_zero_m),
            "cpu_normal" => Float64.(cpu[row, 2:4]),
            "cuda_normal" => Float64.(gpu[row, 2:4]),
            "normal_vector_error" => Float64(errors[row]),
            "interpolation_cell_1based" => cell,
            "local_phi_neighborhood_2x2x2" => neighborhood,
        ))
    end
    return examples
end

function write_geometry_artifact(path, arrays)
    layout = Dict{String,Any}()
    offset = 0
    open(path, "w") do io
        for (name, rows) in arrays
            values = vec(Matrix{Float32}(rows))
            bytes = reinterpret(UInt8, values)
            write(io, bytes)
            layout[name] = Dict(
                "offset_bytes" => offset,
                "nbytes" => length(bytes),
                "shape" => collect(size(rows)),
                "dtype" => "<f4",
                "order" => "F",
                "sha256" => bytes2hex(sha256(bytes)),
            )
            offset += length(bytes)
        end
    end
    return layout, bytes2hex(sha256(read(path)))
end

function field_snapshot(sim)
    return (
        u=Array(sim.flow.u),
        p=Array(sim.flow.p),
        sigma=Array(sim.flow.σ),
        mu0=Array(sim.flow.μ₀),
        body_velocity=Array(sim.flow.V),
    )
end

function field_stats(array)
    values = Float32.(array)
    return Dict(
        "shape" => collect(size(values)),
        "finite_count" => count(isfinite, values),
        "nonzero_count" => count(!iszero, values),
        "max_abs" => maximum(abs, values),
        "array_sha256" => bytes2hex(sha256(reinterpret(UInt8, vec(values)))),
    )
end

function field_summary(snapshot)
    return Dict(name => field_stats(getproperty(snapshot, Symbol(name)))
        for name in ("u", "p", "sigma", "mu0", "body_velocity"))
end

function write_field_artifact(path, snapshot)
    layout = Dict{String,Any}()
    offset = 0
    open(path, "w") do io
        for name in ("u", "p", "sigma", "mu0", "body_velocity")
            values = vec(Float32.(getproperty(snapshot, Symbol(name))))
            bytes = reinterpret(UInt8, values)
            write(io, bytes)
            layout[name] = Dict(
                "offset_bytes" => offset,
                "nbytes" => length(bytes),
                "shape" => collect(size(getproperty(snapshot, Symbol(name)))),
                "dtype" => "<f4",
                "order" => "F",
                "sha256" => bytes2hex(sha256(bytes)),
            )
            offset += length(bytes)
        end
    end
    return layout, bytes2hex(sha256(read(path)))
end

function force_snapshot(sim, body)
    pressure = Float64.(WaterLily.pressure_force(sim.flow, body))
    viscous = Float64.(WaterLily.viscous_force(sim.flow, body))
    total = pressure + viscous
    return Dict(
        "solver_time" => Float64(WaterLily.sim_time(sim)),
        "waterlily_pressure_force_raw" => pressure,
        "waterlily_viscous_force_raw" => viscous,
        "waterlily_total_force_raw" => total,
        "body_pressure_force" => -pressure,
        "body_viscous_force" => -viscous,
        "body_total_force" => -total,
        "registered_drag_plus_fx_body" => -total[1],
        "registered_downforce_minus_fz_body" => total[3],
    )
end

function backend_identity()
    return Dict(
        "julia_version" => string(VERSION),
        "julia_threads" => Threads.nthreads(),
        "waterlily_version" => string(pkgversion(WaterLily)),
        "waterlily_backend" => string(WaterLily.backend),
        "cuda_jl_version" => string(pkgversion(CUDA)),
        "cuda_runtime_version" => string(CUDA.runtime_version()),
        "cuda_driver_api_version" => string(CUDA.driver_version()),
        "gpu_name" => CUDA.name(CUDA.device()),
        "gpu_uuid" => get(ENV, "W3_DIAGNOSTIC_SELECTED_GPU_UUID", ""),
        "cuda_visible_devices" => get(ENV, "CUDA_VISIBLE_DEVICES", ""),
        "visible_gpu_count" => length(CUDA.devices()),
    )
end

function owner_weak_state(weak)
    return weak.value === nothing ? "cleared" : "alive"
end

function run_observations!(canonical, cpu_bodies, gpu_bodies, sim, weak, strategy)
    probes = representative_probes(canonical)
    REPORT["ownership"]["weakref_before_pre_gc_observations"] = owner_weak_state(weak)
    stage = "fixed_probes_before_gc_started"
    checkpoint!(stage)
    if strategy == "unrooted" && owner_weak_state(weak) == "cleared"
        REPORT["fixed_probes_before_gc"] = Dict("skipped" => "owner weak reference had already cleared")
    else
        REPORT["fixed_probes_before_gc"] = probe_rows(cpu_bodies, gpu_bodies, probes)
    end
    checkpoint!("fixed_probes_before_gc_completed")

    stage = "measure_before_gc_started"
    checkpoint!(stage)
    if strategy == "unrooted" && owner_weak_state(weak) == "cleared"
        REPORT["after_measure_before_gc"] = Dict("skipped" => "owner weak reference had already cleared")
    else
        WaterLily.measure!(sim.flow, sim.body)
        CUDA.synchronize()
        before_fields = field_summary(field_snapshot(sim))
        before_force = force_snapshot(sim, gpu_bodies.candidate)
        REPORT["after_measure_before_gc"] = Dict(
            "fields" => before_fields,
            "candidate_force" => before_force,
        )
    end
    checkpoint!("measure_before_gc_completed")

    REPORT["ownership"]["weakref_before_gc"] = owner_weak_state(weak)
    REPORT["ownership"]["full_gc_calls"] = 0
    REPORT["ownership"]["cuda_synchronize_before_gc"] = true
    CUDA.synchronize()
    for gc_index in 1:2
        stage = "full_gc_$(gc_index)_started"
        checkpoint!(stage)
        strategy == "unrooted" && GC.enable(true)
        GC.gc(true)
        CUDA.synchronize()
        REPORT["ownership"]["full_gc_calls"] = gc_index
        weak_state = owner_weak_state(weak)
        strategy == "unrooted" && push!(
            REPORT["ownership"]["automatic_gc_reenabled_before_each_forced_gc"], true)
        strategy == "unrooted" && gc_index == 1 && GC.enable(false)
        push!(REPORT["ownership"]["weakref_after_each_gc"], weak_state)
        checkpoint!("full_gc_$(gc_index)_completed", Dict(
            "weakref_state" => weak_state,
            "cuda_synchronize_after_gc" => true,
        ))
    end
    REPORT["ownership"]["cuda_synchronize_after_gc"] = true
    REPORT["ownership"]["weakref_after_gc"] = owner_weak_state(weak)
    REPORT["ownership"]["owner_collected_during_forced_gc"] =
        REPORT["ownership"]["weakref_before_gc"] == "alive" &&
        REPORT["ownership"]["weakref_after_gc"] == "cleared"

    stage = "fixed_probes_after_gc_started"
    checkpoint!(stage)
    after_probes = probe_rows(cpu_bodies, gpu_bodies, probes)
    REPORT["fixed_probes_after_gc"] = after_probes
    checkpoint!("fixed_probes_after_gc_completed")

    stage = "full_grid_geometry_started"
    checkpoint!(stage, Dict("flow_dims" => collect(FLOW_DIMS)))
    points = flow_grid_points()
    geometry_arrays = Dict{String,Matrix{Float32}}()
    geometry_stats = Dict{String,Any}()
    for name in ("candidate", "combined")
        cpu_rows = cpu_measure_rows(getproperty(cpu_bodies, Symbol(name)), points)
        cuda_rows = gpu_measure_rows(getproperty(gpu_bodies, Symbol(name)), points)
        geometry_arrays["$(name)_cpu"] = cpu_rows
        geometry_arrays["$(name)_cuda"] = cuda_rows
        geometry_stats["$(name)_cpu"] = row_stats(cpu_rows)
        geometry_stats["$(name)_cuda"] = row_stats(cuda_rows)
        if name == "candidate"
            error_vector = [sqrt(sum(abs2, cpu_rows[i, 2:4] .- cuda_rows[i, 2:4]))
                for i in axes(cpu_rows, 1)]
            geometry_stats["candidate_cpu_cuda_max_distance_error_m"] =
                Float64(maximum(abs.(cpu_rows[:, 1] .- cuda_rows[:, 1])) * SPACING_M)
            geometry_stats["candidate_cpu_cuda_max_normal_vector_error"] = Float64(maximum(error_vector))
            geometry_stats["candidate_cpu_cuda_normal_error_examples"] =
                normal_error_examples(canonical, points, cpu_rows, cuda_rows)
        end
    end
    geometry_path = joinpath(output_dir, "w3_v16_cuda_owner_geometry_$(arm_id).f32")
    geometry_layout, geometry_sha = write_geometry_artifact(geometry_path, geometry_arrays)
    REPORT["full_grid_geometry"] = Dict(
        "flow_dims" => collect(FLOW_DIMS),
        "sample_count" => prod(FLOW_DIMS),
        "candidate_and_combined" => geometry_stats,
        "artifact" => basename(geometry_path),
        "artifact_sha256" => geometry_sha,
        "layout" => geometry_layout,
    )
    checkpoint!("full_grid_geometry_completed", Dict(
        "sample_count" => prod(FLOW_DIMS),
        "artifact_sha256" => geometry_sha,
    ))

    stage = "measure_after_gc_started"
    checkpoint!(stage)
    WaterLily.measure!(sim.flow, sim.body)
    CUDA.synchronize()
    post_fields = field_snapshot(sim)
    post_force = force_snapshot(sim, gpu_bodies.candidate)
    field_stages = Dict{String,Any}("after_measure_after_gc" => field_summary(post_fields))
    haskey(REPORT["after_measure_before_gc"], "fields") &&
        (field_stages["after_measure_before_gc"] = REPORT["after_measure_before_gc"]["fields"])
    forces = Dict{String,Any}(
        "step0_after_gc" => post_force,
    )
    haskey(REPORT["after_measure_before_gc"], "candidate_force") &&
        (forces["step0_before_gc"] = REPORT["after_measure_before_gc"]["candidate_force"])
    REPORT["simulation_fields"] = field_stages
    REPORT["force_history"] = forces
    checkpoint!("measure_after_gc_completed")
    for step in 1:2
        stage = "primal_step_$(step)_started"
        checkpoint!(stage)
        WaterLily.sim_step!(sim)
        CUDA.synchronize()
        fields = field_snapshot(sim)
        field_stages["after_step$(step)"] = field_summary(fields)
        forces["step$(step)"] = force_snapshot(sim, gpu_bodies.candidate)
        checkpoint!("primal_step_$(step)_completed", Dict(
            "solver_time" => Float64(WaterLily.sim_time(sim)),
            "candidate_force" => forces["step$(step)"],
        ))
        REPORT["simulation_fields"] = field_stages
        REPORT["force_history"] = forces
        if step == 2
            fields_path = joinpath(output_dir, "w3_v16_cuda_owner_fields_$(arm_id).f32")
            fields_layout, fields_sha = write_field_artifact(fields_path, fields)
            REPORT["simulation_fields_artifact"] = Dict(
                "artifact" => basename(fields_path),
                "artifact_sha256" => fields_sha,
                "layout" => fields_layout,
            )
        end
    end
    REPORT["simulation_fields"] = field_stages
    REPORT["force_history"] = forces
    REPORT["status"] = "completed"
    REPORT["failed_stage"] = nothing
    REPORT["exact_exception"] = nothing
    checkpoint!("arm_completed", Dict("solver_steps" => 2))
    report_path = joinpath(output_dir, "w3_v16_cuda_owner_lifetime_$(arm_id).json")
    write_json_atomic(report_path, REPORT)
    println("W3_OWNER_LIFETIME_ARM_DONE ", arm_id, " ", basename(report_path))
end

function main()
    stage = "canonical_input_load_started"
    checkpoint!(stage)
    canonical, phi_fortran_sha, phi_c_sha, margin = load_canonical_grid(phi_raw_path)
    cpu_bodies = v16_physical_profile_bodies(canonical; T=Float32)
    REPORT["input_identity"] = Dict(
        "canonical_phi_fortran_sha256" => phi_fortran_sha,
        "canonical_phi_c_order_sha256" => phi_c_sha,
        "canonical_state_sha256" => get(ENV, "W3_DIAGNOSTIC_STATE_SHA256", ""),
        "cpu_measured_sdf_margin_m" => margin,
        "canonical_origin_m" => collect(canonical.origin),
        "spacing_m" => SPACING_M,
        "point_shape" => collect(canonical.shape),
        "flow_origin_m" => collect(FLOW_ORIGIN_M),
        "flow_dims" => collect(FLOW_DIMS),
        "gpu_phi_roundtrip_sha256" => nothing,
    )
    REPORT["source_identity"] = Dict(
        "owner_criteria_sha256" => get(ENV, "W3_OWNER_CRITERIA_SHA256", ""),
        "owner_criteria_sidecar_sha256" => get(ENV, "W3_OWNER_CRITERIA_SIDECAR_SHA256", ""),
        "owner_job_sha256" => get(ENV, "W3_OWNER_JOB_SHA256", ""),
        "diagnostic_source_commit" => get(ENV, "W3_DIAGNOSTIC_SOURCE_COMMIT", ""),
        "diagnostic_job_sha256" => get(ENV, "W3_DIAGNOSTIC_JOB_SHA256", ""),
        "source_w3_job_sha256" => get(ENV, "W3_DIAGNOSTIC_W3_JOB_SHA256", ""),
        "project_sha256" => get(ENV, "W3_DIAGNOSTIC_PROJECT_SHA256", ""),
        "manifest_sha256" => get(ENV, "W3_DIAGNOSTIC_MANIFEST_SHA256", ""),
        "julia_archive_sha256" => get(ENV, "W3_DIAGNOSTIC_JULIA_SHA256", ""),
        "runner_sha256" => get(ENV, "W3_DIAGNOSTIC_RUNNER_SHA256", ""),
        "dataset_id" => get(ENV, "W3_DIAGNOSTIC_DATASET_ID", ""),
        "dataset_manifest_sha256" => get(ENV, "W3_DIAGNOSTIC_DATASET_MANIFEST_SHA256", ""),
    )
    REPORT["arm_id"] = arm_id
    REPORT["input_identity"]["canonical_phi_fortran_sha256"] == EXPECTED_PHI_SHA256 || error("input phi identity mismatch")
    REPORT["input_identity"]["gpu_phi_roundtrip_sha256"] = nothing
    REPORT["qualification_evidence"] = false
    REPORT["qualification_flags"] = Dict(
        "waterlily_v16_primal_qualified" => false,
        "physical_profile_qualified" => false,
        "grid_response_qualified" => false,
        "sdf_gradient_qualified" => false,
        "waterlily_reverse_cpu_qualified" => false,
        "waterlily_reverse_cuda_qualified" => false,
        "topology_birth_qualified" => false,
        "shape_update_allowed" => false,
    )
    REPORT["runtime_identity"] = backend_identity()
    REPORT["ownership"] = Dict(
        "strategy" => arm_id == "A" ? "GC.@preserve owner" :
            arm_id == "C" ? "OwnedV16Diagnostic owns owner,bodies,simulation" :
            "helper returns bodies,simulation,WeakRef only",
        "owner_type" => nothing,
        "weakref_target_path" => nothing,
        "weakref_target_type" => nothing,
        "kernel_view_type" => nothing,
        "owner_array_isbits" => nothing,
        "kernel_view_isbits" => nothing,
        "candidate_body_isbits" => nothing,
        "weakref_created" => true,
        "weakref_before_gc" => nothing,
        "weakref_after_each_gc" => Any[],
        "weakref_after_gc" => nothing,
        "automatic_gc_reenabled_before_each_forced_gc" => Any[],
        "unrooted_automatic_gc_disabled_until_forced_gc" => false,
        "owner_collected_during_forced_gc" => false,
        "full_gc_calls" => 0,
        "cuda_synchronize_before_gc" => false,
        "cuda_synchronize_after_gc" => false,
        "strong_owner_reference_escaped_helper" => arm_id != "B1" && arm_id != "B2",
    )
    REPORT["status"] = "running"
    REPORT["qualification_evidence"] = false
    REPORT["claim_scope"] = "diagnostic-only CUDA owner-lifetime experiment; not W3 qualification or a production fix"

    if arm_id == "A"
        owner, device_grid, bodies, sim, roundtrip = build_components(canonical)
        REPORT["input_identity"]["gpu_phi_roundtrip_sha256"] = roundtrip
        REPORT["ownership"]["owner_type"] = string(typeof(owner.grid.phi))
        REPORT["ownership"]["weakref_target_path"] = "owner.grid.phi"
        REPORT["ownership"]["weakref_target_type"] = string(typeof(owner.grid.phi))
        REPORT["ownership"]["kernel_view_type"] = string(typeof(device_grid.phi))
        REPORT["ownership"]["owner_array_isbits"] = isbitstype(typeof(owner.grid.phi))
        REPORT["ownership"]["kernel_view_isbits"] = isbitstype(typeof(device_grid.phi))
        REPORT["ownership"]["candidate_body_isbits"] = isbitstype(typeof(bodies.candidate))
        weak = WeakRef(owner.grid.phi)
        GC.@preserve owner begin
            run_observations!(canonical, cpu_bodies, bodies, sim, weak, "retained")
        end
    elseif arm_id == "C"
        owner, device_grid, bodies, sim, roundtrip = build_components(canonical)
        owned = OwnedV16Diagnostic(owner, bodies, sim)
        REPORT["input_identity"]["gpu_phi_roundtrip_sha256"] = roundtrip
        REPORT["ownership"]["owner_type"] = string(typeof(owned.owner.grid.phi))
        REPORT["ownership"]["weakref_target_path"] = "owner.grid.phi"
        REPORT["ownership"]["weakref_target_type"] = string(typeof(owned.owner.grid.phi))
        REPORT["ownership"]["kernel_view_type"] = string(typeof(device_grid.phi))
        REPORT["ownership"]["owner_array_isbits"] = isbitstype(typeof(owned.owner.grid.phi))
        REPORT["ownership"]["kernel_view_isbits"] = isbitstype(typeof(device_grid.phi))
        REPORT["ownership"]["candidate_body_isbits"] = isbitstype(typeof(owned.bodies.candidate))
        weak = WeakRef(owned.owner.grid.phi)
        GC.@preserve owned begin
            run_observations!(canonical, cpu_bodies, owned.bodies, owned.sim, weak, "owned")
        end
    else
        bodies, sim, weak, info = build_unrooted_components(canonical)
        REPORT["input_identity"]["gpu_phi_roundtrip_sha256"] = info["gpu_phi_roundtrip_sha256"]
        for key in ("owner_type", "weakref_target_path", "weakref_target_type",
                    "kernel_view_type", "owner_array_isbits", "kernel_view_isbits",
                    "candidate_body_isbits", "unrooted_automatic_gc_disabled_until_forced_gc",
                    "automatic_gc_was_enabled_before_unrooted_bracket")
            REPORT["ownership"][key] = info[key]
        end
        run_observations!(canonical, cpu_bodies, bodies, sim, weak, "unrooted")
    end
end

try
    main()
catch error
    REPORT["status"] = "operation_error"
    REPORT["failed_stage"] = get(REPORT, "last_stage", "before_first_checkpoint")
    REPORT["exact_exception"] = sprint(showerror, error, catch_backtrace())
    path = joinpath(output_dir, "w3_v16_cuda_owner_lifetime_$(arm_id).json")
    write_json_atomic(path, REPORT)
    println("W3_OWNER_LIFETIME_ARM_ERROR ", arm_id, " ", json_value(Dict(
        "failed_stage" => REPORT["failed_stage"],
        "exception" => REPORT["exact_exception"],
    )))
finally
    GC.enable(true)
end
