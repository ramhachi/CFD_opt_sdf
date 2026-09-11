"""Fail-closed transfer between axis-aligned uniform Cartesian cell grids.

The matrix built here maps a *canonical target* density field onto a source
OpenFOAM cell grid.  Its only supported geometry is two axis-aligned, uniform
Cartesian grids, with cells ordered ``x-fastest`` (``i + nx * (j + ny * k)``).
This intentionally excludes arbitrary polyhedral meshes: such a mapping would
need separately persisted conservative interpolation semantics.

For source cell ``s`` and target cell ``t`` the state map is

``source[s] = sum_t P[s, t] * target[t]``

where ``P[s, t] = volume(overlap(s, t)) / volume(source[s])``.  The builder
rejects a partial active-domain overlap, so every active row sums to exactly
one (within a strict floating-point tolerance).

``transfer_gradient_to_target`` uses the Euclidean-coordinate adjoint of that
state map: ``g_target = P.T @ g_source``.  Here gradients mean the discrete
derivative coefficients in ``dJ = g.dot(dstate)``; no cell-volume factor is
part of that dot product.  Physical volumes are used *only* to form the state
average above.  If callers instead store an L2 gradient density under a
volume-weighted inner product, they must apply the corresponding diagonal
volume factors themselves; silently treating one convention as the other is
not permitted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Sequence

import numpy as np
from scipy.sparse import csr_array


CANONICAL_CELL_ORDER = "x-fastest"
_GRID_SCHEMA_VERSION = 1
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_COVERAGE_RTOL = 1.0e-12
_COVERAGE_ATOL = 1.0e-12
OPENFOAM_GLOBAL_CELL_LABEL_ORDER = "openfoam-global-cell-label-ascending"


@dataclass(frozen=True)
class UniformCartesianCellGrid:
    """A uniform cell-centred Cartesian grid with canonical cell ordering.

    ``origin`` is the lower corner of cell ``(0, 0, 0)``.  ``spacing`` may be
    anisotropic across axes but is constant along each axis.  ``axes`` is
    accepted solely to make an attempted rotated-grid binding explicit: it
    must be the identity matrix, otherwise construction fails.
    """

    origin: Sequence[float]
    spacing: Sequence[float]
    cell_shape: Sequence[int]
    cell_order: str = CANONICAL_CELL_ORDER
    axes: Sequence[Sequence[float]] | None = None

    def __post_init__(self) -> None:
        origin = _finite_vector(self.origin, "origin")
        spacing = _finite_vector(self.spacing, "spacing")
        if np.any(spacing <= 0.0):
            raise ValueError("spacing must contain three positive finite values")
        shape = _cell_shape(self.cell_shape)
        if self.cell_order != CANONICAL_CELL_ORDER:
            raise ValueError(
                f"cell_order must be {CANONICAL_CELL_ORDER!r}; got {self.cell_order!r}"
            )
        axes = np.eye(3, dtype=np.float64) if self.axes is None else np.asarray(self.axes)
        if axes.shape != (3, 3) or not np.issubdtype(axes.dtype, np.number):
            raise ValueError("axes must be a numeric 3x3 matrix")
        axes = np.asarray(axes, dtype=np.float64)
        if not np.isfinite(axes).all():
            raise ValueError("axes must contain only finite values")
        if not np.allclose(axes, np.eye(3), rtol=0.0, atol=0.0):
            raise ValueError("only identity axes are supported; non-axis-aligned grids are refused")
        object.__setattr__(self, "origin", tuple(float(value) for value in origin))
        object.__setattr__(self, "spacing", tuple(float(value) for value in spacing))
        object.__setattr__(self, "cell_shape", shape)
        object.__setattr__(self, "axes", tuple(tuple(float(value) for value in row) for row in axes))

    @property
    def cell_count(self) -> int:
        return int(np.prod(self.cell_shape, dtype=np.int64))

    @property
    def cell_volume(self) -> float:
        return float(np.prod(self.spacing, dtype=np.float64))

    @property
    def lower(self) -> np.ndarray:
        return np.asarray(self.origin, dtype=np.float64)

    @property
    def upper(self) -> np.ndarray:
        return self.lower + np.asarray(self.spacing, dtype=np.float64) * np.asarray(
            self.cell_shape, dtype=np.float64
        )

    @property
    def sha256(self) -> str:
        """Hash the complete geometry and canonical-order contract."""

        payload = {
            "schema_version": _GRID_SCHEMA_VERSION,
            "cell_order": CANONICAL_CELL_ORDER,
            "origin": list(self.origin),
            "spacing": list(self.spacing),
            "cell_shape": list(self.cell_shape),
            "axes": [list(row) for row in self.axes],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def flat_index(self, x: int, y: int, z: int) -> int:
        """Return the canonical x-fastest flat index, rejecting invalid cells."""

        nx, ny, nz = self.cell_shape
        if not (0 <= x < nx and 0 <= y < ny and 0 <= z < nz):
            raise ValueError(f"cell index {(x, y, z)!r} is outside cell_shape {self.cell_shape!r}")
        return int(x + nx * (y + ny * z))


@dataclass(frozen=True)
class OpenFoamCellOrderMapping:
    """Permutation from source x-fastest indices to OpenFOAM global labels."""

    path: Path
    global_cell_labels_by_xfastest: np.ndarray
    file_sha256: str
    array_sha256: str

    def to_dict(self) -> dict[str, object]:
        values = self.global_cell_labels_by_xfastest
        return {
            "path": str(self.path),
            "sha256": self.file_sha256,
            "array_sha256": self.array_sha256,
            "mapping": "global_label = values[x_fastest_index]",
            "source_order": CANONICAL_CELL_ORDER,
            "field_order": OPENFOAM_GLOBAL_CELL_LABEL_ORDER,
            "cell_count": int(values.size),
            "identity": bool(np.array_equal(values, np.arange(values.size))),
        }


def load_openfoam_cell_order_mapping(
    path: str | Path,
    *,
    cell_count: int,
) -> OpenFoamCellOrderMapping:
    """Load an exact NPY permutation without assuming blockMesh numbering."""

    mapping_path = Path(path).resolve()
    try:
        raw_bytes = mapping_path.read_bytes()
        values = np.load(mapping_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"source global-label mapping cannot be read: {mapping_path}"
        ) from exc
    if values.shape != (cell_count,) or values.dtype.kind not in "iu":
        raise ValueError(
            "source_global_cell_labels_by_xfastest must be a one-dimensional "
            f"integer vector with shape ({cell_count},)"
        )
    mapping = np.asarray(values, dtype=np.int64)
    if not np.array_equal(np.sort(mapping), np.arange(cell_count, dtype=np.int64)):
        raise ValueError(
            "source_global_cell_labels_by_xfastest must be a permutation of global labels"
        )
    mapping.setflags(write=False)
    return OpenFoamCellOrderMapping(
        path=mapping_path,
        global_cell_labels_by_xfastest=mapping,
        file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        array_sha256=_array_sha256(mapping),
    )


@dataclass(frozen=True)
class ExactCartesianOverlapTransfer:
    """A provenance-bound target-to-source state transfer and its Euclidean dual."""

    source_grid: UniformCartesianCellGrid
    target_grid: UniformCartesianCellGrid
    matrix: csr_array
    source_active_mask: np.ndarray
    target_active_mask: np.ndarray
    source_grid_sha256: str
    target_grid_sha256: str
    source_active_mask_sha256: str
    target_active_mask_sha256: str

    @classmethod
    def build(
        cls,
        *,
        source_grid: UniformCartesianCellGrid,
        target_grid: UniformCartesianCellGrid,
        source_active_mask: np.ndarray | Sequence[bool] | None = None,
        target_active_mask: np.ndarray | Sequence[bool] | None = None,
        expected_source_grid_sha256: str | None = None,
        expected_target_grid_sha256: str | None = None,
    ) -> "ExactCartesianOverlapTransfer":
        """Build ``P`` after proving complete active-domain coverage.

        Source and target masks select the physical domains to bind.  Both
        selected domains must cover each other exactly; a missing target sliver
        or an unrepresented active target cell raises instead of dropping a
        state or sensitivity contribution.
        """

        if not isinstance(source_grid, UniformCartesianCellGrid):
            raise ValueError("source_grid must be UniformCartesianCellGrid")
        if not isinstance(target_grid, UniformCartesianCellGrid):
            raise ValueError("target_grid must be UniformCartesianCellGrid")
        _validate_expected_hash(
            expected_source_grid_sha256, source_grid.sha256, "expected_source_grid_sha256"
        )
        _validate_expected_hash(
            expected_target_grid_sha256, target_grid.sha256, "expected_target_grid_sha256"
        )
        source_mask = _active_mask(source_active_mask, source_grid.cell_count, "source_active_mask")
        target_mask = _active_mask(target_active_mask, target_grid.cell_count, "target_active_mask")

        rows: list[int] = []
        columns: list[int] = []
        values: list[float] = []
        source_coverage = np.zeros(source_grid.cell_count, dtype=np.float64)
        target_coverage = np.zeros(target_grid.cell_count, dtype=np.float64)
        for source_index, target_index, overlap_volume in _active_overlaps(
            source_grid, target_grid, source_mask, target_mask
        ):
            rows.append(source_index)
            columns.append(target_index)
            values.append(overlap_volume / source_grid.cell_volume)
            source_coverage[source_index] += overlap_volume
            target_coverage[target_index] += overlap_volume

        _require_full_coverage(
            source_coverage, source_mask, source_grid.cell_volume, "source active domain"
        )
        _require_full_coverage(
            target_coverage, target_mask, target_grid.cell_volume, "target active domain"
        )
        matrix = csr_array(
            (np.asarray(values, dtype=np.float64), (rows, columns)),
            shape=(source_grid.cell_count, target_grid.cell_count),
            dtype=np.float64,
        )
        _require_state_row_sums(matrix, source_mask)
        source_mask.setflags(write=False)
        target_mask.setflags(write=False)
        return cls(
            source_grid=source_grid,
            target_grid=target_grid,
            matrix=matrix,
            source_active_mask=source_mask,
            target_active_mask=target_mask,
            source_grid_sha256=source_grid.sha256,
            target_grid_sha256=target_grid.sha256,
            source_active_mask_sha256=_mask_sha256(source_mask),
            target_active_mask_sha256=_mask_sha256(target_mask),
        )

    def transfer_state_to_source(self, target_state: np.ndarray | Sequence[float]) -> np.ndarray:
        """Return the source-cell volume average ``P @ target_state``.

        Inactive source cells are zero because they are outside the proven
        binding domain.  Inputs must still provide one finite canonical value
        per target cell; accepting implicit reordering or missing values would
        invalidate the transfer provenance.
        """

        values = _finite_cell_values(target_state, self.target_grid.cell_count, "target_state")
        result = np.asarray(self.matrix @ values, dtype=np.float64).reshape(-1)
        result[~self.source_active_mask] = 0.0
        return result

    def transfer_gradient_to_target(self, source_gradient: np.ndarray | Sequence[float]) -> np.ndarray:
        """Return the Euclidean-coordinate dual ``P.T @ source_gradient``.

        See the module-level convention: this is exact for discrete derivative
        coefficients satisfying ``dJ = g.dot(dstate)``.  It is deliberately not
        a volume-weighted L2 gradient-density conversion.
        """

        values = _finite_cell_values(source_gradient, self.source_grid.cell_count, "source_gradient")
        result = np.asarray(self.matrix.T @ values, dtype=np.float64).reshape(-1)
        result[~self.target_active_mask] = 0.0
        return result


def _finite_vector(values: Sequence[float], name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (3,) or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a numeric vector with shape (3,)")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _cell_shape(values: Sequence[int]) -> tuple[int, int, int]:
    raw = np.asarray(values)
    if raw.shape != (3,) or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError("cell_shape must be an integer vector with shape (3,)")
    shape = tuple(int(value) for value in raw)
    if any(value <= 0 for value in shape):
        raise ValueError("cell_shape must contain three positive integers")
    return shape


def _active_mask(
    values: np.ndarray | Sequence[bool] | None, count: int, name: str
) -> np.ndarray:
    if values is None:
        return np.ones(count, dtype=bool)
    array = np.asarray(values)
    if array.shape != (count,) or array.dtype != np.bool_:
        raise ValueError(f"{name} must be a boolean vector with shape ({count},)")
    if not bool(np.any(array)):
        raise ValueError(f"{name} must select at least one cell")
    return np.array(array, dtype=bool, copy=True)


def _finite_cell_values(values: np.ndarray | Sequence[float], count: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.shape != (count,) or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a numeric vector with shape ({count},)")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array


def _validate_expected_hash(expected: str | None, actual: str, name: str) -> None:
    if expected is None:
        return
    if not isinstance(expected, str) or _HASH_RE.fullmatch(expected) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    if expected != actual:
        raise ValueError(f"{name} does not match the canonical grid hash")


def _active_overlaps(
    source: UniformCartesianCellGrid,
    target: UniformCartesianCellGrid,
    source_mask: np.ndarray,
    target_mask: np.ndarray,
):
    source_origin = source.lower
    source_spacing = np.asarray(source.spacing, dtype=np.float64)
    target_origin = target.lower
    target_spacing = np.asarray(target.spacing, dtype=np.float64)
    for sx in range(source.cell_shape[0]):
        for sy in range(source.cell_shape[1]):
            for sz in range(source.cell_shape[2]):
                source_index = source.flat_index(sx, sy, sz)
                if not source_mask[source_index]:
                    continue
                lower = source_origin + source_spacing * np.asarray((sx, sy, sz), dtype=np.float64)
                upper = lower + source_spacing
                ranges = tuple(
                    _overlapping_axis_indices(
                        lower[axis], upper[axis], target_origin[axis], target_spacing[axis], target.cell_shape[axis]
                    )
                    for axis in range(3)
                )
                for tx in ranges[0]:
                    for ty in ranges[1]:
                        for tz in ranges[2]:
                            target_index = target.flat_index(tx, ty, tz)
                            if not target_mask[target_index]:
                                continue
                            target_lower = target_origin + target_spacing * np.asarray(
                                (tx, ty, tz), dtype=np.float64
                            )
                            target_upper = target_lower + target_spacing
                            lengths = np.minimum(upper, target_upper) - np.maximum(lower, target_lower)
                            if np.any(lengths <= 0.0):
                                continue
                            yield source_index, target_index, float(np.prod(lengths, dtype=np.float64))


def _overlapping_axis_indices(
    lower: float, upper: float, target_origin: float, target_spacing: float, target_count: int
) -> range:
    first = max(0, int(np.floor((lower - target_origin) / target_spacing)))
    # ``nextafter`` keeps a shared upper face out of the following cell while
    # preserving an actual positive-width final overlap.
    last = min(target_count - 1, int(np.floor(np.nextafter((upper - target_origin) / target_spacing, -np.inf))))
    return range(first, last + 1) if last >= first else range(0)


def _require_full_coverage(
    coverage: np.ndarray, active_mask: np.ndarray, cell_volume: float, domain_name: str
) -> None:
    active_coverage = coverage[active_mask]
    tolerance = max(_COVERAGE_ATOL, _COVERAGE_RTOL * cell_volume)
    missing = np.flatnonzero(active_mask & (np.abs(coverage - cell_volume) > tolerance))
    if missing.size:
        index = int(missing[0])
        raise ValueError(
            f"{domain_name} is not fully covered by overlap transfer; "
            f"cell {index} has coverage {coverage[index]:.17g} of {cell_volume:.17g}"
        )
    if not np.isfinite(active_coverage).all():
        raise ValueError(f"{domain_name} coverage is non-finite")


def _require_state_row_sums(matrix: csr_array, source_mask: np.ndarray) -> None:
    row_sums = np.asarray(matrix.sum(axis=1), dtype=np.float64).reshape(-1)
    if not np.allclose(row_sums[source_mask], 1.0, rtol=_COVERAGE_RTOL, atol=_COVERAGE_ATOL):
        raise ValueError("source state-transfer rows do not preserve volume averages")
    if not np.allclose(row_sums[~source_mask], 0.0, rtol=0.0, atol=0.0):
        raise ValueError("inactive source rows must be zero")


def _mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values))
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + array.tobytes()).hexdigest()


__all__ = [
    "CANONICAL_CELL_ORDER",
    "ExactCartesianOverlapTransfer",
    "OPENFOAM_GLOBAL_CELL_LABEL_ORDER",
    "OpenFoamCellOrderMapping",
    "UniformCartesianCellGrid",
    "load_openfoam_cell_order_mapping",
]
