# G2: full-window forward-mode AD (Dual width 1, four directions in sequence) on the canonical v17 Candidate C body.
# Measurement semantics are the registered FD-08 job's (scripts/waterlily_xfid_candidate_c_job.jl run_case): flow_24,
# sim_step!(sim) with default remeasure, one warm-up step that counts as step 1, a force sample every 8 steps (and at the
# end), candidate-only force -(pressure+viscous), drag = Fx, downforce = -Fz, [80,120] tU/L window with linearly
# interpolated endpoints and trapezoid time weights.  The tangent is d/dalpha of phi(alpha) = phi0 + alpha*d, alpha in
# metres, so tangents are in solver-force units per metre; the host converts to N/m.
#
# Not a gradient qualification, no error gate is chosen, no flag changes.  Runs: plain Float32 baseline, then D0, D1, D2,
# P1 each as an independent Dual{Tag,Float32,1} simulation.  Any error aborts the remaining runs, writes an error JSON and
# exits non-zero.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha> <D1_raw> <D1_sha> <D2_raw> <D2_sha> <P1_raw> <P1_sha>
# env:   G2_BACKEND (cuda | cpu; cpu is a code-path dry run only), G2_DRYRUN_T_END (cpu only; shortens the window)

using WaterLily
using SHA
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "G2_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("G2_BACKEND must be cuda or cpu")
const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
if BACKEND == "cuda"
    using CUDA
end
include(joinpath(PKG, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
for name in ("V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG, name))
end
if BACKEND == "cuda"
    Base.include(CFDSDFWaterLily, joinpath(PKG, "DeviceGridSDF.jl"))
    CUDA.allowscalar(false)
end
using .CFDSDFWaterLily: V16MovingGroundBody, v16_native_far_field_uBC, NormalFloorWaterLilyBody, CandidateCWaterLilyBody
using .CFDSDFWaterLily.V16W4Sensitivity

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)
const SAMPLE_EVERY = 8
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
const BURN_IN = 80.0
const T_END = 120.0
const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")

# the production window is fixed; only the CPU code-path dry run may shorten it
const WINDOW = if BACKEND == "cpu" && haskey(ENV, "G2_DRYRUN_T_END")
    t_end = parse(Float64, ENV["G2_DRYRUN_T_END"]); (0.4 * t_end, t_end)
else
    haskey(ENV, "G2_DRYRUN_T_END") && error("G2_DRYRUN_T_END is only allowed with G2_BACKEND=cpu")
    (BURN_IN, T_END)
end

to_device(a) = BACKEND == "cuda" ? Base.invokelatest(getfield(Main, :CuArray), a) : a
sync() = BACKEND == "cuda" ? Base.invokelatest(CUDA.synchronize) : nothing
used_memory() = BACKEND == "cuda" ? Base.invokelatest(CUDA.used_memory) : 0

real_type(::Type{T}) where {T<:Real} = T
real_type(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V

function load_raw(path, sha)
    raw = read(path)
    bytes2hex(sha256(raw)) == sha || error("SHA mismatch: $path")
    length(raw) == prod(SHAPE) * 4 || error("byte length mismatch: $path")
    return reshape(copy(reinterpret(Float32, raw)), SHAPE)
end

function build(phi_dev::AbstractArray{S,3}, ::Type{T}, case) where {S,T}
    FS = real_type(T)
    grid = GridSDF(phi_dev, FS.(ORIGIN), FS.((SPACING, SPACING, SPACING)), SHAPE, FS(3), FS(0.15))
    if BACKEND == "cuda"
        owner = CFDSDFWaterLily.DeviceGridSDF.DeviceGridSDF(grid, "g2-bridge")
        kgrid = CFDSDFWaterLily.DeviceGridSDF.kernel_grid(owner)
    else
        owner, kgrid = nothing, grid
    end
    floor_body = NormalFloorWaterLilyBody(kgrid, FS.(case.flow_origin_m), FS(case.flow_spacing_m), FS(0.25))
    candidate = CandidateCWaterLilyBody(floor_body; normal_floor=FS(0.25), transition_width=FS(TRANSITION))
    ground = V16MovingGroundBody(FS(0), FS(1))
    combined = CandidateCWaterLilyBody(floor_body, ground; normal_floor=FS(0.25), transition_width=FS(TRANSITION))
    BACKEND == "cuda" && !isbitstype(typeof(combined)) && error("Candidate C body is not isbits")
    mem = BACKEND == "cuda" ? getfield(Main, :CuArray) : Array
    sim = WaterLily.Simulation(case.flow_dims, v16_native_far_field_uBC, FS(case.solver_length);
        U=FS(case.solver_velocity), ν=FS(case.solver_viscosity), exitBC=true, body=combined, T=T, mem=mem)
    return sim, (candidate=candidate, ground=ground, combined=combined), owner
end

vp(x::FD.Dual) = (Float64(FD.value(x)), Float64(FD.partials(x, 1)))
vp(x::Real) = (Float64(x), 0.0)

# one history row: (step, t, t_tan, then value/tangent for each of SERIES)
function sample_row(sim, bodies, step)
    pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))
    viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
    total = pressure + viscous
    t, t_tan = vp(WaterLily.sim_time(sim))
    quantities = (total[1], total[2], total[3], pressure[1], pressure[2], pressure[3], viscous[1], viscous[2], viscous[3])
    cells = Float64[Float64(step), t, t_tan]
    for q in quantities
        v, p = vp(q)
        push!(cells, v); push!(cells, p)
    end
    all(isfinite, cells) || error("non-finite force/tangent at step $step (t=$t)")
    return cells
end

# ---- window mean with an optionally propagated time tangent (Dual64 arithmetic, tag-free) -----------------------------
D(v, p) = FD.Dual{Nothing,Float64,1}(v, FD.Partials((p,)))
row_time(r, time_tangent) = D(r[2], time_tangent ? r[3] : 0.0)
row_value(r, series_index) = D(r[4 + 2(series_index - 1)], r[5 + 2(series_index - 1)])

function window_mean(rows, series_index, start_t, end_t; time_tangent=true)
    lastle(t) = findlast(r -> r[2] <= t, rows)
    firstge(t) = findfirst(r -> r[2] >= t, rows)
    (lastle(start_t) !== nothing && firstge(start_t) !== nothing && lastle(end_t) !== nothing && firstge(end_t) !== nothing) ||
        error("history does not bracket the window")
    function at(t)
        l, r = rows[lastle(t)], rows[firstge(t)]
        l[2] == r[2] && return (row_time(l, time_tangent), row_value(l, series_index))
        tl, tr = row_time(l, time_tangent), row_time(r, time_tangent)
        alpha = (D(t, 0.0) - tl) / (tr - tl)
        fl, fr = row_value(l, series_index), row_value(r, series_index)
        return (D(t, 0.0), fl + alpha * (fr - fl))
    end
    points = [at(start_t)]
    for r in rows
        start_t < r[2] < end_t && push!(points, (row_time(r, time_tangent), row_value(r, series_index)))
    end
    push!(points, at(end_t))
    num = D(0.0, 0.0); den = D(0.0, 0.0)
    for i in 1:(length(points) - 1)
        dt = points[i + 1][1] - points[i][1]
        num += 0.5 * (points[i][2] + points[i + 1][2]) * dt
        den += dt
    end
    m = num / den
    return (FD.value(m), FD.partials(m, 1))
end

function summarize(rows)
    out = Dict{String,Any}("sample_count" => length(rows), "t_first" => rows[1][2], "t_last" => rows[end][2])
    for (name, idx) in (("fx", 1), ("fz", 3))
        for (tag, tt) in (("dual_time", true), ("frozen_time", false))
            v, p = window_mean(rows, idx, WINDOW[1], WINDOW[2]; time_tangent=tt)
            out["window_mean_$(name)_$(tag)"] = Dict("value" => v, "tangent" => p)
        end
    end
    return out
end

function run_one(label, phi_host::AbstractArray, ::Type{T}, case) where {T}
    started = time()
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    rows = Vector{Vector{Float64}}()
    step_seconds = 0.0
    GC.@preserve phi_dev owner sim bodies begin
        warm = time()
        WaterLily.sim_step!(sim)   # registered job: compile step counted as step 1, default remeasure
        sync()
        first_step_seconds = time() - warm
        step = 1
        peak = used_memory()
        loop_started = time()
        while WaterLily.sim_time(sim) < WINDOW[2]
            WaterLily.sim_step!(sim)
            step += 1
            if step % SAMPLE_EVERY == 0 || WaterLily.sim_time(sim) >= WINDOW[2]
                push!(rows, sample_row(sim, bodies, step))
            end
            step % 50 == 0 && (peak = max(peak, used_memory()))
        end
        sync()
        step_seconds = time() - loop_started
        peak = max(peak, used_memory())
        u = Array(sim.flow.u)
        fields_finite = all(x -> isfinite(vp(x)[1]) && isfinite(vp(x)[2]), u)
        summary = summarize(rows)
        summary["label"] = label
        summary["real_type"] = string(T)
        summary["steps"] = step
        summary["first_step_seconds_incl_jit"] = first_step_seconds
        summary["loop_seconds"] = step_seconds
        summary["total_seconds"] = time() - started
        summary["peak_vram_bytes"] = peak
        summary["fields_finite_incl_partials"] = fields_finite
        return rows, summary
    end
end

function write_history(path, rows)
    header = ["step", "t_u_l", "t_u_l_tan"]
    for s in SERIES
        push!(header, s); push!(header, s * "_tan")
    end
    open(path, "w") do io
        println(io, join(header, ","))
        for r in rows
            println(io, join((string(x) for x in r), ","))   # shortest round-trip representation
        end
    end
end

json(x::Nothing) = "null"
json(x::Bool) = x ? "true" : "false"
json(x::Integer) = string(x)
json(x::AbstractFloat) = isfinite(x) ? string(x) : "null"
json(x::AbstractString) = "\"" * replace(x, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n") * "\""
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::Tuple) = json(collect(x))
json(x::AbstractDict) = "{" * join([json(string(k)) * ":" * json(x[k]) for k in sort(collect(keys(x)); by=string)], ",") * "}"
write_json(path, value) = open(io -> write(io, json(value), "\n"), path, "w")

function main()
    length(ARGS) == 11 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha> <D1_raw> <D1_sha> <D2_raw> <D2_sha> <P1_raw> <P1_sha>")
    phi_path, phi_sha, outdir = ARGS[1], ARGS[2], ARGS[3]
    mkpath(outdir)
    isfile(joinpath(outdir, "g2_run_index.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "window_t_u_l" => collect(WINDOW), "sample_every" => SAMPLE_EVERY,
        "run_order" => collect(("plain",) ∪ DIRECTIONS), "runs" => Dict{String,Any}(), "status" => "RUNNING",
        "evidence_class" => "gpu_full_window_forward_ad_bridge_measurement_unregistered",
        "claim_limit" => "point derivative of the exact discrete full-window objective; not a gradient qualification; no error gate chosen",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    try
        if BACKEND == "cuda"
            index["gpu_name"] = Base.invokelatest(() -> CUDA.name(CUDA.device()))
            index["cuda_jl"] = string(pkgversion(CUDA))
            Base.invokelatest(CUDA.functional) || error("CUDA is not functional")
        end
        phi32 = load_raw(phi_path, phi_sha)
        zero_level_margin_m(Float64.(phi32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 || error("baseline clearance gate failed")
        case = only(c for c in w4_cases(ORIGIN, SPACING) if c.case_id == "flow_24")
        validate_w4_case(case; canonical_design_origin_m=ORIGIN, canonical_design_spacing_m=SPACING)
        rows, summary = run_one("plain", phi32, Float32, case)
        write_history(joinpath(outdir, "plain.history.csv"), rows); write_json(joinpath(outdir, "plain.summary.json"), summary)
        index["runs"]["plain"] = summary["total_seconds"]
        for (k, name) in enumerate(DIRECTIONS)
            d32 = load_raw(ARGS[2 + 2k], ARGS[3 + 2k])
            maximum(abs, d32) == 1.0f0 || error("$name: direction max-norm != 1")
            for s in (-1.0, 1.0)  # clearance gate on the primal phi +- alpha d for the largest FD-08 amplitude (5 mm)
                zero_level_margin_m(Float64.(phi32) .+ s * 5e-3 .* Float64.(d32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 ||
                    error("$name: clearance gate failed")
            end
            tag = FD.Tag(run_one, Float32)
            DT = FD.Dual{typeof(tag),Float32,1}
            phi_dual = DT.(phi32, FD.Partials.(tuple.(d32)))   # alpha = 0 primal, seed 1, alpha in metres
            rows, summary = run_one(name, phi_dual, DT, case)
            write_history(joinpath(outdir, "$name.history.csv"), rows); write_json(joinpath(outdir, "$name.summary.json"), summary)
            index["runs"][name] = summary["total_seconds"]
            write_json(joinpath(outdir, "g2_run_index.json"), index)
        end
        index["status"] = "COMPLETE"
    catch err
        index["status"] = "ERROR"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
    end
    write_json(joinpath(outdir, "g2_run_index.json"), index)
    println("G2_RESULT ", index["status"], " ", outdir)
    index["status"] == "COMPLETE" || exit(2)
end

main()
