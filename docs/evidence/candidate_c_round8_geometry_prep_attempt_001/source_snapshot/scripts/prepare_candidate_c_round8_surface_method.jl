# Geometry-only staging for #44 Round 8. This command never constructs a
# WaterLily Simulation and never advances CFD.
using SHA, DelimitedFiles
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "CFDSDFWaterLily.jl"))
using .CFDSDFWaterLily.GridSDFBody
include(joinpath(@__DIR__, "..", "julia", "CFDSDFWaterLily", "src", "SurfaceFluxQuadrature.jl"))
using .SurfaceFluxQuadrature

length(ARGS) == 3 || error("usage: prepare_candidate_c_round8_surface_method.jl <fixture_id> <input_dir> <output_dir>")
fixture, input_dir, output_dir = ARGS
fixture in ("sphere", "plate_1cell", "plate_2cell", "moving_ground_only") || error("unknown fixture")
isdir(input_dir) || error("input directory missing")
mkdir(output_dir) # exclusive: retain every preparation and never overwrite
sha(bytes) = bytes2hex(sha256(bytes))
sha_file(path) = open(path, "r") do io; bytes2hex(sha256(io)); end
const FLOW_DIMS = (100, 48, 36)
const FLOW_ORIGIN = (-2.5, -1.2, -0.9)
const H = 0.05
const GROUND_Z_SOLVER = 8.0

function write_hash(io, value)
    print(io, value)
    flush(io)
end

function dump_quadrature(path, result)
    open(path, "w") do io
        println(io, "point_id,x_m,y_m,z_m,nx_geom,ny_geom,nz_geom,weight_m2")
        for i in eachindex(result.points)
            p = result.points[i]; n = result.geometric_normals[i]
            println(io, join((i, p..., n..., result.area_weights_m2[i]), ","))
        end
    end
end

function load_body_inputs()
    phi_path = joinpath(input_dir, "canonical_phi_f32_fortran.bin")
    vertex_path = joinpath(input_dir, "seed_vertices.csv")
    face_path = joinpath(input_dir, "seed_faces.csv")
    manifest_path = joinpath(input_dir, "input_manifest.json")
    for path in (phi_path, vertex_path, face_path, manifest_path)
        isfile(path) || error("missing registered geometry input: $path")
    end
    shape = (61, 33, 25)
    raw_phi = read(phi_path)
    length(raw_phi) == prod(shape) * sizeof(Float32) || error("canonical phi binary has wrong length")
    values = copy(reinterpret(Float32, raw_phi))
    phi = reshape(values, shape)
    grid = GridSDF(phi; origin=(-1.0, -0.8, -0.6), h=(H,H,H),
        outside_value=3.0, margin_m=0.15)
    vertices_raw = readdlm(vertex_path, ',', Float64)
    faces_raw = readdlm(face_path, ',', Int)
    vertices = [Tuple(vertices_raw[i, :]) for i in axes(vertices_raw, 1)]
    faces = [Tuple(faces_raw[i, :]) for i in axes(faces_raw, 1)]
    manifest_sha = strip(first(split(read(joinpath(input_dir, "input_manifest.json.sha256"), String))))
    sha_file(manifest_path) == manifest_sha || error("input manifest SHA mismatch")
    input_phi_sha = sha_file(phi_path)
    manifest_text = read(manifest_path, String)
    phi_match = match(r"\"phi_sha256\"\s*:\s*\"([0-9a-f]{64})\"", manifest_text)
    phi_match === nothing && error("input manifest lacks canonical phi identity")
    input_phi_sha == phi_match.captures[1] ||
        error("phi hash differs from registered input manifest")
    return grid, vertices, faces, manifest_sha, input_phi_sha
end

function exact_grid_evaluator(grid)
    lo = grid.origin
    hi = ntuple(d -> grid.origin[d] + (grid.shape[d] - 1) * grid.h[d], 3)
    return function (x)
        all(d -> lo[d] <= x[d] <= hi[d], 1:3) || error("surface projection/evaluation escaped canonical GridSDF bounds")
        sdf_value_gradient_at_world(grid, x)
    end
end

function ground_patch()
    # Solver x=[2,97], y=[2,45], z=8 mapped to world coordinates.
    x0, x1 = FLOW_ORIGIN[1] + H * 2, FLOW_ORIGIN[1] + H * 97
    y0, y1 = FLOW_ORIGIN[2] + H * 2, FLOW_ORIGIN[2] + H * 45
    z = FLOW_ORIGIN[3] + H * GROUND_Z_SOLVER
    vertices = [(x0,y0,z), (x1,y0,z), (x1,y1,z), (x0,y1,z)]
    faces = [(1,2,3), (1,3,4)] # intentionally open patch; not a closed-body mesh
    evaluator = p -> (p[3] - z, (0.0, 0.0, 1.0))
    return vertices, faces, evaluator
end

function fixed_masks(grid)
    fluid = falses(FLOW_DIMS)
    transition = falses(FLOW_DIMS)
    for k in 2:FLOW_DIMS[3]-1, j in 2:FLOW_DIMS[2]-1, i in 2:FLOW_DIMS[1]-1
        xsolver = (i - 1.5, j - 1.5, k - 1.5)
        xworld = ntuple(d -> FLOW_ORIGIN[d] + H * xsolver[d], 3)
        body_d = grid === nothing ? Inf : sdf_at_world(grid, xworld) / H
        union_d = min(body_d, xsolver[3] - GROUND_Z_SOLVER)
        fluid[i,j,k] = union_d > 0
        transition[i,j,k] = 0 < union_d <= 1
    end
    return fluid, transition
end

grid = nothing
body_vertices = Tuple{Float64,Float64,Float64}[]
body_faces = NTuple{3,Int}[]
input_manifest_sha = "none"
phi_sha = "none"
if fixture != "moving_ground_only"
    grid, body_vertices, body_faces, input_manifest_sha, phi_sha = load_body_inputs()
end
fluid, transition = fixed_masks(grid)
mask_bytes = vcat(vec(UInt8.(fluid)), vec(UInt8.(transition)))
mask_path = joinpath(output_dir, "fixed_fluid_transition_masks.bin")
open(mask_path, "w") do io; write(io, mask_bytes); end
open(joinpath(output_dir, "mask_manifest.txt"), "w") do io
    println(io, "dims=$(join(FLOW_DIMS, ','))")
    println(io, "array_order=Fortran/i-fastest")
    println(io, "fluid_count=$(count(fluid))")
    println(io, "transition_count=$(count(transition))")
    println(io, "mask_sha256=$(sha(mask_bytes))")
    println(io, "input_manifest_sha256=$input_manifest_sha")
    println(io, "phi_sha256=$phi_sha")
end

manifest_path = joinpath(output_dir, "method_manifest.txt")
open(manifest_path, "w") do io
    println(io, "fixture=$fixture")
    println(io, "input_manifest_sha256=$input_manifest_sha")
    println(io, "phi_sha256=$phi_sha")
    println(io, "mask_sha256=$(sha(mask_bytes))")
    for kind in (fixture == "moving_ground_only" ? (:ground,) : (:body, :ground))
        vertices, faces, evaluator = if kind === :body
            (body_vertices, body_faces, exact_grid_evaluator(grid))
        else
            ground_patch()
        end
        for level in 0:2
            result = refined_surface_quadrature(vertices, faces, evaluator; level,
                projection_tolerance_m=1e-10, max_projection_iterations=20)
            path = joinpath(output_dir, "$(kind)_level$(level)_quadrature.csv")
            dump_quadrature(path, result)
            println(io, "$(kind)_level$(level)_csv_sha256=$(sha_file(path))")
            println(io, "$(kind)_level$(level)_triangle_count=$(result.triangle_count)")
            println(io, "$(kind)_level$(level)_area_m2=$(result.area_m2)")
        end
    end
    println(io, "mask_file_sha256=$(sha_file(mask_path))")
    println(io, "method_source_sha256=$(sha_file(@__FILE__))")
end
println(read(manifest_path, String))
