# normal_floor selftest (#37): default 0 is the historical bridge; floor > 0 gives g/max(|g|, floor).
# Run: julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_normal_floor.jl
include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily

# a * (r - 0.3) around the box centre: |grad| ~ a away from the centre, solid inside r < 0.3
cone(a) = GridSDF(Float32[a * (sqrt((0.1 * (i - 6))^2 + (0.1 * (j - 6))^2 + (0.1 * (k - 6))^2) - 0.3)
    for i in 1:11, j in 1:11, k in 1:11]; origin = (0.0, 0.0, 0.0), h = (0.1, 0.1, 0.1),
    outside_value = 3.0, margin_m = 0.0)
mk(a, floor...) = CFDSDFWaterLily.GridSDFWaterLilyBody(cone(a), (0.0f0, 0.0f0, 0.0f0), 0.1f0, floor...)
probe = Float32[8.15, 5.0, 5.0]  # solver coordinates; world x = 0.815, off node planes
normal(body) = WaterLily.measure(body, probe, 0.0f0)[2]
gmag(a) = sqrt(sum(abs2, sdf_value_gradient_at_world(cone(a), (0.815, 0.5, 0.5))[2]))

ok = true
chk(name, cond) = (println("RESULT ", name, " ", cond ? "PASS" : "FAIL"); global ok &= cond)
chk("default_is_zero_floor", mk(0.1).normal_floor == 0f0)
chk("default_unit_normal_small_gradient", isapprox(sqrt(sum(abs2, normal(mk(0.1)))), 1.0; atol = 1e-5))
chk("floor_shrinks_small_gradient", isapprox(sqrt(sum(abs2, normal(mk(0.1, 0.25f0)))), gmag(0.1) / 0.25; rtol = 1e-4) && gmag(0.1) < 0.25)
chk("floor_leaves_large_gradient", isapprox(normal(mk(1.0, 0.25f0)), normal(mk(1.0)); atol = 1e-6))
chk("floor_same_direction", isapprox(normal(mk(0.1, 0.25f0)) ./ sqrt(sum(abs2, normal(mk(0.1, 0.25f0)))), normal(mk(0.1)); atol = 1e-5))
ok || exit(1)
