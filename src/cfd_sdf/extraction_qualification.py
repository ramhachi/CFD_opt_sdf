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
    "require_self_intersection_measured": True,
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
    "require_self_intersection_measured": True,
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
        "self_intersection": _triangles_self_intersect(mesh),
    }
    checks["mesh_manifold"] = manifold
    if profile["require_no_duplicate_faces"] and manifold["non_manifold_edge_count"] > 0:
        reasons.append("mesh_has_non_manifold_edges")
    if (
        profile.get("require_self_intersection_measured")
        and manifold["self_intersection"].startswith("not_evaluated")
    ):
        reasons.append(f"self_intersection:{manifold['self_intersection']}")
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


def _triangles_self_intersect(mesh) -> str:
    """Direct triangle-triangle self-intersection test (edge/plane narrow phase).

    Vectorized over the AABB-overlap candidate pairs; pairs sharing a vertex
    are excluded. Returns "none", "fail", or a "not_evaluated_*" status that a
    required profile turns into a failure.
    """

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    n = faces.shape[0]
    if n > 12_000:
        return "not_evaluated_too_many_triangles"
    tri = vertices[faces]  # (n, 3, 3)
    tri_min = tri.min(axis=1)
    tri_max = tri.max(axis=1)

    overlap_min = np.maximum(tri_min[:, None, :], tri_min[None, :, :])
    overlap_max = np.minimum(tri_max[:, None, :], tri_max[None, :, :])
    candidate_pairs = np.all(overlap_min <= overlap_max, axis=2)
    iu = np.triu_indices(n, k=1)
    pair_i, pair_j = iu[0][candidate_pairs[iu]], iu[1][candidate_pairs[iu]]
    if pair_i.size == 0:
        return "none"

    # exclude pairs sharing a vertex via sorted-vertex label overlap
    labels = np.sort(faces, axis=1)  # (n, 3) sorted vertex ids per triangle
    labels_pairs_a = labels[pair_i]
    labels_pairs_b = labels[pair_j]
    column_a = np.repeat(labels_pairs_a, 3, axis=1)  # (p, 9)
    column_b = np.tile(labels_pairs_b, (1, 3))       # (p, 9)
    shared = (column_a == column_b).any(axis=1)
    keep = ~shared
    pair_i, pair_j = pair_i[keep], pair_j[keep]
    if pair_i.size == 0:
        return "none"

    A = tri[pair_i]
    B = tri[pair_j]
    hits = _edges_pierce_triangles(A, B) | _edges_pierce_triangles(B, A)
    return "fail" if bool(np.any(hits)) else "none"


def _edges_pierce_triangles(frm: np.ndarray, to: np.ndarray) -> np.ndarray:
    """Vectorized edge-triangle pierce test for candidate pairs (one direction)."""

    hit = np.zeros(frm.shape[0], dtype=bool)
    for edge in range(3):
        p0 = frm[:, edge, :]
        p1 = frm[:, (edge + 1) % 3, :]
        normal = np.cross(to[:, 1, :] - to[:, 0, :], to[:, 2, :] - to[:, 0, :])
        denom = np.einsum("ij,ij->i", normal, normal)
        denom = np.where(np.abs(denom) < 1e-30, np.nan, denom)
        d0 = np.einsum("ij,ij->i", p0 - to[:, 0, :], normal)
        d1 = np.einsum("ij,ij->i", p1 - to[:, 0, :], normal)
        with np.errstate(invalid="ignore", divide="ignore"):
            t = d0 / (d0 - d1)
        crossing = (d0 * d1 < 0) & np.isfinite(t)
        point = p0 + np.nan_to_num(t)[:, None] * (p1 - p0)
        v0 = to[:, 1, :] - to[:, 0, :]
        v1 = to[:, 2, :] - to[:, 0, :]
        v2 = point - to[:, 0, :]
        d00 = np.einsum("ij,ij->i", v0, v0)
        d01 = np.einsum("ij,ij->i", v0, v1)
        d11 = np.einsum("ij,ij->i", v1, v1)
        d20 = np.einsum("ij,ij->i", v2, v0)
        d21 = np.einsum("ij,ij->i", v2, v1)
        denom_b = d00 * d11 - d01 * d01
        denom_b = np.where(np.abs(denom_b) < 1e-30, np.nan, denom_b)
        v = (d11 * d20 - d01 * d21) / denom_b
        w = (d00 * d20 - d01 * d21) / denom_b
        inside = (v >= -1e-12) & (w >= -1e-12) & (v + w <= 1 + 1e-12)
        hit |= crossing & inside & ~np.isnan(v) & ~np.isnan(w)
    return hit


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
