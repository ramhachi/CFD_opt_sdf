# Registered criteria-bound 33-run centered directional-FD measurement.

const CPU_PRESTEP = get(ENV, "FD_CPU_PRESTEP", "0") == "1"
if !CPU_PRESTEP
    @eval using CUDA
end
using Printf
using SHA
using WaterLily

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16W4Sensitivity.jl"))
if !CPU_PRESTEP
    Base.include(CFDSDFWaterLily,
        joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
    @eval using .CFDSDFWaterLily.DeviceGridSDF
end
using .CFDSDFWaterLily: GridSDFWaterLilyBody, V16_PROFILE_POINT_SHAPE,
    V16_CANONICAL_SDF_ORIGIN_M, V16_PROFILE_SPACING_M, V16MovingGroundBody,
    v16_native_far_field_uBC
using .CFDSDFWaterLily.V16W4Sensitivity: w4_cases, validate_w4_case
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "OwnedV16Run.jl"))
using .CFDSDFW3RunOwnership: OwnedV16Run

length(ARGS) == 3 || error("usage: waterlily_sdf_directional_fd_v16_job.jl <dataset_dir> <run_queue.tsv> <output_dir>")
dataset_dir, queue_path, output_dir = ARGS

const STATE_LABEL = get(ENV, "FD_STATE_LABEL", "v16")
# n = g/max(|g|, NORMAL_FLOOR); 0 keeps the historical bridge (all criteria before FD-06)
const NORMAL_FLOOR = parse(Float64, get(ENV, "FD_NORMAL_FLOOR", "0.0"))
const EXPECTED_STATE_SHA = get(ENV, "FD_STATE_SHA256", "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8")
const EXPECTED_PHI_C_SHA = get(ENV, "FD_PHI_C_ORDER_SHA256", "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785")
const EXPECTED_PHI_F_SHA = get(ENV, "FD_PHI_FORTRAN_SHA256", "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7")
const EXPECTED_SOURCE_SHA = get(ENV, "FD_SOURCE_SURFACE_SHA256", "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11")
const point_shape_from_env = Tuple(parse.(Int, split(get(ENV, "FD_POINT_SHAPE", "61,33,25"), ",")))
const sdf_origin_from_env = Tuple(parse.(Float64, split(get(ENV, "FD_SDF_ORIGIN_M", "-1,-0.8,-0.6"), ",")))
const sdf_spacing_from_env = parse(Float64, get(ENV, "FD_SDF_SPACING_M", "0.05"))
const EXPECTED_FLOW_ORIGIN = Tuple(parse.(Float64, split(get(ENV, "FD_FLOW_ORIGIN_M", "-2.5,-1.2,-0.9"), ",")))
const OUTSIDE_VALUE = 3.0
const REQUIRED_MARGIN = parse(Float64, get(ENV, "FD_MARGIN_GATE_M", "0.15"))
const EXPECTED_MARGIN = parse(Float64, get(ENV, "FD_EXPECTED_MARGIN_M", "0.3499999939931499"))
const MARGIN_TOL = 1e-6
const T_END = parse(Float64, get(ENV, "FD_T_END", "120.0"))
const BURN_IN = parse(Float64, get(ENV, "FD_BURN_IN", "80.0"))
const WINDOW_START = parse(Float64, get(ENV, "FD_WINDOW_START", "80.0"))
const WINDOW_END = parse(Float64, get(ENV, "FD_WINDOW_END", "120.0"))
const STATIONARITY_SPLIT = parse(Float64, get(ENV, "FD_STATIONARITY_SPLIT", "100.0"))
const SAMPLE_EVERY = parse(Int, get(ENV, "FD_SAMPLE_EVERY", "8"))
const FLOW_CASE_ID = get(ENV, "FD_FLOW_CASE_ID", "flow_16")
const FLOW_CASE = only(filter(case -> case.case_id == FLOW_CASE_ID,
    w4_cases(sdf_origin_from_env, sdf_spacing_from_env)))
const EXPECTED_FLOW_DIMS = Tuple(parse.(Int, split(get(ENV, "FD_FLOW_DIMS", "100,48,36"), ",")))
const EXPECTED_FLOW_SPACING = parse(Float64, get(ENV, "FD_FLOW_SPACING_M", "0.05"))
const EXPECTED_SOLVER_LENGTH = parse(Float64, get(ENV, "FD_SOLVER_LENGTH", "16.0"))
const EXPECTED_SOLVER_VISCOSITY = parse(Float64, get(ENV, "FD_SOLVER_VISCOSITY", "0.2"))
const EXPECTED_SOLVER_TIME_UNIT = parse(Float64, get(ENV, "FD_SOLVER_TIME_UNIT_S", "0.05"))
const FORCE_COLUMNS = ("step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
    "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver")
const EPSILONS = Tuple(parse.(Float64, split(get(ENV, "FD_EPSILONS_M", "0.0005,0.001,0.0025,0.005,0.01"), ",")))
const DIRECTIONS = Tuple(split(get(ENV, "FD_DIRECTION_IDS", "D0_interface_offset,D1_filtered_seed11,D2_filtered_seed2026"), ","))
const SDF_POINT_SHAPE = point_shape_from_env
const SDF_ORIGIN = sdf_origin_from_env
const SDF_SPACING = sdf_spacing_from_env

json_string(value::AbstractString) = "\"" * replace(value, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n") * "\""
json_value(value::Bool) = value ? "true" : "false"
json_value(value::AbstractString) = json_string(value)
json_value(value::Integer) = string(value)
json_value(value::AbstractFloat) = isfinite(value) ? string(Float64(value)) : error("nonfinite JSON value")
json_value(value::Tuple) = "[" * join(json_value.(collect(value)), ",") * "]"
json_value(value::AbstractVector) = "[" * join(json_value.(value), ",") * "]"
json_value(value) = error("unsupported JSON value type: $(typeof(value))")

function write_summary(path, summary)
    open(path, "w") do io
        print(io, "{")
        for (index, (key, value)) in enumerate(pairs(summary))
            index > 1 && print(io, ",")
            print(io, json_string(string(key)), ":", json_value(value))
        end
        println(io, "}")
    end
end

function read_queue(path)
    rows = [split(strip(line), '\t') for line in eachline(path) if !isempty(strip(line))]
    all(length(row) == 7 for row in rows) || error("FD run queue TSV schema mismatch")
    return [(run_id=row[1], phi_path=row[2], phi_sha=row[3], state_sha=row[4],
             direction_id=row[5], epsilon_m=parse(Float64, row[6]), sign=parse(Int, row[7]))
            for row in rows]
end

function perturbation_id(direction_id, epsilon, sign)
    tag = replace(@sprintf("%.4f", epsilon), "." => "p")
    return "$(direction_id)__eps_$(tag)m__$(sign == 1 ? "plus" : "minus")"
end

function expected_order()
    pairs = [(direction_id, epsilon, sign) for direction_id in DIRECTIONS
             for epsilon in EPSILONS for sign in (1, -1)]
    names = [perturbation_id(direction_id, epsilon, sign) for (direction_id, epsilon, sign) in pairs]
    return vcat(["baseline_A"], names[1:16], ["baseline_B"], names[17:30], ["baseline_C"])
end

function phi_hashes(phi)
    f_sha = bytes2hex(sha256(reinterpret(UInt8, vec(phi))))
    c_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    return c_sha, f_sha
end

function read_phi(run)
    raw = read(run.phi_path)
    bytes2hex(sha256(raw)) == run.phi_sha || error("$(run.run_id): registered phi file SHA mismatch")
    length(raw) == prod(SDF_POINT_SHAPE) * sizeof(Float32) || error("$(run.run_id): phi byte length mismatch")
    phi = reshape(copy(reinterpret(Float32, raw)), SDF_POINT_SHAPE)
    all(isfinite, phi) || error("$(run.run_id): non-finite phi input")
    c_sha, f_sha = phi_hashes(phi)
    f_sha == run.phi_sha || error("$(run.run_id): Fortran phi SHA mismatch")
    return phi, c_sha, f_sha
end

function load_cpu_grid(run)
    phi, c_sha, f_sha = read_phi(run)
    if run.run_id in ("baseline_A", "baseline_B", "baseline_C")
        run.state_sha == EXPECTED_STATE_SHA || error("baseline state SHA binding mismatch")
        c_sha == EXPECTED_PHI_C_SHA || error("canonical baseline C-order phi identity mismatch")
        f_sha == EXPECTED_PHI_F_SHA || error("canonical baseline Fortran phi identity mismatch")
    end
    margin = zero_level_margin_m(phi, SDF_ORIGIN, (SDF_SPACING, SDF_SPACING, SDF_SPACING))
    isfinite(margin) && margin >= REQUIRED_MARGIN - MARGIN_TOL ||
        error("$(run.run_id): perturbed phi fails the CPU SDF margin gate ($margin)")
    if run.run_id in ("baseline_A", "baseline_B", "baseline_C")
        abs(margin - EXPECTED_MARGIN) <= MARGIN_TOL || error("canonical SDF margin drift")
    end
    grid = GridSDF(phi; origin=SDF_ORIGIN,
        h=(SDF_SPACING, SDF_SPACING, SDF_SPACING),
        outside_value=OUTSIDE_VALUE, margin_m=REQUIRED_MARGIN)
    return grid, phi, margin, c_sha, f_sha
end

function write_force_csv(path, rows)
    open(path, "w") do io
        println(io, join(FORCE_COLUMNS, ","))
        for row in rows
            println(io, join(row, ","))
        end
    end
end

function interpolate_row(left, right, t)
    left[2] <= t <= right[2] || error("force samples do not bracket a window endpoint")
    left[2] == right[2] && return left
    alpha = (t - left[2]) / (right[2] - left[2])
    return ntuple(i -> i == 2 ? Float64(t) : left[i] + alpha * (right[i] - left[i]), 13)
end

function clipped_window(rows, start_t, end_t)
    a = findlast(row -> row[2] <= start_t, rows)
    b = findfirst(row -> row[2] >= start_t, rows)
    c = findlast(row -> row[2] <= end_t, rows)
    d = findfirst(row -> row[2] >= end_t, rows)
    all(index -> index !== nothing, (a, b, c, d)) || error("force rows do not bracket the registered force window")
    return vcat([interpolate_row(rows[a], rows[b], start_t)],
        [row for row in rows if start_t < row[2] < end_t],
        [interpolate_row(rows[c], rows[d], end_t)])
end

function tw_mean(rows, column)
    numerator = denominator = 0.0
    for i in 1:(length(rows) - 1)
        dt = rows[i + 1][2] - rows[i][2]
        numerator += 0.5 * (rows[i][column] + rows[i + 1][column]) * dt
        denominator += dt
    end
    denominator > 0.0 || error("non-positive exact-window duration")
    return numerator / denominator
end

function window_stats(rows, column)
    whole = tw_mean(clipped_window(rows, WINDOW_START, WINDOW_END), column)
    first = tw_mean(clipped_window(rows, WINDOW_START, STATIONARITY_SPLIT), column)
    second = tw_mean(clipped_window(rows, STATIONARITY_SPLIT, WINDOW_END), column)
    drift = abs(first - second) / max(abs(whole), eps(Float64))
    return whole, first, second, drift
end

function measure_fresh_run(run, vram_total)
    validate_w4_case(FLOW_CASE; canonical_design_origin_m=SDF_ORIGIN,
        canonical_design_spacing_m=SDF_SPACING)
    FLOW_CASE.flow_origin_m == EXPECTED_FLOW_ORIGIN || error("registered flow origin differs from W4 case")
    FLOW_CASE.flow_dims == EXPECTED_FLOW_DIMS || error("registered flow dimensions differ from W4 case")
    abs(FLOW_CASE.flow_spacing_m - EXPECTED_FLOW_SPACING) <= 1e-12 || error("registered flow spacing differs from W4 case")
    abs(FLOW_CASE.solver_length - EXPECTED_SOLVER_LENGTH) <= 1e-12 || error("registered solver length differs from W4 case")
    abs(FLOW_CASE.solver_viscosity - EXPECTED_SOLVER_VISCOSITY) <= 1e-12 || error("registered solver viscosity differs from W4 case")
    abs(FLOW_CASE.solver_time_unit_s - EXPECTED_SOLVER_TIME_UNIT) <= 1e-12 || error("registered solver time unit differs from W4 case")
    grid, phi, margin, c_sha, f_sha = load_cpu_grid(run)
    owner = CPU_PRESTEP ? grid : device_copy(grid)
    roundtrip_sha = CPU_PRESTEP ? f_sha : device_roundtrip_sha(owner)
    roundtrip_sha == f_sha || error("$(run.run_id): device phi round-trip SHA mismatch")
    candidate_grid = CPU_PRESTEP ? grid : kernel_grid(owner)
    candidate = GridSDFWaterLilyBody(candidate_grid, Float32.(FLOW_CASE.flow_origin_m), Float32(FLOW_CASE.flow_spacing_m),
        Float32(NORMAL_FLOOR))
    ground = V16MovingGroundBody(0.0f0, 1.0f0)
    bodies = (candidate=candidate, ground=ground, combined=candidate + ground)
    sim = WaterLily.Simulation(FLOW_CASE.flow_dims, v16_native_far_field_uBC,
        Float32(FLOW_CASE.solver_length); U=Float32(FLOW_CASE.solver_velocity),
        ν=Float32(FLOW_CASE.solver_viscosity), exitBC=true, body=bodies.combined,
        T=Float32, mem=(CPU_PRESTEP ? Array : CuArray))
    owned = OwnedV16Run(owner, bodies, sim)
    if CPU_PRESTEP
        println("FD_PRESTEP_IDENTITY ", run.run_id, " state=", run.state_sha,
            " phi_c=", c_sha, " phi_f=", f_sha, " shape=", join(SDF_POINT_SHAPE, ","),
            " spacing_m=", SDF_SPACING, " flow=", FLOW_CASE.case_id,
            " dims=", join(FLOW_CASE.flow_dims, ","), " flow_origin_m=", join(FLOW_CASE.flow_origin_m, ","),
            " flow_spacing_m=", FLOW_CASE.flow_spacing_m,
            " normal_floor=", candidate.normal_floor)
        println("FD_PRESTEP_READY ", run.run_id)
        flush(stdout)
        return nothing
    end
    summary = nothing
    GC.@preserve owned begin
        println("FD_RUN_STARTED ", run.run_id)
        println("FD_SOLVER_STEP_INVOKED ", run.run_id)
        flush(stdout)
        warm_started = time()
        sim_step!(sim) # compile the fresh simulation's first GPU step; record separately
        CUDA.synchronize()
        first_step_seconds = time() - warm_started
        println("FD_SOLVER_STEP_RETURNED ", run.run_id)
        flush(stdout)
        history = Vector{NTuple{13,Float64}}()
        step = 1
        peak_vram = CUDA.used_memory()
        started = time()
        while sim_time(sim) < T_END
            sim_step!(sim)
            step += 1
            if step % SAMPLE_EVERY == 0 || sim_time(sim) >= T_END
                pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))
                viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
                total = pressure + viscous
                push!(history, (Float64(step), Float64(sim_time(sim)), Float64(total[1]),
                    Float64(total[2]), Float64(total[3]), Float64(total[1]), Float64(-total[3]),
                    Float64(pressure[1]), Float64(pressure[2]), Float64(pressure[3]),
                    Float64(viscous[1]), Float64(viscous[2]), Float64(viscous[3])))
            end
            step % 50 == 0 && (peak_vram = max(peak_vram, CUDA.used_memory()))
        end
        CUDA.synchronize()
        wall_seconds = time() - started
        peak_vram = max(peak_vram, CUDA.used_memory())
        finite_u = all(isfinite, sim.flow.u)
        finite_p = all(isfinite, sim.flow.p)
        finite_forces = all(row -> all(isfinite, row), history)
        finite_u && finite_p && finite_forces || error("$(run.run_id): nonfinite primal field/force")
        window_sample_count = count(row -> BURN_IN <= row[2] <= T_END, history)
        drag, drag_first, drag_second, drag_drift = window_stats(history, 6)
        down, down_first, down_second, down_drift = window_stats(history, 7)
        force_window = clipped_window(history, BURN_IN, T_END)
        fx = tw_mean(force_window, 3)
        fy = tw_mean(force_window, 4)
        fz = tw_mean(force_window, 5)
        pressure_fx = tw_mean(force_window, 8)
        pressure_fy = tw_mean(force_window, 9)
        pressure_fz = tw_mean(force_window, 10)
        viscous_fx = tw_mean(force_window, 11)
        viscous_fy = tw_mean(force_window, 12)
        viscous_fz = tw_mean(force_window, 13)
        force_scale = FLOW_CASE.density_kg_m3 * FLOW_CASE.freestream_mps^2 * FLOW_CASE.flow_spacing_m^2
        area_solver = FLOW_CASE.reference_area_m2 / FLOW_CASE.flow_spacing_m^2
        csv_path = joinpath(output_dir, run.run_id * ".forces.csv")
        write_force_csv(csv_path, history)
        csv_sha = bytes2hex(sha256(read(csv_path)))
        summary_path = joinpath(output_dir, run.run_id * ".summary.json")
        summary = (
            run_id=run.run_id, direction_id=run.direction_id, epsilon_m=run.epsilon_m,
            sign=run.sign, input_phi_sha256=f_sha, input_state_sha256=run.state_sha,
            phi_c_order_sha256=c_sha, phi_fortran_sha256=f_sha,
            device_roundtrip_sha256=roundtrip_sha, canonical_state_label=STATE_LABEL,
            normal_floor=NORMAL_FLOOR,
            canonical_state_sha256=EXPECTED_STATE_SHA,
            canonical_source_surface_sha256=EXPECTED_SOURCE_SHA,
            point_shape=SDF_POINT_SHAPE,
            canonical_sdf_origin_m=SDF_ORIGIN,
            flow_origin_m=FLOW_CASE.flow_origin_m, flow_dims=FLOW_CASE.flow_dims,
            flow_spacing_m=FLOW_CASE.flow_spacing_m, solver_length=FLOW_CASE.solver_length,
            solver_viscosity=FLOW_CASE.solver_viscosity, solver_velocity=FLOW_CASE.solver_velocity,
            solver_time_unit_s=FLOW_CASE.solver_time_unit_s, reynolds=FLOW_CASE.reynolds,
            density_kg_m3=FLOW_CASE.density_kg_m3,
            dynamic_viscosity_pa_s=FLOW_CASE.dynamic_viscosity_pa_s,
            freestream_mps=(FLOW_CASE.freestream_mps, 0.0, 0.0),
            reference_length_m=FLOW_CASE.reference_length_m,
            reference_area_m2=FLOW_CASE.reference_area_m2,
            physical_box_m=ntuple(i -> (FLOW_CASE.flow_origin_m[i], FLOW_CASE.physical_box_max_m[i]), 3),
            canonical_design_spacing_m=SDF_SPACING,
            candidate_body_mapping="flow_origin + solver_coordinate*flow_spacing; canonical GridSDF retains its registered origin and spacing",
            sdf_outside_value_m=OUTSIDE_VALUE,
            moving_ground_solver_plane=0.0,
            moving_ground_world_plane_m=FLOW_CASE.flow_origin_m[3],
            moving_ground_velocity_mps=(1.0, 0.0, 0.0),
            force_window_t_u_l=(WINDOW_START, WINDOW_END),
            stationarity_half_windows_t_u_l=((WINDOW_START, STATIONARITY_SPLIT),
                (STATIONARITY_SPLIT, WINDOW_END)),
            phi_margin_m=margin, phi_margin_gate_m=REQUIRED_MARGIN,
            julia_version=string(VERSION), julia_threads=Threads.nthreads(),
            cuda_jl_version=string(pkgversion(CUDA)),
            cuda_runtime_version=string(CUDA.runtime_version()),
            waterlily_version=string(pkgversion(WaterLily)),
            waterlily_backend=string(WaterLily.backend),
            gpu_name=CUDA.name(CUDA.device()), gpu_uuid=get(ENV, "FD_SELECTED_GPU_UUID", ""),
            cuda_visible_devices=get(ENV, "CUDA_VISIBLE_DEVICES", ""),
            native_velocity_boundary="v16_native_far_field_uBC: +x freestream velocity 1 m/s; other normal components zero",
            side_top_tangential_boundary="WaterLily native tangential zero-Neumann",
            x_plus_boundary="WaterLily convective exit",
            pressure_boundary="WaterLily projection pressure; no per-patch freestreamPressure input",
            ground_model="moving planar half-space at solver z=0, mapped to world z=-0.9 m by flow origin, with +x wall velocity 1 m/s",
            force_integration_body="canonical $(STATE_LABEL) candidate GridSDF only; exclude auxiliary moving-ground half-space",
            force_projection_semantics="drag=+Fx; downforce=-Fz",
            source_profile_equivalent=false, physical_profile_qualified=false,
            t_end_target=T_END, t_end_reached=Float64(sim_time(sim)), steps=step,
            sample_every_solver_steps=SAMPLE_EVERY, force_samples=length(history),
            finite_u=finite_u, finite_p=finite_p, finite_forces=finite_forces,
            first_step_seconds=first_step_seconds, wall_seconds=wall_seconds,
            peak_vram_bytes=peak_vram, vram_total_bytes=vram_total,
            window_samples=window_sample_count,
            window_time_weighted_fx_solver=fx, window_time_weighted_fy_solver=fy,
            window_time_weighted_fz_solver=fz, window_time_weighted_drag_solver=drag,
            window_time_weighted_downforce_solver=down,
            window_time_weighted_pressure_fx_solver=pressure_fx,
            window_time_weighted_pressure_fy_solver=pressure_fy,
            window_time_weighted_pressure_fz_solver=pressure_fz,
            window_time_weighted_viscous_fx_solver=viscous_fx,
            window_time_weighted_viscous_fy_solver=viscous_fy,
            window_time_weighted_viscous_fz_solver=viscous_fz,
            drag_time_weighted_n=drag * force_scale, downforce_time_weighted_n=down * force_scale,
            cd_time_weighted=drag / (0.5 * area_solver * FLOW_CASE.solver_velocity^2),
            stationarity_first_half_time_weighted_drag_solver=drag_first,
            stationarity_second_half_time_weighted_drag_solver=drag_second,
            stationarity_relative_half_window_drift_drag=drag_drift,
            stationarity_first_half_time_weighted_downforce_solver=down_first,
            stationarity_second_half_time_weighted_downforce_solver=down_second,
            stationarity_relative_half_window_drift_downforce=down_drift,
            force_csv_sha256=csv_sha,
        )
        write_summary(summary_path, summary)
        println("FD_RUN_DONE ", run.run_id, " ", read(summary_path, String))
        flush(stdout)
    end
    return summary
end

function main()
    mkpath(output_dir)
    queue = read_queue(queue_path)
    [run.run_id for run in queue] == expected_order() || error("FD fixed 33-run order differs from registration")
    all(run -> isfile(run.phi_path), queue) || error("FD input queue references a missing phi file")
    all(run -> bytes2hex(sha256(read(run.phi_path))) == run.phi_sha, queue) ||
        error("FD run queue contains an input phi hash mismatch")
    all(run -> run.run_id in ("baseline_A", "baseline_B", "baseline_C") ||
        perturbation_id(run.direction_id, run.epsilon_m, run.sign) == run.run_id, queue) ||
        error("FD run queue perturbation identity mismatch")
    run_queue_summary = joinpath(output_dir, "run_queue.tsv")
    cp(queue_path, run_queue_summary; force=true)
    if CPU_PRESTEP
        queue[1].run_id == "baseline_A" || error("CPU prestep must initialize the first registered baseline")
        measure_fresh_run(queue[1], nothing)
        println("FD_PRESTEP_COMPLETE runs_validated=", length(queue), " next=sim_step!")
        flush(stdout)
        return
    end
    CUDA_VISIBLE = get(ENV, "CUDA_VISIBLE_DEVICES", "")
    CUDA_VISIBLE == "0" || error("registered single-T4 visibility must be CUDA_VISIBLE_DEVICES=0")
    runtime = Dict{String,Any}()
    total_started = time()
    vram_total = last(CUDA.memory_info())
    println("FD_MATRIX_STARTED runs=", length(queue))
    flush(stdout)
    for run in queue
        summary = measure_fresh_run(run, vram_total)
        runtime[run.run_id] = summary.wall_seconds
        GC.gc()
        CUDA.synchronize()
        if sum(values(runtime)) > 7200.0
            error("registered aggregate FD solver wall time limit exceeded")
        end
    end
    total_wall = time() - total_started
    open(joinpath(output_dir, "matrix_summary.json"), "w") do io
        print(io, "{\"run_order\":", json_value([run.run_id for run in queue]),
              ",\"run_count\":", length(queue), ",\"aggregate_solver_wall_seconds\":",
              json_value(sum(values(runtime))), ",\"total_job_wall_seconds\":", json_value(total_wall),
              ",\"runtime_by_run\":{")
        for (index, (run_id, seconds)) in enumerate(sort!(collect(runtime); by=first))
            index > 1 && print(io, ",")
            print(io, json_string(run_id), ":", json_value(seconds))
        end
        println(io, "}}")
    end
    println("FD_MATRIX_DONE runs=", length(queue), " solver_wall_s=", sum(values(runtime)),
        " total_wall_s=", total_wall)
    write(joinpath(output_dir, "FD_JOB_DONE"), "All 33 registered $(FLOW_CASE_ID) primals returned; host verification required.\n")
end

main()
