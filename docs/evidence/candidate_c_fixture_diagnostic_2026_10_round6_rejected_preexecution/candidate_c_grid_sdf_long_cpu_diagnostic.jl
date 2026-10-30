# Candidate C long-window CPU diagnostic for sampled analytic fixtures.
# This is a new round-6 job; do not edit the immutable short round-5 runner.
# No thresholds here qualify native/GridSDF accuracy, stationarity, or mass.
#
# Usage:
#   julia -t auto --project=julia/CFDSDFWaterLily \
#     scripts/candidate_c_grid_sdf_long_cpu_diagnostic.jl <plan.json> <raw.csv> [--preflight-only]

using SHA
using WaterLily

const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end

length(ARGS) in (2, 3) || error("usage: candidate_c_grid_sdf_long_cpu_diagnostic.jl <plan.json> <raw.csv> [--preflight-only]")
plan_path, output_path = ARGS[1:2]
preflight_only = length(ARGS) == 3 && ARGS[3] == "--preflight-only"
length(ARGS) == 3 && !preflight_only && error("unknown option: $(ARGS[3])")
isfile(plan_path) || error("diagnostic criteria are missing")
plan_bytes = read(plan_path)
plan_text = String(copy(plan_bytes))
sha(bytes) = bytes2hex(sha256(bytes))
plan_sha = sha(plan_bytes)
sidecar = replace(plan_path, r"\.json$" => ".sha256")
isfile(sidecar) || error("criteria SHA-256 sidecar is missing")
plan_sha == first(split(read(sidecar, String))) || error("criteria SHA-256 mismatch")
plan_field(name) = begin
    match_value = match(Regex("\\\"" * name * "\\\"\\s*:\\s*\\\"([0-9a-f]{64})\\\""), plan_text)
    match_value === nothing && error("criteria is missing hash field: $name")
    match_value.captures[1]
end
plan_field("job_sha256") == sha(read(@__FILE__)) || error("job source hash mismatch")
manifest_path = joinpath(dirname(plan_path), "runner_sources.sha256")
isfile(manifest_path) || error("source manifest is missing")
sha(read(manifest_path)) == plan_field("source_manifest_sha256") || error("source manifest hash mismatch")
for line in eachline(manifest_path)
    expected, relative = split(line, "  "; limit=2)
    source_path = startswith(relative, "external:") ? relative[10:end] : joinpath(ROOT, relative)
    isfile(source_path) || error("registered source is missing: $relative")
    sha(read(source_path)) == expected || error("registered source hash mismatch: $relative")
end

const FLOW_DIMS = (100, 48, 36)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOW_H = 0.05
const FLOW_L = 16.0
const FLOW_U = 1.0
const FLOW_NU = 0.2
const RHO_KG_M3 = 1.0
const FORCE_N_PER_SOLVER = RHO_KG_M3 * FLOW_U^2 * FLOW_H^2
const MASS_KG_S_PER_SOLVER = RHO_KG_M3 * FLOW_U * FLOW_H^2
const T_END = 10.0
const WINDOW_START = 5.0
const WINDOW_MIDDLE = 7.5
const SAMPLE_EVERY = 4
const GROUND_Z_SOLVER = 8.0f0
const GROUND_U_SOLVER = 1.0f0
const SDF_ORIGIN = (-1.0, -0.8, -0.6)
const SDF_H = (0.05, 0.05, 0.05)
const SDF_SHAPE = (61, 33, 25)
const SDF_MARGIN_M = 0.15
const BODY_CENTER = (0.0, 0.0, -0.2)
const TRANSITION_WIDTH = 1.1444091796875e-4
const FIXTURES = (
    (id="sphere", shape=:sphere, extents=(0.25, 0.25, 0.25)),
    (id="plate_1cell", shape=:box, extents=(0.25, 0.025, 0.25)),
    (id="plate_2cell", shape=:box, extents=(0.25, 0.05, 0.25)),
    (id="moving_ground_only", shape=:none, extents=(0.0, 0.0, 0.0)),
)
const MODES = (:native, :grid_upstream, :candidate_c)

analytic_phi(shape, extents, p) = if shape === :none
    3.0
elseif shape === :sphere
    sqrt(sum((p[i] - BODY_CENTER[i])^2 for i in 1:3)) - extents[1]
else
    q = ntuple(i -> abs(p[i] - BODY_CENTER[i]) - extents[i], 3)
    sqrt(sum(max(q[i], 0.0)^2 for i in 1:3)) + min(maximum(q), 0.0)
end

function sampled_grid(fixture)
    phi = Array{Float32}(undef, SDF_SHAPE)
    for k in 1:SDF_SHAPE[3], j in 1:SDF_SHAPE[2], i in 1:SDF_SHAPE[1]
        p = ntuple(d -> SDF_ORIGIN[d] + (d == 1 ? i - 1 : d == 2 ? j - 1 : k - 1) * SDF_H[d], 3)
        phi[i, j, k] = Float32(analytic_phi(fixture.shape, fixture.extents, p))
    end
    margin = zero_level_margin_m(phi, SDF_ORIGIN, SDF_H)
    margin >= SDF_MARGIN_M || error("$(fixture.id): sampled SDF margin $margin below $SDF_MARGIN_M m")
    grid = GridSDF(phi; origin=SDF_ORIGIN, h=SDF_H,
        outside_value=3.0, margin_m=SDF_MARGIN_M)
    return grid, bytes2hex(sha256(reinterpret(UInt8, vec(phi)))), margin
end

solver_center() = ntuple(i -> Float32((BODY_CENTER[i] - FLOW_ORIGIN[i]) / FLOW_H), 3)

function analytic_body(fixture)
    fixture.shape === :none && return WaterLily.NoBody()
    center = solver_center()
    sdf = if fixture.shape === :sphere
        radius = Float32(fixture.extents[1] / FLOW_H)
        (x, t) -> sqrt(sum((x[i] - center[i])^2 for i in 1:3)) - radius
    else
        half_extent = ntuple(i -> Float32(fixture.extents[i] / FLOW_H), 3)
        (x, t) -> begin
            q = ntuple(i -> abs(x[i] - center[i]) - half_extent[i], 3)
            sqrt(sum(max(q[i], 0f0)^2 for i in 1:3)) + min(maximum(q), 0f0)
        end
    end
    return WaterLily.AutoBody(sdf)
end

function body_set(fixture, mode, grid)
    ground = CFDSDFWaterLily.V16MovingGroundBody(GROUND_Z_SOLVER, GROUND_U_SOLVER)
    floor_body = CFDSDFWaterLily.NormalFloorWaterLilyBody(
        grid, ntuple(i -> Float32(FLOW_ORIGIN[i]), 3), Float32(FLOW_H), 0.25f0)
    native = analytic_body(fixture)
    candidate = mode === :native ? native :
        mode === :candidate_c ? CFDSDFWaterLily.CandidateCWaterLilyBody(
            floor_body; normal_floor=0.25f0, transition_width=Float32(TRANSITION_WIDTH)) :
            floor_body
    # The outer C wrapper is required: CandidateC(candidate)+ground dispatches
    # measure! on SetBody and bypasses Candidate C's specialized moment fill.
    combined = mode === :candidate_c ?
        CFDSDFWaterLily.CandidateCWaterLilyBody(
            floor_body, ground; normal_floor=0.25f0,
            transition_width=Float32(TRANSITION_WIDTH)) : candidate + ground
    return (; candidate, ground, combined)
end

function init_sim(fixture, mode, grid)
    bodies = body_set(fixture, mode, grid)
    sim = WaterLily.Simulation(FLOW_DIMS,
        CFDSDFWaterLily.v16_native_far_field_uBC, FLOW_L;
        U=FLOW_U, ν=FLOW_NU, exitBC=true,
        body=bodies.combined, T=Float32, mem=Array)
    return sim, bodies
end

function physical_force_parts(sim, body)
    p = -WaterLily.pressure_force(sim.flow, body) .* FORCE_N_PER_SOLVER
    v = -WaterLily.viscous_force(sim.flow, body) .* FORCE_N_PER_SOLVER
    # Define total from the two SI components so the exact identity can be
    # independently checked from the raw CSV without a guessed physics bound.
    return p, v, p .+ v
end

function external_face_fluxes(sim)
    u = sim.flow.u
    nx, ny, nz = size(u)[1:3]
    ys, zs, xs = 2:ny-1, 2:nz-1, 2:nx-1 # omit transverse ghost layers
    scale = MASS_KG_S_PER_SOLVER
    q = (
        x_minus=-sum(Float64, @view u[2, ys, zs, 1]) * scale,
        x_plus=sum(Float64, @view u[nx, ys, zs, 1]) * scale,
        y_minus=-sum(Float64, @view u[xs, 2, zs, 2]) * scale,
        y_plus=sum(Float64, @view u[xs, ny, zs, 2]) * scale,
        z_minus=-sum(Float64, @view u[xs, ys, 2, 3]) * scale,
        z_plus=sum(Float64, @view u[xs, ys, nz, 3]) * scale,
    )
    return q, sum(values(q))
end

function float64_domain_divergence(sim)
    # Cast each face operand before subtracting: WaterLily.div returns Float32
    # differences for this Float32 state, which would spoil a telescoping sum.
    u = sim.flow.u
    total = 0.0
    for I in WaterLily.inside(sim.flow.p)
        for axis in 1:3
            high = Float64(u[I + WaterLily.δ(axis, I), axis])
            low = Float64(u[I, axis])
            total += high - low
        end
    end
    return total * MASS_KG_S_PER_SOLVER
end

function wall_diagnostics(sim, ground)
    x = Float32[0, 0, GROUND_Z_SOLVER]
    distance, normal, velocity = WaterLily.measure(ground, x, sim_time(sim))
    body_velocity_matches_freestream = velocity[1] == Float32(FLOW_U) &&
        velocity[2] == 0f0 && velocity[3] == 0f0
    body_has_no_normal_velocity = sum(Float64(normal[i]) * Float64(velocity[i]) for i in 1:3) == 0.0
    residual_normal = 0.0
    residual_tangent = 0.0
    samples = 0
    for I in WaterLily.inside_u(size(sim.flow.u)[1:3], 3)
        loc = WaterLily.loc(3, I, Float64)
        if loc[3] == Float64(GROUND_Z_SOLVER)
            uz = Float64(sim.flow.u[I, 3])
            ux = Float64(sim.flow.u[I, 1])
            residual_normal = max(residual_normal, abs(uz - Float64(velocity[3])))
            residual_tangent = max(residual_tangent, abs(ux - Float64(velocity[1])))
            samples += 1
        end
    end
    samples > 0 || error("registered moving-ground normal-velocity face was not sampled")
    return (; distance=Float64(distance), normal=Tuple(Float64.(normal)),
        velocity=Tuple(Float64.(velocity)), body_velocity_matches_freestream,
        body_has_no_normal_velocity, max_wall_normal_velocity_error_solver=residual_normal,
        max_wall_tangent_velocity_error_solver=residual_tangent, wall_face_samples=samples)
end

const FORCE_GROUPS = (:candidate, :ground, :combined)
const AXES = (:x, :y, :z)
function force_group_columns(group)
    return vcat(Symbol[Symbol(group, "_pressure_f", axis, "_n") for axis in AXES],
        Symbol[Symbol(group, "_viscous_f", axis, "_n") for axis in AXES],
        Symbol[Symbol(group, "_total_f", axis, "_n") for axis in AXES])
end

const BASE_COLUMNS = Symbol[:fixture, :mode, :step, :t_u_over_l, :phi_sha256,
    :phi_margin_m, :candidate_closure_n, :ground_closure_n, :combined_closure_n,
    :flux_x_minus_kg_s, :flux_x_plus_kg_s, :flux_y_minus_kg_s, :flux_y_plus_kg_s,
    :flux_z_minus_kg_s, :flux_z_plus_kg_s, :net_outward_kg_s,
    :integrated_divergence_kg_s, :divergence_boundary_difference_kg_s,
    :ground_velocity_matches_freestream, :ground_body_has_no_normal_velocity,
    :ground_velocity_x_solver, :ground_velocity_y_solver, :ground_velocity_z_solver,
    :ground_wall_normal_error_max_solver, :ground_wall_tangent_error_max_solver,
    :ground_wall_face_samples, :finite_u, :finite_p]
const CSV_COLUMNS = vcat([:fixture, :mode, :step, :t_u_over_l, :phi_sha256,
    :phi_margin_m], reduce(vcat, force_group_columns.(FORCE_GROUPS); init=Symbol[]),
    BASE_COLUMNS[7:end])

function force_data(sim, body)
    pressure, viscous, total = physical_force_parts(sim, body)
    closure = maximum(abs.(pressure .+ viscous .- total))
    return (; pressure=Tuple(pressure), viscous=Tuple(viscous), total=Tuple(total), closure)
end

function sample_record(fixture, mode, grid_sha, margin, sim, bodies, step)
    finite_u, finite_p = all(isfinite, sim.flow.u), all(isfinite, sim.flow.p)
    finite_u && finite_p || error("non-finite flow field at $(fixture.id)/$mode step=$step")
    forces = (
        candidate=force_data(sim, bodies.candidate),
        ground=force_data(sim, bodies.ground),
        combined=force_data(sim, bodies.combined),
    )
    fluxes, net = external_face_fluxes(sim)
    divergence = float64_domain_divergence(sim)
    wall = wall_diagnostics(sim, bodies.ground)
    return (; fixture=fixture.id, mode=string(mode), step, t_u_over_l=Float64(sim_time(sim)),
        phi_sha256=grid_sha, phi_margin_m=margin, forces,
        candidate_closure_n=forces.candidate.closure,
        ground_closure_n=forces.ground.closure, combined_closure_n=forces.combined.closure,
        fluxes, net_outward_kg_s=net, integrated_divergence_kg_s=divergence,
        divergence_boundary_difference_kg_s=divergence-net,
        wall, finite_u, finite_p)
end

function csv_values(row)
    values = Any[row.fixture, row.mode, row.step, row.t_u_over_l,
        row.phi_sha256, row.phi_margin_m]
    for group in FORCE_GROUPS
        force = getproperty(row.forces, group)
        append!(values, force.pressure)
        append!(values, force.viscous)
        append!(values, force.total)
    end
    append!(values, [row.candidate_closure_n, row.ground_closure_n, row.combined_closure_n,
        row.fluxes.x_minus, row.fluxes.x_plus, row.fluxes.y_minus, row.fluxes.y_plus,
        row.fluxes.z_minus, row.fluxes.z_plus, row.net_outward_kg_s,
        row.integrated_divergence_kg_s, row.divergence_boundary_difference_kg_s,
        row.wall.body_velocity_matches_freestream, row.wall.body_has_no_normal_velocity,
        row.wall.velocity..., row.wall.max_wall_normal_velocity_error_solver,
        row.wall.max_wall_tangent_velocity_error_solver, row.wall.wall_face_samples,
        row.finite_u, row.finite_p])
    return values
end

function init_check()
    for fixture in FIXTURES, mode in MODES
        grid, _, _ = sampled_grid(fixture)
        sim, bodies = init_sim(fixture, mode, grid)
        all(isfinite, sim.flow.u) && all(isfinite, sim.flow.p) ||
            error("initial field is non-finite for $(fixture.id)/$mode")
        wall = wall_diagnostics(sim, bodies.ground)
        wall.body_velocity_matches_freestream && wall.body_has_no_normal_velocity ||
            error("moving-ground body velocity contract failed")
    end
    println("CANDIDATE_C_LONG_CPU_INITIALIZATION_PASS no sim_step! called")
end

function run_diagnostic()
    output_path = abspath(output_path)
    any(ispath, (output_path, output_path * ".claim", output_path * ".sha256")) &&
        error("refusing to overwrite an existing diagnostic output")
    mkdir(output_path * ".claim")
    open(output_path, "w") do raw
        println(raw, join(CSV_COLUMNS, ",")); flush(raw)
        for fixture in FIXTURES
            grid, grid_sha, margin = sampled_grid(fixture)
            for mode in MODES
                sim, bodies = init_sim(fixture, mode, grid)
                step = 0
                while sim_time(sim) < T_END
                    sim_step!(sim)
                    step += 1
                    if step % SAMPLE_EVERY == 0 || sim_time(sim) >= T_END
                        row = sample_record(fixture, mode, grid_sha, margin, sim, bodies, step)
                        all(value -> value isa Bool || value isa AbstractString || isfinite(value), csv_values(row)) ||
                            error("non-finite diagnostic data in $(fixture.id)/$mode at t=$(sim_time(sim))")
                        println(raw, join(csv_values(row), ",")); flush(raw)
                    end
                end
                Float64(sim_time(sim)) >= T_END || error("$(fixture.id)/$mode did not reach t_end")
            end
        end
    end
    println("CANDIDATE_C_LONG_CPU_DONE $output_path")
end

preflight_only ? init_check() : run_diagnostic()
