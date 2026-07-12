from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from .fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _assert_same_grid,
    _grid_from_manifest,
    _read_cell_vti,
    _write_cell_vti,
)


FIXED_GRID_CONNECTIVITY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FixedGridConnectivityArtifacts:
    output_dir: Path
    topology_state_json: Path
    density_vti: Path
    connectivity_state_vti: Path
    connectivity_summary_json: Path
    summary: dict[str, object]

    @property
    def ok(self) -> bool:
        return bool(self.summary.get("ok"))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "output_dir",
            "topology_state_json",
            "density_vti",
            "connectivity_state_vti",
            "connectivity_summary_json",
        ):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class FixedGridConnectivityDerivativeArtifacts:
    output_dir: Path
    topology_state_json: Path
    density_vti: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    derivative_summary_json: Path
    summary: dict[str, object]

    @property
    def ok(self) -> bool:
        return bool(self.summary.get("ok"))

    @property
    def optimizer_ready(self) -> bool:
        return bool(self.summary.get("optimizer_ready"))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "output_dir",
            "topology_state_json",
            "density_vti",
            "sensitivity_vti",
            "sensitivity_summary_json",
            "derivative_summary_json",
        ):
            data[key] = str(data[key])
        return data


def build_fixed_grid_connectivity_state(
    topology_state_json: Path,
    *,
    output_dir: Path | None = None,
    density_array: str = "rho",
    solid_threshold: float = 0.5,
    min_connection_width_m: float = 0.01,
    require_eroded_connectivity: bool = True,
    conductivity_floor: float = 1.0e-6,
    leakage: float = 1.0e-6,
    root_penalty: float = 1.0e6,
) -> FixedGridConnectivityArtifacts:
    if not (0.0 <= solid_threshold <= 1.0):
        raise ValueError("solid_threshold must be within [0, 1]")
    if min_connection_width_m < 0:
        raise ValueError("min_connection_width_m must be non-negative")
    if conductivity_floor <= 0:
        raise ValueError("conductivity_floor must be greater than zero")
    if leakage <= 0:
        raise ValueError("leakage must be greater than zero")
    if root_penalty <= 0:
        raise ValueError("root_penalty must be greater than zero")

    topology_state_json = topology_state_json.resolve()
    state = json.loads(topology_state_json.read_text(encoding="utf-8"))
    if state.get("schema_version") != FIXED_GRID_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported fixed-grid schema_version: {state.get('schema_version')!r}"
        )
    if state.get("kind") != "fixed_grid_topology_state":
        raise ValueError(f"Unsupported topology state kind: {state.get('kind')!r}")

    density_path = _resolve_manifest_path(topology_state_json.parent, state.get("density_vti"))
    grid, arrays = _read_cell_vti(density_path, expected_kind="fixed_grid_density")
    manifest_grid = _grid_from_manifest(dict(state.get("grid") or {}))
    _assert_same_grid(grid, manifest_grid, "density.vti", "topology_state.json")
    missing = sorted(
        name
        for name in (
            density_array,
            "root_mask",
            "active_design_mask",
            "fixed_solid_mask",
        )
        if name not in arrays
    )
    if missing:
        raise ValueError(f"density.vti is missing arrays: {', '.join(missing)}")

    output_dir = (output_dir or topology_state_json.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    density = np.asarray(arrays[density_array], dtype=np.float64)
    density = np.clip(density, 0.0, 1.0)
    fixed_solid = np.asarray(arrays["fixed_solid_mask"], dtype=np.uint8) > 0
    root_mask = np.asarray(arrays["root_mask"], dtype=np.uint8) > 0
    active_design = np.asarray(arrays["active_design_mask"], dtype=np.uint8) > 0
    material = np.maximum(density, fixed_solid.astype(np.float64))
    root_float = root_mask.astype(np.float64)

    nominal = _evaluate_connectivity_field(
        grid,
        material,
        root_mask=root_mask,
        solid_threshold=solid_threshold,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )

    erosion_radius_m = 0.5 * min_connection_width_m
    eroded_material = _erode_material(
        material,
        grid,
        threshold=solid_threshold,
        erosion_radius_m=erosion_radius_m,
    )
    eroded = _evaluate_connectivity_field(
        grid,
        eroded_material,
        root_mask=root_mask,
        solid_threshold=solid_threshold,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )

    connectivity_arrays = {
        "connectivity_nominal_potential": nominal.potential.astype(np.float32),
        "connectivity_eroded_potential": eroded.potential.astype(np.float32),
        "connectivity_nominal_violation": nominal.violation.astype(np.float32),
        "connectivity_eroded_violation": eroded.violation.astype(np.float32),
        "root_mask": root_float.astype(np.uint8),
        "active_design_mask": active_design.astype(np.uint8),
    }
    connectivity_state_vti = output_dir / "connectivity_state.vti"
    _write_cell_vti(
        grid,
        connectivity_arrays,
        connectivity_state_vti,
        kind="fixed_grid_connectivity",
    )

    nonroot_material_count = int(np.count_nonzero((material >= solid_threshold) & ~root_mask))
    eroded_nonroot_material_count = int(
        np.count_nonzero((eroded_material >= solid_threshold) & ~root_mask)
    )
    eroded_all_nonroot_material_removed = (
        require_eroded_connectivity
        and nonroot_material_count > 0
        and eroded_nonroot_material_count == 0
    )
    root_count = int(np.count_nonzero(root_mask))
    material_count = int(np.count_nonzero(material >= solid_threshold))
    if material_count == 0:
        status = "empty_design"
        ok = True
    elif root_count == 0:
        status = "missing_root"
        ok = False
    else:
        nominal_ok = nominal.unrooted_components == 0
        eroded_ok = (
            not require_eroded_connectivity
            or (
                eroded.unrooted_components == 0
                and not eroded_all_nonroot_material_removed
            )
        )
        ok = bool(nominal_ok and eroded_ok)
        status = "pass" if ok else "fail"

    created_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": FIXED_GRID_CONNECTIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_connectivity_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T4",
        "created_at_utc": created_at,
        "status": status,
        "ok": ok,
        "topology_state_json": str(topology_state_json),
        "density_vti": str(density_path),
        "connectivity_state_vti": str(connectivity_state_vti),
        "design_variable": "rho",
        "density_array": density_array,
        "solid_threshold": solid_threshold,
        "min_connection_width_m": min_connection_width_m,
        "erosion_radius_m": erosion_radius_m,
        "require_eroded_connectivity": require_eroded_connectivity,
        "method": {
            "name": "root_connected_virtual_diffusion",
            "conductivity_floor": conductivity_floor,
            "leakage": leakage,
            "root_penalty": root_penalty,
            "component_connectivity": 1,
            "derivative_status": "not_evaluated_t4_state_only",
        },
        "counts": {
            "root_cells": root_count,
            "material_cells": material_count,
            "nonroot_material_cells": nonroot_material_count,
            "eroded_material_cells": int(np.count_nonzero(eroded_material >= solid_threshold)),
            "eroded_nonroot_material_cells": eroded_nonroot_material_count,
            "active_design_cells": int(np.count_nonzero(active_design)),
        },
        "nominal": nominal.to_summary(),
        "eroded": eroded.to_summary(),
        "failure_reasons": _failure_reasons(
            root_count=root_count,
            material_count=material_count,
            nominal=nominal,
            eroded=eroded,
            require_eroded_connectivity=require_eroded_connectivity,
            eroded_all_nonroot_material_removed=eroded_all_nonroot_material_removed,
        ),
        "array_metadata": {
            "connectivity_nominal_potential": {
                "units": "1",
                "location": "cell",
                "source": "T4 virtual-diffusion solve on nominal density",
                "sign_convention": "higher means weaker root heat sink connection",
            },
            "connectivity_eroded_potential": {
                "units": "1",
                "location": "cell",
                "source": "T4 virtual-diffusion solve on eroded density",
                "sign_convention": "higher means weaker root heat sink connection after erosion",
            },
            "connectivity_nominal_violation": {
                "units": "1",
                "location": "cell",
                "source": "nominal material times virtual-diffusion potential",
                "sign_convention": "positive marks nominal connectivity violation pressure",
            },
            "connectivity_eroded_violation": {
                "units": "1",
                "location": "cell",
                "source": "eroded material times virtual-diffusion potential",
                "sign_convention": "positive marks eroded connectivity violation pressure",
            },
            "root_mask": {
                "units": "1",
                "location": "cell",
                "source": "fixed-grid density contract root_mask",
            },
            "active_design_mask": {
                "units": "1",
                "location": "cell",
                "source": "fixed-grid density contract active_design_mask",
            },
        },
    }
    connectivity_summary_json = output_dir / "fixed_grid_connectivity_summary.json"
    connectivity_summary_json.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return FixedGridConnectivityArtifacts(
        output_dir=output_dir,
        topology_state_json=topology_state_json,
        density_vti=density_path,
        connectivity_state_vti=connectivity_state_vti,
        connectivity_summary_json=connectivity_summary_json,
        summary=summary,
    )


def build_fixed_grid_connectivity_derivatives(
    topology_state_json: Path,
    *,
    output_dir: Path | None = None,
    density_array: str = "rho",
    base_sensitivity_vti: Path | None = None,
    epsilon: float = 1.0e-4,
    max_cells: int | None = None,
    sample_seed: int = 1,
    solid_threshold: float = 0.5,
    min_connection_width_m: float = 0.01,
    require_eroded_connectivity: bool = True,
    conductivity_floor: float = 1.0e-6,
    leakage: float = 1.0e-6,
    root_penalty: float = 1.0e6,
) -> FixedGridConnectivityDerivativeArtifacts:
    """Write finite-difference reference T4 connectivity derivatives.

    This is intentionally a reference implementation. A full active-cell run is
    optimizer-usable for small fixed grids, while sampled runs are for checking
    signs and scales before replacing this with an adjoint derivative.
    """
    if epsilon <= 0.0:
        raise ValueError("epsilon must be greater than zero")
    if max_cells is not None and max_cells <= 0:
        raise ValueError("max_cells must be positive when provided")
    if not (0.0 <= solid_threshold <= 1.0):
        raise ValueError("solid_threshold must be within [0, 1]")
    if min_connection_width_m < 0:
        raise ValueError("min_connection_width_m must be non-negative")
    if conductivity_floor <= 0:
        raise ValueError("conductivity_floor must be greater than zero")
    if leakage <= 0:
        raise ValueError("leakage must be greater than zero")
    if root_penalty <= 0:
        raise ValueError("root_penalty must be greater than zero")

    inputs = _load_connectivity_inputs(
        topology_state_json,
        density_array=density_array,
    )
    output_dir = (output_dir or inputs.topology_state_json.parent).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    base_pair = _evaluate_connectivity_pair(
        inputs.grid,
        inputs.density,
        fixed_solid=inputs.fixed_solid,
        root_mask=inputs.root_mask,
        solid_threshold=solid_threshold,
        min_connection_width_m=min_connection_width_m,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )
    base_objectives = _connectivity_objectives(base_pair)

    candidate_indices = _select_derivative_cells(
        density=inputs.density,
        active_design=inputs.active_design,
        root_mask=inputs.root_mask,
        fixed_solid=inputs.fixed_solid,
        max_cells=max_cells,
        sample_seed=sample_seed,
    )
    all_candidate_indices = _select_derivative_cells(
        density=inputs.density,
        active_design=inputs.active_design,
        root_mask=inputs.root_mask,
        fixed_solid=inputs.fixed_solid,
        max_cells=None,
        sample_seed=sample_seed,
    )

    nominal_derivative = np.zeros(inputs.grid.cell_count, dtype=np.float64)
    eroded_derivative = np.zeros(inputs.grid.cell_count, dtype=np.float64)
    sample_mask = np.zeros(inputs.grid.cell_count, dtype=np.uint8)
    sample_records: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for cell_index in candidate_indices:
        plus_density = inputs.density.copy()
        minus_density = inputs.density.copy()
        plus_density[cell_index] = min(1.0, plus_density[cell_index] + epsilon)
        minus_density[cell_index] = max(0.0, minus_density[cell_index] - epsilon)
        plus_density = _apply_connectivity_hard_masks(plus_density, inputs.arrays)
        minus_density = _apply_connectivity_hard_masks(minus_density, inputs.arrays)
        effective_delta = float(plus_density[cell_index] - minus_density[cell_index])
        if abs(effective_delta) <= 1.0e-30:
            skipped.append(
                {
                    "cell_index": int(cell_index),
                    "reason": "zero_effective_density_delta",
                    "rho": float(inputs.density[cell_index]),
                }
            )
            continue

        plus_pair = _evaluate_connectivity_pair(
            inputs.grid,
            plus_density,
            fixed_solid=inputs.fixed_solid,
            root_mask=inputs.root_mask,
            solid_threshold=solid_threshold,
            min_connection_width_m=min_connection_width_m,
            conductivity_floor=conductivity_floor,
            leakage=leakage,
            root_penalty=root_penalty,
        )
        minus_pair = _evaluate_connectivity_pair(
            inputs.grid,
            minus_density,
            fixed_solid=inputs.fixed_solid,
            root_mask=inputs.root_mask,
            solid_threshold=solid_threshold,
            min_connection_width_m=min_connection_width_m,
            conductivity_floor=conductivity_floor,
            leakage=leakage,
            root_penalty=root_penalty,
        )
        plus_objectives = _connectivity_objectives(plus_pair)
        minus_objectives = _connectivity_objectives(minus_pair)
        nominal_value = (
            plus_objectives["connectivity_nominal_violation_l1"]
            - minus_objectives["connectivity_nominal_violation_l1"]
        ) / effective_delta
        eroded_value = (
            plus_objectives["connectivity_eroded_violation_l1"]
            - minus_objectives["connectivity_eroded_violation_l1"]
        ) / effective_delta
        nominal_derivative[cell_index] = nominal_value
        eroded_derivative[cell_index] = eroded_value
        sample_mask[cell_index] = 1
        if len(sample_records) < 100:
            sample_records.append(
                {
                    "cell_index": int(cell_index),
                    "rho": float(inputs.density[cell_index]),
                    "rho_plus": float(plus_density[cell_index]),
                    "rho_minus": float(minus_density[cell_index]),
                    "effective_delta": effective_delta,
                    "d_connectivity_nominal_d_rho": float(nominal_value),
                    "d_connectivity_eroded_d_rho": float(eroded_value),
                }
            )

    active = inputs.active_design.astype(bool)
    nominal_derivative[~active] = 0.0
    eroded_derivative[~active] = 0.0
    sensitivity_arrays = _base_sensitivity_arrays(
        inputs,
        base_sensitivity_vti=base_sensitivity_vti,
    )
    sensitivity_arrays["d_connectivity_nominal_d_rho"] = nominal_derivative.astype(
        np.float32
    )
    sensitivity_arrays["d_connectivity_eroded_d_rho"] = eroded_derivative.astype(
        np.float32
    )
    sensitivity_arrays["connectivity_derivative_sample_mask"] = sample_mask
    sensitivity_arrays["active_design_mask"] = inputs.active_design.astype(np.uint8)

    sensitivity_vti = output_dir / "fixed_grid_sensitivity.vti"
    _write_cell_vti(
        inputs.grid,
        sensitivity_arrays,
        sensitivity_vti,
        kind="fixed_grid_sensitivity",
    )

    evaluated_count = int(np.count_nonzero(sample_mask))
    candidate_count = int(all_candidate_indices.size)
    selected_count = int(candidate_indices.size)
    full_derivative = bool(evaluated_count == candidate_count and not skipped)
    status = "generated" if evaluated_count > 0 else "no_derivative_cells"
    derivative_status = (
        "finite_difference_reference_full"
        if full_derivative
        else "finite_difference_reference_sampled"
    )
    if evaluated_count == 0:
        derivative_status = "not_evaluated_no_active_cells"

    sensitivity_summary_json = output_dir / "fixed_grid_sensitivity_summary.json"
    derivative_summary_json = output_dir / "fixed_grid_connectivity_derivative_summary.json"
    summary = {
        "schema_version": FIXED_GRID_CONNECTIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_summary",
        "derivative_summary_kind": "fixed_grid_connectivity_derivative_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T4",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "ok": evaluated_count > 0,
        "optimizer_ready": full_derivative,
        "topology_state_json": str(inputs.topology_state_json),
        "density_vti": str(inputs.density_path),
        "sensitivity_vti": str(sensitivity_vti),
        "sensitivity_summary_json": str(sensitivity_summary_json),
        "derivative_summary_json": str(derivative_summary_json),
        "base_sensitivity_vti": (
            str(base_sensitivity_vti.resolve()) if base_sensitivity_vti else None
        ),
        "design_variable": "rho",
        "density_array": density_array,
        "solid_threshold": solid_threshold,
        "min_connection_width_m": min_connection_width_m,
        "erosion_radius_m": base_pair.erosion_radius_m,
        "require_eroded_connectivity": require_eroded_connectivity,
        "connectivity_derivative_status": derivative_status,
        "connectivity_derivative_note": (
            "T4 finite-difference reference derivatives populate the "
            "connectivity derivative arrays. Full active-cell runs are "
            "optimizer-ready for this reference scalarization; sampled runs "
            "are diagnostic only."
        ),
        "method": {
            "name": "root_connected_virtual_diffusion_finite_difference",
            "derivative_status": derivative_status,
            "epsilon": epsilon,
            "sample_seed": sample_seed,
            "max_cells": max_cells,
            "conductivity_floor": conductivity_floor,
            "leakage": leakage,
            "root_penalty": root_penalty,
            "scalar_objectives": [
                "connectivity_nominal_violation_l1",
                "connectivity_eroded_violation_l1",
            ],
            "note": (
                "Finite-difference reference derivatives are correct for the "
                "current scalarized virtual-diffusion constraints, but sampled "
                "runs are not optimizer-ready."
            ),
        },
        "counts": {
            "candidate_cells": candidate_count,
            "selected_cells": selected_count,
            "evaluated_cells": evaluated_count,
            "skipped_cells": len(skipped),
            "active_design_cells": int(np.count_nonzero(inputs.active_design)),
            "root_cells": int(np.count_nonzero(inputs.root_mask)),
            "fixed_solid_cells": int(np.count_nonzero(inputs.fixed_solid)),
        },
        "base_objectives": base_objectives,
        "base_connectivity": {
            "nominal": base_pair.nominal.to_summary(),
            "eroded": base_pair.eroded.to_summary(),
        },
        "statistics": {
            name: _array_statistics(values, inputs.active_design)
            for name, values in sensitivity_arrays.items()
        },
        "array_metadata": _connectivity_derivative_array_metadata(
            base_sensitivity_vti=base_sensitivity_vti,
            derivative_status=derivative_status,
        ),
        "sample_records_truncated": len(sample_records) < evaluated_count,
        "sample_records": sample_records,
        "skipped_records": skipped[:100],
        "skipped_records_truncated": len(skipped) > 100,
    }

    summary_text = json.dumps(summary, indent=2)
    sensitivity_summary_json.write_text(
        summary_text,
        encoding="utf-8",
    )
    derivative_summary_json.write_text(
        summary_text,
        encoding="utf-8",
    )
    return FixedGridConnectivityDerivativeArtifacts(
        output_dir=output_dir,
        topology_state_json=inputs.topology_state_json,
        density_vti=inputs.density_path,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        derivative_summary_json=derivative_summary_json,
        summary=summary,
    )


def evaluate_fixed_grid_connectivity_objectives(
    topology_state_json: Path,
    *,
    density: np.ndarray | None = None,
    density_array: str = "rho",
    solid_threshold: float = 0.5,
    min_connection_width_m: float = 0.01,
    conductivity_floor: float = 1.0e-6,
    leakage: float = 1.0e-6,
    root_penalty: float = 1.0e6,
) -> dict[str, float]:
    inputs = _load_connectivity_inputs(
        topology_state_json,
        density_array=density_array,
    )
    values = inputs.density if density is None else np.asarray(density, dtype=np.float64)
    if values.shape != inputs.density.shape:
        raise ValueError(
            f"density override has shape {values.shape}; expected {inputs.density.shape}"
        )
    values = _apply_connectivity_hard_masks(values, inputs.arrays)
    pair = _evaluate_connectivity_pair(
        inputs.grid,
        values,
        fixed_solid=inputs.fixed_solid,
        root_mask=inputs.root_mask,
        solid_threshold=solid_threshold,
        min_connection_width_m=min_connection_width_m,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )
    return _connectivity_objectives(pair)


@dataclass(frozen=True)
class _ConnectivityInputs:
    topology_state_json: Path
    state: dict[str, object]
    density_path: Path
    grid: CartesianCellGrid
    arrays: dict[str, np.ndarray]
    density: np.ndarray
    fixed_solid: np.ndarray
    root_mask: np.ndarray
    active_design: np.ndarray


@dataclass(frozen=True)
class _ConnectivityEvaluation:
    potential: np.ndarray
    violation: np.ndarray
    solid_mask: np.ndarray
    rooted_mask: np.ndarray
    unrooted_mask: np.ndarray
    components: int
    rooted_components: int
    unrooted_components: int

    def to_summary(self) -> dict[str, object]:
        solid_potential = self.potential[self.solid_mask]
        return {
            "components": self.components,
            "rooted_components": self.rooted_components,
            "unrooted_components": self.unrooted_components,
            "solid_cells": int(np.count_nonzero(self.solid_mask)),
            "rooted_cells": int(np.count_nonzero(self.rooted_mask)),
            "unrooted_cells": int(np.count_nonzero(self.unrooted_mask)),
            "potential_min": float(np.min(solid_potential)) if solid_potential.size else 0.0,
            "potential_max": float(np.max(solid_potential)) if solid_potential.size else 0.0,
            "potential_mean": float(np.mean(solid_potential)) if solid_potential.size else 0.0,
            "violation_linf": float(np.max(np.abs(self.violation))) if self.violation.size else 0.0,
            "violation_l1": float(np.sum(np.abs(self.violation))),
        }


@dataclass(frozen=True)
class _ConnectivityPair:
    material: np.ndarray
    nominal: _ConnectivityEvaluation
    eroded_material: np.ndarray
    eroded: _ConnectivityEvaluation
    erosion_radius_m: float


def _load_connectivity_inputs(
    topology_state_json: Path,
    *,
    density_array: str,
) -> _ConnectivityInputs:
    topology_state_json = topology_state_json.resolve()
    state = json.loads(topology_state_json.read_text(encoding="utf-8"))
    if state.get("schema_version") != FIXED_GRID_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported fixed-grid schema_version: {state.get('schema_version')!r}"
        )
    if state.get("kind") != "fixed_grid_topology_state":
        raise ValueError(f"Unsupported topology state kind: {state.get('kind')!r}")

    density_path = _resolve_manifest_path(topology_state_json.parent, state.get("density_vti"))
    grid, arrays = _read_cell_vti(density_path, expected_kind="fixed_grid_density")
    manifest_grid = _grid_from_manifest(dict(state.get("grid") or {}))
    _assert_same_grid(grid, manifest_grid, "density.vti", "topology_state.json")
    missing = sorted(
        name
        for name in (
            density_array,
            "root_mask",
            "active_design_mask",
            "fixed_solid_mask",
        )
        if name not in arrays
    )
    if missing:
        raise ValueError(f"density.vti is missing arrays: {', '.join(missing)}")

    density = _apply_connectivity_hard_masks(
        np.asarray(arrays[density_array], dtype=np.float64),
        arrays,
    )
    fixed_solid = np.asarray(arrays["fixed_solid_mask"], dtype=np.uint8) > 0
    root_mask = np.asarray(arrays["root_mask"], dtype=np.uint8) > 0
    active_design = np.asarray(arrays["active_design_mask"], dtype=np.uint8)
    return _ConnectivityInputs(
        topology_state_json=topology_state_json,
        state=state,
        density_path=density_path,
        grid=grid,
        arrays=arrays,
        density=density,
        fixed_solid=fixed_solid,
        root_mask=root_mask,
        active_design=active_design,
    )


def _evaluate_connectivity_pair(
    grid: CartesianCellGrid,
    density: np.ndarray,
    *,
    fixed_solid: np.ndarray,
    root_mask: np.ndarray,
    solid_threshold: float,
    min_connection_width_m: float,
    conductivity_floor: float,
    leakage: float,
    root_penalty: float,
) -> _ConnectivityPair:
    material = np.maximum(
        np.asarray(density, dtype=np.float64),
        np.asarray(fixed_solid, dtype=bool).astype(np.float64),
    )
    nominal = _evaluate_connectivity_field(
        grid,
        material,
        root_mask=root_mask,
        solid_threshold=solid_threshold,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )

    erosion_radius_m = 0.5 * min_connection_width_m
    eroded_material = _erode_material(
        material,
        grid,
        threshold=solid_threshold,
        erosion_radius_m=erosion_radius_m,
    )
    eroded = _evaluate_connectivity_field(
        grid,
        eroded_material,
        root_mask=root_mask,
        solid_threshold=solid_threshold,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )
    return _ConnectivityPair(
        material=material,
        nominal=nominal,
        eroded_material=eroded_material,
        eroded=eroded,
        erosion_radius_m=erosion_radius_m,
    )


def _connectivity_objectives(pair: _ConnectivityPair) -> dict[str, float]:
    return {
        "connectivity_nominal_violation_l1": float(np.sum(np.abs(pair.nominal.violation))),
        "connectivity_eroded_violation_l1": float(np.sum(np.abs(pair.eroded.violation))),
    }


def _select_derivative_cells(
    *,
    density: np.ndarray,
    active_design: np.ndarray,
    root_mask: np.ndarray,
    fixed_solid: np.ndarray,
    max_cells: int | None,
    sample_seed: int,
) -> np.ndarray:
    active = np.asarray(active_design, dtype=np.uint8) > 0
    finite = np.isfinite(np.asarray(density, dtype=np.float64))
    candidates = np.flatnonzero(active & finite & ~root_mask & ~fixed_solid)
    if max_cells is None or candidates.size <= max_cells:
        return candidates.astype(np.int64)
    rng = np.random.default_rng(sample_seed)
    return np.sort(rng.choice(candidates, size=max_cells, replace=False)).astype(
        np.int64
    )


def _apply_connectivity_hard_masks(
    density: np.ndarray,
    arrays: dict[str, np.ndarray],
) -> np.ndarray:
    values = np.clip(np.asarray(density, dtype=np.float64).copy(), 0.0, 1.0)
    fixed_solid = np.asarray(
        arrays.get("fixed_solid_mask", np.zeros(values.size, dtype=np.uint8)),
        dtype=np.uint8,
    ) > 0
    allowed = np.asarray(
        arrays.get("allowed_mask", np.ones(values.size, dtype=np.uint8)),
        dtype=np.uint8,
    ) > 0
    forbidden = np.asarray(
        arrays.get("forbidden_mask", np.zeros(values.size, dtype=np.uint8)),
        dtype=np.uint8,
    ) > 0
    values[(~allowed) & (~fixed_solid)] = 0.0
    values[fixed_solid & (~forbidden)] = 1.0
    values[forbidden] = 0.0
    return values


def _base_sensitivity_arrays(
    inputs: _ConnectivityInputs,
    *,
    base_sensitivity_vti: Path | None,
) -> dict[str, np.ndarray]:
    required = (
        "d_downforce_d_rho",
        "d_drag_d_rho",
        "d_efficiency_constraint_d_rho",
        "d_connectivity_nominal_d_rho",
        "d_connectivity_eroded_d_rho",
        "active_design_mask",
    )
    if base_sensitivity_vti is None:
        arrays = {
            "d_downforce_d_rho": np.zeros(inputs.grid.cell_count, dtype=np.float32),
            "d_drag_d_rho": np.zeros(inputs.grid.cell_count, dtype=np.float32),
            "d_efficiency_constraint_d_rho": np.zeros(
                inputs.grid.cell_count,
                dtype=np.float32,
            ),
        }
    else:
        path = base_sensitivity_vti.resolve()
        grid, base_arrays = _read_cell_vti(path, expected_kind="fixed_grid_sensitivity")
        _assert_same_grid(grid, inputs.grid, "base sensitivity", "density.vti")
        missing = sorted(set(required) - set(base_arrays))
        if missing:
            raise ValueError(
                f"base sensitivity VTI is missing arrays: {', '.join(missing)}"
            )
        arrays = {
            "d_downforce_d_rho": np.asarray(
                base_arrays["d_downforce_d_rho"],
                dtype=np.float32,
            ).copy(),
            "d_drag_d_rho": np.asarray(
                base_arrays["d_drag_d_rho"],
                dtype=np.float32,
            ).copy(),
            "d_efficiency_constraint_d_rho": np.asarray(
                base_arrays["d_efficiency_constraint_d_rho"],
                dtype=np.float32,
            ).copy(),
        }
    active = inputs.active_design.astype(bool)
    for values in arrays.values():
        values[~active] = 0.0
    return arrays


def _connectivity_derivative_array_metadata(
    *,
    base_sensitivity_vti: Path | None,
    derivative_status: str,
) -> dict[str, dict[str, object]]:
    aero_source = (
        f"preserved from {base_sensitivity_vti.resolve()}"
        if base_sensitivity_vti
        else "zero placeholder; no aerodynamic base sensitivity provided"
    )
    return {
        "d_downforce_d_rho": {
            "units": "1",
            "location": "cell",
            "source": aero_source,
            "sign_convention": "positive increases positive -Z downforce",
        },
        "d_drag_d_rho": {
            "units": "1",
            "location": "cell",
            "source": aero_source,
            "sign_convention": "positive increases positive +X drag",
        },
        "d_efficiency_constraint_d_rho": {
            "units": "1",
            "location": "cell",
            "source": aero_source,
            "sign_convention": "positive increases efficiency constraint violation",
        },
        "d_connectivity_nominal_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "T4 virtual-diffusion finite-difference reference",
            "sign_convention": "positive increases nominal connectivity violation_l1",
            "status": derivative_status,
        },
        "d_connectivity_eroded_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "T4 virtual-diffusion finite-difference reference",
            "sign_convention": "positive increases eroded connectivity violation_l1",
            "status": derivative_status,
        },
        "active_design_mask": {
            "units": "1",
            "location": "cell",
            "source": "fixed-grid role mask",
            "sign_convention": "1 where sensitivity may update rho",
        },
        "connectivity_derivative_sample_mask": {
            "units": "1",
            "location": "cell",
            "source": "T4 finite-difference derivative cell selection",
            "sign_convention": "1 where connectivity derivatives were evaluated",
        },
    }


def _array_statistics(values: np.ndarray, active_design_mask: np.ndarray) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    active = np.asarray(active_design_mask) > 0
    active_values = array[active] if active.shape == array.shape else array
    return {
        "min": float(np.min(active_values)) if active_values.size else None,
        "max": float(np.max(active_values)) if active_values.size else None,
        "mean": float(np.mean(active_values)) if active_values.size else None,
        "l2": float(np.linalg.norm(active_values)) if active_values.size else 0.0,
        "nonzero_count": int(np.count_nonzero(active_values)),
        "active_cell_count": int(np.count_nonzero(active)),
    }


def _evaluate_connectivity_field(
    grid: CartesianCellGrid,
    material: np.ndarray,
    *,
    root_mask: np.ndarray,
    solid_threshold: float,
    conductivity_floor: float,
    leakage: float,
    root_penalty: float,
) -> _ConnectivityEvaluation:
    material = np.asarray(material, dtype=np.float64)
    solid_mask = (material >= solid_threshold) | root_mask
    potential = _solve_virtual_diffusion(
        grid,
        material=np.maximum(material, root_mask.astype(np.float64)),
        root_mask=root_mask,
        conductivity_floor=conductivity_floor,
        leakage=leakage,
        root_penalty=root_penalty,
    )
    rooted_mask, unrooted_mask, components, rooted_components, unrooted_components = (
        _component_masks(
            solid_mask.reshape(grid.cell_shape, order="F"),
            root_mask.reshape(grid.cell_shape, order="F"),
        )
    )
    visible_potential = np.where(solid_mask, potential, 0.0)
    violation = np.where(solid_mask, material * visible_potential, 0.0)
    return _ConnectivityEvaluation(
        potential=visible_potential,
        violation=violation,
        solid_mask=solid_mask,
        rooted_mask=rooted_mask,
        unrooted_mask=unrooted_mask,
        components=components,
        rooted_components=rooted_components,
        unrooted_components=unrooted_components,
    )


def _solve_virtual_diffusion(
    grid: CartesianCellGrid,
    *,
    material: np.ndarray,
    root_mask: np.ndarray,
    conductivity_floor: float,
    leakage: float,
    root_penalty: float,
) -> np.ndarray:
    shape = grid.cell_shape
    count = grid.cell_count
    material_grid = np.asarray(material, dtype=np.float64).reshape(shape, order="F")
    root_grid = np.asarray(root_mask, dtype=bool).reshape(shape, order="F")
    conductivity = conductivity_floor + np.clip(material_grid, 0.0, 1.0)
    rhs = np.clip(material_grid, 0.0, 1.0).ravel(order="F")
    rhs[root_grid.ravel(order="F")] = 0.0

    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    diag = np.full(count, leakage, dtype=np.float64)

    for k in range(shape[2]):
        for j in range(shape[1]):
            for i in range(shape[0]):
                index = np.ravel_multi_index((i, j, k), shape, order="F")
                for axis, spacing in enumerate(grid.spacing):
                    for step in (-1, 1):
                        neighbor = [i, j, k]
                        neighbor[axis] += step
                        if not (
                            0 <= neighbor[0] < shape[0]
                            and 0 <= neighbor[1] < shape[1]
                            and 0 <= neighbor[2] < shape[2]
                        ):
                            continue
                        neighbor_index = np.ravel_multi_index(
                            tuple(neighbor),
                            shape,
                            order="F",
                        )
                        edge_k = 0.5 * (
                            conductivity[i, j, k]
                            + conductivity[neighbor[0], neighbor[1], neighbor[2]]
                        )
                        conductance = float(edge_k / (spacing * spacing))
                        diag[index] += conductance
                        rows.append(index)
                        cols.append(neighbor_index)
                        values.append(-conductance)
                if root_grid[i, j, k]:
                    diag[index] += root_penalty

    rows.extend(range(count))
    cols.extend(range(count))
    values.extend(float(value) for value in diag)
    matrix = coo_matrix((values, (rows, cols)), shape=(count, count)).tocsr()
    solution = spsolve(matrix, rhs)
    return np.asarray(solution, dtype=np.float64)


def _component_masks(
    solid_mask: np.ndarray,
    root_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    shape = solid_mask.shape if solid_mask.ndim == 3 else None
    if shape is None:
        raise ValueError("solid_mask must be a 3D array")
    structure = ndimage.generate_binary_structure(3, 1)
    labels, component_count = ndimage.label(solid_mask, structure=structure)
    if component_count == 0:
        empty = np.zeros(solid_mask.size, dtype=bool)
        return empty, empty, 0, 0, 0
    rooted_ids = set(np.unique(labels[root_mask & solid_mask]).tolist())
    rooted_ids.discard(0)
    all_ids = set(range(1, component_count + 1))
    unrooted_ids = all_ids - rooted_ids
    rooted = np.isin(labels, list(rooted_ids)) if rooted_ids else np.zeros_like(solid_mask)
    unrooted = (
        np.isin(labels, list(unrooted_ids))
        if unrooted_ids
        else np.zeros_like(solid_mask)
    )
    return (
        rooted.ravel(order="F"),
        unrooted.ravel(order="F"),
        int(component_count),
        int(len(rooted_ids)),
        int(len(unrooted_ids)),
    )


def _erode_material(
    material: np.ndarray,
    grid: CartesianCellGrid,
    *,
    threshold: float,
    erosion_radius_m: float,
) -> np.ndarray:
    if erosion_radius_m <= 0:
        return np.asarray(material, dtype=np.float64).copy()
    shape = grid.cell_shape
    solid = np.asarray(material, dtype=np.float64).reshape(shape, order="F") >= threshold
    distance = ndimage.distance_transform_edt(solid, sampling=grid.spacing)
    eroded = distance >= erosion_radius_m
    return np.where(eroded.ravel(order="F"), material, 0.0)


def _failure_reasons(
    *,
    root_count: int,
    material_count: int,
    nominal: _ConnectivityEvaluation,
    eroded: _ConnectivityEvaluation,
    require_eroded_connectivity: bool,
    eroded_all_nonroot_material_removed: bool,
) -> list[str]:
    reasons: list[str] = []
    if material_count > 0 and root_count == 0:
        reasons.append("missing_root_mask")
    if nominal.unrooted_components > 0:
        reasons.append("nominal_unrooted_components")
    if require_eroded_connectivity and eroded.unrooted_components > 0:
        reasons.append("eroded_unrooted_components")
    if eroded_all_nonroot_material_removed:
        reasons.append("eroded_all_nonroot_material_removed")
    return reasons


def _resolve_manifest_path(directory: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else directory / path
