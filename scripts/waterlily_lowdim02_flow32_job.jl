# LOWDIM-02A job: the W4 Candidate C evaluator and measurement contract unchanged, restricted to the
# registered flow_32 case and applied to one registered canonical-lattice state per invocation.
# Copied from scripts/waterlily_xfid_candidate_c_job.jl; only the case inventory and messages differ (flow_24 -> flow_32).

using CUDA
using SHA

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "OwnedV16Run.jl"))
using .CFDSDFW3RunOwnership: OwnedV16Run
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "WaterLilyNormalFloorBody.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CandidateCWaterLilyBody.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16W4Sensitivity.jl"))
using .CFDSDFWaterLily: GridSDFWaterLilyBody, V16_PROFILE_POINT_SHAPE,
    V16_CANONICAL_SDF_ORIGIN_M, V16_PROFILE_SPACING_M, V16MovingGroundBody,
    v16_native_far_field_uBC, NormalFloorWaterLilyBody, CandidateCWaterLilyBody
using .CFDSDFWaterLily.DeviceGridSDF
using .CFDSDFWaterLily.V16W4Sensitivity

length(ARGS) == 2 || error("usage: waterlily_lowdim02_flow32_job.jl <phi_fortran.raw> <output_dir>")
phi_raw_path, output_dir = ARGS

env_tuple(name, ::Type{T}, fallback) where {T} =
    haskey(ENV, name) ? Tuple(parse.(T, split(ENV[name], ","))) : fallback

const CANONICAL_STATE_LABEL = get(ENV, "W4_CANONICAL_STATE_LABEL", "v16")
const EXPECTED_STATE_SHA256 = get(ENV, "W4_STATE_SHA256",
    "44507748807dfbff995eb146866776b4a292e2fa2ddfe6caa5c3a611c29f6de8")
const EXPECTED_STATE_NPZ_SHA256 = get(ENV, "W4_STATE_NPZ_SHA256",
    "3d2cd6c1b4c6d03cc166eed8a9a46472ff697d95315dd8c22f6828bca59e43fe")
const EXPECTED_PHI_C_ORDER_SHA256 = get(ENV, "W4_PHI_C_ORDER_SHA256",
    "45b6c8f46a3d7bc4c321ab13529babe62469c6fe5834ef8f88604847dbba0785")
const EXPECTED_PHI_FORTRAN_SHA256 = get(ENV, "W4_PHI_FORTRAN_SHA256",
    "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7")
const EXPECTED_SOURCE_STL_SHA256 = get(ENV, "W4_SOURCE_SURFACE_SHA256",
    "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11")
const CANONICAL_POINT_SHAPE = env_tuple("W4_POINT_SHAPE", Int, V16_PROFILE_POINT_SHAPE)
const CANONICAL_CELL_SHAPE = env_tuple("W4_CELL_SHAPE", Int,
    ntuple(i -> V16_PROFILE_POINT_SHAPE[i] - 1, 3))
const CANONICAL_ORIGIN_M = env_tuple("W4_CANONICAL_ORIGIN_M", Float64,
    V16_CANONICAL_SDF_ORIGIN_M)
const CANONICAL_DESIGN_SPACING_M = parse(Float64,
    get(ENV, "W4_CANONICAL_DESIGN_SPACING_M", string(V16_PROFILE_SPACING_M)))
const REQUIRED_MARGIN_M = parse(Float64, get(ENV, "W4_MARGIN_GATE_M", "0.15"))
const EXPECTED_MARGIN_M = parse(Float64,
    get(ENV, "W4_EXPECTED_MARGIN_M", "0.3499999939931499"))
const MARGIN_TOL_M = parse(Float64, get(ENV, "W4_MARGIN_TOLERANCE_M", "1e-6"))
const T_END = 120.0
const BURN_IN = 80.0
const SAMPLE_EVERY = 8
const EXPECTED_CASE_IDS = ("flow_32",)
const C_TRANSITION_WIDTH = Float32(1.1444091796875e-4)

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

function interpolate_force_row(left, right, t)
    left[2] <= t <= right[2] || error("force samples do not bracket the measurement endpoint")
    left[2] == right[2] && return left
    alpha = (t - left[2]) / (right[2] - left[2])
    ntuple(i -> i == 2 ? Float64(t) : left[i] + alpha * (right[i] - left[i]), 13)
end

function clipped_force_window(rows, start_t, end_t)
    start_left = findlast(row -> row[2] <= start_t, rows)
    start_right = findfirst(row -> row[2] >= start_t, rows)
    end_left = findlast(row -> row[2] <= end_t, rows)
    end_right = findfirst(row -> row[2] >= end_t, rows)
    all(index -> index !== nothing, (start_left, start_right, end_left, end_right)) ||
        error("raw force samples do not bracket the complete registered time window")
    first_row = interpolate_force_row(rows[start_left], rows[start_right], start_t)
    last_row = interpolate_force_row(rows[end_left], rows[end_right], end_t)
    interior = [row for row in rows if start_t < row[2] < end_t]
    return vcat([first_row], interior, [last_row])
end

function stationarity_metrics(rows, column)
    first_mean = time_weighted_mean(clipped_force_window(rows, 80.0, 100.0), column, NaN)
    second_mean = time_weighted_mean(clipped_force_window(rows, 100.0, 120.0), column, NaN)
    whole_mean = time_weighted_mean(clipped_force_window(rows, 80.0, 120.0), column, NaN)
    drift = abs(first_mean - second_mean) / max(abs(whole_mean), eps(Float64))
    return first_mean, second_mean, whole_mean, drift
end

function load_canonical_grid(path)
    Base.ENDIAN_BOM == 0x04030201 || error("registered phi requires a little-endian runtime")
    bytes = read(path)
    length(bytes) == prod(CANONICAL_POINT_SHAPE) * sizeof(Float32) ||
        error("canonical $(CANONICAL_STATE_LABEL) phi byte length mismatch")
    bytes2hex(sha256(bytes)) == EXPECTED_PHI_FORTRAN_SHA256 ||
        error("canonical $(CANONICAL_STATE_LABEL) Fortran-order phi source hash mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), CANONICAL_POINT_SHAPE)
    c_order_sha = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
    c_order_sha == EXPECTED_PHI_C_ORDER_SHA256 ||
        error("canonical $(CANONICAL_STATE_LABEL) C-order phi hash mismatch")
    margin = zero_level_margin_m(phi, CANONICAL_ORIGIN_M,
        (CANONICAL_DESIGN_SPACING_M, CANONICAL_DESIGN_SPACING_M, CANONICAL_DESIGN_SPACING_M))
    abs(margin - EXPECTED_MARGIN_M) <= MARGIN_TOL_M ||
        error("canonical $(CANONICAL_STATE_LABEL) CPU-side SDF margin drift: $margin")
    grid = GridSDF(phi; origin=CANONICAL_ORIGIN_M,
        h=(CANONICAL_DESIGN_SPACING_M, CANONICAL_DESIGN_SPACING_M,
            CANONICAL_DESIGN_SPACING_M),
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

function run_case_measurement(case, owned, phi_margin, phi_f_sha, phi_c_sha, roundtrip_sha, vram_total)
    sim = owned.sim
    bodies = owned.bodies
    validate_w4_case(case; canonical_design_origin_m=CANONICAL_ORIGIN_M,
        canonical_design_spacing_m=CANONICAL_DESIGN_SPACING_M)
    println("W4_CASE_STARTED ", case.case_id)
    flush(stdout)
    history = Vector{NTuple{13,Float64}}()
    warm_started = time()
    println("W4_SOLVER_STEP_INVOKED ", case.case_id)
    flush(stdout)
    sim_step!(sim) # compile this grid's GPU path; excluded from case solve timing
    println("W4_SOLVER_STEP_RETURNED ", case.case_id)
    flush(stdout)
    first_step_seconds = time() - warm_started
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
    weighted_window = clipped_force_window(history, BURN_IN, T_END)
    middle = 0.5 * (BURN_IN + T_END)
    first_half = [row for row in window if row[2] < middle]
    second_half = [row for row in window if row[2] >= middle]
    (!isempty(first_half) && !isempty(second_half)) || error("$(case.case_id): empty diagnostic half-window")

    drag_mean = mean_column(window, 6)
    downforce_mean = mean_column(window, 7)
    drag_weighted = time_weighted_mean(weighted_window, 6, drag_mean)
    downforce_weighted = time_weighted_mean(weighted_window, 7, downforce_mean)
    drag_first_weighted, drag_second_weighted, _, drag_stationarity = stationarity_metrics(history, 6)
    downforce_first_weighted, downforce_second_weighted, _, downforce_stationarity = stationarity_metrics(history, 7)
    area_solver = case.reference_area_m2 / case.flow_spacing_m^2
    force_scale_n = case.density_kg_m3 * case.freestream_mps^2 * case.flow_spacing_m^2
    summary = (
        case_id=case.case_id,
        cells_per_reference_length=case.cells_per_reference_length,
        flow_dims=case.flow_dims,
        flow_spacing_m=case.flow_spacing_m,
        flow_origin_m=case.flow_origin_m,
        canonical_sdf_origin_m=case.canonical_design_origin_m,
        physical_box_max_m=case.physical_box_max_m,
        canonical_design_spacing_m=case.canonical_design_spacing_m,
        canonical_state_label=CANONICAL_STATE_LABEL,
        canonical_design_point_shape=CANONICAL_POINT_SHAPE,
        canonical_design_cell_shape=CANONICAL_CELL_SHAPE,
        solver_length=case.solver_length,
        solver_time_unit_s=case.solver_time_unit_s,
        solver_velocity=case.solver_velocity,
        solver_viscosity=case.solver_viscosity,
        reynolds=case.reynolds,
        density_kg_m3=case.density_kg_m3,
        dynamic_viscosity_pa_s=case.dynamic_viscosity_pa_s,
        freestream_mps=(case.freestream_mps, 0.0, 0.0),
        reference_length_m=case.reference_length_m,
        reference_area_m2=case.reference_area_m2,
        state_sha256=EXPECTED_STATE_SHA256,
        state_npz_sha256=EXPECTED_STATE_NPZ_SHA256,
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
        native_velocity_boundary="v16_native_far_field_uBC: +x freestream velocity 1 m/s; other normal components zero",
        side_top_tangential_boundary="WaterLily native tangential zero-Neumann",
        x_max_boundary="WaterLily convective exit",
        pressure_boundary="WaterLily projection pressure; no per-patch freestreamPressure input",
        ground_model="moving planar half-space on the expanded flow-domain bottom at world z=-0.9 m, with +x wall velocity 1 m/s",
        force_integration_body="CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))",
        force_projection_semantics="drag=+Fx; downforce=-Fz",
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
        window_time_weighted_fx_solver=time_weighted_mean(weighted_window, 3, mean_column(window, 3)),
        window_time_weighted_fy_solver=time_weighted_mean(weighted_window, 4, mean_column(window, 4)),
        window_time_weighted_fz_solver=time_weighted_mean(weighted_window, 5, mean_column(window, 5)),
        window_time_weighted_drag_solver=time_weighted_mean(weighted_window, 6, drag_mean),
        window_time_weighted_downforce_solver=time_weighted_mean(weighted_window, 7, downforce_mean),
        window_time_weighted_pressure_fx_solver=time_weighted_mean(weighted_window, 8, mean_column(window, 8)),
        window_time_weighted_pressure_fy_solver=time_weighted_mean(weighted_window, 9, mean_column(window, 9)),
        window_time_weighted_pressure_fz_solver=time_weighted_mean(weighted_window, 10, mean_column(window, 10)),
        window_time_weighted_viscous_fx_solver=time_weighted_mean(weighted_window, 11, mean_column(window, 11)),
        window_time_weighted_viscous_fy_solver=time_weighted_mean(weighted_window, 12, mean_column(window, 12)),
        window_time_weighted_viscous_fz_solver=time_weighted_mean(weighted_window, 13, mean_column(window, 13)),
        diagnostic_first_half_mean_drag_solver=mean_column(first_half, 6),
        diagnostic_second_half_mean_drag_solver=mean_column(second_half, 6),
        diagnostic_first_half_mean_downforce_solver=mean_column(first_half, 7),
        diagnostic_second_half_mean_downforce_solver=mean_column(second_half, 7),
        stationarity_first_half_time_weighted_drag_solver=drag_first_weighted,
        stationarity_second_half_time_weighted_drag_solver=drag_second_weighted,
        stationarity_relative_half_window_drift_drag=drag_stationarity,
        stationarity_first_half_time_weighted_downforce_solver=downforce_first_weighted,
        stationarity_second_half_time_weighted_downforce_solver=downforce_second_weighted,
        stationarity_relative_half_window_drift_downforce=downforce_stationarity,
        cd_time_weighted=drag_weighted / (0.5 * area_solver * case.solver_velocity^2),
        drag_time_weighted_n=drag_weighted * force_scale_n,
        downforce_time_weighted_n=downforce_weighted * force_scale_n,
        pressure_drag_time_weighted_n=time_weighted_mean(weighted_window, 8,
            mean_column(window, 8)) * force_scale_n,
        viscous_drag_time_weighted_n=time_weighted_mean(weighted_window, 11,
            mean_column(window, 11)) * force_scale_n,
        pressure_downforce_time_weighted_n=-time_weighted_mean(weighted_window, 10,
            mean_column(window, 10)) * force_scale_n,
        viscous_downforce_time_weighted_n=-time_weighted_mean(weighted_window, 13,
            mean_column(window, 13)) * force_scale_n,
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
    println("W4_$(uppercase(CANONICAL_STATE_LABEL))_CASE_DONE ", case.case_id, " ", read(summary_path, String))
    flush(stdout)
end

function run_case(case, owner, phi_margin, phi_f_sha, phi_c_sha, roundtrip_sha, vram_total)
    validate_w4_case(case; canonical_design_origin_m=CANONICAL_ORIGIN_M,
        canonical_design_spacing_m=CANONICAL_DESIGN_SPACING_M)
    candidate_grid = kernel_grid(owner)
    floor_candidate = NormalFloorWaterLilyBody(candidate_grid,
        Float32.(case.flow_origin_m), Float32(case.flow_spacing_m), 0.25f0)
    candidate = CandidateCWaterLilyBody(floor_candidate;
        normal_floor=0.25f0, transition_width=C_TRANSITION_WIDTH)
    ground = V16MovingGroundBody(0.0f0, 1.0f0)
    # Candidate C is outermost so WaterLily.measure! dispatches the μ₀ blend
    # over the entire candidate+ground union. Force reporting stays candidate-only.
    bodies = (candidate=candidate, ground=ground,
        combined=CandidateCWaterLilyBody(floor_candidate, ground;
            normal_floor=0.25f0, transition_width=C_TRANSITION_WIDTH))
    isbitstype(typeof(bodies.combined)) || error("Candidate C composed CUDA body must be isbits")
    sim = WaterLily.Simulation(
        case.flow_dims, v16_native_far_field_uBC, Float32(case.solver_length);
        U=Float32(case.solver_velocity), ν=Float32(case.solver_viscosity),
        exitBC=true, body=bodies.combined, T=Float32, mem=CuArray,
    )
    owned = OwnedV16Run(owner, bodies, sim)
    GC.@preserve owned begin
        run_case_measurement(case, owned, phi_margin, phi_f_sha, phi_c_sha,
            roundtrip_sha, vram_total)
    end
end

function main()
    cases = Tuple(c for c in w4_cases(CANONICAL_ORIGIN_M, CANONICAL_DESIGN_SPACING_M)
        if c.case_id == "flow_32")
    Tuple(case.case_id for case in cases) == EXPECTED_CASE_IDS || error("W4 case inventory drift")
    all(case -> case.canonical_design_origin_m == CANONICAL_ORIGIN_M
        && case.canonical_design_spacing_m == CANONICAL_DESIGN_SPACING_M, cases) ||
        error("W4 flow grid and canonical design lattice identities were mixed")
    mkpath(output_dir)
    grid, margin, phi_f_sha, phi_c_sha = load_canonical_grid(phi_raw_path)
    device_owner = device_copy(grid)
    roundtrip_sha = device_roundtrip_sha(device_owner)
    roundtrip_sha == EXPECTED_PHI_FORTRAN_SHA256 || error("canonical $(CANONICAL_STATE_LABEL) GPU round-trip hash mismatch")
    vram_total = last(CUDA.memory_info())
    GC.@preserve device_owner begin
        for case in cases
            run_case(case, device_owner, margin, phi_f_sha, phi_c_sha, roundtrip_sha, vram_total)
            GC.gc()
            CUDA.synchronize()
        end
    end
    write(joinpath(output_dir, "W4_JOB_DONE"), "The registered LOWDIM-02A flow_32 case returned; host verification required.\n")
    println("W4_$(uppercase(CANONICAL_STATE_LABEL))_SENSITIVITY_DONE cases=", length(cases))
    flush(stdout)
end

main()
