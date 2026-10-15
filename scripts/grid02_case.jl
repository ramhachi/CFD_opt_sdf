# GRID-02 case selection and validation. Included by waterlily_grid02_job.jl after
# `using .CFDSDFWaterLily.V16W4Sensitivity`; needs only that module (no CUDA).
# V16W4Sensitivity.w4_cases/validate_w4_case know only 16/24/32, so flow_16/flow_48 are built
# with build_case and checked against an explicit dimension table.

const GRID02_CELLS = Dict("flow_16" => 16, "flow_48" => 48)
const GRID02_DIMS = Dict("flow_16" => (100, 48, 36), "flow_48" => (300, 144, 108))

function grid02_case_id()
    haskey(ENV, "GRID02_CASE") || error("GRID02_CASE must be set to flow_16 or flow_48")
    id = ENV["GRID02_CASE"]
    haskey(GRID02_CELLS, id) || error("GRID02_CASE must be flow_16 or flow_48, got $id")
    return id
end

grid02_case(origin_m, spacing_m, id=grid02_case_id()) =
    V16W4Sensitivity.build_case(id, GRID02_CELLS[id], V16W4Sensitivity.BASE_MAX_M,
        origin_m, spacing_m)

function validate_grid02_case(case; canonical_design_origin_m, canonical_design_spacing_m,
                              dims_table=GRID02_DIMS)
    n = case.cells_per_reference_length
    haskey(GRID02_CELLS, case.case_id) && GRID02_CELLS[case.case_id] == n ||
        error("GRID-02 case id / resolution mismatch")
    case.flow_origin_m == V16W4Sensitivity.FLOW_ORIGIN_M || error("W4 flow origin drift")
    case.canonical_design_origin_m == Tuple(canonical_design_origin_m) ||
        error("canonical SDF origin differs from registered state")
    case.physical_box_max_m == V16W4Sensitivity.BASE_MAX_M || error("W4 physical box drift")
    case.canonical_design_spacing_m == canonical_design_spacing_m ||
        error("canonical design spacing differs from registered state")
    case.flow_dims == dims_table[case.case_id] ||
        error("W4 flow dimensions drift for $(case.case_id)")
    case.solver_length == n || error("W4 solver reference length drift")
    isapprox(case.solver_viscosity, n / 80; atol=1e-12, rtol=0) ||
        error("W4 viscosity does not preserve Re=80")
    isapprox(case.reynolds, V16W4Sensitivity.REYNOLDS; atol=1e-12, rtol=0) ||
        error("W4 Reynolds drift")
    return nothing
end
