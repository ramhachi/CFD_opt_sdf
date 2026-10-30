# POST-HOC DIAGNOSTIC (not pre-registered; written after the frozen spike script had been run) of the same CPU spike.
# Purpose: separate finite-difference noise of the discrete model from AD error on the toy.
# CPU-only capability spike (GRAD-02 follow-up): can forward-mode AD (ForwardDiff Dual numbers) differentiate a
# few WaterLily `sim_step!`s of the Candidate C composite body with respect to a perturbation of the SDF design
# field phi along a direction d?  Compares  d/dt force(phi + t d)  from Dual partials with centered finite differences
# of the same discrete model.  Instantaneous force after a few steps only: NOT the FD-08 window mean, NOT comparable
# to the FD-08 oracle value, NOT a gradient qualification.  No flag is touched.
#
# usage: julia --startup-file=no --project=julia/CFDSDFWaterLily scripts/waterlily_grad_forwarddiff_spike_diag_2026_10_08.jl toy64sweep <output.json>
# tier: toy64sweep only (the other tiers live in the frozen script).
# env:  SPIKE_STEPS (default 3)

using WaterLily
const FD = WaterLily.ForwardDiff

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end
using .CFDSDFWaterLily
using SHA
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m

# --- Poisson tolerance knob (WaterLily 1.8.0 hard-codes tol=1e-4, itmx=32 in solver!; precedent: GRAD-02 sweep override) ---
const POIS = Ref((1e-4, 32))
function WaterLily.solver!(ml::WaterLily.MultiLevelPoisson{T}; tol=POIS[][1], itmx=POIS[][2]) where T
    p = ml.levels[1]
    WaterLily.residual!(p); r₂ = WaterLily.L₂(p); ω = T(1)
    nᵖ = 0
    while nᵖ < itmx
        WaterLily.Vcycle!(ml; ω)
        WaterLily.smooth!(p; ω)
        rnew = WaterLily.L₂(p); nᵖ += 1
        ω = rnew ≥ r₂ ? T(max(0.2, 0.9ω)) : T(min(1.0, 1.02ω))
        r₂ = rnew
        r₂ < tol && break
    end
    WaterLily.perBC!(p.x, p.perdir)
    push!(ml.n, nᵖ)
end

# --- fixtures ---------------------------------------------------------------------------------------------------------
struct Fixture
    dims::NTuple{3,Int}
    L::Float64
    ν::Float64
    origin_m::NTuple{3,Float64}      # SDF design lattice origin (world, m)
    h_m::NTuple{3,Float64}
    flow_origin_m::NTuple{3,Float64} # world position of solver coordinate 0
    world_per_solver::Float64
    ground_z::Float64
    phi::Array{Float64,3}            # baseline phi (m)
    d::Array{Float64,3}              # direction (max |d| = 1)
    steps::Int
end

function toy_fixture(; steps)
    origin, h = (-1.0, -1.0, -1.0), (0.1, 0.1, 0.1)
    phi = Array{Float64}(undef, 21, 21, 21)
    d = zeros(21, 21, 21)
    for k in axes(phi, 3), j in axes(phi, 2), i in axes(phi, 1)
        x, y, z = origin[1] + (i - 1) * h[1], origin[2] + (j - 1) * h[2], origin[3] + (k - 1) * h[3]
        phi[i, j, k] = sqrt(x^2 + y^2 + z^2) - 0.3
        r = abs(phi[i, j, k]) / 0.2   # smooth, non-spherical bump on the surface band
        d[i, j, k] = r < 1 ? 0.5 * (1 + cos(pi * r)) * (1 + 0.5 * x / 0.3) : 0.0
    end
    d ./= maximum(abs, d)
    return Fixture((32, 24, 24), 20.0, 0.1, origin, h, (-1.0, -1.0, -1.0), 0.1, -10.0, phi, d, steps)
end

# --- model: loss(phi) = instantaneous force components after `steps` steps -------------------------------------------------
real_type(::Type{T}) where {T<:Real} = T
real_type(::Type{<:FD.Dual{Tag,V}}) where {Tag,V} = V

function build_sim(fx::Fixture, phi::AbstractArray{S,3}, ::Type{T}) where {S,T}
    FS = real_type(T)
    grid = GridSDF(phi, fx.origin_m, fx.h_m, size(phi), 3.0, 0.15)  # positional ctor: no margin gate on Dual values
    floor_body = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, FS.(fx.flow_origin_m), FS(fx.world_per_solver), FS(0.25))
    ground = CFDSDFWaterLily.V16MovingGroundBody(FS(fx.ground_z), FS(1))
    body = CFDSDFWaterLily.CandidateCWaterLilyBody(floor_body, ground; normal_floor=FS(0.25),
                                                   transition_width=FS(1.1444091796875e-4))
    uBC(i, x, t) = i == 1 ? one(eltype(x)) : zero(eltype(x))
    return WaterLily.Simulation(fx.dims, uBC, FS(fx.L); U=one(FS), ν=FS(fx.ν), exitBC=true, body, T=T, mem=Array)
end

function forces(fx::Fixture, phi::AbstractArray, ::Type{T}) where {T}
    sim = build_sim(fx, phi, T)
    for _ in 1:fx.steps
        WaterLily.sim_step!(sim; remeasure=false)
    end
    f = WaterLily.total_force(sim)
    return (f[1], f[3])
end

# value + tangent of (Fx, Fz) along d via Dual numbers
function ad_forces(fx::Fixture, ::Type{V}) where {V<:Real}
    tag = FD.Tag(forces, V)
    DT = FD.Dual{typeof(tag),V,1}
    phi_dual = DT.(V.(fx.phi), FD.Partials.(tuple.(V.(fx.d))))
    fxd, fzd = forces(fx, phi_dual, DT)
    return (FD.value(fxd), FD.value(fzd)), (only(FD.partials(fxd)), only(FD.partials(fzd)))
end

# centered finite difference of the same discrete model (perturbation rounded to the storage type like the oracle)
function fd_forces(fx::Fixture, ::Type{V}, eps::Float64) where {V<:Real}
    fp = forces(fx, V.(fx.phi .+ eps .* fx.d), V)
    fm = forces(fx, V.(fx.phi .- eps .* fx.d), V)
    return ((fp[1] - fm[1]) / (2eps), (fp[2] - fm[2]) / (2eps))
end

function run_tier(fx::Fixture, ::Type{V}, fd_eps::Vector{Float64}) where {V<:Real}
    out = Dict{String,Any}("real_type" => string(V), "steps" => fx.steps, "poisson" => collect(POIS[]))
    base = forces(fx, V.(fx.phi), V)
    out["primal_fx"], out["primal_fz"] = Float64(base[1]), Float64(base[2])
    try
        t0 = time()
        val, tan = ad_forces(fx, V)
        out["ad_ok"] = true
        out["ad_seconds_incl_jit"] = time() - t0
        out["ad_primal_fx"], out["ad_primal_fz"] = Float64(val[1]), Float64(val[2])
        out["ad_primal_equals_plain_primal"] = (val[1] == base[1]) && (val[2] == base[2])
        out["ad_primal_rel_diff"] = max(abs(Float64(val[1] - base[1])) / abs(Float64(base[1])),
                                        abs(Float64(val[2] - base[2])) / abs(Float64(base[2])))
        out["ad_dfx"], out["ad_dfz"] = Float64(tan[1]), Float64(tan[2])
        out["ad_tangent_finite"] = isfinite(tan[1]) && isfinite(tan[2])
    catch err
        out["ad_ok"] = false
        out["ad_error"] = first(sprint(showerror, err), 600)
        out["fd"] = Any[]
        return out
    end
    out["fd"] = [Dict("eps_m" => e, "dfx" => Float64(g[1]), "dfz" => Float64(g[2]),
                      "rel_diff_dfx" => abs(out["ad_dfx"] - g[1]) / max(abs(g[1]), floatmin(Float64)),
                      "rel_diff_dfz" => abs(out["ad_dfz"] - g[2]) / max(abs(g[2]), floatmin(Float64)))
                 for e in fd_eps for g in (fd_forces(fx, V, e),)]
    return out
end

# --- minimal JSON writer (no JSON package in the project) -----------------------------------------------------------------
json(x::Nothing) = "null"
json(x::Bool) = x ? "true" : "false"
json(x::Integer) = string(x)
json(x::AbstractFloat) = isfinite(x) ? string(x) : "null"
json(x::AbstractString) = "\"" * replace(x, "\\" => "\\\\", "\"" => "\\\"", "\n" => "\\n") * "\""
json(x::AbstractVector) = "[" * join(json.(x), ",") * "]"
json(x::Tuple) = json(collect(x))
json(x::AbstractDict) = "{" * join([json(string(k)) * ":" * json(x[k]) for k in sort(collect(keys(x)); by=string)], ",") * "}"

function canonical_fixture(phi_path, phi_sha, dir_path, dir_sha; steps)
    shape = (121, 65, 49)
    function load(path, sha)
        raw = read(path)
        bytes2hex(sha256(raw)) == sha || error("SHA mismatch: $path")
        length(raw) == prod(shape) * 4 || error("byte length mismatch: $path")
        Float64.(reshape(copy(reinterpret(Float32, raw)), shape))
    end
    phi, d = load(phi_path, phi_sha), load(dir_path, dir_sha)
    all(isfinite, phi) && all(isfinite, d) && maximum(abs, d) == 1.0 || error("phi/direction not finite or max|d| != 1")
    origin, h = (-1.0, -0.8, -0.6), (0.025, 0.025, 0.025)
    return Fixture((150, 72, 54), 24.0, 0.3, origin, h, (-2.5, -1.2, -0.9), 1 / 30, 0.0, phi, d, steps)
end

function margins(fx::Fixture, eps_list)  # registered 0.15 m clearance gate checked on the primal phi (Dual values bypass the ctor gate)
    return Dict(string(e) => minimum(zero_level_margin_m(fx.phi .+ s * e .* fx.d, fx.origin_m, fx.h_m) for s in (-1.0, 0.0, 1.0)) for e in eps_list)
end

function sweep(fx::Fixture)
    POIS[] = (1e-10, 1000)
    ad_val, ad = ad_forces(fx, Float64)
    out = Dict{String,Any}("poisson" => collect(POIS[]), "steps" => fx.steps, "ad_dfx" => ad[1], "ad_dfz" => ad[2])
    S(e) = (fp = forces(fx, fx.phi .+ e .* fx.d, Float64); fm = forces(fx, fx.phi .- e .* fx.d, Float64);
            (((fp[1] - fm[1]) / 2, (fp[2] - fm[2]) / 2)))
    fine = [10.0^(-k) for k in 7:-1:2]
    out["decade_sweep"] = [Dict("eps_m" => e, "fd_dfx" => S(e)[1] / e, "fd_dfz" => S(e)[2] / e) for e in fine]
    ladder = exp.(range(log(2e-3), log(2e-2); length=6))   # same 0.02-0.2 h_SDF ratio as the FD-08 ladder (h = 0.1 m here)
    sx, sz = Float64[], Float64[]
    for e in ladder
        v = S(e); push!(sx, v[1]); push!(sz, v[2])
    end
    X = hcat(ladder, ladder .^ 3)
    out["ladder_eps_m"] = ladder
    for (name, svals, adv) in (("fx", sx, ad[1]), ("fz", sz, ad[2]))
        beta = X \ svals
        out["ladder_fit_" * name] = Dict("g" => beta[1], "c" => beta[2], "S" => svals,
                                          "rel_diff_g_vs_ad" => abs(beta[1] - adv) / abs(adv),
                                          "residual_rms" => sqrt(sum(abs2, X * beta - svals) / (length(svals) - 2)))
    end
    return out
end

function main()
    length(ARGS) == 2 && ARGS[1] == "toy64sweep" || error("usage: toy64sweep <output.json>")
    outpath = ARGS[2]
    isfile(outpath) && error("refusing to overwrite $outpath")
    steps = parse(Int, get(ENV, "SPIKE_STEPS", "3"))
    result = Dict{String,Any}("tier" => "toy64sweep", "evidence_class" => "cpu_forward_ad_post_hoc_diagnostic_unregistered",
        "julia" => string(VERSION), "waterlily" => string(pkgversion(WaterLily)),
        "claim_limit" => "post-hoc diagnostic on the toy; not part of the pre-registered decision rule",
        "qualification_flags" => Dict(k => false for k in ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")))
    result["sweep"] = sweep(toy_fixture(; steps))
    open(outpath, "w") do io
        write(io, json(result), "\n")
    end
    println("wrote ", outpath)
end

main()
