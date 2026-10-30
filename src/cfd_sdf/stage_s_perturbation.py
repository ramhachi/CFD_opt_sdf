"""Work F morpher-based perturbation construction and pair-side qualification.

Builds the prescribed B-spline control-point movement for one registered
direction/epsilon/sign, extracts the moved design surface from the morphed
OpenFOAM mesh, and runs the pair-side geometry, mesh and immobility gates. No
flow solver runs here; the shared centered-FD primal catalog is Slice C.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .extraction_qualification import _triangles_self_intersect
from .fixed_grid_contract import CartesianCellGrid
from .handoff import _build_revoxelized_density
from .openfoam_sensitivity import _read_boundary, _read_points, _read_selected_faces
from .shape_feature_metrics import occupancy_metrics
from .stage_v_domain_preflight import (
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
)

WORK_F_DESIGN_PATCH = "design_candidate"
_FOAM_HEADER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2512                                 |
|   \\\\  /    A nd           | www.openfoam.com                                |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


class PerturbationError(ValueError):
    """Fail-closed perturbation contract violation."""


def build_control_point_movement(
    *,
    direction: np.ndarray,
    active_var_ids: tuple[int, ...],
    n_control_points: tuple[int, int, int],
    epsilon: float,
    sign: float,
) -> np.ndarray:
    """The 512-vector control-point displacement with exact inf-norm epsilon."""

    values = np.asarray(direction, dtype=np.float64)
    if values.size != len(active_var_ids):
        raise PerturbationError(
            f"direction has {values.size} entries but {len(active_var_ids)} active ids were registered"
        )
    if not np.isfinite(values).all():
        raise PerturbationError("direction contains non-finite entries")
    nx, ny, nz = (int(value) for value in n_control_points)
    movement = np.zeros((nx * ny * nz, 3), dtype=np.float64)
    for value, var_id in zip(values, active_var_ids, strict=True):
        cp_id, component = divmod(int(var_id), 3)
        movement[cp_id, component] = float(sign) * float(epsilon) * float(value)
    inf_norm = float(np.max(np.abs(movement)))
    expected = float(epsilon)
    if not np.isclose(inf_norm, expected, rtol=0.0, atol=1e-12 * max(expected, 1.0)):
        raise PerturbationError(
            f"control-point movement inf-norm {inf_norm} does not equal the registered epsilon {expected}"
        )
    return movement


def movement_to_text(movement: np.ndarray) -> str:
    rows = "\n".join(
        f"({vector[0]:.12g} {vector[1]:.12g} {vector[2]:.12g})" for vector in movement
    )
    return (
        _FOAM_HEADER.format(object_name="controlPointsMovement")
        + f"\ncontrolPointsMovement {len(movement)}\n(\n{rows}\n);\n\n"
        + "// ************************************************************************* //\n"
    )


def movement_sha256(movement: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(movement, dtype=np.float64).tobytes()
    ).hexdigest()


@dataclass(frozen=True)
class PatchSurface:
    """The design patch of a morphed mesh, oriented outward."""

    vertices: np.ndarray
    faces: np.ndarray
    raw_volume: float
    orientation_flipped: bool


def extract_patch_surface(case_dir: Path, *, time_name: str) -> PatchSurface:
    """Extract and outward-orient the design patch of the mesh at ``time_name``."""

    case_dir = Path(case_dir)
    patch = _read_boundary(case_dir / "constant" / "polyMesh" / "boundary").get(WORK_F_DESIGN_PATCH)
    if patch is None:
        raise PerturbationError(f"case lacks the {WORK_F_DESIGN_PATCH} patch")
    faces = _read_selected_faces(
        case_dir / "constant" / "polyMesh" / "faces",
        [(int(patch["startFace"]), int(patch["nFaces"]))],
    )
    points_path = case_dir / time_name / "polyMesh" / "points"
    if not points_path.is_file():
        points_path = case_dir / "constant" / "polyMesh" / "points"
    vertices = np.asarray(_read_points(points_path), dtype=np.float64)
    triangles: list[list[int]] = []
    for face in faces.values():
        for index in range(1, len(face) - 1):
            triangles.append([face[0], face[index], face[index + 1]])
    faces_array = np.asarray(triangles, dtype=np.int64)
    # closed-patch volume under the mesh face orientation; the snappy patch is
    # inward-oriented, so an outward copy is used for the gates
    import trimesh

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces_array, process=False)
    raw_volume = float(mesh.volume)
    if raw_volume < 0.0:
        faces_array = faces_array[:, ::-1]
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces_array, process=False)
    return PatchSurface(
        vertices=vertices,
        faces=faces_array,
        raw_volume=raw_volume,
        orientation_flipped=raw_volume < 0.0,
    )


def surface_geometry_checks(
    *,
    baseline: PatchSurface,
    moved: PatchSurface,
    spec,
    grid: CartesianCellGrid,
    clearance_profile: dict[str, Any] = STAGE_V_CLEARANCE_PROFILE_V1,
) -> dict[str, Any]:
    """Geometry gates for one moved design surface."""

    import tempfile

    import trimesh

    moved_mesh = trimesh.Trimesh(vertices=moved.vertices, faces=moved.faces, process=True)
    baseline_mesh = trimesh.Trimesh(
        vertices=baseline.vertices, faces=baseline.faces, process=True
    )
    checks: dict[str, Any] = {
        "watertight": bool(moved_mesh.is_watertight),
        "winding_consistent": bool(moved_mesh.is_winding_consistent),
        "positive_volume": bool(moved_mesh.volume > 0.0),
        "self_intersection": _triangles_self_intersect(moved_mesh),
        "volume_m3": float(moved_mesh.volume),
        "baseline_volume_m3": float(baseline_mesh.volume),
        "volume_relative_difference": float(
            abs(moved_mesh.volume - baseline_mesh.volume) / max(abs(baseline_mesh.volume), 1e-30)
        ),
    }
    revoxelized = _build_revoxelized_density(moved_mesh, grid)
    metrics = occupancy_metrics(np.asarray(revoxelized, dtype=bool), float(grid.spacing[0]))
    checks["minimum_solid_width_m"] = metrics.get("thickness_ridge_m_min")
    with tempfile.TemporaryDirectory() as tmp:
        stl_path = Path(tmp) / "moved.stl"
        moved_mesh.export(stl_path)
        preflight = evaluate_stage_v_domain_preflight(
            spec, stl_path, float(spec.grid.voxel_size_m), profile=clearance_profile
        )
    checks["clearance_qualified"] = bool(preflight.qualified)
    checks["clearance_reasons"] = list(preflight.reasons)
    checks["pass"] = bool(
        checks["watertight"]
        and checks["winding_consistent"]
        and checks["positive_volume"]
        and checks["self_intersection"] == "none"
        and checks["clearance_qualified"]
    )
    return checks


def fixed_patch_immobility(
    *, case_dir: Path, baseline_points: Path, moved_points: Path
) -> dict[str, Any]:
    """Max displacement of the outer-patch points must be zero."""

    old = np.asarray(_read_points(baseline_points), dtype=np.float64)
    new = np.asarray(_read_points(moved_points), dtype=np.float64)
    if old.shape != new.shape:
        raise PerturbationError("baseline and moved point counts differ")
    lower, upper = old.min(axis=0), old.max(axis=0)
    tolerance = 1e-6
    on_boundary = np.zeros(old.shape[0], dtype=bool)
    for axis in range(3):
        on_boundary |= np.abs(old[:, axis] - lower[axis]) < tolerance
        on_boundary |= np.abs(old[:, axis] - upper[axis]) < tolerance
    displacement = np.linalg.norm(new - old, axis=1)
    return {
        "boundary_point_count": int(on_boundary.sum()),
        "boundary_max_displacement_m": float(displacement[on_boundary].max()),
        "interior_max_displacement_m": float(displacement[~on_boundary].max()),
        "pass": bool(displacement[on_boundary].max() == 0.0),
    }


def parse_check_mesh_qualified(log_text: str, *, profile) -> dict[str, Any]:
    """checkMesh verdict through the registered Stage V profile."""

    from .cfd import evaluate_check_mesh

    return evaluate_check_mesh(log_text, profile=profile)


def perturbation_side_id(direction: str, epsilon: float, sign: str) -> str:
    return f"{direction}__eps{epsilon:.6g}__{sign}"


def slug(value: float) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", f"{value:.6g}")


__all__ = [
    "PatchSurface",
    "PerturbationError",
    "WORK_F_DESIGN_PATCH",
    "build_control_point_movement",
    "extract_patch_surface",
    "fixed_patch_immobility",
    "movement_sha256",
    "movement_to_text",
    "parse_check_mesh_qualified",
    "perturbation_side_id",
    "slug",
    "surface_geometry_checks",
]
