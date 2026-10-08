# G1 capability gate: do ForwardDiff Dual numbers work in a few WaterLily 1.8.0 `sim_step!`s of the Candidate C
# composite body on the canonical v17 state, with CuArray storage and Float32 (Kaggle T4)?  The same script runs on
# the CPU (G1_BACKEND=cpu) to test the logic without a GPU.  Instantaneous force after a few steps only: NOT the FD-08
# window mean, NOT comparable to the FD-08 oracle value, NOT a gradient qualification.  No flag is touched.
#
# usage: julia --project=julia/CFDSDFWaterLilyT4 scripts/waterlily_grad_dual_gpu_spike_2026_10_08.jl \
#          <phi_f4_fortran.raw> <phi_sha256> <dir_f4_fortran.raw> <dir_sha256> <output.json>
# env:   G1_BACKEND (cuda | cpu, default cuda), SPIKE_STEPS (default 2), G1_FP64 (1 = also run a 1-step Float64 Dual tier)

using WaterLily
using SHA
const FD = WaterLily.ForwardDiff
const BACKEND = get(ENV, "G1_BACKEND", "cuda")
BACKEND in ("cuda", "cpu") || error("G1_BACKEND must be cuda or cpu")
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
const POIS = (1e-4, 32)   # WaterLily 1.8.0 defaults; this script does not override the Poisson solver

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

"""Build the flow_24 Candidate C simulation for the given (device) phi; returns (sim, bodies, owner)."""
function build(phi_dev::AbstractArray{S,3}, ::Type{T}, case) where {S,T}
    FS = real_type(T)
    grid = GridSDF(phi_dev, FS.(ORIGIN), FS.((SPACING, SPACING, SPACING)), SHAPE, FS(3), FS(0.15))  # raw ctor: no gate on device/Dual data
    if BACKEND == "cuda"
        owner = CFDSDFWaterLily.DeviceGridSDF.DeviceGridSDF(grid, "g1-spike")
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

function run_forces(phi_host::AbstractArray, ::Type{T}, case, steps) where {T}
    phi_dev = to_device(phi_host)
    sim, bodies, owner = build(phi_dev, T, case)
    GC.@preserve phi_dev owner sim bodies begin
        for _ in 1:steps
            WaterLily.sim_step!(sim; remeasure=false)
        end
        sync()
        total = WaterLily.total_force(sim)                                   # combined body (CPU-spike definition)
        pressure = -(WaterLily.pressure_force(sim.flow, bodies.candidate))   # candidate only, sign as in the registered job
        viscous = -(WaterLily.viscous_force(sim.flow, bodies.candidate))
        cand = pressure + viscous
        u = Array(sim.flow.u)
        fields_ok = all(x -> isfinite(vp(x)[1]) && isfinite(vp(x)[2]), u)
        tangent_max = maximum(x -> abs(vp(x)[2]), u)
        return (combined_fx=vp(total[1]), combined_fz=vp(total[3]), cand_drag=vp(cand[1]), cand_downforce=vp(-cand[3]),
                fields_finite=fields_ok, field_tangent_max=tangent_max, vram=used_memory())
    end
end

function dual_input(phi32::Array{Float32,3}, d32::Array{Float32,3}, ::Type{V}) where {V<:Real}
    tag = FD.Tag(run_forces, V)
    DT = FD.Dual{typeof(tag),V,1}
    return DT, DT.(V.(phi32), FD.Partials.(tuple.(V.(d32))))
end

rel(a, b) = abs(a - b) / max(abs(b), floatmin(Float64))

function tier(phi32, d32, ::Type{V}, case, steps, fd_eps) where {V<:Real}
    out = Dict{String,Any}("real_type" => string(V), "steps" => steps, "backend" => BACKEND, "poisson" => collect(POIS))
    plain = run_forces(V.(phi32), V, case, steps)
    t0 = time()
    DT, phi_dual = dual_input(phi32, d32, V)
    ad = run_forces(phi_dual, DT, case, steps)
    out["dual_seconds_incl_jit"] = time() - t0
    for key in (:combined_fx, :combined_fz, :cand_drag, :cand_downforce)
        pv, _ = getfield(plain, key); av, at = getfield(ad, key)
        out[string(key)] = Dict("plain" => pv, "ad_primal" => av, "ad_tangent" => at, "primal_rel_diff" => rel(av, pv))
    end
    out["primal_rel_diff_max"] = maximum(out[string(k)]["primal_rel_diff"] for k in (:combined_fx, :combined_fz, :cand_drag, :cand_downforce))
    out["tangent_finite"] = all(isfinite(out[string(k)]["ad_tangent"]) for k in (:combined_fx, :combined_fz, :cand_drag, :cand_downforce))
    out["tangent_nonzero"] = all(out[string(k)]["ad_tangent"] != 0 for k in (:combined_fx, :combined_fz, :cand_drag, :cand_downforce))
    out["fields_finite_incl_partials"] = ad.fields_finite
    out["field_tangent_max"] = ad.field_tangent_max
    out["peak_vram_bytes"] = max(plain.vram, ad.vram)
    fd = Any[]
    for e in fd_eps
        # clearance gate on the primal phi +- eps d (Dual inputs bypass the GridSDF gate)
        for s in (-1.0, 1.0)
            zero_level_margin_m(Float64.(phi32) .+ s * e .* Float64.(d32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 || error("clearance gate failed at eps=$e")
        end
        fp = run_forces(V.(Float64.(phi32) .+ e .* Float64.(d32)), V, case, steps)
        fm = run_forces(V.(Float64.(phi32) .- e .* Float64.(d32)), V, case, steps)
        row = Dict{String,Any}("eps_m" => e)
        for key in (:combined_fx, :combined_fz)
            g = (getfield(fp, key)[1] - getfield(fm, key)[1]) / (2e)
            row[string(key) * "_fd"] = g
            row[string(key) * "_rel_diff_vs_ad"] = rel(out[string(key)]["ad_tangent"], g)
        end
        push!(fd, row)
    end
    out["fd_float_noise_check"] = fd
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

function write_result(result, outpath)
    open(outpath, "w") do io
        write(io, json(result), "\n")
    end
end

function main()
    length(ARGS) == 5 || error("usage: <phi_raw> <phi_sha> <dir_raw> <dir_sha> <output.json>")
    phi_path, phi_sha, dir_path, dir_sha, outpath = ARGS
    isfile(outpath) && error("refusing to overwrite $outpath")
    steps = parse(Int, get(ENV, "SPIKE_STEPS", "2"))
    result = Dict{String,Any}("tier" => "G1", "backend" => BACKEND, "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "forwarddiff" => string(pkgversion(FD)), "evidence_class" => "gpu_forward_ad_capability_spike_unregistered",
        "claim_limit" => "instantaneous force after a few steps; not the FD-08 window mean; not a gradient qualification; no flag is changed",
        "phi_sha256" => phi_sha, "direction_sha256" => dir_sha,
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    try
        if BACKEND == "cuda"
            result["gpu_name"] = Base.invokelatest(() -> CUDA.name(CUDA.device()))
            result["cuda_jl"] = string(pkgversion(CUDA))
            Base.invokelatest(CUDA.functional) || error("CUDA is not functional")
        end
        phi32, d32 = load_raw(phi_path, phi_sha), load_raw(dir_path, dir_sha)
        maximum(abs, d32) == 1.0f0 || error("direction max-norm != 1")
        zero_level_margin_m(Float64.(phi32), ORIGIN, (SPACING, SPACING, SPACING)) >= 0.15 - 1e-6 || error("baseline clearance gate failed")
        case = only(c for c in w4_cases(ORIGIN, SPACING) if c.case_id == "flow_24")
        validate_w4_case(case; canonical_design_origin_m=ORIGIN, canonical_design_spacing_m=SPACING)
        result["float32"] = tier(phi32, d32, Float32, case, steps, [1e-3, 2e-3])
        result["status"] = "FLOAT32_DONE"
        write_result(result, outpath)   # keep the judged tier even if the info-only Float64 tier crashes the process
        if get(ENV, "G1_FP64", "0") == "1"
            try
                result["float64_info"] = tier(phi32, d32, Float64, case, 1, Float64[])
            catch err
                result["float64_info"] = Dict("error" => first(sprint(showerror, err), 800))
            end
        end
        result["status"] = "COMPLETE"
    catch err
        result["status"] = "ERROR"
        result["error"] = first(sprint(showerror, err, catch_backtrace()), 4000)
    end
    write_result(result, outpath)
    println("G1_RESULT ", result["status"], " ", outpath)
    result["status"] == "COMPLETE" || exit(2)
end

main()
