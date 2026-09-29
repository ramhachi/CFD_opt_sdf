# FD-04 (#36) diagnostic: geometry-only (frozen-pressure) response of the WaterLily
# pressure force to the registered directional-FD phi perturbations.
#
# Chain under test: phi(+/-eps) -> trilinear gradient -> normalised bridge normal
# n = g/|g| -> pressure_force(flow, body) with the pressure field held fixed.
# Two bodies are evaluated on identical frozen flows:
#   raw : the production bridge (GridSDFWaterLilyBody), unchanged;
#   reg : a diagnostic-only copy with n = g / max(|g|, TAU); TAU is declared here,
#         before any response is seen, inside the empty gradient band (1e-6, 0.25).
# The bridge source is NOT modified.  CPU, Float32 arithmetic like the T4 job.
#
# usage: julia -t auto --project=julia/CFDSDFWaterLily scripts/sdf_native_fd04_frozen_pressure_response.jl \
#          <dataset_dir> <out.csv> <snapshot_sim_time> [<snapshot_sim_time> ...]

using WaterLily
const SRC = joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16PhysicalProfile.jl"))

const SHAPE = (61, 33, 25)
const ORIGIN = (-1.0, -0.8, -0.6)
const H = (0.05, 0.05, 0.05)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
const EPSILONS = ("0p0005", "0p0010", "0p0025", "0p0050", "0p0100")

include(joinpath(@__DIR__, "sdf_native_fd04_regularized_body.jl"))

read_phi(path) = reshape(copy(reinterpret(Float32, read(path))), SHAPE)
make_grid(phi) = GridSDF(phi; origin = ORIGIN, h = H, outside_value = 3.0, margin_m = 0.15)

function forces(flow, grid)
    fo = Float32.(FLOW_ORIGIN)
    raw = CFDSDFWaterLily.GridSDFWaterLilyBody(grid, fo, 0.05f0)
    reg = RegularizedBody(grid, fo, 0.05f0)
    return (raw = -WaterLily.pressure_force(flow, raw), reg = -WaterLily.pressure_force(flow, reg))
end

function main()
    length(ARGS) >= 3 || error("usage: <dataset_dir> <out.csv> <sim_time>...")
    dir, out = ARGS[1], ARGS[2]
    times = parse.(Float64, ARGS[3:end])
    base_phi = read_phi(joinpath(dir, "canonical_v16_phi_f4_fortran.raw"))
    cases = [("baseline", "0", "0", base_phi)]
    for d in DIRECTIONS, e in EPSILONS, s in ("minus", "plus")
        p = joinpath(dir, "perturbations", "$(d)__eps_$(e)m__$(s).phi-f4-fortran.raw")
        push!(cases, (d, e, s, read_phi(p)))
    end
    base_grid = make_grid(base_phi)
    bodies = CFDSDFWaterLily.v16_physical_profile_bodies(base_grid)
    sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(bodies)
    open(out, "w") do io
        println(io, "snapshot_t,direction,eps,sign,variant,fx,fy,fz")
        for t in times
            while sim_time(sim) < t
                sim_step!(sim)
            end
            println(stderr, "snapshot sim_time=", sim_time(sim), " steps done")
            for (d, e, s, phi) in cases
                f = forces(sim.flow, make_grid(phi))
                for v in (:raw, :reg)
                    a = getfield(f, v)
                    println(io, sim_time(sim), ",", d, ",", e, ",", s, ",", v, ",", a[1], ",", a[2], ",", a[3])
                end
            end
            flush(io)
        end
    end
end

main()
