from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion, gaussian_filter
from scipy.spatial import cKDTree

from .config import load_project
from .design_state import resolve_design_state_path
from .grid import UniformGrid
from .sensitivity import (
    DensityStateData,
    create_sensitivity_summary,
    load_density_state,
    read_vti_scalar_arrays,
    write_vti_scalar_arrays,
)


SURFACE_SENSITIVITY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SurfaceSensitivityCloud:
    points: np.ndarray
    objective: np.ndarray
    downforce: np.ndarray
    drag: np.ndarray
    source_path: Path | None


@dataclass(frozen=True)
class ProjectionArtifacts:
    design_state_json: Path
    surface_sensitivity_csv: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    projection_diagnostics_vti: Path
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "design_state_json",
            "surface_sensitivity_csv",
            "sensitivity_vti",
            "sensitivity_summary_json",
            "projection_diagnostics_vti",
        ):
            data[key] = str(data[key])
        return data


def write_mock_surface_sensitivity_csv(
    design_state_json: Path,
    *,
    output_csv: Path,
    max_points: int = 2000,
) -> Path:
    density_state = load_density_state(design_state_json)
    boundary = density_surface_mask(density_state.density, density_state.allowed_mask)
    indices = np.argwhere(boundary)
    if indices.size == 0:
        indices = np.argwhere(density_state.allowed_mask)
    if indices.size == 0:
        raise ValueError("No active or boundary cells are available for mock surface sensitivity.")
    if len(indices) > max_points:
        stride = max(1, len(indices) // max_points)
        indices = indices[::stride][:max_points]

    xs = density_state.grid.axis(0)
    ys = density_state.grid.axis(1)
    zs = density_state.grid.axis(2)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "x",
            "y",
            "z",
            "objective_surface_sensitivity",
            "downforce_surface_sensitivity",
            "drag_surface_sensitivity",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for i, j, k in indices:
            x = float(xs[i])
            y = float(ys[j])
            z = float(zs[k])
            weight = _mock_surface_weight(density_state.grid, x, y, z)
            downforce = weight
            drag = 0.20 * weight
            objective = -downforce
            writer.writerow(
                {
                    "x": x,
                    "y": y,
                    "z": z,
                    "objective_surface_sensitivity": objective,
                    "downforce_surface_sensitivity": downforce,
                    "drag_surface_sensitivity": drag,
                }
            )
    return output_csv


def project_surface_sensitivity_to_density(
    design_state_json: Path,
    surface_sensitivity_csv: Path,
    *,
    output_dir: Path | None = None,
    projection_radius_m: float | None = None,
    smoothing_radius_cells: float = 1.0,
    max_neighbors: int = 8,
) -> ProjectionArtifacts:
    density_state = load_density_state(design_state_json)
    cloud = read_surface_sensitivity_csv(surface_sensitivity_csv)
    output_dir = output_dir or density_state.design_state_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    projection_radius_m = projection_radius_m or (2.5 * density_state.grid.spacing)

    arrays, diagnostics = project_surface_cloud_arrays(
        density_state=density_state,
        cloud=cloud,
        projection_radius_m=projection_radius_m,
        smoothing_radius_cells=smoothing_radius_cells,
        max_neighbors=max_neighbors,
    )
    sensitivity_vti = output_dir / "sensitivity.vti"
    diagnostics_vti = output_dir / "projection_diagnostics.vti"
    write_vti_scalar_arrays(density_state.grid, arrays, sensitivity_vti)
    write_vti_scalar_arrays(density_state.grid, diagnostics, diagnostics_vti)

    summary = create_sensitivity_summary(
        density_state=density_state,
        sensitivity_vti=sensitivity_vti,
        arrays=arrays,
        backend="surface-projection",
        backend_version="1",
        projection_method="kd-tree-gaussian-surface-to-density",
    )
    summary.update(
        {
            "surface_sensitivity_schema_version": SURFACE_SENSITIVITY_SCHEMA_VERSION,
            "surface_sensitivity_csv": str(surface_sensitivity_csv),
            "projection_radius_m": float(projection_radius_m),
            "smoothing_radius_cells": float(smoothing_radius_cells),
            "surface_point_count": int(len(cloud.points)),
            "projected_active_cell_count": int(arrays["active_mask"].sum()),
            "projection_diagnostics_vti": str(diagnostics_vti),
        }
    )
    summary_path = output_dir / "sensitivity_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return ProjectionArtifacts(
        design_state_json=density_state.design_state_json,
        surface_sensitivity_csv=surface_sensitivity_csv,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=summary_path,
        projection_diagnostics_vti=diagnostics_vti,
        summary=summary,
    )


def project_surface_cloud_arrays(
    *,
    density_state: DensityStateData,
    cloud: SurfaceSensitivityCloud,
    projection_radius_m: float,
    smoothing_radius_cells: float,
    max_neighbors: int,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    if projection_radius_m <= 0.0:
        raise ValueError("projection_radius_m must be > 0")
    if max_neighbors < 1:
        raise ValueError("max_neighbors must be >= 1")
    tree = cKDTree(cloud.points)
    flat_points = density_state.grid.points_flat()
    allowed_flat = density_state.allowed_mask.ravel(order="C")
    query_points = flat_points[allowed_flat]
    if query_points.size == 0:
        raise ValueError("No allowed grid points are available for projection.")

    k = min(max_neighbors, len(cloud.points))
    distances, indices = tree.query(query_points, k=k, distance_upper_bound=projection_radius_m)
    if k == 1:
        distances = distances[:, None]
        indices = indices[:, None]
    finite = np.isfinite(distances) & (indices < len(cloud.points))
    sigma = max(projection_radius_m / 2.0, 1.0e-12)
    weights = np.where(finite, np.exp(-0.5 * (distances / sigma) ** 2), 0.0)
    weight_sum = weights.sum(axis=1)
    projected = weight_sum > 1.0e-12

    objective_values = _weighted_average(cloud.objective, indices, weights, weight_sum)
    downforce_values = _weighted_average(cloud.downforce, indices, weights, weight_sum)
    drag_values = _weighted_average(cloud.drag, indices, weights, weight_sum)

    shape = density_state.grid.shape
    objective = np.zeros(np.prod(shape), dtype=np.float32)
    downforce = np.zeros(np.prod(shape), dtype=np.float32)
    drag = np.zeros(np.prod(shape), dtype=np.float32)
    active = np.zeros(np.prod(shape), dtype=np.uint8)
    distance_flat = np.full(np.prod(shape), np.nan, dtype=np.float32)
    weight_flat = np.zeros(np.prod(shape), dtype=np.float32)

    allowed_indices = np.flatnonzero(allowed_flat)
    target_indices = allowed_indices[projected]
    objective[target_indices] = objective_values[projected].astype(np.float32)
    downforce[target_indices] = downforce_values[projected].astype(np.float32)
    drag[target_indices] = drag_values[projected].astype(np.float32)
    active[target_indices] = 1
    distance_flat[target_indices] = np.min(np.where(finite[projected], distances[projected], np.inf), axis=1).astype(np.float32)
    weight_flat[target_indices] = weight_sum[projected].astype(np.float32)

    objective = objective.reshape(shape, order="C")
    downforce = downforce.reshape(shape, order="C")
    drag = drag.reshape(shape, order="C")
    active_mask = active.reshape(shape, order="C")
    projection_distance = distance_flat.reshape(shape, order="C")
    projection_weight_sum = weight_flat.reshape(shape, order="C")
    if smoothing_radius_cells > 0.0:
        objective = _smooth_projected_array(objective, active_mask, smoothing_radius_cells)
        downforce = _smooth_projected_array(downforce, active_mask, smoothing_radius_cells)
        drag = _smooth_projected_array(drag, active_mask, smoothing_radius_cells)

    efficiency_min = _efficiency_min_from_project(density_state)
    constraint = efficiency_min * drag - downforce
    arrays = {
        "objective_density_sensitivity": objective.astype(np.float32),
        "downforce_density_sensitivity": downforce.astype(np.float32),
        "drag_density_sensitivity": drag.astype(np.float32),
        "constraint_sensitivity": (constraint * active_mask).astype(np.float32),
        "active_mask": active_mask.astype(np.uint8),
    }
    diagnostics = {
        "active_mask": active_mask.astype(np.uint8),
        "projection_distance": projection_distance,
        "projection_weight_sum": projection_weight_sum,
        "objective_density_sensitivity": arrays["objective_density_sensitivity"],
    }
    return arrays, diagnostics


def read_surface_sensitivity_csv(path: Path) -> SurfaceSensitivityCloud:
    points: list[tuple[float, float, float]] = []
    objective: list[float] = []
    downforce: list[float] = []
    drag: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"x", "y", "z", "objective_surface_sensitivity"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Surface sensitivity CSV is missing required columns: {', '.join(sorted(missing))}")
        for row in reader:
            points.append((float(row["x"]), float(row["y"]), float(row["z"])))
            objective_value = float(row["objective_surface_sensitivity"])
            objective.append(objective_value)
            downforce.append(float(row.get("downforce_surface_sensitivity") or -objective_value))
            drag.append(float(row.get("drag_surface_sensitivity") or 0.0))
    if not points:
        raise ValueError(f"No surface sensitivity rows found in {path}")
    return SurfaceSensitivityCloud(
        points=np.array(points, dtype=np.float64),
        objective=np.array(objective, dtype=np.float64),
        downforce=np.array(downforce, dtype=np.float64),
        drag=np.array(drag, dtype=np.float64),
        source_path=path,
    )


def density_surface_mask(density: np.ndarray, allowed_mask: np.ndarray, iso_value: float = 0.5) -> np.ndarray:
    solid = (density >= iso_value) & allowed_mask
    if not solid.any():
        return allowed_mask & (density > 0.0)
    eroded = binary_erosion(solid, structure=np.ones((3, 3, 3), dtype=bool), border_value=0)
    return solid & ~eroded


def _weighted_average(values: np.ndarray, indices: np.ndarray, weights: np.ndarray, weight_sum: np.ndarray) -> np.ndarray:
    safe_indices = np.where(indices < len(values), indices, 0)
    gathered = values[safe_indices]
    numerator = (gathered * weights).sum(axis=1)
    return np.divide(numerator, weight_sum, out=np.zeros_like(numerator), where=weight_sum > 1.0e-12)


def _smooth_projected_array(values: np.ndarray, active_mask: np.ndarray, radius_cells: float) -> np.ndarray:
    active = active_mask.astype(np.float32)
    smoothed = gaussian_filter(values * active, sigma=float(radius_cells), mode="nearest")
    normalizer = gaussian_filter(active, sigma=float(radius_cells), mode="nearest")
    return np.divide(smoothed, normalizer, out=np.zeros_like(smoothed), where=normalizer > 1.0e-6).astype(np.float32)


def _mock_surface_weight(grid: UniformGrid, x: float, y: float, z: float) -> float:
    bounds = grid.bounds
    x_span = max(float(bounds[1, 0] - bounds[0, 0]), 1.0e-12)
    y_span = max(float(bounds[1, 1] - bounds[0, 1]), 1.0e-12)
    z_span = max(float(bounds[1, 2] - bounds[0, 2]), 1.0e-12)
    x_norm = (x - bounds[0, 0]) / x_span
    y_center = 0.5 * (bounds[0, 1] + bounds[1, 1])
    span_weight = np.clip(1.0 - abs(y - y_center) / (0.5 * y_span), 0.15, 1.0)
    height_weight = 0.45 + 0.55 * np.clip((z - bounds[0, 2]) / z_span, 0.0, 1.0)
    chord_weight = 0.55 + 0.45 * np.exp(-((x_norm - 0.48) / 0.28) ** 2)
    return float(0.010 * span_weight * height_weight * chord_weight)


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
