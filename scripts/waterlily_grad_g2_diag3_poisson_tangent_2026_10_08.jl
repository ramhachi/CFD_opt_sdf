# G2-DIAG3: does a tangent-only continuation of the Poisson solve (primal bytes untouched) remove the far-field corner tangent mode of the D0
# Dual{Float32,1} run?  Fork replay from step 780 (as G2-DIAG2), then, only if a candidate is mechanically selected, a held-out D0 long horizon.
#
# Arms (all D0, same scientific state as G2 / DIAG1 / DIAG2; WaterLily defaults for the primal Poisson stop rule):
#   A0   baseline                                  (hook = nothing)
#   A1   tangent-only continuation  (primary)      primal solve unchanged, then A e = dr solved value-only and added to the tangent of x
#        thresholds tau in {1e-4,1e-5,1e-6,1e-7}  (stop on max|dr| <= tau * max|dz|, at most 64 cycles)  and fixed counts 1..64
#   D    Dual stop rule (secondary; changes the primal)  continue the ordinary Dual iteration until primal AND tangent residual are small
#   F32  forced 32 Dual iterations (the DIAG2 V1c arm; quantifies how much the primal moved)
# The primal identity of every A1 arm is checked against a plain replay with VALUE-ONLY checksums at every step.
# No Float64, no D1/D2/P1, no bridge, no delta.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_g2_diag3_poisson_tangent_2026_10_08.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>
# env (cpu code-path dry run only): DIAG3_BACKEND=cpu, DIAG3_FORK_STEP, DIAG3_STEPS, DIAG3_ONLY=<arm,arm,..>, DIAG3_STAGE_B_STEPS=<n>,
#   DIAG3_FORCE_SELECT=<arm>, DIAG3_RAISE_ARM=<arm>

using WaterLily
using SHA
const SVector = WaterLily.SVector
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "DIAG3_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("DIAG3_BACKEND must be cuda or cpu")
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
Base.include(WaterLily, joinpath(@__DIR__, "waterlily_grad_g2_diag1_stages.jl"))
Base.include(WaterLily, joinpath(@__DIR__, "waterlily_grad_g2_diag3_stages.jl"))

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)
const SAMPLE_EVERY = 8
const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")
const WINDOW = (80.0, 120.0)

# ---- configuration (fixed in the pre-run freeze) ---------------------------------------------------------------------------
const DRYRUN = BACKEND == "cpu"
(!DRYRUN && any(haskey(ENV, k) for k in ("DIAG3_FORK_STEP", "DIAG3_STEPS", "DIAG3_ONLY", "DIAG3_STAGE_B_STEPS", "DIAG3_FORCE_SELECT", "DIAG3_RAISE_ARM"))) &&
    error("DIAG3 dry-run switches are only allowed with DIAG3_BACKEND=cpu")
const FORK_STEP = DRYRUN && haskey(ENV, "DIAG3_FORK_STEP") ? parse(Int, ENV["DIAG3_FORK_STEP"]) : 780
const N_STEPS = DRYRUN && haskey(ENV, "DIAG3_STEPS") ? parse(Int, ENV["DIAG3_STEPS"]) : 200
const END_STEP = FORK_STEP + N_STEPS
const SLOPE_FROM = FORK_STEP + N_STEPS ÷ 2
const BASELINE_MIN_SLOPE = 0.05          # decade/step; below this the baseline did not reproduce the mode
const SUPPRESS_SLOPE = 0.005             # diagnostic gate (not a gradient qualification threshold)
const FLOOR_FACTOR = 2.0                 # endpoint global max <= 2 x the near-body floor (global max |tangent u| of the straight replay at the fork step)
const REDUCE_FACTOR = 0.5
const MAX_TANGENT_CYCLES = 64
const PLATEAU_RUN = 3
const LONG_BOX_MAX = 1e3                 # Stage B gates: corner-box max |tangent u| and global max |tangent u| at every step
const LONG_GLOBAL_MAX = 1e6
const MAX_LONG_STEPS = 20000             # hard cap of the Stage B loop (the registered horizon needs ~8,740 steps)
const DRIFT_EVERY = max(1, N_STEPS ÷ 10)
const DRIFT_STEPS = Tuple(FORK_STEP + DRIFT_EVERY:DRIFT_EVERY:END_STEP)   # 20-step spacing in the production run
const DEVICE_N = (152, 74, 56)
const STAGES_U = (:pre_scale, :predict_bdim, :predict_bc, :predict_exitbc, :project1_gradient, :project1_bc, :correct_bdim, :correct_scale,
    :correct_bc, :project2_gradient, :project2_bc)
const TAUS = (1e-4, 1e-5, 1e-6, 1e-7)
const COUNTS = (1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64)
tau_name(t) = "1e-$(Int(round(-log10(t))))"
const ARMS = vcat(
    [(name="A0_baseline", kind=:none, tau=0.0, n=0)],
    [(name="A1_tau_$(tau_name(t))", kind=:refine_threshold, tau=t, n=0) for t in TAUS],
    [(name="A1_n$(lpad(n, 2, '0'))", kind=:refine_count, tau=0.0, n=n) for n in COUNTS],
    [(name="D_tau_$(tau_name(t))", kind=:dual_stop, tau=t, n=0) for t in TAUS],
    [(name="F32_forced_dual_32", kind=:forced, tau=0.0, n=32)])
const ACTIVE = DRYRUN && haskey(ENV, "DIAG3_ONLY") ? Tuple(split(ENV["DIAG3_ONLY"], ",")) : nothing
const STAGE_B_STEPS = DRYRUN && haskey(ENV, "DIAG3_STAGE_B_STEPS") ? parse(Int, ENV["DIAG3_STAGE_B_STEPS"]) : nothing
const FORCE_SELECT = DRYRUN && haskey(ENV, "DIAG3_FORCE_SELECT") ? ENV["DIAG3_FORCE_SELECT"] : nothing
const RAISE_ARM = DRYRUN && haskey(ENV, "DIAG3_RAISE_ARM") ? ENV["DIAG3_RAISE_ARM"] : nothing

to_device(a) = BACKEND == "cuda" ? Base.invokelatest(getfield(Main, :CuArray), a) : a
sync() = BACKEND == "cuda" ? Base.invokelatest(CUDA.synchronize) : nothing
used_memory() = BACKEND == "cuda" ? Base.invokelatest(CUDA.used_memory) : 0
using LinearAlgebra: norm

# ---- verbatim from the G2 script ------------------------------------------------------------------------------------------
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


include(joinpath(@__DIR__, "waterlily_grad_g2_diag3_fixture.jl"))   # TanOf / TMax / AddTan and `make_refiner` (the fixture system itself is not used here)

# ---- writers ---------------------------------------------------------------------------------------------------------------
json(x::Nothing) = "null"
json(x::Bool) = x ? "true" : "false"
json(x::Integer) = string(x)
json(x::AbstractFloat) = isfinite(x) ? string(x) : "null"
json(x::AbstractString) = "\"" * replace(x, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n", "\r" => "\\r", "\t" => "\\t", "\e" => "\\u001b") * "\""
json(x::Symbol) = json(string(x))
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::Tuple) = json(collect(x))
json(x::NamedTuple) = json(Dict(string(k) => v for (k, v) in pairs(x)))
json(x::AbstractDict) = "{" * join([json(string(k)) * ":" * json(x[k]) for k in sort(collect(keys(x)); by=string)], ",") * "}"
function write_json(path, value)   # atomic: a kill during the write must not leave a truncated index
    tmp = string(path, ".tmp")
    open(io -> write(io, json(value), "\n"), tmp, "w")
    mv(tmp, path; force=true)
end
csv_open(path, header) = (io = open(path, "w"); println(io, join(header, ",")); flush(io); io)
csv_row(io, cells) = (println(io, join((string(c) for c in cells), ",")); nothing)


# ---- statistics, checksums ----------------------------------------------------------------------------------------------------
absp(x) = (v = Float64(FD.value(x)); isfinite(v) ? abs(v) : 0.0)
abst(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? abs(v) : 0.0)
badp(x) = !isfinite(FD.value(x))
badt(x) = !isfinite(FD.partials(x, 1))
box_max_t(u) = maximum(abst, view(u, 1:12, 1:8, 49:DEVICE_N[3], :))      # the corner box of G2-DIAG1 / DIAG2 (1-based)

function checksum(A::Array)          # whole Dual bits (value and tangent)
    sizeof(eltype(A)) == 8 || error("expected an 8-byte Dual{Float32,1}")
    w = reinterpret(UInt32, vec(A))
    return (reduce(xor, w), sum(UInt64, w))
end
function value_checksum(A::Array)    # primal values only (the first word of every element)
    w = reinterpret(UInt32, vec(A))[1:2:end]
    return (reduce(xor, w), sum(UInt64, w))
end
sha_hex(A::Array) = GC.@preserve A bytes2hex(sha256(unsafe_wrap(Array, Ptr{UInt8}(pointer(A)), length(A) * sizeof(eltype(A)))))
function dt_bits(sim)
    v, t = vp(sim.flow.Δt[end])
    return (reinterpret(UInt64, v), reinterpret(UInt64, t))
end
function step_record(sim)
    sync()
    u, p = Array(sim.flow.u), Array(sim.flow.p)
    (ux, us), (px, ps) = checksum(u), checksum(p)
    (uvx, uvs), (pvx, pvs) = value_checksum(u), value_checksum(p)
    return (u=u, p=p, cs=(ux, us, px, ps, dt_bits(sim)...), vcs=(uvx, uvs, pvx, pvs, dt_bits(sim)[1]))
end
const CS_HEADER = ["u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits"]
const VCS_HEADER = ["u_val_xor", "u_val_sum", "p_val_xor", "p_val_sum", "dt_val_bits"]
const REFINE_HEADER = [string(c, k) for k in 1:2 for c in ("cyc", "rel_before", "rel_after", "tangent_mean", "dz_max", "rel_after_demeaned", "rel_before_demeaned")]
const ARM_HEADER = ["step", "t_u_l", "dt_value", "dt_tangent", "glob_max_tangent_u", "glob_max_primal_u", "nonfinite_primal_u", "nonfinite_tangent_u",
    (string("box_", s) for s in STAGES_U)..., "iters1", "iters2", "z1_primal", "z1_tangent", "r1_primal", "r1_tangent", "z2_primal", "z2_tangent",
    "r2_primal", "r2_tangent", CS_HEADER..., VCS_HEADER..., REFINE_HEADER...]

mutable struct MProbe
    rec::Dict{String,Float64}
end
function (p::MProbe)(stage::Symbol, fields::NamedTuple; iters=nothing, r2=nothing)
    if haskey(fields, :u) || haskey(fields, :u0)
        A = haskey(fields, :u) ? fields.u : fields.u0
        p.rec["box_$stage"] = box_max_t(A)
        if stage === :project2_bc
            p.rec["glob_t"] = maximum(abst, A); p.rec["glob_p"] = maximum(absp, A)
            p.rec["nf_p"] = count(badp, A); p.rec["nf_t"] = count(badt, A)
        end
    end
    for (tag, n) in ((:project1, "1"), (:project2, "2"))
        if stage === Symbol(tag, :_rhs)
            p.rec["z$(n)_p"] = maximum(absp, fields.z); p.rec["z$(n)_t"] = maximum(abst, fields.z)
        elseif stage === Symbol(tag, :_solve)
            p.rec["r$(n)_p"] = maximum(absp, fields.r); p.rec["r$(n)_t"] = maximum(abst, fields.r); p.rec["iters$n"] = Float64(iters)
        end
    end
    return nothing
end

function make_hook(spec, sim, ::Type{DT}) where {DT}
    spec.kind === :none && return nothing
    spec.kind === :forced && return WaterLily.ForcedSolve(spec.n, NTuple{7,Float64}[])
    spec.kind === :dual_stop && return make_dual_stop(sim.pois, DT; tau=spec.tau, maxit=MAX_TANGENT_CYCLES)
    spec.kind === :refine_threshold && return make_refiner(sim.pois, DT; fixed=0, tau=spec.tau, maxit=MAX_TANGENT_CYCLES)
    spec.kind === :refine_count && return make_refiner(sim.pois, DT; fixed=spec.n, tau=0.0, maxit=spec.n)
    error("unknown arm kind $(spec.kind)")
end
hook_stats(h) = h === nothing ? NTuple{7,Float64}[] : h.stats

function arm_step!(sim, probe, hook)
    WaterLily.measure!(sim)   # sim_step!(sim; remeasure=true): measure!(sim) then mom_step!
    WaterLily.diag3_mom_step!(sim.flow, sim.pois, probe, hook)
    return nothing
end

# ---- run S: straight plain replay, fork state, drift references -----------------------------------------------------------------------
function run_straight(phi_host, ::Type{T}, case, outdir) where {T}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    io = csv_open(joinpath(outdir, "straight_checksums.csv"), ["step", CS_HEADER..., VCS_HEADER..., "glob_max_tangent_u", "box_max_tangent_u"])
    cs, vcs, fork, snaps, final_gt, floor_gt = Dict{Int,Any}(), Dict{Int,Any}(), nothing, Dict{Int,Any}(), NaN, NaN
    started = time()
    GC.@preserve phi_dev owner sim bodies begin
        r0 = step_record(sim); cs[0] = r0.cs; vcs[0] = r0.vcs; csv_row(io, (0, r0.cs..., r0.vcs..., 0, 0))
        for step in 1:END_STEP
            WaterLily.sim_step!(sim)
            r = step_record(sim)
            cs[step] = r.cs; vcs[step] = r.vcs
            gt, bt = step >= FORK_STEP ? (maximum(abst, sim.flow.u), box_max_t(sim.flow.u)) : (NaN, NaN)
            csv_row(io, (step, r.cs..., r.vcs..., gt, bt)); flush(io)
            step == FORK_STEP && (fork = (u=r.u, p=r.p, dt=copy(sim.flow.Δt)); floor_gt = gt)
            step == END_STEP && (final_gt = gt)
            if step in DRIFT_STEPS
                row = try sample_row(sim, bodies, step) catch; fill(NaN, 9) end
                snaps[step] = (u=FD.value.(r.u), p=FD.value.(r.p), fx=row[4], fz=row[8])
            end
        end
        close(io)
        sync()
        size(sim.flow.u) == (DEVICE_N..., 3) || error("flow array extent $(size(sim.flow.u)) != the registered $(DEVICE_N)")
        return Dict{String,Any}("steps_run" => END_STEP, "seconds" => time() - started, "t_end_u_l" => vp(WaterLily.sim_time(sim))[1],
            "fork_u_sha256" => sha_hex(fork.u), "fork_p_sha256" => sha_hex(fork.p), "fork_dt_length" => length(fork.dt),
            "floor_glob_max_tangent_u_at_fork" => floor_gt, "final_glob_max_tangent_u" => final_gt, "checksums" => cs, "value_checksums" => vcs), fork, snaps
    end
end

# ---- one arm -------------------------------------------------------------------------------------------------------------------------------
function run_arm(spec, phi_host, ::Type{T}, ::Type{DT}, case, fork, snaps, outdir, drift_io) where {T,DT}
    RAISE_ARM == spec.name && error("DIAG3 deliberate dry-run exception in $(spec.name)")
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    probe = MProbe(Dict{String,Float64}())
    cs, vcs, stopped, started, io = Dict{Int,Any}(), Dict{Int,Any}(), nothing, time(), nothing
    GC.@preserve phi_dev owner sim bodies begin
        try
            io = csv_open(joinpath(outdir, "arm_$(spec.name).steps.csv"), ARM_HEADER)
            copyto!(sim.flow.u, to_device(fork.u)); copyto!(sim.flow.p, to_device(fork.p))
            empty!(sim.flow.Δt); append!(sim.flow.Δt, fork.dt)
            hook = make_hook(spec, sim, DT)
            for step in FORK_STEP + 1:END_STEP
                empty!(probe.rec); empty!(hook_stats(hook))
                arm_step!(sim, probe, hook)
                r = step_record(sim)
                cs[step] = r.cs; vcs[step] = r.vcs
                rec = probe.rec
                dtv, dtt = vp(sim.flow.Δt[end])
                row = Any[step, vp(WaterLily.sim_time(sim))[1], dtv, dtt, get(rec, "glob_t", NaN), get(rec, "glob_p", NaN), get(rec, "nf_p", NaN), get(rec, "nf_t", NaN)]
                append!(row, (get(rec, "box_$s", NaN) for s in STAGES_U))
                append!(row, (get(rec, k, NaN) for k in ("iters1", "iters2", "z1_p", "z1_t", "r1_p", "r1_t", "z2_p", "z2_t", "r2_p", "r2_t")))
                append!(row, r.cs); append!(row, r.vcs)
                st = hook_stats(hook)
                for k in 1:2
                    append!(row, length(st) >= k ? collect(st[k]) : fill(NaN, 7))
                end
                csv_row(io, row); flush(io)
                if step in DRIFT_STEPS && haskey(snaps, step)
                    s = snaps[step]; du = FD.value.(r.u) .- s.u; dp = FD.value.(r.p) .- s.p
                    frow = try sample_row(sim, bodies, step) catch; fill(NaN, 9) end
                    csv_row(drift_io, (spec.name, step, maximum(abs, du), norm(du) / norm(s.u), maximum(abs, dp), norm(dp) / max(norm(s.p), 1e-300), frow[4], frow[8], s.fx, s.fz))
                    flush(drift_io)
                end
                if get(rec, "nf_p", 0.0) > 0 || get(rec, "nf_t", 0.0) > 0
                    stopped = step
                    break
                end
            end
            hook isa WaterLily.TangentRefine && !aux_operator_matches(sim.pois, hook) && error("the value-only operator of $(spec.name) no longer matches the live Dual operator")
        finally
            io === nothing || close(io)
        end
        sync()
        return Dict{String,Any}("name" => spec.name, "kind" => spec.kind, "tau" => spec.tau, "n" => spec.n, "steps_run" => length(cs), "stopped_nonfinite_at_step" => stopped,
            "seconds" => time() - started, "checksums" => cs, "value_checksums" => vcs, "used_vram_bytes_at_end" => used_memory())
    end
end

# ---- analysis of stage A (mirrored by scripts/analyze_grad_g2_diag3.py) -------------------------------------------------------------------------
function read_cols(path)
    lines = readlines(path)
    head = split(lines[1], ",")
    cols = Dict(h => Float64[] for h in head)
    for l in lines[2:end]
        for (h, c) in zip(head, split(l, ","))
            push!(cols[h], parse(Float64, c))
        end
    end
    return cols
end
function slope(steps, ys)
    n = length(steps)
    n < (DRYRUN ? 3 : 10) && return NaN
    mx, my = sum(steps) / n, sum(ys) / n
    sxx = sum((x - mx)^2 for x in steps)
    return sxx == 0 ? NaN : sum((x - mx) * (y - my) for (x, y) in zip(steps, ys)) / sxx
end
function col_slope(cols, name)
    idx = [i for (i, s) in enumerate(cols["step"]) if s >= SLOPE_FROM && isfinite(cols[name][i])]
    return slope(cols["step"][idx], [log10(max(cols[name][i], 1e-300)) for i in idx])
end
function classify(s, sb, endpoint, s0, sb0, floor_gt, stopped)
    stopped !== nothing && return "diverged"
    (isnan(s) || isnan(sb)) && return "undetermined"
    (s <= SUPPRESS_SLOPE && sb <= SUPPRESS_SLOPE && endpoint <= FLOOR_FACTOR * floor_gt) && return "suppresses"
    (s <= REDUCE_FACTOR * s0 && sb <= REDUCE_FACTOR * sb0) && return "reduces"
    return "no_effect"
end
arm_family(spec) = spec.kind === :refine_threshold ? :threshold : spec.kind === :refine_count ? :count : spec.kind === :dual_stop ? :dual : spec.kind === :forced ? :forced : :baseline

# settings of a family that sit in a run of >= PLATEAU_RUN consecutive suppressing, identity-passing settings (family order = loose -> tight)
function plateau_members(names, ok)
    members, i = String[], 1
    while i <= length(names)
        if ok[names[i]]
            j = i
            while j < length(names) && ok[names[j + 1]]
                j += 1
            end
            j - i + 1 >= PLATEAU_RUN && append!(members, names[i:j])
            i = j + 1
        else
            i += 1
        end
    end
    return members
end
# the selected Stage B candidate: threshold-family plateau member with a looser neighbour that also suppresses, fewest mean tangent cycles, ties -> tighter
function select_candidate(names, ok, mean_cycles)
    plateau = plateau_members(names, ok)
    cand = [n for n in plateau if (k = findfirst(==(n), names); k > 1 && ok[names[k - 1]])]
    isempty(cand) && return nothing
    best = cand[1]
    for n in cand[2:end]
        mean_cycles[n] < mean_cycles[best] && (best = n)
        mean_cycles[n] == mean_cycles[best] && findfirst(==(n), names) > findfirst(==(best), names) && (best = n)
    end
    return best
end

# ---- stage B: held-out D0 long horizon with the selected tangent rule ------------------------------------------------------------------------------
function run_long(phi_host, ::Type{T}, ::Type{DT}, case, outdir, spec) where {T,DT}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    probe = MProbe(Dict{String,Float64}())
    hook = make_hook(spec, sim, DT)
    header = ["step", "t_u_l", "glob_max_tangent_u", "glob_max_primal_u", "box_max_tangent_u", "nonfinite_primal_u", "nonfinite_tangent_u", "iters1", "iters2",
        "cyc1", "rel_before1", "rel_after1", "tangent_mean1", "rel_after_demeaned1", "cyc2", "rel_before2", "rel_after2", "tangent_mean2", "rel_after_demeaned2"]
    io = csv_open(joinpath(outdir, "longrun.steps.csv"), header)
    rows = Vector{Vector{Float64}}()
    started, step, stopped, failure, completed = time(), 0, nothing, nothing, false
    max_box, max_glob = 0.0, 0.0
    GC.@preserve phi_dev owner sim bodies begin
        try
            while true
                step += 1
                empty!(probe.rec); empty!(hook_stats(hook))
                arm_step!(sim, probe, hook)
                rec = probe.rec; st = hook_stats(hook)
                t = vp(WaterLily.sim_time(sim))[1]
                max_box = max(max_box, get(rec, "box_project2_bc", 0.0)); max_glob = max(max_glob, get(rec, "glob_t", 0.0))
                a = length(st) >= 1 ? st[1] : ntuple(_ -> NaN, 7); b = length(st) >= 2 ? st[2] : ntuple(_ -> NaN, 7)
                csv_row(io, (step, t, get(rec, "glob_t", NaN), get(rec, "glob_p", NaN), get(rec, "box_project2_bc", NaN), get(rec, "nf_p", NaN), get(rec, "nf_t", NaN),
                    get(rec, "iters1", NaN), get(rec, "iters2", NaN), a[1], a[2], a[3], a[4], a[6], b[1], b[2], b[3], b[4], b[6]))
                step % 8 == 0 && flush(io)
                if step % 400 == 0
                    write_history(joinpath(outdir, "longrun.history.csv"), rows)       # periodic copy: a kill keeps the history up to here
                    write_json(joinpath(outdir, "longrun.progress.json"), Dict("step" => step, "t_u_l" => t, "samples" => length(rows), "max_box_max_tangent_u" => max_box, "max_glob_max_tangent_u" => max_glob))
                end
                if get(rec, "nf_p", 0.0) > 0 || get(rec, "nf_t", 0.0) > 0
                    stopped = step; break
                end
                if step >= 2 && (step % SAMPLE_EVERY == 0 || t >= WINDOW[2])
                    try
                        push!(rows, sample_row(sim, bodies, step))
                    catch err
                        failure = Dict("step" => step, "message" => sprint(showerror, err)); break
                    end
                end
                t >= WINDOW[2] && (completed = true; break)
                STAGE_B_STEPS !== nothing && step >= STAGE_B_STEPS && break
                step >= MAX_LONG_STEPS && break
            end
        finally
            close(io)
        end
        sync()
        write_history(joinpath(outdir, "longrun.history.csv"), rows)
        summary = nothing
        if completed
            summary = try summarize(rows) catch err Dict("error" => sprint(showerror, err)) end
            write_json(joinpath(outdir, "longrun.summary.json"), summary)
        end
        return Dict{String,Any}("steps_run" => step, "completed_window" => completed, "stopped_nonfinite_at_step" => stopped, "sample_failure" => failure, "seconds" => time() - started,
            "samples" => length(rows), "max_box_max_tangent_u" => max_box, "max_glob_max_tangent_u" => max_glob, "rule" => spec.name,
            "t_end_u_l" => vp(WaterLily.sim_time(sim))[1], "summary_error" => summary isa Dict ? get(summary, "error", nothing) : nothing)
    end
end

# ---- a small production-path smoke test (before the long straight replay) -------------------------------------------------------------------------
function smoke(phi_host, ::Type{T}, ::Type{DT}, case) where {T,DT}
    results = Dict{String,Any}()
    base = nothing
    for spec in ((name="s_none", kind=:none, tau=0.0, n=0), (name="s_refine", kind=:refine_count, tau=0.0, n=2), (name="s_threshold", kind=:refine_threshold, tau=1e-5, n=0),
                 (name="s_dual", kind=:dual_stop, tau=1e-5, n=0), (name="s_forced", kind=:forced, tau=0.0, n=4))
        phi_dev = to_device(phi_host)
        sim, bodies, owner = build(phi_dev, T, case)
        GC.@preserve phi_dev owner sim bodies begin
            hook = make_hook(spec, sim, DT); probe = MProbe(Dict{String,Float64}())
            for _ in 1:2
                empty!(hook_stats(hook)); arm_step!(sim, probe, hook)
            end
            r = step_record(sim)
            finite = count(badp, sim.flow.u) == 0 && count(badt, sim.flow.u) == 0 && isfinite(maximum(abst, sim.flow.u))   # abst/absp map non-finite to 0, so count them
            spec.kind === :none && (base = r.vcs)
            op_ok = !(hook isa WaterLily.TangentRefine) || aux_operator_matches(sim.pois, hook)
            results[spec.name] = Dict("finite" => finite, "primal_equal_to_baseline" => base !== nothing && r.vcs == base, "aux_operator_matches_live_operator" => op_ok,
                "cycles_last_step" => collect(first.(hook_stats(hook))), "stats_last_call" => isempty(hook_stats(hook)) ? nothing : collect(last(hook_stats(hook))))
        end
    end
    results["s_refine"]["primal_equal_to_baseline"] && results["s_threshold"]["primal_equal_to_baseline"] || error("smoke: a tangent-only arm changed the primal: $results")
    all(r["finite"] for r in values(results)) || error("smoke: non-finite result: $results")
    all(r["aux_operator_matches_live_operator"] for r in values(results)) || error("smoke: the value-only operator does not match the live operator: $results")
    results["s_refine"]["cycles_last_step"] == [2.0, 2.0] || error("smoke: the fixed-count refinement did not run 2 cycles per projection: $results")
    # the refinement must actually act: the active-demeaned tangent residual drops (stats tuple: cycles, rel before, rel after, mean, dz, rel after demeaned, rel before demeaned)
    st = results["s_threshold"]["stats_last_call"]
    (st[1] > 0 && st[6] < 0.9 * st[7]) || error("smoke: the threshold refinement did not reduce the tangent residual: $results")
    return results
end

function main()
    length(ARGS) == 5 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>")
    phi_path, phi_sha, outdir, d0_path, d0_sha = ARGS
    mkpath(outdir)
    isfile(joinpath(outdir, "diag_index.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2-DIAG3", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "status" => "RUNNING", "dryrun" => DRYRUN, "fork_step" => FORK_STEP, "end_step" => END_STEP, "slope_from_step" => SLOPE_FROM,
        "arms" => [a.name for a in ARMS],
        "waterlily_flow_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Flow.jl")))),
        "waterlily_multilevelpoisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "MultiLevelPoisson.jl")))),
        "waterlily_poisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Poisson.jl")))),
        "evidence_class" => "gpu_d0_tangent_only_poisson_continuation_diagnostic_unregistered",
        "claim_limit" => "diagnostic of the Poisson differentiation semantics; not a gradient qualification; no bridge value, no error gate",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    write_json(joinpath(outdir, "diag_index.json"), index)   # RUNNING: survives a kill by the kernel time limit
    exit_code = 0
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
        d32 = load_raw(d0_path, d0_sha)
        maximum(abs, d32) == 1.0f0 || error("D0: direction max-norm != 1")
        for s in (-1.0, 1.0)
            zero_level_margin_m(Float64.(phi32) .+ s * 5e-3 .* Float64.(d32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 || error("D0: clearance gate failed")
        end
        tag = FD.Tag(run_one_tag, Float32)
        DT = FD.Dual{typeof(tag),Float32,1}
        phi_dual = DT.(phi32, FD.Partials.(tuple.(d32)))   # alpha = 0 primal, seed 1, alpha in metres (as G2)
        index["smoke"] = smoke(phi_dual, DT, DT, case)
        write_json(joinpath(outdir, "diag_index.json"), index)
        straight, fork, snaps = run_straight(phi_dual, DT, case, outdir)
        index["straight"] = Dict(k => v for (k, v) in straight if k != "checksums" && k != "value_checksums")
        write_json(joinpath(outdir, "diag_index.json"), index)
        drift_io = csv_open(joinpath(outdir, "drift.csv"), ["arm", "step", "max_abs_du", "rel_l2_u", "max_abs_dp", "rel_l2_p", "fx", "fz", "fx_straight", "fz_straight"])
        results, any_exception = Dict{String,Any}(), false
        for spec in ARMS
            ACTIVE !== nothing && !(spec.name in ACTIVE) && continue
            GC.gc()
            index["current_arm"] = spec.name
            write_json(joinpath(outdir, "diag_index.json"), index)
            r = try
                run_arm(spec, phi_dual, DT, DT, case, fork, snaps, outdir, drift_io)
            catch err
                any_exception = true
                Dict{String,Any}("name" => spec.name, "kind" => spec.kind, "steps_run" => 0, "stopped_nonfinite_at_step" => nothing, "checksums" => Dict{Int,Any}(),
                    "value_checksums" => Dict{Int,Any}(), "exception" => first(sprint(showerror, err, catch_backtrace()), 3000))
            end
            results[spec.name] = r
            index["arm_results"] = Dict(k => Dict(kk => vv for (kk, vv) in v if kk != "checksums" && kk != "value_checksums") for (k, v) in results)
            write_json(joinpath(outdir, "diag_index.json"), index)
        end
        close(drift_io)
        # ---- stage A evaluation
        floor_gt = straight["floor_glob_max_tangent_u_at_fork"]
        a0 = get(results, "A0_baseline", nothing)
        full_run(r) = r["steps_run"] == N_STEPS && r["stopped_nonfinite_at_step"] === nothing
        a0_ok = a0 !== nothing && !haskey(a0, "exception") && full_run(a0) && isfinite(straight["final_glob_max_tangent_u"]) &&
                all(haskey(straight["checksums"], s) && straight["checksums"][s] == c for (s, c) in a0["checksums"])
        identity = Dict(n => (!haskey(r, "exception") && !isempty(r["value_checksums"]) &&
                              all(haskey(straight["value_checksums"], s) && straight["value_checksums"][s] == c for (s, c) in r["value_checksums"])) for (n, r) in results)
        slopes, boxslopes, endpoints = Dict{String,Float64}(), Dict{String,Float64}(), Dict{String,Float64}()
        mean_cycles, classes = Dict{String,Float64}(), Dict{String,String}()
        s0 = sb0 = NaN
        if a0_ok
            c0 = read_cols(joinpath(outdir, "arm_A0_baseline.steps.csv")); s0, sb0 = col_slope(c0, "glob_max_tangent_u"), col_slope(c0, "box_project2_bc")
        end
        for spec in ARMS
            (haskey(results, spec.name) && !haskey(results[spec.name], "exception")) || continue
            cols = read_cols(joinpath(outdir, "arm_$(spec.name).steps.csv"))
            slopes[spec.name], boxslopes[spec.name] = col_slope(cols, "glob_max_tangent_u"), col_slope(cols, "box_project2_bc")
            endpoints[spec.name] = isempty(cols["glob_max_tangent_u"]) ? NaN : cols["glob_max_tangent_u"][end]
            cyc = spec.kind in (:refine_threshold, :refine_count) ? cols["cyc1"] .+ cols["cyc2"] : cols["iters1"] .+ cols["iters2"]
            mean_cycles[spec.name] = isempty(cyc) ? NaN : sum(cyc) / length(cyc)
            classes[spec.name] = spec.kind === :none ? "baseline" :
                classify(slopes[spec.name], boxslopes[spec.name], endpoints[spec.name], s0, sb0, floor_gt, results[spec.name]["stopped_nonfinite_at_step"])
        end
        index["identity_primal_values"] = identity; index["slopes_decade_per_step"] = slopes; index["box_slopes_decade_per_step"] = boxslopes
        index["endpoint_glob_max_tangent_u"] = endpoints; index["mean_tangent_cycles_per_step"] = mean_cycles; index["classes"] = classes
        index["baseline"] = Dict("slope" => s0, "box_slope" => sb0, "floor_glob_max_tangent_u_at_fork" => floor_gt, "identity_and_complete" => a0_ok)
        suppress_ok(spec) = get(classes, spec.name, "") == "suppresses" && get(identity, spec.name, false)
        plateau = Dict{String,Any}()
        for f in (:threshold, :count)
            names = [a.name for a in ARMS if arm_family(a) === f]
            ok = Dict(a.name => suppress_ok(a) for a in ARMS if arm_family(a) === f)
            plateau[string(f)] = Dict("members" => plateau_members(names, ok), "suppressing" => [n for n in names if ok[n]])
        end
        index["plateau"] = plateau
        any_support = any(!isempty(v["members"]) for v in values(plateau))
        stage_a, why = any_exception ? ("DIAG3_INCONCLUSIVE", "an arm raised an exception") :
                       !a0_ok ? ("DIAG3_INCONCLUSIVE", "A0 is not complete / not bitwise equal to the straight replay") :
                       (isnan(s0) || s0 < BASELINE_MIN_SLOPE) ? ("DIAG3_NOT_REPRODUCED", "the baseline did not reproduce the tangent growth") :
                       any_support ? ("TANGENT_ONLY_CAUSAL_SUPPORT", "a plateau of >= $PLATEAU_RUN consecutive suppressing tangent-only settings with primal identity") :
                       ("TANGENT_ONLY_NO_SUPPORT", "no plateau of suppressing tangent-only settings")
        index["stage_a_verdict"], index["stage_a_reason"] = stage_a, why
        # ---- selection and stage B
        tnames = [a.name for a in ARMS if arm_family(a) === :threshold]
        selected = nothing
        if stage_a == "TANGENT_ONLY_CAUSAL_SUPPORT"
            tok = Dict(a.name => suppress_ok(a) for a in ARMS if arm_family(a) === :threshold)
            selected = select_candidate(tnames, tok, Dict(n => get(mean_cycles, n, Inf) for n in tnames))
        end
        FORCE_SELECT !== nothing && (selected = FORCE_SELECT)
        index["selected_candidate"] = selected
        write_json(joinpath(outdir, "diag_index.json"), index)
        if selected !== nothing
            spec = only(a for a in ARMS if a.name == selected)
            index["current_arm"] = "STAGE_B:" * selected
            index["status"] = "RUNNING_STAGE_B"
            write_json(joinpath(outdir, "diag_index.json"), index)
            long = try
                run_long(phi_dual, DT, DT, case, outdir, spec)
            catch err
                any_exception = true
                Dict{String,Any}("exception" => first(sprint(showerror, err, catch_backtrace()), 3000))
            end
            gates = !haskey(long, "exception") && long["completed_window"] && long["stopped_nonfinite_at_step"] === nothing && long["sample_failure"] === nothing &&
                    long["max_box_max_tangent_u"] <= LONG_BOX_MAX && long["max_glob_max_tangent_u"] <= LONG_GLOBAL_MAX
            long["gates_pass_kernel_side"] = gates
            index["stage_b"] = long
            index["stage_b_verdict"] = haskey(long, "exception") ? "DIAG3_INCONCLUSIVE" : (DRYRUN && STAGE_B_STEPS !== nothing) ? "DRYRUN_STAGE_B" :
                                       gates ? "DIAG3_LONG_HORIZON_STABLE" : "DIAG3_LONG_HORIZON_NOT_STABLE"
        else
            index["stage_b_verdict"] = "SKIPPED_NO_CANDIDATE"
        end
        terminal = stage_a in ("TANGENT_ONLY_CAUSAL_SUPPORT", "TANGENT_ONLY_NO_SUPPORT", "DIAG3_NOT_REPRODUCED")
        index["status"] = (terminal && get(index, "stage_b_verdict", "") != "DIAG3_INCONCLUSIVE") ? "COMPLETE" : "INCOMPLETE"
        index["verdict"] = index["status"] == "COMPLETE" ? stage_a : "DIAG3_INCONCLUSIVE"     # the top-level verdict is final only when everything completed
        index["status"] == "COMPLETE" || (exit_code = 2)
    catch err
        index["status"] = "ERROR"; index["verdict"] = "DIAG3_INCONCLUSIVE"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        exit_code = 2
    end
    write_json(joinpath(outdir, "diag_index.json"), index)
    println("DIAG3_RESULT ", index["status"], " ", index["verdict"], " stageB=", get(index, "stage_b_verdict", "-"), " ", outdir)
    exit_code == 0 || exit(exit_code)
end

run_one_tag() = nothing
main()
