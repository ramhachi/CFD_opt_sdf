"""Deterministic Round3 zero-level extraction and read-only surface audits."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.csgraph import connected_components

from xfid45_surface_round2_candidates import sample_phi

_FLOW_BOX = (np.array((-2.5, -1.2, -0.9)), np.array((2.5, 1.2, 0.9)))
_DELTAS = (0.02, 0.05, 0.1)


def _grid(phi, origin, h):
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
    if (
        not np.isfinite(field).all()
        or origin.shape != (3,)
        or not np.isfinite(origin).all()
        or not np.isfinite(h)
        or h <= 0
    ):
        raise ValueError(
            "phi, origin, and spacing must be finite; spacing must be positive"
        )
    return field, origin, h


def _array_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).view(np.uint8)).hexdigest()


def _refine(field, r):
    shape = (np.asarray(field.shape, dtype=np.int64) - 1) * r + 1
    refined = ndimage.zoom(
        field,
        zoom=shape / np.asarray(field.shape, dtype=np.float64),
        order=1,
        mode="nearest",
        prefilter=False,
        grid_mode=False,
    )
    if refined.shape != tuple(shape):
        raise RuntimeError(
            f"refined grid shape mismatch: {refined.shape} != {tuple(shape)}"
        )
    return refined


def _float32_cast_stats(field, chunk_size=1_000_000):
    flat = field.reshape(-1)
    underflows = 0
    max_error = 0.0
    for start in range(0, flat.size, chunk_size):
        values = flat[start : start + chunk_size]
        cast = values.astype(np.float32)
        underflows += int(np.count_nonzero((values != 0.0) & (cast == 0.0)))
        max_error = max(
            max_error,
            float(np.max(np.abs(values - cast.astype(np.float64)), initial=0.0)),
        )
    return underflows, max_error


def extract(phi, origin, h, r):
    """Extract level zero after endpoint-preserving float64 trilinear refinement."""
    field, origin, h = _grid(phi, origin, h)
    if r not in (1, 2, 4, 8):
        raise ValueError("r must be one of 1, 2, 4, or 8")
    try:
        from skimage.measure import marching_cubes
    except ImportError as exc:
        raise RuntimeError(
            "scikit-image 0.25.2 is required for Round3 extraction"
        ) from exc
    version = importlib.metadata.version("scikit-image")
    if version != "0.25.2":
        raise RuntimeError(f"Round3 requires scikit-image 0.25.2, found {version}")

    source64 = np.asarray(field, dtype=np.float64)
    refined = _refine(source64, r)
    field_hash = _array_sha(field)
    virtual_hash = _array_sha(refined)
    zero_count = int(np.count_nonzero(refined == 0.0))
    tau = float(np.float32(h * 2.0**-20))
    scratch = refined.copy()
    scratch[scratch == 0.0] = tau
    float32_underflows, float32_max_error = _float32_cast_stats(scratch)
    vertices_ijk, faces, _, _ = marching_cubes(
        scratch,
        level=0.0,
        method="lewiner",
        step_size=1,
        gradient_direction="ascent",
        allow_degenerate=False,
    )
    vertices = origin + vertices_ijk.astype(np.float64, copy=False) * (h / r)
    audit = {
        "algorithm": "scikit-image 0.25.2 Lewiner marching cubes",
        "level": 0.0,
        "step_size": 1,
        "gradient_direction": "ascent",
        "allow_degenerate": False,
        "input_shape": list(field.shape),
        "refinement_factor": int(r),
        "refined_shape": list(refined.shape),
        "origin_m": origin.tolist(),
        "input_spacing_m": h,
        "refined_spacing_m": h / r,
        "source_phi_sha256": field_hash,
        "source_phi_sha256_after_extraction": _array_sha(field),
        "source_phi_unmodified": field_hash == _array_sha(field),
        "virtual_refined_grid_sha256_before_zero_tie": virtual_hash,
        "exact_zero_count_before_tie": zero_count,
        "scratch_exact_zeros_set_to_positive_tau_m": tau,
        "scratch_values_changed": zero_count,
        "scratch_hash_after_tie": _array_sha(scratch),
        "nonzero_to_float32_zero_count": float32_underflows,
        "maximum_float32_rounding_error": float32_max_error,
        "float32_cast_lineage_pass": float32_underflows == 0,
        "vertices": int(len(vertices)),
        "triangles": int(len(faces)),
        "post_extraction_vertex_movement": False,
    }
    return vertices, faces.astype(np.int64, copy=False), audit


def _validate_surface(vertices, faces):
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("vertices must be a finite (N, 3) array")
    if (
        faces.ndim != 2
        or faces.shape[1] != 3
        or not np.issubdtype(faces.dtype, np.integer)
    ):
        raise ValueError("faces must be an integer (M, 3) array")
    faces = faces.astype(np.int64, copy=False)
    if len(faces) and (faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError("face index outside vertices")
    return vertices, faces


def _edge_components(faces):
    """Label exact-index edge-connected faces with minimum-face stable IDs."""
    m = len(faces)
    if not m:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    edges = np.sort(
        np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1
    )
    _, group, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(group, kind="stable")
    starts = np.r_[0, np.cumsum(counts[:-1])]
    group_starts = np.repeat(starts, counts)
    nonfirst = np.arange(len(order)) != group_starts
    positions = np.flatnonzero(nonfirst)
    incident_faces = np.tile(np.arange(m, dtype=np.int64), 3)[order]
    reps = incident_faces[group_starts[positions]]
    others = incident_faces[positions]
    graph = sparse.coo_matrix(
        (np.ones(2 * len(reps)), (np.r_[reps, others], np.r_[others, reps])),
        shape=(m, m),
    ).tocsr()
    count, labels = connected_components(graph, directed=False)
    first = np.full(count, m, dtype=np.int64)
    np.minimum.at(first, labels, np.arange(m))
    component_order = np.argsort(first)
    relabel = np.empty(count, dtype=np.int64)
    relabel[component_order] = np.arange(count)
    labels = relabel[labels]
    return labels, first[component_order]


def _link_audit(faces, vertex_count):
    if not len(faces):
        return 0, []
    # Each triangle contributes one link edge at each of its three vertices.
    center = faces.ravel()
    left = faces[:, [1, 2, 0]].ravel()
    right = faces[:, [2, 0, 1]].ravel()
    pairs, node_ids = np.unique(
        np.vstack((np.column_stack((center, left)), np.column_stack((center, right)))),
        axis=0,
        return_inverse=True,
    )
    link_nodes, right_link_nodes = np.split(node_ids, 2)
    # Repeated link edges retain multiplicity in the degree count.
    degree = np.bincount(np.r_[link_nodes, right_link_nodes], minlength=len(pairs))
    graph = sparse.coo_matrix(
        (
            np.ones(2 * len(center)),
            (np.r_[link_nodes, right_link_nodes], np.r_[right_link_nodes, link_nodes]),
        ),
        shape=(len(pairs), len(pairs)),
    ).tocsr()
    ncomp, labels = connected_components(graph, directed=False)
    component_keys = np.column_stack((pairs[:, 0], labels))
    component_counts = np.bincount(
        np.unique(component_keys, axis=0)[:, 0], minlength=vertex_count
    )
    incident_counts = np.bincount(pairs[:, 0], minlength=vertex_count)
    bad_vertices = np.flatnonzero((incident_counts > 0) & (component_counts != 1))
    bad_degree_vertices = np.unique(pairs[degree != 2, 0])
    bad_vertices = np.union1d(bad_vertices, bad_degree_vertices)
    return int(len(bad_vertices)), bad_vertices.tolist()


def topology(vertices, faces):
    """Audit exact-coordinate topology without dropping or altering any face."""
    vertices, faces = _validate_surface(vertices, faces)
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    f = inverse[faces]
    m = len(f)
    edges = (
        np.vstack((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
        if m
        else np.empty((0, 2), dtype=np.int64)
    )
    undirected = np.sort(edges, axis=1)
    edge_keys, edge_group, edge_counts = (
        np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
        if len(edges)
        else (np.empty((0, 2), int), np.empty(0, int), np.empty(0, int))
    )
    component_labels, component_first = _edge_components(f)
    component_count = len(component_first)
    areas = (
        np.linalg.norm(
            np.cross(
                unique[f[:, 1]] - unique[f[:, 0]], unique[f[:, 2]] - unique[f[:, 0]]
            ),
            axis=1,
        )
        * 0.5
        if m
        else np.empty(0)
    )
    repeated = (
        np.any(
            np.column_stack(
                (f[:, 0] == f[:, 1], f[:, 1] == f[:, 2], f[:, 2] == f[:, 0])
            ),
            axis=1,
        )
        if m
        else np.empty(0, bool)
    )
    sorted_faces = np.sort(f, axis=1) if m else np.empty((0, 3), int)
    duplicate_count = int(m - len(np.unique(sorted_faces, axis=0)))
    signs = (
        np.where(edges[:, 0] < edges[:, 1], 1, -1) if len(edges) else np.empty(0, int)
    )
    winding_sums = (
        np.bincount(edge_group, weights=signs, minlength=len(edge_counts))
        if len(edges)
        else np.empty(0)
    )
    watertight = bool(len(edge_counts) and np.all(edge_counts == 2))
    winding = bool(watertight and np.all(winding_sums == 0))
    bad_links, bad_link_vertices = _link_audit(f, len(unique))
    used = np.unique(f) if m else np.empty(0, int)
    euler = int(len(used) - len(edge_keys) + m)
    signed_volume = (
        float(
            np.einsum(
                "ij,ij->i", unique[f[:, 0]], np.cross(unique[f[:, 1]], unique[f[:, 2]])
            ).sum()
            / 6
        )
        if m
        else 0.0
    )
    bounds = (
        np.stack((unique.min(axis=0), unique.max(axis=0)))
        if len(unique)
        else np.zeros((2, 3))
    )
    clearance_axes = np.minimum(bounds[0] - _FLOW_BOX[0], _FLOW_BOX[1] - bounds[1])
    clearance = float(clearance_axes.min())
    valid = bool(
        watertight
        and winding
        and duplicate_count == 0
        and not repeated.any()
        and not np.any(areas == 0)
        and bad_links == 0
    )
    _, comp_sizes = (
        np.unique(component_labels, return_counts=True)
        if m
        else (np.empty(0), np.empty(0))
    )
    return {
        "original_vertex_count": int(len(vertices)),
        "exact_unique_vertex_count": int(len(unique)),
        "exact_coordinate_merge_count": int(len(vertices) - len(unique)),
        "triangle_count": int(m),
        "edge_connected_component_count": int(component_count),
        "component_min_original_face_id": component_first.astype(int).tolist(),
        "component_face_counts": comp_sizes.astype(int).tolist(),
        "euler_characteristic": euler,
        "watertight": watertight,
        "winding_consistent": winding,
        "edge_count": int(len(edge_keys)),
        "edge_incidence_not_two_count": int(np.count_nonzero(edge_counts != 2)),
        "boundary_edge_count": int(np.count_nonzero(edge_counts == 1)),
        "nonmanifold_edge_count": int(np.count_nonzero(edge_counts > 2)),
        "duplicate_face_count": duplicate_count,
        "repeated_index_face_count": int(repeated.sum()),
        "zero_area_face_count": int(np.count_nonzero(areas == 0)),
        "vertex_link_bad_count": bad_links,
        "vertex_link_bad_vertices": bad_link_vertices,
        "area_m2": float(areas.sum()),
        "signed_volume_m3": signed_volume,
        "bounds_m": bounds.tolist(),
        "stage_v_clearance_by_axis_m": clearance_axes.tolist(),
        "minimum_stage_v_clearance_m": clearance,
        "stage_v_clearance_pass": clearance >= 0.25,
        "topology_pass": valid,
    }


def orient(vertices, faces, phi, origin, h):
    """Flip entire edge-connected components using original-field sidedness votes."""
    field, origin, h = _grid(phi, origin, h)
    vertices, faces = _validate_surface(vertices, faces)
    audit_topology = topology(vertices, faces)
    result = faces.copy()
    if not audit_topology["topology_pass"]:
        return result, {
            "status": "N/A",
            "reason": "topology prerequisite failed",
            "topology": audit_topology,
            "components": [],
        }
    areas = (
        np.linalg.norm(
            np.cross(
                vertices[faces[:, 1]] - vertices[faces[:, 0]],
                vertices[faces[:, 2]] - vertices[faces[:, 0]],
            ),
            axis=1,
        )
        * 0.5
    )
    centroids = vertices[faces].mean(axis=1)
    normals = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]],
    )
    normals /= 2.0 * areas[:, None]
    tol = 64.0 * np.finfo(np.float64).eps * h
    rows = []
    all_orientable = True
    _, exact_inverse = np.unique(vertices, axis=0, return_inverse=True)
    component_labels, component_first = _edge_components(exact_inverse[faces])
    ordered_faces = np.argsort(component_labels, kind="stable")
    component_sizes = np.bincount(component_labels, minlength=len(component_first))
    component_starts = np.r_[0, np.cumsum(component_sizes)]
    for cid, ids in enumerate(np.split(ordered_faces, component_starts[1:-1])):
        votes = []
        delta_rows = []
        for ratio in _DELTAS:
            delta = ratio * h
            plus = sample_phi(field, origin, h, centroids[ids] + delta * normals[ids])
            minus = sample_phi(field, origin, h, centroids[ids] - delta * normals[ids])
            out = (plus > tol) & (minus < -tol)
            inward = (plus < -tol) & (minus > tol)
            out_fraction = float(areas[ids][out].sum() / areas[ids].sum())
            in_fraction = float(areas[ids][inward].sum() / areas[ids].sum())
            vote = (
                "outward"
                if out_fraction > 0.5
                else "inward"
                if in_fraction > 0.5
                else "ambiguous"
            )
            votes.append(vote)
            delta_rows.append(
                {
                    "delta_over_original_h": ratio,
                    "outward_area_fraction": out_fraction,
                    "inward_area_fraction": in_fraction,
                }
            )
        stable = (
            votes[0]
            if len(set(votes)) == 1 and votes[0] != "ambiguous"
            else "ambiguous"
        )
        flipped = stable == "inward"
        if flipped:
            result[ids] = result[ids][:, [0, 2, 1]]
        if stable == "ambiguous":
            all_orientable = False
        raw_volume = float(
            np.einsum(
                "ij,ij->i",
                vertices[faces[ids, 0]],
                np.cross(vertices[faces[ids, 1]], vertices[faces[ids, 2]]),
            ).sum()
            / 6.0
        )
        oriented_volume = -raw_volume if flipped else raw_volume
        rows.append(
            {
                "component_id": cid,
                "minimum_original_face_id": int(ids.min()),
                "face_count": int(len(ids)),
                "delta_votes": votes,
                "stable_sidedness": stable,
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
    global_volume = float(topology(vertices, result)["signed_volume_m3"])
    return result, {
        "status": "PASS" if all_orientable else "FAIL",
        "rule": "strict area majority >50% at all three deltas; same polarity required; phi<0 solid, phi>0 fluid",
        "deltas_over_original_h": list(_DELTAS),
        "roundoff_tolerance_m": tol,
        "topology": audit_topology,
        "components": rows,
        "all_components_orientable": all_orientable,
        "global_signed_volume_m3": global_volume,
        "global_positive_volume": global_volume > 0.0,
    }


def audit_json(value):
    """Return strict JSON text for an audit object (NaN/Inf are rejected)."""
    return json.dumps(value, sort_keys=True, allow_nan=False)
