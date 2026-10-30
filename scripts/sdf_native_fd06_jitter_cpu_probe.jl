# FD-06 (#37) diagnostic, CPU only [jitter variant: arbitrary perturbation scales, run_id = baseline | <direction>@<signed eps_m>]. Original purpose: does a normal floor n = g / max(|g|, TAU) remove the
# eps-independent +/- offset seen in FD-05?  Same flow_24 W4 case, same body map and same
# force sampling (every 8 steps) as the registered FD job; short horizon because the +/- pair
# difference is already fixed by tU/L 5-20 in the FD-05 raw data.  Not a qualified force.
# TAU is fixed before any response is seen: 0.25 = the repository's registered flat-gradient
# threshold (FLAT_GRADIENT_THRESHOLD), not tuned on forces.
#
# usage: julia -t auto --project=julia/CFDSDFWaterLily scripts/sdf_native_fd06_normal_floor_cpu_probe.jl \
#          <dataset_dir> <out_dir> <t_end> <variant:run_id> ...   (variant = raw | floor; run_id = baseline | <perturbation id>)
using WaterLily, Random
const SRC = joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16W4Sensitivity.jl"))
using .CFDSDFWaterLily.V16W4Sensitivity: w4_cases

const TAU = parse(Float64, get(ENV, "FD06_TAU", "0.25"))
const SHAPE = (121, 65, 49)
const SDF_ORIGIN = (-1.0, -0.8, -0.6)
const HD = 0.025
const CASE = only(filter(c -> c.case_id == "flow_24", w4_cases(SDF_ORIGIN, HD)))

struct FloorBody{A,T,S} <: WaterLily.AbstractBody
    grid::GridSDF{A,T}
    world_origin_m::NTuple{3,S}
    world_per_solver::S
end

function WaterLily.measure(body::FloorBody, x::AbstractVector{S}, t; fastd² = S(Inf)) where {S}
    s = body.world_per_solver; o = body.world_origin_m
    x_m = (o[1] + s * x[1], o[2] + s * x[2], o[3] + s * x[3])
    d = S(sdf_at_world(body.grid, x_m) / s)
    d * d > fastd² && return (d, zero(x), zero(x))
    _, g = sdf_value_gradient_at_world(body.grid, x_m)
    m = max(sqrt(g[1] * g[1] + g[2] * g[2] + g[3] * g[3]), TAU)
    n = collect((S(g[1] / m), S(g[2] / m), S(g[3] / m)))
    return (d, n, zero(x))
end

function read_phi(dir, run_id)
    base = reshape(copy(reinterpret(Float32, read(joinpath(dir, "canonical_v17_phi_f4_fortran.raw")))), SHAPE)
    run_id == "baseline" && return base
    direction, eps = split(run_id, "@")
    if startswith(direction, "NOISE")  # random phi noise of amplitude eps [m] on every node (seeded)
        rng = MersenneTwister(parse(Int, direction[6:end]))
        return Float32.(Float64.(base) .+ parse(Float64, eps) .* randn(rng, Float64, SHAPE))
    end
    # directions are stored C-order float32; the phi grid is Fortran-order in memory (SHAPE indexing is the same grid)
    d = permutedims(reshape(copy(reinterpret(Float32, read(joinpath(dir, "directions", direction * ".f4-c.raw")))), reverse(SHAPE)), (3, 2, 1))
    return Float32.(Float64.(base) .+ parse(Float64, eps) .* Float64.(d))
end

function run_case(phi, variant, t_end, io)
    grid = GridSDF(phi; origin = SDF_ORIGIN, h = (HD, HD, HD), outside_value = 3.0, margin_m = 0.15)
    FT = get(ENV, "FD06_FLOAT", "32") == "64" ? Float64 : Float32  # solver/body arithmetic (diagnostic switch)
    fo = FT.(CASE.flow_origin_m); fs = FT(CASE.flow_spacing_m)
    cand = variant == "raw" ? CFDSDFWaterLily.GridSDFWaterLilyBody(grid, fo, fs) : FloorBody(grid, fo, fs)
    ground = CFDSDFWaterLily.V16MovingGroundBody(FT(0), FT(1))
    sim = WaterLily.Simulation(CASE.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
        FT(CASE.solver_length); U = FT(CASE.solver_velocity), ν = FT(CASE.solver_viscosity),
        exitBC = true, body = cand + ground, T = FT, mem = Array)
    println(io, "step,t_u_l,drag_solver,downforce_solver,pressure_fx_solver,viscous_fx_solver")
    step = 0
    while sim_time(sim) < t_end
        sim_step!(sim); step += 1
        if step % 8 == 0
            p = -WaterLily.pressure_force(sim.flow, cand); v = -WaterLily.viscous_force(sim.flow, cand)
            t = p + v
            println(io, step, ",", sim_time(sim), ",", t[1], ",", -t[3], ",", p[1], ",", v[1])
        end
    end
end

function main()
    dir, outdir, t_end = ARGS[1], ARGS[2], parse(Float64, ARGS[3])
    mkpath(outdir)
    for spec in ARGS[4:end]
        variant, run_id = split(spec, ":"; limit = 2)
        t0 = time()
        open(joinpath(outdir, "$(variant)__$(run_id).csv"), "w") do io
            run_case(read_phi(dir, run_id), variant, t_end, io)
        end
        println(stderr, spec, " done ", round(time() - t0; digits = 1), " s")
    end
end
# Optional (FD06_POIS_TOL): tighten the WaterLily multigrid pressure-solver stopping tolerance (default 1e-4, 32 iterations)
# to test whether the response jitter under tiny perturbations is solver-tolerance noise.  Same algorithm as
# WaterLily.solver!(::MultiLevelPoisson); only tol/itmx differ.  Diagnostic only.
if haskey(ENV, "FD06_POIS_TOL")
    const POIS_TOL = parse(Float64, ENV["FD06_POIS_TOL"])
    const POIS_ITMX = parse(Int, get(ENV, "FD06_POIS_ITMX", "200"))
    @eval WaterLily function solver!(ml::MultiLevelPoisson{T}; tol = $POIS_TOL, itmx = $POIS_ITMX) where T
        p = ml.levels[1]
        residual!(p); r₂ = L₂(p); ω = T(1)
        nᵖ = 0
        while nᵖ < itmx
            Vcycle!(ml; ω)
            smooth!(p; ω)
            rnew = L₂(p); nᵖ += 1
            if rnew ≥ r₂
                ω = max(0.2, 0.9ω) |> T
            elseif rnew < r₂
                ω = min(1.0, 1.02ω) |> T
            end
            r₂ = rnew
            r₂ < tol && break
        end
        perBC!(p.x, p.perdir)
        push!(ml.n, nᵖ)
    end
end

main()
