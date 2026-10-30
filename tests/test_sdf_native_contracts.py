"""Oracle/gradient protocol and evidence-record contract tests."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.gradients.base import GradientEngine, GradientEvaluation, GradientRequest
from cfd_sdf.oracles.base import PrimalEvaluation, ResponseOracle, ResponseRequest

STATE_SHA = "12" * 32
PRIMAL_SHA = "34" * 32
BACKEND_SHA = "56" * 32


def _field() -> np.ndarray:
    return np.ones((3, 4, 5), dtype=np.float64)


def test_primal_evaluation_validates_and_hashes_deterministically():
    evaluation = PrimalEvaluation(
        state_sha256=STATE_SHA,
        responses={"drag": 1.25, "downforce": 0.75},
        converged=True,
        backend_fingerprint_sha256=BACKEND_SHA,
    )
    assert evaluation.response("downforce") == 0.75
    assert evaluation.sha256() == evaluation.sha256()
    with pytest.raises(KeyError):
        evaluation.response("missing")
    with pytest.raises(ValueError, match="finite"):
        PrimalEvaluation(
            state_sha256=STATE_SHA,
            responses={"drag": float("nan")},
            converged=True,
            backend_fingerprint_sha256=BACKEND_SHA,
        )


def test_response_request_rejects_duplicate_primitives():
    ResponseRequest(response_ids=("drag", "downforce"), backend_identity="waterlily")
    with pytest.raises(ValueError, match="unique"):
        ResponseRequest(response_ids=("drag", "drag"), backend_identity="waterlily")


def test_gradient_evaluation_requires_finite_field_gradients_and_defaults_unqualified():
    evaluation = GradientEvaluation(
        state_sha256=STATE_SHA,
        primal_sha256=PRIMAL_SHA,
        response_gradients={"drag": _field(), "downforce": _field() * -1.0},
        backend_fingerprint_sha256=BACKEND_SHA,
    )
    assert evaluation.qualified is False
    assert evaluation.field_shape() == (3, 4, 5)
    assert set(evaluation.to_dict()["response_gradients"]) == {"drag", "downforce"}
    with pytest.raises(ValueError, match="3D"):
        GradientEvaluation(
            state_sha256=STATE_SHA,
            primal_sha256=PRIMAL_SHA,
            response_gradients={"drag": np.zeros((3, 4))},
            backend_fingerprint_sha256=BACKEND_SHA,
        )
    with pytest.raises(ValueError, match="share one shape"):
        GradientEvaluation(
            state_sha256=STATE_SHA,
            primal_sha256=PRIMAL_SHA,
            response_gradients={"drag": _field(), "downforce": np.zeros((3, 4, 6))},
            backend_fingerprint_sha256=BACKEND_SHA,
        )


def test_protocols_are_runtime_checkable_and_solver_neutral():
    class DummyOracle:
        def evaluate(self, state: SDFDesignState, request: ResponseRequest) -> PrimalEvaluation:
            raise NotImplementedError

    class DummyGradient:
        def gradient(
            self, state: SDFDesignState, primal: PrimalEvaluation, responses: tuple[str, ...]
        ) -> GradientEvaluation:
            raise NotImplementedError

    assert isinstance(DummyOracle(), ResponseOracle)
    assert isinstance(DummyGradient(), GradientEngine)
    assert isinstance(ResponseRequest(response_ids=("drag",), backend_identity="x"), ResponseRequest)
    assert isinstance(
        GradientRequest(response_ids=("drag",), backend_identity="x"), GradientRequest
    )
