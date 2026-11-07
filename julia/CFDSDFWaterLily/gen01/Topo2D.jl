"""TOPO-2D scene runner: CPU default, explicit unexecuted lazy CUDA path."""
module Topo2D

using WaterLily, SHA, Serialization, TOML

const ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const BRIDGE = joinpath(ROOT, "src", "cfd_harness", "scene_campaign.py")
const PYTHON = get(ENV, "TOPO2D_PYTHON", isfile(joinpath(ROOT, ".venv", "bin", "python")) ? joinpath(ROOT, ".venv", "bin", "python") : "python3")
const C1_MM = 223.4
const BASE_COLUMNS = ["step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver", "downforce_solver", "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver"]
const FORCE_AXES = ("fx", "fy", "fz", "drag", "downforce")
file_sha(path) = bytes2hex(sha256(read(path)))

struct NumericalFailure <: Exception
    message::String
end
Base.showerror(io::IO, e::NumericalFailure) = print(io,e.message)

# Opt in to separately pinned WP1/WP2 additions; registered src bytes stay fixed.
include(joinpath(ROOT, "julia", "CFDSDFWaterLily", "src", "Forces.jl"))
const FORCE_SOURCE = Ref(joinpath(ROOT,"julia","CFDSDFWaterLily","src","Forces.jl"))
for folder in ("gen01","src")
    path=joinpath(ROOT,"julia","CFDSDFWaterLily",folder,"Force00.jl")
    if isfile(path)
        include(path);FORCE_SOURCE[]=path;break
    end
end
const CHECKPOINT_SOURCE = Ref{Union{Nothing,String}}(nothing)
for folder in ("gen01","src")
    path=joinpath(ROOT,"julia","CFDSDFWaterLily",folder,"Checkpoint.jl")
    if isfile(path)
        include(path);CHECKPOINT_SOURCE[]=path;break
    end
end
checkpoint_available() = CHECKPOINT_SOURCE[]!==nothing && isdefined(@__MODULE__,:Checkpoint)

struct PolygonSDF{P} <: Function
    vertices::P
end

"""Point-to-segment Euclidean distance and nonzero-winding sign, directly in 2D.

This is piecewise AD compatible; polygon vertices/medial axes have the usual
distance-function kinks. No finite differences or trilinear grid intervene.
"""
function (poly::PolygonSDF)(x, t)
    best = oftype(x[1], Inf)
    winding = 0
    for i in 1:length(poly.vertices)-1
        a, b = poly.vertices[i], poly.vertices[i+1]
        ex, ez = b[1]-a[1], b[2]-a[2]
        px, pz = x[1]-a[1], x[2]-a[2]
        q = clamp((px*ex+pz*ez)/(ex*ex+ez*ez), zero(px), one(px))
        d2 = (px-q*ex)^2+(pz-q*ez)^2
        best = min(best, d2)
        cross = ex*pz-ez*px
        if a[2] <= x[2] < b[2] && cross > 0
            winding += 1
        elseif b[2] <= x[2] < a[2] && cross < 0
            winding -= 1
        end
    end
    (winding == 0 ? one(best) : -one(best))*sqrt(best)
end

struct MovingGround{T} <: WaterLily.AbstractBody
    z::T
    u::T
end

function WaterLily.measure(g::MovingGround, x::AbstractVector{T}, t; fastd²=T(Inf)) where T
    d = x[2]-g.z
    d*d > fastd² && return (d, zero(x), zero(x))
    (d, WaterLily.SVector(zero(T), one(T)), WaterLily.SVector(T(g.u), zero(T)))
end

function load_scene(path, expected_sha)
    isfile(path) && file_sha(path) == expected_sha || error("scene SHA-256 mismatch before solver")
    lines = split(chomp(read(`$PYTHON $BRIDGE wire $path $expected_sha`, String)), '\n')
    lines[1] == "topo2d-scene-v1" || error("scene wire schema")
    config, dx, ground, height, count = lines[2], parse(Float64, lines[3]), parse(Float64, lines[4]), parse(Float64, lines[5]), parse(Int, lines[6])
    names, polygons, probes = String[], Vector{NTuple{2,Float64}}[], Vector{NTuple{2,Float64}}[]
    pos = 7
    for _ in 1:count
        push!(names, lines[pos]); n = parse(Int, lines[pos+1]); pos += 2
        push!(polygons, [Tuple(parse.(Float64, split(lines[j]))) for j in pos:pos+n-1]); pos += n
        nprobe = parse(Int,lines[pos]); pos += 1
        push!(probes,[Tuple(parse.(Float64,split(lines[j]))) for j in pos:pos+nprobe-1]); pos += nprobe
    end
    pos == length(lines)+1 || error("scene wire trailing data")
    (; configuration=config, dx_mm=dx, ground_z_mm=ground, height_mm=height, names, polygons, probes, sha256=expected_sha)
end

function source_hashes(backend="cpu")
    project = backend == "cuda" ? "CFDSDFWaterLilyT4" : "CFDSDFWaterLily"
    paths = ["scripts/waterlily_topo2d_job.jl", "julia/CFDSDFWaterLily/gen01/Topo2D.jl", "src/cfd_harness/scene_campaign.py", "src/cfd_harness/campaign_schema.py", "src/cfd_gen/topo2d/geometry.py",
        "src/cfd_gen/__init__.py", "src/cfd_gen/topo2d/__init__.py",
        "data/zz2003/main_element_table3.dat", "data/zz2003/flap_table4.dat", "data/zz2003/single_element_table2.dat",
        "julia/CFDSDFWaterLily/src/Forces.jl", "julia/$project/Project.toml", "julia/$project/Manifest.toml"]
    append!(paths,["julia/CFDSDFWaterLily/src/$name" for name in ("CFDSDFWaterLily.jl","GridSDFBody.jl","WaterLilyBody.jl","Runtime.jl","Simulation.jl")])
    hashes=Dict(p => file_sha(joinpath(ROOT, p)) for p in paths)
    if FORCE_SOURCE[] != joinpath(ROOT,"julia","CFDSDFWaterLily","src","Forces.jl")
        key=relpath(FORCE_SOURCE[],ROOT)
        startswith(key,"..") && (key=FORCE_SOURCE[])
        hashes[key]=file_sha(FORCE_SOURCE[])
    end
    if checkpoint_available()
        path=CHECKPOINT_SOURCE[]
        key=relpath(path,ROOT)
        startswith(key,"..") && (key=path)
        hashes[key]=file_sha(path)
    end
    hashes
end

function runtime_identity(backend="cpu")
    identity = Dict{String,Any}("julia_version" => string(VERSION), "waterlily_version" => string(pkgversion(WaterLily)), "threads" => Threads.nthreads(), "scalar_type" => "Float32", "memory" => backend == "cuda" ? "CuArray" : "Array", "scheme" => "quick")
    if backend == "cuda"
        identity["device_name"] = CUDA.name(CUDA.device())
        identity["device_uuid"] = "GPU-"*string(CUDA.uuid(CUDA.device()))
        identity["cuda_jl_version"] = string(pkgversion(CUDA))
    end
    identity
end

function setup(scene; reynolds, phase_shift_m=(0.0,0.0,0.0), dims=nothing, smoke=false,
               start, stop, sample_every=8, batches=8, case_id="topo2d", phase="0", role="primary", grid="main", top_factor=1.0, backend="cpu")
    isfinite(reynolds) && reynolds > 0 && all(isfinite, phase_shift_m) && length(phase_shift_m) == 3 && phase_shift_m[2] == 0 || error("Re or 2D phase")
    all(isfinite,(start,stop)) && 0 <= start < stop && sample_every isa Integer && sample_every > 0 && batches isa Integer && batches >= 4 || error("time/sampling contract")
    backend in ("cpu","cuda") || error("unknown backend")
    L = C1_MM/scene.dx_mm
    ground_padding = 8
    top_factor in (1.0,1.5) || error("unregistered top-boundary factor")
    formal_dims = (round(Int,7L), round(Int,6.8L*top_factor)+ground_padding)
    dims = dims === nothing ? formal_dims : dims
    length(dims)==2 && all(d->d isa Integer && d>=16,dims) || error("2D positive integer flow dimensions required")
    smoke || dims == formal_dims || error("a reduced domain requires TOPO2D_SMOKE=1")
    # World x=-2c1 and z=-8dx on the full domain; explicit CPU smoke uses
    # shorter upstream padding. Both mappings retain source mm and spacing.
    x0 = smoke && dims != formal_dims ? -12scene.dx_mm : -2C1_MM
    z0 = -ground_padding*scene.dx_mm
    shift = (1000phase_shift_m[1],1000phase_shift_m[3])
    polygons = [[(Float32((p[1]+shift[1]-x0)/scene.dx_mm), Float32((p[2]+shift[2]-z0)/scene.dx_mm)) for p in poly] for poly in scene.polygons]
    all(1 < p[1] < dims[1]-1 && 1 < p[2] < dims[2]-1 for poly in polygons for p in poly) || error("scene touches finite domain before CFD")
    # Keep the vertex count out of CPU flow/readout kernel types. CUDA still
    # needs inline isbits storage; the SDF arithmetic is shared and unchanged.
    bodies = if backend == "cuda"
        [AutoBody(PolygonSDF(Tuple(p))) for p in polygons]
    else
        [AutoBody(PolygonSDF(p)) for p in polygons]
    end
    wing = reduce((a,b)->WaterLily.SetBody(min,a,b), bodies)
    ground = MovingGround(Float32((scene.ground_z_mm+shift[2]-z0)/scene.dx_mm),1.0f0)
    combined = WaterLily.SetBody(min,wing,ground)
    memory = Array
    if backend == "cuda"
        isdefined(@__MODULE__,:CUDA) && CUDA.functional() || error("explicit CUDA backend unavailable")
        isbitstype(typeof(combined)) || error("polygon/ground union must be isbits for CUDA")
        get(ENV,"W4_SELECTED_GPU_UUID","") == "GPU-"*string(CUDA.uuid(CUDA.device())) || error("selected/frozen GPU UUID mismatch")
        memory = CUDA.CuArray
    end
    sim = Simulation(dims,(1.0f0,0.0f0),Float32(L); ν=Float32(L/reynolds),body=combined,exitBC=true,λ=WaterLily.quick,T=Float32,mem=memory)
    columns = vcat(BASE_COLUMNS, ["$(r)_$(a)_solver" for r in ("cur","nds","cv") for a in FORCE_AXES], ["element_$(name)_$(a)_solver" for name in scene.names for a in FORCE_AXES])
    ident = Dict("configuration"=>scene.configuration,"height_mm"=>scene.height_mm,"reynolds"=>Float64(reynolds),"grid"=>grid,"phase"=>string(phase),"role"=>role)
    contract = (; scene_sha=scene.sha256, phase_shift_m, dims, reynolds, start, stop, sample_every, batches, L, smoke, case_id, phase=string(phase), role, grid, top_factor, backend, x0, z0, remeasure=true)
    fingerprint = bytes2hex(sha256(repr((contract,sort!(collect(source_hashes(backend));by=first),sort!(collect(runtime_identity(backend));by=first)))))
    wp2 = isdefined(@__MODULE__, :force_readouts)
    box = nothing
    if wp2
        isdefined(@__MODULE__, :validate_force_box) || error("WP2 readouts require candidate box validation")
        # Pressure-cell indices have centres I-1.5 and box faces at first-2 /
        # last-1. Six cells of geometric padding enclose the complete BDIM band
        # and leave >=4 cells to every scene component, including the ground.
        box = ntuple(axis->(floor(Int,minimum(p[axis] for poly in polygons for p in poly))-4):
                          (ceil(Int,maximum(p[axis] for poly in polygons for p in poly))+8),2)
        validate_force_box(sim,box;body=wing)
    end
    available = Dict("cur"=>true,"nds"=>wp2,"cv"=>wp2)
    (; sim, bodies, wing, ground, scene, columns, ident, contract, fingerprint, available, box)
end

project_force(v) = (Float64(v[1]),0.0,Float64(v[2]),Float64(v[1]),-Float64(v[2]))

function provider_readouts(f)
    try
        f()
    catch err
        # WP2's pinned API reports overflow/nonfinite momentum terms before
        # returning a vector. Box/configuration errors remain input failures.
        err isa ArgumentError && err.msg=="non-finite CV momentum term" && throw(NumericalFailure(err.msg))
        rethrow()
    end
end

function force_row(run, step)
    all(isfinite,run.sim.flow.u) && all(isfinite,run.sim.flow.p) || throw(NumericalFailure("non-finite flow at force sample"))
    p = [-(WaterLily.pressure_force(run.sim.flow,b)) for b in run.bodies]
    v = [-(WaterLily.viscous_force(run.sim.flow,b)) for b in run.bodies]
    pressure, viscous = if run.available["nds"]
        (-(WaterLily.pressure_force(run.sim.flow,run.wing)),-(WaterLily.viscous_force(run.sim.flow,run.wing)))
    else
        (reduce(+,p),reduce(+,v))
    end
    total = pressure+viscous
    cur = project_force(total)
    row = Float64[step,sim_time(run.sim),cur[1],cur[2],cur[3],cur[4],cur[5],pressure[1],0,pressure[2],viscous[1],0,viscous[2]]
    if run.available["nds"]
        readouts=provider_readouts(()->force_readouts(run.sim,run.box;body=run.wing,validate_box=false))
        for name in (:cur,:nds,:cv)
            append!(row,project_force(getproperty(readouts,name)))
        end
    else
        append!(row,cur); append!(row,fill(NaN,10))
    end
    for i in eachindex(p)
        append!(row,project_force(p[i]+v[i]))
    end
    all(isfinite,row[1:18]) && all(isfinite,row[29:end]) &&
        (!run.available["nds"] || all(isfinite,row[19:28])) || throw(NumericalFailure("non-finite available force readout"))
    row
end

function advance!(run, rows, step; until=run.contract.stop, stop_after_steps=typemax(Int))
    # WP2's CV storage requires an actually completed time step. Its first
    # sample therefore follows step one; all registered windows start later.
    if isempty(rows) && run.available["cv"] && step==0
        sim_step!(run.sim);step+=1
    end
    isempty(rows) && push!(rows,force_row(run,step))
    taken = 0
    while sim_time(run.sim) < until && taken < stop_after_steps
        sim_step!(run.sim); step += 1; taken += 1
        if step % run.contract.sample_every == 0 || sim_time(run.sim) >= until
            push!(rows,force_row(run,step))
        end
    end
    step
end

"""Exact endpoint-clipped trapezoid; no endpoint/sample-count surrogate."""
function window_mean(rows,column,start,stop)
    rows[1][2] <= start < stop <= rows[end][2] || error("force samples do not bracket complete window")
    total = 0.0
    for (a,b) in zip(rows[1:end-1],rows[2:end])
        lo,hi = max(start,a[2]),min(stop,b[2])
        if lo < hi
            slope = (b[column]-a[column])/(b[2]-a[2])
            total += (a[column]+slope*((lo+hi)/2-a[2]))*(hi-lo)
        end
    end
    total/(stop-start)
end

function save_checkpoint(path,sim,step,rows; fingerprint)
    ispath(path) && error("refusing to overwrite checkpoint")
    if checkpoint_available()
        isempty(rows) && error("checkpoint needs at least one force sample")
        width=length(first(rows))
        all(length(row)==width for row in rows) || error("checkpoint sample widths differ")
        columns=[i for i in 1:width if all(isfinite(row[i]) for row in rows)]
        omitted=setdiff(1:width,columns)
        all(i in 19:28 && all(isnan(row[i]) for row in rows) for i in omitted) || error("checkpoint has nonfinite available columns")
        # WP1 accepts finite numerical rows. The missing-readout mask and
        # width are explicit identity fields; no zero substitutes are stored.
        identity=join((fingerprint,"topo2d-finite-columns-v1",string(width),join(columns,',')),'|')
        Checkpoint.save_checkpoint(path,sim,step,[row[columns] for row in rows];identity)
        return path
    end
    sim.flow.u isa Array || error("GPU checkpoint requires the integrated WP1 checkpointer; CPU Serialization fallback is not a CUDA restore")
    open(path,"w") do io
        serialize(io,(; schema="topo2d-checkpoint-v1",fingerprint,sim,step,rows))
    end
end

function load_checkpoint(path; fingerprint,sim=nothing)
    if checkpoint_available()
        data=Checkpoint.load_checkpoint(path)
        identity=split(data.identity,'|')
        length(identity)==4 && identity[1]==fingerprint && identity[2]=="topo2d-finite-columns-v1" || error("checkpoint source/scene/runtime/window identity mismatch")
        width=parse(Int,identity[3]);columns=parse.(Int,split(identity[4],','))
        expected=[i for i in 1:width if isdefined(@__MODULE__,:force_readouts) || !(i in 19:28)]
        width in (33,38,43) && columns==expected || error("checkpoint finite-column identity is invalid")
        sim===nothing && error("WP1 restore requires a newly constructed identical simulation")
        expected_identity=join((fingerprint,"topo2d-finite-columns-v1",string(width),join(expected,',')),'|')
        Checkpoint.restore_checkpoint!(sim,data;identity=expected_identity)
        rows=[begin
            length(row)==length(columns) || error("checkpoint row width differs")
            full=fill(NaN,width);full[columns]=row;full
        end for row in data.rows]
        return (;schema="topo2d-wp1-checkpoint-v1",fingerprint,sim,step=data.step,rows)
    end
    saved = open(deserialize,path)
    saved.schema == "topo2d-checkpoint-v1" && saved.fingerprint == fingerprint || error("checkpoint source/scene/runtime/window identity mismatch")
    saved
end

"""Wing-only BDIM face-core probes at every registered mirror-paired phase.

The geometry's pinned guarded bulk stations exclude the preserved LE cap and
terminal cap. These checks do not claim a flat core at every boundary point.
"""
function phase_core_checks(scene)
    checks=0
    largest_distance=-Inf
    for k in 1:8, mirror in (1,-1)
        shift=(mirror*(mod(k*0.7548776662,1)-0.5),mirror*(mod(k*0.5698402910,1)-0.5))
        for (polygon,stations) in zip(scene.polygons,scene.probes)
            vertices=Tuple((Float32(p[1]/scene.dx_mm+12+shift[1]),Float32(p[2]/scene.dx_mm+8+shift[2])) for p in polygon)
            body=AutoBody(PolygonSDF(vertices))
            isempty(stations) && error("no geometry-guarded bulk core probes")
            for station in stations, axis in (1,2)
                target=(station[1]/scene.dx_mm+12+shift[1],station[2]/scene.dx_mm+8+shift[2])
                index=CartesianIndex(ntuple(j->round(Int,target[j]+1.5+(axis==j ? 0.5 : 0)),2))
                face=WaterLily.loc(axis,index,Float32)
                center=WaterLily.loc(0,index,Float32)
                df=WaterLily.measure(body,face,0.0f0)[1]
                dc=WaterLily.measure(body,center,0.0f0)[1]
                dc<0 && isfinite(df) || error("guarded wing-core probe is not inside")
                corrected=abs(df)<=0.5 ? df : copysign(df,dc)
                WaterLily.μ₀(corrected,1)==0 || error("wing-only μ0 core failed at phase $k/$mirror, axis $axis")
                largest_distance=max(largest_distance,Float64(corrected));checks+=1
            end
        end
    end
    Dict("passed"=>true,"phases"=>16,"face_probe_count"=>checks,"largest_face_distance_cells"=>largest_distance,
        "scope"=>"geometry-guarded controlled bulk stations; leading and terminal caps excluded")
end

function write_outputs(run,rows,step,out; wall_seconds)
    c = run.contract
    all(isfinite,run.sim.flow.u) && all(isfinite,run.sim.flow.p) || throw(NumericalFailure("non-finite flow"))
    csv_path = joinpath(out,c.case_id*".forces.csv")
    ispath(csv_path) && error("force CSV already exists")
    open(csv_path,"w") do io
        println(io,join(run.columns,','))
        for row in rows
            println(io,join(row,','))
        end
    end
    means = Dict(q=>window_mean(rows,col,c.start,c.stop) for (q,col) in (("drag",6),("downforce",7)))
    middle = (c.start+c.stop)/2
    drifts = Dict(q=>abs(window_mean(rows,col,c.start,middle)-window_mean(rows,col,middle,c.stop))/max(abs(means[q]),eps(Float64)) for (q,col) in (("drag",6),("downforce",7)))
    summary = Dict("schema"=>"topo2d-job-summary-v1","case_id"=>c.case_id,"scene_sha256"=>run.scene.sha256,"topo2d"=>run.ident,
        "observable"=>"total_cl","h_over_c1"=>run.scene.height_mm/C1_MM,"h_over_c"=>run.scene.height_mm/380,
        "source_sha256"=>source_hashes(c.backend),"runtime"=>runtime_identity(c.backend),"backend"=>(c.backend=="cuda" ? "WaterLily CUDA" : "WaterLily CPU"),"smoke"=>c.smoke,
        "phase_shift_m"=>collect(c.phase_shift_m),"flow_dims"=>collect(c.dims),"solver_length"=>c.L,"reynolds"=>Float64(c.reynolds),
        "top_factor"=>c.top_factor,
        "flow_origin_m"=>[c.x0/1000,0.0,c.z0/1000],
        "reference_chord_mm"=>C1_MM,"force_unit"=>"N/m","force_scale_n_per_m"=>run.scene.dx_mm/1000,
        "force_projection_semantics"=>"drag=+Fx; downforce=-Fz","ground_velocity_solver"=>[1.0,0.0],"ground_plane_solver"=>Float64(run.ground.z),
        "finite_u"=>true,"finite_p"=>true,"finite_forces"=>true,"window_t_u_l"=>[Float64(c.start),Float64(c.stop)],
        "t_end_reached"=>Float64(sim_time(run.sim)),"batch_count"=>c.batches,"sample_every_solver_steps"=>c.sample_every,"steps"=>step,
        "readout_available"=>run.available,"readout_note"=>(run.available["nds"] ? "WP2 force_readouts: explicit wing-only body and validated immutable box" : "WP2 wing-only readouts absent: cur only; nds/cv reserved as NaN in CSV"),
        "checkpoint_provider"=>(checkpoint_available() ? "WP1_DATA_ONLY_FINITE_COLUMN_ADAPTER" : "TOPO2D_CPU_SERIALIZATION"),
        "checkpoint_note"=>(checkpoint_available() ? "WP1 source-pinned finite-column payload, explicit missing-column mask, fresh-simulation restore and default remeasurement" : "WP1 absent: isolated CPU full-simulation fallback with source/runtime/scene/window identity"),
        "wall_seconds"=>wall_seconds,"force_csv_sha256"=>file_sha(csv_path),"stationarity_relative_half_window_drift"=>drifts,
        "drag_time_weighted_n_per_m"=>means["drag"]*run.scene.dx_mm/1000,"downforce_time_weighted_n_per_m"=>means["downforce"]*run.scene.dx_mm/1000,
        "cd_time_weighted"=>2means["drag"]/c.L,"cl_time_weighted"=>2means["downforce"]/c.L)
    toml_path = joinpath(out,c.case_id*".summary.toml")
    open(toml_path,"w") do io
        TOML.print(io,summary; sorted=true)
    end
    summary_path = joinpath(out,c.case_id*".summary.json")
    Base.run(`$PYTHON $BRIDGE summary-json $toml_path $summary_path`)
    write(joinpath(out,"W4_JOB_DONE"),"TOPO-2D job returned; host verification required.\n")
    summary
end

function main_loaded(args)
    length(args)==2 || error("usage: waterlily_topo2d_job.jl SCENE.json OUTPUT_DIR")
    scene_path,out = args
    ispath(out) && any(f->f!="job.log",readdir(out)) && error("output directory must be empty (apart from runner job.log)")
    backend = get(ENV,"TOPO2D_BACKEND","cpu")
    backend == "cuda" && !checkpoint_available() && any(haskey(ENV,k) for k in ("TOPO2D_CHECKPOINT","TOPO2D_RESUME")) && error("GPU checkpoint unavailable until WP1 integration")
    expected_job = get(ENV,"W4_JOB_SHA256","")
    expected_job == file_sha(joinpath(ROOT,"scripts","waterlily_topo2d_job.jl")) || error("job source SHA mismatch")
    scene = load_scene(scene_path,get(ENV,"W4_SCENE_SHA256",""))
    required = ("TOPO2D_REYNOLDS","TOPO2D_WINDOW_START","TOPO2D_WINDOW_END","W4_CANONICAL_ORIGIN_M","TOPO2D_PHASE","TOPO2D_GRID","TOPO2D_ROLE","TOPO2D_CASE_ID")
    all(k->haskey(ENV,k),required) || error("missing required TOPO-2D job contract environment")
    smoke = get(ENV,"TOPO2D_SMOKE","0")=="1"
    smoke || get(ENV,"TOPO2D_WINDOW_FROZEN","0")=="1" || error("formal window must be frozen from E1 parent formula")
    dims = haskey(ENV,"TOPO2D_DIMS") ? Tuple(parse.(Int,split(ENV["TOPO2D_DIMS"],','))) : nothing
    run_data = setup(scene;reynolds=parse(Float64,ENV["TOPO2D_REYNOLDS"]),phase_shift_m=Tuple(parse.(Float64,split(ENV["W4_CANONICAL_ORIGIN_M"],','))),
        dims,smoke,start=parse(Float64,ENV["TOPO2D_WINDOW_START"]),stop=parse(Float64,ENV["TOPO2D_WINDOW_END"]),
        sample_every=parse(Int,get(ENV,"TOPO2D_SAMPLE_EVERY","8")),batches=parse(Int,get(ENV,"TOPO2D_BATCHES","8")),
        case_id=ENV["TOPO2D_CASE_ID"],phase=ENV["TOPO2D_PHASE"],role=ENV["TOPO2D_ROLE"],grid=ENV["TOPO2D_GRID"],top_factor=parse(Float64,get(ENV,"TOPO2D_TOP_FACTOR","1")),backend)
    rows,step = Vector{Float64}[],0
    if haskey(ENV,"TOPO2D_RESUME")
        saved = load_checkpoint(ENV["TOPO2D_RESUME"];fingerprint=run_data.fingerprint,sim=run_data.sim)
        run_data = merge(run_data,(;sim=saved.sim));rows,step=saved.rows,saved.step
    end
    mkpath(out)
    preflight=Dict("schema"=>"topo2d-job-preflight-v1","topo2d"=>run_data.ident,"scene_sha256"=>scene.sha256,
        "observable"=>"total_cl","h_over_c1"=>scene.height_mm/C1_MM,"h_over_c"=>scene.height_mm/380,
        "source_sha256"=>source_hashes(backend),"runtime"=>runtime_identity(backend),"smoke"=>smoke,
        "phase_shift_m"=>collect(run_data.contract.phase_shift_m),"window_t_u_l"=>[run_data.contract.start,run_data.contract.stop],
        "flow_dims"=>collect(run_data.contract.dims),"contract_fingerprint"=>run_data.fingerprint)
    preflight_toml=joinpath(out,"job_preflight.toml")
    open(preflight_toml,"w") do io
        TOML.print(io,preflight;sorted=true)
    end
    Base.run(`$PYTHON $BRIDGE summary-json $preflight_toml $(joinpath(out,"job_preflight.json"))`)
    started=time()
    try
        if haskey(ENV,"TOPO2D_CHECKPOINT")
            step=advance!(run_data,rows,step;stop_after_steps=parse(Int,get(ENV,"TOPO2D_CHECKPOINT_STEPS","8")))
            save_checkpoint(ENV["TOPO2D_CHECKPOINT"],run_data.sim,step,rows;fingerprint=run_data.fingerprint)
            get(ENV,"TOPO2D_CHECKPOINT_ONLY","0")=="1" && return nothing
        end
        step=advance!(run_data,rows,step)
        write_outputs(run_data,rows,step,out;wall_seconds=time()-started)
    catch err
        err isa NumericalFailure || rethrow()
        failure=Dict("schema"=>"topo2d-job-failure-v1","status"=>"NUMERICAL","topo2d"=>run_data.ident,
            "observable"=>"total_cl","h_over_c1"=>scene.height_mm/C1_MM,"h_over_c"=>scene.height_mm/380,
            "scene_sha256"=>scene.sha256,"source_sha256"=>source_hashes(backend),"runtime"=>runtime_identity(backend),
            "phase_shift_m"=>collect(run_data.contract.phase_shift_m),"window_t_u_l"=>[run_data.contract.start,run_data.contract.stop],
            "flow_dims"=>collect(run_data.contract.dims),"contract_fingerprint"=>run_data.fingerprint,
            "smoke"=>smoke,"reason"=>sprint(showerror,err),"wall_seconds"=>time()-started)
        toml_path=joinpath(out,"numerical_failure.toml")
        open(toml_path,"w") do io
            TOML.print(io,failure;sorted=true)
        end
        Base.run(`$PYTHON $BRIDGE summary-json $toml_path $(joinpath(out,"numerical_failure.json"))`)
        write(joinpath(out,"ERROR.txt"),"NUMERICAL: "*sprint(showerror,err)*"\n")
        exit(42)
    end
end

function main(args=ARGS)
    backend = get(ENV,"TOPO2D_BACKEND","cpu")
    backend in ("cpu","cuda") || error("unknown TOPO2D_BACKEND")
    if backend=="cuda"
        # This branch is never entered by CPU smoke/selftest. The future
        # frozen runner must supply the qualified device UUID before launch.
        haskey(ENV,"W4_SELECTED_GPU_UUID") || error("CUDA requires a frozen/qualified selected UUID")
        !checkpoint_available() && any(haskey(ENV,k) for k in ("TOPO2D_CHECKPOINT","TOPO2D_RESUME")) && error("GPU checkpoint unavailable until WP1 integration; CUDA was not loaded")
        Base.eval(@__MODULE__,:(using CUDA))
        return Base.invokelatest(main_loaded,args)
    end
    main_loaded(args)
end

end # module
