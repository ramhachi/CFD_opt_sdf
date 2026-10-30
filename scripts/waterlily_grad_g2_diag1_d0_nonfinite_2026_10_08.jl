# G2-DIAG1: where does the D0 Dual{Float32,1} long-horizon run first go non-finite?  Observation only.
#
# Scientific state is that of G2 attempt 1 (scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl): canonical v17 phi,
# D0 direction bytes, flow_24, Candidate C body, Float32, ForwardDiff Dual width 1, WaterLily defaults (remeasure, Poisson tol
# 1e-4 / itmx 32).  `build`, `load_raw`, `vp`, `sample_row` and the constants are verbatim copies of the G2 script (a test pins
# that).  Two runs on the same device, each from a fresh simulation:
#   A "reference":    plain `sim_step!`, G2's force sampling every 8 steps, G2's error semantics -> reproduces (or not) G2's failure
#   B "instrumented": `measure!` + diag_mom_step! (stage copies with read-only probes) every step, per-step force ledger
# Both record bitwise state checksums; any mismatch makes the run DIAG_INCOMPLETE (observation changed the state, or
# non-determinism).  Nothing is clipped, reset, rescaled or replaced.  No Float64 Dual, no D1/D2/P1, no window/bridge, no delta.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_g2_diag1_d0_nonfinite_2026_10_08.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>
# env (cpu code-path dry run only): DIAG1_BACKEND=cpu, DIAG1_HORIZON_STEPS=<n>, DIAG1_SKIP_REFERENCE=1,
#   DIAG1_INJECT=<step>:<stage>:<field>:<tangent_inf|primal_nan>, DIAG1_RAISE_STEP=<n>

using WaterLily
using SHA
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "DIAG1_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("DIAG1_BACKEND must be cuda or cpu")
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

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)
const SAMPLE_EVERY = 8

# ---- diagnostic configuration (fixed in the pre-run freeze) ---------------------------------------------------------------
const DRYRUN = BACKEND == "cpu"
const DRY_STEPS = DRYRUN && haskey(ENV, "DIAG1_HORIZON_STEPS") ? parse(Int, ENV["DIAG1_HORIZON_STEPS"]) : nothing
(!DRYRUN && any(haskey(ENV, k) for k in ("DIAG1_HORIZON_STEPS", "DIAG1_SKIP_REFERENCE", "DIAG1_INJECT", "DIAG1_RAISE_STEP"))) &&
    error("DIAG1 dry-run switches are only allowed with DIAG1_BACKEND=cpu")
const HORIZON_STEPS = DRY_STEPS === nothing ? 1400 : DRY_STEPS     # run to step >= 1400 AND tU/L >= 20 (the later of the two)
const HORIZON_TIME = DRY_STEPS === nothing ? 20.0 : 0.0
const MAX_STEPS = DRY_STEPS === nothing ? 2000 : DRY_STEPS
const G2_FAIL_STEP = 1200
const G2_FAIL_TIME_REPR = "16.409412384033203"
const SNAP_STEPS = (0, 2, 100, 500, 900, 1000, 1050, 1100, 1150, 1175, 1190, 1195, 1198, 1199)
const SNAP_LATE_FROM = 1000
const SNAP_LATE_EVERY = 25
const HASH_EVERY = 25
const RING = 12
const SKIP_REFERENCE = DRYRUN && get(ENV, "DIAG1_SKIP_REFERENCE", "") == "1"
const INJECT = DRYRUN && haskey(ENV, "DIAG1_INJECT") ? Tuple(split(ENV["DIAG1_INJECT"], ":")) : nothing
const RAISE_STEP = DRYRUN && haskey(ENV, "DIAG1_RAISE_STEP") ? parse(Int, ENV["DIAG1_RAISE_STEP"]) : nothing
const SERIES = ("fx", "fy", "fz", "pfx", "pfy", "pfz", "vfx", "vfy", "vfz")
const FORCE_GROUPS = ("candidate_pressure", "candidate_viscous", "candidate_total", "ground_pressure", "ground_viscous", "ground_total")

# ---- verbatim from the G2 script ------------------------------------------------------------------------------------------
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

# ---- writers --------------------------------------------------------------------------------------------------------------
json(x::Nothing) = "null"
json(x::Bool) = x ? "true" : "false"
json(x::Integer) = string(x)
json(x::AbstractFloat) = isfinite(x) ? string(x) : "null"
json(x::AbstractString) = "\"" * replace(x, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n") * "\""
json(x::Symbol) = json(string(x))
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::Tuple) = json(collect(x))
json(x::AbstractDict) = "{" * join([json(string(k)) * ":" * json(x[k]) for k in sort(collect(keys(x)); by=string)], ",") * "}"
write_json(path, value) = open(io -> write(io, json(value), "\n"), path, "w")

csv_open(path, header) = (io = open(path, "w"); println(io, join(header, ",")); flush(io); io)
csv_row(io, cells) = (println(io, join((c isa AbstractFloat ? string(c) : string(c) for c in cells), ",")); nothing)
idxstr(I) = I === nothing ? "" : join(Tuple(I), ";")

# ---- array statistics (primal and tangent separately; Float64 accumulation; non-finite entries counted, not summed) --------
absp(x) = (v = Float64(FD.value(x)); isfinite(v) ? abs(v) : 0.0)
abst(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? abs(v) : 0.0)
sqp(x) = (v = Float64(FD.value(x)); isfinite(v) ? v * v : 0.0)
sqt(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? v * v : 0.0)
badp(x) = !isfinite(FD.value(x))
badt(x) = !isfinite(FD.partials(x, 1))
badany(x) = !(isfinite(FD.value(x)) && isfinite(FD.partials(x, 1)))

struct ToReal{R,F}   # isbits callable (no captured type object) for device `map`
    f::F
end
ToReal{R}(f::F) where {R,F} = ToReal{R,F}(f)
(t::ToReal{R})(x) where {R} = R(t.f(x))

function locate_max(f, A)
    buf = map(ToReal{real_type(eltype(A))}(f), A)
    m = maximum(buf)
    I = findfirst(==(m), buf)
    return I isa CartesianIndex ? I : CartesianIndices(A)[I]
end
host_elem(A, I) = only(Array(vec(A)[LinearIndices(A)[I]:LinearIndices(A)[I]]))

function stats_impl(A::AbstractArray; locate=true)
    n = length(A)
    return (n=n, np=count(badp, A), nt=count(badt, A), mp=maximum(absp, A), mt=maximum(abst, A),
        rp=sqrt(sum(sqp, A) / n), rt=sqrt(sum(sqt, A) / n),
        ap=locate ? locate_max(absp, A) : nothing, at=locate ? locate_max(abst, A) : nothing)
end

# Device reductions are used while they work (checked by `preflight` and on every call); on any device-side exception the same
# statistics are computed on a host copy (read-only), and the fallback is recorded in the index.
const DEVICE_STATS_OK = Ref(true)
const STATS_FALLBACK_ERROR = Ref("")
function stats(A::AbstractArray; locate=true)
    if A isa Array || !DEVICE_STATS_OK[]
        return stats_impl(A isa Array ? A : Array(A); locate)
    end
    try
        return stats_impl(A; locate)
    catch err
        DEVICE_STATS_OK[] = false
        STATS_FALLBACK_ERROR[] = first(sprint(showerror, err), 400)
        return stats_impl(Array(A); locate)
    end
end

function preflight(::Type{T}) where {T}   # tiny array with one infinite tangent: device path vs host path must agree
    h = reshape([T(Float32(i), FD.Partials((Float32(-i),))) for i in 1:24], 2, 3, 4)
    h[7] = T(1.0f0, FD.Partials((Inf32,)))
    d = to_device(h)
    ok = try
        a, b = stats_impl(d), stats_impl(h)
        a == b
    catch
        false
    end
    DEVICE_STATS_OK[] = ok
    return ok
end

# ---- the probe passed into the stage copies -------------------------------------------------------------------------------
const STAGE_HEADER = ["step", "stage_idx", "stage", "field", "n", "nonfinite_primal", "nonfinite_tangent", "maxabs_primal", "maxabs_tangent",
    "rms_primal", "rms_tangent", "argmax_primal", "argmax_tangent"]
const POISSON_HEADER = ["step", "stage", "iters", "dt_value", "dt_tangent", "r2_value", "r2_tangent"]

mutable struct Probe
    step::Int
    idx::Int
    step_t0::Float64
    stage_order::Vector{Tuple{Int,Symbol}}
    stage_io::IO
    poisson_io::IO
    first_bad::Union{Nothing,Dict{String,Any}}
    prev::Dict{Symbol,Tuple{Float64,Float64}}
    sim::Any
    capture::Function
    static::Any   # (sigma = signed distance, mu0, mu1, V) host copies taken right after `measure!` on step 1
    outdir::String
end

function maybe_inject!(p::Probe, stage::Symbol, fields)
    INJECT === nothing && return
    (p.step == parse(Int, INJECT[1]) && string(stage) == INJECT[2] && haskey(fields, Symbol(INJECT[3]))) || return
    A = fields[Symbol(INJECT[3])]
    x = A[1]
    A[1] = INJECT[4] == "tangent_inf" ? typeof(x)(FD.value(x), FD.Partials((typeof(FD.value(x))(Inf),))) :
           INJECT[4] == "primal_nan" ? typeof(x)(typeof(FD.value(x))(NaN), FD.partials(x)) : error("unknown injection kind")
end

function (p::Probe)(stage::Symbol, fields::NamedTuple; iters=nothing, r2=nothing)
    p.idx += 1
    if p.step == 1
        push!(p.stage_order, (p.idx, stage))
    else
        p.stage_order[p.idx] == (p.idx, stage) || error("stage order changed at step $(p.step): got $stage at index $(p.idx)")
    end
    maybe_inject!(p, stage, fields)
    for (name, arr) in pairs(fields)
        scalar = !(arr isa AbstractArray)
        A = scalar ? [arr] : arr
        s = stats(A; locate=!scalar)
        csv_row(p.stage_io, (p.step, p.idx, stage, name, s.n, s.np, s.nt, s.mp, s.mt, s.rp, s.rt, idxstr(s.ap), idxstr(s.at)))
        key = startswith(string(stage), "force_") ? Symbol(stage, ":", name) : name   # force probes reuse the names x, y, z
        if (s.np > 0 || s.nt > 0)
            if p.first_bad === nothing
                Ah = A isa Array ? A : Array(A)   # failure path only: locate on a host copy
                lin = findfirst(badany, vec(Ah))
                bad = CartesianIndices(Ah)[lin]
                x = Ah[lin]
                pv, tv = vp(x)
                last_p, last_t = get(p.prev, key, (NaN, NaN))
                p.first_bad = Dict{String,Any}("step" => p.step, "time_step_start_u_l" => p.step_t0, "stage" => string(stage), "stage_index" => p.idx,
                    "field" => string(name), "component" => (s.np > 0 && s.nt > 0) ? "both" : s.np > 0 ? "primal" : "tangent",
                    "first_bad_element_class" => isfinite(pv) ? "B_primal_finite_tangent_nonfinite" : isfinite(tv) ? "C_primal_nonfinite_tangent_finite" : "D_both_nonfinite",
                    "array_nonfinite_primal" => s.np, "array_nonfinite_tangent" => s.nt,
                    "first_bad_index" => scalar ? "" : idxstr(bad), "first_nonfinite_primal" => pv, "first_nonfinite_tangent" => tv,
                    "first_nonfinite_primal_repr" => string(pv), "first_nonfinite_tangent_repr" => string(tv),
                    "last_finite_maxabs_primal_same_field" => last_p, "last_finite_maxabs_tangent_same_field" => last_t)
                write_json(joinpath(p.outdir, "first_bad.json"), p.first_bad)   # durable the moment it is seen
                p.capture(p)
            end
        else
            p.prev[key] = (s.mp, s.mt)
        end
    end
    if iters !== nothing
        r2v, r2t = vp(r2)
        dtv, dtt = vp(p.sim.flow.Δt[end])
        csv_row(p.poisson_io, (p.step, stage, iters, dtv, dtt, r2v, r2t))
    end
    return nothing
end

function instrumented_step!(sim, probe::Probe)
    probe.idx = 0
    probe.step_t0 = vp(WaterLily.sim_time(sim))[1]
    WaterLily.measure!(sim)   # sim_step!(sim; remeasure=true): measure!(sim) then mom_step!
    if probe.step == 1
        sync()
        probe.static = (sigma=Array(sim.flow.σ), mu0=Array(sim.flow.μ₀), mu1=Array(sim.flow.μ₁), V=Array(sim.flow.V))
    end
    lv = sim.pois.levels
    geom = (sigma=sim.flow.σ, mu0=sim.flow.μ₀, mu1=sim.flow.μ₁, V=sim.flow.V, D1=lv[1].D, iD1=lv[1].iD)
    coarse = NamedTuple{ntuple(l -> Symbol(:L, l + 1), length(lv) - 1)}(ntuple(l -> lv[l + 1].L, length(lv) - 1))
    probe(:measure, merge(geom, coarse))
    WaterLily.diag_mom_step!(sim.flow, sim.pois, probe)
    return nothing
end

# ---- device -> host helpers, checksums, snapshots -------------------------------------------------------------------------
function checksum(A::Array)
    sizeof(eltype(A)) == 8 || error("expected an 8-byte Dual{Float32,1}")
    w = reinterpret(UInt32, vec(A))
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
    return (u=u, p=p, cs=(ux, us, px, ps, dt_bits(sim)...))
end

const CS_HEADER = ["step", "u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits"]

function write_snapshot!(index, outdir, step, tag, arrays)
    dir = joinpath(outdir, "snapshots"); mkpath(dir)
    for (name, A) in arrays
        file = "$(tag).$(name).dual_f32_interleaved_value_tangent.raw"
        open(io -> write(io, GC.@preserve(A, unsafe_wrap(Array, Ptr{UInt8}(pointer(A)), length(A) * sizeof(eltype(A))))), joinpath(dir, file), "w")
        index[file] = Dict("step" => step, "field" => name, "shape" => collect(size(A)), "sha256" => sha_hex(A),
            "layout" => "column-major; per element: value float32 LE, then tangent float32 LE", "bytes" => length(A) * sizeof(eltype(A)))
    end
    write_json(joinpath(outdir, "snapshot_index.json"), index)
    return nothing
end

# ---- run A: reference (plain sim_step!, G2 sampling and error semantics) ----------------------------------------------------
function done_horizon(step, sim)
    step >= MAX_STEPS || (step >= HORIZON_STEPS && vp(WaterLily.sim_time(sim))[1] >= HORIZON_TIME)
end

function run_reference(phi_host, ::Type{T}, case, outdir) where {T}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    cs_io = csv_open(joinpath(outdir, "reference_checksums.csv"), CS_HEADER)
    force_io = csv_open(joinpath(outdir, "reference_forces.csv"), ["step", "t_u_l", "t_u_l_tan", (c for s in SERIES for c in (s, s * "_tan"))...])
    cs, hashes, fail = Dict{Int,Any}(), Dict{Int,Any}(), nothing
    started = time()
    GC.@preserve phi_dev owner sim bodies begin
        function record(step)
            r = step_record(sim)
            cs[step] = r.cs; csv_row(cs_io, (step, r.cs...))
            (step % HASH_EVERY == 0 || step in SNAP_STEPS) && (hashes[step] = (sha_hex(r.u), sha_hex(r.p)))
            flush(cs_io)
        end
        record(0)
        WaterLily.sim_step!(sim)
        step = 1; record(step)
        while !done_horizon(step, sim)
            WaterLily.sim_step!(sim)
            step += 1
            record(step)
            if step % SAMPLE_EVERY == 0
                try
                    csv_row(force_io, sample_row(sim, bodies, step)); flush(force_io)
                catch err
                    fail = Dict{String,Any}("step" => step, "message" => sprint(showerror, err))
                    break
                end
            end
        end
        sync()
        close(cs_io); close(force_io)
        t_end = vp(WaterLily.sim_time(sim))[1]
        return Dict{String,Any}("steps_run" => step, "t_end_u_l" => t_end, "fail" => fail, "seconds" => time() - started, "checksums" => cs, "hashes" => hashes)
    end
end

# ---- run B: instrumented ---------------------------------------------------------------------------------------------------
function inventory(sim)
    rows = Any[]
    function add(path, A)
        A isa AbstractArray || return
        push!(rows, Dict{String,Any}("field_path" => path, "element_type" => string(eltype(A)), "shape" => collect(size(A)),
            "device" => string(nameof(typeof(A))), "contains_dual" => eltype(A) <: FD.Dual))
    end
    f = sim.flow
    for name in (:u, :u⁰, :f, :p, :σ, :V, :μ₀, :μ₁)
        add("sim.flow.$name", getfield(f, name))
    end
    push!(rows, Dict{String,Any}("field_path" => "sim.flow.Δt", "element_type" => string(eltype(f.Δt)), "shape" => [length(f.Δt)], "device" => "Vector(host)", "contains_dual" => eltype(f.Δt) <: FD.Dual))
    for (l, lev) in enumerate(sim.pois.levels), name in (:x, :L, :z, :r, :ϵ, :D, :iD)
        add("sim.pois.levels[$l].$name", getfield(lev, name))
    end
    return rows
end

function geometry_audit(host)
    out = Dict{String,Any}()
    d = FD.value.(host.sigma)
    for (name, A) in pairs(host)
        v, t = FD.value.(A), [FD.partials(x, 1) for x in A]
        fv, ft = filter(isfinite, vec(v)), filter(isfinite, vec(t))
        isempty(fv) && (fv = [NaN32]); isempty(ft) && (ft = [NaN32])
        order = sortperm(abs.(replace(vec(t), NaN => 0, Inf => 0, -Inf => 0)); rev=true)[1:min(10, length(t))]
        out[string(name)] = Dict{String,Any}("n" => length(A), "nonfinite_primal" => count(!isfinite, v), "nonfinite_tangent" => count(!isfinite, t),
            "min_primal" => minimum(fv), "max_primal" => maximum(fv), "min_tangent" => minimum(ft), "max_tangent" => maximum(ft),
            "top10_abs_tangent" => [Dict("index" => idxstr(CartesianIndices(A)[k]), "primal" => Float64(vec(v)[k]), "tangent" => Float64(vec(t)[k])) for k in order])
    end
    interior = (2:size(d, 1) - 1, 2:size(d, 2) - 1, 2:size(d, 3) - 1)
    g = sqrt.(((d[3:end, 2:end - 1, 2:end - 1] .- d[1:end - 2, 2:end - 1, 2:end - 1]) ./ 2) .^ 2 .+
              ((d[2:end - 1, 3:end, 2:end - 1] .- d[2:end - 1, 1:end - 2, 2:end - 1]) ./ 2) .^ 2 .+
              ((d[2:end - 1, 2:end - 1, 3:end] .- d[2:end - 1, 2:end - 1, 1:end - 2]) ./ 2) .^ 2)
    band = abs.(d[interior...]) .< 3
    gb = sort(Float64.(g[band]))
    mu0 = FD.value.(host.mu0)
    out["derived"] = Dict{String,Any}("cells" => length(d), "band_cells_abs_d_lt_3" => count(band), "cells_abs_d_lt_1" => count(abs.(d) .< 1),
        "mu0_strictly_between_0_and_1" => count(x -> 0 < x < 1, mu0),
        "grad_d_band_min" => isempty(gb) ? nothing : gb[1], "grad_d_band_p1" => isempty(gb) ? nothing : gb[max(1, round(Int, 0.01 * length(gb)))],
        "grad_d_band_median" => isempty(gb) ? nothing : gb[max(1, length(gb) ÷ 2)], "grad_d_band_max" => isempty(gb) ? nothing : gb[end],
        "note" => "descriptive only; no threshold is applied to these numbers")
    return out
end

function localize(host, I3, case)
    # solver-cell index -> physical metres (x_phys = origin + spacing * loc, loc(cell centre) = I - 1.5), plus static geometry there
    i, j, k = I3
    dv = FD.value.(host.sigma)
    g = ((dv[min(i + 1, end), j, k] - dv[max(i - 1, 1), j, k]) / 2, (dv[i, min(j + 1, end), k] - dv[i, max(j - 1, 1), k]) / 2,
         (dv[i, j, min(k + 1, end)] - dv[i, j, max(k - 1, 1)]) / 2)
    return Dict{String,Any}("cell" => collect(I3), "xyz_m" => [case.flow_origin_m[a] + case.flow_spacing_m * (I3[a] - 1.5) for a in 1:3],
        "sdf_solver_units_primal" => Float64(dv[i, j, k]), "sdf_solver_units_tangent" => Float64(FD.partials(host.sigma[i, j, k], 1)),
        "grad_sdf_magnitude" => Float64(sqrt(sum(abs2, g))), "in_band_abs_d_lt_3" => abs(dv[i, j, k]) < 3,
        "mu0" => [Float64(FD.value(host.mu0[i, j, k, c])) for c in 1:3], "mu0_tangent" => [Float64(FD.partials(host.mu0[i, j, k, c], 1)) for c in 1:3])
end

function run_instrumented(phi_host, ::Type{T}, case, outdir) where {T}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    stage_io = csv_open(joinpath(outdir, "stage_ledger.csv"), STAGE_HEADER)
    poisson_io = csv_open(joinpath(outdir, "poisson_ledger.csv"), POISSON_HEADER)
    force_io = csv_open(joinpath(outdir, "force_ledger.csv"), ["step", "t_u_l", "t_u_l_tan", (string(g, "_", c, suffix) for g in FORCE_GROUPS for c in ("x", "y", "z") for suffix in ("", "_tan"))...])
    cs_io = csv_open(joinpath(outdir, "instrumented_checksums.csv"), CS_HEADER)
    snap_index, cs, hashes, ring = Dict{String,Any}(), Dict{Int,Any}(), Dict{Int,Any}(), Any[]
    failure_state = Ref{Any}(nothing)
    capture = p -> begin   # state at the moment of the first non-finite observation (read-only host copies)
        sync()
        lv = p.sim.pois.levels
        failure_state[] = Dict("u" => Array(p.sim.flow.u), "u0" => Array(p.sim.flow.u⁰), "f" => Array(p.sim.flow.f), "p" => Array(p.sim.flow.p),
            "sigma" => Array(p.sim.flow.σ), "r" => Array(lv[1].r), "eps" => Array(lv[1].ϵ))
        write_snapshot!(snap_index, outdir, p.step, "firstbad_step$(lpad(p.step, 4, '0'))", collect(failure_state[]))
    end
    probe = Probe(0, 0, 0.0, Tuple{Int,Symbol}[], stage_io, poisson_io, nothing, Dict{Symbol,Tuple{Float64,Float64}}(), sim, capture, nothing, outdir)
    ground_ok = true; ground_reason = ""
    started = time(); first_step_seconds = 0.0; first_step_time = 0.0
    steps_run = 0; exception = nothing
    GC.@preserve phi_dev owner sim bodies begin
        write_json(joinpath(outdir, "inventory.json"), Dict("fields" => inventory(sim), "Δt_note" => "host Vector of Dual, one element per step",
            "probed_by_stage" => "see stage_order.json: u,u0,f,sigma(=Poisson z),p(=Poisson x),r,eps,mu0(=Poisson L),mu1,V,D,iD,coarse L/x/r"))
        r0 = step_record(sim); cs[0] = r0.cs; csv_row(cs_io, (0, r0.cs...)); hashes[0] = (sha_hex(r0.u), sha_hex(r0.p))
        write_snapshot!(snap_index, outdir, 0, "step0000", ["u" => r0.u, "p" => r0.p])
        step = 0
        try
            while true
                step += 1
                probe.step = step
                step == 1 && (first_step_time = time())
                RAISE_STEP !== nothing && step == RAISE_STEP && error("DIAG1 deliberate dry-run exception at step $step")
                instrumented_step!(sim, probe)
                if step == 1
                    sync()
                    first_step_seconds = time() - first_step_time
                    # geometry as measured on step 1 is the geometry of every step (Candidate C is time independent); the
                    # per-step `measure` stage rows in stage_ledger.csv are the check of that statement.
                    write_json(joinpath(outdir, "geometry_static_audit.json"), geometry_audit(probe.static))
                    write_json(joinpath(outdir, "stage_order.json"), [Dict("index" => i, "stage" => string(s)) for (i, s) in probe.stage_order])
                end
                # force ledger (read-only; same expressions as G2's sample_row, plus the ground body where available)
                row = Float64[Float64(step)]
                t, t_tan = vp(WaterLily.sim_time(sim)); push!(row, t, t_tan)
                groups = Dict{String,Any}()
                cp = -(WaterLily.pressure_force(sim.flow, bodies.candidate)); cv = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
                groups["candidate_pressure"], groups["candidate_viscous"], groups["candidate_total"] = cp, cv, cp + cv
                if ground_ok
                    try
                        gp = -(WaterLily.pressure_force(sim.flow, bodies.ground)); gv = -(WaterLily.viscous_force(sim.flow, bodies.ground))
                        groups["ground_pressure"], groups["ground_viscous"], groups["ground_total"] = gp, gv, gp + gv
                    catch err
                        ground_ok = false; ground_reason = first(sprint(showerror, err), 300)
                    end
                end
                for g in FORCE_GROUPS
                    vec3 = get(groups, g, nothing)
                    for c in 1:3
                        v, tg = vec3 === nothing ? (NaN, NaN) : vp(vec3[c])
                        push!(row, v, tg)
                    end
                    vec3 === nothing || probe(Symbol("force_", g), (x=vec3[1], y=vec3[2], z=vec3[3]))
                end
                csv_row(force_io, row)
                rec = step_record(sim)
                cs[step] = rec.cs; csv_row(cs_io, (step, rec.cs...))
                (step % HASH_EVERY == 0 || step in SNAP_STEPS) && (hashes[step] = (sha_hex(rec.u), sha_hex(rec.p)))
                push!(ring, (step, rec.u, rec.p)); length(ring) > RING && popfirst!(ring)
                if step in SNAP_STEPS || (step >= SNAP_LATE_FROM && step % SNAP_LATE_EVERY == 0)
                    write_snapshot!(snap_index, outdir, step, "step$(lpad(step, 4, '0'))", ["u" => rec.u, "p" => rec.p])
                end
                for io in (stage_io, poisson_io, force_io, cs_io); flush(io); end   # durable every step
                steps_run = step
                probe.first_bad !== nothing && break
                done_horizon(step, sim) && break
            end
        catch err
            exception = sprint(showerror, err, catch_backtrace())
        finally
            for io in (stage_io, poisson_io, force_io, cs_io); close(io); end
        end
        t_end = try
            sync(); vp(WaterLily.sim_time(sim))[1]
        catch
            NaN
        end
        # failure artefacts (also after an exception: the last retained steps are the evidence)
        localization = Dict{String,Any}("note" => "index -> metres assumes x_phys = flow_origin + flow_spacing * (I - 1.5) (NormalFloorWaterLilyBody.measure); coarse-level fields (L2..) are not localized")
        if probe.first_bad !== nothing
            fb = probe.first_bad
            idx = get(fb, "first_bad_index", "")
            if !isempty(idx) && probe.static !== nothing && !occursin(r"^L\d+$", fb["field"]) && !startswith(fb["stage"], "force_")
                I3 = Tuple(parse.(Int, split(idx, ";")))[1:3]
                localization["first_bad_cell"] = localize(probe.static, I3, case)
            end
        end
        if probe.first_bad !== nothing || exception !== nothing
            for (st, u, p) in ring
                (st in SNAP_STEPS || (st >= SNAP_LATE_FROM && st % SNAP_LATE_EVERY == 0)) && continue   # already written as a scheduled snapshot
                write_snapshot!(snap_index, outdir, st, "ring_step$(lpad(st, 4, '0'))", ["u" => u, "p" => p])
            end
        end
        if probe.static !== nothing && !isempty(ring)
            # where is the largest |tangent| of u at the end of each retained step, and what sits there
            tops = Any[]
            for (st, u, p) in ring
                vt = [abs(Float64(FD.partials(x, 1))) for x in u]
                vt[.!isfinite.(vt)] .= 0.0
                k = argmax(vt); I = CartesianIndices(u)[k]
                push!(tops, Dict("step" => st, "u_index" => idxstr(I), "maxabs_tangent_u" => vt[k], "location" => localize(probe.static, Tuple(I)[1:3], case)))
            end
            localization["ring_argmax_tangent_u"] = tops
        end
        write_json(joinpath(outdir, "localization.json"), localization)
        write_json(joinpath(outdir, "snapshot_index.json"), snap_index)
        write_json(joinpath(outdir, "stage_order.json"), [Dict("index" => i, "stage" => string(s)) for (i, s) in probe.stage_order])
        return Dict{String,Any}("steps_run" => steps_run, "t_end_u_l" => t_end, "first_bad" => probe.first_bad, "exception" => exception,
            "first_step_seconds_incl_jit" => first_step_seconds, "seconds" => time() - started, "checksums" => cs, "hashes" => hashes,
            "ground_decomposition" => ground_ok ? "available" : "unavailable: $ground_reason", "used_vram_bytes_at_end" => used_memory(), "device_stats_ok" => DEVICE_STATS_OK[], "stats_fallback_error" => STATS_FALLBACK_ERROR[])
    end
end

# ---- verdict (the rule is fixed in the pre-run note; the host analyzer re-derives it from the files) ------------------------
function self_check(A, B)
    A === nothing && return Dict{String,Any}("skipped" => true, "pass" => false, "reason" => "reference skipped (dry-run switch)")
    common = sort(collect(intersect(keys(A["checksums"]), keys(B["checksums"]))))
    mism = [s for s in common if A["checksums"][s] != B["checksums"][s]]
    hcommon = sort(collect(intersect(keys(A["hashes"]), keys(B["hashes"]))))
    hmism = [s for s in hcommon if A["hashes"][s] != B["hashes"][s]]
    return Dict{String,Any}("skipped" => false, "pass" => isempty(mism) && isempty(hmism) && length(common) >= 3, "compared_steps" => length(common),
        "last_common_step" => isempty(common) ? nothing : common[end], "checksum_mismatch_steps" => mism[1:min(end, 20)],
        "compared_sha256_steps" => length(hcommon), "sha256_mismatch_steps" => hmism[1:min(end, 20)])
end

function verdict(A, B, sc)
    B["exception"] === nothing || return ("DIAG_INCOMPLETE", "instrumented run raised an exception")
    A !== nothing && get(A, "exception", nothing) !== nothing && return ("DIAG_INCOMPLETE", "reference run raised an exception")
    if A === nothing
        return DRYRUN ? (B["first_bad"] === nothing ? "DRYRUN_NOT_REPRODUCED" : "DRYRUN_LOCALIZED", "reference skipped; dry run only") : ("DIAG_INCOMPLETE", "reference missing")
    end
    sc["pass"] || return ("DIAG_INCOMPLETE", "non-interference / determinism check failed")
    a_fail, b_fail = A["fail"], B["first_bad"]
    if b_fail === nothing && a_fail === nothing
        return ("DIAG_NOT_REPRODUCED", "both runs finite to the horizon")
    end
    if b_fail !== nothing && a_fail !== nothing
        reproduced = DRYRUN || (a_fail["step"] == G2_FAIL_STEP && occursin("t=$G2_FAIL_TIME_REPR)", a_fail["message"]))
        if !reproduced
            return ("DIAG_INCOMPLETE", "reference did not reproduce G2 attempt 1 (step $(a_fail["step"]))")
        end
        (DRYRUN || b_fail["step"] <= G2_FAIL_STEP) || return ("DIAG_INCOMPLETE", "first bad step after the G2 failure step")
        return (DRYRUN ? "DRYRUN_LOCALIZED" : "DIAG_LOCALIZED", "G2 failure reproduced; first bad quantity found")
    end
    return ("DIAG_INCOMPLETE", "reference and instrumented runs disagree about finiteness")
end

function main()
    length(ARGS) == 5 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>")
    phi_path, phi_sha, outdir, d0_path, d0_sha = ARGS
    mkpath(outdir)
    isfile(joinpath(outdir, "diag_index.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2-DIAG1", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "status" => "RUNNING", "dryrun" => DRYRUN,
        "waterlily_flow_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Flow.jl")))),
        "waterlily_multilevelpoisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "MultiLevelPoisson.jl")))), "horizon_steps" => HORIZON_STEPS, "horizon_time_u_l" => HORIZON_TIME,
        "g2_failure_reference" => Dict("step" => G2_FAIL_STEP, "t_u_l_repr" => G2_FAIL_TIME_REPR), "snapshot_steps" => collect(SNAP_STEPS),
        "evidence_class" => "gpu_d0_nonfinite_localization_diagnostic_unregistered",
        "claim_limit" => "diagnostic localization of the G2 attempt-1 D0 failure; no bridge value, no gradient qualification, no error gate",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    exit_code = 0
    write_json(joinpath(outdir, "diag_index.json"), index)   # status RUNNING: survives a kill by the kernel time limit
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
        index["device_stats_path_ok_preflight"] = preflight(DT)
        write_json(joinpath(outdir, "diag_index.json"), index)
        A = nothing
        if !SKIP_REFERENCE
            A = try
                run_reference(phi_dual, DT, case, outdir)
            catch err   # an unexpected error in the reference must not cost the instrumented run
                Dict{String,Any}("steps_run" => nothing, "t_end_u_l" => nothing, "fail" => nothing, "seconds" => nothing, "checksums" => Dict{Int,Any}(),
                    "hashes" => Dict{Int,Any}(), "exception" => first(sprint(showerror, err, catch_backtrace()), 4000))
            end
            write_json(joinpath(outdir, "reference_run.json"), Dict(k => v for (k, v) in A if k != "checksums" && k != "hashes"))
            GC.gc()
        end
        B = run_instrumented(phi_dual, DT, case, outdir)
        sc = self_check(A, B)
        write_json(joinpath(outdir, "selfcheck.json"), sc)
        v, why = verdict(A, B, sc)
        index["verdict"], index["verdict_reason"] = v, why
        index["reference"] = A === nothing ? nothing : Dict(k => v for (k, v) in A if k != "checksums" && k != "hashes")
        index["instrumented"] = Dict(k => v for (k, v) in B if k != "checksums" && k != "hashes")
        index["self_check"] = sc
        index["status"] = v in ("DIAG_LOCALIZED", "DIAG_NOT_REPRODUCED", "DRYRUN_LOCALIZED", "DRYRUN_NOT_REPRODUCED") ? "COMPLETE" : "INCOMPLETE"
        index["status"] == "COMPLETE" || (exit_code = 2)
    catch err
        index["status"] = "ERROR"; index["verdict"] = "DIAG_INCOMPLETE"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        exit_code = 2
    end
    write_json(joinpath(outdir, "diag_index.json"), index)
    println("DIAG1_RESULT ", index["status"], " ", index["verdict"], " ", outdir)
    exit_code == 0 || exit(exit_code)
end

run_one_tag() = nothing
main()
