"""Forward-only feasibility initialization for a rejected local STL state.

This module deliberately does *not* alter the direct-STL reference bundle.
It derives a separately named raw-density state, evaluates every candidate with
the same full discrete topology evaluator, and publishes nothing unless the
derived projected state succeeds.  In particular, this is not an inverse of
the filter/projection and it must not reuse the direct-STL alpha binding.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    create_localized_design_state_manifest,
    load_and_verify_localized_design_state_manifest,
    localized_design_state_manifest_sha256,
    require_localized_design_state_manifest_v2,
    write_localized_design_state_manifest,
)
from .localized_filter_projection import (
    apply_localized_cone_filter,
    apply_localized_heaviside_projection,
    read_canonical_filter_config,
    read_canonical_projection_config,
)
from .localized_reference_state_bundle import (
    LocalizedReferenceStateBundle,
    verify_localized_reference_state_bundle,
)
from .localized_reference_topology import _Inputs, _STRUCTURE_6, _evaluate_to_dict, _external_void_labels
from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256


LOCALIZED_FEASIBLE_DERIVED_STATE_KIND = "localized_feasible_derived_state"
LOCALIZED_FEASIBLE_DERIVED_STATE_FILENAME = "localized_feasible_derived_state.json"
LOCALIZED_FEASIBLE_DERIVED_STATE_FAILURE_KIND = "localized_feasible_derived_state_failure"


@dataclass(frozen=True)
class FeasibilityInitializerConfig:
    """Bounded repair controls; policy radii are read only from the project."""

    max_iterations: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.max_iterations, int) or isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "constraint_aware_feasibility_projection_controls",
            "schema_version": 1,
            "max_iterations": self.max_iterations,
            "thin_solid_removal": "strict_edt_rolling_opening",
            "narrow_external_gap_fill": "strict_edt_rolling_opening_complement",
            "input_variable": "rho_raw_only",
            "inverse_projection": "forbidden",
        }


@dataclass(frozen=True)
class LocalizedFeasibleDerivedState:
    path: Path
    state_manifest_path: Path
    topology_report_path: Path


def localized_feasible_initializer_failure_report_path(output_dir: str | Path) -> Path:
    destination = Path(output_dir)
    return destination.parent / f".{destination.name}.feasibility-failure.json"


def build_localized_feasible_derived_state(
    problem: ProblemSpec | str | Path,
    *,
    direct_reference_bundle_path: str | Path,
    rejected_topology_report_path: str | Path,
    output_dir: str | Path,
    config: FeasibilityInitializerConfig = FeasibilityInitializerConfig(),
) -> LocalizedFeasibleDerivedState:
    """Derive and publish a feasible state, or publish a diagnostic only.

    The input bundle is independently verified before use.  The caller must
    name a rejected report bound to that exact direct-STL bundle; this prevents
    a derived state from erasing the benchmark's failure evidence.
    """
    spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    if not isinstance(spec, ProblemSpec) or not isinstance(config, FeasibilityInitializerConfig):
        raise ValueError("problem and config are invalid")
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite feasible derived state: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = verify_localized_reference_state_bundle(direct_reference_bundle_path, problem=spec)
    parent_state = require_localized_design_state_manifest_v2(
        load_and_verify_localized_design_state_manifest(
            parent.path / "localized_design_state_manifest.json",
            expected_problem_spec_sha256=problem_spec_sha256(spec),
        )
    ).manifest
    parent_report_path = Path(rejected_topology_report_path)
    parent_report = _read_json(parent_report_path)
    _require_parent_rejected_report(parent_report, parent_report_path, parent, parent_state)

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    records: list[dict[str, Any]] = []
    stop_reason = "unknown"
    try:
        arrays = _load_parent_arrays(parent, parent_state)
        active, forbidden, fixed, root = (arrays[name] for name in ("active_design_mask", "forbidden_mask", "fixed_solid_mask", "root_mask"))
        source_raw = arrays["rho"]
        filter_config = read_canonical_filter_config(parent.path / parent_state.filter_config.relative_path)  # type: ignore[union-attr]
        projection_config = read_canonical_projection_config(parent.path / parent_state.projection_config.relative_path)  # type: ignore[union-attr]
        candidate = np.asarray(source_raw, dtype=np.float64).copy()
        candidate[~active] = 0.0
        success: tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None = None
        for iteration in range(config.max_iterations + 1):
            filtered = apply_localized_cone_filter(candidate, active, parent_state.grid, config=filter_config)
            projected = apply_localized_heaviside_projection(filtered, active, config=projection_config)
            report = _full_topology_report(spec, parent, parent_state.grid, active, forbidden, fixed, root, projected, staging / f"topology_work_{iteration:02d}")
            record = {
                "iteration": iteration,
                "rho_raw_sha256": _sha256_array(candidate),
                "rho_filtered_sha256": _sha256_array(filtered),
                "rho_projected_sha256": _sha256_array(projected),
                "topology_report_sha256": _sha256_json(report),
                "topology_status": report["status"],
                "topology_reasons": report["reasons"],
            }
            records.append(record)
            if report["status"] == "success":
                success = (candidate, filtered, projected, report)
                stop_reason = "topology_success"
                break
            if iteration == config.max_iterations:
                stop_reason = "maximum_iterations_rejected"
                break
            repaired = repair_raw_density_forward_only(
                candidate, active, root, parent_state.grid, spec,
            )
            if np.array_equal(repaired, candidate):
                stop_reason = "repair_fixed_point_rejected"
                break
            candidate = repaired
        if success is None:
            _write_failure_report(destination, parent, parent_report_path, records, stop_reason, config)
            raise ValueError(f"feasibility initializer did not produce a topology-success state: {stop_reason}")
        _publish_success(
            staging, destination, parent, parent_state, parent_report_path, parent_report,
            active, forbidden, fixed, root, source_raw, arrays["rho_projected"], success, records, stop_reason, config,
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedFeasibleDerivedState(
        destination,
        destination / "localized_design_state_manifest.json",
        destination / "topology" / "localized_reference_topology.json",
    )


def repair_raw_density_forward_only(
    rho_raw: np.ndarray,
    active_design_mask: np.ndarray,
    root_mask: np.ndarray,
    grid: LocalizedDesignGrid,
    problem: ProblemSpec,
) -> np.ndarray:
    """One deterministic raw-only repair step under the unchanged policy.

    The repair first removes active solid features below the policy minimum
    width, then fills only *external* gaps below the policy minimum gap.  Root
    cells are preserved in the topology solid but are never written into raw
    cells outside the active design domain.
    """
    n = grid.cell_count
    raw = _state_vector(rho_raw, n, "rho_raw")
    active = _mask_vector(active_design_mask, n, "active_design_mask")
    root = _mask_vector(root_mask, n, "root_mask")
    if np.any(root & active):
        raise ValueError("root_mask must not overlap active_design_mask")
    policy = problem.topology_policy
    shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    active3 = active.reshape(shape); root3 = root.reshape(shape)
    solid = (active & (raw >= 0.5) | root).reshape(shape)
    if policy.minimum_solid_width_m is not None:
        opened = _strict_opening(solid, float(policy.minimum_solid_width_m) / 2.0, grid)
        solid = (opened | root3) & (active3 | root3)
    domain = active3 | root3
    void = domain & ~solid
    if policy.minimum_gap_m is not None:
        labels, count = ndimage.label(void, structure=_STRUCTURE_6)
        external = _external_void_labels(labels, domain, int(count))
        gap = void & external[labels]
        opened_gap = _strict_opening(gap, float(policy.minimum_gap_m) / 2.0, grid)
        solid |= gap & ~opened_gap & active3
    result = np.zeros(n, dtype=np.float64)
    result[active] = solid.ravel(order="C")[active].astype(np.float64)
    return result


def _strict_opening(candidate: np.ndarray, radius_m: float, grid: LocalizedDesignGrid) -> np.ndarray:
    if radius_m <= 0.0:
        return candidate.copy()
    sampling = tuple(reversed(grid.spacing))
    core = candidate & (ndimage.distance_transform_edt(candidate, sampling=sampling) > radius_m)
    return candidate & (ndimage.distance_transform_edt(~core, sampling=sampling) <= radius_m)


def _full_topology_report(
    spec: ProblemSpec, parent: LocalizedReferenceStateBundle, grid: LocalizedDesignGrid,
    active: np.ndarray, forbidden: np.ndarray, fixed: np.ndarray, root: np.ndarray,
    projected: np.ndarray, work: Path,
) -> dict[str, Any]:
    """Run the production topology decision kernel without publishing a bundle.

    The public evaluator intentionally accepts only direct-STL bundles.  A
    derived state therefore calls its identical full-domain kernel directly,
    carrying the parent bundle separately in derived provenance.
    """
    inputs = _Inputs(
        grid, active, forbidden, fixed, root, projected,
        "0" * 64,
        {name: _sha256_array(values) for name, values in {
            "active_design_mask": active, "forbidden_mask": forbidden,
            "fixed_solid_mask": fixed, "root_mask": root,
        }.items()},
        _sha256_array(projected),
    )
    raw = _evaluate_to_dict(spec, parent, inputs, work)
    # Do not emit a standard ``localized_reference_topology_report`` here:
    # its public provenance schema is reserved for verified direct-STL bundles.
    # This envelope preserves the same checks while identifying the derived
    # projected state explicitly instead of inventing a direct-STL manifest.
    return {
        "schema_version": 1,
        "kind": "localized_feasible_derived_topology_report",
        "evaluator": "cfd_sdf.localized_reference_topology._evaluate_to_dict",
        "status": raw["status"],
        "reasons": raw["reasons"],
        "grid_sha256": grid.sha256,
        "rho_projected_sha256": _sha256_array(projected),
        "mask_sha256": inputs.mask_hashes,
        "threshold": raw["threshold"],
        "neighborhood": raw["neighborhood"],
        "checks": raw["checks"],
        "limitations": raw["limitations"],
    }


def _publish_success(
    staging: Path, destination: Path, parent: LocalizedReferenceStateBundle, parent_state: Any,
    parent_report_path: Path, parent_report: dict[str, Any], active: np.ndarray, forbidden: np.ndarray,
    fixed: np.ndarray, root: np.ndarray, source_raw: np.ndarray, source_projected: np.ndarray,
    success: tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]], records: list[dict[str, Any]],
    stop_reason: str, config: FeasibilityInitializerConfig,
) -> None:
    derived_raw, filtered, projected, topology_report = success
    geometry = staging / "geometry_snapshot"
    shutil.copytree(parent.path / "geometry_snapshot", geometry, copy_function=shutil.copy2)
    states = staging / "states"; states.mkdir()
    for name, values in (("rho", derived_raw), ("rho_filtered", filtered), ("rho_projected", projected)):
        np.save(states / f"{name}.npy", np.asarray(values, dtype=np.float64), allow_pickle=False)
    configs = staging / "configs"; configs.mkdir()
    shutil.copy2(parent.path / parent_state.filter_config.relative_path, configs / "filter_config.json")
    shutil.copy2(parent.path / parent_state.projection_config.relative_path, configs / "projection_config.json")
    manifest_path = staging / "localized_design_state_manifest.json"
    state = create_localized_design_state_manifest(
        path=manifest_path, problem_spec_sha256=parent_state.problem_spec_sha256, grid=parent_state.grid,
        masks={name: geometry / _geometry_relative_path(artifact.relative_path) for name, artifact in parent_state.masks.items()},
        states={name: states / f"{name}.npy" for name in ("rho", "rho_filtered", "rho_projected")},
        filter_config_sha256=parent_state.filter_config_sha256, projection_config_sha256=parent_state.projection_config_sha256,
        filter_config_path=configs / "filter_config.json", projection_config_path=configs / "projection_config.json",
    )
    write_localized_design_state_manifest(state)
    topology = staging / "topology"; topology.mkdir()
    _write_json(topology / "localized_reference_topology.json", topology_report)
    metrics = _difference_metrics(source_raw, source_projected, derived_raw, projected, active, parent_state.grid)
    payload = {
        "schema_version": 1,
        "kind": LOCALIZED_FEASIBLE_DERIVED_STATE_KIND,
        "initialization_kind": "constraint_aware_feasibility_projection",
        "parent_direct_stl_bundle_path": str(parent.path),
        "parent_direct_state_manifest_sha256": parent.state_manifest_sha256,
        "parent_direct_raw_manifest_sha256": parent.raw_manifest_sha256,
        "parent_rejected_topology_report_path": str(parent_report_path),
        "parent_rejected_topology_report_sha256": _sha256_file(parent_report_path),
        "parent_rejected_topology_status": parent_report["status"],
        "derived_state_manifest_sha256": localized_design_state_manifest_sha256(state),
        "source_state_hashes": {name: artifact.byte_sha256 for name, artifact in parent_state.states.items()},
        "derived_state_hashes": {name: state.states[name].byte_sha256 for name in state.states},
        "mask_sha256": {name: state.masks[name].byte_sha256 for name in state.masks},
        "hard_mask_invariants": {"raw_zero_outside_active": True, "no_forbidden_material": True, "root_preserved_in_topology_solid": True},
        "repair": {"controls": config.to_dict(), "iterations": records, "stop_reason": stop_reason},
        "differences": metrics,
        "topology_report_relative_path": "topology/localized_reference_topology.json",
        "topology_report_sha256": _sha256_json(topology_report),
        "alpha_reference": {"direct_stl_binding_reused": False, "reason": "changed_projected_state_requires_new_alpha_reference_and_binding"},
    }
    _write_json(staging / LOCALIZED_FEASIBLE_DERIVED_STATE_FILENAME, payload)
    os.replace(staging, destination)


def _difference_metrics(source_raw: np.ndarray, source_projected: np.ndarray, derived_raw: np.ndarray,
                        projected: np.ndarray, active: np.ndarray, grid: LocalizedDesignGrid) -> dict[str, Any]:
    source_solid = active & (source_raw >= 0.5)
    derived_solid = active & (derived_raw >= 0.5)
    changed = source_solid ^ derived_solid
    union = source_solid | derived_solid
    voxel_volume = float(np.prod(grid.spacing))
    distances = _symmetric_solid_distance(source_solid, derived_solid, grid)
    return {
        "active_domain": {
            "added_mask_count": int(np.count_nonzero(derived_solid & ~source_solid)),
            "removed_mask_count": int(np.count_nonzero(source_solid & ~derived_solid)),
            "changed_mask_count": int(np.count_nonzero(changed)),
            "changed_volume_m3": float(np.count_nonzero(changed) * voxel_volume),
        },
        "raw_l1": float(np.sum(np.abs(derived_raw - source_raw))),
        "projected_l1": float(np.sum(np.abs(projected - source_projected))),
        "threshold_solid_symmetric_difference_count": int(np.count_nonzero(changed)),
        "threshold_solid_jaccard": float(np.count_nonzero(source_solid & derived_solid) / np.count_nonzero(union)) if np.any(union) else 1.0,
        "source_raw_volume_m3": float(np.sum(source_raw) * voxel_volume),
        "derived_raw_volume_m3": float(np.sum(derived_raw) * voxel_volume),
        "derived_projected_volume_m3": float(np.sum(projected) * voxel_volume),
        "derived_surface_distance_m": distances,
    }


def _symmetric_solid_distance(left: np.ndarray, right: np.ndarray, grid: LocalizedDesignGrid) -> dict[str, float | None]:
    if not np.any(left) or not np.any(right):
        return {"mean": None, "max": None, "method": "voxel_center_symmetric_edt"}
    shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    spacing = tuple(reversed(grid.spacing))
    left3, right3 = left.reshape(shape), right.reshape(shape)
    values = np.concatenate((ndimage.distance_transform_edt(~right3, sampling=spacing)[left3], ndimage.distance_transform_edt(~left3, sampling=spacing)[right3]))
    return {"mean": float(np.mean(values)), "max": float(np.max(values)), "method": "voxel_center_symmetric_edt"}


def _load_parent_arrays(parent: LocalizedReferenceStateBundle, state: Any) -> dict[str, np.ndarray]:
    values = {name: np.asarray(np.load(parent.path / artifact.relative_path, allow_pickle=False), dtype=np.bool_) for name, artifact in state.masks.items()}
    values.update({name: np.asarray(np.load(parent.path / artifact.relative_path, allow_pickle=False), dtype=np.float64) for name, artifact in state.states.items()})
    return values


def _geometry_relative_path(relative_path: str) -> Path:
    """Map a parent-state mask location into the copied geometry directory."""
    value = Path(relative_path)
    if not value.parts or value.parts[0] != "geometry_snapshot":
        raise ValueError("direct reference state masks must be located in geometry_snapshot")
    result = Path(*value.parts[1:])
    if not result.parts:
        raise ValueError("geometry snapshot mask path is invalid")
    return result


def _require_parent_rejected_report(report: dict[str, Any], path: Path, parent: LocalizedReferenceStateBundle, state: Any) -> None:
    if report.get("kind") != "localized_reference_topology_report" or report.get("status") != "rejected":
        raise ValueError("parent topology report must be a rejected localized topology report")
    if report.get("reference_bundle_path") != str(parent.path) or report.get("reference_state_manifest_sha256") != parent.state_manifest_sha256:
        raise ValueError("parent rejected topology report is not bound to the direct reference bundle")
    if report.get("rho_projected_sha256") != state.states["rho_projected"].byte_sha256:
        raise ValueError("parent rejected topology report does not bind the direct projected state")
    if not path.is_file():
        raise ValueError("parent rejected topology report is missing")


def _write_failure_report(destination: Path, parent: LocalizedReferenceStateBundle, parent_report_path: Path,
                          records: list[dict[str, Any]], stop_reason: str, config: FeasibilityInitializerConfig) -> None:
    _write_json(localized_feasible_initializer_failure_report_path(destination), {
        "schema_version": 1, "kind": LOCALIZED_FEASIBLE_DERIVED_STATE_FAILURE_KIND,
        "status": "rejected_no_feasible_bundle_published", "requested_output_directory": str(destination),
        "parent_direct_stl_bundle_path": str(parent.path), "parent_direct_state_manifest_sha256": parent.state_manifest_sha256,
        "parent_rejected_topology_report_path": str(parent_report_path), "parent_rejected_topology_report_sha256": _sha256_file(parent_report_path),
        "repair": {"controls": config.to_dict(), "iterations": records, "stop_reason": stop_reason},
        "alpha_reference": {"direct_stl_binding_reused": False},
    })


def _state_vector(values: np.ndarray, n: int, name: str) -> np.ndarray:
    value = np.asarray(values)
    if value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all() or np.any(value < 0.0) or np.any(value > 1.0):
        raise ValueError(f"{name} must be a finite float64 vector in [0, 1]")
    return value


def _mask_vector(values: np.ndarray, n: int, name: str) -> np.ndarray:
    value = np.asarray(values)
    if value.dtype != np.bool_ or value.shape != (n,):
        raise ValueError(f"{name} must be a bool vector with the grid cell count")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("JSON artifact must be an object")
    return raw


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _sha256_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


__all__ = [
    "FeasibilityInitializerConfig", "LocalizedFeasibleDerivedState",
    "LOCALIZED_FEASIBLE_DERIVED_STATE_FILENAME", "LOCALIZED_FEASIBLE_DERIVED_STATE_KIND",
    "build_localized_feasible_derived_state", "localized_feasible_initializer_failure_report_path",
    "repair_raw_density_forward_only",
]
