"""Path B centered finite-difference bracket (PQ0.1 4.5).

The refined-grid adjoint is a bounded exception (Path B): its magnitude is not
trusted, so every proposal must be bracketed by centered primal finite
differences before a trial can be accepted. The bracket

- normalizes the proposal to ``d_hat = d / ||d||_inf``;
- refuses any epsilon for which ``rho +/- epsilon d_hat`` leaves the declared
  box or masks (no clipping, which would change the direction);
- requires ``|J+ - J-|`` above the registered noise floor;
- requires both ``D_adj = grad(J)^T d_hat`` and
  ``D_FD = (J+ - J-)/(2 epsilon)`` to be negative in the minimization
  convention (descent) with matching signs;
- applies no magnitude correction.

The outcome is an artifact: proposal, parent, epsilon, both run hashes and both
objectives are recorded.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

BRACKET_SCHEMA_VERSION = 1


class PathBBracketError(ValueError):
    """Fail-closed bracket contract violation."""


@dataclass(frozen=True)
class BracketSpec:
    """Registered bracket rule.

    ``epsilon`` is the maximum step; when the symmetric pair does not fit the
    box at that step, the bracket backs off by ``backoff`` until ``min_epsilon``
    before rejecting. The direction is never clipped or renormalized.
    """

    epsilon: float
    noise_floor_abs: float
    lower: float = 0.0
    upper: float = 1.0
    backoff: float = 2.0
    min_epsilon: float | None = None
    schema_version: int = BRACKET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.epsilon <= 0.0 or not np.isfinite(self.epsilon):
            raise PathBBracketError("bracket epsilon must be finite and positive")
        if self.noise_floor_abs < 0.0 or not np.isfinite(self.noise_floor_abs):
            raise PathBBracketError("bracket noise floor must be finite and non-negative")
        if not self.lower < self.upper:
            raise PathBBracketError("bracket bounds must be increasing")
        if self.backoff <= 1.0 or not np.isfinite(self.backoff):
            raise PathBBracketError("bracket backoff must be finite and greater than 1")
        floor = self.epsilon / 1024.0 if self.min_epsilon is None else float(self.min_epsilon)
        if floor <= 0.0 or floor > self.epsilon:
            raise PathBBracketError("bracket min_epsilon must be within (0, epsilon]")
        object.__setattr__(self, "min_epsilon", floor)


@dataclass(frozen=True)
class BracketOutcome:
    ok: bool
    reason: str
    epsilon: float
    direction_inf_norm: float
    d_adj: float | None = None
    d_fd: float | None = None
    plus_objective: float | None = None
    minus_objective: float | None = None
    plus_rho_sha256: str | None = None
    minus_rho_sha256: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rho_sha256(rho: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(np.asarray(rho, dtype=np.float64)).tobytes()
    ).hexdigest()


def evaluate_path_b_bracket(
    *,
    spec: BracketSpec,
    parent_rho: np.ndarray,
    parent_gradient: np.ndarray,
    proposal_delta: np.ndarray,
    active: np.ndarray,
    evaluate_values: Callable[[np.ndarray], Any],
) -> BracketOutcome:
    """Evaluate the centered bracket around the parent along the proposal."""

    rho = np.asarray(parent_rho, dtype=np.float64)
    delta = np.asarray(proposal_delta, dtype=np.float64)
    gradient = np.asarray(parent_gradient, dtype=np.float64)
    if rho.shape != delta.shape or rho.shape != gradient.shape:
        raise PathBBracketError("parent rho, gradient, and proposal must share the shape")
    peak = float(np.max(np.abs(delta))) if delta.size else 0.0
    if peak <= 0.0:
        return BracketOutcome(False, "zero_direction", spec.epsilon, peak)
    d_hat = delta / peak

    epsilon = spec.epsilon
    plus = rho + epsilon * d_hat
    minus = rho - epsilon * d_hat
    while True:
        violation = None
        for label, candidate in (("plus", plus), ("minus", minus)):
            if np.any(candidate[active] < spec.lower - 1e-12) or np.any(
                candidate[active] > spec.upper + 1e-12
            ):
                violation = label
                break
        if violation is None:
            break
        if epsilon / spec.backoff < float(spec.min_epsilon):
            return BracketOutcome(
                False,
                f"bracket_bounds_asymmetric_{violation}",
                epsilon,
                peak,
                details={
                    "note": "no clipping; epsilon backed off to min_epsilon without a "
                    "symmetric pair",
                    "min_epsilon": float(spec.min_epsilon),
                },
            )
        epsilon = epsilon / spec.backoff
        plus = rho + epsilon * d_hat
        minus = rho - epsilon * d_hat
    if np.any(plus[~active] != rho[~active]) or np.any(minus[~active] != rho[~active]):
        raise PathBBracketError("bracket must not perturb inactive cells")

    plus_result = evaluate_values(plus)
    minus_result = evaluate_values(minus)
    j_plus = float(plus_result.objective)
    j_minus = float(minus_result.objective)
    difference = abs(j_plus - j_minus)
    d_adj = float(np.dot(gradient, d_hat))
    d_fd = (j_plus - j_minus) / (2.0 * epsilon)
    common = {
        "d_adj": d_adj,
        "d_fd": d_fd,
        "plus_objective": j_plus,
        "minus_objective": j_minus,
        "plus_rho_sha256": _rho_sha256(plus),
        "minus_rho_sha256": _rho_sha256(minus),
        "details": {
            "difference": difference,
            "noise_floor_abs": spec.noise_floor_abs,
        },
    }
    if difference <= spec.noise_floor_abs:
        return BracketOutcome(
            False, "below_noise_floor", epsilon, peak, **common
        )
    if d_adj >= 0.0 or d_fd >= 0.0:
        return BracketOutcome(
            False,
            "not_a_descent_direction",
            epsilon,
            peak,
            **common,
        )
    return BracketOutcome(True, "descent_sign_match", epsilon, peak, **common)


__all__ = [
    "BRACKET_SCHEMA_VERSION",
    "BracketOutcome",
    "BracketSpec",
    "PathBBracketError",
    "evaluate_path_b_bracket",
]
