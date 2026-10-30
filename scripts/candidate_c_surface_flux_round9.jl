# New unregistered Round9 body-relative flux diagnostic source.
# Primitive solver definitions are copied from immutable Round7; its file is untouched.
using SHA, DelimitedFiles, LinearAlgebra, WaterLily
const ROOT = normpath(joinpath(@__DIR__, ".."))
const PKG_SRC = joinpath(ROOT, "julia", "CFDSDFWaterLily", "src")
include(joinpath(PKG_SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for name in ("WaterLilyNormalFloorBody.jl", "V16PhysicalProfile.jl", "CandidateCWaterLilyBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(PKG_SRC, name))
end
length(ARGS) in (3,4) || error("usage: candidate_c_surface_flux_round8.jl <plan.json> <geometry_root> <new_output_dir> [--preflight-only]")
plan_path, geometry_root, output_dir = ARGS[1:3]
preflight_only=length(ARGS)==4
preflight_only && ARGS[4]!="--preflight-only" && error("unknown option")
sha(path) = bytes2hex(sha256(read(path)))
plan_sha=sha(plan_path)
first(split(read(plan_path*".sha256",String)))==plan_sha || error("plan SHA mismatch")
for (inventory, base) in ((joinpath(dirname(plan_path),"sources.sha256"),ROOT),
                           (joinpath(geometry_root,"inputs.sha256"),geometry_root))
    for line in eachline(inventory)
        expected,relative=split(line,"  ";limit=2)
        path=startswith(relative,"external:") ? relative[10:end] : joinpath(base,relative)
        isfile(path) && sha(path)==expected || error("registered input mismatch: $relative")
    end
end
VERSION==v"1.12.6" && Base.pkgversion(WaterLily)==v"1.8.0" || error("runtime version mismatch")
println("CANDIDATE_C_SURFACE_RUNTIME julia=$VERSION waterlily=$(Base.pkgversion(WaterLily)) threads=$(Threads.nthreads()) backend=Array precision=Float32 job_sha256=$(sha(@__FILE__)) criteria_sha256=$plan_sha")
ispath(output_dir) && error("refusing existing output directory")
mkdir(output_dir)
const FLOW_DIMS = (100, 48, 36)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOW_H = 0.05
const FLOW_L = 16.0
const FLOW_U = 1.0
const FLOW_NU = 0.2
const RHO_KG_M3 = 1.0
const FORCE_N_PER_SOLVER = RHO_KG_M3 * FLOW_U^2 * FLOW_H^2
const MASS_KG_S_PER_SOLVER = RHO_KG_M3 * FLOW_U * FLOW_H^2
const T_END = 0.25
const WINDOW_START = 0.10
const WINDOW_MIDDLE = 0.175
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
    margin = fixture.shape === :none ? nothing : zero_level_margin_m(phi, SDF_ORIGIN, SDF_H)
    margin === nothing || margin >= SDF_MARGIN_M - 1e-6 ||
        error("$(fixture.id): sampled SDF margin $margin below $(SDF_MARGIN_M - 1e-6) m constructor tolerance")
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


function quadrature(fixture, kind, level)
    path=joinpath(geometry_root,fixture.id,"$(kind)_level$(level)_quadrature.csv")
    q=readdlm(path,',',Float64;skipstart=1)
    size(q,2)==8 && size(q,1)>0 && all(isfinite,q) || error("invalid quadrature payload")
    all(q[:,8].>0) || error("nonpositive surface weights")
    all(i->abs(norm(q[i,5:7])-1)<=1e-12,axes(q,1)) || error("geometric normals not unit")
    q
end
function masks(fixture, sim)
    dims=size(sim.flow.p); dims==FLOW_DIMS.+2 || error("pressure allocation identity drift")
    bytes=read(joinpath(geometry_root,fixture.id,"fixed_fluid_transition_masks.bin"))
    length(bytes)==2*prod(dims) && all(x->x in (0x00,0x01),bytes) || error("invalid fixed mask")
    n=prod(dims); reshape(bytes[1:n].==1,dims),reshape(bytes[n+1:end].==1,dims)
end
function masked_norms(sim, mask)
    count(mask)>0 || error("empty registered geometric mask")
    dv=Float64[]; cached=Float64[]
    for I in findall(mask)
        value=sum(Float64(sim.flow.u[I+WaterLily.δ(d,I),d])-Float64(sim.flow.u[I,d]) for d in 1:3)
        push!(dv,value*FLOW_U/FLOW_H)
        push!(cached,Float64(sim.pois.levels[1].r[I]))
    end
    all(isfinite,dv) && all(isfinite,cached) || error("nonfinite mask diagnostic")
    (length(dv),sqrt(sum(abs2,dv)/length(dv)),maximum(abs,dv),
        sqrt(sum(abs2,cached)/length(cached)),maximum(abs,cached))
end
function surface_values(sim, body, q; points_io=nothing, fixture_id, mode, kind, level)
    signed=0.; absolute=0.; squares=0.; op_signed=0.; op_absolute=0.; maxslip=0.; area=0.
    for i in axes(q,1)
        xworld=q[i,2:4]; x=WaterLily.SVector{3,Float32}(ntuple(d->(xworld[d]-FLOW_ORIGIN[d])/FLOW_H,3))
        dims=size(sim.flow.p)
        for component in 1:3, d in 1:3
            query=Float64(x[d])+(component==d ? .5 : 0.)
            0<=query<=dims[d]-2 || error("velocity query would clamp")
        end
        u=WaterLily.interp(x,sim.flow.u)
        _, opn, V=WaterLily.measure(body,x,sim_time(sim))
        all(isfinite,u) && all(isfinite,opn) && all(isfinite,V) || error("nonfinite surface field")
        rel=(Float64.(u).-Float64.(V)).*FLOW_U; normal=q[i,5:7]; w=q[i,8]
        slip=sum(rel[d]*normal[d] for d in 1:3)
        opslip=sum(rel[d]*Float64(opn[d]) for d in 1:3)
        signed+=RHO_KG_M3*w*slip;absolute+=RHO_KG_M3*w*abs(slip)
        squares+=w*slip^2;area+=w;maxslip=max(maxslip,abs(slip))
        op_signed+=RHO_KG_M3*w*opslip;op_absolute+=RHO_KG_M3*w*abs(opslip)
        if points_io!==nothing
            println(points_io,join((fixture_id,string(mode),kind,level,Float64(sim_time(sim)),i,
                xworld...,Float64.(x)...,normal...,Float64.(opn)...,Float64.(u)...,
                Float64.(V)...,w,slip,opslip),","))
        end
    end
    (size(q,1),area,signed,absolute,sqrt(squares/area),maxslip,op_signed,op_absolute)
end
if preflight_only
    for fixture in FIXTURES, mode in MODES
        grid,grid_sha,_=sampled_grid(fixture)
        grid_sha==strip(read(joinpath(geometry_root,fixture.id,"phi.sha256"),String)) || error("sampled phi drift")
        sim,bodies=init_sim(fixture,mode,grid)
        masks(fixture,sim)
        for kind in (fixture.shape===:none ? (:ground,) : (:body,:ground)),level in 0:2
            body=kind===:body ? bodies.candidate : bodies.ground
            surface_values(sim,body,quadrature(fixture,kind,level);
                fixture_id=fixture.id,mode,kind,level)
        end
    end
    println("CANDIDATE_C_SURFACE_INITIALIZATION_PASS no_sim_step")
    exit(0)
end
history_path=joinpath(output_dir,"surface_history.csv")
point_path=joinpath(output_dir,"final_point_values.csv")
open(history_path,"w") do history
    println(history,"fixture,mode,step,t_u_over_l,surface,level,points,area_m2,signed_body_outward_kg_s,absolute_kg_s,geom_slip_rms_m_s,geom_slip_max_m_s,operator_signed_kg_s,operator_absolute_kg_s,candidate_raw_pressure_fx,candidate_raw_pressure_fy,candidate_raw_pressure_fz,candidate_raw_viscous_fx,candidate_raw_viscous_fy,candidate_raw_viscous_fz,candidate_total_fx_n,candidate_total_fy_n,candidate_total_fz_n,fluid_nodes,fluid_div_rms_s_inv,fluid_div_max_s_inv,fluid_cached_residual_rms_solver,fluid_cached_residual_max_solver,transition_nodes,transition_div_rms_s_inv,transition_div_max_s_inv,transition_cached_residual_rms_solver,transition_cached_residual_max_solver")
    open(point_path,"w") do points
        println(points,"fixture,mode,surface,level,t_u_over_l,point_id,x_world_m,y_world_m,z_world_m,x_solver_f32,y_solver_f32,z_solver_f32,nx_geom,ny_geom,nz_geom,nx_operator,ny_operator,nz_operator,ux_solver,uy_solver,uz_solver,vx_body_solver,vy_body_solver,vz_body_solver,weight_m2,geom_slip_m_s,operator_slip_m_s")
        for fixture in FIXTURES
            kinds=fixture.shape===:none ? (:ground,) : (:body,:ground)
            qs=Dict((kind,level)=>quadrature(fixture,kind,level) for kind in kinds for level in 0:2)
            grid,grid_sha,_=sampled_grid(fixture)
            expected=strip(read(joinpath(geometry_root,fixture.id,"phi.sha256"),String))
            grid_sha==expected || error("actual sampled Float32 phi identity mismatch")
            for mode in MODES
                sim,bodies=init_sim(fixture,mode,grid);fluid,transition=masks(fixture,sim)
                step=0;before_window=false
                while sim_time(sim)<T_END
                    sim_step!(sim);step+=1
                    final=sim_time(sim)>=T_END
                    # Keep every raw sample: short diagnostic windows need brackets.
                    if sim_time(sim)<=WINDOW_START
                        before_window=true
                    end
                    all(isfinite,sim.flow.u) && all(isfinite,sim.flow.p) || error("nonfinite primal fields")
                    fstats=masked_norms(sim,fluid);tstats=masked_norms(sim,transition)
                    rp=WaterLily.pressure_force(sim.flow,bodies.candidate)
                    rv=WaterLily.viscous_force(sim.flow,bodies.candidate)
                    force=-(Float64.(rp).+Float64.(rv)).*FORCE_N_PER_SOLVER
                    for kind in kinds,level in 0:2
                        body=kind===:body ? bodies.candidate : bodies.ground
                        values=surface_values(sim,body,qs[(kind,level)];points_io=final ? points : nothing,
                            fixture_id=fixture.id,mode,kind,level)
                        println(history,join((fixture.id,string(mode),step,Float64(sim_time(sim)),kind,level,
                            values...,rp...,rv...,force...,fstats...,tstats...),","))
                    end
                    flush(history);flush(points)
                    if final
                        for (label,array) in (("u",sim.flow.u),("p",sim.flow.p),
                                              ("cached_scaled_residual",sim.pois.levels[1].r))
                            open(joinpath(output_dir,"$(fixture.id)__$(mode)__$(label)_f32_fortran.bin"),"w") do field
                                write(field,vec(array))
                            end
                        end
                    end
                end
                before_window || error("no raw bracket before .10 tU/L")
            end
        end
    end
end
println("CANDIDATE_C_SURFACE_DONE raw_observables_only_no_physical_qualification")
