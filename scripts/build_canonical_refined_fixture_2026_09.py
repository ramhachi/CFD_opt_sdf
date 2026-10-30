"""Build the refined canonical fixture (voxel 0.025) for the PQ1.1 factor (2026-09-22).

The source grid stays fixed; only the canonical design parameterization is
refined (0.05 -> 0.025, each axis doubled). The coarse canonical state is
upsampled 2x per axis (exact integer refinement of the same domain), the masks
and spec are regenerated, and a candidate binding is produced. This is the
input for the canonical-grid FD campaign that isolates the parameterization
effect on the FD/adjoint ratio.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.canonical_geometry_masks import build_canonical_geometry_mask_snapshot  # noqa: E402
from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _read_cell_vti, _write_cell_vti  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256, write_problem_spec_snapshot  # noqa: E402

SOURCE = ROOT / "work" / "p0_closed_loop"
TARGET = ROOT / "work" / "pq1_canonical_refined"
FINE_VOXEL = 0.025


def main() -> None:
    if TARGET.exists():
        raise SystemExit(f"{TARGET} already exists; refusing to rebuild")
    TARGET.mkdir(parents=True)

    # 1. refined spec (same domain, voxel 0.025)
    spec_document = yaml.safe_load((SOURCE / "project.yaml").read_text(encoding="utf-8"))
    spec_document["grid"]["voxel_size_m"] = FINE_VOXEL
    (TARGET / "project.yaml").write_text(
        yaml.safe_dump(spec_document, sort_keys=False), encoding="utf-8"
    )
    shutil.copytree(SOURCE / "geometry", TARGET / "geometry")
    spec = load_problem_spec(TARGET / "project.yaml")
    write_problem_spec_snapshot(spec, TARGET / "problem_spec_snapshot.json")

    # 2. canonical mask snapshot + verification
    artifacts = build_canonical_geometry_mask_snapshot(spec, output_dir=TARGET)
    verified = load_and_verify_canonical_grid_snapshot(
        artifacts.snapshot_path, spec
    )
    coarse_grid, coarse_arrays = _read_cell_vti(
        SOURCE / "density.vti", expected_kind="fixed_grid_density"
    )
    coarse_shape = tuple(coarse_grid.cell_shape)
    fine_shape = tuple(verified.snapshot.grid.cell_shape)
    if tuple(fine_shape) != tuple(2 * v for v in coarse_shape):
        raise SystemExit(f"unexpected fine shape {fine_shape} for coarse {coarse_shape}")

    # 3. upsample the canonical state 2x per axis (x-fastest flat arrays)
    def upsample(values: np.ndarray, dtype) -> np.ndarray:
        arr = np.asarray(values).reshape(coarse_shape, order="F")
        arr = np.repeat(np.repeat(np.repeat(arr, 2, axis=0), 2, axis=1), 2, axis=2)
        return arr.ravel(order="F").astype(dtype)

    fine_grid = CartesianCellGrid(
        origin=tuple(verified.snapshot.grid.origin),
        spacing=tuple(verified.snapshot.grid.spacing),
        cell_shape=fine_shape,
    )
    fine_arrays = {
        name: upsample(coarse_arrays[name], coarse_arrays[name].dtype)
        for name in coarse_arrays
    }
    # role masks come from the regenerated snapshot, not the coarse upsample
    for mask_id, values in verified.masks.items():
        fine_arrays[mask_id] = np.asarray(values, dtype=np.uint8)
    _write_cell_vti(fine_grid, fine_arrays, TARGET / "density.vti", kind="fixed_grid_density")

    # 4. refined canonical topology state
    state = json.loads((SOURCE / "topology_state.json").read_text(encoding="utf-8"))
    state["grid"] = {
        "location": "cell",
        "cell_order": "vtk-x-fastest",
        "origin": list(verified.snapshot.grid.origin),
        "spacing": list(verified.snapshot.grid.spacing),
        "cell_shape": list(fine_shape),
        "point_dimensions": [v + 1 for v in fine_shape],
        "cell_count": int(np.prod(fine_shape)),
        "bounds": (
            verified.snapshot.to_dict()["grid"]["bounds"]
            if hasattr(verified.snapshot, "to_dict")
            else [[
                verified.snapshot.grid.origin[i],
                verified.snapshot.grid.origin[i] + fine_shape[i] * verified.snapshot.grid.spacing[i],
            ] for i in range(3)]
        ),
    }
    state["problem_spec_sha256"] = problem_spec_sha256(spec)
    state["candidate_id"] = "p0_closed_loop_canonical_refined_0025"
    state["provenance"] = dict(
        state.get("provenance", {}),
        resample_method="exact_2x_block_upsample_of_the_coarse_canonical_state",
        generated_by="scripts/build_canonical_refined_fixture_2026_09.py",
    )
    density_vti = TARGET / "density.vti"
    state["density_vti"] = density_vti.name
    (TARGET / "topology_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(json.dumps({
        "fine_shape": list(fine_shape),
        "fine_cells": int(np.prod(fine_shape)),
        "snapshot": str(artifacts.snapshot_path),
        "density_vti": str(density_vti),
        "spec": str(TARGET / "project.yaml"),
    }, indent=2))


if __name__ == "__main__":
    main()
