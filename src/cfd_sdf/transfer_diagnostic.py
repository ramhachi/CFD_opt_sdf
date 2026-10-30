"""Diagnostics for the canonical-to-solver grid transfer (DF2, P6).

The Stage T loop transfers the canonical density to the solver grid with
``source = P @ target`` and returns sensitivities with ``P.T @ sens``. P6
records a reproducible ~10% FD ratio deficit on generic directions and about
0.90--0.99 along the sensitivity direction; the prime suspect is the
non-integer overlap transfer. This module makes the transfer's two classical
mapping properties measurable without any solver:

- **consistency**: a constant target field maps to the same constant on the
  source domain (each source row sums to one);
- **conservation**: the physical integral is preserved,
  ``sum_s (P x)_s V_s == sum_t x_t V_t``;
- **adjoint identity**: ``<P x, y> == <x, P.T y>``. For the value-transfer
  definition used here (each source row sums to one, ``P`` maps cell values),
  ``P.T`` **is** the exact discrete adjoint; no volume weighting belongs in the
  sensitivity pullback. The optional ``volume_weighted_pullback_difference``
  fields record, informationally, how different a volume-weighted pullback
  would be (they are zero only when the transfer connects equal cell volumes);
  they are not a defect.

The verdict is machine-readable: ``exact`` (all relative errors below the
declared tolerance) or ``invalid`` (a non-finite metric). A bounded
non-exactness here means a broken transfer operator, not a solver effect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

import numpy as np

from .openfoam_grid_transfer import ExactCartesianOverlapTransfer

TOLERANCE = 1e-12


@dataclass(frozen=True)
class TransferDiagnostic:
    source_cell_shape: tuple[int, int, int]
    target_cell_shape: tuple[int, int, int]
    source_spacing: tuple[float, float, float]
    target_spacing: tuple[float, float, float]
    spacing_ratios: tuple[float, float, float]
    integer_ratio: bool
    source_cell_volume_m3: float
    target_cell_volume_m3: float
    cell_volume_ratio: float
    consistency_error: float
    uniform_state_conservation_error: float
    random_state_conservation_error: float
    euclidean_adjoint_identity_error: float
    volume_weighted_pullback_difference_abs: float
    volume_weighted_pullback_difference_relative: float
    verdict: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _relative(numerator: float, scale: float) -> float:
    return float(abs(numerator) / scale) if scale > 0.0 else float(abs(numerator))


def diagnose_transfer(
    transfer: ExactCartesianOverlapTransfer,
    *,
    seed: int = 20260921,
    tolerance: float = TOLERANCE,
) -> TransferDiagnostic:
    """Measure consistency, conservation and adjoint metric mismatch of ``P``."""

    matrix = transfer.matrix
    source_count = transfer.source_grid.cell_count
    target_count = transfer.target_grid.cell_count
    source_volume = float(transfer.source_grid.cell_volume)
    target_volume = float(transfer.target_grid.cell_volume)
    source_mask = np.asarray(transfer.source_active_mask, dtype=bool)
    target_mask = np.asarray(transfer.target_active_mask, dtype=bool)

    spacing_ratios = tuple(
        float(s) / float(t)
        for s, t in zip(transfer.source_grid.spacing, transfer.target_grid.spacing)
    )
    integer_ratio = all(abs(ratio - round(ratio)) < 1e-9 for ratio in spacing_ratios)

    constants = np.zeros(target_count, dtype=np.float64)
    constants[target_mask] = 1.0
    mapped_constants = np.asarray(matrix @ constants).ravel()
    consistency_error = float(
        np.max(np.abs(mapped_constants[source_mask] - 1.0)) if source_mask.any() else 0.0
    )

    uniform = np.zeros(target_count, dtype=np.float64)
    uniform[target_mask] = 0.5
    random = np.zeros(target_count, dtype=np.float64)
    rng = np.random.default_rng(seed)
    random[target_mask] = rng.uniform(0.1, 0.9, size=int(target_mask.sum()))

    def conservation_error(state: np.ndarray) -> float:
        mapped = np.asarray(matrix @ state).ravel()
        source_integral = float(np.sum(mapped[source_mask] * source_volume))
        target_integral = float(np.sum(state[target_mask] * target_volume))
        return _relative(source_integral - target_integral, abs(target_integral))

    source_weights = np.zeros(source_count, dtype=np.float64)
    source_weights[source_mask] = source_volume
    target_weights = np.zeros(target_count, dtype=np.float64)
    target_weights[target_mask] = target_volume
    probe = np.zeros(source_count, dtype=np.float64)
    probe[source_mask] = rng.uniform(-1.0, 1.0, size=int(source_mask.sum()))
    target_probe = np.zeros(target_count, dtype=np.float64)
    target_probe[target_mask] = rng.uniform(-1.0, 1.0, size=int(target_mask.sum()))

    def metric_mismatch(source_sensitivity: np.ndarray) -> tuple[float, float]:
        weighted_pullback = np.asarray(
            matrix.T @ (source_weights * source_sensitivity)
        ).ravel()
        euclidean_pullback = np.asarray(matrix.T @ source_sensitivity).ravel()
        mismatch = weighted_pullback - target_weights * euclidean_pullback
        scale = float(np.max(np.abs(weighted_pullback))) if weighted_pullback.size else 0.0
        absolute = float(np.max(np.abs(mismatch))) if mismatch.size else 0.0
        return absolute, _relative(absolute, scale)

    pullback_difference_abs, pullback_difference_relative = metric_mismatch(probe)

    euclidean_lhs = float(np.dot(np.asarray(matrix @ target_probe).ravel(), probe))
    euclidean_rhs = float(np.dot(target_probe, np.asarray(matrix.T @ probe).ravel()))
    euclid_identity = _relative(
        euclidean_lhs - euclidean_rhs, max(abs(euclidean_lhs), abs(euclidean_rhs))
    )

    errors = {
        "consistency": consistency_error,
        "uniform_conservation": conservation_error(uniform),
        "random_conservation": conservation_error(random),
        "adjoint_identity": euclid_identity,
    }
    if not all(isfinite(value) for value in errors.values()):
        verdict = "invalid"
    elif all(value <= tolerance for value in errors.values()):
        verdict = "exact"
    else:
        verdict = "bounded_not_exact"

    notes: list[str] = [
        "P maps cell values (source rows sum to 1); P.T is the exact discrete adjoint",
    ]
    if not integer_ratio:
        notes.append(
            "spacing ratios are not integers; overlap coverage is still exact because "
            "build() rejects incomplete coverage"
        )
    if abs(source_volume - target_volume) > tolerance:
        notes.append(
            f"cell volume ratio {source_volume / target_volume:.6g}; a volume-weighted "
            "pullback would differ, but the value-transfer adjoint is P.T by definition"
        )
    return TransferDiagnostic(
        source_cell_shape=tuple(int(v) for v in transfer.source_grid.cell_shape),
        target_cell_shape=tuple(int(v) for v in transfer.target_grid.cell_shape),
        source_spacing=tuple(float(v) for v in transfer.source_grid.spacing),
        target_spacing=tuple(float(v) for v in transfer.target_grid.spacing),
        spacing_ratios=spacing_ratios,
        integer_ratio=integer_ratio,
        source_cell_volume_m3=source_volume,
        target_cell_volume_m3=target_volume,
        cell_volume_ratio=source_volume / target_volume,
        consistency_error=consistency_error,
        uniform_state_conservation_error=conservation_error(uniform),
        random_state_conservation_error=conservation_error(random),
        euclidean_adjoint_identity_error=euclid_identity,
        volume_weighted_pullback_difference_abs=pullback_difference_abs,
        volume_weighted_pullback_difference_relative=pullback_difference_relative,
        verdict=verdict,
        notes=tuple(notes),
    )


__all__ = ["TransferDiagnostic", "diagnose_transfer", "grid_from_json", "load_grid_json"]


def grid_from_json(data: dict[str, Any]) -> "UniformCartesianCellGrid":
    """Build a uniform grid from a topology-state, snapshot, or bare grid block."""

    from .openfoam_grid_transfer import UniformCartesianCellGrid

    block = data.get("grid", data)
    origin = block.get("origin", block.get("lower_origin_m"))
    spacing = block.get("spacing", block.get("spacing_m"))
    cell_shape = block.get("cell_shape")
    if origin is None or spacing is None or cell_shape is None:
        raise ValueError(
            "grid JSON must provide origin/lower_origin_m, spacing/spacing_m, and cell_shape"
        )
    return UniformCartesianCellGrid(
        origin=tuple(float(v) for v in origin),
        spacing=tuple(float(v) for v in spacing),
        cell_shape=tuple(int(v) for v in cell_shape),
    )


def load_grid_json(path: str | Path) -> "UniformCartesianCellGrid":
    import json
    from pathlib import Path as _Path

    return grid_from_json(json.loads(_Path(path).read_text(encoding="utf-8")))
