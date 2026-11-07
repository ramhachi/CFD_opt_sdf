#!/usr/bin/env julia
# CPU-only source-path regression. It executes both production measurement
# functions, extracting their ASTs to avoid either GPU-only top-level/main path.
# Test-only changes: Array storage, CUDA telemetry stub, sample cadence 1, window
# [0.15,0.30] and the corresponding stationarity split 0.225. No force/sampling,
# CSV, clipping, or integration expression is replaced.
using SHA
using Test
using WaterLily

const FORCE00_REPO = normpath(joinpath(@__DIR__, ".."))
include(joinpath(@__DIR__, "waterlily_force00_dispatch.jl"))
include(joinpath(FORCE00_REPO, "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily, joinpath(FORCE00_REPO, "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
for source in ("V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl",
               "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")
    Base.include(CFDSDFWaterLily,
        joinpath(FORCE00_REPO, "julia", "CFDSDFWaterLily", "src", source))
end

module Force00CPUTelemetry
used_memory() = 0
synchronize() = nothing
device() = nothing
name(::Nothing) = "CPU test telemetry stub; no CUDA execution"
end

function definition_name(expression)
    expression isa Expr || return nothing
    expression.head in (:function, :(=)) || return nothing
    signature = expression.args[1]
    while signature isa Expr && signature.head == :where
        signature = signature.args[1]
    end
    signature isa Expr && signature.head == :call ? signature.args[1] : nothing
end

function short_stationarity(expression)
    expression == 80.0 && return 0.15
    expression == 100.0 && return 0.225
    expression == 120.0 && return 0.30
    expression isa Expr || return expression
    Expr(expression.head, short_stationarity.(expression.args)...)
end

# The existing job loader remains the source of canonical-grid validation.
# Read identities and lattice values from evidence, rather than duplicate hashes.
function parent_constants()
    evidence = joinpath(FORCE00_REPO, "docs", "evidence", "v18_genesis_2026_10_19")
    text = read(joinpath(evidence, "genesis.json"), String)
    hash(key) = last(collect(eachmatch(Regex("\\\"$key\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\""), text))).captures[1]
    numbers(key, type) = Tuple(parse.(type, split(
        match(Regex("\\\"$key\\\"\\s*:\\s*\\[([^\\]]+)\\]"), text).captures[1], ',')))
    margin = parse(Float64, match(r"\"zero_level_margin_m\"\s*:\s*([0-9.eE+-]+)", text).captures[1])
    lattice = match(r"\"lattice\"\s*:\s*\{([^}]+)\}"s, text).captures[1]
    spacing = parse(Float64, match(r"\"spacing_m\"\s*:\s*([0-9.eE+-]+)", lattice).captures[1])
    constants = (
        CANONICAL_STATE_LABEL="v18",
        EXPECTED_STATE_SHA256=hash("state_sha256"),
        EXPECTED_STATE_NPZ_SHA256=hash("npz_sha256"),
        EXPECTED_PHI_C_ORDER_SHA256=hash("phi_c_order_sha256"),
        EXPECTED_PHI_FORTRAN_SHA256=hash("phi_fortran_order_sha256"),
        EXPECTED_SOURCE_STL_SHA256=hash("source_sha256"),
        CANONICAL_POINT_SHAPE=numbers("shape", Int),
        CANONICAL_CELL_SHAPE=numbers("shape", Int) .- 1,
        CANONICAL_ORIGIN_M=numbers("origin_m", Float64),
        CANONICAL_DESIGN_SPACING_M=spacing,
        REQUIRED_MARGIN_M=0.15,
        EXPECTED_MARGIN_M=margin,
        MARGIN_TOL_M=1e-6,
    )
    raw = joinpath(evidence, "v18_parent.phi_f4_fortran.raw")
    return constants, raw
end

function cpu_job_module(path, name, output_dir, constants)
    job = Module(name)
    for (key, value) in pairs(merge(constants, (
        T_END=0.30, BURN_IN=0.15, SAMPLE_EVERY=1, output_dir=output_dir,
        CFDSDFWaterLily=CFDSDFWaterLily,
        WaterLily=WaterLily, CUDA=Force00CPUTelemetry, sha256=SHA.sha256,
        sim_step! = WaterLily.sim_step!, sim_time=WaterLily.sim_time,
        GridSDF=CFDSDFWaterLily.GridSDFBody.GridSDF,
        zero_level_margin_m=CFDSDFWaterLily.GridSDFBody.zero_level_margin_m,
        validate_w4_case=CFDSDFWaterLily.V16W4Sensitivity.validate_w4_case,
    )))
        Core.eval(job, :(const $key = $value))
    end
    required = Set((:json_number, :json_array, :mean_column, :time_weighted_mean,
        :interpolate_force_row, :clipped_force_window, :stationarity_metrics,
        :load_canonical_grid, :write_force_csv, :run_case_measurement))
    loaded = Set{Symbol}()
    for expression in Meta.parseall(read(path, String); filename=path).args
        key = definition_name(expression)
        if key in required || key in (:force00_cpu_box, :force00_cv_box, :force00_source_sha256)
            Core.eval(job, key == :stationarity_metrics ? short_stationarity(expression) : expression)
            push!(loaded, key)
        end
    end
    issubset(required, loaded) || error("job source is missing measurement definitions")
    return job
end

call_job(job, name, arguments...) =
    Base.invokelatest(() -> getproperty(job, name)(arguments...))

function cpu_parent_sim(case, grid)
    T = Float32
    floor = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid,
        T.(case.flow_origin_m), T(case.flow_spacing_m), 0.25f0)
    candidate = CFDSDFWaterLily.CandidateCWaterLilyBody(floor)
    ground = CFDSDFWaterLily.V16MovingGroundBody(0.0f0, 1.0f0)
    combined = CFDSDFWaterLily.CandidateCWaterLilyBody(floor, ground)
    bodies = (; candidate, ground, combined)
    sim = WaterLily.Simulation(case.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
        T(case.solver_length); U=T(case.solver_velocity), ν=T(case.solver_viscosity),
        exitBC=true, body=combined, T=T, mem=Array)
    return (; sim, bodies)
end

function main()
    length(ARGS) == 1 || error("usage: force00_job_regression.jl <new_output_dir>")
    output = abspath(ARGS[1])
    ispath(output) && error("refusing to overwrite CPU regression output: $output")
    pkgversion(WaterLily) == v"1.8.0" || error("requires pinned WaterLily 1.8.0")
    constants, raw = parent_constants()
    # At flow_16 this encloses the complete v18 parent, excludes the ground,
    # and is checked by the production CV implementation against four-cell
    # body clearance, exact normal-face μ₀ = 1, and two-cell domain clearance.
    box = (31:69, 9:40, 7:30)
    baseline_dir, variant_dir = joinpath.(output, ("registered", "force00"))
    mkpath(baseline_dir)
    mkpath(variant_dir)
    baseline_source = joinpath(@__DIR__, "waterlily_lowdim02_flow32_job.jl")
    variant_source = joinpath(@__DIR__, "waterlily_force00_job.jl")
    # Check the optional F1 launcher structurally, without importing CUDA or
    # executing its main. Inventory selection is the only permitted rewrite.
    variant_ast = Meta.parseall(read(variant_source, String); filename=variant_source)
    for case_id in ("flow_24", "flow_32")
        selected = force00_case_expression.(variant_ast.args, Ref(case_id))
        changed = findall(i -> selected[i] != variant_ast.args[i], eachindex(selected))
        @test length(changed) == (case_id == "flow_24" ? 2 : 0)
        target = only(c for c in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(
            constants.CANONICAL_ORIGIN_M, constants.CANONICAL_DESIGN_SPACING_M)
            if c.case_id == case_id)
        @test target.cells_per_reference_length == (case_id == "flow_24" ? 24 : 32)
    end
    @test_throws ArgumentError force00_case_expression(:(main()), "flow_48")
    @test_throws ErrorException force00_case_expression(:(function main() end), "flow_24")
    baseline = cpu_job_module(baseline_source, :Force00BaselineJob, baseline_dir, constants)
    variant = cpu_job_module(variant_source, :Force00VariantJob, variant_dir, constants)
    case = first(CFDSDFWaterLily.V16W4Sensitivity.w4_cases(
        constants.CANONICAL_ORIGIN_M, constants.CANONICAL_DESIGN_SPACING_M))
    @test case.case_id == "flow_16"
    grid, margin, phi_f_sha, phi_c_sha = call_job(baseline, :load_canonical_grid, raw)
    registered, force00 = cpu_parent_sim(case, grid), cpu_parent_sim(case, grid)
    @test reinterpret(UInt8, vec(registered.sim.flow.u)) == reinterpret(UInt8, vec(force00.sim.flow.u))
    box_text = join(("$(first(r)):$(last(r))" for r in box), ',')
    withenv("FORCE00_CPU_TEST" => "1", "FORCE00_CV_BOX" => box_text) do
        for (job, owned) in ((baseline, registered), (variant, force00))
            call_job(job, :run_case_measurement, case, owned, margin,
                phi_f_sha, phi_c_sha, phi_f_sha, 0)
        end
    end
    original = read(joinpath(baseline_dir, "flow_16.forces.csv"), String)
    extended = readlines(joinpath(variant_dir, "flow_16.forces.csv"))
    summary_text = read(joinpath(variant_dir, "flow_16.summary.json"), String)
    for (key, expected) in (("force00_cv_box_lower", first.(box)),
                            ("force00_cv_box_upper", last.(box)))
        values = match(Regex("\\\"$key\\\"\\s*:\\s*\\[([^\\]]+)\\]"), summary_text)
        @test values !== nothing
        @test Tuple(parse.(Int, split(values.captures[1], ','))) == expected
    end
    projected = join((join(split(line, ',')[1:13], ',') for line in extended), '\n') * "\n"
    @test projected == original
    @test length(extended) >= 5
    for line in extended[2:end]
        values = split(line, ',')
        @test length(values) == 28
        @test values[14:18] == values[3:7]
        @test all(isfinite, parse.(Float64, values))
    end
    # New readouts must not perturb the following step through scratch arrays.
    for key in (:u, :u⁰, :p, :f, :μ₀, :μ₁, :Δt)
        @test reinterpret(UInt8, vec(getproperty(registered.sim.flow, key))) ==
            reinterpret(UInt8, vec(getproperty(force00.sim.flow, key)))
    end
    source_hashes = call_job(variant, :force00_source_sha256)
    @test length(source_hashes) == 3
    for (path, digest) in source_hashes
        @test digest == bytes2hex(sha256(read(joinpath(FORCE00_REPO, path))))
        @test occursin("\"$path\":\"$digest\"", summary_text)
    end
    for flag in ("force00_timing_comparable_to_registered", "force00_peak_vram_comparable_to_registered")
        @test occursin("\"$flag\":false", summary_text)
    end
    @test occursin("\"force00_timing_includes_readout_overhead\":true", summary_text)
    @test call_job(variant, :force00_cpu_box, box_text) == box
    @test_throws Exception call_job(variant, :force00_cpu_box, "1:2,3:4")
    @test_throws Exception call_job(variant, :force00_cpu_box, "2:1,3:4,5:6")
    @test_throws Exception call_job(variant, :force00_cpu_box, "a:2,3:4,5:6")
    withenv("FORCE00_CV_BOX" => box_text, "FORCE00_CPU_TEST" => nothing) do
        @test_throws ArgumentError call_job(variant, :force00_cv_box, case, force00.sim)
    end
    withenv("FORCE00_CV_BOX" => box_text, "FORCE00_CPU_TEST" => "1") do
        @test call_job(variant, :force00_cv_box, case, force00.sim) == box
        # A non-Array backend is rejected even with the CPU opt-in. This uses
        # an Array view rather than loading or initializing CUDA on the CPU.
        non_array = (; flow=(; u=view(force00.sim.flow.u, :, :, :, :)))
        @test_throws ArgumentError call_job(variant, :force00_cv_box, case, non_array)
    end
    # Exercise the exact production registry loader without a GPU or external
    # process, including both grid identities and fail-closed metadata guards.
    registry_path = joinpath(FORCE00_REPO, "docs", "harness", "force00_boxes.json")
    withenv("FORCE00_CV_BOX" => nothing, "FORCE00_CPU_TEST" => nothing) do
        for production_case in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(
                constants.CANONICAL_ORIGIN_M, constants.CANONICAL_DESIGN_SPACING_M)
            production_case.case_id in ("flow_24", "flow_32") || continue
            registered_box = call_job(variant, :force00_cv_box, production_case, force00.sim)
            @test all(first(r) <= last(r) for r in registered_box)
            @test all(i -> first(registered_box[i]) >= 4 &&
                last(registered_box[i]) <= production_case.flow_dims[i] - 1, 1:3)
        end
        @test_throws Exception call_job(variant, :force00_cv_box, case, force00.sim)
        valid_registration = read(registry_path, String)
        mktempdir() do scratch
            bad_path = joinpath(scratch, "boxes.json")
            production_case = only(c for c in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(
                constants.CANONICAL_ORIGIN_M, constants.CANONICAL_DESIGN_SPACING_M)
                if c.case_id == "flow_24")
            for (old, new) in (("force00_boxes_v1", "force00_boxes_v0"),
                    (constants.EXPECTED_STATE_SHA256, repeat("0", 64)),
                    (constants.EXPECTED_PHI_FORTRAN_SHA256, repeat("0", 64)),
                    (r"\"domain_inset_cells\"\s*:\s*2", "\"domain_inset_cells\":3"),
                    (r"\"body_clearance_cells\"\s*:\s*5", "\"body_clearance_cells\":4"),
                    (r"\"flow_dims\"\s*:\s*\[[^\]]+\]", "\"flow_dims\":[1,2,3]"),
                    (r"\"lower\"\s*:\s*\[[^\]]+\]", "\"lower\":[0,0,0]"))
                invalid = replace(valid_registration, old => new)
                @test invalid != valid_registration
                write(bad_path, invalid)
                @test_throws Exception Base.invokelatest(() ->
                    variant.force00_cv_box(production_case, force00.sim; path=bad_path))
            end
        end
    end
    projected_path = joinpath(output, "force00.original_columns.csv")
    write(projected_path, projected)
    receipt = """
    {
      "schema":"force00_cpu_job_regression_v1",
      "evidence_class":"CPU development regression; not T4 C1 evidence",
      "status":"PASS",
      "julia_version":"$(VERSION)",
      "waterlily_version":"$(pkgversion(WaterLily))",
      "case_id":"flow_16",
      "flow_dims":[100,48,36],
      "window":[0.15,0.30],
      "stationarity_split":0.225,
      "sample_every_solver_steps":1,
      "control_volume_box":[[31,69],[9,40],[7,30]],
      "samples":$(length(extended)-1),
      "source_ast_changes":"stationarity endpoints only; top-level/main not run; CUDA telemetry stub",
      "registered_source_sha256":"$(bytes2hex(sha256(read(baseline_source))))",
      "force00_source_sha256":"$(bytes2hex(sha256(read(variant_source))))",
      "force00_dispatch_sha256":"$(bytes2hex(sha256(read(joinpath(@__DIR__,"waterlily_force00_dispatch.jl")))))",
      "force_module_sha256":"$(bytes2hex(sha256(read(joinpath(FORCE00_REPO,"julia","CFDSDFWaterLily","src","Forces.jl")))))",
      "force00_module_sha256":"$(bytes2hex(sha256(read(joinpath(FORCE00_REPO,"julia","CFDSDFWaterLily","gen01","Force00.jl")))))",
      "parent_phi_fortran_sha256":"$phi_f_sha",
      "registered_csv_sha256":"$(bytes2hex(sha256(original)))",
      "force00_projected_csv_sha256":"$(bytes2hex(sha256(projected)))",
      "force00_extended_csv_sha256":"$(bytes2hex(sha256(read(joinpath(variant_dir,"flow_16.forces.csv")))))",
      "original_columns_byte_identical":true,
      "appended_cur_tokens_identical":true,
      "final_flow_arrays_byte_identical":true
    }
    """
    write(joinpath(output, "regression.json"), receipt)
    println("FORCE00_CPU_JOB_REGRESSION_PASS ", output)
end

main()
