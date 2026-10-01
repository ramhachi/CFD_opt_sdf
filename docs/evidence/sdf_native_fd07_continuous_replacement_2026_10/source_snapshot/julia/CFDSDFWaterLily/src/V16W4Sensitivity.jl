"""Registered W4 flow-grid and finite-box cases, independent of design spacing."""
module V16W4Sensitivity

export V16W4_CASES, v16_w4_case, validate_v16_w4_case
export w4_cases, validate_w4_case

const FLOW_ORIGIN_M = (-2.5, -1.2, -0.9)
const CANONICAL_SDF_ORIGIN_M = (-1.0, -0.8, -0.6)
const BASE_MAX_M = (2.5, 1.2, 0.9)
const EXTENDED_MAX_M = (3.5, 1.2, 0.9)
const DESIGN_SPACING_M = 0.05
const REFERENCE_LENGTH_M = 0.8
const REFERENCE_AREA_M2 = 0.64
const FREESTREAM_MPS = 1.0
const DENSITY_KG_M3 = 1.0
const DYNAMIC_VISCOSITY_PA_S = 0.01
const REYNOLDS = 80.0

function build_case(case_id, cells_per_reference_length, upper_m,
                    canonical_design_origin_m, canonical_design_spacing_m)
    flow_spacing_m = REFERENCE_LENGTH_M / cells_per_reference_length
    spans = ntuple(i -> upper_m[i] - FLOW_ORIGIN_M[i], 3)
    cell_dims = ntuple(i -> round(Int, spans[i] / flow_spacing_m), 3)
    all(i -> isapprox(cell_dims[i] * flow_spacing_m, spans[i]; atol=1e-12, rtol=0), 1:3) ||
        error("W4 physical bounds do not align with the flow grid: $case_id")
    solver_length = REFERENCE_LENGTH_M / flow_spacing_m
    solver_time_unit_s = flow_spacing_m / FREESTREAM_MPS
    solver_viscosity = (DYNAMIC_VISCOSITY_PA_S / DENSITY_KG_M3) *
        solver_time_unit_s / flow_spacing_m^2
    return (
        case_id = case_id,
        cells_per_reference_length = cells_per_reference_length,
        flow_spacing_m = flow_spacing_m,
        flow_dims = cell_dims,
        solver_length = solver_length,
        solver_time_unit_s = solver_time_unit_s,
        solver_velocity = 1.0,
        solver_viscosity = solver_viscosity,
        reynolds = DENSITY_KG_M3 * FREESTREAM_MPS * REFERENCE_LENGTH_M /
            DYNAMIC_VISCOSITY_PA_S,
        flow_origin_m = FLOW_ORIGIN_M,
        canonical_design_origin_m = Tuple(canonical_design_origin_m),
        physical_box_max_m = upper_m,
        canonical_design_spacing_m = Float64(canonical_design_spacing_m),
        reference_length_m = REFERENCE_LENGTH_M,
        reference_area_m2 = REFERENCE_AREA_M2,
        freestream_mps = FREESTREAM_MPS,
        density_kg_m3 = DENSITY_KG_M3,
        dynamic_viscosity_pa_s = DYNAMIC_VISCOSITY_PA_S,
    )
end

"""Build the fixed registered four-case matrix for a supplied canonical SDF lattice."""
function w4_cases(canonical_design_origin_m=CANONICAL_SDF_ORIGIN_M,
                  canonical_design_spacing_m=DESIGN_SPACING_M)
    return (
        build_case("flow_16", 16, BASE_MAX_M, canonical_design_origin_m,
                   canonical_design_spacing_m),
        build_case("flow_24", 24, BASE_MAX_M, canonical_design_origin_m,
                   canonical_design_spacing_m),
        build_case("flow_32", 32, BASE_MAX_M, canonical_design_origin_m,
                   canonical_design_spacing_m),
        build_case("domain_xplus1m_16", 16, EXTENDED_MAX_M, canonical_design_origin_m,
                   canonical_design_spacing_m),
    )
end

const V16W4_CASES = w4_cases()

function v16_w4_case(case_id::AbstractString)
    for case in V16W4_CASES
        case.case_id == case_id && return case
    end
    throw(ArgumentError("unregistered W4 case: $case_id"))
end

function validate_w4_case(case; canonical_design_origin_m=case.canonical_design_origin_m,
                           canonical_design_spacing_m=case.canonical_design_spacing_m)
    n = case.cells_per_reference_length
    expected_max = case.case_id == "domain_xplus1m_16" ? EXTENDED_MAX_M : BASE_MAX_M
    expected_dims = n == 16 ? (100, 48, 36) : n == 24 ? (150, 72, 54) : (200, 96, 72)
    if case.case_id == "domain_xplus1m_16"
        expected_dims = (120, 48, 36)
    end
    case.flow_origin_m == FLOW_ORIGIN_M || error("W4 flow origin drift")
    case.canonical_design_origin_m == Tuple(canonical_design_origin_m) ||
        error("canonical SDF origin differs from registered state")
    case.physical_box_max_m == expected_max || error("W4 physical box drift")
    case.canonical_design_spacing_m == canonical_design_spacing_m ||
        error("canonical design spacing differs from registered state")
    case.flow_dims == expected_dims || error("W4 flow dimensions drift for $(case.case_id)")
    case.solver_length == n || error("W4 solver reference length drift")
    isapprox(case.solver_viscosity, n / 80; atol=1e-12, rtol=0) ||
        error("W4 viscosity does not preserve Re=80")
    isapprox(case.reynolds, REYNOLDS; atol=1e-12, rtol=0) || error("W4 Reynolds drift")
    return nothing
end

"""Compatibility validator for the historical canonical v16 state."""
validate_v16_w4_case(case) = validate_w4_case(case)

foreach(validate_v16_w4_case, V16W4_CASES)

end # module
