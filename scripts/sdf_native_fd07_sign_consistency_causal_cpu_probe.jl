# Bounded FD-07 causal diagnostic; no production source is changed.
# Usage: julia -t 4 --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_sign_consistency_causal_cpu_probe.jl <evidence-dir>
using WaterLily, SHA, Statistics

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for file in ("V16PhysicalProfile.jl", "V16W4Sensitivity.jl", "WaterLilyNormalFloorBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, file))
end

const BASE_HEAD = "b41c8fa8ff054f7f9aeee983850dadeefdf8a7d4"
const BODY_SHA256 = "aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee"
const SHAPE = (121, 65, 49)
const DESIGN_ORIGIN = (-1.0, -0.8, -0.6)
const H = 0.025
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOOR = 0.25f0
const CASE = only(filter(c -> c.case_id == "flow_24",
    CFDSDFWaterLily.V16W4Sensitivity.w4_cases(DESIGN_ORIGIN, H)))
const RUN_CASES = vcat(["baseline"], [
    "seed_$(seed)_$(sign)_$(amp)" for seed in (1, 11, 2026)
    for amp in ("1e-08", "1e-07") for sign in ("plus", "minus")
])
const ARMS = ("UPSTREAM", "NO_SIGN_CORRECTION")

struct DiagnosticBody{B,C} <: WaterLily.AbstractBody
    inner::B
    correction::C
end

WaterLily.measure(body::DiagnosticBody, x::AbstractVector, t; fastd²=eltype(x)(Inf)) =
    WaterLily.measure(body.inner, x, t; fastd²)

@inline apply_sign_consistency(dᵢ, center, ::Val{true}) =
    abs(dᵢ) ≤ 0.5 ? dᵢ : copysign(dᵢ, center)
@inline apply_sign_consistency(dᵢ, center, ::Val{false}) = dᵢ

# Diagnostic-only copy of the pinned WaterLily 1.8.0 Body.jl measure! method.
# The only intervention is the apply_sign_consistency dispatch above.
function WaterLily.measure!(a::WaterLily.AbstractFlow{N,T},
                            body::DiagnosticBody; t=zero(T), ϵ=1) where {N,T}
    a.V .= zero(T)
    a.μ₀ .= one(T)
    a.μ₁ .= zero(T)
    d² = T(2 + ϵ)^2
    WaterLily.measure_sdf!(a.σ, body, t; fastd²=d²)
    @fastmath @inline function fill_body!(μ₀, μ₁, V, d, I)
        if d[I]^2 < d²
            for i ∈ 1:N
                dᵢ, nᵢ, Vᵢ = WaterLily.measure(body, WaterLily.loc(i, I, T), t, fastd²=d²)
                dᵢ = apply_sign_consistency(dᵢ, d[I], body.correction)
                V[I, i] = Vᵢ[i]
                μ₀[I, i] = WaterLily.μ₀(dᵢ, ϵ)
                for j ∈ 1:N
                    μ₁[I, i, j] = WaterLily.μ₁(dᵢ, ϵ) * nᵢ[j]
                end
            end
        elseif d[I] < zero(T)
            for i ∈ 1:N
                μ₀[I, i] = zero(T)
            end
        end
    end
    WaterLily.@loop fill_body!(a.μ₀, a.μ₁, a.V, a.σ, I) over I ∈ WaterLily.inside(a.p)
    WaterLily.BC!(a.μ₀, zeros(WaterLily.SVector{N,T}), false, a.perdir)
    WaterLily.BC!(a.V, zeros(WaterLily.SVector{N,T}), a.exitBC, a.perdir)
end

sha(data::AbstractVector{UInt8}) = bytes2hex(sha256(data))
sha(path::AbstractString) = sha(read(path))
array_sha(array) = sha(reinterpret(UInt8, vec(Array(array))))
same_array(a, b) = size(a) == size(b) && all(isequal.(a, b))

function write_checked_record(path, payload)
    if isfile(path)
        read(path, String) == payload || error("existing preflight record differs: $path")
    else
        open_exclusive(path) do io
            write(io, payload)
        end
    end
    return nothing
end

function open_exclusive(f::Function, path)
    flags = Base.Filesystem.JL_O_WRONLY | Base.Filesystem.JL_O_CREAT | Base.Filesystem.JL_O_EXCL
    io = Base.Filesystem.open(path, flags, 0o666)
    try
        f(io)
    finally
        close(io)
    end
end

function ensure_plan(outdir)
    plan_path = joinpath(outdir, "plan.json")
    plan_text = read(plan_path, String)
    plan_sha = split(read(joinpath(outdir, "plan.sha256"), String))[1]
    sha(plan_path) == plan_sha || error("preregistered plan hash mismatch")
    planned_hash(name) = begin
        found = match(Regex("\\\"" * name * "\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\""), plan_text)
        found === nothing && error("plan is missing registered hash $name")
        found.captures[1]
    end
    input_manifest = joinpath(outdir, "input_files.sha256")
    sha(input_manifest) == planned_hash("input_files_manifest_sha256") ||
        error("input file manifest differs from preregistration")
    source_manifest = joinpath(outdir, "repository_sources.sha256")
    sha(source_manifest) == planned_hash("repository_sources_manifest_sha256") ||
        error("repository source manifest differs from preregistration")
    body_path = joinpath(pkgdir(WaterLily), "src", "Body.jl")
    Base.pkgversion(WaterLily) == v"1.8.0" || error("WaterLily version drift")
    sha(body_path) == BODY_SHA256 || error("WaterLily Body.jl hash drift")
    for line in eachline(input_manifest)
        expected, relative = split(line, "  "; limit=2)
        sha(joinpath(outdir, relative)) == expected || error("input hash mismatch: $relative")
    end
    for line in eachline(joinpath(outdir, "repository_sources.sha256"))
        expected, relative = split(line, "  "; limit=2)
        sha(joinpath(ROOT, relative)) == expected || error("preregistered repository source changed: $relative")
    end
    return plan_sha
end

function make_grid(phi)
    GridSDF(phi; origin=DESIGN_ORIGIN, h=(H, H, H),
        outside_value=3.0, margin_m=0.15)
end

function make_candidate(phi)
    grid = make_grid(phi)
    return CFDSDFWaterLily.NormalFloorWaterLilyBody(
        grid, Float32.(CASE.flow_origin_m), Float32(CASE.flow_spacing_m), FLOOR)
end

make_ground() = CFDSDFWaterLily.V16MovingGroundBody(0f0, 1f0)

function make_sim(body)
    WaterLily.Simulation(CASE.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
        Float32(CASE.solver_length);
        U=Float32(CASE.solver_velocity), ν=Float32(CASE.solver_viscosity),
        exitBC=true, body, T=Float32, mem=Array)
end

function csv_column(header, name)
    index = findfirst(==(name), header)
    index === nothing && error("fixed-face CSV is missing column $name")
    return index
end

function fixed_face_values(path, wanted_maps, wanted_runs)
    lines = readlines(path)
    isempty(lines) && error("empty registered fixed-face CSV")
    header = split(first(lines), ',')
    col = Dict(name => csv_column(header, name) for name in
        ("map", "run_id", "i", "j", "k", "axis", "center_solver", "face_solver",
         "corrected_face_solver", "mu0_corrected", "mu0_uncorrected"))
    values = Dict((map_name, run_id) => Dict{NTuple{4,Int},NTuple{5,Float32}}()
        for map_name in wanted_maps for run_id in wanted_runs)
    for line in Iterators.drop(lines, 1)
        isempty(line) && continue
        fields = split(line, ',')
        length(fields) == length(header) || error("malformed fixed-face CSV row")
        map_name = fields[col["map"]]
        run_id = fields[col["run_id"]]
        haskey(values, (map_name, run_id)) || continue
        key = (parse(Int, fields[col["i"]]), parse(Int, fields[col["j"]]),
               parse(Int, fields[col["k"]]), parse(Int, fields[col["axis"]]))
        target = values[(map_name, run_id)]
        haskey(target, key) && error("duplicate fixed face $run_id/$key")
        target[key] = (
            parse(Float32, fields[col["center_solver"]]),
            parse(Float32, fields[col["face_solver"]]),
            parse(Float32, fields[col["corrected_face_solver"]]),
            parse(Float32, fields[col["mu0_corrected"]]),
            parse(Float32, fields[col["mu0_uncorrected"]]),
        )
    end
    return values
end

function check_fixed_face_control(outdir)
    plan_path = joinpath(outdir, "plan.json")
    plan = read(plan_path, String)
    contains(plan, "\"source_csv_sha256\": \"ddc3e5ed8470c7c247cc616b686f078a9ce2ab91414b91ba0eb73d7ac2ce7519\"") ||
        error("plan does not register the FD-07 fixed-face control hash")
    maps = ("A", "B", "C")
    runs = ("baseline", "seed1_plus_1e-8", "seed1_minus_1e-8")
    source = fixed_face_values(joinpath(outdir, "controls", "fd07_fixed_face_scalar_ablation.csv"), maps, runs)
    all(length(source[(map_name, run_id)]) == 261 for map_name in maps for run_id in runs) ||
        error("fixed-face control does not contain exactly 261 faces per map and run")
    expected = Dict(
        "A" => Dict("seed1_plus_1e-8" => (0.81831123, 54, 2.6e-7),
                    "seed1_minus_1e-8" => (0.81831123, 64, 2.7e-7)),
        "B" => Dict("seed1_plus_1e-8" => (2.5e-7, 0, 2.5e-7),
                    "seed1_minus_1e-8" => (2.6e-7, 0, 2.6e-7)),
        "C" => Dict("seed1_plus_1e-8" => (0.818310245, 10, 2.5e-7),
                    "seed1_minus_1e-8" => (0.818310335, 23, 2.5e-7)),
    )
    recorded_mu0_tolerance = 5e-7
    expected_stats_tolerance = 5e-7
    rows = NamedTuple[]
    all_pass = true
    for map_name in maps, run_id in runs
        current = source[(map_name, run_id)]
        base = source[(map_name, "baseline")]
        Set(keys(current)) == Set(keys(base)) || error("fixed-face identities differ for $map_name/$run_id")
        corrected_deltas = Float64[]
        uncorrected_deltas = Float64[]
        recorded_mu0_error = 0.0
        corrected_face_bitwise_equal = true
        for key in keys(base)
            center, face, recorded_corrected_face, recorded_mu0_corrected, recorded_mu0_uncorrected = current[key]
            corrected_face = apply_sign_consistency(face, center, Val(true))
            mu0_corrected = WaterLily.μ₀(corrected_face, 1)
            mu0_uncorrected = WaterLily.μ₀(face, 1)
            recorded_mu0_error = max(recorded_mu0_error,
                abs(Float64(mu0_corrected) - Float64(recorded_mu0_corrected)),
                abs(Float64(mu0_uncorrected) - Float64(recorded_mu0_uncorrected)))
            corrected_face_bitwise_equal &= isequal(corrected_face, recorded_corrected_face)
            push!(corrected_deltas, Float64(mu0_corrected) - Float64(WaterLily.μ₀(
                apply_sign_consistency(base[key][2], base[key][1], Val(true)), 1)))
            push!(uncorrected_deltas, Float64(mu0_uncorrected) - Float64(WaterLily.μ₀(base[key][2], 1)))
        end
        corrected_max = maximum(abs, corrected_deltas)
        corrected_count = count(value -> abs(value) > 1e-3, corrected_deltas)
        uncorrected_max = maximum(abs, uncorrected_deltas)
        uncorrected_count = count(value -> abs(value) > 1e-3, uncorrected_deltas)
        if run_id == "baseline"
            expected_max, expected_count, expected_uncorrected_max = (0.0, 0, 0.0)
        else
            expected_max, expected_count, expected_uncorrected_max = expected[map_name][run_id]
        end
        pass = corrected_count == expected_count && abs(corrected_max - expected_max) <= expected_stats_tolerance &&
            uncorrected_count == 0 && abs(uncorrected_max - expected_uncorrected_max) <= expected_stats_tolerance &&
            recorded_mu0_error <= recorded_mu0_tolerance && corrected_face_bitwise_equal
        all_pass &= pass
        push!(rows, (map=map_name, run_id=run_id, face_count=length(current),
            corrected_max_abs_delta=corrected_max,
            corrected_count_abs_delta_gt_1e_3=corrected_count,
            uncorrected_max_abs_delta=uncorrected_max,
            uncorrected_count_abs_delta_gt_1e_3=uncorrected_count,
            recorded_mu0_max_abs_error=recorded_mu0_error,
            corrected_face_bitwise_equal=corrected_face_bitwise_equal,
            control_pass=pass))
    end
    control_io = IOBuffer()
    println(control_io, "map,run_id,face_count,corrected_max_abs_delta,corrected_count_abs_delta_gt_1e-3,uncorrected_max_abs_delta,uncorrected_count_abs_delta_gt_1e-3,recorded_mu0_max_abs_error,corrected_face_bitwise_equal,control_pass")
    for row in rows
        println(control_io, join(string.((row.map, row.run_id, row.face_count, row.corrected_max_abs_delta,
            row.corrected_count_abs_delta_gt_1e_3, row.uncorrected_max_abs_delta,
            row.uncorrected_count_abs_delta_gt_1e_3, row.recorded_mu0_max_abs_error,
            row.corrected_face_bitwise_equal, row.control_pass)), ","))
    end
    write_checked_record(joinpath(outdir, "fixed_face_control.csv"), String(take!(control_io)))
    all_pass || error("registered FD-07 fixed-face scalar control failed; no force solve started")
    return rows
end

const FLOW_ARRAYS = ((:sigma, :σ), (:mu0, :μ₀), (:mu1, :μ₁), (:body_velocity, :V))
function field_hashes(sim)
    Dict(String(label) => array_sha(getproperty(sim.flow, field)) for (label, field) in FLOW_ARRAYS)
end

function check_initialization_controls(outdir, phi)
    candidate = make_candidate(phi)
    ground = make_ground()
    native_combined = make_sim(candidate + ground)
    upstream = DiagnosticBody(candidate + ground, Val(true))
    copied_upstream = make_sim(upstream)
    native_hashes = field_hashes(native_combined)
    copied_hashes = field_hashes(copied_upstream)
    native_matches = all(same_array(getproperty(native_combined.flow, field),
                                    getproperty(copied_upstream.flow, field))
                         for (_, field) in FLOW_ARRAYS)
    native_matches || error("diagnostic UPSTREAM copy does not match native initialization")

    ground_native = make_sim(ground)
    ground_no_correction = make_sim(DiagnosticBody(ground, Val(false)))
    ground_matches = all(same_array(getproperty(ground_native.flow, field),
                                    getproperty(ground_no_correction.flow, field))
                         for (_, field) in FLOW_ARRAYS)
    ground_matches || error("NO_SIGN_CORRECTION changes the moving-ground-only initialization")
    fixed_face_rows = check_fixed_face_control(outdir)

    path = joinpath(outdir, "preflight.txt")
    preflight_io = IOBuffer()
    println(preflight_io, "evidence_class=solver_free_preflight")
    println(preflight_io, "plan_sha256=", sha(joinpath(outdir, "plan.json")))
    println(preflight_io, "native_vs_diagnostic_upstream_exact=", native_matches)
    println(preflight_io, "native_upstream_hashes=", join((k * ":" * v for (k, v) in sort(collect(native_hashes))), ","))
    println(preflight_io, "diagnostic_upstream_hashes=", join((k * ":" * v for (k, v) in sort(collect(copied_hashes))), ","))
    println(preflight_io, "moving_ground_native_vs_no_correction_exact=", ground_matches)
    println(preflight_io, "moving_ground_upstream_hashes=", join((k * ":" * v for (k, v) in sort(collect(field_hashes(ground_native)))), ","))
    println(preflight_io, "moving_ground_no_correction_hashes=", join((k * ":" * v for (k, v) in sort(collect(field_hashes(ground_no_correction)))), ","))
    println(preflight_io, "combined_ground_z_plane_solver=0.0")
    println(preflight_io, "combined_ground_velocity_x_solver=1.0")
    println(preflight_io, "fixed_face_scalar_control_pass=true")
        for row in fixed_face_rows
            println(preflight_io, "fixed_face_", row.map, "_", row.run_id, "_faces=", row.face_count,
                " corrected_max_abs_delta=", row.corrected_max_abs_delta,
            " corrected_count_gt_1e-3=", row.corrected_count_abs_delta_gt_1e_3,
            " uncorrected_max_abs_delta=", row.uncorrected_max_abs_delta,
            " uncorrected_count_gt_1e-3=", row.uncorrected_count_abs_delta_gt_1e_3)
    end
    println(preflight_io, "flow_dims=", join(CASE.flow_dims, "x"))
    println(preflight_io, "flow_origin_m=", join(FLOW_ORIGIN, ","))
    println(preflight_io, "flow_spacing_m=", CASE.flow_spacing_m)
    println(preflight_io, "normal_floor=", FLOOR)
    println(preflight_io, "qualification_flags=false")
    write_checked_record(path, String(take!(preflight_io)))
    return nothing
end

function capture_inputs(sim, body, phi_sha)
    p = sim.flow.p
    dims = size(p)
    sample_dims = (dims..., 3)
    vector_dims = (dims..., 3, 3)
    face_distance = zeros(Float32, sample_dims)
    face_normal = zeros(Float32, vector_dims)
    face_velocity = zeros(Float32, vector_dims)
    branch_mask = falses(sample_dims)
    sign_flip_mask = falses(sample_dims)
    d² = Float32(2 + sim.ϵ)^2
    for I in WaterLily.inside(p)
        center = sim.flow.σ[I]
        center^2 < d² || continue
        for i in 1:3
            dᵢ, nᵢ, Vᵢ = WaterLily.measure(body, WaterLily.loc(i, I, Float32), 0f0; fastd²=d²)
            face_distance[I, i] = dᵢ
            branch = abs(dᵢ) > 0.5
            branch_mask[I, i] = branch
            sign_flip_mask[I, i] = branch && (signbit(dᵢ) != signbit(center))
            for j in 1:3
                face_normal[I, i, j] = nᵢ[j]
                face_velocity[I, i, j] = Vᵢ[j]
            end
        end
    end
    hashes = Dict(
        "phi_sha256" => phi_sha,
        "sigma_center_sha256" => array_sha(sim.flow.σ),
        "raw_face_distance_sha256" => array_sha(face_distance),
        "raw_face_normal_sha256" => array_sha(face_normal),
        "raw_face_velocity_sha256" => array_sha(face_velocity),
        "initialized_velocity_sha256" => array_sha(sim.flow.V),
    )
    stats = (
        branch_face_count=count(branch_mask),
        sign_flip_face_count=count(sign_flip_mask),
        branch_mask=branch_mask,
        sign_flip_mask=sign_flip_mask,
        hashes=hashes,
    )
    return stats
end

function delta_stats(current, reference; threshold=1e-3)
    delta = Float64.(Array(current)) .- Float64.(Array(reference))
    (changed=count(!iszero, delta), max_abs=maximum(abs, delta),
     count_gt_threshold=count(x -> abs(x) > threshold, delta))
end

function load_phi(outdir, case_id)
    record_path = case_id == "baseline" ? "inputs/phi/baseline.raw" : "inputs/phi/$(case_id).raw"
    raw = read(joinpath(outdir, record_path))
    length(raw) == prod(SHAPE) * sizeof(Float32) || error("wrong phi byte count: $case_id")
    return reshape(copy(reinterpret(Float32, raw)), SHAPE), sha(raw)
end

function write_runtime(outdir, plan_sha, sim)
    body_path = joinpath(pkgdir(WaterLily), "src", "Body.jl")
    open_exclusive(joinpath(outdir, "runtime.txt")) do io
        println(io, "plan_sha256=", plan_sha)
        println(io, "julia_version=", VERSION, " threads=", Threads.nthreads())
        println(io, "kernel=", Sys.KERNEL, " arch=", Sys.ARCH, " cpu=", Sys.CPU_NAME)
        println(io, "WaterLily_version=", Base.pkgversion(WaterLily), " package=", pkgdir(WaterLily))
        println(io, "Body.jl_sha256=", sha(body_path))
        println(io, "flow_dims=", join(CASE.flow_dims, "x"), " origin_m=", join(FLOW_ORIGIN, ","),
            " spacing_m=", CASE.flow_spacing_m, " solver_length=", CASE.solver_length)
        println(io, "flow_type=", typeof(sim.flow), " poisson_type=", typeof(sim.pois))
        println(io, "cpu_backend=Array Float32")
        for (dir, dirs, files) in walkdir(joinpath(pkgdir(WaterLily), "src"))
            sort!(dirs); sort!(files)
            for file in files
                endswith(file, ".jl") || continue
                path = joinpath(dir, file)
                println(io, sha(path), "  ", path)
            end
        end
    end
end

function main(outdir)
    plan_sha = ensure_plan(outdir)
    phi0, phi0_sha = load_phi(outdir, "baseline")
    check_initialization_controls(outdir, phi0)
    candidate = make_candidate(phi0)
    first_sim = make_sim(DiagnosticBody(candidate + make_ground(), Val(true)))
    write_runtime(outdir, plan_sha, first_sim)

    open_exclusive(joinpath(outdir, "initialization.csv")) do initio
        println(initio, "arm,case_id,phi_sha256,mu0_sha256,mu1_sha256,sigma_sha256,flow_velocity_sha256,branch_face_count,sign_flip_face_count,threshold_branch_changed_faces,sign_flip_decision_changed_faces,mu0_changed_vs_arm_baseline,mu0_max_delta_vs_arm_baseline,mu0_count_delta_gt_1e-3,mu1_changed_vs_arm_baseline,mu1_max_delta_vs_arm_baseline,mu1_count_delta_gt_1e-3,ab_mu0_max_delta,ab_mu0_count_gt_1e-3,ab_mu1_max_delta,ab_mu1_count_gt_1e-3,input_hashes")
        base_mu0 = Dict{String,Array}()
        base_mu1 = Dict{String,Array}()
        base_masks = Dict{String,Tuple{BitArray,BitArray}}()
        for case_id in RUN_CASES
            phi, phi_sha = load_phi(outdir, case_id)
            case_id == "baseline" && phi_sha != phi0_sha && error("registered baseline phi changed")
            arms = Dict{String,NamedTuple}()
            for arm in ARMS
                candidate = make_candidate(phi)
                body = candidate + make_ground()
                correction = arm == "UPSTREAM" ? Val(true) : Val(false)
                probe_body = DiagnosticBody(body, correction)
                sim = make_sim(probe_body)
                input_stats = capture_inputs(sim, probe_body, phi_sha)
                arms[arm] = (; candidate, probe_body, sim, input_stats)
            end
            arms["UPSTREAM"].input_stats.hashes == arms["NO_SIGN_CORRECTION"].input_stats.hashes ||
                error("A/B raw body-map inputs differ for $case_id")

            if case_id == "baseline"
                for arm in ARMS
                    base_mu0[arm] = copy(arms[arm].sim.flow.μ₀)
                    base_mu1[arm] = copy(arms[arm].sim.flow.μ₁)
                    base_masks[arm] = (
                        arms[arm].input_stats.branch_mask,
                        arms[arm].input_stats.sign_flip_mask,
                    )
                end
            end
            ab_mu0 = delta_stats(arms["NO_SIGN_CORRECTION"].sim.flow.μ₀,
                                 arms["UPSTREAM"].sim.flow.μ₀)
            ab_mu1 = delta_stats(arms["NO_SIGN_CORRECTION"].sim.flow.μ₁,
                                 arms["UPSTREAM"].sim.flow.μ₁)
            for arm in ARMS
                current = arms[arm]
                stats = current.input_stats
                mask0, mask1 = base_masks[arm]
                branch_changed = count(stats.branch_mask .!= mask0)
                flip_changed = count(stats.sign_flip_mask .!= mask1)
                mu0_stats = delta_stats(current.sim.flow.μ₀, base_mu0[arm])
                mu1_stats = delta_stats(current.sim.flow.μ₁, base_mu1[arm])
                packed_hashes = join((k * ":" * v for (k, v) in sort(collect(stats.hashes))), ";")
                values = (arm, case_id, phi_sha, array_sha(current.sim.flow.μ₀),
                    array_sha(current.sim.flow.μ₁), array_sha(current.sim.flow.σ),
                    array_sha(current.sim.flow.V), stats.branch_face_count,
                    stats.sign_flip_face_count, branch_changed, flip_changed,
                    mu0_stats.changed, mu0_stats.max_abs, mu0_stats.count_gt_threshold,
                    mu1_stats.changed, mu1_stats.max_abs, mu1_stats.count_gt_threshold,
                    ab_mu0.max_abs, ab_mu0.count_gt_threshold,
                    ab_mu1.max_abs, ab_mu1.count_gt_threshold, packed_hashes)
                println(initio, join(string.(values), ","))
                flush(initio)
            end
            for arm in ARMS
                current = arms[arm]
                write_history(outdir, current.sim, current.candidate, arm, case_id)
            end
            GC.gc()
        end
    end
    return nothing
end

function write_history(outdir, sim, candidate, arm, case_id)
    path = joinpath(outdir, lowercase(arm), case_id * ".csv")
    mkpath(dirname(path))
    open_exclusive(path) do io
        println(io, "step,t_u_l,drag_solver,downforce_solver,pressure_fx_solver,pressure_fz_solver,viscous_fx_solver,viscous_fz_solver")
        step = 0
        while WaterLily.sim_time(sim) < 3.0
            WaterLily.sim_step!(sim)
            step += 1
            if step % 8 == 0 || WaterLily.sim_time(sim) >= 3.0
                pressure = -WaterLily.pressure_force(sim.flow, candidate)
                viscous = -WaterLily.viscous_force(sim.flow, candidate)
                force = pressure + viscous
                all(isfinite, force) || error("nonfinite diagnostic force: $arm/$case_id")
                println(io, join((step, WaterLily.sim_time(sim), force[1], -force[3],
                    pressure[1], pressure[3], viscous[1], viscous[3]), ","))
                flush(io)
            end
        end
    end
    println(stderr, arm, "/", case_id, " complete at tU/L=", WaterLily.sim_time(sim))
end

if length(ARGS) == 2 && ARGS[1] == "--preflight-only"
    outdir = abspath(ARGS[2])
    ensure_plan(outdir)
    phi, _ = load_phi(outdir, "baseline")
    check_initialization_controls(outdir, phi)
    println("solver_free_preflight=passed flow_steps=0")
elseif length(ARGS) == 1
    main(abspath(only(ARGS)))
else
    error("usage: julia ... [--preflight-only] <evidence-dir>")
end
