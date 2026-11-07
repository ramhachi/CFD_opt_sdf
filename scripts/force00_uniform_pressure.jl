# FORCE-00 U1/U2: CPU geometry only; no Poisson solve or simulation step.
# julia --project=julia/CFDSDFWaterLily scripts/force00_uniform_pressure.jl [new-output.json]
using WaterLily, LinearAlgebra, SHA, TOML
const ROOT = normpath(joinpath(@__DIR__, ".."))
const LOCAL_SOURCES = ("scripts/force00_uniform_pressure.jl", "scripts/force00_uniform_inputs.py",
    "scripts/force00_boxes.py", "scripts/waterlily_force00_job.jl", "scripts/waterlily_force00_dispatch.jl",
    "julia/CFDSDFWaterLily/Project.toml", "julia/CFDSDFWaterLily/Manifest.toml",
    "julia/CFDSDFWaterLily/gen01/Force00.jl",
    ("julia/CFDSDFWaterLily/src/" * name for name in (
        "CFDSDFWaterLily.jl", "Runtime.jl", "Forces.jl", "Simulation.jl", "GridSDFBody.jl", "WaterLilyBody.jl",
        "V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl"))...)
const START_SOURCE_HASHES = Dict(file => bytes2hex(sha256(read(joinpath(ROOT,file)))) for file in LOCAL_SOURCES)
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "gen01", "Force00.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for file in ("V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")
    Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", file))
end

const PYTHON = get(ENV, "FORCE00_PYTHON", joinpath(ROOT, ".venv", "bin", "python"))
const BRIDGE = joinpath(@__DIR__, "force00_uniform_inputs.py")
const BOX_BRIDGE = joinpath(@__DIR__, "force00_boxes.py")
const BOX_REGISTRY = "docs/harness/force00_boxes.json"

function uniform_flow(body, dims; T=Float64)
    # No Simulation/Poisson allocation: the readouts need only measured Flow.
    flow = WaterLily.Flow(dims, (zero(T), zero(T), zero(T)); T=T, mem=Array)
    WaterLily.measure!(flow, body)
    flow.p .= 1.; flow.u .= 0.; flow.u⁰ .= 0.
    push!(flow.Δt, flow.Δt[end]) # zero storage; no solver time step was taken
    return (; flow, body)
end

function uniform_row(sim, box; metadata...)
    CFDSDFWaterLily.validate_force_box(sim, box)
    # These two rows are ∮p nds (reaction), rather than body forces.
    cur = WaterLily.pressure_force(sim.flow, sim.body)
    nds = CFDSDFWaterLily.pressure_force_nds(sim; box)
    cv = CFDSDFWaterLily.control_volume_force(sim, box)
    return Dict{String,Any}(string(k) => v for (k,v) in pairs((; metadata...,
        box_lower=collect(first.(box)), box_upper=collect(last.(box)), cur, nds, cv)))
end

function parent_grid(data)
    shape = Tuple(Int.(data["shape"]))
    phi = reshape(copy(reinterpret(Float32, read(data["raw_path"]))), shape)
    h0 = data["spacing_m"]
    GridSDF(phi; origin=Tuple(data["origin_m"]), h=(h0,h0,h0),
        outside_value=3.0, margin_m=data["margin_m"])
end

function parent_body(grid, origin, h, ::Type{T}=Float64; ground=false) where T
    inner = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, T.(origin), T(h), T(0.25))
    kwargs = (; normal_floor=T(0.25), transition_width=T(1.1444091796875e-4))
    ground ? CFDSDFWaterLily.CandidateCWaterLilyBody(inner,
        CFDSDFWaterLily.V16MovingGroundBody(zero(T), one(T)); kwargs...) :
        CFDSDFWaterLily.CandidateCWaterLilyBody(inner; kwargs...)
end

function box_support()
    data = TOML.parse(read(`$PYTHON $BRIDGE inputs`, String))
    grid = parent_grid(data)
    records = Dict{String,Any}()
    for case in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(Tuple(data["origin_m"]), data["spacing_m"])
        case.case_id in ("flow_24", "flow_32") || continue
        body = parent_body(grid, case.flow_origin_m, case.flow_spacing_m, Float32)
        sim = uniform_flow(body, case.flow_dims; T=Float32)
        lower, upper = fill(typemax(Int), 3), fill(typemin(Int), 3)
        count = 0
        # Exclude only artificial zeroed domain-normal faces. This scans every
        # physical candidate face, including the solid, using measured moments.
        for I in WaterLily.inside(sim.flow.p; buff=2)
            if any(i -> sim.flow.μ₀[I, i] < 1, 1:3)
                lower .= min.(lower, Tuple(I)); upper .= max.(upper, Tuple(I))
                count += 1
            end
        end
        count > 0 || error("empty parent moment support")
        records[case.case_id] = Dict("flow_dims" => collect(case.flow_dims),
            "mu0_support_lower" => lower, "mu0_support_upper" => upper,
            "mu0_support_count" => count)
        # The largest allowed box has bottom normal face z=4 above the ground.
        # Independently preflight its complete scene, including exact mu0 faces.
        combined = parent_body(grid, case.flow_origin_m, case.flow_spacing_m, Float32; ground=true)
        WaterLily.measure!(sim.flow, combined)
        scene = (; flow=sim.flow, body=combined)
        box = (4:(case.flow_dims[1]-1), 4:(case.flow_dims[2]-1), 6:(case.flow_dims[3]-1))
        CFDSDFWaterLily.validate_force_box(scene, box; body)
    end
    hashes = merge(data["source_sha256"], Dict(file => bytes2hex(sha256(read(joinpath(ROOT,file))))
        for file in LOCAL_SOURCES if !(file in ("scripts/waterlily_force00_job.jl", "scripts/waterlily_force00_dispatch.jl"))))
    TOML.print(stdout, Dict("schema" => "force00_box_support_v1", "phase_shift_m" => [0.0,0.0,0.0],
        "field_type" => "Float32", "waterlily_version" => string(pkgversion(WaterLily)),
        "ground_plane_solver" => 0.0, "source_sha256" => hashes, "grids" => records); sorted=true)
end

function force_summary(rows, readout)
    lengths = [norm(row[readout]) for row in rows]
    return Dict("max" => maximum(lengths), "rms" => sqrt(sum(abs2, lengths) / length(lengths)))
end

function main()
    length(ARGS) <= 1 || error("usage: force00_uniform_pressure.jl [new-output.json]")
    pkgversion(WaterLily) == v"1.8.0" || error("FORCE-00 requires pinned WaterLily 1.8.0")
    output = isempty(ARGS) ? joinpath(ROOT, "docs", "evidence", "force00_2026_11", "uniform_pressure.json") : abspath(ARGS[1])
    ispath(output) && error("refusing existing output: $output")
    data = TOML.parse(read(`$PYTHON $BRIDGE inputs`, String))
    boxes = TOML.parse(read(`$PYTHON $BOX_BRIDGE --toml`, String))
    registry_start_sha = boxes["registry_sha256"]
    h0 = data["spacing_m"]
    grid = parent_grid(data)
    rows = Dict{String,Any}[]
    for case in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(Tuple(data["origin_m"]), h0)
        case.case_id in ("flow_24", "flow_32") || continue
        h = case.flow_spacing_m
        record = boxes["grids"][case.case_id]
        record["flow_dims"] == collect(case.flow_dims) || error("registered box grid mismatch")
        box = ntuple(i -> record["lower"][i]:record["upper"][i], 3)
        for placement in data["placements"]
            shift = placement["shift_m"]
            # Shifting the canonical origin by +shift translates the body by +shift.
            origin = ntuple(d -> case.flow_origin_m[d] - shift[d], 3)
            body = parent_body(grid, origin, h)
            sim = uniform_flow(body, case.flow_dims)
            push!(rows, uniform_row(sim, box; run="U1", body="v18_parent", grid=case.case_id,
                phase_id=placement["phase_id"], shift_m=shift,
                shift_cells=shift ./ h, projected_area=data["planform_area_m2"] / h^2))
        end
        println(stderr, "FORCE00_UNIFORM ", case.case_id, " placements=", length(data["placements"]))
    end
    for radius in (8,16,32)
        # W2a exact sphere SDF and physical radius. Crop the empty far field for
        # this geometry-only test; no flow/domain-sensitivity claim is made.
        h = data["sphere_radius_m"] / radius
        dims = ntuple(_ -> 2radius + 16, 3)
        for placement in data["sphere_placements"]
            shift = placement["shift_m"]
            center = WaterLily.SVector{3,Float64}(ntuple(d -> radius + 8.0 + shift[d] / h, 3))
            body = WaterLily.AutoBody((x,t) -> sqrt(sum(abs2, x - center)) - radius)
            sim = uniform_flow(body, dims)
            box = ntuple(d -> 4:(size(sim.flow.p, d) - 3), 3)
            push!(rows, uniform_row(sim, box; run="U2", body="w2a_sphere", radius_cells=radius,
                phase_id=placement["phase_id"], shift_m=shift, shift_cells=shift ./ h,
                physical_center_m=collect(CFDSDFWaterLily.SPHERE_CENTER_M) + shift,
                projected_area=π * radius^2))
        end
        println(stderr, "FORCE00_UNIFORM sphere R=", radius, " placements=", length(data["sphere_placements"]))
    end
    summary = Dict{String,Any}()
    for (name, subset) in (("U1_flow_24", filter(r -> get(r,"grid","") == "flow_24", rows)),
                           ("U1_flow_32", filter(r -> get(r,"grid","") == "flow_32", rows)),
                           ("U2_sphere", filter(r -> r["run"] == "U2", rows)))
        summary[name] = Dict(readout => force_summary(subset, readout) for readout in ("cur","nds","cv"))
    end
    for radius in (8,16,32)
        subset = filter(r -> get(r,"radius_cells",0) == radius, rows)
        summary["U2_R$radius"] = Dict(readout => force_summary(subset, readout) for readout in ("cur","nds","cv"))
    end
    hashes = data["source_sha256"]
    hashes[BOX_REGISTRY] = bytes2hex(sha256(read(joinpath(ROOT, BOX_REGISTRY))))
    hashes[BOX_REGISTRY] == registry_start_sha || error("box registry changed during CPU measurement")
    for file in LOCAL_SOURCES
        current = bytes2hex(sha256(read(joinpath(ROOT,file))))
        current == START_SOURCE_HASHES[file] || error("source changed during CPU measurement: $file")
        hashes[file] = current
    end
    waterlily_hashes = Dict(name => bytes2hex(sha256(read(joinpath(dirname(pathof(WaterLily)), name))))
        for name in ("Metrics.jl", "Flow.jl", "Body.jl", "AutoBody.jl", "util.jl"))
    document = Dict("schema" => "force00_uniform_pressure_v1", "evidence_class" => "CPU geometry closure; no solved flow",
        "waterlily_version" => string(pkgversion(WaterLily)), "julia_version" => string(VERSION),
        "field_type" => "Float64", "rows" => rows, "summary" => summary, "source_sha256" => hashes,
        "sphere_radius_m" => data["sphere_radius_m"],
        "waterlily_source_sha256" => waterlily_hashes,
        "pressure_semantics" => "cur/nds are pressure reaction integrals; cv is body force (uniform exact answer zero)",
        "area_source" => "v18 genesis measurements.planform_area_m2 / flow_spacing_m^2; sphere pi R^2",
        "phase_extension" => "FID V1 registered32 3D shifts, plus next4 mirror pairs z-only; U2 uses all3 components of those8 extra shifts",
        "issue369_reference" => Dict("source" => "docs/evidence/gen01_plan_2026_11_01/research/facts_for_w1_drafts.md section3",
            "circle_radii_cells" => [8,16,32], "circle_reported_residual" => [8.5e-3,2.7e-3,2.9e-2],
            "sphere_radius_cells" => 16, "sphere_reported_residual" => 0.29,
            "comparison_scope" => "different off-grid placements; descriptive comparison, not replay of upstream fixture"))
    buffer = IOBuffer(); TOML.print(buffer, document; sorted=true); seekstart(buffer)
    mkpath(dirname(output))
    run(pipeline(`$PYTHON $BRIDGE json $output`; stdin=buffer))
    println("FORCE00_UNIFORM_DONE rows=", length(rows), " sha256=", bytes2hex(sha256(read(output))))
end

if abspath(PROGRAM_FILE) == abspath(@__FILE__)
    ARGS == ["--box-support"] ? box_support() : main()
end
