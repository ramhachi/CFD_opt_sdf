"""Solver-neutral gradient-engine contract.

A gradient engine turns a qualified primal evaluation into per-response
field gradients ``d(response)/d(phi)``.  Reverse AD, a custom discrete
adjoint and centered FD are interchangeable engines; FD remains the
permanent independent verification oracle.

``qualified`` defaults to ``False`` and only a registered qualification
procedure may set it.  An unqualified gradient may be reported as evidence
but must not be consumed by an optimizer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np

from ..design.sdf_state import SDFDesignState
from ..oracles.base import PrimalEvaluation
from ..runtime.fingerprint import canonical_json_sha256, validate_sha256_hex


def _validate_field_gradient(array: Any, response_id: str) -> np.ndarray:
    gradient = np.asarray(array, dtype=np.float64)
    if gradient.ndim != 3:
        raise ValueError(f"gradient {response_id!r} must be a 3D array")
    if not np.isfinite(gradient).all():
        raise ValueError(f"gradient {response_id!r} must be finite")
    return np.ascontiguousarray(gradient)


def _gradient_sha256(gradient: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(gradient, dtype="<f8").tobytes()).hexdigest()


@dataclass(frozen=True)
class GradientRequest:
    """Which response gradients are requested from which backend."""

    response_ids: tuple[str, ...]
    backend_identity: str
    notes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.response_ids or len(set(self.response_ids)) != len(self.response_ids):
            raise ValueError("response_ids must be non-empty and unique")
        if not isinstance(self.backend_identity, str) or not self.backend_identity.strip():
            raise ValueError("backend_identity must be a non-empty string")
        canonical_json_sha256({"notes": dict(self.notes)})


@dataclass(frozen=True)
class GradientEvaluation:
    """Per-response field gradients bound to one primal evaluation."""

    state_sha256: str
    primal_sha256: str
    response_gradients: Mapping[str, np.ndarray]
    backend_fingerprint_sha256: str
    qualified: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_sha256_hex(self.state_sha256, field_name="state_sha256")
        validate_sha256_hex(self.primal_sha256, field_name="primal_sha256")
        validate_sha256_hex(
            self.backend_fingerprint_sha256, field_name="backend_fingerprint_sha256"
        )
        if not self.response_gradients:
            raise ValueError("response_gradients must not be empty")
        shapes = {
            _validate_field_gradient(array, response_id).shape
            for response_id, array in self.response_gradients.items()
        }
        if len(shapes) != 1:
            raise ValueError("all response gradients must share one shape")
        if not isinstance(self.qualified, bool):
            raise ValueError("qualified must be a bool")
        canonical_json_sha256({"evidence": dict(self.evidence)})

    def gradient(self, response_id: str) -> np.ndarray:
        if response_id not in self.response_gradients:
            raise KeyError(f"gradient evaluation has no response {response_id!r}")
        return np.asarray(self.response_gradients[response_id], dtype=np.float64)

    def field_shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in next(iter(self.response_gradients.values())).shape)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_sha256": self.state_sha256,
            "primal_sha256": self.primal_sha256,
            "backend_fingerprint_sha256": self.backend_fingerprint_sha256,
            "qualified": bool(self.qualified),
            "response_gradients": {
                response_id: {
                    "shape": [int(value) for value in np.asarray(array).shape],
                    "sha256": _gradient_sha256(np.asarray(array, dtype=np.float64)),
                }
                for response_id, array in self.response_gradients.items()
            },
            "evidence": dict(self.evidence),
        }

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


@runtime_checkable
class GradientEngine(Protocol):
    """A differentiable backend; it never forms the canonical objective itself."""

    def gradient(
        self,
        state: SDFDesignState,
        primal: PrimalEvaluation,
        responses: tuple[str, ...],
    ) -> GradientEvaluation: ...


__all__ = ["GradientEngine", "GradientEvaluation", "GradientRequest"]
