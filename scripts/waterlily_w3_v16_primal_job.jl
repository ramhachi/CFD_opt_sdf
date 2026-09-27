# Registered W3 first primal for the canonical v16 GridSDF and moving-ground
# WaterLily adapter. Acceptance limits come from an immutable criteria file;
# this job only reports deterministic inputs and measured outputs.
#
# Usage on the registered Kaggle T4 runtime:
#   julia --project=<T4 env> scripts/waterlily_w3_v16_primal_job.jl \
#       <canonical_phi_f4_fortran.raw> <output_dir>

using CUDA
using SHA

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))

Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
using .CFDSDFWaterLily.DeviceGridSDF

length(ARGS) == 2 || error("usage: waterlily_w3_v16_primal_job.jl <phi_fortran.raw> <output_dir>")
phi_raw_path, output_dir = ARGS

const EXPECTED_STATE_SHA256 = "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8"
const EXPECTED_PHI_C_ORDER_SHA256 = "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785"
const EXPECTED_PHI_FORTRAN_SHA256 = "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
const EXPECTED_SOURCE_STL_SHA256 = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
const REQUIRED_MARGIN_M = 0.15
const EXPECTED_MARGIN_M = 0.3499999939931499
const MARGIN_TOL_M = 1e-6
const T_END = 120.0
const BURN_IN = 80.0
const SAMPLE_EVERY = 8

function json_number(x)
    x isa Bool && return x ? "true" : "false"
    x isa Integer && return string(x)
    return string(Float64(x))
end
json_array(values) = "[" * join(json_number.(values), ",") * "]"

function time_weighted_mean(rows, column, fallback)
    length(rows) >= 2 || return fallback
    numerator = 0.0
    denominator = 0.0
    for i in 1:(length(rows) - 1)
        dt = rows[i + 1][2] - rows[i][2]
        numerator += 0.5 * (rows[i][column] + rows[i + 1][column]) * dt
        denominator += dt
    end
    denominator > 0.0 ? numerator / denominator : fallback
end

function mean_column(rows, column)
    sum(row[column] for row in rows) / length(rows)
end

function write_force_csv(path, rows)
    open(path, "w") do io
        println(io, "step,t_u_l,fx_solver,fy_solver,fz_solver,drag_solver,downforce_solver,pressure_drag_solver,viscous_drag_solver")
        for row in rows
            println(io, join(row, ","))
        end
    end
end

function load_canonical_grid(path)
    Base.ENDIAN_BOM == 0x04030201 ||
        error("registered phi byte encoding requires little-endian runtime")
    bytes = read(path)
    length(bytes) == prod(V16_PROFILE_POINT_SHAPE) * sizeof(Float32) ||
        error("canonical v16 phi byte length mismatch")
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_FORTRAN_SHA256 ||
        error("canonical v16 Fortran-order phi source hash mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), V16_PROFILE_POINT_SHAPE)
    c_order_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_order_sha == EXPECTED_PHI_C_ORDER_SHA256 ||
        error("canonical v16 C-order phi hash mismatch")
    grid = GridSDF(
        phi;
        origin = V16_PROFILE_ORIGIN_M,
        h = (V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M),
        outside_value = 3.0,
        margin_m = REQUIRED_MARGIN_M,
    )
    measured_margin = zero_level_margin_m(phi, V16_PROFILE_ORIGIN_M,
        (V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M))
    abs(measured_margin - EXPECTED_MARGIN_M) <= MARGIN_TOL_M ||
        error("canonical v16 phi margin drift: $(measured_margin)")
    return grid, measured_margin, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), c_order_sha
end

function run_primal(sim, bodies; vram_total)
    history = Vector{NTuple{9,Float64}}()
    warm_started = time()
    sim_step!(sim) # compile the registered GPU path; excluded from solve timing
    first_step_seconds = time() - warm_started
    step = 1
    peak_vram = CUDA.used_memory()
    started = time()
    while sim_time(sim) < T_END
        sim_step!(sim)
        step += 1
        if step % SAMPLE_EVERY == 0
            pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))
            viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
            total = pressure + viscous
            drag = total[1]
            downforce = -total[3]
            push!(history, (
                Float64(step), Float64(sim_time(sim)), Float64(total[1]),
                Float64(total[2]), Float64(total[3]), Float64(drag),
                Float64(downforce), Float64(pressure[1]), Float64(viscous[1]),
            ))
        end
        if step % 50 == 0
            peak_vram = max(peak_vram, CUDA.used_memory())
        end
    end
    CUDA.synchronize()
    wall_seconds = time() - started
    peak_vram = max(peak_vram, CUDA.used_memory())
    all(isfinite, sim.flow.u) || error("non-finite velocity field")
    all(isfinite, sim.flow.p) || error("non-finite pressure field")
    isempty(history) && error("no candidate-force samples were captured")
    window = [row for row in history if BURN_IN <= row[2] <= T_END]
    length(window) >= 4 || error("too few samples in registered W3 force window")
    middle = (BURN_IN + T_END) / 2
    first_half = [row for row in window if row[2] < middle]
    second_half = [row for row in window if row[2] >= middle]
    (!isempty(first_half) && !isempty(second_half)) || error("empty W3 diagnostic half-window")
    drag = mean_column(window, 6)
    downforce = mean_column(window, 7)
    area_solver = V16_PROFILE_REFERENCE_AREA_M2 / V16_PROFILE_SPACING_M^2
    force_scale_n = V16_PROFILE_DENSITY_KG_M3 *
        V16_PROFILE_FREESTREAM_MPS[1]^2 * V16_PROFILE_SPACING_M^2
    return (
        history = history,
        steps = step,
        wall_seconds = wall_seconds,
        first_step_seconds = first_step_seconds,
        t_end_reached = Float64(sim_time(sim)),
        finite_u = all(isfinite, sim.flow.u),
        finite_p = all(isfinite, sim.flow.p),
        force_samples = length(history),
        window_samples = length(window),
        window_mean_drag_solver = drag,
        window_mean_downforce_solver = downforce,
        window_time_weighted_drag_solver = time_weighted_mean(window, 6, drag),
        window_time_weighted_downforce_solver = time_weighted_mean(window, 7, downforce),
        diagnostic_first_half_mean_drag_solver = mean_column(first_half, 6),
        diagnostic_second_half_mean_drag_solver = mean_column(second_half, 6),
        diagnostic_first_half_mean_downforce_solver = mean_column(first_half, 7),
        diagnostic_second_half_mean_downforce_solver = mean_column(second_half, 7),
        cd_window_mean = drag / (0.5 * area_solver),
        cd_time_weighted = time_weighted_mean(window, 6, drag) / (0.5 * area_solver),
        drag_time_weighted_n = time_weighted_mean(window, 6, drag) * force_scale_n,
        downforce_time_weighted_n = time_weighted_mean(window, 7, downforce) * force_scale_n,
        peak_vram_bytes = peak_vram,
        vram_total_bytes = vram_total,
    )
end

function run_w3_primal()
    mkpath(output_dir)
    canonical, margin, phi_fortran_sha, phi_c_order_sha = load_canonical_grid(phi_raw_path)
    device_owner = device_copy(canonical)
    roundtrip_sha = device_roundtrip_sha(device_owner)
    roundtrip_sha == EXPECTED_PHI_FORTRAN_SHA256 || error("v16 GPU phi round-trip hash mismatch")
    device_grid = kernel_grid(device_owner)
    bodies = v16_physical_profile_bodies(device_grid; T = Float32)
    sim = build_v16_physical_profile_simulation(bodies; T = Float32, mem = CuArray)
    fingerprint = runtime_fingerprint()
    vram_total = last(CUDA.memory_info())
    summary = run_primal(sim, bodies; vram_total)

    csv_path = joinpath(output_dir, "v16.forces.csv")
    write_force_csv(csv_path, summary.history)
    csv_sha = bytes2hex(sha256(read(csv_path)))
    adapter = v16_physical_profile_adapter_contract()
    result = string(
        "{",
        "\"state_sha256\":\"", EXPECTED_STATE_SHA256, "\",",
        "\"source_surface_sha256\":\"", EXPECTED_SOURCE_STL_SHA256, "\",",
        "\"phi_c_order_sha256\":\"", phi_c_order_sha, "\",",
        "\"phi_fortran_sha256\":\"", phi_fortran_sha, "\",",
        "\"device_roundtrip_sha256\":\"", roundtrip_sha, "\",",
        "\"phi_margin_m\":", json_number(margin), ",",
        "\"phi_margin_gate_m\":", json_number(REQUIRED_MARGIN_M), ",",
        "\"julia_version\":\"", fingerprint.julia_version, "\",",
        "\"julia_threads\":", fingerprint.julia_threads, ",",
        "\"waterlily_version\":\"", fingerprint.waterlily_version, "\",",
        "\"waterlily_backend\":\"", fingerprint.waterlily_backend, "\",",
        "\"cuda_jl_version\":\"", string(pkgversion(CUDA)), "\",",
        "\"gpu_name\":\"", CUDA.name(CUDA.device()), "\",",
        "\"gpu_uuid\":\"", get(ENV, "W3_SELECTED_GPU_UUID", ""), "\",",
        "\"dims\":", json_array(V16_PROFILE_CELL_DIMS), ",",
        "\"origin_m\":", json_array(V16_PROFILE_ORIGIN_M), ",",
        "\"spacing_m\":", json_number(V16_PROFILE_SPACING_M), ",",
        "\"world_per_solver\":", json_number(V16_PROFILE_SPACING_M), ",",
        "\"solver_time_unit_s\":", json_number(V16_PROFILE_SOLVER_TIME_UNIT_S), ",",
        "\"solver_length\":", json_number(V16_PROFILE_SOLVER_LENGTH), ",",
        "\"solver_u\":", json_number(V16_PROFILE_SOLVER_U), ",",
        "\"reynolds\":", json_number(V16_PROFILE_REYNOLDS), ",",
        "\"solver_viscosity\":", json_number(V16_PROFILE_SOLVER_VISCOSITY), ",",
        "\"freestream_mps\":", json_array(V16_PROFILE_FREESTREAM_MPS), ",",
        "\"ground_velocity_mps\":", json_array(V16_PROFILE_FREESTREAM_MPS), ",",
        "\"source_profile_equivalent\":", adapter.source_profile_equivalent, ",",
        "\"physical_profile_qualified\":", adapter.physical_profile_qualified, ",",
        "\"x_max_boundary\":\"", adapter.x_max_boundary, "\",",
        "\"pressure_boundary\":\"", adapter.pressure_boundary, "\",",
        "\"t_end_target\":", json_number(T_END), ",",
        "\"t_end_reached\":", json_number(summary.t_end_reached), ",",
        "\"burn_in\":", json_number(BURN_IN), ",",
        "\"sample_every_steps\":", SAMPLE_EVERY, ",",
        "\"steps\":", summary.steps, ",",
        "\"wall_seconds\":", json_number(summary.wall_seconds), ",",
        "\"first_step_seconds\":", json_number(summary.first_step_seconds), ",",
        "\"force_samples\":", summary.force_samples, ",",
        "\"window_samples\":", summary.window_samples, ",",
        "\"finite_u\":", summary.finite_u, ",",
        "\"finite_p\":", summary.finite_p, ",",
        "\"window_mean_drag_solver\":", json_number(summary.window_mean_drag_solver), ",",
        "\"window_mean_downforce_solver\":", json_number(summary.window_mean_downforce_solver), ",",
        "\"window_time_weighted_drag_solver\":", json_number(summary.window_time_weighted_drag_solver), ",",
        "\"window_time_weighted_downforce_solver\":", json_number(summary.window_time_weighted_downforce_solver), ",",
        "\"diagnostic_first_half_mean_drag_solver\":", json_number(summary.diagnostic_first_half_mean_drag_solver), ",",
        "\"diagnostic_second_half_mean_drag_solver\":", json_number(summary.diagnostic_second_half_mean_drag_solver), ",",
        "\"diagnostic_first_half_mean_downforce_solver\":", json_number(summary.diagnostic_first_half_mean_downforce_solver), ",",
        "\"diagnostic_second_half_mean_downforce_solver\":", json_number(summary.diagnostic_second_half_mean_downforce_solver), ",",
        "\"cd_window_mean\":", json_number(summary.cd_window_mean), ",",
        "\"cd_time_weighted\":", json_number(summary.cd_time_weighted), ",",
        "\"drag_time_weighted_n\":", json_number(summary.drag_time_weighted_n), ",",
        "\"downforce_time_weighted_n\":", json_number(summary.downforce_time_weighted_n), ",",
        "\"peak_vram_bytes\":", summary.peak_vram_bytes, ",",
        "\"vram_total_bytes\":", summary.vram_total_bytes, ",",
        "\"force_csv_sha256\":\"", csv_sha, "\"",
        "}",
    )
    write(joinpath(output_dir, "v16.summary.json"), result * "\n")
    write(joinpath(output_dir, "w3_adapter_contract.json"),
        "{\"source_profile_equivalent\":false,\"physical_profile_qualified\":false,\"" *
        "pressure_boundary\":\"WaterLily projection pressure; no per-patch freestreamPressure input\",\"" *
        "x_max_boundary\":\"WaterLily convective exit\",\"" *
        "side_top_normal_velocity\":\"zero\",\"" *
        "side_top_tangential_condition\":\"zero-Neumann\"}\n")
    println("W3_V16_PRIMAL_DONE ", result)
end

run_w3_primal()
