"""Fail-closed reference binding for localized-design ``alpha`` sources.

The local G3 design state is authoritative.  This module records the one
allowed route from that state to the coarse CFD topology field:

``alpha = alpha_reference + E @ (rho_projected - rho_projected_reference)``.

``E`` is :class:`~cfd_sdf.localized_design_transfer.LocalizedDesignToCfdTransfer`.
There is deliberately no reverse transfer, no clipping, no OpenFOAM field
writer, and no native-v2 readiness signal here.  Keeping the reference record
separate makes a later case writer prove precisely which local state and which
CFD ``alpha`` it is allowed to use.
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

from .localized_design_state_manifest import (
    LocalizedDesignStateManifest,
    VerifiedLocalizedDesignStateManifest,
    load_and_verify_localized_design_state_manifest,
    localized_design_state_manifest_sha256,
    require_localized_design_state_manifest_v2,
    validate_localized_design_state_manifest,
)
from .localized_design_transfer import LocalizedDesignToCfdTransfer
from .openfoam_grid_transfer import UniformCartesianCellGrid


LOCALIZED_ALPHA_REFERENCE_BINDING_SCHEMA_VERSION = 1
LOCALIZED_ALPHA_REFERENCE_BINDING_KIND = "localized_alpha_reference_binding"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ARRAY_CHUNK_CELLS = 1_048_576


@dataclass(frozen=True)
class LocalizedAlphaReferenceBinding:
    """Portable metadata binding a reference local state to a CFD alpha vector."""

    path: Path
    schema_version: int
    kind: str
    problem_spec_sha256: str
    reference_state_manifest_relative_path: str
    reference_state_manifest_sha256: str
    reference_rho_projected_sha256: str
    cfd_grid: UniformCartesianCellGrid
    cfd_grid_sha256: str
    alpha_reference_relative_path: str
    alpha_reference_sha256: str
    alpha_reference_dtype: str
    alpha_reference_shape: tuple[int, ...]
    provenance: Mapping[str, Any]
    provenance_sha256: str

    @property
    def sha256(self) -> str:
        return localized_alpha_reference_binding_sha256(self)


@dataclass(frozen=True)
class VerifiedLocalizedAlphaReferenceBinding:
    """Binding with its local state and reference alpha fully verified."""

    binding: LocalizedAlphaReferenceBinding
    reference_state: VerifiedLocalizedDesignStateManifest
    alpha_reference: np.memmap


@dataclass(frozen=True)
class LocalizedAlphaSource:
    """Calculated alpha plus the CFD-grid contract required by a case writer.

    This is not an interchangeable raw vector.  Downstream OpenFOAM staging
    must prove its own parsed ``blockMeshDict`` is exactly this CFD grid and
    preserve both the binding and canonical x-fastest ordering.
    """

    alpha: np.ndarray
    binding_sha256: str
    current_state_manifest_sha256: str
    alpha_sha256: str
    cfd_grid_sha256: str
    cfd_cell_count: int
    cell_order: str


def create_localized_alpha_reference_binding(
    *,
    path: str | Path,
    reference_state_manifest_path: str | Path,
    cfd_grid: UniformCartesianCellGrid,
    alpha_reference_path: str | Path,
    provenance: Mapping[str, Any],
) -> LocalizedAlphaReferenceBinding:
    """Create metadata for a validated reference state and alpha array.

    The referenced state manifest and ``.npy`` alpha array must both reside
    below the binding JSON directory.  Creation never copies or mutates either
    artifact; callers must explicitly call
    :func:`write_localized_alpha_reference_binding` after inspecting it.
    """

    binding_path = _binding_path(path)
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path = _input_artifact_path(
        binding_path.parent, reference_state_manifest_path, ".json", "reference state manifest"
    )
    alpha_path = _input_artifact_path(
        binding_path.parent, alpha_reference_path, ".npy", "alpha reference"
    )
    reference_state = require_localized_design_state_manifest_v2(
        load_and_verify_localized_design_state_manifest(reference_path)
    )
    if not isinstance(cfd_grid, UniformCartesianCellGrid):
        raise ValueError("cfd_grid must be UniformCartesianCellGrid")
    alpha = _load_alpha_reference(alpha_path, cfd_grid.cell_count)
    canonical_provenance = _canonical_provenance(provenance)
    manifest = reference_state.manifest
    return LocalizedAlphaReferenceBinding(
        path=binding_path,
        schema_version=LOCALIZED_ALPHA_REFERENCE_BINDING_SCHEMA_VERSION,
        kind=LOCALIZED_ALPHA_REFERENCE_BINDING_KIND,
        problem_spec_sha256=manifest.problem_spec_sha256,
        reference_state_manifest_relative_path=_relative_path(binding_path.parent, reference_path),
        reference_state_manifest_sha256=localized_design_state_manifest_sha256(manifest),
        reference_rho_projected_sha256=manifest.states["rho_projected"].byte_sha256,
        cfd_grid=cfd_grid,
        cfd_grid_sha256=cfd_grid.sha256,
        alpha_reference_relative_path=_relative_path(binding_path.parent, alpha_path),
        alpha_reference_sha256=_sha256_file(alpha_path),
        alpha_reference_dtype=alpha.dtype.name,
        alpha_reference_shape=tuple(int(value) for value in alpha.shape),
        provenance=canonical_provenance,
        provenance_sha256=_sha256_json(canonical_provenance),
    )


def write_localized_alpha_reference_binding(binding: LocalizedAlphaReferenceBinding) -> Path:
    """Validate and atomically persist a reference-binding JSON sidecar."""

    validate_localized_alpha_reference_binding(binding)
    binding.path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_binding_to_dict(binding), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    temporary = binding.path.with_name(f".{binding.path.name}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(binding.path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return binding.path


def read_localized_alpha_reference_binding(path: str | Path) -> LocalizedAlphaReferenceBinding:
    """Read metadata only; call :func:`validate_localized_alpha_reference_binding` before use."""

    binding_path = _binding_path(path)
    try:
        raw = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read localized alpha reference binding: {binding_path}") from exc
    return _binding_from_dict(binding_path, raw)


def load_and_verify_localized_alpha_reference_binding(
    path: str | Path,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalizedAlphaReferenceBinding:
    """Read and fail closed on any state, grid, alpha, or provenance mismatch."""

    return validate_localized_alpha_reference_binding(
        read_localized_alpha_reference_binding(path),
        expected_problem_spec_sha256=expected_problem_spec_sha256,
    )


def validate_localized_alpha_reference_binding(
    binding: LocalizedAlphaReferenceBinding,
    *,
    expected_problem_spec_sha256: str | None = None,
) -> VerifiedLocalizedAlphaReferenceBinding:
    """Verify the reference manifest, rho binding, CFD grid, alpha, and provenance."""

    _validate_binding_metadata(binding)
    if expected_problem_spec_sha256 is not None:
        _required_sha256(expected_problem_spec_sha256, "expected_problem_spec_sha256")
        if binding.problem_spec_sha256 != expected_problem_spec_sha256:
            raise ValueError("localized alpha reference binding problem_spec_sha256 does not match")
    reference_path = _resolve_relative_path(
        binding.path.parent, binding.reference_state_manifest_relative_path, ".json", "reference state manifest"
    )
    reference_state = require_localized_design_state_manifest_v2(
        load_and_verify_localized_design_state_manifest(
            reference_path, expected_problem_spec_sha256=binding.problem_spec_sha256
        )
    )
    manifest = reference_state.manifest
    if localized_design_state_manifest_sha256(manifest) != binding.reference_state_manifest_sha256:
        raise ValueError("localized alpha reference binding reference state manifest hash mismatch")
    if manifest.states["rho_projected"].byte_sha256 != binding.reference_rho_projected_sha256:
        raise ValueError("localized alpha reference binding reference rho_projected hash mismatch")
    alpha_path = _resolve_relative_path(
        binding.path.parent, binding.alpha_reference_relative_path, ".npy", "alpha reference"
    )
    alpha = _load_alpha_reference(alpha_path, binding.cfd_grid.cell_count)
    if _sha256_file(alpha_path) != binding.alpha_reference_sha256:
        raise ValueError("localized alpha reference binding alpha reference hash mismatch")
    if alpha.dtype.name != binding.alpha_reference_dtype or tuple(alpha.shape) != binding.alpha_reference_shape:
        raise ValueError("localized alpha reference binding alpha reference layout mismatch")
    return VerifiedLocalizedAlphaReferenceBinding(
        binding=binding, reference_state=reference_state, alpha_reference=alpha
    )


def localized_alpha_reference_binding_sha256(binding: LocalizedAlphaReferenceBinding) -> str:
    """Return the canonical metadata hash used by downstream alpha provenance."""

    if not isinstance(binding, LocalizedAlphaReferenceBinding):
        raise ValueError("binding must be LocalizedAlphaReferenceBinding")
    return _sha256_json(_binding_to_dict(binding))


def calculate_localized_alpha_source(
    *,
    binding: LocalizedAlphaReferenceBinding | VerifiedLocalizedAlphaReferenceBinding,
    current_state: LocalizedDesignStateManifest | VerifiedLocalizedDesignStateManifest,
    transfer: LocalizedDesignToCfdTransfer,
    target_z_chunk_size: int | None = None,
) -> LocalizedAlphaSource:
    """Calculate the only permitted local-state alpha source without clipping.

    Both state manifests are independently verified.  The current state must
    preserve the reference problem, local grid, masks, filter, and projection
    contracts; only the three ``rho`` values may differ.  A reference manifest
    as current input must reproduce ``alpha_reference`` exactly.
    """

    verified_binding = _verified_binding(binding)
    verified_current = _verified_state(current_state)
    reference_manifest = verified_binding.reference_state.manifest
    current_manifest = verified_current.manifest
    _validate_current_state_contract(reference_manifest, current_manifest)
    _validate_transfer_contract(transfer, reference_manifest, verified_binding.binding.cfd_grid)
    current_rho = _load_state_array(current_manifest, "rho_projected")
    reference_rho = _load_state_array(reference_manifest, "rho_projected")
    difference = transfer.apply_forward_difference(
        current_rho, reference_rho, target_z_chunk_size=target_z_chunk_size
    )
    alpha = np.add(np.asarray(verified_binding.alpha_reference), difference, dtype=np.float64)
    _validate_alpha_values(alpha, "calculated alpha source")
    if localized_design_state_manifest_sha256(current_manifest) == verified_binding.binding.reference_state_manifest_sha256:
        if not np.array_equal(alpha, np.asarray(verified_binding.alpha_reference)):
            raise ValueError("reference current state must reproduce alpha_reference exactly")
    return LocalizedAlphaSource(
        alpha=alpha,
        binding_sha256=verified_binding.binding.sha256,
        current_state_manifest_sha256=localized_design_state_manifest_sha256(current_manifest),
        alpha_sha256=_sha256_values(alpha),
        cfd_grid_sha256=verified_binding.binding.cfd_grid_sha256,
        cfd_cell_count=verified_binding.binding.cfd_grid.cell_count,
        cell_order=verified_binding.binding.cfd_grid.cell_order,
    )


def _verified_binding(
    value: LocalizedAlphaReferenceBinding | VerifiedLocalizedAlphaReferenceBinding,
) -> VerifiedLocalizedAlphaReferenceBinding:
    if isinstance(value, VerifiedLocalizedAlphaReferenceBinding):
        return validate_localized_alpha_reference_binding(value.binding)
    return validate_localized_alpha_reference_binding(value)


def _verified_state(
    value: LocalizedDesignStateManifest | VerifiedLocalizedDesignStateManifest,
) -> VerifiedLocalizedDesignStateManifest:
    if isinstance(value, VerifiedLocalizedDesignStateManifest):
        return require_localized_design_state_manifest_v2(validate_localized_design_state_manifest(value.manifest))
    return require_localized_design_state_manifest_v2(validate_localized_design_state_manifest(value))


def _validate_current_state_contract(
    reference: LocalizedDesignStateManifest, current: LocalizedDesignStateManifest
) -> None:
    if current.problem_spec_sha256 != reference.problem_spec_sha256:
        raise ValueError("current local design state problem_spec_sha256 does not match reference")
    if current.grid_sha256 != reference.grid_sha256:
        raise ValueError("current local design state grid_sha256 does not match reference")
    if current.filter_config_sha256 != reference.filter_config_sha256:
        raise ValueError("current local design state filter_config_sha256 does not match reference")
    if current.projection_config_sha256 != reference.projection_config_sha256:
        raise ValueError("current local design state projection_config_sha256 does not match reference")
    for identifier in reference.masks:
        if current.masks[identifier].byte_sha256 != reference.masks[identifier].byte_sha256:
            raise ValueError(f"current local design state {identifier} hash does not match reference")


def _validate_transfer_contract(
    transfer: LocalizedDesignToCfdTransfer,
    reference: LocalizedDesignStateManifest,
    cfd_grid: UniformCartesianCellGrid,
) -> None:
    if not isinstance(transfer, LocalizedDesignToCfdTransfer):
        raise ValueError("transfer must be LocalizedDesignToCfdTransfer")
    if not isinstance(transfer.cfd_grid, UniformCartesianCellGrid):
        raise ValueError("transfer cfd_grid must be UniformCartesianCellGrid")
    design_grid = transfer.design_grid
    if getattr(design_grid, "sha256", None) != reference.grid_sha256:
        raise ValueError("transfer design grid does not match reference local design grid")
    if transfer.cfd_grid.sha256 != cfd_grid.sha256:
        raise ValueError("transfer CFD grid does not match alpha reference grid")


def _load_state_array(manifest: LocalizedDesignStateManifest, identifier: str) -> np.memmap:
    artifact = manifest.states[identifier]
    path = _resolve_relative_path(manifest.path.parent, artifact.relative_path, ".npy", identifier)
    try:
        values = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unable to memory-map {identifier}") from exc
    if not isinstance(values, np.memmap) or values.dtype != np.dtype(np.float64) or values.shape != (manifest.grid.cell_count,):
        raise ValueError(f"{identifier} has an invalid localized state layout")
    return values


def _load_alpha_reference(path: Path, cell_count: int) -> np.memmap:
    try:
        alpha = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise ValueError("Unable to memory-map alpha reference") from exc
    if not isinstance(alpha, np.memmap) or alpha.dtype != np.dtype(np.float64) or alpha.shape != (cell_count,):
        raise ValueError(f"alpha reference must have float64 shape ({cell_count},)")
    _validate_alpha_values(alpha, "alpha reference")
    return alpha


def _validate_alpha_values(values: np.ndarray, context: str) -> None:
    for start in range(0, values.size, _ARRAY_CHUNK_CELLS):
        chunk = np.asarray(values[start : start + _ARRAY_CHUNK_CELLS])
        if not np.isfinite(chunk).all() or np.any(chunk < 0.0) or np.any(chunk > 1.0):
            raise ValueError(f"{context} must contain only finite values in [0, 1]; clipping is forbidden")


def _binding_from_dict(path: Path, raw: Any) -> LocalizedAlphaReferenceBinding:
    data = _mapping(raw, "localized alpha reference binding")
    expected = {
        "schema_version", "kind", "problem_spec_sha256", "reference_state_manifest_relative_path",
        "reference_state_manifest_sha256", "reference_rho_projected_sha256", "cfd_grid",
        "cfd_grid_sha256", "alpha_reference_relative_path", "alpha_reference_sha256",
        "alpha_reference_dtype", "alpha_reference_shape", "provenance", "provenance_sha256",
    }
    if set(data) != expected:
        raise ValueError("localized alpha reference binding has unsupported or missing fields")
    cfd_grid = _grid_from_dict(data["cfd_grid"])
    return LocalizedAlphaReferenceBinding(
        path=path,
        schema_version=_exact_int(data["schema_version"], "schema_version"),
        kind=_required_text(data["kind"], "kind"),
        problem_spec_sha256=_required_sha256(data["problem_spec_sha256"], "problem_spec_sha256"),
        reference_state_manifest_relative_path=_safe_relative_path(
            data["reference_state_manifest_relative_path"], "reference_state_manifest_relative_path"
        ),
        reference_state_manifest_sha256=_required_sha256(
            data["reference_state_manifest_sha256"], "reference_state_manifest_sha256"
        ),
        reference_rho_projected_sha256=_required_sha256(
            data["reference_rho_projected_sha256"], "reference_rho_projected_sha256"
        ),
        cfd_grid=cfd_grid,
        cfd_grid_sha256=_required_sha256(data["cfd_grid_sha256"], "cfd_grid_sha256"),
        alpha_reference_relative_path=_safe_relative_path(
            data["alpha_reference_relative_path"], "alpha_reference_relative_path"
        ),
        alpha_reference_sha256=_required_sha256(data["alpha_reference_sha256"], "alpha_reference_sha256"),
        alpha_reference_dtype=_required_text(data["alpha_reference_dtype"], "alpha_reference_dtype"),
        alpha_reference_shape=_shape(data["alpha_reference_shape"], "alpha_reference_shape"),
        provenance=_canonical_provenance(data["provenance"]),
        provenance_sha256=_required_sha256(data["provenance_sha256"], "provenance_sha256"),
    )


def _binding_to_dict(binding: LocalizedAlphaReferenceBinding) -> dict[str, Any]:
    return {
        "schema_version": binding.schema_version,
        "kind": binding.kind,
        "problem_spec_sha256": binding.problem_spec_sha256,
        "reference_state_manifest_relative_path": binding.reference_state_manifest_relative_path,
        "reference_state_manifest_sha256": binding.reference_state_manifest_sha256,
        "reference_rho_projected_sha256": binding.reference_rho_projected_sha256,
        "cfd_grid": _grid_to_dict(binding.cfd_grid),
        "cfd_grid_sha256": binding.cfd_grid_sha256,
        "alpha_reference_relative_path": binding.alpha_reference_relative_path,
        "alpha_reference_sha256": binding.alpha_reference_sha256,
        "alpha_reference_dtype": binding.alpha_reference_dtype,
        "alpha_reference_shape": list(binding.alpha_reference_shape),
        "provenance": dict(binding.provenance),
        "provenance_sha256": binding.provenance_sha256,
    }


def _validate_binding_metadata(binding: LocalizedAlphaReferenceBinding) -> None:
    if not isinstance(binding, LocalizedAlphaReferenceBinding):
        raise ValueError("binding must be LocalizedAlphaReferenceBinding")
    if binding.schema_version != LOCALIZED_ALPHA_REFERENCE_BINDING_SCHEMA_VERSION:
        raise ValueError("localized alpha reference binding has unsupported schema_version")
    if binding.kind != LOCALIZED_ALPHA_REFERENCE_BINDING_KIND:
        raise ValueError("localized alpha reference binding has unsupported kind")
    _required_sha256(binding.problem_spec_sha256, "problem_spec_sha256")
    _safe_relative_path(binding.reference_state_manifest_relative_path, "reference_state_manifest_relative_path")
    _required_sha256(binding.reference_state_manifest_sha256, "reference_state_manifest_sha256")
    _required_sha256(binding.reference_rho_projected_sha256, "reference_rho_projected_sha256")
    if not isinstance(binding.cfd_grid, UniformCartesianCellGrid) or binding.cfd_grid_sha256 != binding.cfd_grid.sha256:
        raise ValueError("localized alpha reference binding CFD grid binding is invalid")
    _safe_relative_path(binding.alpha_reference_relative_path, "alpha_reference_relative_path")
    _required_sha256(binding.alpha_reference_sha256, "alpha_reference_sha256")
    if binding.alpha_reference_dtype != np.dtype(np.float64).name or binding.alpha_reference_shape != (binding.cfd_grid.cell_count,):
        raise ValueError("localized alpha reference binding alpha reference layout is invalid")
    canonical_provenance = _canonical_provenance(binding.provenance)
    if dict(canonical_provenance) != dict(binding.provenance) or _sha256_json(canonical_provenance) != binding.provenance_sha256:
        raise ValueError("localized alpha reference binding provenance hash mismatch")


def _grid_to_dict(grid: UniformCartesianCellGrid) -> dict[str, Any]:
    return {
        "origin": list(grid.origin), "spacing": list(grid.spacing), "cell_shape": list(grid.cell_shape),
        "cell_order": grid.cell_order, "axes": [list(row) for row in grid.axes],
    }


def _grid_from_dict(raw: Any) -> UniformCartesianCellGrid:
    data = _mapping(raw, "cfd_grid")
    if set(data) != {"origin", "spacing", "cell_shape", "cell_order", "axes"}:
        raise ValueError("cfd_grid has unsupported or missing fields")
    try:
        return UniformCartesianCellGrid(
            origin=data["origin"], spacing=data["spacing"], cell_shape=data["cell_shape"],
            cell_order=data["cell_order"], axes=data["axes"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("cfd_grid is invalid") from exc


def _canonical_provenance(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("provenance must be a non-empty JSON mapping")
    try:
        canonical = json.loads(json.dumps(dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("provenance must be finite JSON data") from exc
    if not isinstance(canonical, dict) or not canonical:
        raise ValueError("provenance must be a non-empty JSON mapping")
    return canonical


def _binding_path(path: str | Path) -> Path:
    result = Path(path)
    if result.suffix.lower() != ".json":
        raise ValueError("localized alpha reference binding path must end in .json")
    return result


def _input_artifact_path(root: Path, value: str | Path, suffix: str, context: str) -> Path:
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    _relative_path(root, resolved)
    if resolved.suffix.lower() != suffix or not resolved.is_file():
        raise ValueError(f"{context} must be an existing {suffix} file below binding directory")
    return resolved


def _resolve_relative_path(root: Path, value: str, suffix: str, context: str) -> Path:
    relative = _safe_relative_path(value, context)
    resolved = (root / relative).resolve()
    _relative_path(root, resolved)
    if resolved.suffix.lower() != suffix or not resolved.is_file():
        raise ValueError(f"{context} is missing or has an invalid suffix")
    return resolved


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("reference artifacts must be below binding directory") from exc


def _safe_relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty safe relative path")
    path = Path(value)
    if path.is_absolute() or path.drive or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{context} must be a non-empty safe relative path")
    return path.as_posix()


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be non-empty text")
    return value


def _required_sha256(value: Any, context: str) -> str:
    result = _required_text(value, context)
    if _SHA256_RE.fullmatch(result) is None:
        raise ValueError(f"{context} must be a lower-case SHA-256 hex digest")
    return result


def _exact_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _shape(value: Any, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{context} must be a positive-integer list")
    return tuple(value)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


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


def _sha256_values(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


__all__ = [
    "LOCALIZED_ALPHA_REFERENCE_BINDING_KIND",
    "LOCALIZED_ALPHA_REFERENCE_BINDING_SCHEMA_VERSION",
    "LocalizedAlphaReferenceBinding",
    "LocalizedAlphaSource",
    "VerifiedLocalizedAlphaReferenceBinding",
    "calculate_localized_alpha_source",
    "create_localized_alpha_reference_binding",
    "load_and_verify_localized_alpha_reference_binding",
    "localized_alpha_reference_binding_sha256",
    "read_localized_alpha_reference_binding",
    "validate_localized_alpha_reference_binding",
    "write_localized_alpha_reference_binding",
]
