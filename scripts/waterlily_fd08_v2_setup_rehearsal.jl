# Bounded, non-scientific input/Candidate-C/GPU setup rehearsal for FD-08 v2.
# It advances exactly one solver step and writes no force-history artifact.

using CUDA
using SHA

include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "OwnedV16Run.jl"))
using .CFDSDFW3RunOwnership: OwnedV16Run
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16PhysicalProfile.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "DeviceGridSDF.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "WaterLilyNormalFloorBody.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CandidateCWaterLilyBody.jl"))
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "V16W4Sensitivity.jl"))
using .CFDSDFWaterLily: V16_PROFILE_POINT_SHAPE, V16_CANONICAL_SDF_ORIGIN_M,
    V16_PROFILE_SPACING_M, V16MovingGroundBody, v16_native_far_field_uBC,
    NormalFloorWaterLilyBody, CandidateCWaterLilyBody
using .CFDSDFWaterLily.DeviceGridSDF
using .CFDSDFWaterLily.V16W4Sensitivity

length(ARGS) == 2 || error("usage: waterlily_fd08_v2_setup_rehearsal.jl <phi_fortran.raw> <output.json>")
phi_raw_path, output_path = ARGS
shape = Tuple(parse.(Int, split(ENV["W4_POINT_SHAPE"], ",")))
origin = Tuple(parse.(Float64, split(ENV["W4_CANONICAL_ORIGIN_M"], ",")))
spacing = parse(Float64, ENV["W4_CANONICAL_DESIGN_SPACING_M"])
expected_phi_f = ENV["W4_PHI_FORTRAN_SHA256"]
expected_phi_c = ENV["W4_PHI_C_ORDER_SHA256"]
expected_state = ENV["W4_STATE_SHA256"]
expected_margin = parse(Float64, ENV["W4_EXPECTED_MARGIN_M"])
margin_gate = parse(Float64, get(ENV, "W4_MARGIN_GATE_M", "0.15"))
margin_tol = parse(Float64, get(ENV, "W4_MARGIN_TOLERANCE_M", "1e-6"))

Base.ENDIAN_BOM == 0x04030201 || error("FD08 v2 requires a little-endian host runtime")
bytes = read(phi_raw_path)
length(bytes) == prod(shape) * sizeof(Float32) || error("Float32 phi byte length mismatch")
bytes2hex(sha256(bytes)) == expected_phi_f || error("Fortran-order phi SHA mismatch")
phi = reshape(copy(reinterpret(Float32, bytes)), shape)
phi_c = bytes2hex(sha256(reinterpret(UInt8, vec(permutedims(phi, (3, 2, 1))))))
phi_c == expected_phi_c || error("C-order phi SHA mismatch")
margin = zero_level_margin_m(phi, origin, (spacing, spacing, spacing))
abs(margin - expected_margin) <= margin_tol || error("CPU-side margin drift")
margin >= margin_gate || error("CPU-side margin is below gate")

grid = GridSDF(phi; origin=origin, h=(spacing, spacing, spacing), outside_value=3.0, margin_m=margin_gate)
owner = device_copy(grid)
roundtrip = device_roundtrip_sha(owner)
roundtrip == expected_phi_f || error("device round-trip phi SHA mismatch")
cases = Tuple(c for c in w4_cases(origin, spacing) if c.case_id == "flow_24")
length(cases) == 1 || error("expected exactly one frozen flow_24 case")
case = only(cases)
validate_w4_case(case; canonical_design_origin_m=origin, canonical_design_spacing_m=spacing)
candidate_grid = kernel_grid(owner)
floor_candidate = NormalFloorWaterLilyBody(candidate_grid, Float32.(case.flow_origin_m), Float32(case.flow_spacing_m), 0.25f0)
candidate = CandidateCWaterLilyBody(floor_candidate; normal_floor=0.25f0,
    transition_width=Float32(1.1444091796875e-4))
ground = V16MovingGroundBody(0.0f0, 1.0f0)
combined = CandidateCWaterLilyBody(floor_candidate, ground;
    normal_floor=0.25f0, transition_width=Float32(1.1444091796875e-4))
isbitstype(typeof(combined)) || error("Candidate C body is not isbits")
sim = WaterLily.Simulation(case.flow_dims, v16_native_far_field_uBC, Float32(case.solver_length);
    U=Float32(case.solver_velocity), ν=Float32(case.solver_viscosity),
    exitBC=true, body=combined, T=Float32, mem=CuArray)
owned = OwnedV16Run(owner, (candidate=candidate, ground=ground, combined=combined), sim)
GC.@preserve owned begin
    sim_step!(sim)
    CUDA.synchronize()
end
finite_u = all(isfinite, sim.flow.u)
finite_p = all(isfinite, sim.flow.p)
finite_u && finite_p || error("one-step setup produced a non-finite solver field")
record = "{\"evidence_class\":\"setup_only_not_calibration\",\"state_sha256\":\"$(expected_state)\",\"phi_fortran_sha256\":\"$(expected_phi_f)\",\"phi_c_order_sha256\":\"$(phi_c)\",\"device_roundtrip_sha256\":\"$(roundtrip)\",\"margin_m\":$(margin),\"finite_u\":true,\"finite_p\":true,\"julia_version\":\"$(VERSION)\",\"waterlily_version\":\"$(pkgversion(WaterLily))\",\"cuda_jl_version\":\"$(pkgversion(CUDA))\",\"gpu_name\":\"$(CUDA.name(CUDA.device()))\"}"
write(output_path, record * "\n")
println("FD08_V2_SETUP_DONE ", record)
flush(stdout)
