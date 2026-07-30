"""Immutable STL-derived local design-mask snapshots.

This is deliberately a *geometry* artifact, not a design-state artifact.
It binds the declared STL roles to the independent local topology grid before
any ``rho`` values exist.  In particular it cannot be used to reconstruct a
fine topology state from a coarse CFD field.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import numpy as np

from .local_design_mask_memmap import MASK_IDS, build_local_design_mask_memmaps
from .local_design_stl_roles import local_design_stl_role_classifier
from .localized_design_state_manifest import LocalizedDesignGrid
from .problem_spec import ProblemSpec, canonical_local_design_grid, load_problem_spec, problem_spec_sha256


LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION = 1
LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND = "local_design_geometry_mask_snapshot"
LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME = "local_geometry_masks.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MASK_DTYPE = np.dtype(np.bool_)
_CHUNK_CELLS = 1_048_576


@dataclass(frozen=True)
class LocalDesignGeometryMaskArtifact:
    """One portable, immutable bool mask in a geometry snapshot."""

    artifact_id: str
    relative_path: str
    byte_sha256: str
    dtype: str
    shape: tuple[int, ...]
    true_count: int


@dataclass(frozen=True)
class LocalDesignGeometryMaskSnapshot:
    """Metadata for STL-derived masks, with no mutable topology state."""

    path: Path
    schema_version: int
    kind: str
    problem_spec_sha256: str
    grid: LocalizedDesignGrid
    grid_sha256: str
    topology_resolution: Mapping[str, int]
    classifier_regions: Mapping[str, Mapping[str, Any]]
    masks: Mapping[str, LocalDesignGeometryMaskArtifact]

    @property
    def sha256(self) -> str:
        return local_design_geometry_mask_snapshot_sha256(self)


@dataclass(frozen=True)
class VerifiedLocalDesignGeometryMaskSnapshot:
    snapshot: LocalDesignGeometryMaskSnapshot


def create_local_design_geometry_mask_snapshot(
    problem: ProblemSpec | str | Path,
    *,
    output_dir: str | Path,
    z_chunk_size: int = 1,
    containment_chunk_size: int = 65_536,
) -> VerifiedLocalDesignGeometryMaskSnapshot:
    """Classify declared STL roles and atomically publish immutable masks.

    ``output_dir`` must not already exist.  Both the mask arrays and the
    manifest are constructed below a private sibling directory, verified by
    streaming memory maps, then published by one directory rename.  A visible
    snapshot can therefore never be a mask-only partial result.
    """

    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not isinstance(spec, ProblemSpec):
        raise ValueError("problem must be ProblemSpec or a problem specification path")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing local geometry snapshot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    classifier = local_design_stl_role_classifier(spec, containment_chunk_size=containment_chunk_size)
    source_grid = canonical_local_design_grid(spec)
    grid = LocalizedDesignGrid(
        origin=tuple(float(value) for value in source_grid.origin),
        spacing=tuple(float(value) for value in source_grid.spacing),
        cell_shape=tuple(int(value) for value in source_grid.cell_shape),
        cell_order=source_grid.cell_order,
    )
    if classifier.grid != source_grid:
        raise ValueError("STL role classifier grid does not match canonical local design grid")

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        artifacts = build_local_design_mask_memmaps(
            grid,
            output_dir=staging / "masks",
            role_containment=classifier.as_role_containment(),
            z_chunk_size=z_chunk_size,
            require_active=True,
            require_root=True,
        )
        snapshot_path = staging / LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME
        snapshot = LocalDesignGeometryMaskSnapshot(
            path=snapshot_path,
            schema_version=LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION,
            kind=LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND,
            problem_spec_sha256=problem_spec_sha256(spec),
            grid=grid,
            grid_sha256=grid.sha256,
            topology_resolution=_topology_resolution(spec),
            classifier_regions=_canonical_regions(classifier.provenance_metadata),
            masks={
                identifier: _make_mask_artifact(
                    identifier, artifacts.paths[identifier], staging, grid.cell_count
                )
                for identifier in MASK_IDS
            },
        )
        write_local_design_geometry_mask_snapshot(snapshot)
        validate_local_design_geometry_mask_snapshot(snapshot)
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite existing local geometry snapshot: {destination}")
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    return load_and_verify_local_design_geometry_mask_snapshot(
        destination / LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME,
        expected_problem_spec_sha256=problem_spec_sha256(spec),
    )


def write_local_design_geometry_mask_snapshot(snapshot: LocalDesignGeometryMaskSnapshot) -> Path:
    """Streaming-validate then write deterministic snapshot metadata."""

    validate_local_design_geometry_mask_snapshot(snapshot)
    snapshot.path.write_text(
        json.dumps(_snapshot_to_dict(snapshot), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return snapshot.path


def read_local_design_geometry_mask_snapshot(path: str | Path) -> LocalDesignGeometryMaskSnapshot:
    manifest_path = _snapshot_path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read local design geometry snapshot: {manifest_path}") from exc
    return _snapshot_from_dict(manifest_path, raw)


def validate_local_design_geometry_mask_snapshot(
    snapshot: LocalDesignGeometryMaskSnapshot,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalDesignGeometryMaskSnapshot:
    """Fail closed unless every artifact and mask relationship is intact."""

    _validate_metadata(snapshot)
    if expected_problem_spec_sha256 is not None:
        _sha256(expected_problem_spec_sha256, "expected_problem_spec_sha256")
        if snapshot.problem_spec_sha256 != expected_problem_spec_sha256:
            raise ValueError("local design geometry snapshot problem_spec_sha256 does not match")
    arrays = {identifier: _verify_mask(snapshot, snapshot.masks[identifier]) for identifier in MASK_IDS}
    _validate_mask_relationships(arrays)
    # _verify_mask has already streamed the file and compared this count to
    # metadata.  Do not call np.any on the full 87M-cell memmap here.
    if snapshot.masks["active_design_mask"].true_count == 0:
        raise ValueError("local design geometry snapshot active_design_mask is empty")
    if snapshot.masks["root_mask"].true_count == 0:
        raise ValueError("local design geometry snapshot root_mask is empty")
    return VerifiedLocalDesignGeometryMaskSnapshot(snapshot=snapshot)


def load_and_verify_local_design_geometry_mask_snapshot(
    path: str | Path,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalDesignGeometryMaskSnapshot:
    return validate_local_design_geometry_mask_snapshot(
        read_local_design_geometry_mask_snapshot(path),
        expected_problem_spec_sha256=expected_problem_spec_sha256,
    )


def local_design_geometry_mask_snapshot_sha256(snapshot: LocalDesignGeometryMaskSnapshot) -> str:
    _validate_metadata(snapshot)
    return _sha256_json(_snapshot_to_dict(snapshot))


def _make_mask_artifact(identifier: str, path: Path, root: Path, count: int) -> LocalDesignGeometryMaskArtifact:
    array = _load_mask(path, identifier)
    _validate_mask_layout(array, count, identifier)
    return LocalDesignGeometryMaskArtifact(
        artifact_id=identifier,
        relative_path=_relative_path(root, path),
        byte_sha256=_sha256_file(path),
        dtype=array.dtype.name,
        shape=tuple(int(value) for value in array.shape),
        true_count=_stream_true_count(array),
    )


def _verify_mask(snapshot: LocalDesignGeometryMaskSnapshot, artifact: LocalDesignGeometryMaskArtifact) -> np.ndarray:
    path = _resolve_relative_path(snapshot.path.parent, artifact.relative_path)
    if not path.is_file() or path.suffix.lower() != ".npy":
        raise ValueError(f"local design geometry mask is missing or invalid: {artifact.relative_path}")
    if _sha256_file(path) != artifact.byte_sha256:
        raise ValueError(f"local design geometry mask hash mismatch: {artifact.artifact_id}")
    array = _load_mask(path, artifact.artifact_id)
    _validate_mask_layout(array, snapshot.grid.cell_count, artifact.artifact_id)
    if array.dtype.name != artifact.dtype or tuple(array.shape) != artifact.shape:
        raise ValueError(f"local design geometry mask metadata does not match file: {artifact.artifact_id}")
    if _stream_true_count(array) != artifact.true_count:
        raise ValueError(f"local design geometry mask true_count does not match file: {artifact.artifact_id}")
    return array


def _validate_mask_relationships(masks: Mapping[str, np.ndarray]) -> None:
    active = masks["active_design_mask"]
    forbidden = masks["forbidden_mask"]
    fixed = masks["fixed_solid_mask"]
    root = masks["root_mask"]
    # Four synchronized slices preserve the writer's relationships without
    # allocating an N-cell temporary boolean vector for any expression.
    for start in range(0, active.size, _CHUNK_CELLS):
        stop = min(active.size, start + _CHUNK_CELLS)
        active_chunk = active[start:stop]
        forbidden_chunk = forbidden[start:stop]
        fixed_chunk = fixed[start:stop]
        root_chunk = root[start:stop]
        if np.any(active_chunk & forbidden_chunk):
            raise ValueError("active_design_mask must not overlap forbidden_mask")
        if np.any(active_chunk & fixed_chunk):
            raise ValueError("active_design_mask must not overlap fixed_solid_mask")
        if np.any(forbidden_chunk & fixed_chunk):
            raise ValueError("forbidden_mask must not overlap fixed_solid_mask")
        if np.any(root_chunk & ~fixed_chunk):
            raise ValueError("root_mask must be a subset of fixed_solid_mask")


def _snapshot_to_dict(snapshot: LocalDesignGeometryMaskSnapshot) -> dict[str, Any]:
    return {
        "schema_version": snapshot.schema_version,
        "kind": snapshot.kind,
        "problem_spec_sha256": snapshot.problem_spec_sha256,
        "grid": {
            "kind": "uniform_cartesian_local_design_grid",
            "origin": list(snapshot.grid.origin),
            "spacing": list(snapshot.grid.spacing),
            "cell_shape": list(snapshot.grid.cell_shape),
            "cell_order": snapshot.grid.cell_order,
        },
        "grid_sha256": snapshot.grid_sha256,
        "topology_resolution": dict(snapshot.topology_resolution),
        "classifier_regions": {key: dict(snapshot.classifier_regions[key]) for key in sorted(snapshot.classifier_regions)},
        "masks": {
            identifier: {
                "relative_path": snapshot.masks[identifier].relative_path,
                "byte_sha256": snapshot.masks[identifier].byte_sha256,
                "dtype": snapshot.masks[identifier].dtype,
                "shape": list(snapshot.masks[identifier].shape),
                "true_count": snapshot.masks[identifier].true_count,
            }
            for identifier in MASK_IDS
        },
    }


def _snapshot_from_dict(path: Path, raw: Any) -> LocalDesignGeometryMaskSnapshot:
    data = _mapping(raw, "local design geometry snapshot")
    _exact_keys(data, {"schema_version", "kind", "problem_spec_sha256", "grid", "grid_sha256", "topology_resolution", "classifier_regions", "masks"}, "local design geometry snapshot")
    if _int(data["schema_version"], "schema_version") != LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported local design geometry snapshot schema_version")
    if data["kind"] != LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND:
        raise ValueError("Unsupported local design geometry snapshot kind")
    grid = _grid_from_dict(data["grid"])
    grid_sha256 = _sha256(data["grid_sha256"], "grid_sha256")
    if grid_sha256 != grid.sha256:
        raise ValueError("local design geometry snapshot grid_sha256 does not match grid geometry")
    topology_resolution = _topology_from_dict(data["topology_resolution"])
    regions = _regions_from_dict(data["classifier_regions"])
    masks_raw = _mapping(data["masks"], "masks")
    if set(masks_raw) != set(MASK_IDS):
        raise ValueError(f"masks must contain exactly {list(MASK_IDS)!r}")
    masks: dict[str, LocalDesignGeometryMaskArtifact] = {}
    for identifier in MASK_IDS:
        item = _mapping(masks_raw[identifier], f"mask {identifier}")
        _exact_keys(item, {"relative_path", "byte_sha256", "dtype", "shape", "true_count"}, f"mask {identifier}")
        shape = _shape(item["shape"], f"mask {identifier}.shape")
        masks[identifier] = LocalDesignGeometryMaskArtifact(
            artifact_id=identifier,
            relative_path=_safe_relative_path(item["relative_path"], f"mask {identifier}.relative_path"),
            byte_sha256=_sha256(item["byte_sha256"], f"mask {identifier}.byte_sha256"),
            dtype=_text(item["dtype"], f"mask {identifier}.dtype"),
            shape=shape,
            true_count=_nonnegative_int(item["true_count"], f"mask {identifier}.true_count"),
        )
    return LocalDesignGeometryMaskSnapshot(
        path=path,
        schema_version=LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION,
        kind=LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND,
        problem_spec_sha256=_sha256(data["problem_spec_sha256"], "problem_spec_sha256"),
        grid=grid,
        grid_sha256=grid_sha256,
        topology_resolution=topology_resolution,
        classifier_regions=regions,
        masks=masks,
    )


def _validate_metadata(snapshot: LocalDesignGeometryMaskSnapshot) -> None:
    if not isinstance(snapshot, LocalDesignGeometryMaskSnapshot):
        raise ValueError("snapshot must be LocalDesignGeometryMaskSnapshot")
    if snapshot.schema_version != LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION or snapshot.kind != LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND:
        raise ValueError("local design geometry snapshot schema binding is invalid")
    _sha256(snapshot.problem_spec_sha256, "problem_spec_sha256")
    if not isinstance(snapshot.grid, LocalizedDesignGrid) or snapshot.grid_sha256 != snapshot.grid.sha256:
        raise ValueError("local design geometry snapshot grid binding is invalid")
    _topology_from_dict(snapshot.topology_resolution)
    _regions_from_dict(snapshot.classifier_regions)
    if set(snapshot.masks) != set(MASK_IDS):
        raise ValueError(f"masks must contain exactly {list(MASK_IDS)!r}")
    for identifier in MASK_IDS:
        artifact = snapshot.masks[identifier]
        if not isinstance(artifact, LocalDesignGeometryMaskArtifact) or artifact.artifact_id != identifier:
            raise ValueError(f"local design geometry mask metadata is invalid: {identifier}")
        _safe_relative_path(artifact.relative_path, f"mask {identifier}.relative_path")
        _sha256(artifact.byte_sha256, f"mask {identifier}.byte_sha256")
        if artifact.dtype != _MASK_DTYPE.name or artifact.shape != (snapshot.grid.cell_count,) or artifact.true_count < 0:
            raise ValueError(f"local design geometry mask metadata has wrong layout: {identifier}")


def _topology_resolution(spec: ProblemSpec) -> dict[str, int]:
    if spec.design_grid is None:
        raise ValueError("local geometry snapshot requires design_grid")
    resolution = spec.design_grid.topology_resolution
    return {
        "minimum_solid_width_cells": resolution.minimum_solid_width_cells,
        "minimum_void_width_cells": resolution.minimum_void_width_cells,
        "minimum_gap_cells": resolution.minimum_gap_cells,
        "erosion_radius_cells": resolution.erosion_radius_cells,
    }


def _topology_from_dict(raw: Any) -> dict[str, int]:
    data = _mapping(raw, "topology_resolution")
    expected = {"minimum_solid_width_cells", "minimum_void_width_cells", "minimum_gap_cells", "erosion_radius_cells"}
    _exact_keys(data, expected, "topology_resolution")
    return {key: _positive_int(data[key], f"topology_resolution.{key}") for key in sorted(expected)}


def _canonical_regions(raw: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    # Round-trip through the parser now, so the generated artifact obeys the
    # same strict portable contract as an untrusted one read later.
    return {key: dict(value) for key, value in _regions_from_dict(raw).items()}


def _regions_from_dict(raw: Any) -> dict[str, Mapping[str, Any]]:
    data = _mapping(raw, "classifier_regions")
    if not data:
        raise ValueError("classifier_regions must not be empty")
    result: dict[str, Mapping[str, Any]] = {}
    for identifier, value in data.items():
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("classifier region id must be non-empty text")
        item = _mapping(value, f"classifier region {identifier}")
        _exact_keys(item, {"role", "relative_source_path", "resolved_relative_source_path", "sha256", "bounds_m"}, f"classifier region {identifier}")
        bounds = _mapping(item["bounds_m"], f"classifier region {identifier}.bounds_m")
        _exact_keys(bounds, {"lower", "upper"}, f"classifier region {identifier}.bounds_m")
        lower = _vector3(bounds["lower"], f"classifier region {identifier}.bounds_m.lower")
        upper = _vector3(bounds["upper"], f"classifier region {identifier}.bounds_m.upper")
        if any(low > high for low, high in zip(lower, upper, strict=True)):
            raise ValueError(f"classifier region {identifier}.bounds_m lower must not exceed upper")
        result[identifier] = {
            "role": _text(item["role"], f"classifier region {identifier}.role"),
            "relative_source_path": _safe_relative_path(item["relative_source_path"], f"classifier region {identifier}.relative_source_path"),
            "resolved_relative_source_path": _safe_relative_path(item["resolved_relative_source_path"], f"classifier region {identifier}.resolved_relative_source_path"),
            "sha256": _sha256(item["sha256"], f"classifier region {identifier}.sha256"),
            "bounds_m": {"lower": list(lower), "upper": list(upper)},
        }
    return result


def _grid_from_dict(raw: Any) -> LocalizedDesignGrid:
    data = _mapping(raw, "grid")
    _exact_keys(data, {"kind", "origin", "spacing", "cell_shape", "cell_order"}, "grid")
    if data["kind"] != "uniform_cartesian_local_design_grid":
        raise ValueError("local design geometry snapshot grid.kind is unsupported")
    return LocalizedDesignGrid(
        origin=_vector3(data["origin"], "grid.origin"),
        spacing=_vector3(data["spacing"], "grid.spacing"),
        cell_shape=_cell_shape(data["cell_shape"], "grid.cell_shape"),
        cell_order=_text(data["cell_order"], "grid.cell_order"),
    )


def _load_mask(path: Path, identifier: str) -> np.ndarray:
    try:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to load local design geometry mask: {identifier}") from exc
    if not isinstance(array, np.ndarray):
        raise ValueError(f"local design geometry mask is not an array: {identifier}")
    return array


def _validate_mask_layout(array: np.ndarray, count: int, identifier: str) -> None:
    if array.dtype != _MASK_DTYPE or array.shape != (count,):
        raise ValueError(f"{identifier} must have dtype bool and shape ({count},)")


def _stream_true_count(array: np.ndarray) -> int:
    total = 0
    for start in range(0, array.size, _CHUNK_CELLS):
        total += int(np.count_nonzero(array[start : start + _CHUNK_CELLS]))
    return total


def _snapshot_path(path: str | Path) -> Path:
    target = Path(path)
    if target.name != LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME:
        raise ValueError(f"local design geometry snapshot path must be named {LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME}")
    return target


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("local design geometry mask must be below snapshot directory") from exc


def _resolve_relative_path(root: Path, value: str) -> Path:
    relative = _safe_relative_path(value, "local design geometry mask path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("local design geometry mask path escapes snapshot directory") from exc
    return candidate


def _safe_relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or path.drive or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{context} must be a safe relative path")
    return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{context} has unsupported or missing fields")


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be non-empty text")
    return value


def _sha256(value: Any, context: str) -> str:
    text = _text(value, context)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{context} must be a lower-case SHA-256 hex digest")
    return text


def _int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _positive_int(value: Any, context: str) -> int:
    result = _int(value, context)
    if result <= 0:
        raise ValueError(f"{context} must be positive")
    return result


def _nonnegative_int(value: Any, context: str) -> int:
    result = _int(value, context)
    if result < 0:
        raise ValueError(f"{context} must be non-negative")
    return result


def _shape(value: Any, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{context} must be a non-empty positive-integer list")
    return tuple(value)


def _cell_shape(value: Any, context: str) -> tuple[int, int, int]:
    shape = _shape(value, context)
    if len(shape) != 3:
        raise ValueError(f"{context} must have three positive integers")
    return shape  # type: ignore[return-value]


def _vector3(value: Any, context: str) -> tuple[float, float, float]:
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a three-value numeric vector") from exc
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError(f"{context} must be a three-value finite vector")
    return tuple(float(item) for item in vector)  # type: ignore[return-value]


__all__ = [
    "LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME",
    "LOCAL_DESIGN_GEOMETRY_SNAPSHOT_KIND",
    "LOCAL_DESIGN_GEOMETRY_SNAPSHOT_SCHEMA_VERSION",
    "LocalDesignGeometryMaskArtifact",
    "LocalDesignGeometryMaskSnapshot",
    "VerifiedLocalDesignGeometryMaskSnapshot",
    "create_local_design_geometry_mask_snapshot",
    "load_and_verify_local_design_geometry_mask_snapshot",
    "local_design_geometry_mask_snapshot_sha256",
    "read_local_design_geometry_mask_snapshot",
    "validate_local_design_geometry_mask_snapshot",
    "write_local_design_geometry_mask_snapshot",
]
