# FORCE-00 U1/U2: CPU geometry only; no Poisson solve or simulation step.
# julia --project=julia/CFDSDFWaterLily scripts/force00_uniform_pressure.jl [new-output.json]
using WaterLily, LinearAlgebra, SHA, TOML
const ROOT = normpath(joinpath(@__DIR__, ".."))
const LOCAL_SOURCES = ("scripts/force00_uniform_pressure.jl", "scripts/force00_uniform_inputs.py",
    "julia/CFDSDFWaterLily/Project.toml", "julia/CFDSDFWaterLily/Manifest.toml",
    ("julia/CFDSDFWaterLily/src/" * name for name in (
        "CFDSDFWaterLily.jl", "Runtime.jl", "Forces.jl", "Simulation.jl", "GridSDFBody.jl", "WaterLilyBody.jl",
        "WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl"))...)
const START_SOURCE_HASHES = Dict(file => bytes2hex(sha256(read(joinpath(ROOT,file)))) for file in LOCAL_SOURCES)
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily
using .CFDSDFWaterLily.GridSDFBody
for file in ("WaterLilyNormalFloorBody.jl", "CandidateCWaterLilyBody.jl", "V16W4Sensitivity.jl")
    Base.include(CFDSDFWaterLily, joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", file))
end

const PYTHON = get(ENV, "FORCE00_PYTHON", joinpath(ROOT, ".venv", "bin", "python"))
const BRIDGE = joinpath(@__DIR__, "force00_uniform_inputs.py")

function uniform_flow(body, dims)
    # No Simulation/Poisson allocation: the readouts need only measured Flow.
    flow = WaterLily.Flow(dims, (0., 0., 0.); T=Float64, mem=Array)
    WaterLily.measure!(flow, body)
    flow.p .= 1.; flow.u .= 0.; flow.u⁰ .= 0.
    push!(flow.Δt, flow.Δt[end]) # zero storage; no solver time step was taken
    return (; flow, body)
end

function uniform_row(sim; metadata...)
    box = ntuple(d -> 4:(size(sim.flow.p, d) - 3), 3)
    # These two rows are ∮p nds (reaction), rather than body forces.
    cur = WaterLily.pressure_force(sim.flow, sim.body)
    nds = CFDSDFWaterLily.pressure_force_nds(sim; box)
    cv = CFDSDFWaterLily.control_volume_force(sim, box)
    return Dict{String,Any}(string(k) => v for (k,v) in pairs((; metadata..., cur, nds, cv)))
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
    shape = Tuple(Int.(data["shape"]))
    phi = reshape(copy(reinterpret(Float32, read(data["raw_path"]))), shape)
    h0 = data["spacing_m"]
    grid = GridSDF(phi; origin=Tuple(data["origin_m"]), h=(h0,h0,h0),
        outside_value=3.0, margin_m=data["margin_m"])
    rows = Dict{String,Any}[]
    for case in CFDSDFWaterLily.V16W4Sensitivity.w4_cases(Tuple(data["origin_m"]), h0)
        case.case_id in ("flow_24", "flow_32") || continue
        h = case.flow_spacing_m
        for placement in data["placements"]
            shift = placement["shift_m"]
            # Shifting the canonical origin by +shift translates the body by +shift.
            origin = ntuple(d -> case.flow_origin_m[d] - shift[d], 3)
            inner = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, origin, h, 0.25)
            body = CFDSDFWaterLily.CandidateCWaterLilyBody(inner;
                normal_floor=0.25, transition_width=1.1444091796875e-4)
            sim = uniform_flow(body, case.flow_dims)
            push!(rows, uniform_row(sim; run="U1", body="v18_parent", grid=case.case_id,
                phase_id=placement["phase_id"], shift_m=shift,
                shift_cells=shift ./ h, projected_area=data["planform_area_m2"] / h^2))
        end
        println(stderr, "FORCE00_UNIFORM ", case.case_id, " placements=", length(data["placements"]))
    end
    for radius in (8,16,32)
        # W2a exact sphere SDF and physical radius. Crop the empty far field for
        # this geometry-only test; no flow/domain-sensitivity claim is made.
        h = CFDSDFWaterLily.SPHERE_RADIUS_M / radius
        dims = ntuple(_ -> 2radius + 16, 3)
        for placement in data["sphere_placements"]
            shift = placement["shift_m"]
            center = WaterLily.SVector{3,Float64}(ntuple(d -> radius + 8.0 + shift[d] / h, 3))
            body = WaterLily.AutoBody((x,t) -> sqrt(sum(abs2, x - center)) - radius)
            sim = uniform_flow(body, dims)
            push!(rows, uniform_row(sim; run="U2", body="w2a_sphere", radius_cells=radius,
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

abspath(PROGRAM_FILE) == abspath(@__FILE__) && main()
