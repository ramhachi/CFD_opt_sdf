# G2-DIAG2: which operator / boundary treatment / numerical setting makes the far-field corner tangent mode of the D0
# Dual{Float32,1} run grow (G2-DIAG1: x1.26 per step from step ~800, primal steady)?  Counterfactual fork replay.
#
# Same scientific state as G2 / G2-DIAG1 (canonical v17 phi, D0 bytes, flow_24, Candidate C, Float32, Dual width 1, WaterLily defaults).
#   1. S "straight": plain `sim_step!` from step 0 to END_STEP with per-step state checksums; the state (u, p, dt vector) after
#      step FORK_STEP is copied to the host.
#   2. For every variant: a fresh simulation, the fork state restored, then FORK_STEP+1 .. END_STEP steps of `measure!` +
#      `diag2_mom_step!` with a probe that records and, for the counterfactual variants only, intervenes (zeroing the tangent
#      part of u in a region after the boundary-condition stages, forcing the Poisson iteration count, freezing the dt tangent).
#   V0 has no intervention; its per-step checksums must equal S's (bitwise) or the run is DIAG2_INCOMPLETE.
# The interventions are counterfactual perturbations of the tangent computation, NOT observation-only and NOT a fix.
# No Float64, no D1/D2/P1, no window/bridge, no delta.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_g2_diag2_d0_tangent_counterfactual_2026_10_08.jl \
#          <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>
# env (cpu code-path dry run only): DIAG2_BACKEND=cpu, DIAG2_FORK_STEP, DIAG2_STEPS, DIAG2_ONLY=<comma separated variant names>,
#   DIAG2_RAISE_VARIANT=<name>

using WaterLily
using SHA
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "DIAG2_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("DIAG2_BACKEND must be cuda or cpu")
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
Base.include(WaterLily, joinpath(@__DIR__, "waterlily_grad_g2_diag2_stages.jl"))

const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const SPACING = 0.025
const TRANSITION = Float32(1.1444091796875e-4)

# ---- configuration (fixed in the pre-run freeze) ---------------------------------------------------------------------------
const DRYRUN = BACKEND == "cpu"
(!DRYRUN && any(haskey(ENV, k) for k in ("DIAG2_FORK_STEP", "DIAG2_STEPS", "DIAG2_ONLY", "DIAG2_RAISE_VARIANT"))) &&
    error("DIAG2 dry-run switches are only allowed with DIAG2_BACKEND=cpu")
const FORK_STEP = DRYRUN && haskey(ENV, "DIAG2_FORK_STEP") ? parse(Int, ENV["DIAG2_FORK_STEP"]) : 780
const N_STEPS = DRYRUN && haskey(ENV, "DIAG2_STEPS") ? parse(Int, ENV["DIAG2_STEPS"]) : 200
const END_STEP = FORK_STEP + N_STEPS
const SLOPE_FROM = FORK_STEP + N_STEPS ÷ 2            # slope window = [FORK+100, FORK+200] in the production run
const BASELINE_MIN_SLOPE = 0.05                        # decade/step; below this V0 did not reproduce the mode
const SUPPRESS_SLOPE = 0.01
const REDUCE_FACTOR = 0.5
const DEVICE_N = (152, 74, 56)                         # flow array extent (flow_24 + 2 ghost layers)
const STAGES_U = (:pre_scale, :predict_bdim, :predict_bc, :predict_exitbc, :project1_gradient, :project1_bc, :correct_bdim, :correct_scale,
    :correct_bc, :project2_gradient, :project2_bc)
const KILL_STAGES = (:predict_bc, :predict_exitbc, :project1_bc, :correct_bc, :project2_bc)   # right after each BC! / exitBC!
# name, kill region (tangent of u zeroed), forced Poisson (tol, itmx), freeze the dt tangent
const VARIANTS = (
    (name="V0_baseline", kill=nothing, poisson=nothing, freeze_dt=false),
    (name="V1a_poisson_n4", kill=nothing, poisson=(tol=0.0, itmx=4), freeze_dt=false),
    (name="V1b_poisson_n16", kill=nothing, poisson=(tol=0.0, itmx=16), freeze_dt=false),
    (name="V1c_poisson_n32", kill=nothing, poisson=(tol=0.0, itmx=32), freeze_dt=false),
    (name="V2_dt_tangent_frozen", kill=nothing, poisson=nothing, freeze_dt=true),
    (name="V3_kill_corner_box", kill=:box, poisson=nothing, freeze_dt=false),
    (name="V4a_kill_slab_xmin", kill=:xmin, poisson=nothing, freeze_dt=false),
    (name="V4b_kill_slab_ymin", kill=:ymin, poisson=nothing, freeze_dt=false),
    (name="V4c_kill_slab_zmax", kill=:zmax, poisson=nothing, freeze_dt=false),
    (name="V4d_kill_slabs_all", kill=:far, poisson=nothing, freeze_dt=false),
    (name="V5_kill_ghost_layers", kill=:ghost, poisson=nothing, freeze_dt=false),
    (name="V6_kill_exit_slab", kill=:xmax, poisson=nothing, freeze_dt=false),
)
const ACTIVE = DRYRUN && haskey(ENV, "DIAG2_ONLY") ? Tuple(split(ENV["DIAG2_ONLY"], ",")) : nothing
const RAISE_VARIANT = DRYRUN && haskey(ENV, "DIAG2_RAISE_VARIANT") ? ENV["DIAG2_RAISE_VARIANT"] : nothing

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

# ---- tangent statistics and interventions ------------------------------------------------------------------------------------
absp(x) = (v = Float64(FD.value(x)); isfinite(v) ? abs(v) : 0.0)
abst(x) = (v = Float64(FD.partials(x, 1)); isfinite(v) ? abs(v) : 0.0)
badp(x) = !isfinite(FD.value(x))
badt(x) = !isfinite(FD.partials(x, 1))
zero_tangent(x::FD.Dual{T,V,1}) where {T,V} = FD.Dual{T,V,1}(FD.value(x), FD.Partials{1,V}((zero(V),)))

function region_ranges(kind::Symbol)
    nx, ny, nz = DEVICE_N
    kind === :box && return [(1:12, 1:8, 49:nz)]
    kind === :xmin && return [(1:8, 1:ny, 1:nz)]
    kind === :ymin && return [(1:nx, 1:8, 1:nz)]
    kind === :zmax && return [(1:nx, 1:ny, 49:nz)]
    kind === :xmax && return [(nx - 7:nx, 1:ny, 1:nz)]
    kind === :far && return vcat(region_ranges(:xmin), region_ranges(:ymin), region_ranges(:zmax))
    kind === :ghost && return [(1:2, 1:ny, 1:nz), (nx - 1:nx, 1:ny, 1:nz), (1:nx, 1:2, 1:nz), (1:nx, ny - 1:ny, 1:nz), (1:nx, 1:ny, 1:2), (1:nx, 1:ny, nz - 1:nz)]
    error("unknown region $kind")
end

function kill_tangent!(u, kind::Symbol)   # counterfactual: the tangent part of u in a region is set to 0, the value is kept
    for (ri, rj, rk) in region_ranges(kind)
        v = view(u, ri, rj, rk, :)
        v .= zero_tangent.(v)
    end
    return nothing
end

box_max_t(u) = maximum(abst, view(u, 1:12, 1:8, 49:DEVICE_N[3], :))
function freeze_dt!(sim)
    for k in eachindex(sim.flow.Δt)
        sim.flow.Δt[k] = zero_tangent(sim.flow.Δt[k])
    end
end

# ---- host copies, checksums ---------------------------------------------------------------------------------------------------
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
const CS_HEADER = ["u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits"]

# ---- the variant probe -------------------------------------------------------------------------------------------------------
const STEP_HEADER = ["step", "t_u_l", "dt_value", "dt_tangent", "glob_max_tangent_u", "glob_max_primal_u", "nonfinite_primal_u", "nonfinite_tangent_u",
    (string("box_", s) for s in STAGES_U)..., "iters1", "iters2", "z1_primal", "z1_tangent", "r1_primal", "r1_tangent", "z2_primal", "z2_tangent",
    "r2_primal", "r2_tangent", CS_HEADER...]

mutable struct VProbe
    spec::Any
    step::Int
    rec::Dict{String,Float64}
end

function (p::VProbe)(stage::Symbol, fields::NamedTuple; iters=nothing, r2=nothing)
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
    # counterfactual intervention (never for V0): only after the fork, only after a boundary-condition stage
    if p.spec.kill !== nothing && p.step > FORK_STEP && stage in KILL_STAGES && haskey(fields, :u)
        kill_tangent!(fields.u, p.spec.kill)
    end
    return nothing
end

function variant_step!(sim, probe::VProbe)
    WaterLily.measure!(sim)   # sim_step!(sim; remeasure=true): measure!(sim) then mom_step!
    WaterLily.diag2_mom_step!(sim.flow, sim.pois, probe, probe.spec.poisson)
    probe.spec.freeze_dt && freeze_dt!(sim)
    return nothing
end

# ---- run S: straight plain replay + fork state --------------------------------------------------------------------------------
function run_straight(phi_host, ::Type{T}, case, outdir) where {T}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    cs_io = csv_open(joinpath(outdir, "straight_checksums.csv"), ["step", CS_HEADER..., "glob_max_tangent_u", "box_max_tangent_u"])
    cs, fork, final_gt = Dict{Int,Any}(), nothing, NaN
    started = time()
    GC.@preserve phi_dev owner sim bodies begin
        r0 = step_record(sim); cs[0] = r0.cs; csv_row(cs_io, (0, r0.cs..., 0, 0))
        for step in 1:END_STEP
            WaterLily.sim_step!(sim)
            r = step_record(sim)
            cs[step] = r.cs
            gt, bt = step >= FORK_STEP ? (maximum(abst, sim.flow.u), box_max_t(sim.flow.u)) : (NaN, NaN)
            step == END_STEP && (final_gt = gt)
            csv_row(cs_io, (step, r.cs..., gt, bt)); flush(cs_io)
            step == FORK_STEP && (fork = (u=r.u, p=r.p, dt=copy(sim.flow.Δt)))
        end
        close(cs_io)
        sync()
        size(sim.flow.u) == (DEVICE_N..., 3) || error("flow array extent $(size(sim.flow.u)) != the registered $(DEVICE_N)")
        return Dict{String,Any}("steps_run" => END_STEP, "seconds" => time() - started, "t_end_u_l" => vp(WaterLily.sim_time(sim))[1],
            "fork_u_sha256" => sha_hex(fork.u), "fork_p_sha256" => sha_hex(fork.p), "fork_dt_length" => length(fork.dt), "final_glob_max_tangent_u" => final_gt, "checksums" => cs), fork
    end
end

# ---- one variant ---------------------------------------------------------------------------------------------------------------
function run_variant(spec, phi_host, ::Type{T}, case, fork, outdir) where {T}
    RAISE_VARIANT == spec.name && error("DIAG2 deliberate dry-run exception in $(spec.name)")
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    probe = VProbe(spec, FORK_STEP, Dict{String,Float64}())
    cs, stopped, started = Dict{Int,Any}(), nothing, time()
    io = nothing
    GC.@preserve phi_dev owner sim bodies begin
        try
            io = csv_open(joinpath(outdir, "variant_$(spec.name).steps.csv"), STEP_HEADER)
            copyto!(sim.flow.u, to_device(fork.u)); copyto!(sim.flow.p, to_device(fork.p))
            empty!(sim.flow.Δt); append!(sim.flow.Δt, fork.dt)
            spec.freeze_dt && freeze_dt!(sim)
            for step in FORK_STEP + 1:END_STEP
                probe.step = step
                empty!(probe.rec)
                variant_step!(sim, probe)
                r = step_record(sim)
                cs[step] = r.cs
                rec = probe.rec
                dtv, dtt = vp(sim.flow.Δt[end])
                row = Any[step, vp(WaterLily.sim_time(sim))[1], dtv, dtt, get(rec, "glob_t", NaN), get(rec, "glob_p", NaN), get(rec, "nf_p", NaN), get(rec, "nf_t", NaN)]
                append!(row, (get(rec, "box_$s", NaN) for s in STAGES_U))
                append!(row, (get(rec, k, NaN) for k in ("iters1", "iters2", "z1_p", "z1_t", "r1_p", "r1_t", "z2_p", "z2_t", "r2_p", "r2_t")))
                append!(row, r.cs)
                csv_row(io, row); flush(io)
                if get(rec, "nf_p", 0.0) > 0 || get(rec, "nf_t", 0.0) > 0
                    stopped = step
                    break
                end
            end
        finally
            io === nothing || close(io)
        end
        sync()
        return Dict{String,Any}("name" => spec.name, "steps_run" => length(cs), "stopped_nonfinite_at_step" => stopped, "seconds" => time() - started,
            "checksums" => cs, "used_vram_bytes_at_end" => used_memory())
    end
end

# ---- classification (the analyzer re-derives it from the CSV files) --------------------------------------------------------------
function slope(steps, ys)
    n = length(steps)
    n < (DRYRUN ? 3 : 10) && return NaN
    mx, my = sum(steps) / n, sum(ys) / n
    sxx = sum((x - mx)^2 for x in steps)
    return sxx == 0 ? NaN : sum((x - mx) * (y - my) for (x, y) in zip(steps, ys)) / sxx
end

function variant_slope(name, outdir, column="glob_max_tangent_u")
    lines = readlines(joinpath(outdir, "variant_$(name).steps.csv"))
    head = split(lines[1], ",")
    ig, ist = findfirst(==(column), head), findfirst(==("step"), head)
    pts = [(parse(Int, c[ist]), parse(Float64, c[ig])) for c in (split(l, ",") for l in lines[2:end])]
    pts = filter(p -> p[1] >= SLOPE_FROM && isfinite(p[2]), pts)
    return slope([p[1] for p in pts], [log10(max(p[2], 1e-300)) for p in pts])
end

# Both the global max and the corner-box max (box_project2_bc) must meet a threshold: the global max sits on the near-body floor (~21)
# until the corner mode exceeds it, so a slowed mode could otherwise look suppressed.
function classify(s, sb, s0, sb0, stopped)
    stopped !== nothing && return "diverged"
    (isnan(s) || isnan(sb)) && return "undetermined"
    (s <= SUPPRESS_SLOPE && sb <= SUPPRESS_SLOPE) && return "suppresses"
    (s <= REDUCE_FACTOR * s0 && sb <= REDUCE_FACTOR * sb0) && return "reduces"
    return "no_effect"
end

function main()
    length(ARGS) == 5 || error("usage: <phi_raw> <phi_sha> <outdir> <D0_raw> <D0_sha>")
    phi_path, phi_sha, outdir, d0_path, d0_sha = ARGS
    mkpath(outdir)
    isfile(joinpath(outdir, "diag_index.json")) && error("refusing to overwrite $outdir")
    index = Dict{String,Any}("tier" => "G2-DIAG2", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "status" => "RUNNING", "dryrun" => DRYRUN, "fork_step" => FORK_STEP, "end_step" => END_STEP,
        "slope_from_step" => SLOPE_FROM, "variants" => [v.name for v in VARIANTS],
        "waterlily_flow_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "Flow.jl")))),
        "waterlily_multilevelpoisson_jl_sha256" => bytes2hex(sha256(read(joinpath(pkgdir(WaterLily), "src", "MultiLevelPoisson.jl")))),
        "evidence_class" => "gpu_d0_tangent_counterfactual_diagnostic_unregistered",
        "claim_limit" => "counterfactual diagnostic of the far-field tangent mode; interventions are perturbations of the tangent computation, not a fix; no bridge value, no error gate",
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
        # preflight: view reductions and the tangent kill on a tiny array (device path must equal the host path)
        h = reshape([DT(Float32(i), FD.Partials((Float32(-i),))) for i in 1:DEVICE_N[1]*DEVICE_N[2]*DEVICE_N[3]*3], DEVICE_N..., 3)
        d = to_device(copy(h))
        before = box_max_t(d); kill_tangent!(d, :box); dh = Array(d)
        d2 = similar(d); copyto!(d2, d)   # device -> device copy (the fork restore path)
        index["preflight"] = Dict("box_max_before" => before, "box_max_after_kill" => box_max_t(d), "tangent_zero_in_box" => all(FD.partials(x, 1) == 0 for x in dh[1:12, 1:8, 49:DEVICE_N[3], :]),
            "value_kept" => all(FD.value.(dh) .== FD.value.(h)), "tangent_untouched_outside" => FD.partials(dh[13, 9, 1, 1], 1) == FD.partials(h[13, 9, 1, 1], 1),
            "device_copy_equal" => Array(d2) == dh)
        # every other region kind must also run on the device and zero exactly its own cells (compared with the same operation on the host)
        for kind in (:xmin, :ymin, :zmax, :xmax, :far, :ghost)
            dd = to_device(copy(h)); kill_tangent!(dd, kind)
            hh = copy(h)
            for (ri, rj, rk) in region_ranges(kind)
                hh[ri, rj, rk, :] .= zero_tangent.(hh[ri, rj, rk, :])
            end
            index["preflight"]["region_$kind"] = Array(dd) == hh
        end
        pre = index["preflight"]
        (pre["box_max_after_kill"] == 0 && pre["tangent_zero_in_box"] && pre["value_kept"] && pre["tangent_untouched_outside"] && before > 0 && pre["device_copy_equal"] &&
         all(pre["region_$k"] for k in (:xmin, :ymin, :zmax, :xmax, :far, :ghost))) || error("preflight failed: $pre")
        h = d = dh = d2 = nothing
        write_json(joinpath(outdir, "diag_index.json"), index)
        straight, fork = run_straight(phi_dual, DT, case, outdir)
        index["straight"] = Dict(k => v for (k, v) in straight if k != "checksums")
        write_json(joinpath(outdir, "diag_index.json"), index)
        results, any_exception = Dict{String,Any}(), false
        for spec in VARIANTS
            ACTIVE !== nothing && !(spec.name in ACTIVE) && continue
            GC.gc()
            index["current_variant"] = spec.name
            write_json(joinpath(outdir, "diag_index.json"), index)
            r = try
                run_variant(spec, phi_dual, DT, case, fork, outdir)
            catch err
                any_exception = true
                Dict{String,Any}("name" => spec.name, "steps_run" => 0, "stopped_nonfinite_at_step" => nothing, "checksums" => Dict{Int,Any}(),
                    "exception" => first(sprint(showerror, err, catch_backtrace()), 3000))
            end
            results[spec.name] = r
            index["variant_results"] = Dict(k => Dict(kk => vv for (kk, vv) in v if kk != "checksums") for (k, v) in results)
            write_json(joinpath(outdir, "diag_index.json"), index)
        end
        v0 = get(results, "V0_baseline", nothing)
        gate = v0 !== nothing && !haskey(v0, "exception") && v0["steps_run"] == N_STEPS && v0["stopped_nonfinite_at_step"] === nothing &&
               isfinite(straight["final_glob_max_tangent_u"]) && all(haskey(straight["checksums"], s) && straight["checksums"][s] == c for (s, c) in v0["checksums"])
        index["v0_bitwise_equal_to_straight"] = gate
        s0 = v0 === nothing || haskey(v0, "exception") ? NaN : variant_slope("V0_baseline", outdir)
        sb0 = v0 === nothing || haskey(v0, "exception") ? NaN : variant_slope("V0_baseline", outdir, "box_project2_bc")
        index["slopes_decade_per_step"] = Dict(n => (haskey(r, "exception") ? NaN : variant_slope(n, outdir)) for (n, r) in results)
        index["box_slopes_decade_per_step"] = Dict(n => (haskey(r, "exception") ? NaN : variant_slope(n, outdir, "box_project2_bc")) for (n, r) in results)
        index["classes"] = Dict(n => (haskey(r, "exception") ? "exception" : n == "V0_baseline" ? "baseline" :
            classify(index["slopes_decade_per_step"][n], index["box_slopes_decade_per_step"][n], s0, sb0, r["stopped_nonfinite_at_step"])) for (n, r) in results)
        verdict, why = any_exception ? ("DIAG2_INCOMPLETE", "a variant raised an exception") :
                       !gate ? ("DIAG2_INCOMPLETE", "V0 is not bitwise equal to the straight replay (fork restore or observation changed the state)") :
                       isnan(s0) || s0 < BASELINE_MIN_SLOPE ? ("DIAG2_NOT_REPRODUCED", "the baseline did not reproduce the tangent growth (slope $s0 decade/step)") :
                       ("DIAG2_LOCALIZED", "baseline reproduced the growth and every variant was recorded")
        index["verdict"], index["verdict_reason"] = verdict, why
        index["status"] = verdict in ("DIAG2_LOCALIZED", "DIAG2_NOT_REPRODUCED") ? "COMPLETE" : "INCOMPLETE"
        index["status"] == "COMPLETE" || (exit_code = 2)
    catch err
        index["status"] = "ERROR"; index["verdict"] = "DIAG2_INCOMPLETE"
        index["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
        exit_code = 2
    end
    write_json(joinpath(outdir, "diag_index.json"), index)
    println("DIAG2_RESULT ", index["status"], " ", index["verdict"], " ", outdir)
    exit_code == 0 || exit(exit_code)
end

run_one_tag() = nothing
main()
