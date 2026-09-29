from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.gradients import (
    CenteredDirectionalFD,
    DirectionalComparisonError,
    GradientEvaluation,
    compare_field_gradient_to_centered_fd,
    field_direction_sha256,
)
from cfd_sdf.oracles.base import PrimalEvaluation


RESPONSE_SEMANTICS_SHA = "12" * 32
GRADIENT_BACKEND_SHA = "34" * 32
FD_BACKEND_SHA = "56" * 32
QUALIFICATION_SHA = "78" * 32
DIRECTION_ID = "registered_direction_1"


def _case(
    *,
    response_id: str = "drag",
    gradient_value: float = 2.0,
    fd_value: float | None = None,
    absolute_noise_floor: float = 1.0e-8,
    qualified_gradient: bool = True,
    qualified_fd: bool = True,
) -> tuple[
    SDFDesignState,
    PrimalEvaluation,
    GradientEvaluation,
    np.ndarray,
    CenteredDirectionalFD,
]:
    state = SDFDesignState.create(
        phi=np.zeros((2, 2, 2), dtype=np.float32),
        origin_m=(0.0, 0.0, 0.0),
        spacing_m=0.1,
        narrow_band_width_m=0.2,
    )
    primal = PrimalEvaluation(
        state_sha256=state.state_sha256,
        responses={"drag": 3.0, "downforce": 4.0},
        converged=True,
        backend_fingerprint_sha256=GRADIENT_BACKEND_SHA,
    )
    gradients = {
        "drag": np.full(state.shape, gradient_value, dtype=np.float64),
        "downforce": np.full(state.shape, gradient_value, dtype=np.float64),
    }
    gradient = GradientEvaluation(
        state_sha256=state.state_sha256,
        primal_sha256=primal.sha256(),
        response_gradients=gradients,
        backend_fingerprint_sha256=GRADIENT_BACKEND_SHA,
        qualified=qualified_gradient,
        evidence={
            "qualification_evidence_sha256": QUALIFICATION_SHA,
            "response_semantics_sha256": {
                "drag": RESPONSE_SEMANTICS_SHA,
                "downforce": RESPONSE_SEMANTICS_SHA,
            },
        },
    )
    direction = np.ones(state.shape, dtype=np.float64)
    fd = CenteredDirectionalFD(
        state_sha256=state.state_sha256,
        direction_id=DIRECTION_ID,
        direction_sha256=field_direction_sha256(direction),
        response_id=response_id,
        response_semantics_sha256=RESPONSE_SEMANTICS_SHA,
        derivative=(gradient_value * direction.size if fd_value is None else fd_value),
        epsilon=1.0e-3,
        absolute_noise_floor=absolute_noise_floor,
        relative_error_tolerance=0.05,
        backend_fingerprint_sha256=FD_BACKEND_SHA,
        qualification_evidence_sha256=QUALIFICATION_SHA,
        qualified=qualified_fd,
    )
    return state, primal, gradient, direction, fd


def _compare(state, primal, gradient, direction, fd):
    return compare_field_gradient_to_centered_fd(
        state=state,
        primal=primal,
        gradient=gradient,
        direction=direction,
        direction_id=DIRECTION_ID,
        response_semantics_sha256=RESPONSE_SEMANTICS_SHA,
        fd=fd,
    )


@pytest.mark.parametrize(
    ("response_id", "expected"), (("drag", 16.0), ("downforce", 16.0))
)
def test_matching_raw_response_gradient_passes_and_binds_independent_backends(
    response_id, expected
):
    state, primal, gradient, direction, fd = _case(response_id=response_id)

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is True
    assert result.reason is None
    assert result.response_id == response_id
    assert result.gradient_directional_derivative == pytest.approx(expected)
    assert result.centered_fd_derivative == pytest.approx(expected)
    assert result.sign_match is True
    assert result.absolute_error == pytest.approx(0.0)
    assert result.relative_error == pytest.approx(0.0)
    assert result.gradient_backend_fingerprint_sha256 == GRADIENT_BACKEND_SHA
    assert result.fd_backend_fingerprint_sha256 == FD_BACKEND_SHA
    assert result.gradient_backend_fingerprint_sha256 != result.fd_backend_fingerprint_sha256


def test_sign_flip_fails_with_sign_and_error_recorded():
    state, primal, gradient, direction, fd = _case(fd_value=-16.0)

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is False
    assert result.reason == "sign_mismatch"
    assert result.gradient_sign == 1
    assert result.fd_sign == -1
    assert result.sign_match is False
    assert result.absolute_error == pytest.approx(32.0)
    assert result.relative_error == pytest.approx(2.0)


def test_magnitude_error_fails_relative_rule():
    state, primal, gradient, direction, fd = _case(fd_value=14.0)

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is False
    assert result.reason == "relative_error"
    assert result.sign_match is True
    assert result.absolute_error == pytest.approx(2.0)
    assert result.relative_error == pytest.approx(2.0 / 14.0)
    assert result.error_rule == "relative"


def test_near_zero_fd_uses_only_registered_absolute_noise_floor():
    state, primal, gradient, direction, fd = _case(
        gradient_value=0.0, fd_value=5.0e-9, absolute_noise_floor=1.0e-8
    )

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is True
    assert result.error_rule == "absolute_noise_floor"
    assert result.tolerance_applied == pytest.approx(1.0e-8)
    assert result.absolute_error == pytest.approx(5.0e-9)
    assert result.relative_error is None
    assert result.sign_match is None
    assert result.gradient_sign == 0
    assert result.fd_sign == 1


def test_near_zero_fd_outside_absolute_noise_floor_fails():
    state, primal, gradient, direction, fd = _case(
        gradient_value=1.0e-8, fd_value=5.0e-9, absolute_noise_floor=1.0e-8
    )

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is False
    assert result.reason == "absolute_error"
    assert result.absolute_error > result.tolerance_applied
    assert result.relative_error is None


def test_state_direction_and_response_semantics_mismatches_fail_closed():
    state, primal, gradient, direction, fd = _case()
    with pytest.raises(DirectionalComparisonError, match="FD state SHA"):
        _compare(state, primal, gradient, direction, replace(fd, state_sha256="ab" * 32))

    changed_direction = direction.copy()
    changed_direction[0, 0, 0] = 2.0
    with pytest.raises(DirectionalComparisonError, match="direction SHA"):
        _compare(state, primal, gradient, changed_direction, fd)

    with pytest.raises(DirectionalComparisonError, match="direction ID"):
        compare_field_gradient_to_centered_fd(
            state=state,
            primal=primal,
            gradient=gradient,
            direction=direction,
            direction_id="a_different_direction",
            response_semantics_sha256=RESPONSE_SEMANTICS_SHA,
            fd=fd,
        )

    mismatched_fd_semantics = replace(fd, response_semantics_sha256="cd" * 32)
    with pytest.raises(DirectionalComparisonError, match="response semantics"):
        _compare(state, primal, gradient, direction, mismatched_fd_semantics)

    mismatched_gradient_semantics = replace(
        gradient,
        evidence={
            **gradient.evidence,
            "response_semantics_sha256": {"drag": "cd" * 32},
        },
    )
    with pytest.raises(DirectionalComparisonError, match="gradient response semantics"):
        _compare(state, primal, mismatched_gradient_semantics, direction, fd)


@pytest.mark.parametrize(
    ("qualified_gradient", "qualified_fd", "message"),
    ((False, True, "gradient is not qualified"), (True, False, "centered FD is not qualified")),
)
def test_unqualified_gradient_or_fd_fails_closed(qualified_gradient, qualified_fd, message):
    state, primal, gradient, direction, fd = _case(
        qualified_gradient=qualified_gradient, qualified_fd=qualified_fd
    )

    with pytest.raises(DirectionalComparisonError, match=message):
        _compare(state, primal, gradient, direction, fd)


def test_zero_direction_and_missing_gradient_qualification_evidence_fail_closed():
    state, primal, gradient, direction, fd = _case()
    with pytest.raises(DirectionalComparisonError, match="non-zero"):
        _compare(state, primal, gradient, np.zeros(state.shape), fd)

    gradient_without_evidence = replace(gradient, evidence={})
    with pytest.raises(DirectionalComparisonError, match="qualification evidence"):
        _compare(state, primal, gradient_without_evidence, direction, fd)


def test_comparison_does_not_promote_the_field_gradient():
    state, primal, gradient, direction, fd = _case()
    gradient_sha256 = gradient.sha256()

    result = _compare(state, primal, gradient, direction, fd)

    assert result.passed is True
    assert gradient.qualified is True
    assert gradient.sha256() == gradient_sha256
