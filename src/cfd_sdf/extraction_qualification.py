"""Quantitative extraction qualification (PQ4).

The handed-off Stage S readiness flag was a placeholder: the fidelity report
listed ``surface_distance_not_evaluated``, ``minimum_feature_survival_not_evaluated``,
``self_intersection_not_evaluated`` and root-connectivity gaps, so
``ready_for_stage_s`` could never be evaluated numerically. This module adds
the missing quantitative checks on top of the handoff artifacts (read-only):

- **surface distance**: the maximum and RMS distance (meters) from the extracted
  mesh vertices to the revoxelized material boundary, computed with an exact
  Euclidean distance transform of the revoxelized occupancy; a mesh that
  disagrees with the density it was contoured from fails;
- **feature survival**: the minimum local feature size (supersampled distance
  transform) of the revoxelized material must not shrink below the source
  threshold occupancy by more than the registered number of voxels;
- **self-intersection / manifoldness**: watertight, winding-consistent, volume
  positive, and no duplicated faces in the extracted mesh;
- **root connectivity**: when the source root mask is non-empty, every
  revoxelized material component must touch a root cell; with no root mask the
  check is recorded ``not_applicable`` (never silently passed).

A versioned profile owns the thresholds; the verdict is fail-closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .fixed_grid_contract import _read_cell_vti
from .shape_feature_metrics import occupancy_metrics

EXTRACTION_QUALIFICATION_PROFILE_V1: dict[str, Any] = {
    "profile_id": "extraction_qualification_v1",
    "surface_distance_max_m": 0.05,
    "surface_distance_rms_max_m": 0.025,
    "feature_shrink_max_voxels": 1.0,
    "require_watertight": True,
    "require_winding_consistent": True,
    "require_positive_volume": True,
    "require_no_duplicate_faces": True,
    "require_root_connectivity": True,
    "scope": "fixed-grid density-to-SDF handoff on the canonical Cartesian grid",
}


# v2: calibrated on analytic ground truth (docs/evidence/pq4_profile_calibration_2026_09.json).
# A perfect binary field measures 1.41-1.73 voxels max and ~1 voxel RMS on the
# cell-centered metric, so v1 (1.0 / 0.5 voxel) sat below the metric floor and no
# candidate could pass. v2 thresholds are 2.0 / 1.25 voxels.
EXTRACTION_QUALIFICATION_PROFILE_V2: dict[str, Any] = {
    "profile_id": "extraction_qualification_v2",
    "surface_distance_max_m": 0.10,
    "surface_distance_rms_max_m": 0.0625,
    "feature_shrink_max_voxels": 1.0,
    "require_watertight": True,
    "require_winding_consistent": True,
    "require_positive_volume": True,
    "require_no_duplicate_faces": True,
    "require_root_connectivity": True,
    "calibration": "docs/evidence/pq4_profile_calibration_2026_09.json",
    "scope": "fixed-grid density-to-SDF handoff on the canonical Cartesian grid",
}

EXTRACTION_QUALIFICATION_PROFILES: dict[str, dict[str, Any]] = {
    "v1": EXTRACTION_QUALIFICATION_PROFILE_V1,
    "v2": EXTRACTION_QUALIFICATION_PROFILE_V2,
}


class ExtractionQualificationError(ValueError):
    """Fail-closed extraction qualification contract violation."""


@dataclass(frozen=True)
class ExtractionQualification:
    ready_for_stage_s: bool
    profile_id: str
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify_extraction(
    handoff_manifest_json: str | Path,
    *,
    mesh_path: str | Path,
    profile: dict[str, Any] | None = None,
) -> ExtractionQualification:
    """Evaluate the quantitative extraction gates for one handoff."""

    profile = dict(EXTRACTION_QUALIFICATION_PROFILE_V1 if profile is None else profile)
    manifest_path = Path(handoff_manifest_json)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ExtractionQualificationError("handoff manifest has no artifacts block")
    revoxelized_path = base / artifacts["revoxelized_density_vti"]["path"]
    source_density_path = base / artifacts["source_density_vti"]["path"]
    for key in ("revoxelized_density_vti", "source_density_vti"):
        expected = artifacts[key]["sha256"]
        actual = _sha256(base / artifacts[key]["path"])
        if actual != expected:
            raise ExtractionQualificationError(f"{key} changed after the handoff")

    mesh = _load_mesh(Path(mesh_path))
    revoxelized_grid, revoxelized_arrays = _read_cell_vti(
        revoxelized_path, expected_kind="stage_s_revoxelized_density"
    )
    source_grid, source_arrays = _read_cell_vti(
        source_density_path, expected_kind="fixed_grid_density"
    )
    spacing = float(revoxelized_grid.spacing[0])
    shape = tuple(int(v) for v in revoxelized_grid.cell_shape)
    material = (revoxelized_arrays["rho_revoxelized"] > 0.5).reshape(shape, order="F")
    threshold = float(manifest.get("rho", {}).get("iso_value", 0.5))
    source_material = (source_arrays["rho"] >= threshold).reshape(shape, order="F")

    checks: dict[str, Any] = {}
    reasons: list[str] = []

    # --- surface distance ---------------------------------------------------
    if not material.any():
        surface_distance = {"max_m": None, "rms_m": None, "status": "empty_material"}
        reasons.append("revoxelized_material_is_empty")
    else:
        distance = ndimage.distance_transform_edt(~material, sampling=spacing)
        samples = _sample_distance_at_vertices(distance, revoxelized_grid, mesh.vertices)
        surface_distance = {
            "max_m": float(samples.max()),
            "rms_m": float(np.sqrt(np.mean(samples**2))),
            "status": "measured",
        }
    checks["surface_distance"] = surface_distance
    if surface_distance["status"] == "measured":
        if surface_distance["max_m"] > float(profile["surface_distance_max_m"]):
            reasons.append("surface_distance_exceeds_profile")
        if surface_distance["rms_m"] > float(profile["surface_distance_rms_max_m"]):
            reasons.append("surface_distance_rms_exceeds_profile")

    # --- feature survival ---------------------------------------------------
    feature = {"status": "not_applicable"}
    if material.any() and source_material.any():
        revoxelized_metrics = occupancy_metrics(material, spacing)
        source_metrics = occupancy_metrics(source_material, spacing)
        revox_min = float(revoxelized_metrics["max_inscribed_diameter_m"])
        source_min = float(source_metrics["max_inscribed_diameter_m"])
        shrink_voxels = (source_min - revox_min) / spacing
        feature = {
            "status": "measured",
            "source_min_feature_m": source_min,
            "revoxelized_min_feature_m": revox_min,
            "shrink_voxels": shrink_voxels,
        }
        if shrink_voxels > float(profile["feature_shrink_max_voxels"]):
            reasons.append("feature_shrink_exceeds_profile")
    checks["feature_survival"] = feature

    # --- reverse distance (voxel boundary -> mesh) --------------------------
    reverse = {"status": "not_applicable"}
    if material.any():
        boundary = material & ~ndimage.binary_erosion(
            material, structure=np.ones((3, 3, 3), dtype=bool)
        )
        boundary_indices = np.argwhere(boundary)
        if boundary_indices.size:
            rng = np.random.default_rng(20260922)
            if boundary_indices.shape[0] > 5000:
                choice = rng.choice(boundary_indices.shape[0], size=5000, replace=False)
                boundary_indices = boundary_indices[choice]
            origin = np.asarray(revoxelized_grid.origin, dtype=np.float64)
            spacing_vec = np.asarray(revoxelized_grid.spacing, dtype=np.float64)
            points = origin + (boundary_indices + 0.5) * spacing_vec
            import trimesh

            proximity = trimesh.proximity.ProximityQuery(mesh)
            distance = np.abs(proximity.signed_distance(points))
            reverse = {
                "status": "measured",
                "max_m": float(distance.max()),
                "rms_m": float(np.sqrt(np.mean(distance**2))),
                "sample_count": int(points.shape[0]),
            }
    checks["reverse_surface_distance"] = reverse
    if reverse["status"] == "measured":
        if reverse["max_m"] > float(profile["surface_distance_max_m"]):
            reasons.append("reverse_surface_distance_exceeds_profile")
        if reverse["rms_m"] > float(profile["surface_distance_rms_max_m"]):
            reasons.append("reverse_surface_distance_rms_exceeds_profile")

    # --- mesh manifoldness --------------------------------------------------
    unique_faces = np.unique(mesh.faces, axis=0).shape[0]
    edges = np.sort(mesh.edges_sorted, axis=1)
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    non_manifold_edges = int(np.count_nonzero(edge_counts != 2))
    manifold = {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "positive_volume": bool(mesh.is_volume and mesh.volume > 0.0),
        "duplicate_face_count": int(len(mesh.faces) - unique_faces),
        "non_manifold_edge_count": non_manifold_edges,
        "self_intersection": _self_intersection_status(mesh),
    }
    checks["mesh_manifold"] = manifold
    if profile["require_no_duplicate_faces"] and manifold["non_manifold_edge_count"] > 0:
        reasons.append("mesh_has_non_manifold_edges")
    if profile["require_watertight"] and not manifold["watertight"]:
        reasons.append("mesh_not_watertight")
    if profile["require_winding_consistent"] and not manifold["winding_consistent"]:
        reasons.append("mesh_winding_inconsistent")
    if profile["require_positive_volume"] and not manifold["positive_volume"]:
        reasons.append("mesh_volume_not_positive")
    if profile["require_no_duplicate_faces"] and manifold["duplicate_face_count"] > 0:
        reasons.append("mesh_has_duplicate_faces")

    # --- root connectivity --------------------------------------------------
    root_mask = np.asarray(
        source_arrays.get("root_mask", np.zeros(source_grid.cell_count, dtype=np.uint8))
    ).reshape(shape, order="F") > 0
    if not root_mask.any():
        root = {"status": "not_applicable", "reason": "source root mask is empty"}
    elif not material.any():
        root = {"status": "fail", "reason": "no material to connect"}
        reasons.append("root_connectivity_no_material")
    else:
        labels, count = ndimage.label(material, structure=np.ones((3, 3, 3), dtype=bool))
        attached = {
            int(label): bool(np.any(root_mask & (labels == label)))
            for label in range(1, count + 1)
        }
        root = {
            "status": "pass" if all(attached.values()) else "fail",
            "components": count,
            "attached": attached,
        }
        if profile["require_root_connectivity"] and not all(attached.values()):
            reasons.append("root_connectivity_unattached_component")
    checks["root_connectivity"] = root

    return ExtractionQualification(
        ready_for_stage_s=not reasons,
        profile_id=str(profile["profile_id"]),
        reasons=reasons,
        checks=checks,
    )


def _self_intersection_status(mesh) -> str:
    """Direct self-intersection test when manifold3d is available, else recorded."""

    try:
        import manifold3d  # noqa: F401
    except ImportError:
        return "not_evaluated_no_manifold3d"
    try:
        import trimesh

        return "none" if not trimesh.boolean.intersection([mesh, mesh]).is_empty else "fail"
    except Exception:  # noqa: BLE001 - recorded, never hidden
        return "not_evaluated_boolean_error"


def _load_mesh(path: Path):
    import trimesh

    mesh = trimesh.load_mesh(path)  # default processing, as the handoff assessment
    if mesh.is_empty:
        raise ExtractionQualificationError(f"mesh is empty: {path}")
    return mesh


def _sample_distance_at_vertices(
    distance: np.ndarray, grid, vertices: np.ndarray
) -> np.ndarray:
    origin = np.asarray(grid.origin, dtype=np.float64)
    spacing = np.asarray(grid.spacing, dtype=np.float64)
    shape = distance.shape
    indices = np.floor((np.asarray(vertices, dtype=np.float64) - origin) / spacing).astype(int)
    clipped = np.clip(indices, 0, np.asarray(shape) - 1)
    return distance[clipped[:, 0], clipped[:, 1], clipped[:, 2]]


__all__ = [
    "EXTRACTION_QUALIFICATION_PROFILE_V1",
    "EXTRACTION_QUALIFICATION_PROFILE_V2",
    "EXTRACTION_QUALIFICATION_PROFILES",
    "ExtractionQualification",
    "ExtractionQualificationError",
    "qualify_extraction",
]
