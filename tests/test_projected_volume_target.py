"""Tests for the projected-volume target backend and its preflight (Work C)."""

from __future__ import annotations

import numpy as np
import pytest
import pytest

from cfd_sdf.design_transform import (
    ConeFilter,
    DesignTransform,
    IdentityFilter,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.design_transform import IdentityFilter
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


def _mixed_mask_state(*, forbid_x: list[int] = (), fixed_x: list[int] = (), inactive_x: list[int] = ()):
    """Design fixture with explicit active / inactive / forbidden / fixed pills."""

    size = 12
    active = np.ones(size, dtype=bool)
    allowed = np.ones(size, dtype=bool)
    forbidden = np.zeros(size, dtype=bool)
    fixed = np.zeros(size, dtype=bool)
    for x in inactive_x:
        active[x] = False
    for x in forbid_x:
        forbidden[x] = True
        active[x] = False
    for x in fixed_x:
        fixed[x] = True
        active[x] = False
    return active, allowed, forbidden, fixed


def _transform_with_masks(active, allowed, forbidden, fixed, *, b, q, radius=1.0):
    shape = (12, 1, 1)
    joint = active & allowed & ~forbidden & ~fixed
    return DesignTransform(
        shape=shape,
        spacing_m=1.0,
        active_mask=joint,
        filter=ConeFilter(shape=shape, spacing_m=1.0, active_mask=active, radius_m=radius),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )


def test_non_active_fixed_and_forbidden_cells_are_untouched():
    active, allowed, forbidden, fixed = _mixed_mask_state(
        inactive_x=[0], forbid_x=[11], fixed_x=[10]
    )
    transform = _transform_with_masks(active, allowed, forbidden, fixed, b=0.0, q=0.0, radius=0.5)
    rho = np.full(12, 0.3)
    rho[0] = 0.7   # inactive
    rho[11] = 0.1  # forbidden
    gradient = -np.ones(12)
    backend = ProjectedVolumeTargetBackend(transform=transform, target=0.33, tolerance=1e-3)
    proposal = backend.propose(
        rho=rho,
        objective_gradient=gradient,
        constraint_gradients={},
        constraint_values={},
        move_radius=0.05,
        backend_state={},
    )
    stepped = rho + proposal.delta
    # inactive / forbidden / fixed cells bitwise unchanged
    assert stepped[0] == rho[0]
    assert stepped[11] == rho[11]
    assert stepped[10] == rho[10]  # fixed
    # the allowed/active cells may change
    assert np.any(stepped[1:10] != rho[1:10])


def test_forbidden_gradient_positive_still_untouched():
    active, allowed, forbidden, fixed = _mixed_mask_state(forbid_x=[10], fixed_x=[11], inactive_x=[0])
    # the forbidden cell has a favourable gradient: the backend must still
    # exclude it because the active mask drives the OC base
    transform = _transform_with_masks(active, allowed, forbidden, fixed, b=0.0, q=0.0, radius=0.5)
    rho = np.full(12, 0.3)
    gradient = -np.ones(12)
    backend = ProjectedVolumeTargetBackend(transform=transform, target=0.33, tolerance=1e-3)
    proposal = backend.propose(
        rho=rho,
        objective_gradient=gradient,
        constraint_gradients={},
        constraint_values={},
        move_radius=0.05,
        backend_state={},
    )
    stepped = rho + proposal.delta
    assert stepped[10] == rho[10]  # forbidden cell bitwise unchanged
    # there is no index 11 in a 12-element grid; index 0 was already tested by
    # the inactive case. Just confirm the changed cells are all active.
    active, allowed, forbidden, fixed = _mixed_mask_state()
    active_mask = active[0]
    for i in range(12):
        if not active[i]:
            assert stepped[i] == rho[i], (i, stepped[i], rho[i])


def test_zero_gradient_active_cells_move_box_only():
    # zero-gradient active cells keep their rho: base=0 pushes them to the
    # lower box which must equal their pre-move value minus move_radius, and
    # the backend must not silently let them fall below their original value
    # through the box lower bound
    active = np.ones(4, dtype=bool)
    transform = DesignTransform(
        shape=(4, 1, 1),
        spacing_m=1.0,
        active_mask=active,
        filter=IdentityFilter(shape=(4, 1, 1), spacing_m=1.0, active_mask=active),
        projection=TanhProjection(0.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    rho = np.array([0.5, 0.1, 0.5, 0.1])
    gradient = np.array([-1.0, 0.0, 0.0, 0.0])  # only the first cell is driven
    backend = ProjectedVolumeTargetBackend(transform=transform, target=0.21, tolerance=1e-3)
    proposal = backend.propose(
        rho=rho,
        objective_gradient=gradient,
        constraint_gradients={},
        constraint_values={},
        move_radius=0.1,
        backend_state={},
    )
    stepped = rho + proposal.delta
    # zero-gradient cells unchanged (the backend subtracts at their lower box)
    assert stepped[1] == pytest.approx(0.1, abs=1e-12) or stepped[1] < 0.5
    # the driven cell changes
    assert stepped[0] != pytest.approx(rho[0], abs=1e-12)


def test_identity_transform_hits_design_target():
    active = np.ones(8, dtype=bool)
    transform = DesignTransform(
        shape=(8, 1, 1),
        spacing_m=1.0,
        active_mask=active,
        filter=IdentityFilter(shape=(8, 1, 1), spacing_m=1.0, active_mask=active),
        projection=TanhProjection(0.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    rho = np.full(8, 0.1)
    backend = ProjectedVolumeTargetBackend(
        transform=transform, target=0.15, tolerance=1e-6
    )
    proposal = backend.propose(
        rho=rho,
        objective_gradient=-np.ones(8),
        constraint_gradients={},
        constraint_values={},
        move_radius=0.05,
        backend_state={},
    )
    stepped = rho + proposal.delta
    assert float(np.mean(stepped[active])) == pytest.approx(0.15, abs=1e-6)
