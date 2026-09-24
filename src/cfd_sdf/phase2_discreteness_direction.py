"""Projected Phase 2 direction for the active discreteness constraint.

This module is deliberately separate from ``phase2_inequality_policy``.  The
v1/v2 sign-step policies keep their registered behaviour; v13 only uses the
raw-gradient direction below in its bounded one-step discriminant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from cfd_sdf.canonical_objective import canonical_objective_from
from cfd_sdf.path_b_bracket import BracketSpec, evaluate_path_b_bracket
from cfd_sdf.phase2_inequality_policy import (
    BOX_TOLERANCE,
    EXTRACTABILITY_FRACTION,
    EXTRACTABILITY_THRESHOLDS,
    MASK_DRIFT_TOLERANCE,
    MIN_CORRECTED_UPDATE_INF_NORM,
    OCCUPANCY_THRESHOLDS,
)

POLICY_ID = "objective-gradient-discreteness-projected-v1"


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(array.tobytes()).hexdigest()


def _mean_nd(projected: np.ndarray, active: np.ndarray) -> float:
    values = projected[active]
    return float(np.mean(4.0 * values * (1.0 - values)))


def _occupancy(projected: np.ndarray, active: np.ndarray) -> dict[str, Any]:
    values = projected[active]
    result: dict[str, Any] = {"total_active": int(values.size)}
    for threshold in OCCUPANCY_THRESHOLDS:
        count = int(np.count_nonzero(values > threshold))
        result[f"cells_gt_{threshold}"] = count
        result[f"fraction_gt_{threshold}"] = count / values.size if values.size else 0.0
    return result


@dataclass(frozen=True)
class ProjectedDirection:
    values: np.ndarray
    discreteness_gradient: np.ndarray
    free: np.ndarray
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class TransformCandidate:
    alpha: float
    rho: np.ndarray
    metrics: dict[str, Any]
    gates: dict[str, bool]
    discreteness_mean_nd_max: float
    v_max: float

    @property
    def feasible(self) -> bool:
        return bool(all(self.gates.values()))

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "alpha": float(self.alpha),
            "rho_sha256": _array_sha256(self.rho),
            "metrics": dict(self.metrics),
            "gates": dict(self.gates),
            "discreteness_mean_nd_max": float(self.discreteness_mean_nd_max),
            "v_max": float(self.v_max),
            "transform_feasible": self.feasible,
        }


def projected_raw_gradient_direction(
    *,
    transform,
    rho: np.ndarray,
    objective_gradient: np.ndarray,
    freeze_box_faces: bool = True,
) -> ProjectedDirection:
    """Project ``-gJ`` onto the linearized ``mean_nd`` tangent half-space."""

    values = np.asarray(rho, dtype=np.float64)
    gradient = np.asarray(objective_gradient, dtype=np.float64)
    if values.shape != gradient.shape or values.shape != np.asarray(transform.active).shape:
        raise ValueError("rho, objective gradient, and transform active mask must share shape")
    if not np.isfinite(values).all() or not np.isfinite(gradient).all():
        raise ValueError("rho and objective gradient must be finite")

    active = np.asarray(transform.active, dtype=bool)
    active_count = int(np.count_nonzero(active))
    if active_count == 0:
        raise ValueError("discreteness direction requires at least one active cell")
    frozen = active & ((values == 0.0) | (values == 1.0)) if freeze_box_faces else np.zeros_like(active)
    free = active & ~frozen
    state = transform.forward(values)
    projected = np.asarray(state.rho_projected, dtype=np.float64)
    seed = np.zeros_like(values)
    seed[active] = 4.0 * (1.0 - 2.0 * projected[active]) / active_count
    g_discreteness = np.asarray(
        transform.pullback_from_projected(values, seed), dtype=np.float64
    )

    direction_0 = np.zeros_like(values)
    direction_0[free] = -gradient[free]
    g_free = np.zeros_like(values)
    g_free[free] = g_discreteness[free]
    directional_before = float(np.dot(g_discreteness, direction_0))
    denominator = float(np.dot(g_free, g_free))
    coefficient = 0.0
    direction = direction_0.copy()
    if directional_before > 0.0:
        if denominator <= 0.0:
            raise ValueError("positive discreteness derivative has no free-cell gradient")
        coefficient = directional_before / denominator
        direction -= coefficient * g_free
    direction[~free] = 0.0
    peak = float(np.max(np.abs(direction[free]))) if bool(free.any()) else 0.0
    if peak <= 0.0 or not np.isfinite(peak):
        raise ValueError("projected objective direction is zero or non-finite")
    direction /= peak

    diagnostics = {
        "policy_id": POLICY_ID,
        "active_cells": active_count,
        "free_cells": int(np.count_nonzero(free)),
        "frozen_box_face_cells": int(np.count_nonzero(frozen)),
        "objective_gradient_sha256": _array_sha256(gradient),
        "discreteness_gradient_sha256": _array_sha256(g_discreteness),
        "direction_sha256": _array_sha256(direction),
        "projection_applied": bool(directional_before > 0.0),
        "projection_coefficient": float(coefficient),
        "g_discreteness_dot_d0": directional_before,
        "g_discreteness_dot_direction": float(np.dot(g_discreteness, direction)),
        "g_objective_dot_direction": float(np.dot(gradient, direction)),
        "direction_inf_norm": float(np.max(np.abs(direction))),
    }
    return ProjectedDirection(direction, g_discreteness, free, diagnostics)


def transform_candidate(
    *,
    transform,
    rho: np.ndarray,
    direction: np.ndarray,
    alpha: float,
    move_limit: float,
    discreteness_mean_nd_max: float,
    v_max: float,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
    support_allowed_cells: np.ndarray | None = None,
) -> TransformCandidate:
    """Build one move-box candidate and apply solver-free registered gates."""

    values = np.asarray(rho, dtype=np.float64)
    step_direction = np.asarray(direction, dtype=np.float64)
    if values.shape != step_direction.shape:
        raise ValueError("rho and direction must share shape")
    if not np.isfinite(alpha) or float(alpha) <= 0.0:
        raise ValueError("alpha must be finite and positive")
    if not np.isfinite(move_limit) or float(move_limit) <= 0.0:
        raise ValueError("move_limit must be finite and positive")

    active = np.asarray(transform.active, dtype=bool)
    frozen = active & ((values == 0.0) | (values == 1.0)) if freeze_box_faces else np.zeros_like(active)
    lower = np.clip(values - float(move_limit), 0.0, 1.0)
    upper = np.clip(values + float(move_limit), 0.0, 1.0)
    proposal = np.clip(
        values + float(alpha) * float(move_limit) * step_direction,
        lower,
        upper,
    )
    proposal[~active] = values[~active]
    proposal[frozen] = values[frozen]

    parent_projected = np.asarray(transform.forward(values).rho_projected, dtype=np.float64)
    candidate_projected = np.asarray(transform.forward(proposal).rho_projected, dtype=np.float64)
    if support_allowed_cells is not None:
        allowed_cells = np.asarray(support_allowed_cells, dtype=bool)
        if allowed_cells.shape != values.shape:
            raise ValueError("support_allowed_cells must share the design shape")
        support_violations = int(np.count_nonzero((candidate_projected > 0.5) & ~allowed_cells))
    else:
        support_violations = 0
    parent_occupancy = _occupancy(parent_projected, active)
    candidate_occupancy = _occupancy(candidate_projected, active)
    delta = proposal - values
    violation = np.maximum(proposal - upper, lower - proposal)
    mask_drift = float(np.max(np.abs(delta[~active]))) if bool((~active).any()) else 0.0
    metrics = {
        "corrected_update_inf_norm": float(np.max(np.abs(delta))),
        "discreteness_mean_nd_parent": _mean_nd(parent_projected, active),
        "discreteness_mean_nd_candidate": _mean_nd(candidate_projected, active),
        "projected_volume_parent": float(np.mean(parent_projected[active])),
        "projected_volume_candidate": float(np.mean(candidate_projected[active])),
        "projected_field_mean_abs_delta": float(
            np.mean(np.abs(candidate_projected[active] - parent_projected[active]))
        ),
        "projected_field_max_abs_delta": float(
            np.max(np.abs(candidate_projected[active] - parent_projected[active]))
        ),
        "mask_drift_max": mask_drift,
        "move_box_violation_max": float(max(0.0, np.max(violation))),
        "occupancy_parent": parent_occupancy,
        "occupancy_candidate": candidate_occupancy,
        "support_violations": support_violations,
    }
    extractability_ok = all(
        candidate_occupancy[f"cells_gt_{threshold}"]
        >= float(extractability_fraction) * parent_occupancy[f"cells_gt_{threshold}"]
        for threshold in EXTRACTABILITY_THRESHOLDS
    )
    gates = {
        "corrected_update_above_machine_scale": bool(
            metrics["corrected_update_inf_norm"] >= float(min_update_inf_norm)
        ),
        "projected_discreteness_within_limit": bool(
            metrics["discreteness_mean_nd_candidate"] <= float(discreteness_mean_nd_max)
        ),
        "projected_volume_within_v_max": bool(
            metrics["projected_volume_candidate"] <= float(v_max)
        ),
        "extractability_guard": bool(extractability_ok),
        "mask_invariance": bool(mask_drift <= MASK_DRIFT_TOLERANCE),
        "move_box_respected": bool(
            metrics["move_box_violation_max"] <= BOX_TOLERANCE
        ),
        "support_clearance": bool(support_violations == 0),
    }
    return TransformCandidate(
        float(alpha),
        proposal,
        metrics,
        gates,
        float(discreteness_mean_nd_max),
        float(v_max),
    )


def backtrack_transform_candidates(
    *,
    transform,
    rho: np.ndarray,
    direction: np.ndarray,
    ladder: tuple[float, ...],
    move_limit: float,
    discreteness_mean_nd_max: float,
    v_max: float,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
) -> tuple[list[TransformCandidate], TransformCandidate | None]:
    """Return the ledger through the first transform-feasible candidate."""

    ledger: list[TransformCandidate] = []
    for alpha in ladder:
        candidate = transform_candidate(
            transform=transform,
            rho=rho,
            direction=direction,
            alpha=alpha,
            move_limit=move_limit,
            discreteness_mean_nd_max=discreteness_mean_nd_max,
            v_max=v_max,
            freeze_box_faces=freeze_box_faces,
            min_update_inf_norm=min_update_inf_norm,
            extractability_fraction=extractability_fraction,
        )
        ledger.append(candidate)
        if candidate.feasible:
            return ledger, candidate
    return ledger, None


def transform_candidates_full(
    *,
    transform,
    rho: np.ndarray,
    direction: np.ndarray,
    ladder: tuple[float, ...],
    move_limit: float,
    discreteness_mean_nd_max: float,
    v_max: float,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
    support_allowed_cells: np.ndarray | None = None,
) -> list[TransformCandidate]:
    """Evaluate every registered ladder alpha at the transform level."""

    return [
        transform_candidate(
            transform=transform,
            rho=rho,
            direction=direction,
            alpha=alpha,
            move_limit=move_limit,
            discreteness_mean_nd_max=discreteness_mean_nd_max,
            v_max=v_max,
            freeze_box_faces=freeze_box_faces,
            min_update_inf_norm=min_update_inf_norm,
            extractability_fraction=extractability_fraction,
            support_allowed_cells=support_allowed_cells,
        )
        for alpha in ladder
    ]


def _campaign_record(candidate: TransformCandidate) -> dict[str, Any]:
    """Flatten one transform candidate into the shared campaign ledger shape."""

    payload = candidate.to_jsonable()
    metrics = candidate.metrics
    failed_gates = sorted(name for name, passed in candidate.gates.items() if not passed)
    reason_by_gate = {
        "corrected_update_above_machine_scale": "machine_scale_update_rejected",
        "projected_discreteness_within_limit": "discreteness_limit_exceeded",
        "projected_volume_within_v_max": "projected_volume_limit_exceeded",
        "extractability_guard": "extractability_guard_failed",
        "mask_invariance": "mask_invariance_failed",
        "move_box_respected": "move_box_violation",
        "support_clearance": "support_clearance_violated",
    }
    failure_reasons = [reason_by_gate[name] for name in failed_gates]
    payload.update(
        {
            "accepted": False,
            "reason": (
                "+".join(failure_reasons)
                if failed_gates
                else "transform_feasible_response_pending"
            ),
            "failed_transform_gates": failed_gates,
            "transform_failure_reasons": failure_reasons,
            "corrected_rho_sha256": payload["rho_sha256"],
            "corrected_update_inf_norm": metrics["corrected_update_inf_norm"],
            "phi_after": metrics["projected_volume_candidate"],
            "projected_volume_delta": (
                metrics["projected_volume_candidate"]
                - metrics["projected_volume_parent"]
            ),
            "occupancy": metrics["occupancy_candidate"],
            "occupancy_parent": metrics["occupancy_parent"],
            "discreteness_mean_nd_parent": metrics[
                "discreteness_mean_nd_parent"
            ],
            "discreteness_mean_nd_candidate": metrics[
                "discreteness_mean_nd_candidate"
            ],
            "discreteness_mean_nd_max": candidate.discreteness_mean_nd_max,
            "discreteness_field": "rho_projection",
            "discreteness_scope": "transform.active",
            "mask_drift_max": metrics["mask_drift_max"],
            "move_box_violation_max": metrics["move_box_violation_max"],
            "bracket": None,
            "bracket_ok": False,
            "trial_objective": None,
            "trial_downforce": None,
            "trial_primal_converged": False,
            "trial_run": None,
        }
    )
    return payload


def _new_evaluator_calls() -> dict[str, Any]:
    return {
        "path_b_evaluator_requests": 0,
        "trial_evaluator_requests": 0,
        "path_b_proven_fresh_solver_runs": 0,
        "trial_proven_fresh_solver_runs": 0,
        "path_b_freshness_unknown": 0,
        "trial_freshness_unknown": 0,
        "path_b_requests": [],
    }


def _record_path_b(counter: dict[str, Any], evidence: dict[str, Any]) -> None:
    counter["path_b_evaluator_requests"] += 1
    counter["path_b_requests"].append(
        {"request_index": counter["path_b_evaluator_requests"], **evidence}
    )
    reused = evidence.get("reused")
    if reused is False and evidence.get("summary_sha256"):
        counter["path_b_proven_fresh_solver_runs"] += 1
    elif reused is None:
        counter["path_b_freshness_unknown"] += 1


def _record_trial(counter: dict[str, Any], trial_run: Any) -> None:
    counter["trial_evaluator_requests"] += 1
    if isinstance(trial_run, dict) and "reused" in trial_run:
        if trial_run["reused"] is False:
            counter["trial_proven_fresh_solver_runs"] += 1
    else:
        counter["trial_freshness_unknown"] += 1


def _run_evidence(result: Any) -> dict[str, Any]:
    """Extract solver evidence without treating an evaluator request as a run."""

    payload = getattr(result, "primal_artifact", None)
    if not isinstance(payload, dict):
        return {}
    record = payload.get("artifact", payload)
    if not isinstance(record, dict):
        return {}
    summary = record.get("summary", {})
    return {
        "case_dir": record.get("case_dir"),
        "summary_json": record.get("summary_json"),
        "summary_sha256": record.get("summary_sha256"),
        "source_rho_sha256": record.get("source_rho_sha256"),
        "primal_iterations": record.get("primal_iterations"),
        "solver_status": (
            summary.get("status", getattr(result, "solver_status", None))
            if isinstance(summary, dict)
            else getattr(result, "solver_status", None)
        ),
        "reused": record.get("reused"),
    }


def evaluate_phase2_discreteness_direction(
    *,
    transform,
    parent_result: Any,
    rho_parent: np.ndarray,
    parent_downforce: float,
    move_limit: float,
    ladder: tuple[float, ...],
    v_max: float,
    discreteness_mean_nd_max: float,
    objective_noise_threshold: float,
    downforce_noise_threshold: float,
    bracket_spec: BracketSpec,
    evaluate_values: Callable[[np.ndarray], Any],
    evaluate_trial: Callable[[np.ndarray], tuple[Any, dict]],
    return_rho: bool = False,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
    support_allowed_cells: np.ndarray | None = None,
) -> dict | tuple[dict, np.ndarray | None]:
    """Evaluate the projected raw-gradient policy with a response-level ladder.

    Every ladder entry is first checked by deterministic transform gates
    (machine-scale update, discreteness bound, volume cap, extractability,
    support clearance, masks and the move box).  The transform-feasible
    candidates are then evaluated in registered ladder order — centered Path B
    pair plus trial primal — until one passes the full gate set.  Backtracking
    continues to the next smaller transform-feasible alpha only after Path B
    passes and the trial response gates fail; a Path B failure stops
    fail-closed, because the policy is diagnosing nonlinear response, not
    bypassing gradient qualification.  Transform-infeasible alphas never
    consume solver calls.
    """

    parent_objective, objective_gradient = canonical_objective_from(parent_result)
    rho_array = np.asarray(rho_parent, dtype=np.float64)
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho_array,
        objective_gradient=np.asarray(objective_gradient, dtype=np.float64),
        freeze_box_faces=freeze_box_faces,
    )
    ledger = transform_candidates_full(
        transform=transform,
        rho=rho_array,
        direction=direction.values,
        ladder=ladder,
        move_limit=move_limit,
        discreteness_mean_nd_max=discreteness_mean_nd_max,
        v_max=v_max,
        freeze_box_faces=freeze_box_faces,
        min_update_inf_norm=min_update_inf_norm,
        extractability_fraction=extractability_fraction,
        support_allowed_cells=support_allowed_cells,
    )
    records = [_campaign_record(candidate) for candidate in ledger]
    accepted_rho = None
    accepted_alpha = None
    cumulative_calls = _new_evaluator_calls()

    # Response-level ladder: every transform-feasible candidate is evaluated in
    # registered ladder order until one passes the full gate set. Transform-
    # infeasible alphas never consume solver calls. A Path B failure stops the
    # ladder fail-closed; backtracking continues only after Path B passes and
    # the trial response gates fail.
    for candidate, record in zip(ledger, records, strict=True):
        if not candidate.feasible:
            continue
        candidate_calls = _new_evaluator_calls()

        def counted_values(candidate_rho: np.ndarray):
            result = evaluate_values(candidate_rho)
            evidence = _run_evidence(result)
            for counter in (cumulative_calls, candidate_calls):
                _record_path_b(counter, evidence)
            return result

        delta = candidate.rho - rho_array
        bracket = evaluate_path_b_bracket(
            spec=bracket_spec,
            parent_rho=rho_array,
            parent_gradient=np.asarray(objective_gradient, dtype=np.float64),
            proposal_delta=delta,
            active=np.asarray(transform.active, dtype=bool),
            evaluate_values=counted_values,
        )
        record["bracket"] = bracket.to_dict()
        record["bracket_ok"] = bool(bracket.ok)
        response_gates = {
            "d_adj_negative": bool(
                bracket.d_adj is not None and bracket.d_adj < 0.0
            ),
            "d_fd_below_negative_noise_floor": bool(
                bracket.d_fd is not None
                and bracket.d_fd < -float(bracket_spec.noise_floor_abs)
            ),
            "sign_match": bool(
                bracket.d_adj is not None
                and bracket.d_fd is not None
                and np.sign(bracket.d_adj) == np.sign(bracket.d_fd)
            ),
        }
        if bracket.ok:
            trial_result, trial_run = evaluate_trial(candidate.rho)
            for counter in (cumulative_calls, candidate_calls):
                _record_trial(counter, trial_run)
            record["trial_objective"] = float(trial_result.objective)
            record["trial_primal_converged"] = bool(trial_result.primal_converged)
            record["trial_run"] = trial_run
            trial_downforce = None
            if isinstance(trial_run, dict):
                value = trial_run.get("downforce_coefficient")
                if value is None and isinstance(trial_run.get("summary"), dict):
                    value = trial_run["summary"].get("downforce_coefficient")
                trial_downforce = None if value is None else float(value)
            record["trial_downforce"] = trial_downforce
            response_gates.update(
                {
                    "canonical_objective_improved": bool(
                        float(trial_result.objective)
                        < parent_objective - float(objective_noise_threshold)
                    ),
                    "raw_downforce_improved": bool(
                        trial_downforce is not None
                        and trial_downforce
                        > float(parent_downforce) + float(downforce_noise_threshold)
                    ),
                    "trial_primal_converged": bool(trial_result.primal_converged),
                }
            )
        else:
            response_gates.update(
                {
                    "canonical_objective_improved": False,
                    "raw_downforce_improved": False,
                    "trial_primal_converged": False,
                }
            )
        record["gates"].update(response_gates)
        record["evaluator_calls"] = candidate_calls
        record["accepted"] = bool(all(record["gates"].values()))
        if record["accepted"]:
            record["reason"] = "accepted"
            accepted_rho = candidate.rho.copy()
            accepted_alpha = float(candidate.alpha)
            break
        record["reason"] = "path_b_failed" if not bracket.ok else "response_gates_failed"
        if not bracket.ok:
            # fail-closed: a Path B failure ends the attempt; v15 diagnoses
            # nonlinear response rather than bypassing gradient qualification
            break

    payload: dict[str, Any] = {
        "policy_id": POLICY_ID,
        "direction": direction.diagnostics,
        "ladder": [float(alpha) for alpha in ladder],
        "candidates": records,
        "evaluator_calls": cumulative_calls,
        "accepted_alpha": None,
        "all_failed": accepted_rho is None,
        "successful": accepted_rho is not None,
        "corrected_rho_sha256": None,
    }
    if accepted_rho is not None:
        payload["accepted_alpha"] = accepted_alpha
        payload["corrected_rho_sha256"] = _array_sha256(accepted_rho)
    else:
        payload["error"] = (
            "no projected-direction alpha satisfied the registered gates; fail-closed"
        )
    return (payload, accepted_rho) if return_rho else payload


__all__ = [
    "POLICY_ID",
    "ProjectedDirection",
    "TransformCandidate",
    "backtrack_transform_candidates",
    "evaluate_phase2_discreteness_direction",
    "projected_raw_gradient_direction",
    "transform_candidate",
    "transform_candidates_full",
]
