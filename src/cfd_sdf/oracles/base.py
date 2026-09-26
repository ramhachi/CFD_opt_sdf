"""Solver-neutral primal-oracle contract.

A backend evaluates primitive responses (drag, downforce, and later a
volume-like primitive) at an :class:`SDFDesignState`.  A solver never owns
canonical optimization semantics: the ProblemSpec/compiler layer forms the
objective and constraints from these primitives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from ..design.sdf_state import SDFDesignState
from ..runtime.fingerprint import canonical_json_sha256, validate_sha256_hex

PRIMITIVE_RESPONSES: tuple[str, ...] = ("drag", "downforce")


@dataclass(frozen=True)
class ResponseRequest:
    """Which primitives to evaluate and which backend is asked to do it."""

    response_ids: tuple[str, ...]
    backend_identity: str
    flow_case_id: str | None = None
    notes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.response_ids or len(set(self.response_ids)) != len(self.response_ids):
            raise ValueError("response_ids must be non-empty and unique")
        if not isinstance(self.backend_identity, str) or not self.backend_identity.strip():
            raise ValueError("backend_identity must be a non-empty string")
        if self.flow_case_id is not None and not str(self.flow_case_id).strip():
            raise ValueError("flow_case_id must be non-empty when provided")
        if not isinstance(self.notes, Mapping):
            raise ValueError("notes must be a mapping")
        canonical_json_sha256({"notes": dict(self.notes)})

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_ids": list(self.response_ids),
            "backend_identity": self.backend_identity,
            "flow_case_id": self.flow_case_id,
            "notes": dict(self.notes),
        }


@dataclass(frozen=True)
class PrimalEvaluation:
    """Primitive response values plus the identity of the backend that produced them."""

    state_sha256: str
    responses: Mapping[str, float]
    converged: bool
    backend_fingerprint_sha256: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_sha256_hex(self.state_sha256, field_name="state_sha256")
        validate_sha256_hex(
            self.backend_fingerprint_sha256, field_name="backend_fingerprint_sha256"
        )
        if not self.responses:
            raise ValueError("responses must not be empty")
        for response_id, value in self.responses.items():
            if not isinstance(response_id, str) or not response_id.strip():
                raise ValueError("response ids must be non-empty strings")
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"response {response_id!r} must be a finite number")
        if not isinstance(self.converged, bool):
            raise ValueError("converged must be a bool")
        canonical_json_sha256({"evidence": dict(self.evidence)})

    def response(self, response_id: str) -> float:
        if response_id not in self.responses:
            raise KeyError(f"primal evaluation has no response {response_id!r}")
        return float(self.responses[response_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_sha256": self.state_sha256,
            "responses": {key: float(value) for key, value in self.responses.items()},
            "converged": bool(self.converged),
            "backend_fingerprint_sha256": self.backend_fingerprint_sha256,
            "evidence": dict(self.evidence),
        }

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


@runtime_checkable
class ResponseOracle(Protocol):
    """A primal CFD backend.  Backends return primitives, not objectives."""

    def evaluate(self, state: SDFDesignState, request: ResponseRequest) -> PrimalEvaluation: ...


__all__ = ["PRIMITIVE_RESPONSES", "PrimalEvaluation", "ResponseOracle", "ResponseRequest"]
