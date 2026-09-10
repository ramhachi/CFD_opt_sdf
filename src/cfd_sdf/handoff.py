"""Fail-closed Stage T density to Stage S geometry handoff.

The fixed-grid contract stores ``rho`` as cell data.  VTK contouring requires
point data, so this module makes the cell-to-point interpolation explicit and
records it in the handoff manifest before producing an STL and a signed
distance field.  The resulting SDF uses the project convention from
``cfd_sdf.sdf.signed_distance``: negative inside and positive outside.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import numpy as np
import pyvista as pv
from scipy import ndimage
import trimesh

from .fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _assert_same_grid,
    _read_cell_vti,
)
from .openfoam_grid_transfer import UniformCartesianCellGrid
from .sdf import signed_distance


HANDOFF_SCHEMA_VERSION = 1
HANDOFF_KIND = "stage_t_to_stage_s_handoff"
FIDELITY_REPORT_KIND = "density_to_sdf_fidelity_report"
SDF_KIND = "stage_s_signed_distance"
SDF_SIGN_CONVENTION = "negative_inside_positive_outside"
CANONICAL_CELL_ORDER = "vtk-x-fastest"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RHO_VARIANTS = frozenset({"rho", "rho_filtered", "rho_projected"})
_MASK_NAMES = (
    "allowed_mask",
    "forbidden_mask",
    "fixed_solid_mask",
    "root_mask",
    "active_design_mask",
)


@dataclass(frozen=True)
class DensityToSdfHandoffArtifacts:
    """Paths and summaries produced by one validated T-to-S handoff."""

    output_dir: Path
    topology_state_json: Path
    density_vti: Path
    bundled_topology_state_json: Path
    bundled_density_vti: Path
    surface_stl: Path
    sdf_vti: Path
    revoxelized_density_vti: Path
    geometry_binding_json: Path
    fidelity_report_json: Path
    manifest_json: Path
    manifest: Mapping[str, object]
    fidelity_report: Mapping[str, object]

    @property
    def ok(self) -> bool:
        return bool(self.manifest.get("ok"))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "output_dir",
            "topology_state_json",
            "density_vti",
            "bundled_topology_state_json",
            "bundled_density_vti",
            "surface_stl",
            "sdf_vti",
            "revoxelized_density_vti",
            "geometry_binding_json",
            "fidelity_report_json",
            "manifest_json",
        ):
            data[key] = str(data[key])
        return data


def build_density_to_sdf_handoff(
    topology_state_json: str | Path,
    *,
    output_dir: str | Path | None = None,
    rho_variant: str | None = None,
    iso_value: float | None = None,
    expected_topology_state_sha256: str | None = None,
    expected_density_vti_sha256: str | None = None,
) -> DensityToSdfHandoffArtifacts:
    """Convert a fixed-grid cell-density candidate into STL and SDF artifacts.

    The input must be a schema-v1 fixed-grid topology state whose density VTI
    carries the fixed-grid field metadata and a cell-data density array.  The
    default output directory is a sibling ``stage_s_handoff`` directory.  All
    input and output artifact hashes are recorded in the manifest.

    ``rho_variant`` is limited to the three density fields defined by the
    fixed-grid contract.  ``iso_value`` is applied after VTK's explicit
    cell-data-to-point-data arithmetic averaging.  No output is considered
    valid when any required geometry or mask check fails.
    """

    state_path = Path(topology_state_json).resolve()
    if not state_path.is_file():
        raise ValueError(f"Topology state is missing: {state_path}")
    state_bytes = state_path.read_bytes()
    topology_hash = _sha256_bytes(state_bytes)
    _validate_optional_hash(expected_topology_state_sha256, topology_hash, "expected_topology_state_sha256")
    state = _read_state(state_path)

    density_path = _resolve_input_path(state_path.parent, state.get("density_vti"), "density_vti")
    density_bytes = density_path.read_bytes()
    density_hash = _sha256_bytes(density_bytes)
    _validate_optional_hash(expected_density_vti_sha256, density_hash, "expected_density_vti_sha256")
    _validate_declared_density_hash(state, density_hash)

    source_grid, arrays = _read_cell_vti(
        density_path,
        expected_kind="fixed_grid_density",
    )
    state_grid = _state_grid(state)
    _assert_same_grid(source_grid, state_grid, "density.vti", "topology_state.json")
    grid = _uniform_grid(source_grid)

    selected_variant, variant_source = _select_rho_variant(state, rho_variant)
    if selected_variant not in _RHO_VARIANTS:
        raise ValueError(
            f"Unsupported rho variant {selected_variant!r}; expected one of "
            f"{sorted(_RHO_VARIANTS)!r}"
        )
    if selected_variant not in arrays:
        raise ValueError(f"density.vti is missing cell-data array: {selected_variant}")
    density = _validate_density_array(
        arrays[selected_variant],
        source_grid.cell_count,
        selected_variant,
    )
    _validate_variant_metadata(state, selected_variant)
    threshold, threshold_source = _select_iso_value(state, iso_value)

    masks = _read_masks(arrays, source_grid.cell_count)
    material = _material_mask(density, masks, threshold)
    mask_checks = _mask_checks(masks, material, density, threshold)
    mask_failures = [name for name, check in mask_checks.items() if check.get("available") and not check.get("ok")]
    if mask_failures:
        raise ValueError(
            "Density-to-SDF mask validation failed: "
            + ", ".join(mask_failures)
        )
    component_checks = _component_checks(material, masks.get("root_mask"), source_grid.cell_shape)
    component_failures = [
        name
        for name, check in component_checks.items()
        if check.get("available") and not check.get("ok")
    ]
    if component_failures:
        raise ValueError(
            "Density-to-SDF connectivity validation failed: "
            + ", ".join(component_failures)
        )

    surface_density = density.copy()
    fixed_mask = masks.get("fixed_solid_mask")
    if fixed_mask is not None:
        # Fixed solid is part of the physical handoff even when a solver's
        # mutable rho field intentionally stores zero in those cells.
        surface_density = np.maximum(surface_density, fixed_mask.astype(np.float64))
    point_image, point_density = _cell_density_to_points(
        source_grid,
        surface_density,
        selected_variant,
    )
    point_min = float(np.min(point_density))
    point_max = float(np.max(point_density))
    if not point_min < threshold < point_max:
        raise ValueError(
            "iso_value must lie strictly inside the interpolated density range; "
            f"iso_value={threshold:g}, range=[{point_min:g}, {point_max:g}]"
        )
    surface = point_image.contour(
        isosurfaces=[threshold],
        scalars=selected_variant,
    ).triangulate()
    if surface.n_points == 0 or surface.n_cells == 0:
        raise ValueError(
            f"Density field produced an empty iso-surface at iso_value={threshold:g}"
        )
    if not np.isfinite(np.asarray(surface.points)).all():
        raise ValueError("Density field produced an iso-surface with non-finite points")

    target_dir = Path(output_dir).resolve() if output_dir is not None else state_path.parent / "stage_s_handoff"
    target_dir.mkdir(parents=True, exist_ok=True)
    bundled_state_path = target_dir / "source_topology_state.json"
    bundled_density_path = target_dir / "source_density.vti"
    surface_path = target_dir / "iso_surface.stl"
    sdf_path = target_dir / "signed_distance.vti"
    revoxelized_path = target_dir / "revoxelized_density.vti"
    geometry_binding_path = target_dir / "geometry_binding.json"
    report_path = target_dir / "fidelity_report.json"
    manifest_path = target_dir / "handoff_manifest.json"
    final_paths = (
        bundled_state_path,
        bundled_density_path,
        surface_path,
        sdf_path,
        revoxelized_path,
        geometry_binding_path,
        report_path,
        manifest_path,
    )
    existing = [path.name for path in final_paths if path.exists()]
    if existing:
        raise FileExistsError(
            "Handoff output is immutable; choose a new output directory. "
            f"Existing artifacts: {', '.join(existing)}"
        )

    # Stage every output first.  A malformed candidate therefore leaves the
    # previous accepted handoff untouched instead of creating a partial set of
    # artifacts that a later stage could mistake for a valid candidate.
    with tempfile.TemporaryDirectory(prefix=".handoff-", dir=target_dir) as staging_name:
        staging = Path(staging_name)
        staged_state = staging / bundled_state_path.name
        staged_density = staging / bundled_density_path.name
        staged_surface = staging / surface_path.name
        staged_sdf = staging / sdf_path.name
        staged_revoxelized = staging / revoxelized_path.name
        staged_geometry_binding = staging / geometry_binding_path.name
        staged_report = staging / report_path.name
        staged_manifest = staging / manifest_path.name

        shutil.copyfile(state_path, staged_state)
        shutil.copyfile(density_path, staged_density)

        # Validate the written STL as the artifact that downstream stages consume.
        surface.save(staged_surface)
        mesh = _read_and_validate_surface(staged_surface)
        sdf_values = _build_sdf_values(mesh, source_grid)
        revoxelized_density = _build_revoxelized_density(mesh, source_grid)
        revoxelized_material = np.asarray(revoxelized_density, dtype=bool)
        revoxelized_mask_checks = _mask_checks(
            masks,
            revoxelized_material,
            revoxelized_density,
            threshold,
        )
        revoxelized_component_checks = _component_checks(
            revoxelized_material,
            masks.get("root_mask"),
            source_grid.cell_shape,
        )
        _write_sdf_vti(
            staged_sdf,
            source_grid,
            sdf_values,
            point_density,
            selected_variant,
            threshold,
            grid.sha256,
        )
        _write_revoxelized_density_vti(
            staged_revoxelized,
            source_grid,
            revoxelized_density,
            grid.sha256,
        )

        surface_hash = _sha256_path(staged_surface)
        sdf_hash = _sha256_path(staged_sdf)
        revoxelized_hash = _sha256_path(staged_revoxelized)
        geometry_binding = _build_geometry_binding(
            state=state,
            topology_hash=topology_hash,
            density_hash=density_hash,
            surface_hash=surface_hash,
            sdf_hash=sdf_hash,
            revoxelized_hash=revoxelized_hash,
            grid_sha256=grid.sha256,
            selected_variant=selected_variant,
            threshold=threshold,
        )
        _write_json(staged_geometry_binding, geometry_binding)
        geometry_binding_hash = _sha256_path(staged_geometry_binding)
        qualification_reasons = _handoff_qualification_reasons(
            mesh=mesh,
            source_grid=source_grid,
            source_component_checks=component_checks,
            revoxelized_mask_checks=revoxelized_mask_checks,
            revoxelized_component_checks=revoxelized_component_checks,
            missing_lineage=geometry_binding["missing_lineage"],
        )
        report = _build_fidelity_report(
            topology_state_path=state_path,
            density_path=density_path,
            topology_hash=topology_hash,
            density_hash=density_hash,
            source_grid=source_grid,
            grid=grid,
            density=density,
            material=material,
            threshold=threshold,
            selected_variant=selected_variant,
            source_mask_checks=mask_checks,
            source_component_checks=component_checks,
            revoxelized_mask_checks=revoxelized_mask_checks,
            revoxelized_component_checks=revoxelized_component_checks,
            mesh=mesh,
            sdf_values=sdf_values,
            revoxelized_density=revoxelized_density,
            qualification_reasons=qualification_reasons,
            point_dimensions=source_grid.point_dimensions,
        )
        _write_json(staged_report, report)
        report_hash = _sha256_path(staged_report)

        manifest = _build_manifest(
            state_path=state_path,
            density_path=density_path,
            topology_hash=topology_hash,
            density_hash=density_hash,
            surface_hash=surface_hash,
            sdf_hash=sdf_hash,
            revoxelized_hash=revoxelized_hash,
            geometry_binding_hash=geometry_binding_hash,
            report_hash=report_hash,
            source_grid=source_grid,
            grid=grid,
            selected_variant=selected_variant,
            variant_source=variant_source,
            threshold=threshold,
            threshold_source=threshold_source,
            source_mask_checks=mask_checks,
            source_component_checks=component_checks,
            revoxelized_mask_checks=revoxelized_mask_checks,
            revoxelized_component_checks=revoxelized_component_checks,
            mesh=mesh,
            sdf_values=sdf_values,
            qualification_reasons=qualification_reasons,
            report_path=report_path,
        )
        _write_json(staged_manifest, manifest)

        for staged, final in (
            (staged_state, bundled_state_path),
            (staged_density, bundled_density_path),
            (staged_surface, surface_path),
            (staged_sdf, sdf_path),
            (staged_revoxelized, revoxelized_path),
            (staged_geometry_binding, geometry_binding_path),
            (staged_report, report_path),
            (staged_manifest, manifest_path),
        ):
            staged.replace(final)

    return DensityToSdfHandoffArtifacts(
        output_dir=target_dir,
        topology_state_json=state_path,
        density_vti=density_path,
        bundled_topology_state_json=bundled_state_path,
        bundled_density_vti=bundled_density_path,
        surface_stl=surface_path,
        sdf_vti=sdf_path,
        revoxelized_density_vti=revoxelized_path,
        geometry_binding_json=geometry_binding_path,
        fidelity_report_json=report_path,
        manifest_json=manifest_path,
        manifest=manifest,
        fidelity_report=report,
    )


def _read_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read topology state: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("Topology state must contain a JSON object")
    if value.get("schema_version") != FIXED_GRID_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported fixed-grid topology state schema_version: "
            f"{value.get('schema_version')!r}"
        )
    if value.get("kind") != "fixed_grid_topology_state":
        raise ValueError(f"Unsupported topology state kind: {value.get('kind')!r}")
    if value.get("design_variable") != "rho":
        raise ValueError("Stage T handoff requires design_variable='rho'")
    return value


def _state_grid(state: Mapping[str, Any]) -> CartesianCellGrid:
    raw = state.get("grid")
    if not isinstance(raw, Mapping):
        raise ValueError("topology_state.json is missing grid metadata")
    if raw.get("location") != "cell":
        raise ValueError("topology_state.json grid.location must be 'cell'")
    if raw.get("cell_order") != CANONICAL_CELL_ORDER:
        raise ValueError(
            "topology_state.json grid.cell_order must be 'vtk-x-fastest'"
        )
    try:
        origin_values = tuple(float(value) for value in raw["origin"])
        spacing_values = tuple(float(value) for value in raw["spacing"])
        shape_values = tuple(raw["cell_shape"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid topology_state.json grid metadata") from exc
    if len(origin_values) != 3 or len(spacing_values) != 3 or len(shape_values) != 3:
        raise ValueError("topology_state.json grid metadata must have three axes")
    try:
        cell_shape = tuple(int(value) for value in shape_values)
    except (TypeError, ValueError) as exc:
        raise ValueError("topology_state.json grid.cell_shape must contain integers") from exc
    if any(
        isinstance(value, bool) or float(value) != int(value)
        for value in shape_values
    ):
        raise ValueError("topology_state.json grid.cell_shape must contain integers")
    origin = origin_values
    spacing = spacing_values
    if not np.isfinite(origin).all() or not np.isfinite(spacing).all():
        raise ValueError("topology_state.json grid metadata must be finite")
    if any(value <= 0.0 for value in spacing) or any(value <= 0 for value in cell_shape):
        raise ValueError("topology_state.json grid has invalid spacing or cell_shape")
    expected_point_dimensions = tuple(value + 1 for value in cell_shape)
    if raw.get("point_dimensions") is not None and tuple(raw["point_dimensions"]) != expected_point_dimensions:
        raise ValueError("topology_state.json point_dimensions does not match cell_shape")
    expected_count = int(np.prod(cell_shape, dtype=np.int64))
    if raw.get("cell_count") is not None:
        try:
            cell_count = int(raw["cell_count"])
        except (TypeError, ValueError) as exc:
            raise ValueError("topology_state.json cell_count must be an integer") from exc
        if isinstance(raw["cell_count"], bool) or float(raw["cell_count"]) != cell_count:
            raise ValueError("topology_state.json cell_count must be an integer")
        if cell_count != expected_count:
            raise ValueError("topology_state.json cell_count does not match cell_shape")
    return CartesianCellGrid(origin=origin, spacing=spacing, cell_shape=cell_shape)


def _uniform_grid(grid: CartesianCellGrid) -> UniformCartesianCellGrid:
    return UniformCartesianCellGrid(
        origin=grid.origin,
        spacing=grid.spacing,
        cell_shape=grid.cell_shape,
        cell_order="x-fastest",
    )


def _resolve_input_path(directory: Path, value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"topology_state.json is missing {name}")
    raw = Path(value)
    path = raw.resolve() if raw.is_absolute() else (directory / raw).resolve()
    if not path.is_file():
        raise ValueError(f"Topology state artifact is missing: {path}")
    return path


def _select_rho_variant(state: Mapping[str, Any], requested: str | None) -> tuple[str, str]:
    if requested is not None:
        if not isinstance(requested, str) or not requested:
            raise ValueError("rho_variant must be non-empty text")
        return requested, "function_argument"
    declared = state.get("density_array", "rho")
    if not isinstance(declared, str) or not declared:
        raise ValueError("topology_state.json density_array must be non-empty text")
    return declared, "topology_state.json:density_array"


def _select_iso_value(state: Mapping[str, Any], requested: float | None) -> tuple[float, str]:
    source = "function_argument" if requested is not None else "default"
    value = state.get("iso_value", 0.5) if requested is None else requested
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("iso_value must be finite") from exc
    if not isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("iso_value must be finite and strictly within (0, 1)")
    if requested is None and "iso_value" in state:
        source = "topology_state.json:iso_value"
    return threshold, source


def _validate_density_array(values: np.ndarray, count: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (count,) or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"density.vti:{name} must be numeric cell data with shape ({count},)")
    if not np.isfinite(array).all():
        raise ValueError(f"density.vti:{name} contains non-finite values")
    values64 = np.asarray(array, dtype=np.float64)
    if float(values64.min(initial=0.0)) < -1.0e-7 or float(values64.max(initial=0.0)) > 1.0 + 1.0e-7:
        raise ValueError(f"density.vti:{name} must stay within [0, 1]")
    # Contract writers permit only tiny serialization round-off at the bounds.
    return np.clip(values64, 0.0, 1.0)


def _validate_variant_metadata(state: Mapping[str, Any], variant: str) -> None:
    metadata = state.get("array_metadata")
    if metadata is None:
        return
    if not isinstance(metadata, Mapping):
        raise ValueError("topology_state.json array_metadata must be a mapping")
    item = metadata.get(variant)
    if item is None:
        return
    if not isinstance(item, Mapping):
        raise ValueError(f"topology_state.json array_metadata.{variant} must be a mapping")
    if item.get("location") != "cell":
        raise ValueError(f"topology_state.json array_metadata.{variant}.location must be 'cell'")
    if item.get("units") != "1":
        raise ValueError(f"topology_state.json array_metadata.{variant}.units must be '1'")


def _read_masks(arrays: Mapping[str, np.ndarray], count: int) -> dict[str, np.ndarray]:
    masks: dict[str, np.ndarray] = {}
    for name in _MASK_NAMES:
        if name not in arrays:
            continue
        values = np.asarray(arrays[name])
        if values.shape != (count,) or values.dtype.kind not in "biuf":
            raise ValueError(f"density.vti:{name} must be a numeric cell mask with shape ({count},)")
        if not np.isfinite(values).all() or not np.isin(values, (0, 1)).all():
            raise ValueError(f"density.vti:{name} must contain only binary values 0 or 1")
        masks[name] = np.asarray(values, dtype=np.uint8)
    return masks


def _material_mask(
    density: np.ndarray,
    masks: Mapping[str, np.ndarray],
    threshold: float,
) -> np.ndarray:
    material = density >= threshold
    fixed = masks.get("fixed_solid_mask")
    if fixed is not None:
        material |= fixed > 0
    return material


def _mask_checks(
    masks: Mapping[str, np.ndarray],
    material: np.ndarray,
    density: np.ndarray,
    threshold: float,
) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}
    allowed = masks.get("allowed_mask")
    forbidden = masks.get("forbidden_mask")
    fixed = masks.get("fixed_solid_mask")
    root = masks.get("root_mask")
    active = masks.get("active_design_mask")

    if allowed is None:
        checks["allowed_mask"] = {"available": False, "ok": True, "status": "not_available"}
    else:
        outside = material & ~(allowed > 0)
        if fixed is not None:
            outside &= ~(fixed > 0)
        checks["allowed_mask"] = _check(
            available=True,
            ok=not bool(np.any(outside)),
            violation_count=int(np.count_nonzero(outside)),
            status="pass" if not np.any(outside) else "fail",
            rule="material must be inside allowed_mask unless fixed_solid_mask is set",
        )

    if forbidden is None:
        checks["forbidden_mask"] = {"available": False, "ok": True, "status": "not_available"}
    else:
        violation = material & (forbidden > 0)
        checks["forbidden_mask"] = _check(
            available=True,
            ok=not bool(np.any(violation)),
            violation_count=int(np.count_nonzero(violation)),
            status="pass" if not np.any(violation) else "fail",
            rule="material must not overlap forbidden_mask",
        )

    if fixed is None:
        checks["fixed_solid_mask"] = {"available": False, "ok": True, "status": "not_available"}
    else:
        missing = (fixed > 0) & ~material
        checks["fixed_solid_mask"] = _check(
            available=True,
            ok=not bool(np.any(missing)),
            violation_count=int(np.count_nonzero(missing)),
            status="pass" if not np.any(missing) else "fail",
            rule="fixed solid cells must be retained in the extracted material",
        )

    if root is None:
        checks["root_mask"] = {"available": False, "ok": True, "status": "not_available"}
    else:
        missing = (root > 0) & ~material
        checks["root_mask"] = _check(
            available=True,
            ok=not bool(np.any(missing)),
            violation_count=int(np.count_nonzero(missing)),
            status="pass" if not np.any(missing) else "fail",
            rule="root cells must be retained in the extracted material",
        )

    if active is None:
        checks["active_design_mask"] = {"available": False, "ok": True, "status": "not_available"}
    else:
        active_values = active > 0
        violations = np.zeros_like(active_values)
        if allowed is not None:
            violations |= active_values & ~(allowed > 0)
        if forbidden is not None:
            violations |= active_values & (forbidden > 0)
        if fixed is not None:
            violations |= active_values & (fixed > 0)
        checks["active_design_mask"] = _check(
            available=True,
            ok=not bool(np.any(violations)),
            violation_count=int(np.count_nonzero(violations)),
            status="pass" if not np.any(violations) else "fail",
            rule="active_design_mask must be a valid mutable subset",
        )
    return checks


def _check(**values: object) -> dict[str, object]:
    return dict(values)


def _component_checks(
    material_flat: np.ndarray,
    root_flat: np.ndarray | None,
    cell_shape: tuple[int, int, int],
) -> dict[str, dict[str, object]]:
    material = np.asarray(material_flat, dtype=bool).reshape(cell_shape, order="F")
    labels, component_count = ndimage.label(
        material,
        structure=ndimage.generate_binary_structure(3, 1),
    )
    result: dict[str, dict[str, object]] = {
        "nominal_components": {
            "available": True,
            "ok": bool(component_count > 0),
            "status": "pass" if component_count > 0 else "fail",
            "component_count": int(component_count),
        }
    }
    if root_flat is None:
        result["root_connectivity"] = {
            "available": False,
            "ok": True,
            "status": "not_available",
            "root_cell_count": 0,
            "unrooted_components": None,
        }
        return result

    root = np.asarray(root_flat, dtype=bool).reshape(cell_shape, order="F")
    root_count = int(np.count_nonzero(root))
    if root_count == 0:
        # A contract can carry an empty placeholder root array when no root
        # geometry was bound.  Preserve that fact without inventing a root
        # requirement; a native policy that requires roots is checked by the
        # upstream topology contract.
        result["root_connectivity"] = {
            "available": False,
            "ok": True,
            "status": "not_available",
            "root_cell_count": 0,
            "unrooted_components": None,
        }
        return result
    root_labels = set(int(value) for value in np.unique(labels[root & material]) if value > 0)
    all_labels = set(int(value) for value in np.unique(labels) if value > 0)
    unrooted = all_labels.difference(root_labels)
    missing_root = int(np.count_nonzero(root & ~material))
    ok = bool(missing_root == 0 and not unrooted)
    result["root_connectivity"] = {
        "available": True,
        "ok": ok,
        "status": "pass" if ok else "fail",
        "root_cell_count": root_count,
        "rooted_components": int(len(root_labels)),
        "unrooted_components": int(len(unrooted)),
        "missing_root_cells": missing_root,
    }
    return result


def _cell_density_to_points(
    grid: CartesianCellGrid,
    density: np.ndarray,
    name: str,
) -> tuple[pv.ImageData, np.ndarray]:
    image = pv.ImageData(
        dimensions=grid.point_dimensions,
        spacing=grid.spacing,
        origin=grid.origin,
    )
    image.cell_data[name] = np.ascontiguousarray(density, dtype=np.float64)
    point_image = image.cell_data_to_point_data(pass_cell_data=False)
    point_values = np.asarray(point_image.point_data[name], dtype=np.float64)
    expected = int(np.prod(grid.point_dimensions, dtype=np.int64))
    if point_values.shape != (expected,) or not np.isfinite(point_values).all():
        raise ValueError("cell-data-to-point-data interpolation produced invalid rho values")
    return point_image, point_values


def _read_and_validate_surface(path: Path) -> trimesh.Trimesh:
    try:
        mesh = trimesh.load_mesh(path, process=True)
    except Exception as exc:
        raise ValueError(f"Unable to read generated iso-surface STL: {path}") from exc
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("Generated iso-surface STL must contain one mesh")
    if mesh.is_empty or len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("Generated iso-surface STL is empty")
    if not np.isfinite(mesh.vertices).all() or not np.isfinite(mesh.faces).all():
        raise ValueError("Generated iso-surface STL contains non-finite geometry")
    if not mesh.is_watertight:
        raise ValueError("Generated iso-surface STL must be watertight")
    if not mesh.is_volume or not isfinite(float(mesh.volume)) or float(mesh.volume) <= 0.0:
        raise ValueError("Generated iso-surface STL must enclose a positive volume")
    return mesh


def _build_sdf_values(mesh: trimesh.Trimesh, grid: CartesianCellGrid) -> np.ndarray:
    point_dimensions = grid.point_dimensions
    xs = grid.origin[0] + grid.spacing[0] * np.arange(point_dimensions[0], dtype=np.float64)
    ys = grid.origin[1] + grid.spacing[1] * np.arange(point_dimensions[1], dtype=np.float64)
    zs = grid.origin[2] + grid.spacing[2] * np.arange(point_dimensions[2], dtype=np.float64)
    x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")
    points = np.column_stack((x.ravel(order="F"), y.ravel(order="F"), z.ravel(order="F")))
    values = signed_distance(mesh, points)
    if values.shape != (int(np.prod(point_dimensions, dtype=np.int64)),) or not np.isfinite(values).all():
        raise ValueError("Signed-distance evaluation produced invalid values")
    if not np.any(values < 0.0) or not np.any(values > 0.0):
        raise ValueError(
            "Signed-distance field does not contain both inside and outside samples; "
            "the source grid cannot establish the SDF sign"
        )
    return values.reshape(point_dimensions, order="F")


def _build_revoxelized_density(
    mesh: trimesh.Trimesh,
    grid: CartesianCellGrid,
) -> np.ndarray:
    axes = [
        grid.origin[index]
        + grid.spacing[index] * (np.arange(grid.cell_shape[index], dtype=np.float64) + 0.5)
        for index in range(3)
    ]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    centers = np.column_stack(
        (x.ravel(order="F"), y.ravel(order="F"), z.ravel(order="F"))
    )
    values = signed_distance(mesh, centers)
    if values.shape != (grid.cell_count,) or not np.isfinite(values).all():
        raise ValueError("Revoxelization produced invalid signed-distance samples")
    return np.asarray(values <= 0.0, dtype=np.uint8)


def _write_sdf_vti(
    path: Path,
    grid: CartesianCellGrid,
    sdf_values: np.ndarray,
    point_density: np.ndarray,
    variant: str,
    threshold: float,
    grid_sha256: str,
) -> None:
    image = pv.ImageData(
        dimensions=grid.point_dimensions,
        spacing=grid.spacing,
        origin=grid.origin,
    )
    image.point_data["sdf"] = np.ascontiguousarray(sdf_values.ravel(order="F"), dtype=np.float32)
    image.point_data[variant] = np.ascontiguousarray(point_density, dtype=np.float32)
    image.field_data["schema_version"] = np.array([HANDOFF_SCHEMA_VERSION], dtype=np.int32)
    image.field_data["kind"] = np.array([SDF_KIND])
    image.field_data["sdf_sign_convention"] = np.array([SDF_SIGN_CONVENTION])
    image.field_data["rho_variant"] = np.array([variant])
    image.field_data["iso_value"] = np.array([threshold], dtype=np.float64)
    image.field_data["grid_sha256"] = np.array([grid_sha256])
    image.save(path)


def _write_revoxelized_density_vti(
    path: Path,
    grid: CartesianCellGrid,
    density: np.ndarray,
    grid_sha256: str,
) -> None:
    image = pv.ImageData(
        dimensions=grid.point_dimensions,
        spacing=grid.spacing,
        origin=grid.origin,
    )
    image.cell_data["rho_revoxelized"] = np.ascontiguousarray(
        density,
        dtype=np.uint8,
    )
    image.field_data["schema_version"] = np.array(
        [HANDOFF_SCHEMA_VERSION], dtype=np.int32
    )
    image.field_data["kind"] = np.array(["stage_s_revoxelized_density"])
    image.field_data["cell_order"] = np.array([CANONICAL_CELL_ORDER])
    image.field_data["grid_sha256"] = np.array([grid_sha256])
    image.save(path)


def _build_geometry_binding(
    *,
    state: Mapping[str, Any],
    topology_hash: str,
    density_hash: str,
    surface_hash: str,
    sdf_hash: str,
    revoxelized_hash: str,
    grid_sha256: str,
    selected_variant: str,
    threshold: float,
) -> dict[str, object]:
    problem = state.get("problem")
    problem_mapping = problem if isinstance(problem, Mapping) else {}
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": "stage_t_to_stage_s_geometry_binding",
        "status": "diagnostic_only",
        "ready_for_stage_s": False,
        "problem_id": state.get("problem_id", problem_mapping.get("problem_id")),
        "problem_spec_sha256": state.get(
            "problem_spec_sha256",
            problem_mapping.get("problem_spec_sha256"),
        ),
        "candidate_id": state.get("candidate_id"),
        "parent_candidate_id": state.get("parent_candidate_id"),
        "geometry_role": "derived_design_surface",
        "coordinate_system": state.get("coordinate_system"),
        "source": {
            "topology_state_sha256": topology_hash,
            "density_vti_sha256": density_hash,
            "rho_variant": selected_variant,
            "iso_value": threshold,
            "grid_sha256": grid_sha256,
        },
        "derived": {
            "surface_stl": {"path": "iso_surface.stl", "sha256": surface_hash},
            "sdf_vti": {"path": "signed_distance.vti", "sha256": sdf_hash},
            "revoxelized_density_vti": {
                "path": "revoxelized_density.vti",
                "sha256": revoxelized_hash,
            },
        },
        "missing_lineage": [
            key
            for key, value in (
                ("problem_id", state.get("problem_id", problem_mapping.get("problem_id"))),
                (
                    "problem_spec_sha256",
                    state.get(
                        "problem_spec_sha256",
                        problem_mapping.get("problem_spec_sha256"),
                    ),
                ),
                ("candidate_id", state.get("candidate_id")),
            )
            if value is None
        ],
    }


def _handoff_qualification_reasons(
    *,
    mesh: trimesh.Trimesh,
    source_grid: CartesianCellGrid,
    source_component_checks: Mapping[str, Mapping[str, object]],
    revoxelized_mask_checks: Mapping[str, Mapping[str, object]],
    revoxelized_component_checks: Mapping[str, Mapping[str, object]],
    missing_lineage: object,
) -> list[str]:
    reasons = [
        "quantitative_fidelity_limits_not_configured",
        "surface_distance_not_evaluated",
        "minimum_feature_survival_not_evaluated",
        "self_intersection_not_evaluated",
    ]
    if missing_lineage:
        reasons.append("required_lineage_not_available")
    if not bool(source_component_checks["root_connectivity"].get("available")):
        reasons.append("source_root_connectivity_not_available")
    if not _checks_ok(revoxelized_mask_checks):
        reasons.append("revoxelized_mask_validation_failed")
    if not _checks_ok(revoxelized_component_checks):
        reasons.append("revoxelized_component_validation_failed")
    if not bool(
        revoxelized_component_checks["root_connectivity"].get("available")
    ):
        reasons.append("revoxelized_root_connectivity_not_available")
    extent = np.ptp(np.asarray(mesh.bounds, dtype=np.float64), axis=0)
    if np.any(extent < np.asarray(source_grid.spacing, dtype=np.float64)):
        reasons.append("surface_extent_below_one_source_cell")
    return reasons


def _build_fidelity_report(
    *,
    topology_state_path: Path,
    density_path: Path,
    topology_hash: str,
    density_hash: str,
    source_grid: CartesianCellGrid,
    grid: UniformCartesianCellGrid,
    density: np.ndarray,
    material: np.ndarray,
    threshold: float,
    selected_variant: str,
    source_mask_checks: Mapping[str, Mapping[str, object]],
    source_component_checks: Mapping[str, Mapping[str, object]],
    revoxelized_mask_checks: Mapping[str, Mapping[str, object]],
    revoxelized_component_checks: Mapping[str, Mapping[str, object]],
    mesh: trimesh.Trimesh,
    sdf_values: np.ndarray,
    revoxelized_density: np.ndarray,
    qualification_reasons: list[str],
    point_dimensions: tuple[int, int, int],
) -> dict[str, object]:
    cell_volume = float(np.prod(source_grid.spacing, dtype=np.float64))
    voxel_volume = float(np.count_nonzero(material) * cell_volume)
    mesh_volume = float(mesh.volume)
    revoxelized_volume = float(np.count_nonzero(revoxelized_density) * cell_volume)
    report = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": FIDELITY_REPORT_KIND,
        "status": "diagnostic_only",
        "ok": True,
        "ready_for_stage_s": False,
        "qualification_reasons": qualification_reasons,
        "inputs": {
            "topology_state_json": {"path": str(topology_state_path), "sha256": topology_hash},
            "density_vti": {"path": str(density_path), "sha256": density_hash},
        },
        "grid": {
            "origin_m": list(grid.origin),
            "spacing_m": list(grid.spacing),
            "cell_shape": list(grid.cell_shape),
            "point_dimensions": list(point_dimensions),
            "cell_order": CANONICAL_CELL_ORDER,
            "sha256": grid.sha256,
        },
        "rho": {
            "variant": selected_variant,
            "location": "cell",
            "iso_value": threshold,
            "surface_density_policy": (
                "rho_with_fixed_solid_overlay"
                if "fixed_solid_mask" in source_mask_checks
                and bool(source_mask_checks["fixed_solid_mask"].get("available"))
                else "rho"
            ),
            "min": float(np.min(density)),
            "max": float(np.max(density)),
            "mean": float(np.mean(density)),
        },
        "volume": {
            "cell_threshold_volume_m3": voxel_volume,
            "surface_mesh_volume_m3": mesh_volume,
            "revoxelized_cell_volume_m3": revoxelized_volume,
            "absolute_difference_m3": abs(mesh_volume - voxel_volume),
            "relative_difference": _relative_difference(mesh_volume, voxel_volume),
            "revoxelized_relative_difference": _relative_difference(
                revoxelized_volume,
                voxel_volume,
            ),
            "status": "diagnostic_only",
            "note": "Cell threshold volume and interpolated iso-surface volume use different discretizations.",
        },
        "surface": {
            "watertight": bool(mesh.is_watertight),
            "positive_volume": bool(mesh.is_volume and mesh.volume > 0.0),
            "component_count": int(len(mesh.split(only_watertight=False))),
            "vertex_count": int(len(mesh.vertices)),
            "face_count": int(len(mesh.faces)),
            "area_m2": float(mesh.area),
            "bounds_m": np.asarray(mesh.bounds, dtype=np.float64).tolist(),
        },
        "sdf": {
            "sign_convention": SDF_SIGN_CONVENTION,
            "location": "point",
            "min_m": float(np.min(sdf_values)),
            "max_m": float(np.max(sdf_values)),
            "negative_sample_count": int(np.count_nonzero(sdf_values < 0.0)),
            "positive_sample_count": int(np.count_nonzero(sdf_values > 0.0)),
            "zero_sample_count": int(np.count_nonzero(sdf_values == 0.0)),
            "finite": bool(np.isfinite(sdf_values).all()),
        },
        "qualification": "geometry_handoff_capability_only",
        "source_material_checks": {
            "masks": dict(source_mask_checks),
            "components": dict(source_component_checks),
        },
        "revoxelized_geometry_checks": {
            "masks": dict(revoxelized_mask_checks),
            "components": dict(revoxelized_component_checks),
        },
        "checks": {
            "input_hashes": True,
            "cell_data_contract": True,
            "surface_geometry": True,
            "sdf_sign": True,
            "source_mask_validation": _checks_ok(source_mask_checks),
            "source_component_validation": _checks_ok(source_component_checks),
            "revoxelized_mask_validation": _checks_ok(
                revoxelized_mask_checks
            ),
            "revoxelized_component_validation": _checks_ok(
                revoxelized_component_checks
            ),
        },
    }
    return report


def _build_manifest(
    *,
    state_path: Path,
    density_path: Path,
    topology_hash: str,
    density_hash: str,
    surface_hash: str,
    sdf_hash: str,
    revoxelized_hash: str,
    geometry_binding_hash: str,
    report_hash: str,
    source_grid: CartesianCellGrid,
    grid: UniformCartesianCellGrid,
    selected_variant: str,
    variant_source: str,
    threshold: float,
    threshold_source: str,
    source_mask_checks: Mapping[str, Mapping[str, object]],
    source_component_checks: Mapping[str, Mapping[str, object]],
    revoxelized_mask_checks: Mapping[str, Mapping[str, object]],
    revoxelized_component_checks: Mapping[str, Mapping[str, object]],
    mesh: trimesh.Trimesh,
    sdf_values: np.ndarray,
    qualification_reasons: list[str],
    report_path: Path,
) -> dict[str, object]:
    output_paths = {
        "source_topology_state": {
            "path": "source_topology_state.json",
            "sha256": topology_hash,
        },
        "source_density_vti": {
            "path": "source_density.vti",
            "sha256": density_hash,
        },
        "surface_stl": {"path": "iso_surface.stl", "sha256": surface_hash},
        "sdf_vti": {"path": "signed_distance.vti", "sha256": sdf_hash},
        "revoxelized_density_vti": {
            "path": "revoxelized_density.vti",
            "sha256": revoxelized_hash,
        },
        "geometry_binding": {
            "path": "geometry_binding.json",
            "sha256": geometry_binding_hash,
        },
        "fidelity_report": {"path": report_path.name, "sha256": report_hash},
    }
    grid_transform = {
        "kind": "identity",
        "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "translation_m": [0.0, 0.0, 0.0],
        "source_grid": {
            "origin_m": list(source_grid.origin),
            "spacing_m": list(source_grid.spacing),
            "cell_shape": list(source_grid.cell_shape),
            "point_dimensions": list(source_grid.point_dimensions),
            "cell_order": CANONICAL_CELL_ORDER,
            "location": "cell",
            "sha256": grid.sha256,
        },
        "sdf_grid": {
            "origin_m": list(source_grid.origin),
            "spacing_m": list(source_grid.spacing),
            "point_dimensions": list(source_grid.point_dimensions),
            "location": "point",
        },
        "cell_to_point": {
            "method": "vtk_cell_data_to_point_data",
            "weights": "arithmetic_mean_of_adjacent_cells",
        },
    }
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": HANDOFF_KIND,
        "status": "diagnostic_only",
        "ok": True,
        "ready_for_stage_s": False,
        "qualification_reasons": qualification_reasons,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "topology_state_json": {"path": str(state_path), "sha256": topology_hash},
            "density_vti": {"path": str(density_path), "sha256": density_hash},
        },
        "topology_state_sha256": topology_hash,
        "density_vti_sha256": density_hash,
        "rho": {
            "variant": selected_variant,
            "selection_source": variant_source,
            "location": "cell",
            "iso_value": threshold,
            "iso_value_source": threshold_source,
            "surface_density_policy": (
                "rho_with_fixed_solid_overlay"
                if "fixed_solid_mask" in source_mask_checks
                and bool(source_mask_checks["fixed_solid_mask"].get("available"))
                else "rho"
            ),
        },
        "grid_transform": grid_transform,
        "sdf": {
            "sign_convention": SDF_SIGN_CONVENTION,
            "location": "point",
            "finite": bool(np.isfinite(sdf_values).all()),
            "negative_sample_count": int(np.count_nonzero(sdf_values < 0.0)),
            "positive_sample_count": int(np.count_nonzero(sdf_values > 0.0)),
        },
        "qualification": "geometry_handoff_capability_only",
        "surface": {
            "watertight": bool(mesh.is_watertight),
            "positive_volume": bool(mesh.is_volume and mesh.volume > 0.0),
            "component_count": int(len(mesh.split(only_watertight=False))),
            "vertex_count": int(len(mesh.vertices)),
            "face_count": int(len(mesh.faces)),
        },
        "source_material_checks": {
            "masks": dict(source_mask_checks),
            "components": dict(source_component_checks),
        },
        "revoxelized_geometry_checks": {
            "masks": dict(revoxelized_mask_checks),
            "components": dict(revoxelized_component_checks),
        },
        "artifacts": output_paths,
    }


def _checks_ok(checks: Mapping[str, Mapping[str, object]]) -> bool:
    return all(bool(item.get("ok")) for item in checks.values())


def _validate_declared_density_hash(state: Mapping[str, Any], actual: str) -> None:
    candidates = [state.get("density_vti_sha256"), state.get("density_sha256")]
    artifacts = state.get("artifacts")
    if isinstance(artifacts, Mapping):
        item = artifacts.get("density_vti")
        if isinstance(item, Mapping):
            candidates.append(item.get("sha256"))
    for declared in candidates:
        if declared is None:
            continue
        _validate_optional_hash(str(declared), actual, "declared density VTI hash")


def _validate_optional_hash(expected: str | None, actual: str, name: str) -> None:
    if expected is None:
        return
    if not isinstance(expected, str) or _SHA256_RE.fullmatch(expected) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    if expected != actual:
        raise ValueError(f"{name} does not match the input artifact")


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _relative_difference(value: float, reference: float) -> float | None:
    scale = max(abs(reference), 1.0e-30)
    return float(abs(value - reference) / scale)


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


__all__ = [
    "CANONICAL_CELL_ORDER",
    "FIDELITY_REPORT_KIND",
    "HANDOFF_KIND",
    "HANDOFF_SCHEMA_VERSION",
    "SDF_KIND",
    "SDF_SIGN_CONVENTION",
    "DensityToSdfHandoffArtifacts",
    "build_density_to_sdf_handoff",
    "handoff_density_to_sdf",
]
