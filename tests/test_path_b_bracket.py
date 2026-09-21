"""Tests for the Path B centered FD bracket (PQ0.1 4.5)."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.path_b_bracket import (
    BracketSpec,
    PathBBracketError,
    evaluate_path_b_bracket,
)


class _Values:
    def __init__(self, objective: float) -> None:
        self.objective = objective


def _linear_evaluator(slope: float):
    def evaluate_values(rho: np.ndarray) -> _Values:
        return _Values(float(slope * np.sum(rho)))

    return evaluate_values


def test_descent_sign_match_passes_and_records_both_sides():
    spec = BracketSpec(epsilon=1e-3, noise_floor_abs=1e-9)
    rho = np.full(4, 0.5)
    delta = np.full(4, 0.1)
    gradient = np.full(4, -1.0)  # dJ/drho = -1 -> descent means increasing rho
    outcome = evaluate_path_b_bracket(
        spec=spec,
        parent_rho=rho,
        parent_gradient=gradient,
        proposal_delta=delta,
        active=np.ones(4, dtype=bool),
        evaluate_values=_linear_evaluator(-1.0),
    )
    assert outcome.ok is True
    assert outcome.reason == "descent_sign_match"
    assert outcome.d_adj < 0.0 and outcome.d_fd < 0.0
    assert outcome.plus_rho_sha256 and outcome.minus_rho_sha256


def test_sign_mismatch_is_rejected():
    spec = BracketSpec(epsilon=1e-3, noise_floor_abs=1e-9)
    rho = np.full(4, 0.5)
    delta = np.full(4, 0.1)
    # analytic says descent while the primal response increases with rho
    outcome = evaluate_path_b_bracket(
        spec=spec,
        parent_rho=rho,
        parent_gradient=np.full(4, -1.0),
        proposal_delta=delta,
        active=np.ones(4, dtype=bool),
        evaluate_values=_linear_evaluator(+1.0),
    )
    assert outcome.ok is False
    assert outcome.reason == "not_a_descent_direction"
    assert outcome.d_adj < 0.0 < outcome.d_fd


def test_below_noise_floor_is_rejected():
    spec = BracketSpec(epsilon=1e-6, noise_floor_abs=1.0)
    outcome = evaluate_path_b_bracket(
        spec=spec,
        parent_rho=np.full(4, 0.5),
        parent_gradient=np.full(4, -1.0),
        proposal_delta=np.full(4, 0.1),
        active=np.ones(4, dtype=bool),
        evaluate_values=_linear_evaluator(-1.0),
    )
    assert outcome.ok is False
    assert outcome.reason == "below_noise_floor"


def test_asymmetric_bounds_are_rejected_without_clipping():
    spec = BracketSpec(epsilon=0.1, noise_floor_abs=1e-9)
    outcome = evaluate_path_b_bracket(
        spec=spec,
        parent_rho=np.full(4, 0.95),
        parent_gradient=np.full(4, -1.0),
        proposal_delta=np.full(4, 0.1),
        active=np.ones(4, dtype=bool),
        evaluate_values=_linear_evaluator(-1.0),
    )
    assert outcome.ok is False
    assert outcome.reason.startswith("bracket_bounds_asymmetric")
    assert outcome.d_fd is None  # no evaluation happened


def test_zero_direction_and_invalid_spec_are_rejected():
    spec = BracketSpec(epsilon=1e-3, noise_floor_abs=1e-9)
    outcome = evaluate_path_b_bracket(
        spec=spec,
        parent_rho=np.full(4, 0.5),
        parent_gradient=np.full(4, -1.0),
        proposal_delta=np.zeros(4),
        active=np.ones(4, dtype=bool),
        evaluate_values=_linear_evaluator(-1.0),
    )
    assert outcome.ok is False
    assert outcome.reason == "zero_direction"

    with pytest.raises(PathBBracketError, match="epsilon"):
        BracketSpec(epsilon=0.0, noise_floor_abs=1e-9)
    with pytest.raises(PathBBracketError, match="noise floor"):
        BracketSpec(epsilon=1e-3, noise_floor_abs=-1.0)
    with pytest.raises(PathBBracketError, match="bounds"):
        BracketSpec(epsilon=1e-3, noise_floor_abs=1e-9, lower=1.0, upper=0.0)
