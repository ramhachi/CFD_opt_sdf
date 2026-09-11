from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyvista as pv
from scipy.ndimage import gaussian_filter

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE
from .fixed_grid_contract import (
    CartesianCellGrid,
    _assert_same_grid,
    _cartesian_grid,
    _read_cell_vti,
    _write_cell_vti,
)
from .fixed_grid_gradient_gate import load_verified_gradient_problem_binding
from .fixed_grid_primal import (
    FixedGridPrimalCaseArtifacts,
    load_fixed_grid_density_state,
    run_fixed_grid_primal_case,
)


FIXED_GRID_SENSITIVITY_SCHEMA_VERSION = 1

SENSITIVITY_OBJECTIVES = (
    "drag",
    "downforce",
    "efficiency_constraint",
)

DIRECTION_MODES = (
    "cellwise",
    "filtered-random",
    "sensitivity",
)


@dataclass(frozen=True)
class FixedGridSensitivityArtifacts:
    case_dir: Path
    topology_state_json: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "case_dir",
            "topology_state_json",
            "sensitivity_vti",
            "sensitivity_summary_json",
        ):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class FixedGridSensitivityDirectionCheck:
    baseline_case_dir: Path
    plus_case_dir: Path
    minus_case_dir: Path
    sensitivity_vti: Path
    output_dir: Path
    report_json: Path
    report_markdown: Path
    direction_vti: Path
    objective: str
    status: str
    finite_difference_derivative: float
    adjoint_directional_derivative: float
    finite_difference_to_adjoint_ratio: float | None
    suggested_sensitivity_multiplier: float | None
    absolute_error: float
    relative_error: float
    relative_error_tolerance: float
    sign_match: bool
    perturbed_cell_count: int
    problem_binding: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        data["ok"] = self.ok
        return data


@dataclass(frozen=True)
class FixedGridSensitivityDirectionSuite:
    baseline_case_dir: Path
    run_dir: Path
    sensitivity_vti: Path
    direction_vti: Path
    direction_summary_json: Path
    plus_topology_state_json: Path
    minus_topology_state_json: Path
    plus_case: FixedGridPrimalCaseArtifacts
    minus_case: FixedGridPrimalCaseArtifacts
    validation: FixedGridSensitivityDirectionCheck | None
    summary_json: Path
    summary_markdown: Path
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "baseline_case_dir",
            "run_dir",
            "sensitivity_vti",
            "direction_vti",
            "direction_summary_json",
            "plus_topology_state_json",
            "minus_topology_state_json",
            "summary_json",
            "summary_markdown",
        ):
            data[key] = str(data[key])
        data["plus_case"] = self.plus_case.to_dict()
        data["minus_case"] = self.minus_case.to_dict()
        data["validation"] = self.validation.to_dict() if self.validation else None
        return data


def build_fixed_grid_sensitivity_from_primal_case(
    case_dir: Path,
    *,
    output_dir: Path | None = None,
    topology_state_json: Path | None = None,
    efficiency_min: float | None = None,
    drag_field: str = "topOSensas1",
    downforce_field: str = "topOSensdownforce",
    time_name: str | None = None,
) -> FixedGridSensitivityArtifacts:
    case_dir = case_dir.resolve()
    if not case_dir.exists():
        raise FileNotFoundError(f"Fixed-grid primal case does not exist: {case_dir}")

    metadata = _read_json(case_dir / "fixed_grid_primal_case_metadata.json")
    primal_summary = _read_json(case_dir / "fixed_grid_primal_summary.json")
    topology_state_path = _resolve_topology_state(
        case_dir,
        metadata,
        topology_state_json,
    )
    density_state = load_fixed_grid_density_state(topology_state_path)

    if efficiency_min is None:
        summary_efficiency = primal_summary.get("efficiency_min")
        efficiency_min = float(summary_efficiency) if summary_efficiency is not None else 3.0
    if efficiency_min <= 0.0:
        raise ValueError("efficiency_min must be greater than zero")

    time_dir = _select_time_dir(case_dir, time_name, required_fields=(drag_field, downforce_field))
    drag_openfoam = read_openfoam_vol_scalar_field(time_dir / _field_filename(time_dir, drag_field))
    downforce_openfoam = read_openfoam_vol_scalar_field(time_dir / _field_filename(time_dir, downforce_field))
    expected_cells = density_state.grid.cell_count
    if drag_openfoam.size != expected_cells:
        raise ValueError(
            f"{drag_field} has {drag_openfoam.size} cells, expected {expected_cells}"
        )
    if downforce_openfoam.size != expected_cells:
        raise ValueError(
            f"{downforce_field} has {downforce_openfoam.size} cells, expected {expected_cells}"
        )

    ordering = _openfoam_to_contract_ordering(case_dir, density_state.grid)
    drag = _to_contract_order(drag_openfoam, ordering)
    downforce = _to_contract_order(downforce_openfoam, ordering)
    active = np.asarray(density_state.arrays["active_design_mask"], dtype=np.uint8)
    inactive = active == 0
    drag[inactive] = 0.0
    downforce[inactive] = 0.0
    efficiency = efficiency_min * drag - downforce

    arrays = {
        "d_downforce_d_rho": downforce.astype(np.float32),
        "d_drag_d_rho": drag.astype(np.float32),
        "d_efficiency_constraint_d_rho": efficiency.astype(np.float32),
        "d_connectivity_nominal_d_rho": np.zeros(expected_cells, dtype=np.float32),
        "d_connectivity_eroded_d_rho": np.zeros(expected_cells, dtype=np.float32),
        "active_design_mask": active,
    }

    target_dir = (output_dir or case_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    sensitivity_vti = target_dir / "fixed_grid_sensitivity.vti"
    sensitivity_summary_json = target_dir / "fixed_grid_sensitivity_summary.json"
    _write_cell_vti(
        density_state.grid,
        arrays,
        sensitivity_vti,
        kind="fixed_grid_sensitivity",
    )

    summary = _sensitivity_summary(
        case_dir=case_dir,
        topology_state_json=density_state.topology_state_json,
        sensitivity_vti=sensitivity_vti,
        efficiency_min=efficiency_min,
        drag_field=drag_field,
        downforce_field=downforce_field,
        time_dir=time_dir,
        arrays=arrays,
        active_design_mask=active,
        metadata=metadata,
        primal_summary=primal_summary,
        ordering=ordering,
    )
    sensitivity_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return FixedGridSensitivityArtifacts(
        case_dir=case_dir,
        topology_state_json=density_state.topology_state_json,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        summary=summary,
    )


def run_fixed_grid_sensitivity_direction_suite(
    baseline_case_dir: Path,
    *,
    run_dir: Path,
    sensitivity_vti: Path | None = None,
    objective: str = "efficiency_constraint",
    direction_mode: str = "cellwise",
    cell_index: int | None = None,
    epsilon: float = 1.0e-2,
    relative_error_tolerance: float = 0.25,
    backend: str = "auto",
    execute: bool = False,
    timeout_seconds: int | None = None,
    overwrite: bool = False,
    template_case_dir: Path | None = None,
    perturbation_seed: int = 1,
    smoothing_radius_cells: float = 1.0,
    adjoint_iterations: int = 1,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
    candidate_binding_json: Path | None = None,
    problem_yaml: Path | None = None,
) -> FixedGridSensitivityDirectionSuite:
    if objective not in SENSITIVITY_OBJECTIVES:
        raise ValueError(
            f"objective must be one of: {', '.join(SENSITIVITY_OBJECTIVES)}"
        )
    if direction_mode not in DIRECTION_MODES:
        raise ValueError(
            f"direction_mode must be one of: {', '.join(DIRECTION_MODES)}"
        )
    if epsilon <= 0.0:
        raise ValueError("epsilon must be greater than zero")
    if relative_error_tolerance < 0.0:
        raise ValueError("relative_error_tolerance must be non-negative")
    if smoothing_radius_cells < 0.0:
        raise ValueError("smoothing_radius_cells must be non-negative")
    if (candidate_binding_json is None) != (problem_yaml is None):
        raise ValueError(
            "candidate_binding_json and problem_yaml must be provided together"
        )

    baseline_case_dir = baseline_case_dir.resolve()
    run_dir = run_dir.resolve()

    baseline_metadata = _read_json(baseline_case_dir / "fixed_grid_primal_case_metadata.json")
    topology_state_json = _resolve_topology_state(
        baseline_case_dir,
        baseline_metadata,
        None,
    )
    density_state = load_fixed_grid_density_state(topology_state_json)
    problem_binding = (
        load_verified_gradient_problem_binding(
            candidate_binding_json,
            problem_yaml,
            expected_topology_state=topology_state_json,
        )
        if candidate_binding_json is not None and problem_yaml is not None
        else None
    )
    _prepare_direction_run_directory(run_dir, overwrite=overwrite)
    baseline_grid, baseline_density = _read_density_input(baseline_case_dir)
    _assert_same_grid(
        baseline_grid,
        density_state.grid,
        "baseline fixed_grid_input_density.vti",
        "topology_state.json",
    )

    if sensitivity_vti is None:
        sensitivity = build_fixed_grid_sensitivity_from_primal_case(baseline_case_dir)
        sensitivity_vti = sensitivity.sensitivity_vti
    sensitivity_vti = sensitivity_vti.resolve()
    sensitivity_grid, sensitivity_arrays = _read_cell_vti(
        sensitivity_vti,
        expected_kind="fixed_grid_sensitivity",
    )
    _assert_same_grid(sensitivity_grid, baseline_grid, "sensitivity", "baseline density")

    sensitivity_array_name = _objective_sensitivity_array(objective)
    selected_sensitivity = np.asarray(
        sensitivity_arrays[sensitivity_array_name],
        dtype=np.float64,
    )
    active = np.asarray(density_state.arrays["active_design_mask"], dtype=np.uint8) > 0
    requested_direction, direction_info = _build_density_direction(
        baseline_density,
        selected_sensitivity,
        active,
        grid=density_state.grid,
        mode=direction_mode,
        epsilon=epsilon,
        cell_index=cell_index,
        perturbation_seed=perturbation_seed,
        smoothing_radius_cells=smoothing_radius_cells,
    )
    plus_density = _apply_contract_hard_masks(
        baseline_density + epsilon * requested_direction,
        density_state.arrays,
    )
    minus_density = _apply_contract_hard_masks(
        baseline_density - epsilon * requested_direction,
        density_state.arrays,
    )
    actual_direction = (plus_density - minus_density) / (2.0 * epsilon)
    actual_direction[~active] = 0.0
    if np.count_nonzero(np.abs(actual_direction) > 1.0e-12) == 0:
        raise ValueError("The generated plus/minus densities produce no active perturbation")

    direction_vti = run_dir / "fixed_grid_sensitivity_direction.vti"
    direction_summary_json = run_dir / "fixed_grid_sensitivity_direction_summary.json"
    _write_cell_vti(
        density_state.grid,
        {
            "rho_baseline": baseline_density.astype(np.float32),
            "rho_plus": plus_density.astype(np.float32),
            "rho_minus": minus_density.astype(np.float32),
            "requested_density_direction": requested_direction.astype(np.float32),
            "actual_density_direction": actual_direction.astype(np.float32),
            sensitivity_array_name: selected_sensitivity.astype(np.float32),
            "active_design_mask": active.astype(np.uint8),
        },
        direction_vti,
        kind="fixed_grid_sensitivity_direction",
    )
    direction_summary = _direction_summary(
        baseline_case_dir=baseline_case_dir,
        sensitivity_vti=sensitivity_vti,
        objective=objective,
        sensitivity_array=sensitivity_array_name,
        direction_mode=direction_mode,
        direction_info=direction_info,
        epsilon=epsilon,
        requested_direction=requested_direction,
        actual_direction=actual_direction,
        plus_density=plus_density,
        minus_density=minus_density,
        active=active,
        problem_binding=problem_binding,
    )
    direction_summary_json.write_text(
        json.dumps(direction_summary, indent=2),
        encoding="utf-8",
    )

    contracts_dir = run_dir / "contracts"
    plus_topology = _write_perturbed_contract(
        density_state,
        contracts_dir / "plus",
        density=plus_density,
        baseline_case_dir=baseline_case_dir,
        direction_summary_json=direction_summary_json,
        label="plus",
        problem_binding=problem_binding,
    )
    minus_topology = _write_perturbed_contract(
        density_state,
        contracts_dir / "minus",
        density=minus_density,
        baseline_case_dir=baseline_case_dir,
        direction_summary_json=direction_summary_json,
        label="minus",
        problem_binding=problem_binding,
    )

    template = _resolve_direction_template_case(
        baseline_metadata,
        template_case_dir,
    )
    plus_case = run_fixed_grid_primal_case(
        plus_topology,
        case_dir=run_dir / "plus",
        template_case_dir=template,
        density_variant="seed",
        backend=backend,
        execute=execute,
        timeout_seconds=timeout_seconds,
        overwrite=True,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
        problem_binding=problem_binding,
    )
    minus_case = run_fixed_grid_primal_case(
        minus_topology,
        case_dir=run_dir / "minus",
        template_case_dir=template,
        density_variant="seed",
        backend=backend,
        execute=execute,
        timeout_seconds=timeout_seconds,
        overwrite=True,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
        problem_binding=problem_binding,
    )

    validation: FixedGridSensitivityDirectionCheck | None = None
    validation_error = None
    if execute:
        try:
            validation = validate_fixed_grid_sensitivity_direction(
                baseline_case_dir,
                plus_case.case_dir,
                minus_case.case_dir,
                sensitivity_vti=sensitivity_vti,
                output_dir=run_dir / "validation",
                objective=objective,
                epsilon=epsilon,
                relative_error_tolerance=relative_error_tolerance,
                problem_binding=problem_binding,
            )
        except Exception as exc:
            validation_error = str(exc)

    summary = _direction_suite_summary(
        baseline_case_dir=baseline_case_dir,
        run_dir=run_dir,
        sensitivity_vti=sensitivity_vti,
        direction_vti=direction_vti,
        direction_summary_json=direction_summary_json,
        plus_topology_state_json=plus_topology,
        minus_topology_state_json=minus_topology,
        plus_case=plus_case,
        minus_case=minus_case,
        validation=validation,
        validation_error=validation_error,
        objective=objective,
        direction_mode=direction_mode,
        epsilon=epsilon,
        execute=execute,
        backend=backend,
        docker_image=docker_image,
        problem_binding=problem_binding,
    )
    summary_json = run_dir / "fixed_grid_sensitivity_direction_suite_summary.json"
    summary_markdown = run_dir / "fixed_grid_sensitivity_direction_suite_summary.md"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary_markdown.write_text(_direction_suite_markdown(summary), encoding="utf-8")

    return FixedGridSensitivityDirectionSuite(
        baseline_case_dir=baseline_case_dir,
        run_dir=run_dir,
        sensitivity_vti=sensitivity_vti,
        direction_vti=direction_vti,
        direction_summary_json=direction_summary_json,
        plus_topology_state_json=plus_topology,
        minus_topology_state_json=minus_topology,
        plus_case=plus_case,
        minus_case=minus_case,
        validation=validation,
        summary_json=summary_json,
        summary_markdown=summary_markdown,
        summary=summary,
    )


def validate_fixed_grid_sensitivity_direction(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    *,
    sensitivity_vti: Path | None = None,
    output_dir: Path | None = None,
    objective: str = "efficiency_constraint",
    epsilon: float = 1.0e-3,
    relative_error_tolerance: float = 0.25,
    perturbation_tolerance: float = 1.0e-12,
    problem_binding: dict[str, object] | None = None,
) -> FixedGridSensitivityDirectionCheck:
    if objective not in SENSITIVITY_OBJECTIVES:
        raise ValueError(
            f"objective must be one of: {', '.join(SENSITIVITY_OBJECTIVES)}"
        )
    if epsilon <= 0.0:
        raise ValueError("epsilon must be greater than zero")
    if relative_error_tolerance < 0.0:
        raise ValueError("relative_error_tolerance must be non-negative")

    baseline_case_dir = baseline_case_dir.resolve()
    plus_case_dir = plus_case_dir.resolve()
    minus_case_dir = minus_case_dir.resolve()
    output_dir = (output_dir or (baseline_case_dir / "fixed_grid_sensitivity_check")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if sensitivity_vti is None:
        sensitivity = build_fixed_grid_sensitivity_from_primal_case(baseline_case_dir)
        sensitivity_vti = sensitivity.sensitivity_vti
    sensitivity_vti = sensitivity_vti.resolve()

    baseline_density = _read_density_input(baseline_case_dir)
    plus_density = _read_density_input(plus_case_dir)
    minus_density = _read_density_input(minus_case_dir)
    grid, sensitivity_arrays = _read_cell_vti(
        sensitivity_vti,
        expected_kind="fixed_grid_sensitivity",
    )
    _assert_same_grid(baseline_density[0], grid, "baseline density", "sensitivity")
    _assert_same_grid(plus_density[0], grid, "plus density", "sensitivity")
    _assert_same_grid(minus_density[0], grid, "minus density", "sensitivity")

    direction = (
        np.asarray(plus_density[1], dtype=np.float64)
        - np.asarray(minus_density[1], dtype=np.float64)
    ) / (2.0 * epsilon)
    active = np.asarray(sensitivity_arrays["active_design_mask"], dtype=np.uint8) > 0
    direction[~active] = 0.0
    perturbed = np.abs(direction) > perturbation_tolerance
    perturbed_cell_count = int(np.count_nonzero(perturbed))
    if perturbed_cell_count == 0:
        raise ValueError("No active density perturbation was detected")

    finite_difference = (
        _objective_value(plus_case_dir, objective)
        - _objective_value(minus_case_dir, objective)
    ) / (2.0 * epsilon)
    sensitivity_array = _objective_sensitivity_array(objective)
    adjoint_derivative = float(
        np.dot(
            np.asarray(sensitivity_arrays[sensitivity_array], dtype=np.float64),
            direction,
        )
    )
    if abs(adjoint_derivative) > 1.0e-30:
        finite_difference_to_adjoint_ratio = float(
            finite_difference / adjoint_derivative
        )
        suggested_sensitivity_multiplier = finite_difference_to_adjoint_ratio
    else:
        finite_difference_to_adjoint_ratio = None
        suggested_sensitivity_multiplier = None
    absolute_error = abs(finite_difference - adjoint_derivative)
    relative_error = absolute_error / max(
        abs(finite_difference),
        abs(adjoint_derivative),
        1.0e-30,
    )
    sign_match = _sign_match(finite_difference, adjoint_derivative)
    status = (
        "pass"
        if sign_match and relative_error <= relative_error_tolerance
        else "fail"
    )

    report_json = output_dir / "fixed_grid_sensitivity_direction_check.json"
    report_markdown = output_dir / "fixed_grid_sensitivity_direction_check.md"
    direction_vti = output_dir / "fixed_grid_sensitivity_direction.vti"
    _write_cell_vti(
        grid,
        {
            "density_direction": direction.astype(np.float32),
            "perturbation_mask": perturbed.astype(np.uint8),
            sensitivity_array: np.asarray(
                sensitivity_arrays[sensitivity_array],
                dtype=np.float32,
            ),
            "active_design_mask": np.asarray(
                sensitivity_arrays["active_design_mask"],
                dtype=np.uint8,
            ),
        },
        direction_vti,
        kind="fixed_grid_sensitivity_direction_check",
    )

    result = FixedGridSensitivityDirectionCheck(
        baseline_case_dir=baseline_case_dir,
        plus_case_dir=plus_case_dir,
        minus_case_dir=minus_case_dir,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        report_json=report_json,
        report_markdown=report_markdown,
        direction_vti=direction_vti,
        objective=objective,
        status=status,
        finite_difference_derivative=float(finite_difference),
        adjoint_directional_derivative=adjoint_derivative,
        finite_difference_to_adjoint_ratio=finite_difference_to_adjoint_ratio,
        suggested_sensitivity_multiplier=suggested_sensitivity_multiplier,
        absolute_error=float(absolute_error),
        relative_error=float(relative_error),
        relative_error_tolerance=float(relative_error_tolerance),
        sign_match=sign_match,
        perturbed_cell_count=perturbed_cell_count,
        problem_binding=problem_binding,
    )
    report_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    report_markdown.write_text(_direction_check_markdown(result), encoding="utf-8")
    _write_direction_check_samples_csv(
        output_dir / "fixed_grid_sensitivity_direction_samples.csv",
        direction=direction,
        sensitivity=np.asarray(sensitivity_arrays[sensitivity_array], dtype=np.float64),
        perturbed=perturbed,
    )
    return result


def read_openfoam_vol_scalar_field(path: Path) -> np.ndarray:
    text = _read_openfoam_text(path)
    uniform = re.search(
        r"\binternalField\s+uniform\s+([-+0-9.eE]+)\s*;",
        text,
    )
    if uniform:
        raise ValueError(
            f"Cannot infer cell count from uniform internalField in {path}"
        )
    match = re.search(
        r"\binternalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*"
        r"\(\s*(.*?)\s*\)\s*;",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError(f"Could not parse nonuniform volScalarField: {path}")
    expected = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", dtype=np.float64)
    if values.size != expected:
        raise ValueError(
            f"Parsed {values.size} values from {path}, expected {expected}"
        )
    if not np.isfinite(values).all():
        raise ValueError(f"Field {path} contains non-finite values")
    return values


def _resolve_topology_state(
    case_dir: Path,
    metadata: dict[str, object],
    override: Path | None,
) -> Path:
    if override is not None:
        return override.resolve()
    value = metadata.get("topology_state_json")
    if not value:
        raise ValueError(
            f"{case_dir / 'fixed_grid_primal_case_metadata.json'} does not record topology_state_json"
        )
    path = Path(str(value))
    if not path.is_absolute():
        path = case_dir / path
    return path.resolve()


def _select_time_dir(
    case_dir: Path,
    time_name: str | None,
    *,
    required_fields: tuple[str, str],
) -> Path:
    if time_name is not None:
        candidate = case_dir / time_name
        if not candidate.is_dir():
            raise FileNotFoundError(f"OpenFOAM time directory does not exist: {candidate}")
        for field in required_fields:
            _field_filename(candidate, field)
        return candidate

    candidates = [
        path
        for path in case_dir.iterdir()
        if path.is_dir() and _parse_time_name(path.name) is not None
    ]
    candidates.sort(key=lambda path: _parse_time_name(path.name) or -math.inf)
    for candidate in reversed(candidates):
        if all(_field_exists(candidate, field) for field in required_fields):
            return candidate
    raise FileNotFoundError(
        f"No OpenFOAM time directory under {case_dir} contains "
        f"{', '.join(required_fields)}"
    )


def _field_filename(time_dir: Path, field: str) -> str:
    for suffix in ("", ".gz"):
        candidate = time_dir / f"{field}{suffix}"
        if candidate.exists():
            return candidate.name
    raise FileNotFoundError(f"Field {field!r} not found in {time_dir}")


def _field_exists(time_dir: Path, field: str) -> bool:
    return (time_dir / field).exists() or (time_dir / f"{field}.gz").exists()


def _parse_time_name(name: str) -> float | None:
    try:
        return float(name)
    except ValueError:
        return None


def _openfoam_to_contract_ordering(
    case_dir: Path,
    contract_grid: CartesianCellGrid,
) -> np.ndarray:
    vtk_root = case_dir / "VTK"
    if vtk_root.exists():
        for path in sorted(vtk_root.glob("**/internal.vtu"), reverse=True):
            mesh = pv.read(path)
            try:
                grid, flat_indices = _cartesian_grid(mesh)
                _assert_same_grid(contract_grid, grid, "topology_state", str(path))
            except ValueError:
                continue
            return flat_indices.astype(np.int64)
    return np.arange(contract_grid.cell_count, dtype=np.int64)


def _to_contract_order(values: np.ndarray, ordering: np.ndarray) -> np.ndarray:
    if values.size != ordering.size:
        raise ValueError(
            f"Field has {values.size} cells but ordering has {ordering.size}"
        )
    ordered = np.empty(values.size, dtype=np.float64)
    ordered[ordering] = values
    return ordered


def _sensitivity_summary(
    *,
    case_dir: Path,
    topology_state_json: Path,
    sensitivity_vti: Path,
    efficiency_min: float,
    drag_field: str,
    downforce_field: str,
    time_dir: Path,
    arrays: dict[str, np.ndarray],
    active_design_mask: np.ndarray,
    metadata: dict[str, object],
    primal_summary: dict[str, object],
    ordering: np.ndarray,
) -> dict[str, object]:
    return {
        "schema_version": FIXED_GRID_SENSITIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "extracted",
        "design_variable": "rho",
        "location": "cell",
        "case_dir": str(case_dir),
        "topology_state_json": str(topology_state_json),
        "sensitivity_vti": str(sensitivity_vti),
        "source_solver": {
            **dict(metadata.get("source_solver") or {}),
            "case_dir": str(case_dir),
            "time_dir": str(time_dir),
            "mesh_policy": "fixed",
            "remeshing_per_iteration": False,
        },
        "objective_definition": "minimize -C_DF",
        "constraint_definition": "efficiency_min*C_D-C_DF <= 0",
        "efficiency_min": efficiency_min,
        "primal_summary_json": str(case_dir / "fixed_grid_primal_summary.json"),
        "primal_values": {
            key: primal_summary.get(key)
            for key in (
                "drag_coefficient",
                "downforce_coefficient",
                "objective",
                "efficiency_constraint",
            )
        },
        "field_sources": {
            "d_drag_d_rho": str(time_dir / _field_filename(time_dir, drag_field)),
            "d_downforce_d_rho": str(time_dir / _field_filename(time_dir, downforce_field)),
            "d_efficiency_constraint_d_rho": (
                "efficiency_min*d_drag_d_rho-d_downforce_d_rho"
            ),
        },
        "array_metadata": _sensitivity_array_metadata(),
        "statistics": {
            name: _array_statistics(values, active_design_mask)
            for name, values in arrays.items()
        },
        "openfoam_mapping": {
            "internal_field_order": "OpenFOAM cell label order",
            "contract_order": "vtk-x-fastest",
            "ordering_hash_sha256_int64": _array_hash_int64(ordering),
            "ordering_source": "case VTK cell centers if available, otherwise identity",
        },
        "connectivity_derivative_status": "not_evaluated_t3_aero_only",
        "connectivity_derivative_note": (
            "T3 extracts aerodynamic density sensitivities. "
            "Virtual-diffusion connectivity derivatives are implemented in T4."
        ),
    }


def _sensitivity_array_metadata() -> dict[str, dict[str, object]]:
    return {
        "d_downforce_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM topOSensdownforce volScalarField",
            "sign_convention": "positive increases positive -Z downforce",
        },
        "d_drag_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "OpenFOAM topOSensas1 volScalarField",
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
            "source": "T3 reserved zero field",
            "sign_convention": "positive will increase nominal violation",
            "status": "not_evaluated_t3_aero_only",
        },
        "d_connectivity_eroded_d_rho": {
            "units": "1",
            "location": "cell",
            "source": "T3 reserved zero field",
            "sign_convention": "positive will increase eroded violation",
            "status": "not_evaluated_t3_aero_only",
        },
        "active_design_mask": {
            "units": "1",
            "location": "cell",
            "source": "fixed-grid role mask",
            "sign_convention": "1 where sensitivity may update rho",
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


def _read_density_input(case_dir: Path) -> tuple[CartesianCellGrid, np.ndarray]:
    path = case_dir / "fixed_grid_input_density.vti"
    grid, arrays = _read_cell_vti(path, expected_kind="fixed_grid_primal_input")
    if "rho_input" not in arrays:
        raise ValueError(f"{path} is missing rho_input")
    return grid, np.asarray(arrays["rho_input"], dtype=np.float64)


def _objective_value(case_dir: Path, objective: str) -> float:
    summary = _read_json(case_dir / "fixed_grid_primal_summary.json")
    if objective == "drag":
        value = summary.get("drag_coefficient")
    elif objective == "downforce":
        value = summary.get("downforce_coefficient")
    else:
        value = summary.get("efficiency_constraint")
    if value is None:
        raise ValueError(f"{case_dir} summary does not contain {objective}")
    return float(value)


def _objective_sensitivity_array(objective: str) -> str:
    if objective == "drag":
        return "d_drag_d_rho"
    if objective == "downforce":
        return "d_downforce_d_rho"
    return "d_efficiency_constraint_d_rho"


def _sign_match(left: float, right: float) -> bool:
    if math.isclose(left, 0.0, abs_tol=1.0e-12):
        return math.isclose(right, 0.0, abs_tol=1.0e-12)
    if math.isclose(right, 0.0, abs_tol=1.0e-12):
        return False
    return left * right > 0.0


def _direction_check_markdown(result: FixedGridSensitivityDirectionCheck) -> str:
    return (
        "# Fixed-Grid Sensitivity Direction Check\n\n"
        f"- Status: `{result.status}`\n"
        f"- Objective: `{result.objective}`\n"
        f"- Perturbed cells: `{result.perturbed_cell_count}`\n"
        f"- Finite-difference derivative: `{result.finite_difference_derivative:.12g}`\n"
        f"- Adjoint directional derivative: `{result.adjoint_directional_derivative:.12g}`\n"
        f"- Finite-difference / adjoint ratio: "
        f"`{_format_optional_float(result.finite_difference_to_adjoint_ratio)}`\n"
        f"- Relative error: `{result.relative_error:.6%}`\n"
        f"- Relative-error tolerance: `{result.relative_error_tolerance:.6%}`\n"
        f"- Sign match: `{str(result.sign_match).lower()}`\n"
        f"- Sensitivity VTI: `{result.sensitivity_vti}`\n"
        f"- Direction VTI: `{result.direction_vti}`\n"
    )


def _write_direction_check_samples_csv(
    path: Path,
    *,
    direction: np.ndarray,
    sensitivity: np.ndarray,
    perturbed: np.ndarray,
) -> None:
    rows = np.flatnonzero(perturbed)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("cell_index", "density_direction", "sensitivity", "contribution"),
        )
        writer.writeheader()
        for index in rows:
            writer.writerow(
                {
                    "cell_index": int(index),
                    "density_direction": f"{float(direction[index]):.12g}",
                    "sensitivity": f"{float(sensitivity[index]):.12g}",
                    "contribution": f"{float(direction[index] * sensitivity[index]):.12g}",
                }
            )


def _prepare_direction_run_directory(run_dir: Path, *, overwrite: bool) -> None:
    if run_dir.exists() and any(run_dir.iterdir()):
        marker = run_dir / "fixed_grid_sensitivity_direction_suite_summary.json"
        if not overwrite or not marker.exists():
            raise FileExistsError(
                f"{run_dir} already exists. Use overwrite=True for a generated direction suite."
            )
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)


def _build_density_direction(
    density: np.ndarray,
    sensitivity: np.ndarray,
    active: np.ndarray,
    *,
    grid: CartesianCellGrid,
    mode: str,
    epsilon: float,
    cell_index: int | None,
    perturbation_seed: int,
    smoothing_radius_cells: float,
) -> tuple[np.ndarray, dict[str, object]]:
    rho = np.asarray(density, dtype=np.float64)
    sens = np.asarray(sensitivity, dtype=np.float64)
    active_mask = np.asarray(active, dtype=bool)
    if rho.shape != sens.shape or rho.shape != active_mask.shape:
        raise ValueError("density, sensitivity, and active mask shapes must match")
    if not np.isfinite(sens[active_mask]).all():
        raise ValueError("sensitivity contains non-finite values in active cells")

    direction = np.zeros_like(rho, dtype=np.float64)
    info: dict[str, object] = {"mode": mode}
    if mode == "cellwise":
        index = _select_cellwise_direction_index(
            rho,
            sens,
            active_mask,
            epsilon=epsilon,
            cell_index=cell_index,
        )
        sign = 1.0 if sens[index] >= 0.0 else -1.0
        if sign > 0.0 and rho[index] >= 1.0:
            sign = -1.0
        if sign < 0.0 and rho[index] <= 0.0:
            sign = 1.0
        direction[index] = sign
        info.update(
            {
                "selected_cell_index": int(index),
                "selected_density": float(rho[index]),
                "selected_sensitivity": float(sens[index]),
                "selected_direction": float(sign),
                "selection_policy": (
                    "explicit_cell_index"
                    if cell_index is not None
                    else "largest_abs_sensitivity_prefer_central_feasible"
                ),
            }
        )
    elif mode == "sensitivity":
        direction[active_mask] = sens[active_mask]
        info["selection_policy"] = "normalized_selected_objective_sensitivity"
    elif mode == "filtered-random":
        rng = np.random.default_rng(perturbation_seed)
        noise = rng.normal(0.0, 1.0, size=grid.cell_shape)
        if smoothing_radius_cells > 0:
            noise = gaussian_filter(noise, sigma=smoothing_radius_cells, mode="nearest")
        direction = noise.ravel(order="F").astype(np.float64)
        direction[~active_mask] = 0.0
        info.update(
            {
                "selection_policy": "normalized_filtered_random_field",
                "perturbation_seed": int(perturbation_seed),
                "smoothing_radius_cells": float(smoothing_radius_cells),
            }
        )
    else:
        raise ValueError(f"Unsupported direction mode: {mode}")

    direction[~active_mask] = 0.0
    max_abs = float(np.max(np.abs(direction[active_mask]))) if np.any(active_mask) else 0.0
    if max_abs <= 1.0e-30:
        raise ValueError("Generated direction is zero on active cells")
    if mode != "cellwise":
        direction = direction / max_abs
    info["requested_direction_stats"] = _simple_array_stats(direction[active_mask])
    return direction, info


def _select_cellwise_direction_index(
    rho: np.ndarray,
    sensitivity: np.ndarray,
    active: np.ndarray,
    *,
    epsilon: float,
    cell_index: int | None,
) -> int:
    if cell_index is not None:
        if cell_index < 0 or cell_index >= rho.size:
            raise ValueError(f"cell_index {cell_index} is outside [0, {rho.size})")
        if not active[cell_index]:
            raise ValueError(f"cell_index {cell_index} is not active")
        return int(cell_index)

    finite = np.isfinite(sensitivity)
    central = active & finite & (rho >= epsilon) & (rho <= 1.0 - epsilon)
    candidates = central if np.any(central) else (active & finite)
    if not np.any(candidates):
        raise ValueError("No active finite-sensitivity cell is available")
    scores = np.where(candidates, np.abs(sensitivity), -np.inf)
    return int(np.argmax(scores))


def _apply_contract_hard_masks(
    density: np.ndarray,
    arrays: dict[str, np.ndarray],
) -> np.ndarray:
    values = np.asarray(density, dtype=np.float64).copy()
    allowed = np.asarray(arrays["allowed_mask"], dtype=np.uint8) > 0
    forbidden = np.asarray(arrays["forbidden_mask"], dtype=np.uint8) > 0
    fixed_solid = np.asarray(arrays["fixed_solid_mask"], dtype=np.uint8) > 0
    values[~allowed & ~fixed_solid] = 0.0
    values[fixed_solid & ~forbidden] = 1.0
    values[forbidden] = 0.0
    return np.clip(values, 0.0, 1.0)


def _write_perturbed_contract(
    density_state,
    output_dir: Path,
    *,
    density: np.ndarray,
    baseline_case_dir: Path,
    direction_summary_json: Path,
    label: str,
    problem_binding: dict[str, object] | None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    beta_max = _infer_beta_max(density_state.arrays)
    rho = np.asarray(density, dtype=np.float64)
    arrays = {
        "rho": rho.astype(np.float32),
        "rho_filtered": rho.astype(np.float32),
        "rho_projected": rho.astype(np.float32),
        "alpha": (beta_max * rho).astype(np.float32),
        "allowed_mask": np.asarray(
            density_state.arrays["allowed_mask"],
            dtype=np.uint8,
        ),
        "forbidden_mask": np.asarray(
            density_state.arrays["forbidden_mask"],
            dtype=np.uint8,
        ),
        "fixed_solid_mask": np.asarray(
            density_state.arrays["fixed_solid_mask"],
            dtype=np.uint8,
        ),
        "root_mask": np.asarray(
            density_state.arrays["root_mask"],
            dtype=np.uint8,
        ),
        "active_design_mask": np.asarray(
            density_state.arrays["active_design_mask"],
            dtype=np.uint8,
        ),
    }
    density_vti = output_dir / "density.vti"
    _write_cell_vti(
        density_state.grid,
        arrays,
        density_vti,
        kind="fixed_grid_density",
    )

    state = json.loads(json.dumps(density_state.state))
    state["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    state["density_vti"] = density_vti.name
    state["source_solver"] = {
        **dict(state.get("source_solver") or {}),
        "backend": "fixed-grid-sensitivity-direction",
        "solver": "density_perturbation",
        "case_dir": str(baseline_case_dir),
        "parent_topology_state_json": str(density_state.topology_state_json),
        "baseline_case_dir": str(baseline_case_dir),
        "direction_summary_json": str(direction_summary_json),
        "direction_label": label,
        "mesh_policy": "fixed",
        "remeshing_per_iteration": False,
    }
    if problem_binding is not None:
        for key in (
            "problem_id",
            "problem_spec_sha256",
            "candidate_id",
            "parent_candidate_id",
            "iteration",
        ):
            if state.get(key) != problem_binding.get(key):
                raise ValueError(
                    f"baseline topology state {key} does not match candidate binding"
                )
        state["baseline_candidate_binding"] = problem_binding
    state["density_sha256"] = _file_sha256(density_vti)
    path = output_dir / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    summary = {
        "schema_version": FIXED_GRID_SENSITIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_direction_contract",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "topology_state_json": str(path),
        "density_vti": str(density_vti),
        "density_sha256": _file_sha256(density_vti),
        "baseline_case_dir": str(baseline_case_dir),
        "direction_summary_json": str(direction_summary_json),
        "beta_max": beta_max,
        "density_statistics": _simple_array_stats(rho),
        "baseline_candidate_binding": problem_binding,
    }
    (output_dir / "fixed_grid_direction_contract_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return path


def _infer_beta_max(arrays: dict[str, np.ndarray]) -> float:
    projected = np.asarray(arrays.get("rho_projected"), dtype=np.float64)
    alpha = np.asarray(arrays.get("alpha"), dtype=np.float64)
    if projected.shape == alpha.shape:
        mask = np.abs(projected) > 1.0e-12
        ratios = alpha[mask] / projected[mask] if np.any(mask) else np.array([])
        ratios = ratios[np.isfinite(ratios) & (ratios > 0.0)]
        if ratios.size:
            return float(np.median(ratios))
    return 2500.0


def _resolve_direction_template_case(
    metadata: dict[str, object],
    override: Path | None,
) -> Path:
    if override is not None:
        return override.resolve()
    value = metadata.get("template_case_dir")
    if value:
        return Path(str(value)).resolve()
    source_solver = dict(metadata.get("source_solver") or {})
    value = source_solver.get("case_dir")
    if value:
        return Path(str(value)).resolve()
    raise ValueError("template_case_dir is required when baseline metadata lacks it")


def _direction_summary(
    *,
    baseline_case_dir: Path,
    sensitivity_vti: Path,
    objective: str,
    sensitivity_array: str,
    direction_mode: str,
    direction_info: dict[str, object],
    epsilon: float,
    requested_direction: np.ndarray,
    actual_direction: np.ndarray,
    plus_density: np.ndarray,
    minus_density: np.ndarray,
    active: np.ndarray,
    problem_binding: dict[str, object] | None,
) -> dict[str, object]:
    active_mask = np.asarray(active, dtype=bool)
    perturbed = np.abs(actual_direction) > 1.0e-12
    return {
        "schema_version": FIXED_GRID_SENSITIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_direction_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_case_dir": str(baseline_case_dir),
        "sensitivity_vti": str(sensitivity_vti),
        "objective": objective,
        "sensitivity_array": sensitivity_array,
        "direction_mode": direction_mode,
        "epsilon": epsilon,
        "direction_info": direction_info,
        "statistics": {
            "requested_direction_active": _simple_array_stats(
                requested_direction[active_mask],
            ),
            "actual_direction_active": _simple_array_stats(
                actual_direction[active_mask],
            ),
            "plus_density_active": _simple_array_stats(plus_density[active_mask]),
            "minus_density_active": _simple_array_stats(minus_density[active_mask]),
        },
        "active_cell_count": int(np.count_nonzero(active_mask)),
        "perturbed_cell_count": int(np.count_nonzero(perturbed & active_mask)),
        "problem_binding": problem_binding,
    }


def _perturbed_contract_record(topology_state_json: Path) -> dict[str, object]:
    state = _read_json(topology_state_json)
    density = Path(str(state["density_vti"]))
    if not density.is_absolute():
        density = topology_state_json.parent / density
    density = density.resolve()
    return {
        "topology_state_json": str(topology_state_json.resolve()),
        "topology_state_sha256": _file_sha256(topology_state_json),
        "density_vti": str(density),
        "density_sha256": _file_sha256(density),
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _direction_suite_summary(
    *,
    baseline_case_dir: Path,
    run_dir: Path,
    sensitivity_vti: Path,
    direction_vti: Path,
    direction_summary_json: Path,
    plus_topology_state_json: Path,
    minus_topology_state_json: Path,
    plus_case: FixedGridPrimalCaseArtifacts,
    minus_case: FixedGridPrimalCaseArtifacts,
    validation: FixedGridSensitivityDirectionCheck | None,
    validation_error: str | None,
    objective: str,
    direction_mode: str,
    epsilon: float,
    execute: bool,
    backend: str,
    docker_image: str,
    problem_binding: dict[str, object] | None,
) -> dict[str, object]:
    if not execute:
        status = "prepared"
        ok = True
    elif validation is not None:
        status = validation.status
        ok = validation.ok
    else:
        status = "fail"
        ok = False
    return {
        "schema_version": FIXED_GRID_SENSITIVITY_SCHEMA_VERSION,
        "kind": "fixed_grid_sensitivity_direction_suite_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "ok": ok,
        "execute": execute,
        "backend": backend,
        "docker_image": docker_image,
        "baseline_case_dir": str(baseline_case_dir),
        "run_dir": str(run_dir),
        "objective": objective,
        "direction_mode": direction_mode,
        "epsilon": epsilon,
        "sensitivity_vti": str(sensitivity_vti),
        "direction_vti": str(direction_vti),
        "direction_summary_json": str(direction_summary_json),
        "plus_topology_state_json": str(plus_topology_state_json),
        "minus_topology_state_json": str(minus_topology_state_json),
        "plus_case": plus_case.to_dict(),
        "minus_case": minus_case.to_dict(),
        "validation": validation.to_dict() if validation is not None else None,
        "validation_error": validation_error,
        "problem_binding": problem_binding,
        "perturbed_contracts": {
            "plus": _perturbed_contract_record(plus_topology_state_json),
            "minus": _perturbed_contract_record(minus_topology_state_json),
        },
    }


def _direction_suite_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Fixed-Grid Sensitivity Direction Suite",
        "",
        f"- Status: `{summary['status']}`",
        f"- Objective: `{summary['objective']}`",
        f"- Direction mode: `{summary['direction_mode']}`",
        f"- Epsilon: `{summary['epsilon']}`",
        f"- Execute: `{str(summary['execute']).lower()}`",
        f"- Sensitivity VTI: `{summary['sensitivity_vti']}`",
        f"- Direction VTI: `{summary['direction_vti']}`",
    ]
    validation = summary.get("validation")
    if isinstance(validation, dict):
        lines.extend(
            [
                f"- Finite-difference derivative: `{validation['finite_difference_derivative']:.12g}`",
                f"- Adjoint directional derivative: `{validation['adjoint_directional_derivative']:.12g}`",
                "- Finite-difference / adjoint ratio: "
                f"`{_format_optional_float(validation.get('finite_difference_to_adjoint_ratio'))}`",
                f"- Relative error: `{validation['relative_error']:.6%}`",
                f"- Sign match: `{str(validation['sign_match']).lower()}`",
            ]
        )
    if summary.get("validation_error"):
        lines.append(f"- Validation error: `{summary['validation_error']}`")
    return "\n".join(lines) + "\n"


def _simple_array_stats(values: np.ndarray) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "l2": 0.0,
            "nonzero_count": 0,
            "count": 0,
        }
    return {
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "l2": float(np.linalg.norm(array)),
        "nonzero_count": int(np.count_nonzero(array)),
        "count": int(array.size),
    }


def _format_optional_float(value: object) -> str:
    if value is None:
        return "null"
    return f"{float(value):.12g}"


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_openfoam_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8", errors="replace")


def _array_hash_int64(values: np.ndarray) -> str:
    import hashlib

    array = np.asarray(values, dtype=np.int64)
    return hashlib.sha256(array.tobytes()).hexdigest()
