using Test

include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m

@testset "FD-08 CPU constructor uses one spatial scalar type" begin
    origin = (-0.5, -0.5, -0.5)
    h = (0.05, 0.05, 0.05)
    coordinates = ntuple(axis -> origin[axis] .+ (0:20) .* h[axis], 3)
    phi = Float32[
        sqrt(x^2 + y^2 + z^2) - 0.2
        for x in coordinates[1], y in coordinates[2], z in coordinates[3]
    ]

    @test zero_level_margin_m(phi, origin, h) >= 0.15
    grid = GridSDF(phi; origin, h, outside_value=3.0, margin_m=0.15)
    @test grid.margin_m === 0.15
end
