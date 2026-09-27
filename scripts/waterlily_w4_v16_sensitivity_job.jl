# W4 v16 flow-grid and finite-box domain sensitivity matrix.
# Uses one unchanged canonical design SDF on four registered WaterLily grids.

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
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16W4Sensitivity.jl"))
using .CFDSDFWaterLily: GridSDFWaterLilyBody, V16_PROFILE_POINT_SHAPE,
    V16_PROFILE_ORIGIN_M, V16_PROFILE_SPACING_M, V16MovingGroundBody,
    v16_native_far_field_uBC
using .CFDSDFWaterLily.DeviceGridSDF
using .CFDSDFWaterLily.V16W4Sensitivity

length(ARGS) == 2 || error("usage: waterlily_w4_v16_sensitivity_job.jl <phi_fortran.raw> <output_dir>")
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
const EXPECTED_CASE_IDS = ("flow_16", "flow_24", "flow_32", "domain_xplus3p5_16")

json_number(x) = x isa Bool ? string(x) : x isa Integer ? string(x) : string(Float64(x))
json_array(values) = "[" * join(json_number.(values), ",") * "]"
mean_column(rows, column) = sum(row[column] for row in rows) / length(rows)

function time_weighted_mean(rows, column, fallback)
    length(rows) >= 2 || return fallback
    numerator = denominator = 0.0
    for i in 1:(length(rows) - 1)
        dt = rows[i + 1][2] - rows[i][2]
        numerator += 0.5 * (rows[i][column] + rows[i + 1][column]) * dt
        denominator += dt
    end
    denominator > 0.0 ? numerator / denominator : fallback
end

function load_canonical_grid(path)
    Base.ENDIAN_BOM == 0x04030201 || error("registered phi requires a little-endian runtime")
    bytes = read(path)
    length(bytes) == prod(V16_PROFILE_POINT_SHAPE) * sizeof(Float32) ||
        error("canonical v16 phi byte length mismatch")
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_FORTRAN_SHA256 ||
        error("canonical v16 Fortran-order phi source hash mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), V16_PROFILE_POINT_SHAPE)
    c_order_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_order_sha == EXPECTED_PHI_C_ORDER_SHA256 || error("canonical v16 C-order phi hash mismatch")
    margin = zero_level_margin_m(phi, V16_PROFILE_ORIGIN_M,
        (V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M))
    abs(margin - EXPECTED_MARGIN_M) <= MARGIN_TOL_M ||
        error("canonical v16 CPU-side SDF margin drift: $margin")
    grid = GridSDF(phi; origin=V16_PROFILE_ORIGIN_M,
        h=(V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M, V16_PROFILE_SPACING_M),
        outside_value=3.0, margin_m=REQUIRED_MARGIN_M)
    return grid, margin, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), c_order_sha
end

function write_force_csv(path, rows)
    open(path, "w") do io
        println(io, "step,t_u_l,fx_solver,fy_solver,fz_solver,drag_solver,downforce_solver,pressure_fx_solver,pressure_fy_solver,pressure_fz_solver,viscous_fx_solver,viscous_fy_solver,viscous_fz_solver")
        for row in rows
            println(io, join(row, ","))
        end
    end
end

function run_case(case, owner, phi_margin, phi_f_sha, phi_c_sha, roundtrip_sha, vram_total)
    validate_v16_w4_case(case)
    candidate_grid = kernel_grid(owner)
    candidate = GridSDFWaterLilyBody(candidate_grid,
        Float32.(case.world_origin_m), Float32(case.flow_spacing_m))
    ground = V16MovingGroundBody(0.0f0, 1.0f0)
    bodies = (candidate=candidate, ground=ground, combined=candidate + ground)
    sim = WaterLily.Simulation(
        case.flow_dims, v16_native_far_field_uBC, Float32(case.solver_length);
        U=Float32(case.solver_velocity), ν=Float32(case.solver_viscosity),
        exitBC=true, body=bodies.combined, T=Float32, mem=CuArray,
    )

    history = Vector{NTuple{13,Float64}}()
    warm_started = time()
    sim_step!(sim) # compile this grid's GPU path; excluded from case solve timing
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
            push!(history, (
                Float64(step), Float64(sim_time(sim)), Float64(total[1]),
                Float64(total[2]), Float64(total[3]), Float64(total[1]),
                Float64(-total[3]), Float64(pressure[1]), Float64(pressure[2]),
                Float64(pressure[3]), Float64(viscous[1]), Float64(viscous[2]),
                Float64(viscous[3]),
            ))
        end
        if step % 50 == 0
            peak_vram = max(peak_vram, CUDA.used_memory())
        end
    end
    CUDA.synchronize()
    wall_seconds = time() - started
    peak_vram = max(peak_vram, CUDA.used_memory())
    finite_u = all(isfinite, sim.flow.u)
    finite_p = all(isfinite, sim.flow.p)
    finite_forces = all(row -> all(isfinite, row), history)
    finite_u && finite_p && finite_forces || error("$(case.case_id): non-finite field or force")
    window = [row for row in history if BURN_IN <= row[2] <= T_END]
    length(window) >= 4 || error("$(case.case_id): too few samples in [80,120]")
    middle = 0.5 * (BURN_IN + T_END)
    first_half = [row for row in window if row[2] < middle]
    second_half = [row for row in window if row[2] >= middle]
    (!isempty(first_half) && !isempty(second_half)) || error("$(case.case_id): empty diagnostic half-window")

    drag_mean = mean_column(window, 6)
    downforce_mean = mean_column(window, 7)
    drag_weighted = time_weighted_mean(window, 6, drag_mean)
    downforce_weighted = time_weighted_mean(window, 7, downforce_mean)
    area_solver = case.reference_area_m2 / case.flow_spacing_m^2
    force_scale_n = case.density_kg_m3 * case.freestream_mps^2 * case.flow_spacing_m^2
    summary = (
        case_id=case.case_id,
        cells_per_reference_length=case.cells_per_reference_length,
        flow_dims=case.flow_dims,
        flow_spacing_m=case.flow_spacing_m,
        world_origin_m=case.world_origin_m,
        physical_box_max_m=case.physical_box_max_m,
        canonical_design_spacing_m=case.canonical_design_spacing_m,
        solver_length=case.solver_length,
        solver_time_unit_s=case.solver_time_unit_s,
        solver_velocity=case.solver_velocity,
        solver_viscosity=case.solver_viscosity,
        reynolds=case.reynolds,
        state_sha256=EXPECTED_STATE_SHA256,
        source_surface_sha256=EXPECTED_SOURCE_STL_SHA256,
        phi_c_order_sha256=phi_c_sha,
        phi_fortran_sha256=phi_f_sha,
        device_roundtrip_sha256=roundtrip_sha,
        phi_margin_m=phi_margin,
        phi_margin_gate_m=REQUIRED_MARGIN_M,
        julia_version=string(VERSION),
        julia_threads=Threads.nthreads(),
        waterlily_version=string(pkgversion(WaterLily)),
        waterlily_backend=string(WaterLily.backend),
        cuda_jl_version=string(pkgversion(CUDA)),
        gpu_name=CUDA.name(CUDA.device()),
        gpu_uuid=get(ENV, "W4_SELECTED_GPU_UUID", ""),
        x_max_boundary="WaterLily convective exit",
        pressure_boundary="WaterLily projection pressure; no per-patch freestreamPressure input",
        source_profile_equivalent=false,
        physical_profile_qualified=false,
        t_end_target=T_END,
        t_end_reached=Float64(sim_time(sim)),
        burn_in_t_u_l=BURN_IN,
        sample_every_solver_steps=SAMPLE_EVERY,
        steps=step,
        wall_seconds=wall_seconds,
        first_step_seconds=first_step_seconds,
        force_samples=length(history),
        window_samples=length(window),
        finite_u=finite_u,
        finite_p=finite_p,
        finite_forces=finite_forces,
        window_mean_drag_solver=drag_mean,
        window_mean_downforce_solver=downforce_mean,
        window_time_weighted_drag_solver=drag_weighted,
        window_time_weighted_downforce_solver=downforce_weighted,
        diagnostic_first_half_mean_drag_solver=mean_column(first_half, 6),
        diagnostic_second_half_mean_drag_solver=mean_column(second_half, 6),
        diagnostic_first_half_mean_downforce_solver=mean_column(first_half, 7),
        diagnostic_second_half_mean_downforce_solver=mean_column(second_half, 7),
        cd_time_weighted=drag_weighted / (0.5 * area_solver * case.solver_velocity^2),
        drag_time_weighted_n=drag_weighted * force_scale_n,
        downforce_time_weighted_n=downforce_weighted * force_scale_n,
        peak_vram_bytes=peak_vram,
        vram_total_bytes=vram_total,
    )
    csv_path = joinpath(output_dir, case.case_id * ".forces.csv")
    write_force_csv(csv_path, history)
    csv_sha = bytes2hex(sha256(read(csv_path)))
    summary_path = joinpath(output_dir, case.case_id * ".summary.json")
    open(summary_path, "w") do io
        print(io, "{")
        fields = collect(pairs(summary))
        for (index, (key, value)) in enumerate(fields)
            index > 1 && print(io, ",")
            print(io, "\"", key, "\":")
            if value isa Bool
                print(io, value ? "true" : "false")
            elseif value isa AbstractString
                print(io, "\"", value, "\"")
            elseif value isa Tuple
                print(io, json_array(value))
            else
                print(io, json_number(value))
            end
        end
        print(io, ",\"force_csv_sha256\":\"", csv_sha, "\"}\n")
    end
    println("W4_V16_CASE_DONE ", case.case_id, " ", read(summary_path, String))
    flush(stdout)
end

function main()
    tuple(case.case_id for case in V16W4_CASES) == EXPECTED_CASE_IDS || error("W4 case inventory drift")
    mkpath(output_dir)
    grid, margin, phi_f_sha, phi_c_sha = load_canonical_grid(phi_raw_path)
    device_owner = device_copy(grid)
    roundtrip_sha = device_roundtrip_sha(device_owner)
    roundtrip_sha == EXPECTED_PHI_FORTRAN_SHA256 || error("canonical v16 GPU round-trip hash mismatch")
    vram_total = last(CUDA.memory_info())
    for case in V16W4_CASES
        run_case(case, device_owner, margin, phi_f_sha, phi_c_sha, roundtrip_sha, vram_total)
        GC.gc()
        CUDA.synchronize()
    end
    write(joinpath(output_dir, "W4_JOB_DONE"), "All four registered W4 cases returned; host verification required.\n")
    println("W4_V16_SENSITIVITY_DONE cases=", length(V16W4_CASES))
    flush(stdout)
end

main()
