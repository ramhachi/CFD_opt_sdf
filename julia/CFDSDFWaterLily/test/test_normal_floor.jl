# NormalFloorWaterLilyBody selftest (#37): floor 0 equals the historical body; floor > 0 gives g/max(|g|, floor).
# Run: julia --project=julia/CFDSDFWaterLily julia/CFDSDFWaterLily/test/test_normal_floor.jl
include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "src", "WaterLilyNormalFloorBody.jl"))
using WaterLily

# a * (r - 0.3) around the box centre: |grad| ~ a away from the centre, solid inside r < 0.3
cone(a) = GridSDF(Float32[a * (sqrt((0.1 * (i - 6))^2 + (0.1 * (j - 6))^2 + (0.1 * (k - 6))^2) - 0.3)
    for i in 1:11, j in 1:11, k in 1:11]; origin = (0.0, 0.0, 0.0), h = (0.1, 0.1, 0.1),
    outside_value = 3.0, margin_m = 0.0)
hist(a) = CFDSDFWaterLily.GridSDFWaterLilyBody(cone(a), (0.0f0, 0.0f0, 0.0f0), 0.1f0)
floored(a, f) = CFDSDFWaterLily.NormalFloorWaterLilyBody(cone(a), (0.0f0, 0.0f0, 0.0f0), 0.1f0, Float32(f))
probe = Float32[8.15, 5.0, 5.0]  # solver coordinates; world (0.815, 0.5, 0.5), off node planes
normal(body) = WaterLily.measure(body, probe, 0.0f0)[2]
len(v) = sqrt(sum(abs2, v))
gmag(a) = len(sdf_value_gradient_at_world(cone(a), (0.815, 0.5, 0.5))[2])

ok = true
chk(name, cond) = (println("RESULT ", name, " ", cond ? "PASS" : "FAIL"); global ok &= cond)
chk("floor0_equals_historical_body", normal(floored(0.1, 0)) == normal(hist(0.1)) && normal(floored(1.0, 0)) == normal(hist(1.0)))
chk("historical_unit_normal", isapprox(len(normal(hist(0.1))), 1.0; atol = 1e-5))
chk("floor_shrinks_small_gradient", gmag(0.1) < 0.25 && isapprox(len(normal(floored(0.1, 0.25))), gmag(0.1) / 0.25; rtol = 1e-4))
chk("floor_leaves_large_gradient", isapprox(normal(floored(1.0, 0.25)), normal(hist(1.0)); atol = 1e-6))
chk("floor_same_direction", isapprox(normal(floored(0.1, 0.25)) ./ len(normal(floored(0.1, 0.25))), normal(hist(0.1)); atol = 1e-5))
chk("value_and_velocity_unchanged", WaterLily.measure(floored(0.1, 0.25), probe, 0.0f0)[[1, 3]] == WaterLily.measure(hist(0.1), probe, 0.0f0)[[1, 3]])
ok || exit(1)
