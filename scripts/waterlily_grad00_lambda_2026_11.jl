# GRAD-00: a copy of frozen GRAD-TA1 with a constructor-routed convection scheme and same-scheme FD primals.
# Frozen measurement semantics: v17/flow_24, default remeasure, warm-up counts as step 1, force every 8 steps,
# candidate force -(pressure+viscous), Fx drag/-Fz downforce, endpoint-clipped time-weighted [80,120], Dual width 1.
# Watchdog every 100 steps; BLOCKED at non-finite or >1e30 tangent; only BLOCKED continues, errors abort the job;
# Dual wall abort remains 8x selected-lambda plain time. Additional terminal tangent maxima are report-only.
# One shared plain + four (Dual,+epsilon,-epsilon) groups = 13 CUDA runs, matching GRAD-00 spec section 4.
# CPU E/F and Float32 controls use D0/D1 (7 runs), per spec Amendment 2; all raw source inputs remain canonical Float32.
# Precision F: GRAD00_T=Float64 is CPU quick/quick_nobound only. Preflight argmax locations are report-only.
# CLI: TA1's 11 arguments followed by D0,D1,D2,P1 epsilon_m (required, no plateau values inferred).
# env: GRAD00_ARM=quick|quick_nobound|cds|vanLeer|vanLeer_safe, GRAD00_T=Float32|Float64, G2_BACKEND=cpu|cuda.
# Existing CPU-only G2_DRYRUN_T_END, TA1_PREFLIGHT_ONLY and TA1_BLOCK_LIMIT hooks are unchanged.
# g2_run_index.json retains its name; frozen five-run terminal verifier is not directly compatible with these 13 runs.

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
Base.include(WaterLily, joinpath(@__DIR__, "quick_nobound.jl"))
Base.include(WaterLily, joinpath(@__DIR__, "vanleer_safe.jl"))

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)
const SAMPLE_EVERY = 8
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
const BURN_IN = 80.0
const T_END = 120.0
const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")
const ARM = get(ENV, "GRAD00_ARM", "")
ARM in ("quick", "quick_nobound", "cds", "vanLeer", "vanLeer_safe") || error("GRAD00_ARM must be quick, quick_nobound, cds, vanLeer or vanLeer_safe")
const REAL_TYPE_NAME = get(ENV, "GRAD00_T", "Float32")
REAL_TYPE_NAME in ("Float32", "Float64") || error("GRAD00_T must be Float32 or Float64")
const RT = REAL_TYPE_NAME == "Float32" ? Float32 : Float64
RT === Float64 && (BACKEND != "cpu" || !(ARM in ("quick", "quick_nobound"))) &&
    error("the Float64 precision arm is CPU-only and restricted to quick/quick_nobound")
const ACTIVE_DIRECTIONS = BACKEND == "cpu" ? DIRECTIONS[1:2] : DIRECTIONS
const LAMBDA = getfield(WaterLily, Symbol(ARM))
const PREFLIGHT_STEPS = 20
const WATCH_EVERY = 100
const BLOCK_LIMIT = if haskey(ENV, "TA1_BLOCK_LIMIT")   # Float32 headroom 1e30 (plan C5); the override exists only to exercise the BLOCKED path in a CPU dry run
    BACKEND == "cpu" || error("TA1_BLOCK_LIMIT is only allowed with G2_BACKEND=cpu")
    parse(Float64, ENV["TA1_BLOCK_LIMIT"])
else
    1.0e30
end
const WALL_FACTOR = 8.0                # a Dual run longer than WALL_FACTOR x the plain run's total seconds aborts the whole kernel (plan C5, Amendment 2)
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

function build(phi_dev::AbstractArray{S,3}, ::Type{T}, case, λ) where {S,T}
    FS = real_type(T)
    grid = GridSDF(phi_dev, FS.(ORIGIN), FS.((SPACING, SPACING, SPACING)), SHAPE, FS(3), FS(0.15))
    if BACKEND == "cuda"
        owner = CFDSDFWaterLily.DeviceGridSDF.DeviceGridSDF(grid, "grad00-bridge")
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
        U=FS(case.solver_velocity), ν=FS(case.solver_viscosity), exitBC=true, body=combined, T=T, mem=mem, λ=λ)   # λ ONLY works here (sim_step!(sim; λ) ignores it)
    typeof(sim.flow.λ) === typeof(λ) || error("convective scheme not routed: sim.flow.λ is $(typeof(sim.flow.λ)), requested $(typeof(λ))")
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
    sim, bodies, owner = build(phi_dev, T, case, λ)
    lambda_type = string(typeof(sim.flow.λ))
    rows = Vector{Vector{Float64}}()
    hist = open(joinpath(outdir, "$label.history.csv"), "w"); csv_line(hist, history_header())
    watch = dual ? open(joinpath(outdir, "$label.watchdog.csv"), "w") : nothing
    dual && csv_line(watch, WATCH_HEADER)
    blocked = nothing
    max_tangent_u_finite = 0.0; max_tangent_p_finite = 0.0
    last_sample = nothing
    try
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
                    cells = sample_row(sim, bodies, step)
                    push!(rows, cells); csv_line(hist, cells); last_sample = cells
                    all(isfinite, value_cells(cells)) || error("$label: non-finite primal force/time at step $step")
                    if !all(isfinite, tangent_cells(cells))
                        mu, au = tangent_max(sim.flow.u); mp, ap = tangent_max(sim.flow.p)   # the field state at the detection point (the cell may be elsewhere than the force's source)
                        isfinite(mu) && (max_tangent_u_finite = max(max_tangent_u_finite, abs(mu)))
                        isfinite(mp) && (max_tangent_p_finite = max(max_tangent_p_finite, abs(mp)))
                        blocked = Dict{String,Any}("reason" => "non_finite_tangent_in_force_sample", "onset_step" => step, "t_u_l" => cells[2],
                                                    "tan_max_u" => mu, "tan_argmax_u" => au, "tan_max_p" => mp, "tan_argmax_p" => ap)
                        break
                    end
                end
                step % 50 == 0 && (peak = max(peak, used_memory()))
                if dual && step % WATCH_EVERY == 0
                    mu, au = tangent_max(sim.flow.u); mp, ap = tangent_max(sim.flow.p)
                    isfinite(mu) && (max_tangent_u_finite = max(max_tangent_u_finite, abs(mu)))
                    isfinite(mp) && (max_tangent_p_finite = max(max_tangent_p_finite, abs(mp)))
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
                                       "loop_seconds" => step_seconds, "peak_vram_bytes" => peak, "lambda_type" => lambda_type, "status" => blocked === nothing ? "COMPLETE" : "BLOCKED")
            if blocked === nothing
                u = Array(sim.flow.u)
                summary["fields_finite_incl_partials"] = all(x -> isfinite(vp(x)[1]) && isfinite(vp(x)[2]), u)
                merge!(summary, summarize(rows))
            else
                summary["blocked"] = blocked
                summary["sample_count"] = length(rows)
            end
            if dual
                # Report the terminal state as well; scheduled watchdog/gates above are unchanged from TA1.
                mu, au = tangent_max(sim.flow.u); mp, ap = tangent_max(sim.flow.p)
                isfinite(mu) && (max_tangent_u_finite = max(max_tangent_u_finite, abs(mu)))
                isfinite(mp) && (max_tangent_p_finite = max(max_tangent_p_finite, abs(mp)))
                summary["watchdog_max_abs_tangent_u_finite"] = max_tangent_u_finite
                summary["watchdog_max_abs_tangent_p_finite"] = max_tangent_p_finite
                summary["terminal_tangent"] = Dict("tan_max_u" => mu, "tan_argmax_u" => au, "tan_max_p" => mp, "tan_argmax_p" => ap)
                summary["watchdog_onset"] = blocked
            end
            summary["total_seconds"] = time() - started
            return rows, summary, blocked
        end
    finally
        close(hist); watch === nothing || close(watch)
    end
end

# ---- 20-step preflight: selected plain/Dual finite, A quick control and D' stock-vanLeer plain control -----------------
array_sha(a) = bytes2hex(sha256(reinterpret(UInt8, vec(a))))

# Host-only description of the 20-step state. This does not change the frozen watchdog or its gates.
function preflight_tangent_location(tangents, case, grid)
    k = findfirst(!isfinite, tangents)
    finite = k === nothing
    finite && ((_, k) = findmax(abs.(tangents)))
    indices = Tuple(k)
    component = ndims(tangents) == 4 ? indices[4] : 0
    x = WaterLily.loc(component, CartesianIndex(indices[1:3]), RT)
    world = ntuple(d -> RT(case.flow_origin_m[d]) + RT(case.flow_spacing_m) * x[d], 3)
    candidate = Float64(CFDSDFWaterLily.GridSDFBody.sdf_at_world(grid, world))
    ground = Float64(RT(case.flow_spacing_m) * x[3])  # V16MovingGroundBody has z_plane=0.
    outside_design = any(d -> world[d] < grid.origin[d] || world[d] > grid.origin[d] + (grid.shape[d] - 1) * grid.h[d], 1:3)
    value = Float64(tangents[k])
    return Dict{String,Any}("selection" => finite ? "max_abs_tangent" : "first_non_finite",
        "index" => collect(indices), "value" => value, "abs_value" => abs(value), "finite" => finite,
        "solver_position" => collect(x), "world_position_m" => collect(world),
        "candidate_sdf_m" => candidate, "candidate_sdf_is_fluid_extension" => outside_design,
        "ground_distance_m" => ground, "combined_sdf_m" => min(candidate, ground),
        "inside_solid" => min(candidate, ground) < 0,
        "halo_cell" => any(d -> indices[d] == 1 || indices[d] == case.flow_dims[d] + 2, 1:3),
        "domain_boundary_clearance_m" => [Float64(min(x[d], case.flow_dims[d] - x[d]) * RT(case.flow_spacing_m)) for d in 1:3])
end

function preflight(phi32, d32, case, DT, outdir)
    out = Dict{String,Any}("steps" => PREFLIGHT_STEPS, "arm" => ARM, "arms" => Dict{String,Any}(),
        "localization_note" => "report only; 1-based array index (u includes component), WaterLily.loc staggered coordinates and canonical primal GridSDF; outside design box candidate SDF is the registered positive fluid extension, not a geometric distance")
    grid = GridSDF(RT.(phi32), RT.(ORIGIN), RT.((SPACING, SPACING, SPACING)), SHAPE, RT(3), RT(0.15))
    arms = (("selected_dual", LAMBDA, DT), ("selected_plain", LAMBDA, RT))
    ARM == "quick" && (arms = (("quick", WaterLily.quick, DT), arms...))
    ARM == "vanLeer_safe" && (arms = (arms..., ("vanLeer_plain", WaterLily.vanLeer, RT)))
    for (name, λ, T) in arms
        started = time()
        println("GRAD00_PREFLIGHT_BEGIN ", name, " lambda=", typeof(λ), " steps=", PREFLIGHT_STEPS); flush(stdout)
        phi = T <: FD.Dual ? DT.(RT.(phi32), FD.Partials.(tuple.(RT.(d32)))) : RT.(phi32)
        phi_dev = to_device(phi)
        sim, bodies, owner = build(phi_dev, T, case, λ)
        lambda_type = string(typeof(sim.flow.λ))
        local u, p
        GC.@preserve phi_dev owner sim bodies begin
            for _ in 1:PREFLIGHT_STEPS
                WaterLily.sim_step!(sim)
            end
            sync()
            u = Array(sim.flow.u); p = Array(sim.flow.p)
        end
        vu, vp_ = FD.value.(u), FD.value.(p)
        tu, tp = last.(vp.(u)), last.(vp.(p))
        out["arms"][name] = Dict("lambda_type" => lambda_type,
            "primal_finite" => all(isfinite, vu) && all(isfinite, vp_),
            "tangent_u_finite" => all(isfinite, tu), "tangent_p_finite" => all(isfinite, tp),
            "max_abs_tangent_u" => maximum(abs, tu), "max_abs_tangent_p" => maximum(abs, tp),
            "tangent_argmax_u" => preflight_tangent_location(tu, case, grid),
            "tangent_argmax_p" => preflight_tangent_location(tp, case, grid),
            "primal_u_sha256" => array_sha(vu), "primal_p_sha256" => array_sha(vp_), "total_seconds" => time() - started)
        println("GRAD00_PREFLIGHT_END ", name, " seconds=", out["arms"][name]["total_seconds"]); flush(stdout)
        write_json(joinpath(outdir, "preflight.progress.json"), out)  # partial readouts survive an external timeout; this has no pass label
        sim = bodies = owner = phi_dev = nothing; reclaim()
    end
    selected = out["arms"]["selected_dual"]
    out["determinism_primal_u_bit_equal"] = ARM == "quick" ? out["arms"]["quick"]["primal_u_sha256"] == selected["primal_u_sha256"] : nothing
    out["determinism_primal_p_bit_equal"] = ARM == "quick" ? out["arms"]["quick"]["primal_p_sha256"] == selected["primal_p_sha256"] : nothing
    out["determinism_control_note"] = ARM == "quick" ?
        "same-build repeated quick-Dual path: determinism only; the separate CPU ta1_bit_comparison.json checks the frozen TA1 cross-script hashes" :
        "not applicable to this arm; preflight checks the selected plain and Dual paths"
    plain = out["arms"]["selected_plain"]
    out["vanLeer_primal_u_bit_equal"] = ARM == "vanLeer_safe" ? out["arms"]["vanLeer_plain"]["primal_u_sha256"] == plain["primal_u_sha256"] : nothing
    out["vanLeer_primal_p_bit_equal"] = ARM == "vanLeer_safe" ? out["arms"]["vanLeer_plain"]["primal_p_sha256"] == plain["primal_p_sha256"] : nothing
    out["pass"] = (ARM != "quick" || (out["determinism_primal_u_bit_equal"] && out["determinism_primal_p_bit_equal"])) &&
                  (ARM != "vanLeer_safe" || (out["vanLeer_primal_u_bit_equal"] && out["vanLeer_primal_p_bit_equal"])) &&
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

function write_indices(outdir, index, records)
    write_json(joinpath(outdir, "g2_run_index.json"), index)
    grad = copy(index)
    grad["runs"] = records
    write_json(joinpath(outdir, "grad00_index.json"), grad)
end

function save_run!(index, records, label, phi, T, case, outdir; wall_limit=Inf)
    index["active_run"] = label
    write_indices(outdir, index, records)
    _, summary, blocked = run_one(label, phi, T, case, LAMBDA, outdir; wall_limit)
    summary["input_phi_sha256"] = array_sha(FD.value.(phi))
    summary["input_phi_storage_type"] = REAL_TYPE_NAME
    T <: FD.Dual && (summary["input_tangent_sha256"] = array_sha(FD.partials.(phi, 1)))
    summary_path = "$label.summary.json"
    write_json(joinpath(outdir, summary_path), summary)
    record = copy(summary)
    for (kind, path) in (("summary", summary_path), ("history", "$label.history.csv"))
        record[kind * "_path"] = path
        record[kind * "_sha256"] = bytes2hex(sha256(read(joinpath(outdir, path))))
    end
    if T <: FD.Dual
        path = "$label.watchdog.csv"
        record["watchdog_path"] = path
        record["watchdog_sha256"] = bytes2hex(sha256(read(joinpath(outdir, path))))
    end
    if blocked !== nothing
        path = "$label.blocked.json"
        write_json(joinpath(outdir, path), blocked)
        record["blocked_path"] = path
        record["blocked_sha256"] = bytes2hex(sha256(read(joinpath(outdir, path))))
    end
    records[label] = record
    index["runs"][label] = summary["total_seconds"]
    index["run_status"][label] = summary["status"]
    index["lambda_types"][label] = summary["lambda_type"]
    write_indices(outdir, index, records)
    reclaim()
    return summary, blocked
end

function main()
    length(ARGS) == 15 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha> <D1_raw> <D1_sha> <D2_raw> <D2_sha> <P1_raw> <P1_sha> <D0_epsilon_m> <D1_epsilon_m> <D2_epsilon_m> <P1_epsilon_m>")
    phi_path, phi_sha, outdir = ARGS[1], ARGS[2], ARGS[3]
    mkpath(outdir)
    for path in ("g2_run_index.json", "grad00_index.json", "preflight.json", "preflight.progress.json")
        isfile(joinpath(outdir, path)) && error("refusing to overwrite $outdir/$path")
    end
    run_order = ["plain"]
    by_direction = Dict{String,Any}()
    for name in ACTIVE_DIRECTIONS
        append!(run_order, [name, name * "__plus", name * "__minus"])
        by_direction[name] = Dict{String,Any}("plain" => "plain", "dual" => name, "plus" => name * "__plus", "minus" => name * "__minus")
    end
    for label in run_order, suffix in (".history.csv", ".watchdog.csv", ".summary.json", ".blocked.json")
        isfile(joinpath(outdir, label * suffix)) && error("refusing to overwrite $outdir/$label$suffix")
    end
    index = Dict{String,Any}("schema_version" => 1, "tier" => "GRAD-00", "arm" => ARM, "real_type" => REAL_TYPE_NAME,
        "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "window_t_u_l" => collect(WINDOW), "sample_every" => SAMPLE_EVERY,
        "lambda_type" => string(typeof(LAMBDA)), "lambda_types" => Dict{String,Any}(), "dual_width" => 1,
        "block_limit" => BLOCK_LIMIT, "wall_factor" => WALL_FACTOR, "watch_every" => WATCH_EVERY,
        "directions" => collect(ACTIVE_DIRECTIONS), "by_direction" => by_direction,
        "input_sha256" => Dict("phi" => phi_sha, "directions" => Dict(name => ARGS[3 + 2k] for (k, name) in enumerate(DIRECTIONS))),
        "epsilon_m" => Dict{String,Any}(), "run_order" => run_order,
        "runs" => Dict{String,Any}(), "run_status" => Dict{String,Any}(), "status" => "RUNNING",
        "evidence_class" => BACKEND == "cpu" && (PREFLIGHT_ONLY || haskey(ENV, "G2_DRYRUN_T_END")) ? "cpu_code_path_dryrun" : "exploratory_lambda_swap_forward_ad_measurement",
        "claim_limit" => "flow_24 v17 Re80 lambda/precision/version comparison; CPU dry runs do not measure the registered window; no gradient qualification",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    records = Dict{String,Any}()
    exit_code = 2
    try
        for (k, name) in enumerate(DIRECTIONS)
            epsilon = parse(Float64, ARGS[11 + k])
            isfinite(epsilon) && 0 < epsilon <= 5e-3 || error("$name: epsilon_m must be finite, positive and <= 5e-3 m (FD-08 maximum clearance amplitude)")
            index["epsilon_m"][name] = epsilon
            haskey(by_direction, name) && (by_direction[name]["epsilon_m"] = epsilon)
        end
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
            for s in (-1.0, 1.0)  # unchanged clearance gate at the largest FD-08 amplitude (5 mm)
                zero_level_margin_m(Float64.(phi32) .+ s * 5e-3 .* Float64.(d32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 ||
                    error("$name: clearance gate failed")
            end
            dirs[name] = d32
        end
        tag = FD.Tag(run_one, RT)
        DT = FD.Dual{typeof(tag),RT,1}

        write_indices(outdir, index, records)
        pre = preflight(phi32, dirs[DIRECTIONS[1]], case, DT, outdir)
        index["preflight"] = pre
        write_json(joinpath(outdir, "preflight.json"), pre)
        if !pre["pass"]
            index["status"] = "INCOMPLETE"
            index["error"] = "preflight failed: non-finite selected primal/tangent or control primal bit mismatch"
        elseif PREFLIGHT_ONLY
            index["status"] = "PREFLIGHT_ONLY"; exit_code = 0
        else
            phi = RT.(phi32)
            summary, _ = save_run!(index, records, "plain", phi, RT, case, outdir)
            wall_limit = WALL_FACTOR * summary["total_seconds"]
            index["wall_limit_s"] = wall_limit
            blocked_runs = String[]
            for name in ACTIVE_DIRECTIONS
                phi_dual = DT.(phi, FD.Partials.(tuple.(RT.(dirs[name]))))
                _, blocked = save_run!(index, records, name, phi_dual, DT, case, outdir; wall_limit)
                blocked === nothing || push!(blocked_runs, name)
                # FD-08 casts only AFTER phi0 +/- epsilon*d in Float64. F keeps that Float64 field.
                for (suffix, sign) in (("__plus", 1.0), ("__minus", -1.0))
                    perturbed = RT.(Float64.(phi32) .+ sign * index["epsilon_m"][name] .* Float64.(dirs[name]))
                    array_sha(perturbed) != array_sha(phi) || error("$name$suffix: epsilon does not change the stored field")
                    save_run!(index, records, name * suffix, perturbed, RT, case, outdir)
                end
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
    write_indices(outdir, index, records)
    println("GRAD00_RESULT ", index["status"], " ", outdir)
    exit_code == 0 || exit(exit_code)
end

abspath(PROGRAM_FILE) == (@__FILE__) && main()
