# FD-04 (#36) diagnostic: full CPU solve, raw bridge vs diagnostic-regularized normal
# in BOTH the flow solve (BDIM) and the force integral.  Short horizon: this is a
# scaling diagnostic (does the +/- pair signal shrink with eps?), not a qualified
# force value.  Bridge source is not modified.  TAU is declared in the included
# regularized-body file before any response is seen.
#
# usage: julia -t auto --project=julia/CFDSDFWaterLily scripts/sdf_native_fd04_full_response.jl \
#          <dataset_dir> <out.csv> <t_end> <window_start>

using WaterLily
const SRC = joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, joinpath(SRC, "V16PhysicalProfile.jl"))
include(joinpath(@__DIR__, "sdf_native_fd04_regularized_body.jl"))

const SHAPE = (61, 33, 25)
const DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
const EPSILONS = ("0p0005", "0p0025", "0p0100")
read_phi(path) = reshape(copy(reinterpret(Float32, read(path))), SHAPE)
make_grid(phi) = GridSDF(phi; origin = (-1.0, -0.8, -0.6), h = (0.05, 0.05, 0.05),
    outside_value = 3.0, margin_m = 0.15)

function run_case(phi, variant, t_end, w0)
    grid = make_grid(phi)
    fo = Float32.(CFDSDFWaterLily.V16_PROFILE_FLOW_ORIGIN_M)
    cand = variant == :raw ? CFDSDFWaterLily.GridSDFWaterLilyBody(grid, fo, 0.05f0) :
                              RegularizedBody(grid, fo, 0.05f0)
    ground = CFDSDFWaterLily.V16MovingGroundBody(0.0f0, 1.0f0)
    sim = CFDSDFWaterLily.build_v16_physical_profile_simulation((combined = cand + ground,))
    acc = zeros(3); n = 0
    while sim_time(sim) < t_end
        sim_step!(sim)
        if sim_time(sim) >= w0
            f = -(WaterLily.pressure_force(sim.flow, cand) + WaterLily.viscous_force(sim.flow, cand))
            acc .+= Float64.(f); n += 1
        end
    end
    return acc ./ n
end

function main()
    dir, out = ARGS[1], ARGS[2]
    t_end, w0 = parse(Float64, ARGS[3]), parse(Float64, ARGS[4])
    cases = [("baseline", "0", "0", read_phi(joinpath(dir, "canonical_v16_phi_f4_fortran.raw")))]
    for d in DIRECTIONS, e in EPSILONS, s in ("minus", "plus")
        push!(cases, (d, e, s, read_phi(joinpath(dir, "perturbations", "$(d)__eps_$(e)m__$(s).phi-f4-fortran.raw"))))
    end
    open(out, "w") do io
        println(io, "t_end,window_start,direction,eps,sign,variant,fx,fy,fz")
        for (d, e, s, phi) in cases, v in (:raw, :reg)
            f = run_case(phi, v, t_end, w0)
            println(io, t_end, ",", w0, ",", d, ",", e, ",", s, ",", v, ",", f[1], ",", f[2], ",", f[3])
            flush(io)
            println(stderr, d, " ", e, " ", s, " ", v, " done")
        end
    end
end

main()
