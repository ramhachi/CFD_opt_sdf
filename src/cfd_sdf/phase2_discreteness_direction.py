"""Projected Phase 2 direction for the active discreteness constraint.

This module is deliberately separate from ``phase2_inequality_policy``.  The
v1/v2 sign-step policies keep their registered behaviour; v13 only uses the
raw-gradient direction below in its bounded one-step discriminant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from cfd_sdf.phase2_inequality_policy import (
    BOX_TOLERANCE,
    EXTRACTABILITY_FRACTION,
    EXTRACTABILITY_THRESHOLDS,
    MASK_DRIFT_TOLERANCE,
    MIN_CORRECTED_UPDATE_INF_NORM,
    OCCUPANCY_THRESHOLDS,
)

POLICY_ID = "objective-gradient-discreteness-projected-v1"


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def _mean_nd(projected: np.ndarray, active: np.ndarray) -> float:
    values = projected[active]
    return float(np.mean(4.0 * values * (1.0 - values)))


def _occupancy(projected: np.ndarray, active: np.ndarray) -> dict[str, Any]:
    values = projected[active]
    result: dict[str, Any] = {"total_active": int(values.size)}
    for threshold in OCCUPANCY_THRESHOLDS:
        count = int(np.count_nonzero(values > threshold))
        result[f"cells_gt_{threshold}"] = count
        result[f"fraction_gt_{threshold}"] = count / values.size if values.size else 0.0
    return result


@dataclass(frozen=True)
class ProjectedDirection:
    values: np.ndarray
    discreteness_gradient: np.ndarray
    free: np.ndarray
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class TransformCandidate:
    alpha: float
    rho: np.ndarray
    metrics: dict[str, Any]
    gates: dict[str, bool]

    @property
    def feasible(self) -> bool:
        return bool(all(self.gates.values()))

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "alpha": float(self.alpha),
            "rho_sha256": _array_sha256(self.rho),
            "metrics": dict(self.metrics),
            "gates": dict(self.gates),
            "transform_feasible": self.feasible,
        }


def projected_raw_gradient_direction(
    *,
    transform,
    rho: np.ndarray,
    objective_gradient: np.ndarray,
    freeze_box_faces: bool = True,
) -> ProjectedDirection:
    """Project ``-gJ`` onto the linearized ``mean_nd`` tangent half-space."""

    values = np.asarray(rho, dtype=np.float64)
    gradient = np.asarray(objective_gradient, dtype=np.float64)
    if values.shape != gradient.shape or values.shape != np.asarray(transform.active).shape:
        raise ValueError("rho, objective gradient, and transform active mask must share shape")
    if not np.isfinite(values).all() or not np.isfinite(gradient).all():
        raise ValueError("rho and objective gradient must be finite")

    active = np.asarray(transform.active, dtype=bool)
    active_count = int(np.count_nonzero(active))
    if active_count == 0:
        raise ValueError("discreteness direction requires at least one active cell")
    frozen = active & ((values == 0.0) | (values == 1.0)) if freeze_box_faces else np.zeros_like(active)
    free = active & ~frozen
    state = transform.forward(values)
    projected = np.asarray(state.rho_projected, dtype=np.float64)
    seed = np.zeros_like(values)
    seed[active] = 4.0 * (1.0 - 2.0 * projected[active]) / active_count
    g_discreteness = np.asarray(
        transform.pullback_from_projected(values, seed), dtype=np.float64
    )

    direction_0 = np.zeros_like(values)
    direction_0[free] = -gradient[free]
    g_free = np.zeros_like(values)
    g_free[free] = g_discreteness[free]
    directional_before = float(np.dot(g_discreteness, direction_0))
    denominator = float(np.dot(g_free, g_free))
    coefficient = 0.0
    direction = direction_0.copy()
    if directional_before > 0.0:
        if denominator <= 0.0:
            raise ValueError("positive discreteness derivative has no free-cell gradient")
        coefficient = directional_before / denominator
        direction -= coefficient * g_free
    direction[~free] = 0.0
    peak = float(np.max(np.abs(direction[free]))) if bool(free.any()) else 0.0
    if peak <= 0.0 or not np.isfinite(peak):
        raise ValueError("projected objective direction is zero or non-finite")
    direction /= peak

    diagnostics = {
        "policy_id": POLICY_ID,
        "active_cells": active_count,
        "free_cells": int(np.count_nonzero(free)),
        "frozen_box_face_cells": int(np.count_nonzero(frozen)),
        "objective_gradient_sha256": _array_sha256(gradient),
        "discreteness_gradient_sha256": _array_sha256(g_discreteness),
        "direction_sha256": _array_sha256(direction),
        "projection_applied": bool(directional_before > 0.0),
        "projection_coefficient": float(coefficient),
        "g_discreteness_dot_d0": directional_before,
        "g_discreteness_dot_direction": float(np.dot(g_discreteness, direction)),
        "g_objective_dot_direction": float(np.dot(gradient, direction)),
        "direction_inf_norm": float(np.max(np.abs(direction))),
    }
    return ProjectedDirection(direction, g_discreteness, free, diagnostics)


def transform_candidate(
    *,
    transform,
    rho: np.ndarray,
    direction: np.ndarray,
    alpha: float,
    move_limit: float,
    discreteness_mean_nd_max: float,
    v_max: float,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
) -> TransformCandidate:
    """Build one move-box candidate and apply solver-free registered gates."""

    values = np.asarray(rho, dtype=np.float64)
    step_direction = np.asarray(direction, dtype=np.float64)
    if values.shape != step_direction.shape:
        raise ValueError("rho and direction must share shape")
    if not np.isfinite(alpha) or float(alpha) <= 0.0:
        raise ValueError("alpha must be finite and positive")
    if not np.isfinite(move_limit) or float(move_limit) <= 0.0:
        raise ValueError("move_limit must be finite and positive")

    active = np.asarray(transform.active, dtype=bool)
    frozen = active & ((values == 0.0) | (values == 1.0)) if freeze_box_faces else np.zeros_like(active)
    lower = np.clip(values - float(move_limit), 0.0, 1.0)
    upper = np.clip(values + float(move_limit), 0.0, 1.0)
    proposal = np.clip(
        values + float(alpha) * float(move_limit) * step_direction,
        lower,
        upper,
    )
    proposal[~active] = values[~active]
    proposal[frozen] = values[frozen]

    parent_projected = np.asarray(transform.forward(values).rho_projected, dtype=np.float64)
    candidate_projected = np.asarray(transform.forward(proposal).rho_projected, dtype=np.float64)
    parent_occupancy = _occupancy(parent_projected, active)
    candidate_occupancy = _occupancy(candidate_projected, active)
    delta = proposal - values
    violation = np.maximum(proposal - upper, lower - proposal)
    mask_drift = float(np.max(np.abs(delta[~active]))) if bool((~active).any()) else 0.0
    metrics = {
        "corrected_update_inf_norm": float(np.max(np.abs(delta))),
        "discreteness_mean_nd_parent": _mean_nd(parent_projected, active),
        "discreteness_mean_nd_candidate": _mean_nd(candidate_projected, active),
        "projected_volume_parent": float(np.mean(parent_projected[active])),
        "projected_volume_candidate": float(np.mean(candidate_projected[active])),
        "projected_field_mean_abs_delta": float(
            np.mean(np.abs(candidate_projected[active] - parent_projected[active]))
        ),
        "projected_field_max_abs_delta": float(
            np.max(np.abs(candidate_projected[active] - parent_projected[active]))
        ),
        "mask_drift_max": mask_drift,
        "move_box_violation_max": float(max(0.0, np.max(violation))),
        "occupancy_parent": parent_occupancy,
        "occupancy_candidate": candidate_occupancy,
    }
    extractability_ok = all(
        candidate_occupancy[f"cells_gt_{threshold}"]
        >= float(extractability_fraction) * parent_occupancy[f"cells_gt_{threshold}"]
        for threshold in EXTRACTABILITY_THRESHOLDS
    )
    gates = {
        "corrected_update_above_machine_scale": bool(
            metrics["corrected_update_inf_norm"] >= float(min_update_inf_norm)
        ),
        "projected_discreteness_within_limit": bool(
            metrics["discreteness_mean_nd_candidate"] <= float(discreteness_mean_nd_max)
        ),
        "projected_volume_within_v_max": bool(
            metrics["projected_volume_candidate"] <= float(v_max)
        ),
        "extractability_guard": bool(extractability_ok),
        "mask_invariance": bool(mask_drift <= MASK_DRIFT_TOLERANCE),
        "move_box_respected": bool(
            metrics["move_box_violation_max"] <= BOX_TOLERANCE
        ),
    }
    return TransformCandidate(float(alpha), proposal, metrics, gates)


def backtrack_transform_candidates(
    *,
    transform,
    rho: np.ndarray,
    direction: np.ndarray,
    ladder: tuple[float, ...],
    move_limit: float,
    discreteness_mean_nd_max: float,
    v_max: float,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
) -> tuple[list[TransformCandidate], TransformCandidate | None]:
    """Return the ledger through the first transform-feasible candidate."""

    ledger: list[TransformCandidate] = []
    for alpha in ladder:
        candidate = transform_candidate(
            transform=transform,
            rho=rho,
            direction=direction,
            alpha=alpha,
            move_limit=move_limit,
            discreteness_mean_nd_max=discreteness_mean_nd_max,
            v_max=v_max,
            freeze_box_faces=freeze_box_faces,
            min_update_inf_norm=min_update_inf_norm,
            extractability_fraction=extractability_fraction,
        )
        ledger.append(candidate)
        if candidate.feasible:
            return ledger, candidate
    return ledger, None


__all__ = [
    "POLICY_ID",
    "ProjectedDirection",
    "TransformCandidate",
    "backtrack_transform_candidates",
    "projected_raw_gradient_direction",
    "transform_candidate",
]
