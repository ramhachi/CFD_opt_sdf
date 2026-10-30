#!/usr/bin/env python3
"""Supplemental, non-gating localization of the original baseline defect counts."""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from audit_xfid45_surface_export_round_2026_10_03 import (  # noqa: E402
    EVIDENCE,
    CASE_IDS,
    grid_cell_details,
    load_mesh,
    merge_exact_coordinates,
    sha256_file,
    source_cell_ids_by_triangle,
    structured_grid,
    topology,
    triangle_key,
    write_json,
)


def edge_entities(faces: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    rows: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for face_id, face in enumerate(np.asarray(faces, dtype=np.int64)):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (int(min(a, b)), int(max(a, b)))
            direction = 1 if (int(a), int(b)) == edge else -1
            rows[edge].append((face_id, direction))
    return rows


def serialize_merge_maps(
    rounded_mesh,
    original_stl_vertices: np.ndarray,
    original_ply_vertices: np.ndarray,
) -> tuple[
    dict[tuple[float, float, float], list[int]],
    dict[tuple[float, float, float], list[int]],
]:
    stl_groups: dict[tuple[float, float, float], list[int]] = defaultdict(list)
    ply_groups: dict[tuple[float, float, float], list[int]] = defaultdict(list)
    for vertex_id, point in enumerate(original_stl_vertices):
        stl_groups[tuple(np.round(point, decimals=8))].append(vertex_id)
    for vertex_id, point in enumerate(original_ply_vertices):
        ply_groups[tuple(np.round(point, decimals=8))].append(vertex_id)
    rounded_keys = [
        tuple(np.round(point, decimals=8)) for point in rounded_mesh.vertices
    ]
    if len(set(rounded_keys)) != len(rounded_keys):
        raise ValueError(
            "default trimesh merge left duplicate 8-decimal coordinate keys"
        )
    if set(rounded_keys) != set(stl_groups):
        raise ValueError(
            "rounded vertex groups do not match trimesh.merge_vertices output"
        )
    return stl_groups, ply_groups


def main() -> int:
    evidence = ROOT / "docs/evidence/xfid45_surface_export_round_2026_10_03"
    output = evidence / "diagnostics"
    output.mkdir(parents=True, exist_ok=True)
    criteria_path = (
        ROOT / "docs/evidence/xfid45_surface_export_round_2026_10_03_prereg.json"
    )
    result_path = evidence / "result.json"
    base = EVIDENCE / "surfaces/baseline"
    ply_path = base / "canonical_export/zero_surface.ply"
    stl_path = base / "design_candidate.stl"
    ply = load_mesh(ply_path)
    stl = load_mesh(stl_path)
    if len(ply.faces) != len(stl.faces) or any(
        triangle_key(ply.vertices[left]) != triangle_key(stl.vertices[right])
        for left, right in zip(ply.faces, stl.faces, strict=True)
    ):
        raise ValueError(
            "frozen PLY and STL triangle order differs; face lineage is ambiguous"
        )

    state = SDFDesignState.load(EVIDENCE / "canonical_state.npz")
    grid, surface = structured_grid(state)
    source_cells = source_cell_ids_by_triangle(ply, surface)
    exact_ply_vertices, exact_ply_faces = merge_exact_coordinates(ply)
    exact_topology = topology(exact_ply_vertices, exact_ply_faces)

    rounded = load_mesh(stl_path)
    stl_source_vertices = np.asarray(rounded.vertices).copy()
    rounded.merge_vertices()
    stl_groups, ply_groups = serialize_merge_maps(
        rounded, stl_source_vertices, np.asarray(ply.vertices)
    )
    rounded_topology = topology(np.asarray(rounded.vertices), np.asarray(rounded.faces))
    edge_rows = rounded_topology["edge_incidence"]
    winding_edges = [
        (edge, faces)
        for edge, faces in edge_rows.items()
        if len(faces) == 2 and faces[0][1] == faces[1][1]
    ]
    duplicate_groups = rounded_topology["face_key_groups"]
    defect_triangles: set[int] = set()
    zero_defect_triangles: set[int] = set()
    type_counts = Counter()
    type_zero_counts = Counter()
    mapping_path = output / "baseline_original_712_defects_to_grid.jsonl.gz"

    def face_record(face_id: int) -> dict[str, object]:
        face = np.asarray(ply.faces[face_id], dtype=np.int64)
        cell_id = source_cells[face_id]
        cell_info = grid_cell_details(grid, state, cell_id)
        points = np.asarray(ply.vertices)[face]
        exact_nodes = []
        for point in points:
            q = (
                np.asarray(point, dtype=np.float64) - np.asarray(state.origin_m)
            ) / state.spacing_m
            ijk = np.rint(q).astype(np.int64)
            if np.all(ijk >= 0) and np.all(ijk < np.asarray(state.shape)):
                grid_point = np.asarray(state.origin_m) + state.spacing_m * ijk
                if np.array_equal(
                    np.asarray(point, dtype="<f4"), np.asarray(grid_point, dtype="<f4")
                ):
                    exact_nodes.append(tuple(int(value) for value in ijk))
        zero_nodes = {
            tuple(node["ijk"])
            for node in cell_info["node_phi_values_and_exact_zero"]
            if node["exact_zero"]
        }
        zero_nodes.update(node for node in exact_nodes if state.phi[node] == 0.0)
        source_vertex_instance_ids = [
            np.flatnonzero(np.all(np.asarray(ply.vertices) == point, axis=1))
            .astype(int)
            .tolist()
            for point in points
        ]
        return {
            "source_triangle_id": int(face_id),
            "source_contouring_cell_id": int(cell_id),
            "triangle_area_m2": float(
                0.5
                * np.linalg.norm(
                    np.cross(
                        points[1].astype(np.float64) - points[0].astype(np.float64),
                        points[2].astype(np.float64) - points[0].astype(np.float64),
                    )
                )
            ),
            "triangle_vertex_coordinates_m": points.tolist(),
            "coincident_ply_vertex_instance_ids_per_corner": source_vertex_instance_ids,
            "source_cell": cell_info,
            "triangle_vertices_exactly_on_grid_nodes_ijk": [
                list(node) for node in exact_nodes
            ],
            "exact_zero_grid_nodes_involved_ijk": [
                list(node) for node in sorted(zero_nodes)
            ],
            "touches_exact_zero_grid_node": bool(zero_nodes),
        }

    def emit(
        stream, defect_type: str, defect_id: str, face_ids: list[int], edge=None
    ) -> None:
        faces = [face_record(int(face_id)) for face_id in face_ids]
        touched_zero = any(face["touches_exact_zero_grid_node"] for face in faces)
        type_counts[defect_type] += 1
        type_zero_counts[defect_type] += int(touched_zero)
        defect_triangles.update(face_ids)
        if touched_zero:
            zero_defect_triangles.update(face_ids)
        row = {
            "defect_type": defect_type,
            "defect_id": defect_id,
            "source_triangles": faces,
            "touches_exact_zero_grid_node": touched_zero,
        }
        if edge is not None:
            vertices = np.asarray(rounded.vertices)
            endpoints = []
            for vertex_id in edge:
                point = vertices[vertex_id]
                rounded_key = tuple(np.round(point, decimals=8))
                endpoints.append(
                    {
                        "rounded_merge_vertex_id": int(vertex_id),
                        "retained_source_coordinate_m": point.tolist(),
                        "rounded_coordinate_key_8dp": list(rounded_key),
                        "source_stl_vertex_instances": stl_groups[rounded_key],
                        "source_ply_vertex_instances_in_8dp_bin": ply_groups.get(
                            rounded_key, []
                        ),
                    }
                )
            row["coincident_edge_vertices"] = endpoints
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

    with gzip.open(mapping_path, "wt", encoding="utf-8", newline="\n") as stream:
        for edge, incident in sorted(edge_rows.items()):
            if len(incident) != 2:
                emit(
                    stream,
                    "prior_audit_edge_incidence_not_two",
                    f"rounded_edge:{edge[0]}:{edge[1]}",
                    [row[0] for row in incident],
                    edge,
                )
            elif incident[0][1] == incident[1][1]:
                emit(
                    stream,
                    "prior_audit_winding_conflict_edge",
                    f"rounded_edge:{edge[0]}:{edge[1]}",
                    [incident[0][0], incident[1][0]],
                    edge,
                )
        for key, face_ids in sorted(duplicate_groups.items()):
            for duplicate_id in face_ids[1:]:
                emit(
                    stream,
                    "prior_audit_duplicate_face",
                    f"face:{face_ids[0]}:{duplicate_id}",
                    [face_ids[0], duplicate_id],
                )

    exact_merged_faces = np.unique(
        np.asarray(ply.vertices), axis=0, return_inverse=True
    )[1][np.asarray(ply.faces, dtype=np.int64)]
    face_keys = np.sort(exact_merged_faces, axis=1)
    _, first_face_ids = np.unique(face_keys, axis=0, return_index=True)
    first_face_ids = np.sort(first_face_ids)
    unique_faces = exact_merged_faces[first_face_ids]
    repeated_indices = (
        (unique_faces[:, 0] == unique_faces[:, 1])
        | (unique_faces[:, 1] == unique_faces[:, 2])
        | (unique_faces[:, 2] == unique_faces[:, 0])
    )
    exact_vertices = np.unique(np.asarray(ply.vertices), axis=0)
    triangle_points = exact_vertices[unique_faces].astype(np.float64, copy=False)
    areas = 0.5 * np.linalg.norm(
        np.cross(
            triangle_points[:, 1] - triangle_points[:, 0],
            triangle_points[:, 2] - triangle_points[:, 0],
        ),
        axis=1,
    )
    zero_area_only = (areas == 0.0) & ~repeated_indices
    degenerate_indices = repeated_indices | (areas == 0.0)
    degenerate_path = (
        output / "baseline_exact_merge_degenerate_triangles_to_grid.jsonl.gz"
    )
    degenerate_zero_counts = Counter()
    degenerate_min_corner_abs_phi = []
    degenerate_triangle_grid_node_hits = 0
    collapsed_grid_nodes: set[tuple[int, int, int]] = set()
    degenerate_source_cells: set[int] = set()
    with gzip.open(degenerate_path, "wt", encoding="utf-8", newline="\n") as stream:
        for row_id, is_degenerate in enumerate(degenerate_indices):
            if not is_degenerate:
                continue
            source_triangle_id = int(first_face_ids[row_id])
            face = face_record(source_triangle_id)
            kind = (
                "repeated_index_after_exact_coordinate_merge"
                if repeated_indices[row_id]
                else "exact_zero_area_nonrepeated"
            )
            degenerate_zero_counts[kind] += int(face["touches_exact_zero_grid_node"])
            degenerate_source_cells.add(int(source_cells[source_triangle_id]))
            cell_values = [
                abs(float(node["phi"]))
                for node in face["source_cell"]["node_phi_values_and_exact_zero"]
            ]
            degenerate_min_corner_abs_phi.append(min(cell_values))
            grid_hits = [
                tuple(node)
                for node in face["triangle_vertices_exactly_on_grid_nodes_ijk"]
                if node is not None
            ]
            degenerate_triangle_grid_node_hits += int(bool(grid_hits))
            if len(grid_hits) == 3 and len(set(grid_hits)) == 1:
                collapsed_grid_nodes.add(grid_hits[0])
            stream.write(
                json.dumps(
                    {
                        "defect_type": kind,
                        "source_triangle_id": source_triangle_id,
                        "triangle_area_m2": float(areas[row_id]),
                        "exact_merged_vertex_indices": unique_faces[row_id]
                        .astype(int)
                        .tolist(),
                        **face,
                    },
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )

    residual_path = output / "baseline_candidate_residual_edges.jsonl.gz"
    baseline_case = json.loads(
        (evidence / "cases/baseline/case_audit.json").read_text()
    )
    kept_source_ids = baseline_case["canonicalization_audit"][
        "kept_source_triangle_ids"
    ]
    candidate = load_mesh(evidence / "cases/baseline/stage_v_candidate.stl")
    candidate_vertices, candidate_faces = merge_exact_coordinates(candidate)
    candidate_topology = topology(candidate_vertices, candidate_faces)
    residual_rows = []
    for edge, incident in sorted(candidate_topology["edge_incidence"].items()):
        if len(incident) == 2:
            continue
        mapped_face_ids = [int(kept_source_ids[row[0]]) for row in incident]
        residual_rows.append(
            {
                "candidate_edge_id": [int(edge[0]), int(edge[1])],
                "candidate_edge_vertex_coordinates_m": [
                    candidate_vertices[index].tolist() for index in edge
                ],
                "candidate_edge_incidence": len(incident),
                "source_triangles": [
                    face_record(face_id) for face_id in mapped_face_ids
                ],
            }
        )
    with gzip.open(residual_path, "wt", encoding="utf-8", newline="\n") as stream:
        for row in residual_rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

    orientation_conflict_path = (
        output / "perturbation_orientation_winding_conflicts.jsonl.gz"
    )
    perturbation_summaries = {}
    with gzip.open(
        orientation_conflict_path, "wt", encoding="utf-8", newline="\n"
    ) as stream:
        for case_id in CASE_IDS[1:]:
            case_dir = evidence / "cases" / case_id
            mesh = load_mesh(case_dir / "stage_v_candidate.stl")
            vertices, faces = merge_exact_coordinates(mesh)
            topo = topology(vertices, faces)
            conflicts = [
                (edge, rows)
                for edge, rows in topo["edge_incidence"].items()
                if len(rows) == 2 and rows[0][1] == rows[1][1]
            ]
            audit = json.loads((case_dir / "case_audit.json").read_text())
            flipped = set(
                audit["canonicalization_audit"]["flipped_face_ids_after_cleanup"]
            )
            orientation_by_id = {}
            orientation_path = case_dir / "raw_orientation.jsonl.gz"
            with gzip.open(
                orientation_path, "rt", encoding="utf-8"
            ) as orientation_stream:
                for line in orientation_stream:
                    record = json.loads(line)
                    orientation_by_id[record["source_triangle_id"]] = record
            for edge, rows in sorted(conflicts):
                face_details = []
                for face_id, direction in rows:
                    record = orientation_by_id[int(face_id)]
                    face_details.append(
                        {
                            "candidate_face_id": int(face_id),
                            "source_triangle_id": record["source_triangle_id"],
                            "source_contouring_cell_id": record[
                                "source_contouring_cell_id"
                            ],
                            "raw_normal_gradient_dot": record["normal_gradient_dot"],
                            "raw_dot_sign": record["dot_sign"],
                            "candidate_face_flipped": int(face_id) in flipped,
                            "candidate_edge_direction_sign": int(direction),
                            "triangle_vertices_m": record["triangle_vertices_m"],
                        }
                    )
                stream.write(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "winding_conflict_edge_id": [int(edge[0]), int(edge[1])],
                            "edge_vertex_coordinates_m": [
                                vertices[index].tolist() for index in edge
                            ],
                            "incident_faces": face_details,
                        },
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                )
            perturbation_summaries[case_id] = {
                "raw_normal_gradient_dot_sign_counts": audit["raw_orientation"][
                    "dot_sign_counts_before_orientation"
                ],
                "locally_oriented_face_count": len(flipped),
                "candidate_same_direction_two_face_edge_count": len(conflicts),
                "candidate_non_manifold_edge_count": topo[
                    "non_manifold_edge_count_incidence_not_two"
                ],
                "candidate_signed_volume_m3": topo["signed_volume_m3"],
            }

    baseline_ambiguous_ids = baseline_case["canonicalization_audit"][
        "ambiguous_face_ids_after_cleanup"
    ]
    ambiguous_source_ids = [
        int(kept_source_ids[index]) for index in baseline_ambiguous_ids
    ]
    summary = {
        "schema_version": 1,
        "kind": "xfid45_post_result_baseline_defect_metric_reconciliation",
        "evidence_class": "supplemental_solver_free_diagnostic_not_a_candidate_or_gate_change",
        "criteria_sha256": sha256_file(criteria_path),
        "registered_round_result_sha256": sha256_file(result_path),
        "diagnostic_source_sha256": sha256_file(Path(__file__)),
        "canonical_state_sha256": state.state_sha256,
        "exact_zero_node_count": int(np.count_nonzero(state.phi == 0.0)),
        "raw_mesh_metric_reconciliation": {
            "prior_preflight_contract": "Trimesh merge_vertices() default rounding (8 decimal places) before edge counting",
            "prior_audit_non_manifold_edge_count": int(
                len([1 for rows in edge_rows.values() if len(rows) != 2])
            ),
            "exact_coordinate_merge_non_manifold_edge_count": exact_topology[
                "non_manifold_edge_count_incidence_not_two"
            ],
            "prior_audit_rounded_merged_vertex_count": int(len(rounded.vertices)),
            "exact_merged_vertex_count_in_prior_STL": int(
                len(np.unique(stl_source_vertices, axis=0))
            ),
            "vertices_coalesced_only_by_8dp_audit_rounding": int(
                len(np.unique(stl_source_vertices, axis=0)) - len(rounded.vertices)
            ),
            "prior_audit_winding_conflict_edge_count": len(winding_edges),
            "exact_coordinate_merge_winding_conflict_edge_count": sum(
                1
                for rows in exact_topology["edge_incidence"].values()
                if len(rows) == 2 and rows[0][1] == rows[1][1]
            ),
            "duplicate_face_count": int(rounded_topology["duplicate_face_count"]),
            "candidate_sequence_exact_coordinate_only": True,
            "rounded_merge_used_only_to_reconcile_prior_audit_and_localize_defects": True,
        },
        "prior_712_edge_defect_localization": {
            "defect_entity_counts": dict(type_counts),
            "defect_entities_touching_any_exact_zero_grid_node": dict(type_zero_counts),
            "entity_count_total_categories_may_overlap": int(sum(type_counts.values())),
            "entity_zero_touch_percent_total_categories_may_overlap": 100.0
            * sum(type_zero_counts.values())
            / sum(type_counts.values()),
            "unique_source_triangles_involved": len(defect_triangles),
            "unique_source_triangles_touching_exact_zero": len(zero_defect_triangles),
            "source_triangle_zero_touch_percent": 100.0
            * len(zero_defect_triangles)
            / len(defect_triangles),
            "mapping_jsonl_gz": mapping_path.relative_to(ROOT).as_posix(),
            "mapping_sha256": sha256_file(mapping_path),
        },
        "exact_coordinate_merge_degenerate_triangle_localization": {
            "duplicate_faces_removed_before_this_classification": int(
                len(ply.faces) - len(first_face_ids)
            ),
            "repeated_index_triangle_count_removed": int(
                np.count_nonzero(repeated_indices)
            ),
            "exact_zero_area_nonrepeated_triangle_count_removed": int(
                np.count_nonzero(zero_area_only)
            ),
            "degenerate_triangles_touching_exact_zero_grid_node": dict(
                degenerate_zero_counts
            ),
            "degenerate_triangle_count_total": int(
                np.count_nonzero(degenerate_indices)
            ),
            "degenerate_triangle_count_with_any_vertex_exactly_on_grid_node": degenerate_triangle_grid_node_hits,
            "distinct_grid_nodes_where_all_three_triangle_vertices_coincide": len(
                collapsed_grid_nodes
            ),
            "distinct_contouring_source_cells_involved": len(degenerate_source_cells),
            "source_cell_minimum_absolute_corner_phi_quantiles": {
                str(percentile): float(
                    np.quantile(degenerate_min_corner_abs_phi, percentile)
                )
                for percentile in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
            },
            "near_zero_summary_is_descriptive_only_no_threshold_changes_iso_or_candidate_processing": True,
            "mapping_jsonl_gz": degenerate_path.relative_to(ROOT).as_posix(),
            "mapping_sha256": sha256_file(degenerate_path),
        },
        "exact_candidate_residual_baseline_edges": {
            "non_manifold_edge_count": len(residual_rows),
            "ambiguous_candidate_face_ids": baseline_ambiguous_ids,
            "ambiguous_source_triangle_ids": ambiguous_source_ids,
            "mapping_jsonl_gz": residual_path.relative_to(ROOT).as_posix(),
            "mapping_sha256": sha256_file(residual_path),
        },
        "local_gradient_vs_winding_conflicts": {
            "per_perturbation": perturbation_summaries,
            "edge_mapping_jsonl_gz": orientation_conflict_path.relative_to(
                ROOT
            ).as_posix(),
            "edge_mapping_sha256": sha256_file(orientation_conflict_path),
        },
        "solver_started": False,
        "formal_xfid_started": False,
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
    if (
        summary["raw_mesh_metric_reconciliation"]["prior_audit_non_manifold_edge_count"]
        != 712
    ):
        raise ValueError(
            "supplemental audit did not reproduce the frozen 712-edge count"
        )
    if len(residual_rows) != 12:
        raise ValueError(
            "supplemental audit did not reproduce the registered 12-edge residual"
        )
    summary_path = output / "baseline_defect_metric_reconciliation.json"
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "summary": summary_path.as_posix(),
                "reproduced_712_edges": 712,
                "candidate_residual_edges": len(residual_rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
