"""Fail-closed discrete topology checks for localized reference-state bundles.

This evaluator deliberately consumes an *already verified* immutable reference
bundle.  It neither reconstructs density from OpenFOAM nor makes any claim
about continuous geometry: the report scope is explicitly the x-fastest local
voxel grid.  All neighbourhood operations use a full-domain six-face SciPy
EDT/connected-component calculation written to disk-backed NPY arrays; no
slab/halo approximation is used for a topology decision.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import ctypes
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
from scipy import ndimage

from .localized_design_state_manifest import (
    LocalizedDesignGrid,
    load_and_verify_localized_design_state_manifest,
    require_localized_design_state_manifest_v2,
)
from .localized_reference_state_bundle import (
    LocalizedReferenceStateBundle,
    verify_localized_reference_state_bundle,
)
from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256


LOCALIZED_REFERENCE_TOPOLOGY_SCHEMA_VERSION = 1
LOCALIZED_REFERENCE_TOPOLOGY_KIND = "localized_reference_topology_report"
LOCALIZED_REFERENCE_TOPOLOGY_FILENAME = "localized_reference_topology.json"
_CHUNK = 1_048_576
# A full 87.5M-cell EDT/label calculation has several simultaneously live
# disk-backed arrays plus SciPy working storage.  This is intentionally above
# the reference-state bundle guard; callers can inject probes in small tests.
_MIN_DISK_BYTES = 10 * 1024**3
_MIN_MEMORY_BYTES = 8 * 1024**3
_STRUCTURE_6 = ndimage.generate_binary_structure(3, 1)


@dataclass(frozen=True)
class LocalizedReferenceTopologyReport:
    path: Path
    status: str
    reasons: tuple[str, ...]


def evaluate_localized_reference_topology(
    problem: ProblemSpec | str | Path,
    *,
    reference_bundle_path: str | Path,
    output_dir: str | Path,
    disk_free_bytes: Callable[[Path], int] | None = None,
    available_memory_bytes: Callable[[], int] | None = None,
) -> LocalizedReferenceTopologyReport:
    """Evaluate the immutable local reference state and atomically publish a report.

    Bad bundle/provenance, output, resource, or SciPy failures are exceptions
    and never publish a directory.  A physically evaluated but noncompliant
    state instead publishes a ``status='rejected'`` report with every detected
    deterministic reason.
    """
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not isinstance(spec, ProblemSpec):
        raise ValueError("problem must be a ProblemSpec or project YAML path")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite topology report: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    # This calls the expensive independent state/transformation verifier first;
    # topology code never accepts a merely plausible directory of NPY files.
    bundle = verify_localized_reference_state_bundle(reference_bundle_path, problem=spec)
    _require_resources(destination.parent, disk_free_bytes, available_memory_bytes)
    inputs = _load_verified_inputs(bundle, spec)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        result = _evaluate_to_dict(spec, bundle, inputs, staging)
        _write_json(staging / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME, result)
        # Deliberately only expose fully written logical outcomes.
        os.replace(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedReferenceTopologyReport(
        destination / LOCALIZED_REFERENCE_TOPOLOGY_FILENAME,
        str(result["status"]),
        tuple(str(item) for item in result["reasons"]),
    )


@dataclass(frozen=True)
class _Inputs:
    grid: LocalizedDesignGrid
    active: np.ndarray
    forbidden: np.ndarray
    fixed: np.ndarray
    root: np.ndarray
    rho_projected: np.ndarray
    state_manifest_sha256: str
    mask_hashes: Mapping[str, str]
    rho_projected_sha256: str


def _load_verified_inputs(bundle: LocalizedReferenceStateBundle, spec: ProblemSpec) -> _Inputs:
    root = bundle.path
    state_path = root / "localized_design_state_manifest.json"
    state = require_localized_design_state_manifest_v2(
        load_and_verify_localized_design_state_manifest(
            state_path, expected_problem_spec_sha256=problem_spec_sha256(spec)
        )
    ).manifest
    if state.sha256 != bundle.state_manifest_sha256:
        raise ValueError("verified reference bundle state-manifest binding changed")
    arrays = {
        name: np.load(root / state.masks[name].relative_path, mmap_mode="r", allow_pickle=False)
        for name in state.masks
    }
    projected = np.load(root / state.states["rho_projected"].relative_path, mmap_mode="r", allow_pickle=False)
    expected = state.grid.cell_count
    if projected.dtype != np.dtype(np.float64) or projected.shape != (expected,):
        raise ValueError("verified reference bundle has invalid rho_projected layout")
    if not np.isfinite(projected).all():
        raise ValueError("verified reference bundle has non-finite rho_projected values")
    return _Inputs(
        state.grid,
        arrays["active_design_mask"], arrays["forbidden_mask"], arrays["fixed_solid_mask"], arrays["root_mask"],
        projected, state.sha256,
        {name: state.masks[name].byte_sha256 for name in state.masks}, state.states["rho_projected"].byte_sha256,
    )


def _evaluate_to_dict(spec: ProblemSpec, bundle: LocalizedReferenceStateBundle, inputs: _Inputs, work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    shape = inputs.grid.cell_shape
    nx, ny, nz = shape
    spatial_shape = (nz, ny, nx)  # C order corresponds exactly to x-fastest vectors.
    policy = spec.topology_policy
    unsupported = _multiple_groups_unsupported(policy)
    if unsupported:
        return _report_base(spec, bundle, inputs, status="rejected", reasons=unsupported, checks={})

    active = _as_3d(inputs.active, spatial_shape)
    forbidden = _as_3d(inputs.forbidden, spatial_shape)
    fixed = _as_3d(inputs.fixed, spatial_shape)
    root = _as_3d(inputs.root, spatial_shape)
    rho = _as_3d(inputs.rho_projected, spatial_shape)
    d = _new_bool(work / "design_domain.npy", spatial_shape)
    solid = _new_bool(work / "solid.npy", spatial_shape)
    void = _new_bool(work / "void.npy", spatial_shape)
    try:
        d[:] = active | fixed | forbidden
        solid[:] = fixed | (active & (rho >= 0.5))
        void[:] = d & ~solid
        d.flush(); solid.flush(); void.flush()
        reasons: list[str] = []
        checks: dict[str, Any] = {
            "digital_state": {
                "design_domain_count": int(np.count_nonzero(d)),
                "solid_count": int(np.count_nonzero(solid)),
                "void_count": int(np.count_nonzero(void)),
                "first_solid_index": _first_index(solid, inputs.grid),
                "first_void_index": _first_index(void, inputs.grid),
            }
        }
        _connectivity_checks(solid, root, policy.solid_connectivity, inputs.grid, work, "solid", reasons, checks)
        _void_component_checks(void, d, policy.void_connectivity, inputs.grid, work, reasons, checks)
        _erosion_checks(solid, active, root, policy.solid_connectivity, policy.erosion_radius_m, inputs.grid, work, reasons, checks)
        _width_checks(solid, void, d, policy, inputs.grid, work, reasons, checks)
        return _report_base(spec, bundle, inputs, status="success" if not reasons else "rejected", reasons=reasons, checks=checks)
    finally:
        del void, solid, d


def _multiple_groups_unsupported(policy: Any) -> list[str]:
    required = set(policy.solid_connectivity.required_root_group_ids) | set(policy.void_connectivity.required_root_group_ids)
    return ["multiple_required_root_groups_unsupported"] if len(required) > 1 else []


def _connectivity_checks(
    solid: np.ndarray, root: np.ndarray, connectivity: Any, grid: LocalizedDesignGrid, work: Path,
    label: str, reasons: list[str], checks: dict[str, Any],
) -> None:
    if connectivity.mode == "disabled":
        checks[f"{label}_connectivity_nominal"] = {"enabled": False}
        return
    component_count, labels = _label(solid, work / f"{label}_labels.npy")
    try:
        component_info = _component_root_info(labels, root, component_count, grid)
        failed = _connectivity_reasons(component_count, component_info, connectivity, label, eroded=False)
        reasons.extend(failed)
        checks[f"{label}_connectivity_nominal"] = {
            "enabled": True, "component_count": component_count, "components": component_info, "reasons": failed,
        }
    finally:
        del labels


def _void_component_checks(
    void: np.ndarray, domain: np.ndarray, connectivity: Any, grid: LocalizedDesignGrid, work: Path,
    reasons: list[str], checks: dict[str, Any],
) -> None:
    # Void policy currently has no root mount semantics.  Still record full
    # connected components, so a future policy can bind an explicit void mask.
    if connectivity.mode == "disabled":
        checks["void_connectivity_nominal"] = {"enabled": False}
        return
    count, labels = _label(void, work / "void_labels.npy")
    try:
        failed: list[str] = []
        if connectivity.max_components is not None and count > connectivity.max_components:
            failed.append("void_component_count_exceeds_max")
        reasons.extend(failed)
        checks["void_connectivity_nominal"] = {"enabled": True, "component_count": count, "reasons": failed}
    finally:
        del labels


def _erosion_checks(
    solid: np.ndarray, active: np.ndarray, root: np.ndarray, connectivity: Any, radius: float | None,
    grid: LocalizedDesignGrid, work: Path, reasons: list[str], checks: dict[str, Any],
) -> None:
    if radius is None:
        return
    distance = _edt(solid, grid, work / "solid_edt.npy")
    eroded = _new_bool(work / "solid_eroded.npy", solid.shape)
    try:
        eroded[:] = root  # root is a subset of fixed; mount union is preserved.
        # Fixed solid must persist even if it is not a root; derive it from
        # solid & ~active, because only active cells are mutable state.
        eroded[:] |= solid & ~active
        eroded[:] |= active & solid & (distance > radius)
        removed_active = int(np.count_nonzero(active & solid & ~eroded))
        active_solid = int(np.count_nonzero(active & solid))
        failed: list[str] = []
        if active_solid > 0 and removed_active == 0:
            failed.append("erosion_no_effect")
        reasons.extend(failed)
        checks["erosion"] = {"radius_m": radius, "active_solid_count": active_solid, "removed_active_count": removed_active, "reasons": failed}
        if connectivity.mode != "disabled" and connectivity.evaluate_eroded:
            count, labels = _label(eroded, work / "solid_eroded_labels.npy")
            try:
                info = _component_root_info(labels, root, count, grid)
                failed = _connectivity_reasons(count, info, connectivity, "solid", eroded=True)
                reasons.extend(failed)
                checks["solid_connectivity_eroded"] = {"enabled": True, "component_count": count, "components": info, "reasons": failed}
            finally:
                del labels
    finally:
        del eroded, distance


def _width_checks(solid: np.ndarray, void: np.ndarray, domain: np.ndarray, policy: Any, grid: LocalizedDesignGrid,
                  work: Path, reasons: list[str], checks: dict[str, Any]) -> None:
    _rolling_ball_check("minimum_solid_width", solid, _half_width(policy.minimum_solid_width_m), grid, work, reasons, checks)
    count, labels = _label(void, work / "void_for_width_labels.npy")
    try:
        external = _external_void_labels(labels, domain, count)
        enclosed = void & ~external[labels]
        gap = void & external[labels]
        _rolling_ball_check("minimum_void_width", enclosed, _half_width(policy.minimum_void_width_m), grid, work, reasons, checks)
        _rolling_ball_check("minimum_gap", gap, _half_width(policy.minimum_gap_m), grid, work, reasons, checks)
    finally:
        del labels


def _rolling_ball_check(name: str, candidate: np.ndarray, radius: float | None, grid: LocalizedDesignGrid, work: Path,
                        reasons: list[str], checks: dict[str, Any]) -> None:
    if radius is None:
        return
    distance = _edt(candidate, grid, work / f"{name}_edt.npy")
    core = _new_bool(work / f"{name}_core.npy", candidate.shape)
    opened = _new_bool(work / f"{name}_opened.npy", candidate.shape)
    try:
        core[:] = candidate & (distance > radius)
        # Dilation of the strict EDT core is the exact grid rolling-ball
        # opening; crop back to the candidate to avoid borrowing outside D.
        dilation = _edt(~core, grid, work / f"{name}_core_complement_edt.npy")
        try:
            opened[:] = candidate & (dilation <= radius)
        finally:
            del dilation
        violation = candidate & ~opened
        count = int(np.count_nonzero(violation))
        failed = [name] if count else []
        reasons.extend(failed)
        checks[name] = {"radius_m": radius, "candidate_count": int(np.count_nonzero(candidate)), "violation_count": count,
                        "first_violation_index": _first_index(violation, grid), "reasons": failed}
    finally:
        del opened, core, distance


def _label(values: np.ndarray, path: Path) -> tuple[int, np.ndarray]:
    labels = np.lib.format.open_memmap(path, mode="w+", dtype=np.int32, shape=values.shape)
    count = int(ndimage.label(values, structure=_STRUCTURE_6, output=labels))
    labels.flush()
    return count, labels


def _edt(values: np.ndarray, grid: LocalizedDesignGrid, path: Path) -> np.ndarray:
    distances = np.lib.format.open_memmap(path, mode="w+", dtype=np.float64, shape=values.shape)
    # values are (z,y,x), while physical spacing is supplied in that order.
    ndimage.distance_transform_edt(values, sampling=tuple(reversed(grid.spacing)), distances=distances)
    distances.flush()
    return distances


def _component_root_info(labels: np.ndarray, root: np.ndarray, count: int, grid: LocalizedDesignGrid) -> list[dict[str, Any]]:
    root_labels = np.unique(labels[root]) if np.any(root) else np.asarray([], dtype=np.int32)
    root_set = {int(item) for item in root_labels if int(item) != 0}
    return [{"label": item, "touches_root": item in root_set, "first_index": _first_label_index(labels, item, grid)} for item in range(1, count + 1)]


def _connectivity_reasons(count: int, components: list[dict[str, Any]], connectivity: Any, label: str, *, eroded: bool) -> list[str]:
    suffix = "_eroded" if eroded else "_nominal"
    result: list[str] = []
    if connectivity.max_components is not None and count > connectivity.max_components:
        result.append(f"{label}_component_count_exceeds_max{suffix}")
    if connectivity.mode in {"root_connected", "required_root_groups"}:
        if any(not item["touches_root"] for item in components):
            result.append(f"{label}_component_without_root{suffix}")
        if count == 0 or not any(item["touches_root"] for item in components):
            result.append(f"required_root_group_without_component{suffix}")
    elif connectivity.mode == "single_component" and count > 1:
        result.append(f"{label}_multiple_components{suffix}")
    return result


def _half_width(value: float | None) -> float | None:
    return None if value is None else float(value) / 2.0


def _external_void_labels(labels: np.ndarray, domain: np.ndarray, count: int) -> np.ndarray:
    # A void component is external exactly when one of its voxels faces a
    # non-domain voxel or an array boundary.  This uses six faces only.
    boundary = np.zeros(domain.shape, dtype=np.bool_)
    boundary[0] = boundary[-1] = True
    boundary[:, 0] = True; boundary[:, -1] = True
    boundary[:, :, 0] = True; boundary[:, :, -1] = True
    for axis in range(3):
        source = [slice(None)] * 3; neighbor = [slice(None)] * 3
        source[axis] = slice(1, None); neighbor[axis] = slice(None, -1)
        boundary[tuple(source)] |= domain[tuple(source)] & ~domain[tuple(neighbor)]
        source[axis] = slice(None, -1); neighbor[axis] = slice(1, None)
        boundary[tuple(source)] |= domain[tuple(source)] & ~domain[tuple(neighbor)]
    external = np.zeros(count + 1, dtype=np.bool_)
    external[np.unique(labels[boundary])] = True
    external[0] = False
    return external


def _as_3d(values: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    return values.reshape(shape, order="C")


def _new_bool(path: Path, shape: tuple[int, int, int]) -> np.ndarray:
    return np.lib.format.open_memmap(path, mode="w+", dtype=np.bool_, shape=shape)


def _first_index(values: np.ndarray, grid: LocalizedDesignGrid) -> int | None:
    found = np.flatnonzero(values.ravel(order="C"))
    return int(found[0]) if found.size else None


def _first_label_index(labels: np.ndarray, label: int, grid: LocalizedDesignGrid) -> int | None:
    found = np.flatnonzero(labels.ravel(order="C") == label)
    return int(found[0]) if found.size else None


def _report_base(spec: ProblemSpec, bundle: LocalizedReferenceStateBundle, inputs: _Inputs, *, status: str,
                 reasons: list[str], checks: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": LOCALIZED_REFERENCE_TOPOLOGY_SCHEMA_VERSION,
        "kind": LOCALIZED_REFERENCE_TOPOLOGY_KIND,
        "scope": "discrete_voxel_topology_only",
        "status": status,
        "reasons": list(dict.fromkeys(reasons)),
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "reference_bundle_path": str(bundle.path),
        "reference_state_manifest_sha256": inputs.state_manifest_sha256,
        "reference_bundle_geometry_snapshot_sha256": bundle.geometry_snapshot.sha256,
        "reference_bundle_raw_manifest_sha256": bundle.raw_manifest_sha256,
        "initial_design_stl_sha256": bundle.initial_design_stl_sha256,
        "grid_sha256": inputs.grid.sha256,
        "grid": {"origin": list(inputs.grid.origin), "spacing": list(inputs.grid.spacing), "cell_shape": list(inputs.grid.cell_shape), "cell_order": inputs.grid.cell_order},
        "mask_sha256": dict(sorted(inputs.mask_hashes.items())),
        "rho_projected_sha256": inputs.rho_projected_sha256,
        "threshold": {"operator": ">=", "value": 0.5},
        "neighborhood": "6_face",
        "checks": checks,
        "limitations": [
            "discrete_voxel_topology_only",
            "does_not_prove_continuous_manufacturability",
            "does_not_qualify_openfoam_or_native_v2",
            "root_mask_is_a_union_and_cannot_evaluate_multiple_required_root_groups",
        ],
    }


def _require_resources(parent: Path, disk_probe: Callable[[Path], int] | None, memory_probe: Callable[[], int] | None) -> None:
    disk = int((disk_probe or (lambda path: shutil.disk_usage(path).free))(parent))
    memory = int((memory_probe or _available_memory_bytes)())
    if disk < _MIN_DISK_BYTES:
        raise ValueError("localized reference topology evaluator requires at least 10 GiB free disk")
    if memory < _MIN_MEMORY_BYTES:
        raise ValueError("localized reference topology evaluator requires at least 8 GiB available RAM")


def _available_memory_bytes() -> int:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, ValueError, OSError):
        return 0


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


__all__ = [
    "LOCALIZED_REFERENCE_TOPOLOGY_FILENAME", "LOCALIZED_REFERENCE_TOPOLOGY_KIND",
    "LOCALIZED_REFERENCE_TOPOLOGY_SCHEMA_VERSION", "LocalizedReferenceTopologyReport",
    "evaluate_localized_reference_topology",
]
