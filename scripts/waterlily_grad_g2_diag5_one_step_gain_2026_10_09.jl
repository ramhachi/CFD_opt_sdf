# G2-DIAG5: where does the D0 corner tangent get its one-step gain, does the AD tangent agree with a finite-amplitude response of the implemented map, and is the
# gain a property of the map or of the derivative convention at the nonsmooth limiter?  CPU, Float32, Dual width 1, D0 (canonical v17, Candidate C, flow_24).
#
# The experiments are re-evaluations of the one-step map F (WaterLily 1.8.0 `sim_step!`, remeasure = true) at STORED T4 states of the DIAG1 B0 trajectory
# (u and p with their tangents; Δt = CFL(u) is derived, see Flow.jl `sim_step!`/`CFL`).  The persistent state of F is (u incl. its ghost cells, p): `p` is the Poisson
# initial guess (`mom_project!`: `b.x .*= dt`, "solution IC") and so is NOT scratch; u⁰, f, σ, μ₀, μ₁, V are rebuilt every step and Δt[end] is a function of u.
#
#   E0  harness closure: the CPU one-step map from stored step 1188 against the stored step 1189 (faithful geometry seed)
#   E1  stage and term gains of the one-step tangent (full / corner-box-only / outside-box-only inputs; conv_diff roles x (i,j) x region; BDIM terms)
#   E2  limiter audit: branch usage and kink distance of every interior `quick` call (value-only)
#   E3  (E3C: the same with the velocity direction projected onto the solenoidal subspace) one-step JVP against the central finite difference of F (eps scan, ||eps t||_inf = eps), branch flips, mismatch localisation; the E4 derivative variants
#   E5  multi-step: AD tangent growth (baseline and E4 variants) against the finite-amplitude growth of F (E5AD / E5FD)
#   E6  roundoff ensemble: +-1 ulp noise on the primal u, one-step tangent pattern and gain
#
# Nothing is clipped, reset or sanitised.  No Float64, no D1/D2/P1, no bridge, no FD-08 comparison, no delta, no GRAD-03 verdict, no flag change.
# usage: julia -t 1 --project=julia/CFDSDFWaterLily scripts/waterlily_grad_g2_diag5_one_step_gain_2026_10_09.jl \
#          <phi_raw> <phi_sha> <D0_raw> <D0_sha> <snapdir> <snapshot_index.json> <checksums.csv> <outdir> <state> <group>
#   state: S900 | S1000 | R1188 (E0 only);  group: E0 | E1 | E2 | E3 | E3C | E5AD | E5FD:<eps> | E6
# env (code-path dry run only): DIAG5_DRYRUN=1 (allows state S100 and DIAG5_K)

using WaterLily
using SHA
using Random
const FD = WaterLily.ForwardDiff
const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
for name in ("V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG, name))
end
using .CFDSDFWaterLily: V16MovingGroundBody, v16_native_far_field_uBC, NormalFloorWaterLilyBody, CandidateCWaterLilyBody
using .CFDSDFWaterLily.V16W4Sensitivity
Base.include(WaterLily, joinpath(@__DIR__, "waterlily_grad_g2_diag5_stages.jl"))

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)

# ---- registered configuration (fixed in the pre-run freeze) ---------------------------------------------------------------------------------------------
const DRYRUN = get(ENV, "DIAG5_DRYRUN", "0") == "1"
const K_STEPS = DRYRUN && haskey(ENV, "DIAG5_K") ? parse(Int, ENV["DIAG5_K"]) : 40
const EPS_E3 = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2)
const EPS_E5 = (1e-5, 1e-4, 1e-3, 1e-2)
const EPS_E5_VARIANT_B = (1e-4, 1e-3)               # the control without the p perturbation
const TIE_TAUS = (1f-5, 1f-4)
const ENSEMBLE_N = DRYRUN && haskey(ENV, "DIAG5_ENSEMBLE") ? parse(Int, ENV["DIAG5_ENSEMBLE"]) : 16
const BOXR = (1:12, 1:8, 49:56)                       # the corner box of DIAG1..4 (1-based)
const BOX4 = (BOXR..., :)
const INT4 = (2:151, 2:73, 2:55, :)                   # interior cells of the (152,74,56,3) flow arrays
const INT3 = (2:151, 2:73, 2:55)
const STATES = Dict("S900" => ("step0900", 900), "S1000" => ("step1000", 1000), "R1188" => ("ring_step1188", 1188), "S100" => ("step0100", 100))
const E0_NEXT = ("ring_step1189", 1189)
const E0_SCALE = 2.0^-117                             # exact power of two: the tangent at step 1188 (~1e35) is scaled into Float32 range together with the geometry seed
const FLIP_DILATIONS = (1, 2)
const KINK_BINS = (1e-6, 1e-5, 1e-4)

real_type(::Type{T}) where {T<:Real} = T
real_type(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V
function load_raw(path, sha)
    raw = read(path)
    bytes2hex(sha256(raw)) == sha || error("SHA mismatch: $path")
    length(raw) == prod(SHAPE) * 4 || error("byte length mismatch: $path")
    return reshape(copy(reinterpret(Float32, raw)), SHAPE)
end
function build(phi::AbstractArray{S,3}, ::Type{T}, case) where {S,T}
    FS = real_type(T)
    grid = GridSDF(phi, FS.(ORIGIN), FS.((SPACING, SPACING, SPACING)), SHAPE, FS(3), FS(0.15))
    floor_body = NormalFloorWaterLilyBody(grid, FS.(case.flow_origin_m), FS(case.flow_spacing_m), FS(0.25))
    ground = V16MovingGroundBody(FS(0), FS(1))
    combined = CandidateCWaterLilyBody(floor_body, ground; normal_floor=FS(0.25), transition_width=FS(TRANSITION))
    return WaterLily.Simulation(case.flow_dims, v16_native_far_field_uBC, FS(case.solver_length);
        U=FS(case.solver_velocity), ν=FS(case.solver_viscosity), exitBC=true, body=combined, T=T, mem=Array)
end

# ---- writers -------------------------------------------------------------------------------------------------------------------------------------------------------
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
function write_json(path, value)
    tmp = string(path, ".tmp")
    open(io -> write(io, json(value), "\n"), tmp, "w")
    mv(tmp, path; force=true)
end
csv_open(path, header) = (io = open(path, "w"); println(io, join(header, ",")); flush(io); io)
csv_row(io, cells) = (println(io, join((string(c) for c in cells), ",")); flush(io); nothing)

# ---- stored states --------------------------------------------------------------------------------------------------------------------------------------------
function raw_state(snapdir, indexpath, name)
    file = joinpath(snapdir, name * ".dual_f32_interleaved_value_tangent.raw")
    raw = read(file)
    index = read(indexpath, String)
    m = match(Regex("\"" * name * "\\.dual_f32_interleaved_value_tangent\\.raw\":\\{[^}]*?\"sha256\":\"([0-9a-f]{64})\""), index)
    m === nothing && error("no SHA entry for $name in the snapshot index")
    bytes2hex(sha256(raw)) == m.captures[1] || error("SHA mismatch for the stored state $name")
    return reinterpret(Float32, raw)
end
function split_state(raw, shape)
    v = reshape(raw[1:2:end], shape); t = reshape(raw[2:2:end], shape)
    return copy(v), copy(t)
end
function dt_row(csvpath, step)
    for l in eachline(csvpath)
        c = split(l, ',')
        c[1] == string(step) && return (reinterpret(Float64, parse(UInt64, c[6])), reinterpret(Float64, parse(UInt64, c[7])))
    end
    error("no checksum row for step $step")
end
struct Stored
    uv::Array{Float32,4}; ut::Array{Float32,4}; pv::Array{Float32,3}; pt::Array{Float32,3}; dtv::Float64; dtt::Float64; step::Int
end
function load_state(snapdir, indexpath, csvpath, prefix, step)
    uv, ut = split_state(raw_state(snapdir, indexpath, prefix * ".u"), (152, 74, 56, 3))
    pv, pt = split_state(raw_state(snapdir, indexpath, prefix * ".p"), (152, 74, 56))
    dtv, dtt = dt_row(csvpath, step)
    all(isfinite, uv) && all(isfinite, ut) && all(isfinite, pv) && all(isfinite, pt) && isfinite(dtv) && isfinite(dtt) || error("a stored state has non-finite entries: $prefix")
    return Stored(uv, ut, pv, pt, dtv, dtt, step)
end

# ---- statistics (read-only) ---------------------------------------------------------------------------------------------------------------------------------
fin(x) = isfinite(x) ? Float64(x) : NaN
function tstats(T::AbstractArray{<:Real,4})
    A = Float64.(T)
    I = view(A, INT4...); B = view(A, BOX4...)
    gmax = maximum(abs, A); bmax = maximum(abs, B)
    amax = argmax(abs.(A)); abox = argmax(abs.(B))
    return (gmax=gmax, imax=maximum(abs, I), bmax=bmax, l2sq_int=sum(abs2, I), l2sq_box=sum(abs2, B), argmax=join(Tuple(amax), ";"), argmax_box=join(Tuple(abox), ";"))
end
function tstats(T::AbstractArray{<:Real,3})
    A = Float64.(T)
    I = view(A, INT3...); B = view(A, BOXR...)
    amax = argmax(abs.(A))
    return (gmax=maximum(abs, A), imax=maximum(abs, I), bmax=maximum(abs, B), l2sq_int=sum(abs2, I), l2sq_box=sum(abs2, B), argmax=join(Tuple(amax), ";"), argmax_box="")
end
tangent_of(A) = FD.partials.(A, 1)
value_of(A) = FD.value.(A)
function value_checksum(A::AbstractArray{Float32})
    w = reinterpret(UInt32, vec(A))
    return (reduce(xor, w), sum(UInt64, w))
end
function relerr(a, b, region)            # relative L2 error, cosine, norm ratio of two fields over a region
    A = Float64.(view(a, region...)); B = Float64.(view(b, region...))
    nb = sqrt(sum(abs2, B)); na = sqrt(sum(abs2, A))
    return (rel=sqrt(sum(abs2, A .- B)) / max(nb, 1e-300), cos=sum(A .* B) / max(na * nb, 1e-300), ratio=na / max(nb, 1e-300), norm_a=na, norm_b=nb, max_a=maximum(abs, A), max_b=maximum(abs, B))
end

# ---- sims ---------------------------------------------------------------------------------------------------------------------------------------------------------
const TAGFN() = nothing
const TAG = FD.Tag(TAGFN, Float32)
const DT = FD.Dual{typeof(TAG),Float32,1}
mkdual(v, t) = DT.(v, FD.Partials.(tuple.(t)))
mutable struct Ctx
    phi::Array{Float32,3}; seed::Array{Float32,3}; case::Any
end
plain_sim(c::Ctx) = build(c.phi, Float32, c.case)
dual_sim(c::Ctx; seed_scale=0.0) = build(DT.(c.phi, FD.Partials.(tuple.(c.seed .* Float32(seed_scale)))), DT, c.case)
function set_plain!(sim, uv, pv)
    sim.flow.u .= uv; sim.flow.p .= pv
    empty!(sim.flow.Δt); push!(sim.flow.Δt, WaterLily.CFL(sim.flow))     # Δt[end] = CFL(u): the solver's own recurrence
    return sim
end
function set_dual!(sim, uv, ut, pv, pt)
    sim.flow.u .= mkdual(uv, ut); sim.flow.p .= mkdual(pv, pt)
    empty!(sim.flow.Δt); push!(sim.flow.Δt, WaterLily.CFL(sim.flow))
    return sim
end
function step_plain!(sim; λ=WaterLily.quick, hook=WaterLily.NullHook(), probe=WaterLily.NullProbe5())
    WaterLily.measure!(sim); WaterLily.diag5_mom_step!(sim.flow, sim.pois, λ, probe, hook)
end
const step_dual! = step_plain!                      # the same statements for both element types
# The finite-difference runs MUST use the same map as the AD runs.  A plain Float32 simulation is not that map: `quick`, `div`, `μddn` are @fastmath, which
# re-rounds plain Float32 arithmetic (1/6 as a reciprocal product, fused multiply-add) but falls back to ordinary operations for Dual numbers (44% of the limiter
# values and 1.2 of 1.9 million u values differ after one step).  So the "plain" side is a Dual simulation with zero tangents.
function fd_sim(c::Ctx, uv, pv)
    sim = dual_sim(c)
    return set_dual!(sim, uv, zero(uv), pv, zero(pv))
end
uval(sim) = value_of(sim.flow.u)
pval(sim) = value_of(sim.flow.p)

# ---- hooks / probes ----------------------------------------------------------------------------------------------------------------------------------------
mutable struct AuditHook                            # value-only branch ids of both conv_diff calls (plain sims)
    ids::Dict{Symbol,Array{UInt8,5}}; kds::Dict{Symbol,Array{Float32,5}}
end
AuditHook() = AuditHook(Dict{Symbol,Array{UInt8,5}}(), Dict{Symbol,Array{Float32,5}}())
function (h::AuditHook)(tag, a)
    if tag == :predict_conv
        h.ids[tag], h.kds[tag] = WaterLily.audit_quick(FD.value.(a.u⁰))
    elseif tag == :correct_conv
        h.ids[tag], h.kds[tag] = WaterLily.audit_quick(FD.value.(a.u))
    end
    nothing
end
mutable struct GainProbe
    rows::Vector{Any}; variant::String
end
function (g::GainProbe)(stage, fields; kwargs...)
    for (name, A) in pairs(fields)
        if A isa AbstractArray
            s = tstats(tangent_of(A))
            push!(g.rows, (g.variant, string(stage), string(name), s.gmax, s.imax, s.bmax, sqrt(s.l2sq_int), sqrt(s.l2sq_box), s.argmax, s.argmax_box))
        else                                                 # a scalar (the time step)
            t = abs(Float64(FD.partials(A, 1)))
            push!(g.rows, (g.variant, string(stage), string(name), t, 0.0, 0.0, 0.0, 0.0, "", ""))
        end
    end
end
mutable struct TermHook                             # conv_diff roles x (i,j) x region, and the BDIM terms (Dual sims)
    rows::Vector{Any}; variant::String; λ::Any
end
function zero_tangent(u)
    T = eltype(u)
    return T.(FD.value.(u), FD.Partials.(tuple.(zero.(FD.value.(u)))))
end
function (h::TermHook)(tag, a)
    if tag in (:predict_conv, :correct_conv)
        u = tag == :predict_conv ? a.u⁰ : a.u
        Dz = zero_tangent(u); r = similar(a.f); Φ = similar(a.σ); acc = zeros(Float64, size(u))
        total = similar(a.f); WaterLily.conv_diff5!(total, u, u, u, Φ, h.λ; ν=a.ν)
        for i in 1:3, j in 1:3, role in (:adv, :fld, :vis), region in (:interior, :boundary)
            adv, fld, vis = role == :adv ? (u, Dz, Dz) : role == :fld ? (Dz, u, Dz) : (Dz, Dz, u)
            WaterLily.conv_diff5!(r, adv, fld, vis, Φ, h.λ; ν=a.ν, region=region, pair=(i, j))
            tr = Float64.(tangent_of(r)[:, :, :, i]); acc[:, :, :, i] .+= tr
            push!(h.rows, (h.variant, string(tag), i, j, string(role), string(region), maximum(abs, view(tr, BOXR...)), sqrt(sum(abs2, view(tr, BOXR...))),
                           sqrt(sum(abs2, view(tr, INT3...))), maximum(abs, tr)))
        end
        tt = Float64.(tangent_of(total))
        push!(h.rows, (h.variant, string(tag), 0, 0, "closure", "all", maximum(abs, view(tt, BOX4...)), sqrt(sum(abs2, view(tt, BOX4...))), sqrt(sum(abs2, view(tt, INT4...))),
                       sqrt(sum(abs2, tt .- acc)) / max(sqrt(sum(abs2, tt)), 1e-300)))
    elseif tag in (:predict_bdim, :correct_bdim)
        dt = a.Δt[end]; dtv, dtt = FD.value(dt), FD.partials(dt, 1)
        terms = ("u0" => Float64.(tangent_of(a.u⁰)), "dt_df" => Float64(dtv) .* Float64.(tangent_of(a.f)), "ddt_f" => Float64(dtt) .* Float64.(value_of(a.f)),
                 "u_current" => Float64.(tangent_of(a.u)))
        for (name, T) in terms
            push!(h.rows, (h.variant, string(tag), 0, 0, name, "bdim", maximum(abs, view(T, BOX4...)), sqrt(sum(abs2, view(T, BOX4...))), sqrt(sum(abs2, view(T, INT4...))), maximum(abs, T)))
        end
    end
    nothing
end

# ---- the registered input direction ------------------------------------------------------------------------------------------------------------------------
# t = (delta u, delta p) / max|delta u| (interior, all components): ||t||_inf = 1.  The perturbation of F is  x +- eps t  (u incl. ghosts, p); Δt = CFL(u +- eps t).
function direction(s::Stored, ctx=nothing)
    m = maximum(abs, Float64.(view(s.ut, INT4...)))
    m > 0 || error("zero tangent")
    ctx === nothing && return Float32.(Float64.(s.ut) ./ m), Float32.(Float64.(s.pt) ./ m), m
    # variant C: the velocity part is projected onto the discrete solenoidal subspace with the solver's own operator (div, L = mu0, the face gradient), then renormalised;
    # the ghost cells keep their stored tangent (the projection only changes inside faces, like `mom_project!`).  p keeps the same scale factor.
    w = solenoidal(ctx, Float32.(Float64.(s.ut) ./ m))
    f = 1 / maximum(abs, Float64.(view(w, INT4...)))
    return Float32.(f .* Float64.(w)), Float32.(f .* Float64.(s.pt) ./ m), m / f
end
function solenoidal(ctx, w::Array{Float32,4}; tol=1e-7, itmx=200)
    sim = plain_sim(ctx); WaterLily.measure!(sim); b = sim.pois
    for I in WaterLily.inside(b.z)
        b.z[I] = WaterLily.div(I, w)
    end
    fill!(b.x, 0)
    WaterLily.solver!(b; tol=tol, itmx=itmx)
    out = copy(w)
    for i in 1:3, I in WaterLily.inside(b.x)
        out[I, i] -= b.L[I, i] * WaterLily.∂(i, I, b.x)
    end
    return out
end
function perturbed(s::Stored, tu, tp, eps; keep_p=false)
    f(x, t, sg) = Float32.(Float64.(x) .+ sg * eps .* Float64.(t))
    return (f(s.uv, tu, +1), keep_p ? copy(s.pv) : f(s.pv, tp, +1)), (f(s.uv, tu, -1), keep_p ? copy(s.pv) : f(s.pv, tp, -1))
end
function effective(plus, minus, eps)                   # the direction actually applied after rounding to Float32
    return Float32.((Float64.(plus[1]) .- Float64.(minus[1])) ./ (2eps)), Float32.((Float64.(plus[2]) .- Float64.(minus[2])) ./ (2eps))
end

function dt_closure(ctx, s::Stored)                  # the solver's own Δt[end] = CFL(u) against the stored time step (value and tangent)
    sim = dual_sim(ctx); set_dual!(sim, s.uv, s.ut, s.pv, s.pt)
    d = sim.flow.Δt[end]
    return Dict("stored_value" => s.dtv, "cfl_value" => Float64(FD.value(d)), "stored_tangent" => s.dtt, "cfl_tangent" => Float64(FD.partials(d, 1)))
end

# ---- group E0 ---------------------------------------------------------------------------------------------------------------------------------------------
function group_E0(ctx, snapdir, indexpath, csvpath, outdir)
    s = load_state(snapdir, indexpath, csvpath, STATES["R1188"][1], 1188)
    nxt = load_state(snapdir, indexpath, csvpath, E0_NEXT[1], 1189)
    sc = Float32(E0_SCALE)
    sim = dual_sim(ctx; seed_scale=E0_SCALE)                # the faithful geometry seed, scaled like the state tangent (exact power of two)
    set_dual!(sim, s.uv, s.ut .* sc, s.pv, s.pt .* sc)
    dtc = sim.flow.Δt[end]
    res = Dict{String,Any}("group" => "E0", "scale" => E0_SCALE,
        "dt_input" => Dict("stored_value" => s.dtv, "stored_tangent_scaled" => s.dtt * E0_SCALE, "cfl_value" => Float64(FD.value(dtc)), "cfl_tangent" => Float64(FD.partials(dtc, 1))))
    step_dual!(sim)
    uv, ut = value_of(sim.flow.u), tangent_of(sim.flow.u)
    pv = value_of(sim.flow.p)
    dtn = sim.flow.Δt[end]
    res["dt_output"] = Dict("stored_value" => nxt.dtv, "stored_tangent_scaled" => nxt.dtt * E0_SCALE, "cpu_value" => Float64(FD.value(dtn)), "cpu_tangent" => Float64(FD.partials(dtn, 1)))
    res["primal_u"] = relerr(uv, nxt.uv, INT4); res["primal_p"] = relerr(pv, nxt.pv, INT3)
    tin = s.ut .* sc; tst = nxt.ut .* sc
    res["tangent_box_vs_stored"] = relerr(ut, tst, BOX4); res["tangent_outside_box_vs_stored"] = begin
        m = trues(size(ut)); m[BOX4...] .= false
        A = Float64.(ut[m]); B = Float64.(tst[m]); Dict("rel" => sqrt(sum(abs2, A .- B)) / sqrt(sum(abs2, B)), "cos" => sum(A .* B) / sqrt(sum(abs2, A) * sum(abs2, B)))
    end
    res["gain_box_max"] = Dict("cpu" => maximum(abs, view(ut, BOX4...)) / maximum(abs, view(tin, BOX4...)), "stored_t4" => maximum(abs, view(tst, BOX4...)) / maximum(abs, view(tin, BOX4...)))
    res["ghost_closure"] = ghost_closure(ctx, s)
    return res
end
function ghost_closure(ctx, s::Stored)               # does BC! regenerate the stored ghost cells (value) from the interior?
    sim = fd_sim(ctx, s.uv, s.pv)
    u0 = uval(sim)
    WaterLily.BC!(sim.flow.u, sim.flow.uBC, sim.flow.exitBC, sim.flow.perdir, 0)
    u1 = uval(sim)
    changed = u1 .!= u0
    ghost = trues(size(u0)); ghost[INT4...] .= false
    return Dict("ghost_entries" => count(ghost), "ghost_entries_changed_by_BC" => count(changed .& ghost), "interior_entries_changed_by_BC" => count(changed .& .!ghost),
                "max_abs_change" => maximum(abs.(u1 .- u0)))
end

# ---- group E2 ---------------------------------------------------------------------------------------------------------------------------------------------
function group_E2(ctx, s::Stored)
    sim = fd_sim(ctx, s.uv, s.pv)
    hook = AuditHook(); step_plain!(sim; hook)
    out = Dict{String,Any}("group" => "E2")
    for tag in (:predict_conv, :correct_conv)
        ids, kds = hook.ids[tag], hook.kds[tag]
        box = (BOXR..., :, :)
        sections = Dict{String,Any}()
        for (name, region) in (("box", box), ("all", (:, :, :, :, :)))
            I = view(ids, region...); K = view(kds, region...)
            valid = I .!= 0
            n = count(valid)
            counts = [count(==(UInt8(k)), I) for k in 1:5]
            kv = Float64.(K[valid])
            q = n > 0 ? [quantile_sorted(sort(kv), p) for p in (0.1, 0.5, 0.9)] : Float64[]
            sections[name] = Dict("fluxes" => n, "branch_counts" => counts, "kink_distance_q10_q50_q90" => q,
                                  "fraction_below" => Dict(string(b) => count(<(b), kv) / max(n, 1) for b in KINK_BINS),
                                  "flip_prone_fraction" => Dict(string(e) => count(<(19e), kv) / max(n, 1) for e in EPS_E3))
        end
        out[string(tag)] = sections
    end
    return out
end
quantile_sorted(v, p) = v[max(1, min(length(v), ceil(Int, p * length(v))))]

# rms of the discrete divergence (the solver's own `div`) over the interior cells, relative to the rms of the field: how far a direction is from the solenoidal manifold
function div_rms(ctx, u::Array{Float32,4})
    sim = plain_sim(ctx)
    acc = 0.0; n = 0
    for I in WaterLily.inside(sim.flow.p)
        d = WaterLily.div(I, u); acc += Float64(d)^2; n += 1
    end
    return sqrt(acc / n) / (sqrt(sum(abs2, Float64.(view(u, INT4...))) / (length(view(u, INT4...)) / 3)) + 1e-300)
end

# ---- group E3 / E4 ---------------------------------------------------------------------------------------------------------------------------------------
function dilate(mask::BitArray{3}, d)
    out = copy(mask); sz = size(mask)
    for _ in 1:d
        src = copy(out)
        for s in CartesianIndices((-1:1, -1:1, -1:1))
            s == CartesianIndex(0, 0, 0) && continue
            for I in CartesianIndices(src)
                src[I] || continue
                J = I + s
                all(1 .<= Tuple(J) .<= sz) && (out[J] = true)
            end
        end
    end
    return out
end
function flip_cells(ids0, ids1, ids2)                # cells touched by a flux whose branch differs from the unperturbed one
    mask = falses(152, 74, 56)
    for ids in (ids1, ids2), j in 1:3, i in 1:3
        for I in CartesianIndices((152, 74, 56))
            ids[I, i, j] != ids0[I, i, j] || continue
            mask[I] = true
            J = I - CartesianIndex(ntuple(k -> k == j ? 1 : 0, 3)); all(1 .<= Tuple(J) .<= (152, 74, 56)) && (mask[J] = true)
        end
    end
    return mask
end
function lambdas()
    return (("quick", WaterLily.quick), ("tie1e-5", WaterLily.QuickTie(TIE_TAUS[1])), ("tie1e-4", WaterLily.QuickTie(TIE_TAUS[2])), ("linear", WaterLily.QuickLinear()))
end
function group_E3(ctx, s::Stored, outdir, proj::Bool)
    tu, tp, m = direction(s, proj ? ctx : nothing)
    res = Dict{String,Any}("group" => proj ? "E3C" : "E3", "solenoidal_direction" => proj, "direction_relative_divergence_rms" => div_rms(ctx, tu), "normalisation_max_abs_delta_u" => m, "eps" => collect(EPS_E3), "rows" => Any[],
                           "relative_divergence_rms" => Dict("primal_u" => div_rms(ctx, s.uv), "tangent_direction_stored" => div_rms(ctx, Float32.(Float64.(s.ut) ./ m))))
    io = csv_open(joinpath(outdir, proj ? "e3c_rows.csv" : "e3_rows.csv"), ["eps", "lambda", "region", "rel", "cos", "ratio", "norm_jvp", "norm_fd", "max_jvp", "max_fd", "flip_rate_box_predict", "flip_rate_box_correct",
                                                    "flip_rate_all_predict", "flip_rate_all_correct", "mismatch_share_in_flip_cells_d1", "mismatch_share_in_flip_cells_d2", "flip_cell_fraction_d1", "flip_cell_fraction_d2",
                                                    "gain_jvp_box_max", "gain_fd_box_max"])
    sim0 = fd_sim(ctx, s.uv, s.pv); h0 = AuditHook(); step_plain!(sim0; hook=h0)
    for eps in EPS_E3
        plus, minus = perturbed(s, tu, tp, eps)
        te_u, te_p = effective(plus, minus, eps)
        outs = Any[]
        hooks = AuditHook[]
        for (uv, pv) in (plus, minus)
            sim = fd_sim(ctx, uv, pv); h = AuditHook(); step_plain!(sim; hook=h)
            push!(outs, (Float64.(uval(sim)), Float64.(pval(sim)))); push!(hooks, h)
        end
        Du = Float32.((outs[1][1] .- outs[2][1]) ./ (2eps)); Dp = Float32.((outs[1][2] .- outs[2][2]) ./ (2eps))
        flip = Dict{String,Any}()
        for tag in (:predict_conv, :correct_conv)
            f1 = hooks[1].ids[tag] .!= h0.ids[tag]; f2 = hooks[2].ids[tag] .!= h0.ids[tag]
            fb = (f1 .| f2)[BOXR..., :, :]; valid_b = h0.ids[tag][BOXR..., :, :] .!= 0
            fa = (f1 .| f2); valid_a = h0.ids[tag] .!= 0
            flip["box_$tag"] = count(fb .& valid_b) / max(count(valid_b), 1); flip["all_$tag"] = count(fa .& valid_a) / max(count(valid_a), 1)
        end
        cells = flip_cells(h0.ids[:predict_conv], hooks[1].ids[:predict_conv], hooks[2].ids[:predict_conv])
        cells2 = flip_cells(h0.ids[:correct_conv], hooks[1].ids[:correct_conv], hooks[2].ids[:correct_conv])
        base = BitArray(cells .| cells2)
        masks = Dict(d => dilate(base, d) for d in FLIP_DILATIONS)
        for (lname, λ) in lambdas()
            sim = dual_sim(ctx); set_dual!(sim, s.uv, te_u, s.pv, te_p)
            step_dual!(sim; λ=λ)
            tu_out = tangent_of(sim.flow.u)
            for (rname, region) in (("box", BOX4), ("interior", INT4))
                r = relerr(tu_out, Du, region)
                mis = Float64.(tu_out) .- Float64.(Du)
                shares = Float64[]; frac = Float64[]
                for d in FLIP_DILATIONS
                    mk = masks[d]
                    msq = rname == "box" ? [sum(abs2, mis[BOXR..., c][mk[BOXR...]]) for c in 1:3] : [sum(abs2, mis[INT3..., c][mk[INT3...]]) for c in 1:3]
                    tot = rname == "box" ? sum(abs2, view(mis, BOX4...)) : sum(abs2, view(mis, INT4...))
                    push!(shares, sum(msq) / max(tot, 1e-300))
                    push!(frac, rname == "box" ? count(mk[BOXR...]) / prod(length.(BOXR)) : count(mk[INT3...]) / prod(length.(INT3)))
                end
                gj = maximum(abs, view(tu_out, BOX4...)) / maximum(abs, view(te_u, BOX4...)); gf = maximum(abs, view(Du, BOX4...)) / maximum(abs, view(te_u, BOX4...))
                row = (eps, lname, rname, r.rel, r.cos, r.ratio, r.norm_a, r.norm_b, r.max_a, r.max_b, flip["box_predict_conv"], flip["box_correct_conv"], flip["all_predict_conv"], flip["all_correct_conv"],
                       shares[1], shares[2], frac[1], frac[2], gj, gf)
                csv_row(io, row); push!(res["rows"], row)
            end
            res["primal_bits_$(eps)_$(lname)"] = value_checksum(value_of(sim.flow.u))                # the surrogate derivative must not change the primal
        end
        # the pressure part of the same comparison (baseline derivative only)
        simp = dual_sim(ctx); set_dual!(simp, s.uv, te_u, s.pv, te_p); step_dual!(simp)
        res["p_rel_$(eps)"] = relerr(tangent_of(simp.flow.p), Dp, INT3).rel
    end
    close(io)
    return res
end

# ---- group E1 ---------------------------------------------------------------------------------------------------------------------------------------------
function group_E1(ctx, s::Stored, outdir)
    tu, tp, m = direction(s)
    mask = falses(152, 74, 56, 3); mask[BOX4...] .= true
    variants = (("full", ones(Float32, size(tu)), ones(Float32, size(tp))), ("box_only", Float32.(mask), Float32.(mask[:, :, :, 1])), ("outside_only", Float32.(.!mask), Float32.(.!mask[:, :, :, 1])))
    probe_rows = Any[]; term_rows = Any[]
    for (vname, mu, mp) in variants
        for (lname, λ) in (("quick", WaterLily.quick), ("tie1e-5", WaterLily.QuickTie(TIE_TAUS[1])))
            vname == "full" || lname == "quick" || continue
            sim = dual_sim(ctx); set_dual!(sim, s.uv, tu .* mu, s.pv, tp .* mp)
            probe = GainProbe(Any[], vname * "/" * lname); th = TermHook(Any[], vname * "/" * lname, λ)
            din = sim.flow.Δt[end]
            push!(probe.rows, (probe.variant, "input", "u", maximum(abs, tu .* mu), maximum(abs, view(tu .* mu, INT4...)), maximum(abs, view(tu .* mu, BOX4...)), sqrt(sum(abs2, Float64.(view(tu .* mu, INT4...)))),
                               sqrt(sum(abs2, Float64.(view(tu .* mu, BOX4...)))), "", ""))
            push!(probe.rows, (probe.variant, "input", "dt", Float64(abs(FD.partials(din, 1))), 0.0, 0.0, 0.0, 0.0, "", ""))
            step_dual!(sim; λ=λ, probe=probe, hook=th)
            append!(probe_rows, probe.rows); append!(term_rows, th.rows)
        end
    end
    io = csv_open(joinpath(outdir, "e1_stages.csv"), ["variant", "stage", "field", "max_all", "max_interior", "max_box", "l2_interior", "l2_box", "argmax", "argmax_box"])
    foreach(r -> csv_row(io, r), probe_rows); close(io)
    io = csv_open(joinpath(outdir, "e1_terms.csv"), ["variant", "call", "i", "j", "role", "region", "max_box", "l2_box", "l2_interior", "max_all_or_closure"])
    foreach(r -> csv_row(io, r), term_rows); close(io)
    return Dict{String,Any}("group" => "E1", "normalisation_max_abs_delta_u" => m, "stage_rows" => length(probe_rows), "term_rows" => length(term_rows))
end

# ---- group E5 ---------------------------------------------------------------------------------------------------------------------------------------------
const E5_HEADER = ["variant", "eps", "step", "gmax", "imax", "bmax", "l2_int", "l2_box", "argmax", "argmax_box", "u_xor", "u_sum"]
function e5_row(variant, eps, k, T, uv)
    s = tstats(T); cs = value_checksum(uv)
    return (variant, eps, k, s.gmax, s.imax, s.bmax, sqrt(s.l2sq_int), sqrt(s.l2sq_box), s.argmax, s.argmax_box, cs[1], cs[2])
end
function group_E5AD(ctx, s::Stored, outdir)
    tu, tp, m = direction(s)
    io = csv_open(joinpath(outdir, "e5ad_rows.csv"), E5_HEADER)
    res = Dict{String,Any}("group" => "E5AD", "normalisation_max_abs_delta_u" => m, "steps" => K_STEPS)
    # gate: the instrumented step with the original limiter equals `sim_step!` bit for bit (values and tangents) over the first steps
    ga = dual_sim(ctx); set_dual!(ga, s.uv, tu, s.pv, tp); gb = dual_sim(ctx); set_dual!(gb, s.uv, tu, s.pv, tp)
    ident = true
    for _ in 1:min(3, K_STEPS)
        WaterLily.sim_step!(ga); step_dual!(gb)
        ident &= reinterpret(UInt32, vec(ga.flow.u)) == reinterpret(UInt32, vec(gb.flow.u)) && reinterpret(UInt32, vec(ga.flow.p)) == reinterpret(UInt32, vec(gb.flow.p))
    end
    res["instrumented_step_bit_identical_to_sim_step"] = ident
    tuc, tpc, _ = direction(s, ctx)
    for (vname, lname, λ, du, dp) in (("AD", "quick", WaterLily.quick, tu, tp), ("AD", "tie1e-5", WaterLily.QuickTie(TIE_TAUS[1]), tu, tp), ("AD", "tie1e-4", WaterLily.QuickTie(TIE_TAUS[2]), tu, tp),
                                      ("AD", "linear", WaterLily.QuickLinear(), tu, tp), ("ADC", "quick", WaterLily.quick, tuc, tpc))
        sim = dual_sim(ctx); set_dual!(sim, s.uv, du, s.pv, dp)
        csv_row(io, e5_row(vname * "/" * lname, 0.0, 0, tangent_of(sim.flow.u), value_of(sim.flow.u)))
        for k in 1:K_STEPS
            step_dual!(sim; λ=λ)
            csv_row(io, e5_row(vname * "/" * lname, 0.0, k, tangent_of(sim.flow.u), value_of(sim.flow.u)))
        end
    end
    close(io)
    return res
end
function group_E5FD(ctx, s::Stored, outdir, eps)
    tu, tp, m = direction(s)
    io = csv_open(joinpath(outdir, "e5fd_rows.csv"), E5_HEADER)
    res = Dict{String,Any}("group" => "E5FD", "eps" => eps, "normalisation_max_abs_delta_u" => m, "steps" => K_STEPS, "variants" => Any[])
    tuc, tpc, _ = direction(s, ctx)
    for (vname, keep_p) in (("A", false), ("B", true), ("C", false))
        vname != "A" && !(eps in EPS_E5_VARIANT_B) && continue
        plus, minus = vname == "C" ? perturbed(s, tuc, tpc, eps; keep_p) : perturbed(s, tu, tp, eps; keep_p)
        sa = fd_sim(ctx, plus[1], plus[2]); sb = fd_sim(ctx, minus[1], minus[2])
        D(k) = Float32.((Float64.(uval(sa)) .- Float64.(uval(sb))) ./ (2eps))
        csv_row(io, e5_row("FD/" * vname, eps, 0, D(0), uval(sa)))
        for k in 1:K_STEPS
            step_plain!(sa); step_plain!(sb)
            csv_row(io, e5_row("FD/" * vname, eps, k, D(k), uval(sa)))
        end
        push!(res["variants"], vname)
    end
    close(io)
    return res
end

# ---- group E6 ---------------------------------------------------------------------------------------------------------------------------------------------
function noisy(uv, seed)
    rng = MersenneTwister(seed); out = copy(uv)
    for i in eachindex(out)
        out[i] = rand(rng, Bool) ? nextfloat(out[i]) : prevfloat(out[i])
    end
    return out
end
function group_E6(ctx, s::Stored, outdir)
    tu, tp, m = direction(s)
    io = csv_open(joinpath(outdir, "e6_rows.csv"), ["kind", "seed", "gain_box_max", "pattern_rel_change_box", "primal_rel_l2_change", "fd_rel_change_box"])
    function onestep(uv)
        sim = dual_sim(ctx); set_dual!(sim, uv, tu, s.pv, tp); step_dual!(sim)
        return Float64.(value_of(sim.flow.u)), Float64.(tangent_of(sim.flow.u))
    end
    v0, t0 = onestep(s.uv)
    gain(t) = maximum(abs, view(t, BOX4...)) / maximum(abs, view(tu, BOX4...))
    eps = 1e-3
    fd(uv) = begin
        plus = (Float32.(Float64.(uv) .+ eps .* Float64.(tu)), Float32.(Float64.(s.pv) .+ eps .* Float64.(tp)))
        minus = (Float32.(Float64.(uv) .- eps .* Float64.(tu)), Float32.(Float64.(s.pv) .- eps .* Float64.(tp)))
        o = map(x -> (sm = fd_sim(ctx, x[1], x[2]); step_plain!(sm); Float64.(uval(sm))), (plus, minus))
        (o[1] .- o[2]) ./ (2eps)
    end
    fd0 = fd(s.uv)
    csv_row(io, ("baseline", 0, gain(t0), 0.0, 0.0, 0.0))
    res = Dict{String,Any}("group" => "E6", "n" => ENSEMBLE_N, "gain_baseline" => gain(t0), "gains" => Float64[], "pattern_changes" => Float64[], "fd_changes" => Float64[])
    for seed in 1:ENSEMBLE_N
        uvn = noisy(s.uv, seed)
        vn, tn = onestep(uvn)
        pc = sqrt(sum(abs2, view(tn, BOX4...) .- view(t0, BOX4...))) / sqrt(sum(abs2, view(t0, BOX4...)))
        pr = sqrt(sum(abs2, view(vn, INT4...) .- view(v0, INT4...))) / sqrt(sum(abs2, view(v0, INT4...)))
        fdn = fd(uvn)
        fc = sqrt(sum(abs2, view(fdn, BOX4...) .- view(fd0, BOX4...))) / sqrt(sum(abs2, view(fd0, BOX4...)))
        csv_row(io, ("ulp", seed, gain(tn), pc, pr, fc))
        push!(res["gains"], gain(tn)); push!(res["pattern_changes"], pc); push!(res["fd_changes"], fc)
    end
    close(io)
    return res
end

# ---- main ---------------------------------------------------------------------------------------------------------------------------------------------------------
function main()
    length(ARGS) == 10 || error("usage: <phi_raw> <phi_sha> <D0_raw> <D0_sha> <snapdir> <snapshot_index.json> <checksums.csv> <outdir> <state> <group>")
    phi_path, phi_sha, d0_path, d0_sha, snapdir, indexpath, csvpath, outdir, state, group = ARGS
    state in keys(STATES) || error("unknown state $state")
    state == "S100" && !DRYRUN && error("state S100 is a dry-run state")
    (group == "E0") == (state == "R1188") || error("E0 uses state R1188 and only E0 uses it")
    mkpath(outdir)
    isfile(joinpath(outdir, "result.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2-DIAG5", "state" => state, "group" => group, "dryrun" => DRYRUN, "k_steps" => K_STEPS, "julia" => string(VERSION), "threads" => Threads.nthreads(),
        "waterlily" => string(pkgversion(WaterLily)), "forwarddiff" => string(pkgversion(FD)),
        "waterlily_flow_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Flow.jl")))),
        "waterlily_multilevelpoisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "MultiLevelPoisson.jl")))),
        "waterlily_poisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Poisson.jl")))),
        "evidence_class" => "cpu_reevaluation_of_stored_t4_states_unregistered_diagnostic",
        "claim_limit" => "diagnostic: one-step map of stored T4 states re-evaluated on CPU; no bridge value, no FD-08 comparison, no gradient qualification",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")), "status" => "RUNNING")
    write_json(joinpath(outdir, "status.json"), index)
    code = 0
    try
        phi32 = load_raw(phi_path, phi_sha)
        d32 = load_raw(d0_path, d0_sha); maximum(abs, d32) == 1.0f0 || error("D0: direction max-norm != 1")
        case = only(c for c in w4_cases(ORIGIN, SPACING) if c.case_id == "flow_24")
        validate_w4_case(case; canonical_design_origin_m=ORIGIN, canonical_design_spacing_m=SPACING)
        ctx = Ctx(phi32, d32, case)
        started = time()
        local result
        if group == "E0"
            result = group_E0(ctx, snapdir, indexpath, csvpath, outdir)
        else
            prefix, step = STATES[state]
            s = load_state(snapdir, indexpath, csvpath, prefix, step)
            result = group == "E1" ? group_E1(ctx, s, outdir) : group == "E2" ? group_E2(ctx, s) : group == "E3" ? group_E3(ctx, s, outdir, false) : group == "E3C" ? group_E3(ctx, s, outdir, true) :
                     group == "E5AD" ? group_E5AD(ctx, s, outdir) : group == "E6" ? group_E6(ctx, s, outdir) :
                     startswith(group, "E5FD:") ? group_E5FD(ctx, s, outdir, parse(Float64, group[6:end])) : error("unknown group $group")
            startswith(group, "E5FD:") && !(parse(Float64, group[6:end]) in EPS_E5) && !DRYRUN && error("eps outside the registered list")
        end
        group == "E0" || (result["dt_closure"] = dt_closure(ctx, load_state(snapdir, indexpath, csvpath, STATES[state][1], STATES[state][2])))
        result["seconds"] = time() - started
        index["status"] = "COMPLETE"; index["result_written"] = true
        write_json(joinpath(outdir, "result.json"), result)
    catch err
        index["status"] = "ERROR"; index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        code = 2
    end
    write_json(joinpath(outdir, "status.json"), index)
    println("DIAG5_RESULT ", index["status"], " ", state, " ", group)
    code == 0 || exit(code)
end

main()
