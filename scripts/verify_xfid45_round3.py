"""Independent solver-free checks for Round3 surface candidates.

This module intentionally does not import the Round3 extractor or its geometry
helpers. It operates only on supplied arrays and performs no repair or mutation.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.interpolate import RegularGridInterpolator
from scipy.sparse.csgraph import connected_components

FLOW_LO = np.array((-2.5, -1.2, -0.9), dtype=np.float64)
FLOW_HI = np.array((2.5, 1.2, 0.9), dtype=np.float64)
DISTANCE_LIMIT_M = 5.0e-4
_BARY = (
    np.array(
        [(i, j, 3 - i - j) for i in range(4) for j in range(4 - i)],
        dtype=np.float64,
    )
    / 3.0
)


def _surface(vertices, faces):
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces)
    if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
        raise ValueError("vertices must be a finite (N,3) array")
    if f.ndim != 2 or f.shape[1] != 3 or not np.issubdtype(f.dtype, np.integer):
        raise ValueError("faces must be an integer (M,3) array")
    f = f.astype(np.int64, copy=False)
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError("face index outside vertices")
    return v, f


def _mesh_labels(face_ids, edge_group, edge_counts):
    """Sparse face graph, connecting all incidences of every exact edge."""
    m = int(face_ids.max() + 1) if face_ids.size else 0
    if not m:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    grouped = np.argsort(edge_group, kind="stable")
    first_positions = np.r_[0, np.cumsum(edge_counts[:-1])]
    offsets = np.repeat(first_positions, edge_counts)
    extra = np.flatnonzero(np.arange(len(grouped)) != offsets)
    incidences = face_ids[grouped]
    source = incidences[offsets[extra]]
    target = incidences[extra]
    graph = sparse.coo_matrix(
        (np.ones(2 * len(source)), (np.r_[source, target], np.r_[target, source])),
        shape=(m, m),
    ).tocsr()
    n, labels = connected_components(graph, directed=False)
    min_face = np.full(n, m, dtype=np.int64)
    np.minimum.at(min_face, labels, np.arange(m))
    order = np.argsort(min_face)
    remap = np.empty(n, dtype=np.int64)
    remap[order] = np.arange(n)
    return remap[labels], min_face[order]


def _vertex_links(faces, vertex_count):
    """Check each vertex link as a sparse cycle graph, retaining multiplicity."""
    if not len(faces):
        return 0, []
    centers = faces.ravel()
    adjacent = np.vstack(
        (
            np.column_stack((centers, faces[:, [1, 2, 0]].ravel())),
            np.column_stack((centers, faces[:, [2, 0, 1]].ravel())),
        )
    )
    nodes, inverse = np.unique(adjacent, axis=0, return_inverse=True)
    left, right = np.split(inverse, 2)
    degree = np.bincount(np.r_[left, right], minlength=len(nodes))
    graph = sparse.coo_matrix(
        (np.ones(2 * len(left)), (np.r_[left, right], np.r_[right, left])),
        shape=(len(nodes), len(nodes)),
    ).tocsr()
    _, label = connected_components(graph, directed=False)
    links_per_vertex = np.bincount(
        np.unique(np.column_stack((nodes[:, 0], label)), axis=0)[:, 0],
        minlength=vertex_count,
    )
    nodes_per_vertex = np.bincount(nodes[:, 0], minlength=vertex_count)
    bad = np.flatnonzero((nodes_per_vertex > 0) & (links_per_vertex != 1))
    bad = np.union1d(bad, np.unique(nodes[degree != 2, 0]))
    return int(len(bad)), bad.astype(int).tolist()


def topology(vertices, faces):
    """Return Round3 topology keys from exact-coordinate-only in-memory merge."""
    vertices, faces = _surface(vertices, faces)
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    f = inverse[faces]
    m = len(f)
    directed_edges = (
        np.vstack((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
        if m
        else np.empty((0, 2), dtype=np.int64)
    )
    undirected_edges = np.sort(directed_edges, axis=1)
    if len(directed_edges):
        edge_keys, edge_group, edge_counts = np.unique(
            undirected_edges, axis=0, return_inverse=True, return_counts=True
        )
    else:
        edge_keys = np.empty((0, 2), dtype=np.int64)
        edge_group = np.empty(0, dtype=np.int64)
        edge_counts = np.empty(0, dtype=np.int64)
    all_faces = np.tile(np.arange(m, dtype=np.int64), 3)
    labels, component_first = _mesh_labels(all_faces, edge_group, edge_counts)
    component_sizes = np.bincount(labels, minlength=len(component_first))
    if m:
        tri = unique[f]
        areas = 0.5 * np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
        )
        repeated = np.any(
            np.column_stack(
                (f[:, 0] == f[:, 1], f[:, 1] == f[:, 2], f[:, 2] == f[:, 0])
            ),
            axis=1,
        )
        face_keys = np.sort(f, axis=1)
        duplicate_count = int(m - len(np.unique(face_keys, axis=0)))
        edge_sign = np.where(directed_edges[:, 0] < directed_edges[:, 1], 1, -1)
        winding_sum = np.bincount(
            edge_group, weights=edge_sign, minlength=len(edge_counts)
        )
        volume = float(
            np.einsum(
                "ij,ij->i",
                tri[:, 0],
                np.cross(tri[:, 1], tri[:, 2]),
            ).sum()
            / 6.0
        )
    else:
        areas = np.empty(0)
        repeated = np.empty(0, dtype=bool)
        duplicate_count = 0
        winding_sum = np.empty(0)
        volume = 0.0
    watertight = bool(len(edge_counts) > 0 and np.all(edge_counts == 2))
    winding = bool(watertight and np.all(winding_sum == 0))
    bad_links, bad_link_vertices = _vertex_links(f, len(unique))
    used_vertices = np.unique(f) if m else np.empty(0, dtype=np.int64)
    euler = int(len(used_vertices) - len(edge_keys) + m)
    bounds = (
        np.stack((unique.min(axis=0), unique.max(axis=0)))
        if len(unique)
        else np.zeros((2, 3), dtype=np.float64)
    )
    clearance_axes = np.minimum(bounds[0] - FLOW_LO, FLOW_HI - bounds[1])
    clearance = float(clearance_axes.min())
    valid = bool(
        watertight
        and winding
        and duplicate_count == 0
        and not repeated.any()
        and not np.any(areas == 0.0)
        and bad_links == 0
    )
    return {
        "original_vertex_count": int(len(vertices)),
        "exact_unique_vertex_count": int(len(unique)),
        "exact_coordinate_merge_count": int(len(vertices) - len(unique)),
        "triangle_count": int(m),
        "edge_connected_component_count": int(len(component_first)),
        "component_min_original_face_id": component_first.astype(int).tolist(),
        "component_face_counts": component_sizes.astype(int).tolist(),
        "euler_characteristic": euler,
        "watertight": watertight,
        "winding_consistent": winding,
        "edge_count": int(len(edge_keys)),
        "edge_incidence_not_two_count": int(np.count_nonzero(edge_counts != 2)),
        "boundary_edge_count": int(np.count_nonzero(edge_counts == 1)),
        "nonmanifold_edge_count": int(np.count_nonzero(edge_counts > 2)),
        "duplicate_face_count": duplicate_count,
        "repeated_index_face_count": int(repeated.sum()),
        "zero_area_face_count": int(np.count_nonzero(areas == 0.0)),
        "vertex_link_bad_count": bad_links,
        "vertex_link_bad_vertices": bad_link_vertices,
        "area_m2": float(areas.sum()),
        "signed_volume_m3": volume,
        "bounds_m": bounds.tolist(),
        "stage_v_clearance_by_axis_m": clearance_axes.tolist(),
        "minimum_stage_v_clearance_m": clearance,
        "stage_v_clearance_pass": clearance >= 0.25,
        "topology_pass": valid,
    }


def _field(phi, origin, h):
    phi = np.asarray(phi, dtype=np.float64)
    origin = np.asarray(origin, dtype=np.float64)
    h = float(h)
    if phi.ndim != 3 or min(phi.shape) < 2 or not np.isfinite(phi).all():
        raise ValueError(
            "phi must be a finite 3D field with at least two nodes per axis"
        )
    if (
        origin.shape != (3,)
        or not np.isfinite(origin).all()
        or not np.isfinite(h)
        or h <= 0
    ):
        raise ValueError("origin must be finite xyz and h positive finite")
    grid = _grid_axes(phi.shape, origin, h)
    interp = RegularGridInterpolator(grid, phi, method="linear", bounds_error=True)
    return phi, origin, h, interp


def _grid_axes(shape, origin, h):
    return tuple(origin[a] + h * np.arange(shape[a]) for a in range(3))


def _phi_error(phi, origin, h, points):
    """Original trilinear values and a local weighted-corner roundoff bound."""
    points = np.asarray(points, dtype=np.float64)
    upper = np.asarray(phi.shape, dtype=np.int64) - 1
    axes = _grid_axes(phi.shape, origin, h)
    cell = np.column_stack(
        [
            np.clip(
                np.searchsorted(axes[a], points[:, a], side="right") - 1,
                0,
                upper[a] - 1,
            )
            for a in range(3)
        ]
    )
    t = np.column_stack(
        [
            (points[:, a] - axes[a][cell[:, a]])
            / (axes[a][cell[:, a] + 1] - axes[a][cell[:, a]])
            for a in range(3)
        ]
    )
    value = np.zeros(len(points), dtype=np.float64)
    absolute_sum = np.zeros(len(points), dtype=np.float64)
    for a in (0, 1):
        wa = t[:, 0] if a else 1.0 - t[:, 0]
        for b in (0, 1):
            wb = t[:, 1] if b else 1.0 - t[:, 1]
            for c in (0, 1):
                wc = t[:, 2] if c else 1.0 - t[:, 2]
                weight = wa * wb * wc
                corner = phi[cell[:, 0] + a, cell[:, 1] + b, cell[:, 2] + c]
                value += weight * corner
                absolute_sum += np.abs(weight * corner)
    error = 64.0 * np.finfo(np.float64).eps * absolute_sum
    return value, error


def _interpolator_lipschitz(phi, origin, h):
    axes = _grid_axes(phi.shape, origin, h)
    slopes = [
        float(
            np.max(np.abs(np.diff(phi, axis=axis)), initial=0.0)
            / np.diff(axes[axis]).min()
        )
        for axis in range(3)
    ]
    return float(np.linalg.norm(slopes)) * (1.0 + 64.0 * np.finfo(np.float64).eps)


def _axis_root_witness(points, phi, origin, h, interp, reference=None, chunk=6000):
    """Certified local axis roots, split at every intervening source grid plane."""
    n = len(points)
    reference = points if reference is None else np.asarray(reference, dtype=np.float64)
    best = np.full(n, np.inf, dtype=np.float64)
    diagnostic_residual = np.full(n, np.inf, dtype=np.float64)
    axes = _grid_axes(phi.shape, origin, h)
    grid_lo = np.array([axis[0] for axis in axes])
    grid_hi = np.array([axis[-1] for axis in axes])
    for axis in range(3):
        for start in range(0, n, chunk):
            p = points[start : start + chunk]
            ref = reference[start : start + chunk]
            count = len(p)
            q = p[:, axis]
            lo = np.maximum(q - h, grid_lo[axis])
            hi = np.minimum(q + h, grid_hi[axis])
            k = np.searchsorted(axes[axis], q, side="right") - 1
            # Four plane slots cover every source plane in a 2h interval.
            slots = k[:, None] + np.arange(-1, 3, dtype=np.int64)[None, :]
            planes = axes[axis][np.clip(slots, 0, len(axes[axis]) - 1)]
            planes = np.where(
                (planes > lo[:, None]) & (planes < hi[:, None]), planes, q[:, None]
            )
            coords = np.column_stack((lo, planes, q, hi))
            coords.sort(axis=1)
            probes = np.broadcast_to(p[:, None, :], (count, coords.shape[1], 3)).copy()
            probes[:, :, axis] = coords
            value, err = _phi_error(phi, origin, h, probes.reshape(-1, 3))
            value = value.reshape(count, coords.shape[1])
            err = err.reshape(count, coords.shape[1])
            structural = (value == 0.0) & (err == 0.0)
            structural_points = np.broadcast_to(
                p[:, None, :], (count, coords.shape[1], 3)
            ).copy()
            structural_points[:, :, axis] = coords
            guarded = (
                np.linalg.norm(structural_points - ref[:, None, :], axis=2) + h * 1e-9
            )
            guarded[~structural] = np.inf
            best[start : start + count] = np.minimum(
                best[start : start + count], guarded.min(axis=1)
            )
            diagnostic_residual[start : start + count] = np.where(
                structural.any(axis=1), 0.0, diagnostic_residual[start : start + count]
            )
            a, b = value[:, :-1], value[:, 1:]
            ea, eb = err[:, :-1], err[:, 1:]
            reliable_pos_neg = (a - ea > 0.0) & (b + eb < 0.0)
            reliable_neg_pos = (a + ea < 0.0) & (b - eb > 0.0)
            bracket = reliable_pos_neg | reliable_neg_pos
            if not bracket.any():
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                ratios = np.stack(
                    (
                        (a - ea) / ((a - ea) - (b - eb)),
                        (a - ea) / ((a - ea) - (b + eb)),
                        (a + ea) / ((a + ea) - (b - eb)),
                        (a + ea) / ((a + ea) - (b + eb)),
                    ),
                    axis=-1,
                )
            ratios = np.clip(ratios, 0.0, 1.0)
            tlo, thi = ratios.min(axis=-1), ratios.max(axis=-1)
            dist = coords[:, 1:] - coords[:, :-1]
            rootlo = coords[:, :-1] + dist * tlo
            roothi = coords[:, :-1] + dist * thi
            rootlo_points = np.broadcast_to(
                p[:, None, :], (count, dist.shape[1], 3)
            ).copy()
            roothi_points = rootlo_points.copy()
            rootlo_points[:, :, axis] = rootlo
            roothi_points[:, :, axis] = roothi
            candidate = (
                np.maximum(
                    np.linalg.norm(rootlo_points - ref[:, None, :], axis=2),
                    np.linalg.norm(roothi_points - ref[:, None, :], axis=2),
                )
                + h * 1e-9
            )
            candidate[~bracket] = np.inf
            # Computed midpoint residual and axis slope are retained as diagnostics only.
            tm = 0.5 * (tlo + thi)
            rootmid = coords[:, :-1] + dist * tm
            rootmid = np.where(bracket, rootmid, coords[:, :-1])
            root_points = np.broadcast_to(
                p[:, None, :], (count, dist.shape[1], 3)
            ).copy()
            root_points[:, :, axis] = rootmid
            root_value = interp(root_points.reshape(-1, 3)).reshape(
                count, dist.shape[1]
            )
            residual = np.abs(root_value)
            residual[~bracket] = np.inf
            diagnostic_residual[start : start + count] = np.minimum(
                diagnostic_residual[start : start + count], residual.min(axis=1)
            )
            best[start : start + count] = np.minimum(
                best[start : start + count], candidate.min(axis=1)
            )
    return best, diagnostic_residual


def distance(vertices, faces, phi, origin, h):
    """Certify sampled surface distance bounds to the original trilinear zero set."""
    vertices, faces = _surface(vertices, faces)
    field, origin, h, interp = _field(phi, origin, h)
    lip = _interpolator_lipschitz(field, origin, h)
    per_face = np.zeros((len(faces), 3), dtype=np.float64)
    sample_count = 0
    max_root_residual = 0.0
    for face_start in range(0, len(faces), 5000):  # 50,000 fixed barycentric samples.
        f = faces[face_start : face_start + 5000]
        tri = vertices[f]
        points = np.einsum("qi,fij->fqj", _BARY, tri).reshape(-1, 3)
        value, local_error = _phi_error(field, origin, h, points)
        denominator = lip
        lower = (
            np.maximum(np.abs(value) - local_error, 0.0) / denominator
            if denominator > 0
            else np.zeros_like(value)
        )
        original_points = points.copy()
        centers = points.copy()
        upper, residual = _axis_root_witness(points, field, origin, h, interp)
        active = (~np.isfinite(upper)) | (upper > DISTANCE_LIMIT_M)
        for _ in range(20):
            ids = np.flatnonzero(active)
            if not len(ids):
                break
            q = centers[ids]
            value_q, _ = _phi_error(field, origin, h, q)
            step = h * 1e-5
            grad = np.empty((len(q), 3), dtype=np.float64)
            axes = _grid_axes(field.shape, origin, h)
            bounds_hi = np.array([axis[-1] for axis in axes])
            bounds_lo = np.array([axis[0] for axis in axes])
            for axis in range(3):
                plus = q.copy()
                minus = q.copy()
                plus[:, axis] = np.minimum(plus[:, axis] + step, bounds_hi[axis])
                minus[:, axis] = np.maximum(minus[:, axis] - step, bounds_lo[axis])
                width = plus[:, axis] - minus[:, axis]
                grad[:, axis] = np.divide(
                    interp(plus) - interp(minus),
                    width,
                    out=np.zeros(len(q), dtype=np.float64),
                    where=width > 0.0,
                )
            norm2 = np.einsum("ij,ij->i", grad, grad)
            valid = np.isfinite(norm2) & (norm2 > 0.0)
            displacement = np.zeros_like(q)
            displacement[valid] = (
                -value_q[valid, None] * grad[valid] / norm2[valid, None]
            )
            length = np.linalg.norm(displacement, axis=1)
            scale = np.minimum(1.0, h / np.maximum(length, np.finfo(float).tiny))
            q += displacement * scale[:, None]
            q = np.clip(q, origin, bounds_hi)
            centers[ids] = q
            value_new, _ = _phi_error(field, origin, h, q)
            new_upper, new_residual = _axis_root_witness(
                q, field, origin, h, interp, reference=original_points[ids]
            )
            improved = new_upper < upper[ids]
            upper[ids[improved]] = new_upper[improved]
            residual[ids] = np.minimum(residual[ids], new_residual)
            active[ids] = (~np.isfinite(upper[ids])) | (upper[ids] > DISTANCE_LIMIT_M)
            active[ids[~np.isfinite(value_new)]] = True
        unresolved = ~np.isfinite(upper)
        count = len(_BARY)
        shaped_lower = lower.reshape(-1, count)
        shaped_upper = upper.reshape(-1, count)
        shaped_unresolved = unresolved.reshape(-1, count)
        face_count = len(f)
        per_face[face_start : face_start + face_count, 0] = np.max(shaped_upper, axis=1)
        per_face[face_start : face_start + face_count, 1] = np.max(shaped_lower, axis=1)
        per_face[face_start : face_start + face_count, 2] = shaped_unresolved.sum(
            axis=1
        )
        sample_count += points.shape[0]
        finite_residual = residual[np.isfinite(residual)]
        if len(finite_residual):
            max_root_residual = max(max_root_residual, float(finite_residual.max()))
    max_lower = float(np.max(per_face[:, 1], initial=0.0)) if len(per_face) else 0.0
    unresolved_count = int(per_face[:, 2].sum())
    finite_upper = per_face[:, 0][np.isfinite(per_face[:, 0])]
    max_upper_report = float(finite_upper.max()) if len(finite_upper) else None
    return {
        "maximum_certified_upper_distance_m": max_upper_report,
        "maximum_certified_lower_distance_m": max_lower,
        "unresolved_sample_count": unresolved_count,
        "sample_count": sample_count,
        "global_trilinear_lipschitz_bound": lip,
        "maximum_witness_root_residual_m": max_root_residual,
        "distance_limit_m": DISTANCE_LIMIT_M,
        "within_limit": bool(
            unresolved_count == 0
            and max_upper_report is not None
            and max_upper_report <= DISTANCE_LIMIT_M
            and max_lower <= DISTANCE_LIMIT_M
        ),
        "certified_exceeds_limit": bool(max_lower > DISTANCE_LIMIT_M),
        "evidence_scope": "10 fixed face points; locally rounded interval root witnesses and coordinate guard; not interval arithmetic",
        "per_triangle_bounds_columns": [
            "maximum_upper_m",
            "maximum_lower_m",
            "unresolved_samples",
        ],
    }, per_face


def orientation(vertices, faces, phi, origin, h):
    """Score stored winding against original-field sidedness; never flips faces."""
    vertices, faces = _surface(vertices, faces)
    field, origin, h, interp = _field(phi, origin, h)
    top = topology(vertices, faces)
    if not top["topology_pass"]:
        return {
            "status": "N/A",
            "reason": "topology prerequisite failed",
            "topology": top,
            "components": [],
        }
    tri = vertices[faces]
    area2 = np.linalg.norm(
        np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
    )
    area = 0.5 * area2
    centroid = tri.mean(axis=1)
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]) / area2[:, None]
    _, inverse = np.unique(vertices, axis=0, return_inverse=True)
    exact_faces = inverse[faces]
    edge_array = np.sort(
        np.vstack(
            (exact_faces[:, [0, 1]], exact_faces[:, [1, 2]], exact_faces[:, [2, 0]])
        ),
        axis=1,
    )
    _, edge_group, edge_counts = np.unique(
        edge_array, axis=0, return_inverse=True, return_counts=True
    )
    face_ids = np.tile(np.arange(len(faces), dtype=np.int64), 3)
    labels, first = _mesh_labels(face_ids, edge_group, edge_counts)
    order = np.argsort(labels, kind="stable")
    sizes = np.bincount(labels, minlength=len(first))
    cuts = np.r_[0, np.cumsum(sizes)]
    tol = 64.0 * np.finfo(np.float64).eps * h
    rows = []
    every_outward = True
    for cid, ids in enumerate(np.split(order, cuts[1:-1])):
        delta_votes = []
        audits = []
        for ratio in (0.02, 0.05, 0.1):
            delta = ratio * h
            plus = centroid[ids] + delta * normal[ids]
            minus = centroid[ids] - delta * normal[ids]
            plus_phi = interp(plus)
            minus_phi = interp(minus)
            outward = (plus_phi > tol) & (minus_phi < -tol)
            inward = (plus_phi < -tol) & (minus_phi > tol)
            out_fraction = float(area[ids][outward].sum() / area[ids].sum())
            in_fraction = float(area[ids][inward].sum() / area[ids].sum())
            vote = (
                "outward"
                if out_fraction > 0.5
                else "inward"
                if in_fraction > 0.5
                else "ambiguous"
            )
            delta_votes.append(vote)
            audits.append(
                {
                    "delta_over_original_h": ratio,
                    "outward_area_fraction": out_fraction,
                    "inward_area_fraction": in_fraction,
                }
            )
        stable = (
            delta_votes[0] if len(set(delta_votes)) == 1 else "unstable_or_ambiguous"
        )
        comp_volume = float(
            np.einsum(
                "ij,ij->i",
                tri[ids, 0],
                np.cross(tri[ids, 1], tri[ids, 2]),
            ).sum()
            / 6.0
        )
        every_outward &= stable == "outward"
        rows.append(
            {
                "component_id": cid,
                "minimum_original_face_id": int(first[cid]),
                "face_count": int(len(ids)),
                "delta_votes": delta_votes,
                "stable_sidedness": stable,
                "already_outward": stable == "outward",
                "signed_volume_contribution_m3": comp_volume,
                "volume_class": "solid_boundary"
                if comp_volume > 0
                else "void_boundary"
                if comp_volume < 0
                else "ambiguous",
                "delta_audit": audits,
            }
        )
    global_volume = top["signed_volume_m3"]
    passed = bool(every_outward and global_volume > 0.0)
    return {
        "status": "PASS" if passed else "FAIL",
        "stored_faces_flipped": False,
        "rule": "stored faces require strict outward area majority >50% at each original-h offset; global signed volume must be positive",
        "deltas_over_original_h": [0.02, 0.05, 0.1],
        "roundoff_tolerance_m": tol,
        "topology": top,
        "components": rows,
        "all_components_already_outward": bool(every_outward),
        "global_signed_volume_m3": global_volume,
        "global_positive_volume": bool(global_volume > 0.0),
    }


def volume(phi, origin, h, n=16, chunk=128):
    """Integrate phi<0 with exact z roots and fixed xy Gauss quadrature."""
    field, origin, h, _ = _field(phi, origin, h)
    if n not in (16, 32, 64):
        raise ValueError("xy Gauss order n must be 16, 32, or 64")
    corners = np.stack(
        [
            field[
                i : field.shape[0] - 1 + i,
                j : field.shape[1] - 1 + j,
                k : field.shape[2] - 1 + k,
            ]
            for i in (0, 1)
            for j in (0, 1)
            for k in (0, 1)
        ],
        axis=-1,
    )
    low, high = corners.min(axis=-1), corners.max(axis=-1)
    active = np.argwhere((low <= 0.0) & (high >= 0.0))
    total = float(np.count_nonzero(high < 0.0))
    nodes, weights = np.polynomial.legendre.leggauss(n)
    nodes, weights = (nodes + 1.0) / 2.0, weights / 2.0
    uv = np.array([(x, y) for x in nodes for y in nodes])
    quadrature = np.array([wx * wy for wx in weights for wy in weights])
    bilinear = np.column_stack(
        (
            (1 - uv[:, 0]) * (1 - uv[:, 1]),
            (1 - uv[:, 0]) * uv[:, 1],
            uv[:, 0] * (1 - uv[:, 1]),
            uv[:, 0] * uv[:, 1],
        )
    )
    for start in range(0, len(active), chunk):
        block = corners[tuple(active[start : start + chunk].T)]
        bottom = block[:, [0, 2, 4, 6]] @ bilinear.T
        top = block[:, [1, 3, 5, 7]] @ bilinear.T
        fraction = np.zeros_like(bottom)
        inside = (bottom < 0.0) & (top < 0.0)
        rising = (bottom < 0.0) & (top >= 0.0)
        falling = (bottom >= 0.0) & (top < 0.0)
        fraction[inside] = 1.0
        fraction[rising] = (-bottom / np.where(top != bottom, top - bottom, 1.0))[
            rising
        ]
        fraction[falling] = (-top / np.where(bottom != top, bottom - top, 1.0))[falling]
        total += float((fraction @ quadrature).sum())
    return total * h**3


def _certified_ray_roots(point, normal, phi, origin, h, interp, span):
    """Fit each cell-local ray cubic, then certify roots by guarded signs."""
    breaks = [-span, span]
    for axis in range(3):
        if normal[axis] == 0.0:
            continue
        ts = (_grid_axes(phi.shape, origin, h)[axis] - point[axis]) / normal[axis]
        breaks.extend(ts[(ts > -span) & (ts < span)].tolist())
    breaks = np.unique(np.asarray(breaks, dtype=np.float64))
    fraction = np.array((0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0))
    vandermonde = np.polynomial.polynomial.polyvander(fraction, 3)
    roots = []
    zero_interval = False
    for ta, tb in zip(breaks[:-1], breaks[1:], strict=True):
        ts = ta + (tb - ta) * fraction
        probes = point[None, :] + ts[:, None] * normal[None, :]
        axes = _grid_axes(phi.shape, origin, h)
        grid_lo = np.array([axis[0] for axis in axes])
        grid_hi = np.array([axis[-1] for axis in axes])
        if np.any(probes < grid_lo) or np.any(probes > grid_hi):
            continue
        values, _ = _phi_error(phi, origin, h, probes)
        if np.all(values == 0.0):
            zero_interval = True
            continue
        coeff = np.linalg.solve(vandermonde, values)
        local_roots = np.polynomial.polynomial.polyroots(coeff)
        for local in local_roots:
            if abs(local.imag) > 1e-10 or local.real < -1e-10 or local.real > 1 + 1e-10:
                continue
            t = ta + (tb - ta) * float(np.clip(local.real, 0.0, 1.0))
            guard = h * 1e-8
            before, after = t - guard, t + guard
            test = (
                point[None, :] + np.array((before, t, after))[:, None] * normal[None, :]
            )
            grid_hi = origin + h * (np.asarray(phi.shape) - 1)
            if np.any(test < origin) or np.any(test > grid_hi):
                roots.append((t, False, float(abs(values[0]))))
                continue
            val, err = _phi_error(phi, origin, h, test)
            crossing = ((val[0] - err[0] > 0.0) and (val[2] + err[2] < 0.0)) or (
                (val[0] + err[0] < 0.0) and (val[2] - err[2] > 0.0)
            )
            roots.append((t, bool(crossing), float(abs(val[1]))))
    roots.sort(key=lambda row: abs(row[0]))
    unique = []
    for row in roots:
        if not unique or abs(row[0] - unique[-1][0]) > h * 1e-9:
            unique.append(row)
        else:
            unique[-1] = (
                unique[-1][0],
                unique[-1][1] and row[1],
                min(unique[-1][2], row[2]),
            )
    if not unique or zero_interval:
        return None, {
            "zero_polynomial_interval": zero_interval,
            "root_candidate_count": len(unique),
        }
    if len(unique) > 1 and abs(abs(unique[0][0]) - abs(unique[1][0])) <= h * 1e-9:
        return None, {"root_tie": True, "root_candidate_count": len(unique)}
    chosen = unique[0]
    if not chosen[1]:
        return None, {
            "root_uncertified": True,
            "root_residual_m": chosen[2],
            "root_candidate_count": len(unique),
        }
    return float(chosen[0]), {
        "root_residual_m": chosen[2],
        "root_candidate_count": len(unique),
    }


def fidelity(base_v, base_f, target_v, target_f, base_phi, target_phi, origin, h):
    """Compare 1,024 area-stratified baseline-normal SDF and mesh displacements."""
    import trimesh

    base_v, base_f = _surface(base_v, base_f)
    target_v, target_f = _surface(target_v, target_f)
    base_field, origin, h, base_interp = _field(base_phi, origin, h)
    target_field, _, _, target_interp = _field(target_phi, origin, h)
    tri = base_v[base_f]
    areas = 0.5 * np.linalg.norm(
        np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1
    )
    if not len(base_f) or not np.isfinite(areas).all() or areas.sum() <= 0.0:
        return {
            "sample_count": 0,
            "unresolved_samples": 0,
            "maximum_normal_displacement_difference_m": None,
            "within_limit": False,
            "reason": "empty or zero-area baseline mesh",
        }
    cdf = np.cumsum(areas) / areas.sum()
    face_ids = np.searchsorted(cdf, (np.arange(1024) + 0.5) / 1024.0, side="left")
    selected = np.unique(np.clip(face_ids, 0, len(base_f) - 1))
    centers = tri[selected].mean(axis=1)
    step = h * 1e-5
    gradient = np.empty_like(centers)
    grid_hi = origin + h * (np.asarray(base_field.shape) - 1)
    for axis in range(3):
        plus = centers.copy()
        minus = centers.copy()
        plus[:, axis] = np.minimum(plus[:, axis] + step, grid_hi[axis])
        minus[:, axis] = np.maximum(minus[:, axis] - step, origin[axis])
        width = plus[:, axis] - minus[:, axis]
        gradient[:, axis] = np.divide(
            base_interp(plus) - base_interp(minus),
            width,
            out=np.zeros(len(centers), dtype=np.float64),
            where=width > 0.0,
        )
    norm = np.linalg.norm(gradient, axis=1)
    normal_ok = np.isfinite(norm) & (norm > 64.0 * np.finfo(np.float64).eps)
    normals = np.zeros_like(gradient)
    normals[normal_ok] = gradient[normal_ok] / norm[normal_ok, None]
    target_mesh = trimesh.Trimesh(vertices=target_v, faces=target_f, process=False)
    intersector = None
    intersector_error = None
    try:
        intersector = trimesh.ray.ray_triangle.RayMeshIntersector(target_mesh)
    except Exception as exc:  # Runtime acceleration support is a per-sample limitation.
        intersector_error = type(exc).__name__ + ": " + str(exc)
    errors = np.full(len(selected), np.inf, dtype=np.float64)
    details = []
    for i, (point, normal) in enumerate(zip(centers, normals, strict=True)):
        detail = {"selected_face_id": int(selected[i])}
        if not normal_ok[i]:
            detail["unresolved_reason"] = "baseline analytic gradient undefined"
            details.append(detail)
            continue
        t0, a0 = _certified_ray_roots(
            point, normal, base_field, origin, h, base_interp, 2 * h
        )
        t1, a1 = _certified_ray_roots(
            point, normal, target_field, origin, h, target_interp, 2 * h
        )
        detail["baseline_root_audit"] = a0
        detail["target_root_audit"] = a1
        if t0 is None or t1 is None:
            detail["unresolved_reason"] = (
                "SDF ray root missing, ambiguous, or uncertified"
            )
            details.append(detail)
            continue
        if intersector is None:
            detail["unresolved_reason"] = "target mesh ray intersector unavailable"
            detail["ray_intersector_error"] = intersector_error
            details.append(detail)
            continue
        ray_origin = point - 2.0 * h * normal
        try:
            locations, _, _ = intersector.intersects_location(
                np.asarray([ray_origin]), np.asarray([normal]), multiple_hits=True
            )
        except Exception as exc:
            detail["unresolved_reason"] = "target mesh ray query failed"
            detail["ray_intersector_error"] = type(exc).__name__ + ": " + str(exc)
            details.append(detail)
            continue
        ts = (locations - point) @ normal if len(locations) else np.empty(0)
        ts = np.sort(ts[np.abs(ts) <= 2.0 * h])
        unique_hits = []
        for t in ts:
            if not unique_hits or abs(t - unique_hits[-1]) > h * 1e-9:
                unique_hits.append(float(t))
        if not unique_hits:
            detail["unresolved_reason"] = (
                "no target mesh intersection in registered ray span"
            )
            details.append(detail)
            continue
        absolute = np.abs(unique_hits)
        order = np.argsort(absolute)
        if len(order) > 1 and absolute[order[1]] - absolute[order[0]] <= h * 1e-9:
            detail["unresolved_reason"] = "nearest target mesh intersections tie"
            details.append(detail)
            continue
        target_mesh_t = unique_hits[int(order[0])]
        errors[i] = abs(target_mesh_t - (t1 - t0)) + 2.0 * h * 1e-8 + h * 1e-9
        detail.update(
            {
                "baseline_root_t_m": t0,
                "target_root_t_m": t1,
                "target_mesh_root_t_m": target_mesh_t,
                "upper_error_bound_m": errors[i],
            }
        )
        details.append(detail)
    unresolved = int(np.count_nonzero(~np.isfinite(errors)))
    finite = errors[np.isfinite(errors)]
    maximum = float(finite.max()) if len(finite) else None
    top_base = topology(base_v, base_f)
    top_target = topology(target_v, target_f)
    ori_base = orientation(base_v, base_f, base_field, origin, h)
    ori_target = orientation(target_v, target_f, target_field, origin, h)
    prerequisites = bool(
        top_base["topology_pass"]
        and top_target["topology_pass"]
        and ori_base["status"] == "PASS"
        and ori_target["status"] == "PASS"
    )
    return {
        "sample_count": int(len(selected)),
        "requested_stratified_sample_count": 1024,
        "unresolved_samples": unresolved,
        "maximum_normal_displacement_difference_m": maximum,
        "within_limit": bool(
            unresolved == 0 and maximum is not None and maximum <= DISTANCE_LIMIT_M
        ),
        "geometry_prerequisite_pass": prerequisites,
        "baseline_topology": top_base,
        "target_topology": top_target,
        "baseline_orientation": ori_base,
        "target_orientation": ori_target,
        "sample_face_ids": selected.astype(int).tolist(),
        "samples": details,
        "limit_m": DISTANCE_LIMIT_M,
        "ray_span_m": 2.0 * h,
        "normal_gradient_method": "centered finite difference with one-sided grid-boundary clipping, step h*1e-5",
        "evidence_scope": "fixed area-stratified normal-ray correspondence; source SDF roots are interval-sign certified, not a continuous Hausdorff bound",
    }
