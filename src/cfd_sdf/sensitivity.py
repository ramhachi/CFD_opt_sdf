from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pyvista as pv

from .config import load_project
from .design_state import DensityDesignState, read_density_design_state, resolve_design_state_path
from .grid import UniformGrid


SENSITIVITY_SCHEMA_VERSION = 1
DENSITY_UPDATE_SCHEMA_VERSION = 1
SENSITIVITY_DIAGNOSTIC_EPS = 1.0e-12


@dataclass(frozen=True)
class DensityStateData:
    design_state_json: Path
    state: DensityDesignState
    density_vti: Path
    grid: UniformGrid
    density: np.ndarray
    allowed_mask: np.ndarray


@dataclass(frozen=True)
class SensitivityArtifacts:
    design_state_json: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("design_state_json", "sensitivity_vti", "sensitivity_summary_json"):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class DensityUpdatePreview:
    design_state_json: Path
    sensitivity_vti: Path
    density_update_vti: Path
    move_limit: float
    step_size: float
    density_lower: float
    density_upper: float
    active_cell_count: int
    density_delta_min: float
    density_delta_max: float
    density_delta_l2: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("design_state_json", "sensitivity_vti", "density_update_vti"):
            data[key] = str(data[key])
        return data


def load_density_state(design_state_json: Path) -> DensityStateData:
    design_state_json = design_state_json.resolve()
    state = read_density_design_state(design_state_json)
    density_vti = resolve_design_state_path(
        design_state_json,
        state.density_vti,
        local_fallback=Path(state.density_vti).name,
    )
    grid, arrays = read_vti_scalar_arrays(density_vti)
    if state.density_array not in arrays:
        raise ValueError(f"Missing density array '{state.density_array}' in {density_vti}")
    if state.allowed_array not in arrays:
        raise ValueError(f"Missing allowed array '{state.allowed_array}' in {density_vti}")

    density = arrays[state.density_array].astype(np.float32, copy=False)
    allowed_mask = arrays[state.allowed_array] > 0
    _validate_grid_contract(state, grid)
    return DensityStateData(
        design_state_json=design_state_json,
        state=state,
        density_vti=density_vti,
        grid=grid,
        density=density,
        allowed_mask=allowed_mask,
    )


def write_mock_sensitivity_artifacts(
    design_state_json: Path,
    *,
    output_dir: Path | None = None,
) -> SensitivityArtifacts:
    density_state = load_density_state(design_state_json)
    output_dir = output_dir or density_state.design_state_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    arrays = create_mock_sensitivity_arrays(density_state)
    sensitivity_vti = output_dir / "sensitivity.vti"
    write_vti_scalar_arrays(density_state.grid, arrays, sensitivity_vti)

    summary = create_sensitivity_summary(
        density_state=density_state,
        sensitivity_vti=sensitivity_vti,
        arrays=arrays,
        backend="mock-analytic",
        backend_version="1",
        projection_method="direct-grid-density",
    )
    summary_path = output_dir / "sensitivity_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return SensitivityArtifacts(
        design_state_json=density_state.design_state_json,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=summary_path,
        summary=summary,
    )


def create_mock_sensitivity_arrays(density_state: DensityStateData) -> dict[str, np.ndarray]:
    density = density_state.density.astype(np.float64, copy=False)
    active = density_state.allowed_mask
    weights = mock_density_weights(density_state.grid)
    downforce = weights["downforce_weight"] * (1.0 - 0.5 * density)
    drag = weights["drag_linear"] + 2.0 * weights["drag_quadratic"] * density
    efficiency_min = _efficiency_min_from_project(density_state)
    objective = -downforce
    constraint = efficiency_min * drag - downforce

    mask = active.astype(np.float32)
    return {
        "objective_density_sensitivity": (objective * mask).astype(np.float32),
        "downforce_density_sensitivity": (downforce * mask).astype(np.float32),
        "drag_density_sensitivity": (drag * mask).astype(np.float32),
        "constraint_sensitivity": (constraint * mask).astype(np.float32),
        "active_mask": active.astype(np.uint8),
    }


def evaluate_mock_density_functionals(
    density_state: DensityStateData,
    density: np.ndarray | None = None,
) -> dict[str, float]:
    values = density_state.density if density is None else density
    density_values = np.clip(values.astype(np.float64, copy=False), 0.0, 1.0)
    active = density_state.allowed_mask
    weights = mock_density_weights(density_state.grid)
    downforce_density = weights["downforce_weight"] * (density_values - 0.25 * density_values * density_values)
    drag_density = weights["drag_linear"] * density_values + weights["drag_quadratic"] * density_values * density_values
    downforce = float(np.sum(downforce_density[active]))
    drag = float(np.sum(drag_density[active]))
    efficiency_min = _efficiency_min_from_project(density_state)
    objective = -downforce
    return {
        "objective": float(objective),
        "downforce": float(downforce),
        "drag": float(drag),
        "constraint": float(efficiency_min * drag - downforce),
    }


def mock_density_weights(grid: UniformGrid) -> dict[str, np.ndarray]:
    x, y, z = _coordinate_arrays(grid)
    bounds = grid.bounds
    x_span = max(float(bounds[1, 0] - bounds[0, 0]), 1.0e-12)
    y_span = max(float(bounds[1, 1] - bounds[0, 1]), 1.0e-12)
    z_span = max(float(bounds[1, 2] - bounds[0, 2]), 1.0e-12)

    x_norm = (x - bounds[0, 0]) / x_span
    y_center = 0.5 * (bounds[0, 1] + bounds[1, 1])
    span_weight = np.clip(1.0 - np.abs(y - y_center) / (0.5 * y_span), 0.15, 1.0)
    height_weight = 0.45 + 0.55 * np.clip((z - bounds[0, 2]) / z_span, 0.0, 1.0)
    chord_weight = 0.55 + 0.45 * np.exp(-((x_norm - 0.48) / 0.28) ** 2)
    return {
        "downforce_weight": (0.010 * span_weight * height_weight * chord_weight).astype(np.float64),
        "drag_linear": (0.0015 + 0.0006 * chord_weight).astype(np.float64),
        "drag_quadratic": np.full(grid.shape, 0.0006, dtype=np.float64),
    }


def create_sensitivity_summary(
    *,
    density_state: DensityStateData,
    sensitivity_vti: Path,
    arrays: dict[str, np.ndarray],
    backend: str,
    backend_version: str,
    projection_method: str,
    source_primal_case: Path | None = None,
    source_adjoint_case: Path | None = None,
) -> dict[str, object]:
    required = {
        "objective_density_sensitivity",
        "downforce_density_sensitivity",
        "drag_density_sensitivity",
        "constraint_sensitivity",
        "active_mask",
    }
    missing = sorted(required - set(arrays))
    constraint_diagnostics = _constraint_sensitivity_diagnostics(arrays)
    return {
        "schema_version": SENSITIVITY_SCHEMA_VERSION,
        "kind": "density_sensitivity_summary",
        "backend": backend,
        "backend_version": backend_version,
        "objective_name": "minimize_negative_downforce_with_constraints",
        "sign_convention": "objective_density_sensitivity is d(objective)/d(density); negative values favor increasing density under gradient descent.",
        "source_design_state": str(density_state.design_state_json),
        "source_density_vti": str(density_state.density_vti),
        "source_primal_case": str(source_primal_case) if source_primal_case else None,
        "source_adjoint_case": str(source_adjoint_case) if source_adjoint_case else None,
        "projection_method": projection_method,
        "sensitivity_vti": str(sensitivity_vti),
        "arrays": sorted(arrays.keys()),
        "statistics": {name: _array_stats(values) for name, values in arrays.items()},
        "failed_or_missing_arrays": missing,
        "constraint_sensitivity_status": constraint_diagnostics["status"],
        "constraint_sensitivity_diagnostics": constraint_diagnostics,
    }


def read_sensitivity_vti(path: Path) -> tuple[UniformGrid, dict[str, np.ndarray]]:
    grid, arrays = read_vti_scalar_arrays(path)
    required = {
        "objective_density_sensitivity",
        "downforce_density_sensitivity",
        "drag_density_sensitivity",
        "constraint_sensitivity",
        "active_mask",
    }
    missing = sorted(required - set(arrays))
    if missing:
        raise ValueError(f"Sensitivity VTI is missing required arrays: {', '.join(missing)}")
    return grid, arrays


def write_density_update_preview(
    design_state_json: Path,
    *,
    sensitivity_vti: Path | None = None,
    output_dir: Path | None = None,
    move_limit: float = 0.05,
    step_size: float = 1.0,
    density_lower: float = 0.0,
    density_upper: float = 1.0,
) -> DensityUpdatePreview:
    if move_limit < 0.0:
        raise ValueError("move_limit must be >= 0")
    if density_lower > density_upper:
        raise ValueError("density_lower must be <= density_upper")

    density_state = load_density_state(design_state_json)
    sensitivity_vti = sensitivity_vti or (density_state.design_state_json.parent / "sensitivity.vti")
    output_dir = output_dir or density_state.design_state_json.parent
    sensitivity_grid, sensitivity_arrays = read_sensitivity_vti(sensitivity_vti)
    _assert_same_grid(density_state.grid, sensitivity_grid, "density", "sensitivity")

    gradient = sensitivity_arrays["objective_density_sensitivity"].astype(np.float32, copy=False)
    active = (sensitivity_arrays["active_mask"] > 0) & density_state.allowed_mask
    active_values = np.abs(gradient[active])
    scale = float(active_values.max()) if active_values.size else 0.0
    scale = scale if scale > 1.0e-12 else 1.0
    delta = np.zeros_like(density_state.density, dtype=np.float32)
    delta[active] = -float(step_size) * float(move_limit) * gradient[active] / scale
    delta = np.clip(delta, -float(move_limit), float(move_limit))

    density_new = np.clip(density_state.density + delta, density_lower, density_upper).astype(np.float32)
    density_new = np.where(density_state.allowed_mask, density_new, 0.0).astype(np.float32)
    density_delta = (density_new - density_state.density).astype(np.float32)

    update_arrays = {
        "density_old": density_state.density.astype(np.float32, copy=False),
        "density_new": density_new,
        "density_delta": density_delta,
        "objective_density_sensitivity": gradient,
        "active_mask": active.astype(np.uint8),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    update_vti = output_dir / "density_update.vti"
    write_vti_scalar_arrays(density_state.grid, update_arrays, update_vti)

    active_delta = density_delta[active]
    return DensityUpdatePreview(
        design_state_json=density_state.design_state_json,
        sensitivity_vti=sensitivity_vti,
        density_update_vti=update_vti,
        move_limit=float(move_limit),
        step_size=float(step_size),
        density_lower=float(density_lower),
        density_upper=float(density_upper),
        active_cell_count=int(active.sum()),
        density_delta_min=float(active_delta.min()) if active_delta.size else 0.0,
        density_delta_max=float(active_delta.max()) if active_delta.size else 0.0,
        density_delta_l2=float(np.linalg.norm(active_delta.ravel())) if active_delta.size else 0.0,
    )


def read_density_update_vti(path: Path) -> tuple[UniformGrid, dict[str, np.ndarray]]:
    grid, arrays = read_vti_scalar_arrays(path)
    required = {"density_old", "density_new", "density_delta", "objective_density_sensitivity", "active_mask"}
    missing = sorted(required - set(arrays))
    if missing:
        raise ValueError(f"Density update VTI is missing required arrays: {', '.join(missing)}")
    return grid, arrays


def read_vti_scalar_arrays(path: Path) -> tuple[UniformGrid, dict[str, np.ndarray]]:
    dataset = pv.read(path)
    dimensions = tuple(int(value) for value in dataset.dimensions)
    spacing = tuple(float(value) for value in dataset.spacing)
    if len({round(value, 12) for value in spacing}) != 1:
        raise ValueError(f"Expected uniform isotropic VTI spacing in {path}, got {spacing}")
    grid = UniformGrid(
        origin=np.array(dataset.origin, dtype=float),
        spacing=float(spacing[0]),
        shape=dimensions,
    )
    arrays: dict[str, np.ndarray] = {}
    for name in dataset.point_data.keys():
        values = np.asarray(dataset.point_data[name])
        if values.ndim != 1 or values.size != grid.point_count:
            continue
        arrays[name] = values.reshape(grid.shape, order="F")
    return grid, arrays


def write_vti_scalar_arrays(grid: UniformGrid, arrays: dict[str, np.ndarray], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = pv.ImageData()
    image.dimensions = grid.shape
    image.origin = tuple(grid.origin.tolist())
    image.spacing = (grid.spacing, grid.spacing, grid.spacing)
    for name, values in arrays.items():
        if values.shape != grid.shape:
            raise ValueError(f"Array '{name}' has shape {values.shape}, expected {grid.shape}")
        image.point_data[name] = np.ascontiguousarray(values.ravel(order="F"))
    image.save(path)
    return path


def _coordinate_arrays(grid: UniformGrid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs = grid.axis(0)
    ys = grid.axis(1)
    zs = grid.axis(2)
    return np.meshgrid(xs, ys, zs, indexing="ij")


def _efficiency_min_from_project(density_state: DensityStateData) -> float:
    project_path = resolve_design_state_path(
        density_state.design_state_json,
        density_state.state.source_project,
        local_fallback=Path("project.yaml"),
    )
    try:
        return float(load_project(project_path).objective.efficiency_min)
    except Exception:
        return 3.0


def _array_stats(values: np.ndarray) -> dict[str, float]:
    numeric = values.astype(float, copy=False)
    return {
        "min": float(np.min(numeric)) if numeric.size else 0.0,
        "max": float(np.max(numeric)) if numeric.size else 0.0,
        "mean": float(np.mean(numeric)) if numeric.size else 0.0,
        "l2": float(np.linalg.norm(numeric.ravel())) if numeric.size else 0.0,
    }


def _constraint_sensitivity_diagnostics(arrays: dict[str, np.ndarray]) -> dict[str, object]:
    required = {
        "objective_density_sensitivity",
        "downforce_density_sensitivity",
        "drag_density_sensitivity",
        "constraint_sensitivity",
        "active_mask",
    }
    missing = sorted(required - set(arrays))
    if missing:
        return {
            "status": "missing_arrays",
            "usable_for_efficiency_constraint_update": False,
            "missing_arrays": missing,
            "note": "Cannot diagnose constraint sensitivity because required arrays are missing.",
        }

    active = arrays["active_mask"].astype(bool, copy=False)
    active_cell_count = int(active.sum())
    if active_cell_count == 0:
        return {
            "status": "no_active_cells",
            "usable_for_efficiency_constraint_update": False,
            "active_cell_count": 0,
            "missing_arrays": [],
            "note": "No active cells are available for sensitivity diagnostics.",
        }

    objective = arrays["objective_density_sensitivity"].astype(np.float64, copy=False)[active]
    downforce = arrays["downforce_density_sensitivity"].astype(np.float64, copy=False)[active]
    drag = arrays["drag_density_sensitivity"].astype(np.float64, copy=False)[active]
    constraint = arrays["constraint_sensitivity"].astype(np.float64, copy=False)[active]

    objective_l2 = _active_l2(objective)
    downforce_l2 = _active_l2(downforce)
    drag_l2 = _active_l2(drag)
    constraint_l2 = _active_l2(constraint)
    reference_l2 = max(1.0, objective_l2, downforce_l2, constraint_l2)
    drag_is_zero = drag_l2 <= SENSITIVITY_DIAGNOSTIC_EPS * reference_l2
    constraint_is_zero = constraint_l2 <= SENSITIVITY_DIAGNOSTIC_EPS * max(1.0, reference_l2)
    objective_constraint_cosine = _active_cosine(objective, constraint)
    downforce_constraint_cosine = _active_cosine(downforce, constraint)
    drag_constraint_cosine = _active_cosine(drag, constraint)
    collinear_with_objective = (
        objective_constraint_cosine is not None
        and abs(objective_constraint_cosine) >= 0.995
    )

    if constraint_is_zero:
        status = "zero_constraint_sensitivity"
        usable = False
        note = "Constraint sensitivity is numerically zero on active cells."
    elif drag_is_zero:
        status = "degenerate_zero_drag_sensitivity"
        usable = False
        note = (
            "Drag sensitivity is zero, so efficiency-constraint sensitivity is "
            "not independent from the downforce objective."
        )
    else:
        status = "available"
        usable = True
        note = "Constraint sensitivity includes a nonzero drag component on active cells."

    return {
        "status": status,
        "usable_for_efficiency_constraint_update": usable,
        "missing_arrays": [],
        "active_cell_count": active_cell_count,
        "objective_l2_active": objective_l2,
        "downforce_l2_active": downforce_l2,
        "drag_l2_active": drag_l2,
        "constraint_l2_active": constraint_l2,
        "has_independent_drag_sensitivity": not drag_is_zero,
        "constraint_collinear_with_objective": bool(collinear_with_objective),
        "objective_constraint_cosine_active": objective_constraint_cosine,
        "downforce_constraint_cosine_active": downforce_constraint_cosine,
        "drag_constraint_cosine_active": drag_constraint_cosine,
        "note": note,
    }


def _active_l2(values: np.ndarray) -> float:
    return float(np.linalg.norm(values.ravel())) if values.size else 0.0


def _active_cosine(left: np.ndarray, right: np.ndarray) -> float | None:
    left_l2 = _active_l2(left)
    right_l2 = _active_l2(right)
    if left_l2 <= SENSITIVITY_DIAGNOSTIC_EPS or right_l2 <= SENSITIVITY_DIAGNOSTIC_EPS:
        return None
    return float(np.dot(left.ravel(), right.ravel()) / (left_l2 * right_l2))


def _validate_grid_contract(state: DensityDesignState, grid: UniformGrid) -> None:
    expected_shape = tuple(int(value) for value in state.grid["shape"])
    expected_origin = np.array(state.grid["origin"], dtype=float)
    expected_spacing = float(state.grid["spacing"])
    if grid.shape != expected_shape:
        raise ValueError(f"Density VTI shape {grid.shape} does not match design_state grid {expected_shape}")
    if not np.allclose(grid.origin, expected_origin):
        raise ValueError(f"Density VTI origin {grid.origin.tolist()} does not match design_state grid {expected_origin.tolist()}")
    if not np.isclose(grid.spacing, expected_spacing):
        raise ValueError(f"Density VTI spacing {grid.spacing} does not match design_state grid {expected_spacing}")


def _assert_same_grid(left: UniformGrid, right: UniformGrid, left_name: str, right_name: str) -> None:
    if left.shape != right.shape:
        raise ValueError(f"{left_name} grid shape {left.shape} does not match {right_name} grid shape {right.shape}")
    if not np.allclose(left.origin, right.origin):
        raise ValueError(f"{left_name} grid origin does not match {right_name} grid origin")
    if not np.isclose(left.spacing, right.spacing):
        raise ValueError(f"{left_name} grid spacing does not match {right_name} grid spacing")
