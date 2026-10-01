# Diagnostic only: isolate world-map arithmetic and constant representation.
# No sim_step! call, pressure solve, threshold change, or qualification.
# Usage: julia --threads=1 --project=julia/CFDSDFWaterLily scripts/sdf_native_fd07_world_map_precision_probe.jl <control phi.raw> <fixed census faces.csv> <fresh output dir>
using WaterLily, Random, SHA, Statistics
const ROOT = abspath(joinpath(@__DIR__, ".."))
const SRC = joinpath(ROOT, "julia/CFDSDFWaterLily/src")
include(joinpath(SRC, "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily, .CFDSDFWaterLily.GridSDFBody
for name in ("V16PhysicalProfile.jl", "WaterLilyNormalFloorBody.jl")
    Base.include(CFDSDFWaterLily, joinpath(SRC, name))
end
const SHAPE = (121, 65, 49)
const ORIGIN = (-1.0, -0.8, -0.6)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const FLOW_SPACING = 0.8 / 24
const DIMS = (150, 72, 54)
digest(path) = bytes2hex(sha256(read(path)))
array_digest(a) = bytes2hex(sha256(reinterpret(UInt8, vec(a))))
function map_constants(map)
    map == "A" && return Float32.(FLOW_ORIGIN), Float32(FLOW_SPACING)
    map == "B" && return Float64.(Float32.(FLOW_ORIGIN)), Float64(Float32(FLOW_SPACING))
    map == "C" && return FLOW_ORIGIN, FLOW_SPACING
    error("unregistered map")
end
function main(raw, fixed_faces, outdir)
    ispath(outdir) && error("refusing existing diagnostic output directory")
    length(read(raw)) == prod(SHAPE) * 4 || error("raw phi shape mismatch")
    digest(raw) == "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431" || error("not registered v17 raw phi")
    records = split.(readlines(fixed_faces)[2:end], ',')
    samples = [(CartesianIndex(parse.(Int, r[1:3])...), parse(Int, r[5])) for r in records]
    length(unique(samples)) == length(samples) || error("duplicate fixed faces")
    # Save all conditions and source/runtime identities before constructing any simulation.
    mkpath(outdir)
    open(joinpath(outdir, "preregistration.txt"), "w") do io
        println(io, "evidence_class=diagnostic_only; solver_started=false; qualification=false")
        println(io, "matrix=A,B,C x baseline,seed1_plus_1e-8,seed1_minus_1e-8; nine initializations; zero flow steps")
        println(io, "solver_and_returned_distance=Float32; phi_storage=Float32; SDF_origin=", ORIGIN, "; SDF_h=.025; normal_floor=.25")
        println(io, "A=Float32 map arithmetic and Float32 constants")
        println(io, "B=Float64 map arithmetic and Float64(Float32) constants")
        println(io, "C=Float64 map arithmetic and original Float64 physical constants")
        println(io, "phi_raw_sha256=", digest(raw), "; fixed_faces_sha256=", digest(fixed_faces), "; fixed_faces_count=", length(samples))
        println(io, "noise=randn(MersenneTwister(1),Float64,(121,65,49)); same realization across all maps/signs")
        println(io, "scalar_ablation=same measured center/face distances with production copysign enabled versus no sign correction; unchanged .5 threshold; no solver modification")
        println(io, "flow_origin=", FLOW_ORIGIN, "; spacing=", FLOW_SPACING, "; dims=", DIMS, "; moving_ground_solver_z=0; ground_velocity=1")
        println(io, "limits=one seed; fixed exposed faces selected by prior control census; finite precision; no force, FD, optimizer or physical qualification")
        println(io, "julia_version=", VERSION, "; threads=", Threads.nthreads(), "; WaterLily_version=", pkgversion(WaterLily), "; actual_package=", pkgdir(WaterLily))
        for path in [@__FILE__, joinpath(ROOT, "julia/CFDSDFWaterLily/Project.toml"), joinpath(ROOT, "julia/CFDSDFWaterLily/Manifest.toml"),
                     sort(filter(p -> endswith(p, ".jl"), readdir(SRC; join=true)))...,
                     sort(filter(p -> endswith(p, ".jl"), readdir(joinpath(pkgdir(WaterLily), "src"); join=true)))...]
            println(io, "source_sha256 ", digest(path), "  ", path)
        end
    end
    base = reshape(copy(reinterpret(Float32, read(raw))), SHAPE)
    noise = randn(MersenneTwister(1), Float64, SHAPE)
    references = Dict()
    global_reference = nothing
    open(joinpath(outdir, "initial_fields.csv"), "w") do stats
        println(stats, "map,run_id,noise_sha256,mu0_sha256,mu1_sha256,mu0_max_delta_from_map_baseline,mu0_rms_delta_from_map_baseline,mu1_max_delta_from_map_baseline,mu0_max_delta_from_A_baseline")
        open(joinpath(outdir, "fixed_face_scalar_ablation.csv"), "w") do faces
            println(faces, "map,run_id,i,j,k,axis,center_solver,face_solver,corrected_face_solver,mu0_corrected,mu0_uncorrected")
            for map in ("A", "B", "C"), (run_id, eps) in (("baseline", 0.), ("seed1_plus_1e-8", 1e-8), ("seed1_minus_1e-8", -1e-8))
                phi = eps == 0. ? copy(base) : Float32.(Float64.(base) .+ eps .* noise)
                grid = GridSDF(phi; origin=ORIGIN, h=(.025,.025,.025), outside_value=3., margin_m=.15)
                fo, fs = map_constants(map)
                cand = CFDSDFWaterLily.NormalFloorWaterLilyBody(grid, fo, fs, typeof(fs)(.25))
                combined = cand + CFDSDFWaterLily.V16MovingGroundBody(0f0, 1f0)
                sim = WaterLily.Simulation(DIMS, CFDSDFWaterLily.v16_native_far_field_uBC, 24f0;
                    U=1f0, ν=.3f0, exitBC=true, body=combined, T=Float32, mem=Array)
                if run_id == "baseline"
                    references[map] = (copy(sim.flow.μ₀), copy(sim.flow.μ₁))
                    map == "A" && (global_reference = copy(sim.flow.μ₀))
                end
                m0, m1 = references[map]
                d0 = Float64.(sim.flow.μ₀) .- Float64.(m0)
                d1 = Float64.(sim.flow.μ₁) .- Float64.(m1)
                da = Float64.(sim.flow.μ₀) .- Float64.(global_reference)
                println(stats, join((map, run_id, array_digest(noise), array_digest(sim.flow.μ₀), array_digest(sim.flow.μ₁),
                    maximum(abs,d0), sqrt(mean(abs2,d0)), maximum(abs,d1), maximum(abs,da)), ','))
                for (I, axis) in samples
                    dc = WaterLily.sdf(combined, WaterLily.loc(0,I,Float32), 0f0; fastd²=0f0)
                    df = WaterLily.sdf(combined, WaterLily.loc(axis,I,Float32), 0f0; fastd²=0f0)
                    corrected = abs(df) <= .5f0 ? df : copysign(df,dc)
                    println(faces, join((map,run_id,I[1],I[2],I[3],axis,dc,df,corrected,WaterLily.μ₀(corrected,1),WaterLily.μ₀(df,1)), ','))
                end
            end
        end
    end
end
length(ARGS) == 3 || error("expected registered control raw, fixed faces CSV, fresh output directory")
main(ARGS...)
