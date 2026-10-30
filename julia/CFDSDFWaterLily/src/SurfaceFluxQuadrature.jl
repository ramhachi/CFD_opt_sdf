"""Small, fail-closed quadrature builder for a triangulated implicit surface.

Triangles are subdivided and their vertices projected before area weights are
formed. Quadrature points are then separately projected for field evaluation.
This is a diagnostic discretization; it does not define physical acceptance
limits or prove a quadrature error bound.
"""
module SurfaceFluxQuadrature

using LinearAlgebra: norm, dot

export refined_surface_quadrature

const BARYCENTRIC_3 = ((2 / 3, 1 / 6, 1 / 6),
                       (1 / 6, 2 / 3, 1 / 6),
                       (1 / 6, 1 / 6, 2 / 3))

_vadd(a, b) = (a[1] + b[1], a[2] + b[2], a[3] + b[3])
_vsub(a, b) = (a[1] - b[1], a[2] - b[2], a[3] - b[3])
_vscale(a, s) = (a[1] * s, a[2] * s, a[3] * s)
_cross(a, b) = (a[2] * b[3] - a[3] * b[2],
                 a[3] * b[1] - a[1] * b[3],
                 a[1] * b[2] - a[2] * b[1])

function _project(point, value_gradient; tol_m, max_iterations)
    x = Float64.(collect(point))
    for iteration in 0:max_iterations
        value, gradient = value_gradient(Tuple(x))
        isfinite(value) && all(isfinite, gradient) || error("non-finite surface projection sample")
        abs(value) <= tol_m && return (Tuple(x), iteration)
        iteration == max_iterations && break
        g2 = dot(gradient, gradient)
        isfinite(g2) && g2 > 0 || error("zero or non-finite surface gradient during projection")
        x .-= (value / g2) .* gradient
    end
    error("surface projection did not converge within $max_iterations iterations")
end

function _split(vertices, faces)
    out_vertices = copy(vertices)
    out_faces = Vector{NTuple{3,Int}}()
    edge_midpoints = Dict{Tuple{Int,Int},Int}()
    midpoint(i, j) = get!(edge_midpoints, minmax(i, j)) do
        push!(out_vertices, _vscale(_vadd(vertices[i], vertices[j]), 0.5))
        length(out_vertices)
    end
    for (a, b, c) in faces
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        append!(out_faces, ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
    end
    return out_vertices, out_faces
end

# An exactly zero-area face has zero surface measure. Allow its removal only
# for a closed surface whose exact-coordinate quotient remains a closed,
# consistently oriented mesh. Never discard a positive-area face by tolerance.
function _closed_zero_measure_quotient(vertices, faces)
    unique_vertices = NTuple{3,Float64}[]
    indices = Dict{NTuple{3,Float64},Int}()
    mapping = [get!(indices, Tuple(v)) do
        push!(unique_vertices, Tuple(v))
        length(unique_vertices)
    end for v in vertices]
    retained = NTuple{3,Int}[]
    zero_faces = Int[]
    for (i, (a, b, c)) in enumerate(faces)
        area = norm(collect(_cross(_vsub(vertices[b], vertices[a]),
                                   _vsub(vertices[c], vertices[a])))) / 2
        isfinite(area) || error("non-finite projected triangle $i")
        if iszero(area)
            push!(zero_faces, i)
        else
            push!(retained, (mapping[a], mapping[b], mapping[c]))
        end
    end
    isempty(retained) && error("closed surface has no positive-area faces")
    edges = Dict{Tuple{Int,Int},Tuple{Int,Int}}()
    for (a, b, c) in retained, (i, j) in ((a, b), (b, c), (c, a))
        key = minmax(i, j)
        count, orientation = get(edges, key, (0, 0))
        edges[key] = (count + 1, orientation + (i < j ? 1 : -1))
    end
    all(value -> value == (2, 0), values(edges)) ||
        error("exact zero-measure quotient leaves an open or inconsistently oriented surface")
    return unique_vertices, retained, (; zero_face_indices=zero_faces,
        input_face_count=length(faces), retained_face_count=length(retained),
        exact_vertex_mapping=mapping, closed_oriented_edge_audit=true)
end

"""
    refined_surface_quadrature(vertices, faces, value_gradient; level,
                               projection_tolerance_m=1e-10,
                               max_projection_iterations=20)

Build the fixed three-point triangle quadrature at a prescribed subdivision
level 0, 1, or 2. `value_gradient(x)` returns the signed field and its exact
world-space gradient at `x`. Every mesh vertex is projected before triangle
areas are computed; every quadrature point is independently projected before
its unit geometric normal is evaluated. Any invalid point rejects the entire
surface; samples are never silently dropped.
"""
function refined_surface_quadrature(vertices, faces, value_gradient;
        level::Integer, projection_tolerance_m=1e-10,
        max_projection_iterations::Integer=20, closed_surface::Bool=false)
    level in 0:2 || throw(ArgumentError("level must be 0, 1, or 2"))
    projection_tolerance_m > 0 && isfinite(projection_tolerance_m) ||
        throw(ArgumentError("projection tolerance must be finite and positive"))
    max_projection_iterations > 0 || throw(ArgumentError("iteration cap must be positive"))
    isempty(vertices) && error("seed surface has no vertices")
    isempty(faces) && error("seed surface has no triangles")
    all(v -> length(v) == 3 && all(isfinite, v), vertices) || error("invalid seed vertex")
    all(f -> length(f) == 3 && all(i -> 1 <= i <= length(vertices), f), faces) ||
        error("invalid seed triangle index")

    projected = [first(_project(v, value_gradient;
        tol_m=projection_tolerance_m, max_iterations=max_projection_iterations)) for v in vertices]
    refined_faces = NTuple{3,Int}[Tuple(f) for f in faces]
    coverage_audits = []
    if closed_surface
        projected, refined_faces, audit = _closed_zero_measure_quotient(projected, refined_faces)
        push!(coverage_audits, audit)
    end
    for _ in 1:level
        projected, refined_faces = _split(projected, refined_faces)
        projected = [first(_project(v, value_gradient;
            tol_m=projection_tolerance_m, max_iterations=max_projection_iterations)) for v in projected]
        if closed_surface
            projected, refined_faces, audit = _closed_zero_measure_quotient(projected, refined_faces)
            push!(coverage_audits, audit)
        end
    end

    points = NTuple{3,Float64}[]
    normals = NTuple{3,Float64}[]
    weights = Float64[]
    areas = Float64[]
    for (triangle_id, (a, b, c)) in enumerate(refined_faces)
        va, vb, vc = projected[a], projected[b], projected[c]
        area = norm(collect(_cross(_vsub(vb, va), _vsub(vc, va)))) / 2
        isfinite(area) && area > 0 || error("degenerate or non-finite projected triangle $triangle_id (area=$area m^2)")
        push!(areas, area)
        for bary in BARYCENTRIC_3
            seed = ntuple(d -> bary[1] * va[d] + bary[2] * vb[d] + bary[3] * vc[d], 3)
            point, _ = _project(seed, value_gradient;
                tol_m=projection_tolerance_m, max_iterations=max_projection_iterations)
            _, gradient = value_gradient(point)
            magnitude = norm(collect(gradient))
            isfinite(magnitude) && magnitude > 0 || error("zero or non-finite geometric normal")
            push!(points, point)
            push!(normals, _vscale(gradient, 1 / magnitude))
            push!(weights, area / 3)
        end
    end
    all(isfinite, weights) || error("non-finite quadrature weight")
    return (; level, closed_surface, coverage_audits,
        vertices=projected, faces=refined_faces, points, geometric_normals=normals,
        area_weights_m2=weights, triangle_areas_m2=areas,
        projected_vertex_count=length(projected), triangle_count=length(refined_faces),
        quadrature_point_count=length(points), area_m2=sum(areas))
end

end # module
