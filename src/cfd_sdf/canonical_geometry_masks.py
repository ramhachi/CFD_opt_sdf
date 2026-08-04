"""Build fail-closed canonical topology masks from native v2 STL regions.

The masks in a canonical grid snapshot are not generic image-processing
outputs: they establish which density degrees of freedom the native OpenFOAM
transfer is allowed to update.  This module therefore accepts only explicit
canonical domains, water-tight positive-volume STL solids, and deterministic
cell-centre containment.  It writes both the generic snapshot and a companion
geometry manifest that binds every mask to exact STL source hashes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .canonical_grid_snapshot import (
    CANONICAL_MASK_IDS,
    load_and_verify_canonical_grid_snapshot,
    read_canonical_grid_snapshot,
    write_canonical_grid_snapshot,
)
from .problem_spec import (
    ProblemSpec,
    canonical_uniform_cartesian_cell_grid,
    load_problem_spec,
    problem_spec_sha256,
)


CANONICAL_GEOMETRY_MASK_MANIFEST_KIND = "canonical_geometry_mask_manifest"
CANONICAL_GEOMETRY_MASK_MANIFEST_SCHEMA_VERSION = 1
_ROLE_MASK_IDS = {
    "design_domain": "active_design_mask",
    "forbidden_region": "forbidden_mask",
    "fixed_solid": "fixed_solid_mask",
    "root": "root_mask",
}
_MASK_SOURCE_ROLES = {
    "active_design_mask": ("design_domain", "forbidden_region", "fixed_solid"),
    "forbidden_mask": ("forbidden_region",),
    "fixed_solid_mask": ("fixed_solid",),
    "root_mask": ("root",),
}


@dataclass(frozen=True)
class CanonicalGeometryMaskArtifacts:
    """Paths and immutable counts resulting from a geometry-mask build."""

    snapshot_path: Path
    geometry_manifest_path: Path
    mask_true_counts: Mapping[str, int]
    grid_cell_count: int


@dataclass(frozen=True)
class _GeometrySource:
    region_id: str
    role: str
    relative_path: str
    path: Path
    sha256: str
    mesh: trimesh.Trimesh


def build_canonical_geometry_mask_snapshot(
    problem: ProblemSpec | str | Path,
    *,
    output_dir: str | Path,
    snapshot_name: str = "canonical_grid_snapshot.json",
    geometry_manifest_name: str = "canonical_geometry_mask_manifest.json",
    chunk_size: int = 65_536,
) -> CanonicalGeometryMaskArtifacts:
    """Build native-v2 role masks and persist a provenance-bound snapshot.

    ``problem`` may be an already parsed native :class:`ProblemSpec` or its
    YAML path.  Geometry containment is evaluated only at canonical cell
    centres in x-fastest order.  Cells on any STL surface are rejected rather
    than assigned arbitrarily.
    """

    spec = _load_spec(problem)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    grid = canonical_uniform_cartesian_cell_grid(spec)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    snapshot_path = output / _safe_output_name(snapshot_name, "snapshot_name")
    manifest_path = output / _safe_output_name(geometry_manifest_name, "geometry_manifest_name")
    if snapshot_path == manifest_path:
        raise ValueError("snapshot_name and geometry_manifest_name must differ")

    sources = _load_geometry_sources(spec)
    role_masks = _build_role_masks(sources, grid, chunk_size=chunk_size)
    masks = _derive_masks(spec, role_masks)
    written_snapshot = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=masks,
        path=snapshot_path,
    )
    snapshot = read_canonical_grid_snapshot(written_snapshot)
    manifest = _geometry_manifest(spec, snapshot, sources, masks)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    return CanonicalGeometryMaskArtifacts(
        snapshot_path=written_snapshot,
        geometry_manifest_path=manifest_path,
        mask_true_counts={mask_id: int(values.sum(dtype=np.int64)) for mask_id, values in masks.items()},
        grid_cell_count=grid.cell_count,
    )


def verify_canonical_geometry_mask_manifest(
    path: str | Path,
    problem: ProblemSpec | str | Path,
) -> CanonicalGeometryMaskArtifacts:
    """Verify that snapshot masks still bind the exact native STL sources."""

    spec = _load_spec(problem)
    manifest_path = Path(path)
    data = _read_manifest(manifest_path)
    if data.get("schema_version") != CANONICAL_GEOMETRY_MASK_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported canonical geometry mask manifest schema_version")
    if data.get("kind") != CANONICAL_GEOMETRY_MASK_MANIFEST_KIND:
        raise ValueError("Invalid canonical geometry mask manifest kind")
    if data.get("problem_id") != spec.problem_id:
        raise ValueError("canonical geometry mask manifest problem_id does not match problem specification")
    if data.get("problem_spec_sha256") != problem_spec_sha256(spec):
        raise ValueError(
            "canonical geometry mask manifest problem_spec_sha256 does not match problem specification"
        )
    if data.get("execution_ready") != spec.migration.execution_ready:
        raise ValueError(
            "canonical geometry mask manifest execution_ready does not match problem specification"
        )
    snapshot_raw = _mapping(data.get("canonical_grid_snapshot"), "canonical_grid_snapshot")
    snapshot_name = _safe_output_name(snapshot_raw.get("path"), "canonical_grid_snapshot.path")
    snapshot_path = manifest_path.parent / snapshot_name
    if not snapshot_path.is_file():
        raise ValueError("canonical geometry mask manifest snapshot is missing")
    if snapshot_raw.get("sha256") != _sha256_path(snapshot_path):
        raise ValueError("canonical geometry mask manifest snapshot hash mismatch")
    verified_snapshot = load_and_verify_canonical_grid_snapshot(snapshot_path, spec)
    if snapshot_raw.get("grid_sha256") != verified_snapshot.snapshot.grid_sha256:
        raise ValueError("canonical geometry mask manifest grid hash mismatch")

    sources_raw = _mapping(data.get("geometry_sources"), "geometry_sources")
    expected_sources = _geometry_source_records(spec)
    if set(sources_raw) != set(expected_sources):
        raise ValueError("canonical geometry mask manifest geometry source IDs do not match problem specification")
    for region_id, expected in expected_sources.items():
        actual = _mapping(sources_raw.get(region_id), f"geometry_sources.{region_id}")
        if actual != expected:
            raise ValueError(f"canonical geometry mask manifest geometry source mismatch: {region_id}")

    masks_raw = _mapping(data.get("masks"), "masks")
    if set(masks_raw) != set(CANONICAL_MASK_IDS):
        raise ValueError("canonical geometry mask manifest mask IDs do not match canonical snapshot")
    source_ids_by_role = {
        role: [region_id for region_id, item in expected_sources.items() if item["role"] == role]
        for role in _ROLE_MASK_IDS
    }
    counts: dict[str, int] = {}
    for mask_id in CANONICAL_MASK_IDS:
        actual = _mapping(masks_raw.get(mask_id), f"masks.{mask_id}")
        artifact = verified_snapshot.snapshot.masks[mask_id]
        if actual.get("artifact_path") != artifact.relative_path:
            raise ValueError(f"canonical geometry mask manifest artifact path mismatch: {mask_id}")
        if actual.get("artifact_sha256") != artifact.sha256:
            raise ValueError(f"canonical geometry mask manifest artifact hash mismatch: {mask_id}")
        if actual.get("true_count") != artifact.true_count:
            raise ValueError(f"canonical geometry mask manifest true_count mismatch: {mask_id}")
        expected_ids = sorted(
            region_id
            for role in _MASK_SOURCE_ROLES[mask_id]
            for region_id in source_ids_by_role[role]
        )
        if actual.get("source_geometry_ids") != expected_ids:
            raise ValueError(f"canonical geometry mask manifest source IDs mismatch: {mask_id}")
        counts[mask_id] = artifact.true_count
    return CanonicalGeometryMaskArtifacts(
        snapshot_path=snapshot_path,
        geometry_manifest_path=manifest_path,
        mask_true_counts=counts,
        grid_cell_count=verified_snapshot.snapshot.grid.cell_count,
    )


def _load_spec(problem: ProblemSpec | str | Path) -> ProblemSpec:
    if isinstance(problem, ProblemSpec):
        if problem.migration.migrated:
            raise ValueError("canonical geometry masks require a native v2 ProblemSpec")
        return problem
    return load_problem_spec(problem)


def _load_geometry_sources(spec: ProblemSpec) -> tuple[_GeometrySource, ...]:
    if spec.migration.migrated:
        raise ValueError("canonical geometry masks require a native v2 ProblemSpec")
    sources: list[_GeometrySource] = []
    for region in spec.geometry_regions:
        path = (spec.path.parent / region.file).resolve()
        if not path.is_file():
            raise ValueError(f"Geometry STL is missing for region {region.id!r}: {region.file}")
        payload = path.read_bytes()
        mesh = _load_closed_mesh(path, region.id)
        sources.append(
            _GeometrySource(
                region_id=region.id,
                role=region.role,
                relative_path=region.file.as_posix(),
                path=path,
                sha256=hashlib.sha256(payload).hexdigest(),
                mesh=mesh,
            )
        )
    if not sources:
        raise ValueError("canonical geometry masks require at least one geometry region")
    return tuple(sources)


def _load_closed_mesh(path: Path, region_id: str) -> trimesh.Trimesh:
    try:
        # STL repeats vertices per triangle.  ``process=True`` merges those
        # exact duplicates before the water-tightness check; it does not make
        # an open surface closed.
        mesh = trimesh.load_mesh(path, process=True)
    except Exception as exc:  # trimesh raises several parser-specific exception types.
        raise ValueError(f"Unable to load geometry STL for region {region_id!r}: {path}") from exc
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"Geometry STL for region {region_id!r} must contain one mesh, not a scene")
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError(f"Geometry STL for region {region_id!r} is empty")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError(f"Geometry STL for region {region_id!r} has non-finite vertices")
    if not mesh.is_watertight:
        raise ValueError(f"Geometry STL for region {region_id!r} must be watertight")
    if not mesh.is_volume:
        raise ValueError(
            f"Geometry STL for region {region_id!r} must be consistently wound with positive volume"
        )
    return mesh


def _build_role_masks(
    sources: Sequence[_GeometrySource],
    grid: Any,
    *,
    chunk_size: int,
) -> dict[str, np.ndarray]:
    role_masks = {
        role: np.zeros(grid.cell_count, dtype=bool)
        for role in _ROLE_MASK_IDS
    }
    for source in sources:
        if source.role not in role_masks:
            continue
        role_masks[source.role] |= _mesh_cell_centres_inside(source, grid, chunk_size=chunk_size)
    return role_masks


def _mesh_cell_centres_inside(
    source: _GeometrySource,
    grid: Any,
    *,
    chunk_size: int,
) -> np.ndarray:
    result = np.zeros(grid.cell_count, dtype=bool)
    lower, upper = np.asarray(source.mesh.bounds, dtype=np.float64)
    tolerance = max(1.0e-12, min(grid.spacing) * 1.0e-10)
    for start in range(0, grid.cell_count, chunk_size):
        stop = min(start + chunk_size, grid.cell_count)
        points = _cell_centres(grid, start, stop)
        candidates = np.all((points >= lower - tolerance) & (points <= upper + tolerance), axis=1)
        if not np.any(candidates):
            continue
        candidate_points = points[candidates]
        try:
            _, distances, _ = trimesh.proximity.closest_point(source.mesh, candidate_points)
        except Exception as exc:
            raise ValueError(
                f"Unable to establish unambiguous containment for region {source.region_id!r}"
            ) from exc
        if np.any(~np.isfinite(distances)):
            raise ValueError(f"Containment distance is non-finite for region {source.region_id!r}")
        if np.any(distances <= tolerance):
            raise ValueError(
                f"Containment is ambiguous for region {source.region_id!r}: "
                "a canonical cell centre lies on the STL surface"
            )
        try:
            contained = source.mesh.contains(candidate_points)
        except Exception as exc:
            raise ValueError(f"Containment failed for region {source.region_id!r}") from exc
        if contained.shape != (len(candidate_points),) or contained.dtype != np.bool_:
            raise ValueError(f"Containment returned an invalid mask for region {source.region_id!r}")
        result_indices = np.flatnonzero(candidates) + start
        result[result_indices] = contained
    return result


def _cell_centres(grid: Any, start: int, stop: int) -> np.ndarray:
    indices = np.arange(start, stop, dtype=np.int64)
    nx, ny, _ = grid.cell_shape
    x = indices % nx
    yz = indices // nx
    y = yz % ny
    z = yz // ny
    local = np.column_stack((x, y, z)).astype(np.float64, copy=False)
    return np.asarray(grid.origin, dtype=np.float64) + (
        local + 0.5
    ) * np.asarray(grid.spacing, dtype=np.float64)


def _derive_masks(spec: ProblemSpec, role_masks: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    design = _role_mask(role_masks, "design_domain")
    raw_forbidden = _role_mask(role_masks, "forbidden_region")
    fixed = _role_mask(role_masks, "fixed_solid")
    root = _role_mask(role_masks, "root")
    root_outside_fixed = root & ~fixed
    if np.any(root_outside_fixed):
        raise ValueError(
            "root_mask must be contained within fixed_solid_mask; "
            f"first_cell={int(np.flatnonzero(root_outside_fixed)[0])}"
        )
    # A forbidden envelope may deliberately include immutable vehicle/root
    # solids (for example, tire-clearance volumes).  Fixed solids take
    # precedence in that overlap: they remain fixed/root cells rather than
    # being exposed as forbidden void.  The raw envelope still excludes those
    # cells from design degrees of freedom.
    forbidden = raw_forbidden & ~fixed
    active = design & ~raw_forbidden & ~fixed
    if not np.any(active):
        raise ValueError("active_design_mask is empty after forbidden/fixed exclusions")
    root_required = any(
        policy.mode in {"root_connected", "required_root_groups"}
        for policy in (spec.topology_policy.solid_connectivity, spec.topology_policy.void_connectivity)
    )
    if root_required and not np.any(root):
        raise ValueError("root_mask is empty although topology_policy requires root groups")
    return {
        "active_design_mask": active.astype(np.uint8),
        "forbidden_mask": forbidden.astype(np.uint8),
        "fixed_solid_mask": fixed.astype(np.uint8),
        "root_mask": root.astype(np.uint8),
    }


def _role_mask(role_masks: Mapping[str, np.ndarray], role: str) -> np.ndarray:
    value = role_masks.get(role)
    if value is None or value.dtype != np.bool_ or value.ndim != 1:
        raise ValueError(f"Missing or invalid role mask for {role}")
    return value


def _geometry_manifest(
    spec: ProblemSpec,
    snapshot: Any,
    sources: Sequence[_GeometrySource],
    masks: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    sources_by_role = {
        role: [source.region_id for source in sources if source.role == role]
        for role in _ROLE_MASK_IDS
    }
    return {
        "schema_version": CANONICAL_GEOMETRY_MASK_MANIFEST_SCHEMA_VERSION,
        "kind": CANONICAL_GEOMETRY_MASK_MANIFEST_KIND,
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "canonical_grid_snapshot": {
            "path": snapshot.path.name,
            "sha256": _sha256_path(snapshot.path),
            "grid_sha256": snapshot.grid_sha256,
        },
        "geometry_sources": {
            source.region_id: {
                "role": source.role,
                "path": source.relative_path,
                "sha256": source.sha256,
            }
            for source in sources
        },
        "masks": {
            mask_id: {
                "artifact_path": snapshot.masks[mask_id].relative_path,
                "artifact_sha256": snapshot.masks[mask_id].sha256,
                "true_count": int(masks[mask_id].sum(dtype=np.int64)),
                "source_geometry_ids": sorted(
                    region_id
                    for role in _MASK_SOURCE_ROLES[mask_id]
                    for region_id in sources_by_role[role]
                ),
            }
            for mask_id in CANONICAL_MASK_IDS
        },
        "containment": {
            "method": "water_tight_stl_cell_centres",
            "cell_order": "x-fastest",
            "ambiguous_surface_centres": "rejected",
        },
    }


def _geometry_source_records(spec: ProblemSpec) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for region in spec.geometry_regions:
        path = (spec.path.parent / region.file).resolve()
        if not path.is_file():
            raise ValueError(f"Geometry STL is missing for region {region.id!r}: {region.file}")
        result[region.id] = {
            "role": region.role,
            "path": region.file.as_posix(),
            "sha256": _sha256_path(path),
        }
    return result


def _read_manifest(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read canonical geometry mask manifest: {path}") from exc
    return _mapping(data, "canonical geometry mask manifest")


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_output_name(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a single relative .json filename")
    path = Path(value)
    if path.is_absolute() or path.drive or len(path.parts) != 1 or path.suffix != ".json":
        raise ValueError(f"{context} must be a single relative .json filename")
    return value


__all__ = [
    "CANONICAL_GEOMETRY_MASK_MANIFEST_KIND",
    "CANONICAL_GEOMETRY_MASK_MANIFEST_SCHEMA_VERSION",
    "CanonicalGeometryMaskArtifacts",
    "build_canonical_geometry_mask_snapshot",
    "verify_canonical_geometry_mask_manifest",
]
