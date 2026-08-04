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
    LocalizedConeFilterConfig,
    apply_localized_cone_filter,
    apply_localized_heaviside_projection,
    read_canonical_filter_config,
    read_canonical_projection_config,
)
from .localized_filter_projection import _cone_offsets, _overlap_slices
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
            "schema_version": 2,
            "max_iterations": self.max_iterations,
            "thin_solid_removal": "projected_checker_target_exact_positive_cone_support_to_zero",
            "narrow_external_gap_fill": "projected_checker_external_gap_target_exact_positive_cone_support_to_one",
            "phase_order": ["remove", "checker", "fill", "checker"],
            "input_variable": "rho_raw_only",
            "inverse_projection": "forbidden",
        }


@dataclass(frozen=True)
class LocalizedFeasibleDerivedState:
    path: Path
    state_manifest_path: Path
    topology_report_path: Path


class _SupportRepairRejected(RuntimeError):
    """Internal fail-closed control path with sidecar-safe diagnostics."""

    def __init__(self, reason: str, details: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details


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
        _require_hard_mask_invariants(candidate, active, forbidden, root)
        seen_state_hashes: set[str] = {_sha256_array(candidate)}
        success: tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None = None
        failure_details: dict[str, Any] | None = None
        for iteration in range(config.max_iterations):
            # A round always records the unmodified candidate, then performs
            # removal -> checker -> fill -> checker.  This makes the target of
            # each phase the final projected topology result immediately before
            # that phase, never a raw threshold surrogate.
            filtered, projected, report = _evaluate_candidate(
                spec, parent, parent_state.grid, active, forbidden, fixed, root,
                candidate, filter_config, projection_config, staging / f"topology_work_{iteration:02d}_start",
            )
            start_record = _iteration_record(iteration, "start", candidate, filtered, projected, report)
            records.append(start_record)
            if report["status"] == "success":
                success = (candidate, filtered, projected, report)
                stop_reason = "topology_success"
                break

            try:
                thin_targets = _checker_targets(projected, active, root, parent_state.grid, spec, report)
                zero_buffer, zero_metadata = _exact_positive_cone_support(
                    thin_targets["minimum_solid_width"], active, parent_state.grid, filter_config,
                )
                after_remove = candidate.copy()
                after_remove[zero_buffer] = 0.0
                _require_hard_mask_invariants(after_remove, active, forbidden, root)
                remove_hash = _sha256_array(after_remove)
                if not np.array_equal(after_remove, candidate) and remove_hash in seen_state_hashes:
                    raise _SupportRepairRejected("repeated_state_or_cycle_rejected", {
                        "phase": "remove", "state_sha256": remove_hash,
                        "targets": {name: _target_metadata(value) for name, value in thin_targets.items()},
                        "zero_buffer": zero_metadata,
                    })
                if not np.array_equal(after_remove, candidate):
                    seen_state_hashes.add(remove_hash)
                filtered, projected, report = _evaluate_candidate(
                    spec, parent, parent_state.grid, active, forbidden, fixed, root,
                    after_remove, filter_config, projection_config, staging / f"topology_work_{iteration:02d}_remove",
                )
                remove_record = _iteration_record(iteration, "remove_then_check", after_remove, filtered, projected, report)
                remove_record["support_buffer"] = {"zero": zero_metadata}
                remove_record["targets"] = {"minimum_solid_width": _target_metadata(thin_targets["minimum_solid_width"])}
                remove_record["delta_from_previous"] = _raw_delta(candidate, after_remove)
                records.append(remove_record)
                if report["status"] == "success":
                    success = (after_remove, filtered, projected, report)
                    stop_reason = "topology_success_after_removal"
                    break

                gap_targets = _checker_targets(projected, active, root, parent_state.grid, spec, report)
                one_buffer, one_metadata = _exact_positive_cone_support(
                    gap_targets["minimum_gap"], active, parent_state.grid, filter_config,
                )
                conflict = zero_buffer & one_buffer
                if np.any(conflict):
                    raise _SupportRepairRejected("add_remove_support_conflict_rejected", {
                        "iteration": iteration,
                        "conflict": _mask_metadata(conflict),
                        "zero_buffer": zero_metadata,
                        "one_buffer": one_metadata,
                        "remove_targets": {name: _target_metadata(value) for name, value in thin_targets.items()},
                        "fill_targets": {name: _target_metadata(value) for name, value in gap_targets.items()},
                    })
                after_fill = after_remove.copy()
                after_fill[one_buffer] = 1.0
                _require_hard_mask_invariants(after_fill, active, forbidden, root)
                if np.array_equal(after_fill, after_remove):
                    raise _SupportRepairRejected("fill_fixed_point_rejected", {
                        "phase": "fill", "targets": {name: _target_metadata(value) for name, value in gap_targets.items()}, "one_buffer": one_metadata,
                        "zero_buffer": zero_metadata,
                    })
                fill_hash = _sha256_array(after_fill)
                if fill_hash in seen_state_hashes:
                    raise _SupportRepairRejected("repeated_state_or_cycle_rejected", {
                        "phase": "fill", "state_sha256": fill_hash,
                        "targets": {name: _target_metadata(value) for name, value in gap_targets.items()},
                        "one_buffer": one_metadata,
                    })
                seen_state_hashes.add(fill_hash)
                filtered, projected, report = _evaluate_candidate(
                    spec, parent, parent_state.grid, active, forbidden, fixed, root,
                    after_fill, filter_config, projection_config, staging / f"topology_work_{iteration:02d}_fill",
                )
                fill_record = _iteration_record(iteration, "fill_then_check", after_fill, filtered, projected, report)
                fill_record["support_buffer"] = {"zero": zero_metadata, "one": one_metadata}
                fill_record["targets"] = {
                    "minimum_solid_width": _target_metadata(thin_targets["minimum_solid_width"]),
                    "minimum_gap": _target_metadata(gap_targets["minimum_gap"]),
                }
                fill_record["delta_from_previous"] = _raw_delta(after_remove, after_fill)
                records.append(fill_record)
                if report["status"] == "success":
                    success = (after_fill, filtered, projected, report)
                    stop_reason = "topology_success_after_fill"
                    break
                candidate = after_fill
            except _SupportRepairRejected as exc:
                stop_reason = exc.reason
                failure_details = exc.details
                break
            except (MemoryError, OSError) as exc:
                stop_reason = "support_buffer_resource_failure_rejected"
                failure_details = {"error_type": type(exc).__name__, "message": str(exc)}
                break
        else:
            stop_reason = "maximum_iterations_rejected"
        if success is None:
            _write_failure_report(destination, parent, parent_report_path, records, stop_reason, config, failure_details)
            raise ValueError(f"feasibility initializer did not produce a topology-success state: {stop_reason}")
        _publish_success(
            staging, destination, parent, parent_state, parent_report_path, parent_report,
            active, forbidden, fixed, root, source_raw, arrays["rho_projected"], success, records, stop_reason, config,
        )
    except BaseException as exc:
        # Once the verified parent has been accepted, every failed derived
        # attempt gets a sidecar.  In particular a tampered raw state or a
        # resource error must not leave a plausible partial bundle behind.
        failure_path = localized_feasible_initializer_failure_report_path(destination)
        if not failure_path.exists():
            exception_reason = (
                "support_buffer_resource_failure_rejected"
                if isinstance(exc, (MemoryError, OSError))
                else "initializer_exception_rejected"
            )
            _write_failure_report(
                destination, parent, parent_report_path, records,
                stop_reason if stop_reason != "unknown" else exception_reason, config,
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedFeasibleDerivedState(
        destination,
        destination / "localized_design_state_manifest.json",
        destination / "topology" / "localized_reference_topology.json",
    )


def repair_raw_density_threshold_opening_legacy(
    rho_raw: np.ndarray,
    active_design_mask: np.ndarray,
    root_mask: np.ndarray,
    grid: LocalizedDesignGrid,
    problem: ProblemSpec,
) -> np.ndarray:
    """Deprecated raw-threshold operator retained only for historical replay.

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


def _evaluate_candidate(
    spec: ProblemSpec, parent: LocalizedReferenceStateBundle, grid: LocalizedDesignGrid,
    active: np.ndarray, forbidden: np.ndarray, fixed: np.ndarray, root: np.ndarray,
    raw: np.ndarray, filter_config: LocalizedConeFilterConfig, projection_config: Any, work: Path,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Materialise exactly the production forward chain before topology."""

    filtered = apply_localized_cone_filter(raw, active, grid, config=filter_config)
    projected = apply_localized_heaviside_projection(filtered, active, config=projection_config)
    report = _full_topology_report(spec, parent, grid, active, forbidden, fixed, root, projected, work)
    return filtered, projected, report


def _iteration_record(
    iteration: int, phase: str, raw: np.ndarray, filtered: np.ndarray, projected: np.ndarray,
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "phase": phase,
        "rho_raw_sha256": _sha256_array(raw),
        "rho_filtered_sha256": _sha256_array(filtered),
        "rho_projected_sha256": _sha256_array(projected),
        "topology_report_sha256": _sha256_json(report),
        "topology_status": report["status"],
        "topology_reasons": report["reasons"],
        # The whole payload is retained in failure diagnostics, rather than
        # summarising away a failure that drove a material raw-state change.
        "topology_checks": report["checks"],
        "violation_summary": _violation_summary(report),
    }


def _violation_summary(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise _SupportRepairRejected("checker_payload_invalid_rejected", {"report": report})
    result: dict[str, dict[str, Any]] = {}
    for name in ("minimum_solid_width", "minimum_void_width", "minimum_gap"):
        item = checks.get(name)
        if item is None:
            result[name] = {"enabled": False, "violation_count": 0, "first_violation_index": None}
            continue
        if not isinstance(item, dict) or not isinstance(item.get("violation_count"), int):
            raise _SupportRepairRejected("checker_payload_invalid_rejected", {"check": name, "value": item})
        result[name] = {
            "enabled": True,
            "violation_count": int(item["violation_count"]),
            "first_violation_index": item.get("first_violation_index"),
        }
    return result


def _checker_targets(
    projected: np.ndarray, active: np.ndarray, root: np.ndarray, grid: LocalizedDesignGrid,
    spec: ProblemSpec, report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Recreate only the two checker target masks and bind them to its report.

    The public checker deliberately records count/first-index evidence, not
    huge target masks.  This private reconstruction uses the same strict EDT
    opening and external-void labelling and rejects any mismatch, so support
    writes cannot be based on a merely similar raw morphology operation.
    """

    n = grid.cell_count
    values = _state_vector(projected, n, "rho_projected")
    active = _mask_vector(active, n, "active_design_mask")
    root = _mask_vector(root, n, "root_mask")
    shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    active3 = active.reshape(shape); root3 = root.reshape(shape)
    solid = (active & (values >= 0.5) | root).reshape(shape)
    domain = active3 | root3
    void = domain & ~solid
    policy = spec.topology_policy
    targets = {
        "minimum_solid_width": _rolling_violation_mask(
            solid, _half_policy_width(policy.minimum_solid_width_m), grid,
        ),
        "minimum_gap": np.zeros(shape, dtype=np.bool_),
    }
    if policy.minimum_gap_m is not None:
        labels, count = ndimage.label(void, structure=_STRUCTURE_6)
        external = _external_void_labels(labels, domain, int(count))
        targets["minimum_gap"] = _rolling_violation_mask(
            void & external[labels], _half_policy_width(policy.minimum_gap_m), grid,
        )
    result: dict[str, dict[str, Any]] = {}
    summary = _violation_summary(report)
    for name, mask3 in targets.items():
        vector = np.ascontiguousarray(mask3.ravel(order="C"), dtype=np.bool_)
        metadata = _mask_metadata(vector)
        expected = summary[name]
        if metadata["count"] != expected["violation_count"] or metadata["first_index"] != expected["first_violation_index"]:
            raise _SupportRepairRejected("checker_target_mismatch_rejected", {
                "check": name, "checker": expected, "reconstructed": metadata,
            })
        result[name] = metadata | {"mask": vector}
    return result


def _half_policy_width(value: float | None) -> float | None:
    return None if value is None else float(value) / 2.0


def _rolling_violation_mask(candidate: np.ndarray, radius_m: float | None, grid: LocalizedDesignGrid) -> np.ndarray:
    if radius_m is None:
        return np.zeros_like(candidate, dtype=np.bool_)
    if radius_m <= 0.0:
        return np.zeros_like(candidate, dtype=np.bool_)
    sampling = tuple(reversed(grid.spacing))
    core = candidate & (ndimage.distance_transform_edt(candidate, sampling=sampling) > radius_m)
    opened = candidate & (ndimage.distance_transform_edt(~core, sampling=sampling) <= radius_m)
    return candidate & ~opened


def _exact_positive_cone_support(
    target_metadata: dict[str, Any], active: np.ndarray, grid: LocalizedDesignGrid,
    config: LocalizedConeFilterConfig,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return every active raw source with strictly positive filter support.

    ``_cone_offsets`` is the filter's own enumerator, including its strict
    ``weight > 0`` edge convention.  The support map is therefore exact for
    the active-source-normalised filter rather than a radius approximation.
    """

    target = target_metadata.get("mask")
    n = grid.cell_count
    if not isinstance(target, np.ndarray) or target.dtype != np.bool_ or target.shape != (n,):
        raise _SupportRepairRejected("checker_target_invalid_rejected", {"target": target_metadata})
    active = _mask_vector(active, n, "active_design_mask")
    spatial_shape = (grid.cell_shape[2], grid.cell_shape[1], grid.cell_shape[0])
    target3 = target.reshape(spatial_shape)
    support3 = np.zeros(spatial_shape, dtype=np.bool_)
    kernel = []
    for dz, dy, dx, weight in _cone_offsets(grid.spacing, config.radius_m):
        # ``_overlap_slices`` takes the public grid shape (x, y, z), while
        # its returned slices address the internal (z, y, x) storage.
        target_slices, source_slices = _overlap_slices(
            grid.cell_shape, 0, grid.cell_shape[2], dz, dy, dx,
        )
        support3[source_slices] |= target3[target_slices]
        kernel.append({"dz": dz, "dy": dy, "dx": dx, "weight": float(weight)})
    support = np.ascontiguousarray(support3.ravel(order="C") & active, dtype=np.bool_)
    kernel_payload = {
        "filter_radius_m": float(config.radius_m), "grid_spacing_m": list(grid.spacing),
        "positive_weight_offsets": kernel,
    }
    return support, {
        "kind": "exact_positive_active_cone_support",
        "target": {key: value for key, value in target_metadata.items() if key != "mask"},
        "buffer": _mask_metadata(support),
        "kernel": kernel_payload,
        "kernel_sha256": _sha256_json(kernel_payload),
    }


def _mask_metadata(values: np.ndarray) -> dict[str, Any]:
    vector = np.asarray(values, dtype=np.bool_).reshape(-1)
    nonzero = np.flatnonzero(vector)
    return {
        "sha256": _sha256_array(vector), "count": int(nonzero.size),
        "first_index": int(nonzero[0]) if nonzero.size else None,
    }


def _target_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Drop the in-memory target mask before writing any provenance JSON."""

    return {key: item for key, item in value.items() if key != "mask"}


def _raw_delta(previous: np.ndarray, current: np.ndarray) -> dict[str, Any]:
    changed = previous != current
    added = (previous < current) & changed
    removed = (previous > current) & changed
    return {
        "previous_raw_sha256": _sha256_array(previous), "current_raw_sha256": _sha256_array(current),
        "changed": _mask_metadata(changed), "added": _mask_metadata(added), "removed": _mask_metadata(removed),
        "l1": float(np.sum(np.abs(current - previous))),
    }


def _require_hard_mask_invariants(raw: np.ndarray, active: np.ndarray, forbidden: np.ndarray, root: np.ndarray) -> None:
    _state_vector(raw, raw.size, "rho_raw")
    active = _mask_vector(active, raw.size, "active_design_mask")
    forbidden = _mask_vector(forbidden, raw.size, "forbidden_mask")
    root = _mask_vector(root, raw.size, "root_mask")
    if np.any(raw[~active] != 0.0):
        raise ValueError("rho_raw must remain exactly zero outside active_design_mask")
    if np.any(raw[forbidden] != 0.0):
        raise ValueError("rho_raw must remain exactly zero in forbidden_mask")
    if np.any(root & active):
        raise ValueError("root_mask must not overlap active_design_mask")


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
                          records: list[dict[str, Any]], stop_reason: str, config: FeasibilityInitializerConfig,
                          failure_details: dict[str, Any] | None = None) -> None:
    _write_json(localized_feasible_initializer_failure_report_path(destination), {
        "schema_version": 1, "kind": LOCALIZED_FEASIBLE_DERIVED_STATE_FAILURE_KIND,
        "status": "rejected_no_feasible_bundle_published", "requested_output_directory": str(destination),
        "parent_direct_stl_bundle_path": str(parent.path), "parent_direct_state_manifest_sha256": parent.state_manifest_sha256,
        "parent_rejected_topology_report_path": str(parent_report_path), "parent_rejected_topology_report_sha256": _sha256_file(parent_report_path),
        "repair": {
            "controls": config.to_dict(), "iterations": records, "stop_reason": stop_reason,
            "failure_details": failure_details,
        },
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
    "repair_raw_density_threshold_opening_legacy",
]
