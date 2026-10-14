# GRAD-TA1 (#23): the G2 full-window forward-AD bridge (scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl, frozen by the G2 freeze and not edited)
# with the convective scheme lambda = QuickTie(1f-5) (scripts/quick_tie.jl: values bit for bit `quick`, partials tie-averaged within tau; a surrogate, NOT the
# derivative of the implemented map at ties).  Measurement semantics, window, directions, Dual width 1, Float32 and the sampling are the G2 bridge's:
# flow_24, sim_step!(sim; λ) with default remeasure, one warm-up step that counts as step 1, a force sample every 8 steps (and at the end), candidate-only
# force -(pressure+viscous), drag = Fx, downforce = -Fz, [80,120] tU/L window, phi(alpha) = phi0 + alpha*d with alpha in metres.
#
# Additions to the G2 bridge (docs/grad_ta1_plan_2026_10_15.md, Amendment 1):
#   C6  kernel-first 20-step Dual preflight, `quick` vs `QuickTie`: primal u and p must be bit-equal and the tangents finite, else status INCOMPLETE (exit 2)
#   C5  watchdog (Dual runs): every 100 steps max |tangent| over u and p and its argmax cell, written and flushed to <label>.watchdog.csv together with the last
#       force sample; the force history <label>.history.csv is flushed per sample.  BLOCKED = a non-finite or > 1e30 tangent (onset step and cell recorded, the
#       run stops, the next direction still runs); a Dual run longer than 3x the plain run's total time aborts with an error (-> INCOMPLETE).
#   status / exit code: COMPLETE 0, BLOCKED 3, anything else 2.  The index keeps the G2 name `g2_run_index.json` so scripts/verify_grad_g2_terminal.py applies unchanged.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_ta1_2026_10_15.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha> <D1_raw> <D1_sha> <D2_raw> <D2_sha> <P1_raw> <P1_sha>
# env:   G2_BACKEND (cuda | cpu; cpu is a code-path dry run only), G2_DRYRUN_T_END (cpu only; shortens the window),
#        TA1_PREFLIGHT_ONLY=1 (cpu only; run the preflight and stop), TA1_BLOCK_LIMIT (cpu only; lowers the BLOCKED threshold to test that path)

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
Base.include(WaterLily, joinpath(@__DIR__, "quick_tie.jl"))     # QuickTie lives next to `quick` (it needs WaterLily's quick / median / ForwardDiff)

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)
const SAMPLE_EVERY = 8
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
const BURN_IN = 80.0
const T_END = 120.0
const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")
const TAU = 1f-5                       # absolute, velocity units (U = 1); Float32 literal (plan C4)
const LAMBDA = WaterLily.QuickTie(TAU)
const PREFLIGHT_STEPS = 20
const WATCH_EVERY = 100
const BLOCK_LIMIT = if haskey(ENV, "TA1_BLOCK_LIMIT")   # Float32 headroom 1e30 (plan C5); the override exists only to exercise the BLOCKED path in a CPU dry run
    BACKEND == "cpu" || error("TA1_BLOCK_LIMIT is only allowed with G2_BACKEND=cpu")
    parse(Float64, ENV["TA1_BLOCK_LIMIT"])
else
    1.0e30
end
const WALL_FACTOR = 3.0                # a Dual run longer than WALL_FACTOR x the plain run's total seconds aborts (plan C5)
const WATCH_HEADER = ["step", "t_u_l", "tan_max_u", "tan_argmax_u", "tan_max_p", "tan_argmax_p", "last_sample_step", "fx", "fx_tan", "fz", "fz_tan", "elapsed_s", "vram_bytes"]

# the production window is fixed; only the CPU code-path dry run may shorten it
const WINDOW = if BACKEND == "cpu" && haskey(ENV, "G2_DRYRUN_T_END")
    t_end = parse(Float64, ENV["G2_DRYRUN_T_END"]); (0.4 * t_end, t_end)
else
    haskey(ENV, "G2_DRYRUN_T_END") && error("G2_DRYRUN_T_END is only allowed with G2_BACKEND=cpu")
    (BURN_IN, T_END)
end
const PREFLIGHT_ONLY = get(ENV, "TA1_PREFLIGHT_ONLY", "0") == "1"
PREFLIGHT_ONLY && BACKEND != "cpu" && error("TA1_PREFLIGHT_ONLY is only allowed with G2_BACKEND=cpu")

to_device(a) = BACKEND == "cuda" ? Base.invokelatest(getfield(Main, :CuArray), a) : a
sync() = BACKEND == "cuda" ? Base.invokelatest(CUDA.synchronize) : nothing
used_memory() = BACKEND == "cuda" ? Base.invokelatest(CUDA.used_memory) : 0
reclaim() = (GC.gc(); BACKEND == "cuda" ? Base.invokelatest(CUDA.reclaim) : nothing)

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
        owner = CFDSDFWaterLily.DeviceGridSDF.DeviceGridSDF(grid, "ta1-bridge")
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

# one history row: (step, t, t_tan, then value/tangent for each of SERIES).  Finiteness is judged by the caller (a non-finite tangent is BLOCKED, a non-finite value an error).
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
    return cells
end
value_cells(cells) = (cells[1], cells[2], cells[4:2:end]...)
tangent_cells(cells) = (cells[3], cells[5:2:end]...)

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

# ---- watchdog: max |tangent| of a Dual device array and where (non-finite entries are located on the host) ----------------
function tangent_max(A)
    t = FD.partials.(A, 1)
    m = maximum(abs, t)
    if isfinite(m)
        _, k = findmax(abs.(t))
        return Float64(m), join(k isa CartesianIndex ? Tuple(k) : Tuple(CartesianIndices(A)[k]), ";")
    end
    h = Array(t)
    k = findfirst(!isfinite, h)
    return Float64(h[k]), join(Tuple(CartesianIndices(h)[k]), ";")
end

csv_line(io, cells) = (println(io, join((string(x) for x in cells), ",")); flush(io))   # shortest round-trip representation

function history_header()
    header = ["step", "t_u_l", "t_u_l_tan"]
    for s in SERIES
        push!(header, s); push!(header, s * "_tan")
    end
    return header
end

# One simulation.  Returns (rows, summary, blocked) with blocked = nothing or a Dict (onset); throws on any other failure.
function run_one(label, phi_host::AbstractArray, ::Type{T}, case, λ, outdir; wall_limit=Inf) where {T}
    started = time()
    dual = T <: FD.Dual
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    rows = Vector{Vector{Float64}}()
    hist = open(joinpath(outdir, "$label.history.csv"), "w"); csv_line(hist, history_header())
    watch = dual ? open(joinpath(outdir, "$label.watchdog.csv"), "w") : nothing
    dual && csv_line(watch, WATCH_HEADER)
    blocked = nothing
    last_sample = nothing
    try
        GC.@preserve phi_dev owner sim bodies begin
            warm = time()
            WaterLily.sim_step!(sim; λ)   # registered job: compile step counted as step 1, default remeasure
            sync()
            first_step_seconds = time() - warm
            step = 1
            peak = used_memory()
            loop_started = time()
            while WaterLily.sim_time(sim) < WINDOW[2]
                WaterLily.sim_step!(sim; λ)
                step += 1
                if step % SAMPLE_EVERY == 0 || WaterLily.sim_time(sim) >= WINDOW[2]
                    cells = sample_row(sim, bodies, step)
                    push!(rows, cells); csv_line(hist, cells); last_sample = cells
                    all(isfinite, value_cells(cells)) || error("$label: non-finite primal force/time at step $step")
                    if !all(isfinite, tangent_cells(cells))
                        blocked = Dict{String,Any}("reason" => "non_finite_tangent_in_force_sample", "onset_step" => step, "t_u_l" => cells[2], "tan_max_u" => nothing,
                                                    "tan_argmax_u" => "", "tan_max_p" => nothing, "tan_argmax_p" => "")
                        break
                    end
                end
                step % 50 == 0 && (peak = max(peak, used_memory()))
                if dual && step % WATCH_EVERY == 0
                    mu, au = tangent_max(sim.flow.u); mp, ap = tangent_max(sim.flow.p)
                    ls = last_sample === nothing ? (NaN, NaN, NaN, NaN, NaN) : (last_sample[1], last_sample[4], last_sample[5], last_sample[8], last_sample[9])
                    csv_line(watch, (step, vp(WaterLily.sim_time(sim))[1], mu, au, mp, ap, ls[1], ls[2], ls[3], ls[4], ls[5], time() - started, peak))
                    if !(isfinite(mu) && isfinite(mp)) || max(mu, mp) > BLOCK_LIMIT
                        blocked = Dict{String,Any}("reason" => "tangent_non_finite_or_above_limit", "onset_step" => step, "t_u_l" => vp(WaterLily.sim_time(sim))[1],
                                                    "tan_max_u" => mu, "tan_argmax_u" => au, "tan_max_p" => mp, "tan_argmax_p" => ap, "limit" => BLOCK_LIMIT)
                        break
                    end
                    time() - started > wall_limit && error("$label: wall-time abort ($(round(time() - started; digits=1)) s > $(round(wall_limit; digits=1)) s = $(WALL_FACTOR) x the plain run)")
                end
            end
            sync()
            step_seconds = time() - loop_started
            peak = max(peak, used_memory())
            summary = Dict{String,Any}("label" => label, "real_type" => string(T), "steps" => step, "first_step_seconds_incl_jit" => first_step_seconds,
                                       "loop_seconds" => step_seconds, "peak_vram_bytes" => peak, "lambda" => string(λ), "status" => blocked === nothing ? "COMPLETE" : "BLOCKED")
            if blocked === nothing
                u = Array(sim.flow.u)
                summary["fields_finite_incl_partials"] = all(x -> isfinite(vp(x)[1]) && isfinite(vp(x)[2]), u)
                merge!(summary, summarize(rows))
            else
                summary["blocked"] = blocked
                summary["sample_count"] = length(rows)
            end
            summary["total_seconds"] = time() - started
            return rows, summary, blocked
        end
    finally
        close(hist); watch === nothing || close(watch)
    end
end

# ---- C6: 20-step Dual preflight, quick vs QuickTie ------------------------------------------------------------------------
function preflight(phi32, d32, case, DT)
    out = Dict{String,Any}("steps" => PREFLIGHT_STEPS, "tau" => Float64(TAU), "arms" => Dict{String,Any}())
    state = Dict{String,Any}()
    for (name, λ) in (("quick", WaterLily.quick), ("quick_tie", LAMBDA))
        phi_dev = to_device(DT.(phi32, FD.Partials.(tuple.(d32))))
        sim, bodies, owner = build(phi_dev, DT, case)
        local u, p
        GC.@preserve phi_dev owner sim bodies begin
            for _ in 1:PREFLIGHT_STEPS
                WaterLily.sim_step!(sim; λ)
            end
            sync()
            u = Array(sim.flow.u); p = Array(sim.flow.p)
        end
        tu, tp = FD.partials.(u, 1), FD.partials.(p, 1)
        state[name] = (FD.value.(u), FD.value.(p), tu, tp)
        out["arms"][name] = Dict("primal_finite" => all(isfinite, state[name][1]) && all(isfinite, state[name][2]),
                                 "tangent_u_finite" => all(isfinite, tu), "tangent_p_finite" => all(isfinite, tp),
                                 "max_abs_tangent_u" => maximum(abs, tu), "max_abs_tangent_p" => maximum(abs, tp))
        sim = bodies = owner = phi_dev = nothing; reclaim()
    end
    biteq(a, b) = reinterpret(UInt32, a) == reinterpret(UInt32, b)
    out["primal_u_bit_equal"] = biteq(state["quick"][1], state["quick_tie"][1])
    out["primal_p_bit_equal"] = biteq(state["quick"][2], state["quick_tie"][2])
    du = maximum(abs, state["quick"][3] .- state["quick_tie"][3]); nu = maximum(abs, state["quick"][3])
    out["tangent_u_max_abs_difference_report_only"] = du
    out["tangent_u_relative_difference_report_only"] = du / max(nu, floatmin(Float32))
    out["pass"] = out["primal_u_bit_equal"] && out["primal_p_bit_equal"] &&
                  all(a -> a["primal_finite"] && a["tangent_u_finite"] && a["tangent_p_finite"], values(out["arms"]))
    return out
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
    index = Dict{String,Any}("tier" => "GRAD-TA1", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "window_t_u_l" => collect(WINDOW), "sample_every" => SAMPLE_EVERY,
        "lambda" => "QuickTie", "tau" => Float64(TAU), "dual_width" => 1,
        "run_order" => collect(("plain",) ∪ DIRECTIONS), "runs" => Dict{String,Any}(), "run_status" => Dict{String,Any}(), "status" => "RUNNING",
        "evidence_class" => "gpu_full_window_tie_averaged_forward_ad_surrogate_measurement",
        "claim_limit" => "tie-averaged surrogate derivative of the implemented primal vs FD-08 slopes on flow_24 v17, four directions, Re 80; not the derivative of the implemented map, not a gradient qualification",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    exit_code = 2
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
        dirs = Dict{String,Array{Float32,3}}()
        for (k, name) in enumerate(DIRECTIONS)
            d32 = load_raw(ARGS[2 + 2k], ARGS[3 + 2k])
            maximum(abs, d32) == 1.0f0 || error("$name: direction max-norm != 1")
            for s in (-1.0, 1.0)  # clearance gate on the primal phi +- alpha d for the largest FD-08 amplitude (5 mm)
                zero_level_margin_m(Float64.(phi32) .+ s * 5e-3 .* Float64.(d32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 ||
                    error("$name: clearance gate failed")
            end
            dirs[name] = d32
        end
        tag = FD.Tag(run_one, Float32)
        DT = FD.Dual{typeof(tag),Float32,1}

        # C6: the kernel's first action, before any long run
        pre = preflight(phi32, dirs[DIRECTIONS[1]], case, DT)
        index["preflight"] = pre
        write_json(joinpath(outdir, "preflight.json"), pre)
        if !pre["pass"]
            index["status"] = "INCOMPLETE"; index["error"] = "preflight failed: QuickTie-Dual vs quick-Dual primal not bit-equal, or a non-finite value/tangent"
        elseif PREFLIGHT_ONLY
            index["status"] = "PREFLIGHT_ONLY"; exit_code = 0
        else
            rows, summary, _ = run_one("plain", phi32, Float32, case, WaterLily.quick, outdir)
            write_json(joinpath(outdir, "plain.summary.json"), summary)
            index["runs"]["plain"] = summary["total_seconds"]; index["run_status"]["plain"] = summary["status"]
            wall_limit = WALL_FACTOR * summary["total_seconds"]
            index["wall_limit_s"] = wall_limit
            write_json(joinpath(outdir, "g2_run_index.json"), index)
            blocked_runs = String[]
            for name in DIRECTIONS
                phi_dual = DT.(phi32, FD.Partials.(tuple.(dirs[name])))   # alpha = 0 primal, seed 1, alpha in metres
                rows, summary, blocked = run_one(name, phi_dual, DT, case, LAMBDA, outdir; wall_limit)
                write_json(joinpath(outdir, "$name.summary.json"), summary)
                index["runs"][name] = summary["total_seconds"]; index["run_status"][name] = summary["status"]
                blocked === nothing || (push!(blocked_runs, name); write_json(joinpath(outdir, "$name.blocked.json"), blocked))
                write_json(joinpath(outdir, "g2_run_index.json"), index)
                reclaim()
            end
            index["blocked_runs"] = blocked_runs
            index["status"] = isempty(blocked_runs) ? "COMPLETE" : "BLOCKED"
            exit_code = isempty(blocked_runs) ? 0 : 3
        end
    catch err
        index["status"] = "ERROR"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        exit_code = 2
    end
    write_json(joinpath(outdir, "g2_run_index.json"), index)
    println("TA1_RESULT ", index["status"], " ", outdir)
    exit_code == 0 || exit(exit_code)
end

main()
