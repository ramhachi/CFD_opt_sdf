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


# --- SDF-native semantics (PR-01) -----------------------------------------
# Pure functions/dataclasses in response space.  They do not touch historical
# Phase 2 manifests; the Stage T/B-spline path keeps its own compiled algebra.

DOWN_FORCE_RESPONSE = "downforce"
DRAG_RESPONSE = "drag"


def canonical_downforce_objective(c_downforce: float) -> float:
    """Minimization objective ``f = -C_DF`` with the repository downforce sign."""

    return -float(c_downforce)


def canonical_downforce_objective_gradient(downforce_gradient: np.ndarray) -> np.ndarray:
    """``df/dphi = -dC_DF/dphi``."""

    return -np.asarray(downforce_gradient, dtype=np.float64)


@dataclass(frozen=True)
class EfficiencyConstraint:
    """Division-free drag-efficiency requirement ``g_R = R_min*C_D - C_DF <= 0``.

    For ``C_D > 0`` this is equivalent to ``C_DF/C_D >= R_min`` without the
    singularity and denominator sensitivity of a ratio objective.
    """

    r_min: float
    constraint_id: str = "drag_efficiency"

    def __post_init__(self) -> None:
        if not np.isfinite(self.r_min) or float(self.r_min) <= 0.0:
            raise ValueError("r_min must be finite and positive")
        if not str(self.constraint_id).strip():
            raise ValueError("constraint_id must be non-empty")

    def value(self, *, c_drag: float, c_downforce: float) -> float:
        return float(self.r_min) * float(c_drag) - float(c_downforce)

    def gradient(
        self, *, drag_gradient: np.ndarray, downforce_gradient: np.ndarray
    ) -> np.ndarray:
        return float(self.r_min) * np.asarray(drag_gradient, dtype=np.float64) - np.asarray(
            downforce_gradient, dtype=np.float64
        )

    def satisfied(self, *, c_drag: float, c_downforce: float, tolerance: float = 0.0) -> bool:
        return self.value(c_drag=c_drag, c_downforce=c_downforce) <= float(tolerance)

    def to_dict(self) -> dict[str, float | str]:
        return {"constraint_id": self.constraint_id, "r_min": float(self.r_min)}


@dataclass(frozen=True)
class VolumeConstraint:
    """Normalized volume budget ``g_V = V(phi)/V_max - 1 <= 0``."""

    v_max: float
    constraint_id: str = "volume"

    def __post_init__(self) -> None:
        if not np.isfinite(self.v_max) or float(self.v_max) <= 0.0:
            raise ValueError("v_max must be finite and positive")
        if not str(self.constraint_id).strip():
            raise ValueError("constraint_id must be non-empty")

    def value(self, volume: float) -> float:
        return float(volume) / float(self.v_max) - 1.0

    def gradient(self, volume_gradient: np.ndarray) -> np.ndarray:
        return np.asarray(volume_gradient, dtype=np.float64) / float(self.v_max)

    def satisfied(self, volume: float, tolerance: float = 0.0) -> bool:
        return self.value(volume) <= float(tolerance)

    def to_dict(self) -> dict[str, float | str]:
        return {"constraint_id": self.constraint_id, "v_max": float(self.v_max)}


__all__ = [
    "DOWN_FORCE_RESPONSE",
    "DRAG_RESPONSE",
    "CanonicalObjectiveRecord",
    "EfficiencyConstraint",
    "RAW_GRADIENT_ERROR",
    "RAW_GRADIENT_USE",
    "VolumeConstraint",
    "canonical_downforce_objective",
    "canonical_downforce_objective_gradient",
    "canonical_objective_from",
    "canonical_sense_sign",
    "record_from_parent_result",
]
