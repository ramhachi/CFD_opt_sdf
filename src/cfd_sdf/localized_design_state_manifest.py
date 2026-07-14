"""Portable, fail-closed local canonical design-state artifacts.

This is intentionally a new contract for the localized G3 design grid.  It
does not reuse ``DensityDesignState`` or the canonical fixed-grid snapshot
schema: those records have different authority and resolution semantics.

The manifest references pre-existing ``.npy`` files instead of materialising
large arrays itself.  Verification therefore hashes files and inspects them
using read-only NumPy memory maps in bounded chunks.  A valid state is a
float64, x-fastest vector on the declared local grid; every value outside the
active design mask is *exactly* zero.  This strict rule prevents fixed or
forbidden cells from acquiring untracked topology density.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np


LOCALIZED_DESIGN_STATE_MANIFEST_SCHEMA_VERSION = 1
LOCALIZED_DESIGN_STATE_MANIFEST_KIND = "localized_design_state_manifest"
LOCALIZED_DESIGN_GRID_KIND = "uniform_cartesian_local_design_grid"
LOCALIZED_DESIGN_MASK_IDS = (
    "active_design_mask",
    "forbidden_mask",
    "fixed_solid_mask",
    "root_mask",
)
LOCALIZED_DESIGN_STATE_IDS = ("rho", "rho_filtered", "rho_projected")
CANONICAL_CELL_ORDER = "x-fastest"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MASK_DTYPE = np.dtype(np.bool_)
_STATE_DTYPE = np.dtype(np.float64)
_CHUNK_CELLS = 1_048_576


@dataclass(frozen=True)
class LocalizedDesignGrid:
    """The independently-versioned local Cartesian design-grid contract."""

    origin: tuple[float, float, float]
    spacing: tuple[float, float, float]
    cell_shape: tuple[int, int, int]
    cell_order: str = CANONICAL_CELL_ORDER

    def __post_init__(self) -> None:
        origin = _finite_vector(self.origin, "origin")
        spacing = _finite_vector(self.spacing, "spacing")
        if np.any(spacing <= 0.0):
            raise ValueError("spacing must contain three positive finite values")
        shape = _cell_shape(self.cell_shape, "cell_shape")
        if self.cell_order != CANONICAL_CELL_ORDER:
            raise ValueError(f"cell_order must be {CANONICAL_CELL_ORDER!r}")
        object.__setattr__(self, "origin", tuple(float(value) for value in origin))
        object.__setattr__(self, "spacing", tuple(float(value) for value in spacing))
        object.__setattr__(self, "cell_shape", shape)

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.cell_shape, dtype=np.int64))

    @property
    def sha256(self) -> str:
        """Hash all geometry and ordering fields used to index state values."""

        return _sha256_json(
            {
                "schema_version": 1,
                "kind": LOCALIZED_DESIGN_GRID_KIND,
                "origin": list(self.origin),
                "spacing": list(self.spacing),
                "cell_shape": list(self.cell_shape),
                "cell_order": self.cell_order,
            }
        )


@dataclass(frozen=True)
class LocalizedArrayArtifact:
    """Metadata for one immutable local mask or design-state array."""

    artifact_id: str
    relative_path: str
    byte_sha256: str
    dtype: str
    shape: tuple[int, ...]
    true_count: int | None = None


@dataclass(frozen=True)
class LocalizedDesignStateManifest:
    """Parsed local state manifest.  Call :func:`validate` before use."""

    path: Path
    schema_version: int
    kind: str
    problem_spec_sha256: str
    grid: LocalizedDesignGrid
    grid_sha256: str
    masks: Mapping[str, LocalizedArrayArtifact]
    states: Mapping[str, LocalizedArrayArtifact]
    filter_config_sha256: str
    projection_config_sha256: str

    @property
    def sha256(self) -> str:
        """Deterministic digest of the manifest metadata (not its JSON layout)."""

        return localized_design_state_manifest_sha256(self)


@dataclass(frozen=True)
class VerifiedLocalizedDesignStateManifest:
    """A manifest whose files and topology-state invariants were verified."""

    manifest: LocalizedDesignStateManifest


def create_localized_design_state_manifest(
    *,
    path: str | Path,
    problem_spec_sha256: str,
    grid: LocalizedDesignGrid,
    masks: Mapping[str, str | Path],
    states: Mapping[str, str | Path],
    filter_config_sha256: str,
    projection_config_sha256: str,
) -> LocalizedDesignStateManifest:
    """Create metadata for pre-existing local ``.npy`` artifacts.

    The supplied arrays are never copied or rewritten.  They must be below
    the manifest directory so a copied manifest directory remains portable.
    Creation performs the same streaming verification as later reads.
    """

    manifest_path = _manifest_path(path)
    _required_sha256(problem_spec_sha256, "problem_spec_sha256")
    _required_sha256(filter_config_sha256, "filter_config_sha256")
    _required_sha256(projection_config_sha256, "projection_config_sha256")
    if not isinstance(grid, LocalizedDesignGrid):
        raise ValueError("grid must be LocalizedDesignGrid")
    _require_exact_ids(masks, LOCALIZED_DESIGN_MASK_IDS, "masks")
    _require_exact_ids(states, LOCALIZED_DESIGN_STATE_IDS, "states")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    mask_artifacts = {
        identifier: _make_artifact(
            identifier,
            _artifact_input_path(manifest_path.parent, masks[identifier]),
            manifest_path.parent,
            grid.cell_count,
            True,
        )
        for identifier in LOCALIZED_DESIGN_MASK_IDS
    }
    state_artifacts = {
        identifier: _make_artifact(
            identifier,
            _artifact_input_path(manifest_path.parent, states[identifier]),
            manifest_path.parent,
            grid.cell_count,
            False,
        )
        for identifier in LOCALIZED_DESIGN_STATE_IDS
    }
    manifest = LocalizedDesignStateManifest(
        path=manifest_path,
        schema_version=LOCALIZED_DESIGN_STATE_MANIFEST_SCHEMA_VERSION,
        kind=LOCALIZED_DESIGN_STATE_MANIFEST_KIND,
        problem_spec_sha256=problem_spec_sha256,
        grid=grid,
        grid_sha256=grid.sha256,
        masks=mask_artifacts,
        states=state_artifacts,
        filter_config_sha256=filter_config_sha256,
        projection_config_sha256=projection_config_sha256,
    )
    validate_localized_design_state_manifest(manifest)
    return manifest


def write_localized_design_state_manifest(manifest: LocalizedDesignStateManifest) -> Path:
    """Validate then write deterministic JSON without modifying any arrays."""

    validate_localized_design_state_manifest(manifest)
    manifest.path.parent.mkdir(parents=True, exist_ok=True)
    manifest.path.write_text(
        json.dumps(_manifest_to_dict(manifest), sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    return manifest.path


def read_localized_design_state_manifest(path: str | Path) -> LocalizedDesignStateManifest:
    """Parse manifest metadata only; use :func:`validate` before consuming it."""

    manifest_path = _manifest_path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read localized design state manifest: {manifest_path}") from exc
    return _manifest_from_dict(manifest_path, raw)


def validate_localized_design_state_manifest(
    manifest: LocalizedDesignStateManifest,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalizedDesignStateManifest:
    """Fail closed unless all files and local topology invariants match."""

    if not isinstance(manifest, LocalizedDesignStateManifest):
        raise ValueError("manifest must be LocalizedDesignStateManifest")
    _validate_manifest_metadata(manifest)
    if expected_problem_spec_sha256 is not None:
        _required_sha256(expected_problem_spec_sha256, "expected_problem_spec_sha256")
        if manifest.problem_spec_sha256 != expected_problem_spec_sha256:
            raise ValueError("localized design state manifest problem_spec_sha256 does not match")

    verified_masks = {
        identifier: _verify_artifact(manifest, manifest.masks[identifier], True)
        for identifier in LOCALIZED_DESIGN_MASK_IDS
    }
    _validate_mask_relationships(verified_masks)
    active = verified_masks["active_design_mask"]
    for identifier in LOCALIZED_DESIGN_STATE_IDS:
        _verify_artifact(manifest, manifest.states[identifier], False, active_mask=active)
    return VerifiedLocalizedDesignStateManifest(manifest=manifest)


def load_and_verify_localized_design_state_manifest(
    path: str | Path,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalizedDesignStateManifest:
    """Read and fail-closed validate a portable local state artifact."""

    return validate_localized_design_state_manifest(
        read_localized_design_state_manifest(path),
        expected_problem_spec_sha256=expected_problem_spec_sha256,
    )


def localized_design_state_manifest_sha256(manifest: LocalizedDesignStateManifest) -> str:
    """Return the canonical metadata hash used for downstream provenance."""

    if not isinstance(manifest, LocalizedDesignStateManifest):
        raise ValueError("manifest must be LocalizedDesignStateManifest")
    return _sha256_json(_manifest_to_dict(manifest))


def _make_artifact(
    identifier: str,
    path: Path,
    manifest_root: Path,
    cell_count: int,
    is_mask: bool,
) -> LocalizedArrayArtifact:
    array = _load_npy_memmap(path, identifier)
    _validate_array_layout(array, cell_count, is_mask, identifier)
    if is_mask:
        true_count = _stream_mask_true_count(array, identifier)
    else:
        _stream_state_values(array, None, identifier)
        true_count = None
    return LocalizedArrayArtifact(
        artifact_id=identifier,
        relative_path=_relative_artifact_path(manifest_root, path),
        byte_sha256=_sha256_file(path),
        dtype=array.dtype.name,
        shape=tuple(int(value) for value in array.shape),
        true_count=true_count,
    )


def _artifact_input_path(root: Path, value: str | Path) -> Path:
    value_path = Path(value)
    candidate = value_path if value_path.is_absolute() else root / value_path
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("localized design artifact must be below manifest directory") from exc
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError("localized design artifact path must be a safe relative path")
    if resolved.suffix.lower() != ".npy":
        raise ValueError("localized design artifacts must use .npy files")
    if not resolved.is_file():
        raise ValueError(f"localized design artifact is missing: {relative.as_posix()}")
    return resolved


def _manifest_from_dict(path: Path, raw: Any) -> LocalizedDesignStateManifest:
    data = _mapping(raw, "localized design state manifest")
    expected = {
        "schema_version", "kind", "problem_spec_sha256", "grid", "grid_sha256", "masks", "states",
        "filter_config_sha256", "projection_config_sha256",
    }
    _require_exact_keys(data, expected, "localized design state manifest")
    schema_version = _exact_int(data["schema_version"], "localized design state manifest.schema_version")
    if schema_version != LOCALIZED_DESIGN_STATE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported localized design state manifest schema_version: {schema_version}")
    kind = _required_text(data["kind"], "localized design state manifest.kind")
    if kind != LOCALIZED_DESIGN_STATE_MANIFEST_KIND:
        raise ValueError(f"Unsupported localized design state manifest kind: {kind}")
    grid, grid_sha256 = _grid_from_dict(data["grid"], data["grid_sha256"])
    return LocalizedDesignStateManifest(
        path=path,
        schema_version=schema_version,
        kind=kind,
        problem_spec_sha256=_required_sha256(data["problem_spec_sha256"], "problem_spec_sha256"),
        grid=grid,
        grid_sha256=grid_sha256,
        masks=_artifacts_from_dict(data["masks"], LOCALIZED_DESIGN_MASK_IDS, True),
        states=_artifacts_from_dict(data["states"], LOCALIZED_DESIGN_STATE_IDS, False),
        filter_config_sha256=_required_sha256(data["filter_config_sha256"], "filter_config_sha256"),
        projection_config_sha256=_required_sha256(data["projection_config_sha256"], "projection_config_sha256"),
    )


def _manifest_to_dict(manifest: LocalizedDesignStateManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "kind": manifest.kind,
        "problem_spec_sha256": manifest.problem_spec_sha256,
        "grid": {
            "kind": LOCALIZED_DESIGN_GRID_KIND,
            "origin": list(manifest.grid.origin),
            "spacing": list(manifest.grid.spacing),
            "cell_shape": list(manifest.grid.cell_shape),
            "cell_order": manifest.grid.cell_order,
        },
        "grid_sha256": manifest.grid_sha256,
        "masks": {key: _artifact_to_dict(manifest.masks[key]) for key in LOCALIZED_DESIGN_MASK_IDS},
        "states": {key: _artifact_to_dict(manifest.states[key]) for key in LOCALIZED_DESIGN_STATE_IDS},
        "filter_config_sha256": manifest.filter_config_sha256,
        "projection_config_sha256": manifest.projection_config_sha256,
    }


def _artifact_to_dict(artifact: LocalizedArrayArtifact) -> dict[str, Any]:
    result: dict[str, Any] = {
        "relative_path": artifact.relative_path,
        "byte_sha256": artifact.byte_sha256,
        "dtype": artifact.dtype,
        "shape": list(artifact.shape),
    }
    if artifact.true_count is not None:
        result["true_count"] = artifact.true_count
    return result


def _grid_from_dict(raw: Any, grid_sha256: Any) -> tuple[LocalizedDesignGrid, str]:
    data = _mapping(raw, "localized design state manifest.grid")
    _require_exact_keys(data, {"kind", "origin", "spacing", "cell_shape", "cell_order"}, "localized design state manifest.grid")
    if _required_text(data["kind"], "localized design state manifest.grid.kind") != LOCALIZED_DESIGN_GRID_KIND:
        raise ValueError("localized design state manifest.grid.kind is unsupported")
    grid = LocalizedDesignGrid(
        origin=_vector3(data["origin"], "localized design state manifest.grid.origin"),
        spacing=_vector3(data["spacing"], "localized design state manifest.grid.spacing"),
        cell_shape=_cell_shape(data["cell_shape"], "localized design state manifest.grid.cell_shape"),
        cell_order=_required_text(data["cell_order"], "localized design state manifest.grid.cell_order"),
    )
    expected = _required_sha256(grid_sha256, "localized design state manifest.grid_sha256")
    if expected != grid.sha256:
        raise ValueError("localized design state manifest grid_sha256 does not match grid geometry")
    return grid, expected


def _artifacts_from_dict(raw: Any, identifiers: tuple[str, ...], is_mask: bool) -> dict[str, LocalizedArrayArtifact]:
    data = _mapping(raw, "localized design state manifest artifacts")
    _require_exact_ids(data, identifiers, "artifacts")
    result: dict[str, LocalizedArrayArtifact] = {}
    expected_keys = {"relative_path", "byte_sha256", "dtype", "shape", "true_count"} if is_mask else {
        "relative_path", "byte_sha256", "dtype", "shape"
    }
    for identifier in identifiers:
        item = _mapping(data[identifier], f"artifact {identifier}")
        _require_exact_keys(item, expected_keys, f"artifact {identifier}")
        result[identifier] = LocalizedArrayArtifact(
            artifact_id=identifier,
            relative_path=_safe_relative_path(item["relative_path"], f"artifact {identifier}.relative_path"),
            byte_sha256=_required_sha256(item["byte_sha256"], f"artifact {identifier}.byte_sha256"),
            dtype=_required_text(item["dtype"], f"artifact {identifier}.dtype"),
            shape=_shape(item["shape"], f"artifact {identifier}.shape"),
            true_count=_nonnegative_int(item["true_count"], f"artifact {identifier}.true_count") if is_mask else None,
        )
    return result


def _validate_manifest_metadata(manifest: LocalizedDesignStateManifest) -> None:
    if manifest.schema_version != LOCALIZED_DESIGN_STATE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("localized design state manifest has unsupported schema_version")
    if manifest.kind != LOCALIZED_DESIGN_STATE_MANIFEST_KIND:
        raise ValueError("localized design state manifest has unsupported kind")
    _required_sha256(manifest.problem_spec_sha256, "problem_spec_sha256")
    _required_sha256(manifest.filter_config_sha256, "filter_config_sha256")
    _required_sha256(manifest.projection_config_sha256, "projection_config_sha256")
    if not isinstance(manifest.grid, LocalizedDesignGrid) or manifest.grid_sha256 != manifest.grid.sha256:
        raise ValueError("localized design state manifest grid binding is invalid")
    _require_exact_ids(manifest.masks, LOCALIZED_DESIGN_MASK_IDS, "masks")
    _require_exact_ids(manifest.states, LOCALIZED_DESIGN_STATE_IDS, "states")
    for identifier in LOCALIZED_DESIGN_MASK_IDS:
        _validate_artifact_metadata(manifest.masks[identifier], identifier, True, manifest.grid.cell_count)
    for identifier in LOCALIZED_DESIGN_STATE_IDS:
        _validate_artifact_metadata(manifest.states[identifier], identifier, False, manifest.grid.cell_count)


def _validate_artifact_metadata(artifact: LocalizedArrayArtifact, identifier: str, is_mask: bool, count: int) -> None:
    if not isinstance(artifact, LocalizedArrayArtifact) or artifact.artifact_id != identifier:
        raise ValueError(f"localized design artifact metadata is invalid: {identifier}")
    _safe_relative_path(artifact.relative_path, f"artifact {identifier}.relative_path")
    _required_sha256(artifact.byte_sha256, f"artifact {identifier}.byte_sha256")
    expected_dtype = _MASK_DTYPE.name if is_mask else _STATE_DTYPE.name
    if artifact.dtype != expected_dtype or artifact.shape != (count,):
        raise ValueError(f"localized design artifact metadata has wrong layout: {identifier}")
    if is_mask and (artifact.true_count is None or artifact.true_count < 0):
        raise ValueError(f"localized design mask metadata has invalid true_count: {identifier}")
    if not is_mask and artifact.true_count is not None:
        raise ValueError(f"localized design state metadata must not have true_count: {identifier}")


def _verify_artifact(
    manifest: LocalizedDesignStateManifest,
    artifact: LocalizedArrayArtifact,
    is_mask: bool,
    *,
    active_mask: np.ndarray | None = None,
) -> np.ndarray:
    path = _resolve_artifact_path(manifest.path.parent, artifact.relative_path)
    if not path.is_file():
        raise ValueError(f"localized design artifact is missing: {artifact.relative_path}")
    if path.suffix.lower() != ".npy":
        raise ValueError(f"localized design artifact is not a .npy file: {artifact.relative_path}")
    if _sha256_file(path) != artifact.byte_sha256:
        raise ValueError(f"localized design artifact hash mismatch: {artifact.artifact_id}")
    array = _load_npy_memmap(path, artifact.artifact_id)
    _validate_array_layout(array, manifest.grid.cell_count, is_mask, artifact.artifact_id)
    if tuple(array.shape) != artifact.shape or array.dtype.name != artifact.dtype:
        raise ValueError(f"localized design artifact metadata does not match file: {artifact.artifact_id}")
    if is_mask:
        true_count = _stream_mask_true_count(array, artifact.artifact_id)
        if true_count != artifact.true_count:
            raise ValueError(f"localized design mask true_count does not match file: {artifact.artifact_id}")
    else:
        _stream_state_values(array, active_mask, artifact.artifact_id)
    return array


def _validate_mask_relationships(masks: Mapping[str, np.ndarray]) -> None:
    active = masks["active_design_mask"]
    forbidden = masks["forbidden_mask"]
    fixed = masks["fixed_solid_mask"]
    root = masks["root_mask"]
    if np.any(active & forbidden):
        raise ValueError("active_design_mask must not overlap forbidden_mask")
    if np.any(active & fixed):
        raise ValueError("active_design_mask must not overlap fixed_solid_mask")
    if np.any(root & ~fixed):
        raise ValueError("root_mask must be a subset of fixed_solid_mask")


def _load_npy_memmap(path: Path, identifier: str) -> np.ndarray:
    try:
        array = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to memory-map localized design artifact: {identifier}") from exc
    if not isinstance(array, np.memmap):
        raise ValueError(f"localized design artifact must be a memory-mappable .npy array: {identifier}")
    return array


def _validate_array_layout(array: np.ndarray, count: int, is_mask: bool, identifier: str) -> None:
    expected = _MASK_DTYPE if is_mask else _STATE_DTYPE
    if array.shape != (count,):
        raise ValueError(f"{identifier} must have shape ({count},)")
    if array.dtype != expected:
        raise ValueError(f"{identifier} must have dtype {expected.name}")


def _stream_mask_true_count(array: np.ndarray, identifier: str) -> int:
    del identifier
    total = 0
    for start in range(0, array.size, _CHUNK_CELLS):
        total += int(np.count_nonzero(array[start : start + _CHUNK_CELLS]))
    return total


def _stream_state_values(array: np.ndarray, active_mask: np.ndarray | None, identifier: str) -> None:
    for start in range(0, array.size, _CHUNK_CELLS):
        stop = min(array.size, start + _CHUNK_CELLS)
        values = np.asarray(array[start:stop])
        if not np.isfinite(values).all() or np.any(values < 0.0) or np.any(values > 1.0):
            raise ValueError(f"{identifier} must contain only finite values in [0, 1]")
        if active_mask is not None and np.any(values[~active_mask[start:stop]] != 0.0):
            raise ValueError(f"{identifier} must be exactly zero outside active_design_mask")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _manifest_path(path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ValueError("localized design state manifest path must end in .json")
    return target


def _relative_artifact_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("localized design artifact must be below manifest directory") from exc


def _resolve_artifact_path(root: Path, value: str) -> Path:
    relative = _safe_relative_path(value, "localized design artifact path")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("localized design artifact path escapes manifest directory") from exc
    return candidate


def _safe_relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or path.drive or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{context} must be a safe relative path")
    return path.as_posix()


def _require_exact_ids(values: Mapping[str, Any], expected: tuple[str, ...], context: str) -> None:
    if not isinstance(values, Mapping):
        raise ValueError(f"{context} must be a mapping")
    actual = set(values)
    required = set(expected)
    if actual != required:
        raise ValueError(f"{context} must contain exactly {list(expected)!r}")


def _require_exact_keys(values: Mapping[str, Any], expected: set[str], context: str) -> None:
    if set(values) != expected:
        raise ValueError(f"{context} has unsupported or missing fields")


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be non-empty text")
    return value


def _required_sha256(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{context} must be a lower-case SHA-256 hex digest")
    return text


def _exact_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    result = _exact_int(value, context)
    if result < 0:
        raise ValueError(f"{context} must be non-negative")
    return result


def _shape(value: Any, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{context} must be a non-empty positive-integer list")
    return tuple(value)


def _cell_shape(value: Any, context: str) -> tuple[int, int, int]:
    if isinstance(value, tuple):
        value = list(value)
    shape = _shape(value, context)
    if len(shape) != 3:
        raise ValueError(f"{context} must have three positive integers")
    return shape  # type: ignore[return-value]


def _finite_vector(value: Any, context: str) -> np.ndarray:
    try:
        values = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a three-value numeric vector") from exc
    if values.shape != (3,) or not np.issubdtype(values.dtype, np.number):
        raise ValueError(f"{context} must be a three-value numeric vector")
    result = np.asarray(values, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"{context} must contain finite values")
    return result


def _vector3(value: Any, context: str) -> tuple[float, float, float]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a three-value list")
    result = _finite_vector(value, context)
    return tuple(float(item) for item in result)  # type: ignore[return-value]


__all__ = [
    "CANONICAL_CELL_ORDER",
    "LOCALIZED_DESIGN_GRID_KIND",
    "LOCALIZED_DESIGN_MASK_IDS",
    "LOCALIZED_DESIGN_STATE_IDS",
    "LOCALIZED_DESIGN_STATE_MANIFEST_KIND",
    "LOCALIZED_DESIGN_STATE_MANIFEST_SCHEMA_VERSION",
    "LocalizedArrayArtifact",
    "LocalizedDesignGrid",
    "LocalizedDesignStateManifest",
    "VerifiedLocalizedDesignStateManifest",
    "create_localized_design_state_manifest",
    "load_and_verify_localized_design_state_manifest",
    "localized_design_state_manifest_sha256",
    "read_localized_design_state_manifest",
    "validate_localized_design_state_manifest",
    "write_localized_design_state_manifest",
]
