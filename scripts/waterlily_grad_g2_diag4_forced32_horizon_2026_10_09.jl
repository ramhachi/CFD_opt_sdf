# G2-DIAG4: does the forced-32 Poisson variant eliminate the D0 corner tangent mode over a longer horizon, or only delay its onset?
#
# Three independent simulations stepped in lock-step in one process (D0, canonical v17, Candidate C, flow_24, Float32, Dual width 1):
#   B0         original G2 semantics (plain `sim_step!`), step 0 -> 1500 (stops only if its PRIMAL goes non-finite; a non-finite tangent
#              does not stop it: the primal does not depend on the tangent, and the primal is needed for the comparisons)
#   B32fork    PRIMARY. At step 780 an exact clone of B0 (u, p, dt vector copied bit for bit into a fresh simulation), then the DIAG2/DIAG3
#              forced-32 Poisson semantics (`solver!(b; tol=0, itmx=32)`) for steps 781 -> 1500. Stops at its own first non-finite value.
#   B32fresh   SECONDARY (history-dependence diagnostic only): forced-32 from step 0 -> 1500, independent simulation. Never used for the primary verdict.
# Mandatory regression gates (the run stops and is DIAG4_INCOMPLETE on any mismatch):
#   B0 steps 1..980 equal the DIAG3 straight replay bit for bit; B32fork steps 781..980 equal the DIAG3 F32 arm (= DIAG2 V1c) bit for bit.
# The classification (NO_ONSET_OBSERVED / DELAYED_ONSET / DIFFERENT_MODE) is made ONLY by scripts/analyze_grad_g2_diag4.py from the saved histories.
# Nothing is clipped, reset or sanitised.  No Float64, no D1/D2/P1, no bridge, no FD-08 comparison, no delta.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_g2_diag4_forced32_horizon_2026_10_09.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>
# env (cpu code-path dry run only): DIAG4_BACKEND=cpu, DIAG4_FORK_STEP, DIAG4_END_STEP, DIAG4_REF_STRAIGHT, DIAG4_REF_F32 (reference CSVs), DIAG4_NO_REF, DIAG4_RAISE_STEP

using WaterLily
using SHA
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "DIAG4_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("DIAG4_BACKEND must be cuda or cpu")
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
using LinearAlgebra: norm

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)

# ---- configuration (fixed in the pre-run freeze) ---------------------------------------------------------------------------
const DRYRUN = BACKEND == "cpu"
(!DRYRUN && any(haskey(ENV, k) for k in ("DIAG4_FORK_STEP", "DIAG4_END_STEP", "DIAG4_REF_STRAIGHT", "DIAG4_REF_F32", "DIAG4_NO_REF", "DIAG4_RAISE_STEP"))) &&
    error("DIAG4 dry-run switches are only allowed with DIAG4_BACKEND=cpu")
const FORK_STEP = DRYRUN && haskey(ENV, "DIAG4_FORK_STEP") ? parse(Int, ENV["DIAG4_FORK_STEP"]) : 780
const END_STEP = DRYRUN && haskey(ENV, "DIAG4_END_STEP") ? parse(Int, ENV["DIAG4_END_STEP"]) : 1500
const FORCED_ITERATIONS = 32
const REF_LAST_STEP = 980                 # the DIAG3 straight replay and F32 arm cover steps up to 980
const DEVICE_N = (152, 74, 56)
const SNAPSHOT_STEPS = (1000, 1250, 1500)
const NO_REF = DRYRUN && haskey(ENV, "DIAG4_NO_REF")
const REF_STRAIGHT = DRYRUN && haskey(ENV, "DIAG4_REF_STRAIGHT") ? ENV["DIAG4_REF_STRAIGHT"] :
    joinpath(ROOT, "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output/straight_checksums.csv")
const REF_F32 = DRYRUN && haskey(ENV, "DIAG4_REF_F32") ? ENV["DIAG4_REF_F32"] :
    joinpath(ROOT, "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output/arm_F32_forced_dual_32.steps.csv")
const RAISE_STEP = DRYRUN && haskey(ENV, "DIAG4_RAISE_STEP") ? parse(Int, ENV["DIAG4_RAISE_STEP"]) : nothing

to_device(a) = BACKEND == "cuda" ? Base.invokelatest(getfield(Main, :CuArray), a) : a
sync() = BACKEND == "cuda" ? Base.invokelatest(CUDA.synchronize) : nothing
used_memory() = BACKEND == "cuda" ? Base.invokelatest(CUDA.used_memory) : 0

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


# ---- statistics (read-only) --------------------------------------------------------------------------------------------------------------
absp(x) = (v = Float64(FD.value(x)); isfinite(v) ? abs(v) : 0.0)
abst(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? abs(v) : 0.0)
sqt(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? v * v : 0.0)
badp(x) = !isfinite(FD.value(x))
badt(x) = !isfinite(FD.partials(x, 1))
struct TanOf end
(::TanOf)(x) = FD.partials(x, 1)
struct IncFn end                       # tangent minus the reference tangent (value type), element-wise
(::IncFn)(x, r) = FD.partials(x, 1) - r
struct Sq64 end
(::Sq64)(x) = (v = Float64(x); isfinite(v) ? v * v : 0.0)
struct Abs64 end
(::Abs64)(x) = (v = Float64(x); isfinite(v) ? abs(v) : 0.0)
struct ToReal{R,F}
    f::F
end
ToReal{R}(f::F) where {R,F} = ToReal{R,F}(f)
(t::ToReal{R})(x) where {R} = R(t.f(x))
valtype_of(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V
function locate(f, A)                  # first index of the maximum of f over A (device-side map, then findfirst)
    buf = map(ToReal{Float32}(f), A)
    m = maximum(buf)
    I = findfirst(==(m), buf)
    return I isa CartesianIndex ? I : CartesianIndices(A)[I]
end
idxstr(I) = I === nothing ? "" : join(Tuple(I), ";")
const BOX = (1:12, 1:8, 49:DEVICE_N[3], :)          # the corner box of DIAG1..3 (1-based)
in_box(I) = I !== nothing && Tuple(I)[1] in BOX[1] && Tuple(I)[2] in BOX[2] && Tuple(I)[3] in BOX[3]

function checksum(A::Array)
    sizeof(eltype(A)) == 8 || error("expected an 8-byte Dual{Float32,1}")
    w = reinterpret(UInt32, vec(A))
    return (reduce(xor, w), sum(UInt64, w))
end
function value_checksum(A::Array)
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
const ARM_HEADER = ["step", "t_u_l", "glob_max_tangent_u", "box_max_tangent_u", "glob_energy_tangent", "box_energy_tangent", "argmax_tangent_u", "glob_max_primal_u",
    "nonfinite_primal_u", "nonfinite_tangent_u", "inc_max", "inc_energy_glob", "inc_energy_box", "inc_argmax", "iters1", "iters2", "res_primal_last", "res_tangent_last",
    "fx", "fx_tan", "fz", "fz_tan", CS_HEADER..., VCS_HEADER...]
const CMP_HEADER = ["step", "rel_l2_u", "rel_l2_p", "max_abs_du", "argmax_du", "max_abs_dp", "argmax_dp", "box_rel_l2_u", "box_max_abs_du", "box_max_abs_dp",
    "drag_rel_diff", "downforce_rel_diff"]

struct NullProbe end
(::NullProbe)(stage::Symbol, fields::NamedTuple; iters=nothing, r2=nothing) = nothing

mutable struct Arm
    name::String
    kind::Symbol                 # :plain | :forced
    sim::Any
    bodies::Any
    owner::Any
    phi_dev::Any
    hook::Any
    io::IO
    alive::Bool
    tangent_valid::Bool
    first_nonfinite::Any
    ref::Any                     # tangent of u at the registered reference step (device array of the value type)
    cs::Dict{Int,Any}
    last_record::Any
    last_forces::Any
    snapshotted::Bool
    start_step::Int
end

function new_arm(name, kind, phi_host, ::Type{T}, case, outdir) where {T}
    phi_dev = to_device(copy(phi_host))                      # a private device copy of the geometry for every simulation
    sim, bodies, owner = build(phi_dev, T, case)
    BACKEND == "cuda" && size(sim.flow.u) != (DEVICE_N..., 3) && error("flow array extent $(size(sim.flow.u)) != the registered $(DEVICE_N)")
    io = csv_open(joinpath(outdir, "arm_$(name).steps.csv"), ARM_HEADER)
    hook = kind === :forced ? WaterLily.ForcedSolve(FORCED_ITERATIONS, NTuple{7,Float64}[]) : nothing
    return Arm(name, kind, sim, bodies, owner, phi_dev, hook, io, true, true, nothing, nothing, Dict{Int,Any}(), nothing, nothing, false, 0)
end

function step_arm!(a::Arm)
    if a.kind === :plain
        WaterLily.sim_step!(a.sim)                           # the original semantics
    else
        empty!(a.hook.stats)
        WaterLily.measure!(a.sim)                            # sim_step!(sim; remeasure=true): measure!(sim) then mom_step!
        WaterLily.diag3_mom_step!(a.sim.flow, a.sim.pois, NullProbe(), a.hook)
    end
    return nothing
end

function force_values(sim, bodies)      # candidate total force (same expressions as G2's sample_row), never throws on non-finite
    pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))
    viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
    total = pressure + viscous
    fx, fxt = vp(total[1]); fz, fzt = vp(total[3])
    return (fx, fxt, fz, fzt)
end

function arm_metrics!(a::Arm, step, ref_step)
    u = a.sim.flow.u
    r = step_record(a.sim); a.last_record = r; a.cs[step] = r.cs
    nfp, nft = count(badp, u), count(badt, u)
    gt, bt = maximum(abst, u), maximum(abst, view(u, BOX...))
    ge, be = sum(sqt, u), sum(sqt, view(u, BOX...))
    amax = locate(abst, u)
    gp = maximum(absp, u)
    if step == ref_step
        a.ref = map(TanOf(), u)
    end
    incmax = incg = incb = NaN; incarg = nothing
    if a.ref !== nothing && nft == 0
        inc = map(IncFn(), u, a.ref)
        incg, incb = sum(Sq64(), inc), sum(Sq64(), view(inc, BOX...))
        incmax = maximum(Abs64(), inc)
        incarg = locate(Abs64(), inc)
    end
    n = a.sim.pois.n
    q = a.sim.pois.levels[1].r
    fx, fxt, fz, fzt = force_values(a.sim, a.bodies)
    a.last_forces = (fx, fxt, fz, fzt)
    row = Any[step, vp(WaterLily.sim_time(a.sim))[1], gt, bt, ge, be, idxstr(amax), gp, nfp, nft, incmax, incg, incb, idxstr(incarg),
        length(n) >= 2 ? Int(n[end - 1]) : -1, length(n) >= 1 ? Int(n[end]) : -1, maximum(absp, q), maximum(abst, q), fx, fxt, fz, fzt]
    append!(row, r.cs); append!(row, r.vcs)
    csv_row(a.io, row); flush(a.io)
    nft > 0 && a.tangent_valid && (a.tangent_valid = false; a.first_nonfinite = ("tangent", step))
    if nfp > 0
        a.alive = false; a.first_nonfinite === nothing && (a.first_nonfinite = ("primal", step))   # keep the earlier tangent event; the CSV has both
    elseif a.kind === :forced && nft > 0
        a.alive = false                                       # the forced arms are stopped at their own first non-finite value (an onset / blow-up event)
    end
    return r
end

function compare!(io, step, ra, rb, fa, fb)   # ra, rb: step records (host); fa, fb: (fx, fxt, fz, fzt)
    va, vb = FD.value.(ra.u), FD.value.(rb.u)
    pa, pb = FD.value.(ra.p), FD.value.(rb.p)
    du, dp = va .- vb, pa .- pb
    box_du = view(du, BOX...)
    iu, ip = argmax(abs.(du)), argmax(abs.(dp))
    row = (step, norm(du) / max(norm(vb), 1e-300), norm(dp) / max(norm(pb), 1e-300), maximum(abs, du), idxstr(CartesianIndices(du)[iu]), maximum(abs, dp),
        idxstr(CartesianIndices(dp)[ip]), norm(box_du) / max(norm(view(vb, BOX...)), 1e-300), maximum(abs, box_du), maximum(abs, view(dp, BOX[1], BOX[2], BOX[3])),
        (fa[1] - fb[1]) / max(abs(fb[1]), 1e-300), (fa[3] - fb[3]) / max(abs(fb[3]), 1e-300))
    csv_row(io, row); flush(io)
    return nothing
end

function load_reference(path)           # step => the six full-bit checksum columns as strings
    lines = readlines(path); head = split(lines[1], ",")
    idx = [findfirst(==(c), head) for c in ("step", CS_HEADER...)]
    any(isnothing, idx) && error("reference $path lacks the checksum columns")
    return Dict(parse(Int, split(l, ",")[idx[1]]) => Tuple(split(l, ",")[i] for i in idx[2:end]) for l in lines[2:end])
end
cs_strings(cs) = Tuple(string(x) for x in cs)

function buffers(a::Arm)                # device/host buffers that must never be shared between simulations
    f, p = a.sim.flow, a.sim.pois
    arrs = Any[f.u, f.u⁰, f.f, f.p, f.σ, f.V, f.μ₀, f.μ₁, a.phi_dev]
    for lev in p.levels
        append!(arrs, (lev.x, lev.L, lev.z, lev.r, lev.ϵ, lev.D, lev.iD))
    end
    return arrs
end
function assert_independent(arms...)      # no mutable buffer (or device allocation) may be shared between two simulations
    bufs = [(a.name, b) for a in arms for b in buffers(a)]
    for i in eachindex(bufs), j in i + 1:length(bufs)
        bufs[i][1] != bufs[j][1] && Base.mightalias(bufs[i][2], bufs[j][2]) && error("a buffer is shared between simulations $(bufs[i][1]) and $(bufs[j][1])")
    end
    return true
end

function write_snapshot!(index, outdir, step, tag, arrays)
    dir = joinpath(outdir, "snapshots"); mkpath(dir)
    for (name, A) in arrays
        file = "$(tag).$(name).dual_f32_interleaved_value_tangent.raw"
        open(io -> write(io, GC.@preserve(A, unsafe_wrap(Array, Ptr{UInt8}(pointer(A)), length(A) * sizeof(eltype(A))))), joinpath(dir, file), "w")
        index[file] = Dict("step" => step, "field" => name, "shape" => collect(size(A)), "sha256" => sha_hex(A), "bytes" => length(A) * sizeof(eltype(A)))
    end
    write_json(joinpath(outdir, "snapshot_index.json"), index)
    return nothing
end

# ---- the run ------------------------------------------------------------------------------------------------------------------------------
function run_all(phi_dual, ::Type{DT}, case, outdir, index) where {DT}
    straight_ref = NO_REF ? nothing : load_reference(REF_STRAIGHT)
    f32_ref = NO_REF ? nothing : load_reference(REF_F32)
    b0 = new_arm("B0", :plain, phi_dual, DT, case, outdir)
    fresh = new_arm("B32fresh", :forced, phi_dual, DT, case, outdir)
    fork = nothing
    cmp_fork = csv_open(joinpath(outdir, "cmp_B32fork_vs_B0.csv"), CMP_HEADER)
    cmp_fresh = csv_open(joinpath(outdir, "cmp_B32fresh_vs_B0.csv"), CMP_HEADER)
    cmp_ff = csv_open(joinpath(outdir, "cmp_B32fresh_vs_B32fork.csv"), CMP_HEADER)
    snap_index = Dict{String,Any}()
    gate = Dict{String,Any}("b0_vs_diag3_straight_checked_steps" => 0, "fork_vs_diag3_f32_checked_steps" => 0, "failure" => nothing)
    started = time()
    GC.@preserve b0 fresh begin
        try
            for step in 1:END_STEP
                RAISE_STEP !== nothing && step == RAISE_STEP && error("DIAG4 deliberate dry-run exception at step $step")
                b0.alive && step_arm!(b0)
                fresh.alive && step_arm!(fresh)
                fork !== nothing && fork.alive && step_arm!(fork)
                arms = Arm[b0, fresh]
                fork !== nothing && push!(arms, fork)
                recs = Dict{String,Any}()
                for a in arms
                    a.alive || continue
                    recs[a.name] = arm_metrics!(a, step, FORK_STEP)
                end
                # ---- mandatory regression gates against the DIAG3 authority (bitwise)
                if !NO_REF && step <= REF_LAST_STEP && haskey(recs, "B0") && straight_ref !== nothing && haskey(straight_ref, step)
                    cs_strings(recs["B0"].cs) == straight_ref[step] || (gate["failure"] = "B0 differs from the DIAG3 straight replay at step $step"; error(gate["failure"]))
                    gate["b0_vs_diag3_straight_checked_steps"] += 1
                end
                if !NO_REF && step > FORK_STEP && step <= REF_LAST_STEP && fork !== nothing && haskey(recs, "B32fork") && f32_ref !== nothing && haskey(f32_ref, step)
                    cs_strings(recs["B32fork"].cs) == f32_ref[step] || (gate["failure"] = "B32fork differs from the DIAG3 F32 arm (= DIAG2 V1c) at step $step"; error(gate["failure"]))
                    gate["fork_vs_diag3_f32_checked_steps"] += 1
                end
                # ---- the exact clone of B0 at the fork step (u, p and the dt vector copied bit for bit into a fresh simulation)
                if step == FORK_STEP
                    r = recs["B0"]
                    fork = new_arm("B32fork", :forced, phi_dual, DT, case, outdir)
                    fork.start_step = FORK_STEP
                    copyto!(fork.sim.flow.u, to_device(r.u)); copyto!(fork.sim.flow.p, to_device(r.p))
                    empty!(fork.sim.flow.Δt); append!(fork.sim.flow.Δt, copy(b0.sim.flow.Δt))
                    assert_independent(b0, fresh, fork)
                    index["independence_checked"] = true
                    fork.ref = copy(b0.ref)                 # the reference tangent of the cloned state at the fork step (a private copy): increments are measured against it
                    clone_check = step_record(fork.sim)
                    rawbits(x) = reinterpret(UInt8, vec(collect(x)))
                    clone_check.cs == r.cs && rawbits(clone_check.u) == rawbits(r.u) && rawbits(clone_check.p) == rawbits(r.p) && rawbits(fork.sim.flow.Δt) == rawbits(b0.sim.flow.Δt) ||
                        (gate["failure"] = "the B32fork clone is not bit-identical to B0 at the fork step"; error(gate["failure"]))
                    index["clone_bit_identical_at_fork"] = true
                end
                # ---- comparisons (host copies, values only)
                if haskey(recs, "B32fork") && haskey(recs, "B0") && step > FORK_STEP
                    compare!(cmp_fork, step, recs["B32fork"], recs["B0"], fork.last_forces, b0.last_forces)
                end
                if haskey(recs, "B32fresh") && haskey(recs, "B0")
                    compare!(cmp_fresh, step, recs["B32fresh"], recs["B0"], fresh.last_forces, b0.last_forces)
                end
                if haskey(recs, "B32fresh") && haskey(recs, "B32fork") && step > FORK_STEP
                    compare!(cmp_ff, step, recs["B32fresh"], recs["B32fork"], fresh.last_forces, fork.last_forces)
                end
                if step in SNAPSHOT_STEPS
                    for a in arms
                        a.alive && write_snapshot!(snap_index, outdir, step, "$(a.name)_step$(step)", ["u" => a.last_record.u, "p" => a.last_record.p])
                    end
                end
                for a in arms     # the last state of an arm that stopped (its first non-finite value) is kept
                    if !a.alive && !a.snapshotted && a.last_record !== nothing
                        write_snapshot!(snap_index, outdir, step, "$(a.name)_last_step$(step)", ["u" => a.last_record.u, "p" => a.last_record.p]); a.snapshotted = true
                    end
                end
                if step % 50 == 0
                    index["progress"] = Dict("step" => step, "seconds" => time() - started, "alive" => Dict(a.name => a.alive for a in arms),
                        "tangent_valid" => Dict(a.name => a.tangent_valid for a in arms))
                    write_json(joinpath(outdir, "diag_index.json"), index)
                end
                all(!a.alive for a in arms) && fork !== nothing && break
            end
        finally
            for a in (b0, fresh, fork)
                a === nothing || close(a.io)
            end
            for io in (cmp_fork, cmp_fresh, cmp_ff)
                close(io)
            end
        end
        sync()
        summary(a) = a === nothing ? nothing : Dict("alive_at_end" => a.alive, "tangent_valid" => a.tangent_valid, "first_nonfinite" => a.first_nonfinite === nothing ? nothing : collect(a.first_nonfinite),
            "steps_recorded" => length(a.cs), "used_vram_bytes_at_end" => used_memory())
        return Dict{String,Any}("B0" => summary(b0), "B32fresh" => summary(fresh), "B32fork" => summary(fork), "gate" => gate, "seconds" => time() - started)
    end
end

function main()
    length(ARGS) == 5 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>")
    phi_path, phi_sha, outdir, d0_path, d0_sha = ARGS
    mkpath(outdir)
    isfile(joinpath(outdir, "diag_index.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2-DIAG4", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "status" => "RUNNING", "dryrun" => DRYRUN, "fork_step" => FORK_STEP, "end_step" => END_STEP, "forced_iterations" => FORCED_ITERATIONS,
        "reference_last_step" => REF_LAST_STEP, "no_reference" => NO_REF,
        "waterlily_flow_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Flow.jl")))),
        "waterlily_multilevelpoisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "MultiLevelPoisson.jl")))),
        "waterlily_poisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Poisson.jl")))),
        "evidence_class" => "gpu_d0_forced32_long_horizon_diagnostic_unregistered",
        "claim_limit" => "diagnostic: does forced-32 delay or remove the corner tangent mode; forced-32 is a different solver candidate, not an AD fix; no bridge value, no FD-08 comparison, no error gate",
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
        result = run_all(phi_dual, DT, case, outdir, index)
        index["result"] = result
        gate_ok = result["gate"]["failure"] === nothing && (NO_REF || (result["gate"]["b0_vs_diag3_straight_checked_steps"] == min(REF_LAST_STEP, END_STEP) &&
                  result["gate"]["fork_vs_diag3_f32_checked_steps"] == min(REF_LAST_STEP, END_STEP) - FORK_STEP))
        arms_ok = all(result[k] !== nothing for k in ("B0", "B32fresh", "B32fork")) && result["B0"]["steps_recorded"] >= FORK_STEP + 1
        index["verdict"] = gate_ok && arms_ok ? "DIAG4_RECORDED" : "DIAG4_INCOMPLETE"
        index["verdict_reason"] = gate_ok && arms_ok ? "all arms recorded; the scientific classification is made by the host analyzer" : "regression gate or arm inventory failed"
        index["status"] = index["verdict"] == "DIAG4_RECORDED" ? "COMPLETE" : "INCOMPLETE"
        index["status"] == "COMPLETE" || (exit_code = 2)
    catch err
        index["status"] = "ERROR"; index["verdict"] = "DIAG4_INCOMPLETE"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        exit_code = 2
    end
    write_json(joinpath(outdir, "diag_index.json"), index)
    println("DIAG4_RESULT ", index["status"], " ", index["verdict"], " ", outdir)
    exit_code == 0 || exit(exit_code)
end

run_one_tag() = nothing
main()
