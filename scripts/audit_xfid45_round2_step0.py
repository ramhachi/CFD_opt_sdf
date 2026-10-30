#!/usr/bin/env python3
"""Diagnostic-only precursor to round 2; no A/B/C target extraction."""

import gzip
import hashlib
import json
from itertools import product
from pathlib import Path
import numpy as np
import trimesh
from xfid45_round2_metrics import CASES, load_field, gradient, sidedness

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "docs/evidence/xfid01_geometry_preflight_2026_10_03"
OUT = ROOT / "docs/evidence/xfid45_surface_round2_2026_10_03"


def path(case):
    return OLD / (
        "canonical_state.npz" if case == "baseline" else f"state_snapshots/{case}.npz"
    )


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def volume(phi, o, h, n):
    # Fixed midpoint quadrature only in cells straddling zero; all other cells exact.
    corners = np.stack(
        [
            phi[
                i : phi.shape[0] - 1 + i,
                j : phi.shape[1] - 1 + j,
                k : phi.shape[2] - 1 + k,
            ]
            for i, j, k in product((0, 1), repeat=3)
        ],
        axis=-1,
    )
    lo = corners.min(-1)
    hi = corners.max(-1)
    active = np.argwhere((lo <= 0) & (hi >= 0))
    total = float((hi < 0).sum())
    uv = np.array(list(product((np.arange(n) + 0.5) / n, repeat=2)))
    weights = np.stack(
        [
            (uv[:, 0] if a else 1 - uv[:, 0]) * (uv[:, 1] if b else 1 - uv[:, 1])
            for a, b in product((0, 1), repeat=2)
        ],
        axis=1,
    )
    for chunk in np.array_split(active, max(1, int(np.ceil(len(active) / 128)))):
        if not len(chunk):
            continue
        values = corners[tuple(chunk.T)].astype(float)
        bottom = values[:, [0, 2, 4, 6]] @ weights.T
        top = values[:, [1, 3, 5, 7]] @ weights.T
        frac = np.zeros_like(bottom)
        frac[(bottom < 0) & (top < 0)] = 1
        crossing = (bottom < 0) != (top < 0)
        root = np.divide(
            bottom, bottom - top, out=np.zeros_like(bottom), where=bottom != top
        )
        frac[crossing] = np.where(bottom < 0, root, 1 - root)[crossing]
        total += float(frac.sum()) / n**2
    return total * h**3


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    diagnostic = {
        "evidence_class": "solver_free_diagnostic_not_qualification",
        "thresholds_selected_from_observations": False,
        "delta_over_h": [0.02, 0.05, 0.1],
        "orientation_area_majority_rule_fixed_before_observation": "> 0.5 at every delta, same polarity",
        "cases": {},
    }
    for case in CASES[1:]:
        phi, o, h = load_field(path(case))
        mesh = trimesh.load_mesh(
            OLD / f"surfaces/{case}/canonical_export/zero_surface.ply", process=False
        )
        diagnostic["cases"][case] = sidedness(
            np.asarray(mesh.vertices), np.asarray(mesh.faces), phi, o, h
        )
    residual = (
        ROOT
        / "docs/evidence/xfid45_surface_export_round_2026_10_03/diagnostics/baseline_candidate_residual_edges.jsonl.gz"
    )
    rows = [json.loads(line) for line in gzip.open(residual, "rt")]
    near = 0.025 * np.finfo(np.float32).eps
    for row in rows:
        cells = [t["source_cell"] for t in row["source_triangles"]]
        row["has_exact_zero_source_cell"] = any(
            c["contains_exact_zero_grid_node"] for c in cells
        )
        row["has_near_zero_source_cell"] = any(
            abs(n["phi"]) <= near
            for c in cells
            for n in c["node_phi_values_and_exact_zero"]
        )
        row["minimum_abs_source_node_phi_m"] = min(
            abs(n["phi"]) for c in cells for n in c["node_phi_values_and_exact_zero"]
        )
    dump(
        OUT / "baseline_residual12_localization.json",
        {
            "near_zero_threshold_m": float(near),
            "definition": "h times float32 machine epsilon; fixed analytically",
            "source_sha256": hashlib.sha256(residual.read_bytes()).hexdigest(),
            "edge_count": len(rows),
            "exact_zero_cell_touch_count": sum(
                r["has_exact_zero_source_cell"] for r in rows
            ),
            "near_zero_cell_touch_count": sum(
                r["has_near_zero_source_cell"] for r in rows
            ),
            "edges": rows,
        },
    )
    phi, o, h = load_field(path("baseline"))
    mesh = trimesh.load_mesh(
        OLD / "surfaces/baseline/canonical_export/zero_surface.ply", process=False
    )
    v, inv = np.unique(mesh.vertices, axis=0, return_inverse=True)
    f = inv[mesh.faces]
    _, unique = np.unique(np.sort(f, axis=1), axis=0, return_index=True)
    f = f[np.sort(unique)]
    p = v[f]
    area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) / 2
    active = area > 0
    area = area[active]
    c = p[active].mean(1)
    g = np.linalg.norm(gradient(phi, o, h, c), axis=1)
    vol = {
        "epsilon_m": 0.005,
        "area_m2": float(area.sum()),
        "two_epsilon_area_m3": float(0.01 * area.sum()),
        "two_epsilon_integral_inverse_gradient_m3": float(
            0.01 * np.sum(area[g > 0] / g[g > 0])
        ),
        "zero_gradient_positive_area_faces": int((g == 0).sum()),
        "quadrature_method": "fixed xy midpoint quadrature with exact linear-z sublevel fraction in each cell; not exact xy integral",
        "quadrature": {},
    }
    minus, _, _ = load_field(path(CASES[1]))
    plus, _, _ = load_field(path(CASES[2]))
    for n in (4, 8, 16, 32, 64):
        shifted_minus = volume(phi - 0.005, o, h, n)
        shifted_plus = volume(phi + 0.005, o, h, n)
        stored_minus = volume(minus, o, h, n)
        stored_plus = volume(plus, o, h, n)
        vol["quadrature"][str(n)] = {
            "global_phi_minus_epsilon_volume_m3": shifted_minus,
            "global_phi_plus_epsilon_volume_m3": shifted_plus,
            "global_threshold_volume_difference_m3": shifted_minus - shifted_plus,
            "frozen_D0_minus_volume_m3": stored_minus,
            "frozen_D0_plus_volume_m3": stored_plus,
            "frozen_D0_volume_difference_m3": stored_minus - stored_plus,
        }
    volumes = []
    for case in CASES[1:3]:
        m = trimesh.load_mesh(
            OLD / f"surfaces/{case}/canonical_export/zero_surface.ply", process=False
        )
        m.merge_vertices(digits_vertex=15)
        volumes.append(float(m.volume))
    vol["raw_mesh_signed_volumes_m3"] = volumes
    vol["raw_mesh_unsigned_volume_difference_m3"] = abs(volumes[0]) - abs(volumes[1])
    vol["snapshot_global_shift_disagreement_node_counts"] = [
        int(np.count_nonzero(minus != phi - 0.005)),
        int(np.count_nonzero(plus != phi + 0.005)),
    ]
    diagnostic["D0_volume_comparison"] = vol
    dump(OUT / "step0.json", diagnostic)
    # Held-outs generated without extracting or sampling their surfaces.
    held = OUT / "heldout"
    held.mkdir(exist_ok=True)
    d1 = (load_field(path(CASES[4]))[0] - load_field(path(CASES[3]))[0]) / 0.01
    d2 = (load_field(path(CASES[6]))[0] - load_field(path(CASES[5]))[0]) / 0.01
    direction = d1 + d2
    direction /= np.abs(direction).max()
    for sign in (-1, 1):
        target = (phi + sign * 0.005 * direction).astype(np.float32)
        np.savez_compressed(
            held / f"H_combined_{'minus' if sign < 0 else 'plus'}.npz",
            phi=target,
            metadata=json.dumps(
                {
                    "origin_m": o.tolist(),
                    "spacing_m": h,
                    "kind": "heldout_frozen_direction_combination",
                    "formula": "(D1+D2)/max_abs(D1+D2)",
                    "epsilon_m": 0.005,
                    "sign": sign,
                }
            ),
        )
    xyz = np.stack(
        np.meshgrid(
            *(o[a] + h * np.arange(phi.shape[a]) for a in range(3)), indexing="ij"
        ),
        axis=-1,
    )
    r = np.linalg.norm(xyz - [0.071, 0.033, 0.019], axis=-1)
    np.savez_compressed(
        held / "H_analytic_shell.npz",
        phi=np.maximum(r - 0.275, 0.13 - r).astype(np.float32),
        metadata=json.dumps(
            {
                "origin_m": o.tolist(),
                "spacing_m": h,
                "kind": "analytic_heldout_shell",
                "center_m": [0.071, 0.033, 0.019],
                "inner_radius_m": 0.13,
                "outer_radius_m": 0.275,
            }
        ),
    )
    print(
        json.dumps(
            {
                "diagnostic_cases": len(diagnostic["cases"]),
                "residual_edges": len(rows),
                "exact_zero_touch": sum(r["has_exact_zero_source_cell"] for r in rows),
                "volume": vol,
                "heldout_count": 3,
            }
        )
    )


if __name__ == "__main__":
    main()
