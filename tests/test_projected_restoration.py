"""Tests for the projected-volume restoration backends (Phase 1 + Phase 2)."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.projected_restoration import (
    ProjectedVolumeRestorationBackend,
    VolumeCorrectedObjectiveBackend,
)

SHAPE = (6, 5, 4)


def _flat(x):
    return np.asarray(x).ravel(order="F")


def _masks():
    active = np.zeros(SHAPE, dtype=bool)
    active[2:4, 1:4, 1:3] = True
    forbidden = np.zeros(SHAPE, dtype=bool)
    forbidden[0, 0, 0] = True
    fixed = np.zeros(SHAPE, dtype=bool)
    fixed[5, 4, 3] = True
    joint = active & ~forbidden & ~fixed
    return {"active": _flat(joint), "forbidden": _flat(forbidden), "fixed": _flat(fixed)}


def _transform(b: float, q: float, radius_m: float = 0.05):
    masks = _masks()
    return DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=masks["active"],
        filter=ConeFilter(SHAPE, 0.05, masks["active"], radius_m=radius_m),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    ), masks


def _rho(masks, value: float = 0.3):
    rho = np.full(masks["active"].shape, value, dtype=np.float64)
    rho[masks["fixed"]] = 1.0
    return rho


def _phi(transform, rho):
    return float(
        np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)[
            transform.active
        ].mean()
    )


def _props(**kwargs):
    return dict(
        objective_gradient=None,
        constraint_gradients={},
        constraint_values={},
        move_radius=0.05,
        backend_state={},
        **kwargs,
    )


def test_phase1_bisects_kappa_to_target_in_one_step():
    transform, masks = _transform(b=4.0, q=15.0)
    rho = _rho(masks, 0.3)
    upper = np.clip(rho + 0.05, 0.0, 1.0)
    phi_hi = _phi(transform, upper)
    target = 0.5 * (_phi(transform, rho) + phi_hi)
    backend = ProjectedVolumeRestorationBackend(transform=transform, target=target)
    proposal = backend.propose(rho=rho, **_props())
    stepped = rho + proposal.delta
    assert proposal.metadata["bracketed"] is True
    assert proposal.metadata["frontier_step"] is False
    assert abs(_phi(transform, stepped) - target) <= 1e-4


def test_phase1_step_far_from_threshold_uses_frontier_policy():
    transform, masks = _transform(b=16.0, q=100.0)
    rho = _rho(masks, 0.02)
    backend = ProjectedVolumeRestorationBackend(transform=transform, target=0.9)
    proposal = backend.propose(rho=rho, **_props())
    assert proposal.metadata["bracketed"] is False
    assert proposal.metadata["frontier_step"] is True
    phi_front = _phi(transform, rho + proposal.delta)
    phi_design = _phi(transform, rho)
    assert phi_front > phi_design
    # the frontier is the per-cell move box: values + move radius
    upper = np.clip(rho + 0.05, 0.0, 1.0)
    stepped = rho + proposal.delta
    assert np.all(stepped <= upper + 1e-12)
    assert np.all(stepped >= rho - 1e-12)


def test_phase1_maintains_target_already_reached():
    transform, masks = _transform(b=4.0, q=15.0)
    rho = _rho(masks, 0.3)
    backend = ProjectedVolumeRestorationBackend(
        transform=transform, target=_phi(transform, rho)
    )
    proposal = backend.propose(rho=rho, **_props())
    assert proposal.metadata["maintained_without_step"] is True
    assert float(np.max(np.abs(proposal.delta))) == 0.0


def test_phase1_target_above_current_untouched_by_design_basis_judgement():
    transform, masks = _transform(b=8.0, q=30.0)
    rho = _rho(masks, 0.3)
    backend = ProjectedVolumeRestorationBackend(
        transform=transform, target=_phi(transform, rho) + 0.005
    )
    proposal = backend.propose(rho=rho, **_props())
    stepped = rho + proposal.delta
    assert proposal.metadata["bracketed"] is True
    assert abs(_phi(transform, stepped) - backend.target) <= 1e-4
    non_active = ~transform.active
    assert float(np.max(np.abs(stepped[non_active] - rho[non_active]))) == 0.0


def test_phase2_corrects_objective_proposal_back_to_target():
    transform, masks = _transform(b=8.0, q=30.0)
    rho = _rho(masks, 0.3)
    grad = np.zeros(masks["active"].shape, dtype=np.float64)
    grad[masks["active"]] = -1.0
    target = _phi(transform, rho)
    backend = VolumeCorrectedObjectiveBackend(transform=transform, target=target)
    proposal = backend.propose(
        rho=rho,
        objective_gradient=grad,
        constraint_gradients={},
        constraint_values={},
        move_radius=0.05,
        backend_state={},
    )
    stepped = rho + proposal.delta
    assert proposal.metadata["objective_step_taken"] is True
    assert abs(_phi(transform, stepped) - target) <= 1e-4
    non_active = ~transform.active
    assert float(np.max(np.abs(stepped[non_active] - rho[non_active]))) <= 1e-12


def test_phase2_fails_closed_when_correction_cannot_reach_target():
    transform, masks = _transform(b=16.0, q=100.0)
    rho = _rho(masks, 0.05)
    grad = np.zeros(masks["active"].shape, dtype=np.float64)
    grad[masks["active"]] = +1.0  # penalized everywhere: candidate only loses material
    backend = VolumeCorrectedObjectiveBackend(
        transform=transform, target=_phi(transform, rho) + 0.1
    )
    with pytest.raises(ValueError, match="below the target"):
        backend.propose(
            rho=rho,
            objective_gradient=grad,
            constraint_gradients={},
            constraint_values={},
            move_radius=0.05,
            backend_state={},
        )


def test_phase1_monotonic_ledger_failure_is_fail_closed():
    sweep = __import__("cfd_sdf.projected_restoration", fromlist=["_MonotoneSweep"])._MonotoneSweep()
    sweep.add(0.0, 0.2)
    sweep.add(0.1, 0.3)
    with pytest.raises(ValueError, match="monotone"):
        sweep.add(0.05, 0.1)
