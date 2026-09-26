# W2a bridge selftest: gradient, margin, geometry agreement, force sign.
# Run: julia --threads=auto --project=julia/CFDSDFWaterLily \
#        julia/CFDSDFWaterLily/test/test_waterlily_bridge.jl

include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily, Printf

FAILED = false
function verdict(name, ok, value)
    @printf("RESULT %s %s %s\n", name, ok ? "PASS" : "FAIL", value)
    ok || global FAILED = true
end

grid = CFDSDFWaterLily.sphere_phi_fixture()
margin = zero_level_margin_m(grid.phi, grid.origin, grid.h)
verdict("fixture_margin", margin >= CFDSDFWaterLily.RUN_MARGIN_M, @sprintf("%.9e", margin))

# probes kept off lattice node planes so the centered FD stays inside one
# trilinear cell (the interpolant gradient is discontinuous across cells)
points = [
    (0.25 + 0.37, 0.11, -0.21),
    (0.327, 0.031, 0.542),
    (0.613, 0.307, 0.093),
    (-0.093, -0.187, 0.061),
]
max_grad_diff = let acc = 0.0
    for x in points
        _, g = sdf_value_gradient_at_world(grid, x)
        for i in 1:3
            d = 1e-6
            xp = collect(x); xp[i] += d
            xm = collect(x); xm[i] -= d
            fd = (sdf_at_world(grid, Tuple(xp)) - sdf_at_world(grid, Tuple(xm))) / (2d)
            acc = max(acc, abs(g[i] - fd))
        end
    end
    acc
end
verdict("gradient_vs_fd", max_grad_diff <= 1e-8, @sprintf("%.3e", max_grad_diff))

ab = CFDSDFWaterLily.analytic_sphere_body()
gb = CFDSDFWaterLily.grid_sdf_sphere_body()
scale = CFDSDFWaterLily.WORLD_PER_SOLVER
max_dd_m, max_dn = let acc_dd = 0.0, acc_dn = 0.0
    for p in ([32.0f0, 32.0f0, 40.5f0], [32.0f0, 36.0f0, 36.0f0],
              [24.5f0, 32.0f0, 32.0f0], [28.0f0, 34.0f0, 37.0f0])
        da, na, _ = WaterLily.measure(ab, p, 0.0f0)
        db, nb, _ = WaterLily.measure(gb, p, 0.0f0)
        acc_dd = max(acc_dd, abs(Float64(db - da) * scale))
        acc_dn = max(acc_dn, Float64(sqrt(sum(abs2, nb .- na))))
    end
    acc_dd, acc_dn
end
verdict("geometry_value_agreement_m", max_dd_m <= 2e-3, @sprintf("%.3e", max_dd_m))
verdict("geometry_normal_agreement", max_dn <= 0.1, @sprintf("%.3e", max_dn))

sim = CFDSDFWaterLily.build_sphere_sim(ab)
sim_step!(sim)
fp = CFDSDFWaterLily.pressure_force_on_body(sim)
fv = CFDSDFWaterLily.viscous_force_on_body(sim)
force = fp + fv
verdict("one_step_force_finite",
    all(isfinite, force) && all(isfinite, sim.flow.u) && all(isfinite, sim.flow.p),
    @sprintf("%.3e", force[1]))
verdict("one_step_drag_positive", force[1] > 0.0, @sprintf("%.3e", force[1]))

exit(FAILED ? 1 : 0)
