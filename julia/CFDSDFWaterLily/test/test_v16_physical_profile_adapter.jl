# W3 adapter-only checks. This constructs the simulation but does not advance
# a WaterLily time step or make a solver/physics claim.
# Run: julia --startup-file=no --project=julia/CFDSDFWaterLily \
#        julia/CFDSDFWaterLily/test/test_v16_physical_profile_adapter.jl

include(joinpath(@__DIR__, "..", "src", "CFDSDFWaterLily.jl"))
include(joinpath(@__DIR__, "..", "src", "OwnedV16Run.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
using WaterLily
using LinearAlgebra: dot, norm
Base.include(CFDSDFWaterLily,
    joinpath(@__DIR__, "..", "src", "V16PhysicalProfile.jl"))

failures = String[]
function check(name, ok)
    println("RESULT ", name, " ", ok ? "PASS" : "FAIL")
    ok || push!(failures, name)
end

origin = CFDSDFWaterLily.V16_CANONICAL_SDF_ORIGIN_M
flow_origin = CFDSDFWaterLily.V16_PROFILE_FLOW_ORIGIN_M
h = CFDSDFWaterLily.V16_PROFILE_SPACING_M
center = (0.25, 0.0, 0.0)
radius = 0.2
phi = Array{Float32}(undef, CFDSDFWaterLily.V16_PROFILE_POINT_SHAPE)
for k in axes(phi, 3), j in axes(phi, 2), i in axes(phi, 1)
    x = origin[1] + (i - 1) * h
    y = origin[2] + (j - 1) * h
    z = origin[3] + (k - 1) * h
    phi[i, j, k] = Float32(sqrt((x-center[1])^2 + (y-center[2])^2 + (z-center[3])^2) - radius)
end
grid = GridSDF(phi; origin, h=(h,h,h), outside_value=3.0, margin_m=0.15)
bodies = CFDSDFWaterLily.v16_physical_profile_bodies(grid)

candidate_solver_point = Float32[(center[i] - flow_origin[i]) / h for i in 1:3]
candidate_distance, candidate_normal, _ = WaterLily.measure(
    bodies.candidate, candidate_solver_point, 0.0f0,
)
mapped_candidate_point = CFDSDFWaterLily.canonical_point(bodies.candidate, candidate_solver_point)
expected_candidate_distance = Float32(
    sdf_at_world(grid, mapped_candidate_point) / CFDSDFWaterLily.V16_PROFILE_SPACING_M,
)
check("candidate_world_solver_map", collect(mapped_candidate_point) ≈ collect(center) &&
      abs(candidate_distance - expected_candidate_distance) <= 2e-6 &&
      abs(norm(candidate_normal) - 1.0f0) <= 2e-6)

float32_grid = GridSDF(Float32.(phi); origin=Float32.(origin),
    h=(Float32(h), Float32(h), Float32(h)), outside_value=3.0f0, margin_m=0.15f0)
float32_bodies = CFDSDFWaterLily.v16_physical_profile_bodies(float32_grid; T=Float32)
check("canonical_sdf_origin_stays_fixed", grid.origin == origin &&
      collect(CFDSDFWaterLily.canonical_point(bodies.candidate, candidate_solver_point)) ≈ collect(center))
check("flow_origin_is_separate", bodies.candidate.world_origin_m == Float32.(flow_origin) &&
      bodies.candidate.world_origin_m != Float32.(grid.origin))
check("float32_device_map_identity", float32_grid.origin == Float32.(origin) &&
      float32_grid.h == (Float32(h), Float32(h), Float32(h)) &&
      float32_bodies.candidate.world_per_solver == Float32(h))

ground_distance, ground_normal, ground_velocity = WaterLily.measure(
    bodies.ground, Float32[10, 10, 0.5], 0.0f0,
)
check("moving_ground_positive_fluid_side", ground_distance == 0.5f0 &&
      ground_normal == Float32[0,0,1])
check("moving_ground_velocity", ground_velocity == Float32[1,0,0])
check("moving_ground_zero_normal_flux", dot(ground_normal, ground_velocity) == 0.0f0)
ground_at_bottom = CFDSDFWaterLily.canonical_point(
    bodies.candidate, Float32[0, 0, 0])[3]
check("moving_ground_at_expanded_flow_bottom", ground_at_bottom == -0.9f0 &&
      bodies.ground.z_plane == 0.0f0)
check("far_field_velocity_contract",
      CFDSDFWaterLily.v16_native_far_field_uBC(1, Float32[0,0,0], 0.0f0) == 1.0f0 &&
      CFDSDFWaterLily.v16_native_far_field_uBC(2, Float32[0,0,0], 0.0f0) == 0.0f0 &&
      CFDSDFWaterLily.v16_native_far_field_uBC(3, Float32[0,0,0], 0.0f0) == 0.0f0)

contract = CFDSDFWaterLily.v16_physical_profile_adapter_contract()
check("profile_non_equivalence_is_explicit", !contract.source_profile_equivalent &&
      !contract.physical_profile_qualified &&
      occursin("no per-patch freestreamPressure", contract.pressure_boundary))
check("physical_time_scale", contract.solver_time_unit_s == 0.05 &&
      isapprox(contract.solver_viscosity, 0.2; atol=1e-15))
check("expanded_flow_grid_and_reynolds", CFDSDFWaterLily.V16_PROFILE_CELL_DIMS == (100,48,36) &&
      CFDSDFWaterLily.V16_PROFILE_REYNOLDS == 80.0)

sim = CFDSDFWaterLily.build_v16_physical_profile_simulation(bodies)
owner_probe = Ref(:device_owner)
owner_weakref = WeakRef(owner_probe)
owned_run_probe = CFDSDFW3RunOwnership.OwnedV16Run(owner_probe, bodies, sim)
owner_probe = nothing
GC.gc(true)
check("structural_run_bundle_retains_device_owner",
      owner_weakref.value === owned_run_probe.owner)
check("registered_solver_scaling", sim.L == 16.0f0 && sim.U == 1.0f0 &&
      sim.flow.ν == 0.2f0 && sim.flow.exitBC &&
      size(sim.flow.p)[1:3] == (102,50,38))
ground_velocity_field = Array(sim.flow.V)
check("moving_ground_enters_body_velocity_field",
      maximum(@view ground_velocity_field[:,:,:,1]) > 0.5f0)
check("no_solver_step", WaterLily.sim_time(sim) == 0.0f0)
check("candidate_force_overloads_exist",
      applicable(WaterLily.pressure_force, sim.flow, bodies.candidate) &&
      applicable(WaterLily.viscous_force, sim.flow, bodies.candidate))

isempty(failures) || error("W3 adapter checks failed: $(join(failures, ", "))")
println("W3_ADAPTER_DONE 16 checks; no solver step")
