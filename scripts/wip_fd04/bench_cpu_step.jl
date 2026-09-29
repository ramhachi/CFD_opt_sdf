using WaterLily
const R = "/Users/sota/projects/FomulaTMU/CFD2026_09/.claude/worktrees/agent-a9f204bc7344995b4/julia/CFDSDFWaterLily/src/"
include(R * "CFDSDFWaterLily.jl")
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, R * "V16PhysicalProfile.jl")
println("Threads ", Threads.nthreads(), " WL ", pkgversion(WaterLily))
raw = read("/private/tmp/claude-501/-Users-sota-projects-FomulaTMU-CFD2026-09/5c0b0b8e-2077-41f6-b6ff-a1db96c87326/scratchpad/canon_phi_f.raw")
phi = reshape(copy(reinterpret(Float32, raw)), (61, 33, 25))
grid = GridSDF(phi; origin=(-1.0, -0.8, -0.6), h=(0.05, 0.05, 0.05), outside_value=3.0, margin_m=0.15)
bodies = CFDSDFWaterLily.v16_physical_profile_bodies(grid)
sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(bodies)
t0 = time()
sim_step!(sim)
println("first step ", time() - t0)
t0 = time()
for _ in 1:20
    sim_step!(sim)
end
println("20 steps ", time() - t0, " sim_time ", sim_time(sim))
pf = -WaterLily.pressure_force(sim.flow, bodies.candidate)
println(pf)
