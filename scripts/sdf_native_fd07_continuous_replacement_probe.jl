# Diagnostic-only coefficient and short CPU solve probe. No production code is patched.
using WaterLily, SHA, Statistics

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
include(joinpath(@__DIR__, "sdf_native_fd07_continuous_sign_operators.jl"))
using .SDFNativeFD07ContinuousSignOperators
for file in ("V16PhysicalProfile.jl", "V16W4Sensitivity.jl", "WaterLilyNormalFloorBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, file))
end

const EVIDENCE_REL = "docs/evidence/sdf_native_fd07_continuous_replacement_attempt02_2026_10"
const CAUSAL_REL = "docs/evidence/sdf_native_fd07_sign_consistency_causal_2026_10"
const BASE_HEAD = "ecaa1572734596130ffefdd0d7b0ab3c2af67c15"
const BRANCH = "exp/issue-37-continuous-sign-consistency"
const BODY_SHA256 = "aed03bb57053731c7d2098950d92df9b59fda3bd4f7aaaca51bb076bd5edcaee"
const SHAPE = (121, 65, 49)
const DESIGN_ORIGIN = (-1.0, -0.8, -0.6)
const H = 0.025
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOOR = 0.25f0
const CASE = only(filter(c -> c.case_id == "flow_24",
    CFDSDFWaterLily.V16W4Sensitivity.w4_cases(DESIGN_ORIGIN, H)))
const ALL_CASES = ("baseline",
    "seed_1_plus_1e-08", "seed_1_minus_1e-08", "seed_1_plus_1e-07", "seed_1_minus_1e-07",
    "seed_11_plus_1e-08", "seed_11_minus_1e-08", "seed_11_plus_1e-07", "seed_11_minus_1e-07",
    "seed_2026_plus_1e-08", "seed_2026_minus_1e-08", "seed_2026_plus_1e-07", "seed_2026_minus_1e-07")
const COEFFICIENT_MODES = MODES

struct DiagnosticBody{B,M} <: WaterLily.AbstractBody
    inner::B
    delta::Float32
end
DiagnosticBody(inner, ::Val{M}; delta=DEFAULT_DELTA) where M =
    DiagnosticBody{typeof(inner),M}(inner, Float32(delta))

WaterLily.measure(body::DiagnosticBody, x::AbstractVector, t; fastd²=eltype(x)(Inf)) =
    WaterLily.measure(body.inner, x, t; fastd²)

# Local copy of pinned WaterLily 1.8.0 Body.jl measure!; only the named
# diagnostic operator at the face-to-moment handoff varies.
function WaterLily.measure!(a::WaterLily.AbstractFlow{N,T},
                            body::DiagnosticBody{B,M}; t=zero(T), ϵ=1) where {N,T,B,M}
    a.V .= zero(T)
    a.μ₀ .= one(T)
    a.μ₁ .= zero(T)
    d² = T(2 + ϵ)^2
    WaterLily.measure_sdf!(a.σ, body, t; fastd²=d²)
    mode = Val(M)
    @fastmath @inline function fill_body!(μ₀, μ₁, V, d, I)
        if d[I]^2 < d²
            for i ∈ 1:N
                dᵢ, nᵢ, Vᵢ = WaterLily.measure(body, WaterLily.loc(i, I, T), t; fastd²=d²)
                m₀, m₁ = moment_values(dᵢ, d[I], mode, body.delta, ϵ)
                V[I, i] = Vᵢ[i]
                μ₀[I, i] = m₀
                for j ∈ 1:N
                    μ₁[I, i, j] = m₁ * nᵢ[j]
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
    return nothing
end

sha(data::AbstractVector{UInt8}) = bytes2hex(sha256(data))
sha(path::AbstractString) = sha(read(path))
array_sha(array) = sha(reinterpret(UInt8, vec(Array(array))))
same_array(a, b) = size(a) == size(b) && all(isequal.(a, b))

function write_exclusive(path, payload)
    mkpath(dirname(path))
    flags = Base.Filesystem.JL_O_WRONLY | Base.Filesystem.JL_O_CREAT | Base.Filesystem.JL_O_EXCL
    io = Base.Filesystem.open(path, flags, 0o666)
    try
        write(io, payload)
    finally
        close(io)
    end
end

function verify_plan(outdir)
    git(args...) = strip(read(Cmd(["git", "-C", ROOT, args...]), String))
    git("rev-parse", "HEAD") == BASE_HEAD || error("source HEAD drifted from preregistration base")
    git("branch", "--show-current") == BRANCH || error("not on the dedicated experiment branch")
    plan_path = joinpath(outdir, "plan.json")
    plan_text = read(plan_path, String)
    plan_sha = split(read(joinpath(outdir, "plan.sha256"), String))[1]
    sha(plan_path) == plan_sha || error("preregistered plan hash mismatch")
    body_path = joinpath(pkgdir(WaterLily), "src", "Body.jl")
    Base.pkgversion(WaterLily) == v"1.8.0" || error("WaterLily version drift")
    sha(body_path) == BODY_SHA256 || error("pinned Body.jl hash drift")
    for line in eachline(joinpath(outdir, "repository_sources.sha256"))
        expected, relative = split(line, "  "; limit=2)
        if relative == "pinned_WaterLily_Body.jl"
            sha(body_path) == expected || error("pinned Body.jl source manifest mismatch")
        else
            sha(joinpath(ROOT, relative)) == expected || error("preregistered source changed: $relative")
        end
    end
    source_match = match(r"\"repository_sources_manifest_sha256\"\s*:\s*\"([0-9a-f]{64})\"", plan_text)
    source_match !== nothing || error("plan is missing source manifest hash")
    sha(joinpath(outdir, "repository_sources.sha256")) == source_match.captures[1] ||
        error("source manifest identity mismatch")
    for line in eachline(joinpath(outdir, "input_files.sha256"))
        expected, relative = split(line, "  "; limit=2)
        sha(joinpath(ROOT, relative)) == expected || error("input field hash mismatch: $relative")
    end
    input_match = match(r"\"input_files_manifest_sha256\"\s*:\s*\"([0-9a-f]{64})\"", plan_text)
    input_match !== nothing || error("plan is missing input manifest hash")
    sha(joinpath(outdir, "input_files.sha256")) == input_match.captures[1] ||
        error("input manifest identity mismatch")
    return plan_sha
end

function make_grid(phi)
    GridSDF(phi; origin=DESIGN_ORIGIN, h=(H, H, H), outside_value=3.0, margin_m=0.15)
end
function make_candidate(phi)
    grid = make_grid(phi)
    CFDSDFWaterLily.NormalFloorWaterLilyBody(
        grid, Float32.(CASE.flow_origin_m), Float32(CASE.flow_spacing_m), FLOOR)
end
make_ground() = CFDSDFWaterLily.V16MovingGroundBody(0f0, 1f0)
function make_sim(body)
    WaterLily.Simulation(CASE.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
        Float32(CASE.solver_length); U=Float32(CASE.solver_velocity),
        ν=Float32(CASE.solver_viscosity), exitBC=true, body, T=Float32, mem=Array)
end

function load_phi(outdir, case_id)
    filename = case_id == "baseline" ? "baseline.raw" : case_id * ".raw"
    relative = joinpath(CAUSAL_REL, "inputs", "phi", filename)
    manifest_rows = readlines(joinpath(outdir, "input_files.sha256"))
    row = findfirst(line -> endswith(line, "  " * relative), manifest_rows)
    row === nothing && error("phi input is absent from the preregistered manifest: $case_id")
    expected = first(split(manifest_rows[row]))
    raw = read(joinpath(ROOT, relative))
    sha(raw) == expected || error("registered phi hash mismatch: $case_id")
    length(raw) == prod(SHAPE) * sizeof(Float32) || error("wrong phi byte count: $case_id")
    return reshape(copy(reinterpret(Float32, raw)), SHAPE), sha(raw)
end

function delta_stats(current, reference; threshold=1e-3)
    maximum_delta = 0.0
    sumsq = 0.0
    changed = 0
    count_threshold = 0
    nonfinite = 0
    for n in eachindex(current, reference)
        x, y = Float64(current[n]), Float64(reference[n])
        if !isfinite(x) || !isfinite(y)
            nonfinite += 1
            continue
        end
        d = x - y
        maximum_delta = max(maximum_delta, abs(d))
        sumsq += d * d
        changed += !iszero(d)
        count_threshold += abs(d) > threshold
    end
    return (; max_abs=maximum_delta, l2=sqrt(sumsq), changed, count_gt_threshold=count_threshold, nonfinite)
end

function support_changes(current, reference, predicate)
    changed = 0
    for n in eachindex(current, reference)
        changed += predicate(current[n]) != predicate(reference[n])
    end
    return changed
end

function pair_stats(plus, minus, baseline)
    odd_max = even_max = odd_sumsq = even_sumsq = 0.0
    odd_count = even_count = 0
    for n in eachindex(plus, minus, baseline)
        p, m, b = Float64(plus[n]), Float64(minus[n]), Float64(baseline[n])
        odd = (p - m) / 2
        even = (p + m) / 2 - b
        odd_max = max(odd_max, abs(odd)); even_max = max(even_max, abs(even))
        odd_sumsq += odd * odd; even_sumsq += even * even
        odd_count += abs(odd) > 1e-3; even_count += abs(even) > 1e-3
    end
    return (; odd_max, even_max, odd_l2=sqrt(odd_sumsq), even_l2=sqrt(even_sumsq),
        odd_count_gt_1e_3=odd_count, even_count_gt_1e_3=even_count)
end

function mode_result(phi, mode)
    candidate = make_candidate(phi)
    ground = make_ground()
    body = candidate + ground
    probe = DiagnosticBody(body, Val(mode))
    sim = make_sim(probe)
    hashes = Dict(String(label) => array_sha(getproperty(sim.flow, field)) for
        (label, field) in FLOW_ARRAYS)
    center_distance = mode == :UPSTREAM ? copy(sim.flow.σ) : nothing
    body_velocity = mode == :UPSTREAM ? copy(sim.flow.V) : nothing
    return (; candidate, ground, body, mu0=copy(sim.flow.μ₀), mu1=copy(sim.flow.μ₁),
        center_distance, body_velocity, hashes)
end

const FLOW_ARRAYS = ((:sigma, :σ), (:mu0, :μ₀), (:mu1, :μ₁), (:body_velocity, :V))
function array_hashes(result)
    result.hashes
end

function raw_geometry_stats(result, phi_sha)
    body = result.body
    center_field = result.center_distance
    face_distance = zeros(Float32, size(center_field)..., 3)
    face_normal = zeros(Float32, size(center_field)..., 3, 3)
    face_velocity = zeros(Float32, size(center_field)..., 3, 3)
    branch_mask = falses(size(center_field)..., 3)
    disagreement_mask = falses(size(center_field)..., 3)
    d² = Float32(2 + 1)^2
    for I in WaterLily.inside(center_field)
        center = center_field[I]
        center^2 < d² || continue
        for i in 1:3
            dᵢ, nᵢ, vᵢ = WaterLily.measure(body, WaterLily.loc(i, I, Float32), 0f0; fastd²=d²)
            face_distance[I, i] = dᵢ
            branch = abs(dᵢ) > 0.5
            branch_mask[I, i] = branch
            disagreement_mask[I, i] = branch && (signbit(dᵢ) != signbit(center))
            for j in 1:3
                face_normal[I, i, j] = nᵢ[j]
                face_velocity[I, i, j] = vᵢ[j]
            end
        end
    end
    return (; phi_sha, sigma_center_sha256=array_sha(center_field),
        raw_face_distance_sha256=array_sha(face_distance),
        raw_face_normal_sha256=array_sha(face_normal),
        raw_face_velocity_sha256=array_sha(face_velocity),
        branch_face_count=count(branch_mask), sign_disagree_face_count=count(disagreement_mask),
        branch_mask, disagreement_mask, face_distance)
end

function csv_row(io, values)
    println(io, join((replace(string(x), ',' => ';', '\n' => ' ') for x in values), ","))
end

function write_sensitive_faces(io, case_id, data, raw)
    upstream = data[:UPSTREAM]
    body = upstream.body
    center_field = upstream.center_distance
    d² = Float32(3)^2
    delta = DEFAULT_DELTA
    for I in WaterLily.inside(center_field)
        center = center_field[I]
        center^2 < d² || continue
        for axis in 1:3
            dface = raw.face_distance[I, axis]
            branch = abs(dface) > 0.5
            disagreement = branch && (signbit(dface) != signbit(center))
            upstream_mu0 = upstream.mu0[I, axis]
            changed = any(mode != :UPSTREAM &&
                abs(data[mode].mu0[I, axis] - upstream_mu0) > 1e-3 for mode in COEFFICIENT_MODES)
            (disagreement || changed) || continue
            loc = WaterLily.loc(axis, I, Float32)
            world = ntuple(q -> FLOW_ORIGIN[q] + CASE.flow_spacing_m * loc[q], 3)
            body_d = WaterLily.measure(upstream.candidate, loc, 0f0; fastd²=d²)[1]
            ground_d = WaterLily.measure(upstream.ground, loc, 0f0; fastd²=d²)[1]
            region = abs(ground_d) < abs(body_d) ? "moving_ground" : "design_body"
            w_a = activation_weight(dface, delta, Val(:A_THRESHOLD))
            w_c = activation_weight(dface, delta, Val(:C_MOMENT_BLEND)) *
                  smoothstep01((-sign(dface) * center) / delta)
            row_prefix = (case_id, I[1], I[2], I[3], axis, world..., center, dface,
                branch, disagreement, region, body_d, ground_d, w_a,
                activation_weight(dface, delta, Val(:B_CENTER_SIGN)), w_c)
            for mode in COEFFICIENT_MODES
                current = data[mode]
                mu1_delta = sqrt(sum((Float64(current.mu1[I, axis, j]) -
                    Float64(upstream.mu1[I, axis, j]))^2 for j in 1:3))
                csv_row(io, (row_prefix..., String(mode), current.mu0[I, axis],
                    current.mu0[I, axis] - upstream_mu0, mu1_delta,
                    current.mu1[I, axis, 1], current.mu1[I, axis, 2], current.mu1[I, axis, 3]))
            end
        end
    end
end

function emit_case_metrics(outdir, case_id, data, raw, baselines, base_masks, case_fields,
                           response_norms, field_io, metric_io, sensitive_io)
    upstream = data[:UPSTREAM]
    for mode in COEFFICIENT_MODES
        current = data[mode]
        hashes = array_hashes(current)
        vs_base0 = delta_stats(current.mu0, baselines[mode].mu0)
        vs_base1 = delta_stats(current.mu1, baselines[mode].mu1)
        vs_up0 = delta_stats(current.mu0, upstream.mu0)
        vs_up1 = delta_stats(current.mu1, upstream.mu1)
        branch_changed = case_id == "baseline" ? 0 : count(raw.branch_mask .!= base_masks.branch_mask)
        disagreement_changed = case_id == "baseline" ? 0 : count(raw.disagreement_mask .!= base_masks.disagreement_mask)
        sup0_base = support_changes(current.mu0, baselines[mode].mu0, x -> x != 1f0)
        sup1_base = support_changes(current.mu1, baselines[mode].mu1, x -> x != 0f0)
        sup0_up = support_changes(current.mu0, upstream.mu0, x -> x != 1f0)
        sup1_up = support_changes(current.mu1, upstream.mu1, x -> x != 0f0)
        csv_row(field_io, (mode, case_id, raw.phi_sha, hashes["sigma"], hashes["mu0"], hashes["mu1"],
            hashes["body_velocity"], raw.raw_face_distance_sha256, raw.raw_face_normal_sha256,
            raw.raw_face_velocity_sha256, raw.branch_face_count, raw.sign_disagree_face_count,
            branch_changed, disagreement_changed))
        csv_row(metric_io, (String(mode), case_id, raw.branch_face_count, raw.sign_disagree_face_count,
            vs_base0.max_abs, vs_base0.l2, vs_base0.count_gt_threshold,
            vs_base1.max_abs, vs_base1.l2, vs_base1.count_gt_threshold,
            vs_up0.max_abs, vs_up0.l2, vs_up0.count_gt_threshold,
            vs_up1.max_abs, vs_up1.l2, vs_up1.count_gt_threshold,
            sup0_base, sup1_base, sup0_up, sup1_up,
            vs_base0.nonfinite + vs_base1.nonfinite + vs_up0.nonfinite + vs_up1.nonfinite,
            branch_changed, disagreement_changed))
        response_norms[(case_id, mode)] = (; mu0=vs_base0.l2, mu1=vs_base1.l2)
        if case_id != "baseline"
            case_fields[(case_id, mode)] = (; mu0=current.mu0, mu1=current.mu1)
        end
    end
    write_sensitive_faces(sensitive_io, case_id, data, raw)
end

function check_ground_identity(outdir)
    native = make_sim(make_ground())
    path = joinpath(outdir, "moving_ground_identity.csv")
    write_exclusive(path, "mode,field,native_sha256,candidate_sha256,bitwise_equal\n")
    io = open(path, "a")
    try
        for mode in COEFFICIENT_MODES
            candidate = make_sim(DiagnosticBody(make_ground(), Val(mode)))
            for (label, field) in FLOW_ARRAYS
                native_array = getproperty(native.flow, field)
                candidate_array = getproperty(candidate.flow, field)
                csv_row(io, (String(mode), String(label), array_sha(native_array),
                    array_sha(candidate_array), same_array(native_array, candidate_array)))
            end
        end
    finally
        close(io)
    end
    return nothing
end

function coefficient_matrix(outdir)
    plan_sha = verify_plan(outdir)
    check_ground_identity(outdir)
    manifest_paths = Set(split(line, "  "; limit=2)[2] for line in
        readlines(joinpath(outdir, "input_files.sha256")))
    expected_paths = Set(joinpath(CAUSAL_REL, "inputs", "phi",
        case_id == "baseline" ? "baseline.raw" : case_id * ".raw") for case_id in ALL_CASES)
    expected_paths ⊆ manifest_paths || error("registered case matrix differs")
    header_fields = "mode,case_id,phi_sha256,sigma_sha256,mu0_sha256,mu1_sha256,body_velocity_sha256,raw_face_distance_sha256,raw_face_normal_sha256,raw_face_velocity_sha256,branch_face_count,sign_disagree_face_count,threshold_faces_changed_vs_baseline,disagreement_faces_changed_vs_baseline"
    header_metrics = "mode,case_id,branch_face_count,sign_disagree_face_count,mu0_max_abs_vs_mode_baseline,mu0_l2_vs_mode_baseline,mu0_count_gt_1e-3_vs_mode_baseline,mu1_max_abs_vs_mode_baseline,mu1_l2_vs_mode_baseline,mu1_count_gt_1e-3_vs_mode_baseline,mu0_max_abs_vs_upstream_same_case,mu0_l2_vs_upstream_same_case,mu0_count_gt_1e-3_vs_upstream_same_case,mu1_max_abs_vs_upstream_same_case,mu1_l2_vs_upstream_same_case,mu1_count_gt_1e-3_vs_upstream_same_case,mu0_support_changes_vs_mode_baseline,mu1_support_changes_vs_mode_baseline,mu0_support_changes_vs_upstream_same_case,mu1_support_changes_vs_upstream_same_case,nonfinite_count,threshold_faces_changed_vs_baseline,disagreement_faces_changed_vs_baseline"
    header_sensitive = "case_id,i,j,k,axis,face_x_m,face_y_m,face_z_m,center_solver,face_solver,threshold_branch,sign_disagreement,nearest_region,design_body_distance,ground_distance,w_A,w_B,w_C,mode,mu0,delta_mu0_vs_upstream,mu1_l2_delta_vs_upstream,mu1_x,mu1_y,mu1_z"
    fields_path = joinpath(outdir, "coefficient_field_hashes.csv")
    metrics_path = joinpath(outdir, "coefficient_metrics.csv")
    sensitive_path = joinpath(outdir, "sensitive_faces.csv")
    write_exclusive(fields_path, header_fields * "\n")
    write_exclusive(metrics_path, header_metrics * "\n")
    write_exclusive(sensitive_path, header_sensitive * "\n")
    field_io = open(fields_path, "a"); metric_io = open(metrics_path, "a"); sensitive_io = open(sensitive_path, "a")
    try
        baselines = Dict{Symbol,Any}()
        base_masks = nothing
        case_fields = Dict{Tuple{String,Symbol},NamedTuple}()
        response_norms = Dict{Tuple{String,Symbol},NamedTuple}()
        # Baseline maps are fixed once; never repeat them inside this matrix.
        phi, phi_sha = load_phi(outdir, "baseline")
        base_data = Dict(mode => mode_result(phi, mode) for mode in COEFFICIENT_MODES)
        raw_base = raw_geometry_stats(base_data[:UPSTREAM], phi_sha)
        base_masks = (; branch_mask=raw_base.branch_mask, disagreement_mask=raw_base.disagreement_mask)
        baselines = Dict(mode => (; mu0=base_data[mode].mu0, mu1=base_data[mode].mu1) for mode in COEFFICIENT_MODES)
        emit_case_metrics(outdir, "baseline", base_data, raw_base, baselines, base_masks,
                          case_fields, response_norms,
                          field_io, metric_io, sensitive_io)
        baseline_upstream = base_data[:UPSTREAM]
        baseline_native = make_sim(baseline_upstream.body)
        native_exact = same_array(baseline_native.flow.σ, baseline_upstream.center_distance) &&
            same_array(baseline_native.flow.μ₀, baseline_upstream.mu0) &&
            same_array(baseline_native.flow.μ₁, baseline_upstream.mu1) &&
            same_array(baseline_native.flow.V, baseline_upstream.body_velocity)
        native_exact || error("diagnostic UPSTREAM does not reproduce native initialization exactly")
        empty!(base_data); GC.gc()
        for seed in (1, 11, 2026), amplitude in ("1e-08", "1e-07"), sign in ("plus", "minus")
            case_id = "seed_$(seed)_$(sign)_$(amplitude)"
            phi, phi_sha = load_phi(outdir, case_id)
            data = Dict(mode => mode_result(phi, mode) for mode in COEFFICIENT_MODES)
            raw = raw_geometry_stats(data[:UPSTREAM], phi_sha)
            for mode in COEFFICIENT_MODES
                raw.sigma_center_sha256 == array_hashes(data[mode])["sigma"] ||
                    error("candidate altered center-distance field: $mode/$case_id")
            end
            emit_case_metrics(outdir, case_id, data, raw, baselines, base_masks,
                              case_fields, response_norms, field_io, metric_io, sensitive_io)
            if sign == "minus"
                plus_id = "seed_$(seed)_plus_$(amplitude)"
                pair_io_path = joinpath(outdir, "coefficient_pair_responses.csv")
                pair_exists = isfile(pair_io_path)
                pair_io = open(pair_io_path, "a")
                if !pair_exists
                    println(pair_io, "mode,seed,amplitude_m,mu0_odd_l2,mu0_even_l2,mu0_odd_max,mu0_even_max,mu1_odd_l2,mu1_even_l2,mu1_odd_max,mu1_even_max,mu0_plus_l2,mu0_minus_l2,mu1_plus_l2,mu1_minus_l2,monotone_10x_response")
                end
                previous_amp = amplitude == "1e-07" ? "1e-08" : nothing
                for mode in COEFFICIENT_MODES
                    plus = case_fields[(plus_id, mode)]
                    minus = case_fields[(case_id, mode)]
                    base = baselines[mode]
                    mu0_pair = pair_stats(plus.mu0, minus.mu0, base.mu0)
                    mu1_pair = pair_stats(plus.mu1, minus.mu1, base.mu1)
                    plus0 = delta_stats(plus.mu0, base.mu0); minus0 = delta_stats(minus.mu0, base.mu0)
                    plus1 = delta_stats(plus.mu1, base.mu1); minus1 = delta_stats(minus.mu1, base.mu1)
                    mono = true
                    if !isnothing(previous_amp)
                        prev_plus_norm = response_norms[("seed_$(seed)_plus_$(previous_amp)", mode)]
                        prev_minus_norm = response_norms[("seed_$(seed)_minus_$(previous_amp)", mode)]
                        mono = plus0.l2 >= prev_plus_norm.mu0 - 1e-12 &&
                               minus0.l2 >= prev_minus_norm.mu0 - 1e-12 &&
                               plus1.l2 >= prev_plus_norm.mu1 - 1e-12 &&
                               minus1.l2 >= prev_minus_norm.mu1 - 1e-12
                    end
                    csv_row(pair_io, (String(mode), seed, amplitude, mu0_pair.odd_l2, mu0_pair.even_l2,
                        mu0_pair.odd_max, mu0_pair.even_max, mu1_pair.odd_l2, mu1_pair.even_l2,
                        mu1_pair.odd_max, mu1_pair.even_max, plus0.l2, minus0.l2,
                        plus1.l2, minus1.l2, mono))
                end
                close(pair_io)
                for mode in COEFFICIENT_MODES
                    delete!(case_fields, (plus_id, mode))
                    delete!(case_fields, (case_id, mode))
                end
            end
            flush(field_io); flush(metric_io); flush(sensitive_io)
            empty!(data); GC.gc()
        end
        write_exclusive(joinpath(outdir, "coefficient_preflight.txt"),
            "evidence_class=solver_free_initialization_only\nplan_sha256=$plan_sha\nnative_upstream_initialization_exact=$native_exact\nsolver_steps=0\nnormal_floor=$FLOOR\nflow_case=flow_24\n")
    finally
        close(field_io); close(metric_io); close(sensitive_io)
    end
    return nothing
end

function open_force_file(outdir, mode, case_id)
    path = joinpath(outdir, "solved", lowercase(String(mode)), case_id * ".csv")
    mkpath(dirname(path))
    flags = Base.Filesystem.JL_O_WRONLY | Base.Filesystem.JL_O_CREAT | Base.Filesystem.JL_O_EXCL
    io = Base.Filesystem.open(path, flags, 0o666)
    println(io, "step,t_u_l,drag_solver,downforce_solver,pressure_fx_solver,pressure_fz_solver,viscous_fx_solver,viscous_fz_solver")
    return io
end

function write_force_history(io, sim, candidate, mode, case_id)
    step = 0
    while WaterLily.sim_time(sim) < 3.0
        WaterLily.sim_step!(sim)
        step += 1
        if step % 8 == 0 || WaterLily.sim_time(sim) >= 3.0
            pressure = -WaterLily.pressure_force(sim.flow, candidate)
            viscous = -WaterLily.viscous_force(sim.flow, candidate)
            force = pressure + viscous
            all(isfinite, force) || error("nonfinite force: $mode/$case_id")
            csv_row(io, (step, WaterLily.sim_time(sim), force[1], -force[3],
                pressure[1], pressure[3], viscous[1], viscous[3]))
            flush(io)
        end
    end
    println(stderr, mode, "/", case_id, " complete at tU/L=", WaterLily.sim_time(sim))
    return step
end

function solve_modes(outdir, candidate_names)
    plan_sha = verify_plan(outdir)
    allowed = Set((:A_THRESHOLD, :B_CENTER_SIGN, :C_MOMENT_BLEND))
    selected = Symbol.(candidate_names)
    length(selected) <= 2 || error("the frozen Stage-3 cap is two candidates")
    all(in(allowed), selected) || error("Stage 3 accepts preregistered continuous candidates only")
    modes = unique(vcat([:UPSTREAM, :NO_SIGN_CORRECTION], selected))
    records = String[]
    progress_path = joinpath(outdir, "stage3_progress.csv")
    write_exclusive(progress_path, "mode,case_id,steps,t_u_l,force_history_sha256\n")
    progress_io = open(progress_path, "a")
    try
        for case_id in ALL_CASES, mode in modes
            phi, _ = load_phi(outdir, case_id)
            candidate = make_candidate(phi)
            body = DiagnosticBody(candidate + make_ground(), Val(mode))
            sim = make_sim(body)
            io = open_force_file(outdir, mode, case_id)
            steps = 0
            try
                steps = write_force_history(io, sim, candidate, mode, case_id)
            finally
                close(io)
            end
            force_path = joinpath(outdir, "solved", lowercase(String(mode)), case_id * ".csv")
            push!(records, "$(mode)/$(case_id) steps=$steps tU/L=$(WaterLily.sim_time(sim))")
            csv_row(progress_io, (String(mode), case_id, steps, WaterLily.sim_time(sim), sha(read(force_path))))
            flush(progress_io)
            GC.gc()
        end
    finally
        close(progress_io)
    end
    write_exclusive(joinpath(outdir, "stage3_execution.txt"),
        "plan_sha256=$plan_sha\nevidence_class=short_cpu_solved_flow_diagnostic_only\n" *
        "candidate_modes=$(join(string.(selected), ","))\nflow_advance_started=true\n" *
        join(records, "\n") * "\n")
end

if length(ARGS) == 2 && ARGS[1] == "--coefficients"
    coefficient_matrix(abspath(ARGS[2]))
elseif length(ARGS) >= 3 && ARGS[1] == "--solve"
    solve_modes(abspath(ARGS[end]), ARGS[2:end-1])
else
    error("usage: julia -t 4 --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_continuous_replacement_probe.jl --coefficients <evidence-dir> | --solve <candidate-mode> [candidate-mode] <evidence-dir>")
end
