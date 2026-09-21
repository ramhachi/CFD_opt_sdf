"""Restartable Stage T nonlinear loop around the accepted-trial controller (DF3).

The loop is oracle-agnostic: ``ResponseOracle`` returns primitive objective and
constraint values plus their gradients (already pulled back to the design
variable by the transform owned in ``design_transform``), and a ``TrialBackend``
proposes a bounded trial. Acceptance is decided only by
``nonlinear_acceptance`` after the oracle re-evaluates the trial; a rejected
trial rolls back to the same parent with a reduced move radius and the penalty
growth of the GCMMA-like inner loop.

Everything is deterministic and JSON-serializable: the trace records each
measurement, and ``checkpoint``/``resume`` bind the design, transform,
oracle-response, and controller state so a campaign can stop and continue
without re-accepting an unverified step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from .design_transform import DesignTransform
from .nonlinear_acceptance import (
    AcceptanceState,
    TrialEvaluation,
    TrialProposal,
    run_conservative_inner_loop,
)
from .problem_spec_compiler import CompiledProblem


@dataclass(frozen=True)
class OracleResult:
    objective: float
    constraint_values: dict[str, float]
    objective_gradient: np.ndarray
    constraint_gradients: dict[str, np.ndarray]
    primal_converged: bool
    adjoint_converged: bool
    solver_status: str = "unknown"
    geometry_ok: bool = True
    geometry_metrics: dict[str, Any] = field(default_factory=dict)
    response_hash: str | None = None

    def to_evaluation(self) -> TrialEvaluation:
        return TrialEvaluation(
            objective=self.objective,
            constraint_values=dict(self.constraint_values),
            primal_converged=self.primal_converged,
            adjoint_converged=self.adjoint_converged,
            geometry_ok=self.geometry_ok,
            geometry_metrics=dict(self.geometry_metrics),
            solver_status=self.solver_status,
        )


class ResponseOracle(Protocol):
    def evaluate(self, rho_design: np.ndarray) -> OracleResult:
        ...


class TrialBackend(Protocol):
    def propose(
        self,
        *,
        rho: np.ndarray,
        objective_gradient: np.ndarray,
        constraint_gradients: dict[str, np.ndarray],
        constraint_values: dict[str, float],
        move_radius: float,
        backend_state: dict[str, Any],
    ) -> TrialProposal:
        ...


class ProjectedGradientBackend:
    """Reference backend: scaled steepest step with linear constraint scaling.

    For each candidate step length ``alpha`` the direction is
    ``-grad / ||grad||_inf * alpha`` (bounded by ``move_radius``); the largest
    ``alpha`` that keeps every linearized constraint feasible is found by
    bisection. This is deliberately simple: DF3 validates the acceptance
    machinery, DF6 replaces the proposal step behind the same interface.
    """

    def __init__(self, *, max_bisection: int = 40) -> None:
        self.max_bisection = max_bisection

    def propose(
        self,
        *,
        rho: np.ndarray,
        objective_gradient: np.ndarray,
        constraint_gradients: dict[str, np.ndarray],
        constraint_values: dict[str, float],
        move_radius: float,
        backend_state: dict[str, Any],
    ) -> TrialProposal:
        gradient = np.asarray(objective_gradient, dtype=np.float64)
        norm = float(np.max(np.abs(gradient))) if gradient.size else 0.0
        if norm <= 1e-30:
            direction = np.zeros_like(gradient)
        else:
            direction = -gradient / norm

        def feasible(alpha: float) -> bool:
            for name, grad in constraint_gradients.items():
                value = constraint_values.get(name, 0.0)
                if value + float(np.dot(np.asarray(grad), direction * alpha)) > 1e-12:
                    return False
            return True

        low, high = 0.0, float(move_radius)
        if not feasible(high):
            for _ in range(self.max_bisection):
                mid = 0.5 * (low + high)
                if feasible(mid):
                    low = mid
                else:
                    high = mid
            alpha = low
        else:
            alpha = high
        return TrialProposal(
            delta=direction * alpha,
            backend="projected-gradient-constrained",
            metadata={"alpha": alpha, "direction_inf_norm": float(np.max(np.abs(direction)))},
        )


@dataclass(frozen=True)
class LoopSpec:
    transform: DesignTransform
    compiled: CompiledProblem
    move_limit: float = 0.1
    max_iterations: int = 20
    max_inner_iterations: int = 8
    checkpoint_every: int = 1


@dataclass
class LoopResult:
    trace: list[dict[str, Any]]
    final_rho: np.ndarray
    final_evaluation: OracleResult
    accepted: int
    rejected: int
    transform_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_hash": self.transform_hash,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "trace": self.trace,
            "final_rho": [float(v) for v in self.final_rho],
        }


def _rho_sha256(rho: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(np.asarray(rho, dtype=np.float64)).tobytes()
    ).hexdigest()


def _linear_prediction(
    *,
    parent: OracleResult,
    proposal: TrialProposal,
    transform: DesignTransform,
) -> float:
    """Linearized objective at the trial in design space (chain through the transform)."""

    objective_delta = float(np.dot(parent.objective_gradient, proposal.delta))
    return float(parent.objective + objective_delta)


def make_oracle_from_compiled(
    *,
    transform: DesignTransform,
    compiled: CompiledProblem,
    primitive_evaluator: Callable[[np.ndarray], dict[str, Any]],
) -> Callable[[np.ndarray], OracleResult]:
    """Adapt a primitive-response evaluator to the loop's oracle protocol.

    ``primitive_evaluator(rho_design)`` must return ``values`` (keyed by
    ``(flow_case, response)``), ``gradients``, ``primal_converged``,
    ``adjoint_converged``, and optionally ``solver_status``/``geometry``.
    """

    def evaluate(rho_design: np.ndarray) -> OracleResult:
        payload = primitive_evaluator(np.asarray(rho_design, dtype=np.float64))
        values = payload["values"]
        gradients = payload["gradients"]
        objective = compiled.objective_value(values)
        g_values = compiled.constraint_values(values)
        g_gradients = compiled.constraint_gradients(gradients)
        return OracleResult(
            objective=objective,
            constraint_values=g_values,
            objective_gradient=compiled.objective_gradient(gradients),
            constraint_gradients=g_gradients,
            primal_converged=bool(payload.get("primal_converged", True)),
            adjoint_converged=bool(payload.get("adjoint_converged", True)),
            solver_status=str(payload.get("solver_status", "ok")),
            geometry_ok=bool(payload.get("geometry_ok", True)),
            geometry_metrics=dict(payload.get("geometry_metrics", {})),
            response_hash=payload.get("response_hash"),
        )

    return evaluate


def run_stage_t_loop(
    *,
    spec: LoopSpec,
    oracle: ResponseOracle | Callable[[np.ndarray], OracleResult],
    backend: TrialBackend | None = None,
    initial_rho: np.ndarray | None = None,
    checkpoint_path: Path | None = None,
    resume_from: Path | None = None,
) -> LoopResult:
    """Run (or resume) the accepted-trial loop; deterministic for deterministic inputs."""

    transform = spec.transform
    active = transform.active
    backend = backend or ProjectedGradientBackend()
    evaluate = oracle.evaluate if hasattr(oracle, "evaluate") else oracle

    trace: list[dict[str, Any]] = []
    if resume_from is not None:
        checkpoint = json.loads(Path(resume_from).read_text(encoding="utf-8"))
        if checkpoint["transform_hash"] != transform.transform_hash():
            raise ValueError("checkpoint transform hash does not match the current transform")
        rho = np.asarray(checkpoint["rho"], dtype=np.float64)
        state = AcceptanceState(
            rho=rho,
            move_radius=float(checkpoint["move_radius"]),
            iteration=int(checkpoint["iteration"]),
            accepted=int(checkpoint["accepted"]),
            rejected=int(checkpoint["rejected"]),
            penalty=float(checkpoint["penalty"]),
        )
        trace = list(checkpoint.get("trace", []))
        parent_result = evaluate(state.rho)
    else:
        if initial_rho is None:
            raise ValueError("initial_rho is required when not resuming")
        state = AcceptanceState(rho=np.clip(initial_rho, 0.0, 1.0), move_radius=spec.move_limit)
        parent_result = evaluate(state.rho)

    parent_eval = parent_result.to_evaluation()
    state.objective = parent_result.objective

    while state.iteration < spec.max_iterations:
        state.iteration += 1
        iteration_trace: dict[str, Any] = {
            "iteration": state.iteration,
            "parent_objective": parent_result.objective,
            "parent_constraints": dict(parent_result.constraint_values),
            "move_radius_in": state.move_radius,
            "penalty_in": state.penalty,
        }

        proposals: list[TrialProposal] = []

        def propose(working: AcceptanceState) -> TrialProposal:
            proposal = backend.propose(
                rho=working.rho,
                objective_gradient=parent_result.objective_gradient,
                constraint_gradients=parent_result.constraint_gradients,
                constraint_values=parent_result.constraint_values,
                move_radius=working.move_radius,
                backend_state={},
            )
            proposals.append(proposal)
            return proposal

        def evaluate_trial(rho_trial: np.ndarray, proposal: TrialProposal) -> TrialEvaluation:
            return evaluate(rho_trial).to_evaluation()

        decision, trial_rho, inner_trace = run_conservative_inner_loop(
            parent=parent_eval,
            state=state,
            propose=propose,
            evaluate=evaluate_trial,
            predicted_objective=lambda proposal: _linear_prediction(
                parent=parent_result, proposal=proposal, transform=transform
            ),
            max_inner_iterations=spec.max_inner_iterations,
        )
        iteration_trace["inner"] = inner_trace
        if decision.accepted and trial_rho is not None:
            state.rho = trial_rho
            state.accepted += 1
            parent_result = evaluate(state.rho)
            parent_eval = parent_result.to_evaluation()
            state.objective = parent_result.objective
            iteration_trace.update(
                {
                    "accepted": True,
                    "status": decision.status,
                    "reason": decision.reason,
                    "trial_objective": parent_result.objective,
                    "trial_constraints": dict(parent_result.constraint_values),
                    "rho_sha256": _rho_sha256(state.rho),
                }
            )
        else:
            state.rejected += 1
            iteration_trace.update(
                {
                    "accepted": False,
                    "status": decision.status,
                    "reason": decision.reason,
                }
            )
        trace.append(iteration_trace)

        if checkpoint_path is not None and state.iteration % spec.checkpoint_every == 0:
            _write_checkpoint(checkpoint_path, state, transform, trace, parent_result)

    return LoopResult(
        trace=trace,
        final_rho=state.rho,
        final_evaluation=parent_result,
        accepted=state.accepted,
        rejected=state.rejected,
        transform_hash=transform.transform_hash(),
    )


def _write_checkpoint(
    path: Path,
    state: AcceptanceState,
    transform: DesignTransform,
    trace: list[dict[str, Any]],
    last_evaluation: OracleResult,
) -> None:
    payload = {
        "kind": "stage_t_loop_checkpoint",
        "schema_version": 1,
        "transform_hash": transform.transform_hash(),
        "rho": [float(v) for v in state.rho],
        "move_radius": float(state.move_radius),
        "penalty": float(state.penalty),
        "iteration": int(state.iteration),
        "accepted": int(state.accepted),
        "rejected": int(state.rejected),
        "objective": float(last_evaluation.objective),
        "constraints": dict(last_evaluation.constraint_values),
        "response_hash": last_evaluation.response_hash,
        "rho_sha256": _rho_sha256(state.rho),
        "trace": trace,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


__all__ = [
    "LoopResult",
    "LoopSpec",
    "OracleResult",
    "ProjectedGradientBackend",
    "ResponseOracle",
    "TrialBackend",
    "make_oracle_from_compiled",
    "run_stage_t_loop",
]
