"""Merit/trust acceptance control with conservative inner retries (DF3/PQ0).

The historical step marked a trial ``accepted_by_linearization`` from the linear
prediction alone and still wrote artifacts. The architecture plan requires the
opposite: a trial is accepted only after the primal is re-solved and every
constraint and geometry gate is re-evaluated, and a rejected trial rolls back
to the same parent with a reduced move radius.

The acceptance rule borrows the conservative-check structure of Svanberg's
GCMMA: the objective/constraint model is accepted only if the actual merit
decreases; otherwise the controller increases the penalty (the inner-iteration
analog) and the backend re-proposes from the same parent with a smaller move
radius. Gradients are evaluated once per parent; only function values are
re-evaluated at trials.

This is **not** an MMA/GCMMA implementation: it has no moving asymptotes and no
separable convex subproblem. It is a nonlinear merit/trust controller; the
MMA/GCMMA name applies only after such a backend exists (PQ6).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

DEFAULT_VIOLATION_TOLERANCE = 1.0e-8
DEFAULT_MERIT_TOLERANCE = 1.0e-12
DEFAULT_TRUST_LOW = 0.25
DEFAULT_TRUST_HIGH = 0.75
DEFAULT_MOVE_FLOOR = 1.0e-4
DEFAULT_PENALTY = 1.0
DEFAULT_PENALTY_GROWTH = 1.1


@dataclass(frozen=True)
class TrialEvaluation:
    """Everything re-measured at a trial before any acceptance decision."""

    objective: float
    constraint_values: dict[str, float]
    primal_converged: bool
    adjoint_converged: bool
    geometry_ok: bool
    geometry_metrics: dict[str, Any] = field(default_factory=dict)
    solver_status: str = "unknown"


@dataclass(frozen=True)
class TrialProposal:
    """A bounded trial proposed by a backend; it is never accepted here."""

    delta: np.ndarray
    backend: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def trial_rho(self, parent: np.ndarray, *, lower: float = 0.0, upper: float = 1.0) -> np.ndarray:
        return np.clip(np.asarray(parent, dtype=np.float64) + self.delta, lower, upper)


@dataclass
class AcceptanceState:
    rho: np.ndarray
    move_radius: float
    iteration: int = 0
    accepted: int = 0
    rejected: int = 0
    penalty: float = DEFAULT_PENALTY
    objective: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "move_radius": float(self.move_radius),
            "penalty": float(self.penalty),
            "objective": self.objective,
            "rho_sha256": _array_sha256(self.rho),
        }


@dataclass(frozen=True)
class AcceptanceDecision:
    accepted: bool
    status: str
    reason: str
    merit_parent: float | None
    merit_trial: float | None
    trust_ratio: float | None
    new_move_radius: float
    new_penalty: float
    trace: dict[str, Any]


def _array_sha256(values: np.ndarray) -> str:
    import hashlib

    return hashlib.sha256(
        np.ascontiguousarray(np.asarray(values, dtype=np.float64)).tobytes()
    ).hexdigest()


def violation(constraint_values: dict[str, float]) -> float:
    """Total positive part of the normalized ``g <= 0`` constraint values."""

    return float(sum(max(0.0, float(value)) for value in constraint_values.values()))


def merit(
    objective: float,
    constraint_values: dict[str, float],
    *,
    penalty: float,
) -> float:
    """Quadratic-penalty merit; the GCMMA conservative check compares these."""

    return float(objective) + float(penalty) * violation(constraint_values) ** 2


def accept_trial(
    *,
    parent: TrialEvaluation,
    trial: TrialEvaluation,
    predicted_trial_objective: float,
    state: AcceptanceState,
    violation_tolerance: float = DEFAULT_VIOLATION_TOLERANCE,
    merit_tolerance: float = DEFAULT_MERIT_TOLERANCE,
    trust_low: float = DEFAULT_TRUST_LOW,
    trust_high: float = DEFAULT_TRUST_HIGH,
    move_floor: float = DEFAULT_MOVE_FLOOR,
    penalty_growth: float = DEFAULT_PENALTY_GROWTH,
) -> AcceptanceDecision:
    """Decide accept/reject/rollback for one evaluated trial.

    Order of checks: qualification (primal, adjoint, geometry), hard-feasibility
    (with monotone-restoration exception), merit decrease (conservative check),
    then trust-ratio-driven move update for the next proposal.
    """

    parent_merit = merit(parent.objective, parent.constraint_values, penalty=state.penalty)
    trial_merit = merit(trial.objective, trial.constraint_values, penalty=state.penalty)
    predicted_merit = merit(
        predicted_trial_objective, trial.constraint_values, penalty=state.penalty
    )
    parent_violation = violation(parent.constraint_values)
    trial_violation = violation(trial.constraint_values)
    trace: dict[str, Any] = {
        "parent_objective": parent.objective,
        "trial_objective": trial.objective,
        "parent_violation": parent_violation,
        "trial_violation": trial_violation,
        "parent_merit": parent_merit,
        "trial_merit": trial_merit,
        "penalty": state.penalty,
        "move_radius": state.move_radius,
        "primal_converged": trial.primal_converged,
        "adjoint_converged": trial.adjoint_converged,
        "geometry_ok": trial.geometry_ok,
        "solver_status": trial.solver_status,
    }

    def decision(
        accepted: bool,
        status: str,
        reason: str,
        *,
        ratio: float | None = None,
        new_move: float | None = None,
        new_penalty: float | None = None,
    ) -> AcceptanceDecision:
        move = state.move_radius if new_move is None else max(new_move, move_floor)
        penalty = state.penalty if new_penalty is None else new_penalty
        trace.update(
            {
                "status": status,
                "reason": reason,
                "trust_ratio": ratio,
                "next_move_radius": move,
                "next_penalty": penalty,
            }
        )
        return AcceptanceDecision(
            accepted=accepted,
            status=status,
            reason=reason,
            merit_parent=parent_merit,
            merit_trial=trial_merit,
            trust_ratio=ratio,
            new_move_radius=move,
            new_penalty=penalty,
            trace=trace,
        )

    if not trial.primal_converged:
        return decision(False, "reject", "primal_not_converged", new_move=state.move_radius / 2.0)
    if not trial.adjoint_converged:
        return decision(False, "reject", "adjoint_not_converged", new_move=state.move_radius / 2.0)
    if not trial.geometry_ok:
        return decision(False, "reject", "geometry_gate_failed", new_move=state.move_radius / 2.0)

    denominator = parent_merit - predicted_merit
    ratio = (parent_merit - trial_merit) / denominator if abs(denominator) > 1e-30 else None
    trace["predicted_trial_objective"] = predicted_trial_objective
    trace["predicted_merit"] = predicted_merit

    if trial_violation > violation_tolerance:
        if trial_violation < parent_violation:
            if ratio is None or ratio >= trust_low:
                return decision(
                    True,
                    "restoration_accept",
                    "constraint violation decreases monotonically",
                    ratio=ratio,
                    new_move=state.move_radius,
                )
            return decision(
                False,
                "reject",
                "restoration_step_trust_ratio_low",
                ratio=ratio,
                new_move=state.move_radius / 2.0,
            )
        return decision(
            False,
            "reject",
            "constraint_violation_not_reduced",
            ratio=ratio,
            new_move=state.move_radius / 2.0,
            new_penalty=state.penalty * penalty_growth,
        )

    if trial_merit >= parent_merit - merit_tolerance:
        return decision(
            False,
            "reject",
            "merit_not_decreased",
            ratio=ratio,
            new_move=state.move_radius / 2.0,
            new_penalty=state.penalty * penalty_growth,
        )

    if ratio is not None and ratio < trust_low:
        return decision(
            False,
            "reject",
            "trust_ratio_low",
            ratio=ratio,
            new_move=state.move_radius / 2.0,
        )

    new_radius = state.move_radius
    if ratio is not None and ratio > trust_high:
        new_radius = min(state.move_radius * 1.5, 1.0)
    return decision(
        True,
        "accept",
        "feasible merit decrease",
        ratio=ratio,
        new_move=new_radius,
    )


def run_conservative_inner_loop(
    *,
    parent: TrialEvaluation,
    state: AcceptanceState,
    propose: Callable[[AcceptanceState], TrialProposal],
    evaluate: Callable[[np.ndarray, TrialProposal], TrialEvaluation],
    predicted_objective: Callable[[TrialProposal], float],
    max_inner_iterations: int = 8,
) -> tuple[AcceptanceDecision, np.ndarray | None, list[dict[str, Any]]]:
    """GCMMA-like inner iterations: re-propose from the same parent until accepted.

    ``propose`` receives the updated state (move radius, penalty) each inner
    iteration; gradients are not re-evaluated because the parent has not changed.
    """

    trace: list[dict[str, Any]] = []
    working = AcceptanceState(
        rho=state.rho,
        move_radius=state.move_radius,
        iteration=state.iteration,
        accepted=state.accepted,
        rejected=state.rejected,
        penalty=state.penalty,
        objective=state.objective,
    )
    for inner in range(max_inner_iterations):
        proposal = propose(working)
        trial_rho = proposal.trial_rho(working.rho)
        trial = evaluate(trial_rho, proposal)
        decision = accept_trial(
            parent=parent,
            trial=trial,
            predicted_trial_objective=predicted_objective(proposal),
            state=working,
        )
        entry = dict(decision.trace)
        entry["inner_iteration"] = inner
        trace.append(entry)
        if decision.accepted:
            state.move_radius = decision.new_move_radius
            state.penalty = decision.new_penalty
            state.rejected = working.rejected
            return decision, trial_rho, trace
        working.rejected += 1
        working.move_radius = decision.new_move_radius
        working.penalty = decision.new_penalty
    state.move_radius = working.move_radius
    state.penalty = working.penalty
    return (
        AcceptanceDecision(
            accepted=False,
            status="diverged",
            reason="inner_iteration_cap_reached",
            merit_parent=None,
            merit_trial=None,
            trust_ratio=None,
            new_move_radius=working.move_radius,
            new_penalty=working.penalty,
            trace={"status": "diverged", "inner_iterations": max_inner_iterations},
        ),
        None,
        trace,
    )


__all__ = [
    "AcceptanceDecision",
    "AcceptanceState",
    "TrialEvaluation",
    "TrialProposal",
    "accept_trial",
    "merit",
    "run_conservative_inner_loop",
    "violation",
]
