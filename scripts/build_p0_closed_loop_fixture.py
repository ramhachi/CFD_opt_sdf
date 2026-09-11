#!/usr/bin/env python3
"""Build the P0 canonical <-> OpenFOAM closed-loop fixture under work/p0_closed_loop/.

Pairs a synthetic canonical-grid Stage T fixture with the *real, converged*
OpenFOAM case at work/architecture_effectiveness_20260910/{t1_contract,stage_t_base}.
The canonical grid (60x32x24, voxel 0.05 m) is declared to exactly cover the
same domain as that case's blockMesh (32x16x16), so the exact-overlap
transfer operator's coverage precondition holds.

Re-run with --overwrite to rebuild; otherwise refuses to clobber existing
output (work/ is gitignored - nothing here is meant to be committed).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from cfd_sdf.canonical_geometry_masks import build_canonical_geometry_mask_snapshot  # noqa: E402
from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot  # noqa: E402
from cfd_sdf.fixed_grid_contract import (  # noqa: E402
    DENSITY_ARRAYS,
    CartesianCellGrid,
    _density_array_metadata,
    _write_cell_vti,
)
from cfd_sdf.fixed_grid_primal import load_fixed_grid_density_state  # noqa: E402
from cfd_sdf.problem_spec import (  # noqa: E402
    canonical_uniform_cartesian_cell_grid,
    load_problem_spec,
    problem_spec_sha256,
    write_problem_spec_snapshot,
)

SOURCE_CONTRACT = REPO_ROOT / "work/architecture_effectiveness_20260910/t1_contract/topology_state.json"
OUTPUT_DIR = REPO_ROOT / "work/p0_closed_loop"
CFD_SDF = REPO_ROOT / ".venv/bin/cfd-sdf"
CANDIDATE_ID = "p0_closed_loop_candidate_0000"

# Domain shared with the real OpenFOAM blockMeshDict: x in [-1,2], y in
# [-0.8,0.8], z in [-0.6,0.6] -> 60x32x24 cells at 0.05 m voxels.
DOMAIN_LOWER = (-1.0, -0.8, -0.6)
DOMAIN_UPPER = (2.0, 0.8, 0.6)
VOXEL = 0.05


def run(cmd: list[str]) -> str:
    print("+", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}")
    return result.stdout


def design_domain_box_from_source_mask() -> tuple[np.ndarray, np.ndarray]:
    """Bounding box of the true active_design_mask cells in the source contract."""
    state = load_fixed_grid_density_state(SOURCE_CONTRACT)
    grid = state.grid
    mask = np.asarray(state.arrays["active_design_mask"], dtype=bool)
    nx, ny, _ = grid.cell_shape
    idx = np.flatnonzero(mask)
    ix = idx % nx
    iy = (idx // nx) % ny
    iz = idx // (nx * ny)
    origin = np.asarray(grid.origin)
    spacing = np.asarray(grid.spacing)
    lower = origin + np.array([ix.min(), iy.min(), iz.min()]) * spacing
    upper = origin + (np.array([ix.max(), iy.max(), iz.max()]) + 1) * spacing
    # Offset every face by a quarter canonical voxel so no face can land on a
    # canonical cell-centre plane (build_canonical_geometry_mask_snapshot
    # refuses ambiguous surface-touching cell centres).
    pad = VOXEL / 4.0
    return lower - pad, upper + pad


def write_box_stl(path: Path, lower: np.ndarray, upper: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extents = upper - lower
    center = (upper + lower) / 2.0
    mesh = trimesh.creation.box(
        extents=tuple(extents),
        transform=trimesh.transformations.translation_matrix(tuple(center)),
    )
    mesh.export(path)


def write_project_yaml(path: Path, lower: np.ndarray, upper: np.ndarray) -> None:
    import yaml

    project = {
        "schema_version": 2,
        "problem_id": "p0_closed_loop_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": VOXEL,
            "padding_m": 0.0,
            "domain_bounds_m": {
                "lower": list(DOMAIN_LOWER),
                "upper": list(DOMAIN_UPPER),
            },
        },
        "reference_values": {
            "area_m2": 1.2,
            "length_m": 0.8,
            "moment_center_m": [0.25, 0.0, 0.0],
        },
        "geometry_regions": [
            {"id": "design_domain", "role": "design_domain", "file": "geometry/design_domain.stl"},
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [30.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {
                    "inlet": "freestream",
                    "outlet": "pressure_outlet",
                },
                "motion_profiles": {},
            }
        ],
        "responses": [
            {
                "id": "drag",
                "kind": "force",
                "flow_case_id": "straight",
                "direction": [1.0, 0.0, 0.0],
            }
        ],
        "objectives": [
            {
                "id": "minimize_drag",
                "sense": "minimize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "drag"}],
            }
        ],
        "constraints": [],
        "topology_policy": {
            "root_groups": [],
            "solid_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
        },
    }
    path.write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")


def sample_nearest(
    canonical_grid,
    source_grid: CartesianCellGrid,
    source_values: np.ndarray,
) -> np.ndarray:
    """Nearest-neighbour sample source_values onto canonical cell centres."""
    nx, ny, nz = canonical_grid.cell_shape
    idx = np.arange(canonical_grid.cell_count)
    cx = idx % nx
    cy = (idx // nx) % ny
    cz = idx // (nx * ny)
    origin_c = np.asarray(canonical_grid.origin)
    spacing_c = np.asarray(canonical_grid.spacing)
    centres = origin_c + (np.column_stack([cx, cy, cz]) + 0.5) * spacing_c

    origin_s = np.asarray(source_grid.origin)
    spacing_s = np.asarray(source_grid.spacing)
    snx, sny, snz = source_grid.cell_shape
    s_idx = np.floor((centres - origin_s) / spacing_s).astype(np.int64)
    s_idx[:, 0] = np.clip(s_idx[:, 0], 0, snx - 1)
    s_idx[:, 1] = np.clip(s_idx[:, 1], 0, sny - 1)
    s_idx[:, 2] = np.clip(s_idx[:, 2], 0, snz - 1)
    flat = s_idx[:, 0] + snx * (s_idx[:, 1] + sny * s_idx[:, 2])
    return np.asarray(source_values)[flat]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true", help="Remove and rebuild an existing output dir.")
    args = parser.parse_args()

    if OUTPUT_DIR.exists():
        if not args.overwrite:
            raise SystemExit(
                f"{OUTPUT_DIR} already exists; pass --overwrite to rebuild it."
            )
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # 1. Synthetic geometry: design-domain box from the source contract's
    #    active_design_mask bounding box.
    lower, upper = design_domain_box_from_source_mask()
    write_box_stl(OUTPUT_DIR / "geometry/design_domain.stl", lower, upper)
    print(f"design_domain box: lower={lower.tolist()} upper={upper.tolist()}")

    # 2. Native v2 ProblemSpec.
    project_yaml = OUTPUT_DIR / "project.yaml"
    write_project_yaml(project_yaml, lower, upper)
    run([str(CFD_SDF), "validate-problem-spec", str(project_yaml), "--require-execution-ready"])
    spec = load_problem_spec(project_yaml)

    canonical = canonical_uniform_cartesian_cell_grid(spec)
    assert canonical.cell_shape == (60, 32, 24), canonical.cell_shape
    assert canonical.cell_count == 46080
    assert canonical.origin == DOMAIN_LOWER
    assert canonical.spacing == (VOXEL, VOXEL, VOXEL)
    print(f"canonical grid: shape={canonical.cell_shape} count={canonical.cell_count} "
          f"origin={canonical.origin} spacing={canonical.spacing}")

    problem_snapshot = write_problem_spec_snapshot(spec, OUTPUT_DIR / "problem_spec_snapshot.json")

    # 3. Canonical grid snapshot + geometry mask manifest.
    geometry_artifacts = build_canonical_geometry_mask_snapshot(spec, output_dir=OUTPUT_DIR)
    print("canonical mask true-counts:", geometry_artifacts.mask_true_counts)
    verified_grid = load_and_verify_canonical_grid_snapshot(geometry_artifacts.snapshot_path, spec)

    # 4. Canonical Stage T state: nearest-neighbour resample of source rho.
    source_state = load_fixed_grid_density_state(SOURCE_CONTRACT)
    canonical_cell_grid = CartesianCellGrid(
        origin=canonical.origin, spacing=canonical.spacing, cell_shape=canonical.cell_shape,
    )
    masks = verified_grid.masks
    allowed_mask = np.logical_or(masks["active_design_mask"], masks["fixed_solid_mask"]).astype(np.uint8)

    beta_max_match = re.search(r"([\d.eE+-]+)\s*\*\s*OpenFOAM beta", source_state.state["array_metadata"]["alpha"]["source"])
    beta_max = float(beta_max_match.group(1))

    arrays = {
        name: sample_nearest(canonical, source_state.grid, source_state.arrays[name])
        for name in ("rho", "rho_filtered", "rho_projected", "alpha")
    }
    arrays.update(
        allowed_mask=allowed_mask,
        forbidden_mask=masks["forbidden_mask"],
        fixed_solid_mask=masks["fixed_solid_mask"],
        root_mask=masks["root_mask"],
        active_design_mask=masks["active_design_mask"],
    )
    assert set(arrays) == set(DENSITY_ARRAYS)

    density_vti = _write_cell_vti(canonical_cell_grid, arrays, OUTPUT_DIR / "density.vti", kind="fixed_grid_density")

    array_metadata = _density_array_metadata(
        beta_max=beta_max,
        filter_source="nearest-neighbour resample of t1_contract rho_filtered onto the canonical grid",
    )
    array_metadata["rho"]["source"] = "nearest-neighbour resample of t1_contract rho onto the canonical grid"
    array_metadata["rho_projected"]["source"] = "nearest-neighbour resample of t1_contract rho_projected onto the canonical grid"

    topology_state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_variable": "rho",
        "grid": canonical_cell_grid.to_dict(),
        "coordinate_system": source_state.state["coordinate_system"],
        "bounds": {"lower": 0.0, "upper": 1.0},
        "density_vti": density_vti.name,
        "density_array": "rho",
        "array_metadata": array_metadata,
        "mask_precedence": ["forbidden_mask", "fixed_solid_mask", "allowed_mask", "active_design_mask"],
        "source_solver": source_state.state["source_solver"],
        "provenance": {
            "generated_by": "scripts/build_p0_closed_loop_fixture.py",
            "resample_method": "nearest_neighbor_cell_center",
            "source_contract_topology_state": str(SOURCE_CONTRACT),
        },
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "candidate_id": CANDIDATE_ID,
        "parent_candidate_id": None,
        "iteration": 0,
    }
    topology_state_path = OUTPUT_DIR / "topology_state.json"
    topology_state_path.write_text(json.dumps(topology_state, indent=2), encoding="utf-8")

    # 5. Verified Stage T candidate binding.
    binding_path = OUTPUT_DIR / "stage_t_candidate_binding.json"
    run([
        str(CFD_SDF), "bind-stage-t-candidate",
        str(project_yaml), str(topology_state_path), str(density_vti), str(binding_path),
        "--problem-snapshot", str(problem_snapshot),
        "--canonical-grid-snapshot", str(geometry_artifacts.snapshot_path),
        "--canonical-geometry-manifest", str(geometry_artifacts.geometry_manifest_path),
        "--candidate-id", CANDIDATE_ID,
    ])
    run([str(CFD_SDF), "validate-stage-t-candidate-binding", str(binding_path), str(project_yaml)])

    source_active = int(np.asarray(source_state.arrays["active_design_mask"]).sum())
    canonical_active = geometry_artifacts.mask_true_counts["active_design_mask"]
    volume_ratio = (np.prod(source_state.grid.spacing)) / (VOXEL ** 3)
    print(
        f"source active_design_mask={source_active} cells; canonical active_design_mask="
        f"{canonical_active} cells; source*volume_ratio({volume_ratio:.4f})="
        f"{source_active * volume_ratio:.1f}"
    )


if __name__ == "__main__":
    main()
