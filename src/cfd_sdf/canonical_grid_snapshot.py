"""Provenance-bound canonical fixed-grid snapshots.

The OpenFOAM-to-canonical-grid transfer is only meaningful when its target
grid and every topology mask are immutable inputs.  This module persists that
target contract independently of a solver result.  A snapshot binds a native
problem specification to an axis-aligned, x-fastest cell grid and four
``uint8`` binary mask artifacts:

* ``active_design_mask``;
* ``forbidden_mask``;
* ``fixed_solid_mask``; and
* ``root_mask``.

The JSON records artifact paths relative to itself and hashes their exact NPY
bytes.  Verification deliberately re-loads the artifacts and rejects an
unknown path, dtype, shape, non-binary value, or hash mismatch.  It is not a
geometry generator: callers must first build the canonical grid and masks from
the declared STL/SDF workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any

import numpy as np

from .openfoam_grid_transfer import CANONICAL_CELL_ORDER, UniformCartesianCellGrid
from .problem_spec import ProblemSpec, problem_spec_sha256


CANONICAL_GRID_SNAPSHOT_SCHEMA_VERSION = 1
CANONICAL_GRID_SNAPSHOT_KIND = "canonical_fixed_grid_snapshot"
CANONICAL_MASK_IDS = (
    "active_design_mask",
    "forbidden_mask",
    "fixed_solid_mask",
    "root_mask",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MASK_DTYPE = np.dtype(np.uint8)


@dataclass(frozen=True)
class CanonicalMaskArtifact:
    """One exact binary mask artifact referenced by a snapshot."""

    mask_id: str
    relative_path: str
    sha256: str
    dtype: str
    shape: tuple[int, ...]
    true_count: int


@dataclass(frozen=True)
class CanonicalGridSnapshot:
    """Parsed snapshot metadata, without trusting its artifact contents."""

    path: Path
    schema_version: int
    kind: str
    problem_id: str
    problem_spec_sha256: str
    execution_ready: bool
    grid_kind: str
    voxel_size_m: float
    grid: UniformCartesianCellGrid
    grid_sha256: str
    masks: Mapping[str, CanonicalMaskArtifact]


@dataclass(frozen=True)
class VerifiedCanonicalGridSnapshot:
    """A snapshot after its problem binding and all masks were verified."""

    snapshot: CanonicalGridSnapshot
    masks: Mapping[str, np.ndarray]


def write_canonical_grid_snapshot(
    spec: ProblemSpec,
    *,
    grid: UniformCartesianCellGrid,
    masks: Mapping[str, np.ndarray],
    path: str | Path,
    mask_directory_name: str | None = None,
) -> Path:
    """Write a snapshot plus its canonical binary mask artifacts.

    ``masks`` must contain exactly :data:`CANONICAL_MASK_IDS`.  Each input is
    a flat, x-fastest ``uint8`` vector containing only zero and one.  The
    writer applies the same validation as the reader before persisting data so
    a successful write is immediately verifiable.
    """

    _validate_spec_grid_binding(spec, grid)
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ValueError("canonical grid snapshot path must end in .json")
    target.parent.mkdir(parents=True, exist_ok=True)
    directory_name = mask_directory_name or f"{target.stem}_masks"
    _validate_relative_directory_name(directory_name)
    mask_directory = target.parent / directory_name
    mask_directory.mkdir(parents=True, exist_ok=True)

    _require_exact_mask_ids(masks)
    artifacts: dict[str, dict[str, Any]] = {}
    for mask_id in CANONICAL_MASK_IDS:
        values = _validate_mask_values(masks[mask_id], grid.cell_count, mask_id)
        artifact_path = mask_directory / f"{mask_id}.npy"
        np.save(artifact_path, values, allow_pickle=False)
        relative_path = _relative_artifact_path(target.parent, artifact_path)
        artifact_bytes = artifact_path.read_bytes()
        artifacts[mask_id] = {
            "path": relative_path,
            "sha256": _sha256_bytes(artifact_bytes),
            "dtype": _MASK_DTYPE.name,
            "shape": [grid.cell_count],
            "true_count": int(values.sum(dtype=np.int64)),
        }

    payload = {
        "schema_version": CANONICAL_GRID_SNAPSHOT_SCHEMA_VERSION,
        "kind": CANONICAL_GRID_SNAPSHOT_KIND,
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "grid": {
            "kind": spec.grid.kind,
            "voxel_size_m": float(spec.grid.voxel_size_m),
            "lower_origin_m": list(grid.origin),
            "spacing_m": list(grid.spacing),
            "cell_shape": list(grid.cell_shape),
            "cell_order": CANONICAL_CELL_ORDER,
            "sha256": grid.sha256,
        },
        "masks": artifacts,
    }
    target.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    # Fail immediately rather than returning a path for an unusable snapshot.
    verify_canonical_grid_snapshot(read_canonical_grid_snapshot(target), spec)
    return target


def read_canonical_grid_snapshot(path: str | Path) -> CanonicalGridSnapshot:
    """Parse snapshot JSON shape without accepting its mask contents."""

    snapshot_path = Path(path)
    data = _read_json_mapping(snapshot_path)
    schema_version = data.get("schema_version")
    if schema_version != CANONICAL_GRID_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported canonical grid snapshot schema_version: "
            f"{schema_version!r}"
        )
    if data.get("kind") != CANONICAL_GRID_SNAPSHOT_KIND:
        raise ValueError("Invalid canonical grid snapshot kind")
    problem_id = _required_id(data, "problem_id", "canonical grid snapshot")
    problem_hash = _required_sha256(data, "problem_spec_sha256", "canonical grid snapshot")
    execution_ready = data.get("execution_ready")
    if not isinstance(execution_ready, bool):
        raise ValueError("canonical grid snapshot.execution_ready must be boolean")
    raw_grid = _required_mapping(data, "grid", "canonical grid snapshot")
    grid_kind = _required_text(raw_grid, "kind", "canonical grid snapshot.grid")
    if grid_kind != "uniform_cartesian":
        raise ValueError("canonical grid snapshot.grid.kind must be uniform_cartesian")
    voxel_size_m = _positive_float(raw_grid.get("voxel_size_m"), "grid.voxel_size_m")
    grid = UniformCartesianCellGrid(
        origin=_vector3(raw_grid.get("lower_origin_m"), "grid.lower_origin_m"),
        spacing=_vector3(raw_grid.get("spacing_m"), "grid.spacing_m"),
        cell_shape=_cell_shape(raw_grid.get("cell_shape"), "grid.cell_shape"),
        cell_order=_required_text(raw_grid, "cell_order", "canonical grid snapshot.grid"),
    )
    grid_sha256 = _required_sha256(raw_grid, "sha256", "canonical grid snapshot.grid")
    if grid_sha256 != grid.sha256:
        raise ValueError("canonical grid snapshot.grid.sha256 does not match grid geometry")
    raw_masks = _required_mapping(data, "masks", "canonical grid snapshot")
    _require_exact_mask_ids(raw_masks)
    masks: dict[str, CanonicalMaskArtifact] = {}
    for mask_id in CANONICAL_MASK_IDS:
        raw_artifact = _mapping_value(raw_masks[mask_id], f"masks.{mask_id}")
        relative_path = _safe_relative_path(
            _required_text(raw_artifact, "path", f"masks.{mask_id}"),
            f"masks.{mask_id}.path",
        )
        dtype = _required_text(raw_artifact, "dtype", f"masks.{mask_id}")
        if dtype != _MASK_DTYPE.name:
            raise ValueError(f"masks.{mask_id}.dtype must be {_MASK_DTYPE.name!r}")
        shape = _shape(raw_artifact.get("shape"), f"masks.{mask_id}.shape")
        if shape != (grid.cell_count,):
            raise ValueError(
                f"masks.{mask_id}.shape must equal ({grid.cell_count},), got {shape!r}"
            )
        true_count = _nonnegative_int(raw_artifact.get("true_count"), f"masks.{mask_id}.true_count")
        if true_count > grid.cell_count:
            raise ValueError(f"masks.{mask_id}.true_count exceeds grid cell count")
        masks[mask_id] = CanonicalMaskArtifact(
            mask_id=mask_id,
            relative_path=relative_path,
            sha256=_required_sha256(raw_artifact, "sha256", f"masks.{mask_id}"),
            dtype=dtype,
            shape=shape,
            true_count=true_count,
        )
    return CanonicalGridSnapshot(
        path=snapshot_path,
        schema_version=schema_version,
        kind=CANONICAL_GRID_SNAPSHOT_KIND,
        problem_id=problem_id,
        problem_spec_sha256=problem_hash,
        execution_ready=execution_ready,
        grid_kind=grid_kind,
        voxel_size_m=voxel_size_m,
        grid=grid,
        grid_sha256=grid_sha256,
        masks=masks,
    )


def verify_canonical_grid_snapshot(
    snapshot: CanonicalGridSnapshot,
    spec: ProblemSpec,
) -> VerifiedCanonicalGridSnapshot:
    """Fail closed unless snapshot, specification, and all masks agree."""

    if not isinstance(snapshot, CanonicalGridSnapshot):
        raise ValueError("snapshot must be CanonicalGridSnapshot")
    _validate_spec_grid_binding(spec, snapshot.grid)
    if snapshot.problem_id != spec.problem_id:
        raise ValueError("canonical grid snapshot problem_id does not match problem specification")
    expected_hash = problem_spec_sha256(spec)
    if snapshot.problem_spec_sha256 != expected_hash:
        raise ValueError(
            "canonical grid snapshot problem_spec_sha256 does not match problem specification"
        )
    if snapshot.execution_ready != spec.migration.execution_ready:
        raise ValueError(
            "canonical grid snapshot execution_ready does not match problem specification"
        )
    if snapshot.grid_kind != spec.grid.kind:
        raise ValueError("canonical grid snapshot grid.kind does not match problem specification")
    if not isclose(snapshot.voxel_size_m, spec.grid.voxel_size_m, rel_tol=0.0, abs_tol=0.0):
        raise ValueError("canonical grid snapshot voxel_size_m does not match problem specification")
    if snapshot.grid_sha256 != snapshot.grid.sha256:
        raise ValueError("canonical grid snapshot grid hash does not match grid geometry")

    _require_exact_mask_ids(snapshot.masks)
    verified_masks: dict[str, np.ndarray] = {}
    for mask_id in CANONICAL_MASK_IDS:
        artifact = snapshot.masks[mask_id]
        artifact_path = _resolve_artifact_path(snapshot.path.parent, artifact.relative_path)
        if not artifact_path.is_file():
            raise ValueError(f"canonical grid snapshot mask artifact is missing: {artifact.relative_path}")
        payload = artifact_path.read_bytes()
        if _sha256_bytes(payload) != artifact.sha256:
            raise ValueError(f"canonical grid snapshot mask hash mismatch: {mask_id}")
        try:
            values = np.load(artifact_path, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Unable to load canonical grid snapshot mask: {mask_id}") from exc
        values = _validate_mask_values(values, snapshot.grid.cell_count, mask_id)
        if tuple(values.shape) != artifact.shape or values.dtype.name != artifact.dtype:
            raise ValueError(f"canonical grid snapshot mask metadata does not match artifact: {mask_id}")
        if int(values.sum(dtype=np.int64)) != artifact.true_count:
            raise ValueError(f"canonical grid snapshot mask true_count does not match artifact: {mask_id}")
        values.setflags(write=False)
        verified_masks[mask_id] = values
    return VerifiedCanonicalGridSnapshot(snapshot=snapshot, masks=verified_masks)


def load_and_verify_canonical_grid_snapshot(
    path: str | Path,
    spec: ProblemSpec,
) -> VerifiedCanonicalGridSnapshot:
    """Read then verify a snapshot in one fail-closed operation."""

    return verify_canonical_grid_snapshot(read_canonical_grid_snapshot(path), spec)


def _validate_spec_grid_binding(spec: ProblemSpec, grid: UniformCartesianCellGrid) -> None:
    if not isinstance(spec, ProblemSpec):
        raise ValueError("spec must be ProblemSpec")
    if spec.grid.kind != "uniform_cartesian":
        raise ValueError("canonical grid snapshots require uniform_cartesian problem grids")
    expected = float(spec.grid.voxel_size_m)
    if not isfinite(expected) or expected <= 0.0:
        raise ValueError("problem specification has an invalid voxel_size_m")
    if not np.array_equal(np.asarray(grid.spacing, dtype=np.float64), np.full(3, expected)):
        raise ValueError("canonical grid spacing must equal problem voxel_size_m on all axes")


def _require_exact_mask_ids(values: Mapping[str, Any]) -> None:
    if not isinstance(values, Mapping):
        raise ValueError("canonical grid snapshot masks must be a mapping")
    expected = set(CANONICAL_MASK_IDS)
    actual = set(values)
    if actual != expected:
        missing = sorted(expected.difference(actual))
        extra = sorted(actual.difference(expected))
        raise ValueError(
            "canonical grid snapshot masks must contain exactly "
            f"{list(CANONICAL_MASK_IDS)!r}; missing={missing!r}, extra={extra!r}"
        )


def _validate_mask_values(values: np.ndarray, count: int, mask_id: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (count,):
        raise ValueError(f"{mask_id} must have shape ({count},)")
    if array.dtype != _MASK_DTYPE:
        raise ValueError(f"{mask_id} must have dtype {_MASK_DTYPE.name}")
    if not np.isfinite(array).all():
        raise ValueError(f"{mask_id} must contain only finite values")
    if not np.logical_or(array == 0, array == 1).all():
        raise ValueError(f"{mask_id} must contain only binary values 0 or 1")
    return np.ascontiguousarray(array, dtype=_MASK_DTYPE)


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read canonical grid snapshot: {path}") from exc
    return _mapping_value(raw, "canonical grid snapshot")


def _required_mapping(data: Mapping[str, Any], key: str, context: str) -> Mapping[str, Any]:
    if key not in data:
        raise ValueError(f"{context} is missing {key}")
    return _mapping_value(data[key], f"{context}.{key}")


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _required_text(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{key} must be non-empty text")
    return value


def _required_id(data: Mapping[str, Any], key: str, context: str) -> str:
    value = _required_text(data, key, context)
    if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is None:
        raise ValueError(f"{context}.{key} must be a lower-case identifier")
    return value


def _required_sha256(data: Mapping[str, Any], key: str, context: str) -> str:
    value = _required_text(data, key, context)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{context}.{key} must be a lower-case SHA-256 hex digest")
    return value


def _positive_float(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be a positive finite number")
    result = float(value)
    if not isfinite(result) or result <= 0.0:
        raise ValueError(f"{context} must be a positive finite number")
    return result


def _vector3(value: Any, context: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{context} must be a three-value list")
    result = tuple(_finite_float(item, context) for item in value)
    return result  # type: ignore[return-value]


def _finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must contain finite numbers")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{context} must contain finite numbers")
    return result


def _cell_shape(value: Any, context: str) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{context} must be a three-value list")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{context} must contain positive integers")
    return tuple(value)  # type: ignore[return-value]


def _shape(value: Any, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context} must be a non-empty integer list")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{context} must contain positive integers")
    return tuple(value)


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a non-negative integer")
    return value


def _validate_relative_directory_name(value: str) -> None:
    candidate = Path(value) if isinstance(value, str) else None
    if (
        candidate is None
        or not value
        or candidate.is_absolute()
        or candidate.drive
        or len(candidate.parts) != 1
    ):
        raise ValueError("mask_directory_name must be a single relative directory name")
    if value in {".", ".."}:
        raise ValueError("mask_directory_name must not be dot traversal")


def _safe_relative_path(value: str, context: str) -> str:
    path = Path(value)
    if (
        path.is_absolute()
        or path.drive
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{context} must be a safe relative artifact path")
    return path.as_posix()


def _relative_artifact_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("canonical grid snapshot mask artifact must be below snapshot directory") from exc


def _resolve_artifact_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("canonical grid snapshot mask path escapes snapshot directory") from exc
    return candidate


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "CANONICAL_GRID_SNAPSHOT_KIND",
    "CANONICAL_GRID_SNAPSHOT_SCHEMA_VERSION",
    "CANONICAL_MASK_IDS",
    "CanonicalGridSnapshot",
    "CanonicalMaskArtifact",
    "VerifiedCanonicalGridSnapshot",
    "load_and_verify_canonical_grid_snapshot",
    "read_canonical_grid_snapshot",
    "verify_canonical_grid_snapshot",
    "write_canonical_grid_snapshot",
]
