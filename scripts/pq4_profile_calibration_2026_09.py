"""Calibrate the extraction surface-distance profile on analytic ground truth (PQ4).

The v1 profile thresholds (max 0.05 m, RMS 0.025 m) were registered before this
measurement. This script measures the metric floor on analytic binary shapes
whose exact voxel occupancy is known: the handoff contours the binary field at
0.5, and the qualification surface distance then reports how far the
marching-cubes surface sits from the voxel material it was contoured from. The
result informs a separate, registered profile decision; it does not change the
v1 profile.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.analytic_candidate_shapes import (  # noqa: E402
    CANONICAL_ORIGIN,
    CANONICAL_SHAPE,
    CANONICAL_SPACING,
    build_shape,
    reachable_set_definitions,
    shape_definitions,
)
from cfd_sdf.extraction_qualification import qualify_extraction  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti  # noqa: E402
from cfd_sdf.handoff import build_density_to_sdf_handoff  # noqa: E402

OUT = ROOT / "work" / "pq4_profile_calibration"
EVIDENCE = ROOT / "docs/evidence/pq4_profile_calibration_2026_09.json"
SHAPES = ("box_bluff03", "plate_a20_nd", "wing_camber_bent", "wing_two_element")


def _write_binary_state(directory: Path, occupancy: np.ndarray) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=CANONICAL_ORIGIN,
        spacing=(CANONICAL_SPACING,) * 3,
        cell_shape=CANONICAL_SHAPE,
    )
    count = grid.cell_count
    values = np.asarray(occupancy, dtype=np.float32).reshape(count, order="F")
    arrays = {
        "rho": values,
        "rho_filtered": values.copy(),
        "rho_projected": values.copy(),
        "alpha": values.copy(),
        "allowed_mask": np.ones(count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.zeros(count, dtype=np.uint8),
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(grid, arrays, directory / "density.vti", kind="fixed_grid_density")
    state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "density_array": "rho",
        "source_solver": {"backend": "analytic"},
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    definitions = {**shape_definitions(), **reachable_set_definitions()}
    rows = []
    for shape_id in SHAPES:
        definition = definitions[shape_id]
        shape = build_shape(definition)
        state = _write_binary_state(OUT / shape_id, shape.occupancy)
        artifacts = build_density_to_sdf_handoff(
            state, output_dir=OUT / shape_id / "handoff", iso_value=0.5
        )
        qualification = qualify_extraction(
            artifacts.manifest_json, mesh_path=artifacts.surface_stl
        )
        surface = qualification.checks["surface_distance"]
        feature = qualification.checks["feature_survival"]
        rows.append(
            {
                "shape_id": shape_id,
                "surface_distance_max_m": surface.get("max_m"),
                "surface_distance_rms_m": surface.get("rms_m"),
                "surface_distance_cells": (
                    surface.get("max_m") / CANONICAL_SPACING
                    if surface.get("max_m") is not None
                    else None
                ),
                "feature_shrink_voxels": feature.get("shrink_voxels"),
                "ready_for_stage_s_v1": qualification.ready_for_stage_s,
                "reasons": qualification.reasons,
                "watertight": qualification.checks["mesh_manifold"]["watertight"],
            }
        )
        print(json.dumps(rows[-1]))

    maxima = [row["surface_distance_max_m"] for row in rows]
    rms = [row["surface_distance_rms_m"] for row in rows]
    evidence = {
        "artifact_id": "pq4_profile_calibration_2026_09",
        "evidence_class": "numerical_metric_calibration",
        "issue": "PQ4 extraction profile v1 calibration on analytic ground truth",
        "profile_registered_before_this_measurement": {
            "profile_id": "extraction_qualification_v1",
            "surface_distance_max_m": 0.05,
            "surface_distance_rms_max_m": 0.025,
        },
        "method": "binary analytic occupancy -> handoff at 0.5 -> qualification surface distance",
        "rows": rows,
        "metric_floor": {
            "max_of_max_m": max(maxima),
            "max_of_rms_m": max(rms),
            "voxel_m": CANONICAL_SPACING,
        },
        "findings": [
            "the metric reports the marching-cubes-vs-voxel-material deviation for a perfect binary field",
            "the v1 max threshold equals one voxel; shapes whose contour deviates by more than one voxel fail",
        ],
        "decision": (
            "no threshold change here; if a registered profile v2 is needed, it must be "
            "justified by this calibration and registered before the next candidate verdict"
        ),
        "claims_not_supported": ["no candidate verdict is changed by this calibration"],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("wrote", EVIDENCE)


if __name__ == "__main__":
    main()
