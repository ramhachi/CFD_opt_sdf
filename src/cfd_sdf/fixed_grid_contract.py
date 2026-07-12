from __future__ import annotations

import gzip
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyvista as pv

from .config import load_project
from .design_state import read_density_design_state, resolve_design_state_path
from .sdf import build_fields


FIXED_GRID_CONTRACT_SCHEMA_VERSION = 1

DENSITY_ARRAYS = (
    "rho",
    "rho_filtered",
    "rho_projected",
    "alpha",
    "allowed_mask",
    "forbidden_mask",
    "fixed_solid_mask",
    "root_mask",
    "active_design_mask",
)

SENSITIVITY_ARRAYS = (
    "d_downforce_d_rho",
    "d_drag_d_rho",
    "d_efficiency_constraint_d_rho",
    "d_connectivity_nominal_d_rho",
    "d_connectivity_eroded_d_rho",
    "active_design_mask",
)

CONNECTIVITY_ARRAYS = (
    "connectivity_nominal_potential",
    "connectivity_eroded_potential",
    "connectivity_nominal_violation",
    "connectivity_eroded_violation",
    "root_mask",
    "active_design_mask",
)


@dataclass(frozen=True)
class CartesianCellGrid:
    origin: tuple[float, float, float]
    spacing: tuple[float, float, float]
    cell_shape: tuple[int, int, int]

    @property
    def point_dimensions(self) -> tuple[int, int, int]:
        return tuple(value + 1 for value in self.cell_shape)

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.cell_shape))

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        upper = tuple(
            self.origin[index] + self.spacing[index] * self.cell_shape[index]
            for index in range(3)
        )
        return self.origin, upper

    def to_dict(self) -> dict[str, object]:
        lower, upper = self.bounds
        return {
            "location": "cell",
            "cell_order": "vtk-x-fastest",
            "origin": list(self.origin),
            "spacing": list(self.spacing),
            "cell_shape": list(self.cell_shape),
            "point_dimensions": list(self.point_dimensions),
            "cell_count": self.cell_count,
            "bounds": [list(lower), list(upper)],
        }


@dataclass(frozen=True)
class FixedGridContractArtifacts:
    output_dir: Path
    topology_state_json: Path
    density_vti: Path
    case_summary_json: Path
    primal_summary_json: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    connectivity_state_vti: Path
    iteration_result_json: Path
    validation_json: Path
    validation: dict[str, object]

    @property
    def ok(self) -> bool:
        return bool(self.validation.get("ok"))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        data["ok"] = self.ok
        return data


def build_openfoam_fixed_grid_contract(
    case_dir: Path,
    *,
    output_dir: Path,
    efficiency_min: float = 3.0,
    docker_image: str = "opencfd/openfoam-default:2512",
    solver_version: str = "2512",
    drag_objective_name: str = "drag",
    downforce_objective_name: str = "downforce",
    drag_sensitivity_array: str = "topOSensas1",
    downforce_sensitivity_array: str = "topOSensdownforce",
    drag_validation_json: Path | None = None,
    downforce_validation_json: Path | None = None,
    efficiency_validation_json: Path | None = None,
) -> FixedGridContractArtifacts:
    if efficiency_min <= 0:
        raise ValueError("efficiency_min must be greater than zero")

    case_dir = case_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    initial_vtk, initial_mesh = _find_source_vtk(case_dir, ("alpha",))
    final_vtk, final_mesh = _find_source_vtk(
        case_dir,
        ("beta", drag_sensitivity_array, downforce_sensitivity_array, "U", "p"),
    )
    initial_grid, initial_flat_indices = _cartesian_grid(initial_mesh)
    final_grid, final_flat_indices = _cartesian_grid(final_mesh)
    _assert_same_grid(initial_grid, final_grid, "initial VTK", "final VTK")

    rho = _reorder_cell_array(initial_mesh, "alpha", initial_flat_indices)
    if "alphaTilda" in final_mesh.cell_data:
        rho_filtered = _reorder_cell_array(
            final_mesh,
            "alphaTilda",
            final_flat_indices,
        )
        filter_source = "OpenFOAM alphaTilda"
    else:
        rho_filtered = rho.copy()
        filter_source = "identity fallback from alpha"
        warnings.append(
            "alphaTilda was not exported; rho_filtered uses the raw rho field."
        )
    rho_projected = _reorder_cell_array(final_mesh, "beta", final_flat_indices)
    beta_max = _read_beta_max(case_dir)
    brinkman_alpha = beta_max * rho_projected

    active_design_mask, fixed_zone_names = _active_design_mask(
        case_dir,
        initial_grid,
        initial_flat_indices,
        warnings,
    )
    allowed_mask = active_design_mask.copy()
    zero_mask = np.zeros(initial_grid.cell_count, dtype=np.uint8)
    density_arrays = {
        "rho": np.clip(rho, 0.0, 1.0).astype(np.float32),
        "rho_filtered": np.clip(rho_filtered, 0.0, 1.0).astype(np.float32),
        "rho_projected": np.clip(rho_projected, 0.0, 1.0).astype(np.float32),
        "alpha": np.maximum(brinkman_alpha, 0.0).astype(np.float32),
        "allowed_mask": allowed_mask,
        "forbidden_mask": zero_mask.copy(),
        "fixed_solid_mask": zero_mask.copy(),
        "root_mask": zero_mask.copy(),
        "active_design_mask": active_design_mask,
    }

    drag_sensitivity = _reorder_cell_array(
        final_mesh,
        drag_sensitivity_array,
        final_flat_indices,
    )
    downforce_sensitivity = _reorder_cell_array(
        final_mesh,
        downforce_sensitivity_array,
        final_flat_indices,
    )
    efficiency_sensitivity = (
        efficiency_min * drag_sensitivity - downforce_sensitivity
    )
    sensitivity_arrays = {
        "d_downforce_d_rho": downforce_sensitivity.astype(np.float32),
        "d_drag_d_rho": drag_sensitivity.astype(np.float32),
        "d_efficiency_constraint_d_rho": efficiency_sensitivity.astype(
            np.float32
        ),
        "d_connectivity_nominal_d_rho": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "d_connectivity_eroded_d_rho": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "active_design_mask": active_design_mask,
    }
    connectivity_arrays = {
        "connectivity_nominal_potential": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "connectivity_eroded_potential": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "connectivity_nominal_violation": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "connectivity_eroded_violation": np.zeros(
            initial_grid.cell_count,
            dtype=np.float32,
        ),
        "root_mask": zero_mask.copy(),
        "active_design_mask": active_design_mask,
    }

    density_vti = output_dir / "density.vti"
    sensitivity_vti = output_dir / "fixed_grid_sensitivity.vti"
    connectivity_vti = output_dir / "connectivity_state.vti"
    _write_cell_vti(
        initial_grid,
        density_arrays,
        density_vti,
        kind="fixed_grid_density",
    )
    _write_cell_vti(
        initial_grid,
        sensitivity_arrays,
        sensitivity_vti,
        kind="fixed_grid_sensitivity",
    )
    _write_cell_vti(
        initial_grid,
        connectivity_arrays,
        connectivity_vti,
        kind="fixed_grid_connectivity",
    )

    source_solver = {
        "backend": "openfoam-topO",
        "solver": "adjointOptimisationFoam",
        "version": solver_version,
        "docker_image": docker_image,
        "case_dir": str(case_dir),
        "initial_vtk": str(initial_vtk),
        "final_vtk": str(final_vtk),
        "mesh_policy": "fixed",
        "remeshing_per_iteration": False,
    }
    density_metadata = _density_array_metadata(
        beta_max=beta_max,
        filter_source=filter_source,
    )
    sensitivity_metadata = _sensitivity_array_metadata()
    validation_evidence = _read_validation_evidence(
        drag_validation_json=drag_validation_json,
        downforce_validation_json=downforce_validation_json,
        efficiency_validation_json=efficiency_validation_json,
    )

    drag_objective_file, drag = _read_objective(
        case_dir,
        drag_objective_name,
    )
    downforce_objective_file, downforce = _read_objective(
        case_dir,
        downforce_objective_name,
    )
    efficiency_constraint = efficiency_min * drag - downforce
    solver_log = _read_solver_log(case_dir)
    convergence = _parse_solver_convergence(solver_log)
    created_at = datetime.now(timezone.utc).isoformat()

    case_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_case_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "grid": initial_grid.to_dict(),
        "design_variable": "rho",
        "brinkman_interpolation": {
            "openfoam_raw_design_field": "alpha",
            "openfoam_filtered_field": "alphaTilda",
            "openfoam_projected_field": "beta",
            "contract_penalization_field": "alpha",
            "function": "linear",
            "beta_max_per_second": beta_max,
        },
        "fixed_zero_porous_zones": fixed_zone_names,
        "mask_source": "OpenFOAM fixedZeroPorousZones",
        "artifacts": {
            "topology_state_json": "topology_state.json",
            "density_vti": density_vti.name,
            "primal_summary_json": "fixed_grid_primal_summary.json",
            "sensitivity_vti": sensitivity_vti.name,
            "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
            "connectivity_state_vti": connectivity_vti.name,
            "iteration_result_json": "topology_iteration_result.json",
        },
    }
    primal_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_primal_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "status": (
            "converged"
            if convergence["primal_converged"] and convergence["completed"]
            else "failed"
        ),
        "objective_definition": "minimize -C_DF",
        "constraint_definition": "efficiency_min*C_D-C_DF <= 0",
        "sign_convention": {
            "drag": "positive in +X",
            "downforce": "positive in -Z",
            "objective": "negative downforce; lower is better",
            "efficiency_constraint": "non-positive is feasible",
        },
        "units": {
            "drag_coefficient": "1",
            "downforce_coefficient": "1",
            "objective": "1",
            "efficiency_constraint": "1",
        },
        "efficiency_min": efficiency_min,
        "drag_coefficient": drag,
        "downforce_coefficient": downforce,
        "objective": -downforce,
        "efficiency": downforce / drag if abs(drag) > 1.0e-30 else None,
        "efficiency_constraint": efficiency_constraint,
        "convergence": convergence,
        "source_fields": {
            "velocity": {"vtk": str(final_vtk), "array": "U", "units": "m/s"},
            "pressure": {
                "vtk": str(final_vtk),
                "array": "p",
                "units": "m2/s2",
            },
        },
        "objective_files": {
            "drag": str(drag_objective_file),
            "downforce": str(downforce_objective_file),
        },
    }
    sensitivity_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "status": (
            "validated"
            if all(
                item.get("status") == "pass"
                for item in validation_evidence.values()
            )
            and validation_evidence
            else "generated"
        ),
        "design_variable": "rho",
        "location": "cell",
        "sensitivity_vti": sensitivity_vti.name,
        "array_metadata": sensitivity_metadata,
        "statistics": {
            name: _array_statistics(values, active_design_mask)
            for name, values in sensitivity_arrays.items()
        },
        "validation_evidence": validation_evidence,
        "connectivity_derivative_status": "not_evaluated_t1_contract_only",
        "connectivity_derivative_note": (
            "T1 reserves both connectivity derivative arrays. The virtual-"
            "diffusion PDE and nonzero derivatives are implemented in T4."
        ),
    }
    topology_state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "created_at_utc": created_at,
        "design_variable": "rho",
        "grid": initial_grid.to_dict(),
        "coordinate_system": {
            "flow_direction": "+X",
            "span_direction": "Y",
            "downforce_direction": "-Z",
            "length_unit": "m",
        },
        "bounds": {"lower": 0.0, "upper": 1.0},
        "density_vti": density_vti.name,
        "density_array": "rho",
        "array_metadata": density_metadata,
        "mask_precedence": [
            "forbidden_mask",
            "fixed_solid_mask",
            "allowed_mask",
            "active_design_mask",
        ],
        "source_solver": source_solver,
        "case_summary_json": "fixed_grid_case_summary.json",
        "primal_summary_json": "fixed_grid_primal_summary.json",
        "sensitivity_vti": sensitivity_vti.name,
        "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
        "connectivity_state_vti": connectivity_vti.name,
        "connectivity_status": "not_evaluated_t1_contract_only",
        "iteration_result_json": "topology_iteration_result.json",
    }
    iteration_result = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "topology_iteration_result",
        "created_at_utc": created_at,
        "iteration": 0,
        "status": "initialized_from_t0_evidence",
        "update_applied": False,
        "accepted": None,
        "objective": {
            "name": "negative_downforce",
            "value": -downforce,
            "units": "1",
            "sign_convention": "lower is better",
        },
        "constraints": {
            "efficiency": {
                "definition": "efficiency_min*C_D-C_DF <= 0",
                "value": efficiency_constraint,
                "limit": 0.0,
                "feasible": efficiency_constraint <= 0.0,
                "units": "1",
            },
            "connectivity_nominal": {
                "status": "not_evaluated_t1_contract_only",
                "value": None,
            },
            "connectivity_eroded": {
                "status": "not_evaluated_t1_contract_only",
                "value": None,
            },
        },
        "artifacts": {
            "topology_state_json": "topology_state.json",
            "density_vti": density_vti.name,
            "case_summary_json": "fixed_grid_case_summary.json",
            "primal_summary_json": "fixed_grid_primal_summary.json",
            "sensitivity_vti": sensitivity_vti.name,
            "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
            "connectivity_state_vti": connectivity_vti.name,
        },
    }

    topology_state_json = output_dir / "topology_state.json"
    case_summary_json = output_dir / "fixed_grid_case_summary.json"
    primal_summary_json = output_dir / "fixed_grid_primal_summary.json"
    sensitivity_summary_json = output_dir / "fixed_grid_sensitivity_summary.json"
    iteration_result_json = output_dir / "topology_iteration_result.json"
    _write_json(topology_state_json, topology_state)
    _write_json(case_summary_json, case_summary)
    _write_json(primal_summary_json, primal_summary)
    _write_json(sensitivity_summary_json, sensitivity_summary)
    _write_json(iteration_result_json, iteration_result)

    validation_json = output_dir / "fixed_grid_contract_validation.json"
    validation = validate_fixed_grid_contract(
        topology_state_json,
        output_path=validation_json,
        inherited_warnings=warnings,
    )
    return FixedGridContractArtifacts(
        output_dir=output_dir,
        topology_state_json=topology_state_json,
        density_vti=density_vti,
        case_summary_json=case_summary_json,
        primal_summary_json=primal_summary_json,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        connectivity_state_vti=connectivity_vti,
        iteration_result_json=iteration_result_json,
        validation_json=validation_json,
        validation=validation,
    )


def build_fixed_grid_contract_from_density_design_state(
    design_state_json: Path,
    *,
    output_dir: Path,
    project_yaml: Path | None = None,
    beta_max: float = 2500.0,
    efficiency_min: float = 3.0,
) -> FixedGridContractArtifacts:
    if beta_max <= 0:
        raise ValueError("beta_max must be greater than zero")
    if efficiency_min <= 0:
        raise ValueError("efficiency_min must be greater than zero")

    design_state_json = design_state_json.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    design_state = read_density_design_state(design_state_json)
    density_path = resolve_design_state_path(
        design_state_json,
        design_state.density_vti,
        local_fallback=Path("density.vti"),
    )
    image = pv.read(density_path)
    dimensions = tuple(int(value) for value in image.dimensions)
    if any(value < 2 for value in dimensions):
        raise ValueError(f"Point-data density grid is too small: {dimensions}")
    if design_state.density_array not in image.point_data:
        raise ValueError(f"Missing point-data density array {design_state.density_array!r}")
    if design_state.allowed_array not in image.point_data:
        raise ValueError(f"Missing point-data allowed array {design_state.allowed_array!r}")

    grid = CartesianCellGrid(
        origin=tuple(float(value) for value in image.origin),
        spacing=tuple(float(value) for value in image.spacing),
        cell_shape=tuple(value - 1 for value in dimensions),
    )
    rho = _point_data_to_cell_average(
        np.asarray(image.point_data[design_state.density_array], dtype=np.float64),
        dimensions,
    )
    allowed_mask = (
        _point_data_to_cell_average(
            np.asarray(image.point_data[design_state.allowed_array], dtype=np.float64),
            dimensions,
        )
        >= 0.5
    ).astype(np.uint8)

    forbidden_mask = np.zeros(grid.cell_count, dtype=np.uint8)
    fixed_solid_mask = np.zeros(grid.cell_count, dtype=np.uint8)
    root_mask = np.zeros(grid.cell_count, dtype=np.uint8)
    role_project = _resolve_role_project(design_state_json, design_state, project_yaml)
    role_source = "legacy density_design_state allowed_mask"
    if role_project is not None:
        try:
            role_masks = _role_masks_from_project(role_project, dimensions, grid)
            allowed_mask = role_masks["allowed_mask"]
            forbidden_mask = role_masks["forbidden_mask"]
            fixed_solid_mask = role_masks["fixed_solid_mask"]
            root_mask = role_masks["root_mask"]
            role_source = str(role_project)
        except Exception:
            role_source = (
                f"legacy density_design_state allowed_mask; project role-mask "
                f"rebuild failed for {role_project}"
            )

    rho = np.clip(rho, 0.0, 1.0)
    rho[(allowed_mask == 0) & (fixed_solid_mask == 0)] = 0.0
    rho[(fixed_solid_mask > 0) & (forbidden_mask == 0)] = 1.0
    rho[forbidden_mask > 0] = 0.0
    active_design_mask = (
        (allowed_mask > 0) & (forbidden_mask == 0) & (fixed_solid_mask == 0)
    ).astype(np.uint8)
    rho_projected = rho.copy()
    brinkman_alpha = beta_max * rho_projected
    zero_mask = np.zeros(grid.cell_count, dtype=np.uint8)
    density_arrays = {
        "rho": rho.astype(np.float32),
        "rho_filtered": rho.astype(np.float32),
        "rho_projected": rho_projected.astype(np.float32),
        "alpha": brinkman_alpha.astype(np.float32),
        "allowed_mask": allowed_mask,
        "forbidden_mask": forbidden_mask,
        "fixed_solid_mask": fixed_solid_mask,
        "root_mask": root_mask,
        "active_design_mask": active_design_mask,
    }
    sensitivity_arrays = {
        "d_downforce_d_rho": np.zeros(grid.cell_count, dtype=np.float32),
        "d_drag_d_rho": np.zeros(grid.cell_count, dtype=np.float32),
        "d_efficiency_constraint_d_rho": np.zeros(grid.cell_count, dtype=np.float32),
        "d_connectivity_nominal_d_rho": np.zeros(grid.cell_count, dtype=np.float32),
        "d_connectivity_eroded_d_rho": np.zeros(grid.cell_count, dtype=np.float32),
        "active_design_mask": active_design_mask,
    }
    connectivity_arrays = {
        "connectivity_nominal_potential": np.zeros(grid.cell_count, dtype=np.float32),
        "connectivity_eroded_potential": np.zeros(grid.cell_count, dtype=np.float32),
        "connectivity_nominal_violation": np.zeros(grid.cell_count, dtype=np.float32),
        "connectivity_eroded_violation": np.zeros(grid.cell_count, dtype=np.float32),
        "root_mask": root_mask if root_mask.size else zero_mask.copy(),
        "active_design_mask": active_design_mask,
    }

    density_vti = output_dir / "density.vti"
    sensitivity_vti = output_dir / "fixed_grid_sensitivity.vti"
    connectivity_vti = output_dir / "connectivity_state.vti"
    _write_cell_vti(grid, density_arrays, density_vti, kind="fixed_grid_density")
    _write_cell_vti(
        grid,
        sensitivity_arrays,
        sensitivity_vti,
        kind="fixed_grid_sensitivity",
    )
    _write_cell_vti(
        grid,
        connectivity_arrays,
        connectivity_vti,
        kind="fixed_grid_connectivity",
    )

    created_at = datetime.now(timezone.utc).isoformat()
    source_solver = {
        "backend": "legacy-density-design-state",
        "solver": "none",
        "version": "density_conversion",
        "docker_image": None,
        "case_dir": str(design_state_json.parent),
        "initial_vtk": None,
        "final_vtk": None,
        "mesh_policy": "fixed",
        "remeshing_per_iteration": False,
        "source_design_state_json": str(design_state_json),
        "source_density_vti": str(density_path),
        "role_mask_source": role_source,
    }
    density_metadata = _density_array_metadata(
        beta_max=beta_max,
        filter_source="identity from legacy density_design_state",
    )
    density_metadata["rho"]["source"] = (
        f"point-data {design_state.density_array} averaged to cells"
    )
    for name in ("allowed_mask", "forbidden_mask", "fixed_solid_mask", "root_mask"):
        density_metadata[name]["source"] = role_source
    sensitivity_metadata = _sensitivity_array_metadata()
    for name, metadata in sensitivity_metadata.items():
        metadata["source"] = "zero placeholder from legacy density conversion"
        metadata["status"] = "not_evaluated_density_conversion_only"

    case_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_case_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "grid": grid.to_dict(),
        "design_variable": "rho",
        "brinkman_interpolation": {
            "contract_penalization_field": "alpha",
            "function": "linear",
            "beta_max_per_second": beta_max,
        },
        "mask_source": role_source,
        "artifacts": {
            "topology_state_json": "topology_state.json",
            "density_vti": density_vti.name,
            "primal_summary_json": "fixed_grid_primal_summary.json",
            "sensitivity_vti": sensitivity_vti.name,
            "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
            "connectivity_state_vti": connectivity_vti.name,
            "iteration_result_json": "topology_iteration_result.json",
        },
    }
    primal_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_primal_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "status": "not_evaluated_density_conversion_only",
        "objective_definition": "minimize -C_DF",
        "constraint_definition": "efficiency_min*C_D-C_DF <= 0",
        "efficiency_min": efficiency_min,
        "drag_coefficient": None,
        "downforce_coefficient": None,
        "objective": None,
        "efficiency": None,
        "efficiency_constraint": None,
    }
    sensitivity_summary = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_summary",
        "created_at_utc": created_at,
        "source_solver": source_solver,
        "status": "not_evaluated_density_conversion_only",
        "design_variable": "rho",
        "location": "cell",
        "sensitivity_vti": sensitivity_vti.name,
        "array_metadata": sensitivity_metadata,
        "statistics": {
            name: _array_statistics(values, active_design_mask)
            for name, values in sensitivity_arrays.items()
        },
        "validation_evidence": {},
        "connectivity_derivative_status": "not_evaluated_density_conversion_only",
    }
    topology_state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "created_at_utc": created_at,
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "coordinate_system": {
            "flow_direction": "+X",
            "span_direction": "Y",
            "downforce_direction": "-Z",
            "length_unit": "m",
        },
        "bounds": {"lower": 0.0, "upper": 1.0},
        "density_vti": density_vti.name,
        "density_array": "rho",
        "array_metadata": density_metadata,
        "mask_precedence": [
            "forbidden_mask",
            "fixed_solid_mask",
            "allowed_mask",
            "active_design_mask",
        ],
        "source_solver": source_solver,
        "case_summary_json": "fixed_grid_case_summary.json",
        "primal_summary_json": "fixed_grid_primal_summary.json",
        "sensitivity_vti": sensitivity_vti.name,
        "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
        "connectivity_state_vti": connectivity_vti.name,
        "connectivity_status": "not_evaluated_density_conversion_only",
        "iteration_result_json": "topology_iteration_result.json",
    }
    iteration_result = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "topology_iteration_result",
        "created_at_utc": created_at,
        "iteration": 0,
        "status": "initialized_from_legacy_density_design_state",
        "update_applied": False,
        "accepted": None,
        "objective": None,
        "constraints": {
            "efficiency": {
                "definition": "efficiency_min*C_D-C_DF <= 0",
                "value": None,
                "limit": 0.0,
                "feasible": None,
                "units": "1",
            },
            "connectivity_nominal": {
                "status": "not_evaluated_density_conversion_only",
                "value": None,
            },
            "connectivity_eroded": {
                "status": "not_evaluated_density_conversion_only",
                "value": None,
            },
        },
        "artifacts": {
            "topology_state_json": "topology_state.json",
            "density_vti": density_vti.name,
            "case_summary_json": "fixed_grid_case_summary.json",
            "primal_summary_json": "fixed_grid_primal_summary.json",
            "sensitivity_vti": sensitivity_vti.name,
            "sensitivity_summary_json": "fixed_grid_sensitivity_summary.json",
            "connectivity_state_vti": connectivity_vti.name,
        },
    }

    topology_state_json = output_dir / "topology_state.json"
    case_summary_json = output_dir / "fixed_grid_case_summary.json"
    primal_summary_json = output_dir / "fixed_grid_primal_summary.json"
    sensitivity_summary_json = output_dir / "fixed_grid_sensitivity_summary.json"
    iteration_result_json = output_dir / "topology_iteration_result.json"
    _write_json(topology_state_json, topology_state)
    _write_json(case_summary_json, case_summary)
    _write_json(primal_summary_json, primal_summary)
    _write_json(sensitivity_summary_json, sensitivity_summary)
    _write_json(iteration_result_json, iteration_result)
    validation_json = output_dir / "fixed_grid_contract_validation.json"
    validation = validate_fixed_grid_contract(
        topology_state_json,
        output_path=validation_json,
        inherited_warnings=[
            "Aerodynamic and connectivity sensitivities are placeholders from legacy density conversion."
        ],
    )
    return FixedGridContractArtifacts(
        output_dir=output_dir,
        topology_state_json=topology_state_json,
        density_vti=density_vti,
        case_summary_json=case_summary_json,
        primal_summary_json=primal_summary_json,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        connectivity_state_vti=connectivity_vti,
        iteration_result_json=iteration_result_json,
        validation_json=validation_json,
        validation=validation,
    )


def validate_fixed_grid_contract(
    topology_state_json: Path,
    *,
    output_path: Path | None = None,
    inherited_warnings: list[str] | None = None,
) -> dict[str, object]:
    topology_state_json = topology_state_json.resolve()
    output_dir = topology_state_json.parent
    errors: list[str] = []
    warnings = list(inherited_warnings or [])

    state = _load_json(topology_state_json, errors)
    if state:
        _check_json_identity(
            state,
            "fixed_grid_topology_state",
            topology_state_json,
            errors,
        )

    artifact_keys = {
        "density_vti": (DENSITY_ARRAYS, "fixed_grid_density"),
        "sensitivity_vti": (
            SENSITIVITY_ARRAYS,
            "fixed_grid_sensitivity",
        ),
        "connectivity_state_vti": (
            CONNECTIVITY_ARRAYS,
            "fixed_grid_connectivity",
        ),
    }
    artifact_paths: dict[str, Path] = {}
    grids: dict[str, CartesianCellGrid] = {}
    arrays_by_artifact: dict[str, dict[str, np.ndarray]] = {}
    for key, (required_arrays, expected_kind) in artifact_keys.items():
        value = state.get(key) if state else None
        if not value:
            errors.append(f"{topology_state_json.name} is missing {key}")
            continue
        path = _resolve_manifest_path(output_dir, value)
        artifact_paths[key] = path
        if not path.exists():
            errors.append(f"Missing artifact: {path}")
            continue
        try:
            grid, arrays = _read_cell_vti(path, expected_kind=expected_kind)
        except Exception as exc:
            errors.append(f"Could not read {path.name}: {exc}")
            continue
        missing = sorted(set(required_arrays) - set(arrays))
        if missing:
            errors.append(
                f"{path.name} is missing arrays: {', '.join(missing)}"
            )
        for name in required_arrays:
            values = arrays.get(name)
            if values is not None and not np.isfinite(values).all():
                errors.append(f"{path.name}:{name} contains non-finite values")
        grids[key] = grid
        arrays_by_artifact[key] = arrays

    if grids:
        reference_name, reference_grid = next(iter(grids.items()))
        for name, grid in grids.items():
            try:
                _assert_same_grid(reference_grid, grid, reference_name, name)
            except ValueError as exc:
                errors.append(str(exc))
        try:
            manifest_grid = _grid_from_manifest(dict(state.get("grid") or {}))
            _assert_same_grid(
                reference_grid,
                manifest_grid,
                reference_name,
                "topology_state.json",
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"Invalid topology_state.json grid: {exc}")

    density_arrays = arrays_by_artifact.get("density_vti", {})
    sensitivity_arrays = arrays_by_artifact.get("sensitivity_vti", {})
    _validate_density_arrays(density_arrays, errors)
    _validate_sensitivity_arrays(
        density_arrays,
        sensitivity_arrays,
        errors,
    )

    density_metadata = dict(state.get("array_metadata") or {}) if state else {}
    _validate_array_metadata(
        density_metadata,
        DENSITY_ARRAYS,
        "topology_state.json",
        errors,
    )

    summary_specs = {
        "case_summary_json": "fixed_grid_case_summary",
        "primal_summary_json": "fixed_grid_primal_summary",
        "sensitivity_summary_json": "fixed_grid_sensitivity_summary",
        "iteration_result_json": "topology_iteration_result",
    }
    loaded_summaries: dict[str, dict[str, object]] = {}
    for key, kind in summary_specs.items():
        value = state.get(key) if state else None
        if not value:
            errors.append(f"{topology_state_json.name} is missing {key}")
            continue
        path = _resolve_manifest_path(output_dir, value)
        data = _load_json(path, errors)
        if data:
            _check_json_identity(data, kind, path, errors)
            loaded_summaries[key] = data

    sensitivity_summary = loaded_summaries.get("sensitivity_summary_json", {})
    _validate_array_metadata(
        dict(sensitivity_summary.get("array_metadata") or {}),
        SENSITIVITY_ARRAYS,
        "fixed_grid_sensitivity_summary.json",
        errors,
    )
    for key in (
        "case_summary_json",
        "primal_summary_json",
        "sensitivity_summary_json",
    ):
        data = loaded_summaries.get(key, {})
        source_solver = dict(data.get("source_solver") or {})
        for field in ("backend", "solver", "version", "case_dir"):
            if not source_solver.get(field):
                errors.append(f"{key} source_solver is missing {field}")
    case_summary = loaded_summaries.get("case_summary_json", {})
    if grids and case_summary:
        try:
            case_grid = _grid_from_manifest(
                dict(case_summary.get("grid") or {})
            )
            _assert_same_grid(
                next(iter(grids.values())),
                case_grid,
                "VTI artifacts",
                "fixed_grid_case_summary.json",
            )
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"Invalid fixed_grid_case_summary.json grid: {exc}")

    if state.get("connectivity_status") == "not_evaluated_t1_contract_only":
        warnings.append(
            "Connectivity fields are contract placeholders; T4 has not been evaluated."
        )

    grid_dict = next(iter(grids.values())).to_dict() if grids else None
    result = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_contract_validation",
        "status": "pass" if not errors else "fail",
        "topology_state_json": str(topology_state_json),
        "grid": grid_dict,
        "required_density_arrays": list(DENSITY_ARRAYS),
        "required_sensitivity_arrays": list(SENSITIVITY_ARRAYS),
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "ok": not errors,
    }
    target = output_path or (output_dir / "fixed_grid_contract_validation.json")
    _write_json(target, result)
    return result


def _density_array_metadata(
    *,
    beta_max: float,
    filter_source: str,
) -> dict[str, dict[str, object]]:
    return {
        "rho": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM alpha at initial state",
            "sign_convention": "0 is fluid and 1 is solid material",
        },
        "rho_filtered": {
            "units": "1",
            "location": "cell",
            "source": filter_source,
            "sign_convention": "0 is fluid and 1 is solid material",
        },
        "rho_projected": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM beta",
            "sign_convention": "larger values apply stronger penalization",
        },
        "alpha": {
            "units": "1/s",
            "location": "cell",
            "source": f"{beta_max:g} * OpenFOAM beta",
            "sign_convention": "non-negative Brinkman momentum penalization",
        },
        "allowed_mask": _mask_metadata("1 where topology updates are allowed"),
        "forbidden_mask": _mask_metadata("1 where material is forbidden"),
        "fixed_solid_mask": _mask_metadata("1 where solid material is fixed"),
        "root_mask": _mask_metadata("1 in root attachment cells"),
        "active_design_mask": _mask_metadata(
            "1 where rho is an active design variable"
        ),
    }


def _sensitivity_array_metadata() -> dict[str, dict[str, object]]:
    return {
        "d_downforce_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM porousDirectionalForce -Z adjoint",
            "sign_convention": "positive increases positive -Z downforce",
        },
        "d_drag_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM porousDirectionalForce +X adjoint",
            "sign_convention": "positive increases positive +X drag",
        },
        "d_efficiency_constraint_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "efficiency_min*d_drag_d_rho-d_downforce_d_rho",
            "sign_convention": "positive increases constraint violation",
        },
        "d_connectivity_nominal_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "T1 reserved zero field",
            "sign_convention": "positive will increase nominal violation",
            "status": "not_evaluated_t1_contract_only",
        },
        "d_connectivity_eroded_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "T1 reserved zero field",
            "sign_convention": "positive will increase eroded violation",
            "status": "not_evaluated_t1_contract_only",
        },
        "active_design_mask": _mask_metadata(
            "1 where sensitivity may update rho"
        ),
    }


def _mask_metadata(description: str) -> dict[str, object]:
    return {
        "units": "1",
        "location": "cell",
        "source": "fixed-grid role mask",
        "sign_convention": description,
    }


def _point_data_to_cell_average(
    values: np.ndarray,
    dimensions: tuple[int, int, int],
) -> np.ndarray:
    expected = int(np.prod(dimensions))
    if values.size != expected:
        raise ValueError(
            f"Point array has {values.size} values; expected {expected}"
        )
    point = np.asarray(values, dtype=np.float64).reshape(dimensions, order="F")
    cell = (
        point[:-1, :-1, :-1]
        + point[1:, :-1, :-1]
        + point[:-1, 1:, :-1]
        + point[1:, 1:, :-1]
        + point[:-1, :-1, 1:]
        + point[1:, :-1, 1:]
        + point[:-1, 1:, 1:]
        + point[1:, 1:, 1:]
    ) / 8.0
    return np.ascontiguousarray(cell.ravel(order="F"))


def _point_data_to_cell_min(
    values: np.ndarray,
    dimensions: tuple[int, int, int],
) -> np.ndarray:
    expected = int(np.prod(dimensions))
    if values.size != expected:
        raise ValueError(
            f"Point array has {values.size} values; expected {expected}"
        )
    point = np.asarray(values, dtype=np.float64).reshape(dimensions, order="F")
    corners = np.stack(
        (
            point[:-1, :-1, :-1],
            point[1:, :-1, :-1],
            point[:-1, 1:, :-1],
            point[1:, 1:, :-1],
            point[:-1, :-1, 1:],
            point[1:, :-1, 1:],
            point[:-1, 1:, 1:],
            point[1:, 1:, 1:],
        ),
        axis=0,
    )
    return np.ascontiguousarray(np.min(corners, axis=0).ravel(order="F"))


def _resolve_role_project(
    design_state_json: Path,
    design_state: object,
    project_yaml: Path | None,
) -> Path | None:
    if project_yaml is not None:
        resolved = Path(project_yaml).resolve()
        return resolved if resolved.exists() else None
    source_project = getattr(design_state, "source_project", None)
    if source_project is None:
        return None
    resolved = resolve_design_state_path(
        design_state_json,
        Path(source_project),
        local_fallback=Path("project.yaml"),
    )
    return resolved if resolved.exists() else None


def _role_masks_from_project(
    project_yaml: Path,
    dimensions: tuple[int, int, int],
    grid: CartesianCellGrid,
) -> dict[str, np.ndarray]:
    config = load_project(project_yaml)
    bundle = build_fields(config)
    if tuple(bundle.grid.shape) != dimensions:
        raise ValueError(
            f"Project role grid {bundle.grid.shape} does not match density dimensions {dimensions}"
        )
    if not np.allclose(bundle.grid.origin, grid.origin, rtol=0.0, atol=1.0e-7):
        raise ValueError("Project role grid origin does not match density grid")
    spacing = tuple(float(value) for value in np.broadcast_to(bundle.grid.spacing, 3))
    if not np.allclose(spacing, grid.spacing, rtol=0.0, atol=1.0e-7):
        raise ValueError("Project role grid spacing does not match density grid")

    def role_mask(phi_name: str, *, default: int) -> np.ndarray:
        if phi_name not in bundle.arrays:
            return np.full(grid.cell_count, default, dtype=np.uint8)
        point_inside = (np.asarray(bundle.arrays[phi_name]) <= 0.0).astype(np.float64)
        return (_point_data_to_cell_average(point_inside.ravel(order="F"), dimensions) >= 0.5).astype(np.uint8)

    def root_role_mask() -> np.ndarray:
        if "root_phi" not in bundle.arrays:
            return np.zeros(grid.cell_count, dtype=np.uint8)
        root_phi = np.asarray(bundle.arrays["root_phi"], dtype=np.float64)
        cell_min_phi = _point_data_to_cell_min(root_phi.ravel(order="F"), dimensions)
        cell_touch_tolerance = 0.5 * float(np.linalg.norm(np.asarray(grid.spacing)))
        return (cell_min_phi <= cell_touch_tolerance).astype(np.uint8)

    return {
        "allowed_mask": role_mask("allowed_phi", default=1),
        "forbidden_mask": role_mask("forbidden_phi", default=0),
        "fixed_solid_mask": role_mask("fixed_phi", default=0),
        "root_mask": root_role_mask(),
    }


def _find_source_vtk(
    case_dir: Path,
    required_arrays: tuple[str, ...],
) -> tuple[Path, pv.DataSet]:
    for path in sorted((case_dir / "VTK").glob("**/internal.vtu")):
        mesh = pv.read(path)
        if all(name in mesh.cell_data for name in required_arrays):
            return path.resolve(), mesh
    raise FileNotFoundError(
        f"No internal.vtu under {case_dir / 'VTK'} contains "
        f"{', '.join(required_arrays)}"
    )


def _cartesian_grid(mesh: pv.DataSet) -> tuple[CartesianCellGrid, np.ndarray]:
    centers = np.asarray(mesh.cell_centers().points, dtype=np.float64)
    if centers.shape != (mesh.n_cells, 3):
        raise ValueError("Could not read three-dimensional cell centers")
    rounded = np.round(centers, decimals=7)
    axes = tuple(np.unique(rounded[:, index]) for index in range(3))
    shape = tuple(int(axis.size) for axis in axes)
    if int(np.prod(shape)) != mesh.n_cells:
        raise ValueError(
            f"Mesh is not a complete Cartesian product: shape={shape}, "
            f"cells={mesh.n_cells}"
        )

    origin: list[float] = []
    spacing: list[float] = []
    for index, axis in enumerate(axes):
        lower = round(float(mesh.bounds[2 * index]), 7)
        upper = round(float(mesh.bounds[2 * index + 1]), 7)
        extent = upper - lower
        if extent <= 0:
            raise ValueError(f"Cannot infer spacing for axis {index}")
        axis_spacing = round(extent / shape[index], 7)
        expected = lower + (np.arange(shape[index]) + 0.5) * axis_spacing
        tolerance = max(1.0e-7, abs(axis_spacing) * 1.0e-5)
        if not np.allclose(axis, expected, rtol=0.0, atol=tolerance):
            raise ValueError(f"Axis {index} is not uniformly spaced")
        origin.append(lower)
        spacing.append(axis_spacing)

    grid = CartesianCellGrid(
        origin=tuple(origin),
        spacing=tuple(spacing),
        cell_shape=shape,
    )
    indices = tuple(
        np.rint(
            (rounded[:, index] - origin[index]) / spacing[index] - 0.5
        ).astype(np.int64)
        for index in range(3)
    )
    if any(
        np.any(index_values < 0)
        or np.any(index_values >= shape[index])
        for index, index_values in enumerate(indices)
    ):
        raise ValueError("Cartesian cell-center mapping is out of range")
    flat_indices = (
        indices[0]
        + shape[0] * indices[1]
        + shape[0] * shape[1] * indices[2]
    ).astype(np.int64)
    if np.unique(flat_indices).size != mesh.n_cells:
        raise ValueError("Cartesian cell-center mapping contains duplicates")
    return grid, flat_indices


def _reorder_cell_array(
    mesh: pv.DataSet,
    array_name: str,
    flat_indices: np.ndarray,
) -> np.ndarray:
    if array_name not in mesh.cell_data:
        raise ValueError(f"Missing cell array {array_name!r}")
    source = np.asarray(mesh.cell_data[array_name])
    if source.ndim != 1 or source.size != mesh.n_cells:
        raise ValueError(
            f"Cell array {array_name!r} must be scalar with {mesh.n_cells} values"
        )
    if not np.isfinite(source).all():
        raise ValueError(f"Cell array {array_name!r} contains non-finite values")
    ordered = np.empty(source.size, dtype=np.float64)
    ordered[flat_indices] = source.astype(np.float64, copy=False)
    return ordered


def _active_design_mask(
    case_dir: Path,
    grid: CartesianCellGrid,
    flat_indices: np.ndarray,
    warnings: list[str],
) -> tuple[np.ndarray, list[str]]:
    zone_names = _read_fixed_zero_zone_names(case_dir)
    zones = _read_cell_zones(case_dir)
    source_mask = np.ones(grid.cell_count, dtype=np.uint8)
    missing: list[str] = []
    for name in zone_names:
        labels = zones.get(name)
        if labels is None:
            missing.append(name)
            continue
        if np.any(labels < 0) or np.any(labels >= grid.cell_count):
            raise ValueError(f"Cell zone {name!r} contains out-of-range labels")
        source_mask[labels] = 0
    if missing:
        raise ValueError(
            "Missing fixed-zero cell zones: " + ", ".join(sorted(missing))
        )
    if not zone_names:
        warnings.append(
            "No fixedZeroPorousZones were found; every cell is marked active."
        )
    ordered = np.empty_like(source_mask)
    ordered[flat_indices] = source_mask
    return ordered, zone_names


def _read_fixed_zero_zone_names(case_dir: Path) -> list[str]:
    path = case_dir / "system" / "optimisationDict"
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"fixedZeroPorousZones\s*\((.*?)\)\s*;",
        text,
        flags=re.DOTALL,
    )
    if not match:
        return []
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", match.group(1))


def _read_cell_zones(case_dir: Path) -> dict[str, np.ndarray]:
    compressed = case_dir / "constant" / "polyMesh" / "cellZones.gz"
    plain = case_dir / "constant" / "polyMesh" / "cellZones"
    if compressed.exists():
        with gzip.open(compressed, "rt", encoding="utf-8") as stream:
            text = stream.read()
    elif plain.exists():
        text = plain.read_text(encoding="utf-8", errors="replace")
    else:
        return {}

    zones: dict[str, np.ndarray] = {}
    pattern = re.compile(
        r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\n"
        r"\{\s*type\s+cellZone\s*;\s*"
        r"cellLabels\s+List<label>\s*(\d+)\s*"
        r"\(\s*(.*?)\s*\)\s*;",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(text):
        name = match.group(1)
        expected_count = int(match.group(2))
        labels = np.fromstring(match.group(3), sep=" ", dtype=np.int64)
        if labels.size != expected_count:
            raise ValueError(
                f"Cell zone {name!r} declares {expected_count} labels "
                f"but contains {labels.size}"
            )
        zones[name] = labels
    return zones


def _read_beta_max(case_dir: Path) -> float:
    path = case_dir / "system" / "optimisationDict"
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"\bbetaMax\s+([-+0-9.eE]+)\s*;",
        text,
    )
    if not match:
        raise ValueError(f"Could not read betaMax from {path}")
    value = float(match.group(1))
    if value <= 0:
        raise ValueError("betaMax must be greater than zero")
    return value


def _read_objective(case_dir: Path, objective_name: str) -> tuple[Path, float]:
    objective_root = case_dir / "optimisation" / "objective"
    candidates = sorted(
        path
        for path in objective_root.glob(f"**/{objective_name}*")
        if path.is_file() and "Instant" not in path.name
    )
    if not candidates:
        raise FileNotFoundError(
            f"No objective file starting with {objective_name!r} "
            f"under {objective_root}"
        )
    path = candidates[-1]
    rows = [
        line.split()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not rows:
        raise ValueError(f"No objective rows in {path}")
    row = rows[-1]
    value_index = 2 if len(row) >= 3 else 1
    return path.resolve(), float(row[value_index])


def _read_solver_log(case_dir: Path) -> str:
    path = case_dir / "log.adjointOptimisationFoam"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_solver_convergence(log_text: str) -> dict[str, object]:
    def iterations(pattern: str) -> int | None:
        match = re.search(pattern, log_text)
        return int(match.group(1)) if match else None

    primal = iterations(r"op1 solution converged in (\d+) iterations")
    drag = iterations(r"as1 solution converged in (\d+) iterations")
    downforce = iterations(r"downforce solution converged in (\d+) iterations")
    completed = (
        "\nEnd\n" in log_text
        and "Finalising parallel run" in log_text
        and "FOAM FATAL" not in log_text
        and "Floating point exception (8)" not in log_text
    )
    return {
        "completed": completed,
        "primal_converged": primal is not None,
        "drag_adjoint_converged": drag is not None,
        "downforce_adjoint_converged": downforce is not None,
        "primal_iterations": primal,
        "drag_adjoint_iterations": drag,
        "downforce_adjoint_iterations": downforce,
    }


def _read_validation_evidence(
    *,
    drag_validation_json: Path | None,
    downforce_validation_json: Path | None,
    efficiency_validation_json: Path | None,
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    paths = {
        "drag": drag_validation_json,
        "downforce": downforce_validation_json,
        "efficiency_constraint": efficiency_validation_json,
    }
    for name, path in paths.items():
        if path is None:
            continue
        resolved = path.resolve()
        data = json.loads(resolved.read_text(encoding="utf-8"))
        evidence[name] = {
            "path": str(resolved),
            "status": data.get("status"),
            "sign_match": data.get("sign_match"),
            "relative_error": data.get("relative_error"),
            "relative_error_tolerance": data.get(
                "relative_error_tolerance"
            ),
        }
    return evidence


def _write_cell_vti(
    grid: CartesianCellGrid,
    arrays: dict[str, np.ndarray],
    path: Path,
    *,
    kind: str,
) -> Path:
    image = pv.ImageData(
        dimensions=grid.point_dimensions,
        spacing=grid.spacing,
        origin=grid.origin,
    )
    for name, values in arrays.items():
        array = np.asarray(values)
        if array.ndim != 1 or array.size != grid.cell_count:
            raise ValueError(
                f"Array {name!r} has shape {array.shape}; "
                f"expected ({grid.cell_count},)"
            )
        image.cell_data[name] = np.ascontiguousarray(array)
    image.field_data["schema_version"] = np.array(
        [FIXED_GRID_CONTRACT_SCHEMA_VERSION],
        dtype=np.int32,
    )
    image.field_data["kind"] = np.array([kind])
    image.field_data["cell_order"] = np.array(["vtk-x-fastest"])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _read_cell_vti(
    path: Path,
    *,
    expected_kind: str | None = None,
) -> tuple[CartesianCellGrid, dict[str, np.ndarray]]:
    image = pv.read(path)
    schema_values = np.asarray(
        image.field_data.get("schema_version", []),
    ).ravel()
    if (
        schema_values.size != 1
        or int(schema_values[0]) != FIXED_GRID_CONTRACT_SCHEMA_VERSION
    ):
        raise ValueError("missing or unsupported field schema_version")
    kind_values = np.asarray(image.field_data.get("kind", [])).ravel()
    if kind_values.size != 1:
        raise ValueError("missing field kind")
    if expected_kind is not None and str(kind_values[0]) != expected_kind:
        raise ValueError(
            f"field kind must be {expected_kind!r}, got {kind_values[0]!r}"
        )
    order_values = np.asarray(
        image.field_data.get("cell_order", []),
    ).ravel()
    if order_values.size != 1 or str(order_values[0]) != "vtk-x-fastest":
        raise ValueError("cell_order must be 'vtk-x-fastest'")
    dimensions = tuple(int(value) for value in image.dimensions)
    if any(value < 2 for value in dimensions):
        raise ValueError(f"VTI point dimensions must be at least 2: {dimensions}")
    grid = CartesianCellGrid(
        origin=tuple(float(value) for value in image.origin),
        spacing=tuple(float(value) for value in image.spacing),
        cell_shape=tuple(value - 1 for value in dimensions),
    )
    arrays = {
        name: np.asarray(image.cell_data[name])
        for name in image.cell_data
        if np.asarray(image.cell_data[name]).ndim == 1
        and np.asarray(image.cell_data[name]).size == grid.cell_count
    }
    return grid, arrays


def _grid_from_manifest(data: dict[str, object]) -> CartesianCellGrid:
    return CartesianCellGrid(
        origin=tuple(float(value) for value in data["origin"]),
        spacing=tuple(float(value) for value in data["spacing"]),
        cell_shape=tuple(int(value) for value in data["cell_shape"]),
    )


def _validate_density_arrays(
    arrays: dict[str, np.ndarray],
    errors: list[str],
) -> None:
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = arrays.get(name)
        if values is not None and (
            np.min(values) < -1.0e-7 or np.max(values) > 1.0 + 1.0e-7
        ):
            errors.append(f"density.vti:{name} must stay within [0, 1]")
    alpha = arrays.get("alpha")
    if alpha is not None and np.min(alpha) < -1.0e-7:
        errors.append("density.vti:alpha must be non-negative")
    for name in (
        "allowed_mask",
        "forbidden_mask",
        "fixed_solid_mask",
        "root_mask",
        "active_design_mask",
    ):
        values = arrays.get(name)
        if values is not None and not np.isin(values, (0, 1)).all():
            errors.append(f"density.vti:{name} must be binary")

    active = arrays.get("active_design_mask")
    allowed = arrays.get("allowed_mask")
    forbidden = arrays.get("forbidden_mask")
    fixed = arrays.get("fixed_solid_mask")
    if active is not None and allowed is not None and np.any(active > allowed):
        errors.append("active_design_mask must be a subset of allowed_mask")
    if active is not None and forbidden is not None and np.any(active & forbidden):
        errors.append("active_design_mask overlaps forbidden_mask")
    if active is not None and fixed is not None and np.any(active & fixed):
        errors.append("active_design_mask overlaps fixed_solid_mask")
    rho = arrays.get("rho")
    rho_projected = arrays.get("rho_projected")
    if (
        rho is not None
        and allowed is not None
        and fixed is not None
        and np.any(rho[(allowed == 0) & (fixed == 0)] > 1.0e-6)
    ):
        errors.append(
            "rho must be zero outside allowed_mask unless fixed_solid_mask is set"
        )
    if (
        rho_projected is not None
        and forbidden is not None
        and np.any(rho_projected[forbidden > 0] > 1.0e-6)
    ):
        errors.append("rho_projected must be zero inside forbidden_mask")


def _validate_sensitivity_arrays(
    density_arrays: dict[str, np.ndarray],
    sensitivity_arrays: dict[str, np.ndarray],
    errors: list[str],
) -> None:
    density_active = density_arrays.get("active_design_mask")
    sensitivity_active = sensitivity_arrays.get("active_design_mask")
    if (
        density_active is not None
        and sensitivity_active is not None
        and not np.array_equal(density_active, sensitivity_active)
    ):
        errors.append(
            "density and sensitivity active_design_mask arrays do not match"
        )
    if sensitivity_active is not None and not np.isin(
        sensitivity_active,
        (0, 1),
    ).all():
        errors.append(
            "fixed_grid_sensitivity.vti:active_design_mask must be binary"
        )
    if sensitivity_active is None:
        return
    inactive = sensitivity_active == 0
    for name in (
        "d_downforce_d_rho",
        "d_drag_d_rho",
        "d_efficiency_constraint_d_rho",
        "d_connectivity_nominal_d_rho",
        "d_connectivity_eroded_d_rho",
    ):
        values = sensitivity_arrays.get(name)
        if values is not None and np.any(np.abs(values[inactive]) > 1.0e-6):
            errors.append(f"{name} must be zero outside active_design_mask")


def _validate_array_metadata(
    metadata: dict[str, object],
    required_arrays: tuple[str, ...],
    source_name: str,
    errors: list[str],
) -> None:
    for name in required_arrays:
        item = dict(metadata.get(name) or {})
        if not item:
            errors.append(f"{source_name} is missing metadata for {name}")
            continue
        for key in ("units", "location", "source", "sign_convention"):
            if not item.get(key):
                errors.append(
                    f"{source_name} metadata for {name} is missing {key}"
                )


def _array_statistics(
    values: np.ndarray,
    active_mask: np.ndarray,
) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    active = np.asarray(active_mask) > 0
    selected = array[active] if active.any() else array
    return {
        "min": float(np.min(selected)) if selected.size else 0.0,
        "max": float(np.max(selected)) if selected.size else 0.0,
        "mean": float(np.mean(selected)) if selected.size else 0.0,
        "l2": float(np.linalg.norm(selected)) if selected.size else 0.0,
        "nonzero_count": int(np.count_nonzero(selected)),
        "active_cell_count": int(np.count_nonzero(active)),
    }


def _assert_same_grid(
    left: CartesianCellGrid,
    right: CartesianCellGrid,
    left_name: str,
    right_name: str,
) -> None:
    if left.cell_shape != right.cell_shape:
        raise ValueError(
            f"Grid mismatch between {left_name} and {right_name}: "
            f"{left.cell_shape} != {right.cell_shape}"
        )
    if not np.allclose(left.origin, right.origin, rtol=0.0, atol=1.0e-10):
        raise ValueError(
            f"Grid origin mismatch between {left_name} and {right_name}"
        )
    if not np.allclose(left.spacing, right.spacing, rtol=0.0, atol=1.0e-10):
        raise ValueError(
            f"Grid spacing mismatch between {left_name} and {right_name}"
        )


def _load_json(path: Path, errors: list[str]) -> dict[str, object]:
    if not path.exists():
        errors.append(f"Missing JSON artifact: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Could not read {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path} must contain a JSON object")
        return {}
    return data


def _check_json_identity(
    data: dict[str, object],
    expected_kind: str,
    path: Path,
    errors: list[str],
) -> None:
    if data.get("schema_version") != FIXED_GRID_CONTRACT_SCHEMA_VERSION:
        errors.append(
            f"{path.name} has unsupported schema_version "
            f"{data.get('schema_version')!r}"
        )
    if data.get("kind") != expected_kind:
        errors.append(
            f"{path.name} kind must be {expected_kind!r}, "
            f"got {data.get('kind')!r}"
        )


def _resolve_manifest_path(directory: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else directory / path


def _write_json(path: Path, data: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
