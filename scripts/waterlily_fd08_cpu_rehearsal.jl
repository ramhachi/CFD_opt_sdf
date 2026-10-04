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

length(ARGS) == 6 || error("usage: waterlily_fd08_cpu_rehearsal.jl <phi_fortran.raw> <expected_sha256> <run_id> <force_csv> <margin_gate_m> <margin_tolerance_m>")
raw_path, expected_sha, run_id, force_csv_path, margin_gate_arg, margin_tolerance_arg = ARGS
margin_gate_m = parse(Float64, margin_gate_arg)
margin_tolerance_m = parse(Float64, margin_tolerance_arg)
isfinite(margin_gate_m) && isfinite(margin_tolerance_m) && margin_tolerance_m >= 0 ||
    error("$run_id: invalid registered SDF margin rule")
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

margin = zero_level_margin_m(phi, DESIGN_ORIGIN, DESIGN_H)
margin >= margin_gate_m - margin_tolerance_m || error("$run_id: SDF boundary margin failed: $margin m")
grid = GridSDF(phi; origin=DESIGN_ORIGIN, h=DESIGN_H,
    outside_value=3.0, margin_m=Float32(margin_gate_m))
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

const FORCE_COLUMNS = (
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
)

function force_row(step, sim, body)
    # WaterLily reports reaction on the fluid; store force on the body as W4-C does.
    pressure = -(WaterLily.pressure_force(sim.flow, body))
    viscous = -(WaterLily.viscous_force(sim.flow, body))
    total = pressure + viscous
    all(isfinite, pressure) && all(isfinite, viscous) && all(isfinite, total) ||
        error("$run_id: non-finite diagnostic force")
    values = Float64.(total)
    p = Float64.(pressure)
    v = Float64.(viscous)
    return (step, Float64(WaterLily.sim_time(sim)), values[1], values[2], values[3],
        values[1], -values[3], p[1], p[2], p[3], v[1], v[2], v[3])
end

rows = [force_row(0, sim, candidate)]
println("FD08_CPU_REHEARSAL_STEP_INVOKED run_id=$run_id")
flush(stdout)
WaterLily.sim_step!(sim)
all(isfinite, sim.flow.u) || error("$run_id: non-finite velocity after one CPU step")
all(isfinite, sim.flow.p) || error("$run_id: non-finite pressure after one CPU step")
push!(rows, force_row(1, sim, candidate))
rows[2][2] > rows[1][2] || error("$run_id: one CPU step did not advance simulation time")
mkpath(dirname(force_csv_path))
open(force_csv_path, "w") do io
    println(io, join(FORCE_COLUMNS, ","))
    for row in rows
        println(io, join(string.(row), ","))
    end
end
println("FD08_CPU_REHEARSAL_DONE run_id=$run_id phi_fortran_sha256=$expected_sha margin_m=$margin julia=$VERSION waterlily=$(Base.pkgversion(WaterLily)) backend=Array steps=1 force_rows=$(length(rows)) csv_sha256=$(bytes2hex(sha256(read(force_csv_path)))) qualification=false")
