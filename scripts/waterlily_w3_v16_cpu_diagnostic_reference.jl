# W3 v16 CPU-only reference for the all-zero-force CUDA diagnostic. It scans
# the registered flow lattice using candidate, ground, and union bodies, then
# records solver-free fields and one CPU primal step. Diagnostic only; no
# W3 qualification is evaluated.

using SHA
using WaterLily
include(joinpath(pwd(), "julia/CFDSDFWaterLily/src/CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
Base.include(CFDSDFWaterLily, joinpath(pwd(), "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl"))

function run()
    expected_phi_sha = "9ed14a39a1456436ff40411c85ae54b04bfe28554ebe1b87677e7e9a62f632b7"
    dims = (100, 48, 36)
    h = 0.05f0
    bytes = read(path)
    phi_sha = bytes2hex(sha256(bytes))
    phi_sha == expected_phi_sha || error("phi SHA mismatch")
    phi = reshape(copy(reinterpret(Float32, bytes)), CFDSDFWaterLily.V16_PROFILE_POINT_SHAPE)
    measured_margin = zero_level_margin_m(phi, CFDSDFWaterLily.V16_CANONICAL_SDF_ORIGIN_M,
        (0.05,0.05,0.05))
    grid = GridSDF(phi; origin=CFDSDFWaterLily.V16_CANONICAL_SDF_ORIGIN_M,
        h=(0.05,0.05,0.05), outside_value=3.0, margin_m=0.15)
    bodies = CFDSDFWaterLily.v16_physical_profile_bodies(grid; T=Float32)
    counts = Dict(name => Dict("negative" => 0, "support" => 0,
        "support_nonzero_normal" => 0, "min" => Inf32, "max" => -Inf32)
        for name in ("candidate", "combined"))
    for k in 1:dims[3], j in 1:dims[2], i in 1:dims[1]
        point = WaterLily.loc(0, CartesianIndex(i+1,j+1,k+1), Float32)
        # WaterLily.loc returns flow-grid solver coordinates; pass them unchanged.
        solver = point
        for (name, body) in (("candidate", bodies.candidate), ("combined", bodies.combined))
            d, n, _ = WaterLily.measure(body, solver, 0f0; fastd²=1f0)
            row = counts[name]
            row["negative"] += d < 0f0
            row["min"] = min(row["min"], d)
            row["max"] = max(row["max"], d)
            if abs(d) <= 1f0
                row["support"] += 1
                row["support_nonzero_normal"] += sum(abs2, n) > 0f0
            end
        end
    end
    sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(bodies; T=Float32, mem=Array)
    WaterLily.measure!(sim.flow, sim.body)
    pressure0 = WaterLily.pressure_force(sim.flow, bodies.candidate)
    viscous0 = WaterLily.viscous_force(sim.flow, bodies.candidate)
    sigma_nonzero = count(!iszero, sim.flow.σ)
    mu0_nonzero = count(!iszero, sim.flow.μ₀)
    WaterLily.sim_step!(sim)
    pressure1 = WaterLily.pressure_force(sim.flow, bodies.candidate)
    viscous1 = WaterLily.viscous_force(sim.flow, bodies.candidate)
    return (phi_sha=phi_sha, measured_margin=measured_margin, counts=counts,
        initial_sigma_nonzero=sigma_nonzero, initial_mu0_nonzero=mu0_nonzero,
        initial_pressure=pressure0, initial_viscous=viscous0,
        t_after_one_step=WaterLily.sim_time(sim), finite_u=all(isfinite, sim.flow.u),
        finite_p=all(isfinite, sim.flow.p), pressure_after_one_step=pressure1,
        viscous_after_one_step=viscous1)
end

length(ARGS) == 2 || error("usage: waterlily_w3_v16_cpu_diagnostic_reference.jl <phi_fortran.raw> <output_dir>")
path, output_dir = ARGS
mkpath(output_dir)
result = run()
open(joinpath(output_dir, "w3_v16_cpu_diagnostic_reference.txt"), "w") do io
    show(io, MIME("text/plain"), result)
    println(io)
end
println("W3_V16_CPU_DIAGNOSTIC_REFERENCE ", result)
