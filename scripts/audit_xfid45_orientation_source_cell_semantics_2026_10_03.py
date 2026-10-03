#!/usr/bin/env python3
"""Check whether source-cell versus half-open-cell gradients change #45 dots."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.design.sdf_state import SDFDesignState  # noqa: E402
from audit_xfid45_surface_export_round_2026_10_03 import (  # noqa: E402
    CASE_IDS as ALL_CASE_IDS,
    EVIDENCE,
    load_mesh,
    sha256_file,
    source_cell_ids_by_triangle,
    structured_grid,
    trilinear_gradient,
)

ROUND_OFF_FACTOR = 64.0
CASE_IDS = ALL_CASE_IDS[1:]


def in_cell_gradient(
    phi: np.ndarray,
    origin_m: tuple[float, float, float],
    spacing_m: float,
    point_m: np.ndarray,
    cell: tuple[int, int, int],
) -> np.ndarray:
    q = (np.asarray(point_m, dtype=np.float64) - np.asarray(origin_m)) / spacing_m
    t = q - np.asarray(cell, dtype=np.float64)
    i, j, k = cell
    corners = np.asarray(
        [phi[i + a, j + b, k + c] for a in (0, 1) for b in (0, 1) for c in (0, 1)],
        dtype=np.float64,
    ).reshape(2, 2, 2)
    gradient = np.zeros(3, dtype=np.float64)
    for b in (0, 1):
        wb = t[1] if b else 1.0 - t[1]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            gradient[0] += (corners[1, b, c] - corners[0, b, c]) * wb * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for c in (0, 1):
            wc = t[2] if c else 1.0 - t[2]
            gradient[1] += (corners[a, 1, c] - corners[a, 0, c]) * wa * wc
    for a in (0, 1):
        wa = t[0] if a else 1.0 - t[0]
        for b in (0, 1):
            wb = t[1] if b else 1.0 - t[1]
            gradient[2] += (corners[a, b, 1] - corners[a, b, 0]) * wa * wb
    return gradient / spacing_m


def classify(dot: float, gradient: np.ndarray) -> str:
    tolerance = (
        ROUND_OFF_FACTOR
        * np.finfo(np.float64).eps
        * max(1.0, float(np.linalg.norm(gradient)))
    )
    return (
        "positive"
        if dot > tolerance
        else "negative"
        if dot < -tolerance
        else "ambiguous"
    )


def edge_connected_face_components(faces: np.ndarray) -> list[list[int]]:
    parent = np.arange(len(faces), dtype=np.int64)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    def union(first: int, second: int) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    edge_owner: dict[tuple[int, int], int] = {}
    for face_id, face in enumerate(faces):
        for first, second in (
            (face[0], face[1]),
            (face[1], face[2]),
            (face[2], face[0]),
        ):
            edge = tuple(sorted((int(first), int(second))))
            if edge in edge_owner:
                union(face_id, edge_owner[edge])
            else:
                edge_owner[edge] = face_id

    components: dict[int, list[int]] = {}
    for face_id in range(len(faces)):
        components.setdefault(find(face_id), []).append(face_id)
    return [components[root] for root in sorted(components)]


def main() -> int:
    evidence = ROOT / "docs/evidence/xfid45_surface_export_round_2026_10_03"
    rows = {}
    for case_id in CASE_IDS:
        state_path = EVIDENCE / "state_snapshots" / f"{case_id}.npz"
        raw_ply = EVIDENCE / "surfaces" / case_id / "canonical_export/zero_surface.ply"
        state = SDFDesignState.load(state_path)
        grid, surface = structured_grid(state)
        mesh = load_mesh(raw_ply)
        source_cells = source_cell_ids_by_triangle(mesh, surface)
        counts_half_open = {key: 0 for key in ("positive", "negative", "ambiguous")}
        counts_source_cell = dict(counts_half_open)
        half_open_labels = []
        changed_ids = []
        for triangle_id, (face, source_cell_id) in enumerate(
            zip(mesh.faces, source_cells, strict=True)
        ):
            points = np.asarray(mesh.vertices)[face].astype(np.float64, copy=False)
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            normal /= np.linalg.norm(normal)
            centroid = points.mean(axis=0)
            gradient_half, cell_half, _ = trilinear_gradient(
                state.phi, state.origin_m, state.spacing_m, centroid
            )
            half_label = classify(float(normal @ gradient_half), gradient_half)
            counts_half_open[half_label] += 1
            half_open_labels.append(half_label)

            cell = grid.GetCell(int(source_cell_id))
            point_ijk = [
                np.unravel_index(int(cell.GetPointId(local_id)), state.shape, order="F")
                for local_id in range(cell.GetNumberOfPoints())
            ]
            source_cell = tuple(
                min(int(index[axis]) for index in point_ijk) for axis in range(3)
            )
            gradient_source = in_cell_gradient(
                state.phi,
                state.origin_m,
                state.spacing_m,
                centroid,
                source_cell,
            )
            source_label = classify(float(normal @ gradient_source), gradient_source)
            counts_source_cell[source_label] += 1
            if source_label != half_label:
                changed_ids.append(triangle_id)
        _, exact_vertex_ids = np.unique(
            np.asarray(mesh.vertices), axis=0, return_inverse=True
        )
        exact_faces = exact_vertex_ids[np.asarray(mesh.faces)]
        component_rows = []
        for component_id, face_ids in enumerate(
            edge_connected_face_components(exact_faces)
        ):
            labels = [half_open_labels[face_id] for face_id in face_ids]
            counts = {
                key: labels.count(key) for key in ("positive", "negative", "ambiguous")
            }
            component_rows.append(
                {
                    "component_id": component_id,
                    "face_count": len(face_ids),
                    "dot_sign_counts": counts,
                    "one_component_flip_can_align_every_resolvable_face": not (
                        counts["positive"] and counts["negative"]
                    ),
                }
            )
        rows[case_id] = {
            "raw_ply_sha256": sha256_file(raw_ply),
            "state_snapshot_sha256": sha256_file(state_path),
            "triangle_count": len(mesh.faces),
            "half_open_cell_dot_sign_counts": counts_half_open,
            "contouring_source_cell_dot_sign_counts": counts_source_cell,
            "face_classification_changed_count": len(changed_ids),
            "changed_source_triangle_ids": changed_ids,
            "all_source_cell_indices_valid": True,
            "exact_coordinate_edge_connected_component_count": len(component_rows),
            "component_orientation_audit": component_rows,
            "whole_component_orientation_satisfies_all_faces": all(
                row["one_component_flip_can_align_every_resolvable_face"]
                for row in component_rows
            ),
        }

    payload = {
        "schema_version": 1,
        "kind": "xfid45_orientation_cell_semantics_diagnostic",
        "evidence_class": "post_result_solver_free_orientation_diagnostic_only",
        "criteria_sha256": sha256_file(
            ROOT / "docs/evidence/xfid45_surface_export_round_2026_10_03_prereg.json"
        ),
        "registered_candidate_result_sha256": sha256_file(evidence / "result.json"),
        "diagnostic_source_sha256": sha256_file(Path(__file__)),
        "interpretation": "The contouring source-cell local trilinear gradient is compared with the preregistered half-open-cell gradient; no orientation or surface is changed.",
        "cases": rows,
        "source_cell_choice_changes_no_face_classification": all(
            row["face_classification_changed_count"] == 0 for row in rows.values()
        ),
        "solver_started": False,
        "formal_xfid_started": False,
    }
    output = evidence / "diagnostics/orientation_source_cell_semantics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "no_face_classification_changes": payload[
                    "source_cell_choice_changes_no_face_classification"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
