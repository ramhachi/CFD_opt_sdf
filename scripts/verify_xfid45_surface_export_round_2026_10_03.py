#!/usr/bin/env python3
"""Independently recompute geometry gates for a registered #45 export round."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03"
CASE_IDS = (
    "baseline",
    "D0_interface_offset_minus",
    "D0_interface_offset_plus",
    "D1_filtered_seed11_minus",
    "D1_filtered_seed11_plus",
    "D2_filtered_seed2026_minus",
    "D2_filtered_seed2026_plus",
)
FLOW_DOMAIN = ((-2.5, -1.2, -0.9), (2.5, 1.2, 0.9))
MINIMUM_CLEARANCE_M = 0.25
ROUND_OFF_FACTOR = 64.0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, process=False, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError(f"not a nonempty triangle mesh: {path}")
    return mesh


def merged(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    vertices, inverse = np.unique(
        np.asarray(mesh.vertices), axis=0, return_inverse=True
    )
    return vertices, inverse[np.asarray(mesh.faces, dtype=np.int64)]


def triangle_key(points: np.ndarray) -> bytes:
    tri = np.asarray(points, dtype="<f4")
    order = np.lexsort((tri[:, 2], tri[:, 1], tri[:, 0]))
    return np.ascontiguousarray(tri[order]).tobytes()


def triangle_support(mesh: trimesh.Trimesh) -> set[bytes]:
    points = np.asarray(mesh.vertices)[np.asarray(mesh.faces, dtype=np.int64)]
    keys = set()
    for triangle in points:
        if (
            np.linalg.norm(
                np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            )
            > 0.0
        ):
            keys.add(triangle_key(triangle))
    return keys


def point_set_hausdorff(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if len(left) == 0 or len(right) == 0:
        raise ValueError("Hausdorff distance requires two nonempty point sets")
    return float(
        max(
            cKDTree(right).query(left, k=1)[0].max(),
            cKDTree(left).query(right, k=1)[0].max(),
        )
    )


def contour_faces(
    phi: np.ndarray, origin: tuple[float, ...], spacing: float
) -> Counter[bytes]:
    grid = pv.ImageData()
    grid.dimensions = phi.shape
    grid.origin = origin
    grid.spacing = (spacing, spacing, spacing)
    grid.point_data["design_phi"] = np.ascontiguousarray(phi.ravel(order="F"))
    surface = grid.contour(isosurfaces=[0.0], scalars="design_phi")
    faces = np.asarray(surface.faces, dtype=np.int64).reshape(-1, 4)
    if len(faces) == 0 or (faces[:, 0] != 3).any():
        raise ValueError("independent zero contour is empty or non-triangular")
    points = np.asarray(surface.points)
    return Counter(triangle_key(points[row[1:]]) for row in faces)


def independent_stats(mesh: trimesh.Trimesh) -> dict[str, object]:
    vertices, faces = merged(mesh)
    edge_rows: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    face_keys = Counter()
    parent = list(range(len(faces)))
    signed_volume = 0.0
    area = 0.0
    unique_area_by_face: dict[tuple[int, int, int], float] = {}
    for face_id, face in enumerate(faces):
        face_key = tuple(sorted(map(int, face)))
        face_keys[face_key] += 1
        p = vertices[face].astype(np.float64, copy=False)
        cross = np.cross(p[1] - p[0], p[2] - p[0])
        face_area = float(np.linalg.norm(cross)) * 0.5
        area += face_area
        unique_area_by_face.setdefault(face_key, face_area)
        signed_volume += float(np.dot(p[0], np.cross(p[1], p[2]))) / 6.0
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (int(min(a, b)), int(max(a, b)))
            sign = 1 if (int(a), int(b)) == edge else -1
            edge_rows[edge].append((face_id, sign))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for rows in edge_rows.values():
        for face_id, _ in rows[1:]:
            left, right = find(rows[0][0]), find(face_id)
            if left != right:
                parent[max(left, right)] = min(left, right)
    edge_counts = [len(rows) for rows in edge_rows.values()]
    closed = bool(edge_counts) and all(count == 2 for count in edge_counts)
    oriented = closed and all(rows[0][1] == -rows[1][1] for rows in edge_rows.values())
    watertight = bool(closed)
    winding_consistent = bool(oriented)
    duplicate_count = sum(count - 1 for count in face_keys.values())
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    lo, hi = (np.asarray(row, dtype=np.float64) for row in FLOW_DOMAIN)
    clearance = np.minimum(bounds[0] - lo, hi - bounds[1])
    used = np.unique(faces) if len(faces) else np.asarray([], dtype=np.int64)
    return {
        "triangle_count": int(len(faces)),
        "unique_vertex_coordinate_count": int(len(vertices)),
        "connected_component_count_edge_adjacency": len(
            {find(i) for i in range(len(faces))}
        ),
        "euler_characteristic_referenced_mesh": int(
            len(used) - len(edge_rows) + len(faces)
        ),
        "area_m2_including_duplicate_faces": area,
        "area_m2_unique_positive_area_triangles": float(
            sum(unique_area_by_face.values())
        ),
        "watertight": watertight,
        "winding_consistent": winding_consistent,
        "non_manifold_edge_count_incidence_not_two": sum(
            count != 2 for count in edge_counts
        ),
        "duplicate_face_count": int(duplicate_count),
        "signed_volume_m3": signed_volume
        if watertight and winding_consistent and duplicate_count == 0
        else None,
        "unsigned_enclosed_volume_m3": abs(signed_volume)
        if watertight and winding_consistent and duplicate_count == 0
        else None,
        "bounds_m": bounds.tolist(),
        "minimum_stage_v_clearance_m": float(clearance.min()),
        "stage_v_clearance_by_axis_m": clearance.tolist(),
    }


def independent_gradient(
    phi: np.ndarray, origin: tuple[float, ...], spacing: float, point: np.ndarray
) -> np.ndarray:
    q = (np.asarray(point, dtype=np.float64) - np.asarray(origin)) / spacing
    upper = np.asarray(phi.shape) - 1
    if np.any(q < 0) or np.any(q > upper):
        raise ValueError("surface point is outside the GridSDF")
    cell = np.minimum(np.floor(q).astype(np.int64), upper - 1)
    t = q - cell
    corners = np.empty((2, 2, 2), dtype=np.float64)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                corners[a, b, c] = phi[tuple(cell + (a, b, c))]
    result = np.zeros(3, dtype=np.float64)
    for b in (0, 1):
        wb = t[1] if b else 1.0 - t[1]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            result[0] += (corners[1, b, c] - corners[0, b, c]) * wb * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            result[1] += (corners[a, 1, c] - corners[a, 0, c]) * wa * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for b in (0, 1):
            wb = t[1] if b else 1.0 - t[1]
            result[2] += (corners[a, b, 1] - corners[a, b, 0]) * wa * wb
    return result / spacing


def verify_case(
    case_id: str, case_result: dict[str, object], result_root: Path
) -> dict[str, object]:
    state_path = (
        EVIDENCE / "canonical_state.npz"
        if case_id == "baseline"
        else EVIDENCE / "state_snapshots" / f"{case_id}.npz"
    )
    with np.load(state_path, allow_pickle=False) as archive:
        phi = np.asarray(archive["phi"])
        metadata = json.loads(str(archive["metadata"].item()))
        origin = tuple(float(value) for value in metadata["origin_m"])
        spacing = float(metadata["spacing_m"])
    raw_path = EVIDENCE / "surfaces" / case_id / "canonical_export" / "zero_surface.ply"
    raw_stl_path = EVIDENCE / "surfaces" / case_id / "design_candidate.stl"
    candidate_ply = result_root / "cases" / case_id / "candidate_zero_surface.ply"
    candidate_stl = result_root / "cases" / case_id / "stage_v_candidate.stl"
    raw = load_mesh(raw_path)
    raw_stl = load_mesh(raw_stl_path)
    candidate = load_mesh(candidate_stl)
    candidate_ply_mesh = load_mesh(candidate_ply)

    raw_cells = contour_faces(phi, origin, spacing)
    raw_keys = Counter(
        triangle_key(np.asarray(raw.vertices)[face]) for face in np.asarray(raw.faces)
    )
    contour_matches = raw_cells == raw_keys
    raw_unique, _ = merged(raw)
    candidate_ply_unique, _ = merged(candidate_ply_mesh)
    candidate_stl_unique, _ = merged(candidate)
    vertex_set_matches = np.array_equal(raw_unique, candidate_ply_unique)
    support_matches = triangle_support(raw) == triangle_support(candidate)
    ply_stl_support_matches = triangle_support(candidate_ply_mesh) == triangle_support(
        candidate
    )

    stl_stats = independent_stats(candidate)
    raw_stats = independent_stats(raw_stl)
    vertices, faces = merged(candidate)
    dot_counts = {"positive": 0, "negative_or_ambiguous": 0}
    minimum_dot = float("inf")
    for face in faces:
        points = vertices[face].astype(np.float64, copy=False)
        cross = np.cross(points[1] - points[0], points[2] - points[0])
        norm = float(np.linalg.norm(cross))
        if norm == 0.0:
            dot_counts["negative_or_ambiguous"] += 1
            continue
        normal = cross / norm
        gradient = independent_gradient(phi, origin, spacing, points.mean(axis=0))
        dot = float(np.dot(normal, gradient))
        tolerance = (
            ROUND_OFF_FACTOR
            * np.finfo(np.float64).eps
            * max(1.0, float(np.linalg.norm(gradient)))
        )
        if dot > tolerance:
            dot_counts["positive"] += 1
        else:
            dot_counts["negative_or_ambiguous"] += 1
        minimum_dot = min(minimum_dot, dot)

    checks = {
        "raw_ply_is_reproduced_by_independent_zero_contour": contour_matches,
        "raw_ply_raw_stl_positive_area_support_matches": triangle_support(raw)
        == triangle_support(raw_stl),
        "candidate_vertex_coordinate_set_matches_raw_exactly": vertex_set_matches,
        "candidate_positive_area_triangle_support_matches_raw": support_matches,
        "candidate_ply_and_stage_v_stl_support_match": ply_stl_support_matches,
        "watertight": stl_stats["watertight"],
        "winding_consistent": stl_stats["winding_consistent"],
        "non_manifold_edge_count_zero": stl_stats[
            "non_manifold_edge_count_incidence_not_two"
        ]
        == 0,
        "duplicate_face_count_zero": stl_stats["duplicate_face_count"] == 0,
        "positive_signed_volume": stl_stats["signed_volume_m3"] is not None
        and stl_stats["signed_volume_m3"] > 0.0,
        "stage_v_clearance_at_least_0p25_m": stl_stats["minimum_stage_v_clearance_m"]
        >= MINIMUM_CLEARANCE_M,
        "all_candidate_faces_follow_positive_sdf_gradient": dot_counts[
            "negative_or_ambiguous"
        ]
        == 0,
    }
    summary = {
        "case_id": case_id,
        "input_state_sha256": sha256_file(state_path),
        "raw_ply_sha256": sha256_file(raw_path),
        "raw_stl_sha256": sha256_file(raw_stl_path),
        "candidate_ply_sha256": sha256_file(candidate_ply),
        "candidate_stage_v_stl_sha256": sha256_file(candidate_stl),
        "exact_zero_grid_node_count": int(np.count_nonzero(phi == 0.0)),
        "raw_stage_v_stl_metrics": raw_stats,
        "candidate_stage_v_stl_metrics": stl_stats,
        "candidate_orientation_dot_counts": dot_counts,
        "candidate_minimum_normal_gradient_dot": minimum_dot,
        "vertex_coordinate_hausdorff_distance_m": point_set_hausdorff(
            raw_unique, candidate_ply_unique
        ),
        "stage_v_serialized_vertex_coordinate_hausdorff_distance_m": point_set_hausdorff(
            raw_unique, candidate_stl_unique
        ),
        "surface_hausdorff_distance_m": 0.0 if support_matches else None,
        "checks": checks,
        "status": "PASS" if all(value is True for value in checks.values()) else "FAIL",
    }
    if (
        case_result["candidate_stage_v_stl_sha256"]
        != summary["candidate_stage_v_stl_sha256"]
    ):
        summary["status"] = "FAIL"
        summary["checks"]["result_manifest_candidate_stl_hash_matches"] = False
    else:
        summary["checks"]["result_manifest_candidate_stl_hash_matches"] = True
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    criteria_path = args.criteria.resolve()
    result_path = args.result.resolve()
    output_path = args.output.resolve()
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("kind") != "xfid45_zero_level_surface_export_preregistration":
        raise SystemExit("criteria kind mismatch")
    for group in ("frozen_inputs", "frozen_sources"):
        for relative_path, expected_hash in criteria[group].items():
            if sha256_file(ROOT / relative_path) != expected_hash:
                raise SystemExit(f"frozen {group} hash mismatch: {relative_path}")
    if (
        sha256_file(criteria_path)
        != json.loads(result_path.read_text())["criteria_sha256"]
    ):
        raise SystemExit("result is not bound to the supplied criteria")
    result = json.loads(result_path.read_text())
    cases = {
        case_id: verify_case(case_id, result["cases"][case_id], result_path.parent)
        for case_id in CASE_IDS
    }
    all_pass = all(case["status"] == "PASS" for case in cases.values())
    payload = {
        "schema_version": 1,
        "kind": "xfid45_surface_export_independent_recomputation",
        "criteria_sha256": sha256_file(criteria_path),
        "result_sha256": sha256_file(result_path),
        "verifier_source_sha256": sha256_file(Path(__file__)),
        "independent_recomputation": True,
        "canonicalizer_imported": False,
        "solver_started": False,
        "formal_xfid_started": False,
        "cases": cases,
        "all_seven_cases_pass": all_pass,
        "formal_xfid_resumption_eligible": all_pass,
        "qualification_flags": {
            "shape_update_allowed": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
            "solver_qualification": False,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {"output": output_path.as_posix(), "all_seven_pass": all_pass}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
