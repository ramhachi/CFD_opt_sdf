"""Restartable Stage T nonlinear loop around the accepted-trial controller (DF3/PQ0).

The loop separates the two evaluation kinds explicitly (PQ0 I4/I6):

- ``evaluate_values``: primal values, constraints and geometry gates only;
  every trial uses this;
- ``evaluate_gradients``: the parent's adjoint gradients, called once per
  accepted parent (the accepted trial's value payload is reused), so no primal
  is re-run after acceptance and no trial pays for an adjoint.

Gradient spaces are declared, not implied: the oracle adapter maps
``g_solver -> g_design`` through the declared ``DesignTransform`` pullback and
records the transform hash on every result. Checkpoints bind the ProblemSpec,
the compiled problem, the transform, the backend id, the oracle profile and the
design/response hashes; a resume with any mismatch is refused (PQ0 I8).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from .design_transform import DesignTransform, DesignTransformState
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
    primal_converged: bool
    adjoint_converged: bool
    solver_status: str = "unknown"
    geometry_ok: bool = True
    geometry_metrics: dict[str, Any] = field(default_factory=dict)
    response_hash: str | None = None
    objective_gradient: np.ndarray | None = None
    constraint_gradients: dict[str, np.ndarray] = field(default_factory=dict)
    gradient_space: str | None = None
    transform_hash: str | None = None

    def has_gradients(self) -> bool:
        return self.objective_gradient is not None

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
    def evaluate_values(self, rho_design: np.ndarray) -> OracleResult:
        """Primal-only evaluation (values, constraints, gates)."""

    def evaluate_gradients(
        self, rho_design: np.ndarray, values: OracleResult
    ) -> OracleResult:
        """Adjoint evaluation at the same design; returns values + gradients."""


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
    bisection. This is deliberately simple: PQ0 validates the acceptance
    machinery, a moving-asymptotes backend replaces the proposal step behind
    the same interface.
    """

    backend_id = "projected-gradient-constrained"

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
    backend_id: str = "projected-gradient-constrained"
    oracle_profile: str = "default"


@dataclass
class LoopResult:
    trace: list[dict[str, Any]]
    final_rho: np.ndarray
    final_evaluation: OracleResult
    accepted: int
    rejected: int
    transform_hash: str
    counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_hash": self.transform_hash,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "counts": self.counts,
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
    primitive_evaluator: Callable[[DesignTransformState], dict[str, Any]],
) -> Callable[..., OracleResult]:
    """Adapt a solver-field evaluator to the two-space oracle protocol.

    ``primitive_evaluator(state)`` consumes the declared transform state (the
    solver sees ``state.beta``) and returns:

    - ``values``: ``{(flow_case, response): float}``;
    - ``gradients``: ``{(flow_case, response): np.ndarray}`` **in the solver
      field (beta) space**; the adapter maps them to design space with
      ``transform.pullback_from_beta``;
    - ``primal_converged`` / ``adjoint_converged`` / ``solver_status`` /
      ``geometry_ok`` / ``geometry_metrics`` / ``response_hash``.

    ``evaluate_values`` passes no gradients; ``evaluate_gradients`` requires
    them and records the transform hash and gradient space.
    """

    def _evaluate(
        rho_design: np.ndarray, *, with_gradients: bool, values: OracleResult | None
    ) -> OracleResult:
        rho = np.asarray(rho_design, dtype=np.float64)
        state = transform.forward(rho)
        payload = primitive_evaluator(state)
        primitive_values = payload["values"]
        objective = compiled.objective_value(primitive_values)
        constraint_values = compiled.constraint_values(primitive_values)
        result = OracleResult(
            objective=objective,
            constraint_values=constraint_values,
            primal_converged=bool(payload.get("primal_converged", True)),
            adjoint_converged=bool(payload.get("adjoint_converged", True)),
            solver_status=str(payload.get("solver_status", "ok")),
            geometry_ok=bool(payload.get("geometry_ok", True)),
            geometry_metrics=dict(payload.get("geometry_metrics", {})),
            response_hash=payload.get("response_hash"),
        )
        if not with_gradients:
            return result
        raw_gradients = payload.get("gradients")
        if not isinstance(raw_gradients, dict) or not raw_gradients:
            raise ValueError(
                "evaluate_gradients requires solver-field gradients from the evaluator"
            )
        design_gradients = {
            key: transform.pullback_from_beta(rho, np.asarray(gradient, dtype=np.float64))
            for key, gradient in raw_gradients.items()
        }
        return OracleResult(
            objective=result.objective,
            constraint_values=result.constraint_values,
            primal_converged=result.primal_converged,
            adjoint_converged=result.adjoint_converged,
            solver_status=result.solver_status,
            geometry_ok=result.geometry_ok,
            geometry_metrics=result.geometry_metrics,
            response_hash=result.response_hash,
            objective_gradient=compiled.objective_gradient(design_gradients),
            constraint_gradients=compiled.constraint_gradients(design_gradients),
            gradient_space="rho_design",
            transform_hash=transform.transform_hash(),
        )

    class CompiledOracle:
        def evaluate_values(self, rho_design: np.ndarray) -> OracleResult:
            return _evaluate(rho_design, with_gradients=False, values=None)

        def evaluate_gradients(
            self, rho_design: np.ndarray, values: OracleResult | None = None
        ) -> OracleResult:
            return _evaluate(rho_design, with_gradients=True, values=values)

    return CompiledOracle()


def _call_values(oracle: Any, rho: np.ndarray) -> OracleResult:
    return oracle.evaluate_values(rho)


def _call_gradients(oracle: Any, rho: np.ndarray, values: OracleResult) -> OracleResult:
    result = oracle.evaluate_gradients(rho, values)
    if not result.has_gradients():
        raise ValueError("evaluate_gradients returned a result without gradients")
    return result


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
    backend = backend or ProjectedGradientBackend()
    counts = {"value_evaluations": 0, "gradient_evaluations": 0}
    trace: list[dict[str, Any]] = []

    def evaluate_values(rho: np.ndarray) -> OracleResult:
        counts["value_evaluations"] += 1
        return _call_values(oracle, rho)

    def evaluate_gradients(rho: np.ndarray, values: OracleResult) -> OracleResult:
        counts["gradient_evaluations"] += 1
        return _call_gradients(oracle, rho, values)

    if resume_from is not None:
        checkpoint = json.loads(Path(resume_from).read_text(encoding="utf-8"))
        _validate_checkpoint(checkpoint, spec)
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
        counts = dict(checkpoint.get("counts", counts))
        parent_values = evaluate_values(state.rho)
        parent_result = evaluate_gradients(state.rho, parent_values)
    else:
        if initial_rho is None:
            raise ValueError("initial_rho is required when not resuming")
        state = AcceptanceState(rho=np.clip(initial_rho, 0.0, 1.0), move_radius=spec.move_limit)
        parent_values = evaluate_values(state.rho)
        parent_result = evaluate_gradients(state.rho, parent_values)

    parent_eval = parent_result.to_evaluation()
    state.objective = parent_result.objective

    while state.iteration < spec.max_iterations:
        state.iteration += 1
        iteration_trace: dict[str, Any] = {
            "iteration": state.iteration,
            "parent_objective": parent_result.objective,
            "parent_constraints": dict(parent_result.constraint_values),
            "parent_gradient_space": parent_result.gradient_space,
            "transform_hash": parent_result.transform_hash,
            "move_radius_in": state.move_radius,
            "penalty_in": state.penalty,
        }

        def propose(working: AcceptanceState) -> TrialProposal:
            return backend.propose(
                rho=working.rho,
                objective_gradient=parent_result.objective_gradient,
                constraint_gradients=parent_result.constraint_gradients,
                constraint_values=parent_result.constraint_values,
                move_radius=working.move_radius,
                backend_state={},
            )

        last_value_result: OracleResult | None = None

        def evaluate_trial(rho_trial: np.ndarray, proposal: TrialProposal) -> TrialEvaluation:
            nonlocal last_value_result
            last_value_result = evaluate_values(rho_trial)
            return last_value_result.to_evaluation()

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
            # reuse the accepted trial's value payload; one adjoint for the new parent
            if last_value_result is None:
                raise ValueError("accepted trial has no value payload to reuse")
            parent_values = last_value_result
            parent_result = evaluate_gradients(state.rho, parent_values)
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
            _write_checkpoint(checkpoint_path, spec, state, trace, parent_result, counts)

    return LoopResult(
        trace=trace,
        final_rho=state.rho,
        final_evaluation=parent_result,
        accepted=state.accepted,
        rejected=state.rejected,
        transform_hash=transform.transform_hash(),
        counts=counts,
    )


def _checkpoint_binding(spec: LoopSpec) -> dict[str, Any]:
    return {
        "transform_hash": spec.transform.transform_hash(),
        "problem_spec_sha256": spec.compiled.problem_spec_sha256,
        "compiled_problem_hash": spec.compiled.compiled_problem_hash(),
        "backend_id": spec.backend_id,
        "oracle_profile": spec.oracle_profile,
    }


def _validate_checkpoint(checkpoint: dict[str, Any], spec: LoopSpec) -> None:
    if checkpoint.get("kind") != "stage_t_loop_checkpoint":
        raise ValueError("checkpoint kind is not stage_t_loop_checkpoint")
    expected = _checkpoint_binding(spec)
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise ValueError(
                f"checkpoint {key} mismatch: checkpoint={checkpoint.get(key)!r}, "
                f"current={value!r}; refusing to resume a different problem/transform/backend"
            )


def _write_checkpoint(
    path: Path,
    spec: LoopSpec,
    state: AcceptanceState,
    trace: list[dict[str, Any]],
    last_evaluation: OracleResult,
    counts: dict[str, int],
) -> None:
    payload = {
        "kind": "stage_t_loop_checkpoint",
        "schema_version": 2,
        **_checkpoint_binding(spec),
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
        "counts": dict(counts),
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
