"""Experimental #45 zero-surface candidates for synthetic qualification only.

The three extractors are kept together so their tie rules, coordinate order,
and component-level orientation contract are explicit.  This module does not
read registered target snapshots or change the production exporter.
"""

from __future__ import annotations

from itertools import permutations
import numpy as np

H_M = 0.025
ORIENTATION_DELTA_OVER_H = (0.02, 0.05, 0.1)
ORIENTATION_TOLERANCE = 64.0 * np.finfo(np.float64).eps * H_M
ZERO_TIE_TAU_M = H_M * 2.0**-20
_TETRA_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
_PERMUTATIONS = tuple(permutations(range(3)))

CANDIDATES = {
    "A": {
        "algorithm": "PyVista/VTK ImageData.contour at iso 0; exact cleanup; component-sidedness orientation",
        "field_tie": "native VTK handling of exact zero",
        "post_extraction_vertex_movement": False,
        "orientation": "whole edge-connected component only",
    },
    "B": {
        "algorithm": "scikit-image 0.25.2 Lewiner marching cubes",
        "method": "lewiner",
        "level": 0.0,
        "step_size": 1,
        "gradient_direction": "ascent",
        "allow_degenerate": False,
        "field_axis_order": "input xyz order; no transpose",
        "field_tie": "exact zeros replaced in extraction scratch with +tau",
        "post_extraction_vertex_movement": False,
        "orientation": "whole edge-connected component only",
    },
    "C": {
        "algorithm": "deterministic Kuhn-6 marching tetrahedra",
        "cube_split": "six axis permutations along 000-to-111 body diagonal",
        "field_tie": "exact zeros replaced in extraction scratch with +tau",
        "edge_identity": "sorted pair of global C-order grid node ids",
        "interpolation": "float64 t=fa/(fa-fb)",
        "post_extraction_vertex_movement": False,
        "orientation": "affine tetra gradient for native triangles, then whole component only",
    },
}


def _validate_grid(
    phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, float]:
    field = np.asarray(phi)
    origin = np.asarray(origin, dtype=np.float64)
    h = float(h)
    if (
        field.ndim != 3
        or min(field.shape) < 2
        or not np.issubdtype(field.dtype, np.number)
    ):
        raise ValueError(
            "phi must be a numeric 3D array with at least two nodes per axis"
        )
    if not np.isfinite(field).all():
        raise ValueError("phi must contain only finite values")
    if (
        origin.shape != (3,)
        or not np.isfinite(origin).all()
        or not np.isfinite(h)
        or h <= 0
    ):
        raise ValueError("origin must be finite xyz and h must be positive and finite")
    return field, origin, h


def sample_phi(
    phi: np.ndarray, origin: np.ndarray, h: float, points: np.ndarray
) -> np.ndarray:
    """Vectorized trilinear interpolation in the input array's xyz axis order."""
    field, origin, h = _validate_grid(phi, origin, h)
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("points must be a finite (N, 3) array")
    q = (points - origin) / h
    upper = np.asarray(field.shape, dtype=np.int64) - 1
    if np.any(q < 0.0) or np.any(q > upper):
        raise ValueError("sample points must lie inside the grid bounds")
    cell = np.minimum(np.floor(q).astype(np.int64), upper - 1)
    t = q - cell
    result = np.zeros(len(points), dtype=np.float64)
    for i in (0, 1):
        wi = t[:, 0] if i else 1.0 - t[:, 0]
        for j in (0, 1):
            wj = t[:, 1] if j else 1.0 - t[:, 1]
            for k in (0, 1):
                wk = t[:, 2] if k else 1.0 - t[:, 2]
                result += (
                    wi * wj * wk * field[cell[:, 0] + i, cell[:, 1] + j, cell[:, 2] + k]
                )
    return result


def sample_phi_gradient(
    phi: np.ndarray, origin: np.ndarray, h: float, points: np.ndarray
) -> np.ndarray:
    """Vectorized analytic gradient of the cell-local trilinear interpolant."""
    field, origin, h = _validate_grid(phi, origin, h)
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("points must be a finite (N, 3) array")
    q = (points - origin) / h
    upper = np.asarray(field.shape, dtype=np.int64) - 1
    if np.any(q < 0.0) or np.any(q > upper):
        raise ValueError("sample points must lie inside the grid bounds")
    cell = np.minimum(np.floor(q).astype(np.int64), upper - 1)
    t = q - cell
    gradient = np.zeros((len(points), 3), dtype=np.float64)
    for j in (0, 1):
        wj = t[:, 1] if j else 1.0 - t[:, 1]
        for k in (0, 1):
            wk = t[:, 2] if k else 1.0 - t[:, 2]
            a = field[cell[:, 0], cell[:, 1] + j, cell[:, 2] + k]
            b = field[cell[:, 0] + 1, cell[:, 1] + j, cell[:, 2] + k]
            gradient[:, 0] += (b - a) * wj * wk / h
    for i in (0, 1):
        wi = t[:, 0] if i else 1.0 - t[:, 0]
        for k in (0, 1):
            wk = t[:, 2] if k else 1.0 - t[:, 2]
            a = field[cell[:, 0] + i, cell[:, 1], cell[:, 2] + k]
            b = field[cell[:, 0] + i, cell[:, 1] + 1, cell[:, 2] + k]
            gradient[:, 1] += (b - a) * wi * wk / h
    for i in (0, 1):
        wi = t[:, 0] if i else 1.0 - t[:, 0]
        for j in (0, 1):
            wj = t[:, 1] if j else 1.0 - t[:, 1]
            a = field[cell[:, 0] + i, cell[:, 1] + j, cell[:, 2]]
            b = field[cell[:, 0] + i, cell[:, 1] + j, cell[:, 2] + 1]
            gradient[:, 2] += (b - a) * wi * wj / h
    return gradient


def face_components(faces: np.ndarray) -> list[np.ndarray]:
    """Return edge-connected triangle components, stable by first face index."""
    faces = np.asarray(faces)
    if (
        faces.ndim != 2
        or faces.shape[1] != 3
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError("faces must be an integer (M, 3) array")
    n = len(faces)
    parent = np.arange(n, dtype=np.int64)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = int(parent[x])
        return x

    edges: dict[tuple[int, int], int] = {}
    for fi, (a, b, c) in enumerate(faces):
        for u, v in ((a, b), (b, c), (c, a)):
            edge = (int(min(u, v)), int(max(u, v)))
            prior = edges.setdefault(edge, fi)
            left, right = find(prior), find(fi)
            if left != right:
                parent[max(left, right)] = min(left, right)
    groups: dict[int, list[int]] = {}
    for fi in range(n):
        groups.setdefault(find(fi), []).append(fi)
    return [
        np.asarray(ids, dtype=np.int64)
        for ids in sorted(groups.values(), key=lambda x: x[0])
    ]


def _triangle_geometry(
    vertices: np.ndarray, faces: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    tri = vertices[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    twice_area = np.linalg.norm(cross, axis=1)
    normals = np.divide(
        cross,
        twice_area[:, None],
        out=np.zeros_like(cross),
        where=twice_area[:, None] > 0,
    )
    return tri.mean(axis=1), normals


def _signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    if not len(faces):
        return 0.0
    tri = vertices[faces]
    return float(
        np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0
    )


def orient_components(
    vertices: np.ndarray,
    faces: np.ndarray,
    phi: np.ndarray,
    origin: np.ndarray,
    h: float,
) -> tuple[np.ndarray, dict]:
    """Flip whole connected components only, using stable three-offset area votes."""
    field, origin, h = _validate_grid(phi, origin, h)
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("vertices must be finite (N, 3)")
    if (
        faces.ndim != 2
        or faces.shape[1] != 3
        or (len(faces) and (faces.min() < 0 or faces.max() >= len(vertices)))
    ):
        raise ValueError("faces must be a valid (M, 3) index array")
    result = faces.copy()
    centroids, normals = _triangle_geometry(vertices, faces)
    twice_area = np.linalg.norm(
        np.cross(
            vertices[faces[:, 1]] - vertices[faces[:, 0]],
            vertices[faces[:, 2]] - vertices[faces[:, 0]],
        ),
        axis=1,
    )
    areas = 0.5 * twice_area
    components = []
    for component_id, ids in enumerate(face_components(faces)):
        positive_area = areas[ids] > 0.0
        total_area = float(areas[ids][positive_area].sum())
        delta_rows = []
        delta_votes = []
        for ratio in ORIENTATION_DELTA_OVER_H:
            delta = ratio * h
            plus = sample_phi(field, origin, h, centroids[ids] + delta * normals[ids])
            minus = sample_phi(field, origin, h, centroids[ids] - delta * normals[ids])
            outward = (
                positive_area
                & (plus > ORIENTATION_TOLERANCE)
                & (minus < -ORIENTATION_TOLERANCE)
            )
            inward = (
                positive_area
                & (plus < -ORIENTATION_TOLERANCE)
                & (minus > ORIENTATION_TOLERANCE)
            )
            out_area = float(areas[ids][outward].sum())
            in_area = float(areas[ids][inward].sum())
            out_fraction = out_area / total_area if total_area else 0.0
            in_fraction = in_area / total_area if total_area else 0.0
            vote = (
                "outward"
                if out_fraction > 0.5
                else "inward"
                if in_fraction > 0.5
                else "ambiguous"
            )
            delta_votes.append(vote)
            delta_rows.append(
                {
                    "delta_over_h": ratio,
                    "delta_m": delta,
                    "outward_area_fraction": out_fraction,
                    "inward_area_fraction": in_fraction,
                    "unresolved_area_fraction": max(
                        0.0, 1.0 - out_fraction - in_fraction
                    ),
                    "outward_phi_plus_min_max": [float(plus.min()), float(plus.max())]
                    if len(plus)
                    else [0.0, 0.0],
                    "outward_phi_minus_min_max": [
                        float(minus.min()),
                        float(minus.max()),
                    ]
                    if len(minus)
                    else [0.0, 0.0],
                    "positive_area_m2": total_area,
                    "outward_classified_area_m2": out_area,
                    "inward_classified_area_m2": in_area,
                }
            )
        stable = (
            delta_votes[0]
            if len(set(delta_votes)) == 1 and delta_votes[0] != "ambiguous"
            else "ambiguous"
        )
        raw_volume = _signed_volume(vertices, faces[ids])
        flipped = stable == "inward"
        if flipped:
            result[np.ix_(ids, [1, 2])] = result[np.ix_(ids, [2, 1])]
        oriented_volume = -raw_volume if flipped else raw_volume
        components.append(
            {
                "component_id": component_id,
                "face_count": int(len(ids)),
                "positive_area_m2": total_area,
                "delta_votes": delta_votes,
                "stable_sidedness": stable,
                "orientation_contract_pass": stable != "ambiguous",
                "whole_component_flipped": flipped,
                "raw_signed_volume_m3": raw_volume,
                "oriented_signed_volume_m3": oriented_volume,
                "volume_class": "solid_boundary"
                if oriented_volume > 0
                else "void_boundary"
                if oriented_volume < 0
                else "ambiguous",
                "delta_audit": delta_rows,
            }
        )
    return result, {
        "orientation_rule": "area majority > 50% at each delta; same non-ambiguous sign at every delta; whole component flips only",
        "delta_over_h": list(ORIENTATION_DELTA_OVER_H),
        "roundoff_tolerance_m": ORIENTATION_TOLERANCE,
        "normal_gradient_auxiliary_only": True,
        "component_count": len(components),
        "components": components,
        "all_components_orientable_by_contract": all(
            row["orientation_contract_pass"] for row in components
        ),
    }


def _clean_a(
    vertices: np.ndarray, faces: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict]:
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    merged = inverse[faces]
    _, first = np.unique(np.sort(merged, axis=1), axis=0, return_index=True)
    first.sort()
    dedup = merged[first]
    tri = unique[dedup]
    repeated = (
        (dedup[:, 0] == dedup[:, 1])
        | (dedup[:, 1] == dedup[:, 2])
        | (dedup[:, 2] == dedup[:, 0])
    )
    zero_area = (
        np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        == 0.0
    )
    bad = repeated | zero_area
    return (
        unique,
        dedup[~bad].copy(),
        {
            "exact_coincident_vertex_instances_merged": int(
                len(vertices) - len(unique)
            ),
            "duplicate_faces_removed": int(len(merged) - len(dedup)),
            "repeated_index_faces_removed": int(np.count_nonzero(repeated)),
            "exact_zero_area_nonrepeated_faces_removed": int(
                np.count_nonzero(zero_area & ~repeated)
            ),
        },
    )


def _extract_a(
    phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, dict]:
    import pyvista as pv

    field = np.asarray(phi)
    grid = pv.ImageData(dimensions=field.shape, origin=tuple(origin), spacing=(h, h, h))
    grid.point_data["phi"] = np.ascontiguousarray(field.ravel(order="F"))
    surface = grid.contour(isosurfaces=[0.0], scalars="phi")
    vertices = np.asarray(surface.points, dtype=np.float64)
    packed = np.asarray(surface.faces, dtype=np.int64)
    if len(packed) % 4 or (len(packed) and np.any(packed[::4] != 3)):
        raise RuntimeError("VTK contour returned non-triangle faces")
    faces = packed.reshape(-1, 4)[:, 1:]
    vertices, faces, cleanup = _clean_a(vertices, faces)
    return vertices, faces, {"native_point_count": int(len(surface.points)), **cleanup}


def _extract_b(
    phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, dict]:
    import skimage

    if skimage.__version__ != "0.25.2":
        raise RuntimeError("round2 requires pinned scikit-image 0.25.2")
    from skimage.measure import marching_cubes

    field = np.array(phi, dtype=np.float64, copy=True)
    zero_count = int(np.count_nonzero(field == 0))
    field[field == 0] = np.float32(ZERO_TIE_TAU_M)
    vertices, faces, normals, values = marching_cubes(
        field,
        level=0.0,
        spacing=(h, h, h),
        method="lewiner",
        step_size=1,
        gradient_direction="ascent",
        allow_degenerate=False,
    )
    vertices = np.asarray(vertices, dtype=np.float64) + origin
    return (
        vertices,
        np.asarray(faces, dtype=np.int64),
        {
            "skimage_version": __import__("skimage").__version__,
            "method": "lewiner",
            "level": 0.0,
            "step_size": 1,
            "gradient_direction": "ascent",
            "allow_degenerate": False,
            "input_axis_order": "xyz",
            "zero_tie_sign": "positive-fluid",
            "zero_tie_tau_m": ZERO_TIE_TAU_M,
            "exact_zero_node_count": zero_count,
            "scratch_field_dtype": "float64 before scikit-image internal conversion",
            "canonical_phi_mutated": False,
            "returned_normal_count": int(len(normals)),
            "returned_value_count": int(len(values)),
        },
    )


def _node_id(index: tuple[int, int, int], shape: tuple[int, int, int]) -> int:
    return int(np.ravel_multi_index(index, shape, order="C"))


def _extract_c(
    phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, dict]:
    field = np.array(phi, dtype=np.float64, copy=True)
    zero_count = int(np.count_nonzero(field == 0))
    field[field == 0] = np.float32(ZERO_TIE_TAU_M)
    shape = tuple(int(x) for x in field.shape)
    vertices: list[np.ndarray] = []
    edge_keys: list[tuple[int, int]] = []
    edge_to_vertex: dict[tuple[int, int], int] = {}
    faces: list[tuple[int, int, int]] = []
    provenance: list[dict] = []
    cube_corners = [
        field[
            i : field.shape[0] - 1 + i,
            j : field.shape[1] - 1 + j,
            k : field.shape[2] - 1 + k,
        ]
        for i in (0, 1)
        for j in (0, 1)
        for k in (0, 1)
    ]
    negative_count = np.sum(np.stack([corner < 0.0 for corner in cube_corners]), axis=0)
    active = np.argwhere((negative_count > 0) & (negative_count < 8))
    for cell_raw in active:
        cell = tuple(int(x) for x in cell_raw)
        for perm_id, perm in enumerate(_PERMUTATIONS):
            bits = [(0, 0, 0)]
            cur = [0, 0, 0]
            for axis in perm:
                cur = cur.copy()
                cur[axis] = 1
                bits.append(tuple(cur))
            gids = [
                _node_id(tuple(cell[d] + b[d] for d in range(3)), shape) for b in bits
            ]
            vals = np.asarray(
                [field[tuple(cell[d] + b[d] for d in range(3))] for b in bits],
                dtype=np.float64,
            )
            signs = vals < 0.0
            if np.all(signs) or not np.any(signs):
                continue
            local_edges = []
            for ea, eb in _TETRA_EDGES:
                if signs[ea] == signs[eb]:
                    continue
                pair = tuple(sorted((gids[ea], gids[eb])))
                local_edges.append((pair, ea, eb))
            local_edges.sort(key=lambda row: row[0])
            points_by_key = {}
            for key, ea, eb in local_edges:
                if key not in edge_to_vertex:
                    fa, fb = vals[ea], vals[eb]
                    t = float(fa / (fa - fb))
                    ia = tuple(cell[d] + bits[ea][d] for d in range(3))
                    ib = tuple(cell[d] + bits[eb][d] for d in range(3))
                    p = origin + h * (
                        np.asarray(ia, dtype=np.float64)
                        + t * (np.asarray(ib, dtype=np.float64) - ia)
                    )
                    edge_to_vertex[key] = len(vertices)
                    edge_keys.append(key)
                    vertices.append(p)
                points_by_key[key] = edge_to_vertex[key]
            polygon_ids = [points_by_key[row[0]] for row in local_edges]
            coords = np.asarray([vertices[idx] for idx in polygon_ids])
            tetra_points = (
                np.asarray([np.asarray(cell) + b for b in bits], dtype=np.float64) * h
                + origin
            )
            matrix = tetra_points[1:] - tetra_points[0]
            grad = np.linalg.solve(matrix, vals[1:] - vals[0])
            if len(polygon_ids) == 4:
                center = coords.mean(axis=0)
                normal = grad / np.linalg.norm(grad)
                u = coords[0] - center
                u /= np.linalg.norm(u)
                v = np.cross(normal, u)
                order = sorted(
                    range(4),
                    key=lambda i: (
                        float(
                            np.arctan2(
                                np.dot(coords[i] - center, v),
                                np.dot(coords[i] - center, u),
                            )
                        ),
                        edge_keys[polygon_ids[i]],
                    ),
                )
                polygon_ids = [polygon_ids[i] for i in order]
                diag_a = tuple(
                    sorted((edge_keys[polygon_ids[0]], edge_keys[polygon_ids[2]]))
                )
                diag_b = tuple(
                    sorted((edge_keys[polygon_ids[1]], edge_keys[polygon_ids[3]]))
                )
                local_tris = (
                    [
                        (polygon_ids[0], polygon_ids[1], polygon_ids[2]),
                        (polygon_ids[0], polygon_ids[2], polygon_ids[3]),
                    ]
                    if diag_a <= diag_b
                    else [
                        (polygon_ids[1], polygon_ids[2], polygon_ids[3]),
                        (polygon_ids[1], polygon_ids[3], polygon_ids[0]),
                    ]
                )
            else:
                local_tris = [tuple(polygon_ids)]
            for tri_ids in local_tris:
                p = np.asarray([vertices[idx] for idx in tri_ids])
                if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), grad) < 0:
                    tri_ids = (tri_ids[0], tri_ids[2], tri_ids[1])
                faces.append(tuple(int(x) for x in tri_ids))
                provenance.append(
                    {
                        "cell_ijk": list(cell),
                        "tetra_permutation": list(perm),
                        "tetra_permutation_id": perm_id,
                    }
                )
    return (
        np.asarray(vertices, dtype=np.float64).reshape(-1, 3),
        np.asarray(faces, dtype=np.int64).reshape(-1, 3),
        {
            "zero_tie_sign": "positive-fluid",
            "zero_tie_tau_m": ZERO_TIE_TAU_M,
            "exact_zero_node_count": zero_count,
            "scratch_field_dtype": "float64",
            "active_cell_count": int(len(active)),
            "tetrahedra_examined": int(6 * len(active)),
            "vertex_source_edge_keys_global_c_order": [list(key) for key in edge_keys],
            "face_tetra_provenance": provenance,
        },
    )


def extract_candidate(
    name: str, phi: np.ndarray, origin: np.ndarray, h: float
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Extract A/B/C and return world-space vertices, triangle faces, and audit."""
    field, origin, h = _validate_grid(phi, origin, h)
    if name not in CANDIDATES:
        raise ValueError("candidate name must be one of 'A', 'B', or 'C'")
    original_hash = hash(field.tobytes())
    if name == "A":
        vertices, faces, extraction = _extract_a(field, origin, h)
    elif name == "B":
        vertices, faces, extraction = _extract_b(field, origin, h)
    else:
        vertices, faces, extraction = _extract_c(field, origin, h)
    oriented, orientation = orient_components(vertices, faces, field, origin, h)
    audit = {
        "candidate": name,
        "candidate_parameters": CANDIDATES[name],
        "grid_shape_xyz": list(field.shape),
        "origin_m": origin.tolist(),
        "h_m": h,
        "extractor": extraction,
        "orientation": orientation,
        "component_signed_volumes_m3": [
            {
                k: row[k]
                for k in (
                    "component_id",
                    "raw_signed_volume_m3",
                    "oriented_signed_volume_m3",
                    "volume_class",
                )
            }
            for row in orientation["components"]
        ],
        "canonical_phi_mutated": False,
        "source_field_unchanged": hash(field.tobytes()) == original_hash,
    }
    return vertices, oriented, audit


__all__ = [
    "CANDIDATES",
    "H_M",
    "ORIENTATION_DELTA_OVER_H",
    "extract_candidate",
    "face_components",
    "orient_components",
    "sample_phi",
    "sample_phi_gradient",
]
