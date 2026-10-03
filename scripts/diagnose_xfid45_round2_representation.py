#!/usr/bin/env python3
"""Post-screen diagnostics on saved arrays only; no extractor or gate changes."""

import json
import gzip
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03"


def census(v, f):
    edges = np.sort(np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]])), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    area = (
        np.linalg.norm(
            np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1
        )
        / 2
    )
    return {
        "native_id_edge_incidence_not_two": int((counts != 2).sum()),
        "native_id_duplicate_faces": int(
            len(f) - len(np.unique(np.sort(f, axis=1), axis=0))
        ),
        "exact_zero_area_faces": int((area == 0).sum()),
        "minimum_positive_area_m2": float(area[area > 0].min())
        if (area > 0).any()
        else None,
    }


def localize_B_vertex_links(reg):
    z = np.load(OUT / "surfaces/B/baseline/surface.npz")
    vertices, inv = np.unique(z["vertices"], axis=0, return_inverse=True)
    faces = inv[z["faces"]]
    links = defaultdict(list)
    for a, b, c in faces:
        for u, x, y in ((a, b, c), (b, c, a), (c, a, b)):
            links[int(u)].append((int(x), int(y)))
    state = np.load(ROOT / reg["input_files"]["baseline"]["path"])
    meta = json.loads(str(state["metadata"]))
    origin = np.array(meta["origin_m"])
    h = meta["spacing_m"]
    phi = state["phi"]
    rows = []
    for vertex, pairs in links.items():
        graph = defaultdict(list)
        for a, b in pairs:
            graph[a].append(b)
            graph[b].append(a)
        todo = set(graph)
        groups = []
        while todo:
            group = set()
            stack = [min(todo)]
            while stack:
                node = stack.pop()
                if node in group:
                    continue
                group.add(node)
                stack.extend(graph[node])
            todo -= group
            groups.append(sorted(group))
        if len(groups) == 1 and all(
            len(neighbors) == 2 for neighbors in graph.values()
        ):
            continue
        point = vertices[vertex]
        cell = np.clip(
            np.floor((point - origin) / h).astype(int), 0, np.array(phi.shape) - 2
        )
        nodes = []
        for a in (0, 1):
            for b in (0, 1):
                for c in (0, 1):
                    ijk = cell + np.array([a, b, c])
                    value = float(phi[tuple(ijk)])
                    nodes.append(
                        {"ijk": ijk.tolist(), "phi_m": value, "exact_zero": value == 0}
                    )
        rows.append(
            {
                "vertex_index": vertex,
                "coordinate_m": point.tolist(),
                "face_ids": np.flatnonzero(np.any(faces == vertex, axis=1)).tolist(),
                "link_cycle_components": groups,
                "link_node_degrees": {
                    str(node): len(neighbors) for node, neighbors in graph.items()
                },
                "containing_halfopen_cell_ijk": cell.tolist(),
                "cell_nodes": nodes,
            }
        )
    (OUT / "baseline_B_vertex_link_localization.json").write_text(
        json.dumps(
            {
                "evidence_class": "post_screen_localization_not_gate_change",
                "vertices": rows,
            },
            indent=2,
        )
        + "\n"
    )


def main():
    reg = json.loads((OUT / "preregistration.json").read_text())
    localize_B_vertex_links(reg)
    result = json.loads((OUT / "result.json").read_text())
    rows = []
    for row in result["cases"]:
        name = row["candidate"]
        case = row["case"]
        z = np.load(OUT / "surfaces" / name / case / "surface.npz")
        v = z["vertices"]
        f = z["faces"]
        uv, inv, counts = np.unique(v, axis=0, return_inverse=True, return_counts=True)
        v32 = np.asarray(v, dtype=np.float32).astype(float)
        u32, inv32, count32 = np.unique(
            v32, axis=0, return_inverse=True, return_counts=True
        )
        phi = np.load(ROOT / reg["input_files"][case]["path"])["phi"]
        record = {
            "candidate": name,
            "case": case,
            "grid_exact_zero_node_count": int((phi == 0).sum()),
            "native_vertex_ids": len(v),
            "unique_double_coordinates": len(uv),
            "unique_float32_coordinates": len(u32),
            "double_coincident_coordinate_sets": int((counts > 1).sum()),
            "float32_coincident_coordinate_sets": int((count32 > 1).sum()),
            "native_id_census": census(v, f),
            "exact_double_merge_census": census(uv, inv[f]),
            "float32_merge_census": census(u32, inv32[f]),
            "native_to_STL_coordinate_rounding_maximum_m": float(
                np.linalg.norm(v - v32, axis=1).max()
            ),
            "identity_lower_proves_disagreement": row["identity"][
                "certified_exceeds_limit"
            ],
            "identity_witness_upper_m": row["identity"][
                "maximum_certified_upper_distance_m"
            ],
            "identity_global_lipschitz_lower_m": row["identity"][
                "maximum_lipschitz_lower_distance_m"
            ],
        }
        if name == "C":
            audit_path = (
                OUT / "surfaces" / name / case / "extraction_orientation_audit.json"
            )
            audit = json.loads(
                audit_path.read_text()
                if audit_path.exists()
                else gzip.decompress(audit_path.with_suffix(".json.gz").read_bytes())
            )
            keys = np.array(
                audit["extractor"]["vertex_source_edge_keys_global_c_order"]
            )
            record["unique_combinatorial_edge_keys"] = len(np.unique(keys, axis=0))
            record["coordinate_collision_edge_ids_example"] = [
                {"coordinate_m": uv[i].tolist(), "edge_keys": keys[inv == i].tolist()}
                for i in np.flatnonzero(counts > 1)[:8]
            ]
        rows.append(record)
    report = {
        "evidence_class": "post_screen_saved_array_diagnostic_not_new_candidate_or_qualification",
        "source_arrays_modified": False,
        "gate_or_threshold_changed": False,
        "no_extractor_import": True,
        "cases": rows,
    }
    (OUT / "representation_diagnostics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
