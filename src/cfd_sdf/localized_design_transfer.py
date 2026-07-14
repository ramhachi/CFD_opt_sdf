"""Exact, matrix-free transfer from a local design grid to a CFD grid.

This module is the deliberately one-way state map selected for the localized
G3 design-grid path.  A local, fine design density perturbation is averaged
onto an enclosing coarse CFD grid; a CFD derivative is returned with the
Euclidean transpose of exactly that map.  It never attempts to reconstruct a
fine design state from a CFD ``alpha`` field.

For CFD cell ``s`` and design cell ``t`` the map is

``E[s, t] = volume(intersection(s, t)) / volume(s)``.

``E`` is separable for axis-aligned uniform Cartesian grids.  We therefore
store just three small per-axis overlap tables instead of an ``N_cfd x
N_design`` matrix.  The public chunk iterator lets a caller consume the
transpose result without allocating a full localized design vector in
addition to its own state storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import numpy as np

from .openfoam_grid_transfer import CANONICAL_CELL_ORDER


_COVERAGE_TOLERANCE = 1.0e-12


@dataclass(frozen=True)
class LocalizedTransferChunkPlan:
    """A conservative workspace plan for one target-z slab.

    The plan excludes the caller-owned input and output vectors.  In
    particular, :meth:`LocalizedDesignToCfdTransfer.iter_adjoint_design_chunks`
    can be used to avoid allocating the full design-gradient output.
    """

    target_z_chunk_size: int
    estimated_workspace_bytes_per_target_z: int
    max_workspace_bytes: int


@dataclass(frozen=True)
class LocalizedTransferDiagnostics:
    """Coverage proof for a local design box embedded in a CFD grid."""

    design_cell_coverage_min: float
    design_cell_coverage_max: float
    cfd_row_coverage_min: float
    cfd_row_coverage_max: float
    cfd_partial_row_count: int
    cfd_uncovered_row_count: int
    cfd_row_coverage: np.ndarray


@dataclass(frozen=True)
class _GridGeometry:
    """Validated geometry extracted from a UniformCartesianCellGrid-like object."""

    origin: np.ndarray
    spacing: np.ndarray
    cell_shape: tuple[int, int, int]

    @property
    def lower(self) -> np.ndarray:
        return self.origin

    @property
    def upper(self) -> np.ndarray:
        return self.origin + self.spacing * np.asarray(self.cell_shape, dtype=np.float64)

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.cell_shape, dtype=np.int64))

    @property
    def cell_volume(self) -> float:
        return float(np.prod(self.spacing, dtype=np.float64))


@dataclass(frozen=True)
class LocalizedDesignToCfdTransfer:
    """Separable exact volume-average transfer from local design to CFD cells.

    ``design_grid`` must be geometrically contained in ``cfd_grid``.  CFD
    cells outside the local design box intentionally receive zero perturbation;
    cells crossed by its boundary have a valid row sum strictly between zero
    and one.  This is necessary for a local design box and is reported by
    :attr:`diagnostics`, rather than being silently treated as a full-domain
    transfer.
    """

    cfd_grid: Any
    design_grid: Any
    _cfd: _GridGeometry
    _design: _GridGeometry
    axis_weights: tuple[np.ndarray, np.ndarray, np.ndarray]
    diagnostics: LocalizedTransferDiagnostics

    @classmethod
    def build(
        cls,
        *,
        cfd_grid: Any,
        design_grid: Any,
    ) -> "LocalizedDesignToCfdTransfer":
        """Build and validate the exact design-to-CFD overlap operator.

        Objects are accepted structurally so the localized design-grid
        contract need not subclass the existing OpenFOAM grid type.  The
        required attributes are ``origin``, ``spacing``, ``cell_shape`` and
        canonical ``cell_order``; optional ``axes`` must be the identity.
        """

        cfd = _grid_geometry(cfd_grid, "cfd_grid")
        design = _grid_geometry(design_grid, "design_grid")
        _require_containment(cfd, design)
        weights = tuple(
            _axis_overlap_weights(
                cfd.origin[axis],
                cfd.spacing[axis],
                cfd.cell_shape[axis],
                design.origin[axis],
                design.spacing[axis],
                design.cell_shape[axis],
            )
            for axis in range(3)
        )
        diagnostics = _diagnostics(cfd, design, weights)
        return cls(
            cfd_grid=cfd_grid,
            design_grid=design_grid,
            _cfd=cfd,
            _design=design,
            axis_weights=weights,
            diagnostics=diagnostics,
        )

    @property
    def cfd_cell_count(self) -> int:
        return self._cfd.cell_count

    @property
    def design_cell_count(self) -> int:
        return self._design.cell_count

    def plan_target_z_chunks(self, max_workspace_bytes: int) -> LocalizedTransferChunkPlan:
        """Return a bounded-workspace target-z chunk plan.

        The formula covers the simultaneously live separable intermediates in
        both forward and transpose application.  It is intentionally
        conservative and avoids any dependence on the full design-cell count.
        """

        if not isinstance(max_workspace_bytes, (int, np.integer)) or max_workspace_bytes <= 0:
            raise ValueError("max_workspace_bytes must be a positive integer")
        sx, sy, _sz = self._cfd.cell_shape
        tx, ty, tz = self._design.cell_shape
        itemsize = np.dtype(np.float64).itemsize
        forward_per_z = itemsize * (ty * sx + sy * sx)
        adjoint_per_z = itemsize * (sy * sx + ty * sx + ty * tx)
        per_z = int(max(forward_per_z, adjoint_per_z))
        chunk = int(max_workspace_bytes) // per_z
        if chunk < 1:
            raise ValueError(
                "max_workspace_bytes is too small for one localized transfer target-z slab; "
                f"requires at least {per_z} bytes"
            )
        return LocalizedTransferChunkPlan(
            target_z_chunk_size=min(tz, chunk),
            estimated_workspace_bytes_per_target_z=per_z,
            max_workspace_bytes=int(max_workspace_bytes),
        )

    def apply_forward(
        self,
        design_delta_rho: np.ndarray | Sequence[float],
        *,
        target_z_chunk_size: int | None = None,
    ) -> np.ndarray:
        """Return ``E @ design_delta_rho`` as a float64 x-fastest CFD vector."""

        design_values = _finite_values(design_delta_rho, self.design_cell_count, "design_delta_rho")
        chunk = _target_z_chunk_size(target_z_chunk_size, self._design.cell_shape[2])
        tx, ty, tz = self._design.cell_shape
        sx, sy, sz = self._cfd.cell_shape
        wx, wy, wz = self.axis_weights
        design_zyx = design_values.reshape((tz, ty, tx), order="C")
        result = np.zeros((sz, sy, sx), dtype=np.float64)
        for start in range(0, tz, chunk):
            stop = min(tz, start + chunk)
            x_reduced = np.einsum("it,zyt->zyi", wx, design_zyx[start:stop], optimize=True)
            xy_reduced = np.einsum("jt,zti->zji", wy, x_reduced, optimize=True)
            result += np.einsum("kz,zji->kji", wz[:, start:stop], xy_reduced, optimize=True)
        return result.reshape(-1, order="C")

    def iter_adjoint_design_chunks(
        self,
        cfd_gradient: np.ndarray | Sequence[float],
        *,
        target_z_chunk_size: int | None = None,
    ) -> Iterator[tuple[slice, np.ndarray]]:
        """Yield ``E.T @ cfd_gradient`` in contiguous target-z slabs.

        Each yielded vector is x-fastest within the returned target-z slice.
        This is the preferred API for a localized design state too large to
        duplicate as one 87-million-cell gradient allocation.
        """

        source_values = _finite_values(cfd_gradient, self.cfd_cell_count, "cfd_gradient")
        chunk = _target_z_chunk_size(target_z_chunk_size, self._design.cell_shape[2])
        tx, ty, tz = self._design.cell_shape
        sx, sy, sz = self._cfd.cell_shape
        del sz  # dimensions are checked by reshape below; retain names matching the map.
        wx, wy, wz = self.axis_weights
        source_zyx = source_values.reshape(self._cfd.cell_shape[::-1], order="C")
        for start in range(0, tz, chunk):
            stop = min(tz, start + chunk)
            z_expanded = np.einsum("zk,kji->zji", wz[:, start:stop].T, source_zyx, optimize=True)
            zy_expanded = np.einsum("tj,zji->zti", wy.T, z_expanded, optimize=True)
            design_chunk = np.einsum("ti,zyi->zyt", wx.T, zy_expanded, optimize=True)
            # ``design_chunk`` is (z, y, x), i.e. canonical x-fastest C order.
            yield slice(start, stop), np.ascontiguousarray(design_chunk.reshape(-1, order="C"))

    def apply_adjoint(
        self,
        cfd_gradient: np.ndarray | Sequence[float],
        *,
        target_z_chunk_size: int | None = None,
    ) -> np.ndarray:
        """Return the Euclidean-coordinate adjoint ``E.T @ cfd_gradient``.

        Use :meth:`iter_adjoint_design_chunks` when allocating the complete
        design vector is inappropriate for the caller's memory budget.
        """

        tx, ty, tz = self._design.cell_shape
        result = np.empty((tz, ty, tx), dtype=np.float64)
        for target_z, values in self.iter_adjoint_design_chunks(
            cfd_gradient, target_z_chunk_size=target_z_chunk_size
        ):
            result[target_z] = values.reshape((target_z.stop - target_z.start, ty, tx), order="C")
        return result.reshape(-1, order="C")


def _grid_geometry(grid: Any, name: str) -> _GridGeometry:
    if grid is None:
        raise ValueError(f"{name} must be a UniformCartesianCellGrid-like object")
    for attribute in ("origin", "spacing", "cell_shape", "cell_order"):
        if not hasattr(grid, attribute):
            raise ValueError(f"{name} must provide {attribute!r}")
    if getattr(grid, "cell_order") != CANONICAL_CELL_ORDER:
        raise ValueError(f"{name}.cell_order must be {CANONICAL_CELL_ORDER!r}")
    origin = _finite_vector(getattr(grid, "origin"), f"{name}.origin")
    spacing = _finite_vector(getattr(grid, "spacing"), f"{name}.spacing")
    if np.any(spacing <= 0.0):
        raise ValueError(f"{name}.spacing must contain three positive finite values")
    raw_shape = np.asarray(getattr(grid, "cell_shape"))
    if raw_shape.shape != (3,) or not np.issubdtype(raw_shape.dtype, np.integer):
        raise ValueError(f"{name}.cell_shape must be an integer vector with shape (3,)")
    shape = tuple(int(value) for value in raw_shape)
    if any(value <= 0 for value in shape):
        raise ValueError(f"{name}.cell_shape must contain three positive integers")
    axes = getattr(grid, "axes", None)
    if axes is not None:
        axes_array = np.asarray(axes)
        if axes_array.shape != (3, 3) or not np.issubdtype(axes_array.dtype, np.number):
            raise ValueError(f"{name}.axes must be a numeric 3x3 matrix")
        axes_array = np.asarray(axes_array, dtype=np.float64)
        if not np.isfinite(axes_array).all() or not np.array_equal(axes_array, np.eye(3)):
            raise ValueError(f"{name} must be axis-aligned with identity axes")
    return _GridGeometry(origin=origin, spacing=spacing, cell_shape=shape)


def _finite_vector(values: Any, name: str) -> np.ndarray:
    try:
        array = np.asarray(values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric vector with shape (3,)") from exc
    if array.shape != (3,) or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a numeric vector with shape (3,)")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _require_containment(cfd: _GridGeometry, design: _GridGeometry) -> None:
    lower_outside = design.lower < cfd.lower - _COVERAGE_TOLERANCE
    upper_outside = design.upper > cfd.upper + _COVERAGE_TOLERANCE
    if np.any(lower_outside) or np.any(upper_outside):
        raise ValueError(
            "design_grid bounds must be contained in cfd_grid bounds; "
            f"design=[{design.lower.tolist()}, {design.upper.tolist()}], "
            f"cfd=[{cfd.lower.tolist()}, {cfd.upper.tolist()}]"
        )


def _axis_overlap_weights(
    source_origin: float,
    source_spacing: float,
    source_count: int,
    target_origin: float,
    target_spacing: float,
    target_count: int,
) -> np.ndarray:
    source_lower = source_origin + source_spacing * np.arange(source_count, dtype=np.float64)
    source_upper = source_lower + source_spacing
    target_lower = target_origin + target_spacing * np.arange(target_count, dtype=np.float64)
    target_upper = target_lower + target_spacing
    lengths = np.maximum(
        0.0,
        np.minimum(source_upper[:, None], target_upper[None, :])
        - np.maximum(source_lower[:, None], target_lower[None, :]),
    )
    return np.asarray(lengths / source_spacing, dtype=np.float64)


def _diagnostics(
    cfd: _GridGeometry,
    design: _GridGeometry,
    weights: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> LocalizedTransferDiagnostics:
    cfd_axis_coverage = tuple(np.sum(weight, axis=1, dtype=np.float64) for weight in weights)
    design_axis_coverage = tuple(
        np.sum(weight, axis=0, dtype=np.float64) * cfd.spacing[axis] / design.spacing[axis]
        for axis, weight in enumerate(weights)
    )
    for axis, coverage in enumerate(design_axis_coverage):
        if not np.allclose(coverage, 1.0, rtol=0.0, atol=_COVERAGE_TOLERANCE):
            index = int(np.flatnonzero(np.abs(coverage - 1.0) > _COVERAGE_TOLERANCE)[0])
            raise ValueError(
                "every design cell must be fully represented by the enclosing CFD grid; "
                f"axis {axis} cell {index} has coverage {coverage[index]:.17g}"
            )
    # The result layout is z, y, x so ravel(C) is x-fastest.
    row_coverage = np.einsum(
        "k,j,i->kji", cfd_axis_coverage[2], cfd_axis_coverage[1], cfd_axis_coverage[0], optimize=True
    ).reshape(-1, order="C")
    if not np.isfinite(row_coverage).all() or np.any(row_coverage < -_COVERAGE_TOLERANCE) or np.any(
        row_coverage > 1.0 + _COVERAGE_TOLERANCE
    ):
        raise ValueError("CFD overlap row coverage must lie in [0, 1]")
    row_coverage = np.clip(row_coverage, 0.0, 1.0)
    row_coverage.setflags(write=False)
    partial = (row_coverage > _COVERAGE_TOLERANCE) & (row_coverage < 1.0 - _COVERAGE_TOLERANCE)
    uncovered = row_coverage <= _COVERAGE_TOLERANCE
    return LocalizedTransferDiagnostics(
        design_cell_coverage_min=float(min(float(np.min(values)) for values in design_axis_coverage)),
        design_cell_coverage_max=float(max(float(np.max(values)) for values in design_axis_coverage)),
        cfd_row_coverage_min=float(np.min(row_coverage)),
        cfd_row_coverage_max=float(np.max(row_coverage)),
        cfd_partial_row_count=int(np.count_nonzero(partial)),
        cfd_uncovered_row_count=int(np.count_nonzero(uncovered)),
        cfd_row_coverage=row_coverage,
    )


def _finite_values(values: np.ndarray | Sequence[float], count: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (count,) or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a numeric vector with shape ({count},)")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _target_z_chunk_size(value: int | None, target_z_count: int) -> int:
    if value is None:
        return target_z_count
    if not isinstance(value, (int, np.integer)) or not 1 <= int(value) <= target_z_count:
        raise ValueError(f"target_z_chunk_size must be an integer in [1, {target_z_count}]")
    return int(value)


__all__ = [
    "LocalizedDesignToCfdTransfer",
    "LocalizedTransferChunkPlan",
    "LocalizedTransferDiagnostics",
]
