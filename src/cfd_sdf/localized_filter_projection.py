"""Deterministic local-density filtering and Heaviside projection.

The G3 design state uses a *local* Cartesian grid in canonical x-fastest
order.  This module is deliberately separate from the older global-grid
filters: it enforces the local active-mask contract and has a mathematically
specified Euclidean transpose for sensitivity back-propagation.

For an active target cell ``i`` the cone filter is

``F_i(rho) = sum_j a_j max(0, r - ||x_i-x_j||) rho_j / sum_j a_j max(...)``.

Here ``a`` is the active-design mask.  Thus fixed, root and forbidden cells
are neither sources nor normalisation terms; all non-active output values are
exactly zero.  The implementation processes monotonic z slabs.  Changing the
slab size only changes memory lifetime, not the order of each cell's floating
point accumulation, so outputs are byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .localized_design_state_manifest import CANONICAL_CELL_ORDER, LocalizedDesignGrid


LOCALIZED_FILTER_CONFIG_KIND = "localized_active_cone_filter"
LOCALIZED_PROJECTION_CONFIG_KIND = "localized_tanh_heaviside_projection"
LOCALIZED_TOPOLOGY_SOLID_DETECTION_KIND = "localized_topology_solid_detection"
LOCALIZED_FILTER_CONFIG_SCHEMA_VERSION = 1
LOCALIZED_PROJECTION_CONFIG_SCHEMA_VERSION = 1
LOCALIZED_TOPOLOGY_SOLID_DETECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LocalizedConeFilterConfig:
    """Active-mask-normalised finite-support cone-filter parameters."""

    radius_m: float = 0.004

    def __post_init__(self) -> None:
        if not np.isfinite(self.radius_m) or self.radius_m <= 0.0:
            raise ValueError("radius_m must be a positive finite value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOCALIZED_FILTER_CONFIG_SCHEMA_VERSION,
            "kind": LOCALIZED_FILTER_CONFIG_KIND,
            "radius_m": float(self.radius_m),
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class LocalizedHeavisideProjectionConfig:
    """Tanh projection parameters; no clipping is performed."""

    beta: float = 2.0
    eta: float = 0.5

    def __post_init__(self) -> None:
        if not np.isfinite(self.beta) or self.beta <= 0.0:
            raise ValueError("beta must be a positive finite value")
        if not np.isfinite(self.eta) or not 0.0 <= self.eta <= 1.0:
            raise ValueError("eta must be a finite value in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOCALIZED_PROJECTION_CONFIG_SCHEMA_VERSION,
            "kind": LOCALIZED_PROJECTION_CONFIG_KIND,
            "beta": float(self.beta),
            "eta": float(self.eta),
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class LocalizedTopologySolidDetectionConfig:
    """Declared, independent topology-solid threshold (not a morphology rule)."""

    threshold: float = 0.5

    def __post_init__(self) -> None:
        if not np.isfinite(self.threshold) or not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be a finite value in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOCALIZED_TOPOLOGY_SOLID_DETECTION_SCHEMA_VERSION,
            "kind": LOCALIZED_TOPOLOGY_SOLID_DETECTION_KIND,
            "threshold": float(self.threshold),
        }


def write_canonical_filter_config(path: str | Path, config: LocalizedConeFilterConfig) -> str:
    """Persist canonical filter JSON and return its byte SHA-256."""

    if not isinstance(config, LocalizedConeFilterConfig):
        raise ValueError("config must be LocalizedConeFilterConfig")
    return _write_canonical_json(path, config.to_dict())


def write_canonical_projection_config(path: str | Path, config: LocalizedHeavisideProjectionConfig) -> str:
    """Persist canonical projection JSON and return its byte SHA-256."""

    if not isinstance(config, LocalizedHeavisideProjectionConfig):
        raise ValueError("config must be LocalizedHeavisideProjectionConfig")
    return _write_canonical_json(path, config.to_dict())


def read_canonical_filter_config(path: str | Path) -> LocalizedConeFilterConfig:
    data = _read_canonical_json(path, LOCALIZED_FILTER_CONFIG_KIND, LOCALIZED_FILTER_CONFIG_SCHEMA_VERSION)
    if set(data) != {"schema_version", "kind", "radius_m"}:
        raise ValueError("filter config has unsupported or missing fields")
    return LocalizedConeFilterConfig(radius_m=_finite_number(data["radius_m"], "radius_m"))


def read_canonical_projection_config(path: str | Path) -> LocalizedHeavisideProjectionConfig:
    data = _read_canonical_json(path, LOCALIZED_PROJECTION_CONFIG_KIND, LOCALIZED_PROJECTION_CONFIG_SCHEMA_VERSION)
    if set(data) != {"schema_version", "kind", "beta", "eta"}:
        raise ValueError("projection config has unsupported or missing fields")
    return LocalizedHeavisideProjectionConfig(
        beta=_finite_number(data["beta"], "beta"), eta=_finite_number(data["eta"], "eta")
    )


def topology_solid_mask(
    rho_projected: np.ndarray, active_mask: np.ndarray, *, config: LocalizedTopologySolidDetectionConfig = LocalizedTopologySolidDetectionConfig()
) -> np.ndarray:
    """Return the declared topology-solid predicate, restricted to active cells."""

    _validate_vector_pair(rho_projected, active_mask, "rho_projected")
    if not isinstance(config, LocalizedTopologySolidDetectionConfig):
        raise ValueError("config must be LocalizedTopologySolidDetectionConfig")
    return np.asarray(active_mask, dtype=np.bool_) & (np.asarray(rho_projected) >= config.threshold)


def apply_localized_cone_filter(
    rho: np.ndarray,
    active_mask: np.ndarray,
    grid: LocalizedDesignGrid,
    *,
    config: LocalizedConeFilterConfig = LocalizedConeFilterConfig(),
    z_slab_size: int = 1,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the exact active-normalised Euclidean cone filter.

    ``rho`` and ``active_mask`` are one-dimensional x-fastest vectors.  A
    supplied ``out`` may be an ``open_memmap`` array, allowing full resolution
    state materialisation without an extra in-memory output vector.
    """

    shape = _validate_grid(grid)
    values, active = _validate_vector_pair(rho, active_mask, "rho", expected_size=int(np.prod(shape)))
    if not isinstance(config, LocalizedConeFilterConfig):
        raise ValueError("config must be LocalizedConeFilterConfig")
    _validate_slab(z_slab_size, shape[2])
    result = _output_array(out, values.size, "out", source=values)
    result.fill(0.0)
    weights = tuple(_cone_offsets(grid.spacing, config.radius_m))
    source = values.reshape((shape[2], shape[1], shape[0]), order="C")
    active3 = active.reshape((shape[2], shape[1], shape[0]), order="C")
    target = result.reshape((shape[2], shape[1], shape[0]), order="C")
    for z0, z1 in _z_slabs(shape[2], z_slab_size):
        numerator = np.zeros((z1 - z0, shape[1], shape[0]), dtype=np.float64)
        denominator = np.zeros_like(numerator)
        for dz, dy, dx, weight in weights:
            target_slices, source_slices = _overlap_slices(shape, z0, z1, dz, dy, dx)
            src_active = active3[source_slices]
            weighted_active = weight * src_active
            numerator[target_slices] += weighted_active * source[source_slices]
            denominator[target_slices] += weighted_active
        active_slab = active3[z0:z1]
        if np.any(active_slab & (denominator <= 0.0)):
            raise ValueError("active filter target has no active cone support")
        np.divide(numerator, denominator, out=target[z0:z1], where=active_slab)
    _validate_state_vector(result, active, "filtered rho")
    return result


def write_localized_cone_filtered_npy(
    rho: np.ndarray,
    active_mask: np.ndarray,
    grid: LocalizedDesignGrid,
    *,
    output_path: str | Path,
    config: LocalizedConeFilterConfig = LocalizedConeFilterConfig(),
    z_slab_size: int = 1,
) -> Path:
    """Write a float64 NPY filtered state by bounded deterministic z slabs."""

    path = Path(output_path)
    if path.suffix.lower() != ".npy":
        raise ValueError("output_path must end in .npy")
    if path.exists():
        raise FileExistsError(f"refusing to overwrite filtered state: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = np.lib.format.open_memmap(path, mode="w+", dtype=np.float64, shape=(grid.cell_count,))
    try:
        apply_localized_cone_filter(
            rho, active_mask, grid, config=config, z_slab_size=z_slab_size, out=writer
        )
        writer.flush()
    finally:
        del writer
    return path


def apply_localized_cone_filter_adjoint(
    gradient_filtered: np.ndarray,
    active_mask: np.ndarray,
    grid: LocalizedDesignGrid,
    *,
    config: LocalizedConeFilterConfig = LocalizedConeFilterConfig(),
    z_slab_size: int = 1,
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the Euclidean transpose ``F.T`` of the normalised filter.

    The normaliser belongs to the target row, so the operator is generally
    not symmetric near an active-mask boundary.
    """

    shape = _validate_grid(grid)
    gradient, active = _validate_gradient_pair(
        gradient_filtered, active_mask, "gradient_filtered", expected_size=int(np.prod(shape))
    )
    if not isinstance(config, LocalizedConeFilterConfig):
        raise ValueError("config must be LocalizedConeFilterConfig")
    _validate_slab(z_slab_size, shape[2])
    result = _output_array(out, gradient.size, "out", source=gradient)
    result.fill(0.0)
    weights = tuple(_cone_offsets(grid.spacing, config.radius_m))
    active3 = active.reshape((shape[2], shape[1], shape[0]), order="C")
    incoming = gradient.reshape((shape[2], shape[1], shape[0]), order="C")
    result3 = result.reshape((shape[2], shape[1], shape[0]), order="C")
    for z0, z1 in _z_slabs(shape[2], z_slab_size):
        denominator = np.zeros((z1 - z0, shape[1], shape[0]), dtype=np.float64)
        for dz, dy, dx, weight in weights:
            target_slices, source_slices = _overlap_slices(shape, z0, z1, dz, dy, dx)
            denominator[target_slices] += weight * active3[source_slices]
        active_slab = active3[z0:z1]
        if np.any(active_slab & (denominator <= 0.0)):
            raise ValueError("active filter target has no active cone support")
        scaled = np.zeros_like(denominator)
        np.divide(incoming[z0:z1], denominator, out=scaled, where=active_slab)
        for dz, dy, dx, weight in weights:
            target_slices, source_slices = _overlap_slices(shape, z0, z1, dz, dy, dx)
            result3[source_slices] += weight * scaled[target_slices] * active3[source_slices]
    _validate_gradient_vector(result, active, "filter adjoint")
    return result


def apply_localized_heaviside_projection(
    rho_filtered: np.ndarray,
    active_mask: np.ndarray,
    *,
    config: LocalizedHeavisideProjectionConfig = LocalizedHeavisideProjectionConfig(),
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the specified tanh projection without clipping."""

    values, active = _validate_vector_pair(rho_filtered, active_mask, "rho_filtered")
    if not isinstance(config, LocalizedHeavisideProjectionConfig):
        raise ValueError("config must be LocalizedHeavisideProjectionConfig")
    result = _output_array(out, values.size, "out", source=values)
    result.fill(0.0)
    denominator = np.tanh(config.beta * config.eta) + np.tanh(config.beta * (1.0 - config.eta))
    result[active] = (
        np.tanh(config.beta * config.eta)
        + np.tanh(config.beta * (values[active] - config.eta))
    ) / denominator
    _validate_state_vector(result, active, "rho_projected")
    return result


def localized_heaviside_projection_derivative(
    rho_filtered: np.ndarray,
    active_mask: np.ndarray,
    *,
    config: LocalizedHeavisideProjectionConfig = LocalizedHeavisideProjectionConfig(),
    out: np.ndarray | None = None,
) -> np.ndarray:
    """Return the exact derivative of :func:`apply_localized_heaviside_projection`."""

    values, active = _validate_vector_pair(rho_filtered, active_mask, "rho_filtered")
    if not isinstance(config, LocalizedHeavisideProjectionConfig):
        raise ValueError("config must be LocalizedHeavisideProjectionConfig")
    result = _output_array(out, values.size, "out", source=values)
    result.fill(0.0)
    denominator = np.tanh(config.beta * config.eta) + np.tanh(config.beta * (1.0 - config.eta))
    tangent = np.tanh(config.beta * (values[active] - config.eta))
    result[active] = config.beta * (1.0 - tangent * tangent) / denominator
    _validate_gradient_vector(result, active, "projection derivative")
    return result


def _validate_grid(grid: LocalizedDesignGrid) -> tuple[int, int, int]:
    if not isinstance(grid, LocalizedDesignGrid) or grid.cell_order != CANONICAL_CELL_ORDER:
        raise ValueError("grid must be canonical LocalizedDesignGrid")
    return grid.cell_shape


def _validate_vector_pair(
    values: np.ndarray, active_mask: np.ndarray, name: str, *, expected_size: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64) or values.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional float64 array")
    if not isinstance(active_mask, np.ndarray) or active_mask.dtype != np.dtype(np.bool_) or active_mask.ndim != 1:
        raise ValueError("active_mask must be a one-dimensional bool array")
    if values.shape != active_mask.shape or (expected_size is not None and values.size != expected_size):
        raise ValueError(f"{name} and active_mask must match the local grid cell count")
    _validate_state_vector(values, active_mask, name)
    return values, active_mask


def _validate_gradient_pair(
    values: np.ndarray, active_mask: np.ndarray, name: str, *, expected_size: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64) or values.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional float64 array")
    if not isinstance(active_mask, np.ndarray) or active_mask.dtype != np.dtype(np.bool_) or active_mask.ndim != 1:
        raise ValueError("active_mask must be a one-dimensional bool array")
    if values.shape != active_mask.shape or (expected_size is not None and values.size != expected_size):
        raise ValueError(f"{name} and active_mask must match the local grid cell count")
    _validate_gradient_vector(values, active_mask, name)
    return values, active_mask


def _validate_state_vector(values: np.ndarray, active: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all() or np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError(f"{name} must contain only finite values in [0, 1]")
    if np.any(values[~active] != 0.0):
        raise ValueError(f"{name} must be exactly zero outside active_mask")


def _validate_gradient_vector(values: np.ndarray, active: np.ndarray, name: str) -> None:
    if not np.isfinite(values).all():
        raise ValueError(f"{name} must contain only finite values")
    if np.any(values[~active] != 0.0):
        raise ValueError(f"{name} must be exactly zero outside active_mask")


def _output_array(out: np.ndarray | None, size: int, name: str, *, source: np.ndarray) -> np.ndarray:
    if out is None:
        return np.zeros(size, dtype=np.float64)
    if not isinstance(out, np.ndarray) or out.dtype != np.dtype(np.float64) or out.shape != (size,):
        raise ValueError(f"{name} must be a float64 vector with the local grid cell count")
    if np.shares_memory(out, source):
        raise ValueError(f"{name} must not share memory with the input vector")
    return out


def _validate_slab(value: int, nz: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("z_slab_size must be a positive integer")
    if nz <= 0:
        raise ValueError("grid z cell count must be positive")


def _cone_offsets(spacing: tuple[float, float, float], radius: float) -> Iterator[tuple[int, int, int, float]]:
    sx, sy, sz = spacing
    mx, my, mz = (int(np.ceil(radius / step)) for step in (sx, sy, sz))
    entries: list[tuple[int, int, int, float]] = []
    for dz in range(-mz, mz + 1):
        for dy in range(-my, my + 1):
            for dx in range(-mx, mx + 1):
                distance = float(np.sqrt((dx * sx) ** 2 + (dy * sy) ** 2 + (dz * sz) ** 2))
                weight = radius - distance
                if weight > 0.0:
                    entries.append((dz, dy, dx, weight))
    # This is explicit even though loops are already ordered: operator summation
    # order is part of the byte-level reproducibility contract.
    return iter(entries)


def _overlap_slices(
    shape: tuple[int, int, int], z0: int, z1: int, dz: int, dy: int, dx: int
) -> tuple[tuple[slice, slice, slice], tuple[slice, slice, slice]]:
    nx, ny, nz = shape
    tz0, tz1 = max(z0, -dz), min(z1, nz - dz)
    ty0, ty1 = max(0, -dy), min(ny, ny - dy)
    tx0, tx1 = max(0, -dx), min(nx, nx - dx)
    # Empty aligned slices are safe and preserve a single offset traversal.
    return (
        (slice(tz0 - z0, tz1 - z0), slice(ty0, ty1), slice(tx0, tx1)),
        (slice(tz0 + dz, tz1 + dz), slice(ty0 + dy, ty1 + dy), slice(tx0 + dx, tx1 + dx)),
    )


def _z_slabs(nz: int, slab: int) -> Iterator[tuple[int, int]]:
    for z0 in range(0, nz, slab):
        yield z0, min(nz, z0 + slab)


def _write_canonical_json(path: str | Path, data: dict[str, Any]) -> str:
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ValueError("canonical config path must end in .json")
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_canonical_json(path: str | Path, kind: str, schema_version: int) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = target.read_bytes()
        data = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read canonical config: {target}") from exc
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    if payload != canonical:
        raise ValueError("config JSON is not canonical")
    if not isinstance(data, dict) or data.get("kind") != kind or data.get("schema_version") != schema_version:
        raise ValueError("config kind or schema_version is invalid")
    return data


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


__all__ = [
    "LOCALIZED_FILTER_CONFIG_KIND", "LOCALIZED_FILTER_CONFIG_SCHEMA_VERSION",
    "LOCALIZED_PROJECTION_CONFIG_KIND", "LOCALIZED_PROJECTION_CONFIG_SCHEMA_VERSION",
    "LOCALIZED_TOPOLOGY_SOLID_DETECTION_KIND", "LOCALIZED_TOPOLOGY_SOLID_DETECTION_SCHEMA_VERSION",
    "LocalizedConeFilterConfig", "LocalizedHeavisideProjectionConfig", "LocalizedTopologySolidDetectionConfig",
    "apply_localized_cone_filter", "apply_localized_cone_filter_adjoint",
    "apply_localized_heaviside_projection", "localized_heaviside_projection_derivative",
    "read_canonical_filter_config", "read_canonical_projection_config", "topology_solid_mask",
    "write_canonical_filter_config", "write_canonical_projection_config", "write_localized_cone_filtered_npy",
]
