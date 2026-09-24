"""Work F realized-direction audit (diagnosis D1, solver-free).

Reconstructs, for every registered perturbation side, the control-point state
actually realized by the morpher and compares it with the prescribed movement
and direction: equality, boundary confinement, permutation, odd symmetry,
even-component size, and the analytic directional derivatives along the
prescribed versus realized contraction. No CFD response is used and no
registered threshold is changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_CONTROL_POINTS_RE = re.compile(r"\(([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)")

REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M = 1.0e-7
BOUNDARY_MOVEMENT_ABS_TOLERANCE_M = 1.0e-9
ODD_SYMMETRY_ABS_TOLERANCE_M = 1.0e-6
EVEN_COMPONENT_ABS_TOLERANCE_M = 1.0e-6
COSINE_SIMILARITY_MIN = 0.999999
DIRECTION_CP_ABS_TOLERANCE_M = 1.0e-6


class RealizedDirectionError(ValueError):
    """Fail-closed realized-direction audit violation."""


def read_control_points_file(path: str | Path) -> np.ndarray:
    """Parse ``controlPoints nonuniform List<vector> N ( ... )``."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    matches = _CONTROL_POINTS_RE.findall(text)
    if not matches:
        raise RealizedDirectionError(f"no control points found in {path}")
    count_match = re.search(r"^\s*(\d+)\s*$", text, re.MULTILINE)
    values = np.asarray([[float(a), float(b), float(c)] for a, b, c in matches])
    if count_match is not None and int(count_match.group(1)) != values.shape[0]:
        raise RealizedDirectionError(
            f"control point count mismatch in {path}: header {count_match.group(1)} vs {values.shape[0]}"
        )
    return values


def read_control_points_csv(path: str | Path) -> np.ndarray:
    """Parse the NURBS3DVolume control-point catalog CSV (coordinate columns)."""

    rows: list[list[float]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith('"Points'):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
        except ValueError:
            continue
    values = np.asarray(rows, dtype=np.float64)
    if values.size == 0:
        raise RealizedDirectionError(f"no control points found in {path}")
    return values


def read_movement_file(path: str | Path) -> np.ndarray:
    return read_control_points_file(path)


def direction_to_cp_space(
    direction_values: np.ndarray,
    active_var_ids: tuple[int, ...],
    *,
    n_control_points: tuple[int, int, int] = (8, 8, 8),
) -> np.ndarray:
    """Map a registered active-variable direction back to the control-point grid."""

    values = np.asarray(direction_values, dtype=np.float64)
    if values.size != len(active_var_ids):
        raise RealizedDirectionError("direction size does not match the active varID set")
    nx, ny, nz = (int(value) for value in n_control_points)
    grid = np.zeros((nx * ny * nz, 3), dtype=np.float64)
    for value, var_id in zip(values, active_var_ids, strict=True):
        cp_id, component = divmod(int(var_id), 3)
        grid[cp_id, component] = float(value)
    return grid


@dataclass(frozen=True)
class PairAudit:
    direction: str
    epsilon: float
    delta_odd: np.ndarray
    delta_even: np.ndarray


def audit_pair(
    *,
    base: np.ndarray,
    realized_plus: np.ndarray,
    realized_minus: np.ndarray,
    epsilon: float,
) -> PairAudit:
    if not (base.shape == realized_plus.shape == realized_minus.shape):
        raise RealizedDirectionError("control-point state shapes differ")
    delta_odd = (realized_plus - realized_minus) / (2.0 * epsilon)
    delta_even = (realized_plus + realized_minus - 2.0 * base) / (2.0 * epsilon)
    return PairAudit(direction="", epsilon=float(epsilon), delta_odd=delta_odd, delta_even=delta_even)


def audit_case(
    *,
    base: np.ndarray,
    realized: np.ndarray,
    prescribed: np.ndarray,
    active_mask: np.ndarray,
) -> dict[str, Any]:
    """Per-side realized-vs-prescribed checks."""

    applied = base + prescribed
    difference = realized - applied
    boundary_difference = np.abs(realized[~active_mask] - base[~active_mask])
    inactive_movement = np.abs(prescribed[~active_mask])
    return {
        "max_realized_minus_prescribed_m": float(np.max(np.abs(difference))),
        "realized_equals_prescribed": bool(
            np.max(np.abs(difference)) <= REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M
        ),
        "max_boundary_realized_movement_m": float(np.max(boundary_difference))
        if boundary_difference.size
        else 0.0,
        "max_inactive_prescribed_movement_m": float(np.max(inactive_movement))
        if inactive_movement.size
        else 0.0,
        "boundary_fixed": bool(
            (boundary_difference.size == 0)
            or (np.max(boundary_difference) <= BOUNDARY_MOVEMENT_ABS_TOLERANCE_M)
        ),
        "inactive_zero": bool(
            (inactive_movement.size == 0)
            or (np.max(inactive_movement) <= BOUNDARY_MOVEMENT_ABS_TOLERANCE_M)
        ),
        "start_equals_base": bool(
            np.max(np.abs(realized - base - prescribed)) <= REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M
        ),
    }


def direction_comparison(
    *,
    direction_cp: np.ndarray,
    delta_odd: np.ndarray,
    active_mask: np.ndarray,
) -> dict[str, Any]:
    """Prescribed direction vs the realized odd difference in control-point space."""

    prescribed_active = direction_cp[active_mask]
    realized_active = delta_odd[active_mask]
    prescribed_norm = float(np.linalg.norm(prescribed_active))
    realized_norm = float(np.linalg.norm(realized_active))
    denominator = max(prescribed_norm * realized_norm, 1e-30)
    cosine = float(np.dot(prescribed_active, realized_active) / denominator)
    difference = np.abs(realized_active - prescribed_active)
    relative = difference / np.maximum(np.abs(prescribed_active), 1e-30)
    return {
        "prescribed_active_l2_norm": prescribed_norm,
        "realized_active_l2_norm": realized_norm,
        "cosine_similarity": cosine,
        "max_abs_difference": float(difference.max()) if difference.size else 0.0,
        "max_relative_difference": float(relative.max()) if relative.size else 0.0,
        "cosine_ok": bool(cosine >= COSINE_SIMILARITY_MIN),
        "difference_ok": bool(
            difference.size == 0 or float(difference.max()) <= DIRECTION_CP_ABS_TOLERANCE_M
        ),
    }


def active_mask_from_ids(
    active_var_ids: tuple[int, ...], *, n_control_points: tuple[int, int, int] = (8, 8, 8)
) -> np.ndarray:
    nx, ny, nz = (int(value) for value in n_control_points)
    mask = np.zeros((nx * ny * nz, 3), dtype=bool)
    for var_id in active_var_ids:
        cp_id, component = divmod(int(var_id), 3)
        mask[cp_id, component] = True
    return mask


def analytic_directional(
    derivative_vector: np.ndarray, direction_cp: np.ndarray, active_mask: np.ndarray
) -> float:
    return float(np.dot(derivative_vector, direction_cp[active_mask]))


__all__ = [
    "BOUNDARY_MOVEMENT_ABS_TOLERANCE_M",
    "COSINE_SIMILARITY_MIN",
    "DIRECTION_CP_ABS_TOLERANCE_M",
    "EVEN_COMPONENT_ABS_TOLERANCE_M",
    "ODD_SYMMETRY_ABS_TOLERANCE_M",
    "PairAudit",
    "REALIZED_EQUALS_PRESCRIBED_ABS_TOLERANCE_M",
    "RealizedDirectionError",
    "active_mask_from_ids",
    "analytic_directional",
    "audit_case",
    "audit_pair",
    "direction_comparison",
    "direction_to_cp_space",
    "read_control_points_csv",
    "read_control_points_file",
    "read_movement_file",
]
