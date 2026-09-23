"""Tests for the PQ3.3b stopped-state D0 diagnosis (no OpenFOAM)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.phase2_policy import evaluate_phase2_candidate  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from scripts.pq3_3b_stopped_state_d0_2026_09 import (  # noqa: E402
    _array_sha256,
    _fd_check_gradV,
    _norms,
    alpha_diagnosis,
)

SHAPE = (6, 5, 4)


def _transform(b: float = 8.0, q: float = 30.0):
    act = np.zeros(SHAPE, dtype=bool)
    act[2:4, 1:4, 1:3] = True
    active = np.asarray(act).ravel(order="F")
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(SHAPE, 0.05, active, radius_m=0.05),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )
    return transform, active


class _Result:
    """OracleResult stand-in for the equivalence arena (no solver)."""

    def __init__(self, objective, gradient=None, downforce=None):
        self.objective = objective
        self.objective_gradient = gradient
        self.gradient_space = "rho_design" if gradient is not None else None
        self.adjoint_status = "converged" if gradient is not None else None
        self.primal_converged = True
        self.primal_artifact = {
            "artifact": {"summary": {"downforce_coefficient": downforce}}
        }


def _phi(transform, rho, active):
    return float(
        np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)[active].mean()
    )


def test_norms_inf_and_l2_match_numpy():
    values = np.array([0.0, 0.5, -0.25, 0.0])
    active = np.array([True, True, False, True])
    norms = _norms(values, active)
    assert norms["inf_norm"] == 0.5
    assert norms["inf_norm_active"] == 0.5
    assert norms["l2_norm"] == pytest.approx(float(np.sqrt(0.25 + 0.0625)))
    assert norms["l2_norm_active"] == pytest.approx(float(np.sqrt(0.25)))


def test_alpha_diagnosis_reproduces_the_registered_candidate_kappa_and_rho():
    transform, active = _transform()
    values = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    values[active] = 0.30
    gradient = np.zeros_like(values)
    gradient[active] = -1.0

    def phi_of(candidate):
        return _phi(transform, candidate, active)

    target = phi_of(values + 0.0)
    alpha = 0.5
    move_limit = 0.05
    diagnosis = alpha_diagnosis(
        transform=transform,
        rho=values,
        grad_j=gradient,
        grad_v=np.zeros_like(values),
        alpha=alpha,
        move_limit=move_limit,
        target=target,
        volume_tolerance=1e-4,
    )

    def evaluate_values(candidate):
        return _Result(objective=-float(np.sum(candidate)))

    def evaluate_trial(candidate):
        return _Result(objective=-float(np.sum(candidate)), downforce=0.0), {
            "downforce_coefficient": 0.0
        }

    candidate, corrected = evaluate_phase2_candidate(
        transform=transform,
        parent_result=_Result(objective=-float(np.sum(values)), gradient=gradient),
        rho_parent=values,
        parent_downforce=0.0,
        alpha=alpha,
        move_limit=move_limit,
        target=target,
        v_max=0.07632566813424899,
        volume_tolerance=1e-4,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        freeze_box_faces=True,
    )
    assert diagnosis["volume_correction"]["bracketed"] is True
    assert candidate.kappa_volume is not None
    assert diagnosis["volume_correction"]["kappa_volume"] == pytest.approx(
        candidate.kappa_volume, abs=0.0
    )
    assert diagnosis["corrected_rho_sha256"] == _array_sha256(corrected)


def test_alpha_diagnosis_flags_the_volume_correction_cancellation():
    transform, active = _transform()
    values = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    values[active] = 0.30
    gradient = np.zeros_like(values)
    gradient[active] = -1.0
    target = _phi(transform, values, active)
    diagnosis = alpha_diagnosis(
        transform=transform,
        rho=values,
        grad_j=gradient,
        grad_v=np.zeros_like(values),
        alpha=0.25,
        move_limit=0.05,
        target=target,
        volume_tolerance=1e-4,
    )
    assert diagnosis["mechanism"] in (
        "volume_correction_cancels_objective_step",
        "corrected_step_machine_scale",
    )
    assert diagnosis["corrected_norms"]["inf_norm"] <= 1e-8


def test_alpha_diagnosis_counts_frozen_box_faces_and_boundary_cells():
    transform, active = _transform()
    values = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    values[active] = 0.30
    ids = np.nonzero(active)[0]
    values[ids[0]] = 0.0
    values[ids[1]] = 1.0
    diagnosis = alpha_diagnosis(
        transform=transform,
        rho=values,
        grad_j=-np.ones_like(values),
        grad_v=np.zeros_like(values),
        alpha=0.5,
        move_limit=0.05,
        target=_phi(transform, values, active),
        volume_tolerance=1e-4,
    )
    assert diagnosis["frozen_box_face_cells"] == 2
    assert diagnosis["active_cells_at_zero"] == 1
    assert diagnosis["active_cells_at_one"] == 1
    assert diagnosis["corrected_mask_drift_max"] == 0.0


def test_alpha_diagnosis_records_out_of_range_target():
    transform, active = _transform()
    values = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    values[active] = 0.30
    diagnosis = alpha_diagnosis(
        transform=transform,
        rho=values,
        grad_j=-np.ones_like(values),
        grad_v=np.zeros_like(values),
        alpha=0.5,
        move_limit=0.05,
        target=0.99,
        volume_tolerance=1e-4,
    )
    assert diagnosis["mechanism"] == "volume_correction_out_of_range"
    assert diagnosis["corrected_norms"] is None


def test_fd_gradV_interior_variant_matches_the_pullback():
    transform, active = _transform()
    values = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    values[active] = np.linspace(0.02, 0.45, int(active.sum()))
    indicator = np.zeros_like(values)
    indicator[active] = 1.0 / float(np.count_nonzero(active))
    grad_v = transform.pullback_from_projected(values, indicator)
    check = _fd_check_gradV(transform, values, grad_v, active, 1e-5)
    assert check["applicable"] is True
    assert check["interior_only"]["clipped_probe_cells"] == 0
    assert check["interior_only"]["relative_error"] < 1e-6
