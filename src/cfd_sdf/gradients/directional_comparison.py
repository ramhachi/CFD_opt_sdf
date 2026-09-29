"""Solver-neutral comparison of a field gradient with centered directional FD."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

import numpy as np

from ..design.sdf_state import SDFDesignState
from ..oracles.base import PrimalEvaluation
from ..runtime.fingerprint import canonical_json_sha256, validate_sha256_hex
from .base import GradientEvaluation


class DirectionalComparisonError(ValueError):
    """A directional comparison input is missing, unqualified, or mismatched."""


def field_direction_sha256(direction: Any) -> str:
    """Hash a finite 3D direction in C-order float64 without scaling it."""

    values = np.asarray(direction, dtype=np.float64)
    if values.ndim != 3 or not np.isfinite(values).all():
        raise DirectionalComparisonError("direction must be a finite 3D field")
    if not np.any(values):
        raise DirectionalComparisonError("direction must be non-zero")
    metadata = json.dumps(
        {"schema_version": 1, "shape": list(values.shape), "dtype": "<f8", "order": "C"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(metadata)
    digest.update(b"\x00direction\x00")
    digest.update(np.ascontiguousarray(values, dtype="<f8").tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class CenteredDirectionalFD:
    """One centered-FD row from an independently qualified campaign.

    ``response_semantics_sha256`` identifies the raw physical response
    definition (including its flow case, force projection, and units). The
    qualification digest must identify the preregistered evidence that
    supplied this derivative and its thresholds.
    """

    state_sha256: str
    direction_id: str
    direction_sha256: str
    response_id: str
    response_semantics_sha256: str
    derivative: float
    epsilon: float
    absolute_noise_floor: float
    relative_error_tolerance: float
    backend_fingerprint_sha256: str
    qualification_evidence_sha256: str
    qualified: bool = False

    def __post_init__(self) -> None:
        for name in (
            "state_sha256",
            "direction_sha256",
            "response_semantics_sha256",
            "backend_fingerprint_sha256",
            "qualification_evidence_sha256",
        ):
            validate_sha256_hex(getattr(self, name), field_name=name)
        for name in ("direction_id", "response_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise DirectionalComparisonError(f"{name} must be non-empty")
        if not math.isfinite(float(self.derivative)):
            raise DirectionalComparisonError("FD derivative must be finite")
        if not math.isfinite(float(self.epsilon)) or float(self.epsilon) <= 0.0:
            raise DirectionalComparisonError("FD epsilon must be finite and positive")
        if (
            not math.isfinite(float(self.absolute_noise_floor))
            or float(self.absolute_noise_floor) < 0.0
        ):
            raise DirectionalComparisonError(
                "absolute_noise_floor must be finite and non-negative"
            )
        if (
            not math.isfinite(float(self.relative_error_tolerance))
            or float(self.relative_error_tolerance) < 0.0
        ):
            raise DirectionalComparisonError(
                "relative_error_tolerance must be finite and non-negative"
            )
        if not isinstance(self.qualified, bool):
            raise DirectionalComparisonError("qualified must be a bool")

    def sha256(self) -> str:
        return canonical_json_sha256(asdict(self))


@dataclass(frozen=True)
class DirectionalGradientComparison:
    """One response/direction result; it does not qualify the whole gradient."""

    passed: bool
    reason: str | None
    state_sha256: str
    direction_id: str
    direction_sha256: str
    response_id: str
    response_semantics_sha256: str
    gradient_sha256: str
    gradient_primal_sha256: str
    gradient_backend_fingerprint_sha256: str
    fd_sha256: str
    fd_backend_fingerprint_sha256: str
    fd_qualification_evidence_sha256: str
    epsilon: float
    gradient_directional_derivative: float
    centered_fd_derivative: float
    gradient_sign: Literal[-1, 0, 1]
    fd_sign: Literal[-1, 0, 1]
    sign_match: bool | None
    absolute_error: float
    relative_error: float | None
    error_rule: Literal["absolute_noise_floor", "relative"]
    tolerance_applied: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


def compare_field_gradient_to_centered_fd(
    *,
    state: SDFDesignState,
    primal: PrimalEvaluation,
    gradient: GradientEvaluation,
    direction: Any,
    direction_id: str,
    response_semantics_sha256: str,
    fd: CenteredDirectionalFD,
) -> DirectionalGradientComparison:
    """Compare ``sum(dR/dphi * dphi)`` to one qualified raw-response FD row.

    Direction values are not normalized or clipped. Near-zero FD rows use
    only their preregistered absolute floor; their sign and relative error are
    reported as unresolved. Gradient and FD backends remain separately bound
    because the FD oracle is independent.
    """

    if not gradient.qualified:
        raise DirectionalComparisonError("gradient is not qualified")
    if not fd.qualified:
        raise DirectionalComparisonError("centered FD is not qualified")
    if not primal.converged:
        raise DirectionalComparisonError("gradient-side primal is not converged")
    if gradient.state_sha256 != state.state_sha256 or primal.state_sha256 != state.state_sha256:
        raise DirectionalComparisonError("gradient-side state SHA does not match state")
    if fd.state_sha256 != state.state_sha256:
        raise DirectionalComparisonError("FD state SHA does not match state")
    if gradient.primal_sha256 != primal.sha256():
        raise DirectionalComparisonError("gradient primal SHA does not match supplied primal")
    if not isinstance(direction_id, str) or not direction_id.strip():
        raise DirectionalComparisonError("direction_id must be non-empty")
    if fd.direction_id != direction_id:
        raise DirectionalComparisonError("direction ID does not match FD reference")
    direction_values = np.asarray(direction, dtype=np.float64)
    direction_sha256 = field_direction_sha256(direction_values)
    if fd.direction_sha256 != direction_sha256:
        raise DirectionalComparisonError("direction SHA does not match FD reference")
    if direction_values.shape != state.phi.shape:
        raise DirectionalComparisonError("direction shape does not match SDF state")
    if response_semantics_sha256 != fd.response_semantics_sha256:
        raise DirectionalComparisonError("response semantics do not match FD reference")
    validate_sha256_hex(response_semantics_sha256, field_name="response_semantics_sha256")
    if fd.response_id not in gradient.response_gradients:
        raise DirectionalComparisonError(f"gradient has no raw response {fd.response_id!r}")
    try:
        primal.response(fd.response_id)
    except KeyError as error:
        raise DirectionalComparisonError(
            f"gradient-side primal has no raw response {fd.response_id!r}"
        ) from error
    if gradient.field_shape() != state.phi.shape:
        raise DirectionalComparisonError("gradient shape does not match SDF state")

    evidence = gradient.evidence
    gradient_qualification = evidence.get("qualification_evidence_sha256")
    if gradient_qualification is None:
        raise DirectionalComparisonError("gradient qualification evidence is missing")
    validate_sha256_hex(gradient_qualification, field_name="gradient qualification evidence SHA")
    semantics_by_response = evidence.get("response_semantics_sha256")
    if not isinstance(semantics_by_response, Mapping):
        raise DirectionalComparisonError("gradient response semantics evidence is missing")
    gradient_semantics = semantics_by_response.get(fd.response_id)
    if gradient_semantics != response_semantics_sha256:
        raise DirectionalComparisonError("gradient response semantics do not match FD reference")

    field_gradient = gradient.gradient(fd.response_id)
    if field_gradient.shape != direction_values.shape:
        raise DirectionalComparisonError("gradient and direction shapes do not match")
    with np.errstate(over="ignore", invalid="ignore"):
        predicted = float(np.sum(field_gradient * direction_values, dtype=np.float64))
    finite_difference = float(fd.derivative)
    if not math.isfinite(predicted):
        raise DirectionalComparisonError("gradient directional derivative is not finite")

    absolute_error = abs(predicted - finite_difference)
    if not math.isfinite(absolute_error):
        raise DirectionalComparisonError("absolute derivative error is not finite")
    gradient_sign: Literal[-1, 0, 1] = 1 if predicted > 0.0 else (-1 if predicted < 0.0 else 0)
    fd_sign: Literal[-1, 0, 1] = (
        1 if finite_difference > 0.0 else (-1 if finite_difference < 0.0 else 0)
    )
    near_zero = abs(finite_difference) <= float(fd.absolute_noise_floor)
    if near_zero:
        relative_error = None
        sign_match = None
        error_rule: Literal["absolute_noise_floor", "relative"] = "absolute_noise_floor"
        tolerance = float(fd.absolute_noise_floor)
        passed = absolute_error <= tolerance
        reason = None if passed else "absolute_error"
    else:
        relative_error = absolute_error / abs(finite_difference)
        sign_match = gradient_sign == fd_sign
        error_rule = "relative"
        tolerance = float(fd.relative_error_tolerance)
        passed = sign_match and relative_error <= tolerance
        reason = None if passed else ("sign_mismatch" if not sign_match else "relative_error")

    return DirectionalGradientComparison(
        passed=passed,
        reason=reason,
        state_sha256=state.state_sha256,
        direction_id=direction_id,
        direction_sha256=direction_sha256,
        response_id=fd.response_id,
        response_semantics_sha256=response_semantics_sha256,
        gradient_sha256=gradient.sha256(),
        gradient_primal_sha256=gradient.primal_sha256,
        gradient_backend_fingerprint_sha256=gradient.backend_fingerprint_sha256,
        fd_sha256=fd.sha256(),
        fd_backend_fingerprint_sha256=fd.backend_fingerprint_sha256,
        fd_qualification_evidence_sha256=fd.qualification_evidence_sha256,
        epsilon=float(fd.epsilon),
        gradient_directional_derivative=predicted,
        centered_fd_derivative=finite_difference,
        gradient_sign=gradient_sign,
        fd_sign=fd_sign,
        sign_match=sign_match,
        absolute_error=absolute_error,
        relative_error=relative_error,
        error_rule=error_rule,
        tolerance_applied=tolerance,
    )


__all__ = [
    "CenteredDirectionalFD",
    "DirectionalComparisonError",
    "DirectionalGradientComparison",
    "compare_field_gradient_to_centered_fd",
    "field_direction_sha256",
]
