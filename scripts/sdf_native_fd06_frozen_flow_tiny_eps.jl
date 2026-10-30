# [tiny-epsilon variant: perturbation phi = base + eps*direction for eps in FD06_TINY_EPS (comma list, signed)] FD-06 (#37) solver-free-ish diagnostic: geometry-only response of the WaterLily pressure and viscous
# force integrals to the registered FD-05/FD-06 phi perturbations on a FROZEN flow snapshot.
#
# The flow (baseline v17, flow_24, body normal floor 0.25 in the solve) is advanced once to each snapshot time;
# at every snapshot the force integrals are re-evaluated with the flow held fixed for the baseline and all 30
# perturbed phi, and for several body normal floors (tau = 0: historical n = g/|g|).  If the centered slope
# (F(+eps) - F(-eps)) / (2 eps) is smooth in eps here, the force-integral map is not the source of the plateau
# deviation; the rest must come from the flow-solve response.  Diagnostic only; CPU, Float32 like the T4 job.
#
# usage: julia -t auto --project=julia/CFDSDFWaterLily scripts/sdf_native_fd06_frozen_flow_response.jl \
#          <dataset_dir> <out.csv> <taus comma list> <snapshot tU/L> [<snapshot> ...]
using WaterLily, Random
const SRC = joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16W4Sensitivity.jl"))
Base.include(CFDSDFWaterLily, joinpath(SRC, "WaterLilyNormalFloorBody.jl"))
using .CFDSDFWaterLily.V16W4Sensitivity: w4_cases

const SHAPE = (121, 65, 49)
const SDF_ORIGIN = (-1.0, -0.8, -0.6)
const HD = 0.025
const CASE = only(filter(c -> c.case_id == "flow_24", w4_cases(SDF_ORIGIN, HD)))
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
const EPSILONS = ("0p0005", "0p0010", "0p0025", "0p0050", "0p0100")

read_phi(path) = reshape(copy(reinterpret(Float32, read(path))), SHAPE)
make_grid(phi) = GridSDF(phi; origin = SDF_ORIGIN, h = (HD, HD, HD), outside_value = 3.0, margin_m = 0.15)
function body(grid, tau)
    fo = Float32.(CASE.flow_origin_m); fs = Float32(CASE.flow_spacing_m)
    tau == 0 ? CFDSDFWaterLily.GridSDFWaterLilyBody(grid, fo, fs) :
               CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, fo, fs, Float32(tau))
end

function main()
    dir, out = ARGS[1], ARGS[2]
    taus = parse.(Float64, split(ARGS[3], ","))
    times = parse.(Float64, ARGS[4:end])
    base_phi = read_phi(joinpath(dir, "canonical_v17_phi_f4_fortran.raw"))
    cases = [("baseline", "0", "0", base_phi)]
    for d in ("D1_filtered_seed11", "D2_filtered_seed2026"), e in parse.(Float64, split(ENV["FD06_TINY_EPS"], ","))
        dirarr = permutedims(reshape(copy(reinterpret(Float32, read(joinpath(dir, "directions", d * ".f4-c.raw")))), reverse(SHAPE)), (3, 2, 1))
        push!(cases, (d, string(e), "x", Float32.(Float64.(base_phi) .+ e .* Float64.(dirarr))))
    end
    if haskey(ENV, "FD06_NOISE_AMPS")  # extra cases: seeded white noise of the given amplitudes [m] on every node
        for seed in 1:3, a in parse.(Float64, split(ENV["FD06_NOISE_AMPS"], ","))
            rng = MersenneTwister(seed)
            push!(cases, ("NOISE$seed", string(a), "x", Float32.(Float64.(base_phi) .+ a .* randn(rng, Float64, SHAPE))))
        end
    end
    solve_body = body(make_grid(base_phi), 0.25)
    ground = CFDSDFWaterLily.V16MovingGroundBody(0.0f0, 1.0f0)
    sim = WaterLily.Simulation(CASE.flow_dims, CFDSDFWaterLily.v16_native_far_field_uBC,
        Float32(CASE.solver_length); U = Float32(CASE.solver_velocity), ν = Float32(CASE.solver_viscosity),
        exitBC = true, body = solve_body + ground, T = Float32, mem = Array)
    open(out, "w") do io
        println(io, "snapshot_t,direction,eps,sign,tau,pfx,pfy,pfz,vfx,vfy,vfz")
        for t in times
            while sim_time(sim) < t
                sim_step!(sim)
            end
            println(stderr, "snapshot sim_time=", sim_time(sim))
            for (d, e, s, phi) in cases, tau in taus
                b = body(make_grid(phi), tau)
                p = -WaterLily.pressure_force(sim.flow, b); v = -WaterLily.viscous_force(sim.flow, b)
                println(io, sim_time(sim), ",", d, ",", e, ",", s, ",", tau, ",", p[1], ",", p[2], ",", p[3], ",", v[1], ",", v[2], ",", v[3])
            end
            flush(io)
        end
    end
end
main()
