using Test

include(joinpath(@__DIR__, "..", "src", "V16W4Sensitivity.jl"))
using .V16W4Sensitivity

@testset "W4 canonical design grid is independent of flow grid" begin
    @test Tuple(case.case_id for case in V16W4_CASES) ==
        ("flow_16", "flow_24", "flow_32", "domain_xplus1m_16")

    cases = w4_cases((-1.0, -0.8, -0.6), 0.025)
    @test Tuple(case.flow_spacing_m for case in cases) ==
        (0.05, 1 / 30, 0.025, 0.05)
    @test all(case.canonical_design_spacing_m == 0.025 for case in cases)
    @test all(case.canonical_design_origin_m == (-1.0, -0.8, -0.6) for case in cases)
    @test Tuple(case.flow_dims for case in cases) ==
        ((100, 48, 36), (150, 72, 54), (200, 96, 72), (120, 48, 36))
    @test all(validate_w4_case(case; canonical_design_origin_m=(-1.0, -0.8, -0.6),
        canonical_design_spacing_m=0.025) === nothing for case in cases)

    @test all(case.canonical_design_spacing_m == 0.05 for case in V16W4_CASES)
    @test all(validate_v16_w4_case(case) === nothing for case in V16W4_CASES)
    @test_throws ErrorException validate_w4_case(cases[1];
        canonical_design_origin_m=(-1.0, -0.8, -0.6), canonical_design_spacing_m=0.05)
end

println("W4_SENSITIVITY_TESTS_DONE")
