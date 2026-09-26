"""SDF genesis: canonical SDFDesignState from a registered Stage S handoff.

Genesis is the solver-free first gate of the SDF-native gate order.  It
converts an already-validated T-to-S handoff directory (point-grid SDF VTI,
source cell-density VTI with the fixed-grid mask contract, surface STL,
topology state and manifest with artifact hashes) into the canonical
:class:`~cfd_sdf.design.sdf_state.SDFDesignState`:

- every handoff manifest artifact hash is re-verified fail-closed;
- ``phi`` is read from the handoff's own point-grid SDF VTI, still with the
  immutable convention ``phi < 0`` solid / ``phi > 0`` fluid;
- the produced state binds the registered baseline surface STL hash as
  ``source_sha256``.

Cell-to-point mask projection (registered genesis policy v1):

- ``design_mask`` is the strict projection: a point is design-active only
  when it is an interior grid node (a complete 2x2x2 cell neighbourhood)
  and *all eight* adjacent cells are ``active_design_mask`` cells.  A node
  at the boundary of the mutable region therefore cannot move, keeping
  topology changes inside the allowed cells even after an update.
- ``fixed_solid_mask``, ``forbidden_mask`` and ``root_mask`` use the
  permissive projection: a point belongs to the mask when *any* adjacent
  cell carries it.  An over-complete fixed/forbidden/root point mask
  preserves more of the constrained region; the cell-level retain rules
  stay authoritative and are re-verified fail-closed.

No solver runs; no response is evaluated; no evidence is rewritten.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .sdf_state import SDFDesignState

GENESIS_KIND = "sdf_native_genesis"
GENESIS_SCHEMA_VERSION = 1
GENESIS_MASK_PROJECTION_POLICY = "v16_handoff_mask_projection_v1"
_DEFAULT_SDF_ARRAY = "sdf"
_REQUIRED_HANDOFF_ARTIFACTS = (
    "sdf_vti",
    "source_density_vti",
    "surface_stl",
    "source_topology_state",
)
_MASK_NAMES = (
    "allowed_mask",
    "forbidden_mask",
    "fixed_solid_mask",
    "root_mask",
    "active_design_mask",
)
_SHA256_LENGTH = 64


class GenesisError(ValueError):
    """Fail-closed SDF genesis contract violation."""


@dataclass(frozen=True)
class GenesisResult:
    """Canonical SDF design state plus the identity report binding it."""

    state: SDFDesignState
    report: Mapping[str, Any]
    state_path: Path | None


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha256_hex(value: Any, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or not all(character in "0123456789abcdef" for character in value)
    ):
        raise GenesisError(f"{field_name} must be a 64-character lowercase hex sha256")
    return value


def _read_json_object(path: Path, *, field_name: str) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GenesisError(f"{field_name} is unreadable: {path} ({error})") from error
    if not isinstance(document, Mapping):
        raise GenesisError(f"{field_name} must be a JSON object: {path}")
    return document


def _single_string_field(dataset, name: str) -> str:
    values = np.asarray(dataset.field_data.get(name, [])).ravel()
    if values.size != 1:
        raise GenesisError(f"VTI field {name!r} must contain exactly one value")
    return str(values[0])


def _resolve_artifact_path(
    manifest_path: Path,
    artifacts: Mapping[str, Any],
    name: str,
    *,
    suffix: str,
) -> Path:
    entry = artifacts.get(name)
    if not isinstance(entry, Mapping):
        raise GenesisError(f"handoff manifest artifact {name!r} is missing")
    recorded_hash = entry.get("sha256")
    _validate_sha256_hex(recorded_hash, field_name=f"artifact {name} sha256")
    relative = entry.get("path")
    if not isinstance(relative, str) or not relative.strip():
        raise GenesisError(f"handoff manifest artifact {name!r} has no path")
    candidate = Path(relative)
    if not candidate.is_absolute():
        candidates = [
            manifest_path.parent / Path(relative).name,
            manifest_path.parent / Path(relative),
        ]
        resolved = next((path for path in candidates if path.is_file()), None)
        if resolved is None:
            raise GenesisError(
                f"artifact {name} not found next to the manifest: tried {candidates}"
            )
        candidate = resolved
    if candidate.suffix.lower() != suffix:
        raise GenesisError(f"artifact {name} must be a {suffix} file: {candidate}")
    actual = _sha256_path(candidate)
    if actual != recorded_hash:
        raise GenesisError(
            f"artifact {name} hash mismatch: manifest records {recorded_hash}, file is {actual}"
        )
    return candidate


def _single_value_field(dataset, name: str) -> float | None:
    values = np.asarray(dataset.field_data.get(name, [])).ravel()
    return float(values[0]) if values.size == 1 else None


def _isotropic_dims(dataset, path: Path) -> tuple[tuple[int, int, int], float]:
    dimensions = tuple(int(value) for value in dataset.dimensions)
    if len(dimensions) != 3 or any(value < 2 for value in dimensions):
        raise GenesisError(f"VTI dimensions are invalid in {path}: {dimensions}")
    spacings = tuple(float(value) for value in dataset.spacing)
    if len({round(value, 12) for value in spacings}) != 1:
        raise GenesisError(f"spacing must be uniform and isotropic in {path}: {spacings}")
    return dimensions, float(spacings[0])


def _read_point_grid(
    path: Path,
    *,
    array_name: str = _DEFAULT_SDF_ARRAY,
) -> tuple[tuple[float, float, float], float, np.ndarray, float | None, str | None]:
    import pyvista as pv

    dataset = pv.read(path)
    dimensions, spacing = _isotropic_dims(dataset, path)
    if _single_string_field(dataset, "sdf_sign_convention") != (
        "negative_inside_positive_outside"
    ):
        raise GenesisError("SDF VTI must declare the negative_inside sign convention")
    if array_name not in dataset.point_data:
        raise GenesisError(f"SDF VTI point data does not contain {array_name!r}")
    iso_value = _single_value_field(dataset, "iso_value")
    grid_field = np.asarray(dataset.field_data.get("grid_sha256", [])).ravel()
    grid_sha256 = str(grid_field[0]) if grid_field.size == 1 else None
    values = np.asarray(dataset.point_data[array_name])
    expected = int(np.prod(dimensions))
    if values.ndim != 1 or values.size != expected:
        raise GenesisError(f"SDF point array must have {expected} values; got {values.shape}")
    field = np.ascontiguousarray(values.reshape(dimensions, order="F"), dtype=np.float32)
    if not np.isfinite(field).all():
        raise GenesisError("SDF field must be finite everywhere")
    if not (field < 0.0).any() or not (field > 0.0).any():
        raise GenesisError("SDF field must contain both solid and fluid samples")
    return tuple(float(value) for value in dataset.origin), spacing, field, iso_value, grid_sha256


def _read_cell_grid(path: Path) -> tuple[
    tuple[float, float, float],
    float,
    tuple[int, int, int],
    dict[str, np.ndarray],
    np.ndarray,
]:
    import pyvista as pv

    dataset = pv.read(path)
    dimensions, spacing = _isotropic_dims(dataset, path)
    schema = np.asarray(dataset.field_data.get("schema_version", [])).ravel()
    if schema.size != 1 or int(schema[0]) != 1:
        raise GenesisError("source density VTI must declare fixed-grid schema_version 1")
    if _single_string_field(dataset, "cell_order") != "vtk-x-fastest":
        raise GenesisError("source density VTI must declare cell_order vtk-x-fastest")
    if _single_string_field(dataset, "kind") != "fixed_grid_density":
        raise GenesisError("source density VTI kind must be 'fixed_grid_density'")
    cell_shape = tuple(value - 1 for value in dimensions)
    cell_count = int(np.prod(cell_shape))
    arrays: dict[str, np.ndarray] = {}
    for name in dataset.cell_data:
        values = np.asarray(dataset.cell_data[name])
        if values.ndim == 1 and values.size == cell_count:
            arrays[name] = values
    missing = [name for name in _MASK_NAMES if name not in arrays]
    if missing:
        raise GenesisError(f"source density VTI is missing cell arrays: {missing}")
    for name in _MASK_NAMES:
        values = arrays[name]
        if values.dtype == np.bool_:
            continue
        if values.dtype == np.uint8 and int(values.max(initial=0)) <= 1:
            # VTK serializes booleans as uint8 on disk; a binary uint8 array
            # roundtrips or reads as uint8 depending on the writer/reader.
            continue
        raise GenesisError(
            f"cell array {name} must be boolean (or binary uint8); got {values.dtype}"
        )
    if "rho_projection" not in arrays:
        raise GenesisError("source density VTI must contain the rho_projection cell array")
    rho = arrays["rho_projection"]
    if float(np.min(rho)) < -1.0e-7 or float(np.max(rho)) > 1.0 + 1.0e-7:
        raise GenesisError("rho_projection must stay within [0, 1]")
    masks = {name: np.ascontiguousarray(arrays[name], dtype=np.bool_) for name in _MASK_NAMES}
    for name, array in masks.items():
        # The reader already filtered each array to exactly cell_count values;
        # the fixed-grid cell order is vtk-x-fastest (Fortran) on the cube.
        masks[name] = array.reshape(cell_shape, order="F")
    return (
        tuple(float(value) for value in dataset.origin),
        spacing,
        cell_shape,
        masks,
        np.ascontiguousarray(rho, dtype=np.float64).reshape(cell_shape, order="F"),
    )


def _project_mask_any_adjacent(cell_mask: np.ndarray) -> np.ndarray:
    """A point belongs to the mask when *any* adjacent cell carries it."""

    source = np.asarray(cell_mask, dtype=np.bool_)
    if source.ndim != 3 or any(value < 1 for value in source.shape):
        raise GenesisError(f"cell mask must be a non-empty 3D array: {source.shape}")
    sx, sy, sz = source.shape
    padded = np.pad(source, ((1, 1), (1, 1), (1, 1)))
    projected = np.zeros((sx + 1, sy + 1, sz + 1), dtype=np.bool_)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                projected |= padded[di : di + sx + 1, dj : dj + sy + 1, dk : dk + sz + 1]
    return projected


def _project_design_strict(cell_mask: np.ndarray) -> np.ndarray:
    """A point may only change topology in a fully mutable neighbourhood.

    A point is design-active only when it is an interior grid node and all
    eight adjacent cells are mutable cells.  Boundary nodes and nodes at the
    boundary of the mutable region are frozen so a downstream update cannot
    move material outside the registered allowed cells.
    """

    source = np.asarray(cell_mask, dtype=np.bool_)
    if source.ndim != 3 or any(value < 1 for value in source.shape):
        raise GenesisError(f"cell mask must be a non-empty 3D array: {source.shape}")
    sx, sy, sz = source.shape
    padded = np.pad(source, ((1, 1), (1, 1), (1, 1)))
    projected = np.ones((sx + 1, sy + 1, sz + 1), dtype=np.bool_)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                projected &= padded[di : di + sx + 1, dj : dj + sy + 1, dk : dk + sz + 1]
    projected[0, :, :] = False
    projected[-1, :, :] = False
    projected[:, 0, :] = False
    projected[:, -1, :] = False
    projected[:, :, 0] = False
    projected[:, :, -1] = False
    return projected


def _validate_mask_semantics(
    masks: Mapping[str, np.ndarray],
    *,
    cell_material: np.ndarray,
) -> dict[str, bool]:
    allowed = masks["allowed_mask"]
    forbidden = masks["forbidden_mask"]
    fixed_solid = masks["fixed_solid_mask"]
    root = masks["root_mask"]
    active = masks["active_design_mask"]
    checks = {
        "active_subset_of_allowed": bool((active & ~allowed).sum() == 0),
        "forbidden_disjoint_from_allowed": bool((forbidden & allowed).sum() == 0),
        "fixed_solid_outside_active": bool((fixed_solid & active).sum() == 0),
        "root_outside_active": bool((root & active).sum() == 0),
        "fixed_solid_disjoint_from_forbidden": bool((fixed_solid & forbidden).sum() == 0),
        "material_inside_allowed_or_fixed": bool(
            (cell_material & ~allowed & ~fixed_solid).sum() == 0
        ),
        "material_not_in_forbidden": bool((cell_material & forbidden).sum() == 0),
        "fixed_solid_retained": bool((fixed_solid & ~cell_material).sum() == 0),
        "root_retained": bool((root & ~cell_material).sum() == 0),
    }
    failed = sorted(name for name, value in checks.items() if not value)
    if failed:
        raise GenesisError(f"mask contract violated: {failed}")
    return checks


def sdf_state_from_handoff(
    handoff_manifest: str | Path,
    *,
    output_dir: str | Path | None = None,
    expected_surface_sha256: str | None = None,
    persist: bool = True,
    sdf_array_name: str = _DEFAULT_SDF_ARRAY,
) -> GenesisResult:
    """Build the canonical SDFDesignState from a registered handoff directory.

    ``handoff_manifest`` points at the ``handoff_manifest.json`` written by
    :func:`cfd_sdf.handoff.build_density_to_sdf_handoff`.  Everything is
    verified against the manifest's recorded sha256 values fail-closed.

    The state field is the point-grid SDF sample: node ``(i, j, k)`` sits at
    ``origin_m + spacing_m * [i, j, k]``, matching the handoff SDF location
    and giving downstream consumers a node-addressed trilinear body.
    """

    manifest_path = Path(handoff_manifest).resolve()
    if not manifest_path.is_file():
        raise GenesisError(f"handoff manifest is missing: {manifest_path}")
    manifest = _read_json_object(manifest_path, field_name="handoff manifest")
    if manifest.get("kind") != "stage_t_to_stage_s_handoff":
        raise GenesisError(
            f"manifest kind must be 'stage_t_to_stage_s_handoff'; got {manifest.get('kind')!r}"
        )
    if manifest.get("status") != "diagnostic_only":
        raise GenesisError(
            f"manifest status must be 'diagnostic_only'; got {manifest.get('status')!r}"
        )
    if manifest.get("ok") is not True:
        raise GenesisError("handoff manifest must record ok=true")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise GenesisError("handoff manifest must contain an artifacts mapping")
    missing = [name for name in _REQUIRED_HANDOFF_ARTIFACTS if name not in artifacts]
    if missing:
        raise GenesisError(f"handoff manifest is missing artifacts: {missing}")

    sdf_path = _resolve_artifact_path(manifest_path, artifacts, "sdf_vti", suffix=".vti")
    source_density_path = _resolve_artifact_path(
        manifest_path, artifacts, "source_density_vti", suffix=".vti"
    )
    surface_path = _resolve_artifact_path(manifest_path, artifacts, "surface_stl", suffix=".stl")
    source_topology_path = _resolve_artifact_path(
        manifest_path, artifacts, "source_topology_state", suffix=".json"
    )

    sdf_origin, sdf_spacing, sdf, sdf_iso_value, sdf_grid_sha = _read_point_grid(
        sdf_path, array_name=sdf_array_name
    )
    cell_origin, cell_spacing, cell_shape, masks, rho = _read_cell_grid(source_density_path)

    if not all(
        round(sdf_origin[index], 12) == round(cell_origin[index], 12) for index in range(3)
    ):
        raise GenesisError(
            f"SDF origin {sdf_origin} does not match the source cell-grid origin {cell_origin}"
        )
    if round(sdf_spacing, 12) != round(cell_spacing, 12):
        raise GenesisError(
            f"SDF spacing {sdf_spacing} does not match the source spacing {cell_spacing}"
        )
    if cell_shape != tuple(value - 1 for value in sdf.shape):
        raise GenesisError(
            f"SDF point shape {sdf.shape} does not match the source cell grid {cell_shape}"
        )

    if sdf_grid_sha is not None:
        topology_document = _read_json_object(
            source_topology_path, field_name="source topology state"
        )
        declared_grid = topology_document.get("grid")
        if isinstance(declared_grid, Mapping):
            declared_sha = declared_grid.get("sha256")
            if declared_sha is not None and str(declared_sha) != sdf_grid_sha:
                raise GenesisError(
                    "SDF VTI grid hash does not match the source topology state grid hash: "
                    f"{sdf_grid_sha} vs {declared_sha}"
                )

    iso_for_material = float(sdf_iso_value if sdf_iso_value is not None else 0.5)
    cell_material = rho >= iso_for_material
    mask_checks = _validate_mask_semantics(masks, cell_material=cell_material)

    if expected_surface_sha256 is not None:
        _validate_sha256_hex(expected_surface_sha256, field_name="expected_surface_sha256")
        if expected_surface_sha256 != artifacts["surface_stl"]["sha256"]:
            raise GenesisError(
                "surface hash mismatch: expected "
                f"{expected_surface_sha256}, handoff records "
                f"{artifacts['surface_stl']['sha256']}"
            )

    state = SDFDesignState.create(
        phi=sdf,
        origin_m=sdf_origin,
        spacing_m=float(sdf_spacing),
        design_mask=_project_design_strict(masks["active_design_mask"]),
        fixed_solid_mask=_project_mask_any_adjacent(masks["fixed_solid_mask"]),
        forbidden_mask=_project_mask_any_adjacent(masks["forbidden_mask"]),
        root_mask=_project_mask_any_adjacent(masks["root_mask"]),
        narrow_band_width_m=float(sdf_spacing),
        generation=0,
        source_sha256=str(artifacts["surface_stl"]["sha256"]),
    )

    state_path: Path | None = None
    if persist:
        if output_dir is None:
            output_dir = manifest_path.parent / "sdf_native_genesis"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        state_path = output_dir / "sdf_design_state.npz"
        state.save(state_path)

    report: dict[str, Any] = {
        "schema_version": GENESIS_SCHEMA_VERSION,
        "kind": GENESIS_KIND,
        "status": "capability_and_contract",
        "mask_projection_policy": GENESIS_MASK_PROJECTION_POLICY,
        "handoff_manifest": {
            "path": str(manifest_path),
            "sha256": _sha256_path(manifest_path),
        },
        "handoff_artifacts_verified": {
            name: {
                "path": str(artifacts[name].get("path")),
                "sha256": artifacts[name]["sha256"],
                "verdict": "hash_match",
            }
            for name in _REQUIRED_HANDOFF_ARTIFACTS
        },
        "state_sha256": state.state_sha256,
        "state_phi_sha256": state.phi_sha256(),
        "state_path": str(state_path) if state_path else None,
        "grid_identity": {
            "location": "point",
            "origin_m": [float(value) for value in sdf_origin],
            "spacing_m": float(sdf_spacing),
            "point_shape": [int(value) for value in sdf.shape],
            "cell_shape": [int(value) for value in cell_shape],
            "sdf_grid_sha256": sdf_grid_sha,
            "iso_value": iso_for_material,
        },
        "sign_convention": state.sign_convention,
        "narrow_band_width_m": float(state.narrow_band_width_m),
        "mask_cell_counts": {
            "allowed": int(masks["allowed_mask"].sum()),
            "forbidden": int(masks["forbidden_mask"].sum()),
            "fixed_solid": int(masks["fixed_solid_mask"].sum()),
            "root": int(masks["root_mask"].sum()),
            "active_design": int(masks["active_design_mask"].sum()),
        },
        "mask_point_counts": {
            "design": int(state.design_mask.sum()),
            "fixed_solid": int(state.fixed_solid_mask.sum()),
            "forbidden": int(state.forbidden_mask.sum()),
            "root": int(state.root_mask.sum()),
            "solid_design_fraction": (
                float((state.solid_mask & state.design_mask).sum())
                / max(int(state.solid_mask.sum()), 1)
            ),
        },
        "mask_checks": mask_checks,
        "material_diagnostics": {
            "cell_material_count": int(cell_material.sum()),
            "phi_negative_point_count": int((sdf < 0.0).sum()),
            "phi_positive_point_count": int((sdf > 0.0).sum()),
            "phi_zero_point_count": int((sdf == 0.0).sum()),
            "phi_min_m": float(sdf.min()),
            "phi_max_m": float(sdf.max()),
            "material_volume_m3": float(cell_material.sum()) * float(sdf_spacing) ** 3,
        },
        "claims_not_supported": [
            "genesis is contract and capability evidence only; it claims hash identity and mask semantics, not downstream quality",
            "no WaterLily primal, SDF gradient, reverse-AD, topology-birth or optimizer qualification",
            "no absolute, grid-independent, high-Re or full-vehicle downforce claim",
        ],
        "flags": {
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }
    return GenesisResult(state=state, report=report, state_path=state_path)


def persist_genesis_report(result: GenesisResult, *, output_dir: str | Path) -> Path:
    """Write the deterministic genesis identity report as JSON."""

    path = Path(output_dir) / "genesis_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(result.report), indent=2, sort_keys=True) + "\n")
    return path


__all__ = [
    "GENESIS_KIND",
    "GENESIS_MASK_PROJECTION_POLICY",
    "GENESIS_SCHEMA_VERSION",
    "GenesisError",
    "GenesisResult",
    "persist_genesis_report",
    "sdf_state_from_handoff",
]
