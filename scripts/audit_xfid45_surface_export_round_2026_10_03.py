#!/usr/bin/env python3
"""Evaluate the preregistered geometry-only #45 surface candidate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyvista as pv
import scipy
import trimesh
import vtk
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from cfd_sdf.surface_canonicalization import (  # noqa: E402
    canonicalize_triangle_surface,
    trilinear_gradient,
)

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
ORIENTATION_ROUNDOFF_FACTOR = 64.0
EXPECTED_CANONICAL_EXACT_ZERO_NODE_COUNT = 498


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(path, process=False, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError(f"not a nonempty triangle mesh: {path}")
    return mesh


def merge_exact_coordinates(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    vertices, inverse = np.unique(
        np.asarray(mesh.vertices), axis=0, return_inverse=True
    )
    return vertices, inverse[np.asarray(mesh.faces, dtype=np.int64)]


def triangle_key(points: np.ndarray) -> bytes:
    triangle = np.asarray(points, dtype="<f4")
    order = np.lexsort((triangle[:, 2], triangle[:, 1], triangle[:, 0]))
    return np.ascontiguousarray(triangle[order]).tobytes()


def surface_triangle_keys(vertices: np.ndarray, faces: np.ndarray) -> set[bytes]:
    points = np.asarray(vertices)[np.asarray(faces, dtype=np.int64)]
    return {
        triangle_key(triangle)
        for triangle in points
        if np.linalg.norm(
            np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        )
        > 0.0
    }


def topology(vertices: np.ndarray, faces: np.ndarray) -> dict[str, object]:
    vertices = np.asarray(vertices)
    faces = np.asarray(faces, dtype=np.int64)
    edge_incidence: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    face_parent = np.arange(len(faces), dtype=np.int64)

    def find(index: int) -> int:
        while face_parent[index] != index:
            face_parent[index] = face_parent[face_parent[index]]
            index = int(face_parent[index])
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            face_parent[max(a, b)] = min(a, b)

    face_keys: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    areas = np.zeros(len(faces), dtype=np.float64)
    signed_volume = 0.0
    for face_id, face in enumerate(faces):
        key = tuple(sorted(int(index) for index in face))
        face_keys[key].append(face_id)
        p0, p1, p2 = vertices[face].astype(np.float64, copy=False)
        cross = np.cross(p1 - p0, p2 - p0)
        areas[face_id] = 0.5 * np.linalg.norm(cross)
        signed_volume += float(np.dot(p0, np.cross(p1, p2))) / 6.0
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (int(min(a, b)), int(max(a, b)))
            direction = 1 if (int(a), int(b)) == edge else -1
            edge_incidence[edge].append((face_id, direction))

    for incident in edge_incidence.values():
        for face_id, _ in incident[1:]:
            union(incident[0][0], face_id)

    counts = np.asarray(
        [len(incident) for incident in edge_incidence.values()], dtype=np.int64
    )
    watertight = bool(len(counts) > 0 and np.all(counts == 2))
    winding_consistent = bool(
        watertight
        and all(
            incident[0][1] == -incident[1][1] for incident in edge_incidence.values()
        )
    )
    duplicate_count = sum(len(group) - 1 for group in face_keys.values())
    used_vertices = np.unique(faces) if len(faces) else np.asarray([], dtype=np.int64)
    roots = {find(index) for index in range(len(faces))}
    components = len(roots)
    euler = int(len(used_vertices) - len(edge_incidence) + len(faces))
    enclosed = watertight and winding_consistent and duplicate_count == 0
    return {
        "exact_unique_vertex_count": int(len(vertices)),
        "referenced_vertex_count": int(len(used_vertices)),
        "triangle_count": int(len(faces)),
        "connected_component_count_edge_adjacency": int(components),
        "euler_characteristic_referenced_mesh": euler,
        "area_m2_including_duplicate_faces": float(areas.sum()),
        "area_m2_unique_positive_area_triangles": float(
            sum(
                areas[group[0]] for group in face_keys.values() if areas[group[0]] > 0.0
            )
        ),
        "watertight": watertight,
        "winding_consistent": winding_consistent,
        "non_manifold_edge_count_incidence_not_two": int(np.count_nonzero(counts != 2)),
        "boundary_edge_count": int(np.count_nonzero(counts == 1)),
        "edges_with_more_than_two_faces": int(np.count_nonzero(counts > 2)),
        "duplicate_face_count": int(duplicate_count),
        "signed_volume_m3": float(signed_volume) if enclosed else None,
        "unsigned_enclosed_volume_m3": abs(float(signed_volume)) if enclosed else None,
        "face_areas_m2": areas,
        "edge_incidence": edge_incidence,
        "face_key_groups": face_keys,
    }


def xyz_hash(vertices: np.ndarray) -> str:
    canonical = np.asarray(np.unique(vertices, axis=0), dtype="<f4")
    return hashlib.sha256(np.ascontiguousarray(canonical).tobytes()).hexdigest()


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


def mesh_stats(mesh: trimesh.Trimesh) -> dict[str, object]:
    vertices, faces = merge_exact_coordinates(mesh)
    stats = topology(vertices, faces)
    lo, hi = (np.asarray(row, dtype=np.float64) for row in FLOW_DOMAIN)
    bounds = np.asarray(mesh.bounds, dtype=np.float64)
    clearance = np.minimum(bounds[0] - lo, hi - bounds[1])
    stats.pop("face_areas_m2")
    stats.pop("edge_incidence")
    stats.pop("face_key_groups")
    stats.update(
        {
            "unique_vertex_coordinate_set_sha256_float32_lex": xyz_hash(vertices),
            "bounds_m": bounds.tolist(),
            "stage_v_clearance_by_axis_m": clearance.tolist(),
            "minimum_stage_v_clearance_m": float(clearance.min()),
        }
    )
    return stats


def structured_grid(state: SDFDesignState) -> tuple[pv.ImageData, pv.PolyData]:
    grid = pv.ImageData()
    grid.dimensions = state.shape
    grid.origin = tuple(state.origin_m)
    grid.spacing = (state.spacing_m,) * 3
    grid.point_data["design_phi"] = np.ascontiguousarray(state.phi.ravel(order="F"))
    grid.cell_data["source_grid_cell_id"] = np.arange(grid.n_cells, dtype=np.int64)
    surface = grid.contour(isosurfaces=[0.0], scalars="design_phi")
    if surface.n_cells == 0 or "source_grid_cell_id" not in surface.cell_data:
        raise ValueError("zero contour did not retain source grid cell IDs")
    return grid, surface


def source_cell_ids_by_triangle(
    mesh: trimesh.Trimesh, surface: pv.PolyData
) -> list[int]:
    vtk_faces = np.asarray(surface.faces, dtype=np.int64)
    if vtk_faces.size % 4 or (vtk_faces.reshape(-1, 4)[:, 0] != 3).any():
        raise ValueError("zero contour did not consist only of triangles")
    contour_faces = vtk_faces.reshape(-1, 4)[:, 1:]
    contour_cells = np.asarray(surface.cell_data["source_grid_cell_id"], dtype=np.int64)
    if len(contour_faces) != len(contour_cells):
        raise ValueError("source cell IDs do not align with contour triangles")
    by_key: dict[bytes, list[int]] = defaultdict(list)
    contour_points = np.asarray(surface.points)
    for face, cell_id in zip(contour_faces, contour_cells, strict=True):
        by_key[triangle_key(contour_points[face])].append(int(cell_id))
    for cell_ids in by_key.values():
        cell_ids.sort()

    counts = Counter()
    result = []
    for face in np.asarray(mesh.faces, dtype=np.int64):
        key = triangle_key(np.asarray(mesh.vertices)[face])
        offset = counts[key]
        if key not in by_key or offset >= len(by_key[key]):
            raise ValueError(
                "raw PLY triangle cannot be mapped to a contour source cell"
            )
        result.append(by_key[key][offset])
        counts[key] += 1
    if counts != Counter({key: len(values) for key, values in by_key.items()}):
        raise ValueError(
            "raw PLY and metadata-bearing contour triangle multisets differ"
        )
    return result


def grid_cell_details(
    grid: pv.ImageData, state: SDFDesignState, cell_id: int
) -> dict[str, object]:
    cell = grid.GetCell(int(cell_id))
    nodes = []
    for local_id in range(cell.GetNumberOfPoints()):
        point_id = int(cell.GetPointId(local_id))
        ijk = tuple(
            int(index) for index in np.unravel_index(point_id, state.shape, order="F")
        )
        value = float(state.phi[ijk])
        nodes.append({"ijk": list(ijk), "phi": value, "exact_zero": bool(value == 0.0)})
    nodes.sort(key=lambda row: row["ijk"])
    return {
        "source_grid_cell_id": int(cell_id),
        "grid_node_indices_ijk": [row["ijk"] for row in nodes],
        "node_phi_values_and_exact_zero": nodes,
        "contains_exact_zero_grid_node": any(row["exact_zero"] for row in nodes),
    }


def grid_node_at_vertex(
    point: np.ndarray, state: SDFDesignState
) -> tuple[int, int, int] | None:
    q = (
        np.asarray(point, dtype=np.float64) - np.asarray(state.origin_m)
    ) / state.spacing_m
    ijk = np.rint(q).astype(np.int64)
    if np.any(ijk < 0) or np.any(ijk >= np.asarray(state.shape)):
        return None
    node = np.asarray(state.origin_m) + state.spacing_m * ijk
    if np.array_equal(np.asarray(point, dtype="<f4"), np.asarray(node, dtype="<f4")):
        return tuple(int(index) for index in ijk)
    return None


def raw_orientation_rows(
    mesh: trimesh.Trimesh,
    state: SDFDesignState,
    source_cells: list[int],
    output_path: Path,
) -> dict[str, object]:
    vertices, faces = merge_exact_coordinates(mesh)
    counts = {"positive": 0, "negative": 0, "ambiguous": 0}
    minimum_abs_dot = float("inf")
    with gzip.open(output_path, "wt", encoding="utf-8", newline="\n") as stream:
        for triangle_id, (face, cell_id) in enumerate(
            zip(faces, source_cells, strict=True)
        ):
            points = vertices[face].astype(np.float64, copy=False)
            cross = np.cross(points[1] - points[0], points[2] - points[0])
            area2 = float(np.linalg.norm(cross))
            if area2 == 0.0:
                normal = np.zeros(3)
            else:
                normal = cross / area2
            centroid = points.mean(axis=0)
            gradient, grad_cell, corners = trilinear_gradient(
                state.phi, state.origin_m, state.spacing_m, centroid
            )
            dot = float(np.dot(normal, gradient))
            tolerance = (
                ORIENTATION_ROUNDOFF_FACTOR
                * np.finfo(np.float64).eps
                * max(1.0, float(np.linalg.norm(gradient)))
            )
            label = (
                "positive"
                if dot > tolerance
                else "negative"
                if dot < -tolerance
                else "ambiguous"
            )
            counts[label] += 1
            minimum_abs_dot = min(minimum_abs_dot, abs(dot))
            nodes = grid_nodes_for_cell(state, grad_cell)
            row = {
                "source_triangle_id": triangle_id,
                "source_contouring_cell_id": int(cell_id),
                "gradient_sample_cell_index_ijk": list(grad_cell),
                "triangle_vertices_m": points.tolist(),
                "triangle_area_m2": area2 * 0.5,
                "triangle_normal": normal.tolist(),
                "triangle_centroid_m": centroid.tolist(),
                "sdf_gradient_at_centroid": gradient.tolist(),
                "normal_gradient_dot": dot,
                "dot_roundoff_tolerance": tolerance,
                "dot_sign": label,
                "gradient_cell_corner_phi_000_to_111": corners.ravel(
                    order="C"
                ).tolist(),
                "gradient_cell_exact_zero_nodes_ijk": [
                    node for node in nodes if state.phi[node] == 0.0
                ],
            }
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    return {
        "triangle_count": len(faces),
        "dot_sign_counts_before_orientation": counts,
        "minimum_absolute_normal_gradient_dot": minimum_abs_dot,
        "orientation_resolvable": counts["ambiguous"] == 0,
    }


def grid_nodes_for_cell(
    state: SDFDesignState, cell: tuple[int, int, int]
) -> list[tuple[int, int, int]]:
    return [
        (cell[0] + a, cell[1] + b, cell[2] + c)
        for a in (0, 1)
        for b in (0, 1)
        for c in (0, 1)
    ]


def triangle_detail(
    triangle_id: int,
    mesh: trimesh.Trimesh,
    vertices: np.ndarray,
    faces: np.ndarray,
    source_cells: list[int],
    grid: pv.ImageData,
    state: SDFDesignState,
    input_vertex_instances: dict[int, list[int]],
    area: float,
) -> dict[str, object]:
    face = faces[triangle_id]
    points = vertices[face]
    cell_id = source_cells[triangle_id]
    cell_info = grid_cell_details(grid, state, cell_id)
    node_hits = [grid_node_at_vertex(point, state) for point in points]
    exact_vertex_nodes = sorted({hit for hit in node_hits if hit is not None})
    zero_nodes = {
        tuple(row["ijk"])
        for row in cell_info["node_phi_values_and_exact_zero"]
        if row["exact_zero"]
    }
    zero_nodes.update(node for node in exact_vertex_nodes if state.phi[node] == 0.0)
    return {
        "source_triangle_id": int(triangle_id),
        "source_contouring_cell_id": int(cell_id),
        "triangle_area_m2": float(area),
        "triangle_vertex_coordinates_m": points.tolist(),
        "source_vertex_instances_for_each_exact_coordinate": [
            input_vertex_instances[int(index)] for index in face
        ],
        "triangle_vertices_coincident_with_grid_nodes_ijk": [
            list(hit) if hit is not None else None for hit in node_hits
        ],
        "source_cell": cell_info,
        "exact_zero_grid_nodes_involved_ijk": [
            list(node) for node in sorted(zero_nodes)
        ],
        "touches_exact_zero_grid_node": bool(zero_nodes),
    }


def baseline_defects(
    mesh: trimesh.Trimesh,
    source_cells: list[int],
    grid: pv.ImageData,
    state: SDFDesignState,
    output_path: Path,
) -> dict[str, object]:
    raw_vertices = np.asarray(mesh.vertices)
    instances: dict[int, list[int]] = defaultdict(list)
    unique_vertices, inverse = np.unique(raw_vertices, axis=0, return_inverse=True)
    for original_id, unique_id in enumerate(inverse):
        instances[int(unique_id)].append(original_id)
    faces = inverse[np.asarray(mesh.faces, dtype=np.int64)]
    topo = topology(unique_vertices, faces)
    edge_incidence = topo["edge_incidence"]
    face_keys = topo["face_key_groups"]
    triangle_areas = topo["face_areas_m2"]
    records = Counter()
    zero_entity_counts = Counter()
    defect_triangles: set[int] = set()
    zero_defect_triangles: set[int] = set()
    source_vertex_instances = {key: value for key, value in instances.items()}

    def emit(
        kind: str,
        defect_id: str,
        triangle_ids: list[int],
        edge: tuple[int, int] | None = None,
    ) -> None:
        details = [
            triangle_detail(
                triangle_id,
                mesh,
                unique_vertices,
                faces,
                source_cells,
                grid,
                state,
                source_vertex_instances,
                float(triangle_areas[triangle_id]),
            )
            for triangle_id in triangle_ids
        ]
        touched_zero = any(row["touches_exact_zero_grid_node"] for row in details)
        records[kind] += 1
        zero_entity_counts[kind] += int(touched_zero)
        defect_triangles.update(triangle_ids)
        if touched_zero:
            zero_defect_triangles.update(triangle_ids)
        row = {
            "defect_type": kind,
            "defect_id": defect_id,
            "source_triangles": details,
            "touches_exact_zero_grid_node": touched_zero,
        }
        if edge is not None:
            row["coincident_edge_vertices"] = [
                {
                    "merged_vertex_id": int(vertex_id),
                    "coordinate_m": unique_vertices[vertex_id].tolist(),
                    "source_vertex_instance_ids": source_vertex_instances[
                        int(vertex_id)
                    ],
                }
                for vertex_id in edge
            ]
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

    with gzip.open(output_path, "wt", encoding="utf-8", newline="\n") as stream:
        for edge, incident in sorted(edge_incidence.items()):
            if len(incident) != 2:
                emit(
                    "edge_incidence_not_two",
                    f"edge:{edge[0]}:{edge[1]}",
                    [row[0] for row in incident],
                    edge,
                )
            elif incident[0][1] == incident[1][1]:
                emit(
                    "winding_conflict_edge",
                    f"edge:{edge[0]}:{edge[1]}",
                    [row[0] for row in incident],
                    edge,
                )
        for key, group in sorted(face_keys.items()):
            for duplicate_id in group[1:]:
                emit(
                    "duplicate_face",
                    f"face:{group[0]}:{duplicate_id}",
                    [group[0], duplicate_id],
                )

    totals = dict(records)
    zero_counts = dict(zero_entity_counts)
    total_entities = sum(totals.values())
    total_zero = sum(zero_counts.values())
    return {
        "exact_zero_grid_node_count": int(np.count_nonzero(state.phi == 0.0)),
        "unique_raw_surface_vertex_count": int(len(unique_vertices)),
        "raw_triangle_count": int(len(faces)),
        "non_manifold_edge_count_incidence_not_two": int(
            topo["non_manifold_edge_count_incidence_not_two"]
        ),
        "duplicate_face_count": int(topo["duplicate_face_count"]),
        "winding_conflict_edge_count_incidence_two_same_direction": int(
            records["winding_conflict_edge"]
        ),
        "defect_entity_counts": totals,
        "defect_entities_touching_any_exact_zero_grid_node": zero_counts,
        "defect_entity_count_total_categories_may_overlap": total_entities,
        "defect_entity_zero_touch_percent_total_categories_may_overlap": (
            100.0 * total_zero / total_entities if total_entities else 0.0
        ),
        "unique_source_triangles_involved_in_any_defect": len(defect_triangles),
        "unique_defect_source_triangles_touching_exact_zero": len(
            zero_defect_triangles
        ),
        "defect_source_triangle_zero_touch_percent": (
            100.0 * len(zero_defect_triangles) / len(defect_triangles)
            if defect_triangles
            else 0.0
        ),
        "detail_path": output_path.relative_to(ROOT).as_posix(),
        "detail_sha256": sha256_file(output_path),
    }


def validate_criteria(criteria_path: Path) -> dict[str, object]:
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("kind") != "xfid45_zero_level_surface_export_preregistration":
        raise ValueError("criteria kind mismatch")
    for relpath, expected in criteria["frozen_inputs"].items():
        actual = sha256_file(ROOT / relpath)
        if actual != expected:
            raise ValueError(f"frozen input hash mismatch: {relpath}")
    for relpath, expected in criteria["frozen_sources"].items():
        actual = sha256_file(ROOT / relpath)
        if actual != expected:
            raise ValueError(f"frozen source hash mismatch: {relpath}")
    return criteria


def evaluate_case(case_id: str, case_dir: Path) -> dict[str, object]:
    case_dir.mkdir(parents=True, exist_ok=True)
    state_path = (
        EVIDENCE / "canonical_state.npz"
        if case_id == "baseline"
        else EVIDENCE / "state_snapshots" / f"{case_id}.npz"
    )
    state = SDFDesignState.load(state_path)
    raw_ply = EVIDENCE / "surfaces" / case_id / "canonical_export" / "zero_surface.ply"
    raw_stl = EVIDENCE / "surfaces" / case_id / "design_candidate.stl"
    raw_mesh = load_mesh(raw_ply)
    raw_stl_mesh = load_mesh(raw_stl)
    grid, surface = structured_grid(state)
    source_cells = source_cell_ids_by_triangle(raw_mesh, surface)

    before_ply = mesh_stats(raw_mesh)
    before_stl = mesh_stats(raw_stl_mesh)
    raw_ply_stl_support_same = surface_triangle_keys(
        raw_mesh.vertices, raw_mesh.faces
    ) == surface_triangle_keys(raw_stl_mesh.vertices, raw_stl_mesh.faces)
    orientation_path = case_dir / "raw_orientation.jsonl.gz"
    orientation = raw_orientation_rows(raw_mesh, state, source_cells, orientation_path)

    if case_id == "baseline":
        defect_path = case_dir / "defect_to_grid.jsonl.gz"
        defects = baseline_defects(raw_mesh, source_cells, grid, state, defect_path)
    else:
        defects = None

    result = canonicalize_triangle_surface(
        raw_mesh.vertices,
        raw_mesh.faces,
        phi=state.phi,
        origin_m=state.origin_m,
        spacing_m=state.spacing_m,
    )
    candidate = trimesh.Trimesh(
        vertices=result.vertices,
        faces=result.faces,
        process=False,
    )
    candidate_ply = case_dir / "candidate_zero_surface.ply"
    candidate_stl = case_dir / "stage_v_candidate.stl"
    candidate.export(candidate_ply)
    candidate.export(candidate_stl)
    stage_v_mesh = load_mesh(candidate_stl)
    after = mesh_stats(stage_v_mesh)

    before_unique = np.unique(np.asarray(raw_mesh.vertices), axis=0)
    after_unique = np.unique(np.asarray(candidate.vertices), axis=0)
    stage_v_unique = np.unique(np.asarray(stage_v_mesh.vertices), axis=0)
    vertex_set_same = bool(np.array_equal(before_unique, after_unique))
    bounds_same = bool(
        np.array_equal(np.asarray(raw_mesh.bounds), np.asarray(candidate.bounds))
    )
    before_support = surface_triangle_keys(raw_mesh.vertices, raw_mesh.faces)
    after_support = surface_triangle_keys(candidate.vertices, candidate.faces)
    surface_support_same = before_support == after_support
    checks = {
        "source_cell_mapping_complete": len(source_cells) == len(raw_mesh.faces),
        "raw_ply_and_stage_v_stl_positive_area_surface_support_matches": raw_ply_stl_support_same,
        "candidate_vertex_coordinate_set_exactly_unchanged": vertex_set_same,
        "candidate_bounds_exactly_unchanged": bounds_same,
        "candidate_positive_area_triangle_surface_support_unchanged": surface_support_same,
        "watertight": bool(after["watertight"]),
        "winding_consistent": bool(after["winding_consistent"]),
        "non_manifold_edge_count_zero": after[
            "non_manifold_edge_count_incidence_not_two"
        ]
        == 0,
        "duplicate_face_count_zero": after["duplicate_face_count"] == 0,
        "positive_signed_volume": bool(
            after["signed_volume_m3"] is not None and after["signed_volume_m3"] > 0.0
        ),
        "stage_v_clearance_at_least_0p25_m": after["minimum_stage_v_clearance_m"]
        >= MINIMUM_CLEARANCE_M,
        "all_surface_face_orientations_resolved": result.audit[
            "ambiguous_face_ids_after_cleanup"
        ]
        == [],
        "all_surface_normals_follow_positive_sdf_gradient": all(
            row["normal_gradient_dot_before_orientation"]
            > row["dot_roundoff_tolerance"]
            or row["face_flipped"]
            for row in result.audit["orientation_rows"]
        ),
    }
    if case_id == "baseline":
        checks["canonical_v17_exact_zero_node_count_matches_498"] = (
            int(np.count_nonzero(state.phi == 0.0))
            == EXPECTED_CANONICAL_EXACT_ZERO_NODE_COUNT
        )
    # Recompute post-orientation SDF dots from the candidate faces before recording the gate.
    for face in candidate.faces:
        points = candidate.vertices[face].astype(np.float64, copy=False)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        normal /= np.linalg.norm(normal)
        gradient, _, _ = trilinear_gradient(
            state.phi, state.origin_m, state.spacing_m, points.mean(axis=0)
        )
        tolerance = (
            ORIENTATION_ROUNDOFF_FACTOR
            * np.finfo(np.float64).eps
            * max(1.0, float(np.linalg.norm(gradient)))
        )
        if float(np.dot(normal, gradient)) <= tolerance:
            checks["all_surface_normals_follow_positive_sdf_gradient"] = False
            break

    row = {
        "case_id": case_id,
        "state_snapshot_path": state_path.relative_to(ROOT).as_posix(),
        "state_snapshot_sha256": sha256_file(state_path),
        "state_sha256": state.state_sha256,
        "phi_c_order_sha256": hashlib.sha256(
            np.ascontiguousarray(state.phi).tobytes()
        ).hexdigest(),
        "phi_fortran_order_sha256": hashlib.sha256(
            np.asfortranarray(state.phi).tobytes(order="F")
        ).hexdigest(),
        "raw_ply_path": raw_ply.relative_to(ROOT).as_posix(),
        "raw_ply_sha256": sha256_file(raw_ply),
        "raw_stl_path": raw_stl.relative_to(ROOT).as_posix(),
        "raw_stl_sha256": sha256_file(raw_stl),
        "metadata_contour_triangle_count": int(surface.n_cells),
        "source_cell_mapping_complete": checks["source_cell_mapping_complete"],
        "raw_mesh_before": before_ply,
        "raw_stage_v_stl_before": before_stl,
        "raw_ply_and_stage_v_stl_surface_support_matches": raw_ply_stl_support_same,
        "candidate_mesh_after_stl_roundtrip": after,
        "candidate_ply_path": candidate_ply.relative_to(ROOT).as_posix(),
        "candidate_ply_sha256": sha256_file(candidate_ply),
        "candidate_stage_v_stl_path": candidate_stl.relative_to(ROOT).as_posix(),
        "candidate_stage_v_stl_sha256": sha256_file(candidate_stl),
        "raw_orientation": orientation,
        "raw_orientation_path": orientation_path.relative_to(ROOT).as_posix(),
        "raw_orientation_sha256": sha256_file(orientation_path),
        "canonicalization_audit": {
            key: value
            for key, value in result.audit.items()
            if key != "orientation_rows"
        },
        "geometry_identity": {
            "raw_unique_vertex_coordinate_sha256": xyz_hash(raw_mesh.vertices),
            "candidate_unique_vertex_coordinate_sha256": xyz_hash(candidate.vertices),
            "vertex_coordinate_set_exactly_unchanged": vertex_set_same,
            "vertex_coordinate_set_hausdorff_distance_m": point_set_hausdorff(
                before_unique, after_unique
            ),
            "stage_v_serialized_vertex_coordinate_set_hausdorff_distance_m": point_set_hausdorff(
                before_unique, stage_v_unique
            ),
            "raw_positive_area_triangle_support_count": len(before_support),
            "candidate_positive_area_triangle_support_count": len(after_support),
            "positive_area_triangle_support_exactly_unchanged": surface_support_same,
            "positive_area_triangle_surface_hausdorff_distance_m": 0.0
            if surface_support_same
            else None,
            "bounds_exactly_unchanged": bounds_same,
        },
        "checks": checks,
        "status": "PASS" if all(value is True for value in checks.values()) else "FAIL",
    }
    if defects is not None:
        row["baseline_defect_localization"] = defects
    write_json(case_dir / "case_audit.json", row)
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    criteria_path = args.criteria.resolve()
    output = args.output.resolve()
    validate_criteria(criteria_path)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite nonempty output: {output}")
    output.mkdir(parents=True, exist_ok=True)

    rows = {}
    for case_id in CASE_IDS:
        rows[case_id] = evaluate_case(case_id, output / "cases" / case_id)
    all_pass = all(row["status"] == "PASS" for row in rows.values())
    payload = {
        "schema_version": 1,
        "kind": "xfid45_zero_level_surface_export_candidate_result",
        "criteria_path": criteria_path.relative_to(ROOT).as_posix(),
        "criteria_sha256": sha256_file(criteria_path),
        "evidence_class": "solver_free_geometry_export_qualification_candidate",
        "solver_started": False,
        "formal_xfid_started": False,
        "repository_head_at_evaluation": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "repository_branch_at_evaluation": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "case_order": list(CASE_IDS),
        "cases": {case_id: rows[case_id] for case_id in CASE_IDS},
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pyvista": pv.__version__,
            "scipy": scipy.__version__,
            "vtk": vtk.vtkVersion.GetVTKVersion(),
            "trimesh": trimesh.__version__,
        },
        "candidate_sequence_passed_all_cases": all_pass,
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
    result_path = output / "result.json"
    write_json(result_path, payload)
    print(
        json.dumps(
            {
                "result": result_path.as_posix(),
                "case_status": {key: row["status"] for key, row in rows.items()},
                "all_pass": all_pass,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
