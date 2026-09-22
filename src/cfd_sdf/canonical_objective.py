"""Canonical objective contract for Phase 2 (PQ3.3b preflight v4 / manifest v3).

The registered canonical objective is ``J = sense_sign * sum(coeff * response)``
from the compiled ``ProblemSpec``. For ``downforce: maximize`` this is
``J = -downforce`` (sense sign ``-1``), so:

- improvement in the canonical space is ``J_trial < J_parent``;
- the equivalent physical check is ``downforce_trial > downforce_parent``.

Raw OpenFoamOracle ``parent_evaluator`` payloads carry the response-space
sensitivity (beta space). They must never be handed to a Phase 2 backend
directly: the registered path is

``ProblemSpec -> compile_problem(...) -> make_oracle_from_compiled(...)
-> evaluate_parent(...) -> OracleResult.objective_gradient``

which pulls the sensitivity into design space and applies the objective sign.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

RAW_GRADIENT_USE = "raw_oracle_response_gradient"

RAW_GRADIENT_ERROR = (
    "raw oracle sensitivity must not be passed to a Phase 2 backend; route the "
    "gradient through ProblemSpec -> compile_problem -> make_oracle_from_compiled"
    "-> evaluate_parent -> OracleResult.objective_gradient"
)


@dataclass(frozen=True)
class CanonicalObjectiveRecord:
    """One parent evaluation, with the raw and canonical values kept separate."""

    raw_downforce: float
    canonical_objective: float
    raw_response_gradient_sha256: str
    canonical_objective_gradient_sha256: str
    objective_sense: str
    objective_sign: int


def array_sha256_for_evidence(values: np.ndarray) -> str:
    values = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(values.tobytes()).hexdigest()


def canonical_objective_from(result) -> tuple[float, np.ndarray]:
    """Return ``(canonical_objective, canonical_gradient, record)`` from a result.

    Accepts only an ``OracleResult`` with ``gradient_space == "rho_design"`` and
    ``adjoint_status == "converged"``. A raw ``numpy.ndarray`` is rejected with
    the fixed error text; so is any raw-backend surrogate.
    """
    if isinstance(result, np.ndarray):
        raise TypeError(RAW_GRADIENT_ERROR)
    if not hasattr(result, "objective_gradient") or result.objective_gradient is None:
        raise TypeError(RAW_GRADIENT_ERROR)
    if result.gradient_space != "rho_design":
        raise TypeError(
            "canonical Phase 2 gradients must be in rho_design space; observed "
            f"'{result.gradient_space}'"
        )
    if result.adjoint_status != "converged":
        raise TypeError(
            "canonical Phase 2 gradients require adjoint convergence evidence; "
            f"observed {result.adjoint_status!r}"
        )
    return float(result.objective), np.asarray(result.objective_gradient, dtype=np.float64)


def record_from_parent_result(
    *,
    result,
    raw_downforce: float,
    raw_response_gradient: np.ndarray,
    objective_sense: str,
    objective_sign: int,
) -> CanonicalObjectiveRecord:
    """Hash the raw and canonical gradients into one evidence record."""
    canonical_objective, _ = canonical_objective_from(result)
    return CanonicalObjectiveRecord(
        raw_downforce=float(raw_downforce),
        canonical_objective=float(result.objective),
        raw_response_gradient_sha256=array_sha256_for_evidence(raw_response_gradient),
        canonical_objective_gradient_sha256=array_sha256_for_evidence(
            result.objective_gradient
        ),
        objective_sense=str(objective_sense),
        objective_sign=int(objective_sign),
    )


def canonical_sense_sign(sense: str) -> int:
    """``+1`` for minimize, ``-1`` for maximize (J = -downforce)."""
    if sense == "maximize":
        return -1
    if sense == "minimize":
        return 1
    raise ValueError(f"unsupported objective sense: {sense!r}")


__all__ = [
    "CanonicalObjectiveRecord",
    "RAW_GRADIENT_ERROR",
    "RAW_GRADIENT_USE",
    "canonical_objective_from",
    "canonical_sense_sign",
    "record_from_parent_result",
]
