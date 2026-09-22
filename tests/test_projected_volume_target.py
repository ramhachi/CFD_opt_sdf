"""Tests for the projected-volume target backend and its preflight (Work C)."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design_transform import (
    ConeFilter,
    DesignTransform,
    IdentityFilter,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.stage_t_loop import ProjectedVolumeTargetBackend


def _transform(*, b: float, q: float, radius: float = 1.5):
    shape = (8, 1, 1)
    active = np.ones(8, dtype=bool)
    return DesignTransform(
        shape=shape,
        spacing_m=1.0,
        active_mask=active,
        filter=ConeFilter(shape=shape, spacing_m=1.0, active_mask=active, radius_m=radius),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )


def _descent(fraction: float, size: int = 8) -> np.ndarray:
    gradient = np.zeros(size)
    gradient[: int(size * fraction) + 1] = -1.0
    return gradient


def test_projected_volume_backend_hits_target_at_each_continuation_level():
    # start near the projection threshold so the continuation is reachable
    rho = np.full(8, 0.5)
    gradient = -np.ones(8)  # the descent direction favours growth
    for b, q in ((8.0, 30.0), (16.0, 100.0)):
        transform = _transform(b=b, q=q)
        backend = ProjectedVolumeTargetBackend(
            transform=transform, target=0.5, tolerance=1e-4
        )
        proposal = backend.propose(
            rho=rho,
            objective_gradient=gradient,
            constraint_gradients={},
            constraint_values={},
            move_radius=0.05,
            backend_state={},
        )
        state = transform.forward(np.asarray(rho, dtype=np.float64) + proposal.delta)
        projected_volume = float(
            np.asarray(state.rho_projected, dtype=np.float64)[transform.active].mean()
        )
        assert abs(projected_volume - 0.5) <= 1e-4, (b, q, projected_volume)
        assert proposal.metadata["projected_volume_after"] == pytest.approx(
            projected_volume, abs=1e-8
        )
        assert "kappa" in proposal.metadata


def test_backend_fails_closed_when_target_is_unreachable():
    backend = ProjectedVolumeTargetBackend(
        transform=_transform(b=16.0, q=100.0), target=0.9, tolerance=1e-6
    )
    rho = np.full(8, 0.2)
    gradient = np.zeros(8)  # no descent direction at all -> kappa=0 only
    with pytest.raises(ValueError, match="unreachable inside the move box"):
        backend.propose(
            rho=rho,
            objective_gradient=gradient,
            constraint_gradients={},
            constraint_values={},
            move_radius=0.05,
            backend_state={},
        )


def test_backend_fails_closed_when_target_above_move_box():
    backend = ProjectedVolumeTargetBackend(
        transform=_transform(b=8.0, q=30.0), target=0.99, tolerance=1e-8
    )
    rho = np.full(8, 0.01)
    gradient = -np.ones(8)
    with pytest.raises(ValueError, match="unreachable inside the move box"):
        backend.propose(
            rho=rho,
            objective_gradient=gradient,
            constraint_gradients={},
            constraint_values={},
            move_radius=0.05,  # too tight to reach 0.99 projection
            backend_state={},
        )


def test_target_out_of_range_rejected():
    with pytest.raises(ValueError, match="within"):
        ProjectedVolumeTargetBackend(
            transform=_transform(b=0.0, q=0.0), target=0.0
        )
    with pytest.raises(ValueError, match="tolerance"):
        ProjectedVolumeTargetBackend(
            transform=_transform(b=0.0, q=0.0), target=0.5, tolerance=0.0
        )
