using Test

include(joinpath(@__DIR__, "..", "src", "SurfaceFluxQuadrature.jl"))
using .SurfaceFluxQuadrature

@testset "surface quadrature projects vertices before area weights" begin
    plane(x) = (x[3] - 2.0, (0.0, 0.0, 1.0))
    vertices = [(0.0, 0.0, 1.7), (1.0, 0.0, 2.2), (0.0, 1.0, 1.9)]
    seed_flux = ((0.0, 0.0, 2.0),)
    results = [refined_surface_quadrature(vertices, [(1, 2, 3)], plane; level)
               for level in 0:2]
    for result in results
        @test result.area_m2 ≈ 0.5 atol=1e-12
        @test all(p -> p[3] == 2.0, result.vertices)
        @test all(n -> n == (0.0, 0.0, 1.0), result.geometric_normals)
        @test sum(result.area_weights_m2 .* [sum(seed_flux[1][d] * n[d] for d in 1:3)
                                              for n in result.geometric_normals]) ≈ 1.0 atol=1e-12
    end
    @test [r.quadrature_point_count for r in results] == [3, 12, 48]
end

@testset "analytic sphere method control and fail-closed coverage" begin
    sphere(x) = begin
        r = sqrt(sum(c -> c^2, x))
        (r - 1.0, (x[1] / r, x[2] / r, x[3] / r))
    end
    vertices = [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]
    faces = [(1, 3, 5), (3, 2, 5), (2, 4, 5), (4, 1, 5),
             (3, 1, 6), (2, 3, 6), (4, 2, 6), (1, 4, 6)]
    coarse = refined_surface_quadrature(vertices, faces, sphere; level=0)
    fine = refined_surface_quadrature(vertices, faces, sphere; level=2)
    @test all(p -> isapprox(sqrt(sum(c -> c^2, p)), 1.0; atol=1e-10), fine.points)
    @test all(n -> isapprox(sqrt(sum(c -> c^2, n)), 1.0; atol=1e-12), fine.geometric_normals)
    @test fine.area_m2 > coarse.area_m2
    @test abs(fine.area_m2 - coarse.area_m2) > 0 # refinement indicator only
    @test_throws ErrorException refined_surface_quadrature(vertices, faces,
        x -> (1.0, (0.0, 0.0, 0.0)); level=0)
end
