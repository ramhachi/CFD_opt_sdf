# One-step CPU smoke test for registered FD-08 input states.
# This is a setup/operator rehearsal only; it does not measure the FD-08 window.

using SHA
using WaterLily

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody: GridSDF, zero_level_margin_m
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end
using .CFDSDFWaterLily: NormalFloorWaterLilyBody, CandidateCWaterLilyBody,
    V16MovingGroundBody, v16_native_far_field_uBC

length(ARGS) == 3 || error("usage: waterlily_fd08_cpu_rehearsal.jl <phi_fortran.raw> <expected_sha256> <run_id>")
raw_path, expected_sha, run_id = ARGS
raw = read(raw_path)
bytes2hex(sha256(raw)) == expected_sha || error("$run_id: Float32 Fortran phi SHA mismatch")
const POINT_SHAPE = (121, 65, 49)
length(raw) == prod(POINT_SHAPE) * sizeof(Float32) || error("$run_id: canonical phi byte length mismatch")
phi = reshape(copy(reinterpret(Float32, raw)), POINT_SHAPE)
all(isfinite, phi) || error("$run_id: non-finite phi values")

const DESIGN_ORIGIN = (-1.0, -0.8, -0.6)
const DESIGN_H = (0.025, 0.025, 0.025)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOW_SPACING = Float32(1 / 30)
const FLOW_DIMS = (150, 72, 54)
const TRANSITION_WIDTH = Float32(1.1444091796875e-4)
const REQUIRED_MARGIN_M = 0.15

margin = zero_level_margin_m(phi, DESIGN_ORIGIN, DESIGN_H)
margin >= REQUIRED_MARGIN_M - 1e-6 || error("$run_id: SDF boundary margin failed: $margin m")
grid = GridSDF(phi; origin=DESIGN_ORIGIN, h=DESIGN_H,
    outside_value=3.0, margin_m=REQUIRED_MARGIN_M)
floor_body = NormalFloorWaterLilyBody(
    grid, Float32.(FLOW_ORIGIN), FLOW_SPACING, 0.25f0)
candidate = CandidateCWaterLilyBody(floor_body;
    normal_floor=0.25f0, transition_width=TRANSITION_WIDTH)
ground = V16MovingGroundBody(0.0f0, 1.0f0)
# Keep Candidate C outermost so its specialized moment fill covers candidate + ground.
combined = CandidateCWaterLilyBody(floor_body, ground;
    normal_floor=0.25f0, transition_width=TRANSITION_WIDTH)
sim = WaterLily.Simulation(FLOW_DIMS, v16_native_far_field_uBC, 24f0;
    U=1f0, ν=0.3f0, exitBC=true, body=combined, T=Float32, mem=Array)

println("FD08_CPU_REHEARSAL_STEP_INVOKED run_id=$run_id")
flush(stdout)
WaterLily.sim_step!(sim)
all(isfinite, sim.flow.u) || error("$run_id: non-finite velocity after one CPU step")
all(isfinite, sim.flow.p) || error("$run_id: non-finite pressure after one CPU step")
pressure = WaterLily.pressure_force(sim.flow, candidate)
viscous = WaterLily.viscous_force(sim.flow, candidate)
all(isfinite, pressure) && all(isfinite, viscous) || error("$run_id: non-finite diagnostic force")
println("FD08_CPU_REHEARSAL_DONE run_id=$run_id phi_fortran_sha256=$expected_sha margin_m=$margin julia=$VERSION waterlily=$(Base.pkgversion(WaterLily)) backend=Array steps=1 qualification=false")
