"""Geometry-preserving cleanup and local-SDF orientation for triangle surfaces.

The canonical grid convention is ``phi < 0`` in solid and ``phi > 0`` in fluid.
This module never changes vertex coordinates. It only merges exact coincident
coordinates, removes duplicate/degenerate triangles, and orients each face from
the local trilinear SDF gradient.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ORIENTATION_ROUNDOFF_FACTOR = 64.0


@dataclass(frozen=True)
class SurfaceCanonicalization:
    vertices: np.ndarray
    faces: np.ndarray
    audit: dict[str, object]


def trilinear_gradient(
    phi: np.ndarray,
    origin_m: tuple[float, float, float] | np.ndarray,
    spacing_m: float,
    point_m: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int], np.ndarray]:
    """Return the cell-local trilinear gradient, cell index, and corner values.

    Grid cells are half-open on their positive sides: ``floor`` assigns a point
    exactly on an interior grid plane to the cell on its positive side. The
    outermost grid plane is assigned to the final valid cell.
    """

    field = np.asarray(phi)
    point = np.asarray(point_m, dtype=np.float64)
    origin = np.asarray(origin_m, dtype=np.float64)
    spacing = float(spacing_m)
    if (
        field.ndim != 3
        or any(size < 2 for size in field.shape)
        or not np.isfinite(field).all()
    ):
        raise ValueError(
            "phi must be a finite three-dimensional field with at least two nodes per axis"
        )
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError("point_m must contain three finite coordinates")
    if (
        origin.shape != (3,)
        or not np.isfinite(origin).all()
        or not np.isfinite(spacing)
        or spacing <= 0
    ):
        raise ValueError("grid origin and spacing must be finite and spacing positive")

    q = (point - origin) / spacing
    upper = np.asarray(field.shape, dtype=np.int64) - 1
    if np.any(q < 0.0) or np.any(q > upper):
        raise ValueError("surface point lies outside the canonical SDF grid")
    cell = np.minimum(np.floor(q).astype(np.int64), upper - 1)
    t = q - cell
    i, j, k = (int(v) for v in cell)
    corners = np.asarray(
        [field[i + a, j + b, k + c] for a in (0, 1) for b in (0, 1) for c in (0, 1)],
        dtype=np.float64,
    ).reshape(2, 2, 2)

    gx = 0.0
    gy = 0.0
    gz = 0.0
    for b in (0, 1):
        wb = t[1] if b else 1.0 - t[1]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            gx += (corners[1, b, c] - corners[0, b, c]) * wb * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            gy += (corners[a, 1, c] - corners[a, 0, c]) * wa * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for b in (0, 1):
            wb = t[1] if b else 1.0 - t[1]
            gz += (corners[a, b, 1] - corners[a, b, 0]) * wa * wb

    return np.asarray((gx, gy, gz), dtype=np.float64) / spacing, (i, j, k), corners


def _face_components(faces: np.ndarray) -> list[np.ndarray]:
    """Stable edge-connected triangle components, ordered by first face index."""

    count = len(faces)
    parent = np.arange(count, dtype=np.int64)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    edge_faces: dict[tuple[int, int], list[int]] = {}
    for face_id, (a, b, c) in enumerate(faces):
        for left, right in ((a, b), (b, c), (c, a)):
            edge = (int(min(left, right)), int(max(left, right)))
            edge_faces.setdefault(edge, []).append(face_id)
    for incident in edge_faces.values():
        for face_id in incident[1:]:
            union(incident[0], face_id)

    groups: dict[int, list[int]] = {}
    for face_id in range(count):
        groups.setdefault(find(face_id), []).append(face_id)
    return [
        np.asarray(group, dtype=np.int64)
        for group in sorted(groups.values(), key=lambda row: row[0])
    ]


def canonicalize_triangle_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    phi: np.ndarray,
    origin_m: tuple[float, float, float] | np.ndarray,
    spacing_m: float,
) -> SurfaceCanonicalization:
    """Apply the fixed geometry-preserving surface sequence.

    1. Merge numerically exact coincident vertex coordinates.
    2. Remove duplicate triangles, irrespective of input winding, keeping the
       earliest source triangle.
    3. Remove repeated-index and exactly zero-area triangles.
    4. In each edge-connected component, orient each resolvable face so its
       normal has positive dot product with the local trilinear ``grad(phi)``.

    Faces whose normal/gradient dot is within floating-point roundoff are left
    unchanged and reported as ambiguous. The caller must fail its gate if any
    ambiguous faces remain. Signed volume is never used to choose orientation.
    """

    source_vertices = np.asarray(vertices)
    raw_faces = np.asarray(faces)
    if not np.issubdtype(raw_faces.dtype, np.integer):
        raise ValueError("faces must contain integer vertex indices")
    source_faces = raw_faces.astype(np.int64, copy=False)
    if source_vertices.ndim != 2 or source_vertices.shape[1] != 3:
        raise ValueError("vertices must have shape (N, 3)")
    if source_faces.ndim != 2 or source_faces.shape[1] != 3:
        raise ValueError("faces must have shape (M, 3)")
    if (
        not np.issubdtype(source_vertices.dtype, np.number)
        or not np.isfinite(source_vertices).all()
    ):
        raise ValueError("vertices must be finite numeric coordinates")
    if len(source_faces) and (
        source_faces.min() < 0 or source_faces.max() >= len(source_vertices)
    ):
        raise ValueError("faces contain an out-of-range vertex index")

    unique_vertices, inverse = np.unique(source_vertices, axis=0, return_inverse=True)
    merged_faces = inverse[source_faces]

    face_keys = np.sort(merged_faces, axis=1)
    _, first_indices = np.unique(face_keys, axis=0, return_index=True)
    keep_unique = np.sort(first_indices)
    unique_faces = merged_faces[keep_unique]

    repeated = (
        (unique_faces[:, 0] == unique_faces[:, 1])
        | (unique_faces[:, 1] == unique_faces[:, 2])
        | (unique_faces[:, 2] == unique_faces[:, 0])
    )
    tri = unique_vertices[unique_faces].astype(np.float64, copy=False)
    twice_area = np.linalg.norm(
        np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
    )
    zero_area = twice_area == 0.0
    degenerate = repeated | zero_area
    kept_source_face_indices = keep_unique[~degenerate]
    clean_faces = unique_faces[~degenerate].copy()

    component_rows = []
    orientation_rows = []
    oriented_faces = clean_faces.copy()
    ambiguous_ids: list[int] = []
    flipped_ids: list[int] = []
    for component_id, component_faces in enumerate(_face_components(clean_faces)):
        component_flips: list[int] = []
        component_ambiguous: list[int] = []
        signs = {"positive": 0, "negative": 0, "ambiguous": 0}
        for face_id_raw in component_faces:
            face_id = int(face_id_raw)
            points = unique_vertices[clean_faces[face_id]].astype(
                np.float64, copy=False
            )
            cross = np.cross(points[1] - points[0], points[2] - points[0])
            cross_norm = float(np.linalg.norm(cross))
            normal = cross / cross_norm
            centroid = points.mean(axis=0)
            gradient, cell, corners = trilinear_gradient(
                phi, origin_m, spacing_m, centroid
            )
            dot_value = float(np.dot(normal, gradient))
            tolerance = (
                ORIENTATION_ROUNDOFF_FACTOR
                * np.finfo(np.float64).eps
                * max(1.0, float(np.linalg.norm(gradient)))
            )
            if dot_value > tolerance:
                signs["positive"] += 1
                flip = False
            elif dot_value < -tolerance:
                signs["negative"] += 1
                flip = True
            else:
                signs["ambiguous"] += 1
                component_ambiguous.append(face_id)
                ambiguous_ids.append(face_id)
                flip = False
            if flip:
                oriented_faces[face_id, [1, 2]] = oriented_faces[face_id, [2, 1]]
                component_flips.append(face_id)
                flipped_ids.append(face_id)
            orientation_rows.append(
                {
                    "face_id_after_dedup_and_degenerate_removal": face_id,
                    "source_triangle_id": int(kept_source_face_indices[face_id]),
                    "edge_component_id": component_id,
                    "triangle_normal_before_orientation": normal.tolist(),
                    "triangle_centroid_m": centroid.tolist(),
                    "sdf_gradient_at_centroid": gradient.tolist(),
                    "normal_gradient_dot_before_orientation": dot_value,
                    "dot_roundoff_tolerance": tolerance,
                    "cell_index_ijk": list(cell),
                    "cell_corner_phi_000_to_111": corners.ravel(order="C").tolist(),
                    "face_flipped": flip,
                    "orientation_ambiguous": not (
                        dot_value > tolerance or dot_value < -tolerance
                    ),
                }
            )
        component_rows.append(
            {
                "component_id": component_id,
                "face_count": int(len(component_faces)),
                "orientation_dot_sign_counts_before": signs,
                "flipped_face_count": len(component_flips),
                "ambiguous_face_count": len(component_ambiguous),
                "flipped_face_ids": component_flips,
                "ambiguous_face_ids": component_ambiguous,
            }
        )

    audit: dict[str, object] = {
        "source_vertex_instance_count": int(len(source_vertices)),
        "exact_unique_vertex_count": int(len(unique_vertices)),
        "exact_coincident_vertex_instances_merged": int(
            len(source_vertices) - len(unique_vertices)
        ),
        "source_triangle_count": int(len(source_faces)),
        "duplicate_triangle_count_removed": int(len(merged_faces) - len(unique_faces)),
        "repeated_index_triangle_count_removed": int(np.count_nonzero(repeated)),
        "exact_zero_area_triangle_count_removed": int(
            np.count_nonzero(zero_area & ~repeated)
        ),
        "degenerate_triangle_count_removed": int(np.count_nonzero(degenerate)),
        "kept_source_triangle_ids": kept_source_face_indices.tolist(),
        "oriented_face_count": int(len(oriented_faces)),
        "flipped_face_ids_after_cleanup": flipped_ids,
        "ambiguous_face_ids_after_cleanup": ambiguous_ids,
        "orientation_component_count": len(component_rows),
        "orientation_components": component_rows,
        "orientation_roundoff_factor": ORIENTATION_ROUNDOFF_FACTOR,
        "orientation_roundoff_dtype": "float64",
        "orientation_rows": orientation_rows,
    }
    return SurfaceCanonicalization(unique_vertices, oriented_faces, audit)


__all__ = [
    "ORIENTATION_ROUNDOFF_FACTOR",
    "SurfaceCanonicalization",
    "canonicalize_triangle_surface",
    "trilinear_gradient",
]
