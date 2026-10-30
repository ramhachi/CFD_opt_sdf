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
from .path_b_bracket import BracketSpec, evaluate_path_b_bracket
from .problem_spec_compiler import CompiledProblem


@dataclass(frozen=True)
class OracleResult:
    """Values and (optionally) gradients, bound to one primal artifact.

    ``adjoint_status`` is ``None`` for a values-only result and ``"converged"``
    only after an adjoint evaluation that verified its evidence. Trials never
    carry an adjoint status (PQ0.1 4.4).
    """

    objective: float
    constraint_values: dict[str, float]
    primal_converged: bool
    geometry_ok: bool = True
    geometry_metrics: dict[str, Any] = field(default_factory=dict)
    solver_status: str = "unknown"
    response_hash: str | None = None
    primal_artifact: dict[str, Any] | None = None
    artifact_hash: str | None = None
    objective_gradient: np.ndarray | None = None
    constraint_gradients: dict[str, np.ndarray] = field(default_factory=dict)
    gradient_space: str | None = None
    transform_hash: str | None = None
    adjoint_status: str | None = None

    def has_gradients(self) -> bool:
        return self.objective_gradient is not None

    def to_evaluation(self) -> TrialEvaluation:
        return TrialEvaluation(
            objective=self.objective,
            constraint_values=dict(self.constraint_values),
            primal_converged=self.primal_converged,
            geometry_ok=self.geometry_ok,
            adjoint_status="not_applicable",
            geometry_metrics=dict(self.geometry_metrics),
            solver_status=self.solver_status,
            primal_artifact_hash=self.artifact_hash,
        )


class ResponseOracle(Protocol):
    def evaluate_values(self, rho_design: np.ndarray) -> OracleResult:
        """Primal-only evaluation (values, constraints, gates, artifact)."""

    def evaluate_gradients(
        self, rho_design: np.ndarray, values: OracleResult
    ) -> OracleResult:
        """Adjoint evaluation consuming the accepted primal artifact."""


class ParentOracle(Protocol):
    """Optional fast path: one invocation returns values and gradients.

    A real solver that produces the primal and the adjoint in one qualified run
    can implement ``evaluate_parent``; the loop then uses it once per accepted
    parent instead of ``evaluate_values`` + ``evaluate_gradients``. Trials
    still use ``evaluate_values`` only.
    """

    def evaluate_parent(self, rho_design: np.ndarray) -> OracleResult:
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
    bisection. This is deliberately simple: PQ0 validates the acceptance
    machinery, a moving-asymptotes backend replaces the proposal step behind
    the same interface.
    """

    backend_id = "projected-gradient-constrained"

    def __init__(self, *, max_bisection: int = 40, bound_margin: float = 1e-6) -> None:
        self.max_bisection = max_bisection
        self.bound_margin = float(bound_margin)

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
        # A centered bracket needs every perturbed cell to be at least epsilon
        # away from both bounds, whatever the direction sign. The registered
        # margin therefore freezes cells closer than it to either bound.
        rho_values = np.asarray(rho, dtype=np.float64)
        margin = self.bound_margin
        direction[rho_values <= margin] = 0.0
        direction[rho_values >= 1.0 - margin] = 0.0

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


class VolumeTargetBackend:
    """Optimality-criteria style proposal with a registered volume target.

    The projected-gradient backend only respects an upper volume bound, so a
    downforce gradient alone never fills the material budget and the tanh
    projection then removes anything below the threshold. This backend
    multiplies the design toward the favourable cells and bisects a scalar
    multiplier so that ``mean(rho_new[active]) == target`` (subject to the move
    box). It is a *proposal* rule only: acceptance still requires the real
    primal, the constraints and the Path B bracket.
    """

    backend_id = "volume-target-oc"

    def __init__(self, *, target: float, eta: float = 0.5, bisection: int = 60) -> None:
        if not 0.0 < float(target) < 1.0:
            raise ValueError("volume target must be within (0, 1)")
        self.target = float(target)
        self.eta = float(eta)
        self.bisection = int(bisection)

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
        values = np.asarray(rho, dtype=np.float64)
        gradient = np.asarray(objective_gradient, dtype=np.float64)
        active = gradient != 0.0
        lower = np.clip(values - move_radius, 0.0, 1.0)
        upper = np.clip(values + move_radius, 0.0, 1.0)
        base = np.maximum(-gradient, 0.0) ** self.eta

        def candidate(kappa: float) -> np.ndarray:
            stepped = np.clip(values * base * kappa, lower, upper)
            stepped[~active] = values[~active]
            return stepped

        low, high = 0.0, 1.0
        while float(np.mean(candidate(high)[active])) < self.target and high < 1e16:
            high *= 10.0
        for _ in range(self.bisection):
            mid = 0.5 * (low + high)
            if float(np.mean(candidate(mid)[active])) < self.target:
                low = mid
            else:
                high = mid
        proposed = candidate(high)
        return TrialProposal(
            delta=proposed - values,
            backend=self.backend_id,
            metadata={
                "target": self.target,
                "eta": self.eta,
                "kappa": high,
                "mean_after": float(np.mean(proposed[active])),
            },
        )


class ProjectedVolumeTargetBackend:
    """OC-style proposal that bisects kappa to hit a *projected* volume target.

    The raw design-volume target of ``VolumeTargetBackend`` is not the quantity
    the volume constraint and the Stage S geometry see: the projection and the
    RAMP live between the design and the solver field, so a raw-design target
    does not survive continuation (measured in PQ3.2/3.3). This backend

    1. builds ``rho(kappa) = clip(values * max(-grad, 0)^eta * kappa, box)``;
    2. evaluates ``phi(kappa) = mean(rho_projection(rho(kappa))[active])``
       through the declared transform;
    3. bisects kappa until ``|phi - target| <= tolerance``, failing closed when
       even the box endpoints cannot bracket the target (the continuation step
       is too large; register an intermediate level instead).
    """

    backend_id = "projected-volume-target-oc"

    def __init__(
        self,
        *,
        transform,
        target: float,
        tolerance: float = 1e-4,
        eta: float = 0.5,
        bisection: int = 60,
    ) -> None:
        if not 0.0 < float(target) < 1.0:
            raise ValueError("projected volume target must be within (0, 1)")
        if tolerance <= 0.0:
            raise ValueError("projected volume tolerance must be positive")
        self.transform = transform
        self.target = float(target)
        self.tolerance = float(tolerance)
        self.eta = float(eta)
        self.bisection = int(bisection)

    def _projected_volume(self, kappa: float, values, base, lower, upper) -> tuple[float, np.ndarray]:
        stepped = np.clip(values * base * kappa, lower, upper)
        active = self.transform.active
        # non-active cells must be restored before the transform so the alpha/mask
        # contract survives; the OC update applies only to the active cells
        stepped[~active] = values[~active]
        state = self.transform.forward(stepped)
        return float(np.asarray(state.rho_projected, dtype=np.float64)[active].mean()), stepped

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
        values = np.asarray(rho, dtype=np.float64)
        gradient = np.asarray(objective_gradient, dtype=np.float64)
        base = np.maximum(-gradient, 0.0) ** self.eta
        lower = np.clip(values - move_radius, 0.0, 1.0)
        upper = np.clip(values + move_radius, 0.0, 1.0)

        def evaluate(kappa: float):
            return self._projected_volume(kappa, values, base, lower, upper)

        # bracket [lo, hi] kappa so that target is inside the reachable range
        phi_low, stepped_low = evaluate(0.0)
        hi = 1.0
        phi_hi, stepped_hi = evaluate(hi)
        grows = 0
        while phi_hi < self.target and grows < 30:
            hi *= 2.0
            phi_hi, stepped_hi = evaluate(hi)
            grows += 1
        if phi_low >= self.target:
            raise ValueError(
                "projected volume target is below the kappa=0 design; register a "
                "smaller target or expand the move box"
            )
        if phi_hi < self.target:
            raise ValueError(
                "projected volume target is unreachable inside the move box even at "
                f"kappa={hi:.3g}; register an intermediate continuation level"
            )
        low, high = 0.0, hi
        stepped = stepped_hi
        for _ in range(self.bisection):
            mid = 0.5 * (low + high)
            phi_mid, stepped_mid = evaluate(mid)
            if phi_mid < self.target:
                low = mid
            else:
                high = mid
                stepped = stepped_mid
        final_volume, stepped = evaluate(high)
        # the transform.active mask is authoritative: forbid any drift into the
        # fixed / forbidden / inactive cells (the OC base already zeroes out of
        # the descent direction but kappa can move them through the clip box)
        stepped[self.transform.active == False] = values[self.transform.active == False]  # noqa: E712
        if abs(final_volume - self.target) > self.tolerance:
            raise ValueError(
                f"projected volume target not reached: |{final_volume:.6f} - "
                f"{self.target:.6f}| > {self.tolerance}"
            )
        return TrialProposal(
            delta=stepped - values,
            backend=self.backend_id,
            metadata={
                "target": self.target,
                "kappa": high,
                "projected_volume_after": final_volume,
                "design_mean_after": float(np.mean(stepped[self.transform.active])),
            },
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
    bracket: BracketSpec | None = None
    trust_veto: bool = True


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


def _artifact_hash(
    rho: np.ndarray, transform: DesignTransform, payload: dict[str, Any]
) -> str:
    values = payload.get("values")
    encoded = json.dumps(
        {
            "rho_sha256": _rho_sha256(rho),
            "transform_hash": transform.transform_hash(),
            "response_hash": payload.get("response_hash"),
            "values": {
                f"{case}/{response}": float(value)
                for (case, response), value in sorted(values.items())
            }
            if isinstance(values, dict)
            else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _volume_value_gradient(
    *,
    transform: DesignTransform,
    compiled: CompiledProblem,
    rho: np.ndarray,
    constraint_values: dict[str, float],
) -> tuple[float | None, np.ndarray | None]:
    """Add the compiled projected-volume constraint (PQ0.1 4.2)."""

    volume_constraint = compiled.volume_constraint
    if volume_constraint is None:
        return None, None
    if volume_constraint.constraint_id in constraint_values:
        raise ValueError(
            f"volume constraint id {volume_constraint.constraint_id!r} collides with a "
            "response constraint id; ids must be unique"
        )
    value = volume_constraint.value(transform, rho)
    gradient = volume_constraint.gradient(transform, rho)
    return value, gradient


def make_oracle_from_compiled(
    *,
    transform: DesignTransform,
    compiled: CompiledProblem,
    primal_evaluator: Callable[[DesignTransformState], dict[str, Any]],
    adjoint_evaluator: Callable[
        [DesignTransformState, dict[str, Any]], dict[str, Any]
    ]
    | None = None,
    parent_evaluator: Callable[[DesignTransformState], dict[str, Any]] | None = None,
) -> Callable[..., OracleResult]:
    """Adapt split primal/adjoint evaluators to the two-space oracle protocol.

    ``primal_evaluator(state)`` returns ``values``, primal status, geometry
    status and an optional ``response_hash``; its payload becomes the bound
    primal artifact. ``adjoint_evaluator(state, primal_artifact)`` consumes
    that artifact, must not silently re-run the primal, and returns
    ``gradients`` in the solver-field (beta) space plus
    ``adjoint_converged: true``; the adapter maps the gradients to design space
    with ``transform.pullback_from_beta`` and adds the compiled volume
    constraint in projection space.
    """

    def _compile_values(rho: np.ndarray, payload: dict[str, Any]) -> OracleResult:
        primitive_values = payload["values"]
        objective = compiled.objective_value(primitive_values)
        constraint_values = compiled.constraint_values(primitive_values)
        volume_value, _ = _volume_value_gradient(
            transform=transform, compiled=compiled, rho=rho, constraint_values=constraint_values
        )
        if volume_value is not None:
            constraint_values = dict(constraint_values)
            constraint_values[compiled.volume_constraint.constraint_id] = volume_value
        return OracleResult(
            objective=objective,
            constraint_values=constraint_values,
            primal_converged=bool(payload.get("primal_converged", False)),
            geometry_ok=bool(payload.get("geometry_ok", True)),
            geometry_metrics=dict(payload.get("geometry_metrics", {})),
            solver_status=str(payload.get("solver_status", "unknown")),
            response_hash=payload.get("response_hash"),
            primal_artifact=payload,
            artifact_hash=_artifact_hash(rho, transform, payload),
        )

    def _compile_gradients(
        rho: np.ndarray, payload: dict[str, Any], values: OracleResult
    ) -> OracleResult:
        if payload.get("adjoint_converged") is not True:
            raise ValueError(
                "adjoint evaluation did not report converged=True; parent gradients "
                "are fail-closed and never defaulted"
            )
        raw_gradients = payload.get("gradients")
        if not isinstance(raw_gradients, dict) or not raw_gradients:
            raise ValueError("adjoint evaluation returned no solver-field gradients")
        design_gradients = {
            key: transform.pullback_from_beta(rho, np.asarray(gradient, dtype=np.float64))
            for key, gradient in raw_gradients.items()
        }
        response_constraint_values = {
            key: value
            for key, value in values.constraint_values.items()
            if key != compiled.volume_constraint.constraint_id
        } if compiled.volume_constraint is not None else dict(values.constraint_values)
        constraint_values = dict(values.constraint_values)
        constraint_gradients = compiled.constraint_gradients(design_gradients)
        volume_value, volume_gradient = _volume_value_gradient(
            transform=transform,
            compiled=compiled,
            rho=rho,
            constraint_values=response_constraint_values,
        )
        if volume_value is not None:
            constraint_values[compiled.volume_constraint.constraint_id] = volume_value
            constraint_gradients[compiled.volume_constraint.constraint_id] = volume_gradient
        return OracleResult(
            objective=values.objective,
            constraint_values=constraint_values,
            primal_converged=values.primal_converged,
            geometry_ok=values.geometry_ok,
            geometry_metrics=values.geometry_metrics,
            solver_status=values.solver_status,
            response_hash=values.response_hash,
            primal_artifact=values.primal_artifact,
            artifact_hash=values.artifact_hash,
            objective_gradient=compiled.objective_gradient(design_gradients),
            constraint_gradients=constraint_gradients,
            gradient_space="rho_design",
            transform_hash=transform.transform_hash(),
            adjoint_status="converged",
        )

    def _values(rho_design: np.ndarray) -> OracleResult:
        rho = np.asarray(rho_design, dtype=np.float64)
        state = transform.forward(rho)
        payload = primal_evaluator(state)
        return _compile_values(rho, payload)

    def _gradients(rho_design: np.ndarray, values: OracleResult) -> OracleResult:
        if adjoint_evaluator is None:
            raise ValueError("this oracle has no adjoint_evaluator; use evaluate_parent")
        if values.primal_artifact is None:
            raise ValueError(
                "evaluate_gradients requires the accepted primal artifact; a "
                "values-only result cannot seed an adjoint evaluation"
            )
        rho = np.asarray(rho_design, dtype=np.float64)
        expected_hash = _artifact_hash(rho, transform, values.primal_artifact)
        if values.artifact_hash != expected_hash:
            raise ValueError(
                "primal artifact does not belong to this rho/transform/response; "
                "refusing to run the adjoint on a mismatched artifact"
            )
        state = transform.forward(rho)
        payload = adjoint_evaluator(state, values.primal_artifact)
        return _compile_gradients(rho, payload, values)

    def _parent(rho_design: np.ndarray) -> OracleResult:
        if parent_evaluator is None:
            raise ValueError("this oracle has no parent_evaluator")
        rho = np.asarray(rho_design, dtype=np.float64)
        state = transform.forward(rho)
        payload = parent_evaluator(state)
        values = _compile_values(rho, payload)
        return _compile_gradients(rho, payload, values)

    class CompiledOracle:
        def evaluate_values(self, rho_design: np.ndarray) -> OracleResult:
            return _values(rho_design)

        def evaluate_gradients(
            self, rho_design: np.ndarray, values: OracleResult
        ) -> OracleResult:
            return _gradients(rho_design, values)

    if parent_evaluator is not None:
        def evaluate_parent(self, rho_design: np.ndarray) -> OracleResult:
            return _parent(rho_design)

        CompiledOracle.evaluate_parent = evaluate_parent  # type: ignore[attr-defined]

    return CompiledOracle()


def _call_values(oracle: Any, rho: np.ndarray) -> OracleResult:
    return oracle.evaluate_values(rho)


def _call_gradients(oracle: Any, rho: np.ndarray, values: OracleResult) -> OracleResult:
    result = oracle.evaluate_gradients(rho, values)
    if not result.has_gradients():
        raise ValueError("evaluate_gradients returned a result without gradients")
    if result.adjoint_status != "converged":
        raise ValueError(
            "parent gradients require adjoint_status='converged'; "
            "missing evidence is fail-closed"
        )
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
    counts = {
        "value_evaluations": 0,
        "gradient_evaluations": 0,
        "parent_evaluations": 0,
        "bracket_evaluations": 0,
    }
    trace: list[dict[str, Any]] = []

    def evaluate_values(rho: np.ndarray) -> OracleResult:
        counts["value_evaluations"] += 1
        return _call_values(oracle, rho)

    def evaluate_gradients(rho: np.ndarray, values: OracleResult) -> OracleResult:
        counts["gradient_evaluations"] += 1
        return _call_gradients(oracle, rho, values)

    parent_oracle = getattr(oracle, "evaluate_parent", None)
    if parent_oracle is not None:
        def evaluate_parent(rho: np.ndarray) -> OracleResult:
            counts["parent_evaluations"] += 1
            result = parent_oracle(rho)
            if not result.has_gradients():
                raise ValueError("evaluate_parent returned a result without gradients")
            if result.adjoint_status != "converged":
                raise ValueError(
                    "parent gradients require adjoint_status='converged'; "
                    "missing evidence is fail-closed"
                )
            return result

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
        if parent_oracle is not None:
            parent_values = parent_result = evaluate_parent(state.rho)
        else:
            parent_values = evaluate_values(state.rho)
            parent_result = evaluate_gradients(state.rho, parent_values)
    else:
        if initial_rho is None:
            raise ValueError("initial_rho is required when not resuming")
        state = AcceptanceState(rho=np.clip(initial_rho, 0.0, 1.0), move_radius=spec.move_limit)
        if parent_oracle is not None:
            parent_values = parent_result = evaluate_parent(state.rho)
        else:
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

        pre_accept_gate = None
        if spec.bracket is not None:
            def pre_accept_gate(proposal, trial_rho):
                counts["bracket_evaluations"] += 1
                outcome = evaluate_path_b_bracket(
                    spec=spec.bracket,
                    parent_rho=state.rho,
                    parent_gradient=parent_result.objective_gradient,
                    proposal_delta=proposal.delta,
                    active=transform.active,
                    evaluate_values=evaluate_values,
                )
                return outcome.ok, outcome.to_dict()

        decision, trial_rho, inner_trace = run_conservative_inner_loop(
            parent=parent_eval,
            state=state,
            propose=propose,
            evaluate=evaluate_trial,
            predicted_objective=lambda proposal: _linear_prediction(
                parent=parent_result, proposal=proposal, transform=transform
            ),
            max_inner_iterations=spec.max_inner_iterations,
            pre_accept_gate=pre_accept_gate,
            trust_veto=spec.trust_veto,
        )
        iteration_trace["inner"] = inner_trace
        if decision.accepted and trial_rho is not None:
            state.rho = trial_rho
            state.accepted += 1
            # reuse the accepted trial's value payload; one adjoint for the new parent
            if last_value_result is None:
                raise ValueError("accepted trial has no value payload to reuse")
            if parent_oracle is not None:
                parent_values = parent_result = evaluate_parent(state.rho)
            else:
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


def _bracket_hash(spec: LoopSpec) -> str | None:
    if spec.bracket is None:
        return None
    import json as _json

    return hashlib.sha256(
        _json.dumps(spec.bracket.__dict__, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _checkpoint_binding(spec: LoopSpec) -> dict[str, Any]:
    return {
        "transform_hash": spec.transform.transform_hash(),
        "problem_spec_sha256": spec.compiled.problem_spec_sha256,
        "compiled_problem_hash": spec.compiled.compiled_problem_hash(),
        "backend_id": spec.backend_id,
        "oracle_profile": spec.oracle_profile,
        "bracket_hash": _bracket_hash(spec),
        "trust_veto": bool(spec.trust_veto),
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
    "ProjectedVolumeTargetBackend",
    "ResponseOracle",
    "TrialBackend",
    "VolumeTargetBackend",
    "make_oracle_from_compiled",
    "run_stage_t_loop",
]
