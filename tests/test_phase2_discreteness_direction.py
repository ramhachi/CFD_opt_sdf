"""Pure tests for the bounded v13 discreteness direction."""

from __future__ import annotations

import numpy as np

from cfd_sdf.design_transform import (
    ConeFilter,
    DesignTransform,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.phase2_discreteness_direction import (
    backtrack_transform_candidates,
    projected_raw_gradient_direction,
    transform_candidate,
)


SHAPE = (6, 5, 4)


def _arena():
    mask = np.zeros(SHAPE, dtype=bool)
    mask[1:5, 1:4, 1:3] = True
    active = mask.ravel(order="F")
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(SHAPE, 0.05, active, radius_m=0.05),
        projection=TanhProjection(16.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    rho = np.zeros(np.prod(SHAPE), dtype=np.float64)
    ids = np.flatnonzero(active)
    rho[ids] = np.where(np.arange(ids.size) % 2 == 0, 0.42, 0.58)
    rho[ids[0]] = 0.0
    rho[ids[1]] = 1.0
    gradient = np.zeros_like(rho)
    gradient[ids] = np.linspace(-3.0, 2.0, ids.size)
    return transform, rho, gradient, active


def test_raw_gradient_direction_is_a_descent_and_discreteness_tangent():
    transform, rho, gradient, active = _arena()
    result = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )

    assert result.diagnostics["projection_applied"] is True
    assert result.diagnostics["g_objective_dot_direction"] < 0.0
    assert abs(result.diagnostics["g_discreteness_dot_direction"]) < 1e-12
    assert result.diagnostics["direction_inf_norm"] == 1.0
    assert np.all(result.values[~active] == 0.0)
    assert result.values[np.flatnonzero(active)[0]] == 0.0
    assert result.values[np.flatnonzero(active)[1]] == 0.0


def test_transform_candidate_preserves_masks_box_and_records_physical_metrics():
    transform, rho, gradient, active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    candidate = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=0.25,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )

    assert candidate.feasible is True
    assert candidate.metrics["mask_drift_max"] == 0.0
    assert candidate.metrics["move_box_violation_max"] == 0.0
    assert candidate.metrics["corrected_update_inf_norm"] <= 0.0025 + 1e-15
    assert np.all(candidate.rho[~active] == rho[~active])
    assert 0.0 <= candidate.metrics["discreteness_mean_nd_candidate"] <= 1.0


def test_backtracking_stops_at_first_transform_feasible_candidate():
    transform, rho, gradient, _active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    full = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    half = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=0.5,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    assert full.metrics["discreteness_mean_nd_candidate"] > half.metrics[
        "discreteness_mean_nd_candidate"
    ]
    bound = 0.5 * (
        full.metrics["discreteness_mean_nd_candidate"]
        + half.metrics["discreteness_mean_nd_candidate"]
    )

    ledger, selected = backtrack_transform_candidates(
        transform=transform,
        rho=rho,
        direction=direction.values,
        ladder=(1.0, 0.5, 0.25),
        move_limit=0.01,
        discreteness_mean_nd_max=bound,
        v_max=1.0,
    )

    assert [entry.alpha for entry in ledger] == [1.0, 0.5]
    assert ledger[0].feasible is False
    assert ledger[0].gates["projected_discreteness_within_limit"] is False
    assert selected is ledger[1]
    assert selected.feasible is True


def test_invalid_or_zero_projected_direction_fails_closed():
    transform, rho, _gradient, _active = _arena()
    with np.testing.assert_raises(ValueError):
        projected_raw_gradient_direction(
            transform=transform,
            rho=rho,
            objective_gradient=np.zeros_like(rho),
        )
