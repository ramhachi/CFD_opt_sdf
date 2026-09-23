"""Phase 2 inequality policy (v6): objective steps under V <= Vmax.

Registered change per ``docs/evidence/pq3_3b_d2_change_manifest_2026_09.json``:

- proposal ``clip(rho - alpha * move * sign(gradJ), box)`` with the v5
  box-face freeze; no equality volume correction. The D1 discriminant measured
  the equality target 0.018 as the objective blocker: the registered corrected
  step (d1) improved by only 2.7e-7 (below the 1e-6 threshold), while the
  objective-only direction (d2) improved by +0.1340 and the orthogonal volume
  exchange (d3) by +0.0279 at the same parent with unchanged thresholds.
- the projected volume must satisfy the original inequality ``V <= Vmax``;
  the equality target 0.018 remains only as the Phase 1 formation target.
- a corrected-update inf-norm gate rejects machine-scale updates before any
  bracket normalization could qualify them. D0 measured machine-scale
  corrected norms <= 2.8e-17 and the smallest detectable D1 step at 0.03
  inf-norm; the registered threshold 1e-8 sits far above the float noise and
  far below meaningful steps.
- an extractability guard prevents the solid-count collapse that the
  upper-bound-only operation historically produced. It is a guard, not a
  substitute for the PQ4.1 composite gate; full occupancy is recorded per
  candidate.

Phase 1 restoration (projected-volume-restoration-oc) is unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

from cfd_sdf.canonical_objective import canonical_objective_from
from cfd_sdf.path_b_bracket import BracketSpec, evaluate_path_b_bracket
from cfd_sdf.projected_restoration import _restore

POLICY_ID = "objective-oc-inequality-v1"
MIN_CORRECTED_UPDATE_INF_NORM = 1e-8
MASK_DRIFT_TOLERANCE = 1e-12
BOX_TOLERANCE = 1e-12
EXTRACTABILITY_FRACTION = 0.5
EXTRACTABILITY_THRESHOLDS = (0.4, 0.5)
OCCUPANCY_THRESHOLDS = (0.3, 0.4, 0.5, 0.6)


@dataclass
class InequalityCandidate:
    """One alpha's measured candidate under the inequality policy."""

    alpha: float
    frozen_box_face_cells: int = 0
    accepted: bool = False
    reason: str = "not_evaluated"
    corrected_rho_sha256: str | None = None
    corrected_update_inf_norm: float | None = None
    phi_after: float | None = None
    projected_volume_delta: float | None = None
    occupancy: dict | None = None
    occupancy_parent: dict | None = None
    mask_drift_max: float | None = None
    move_box_violation_max: float | None = None
    bracket: dict | None = None
    bracket_ok: bool = False
    trial_objective: float | None = None
    trial_downforce: float | None = None
    trial_primal_converged: bool = False
    trial_run: dict | None = None
    gate_detail: dict = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("gate_detail", None)
        payload["gates"] = {key: bool(value) for key, value in self.gate_detail.items()}
        return payload


def occupancy_metrics(transform, rho: np.ndarray, active: np.ndarray) -> dict:
    """Projected-field occupancy counts/fractions at the registered thresholds."""
    projected = np.asarray(
        transform.forward(np.asarray(rho, dtype=np.float64)).rho_projected,
        dtype=np.float64,
    )
    values = projected[active]
    total = int(values.size)
    metrics = {"total_active": total}
    for threshold in OCCUPANCY_THRESHOLDS:
        count = int(np.count_nonzero(values > threshold))
        metrics[f"cells_gt_{threshold}"] = count
        metrics[f"fraction_gt_{threshold}"] = (count / total) if total else 0.0
    return metrics


def _array_sha256(values: np.ndarray) -> str:
    import hashlib

    raw = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    return hashlib.sha256(raw.tobytes()).hexdigest()


def evaluate_inequality_candidate(
    *,
    transform,
    parent_result: Any,
    rho_parent: np.ndarray,
    parent_downforce: float,
    alpha: float,
    move_limit: float,
    v_max: float,
    objective_noise_threshold: float,
    downforce_noise_threshold: float,
    bracket_spec: BracketSpec,
    evaluate_values: Callable[[np.ndarray], Any],
    evaluate_trial: Callable[[np.ndarray], tuple[Any, dict]],
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
) -> tuple[InequalityCandidate, np.ndarray]:
    """One alpha under the registered inequality policy; fail-closed gates."""
    parent_objective, gradient = canonical_objective_from(parent_result)
    candidate = InequalityCandidate(alpha=float(alpha))
    values = np.asarray(rho_parent, dtype=np.float64)
    move_limit = float(move_limit)
    box_low = np.clip(values - move_limit, 0.0, 1.0)
    box_high = np.clip(values + move_limit, 0.0, 1.0)
    active = np.asarray(transform.active, dtype=bool)
    frozen = active & ((values == 0.0) | (values == 1.0)) if freeze_box_faces else np.zeros_like(active)
    candidate.frozen_box_face_cells = int(np.count_nonzero(frozen))

    proposal = np.clip(values - float(alpha) * move_limit * np.sign(gradient), box_low, box_high)
    proposal[frozen] = values[frozen]
    proposal = _restore(proposal, values, active)
    delta = proposal - values
    candidate.corrected_rho_sha256 = _array_sha256(proposal)
    candidate.corrected_update_inf_norm = float(np.max(np.abs(delta)))
    if candidate.corrected_update_inf_norm < float(min_update_inf_norm):
        candidate.reason = "machine_scale_update_rejected"
        candidate.gate_detail = {"corrected_update_above_machine_scale": False}
        return candidate, values

    phi_parent = float(
        np.asarray(transform.forward(values).rho_projected, dtype=np.float64)[active].mean()
    )
    phi_after = float(
        np.asarray(transform.forward(proposal).rho_projected, dtype=np.float64)[active].mean()
    )
    candidate.phi_after = phi_after
    candidate.projected_volume_delta = phi_after - phi_parent
    parent_occupancy = occupancy_metrics(transform, values, active)
    candidate_occupancy = occupancy_metrics(transform, proposal, active)
    candidate.occupancy = candidate_occupancy
    candidate.occupancy_parent = parent_occupancy

    mask_drift = 0.0
    if bool((~active).any()):
        mask_drift = float(np.max(np.abs(proposal[~active] - values[~active])))
    candidate.mask_drift_max = mask_drift
    violation = np.maximum(proposal - box_high, box_low - proposal)
    candidate.move_box_violation_max = float(max(0.0, np.max(violation)))

    outcome = evaluate_path_b_bracket(
        spec=bracket_spec,
        parent_rho=values,
        parent_gradient=gradient,
        proposal_delta=delta,
        active=active,
        evaluate_values=evaluate_values,
    )
    candidate.bracket = outcome.to_dict()
    candidate.bracket_ok = bool(outcome.ok)

    trial_result, trial_run = evaluate_trial(proposal)
    candidate.trial_objective = float(trial_result.objective)
    candidate.trial_primal_converged = bool(trial_result.primal_converged)
    candidate.trial_run = trial_run
    trial_downforce_value = None
    if isinstance(trial_run, dict):
        value = trial_run.get("downforce_coefficient")
        if value is None and isinstance(trial_run.get("summary"), dict):
            value = trial_run["summary"].get("downforce_coefficient")
        trial_downforce_value = None if value is None else float(value)
    candidate.trial_downforce = trial_downforce_value

    update_ok = bool(candidate.corrected_update_inf_norm >= float(min_update_inf_norm))
    vmax_ok = bool(phi_after <= float(v_max))
    extractability_ok = all(
        candidate_occupancy[f"cells_gt_{threshold}"]
        >= float(extractability_fraction) * parent_occupancy[f"cells_gt_{threshold}"]
        for threshold in EXTRACTABILITY_THRESHOLDS
    )
    adj_ok = bool(outcome.d_adj is not None and outcome.d_adj < 0.0)
    fd_ok = bool(
        outcome.d_fd is not None
        and outcome.d_fd < -float(bracket_spec.noise_floor_abs)
    )
    sign_ok = bool(
        outcome.d_adj is not None
        and outcome.d_fd is not None
        and np.sign(outcome.d_adj) == np.sign(outcome.d_fd)
    )
    objective_ok = bool(
        candidate.trial_objective is not None
        and candidate.trial_objective < parent_objective - float(objective_noise_threshold)
    )
    downforce_ok = bool(
        candidate.trial_downforce is not None
        and candidate.trial_downforce > float(parent_downforce) + float(downforce_noise_threshold)
    )
    drift_ok = bool(candidate.mask_drift_max <= MASK_DRIFT_TOLERANCE)
    box_ok = bool(candidate.move_box_violation_max <= BOX_TOLERANCE)
    primal_ok = bool(candidate.trial_primal_converged)
    candidate.gate_detail = {
        "corrected_update_above_machine_scale": update_ok,
        "projected_volume_within_v_max": vmax_ok,
        "extractability_guard": extractability_ok,
        "d_adj_negative": adj_ok,
        "d_fd_below_negative_noise_floor": fd_ok,
        "sign_match": sign_ok,
        "canonical_objective_improved": objective_ok,
        "raw_downforce_improved": downforce_ok,
        "mask_invariance": drift_ok,
        "move_box_respected": box_ok,
        "trial_primal_converged": primal_ok,
    }
    candidate.accepted = bool(all(candidate.gate_detail.values()) and candidate.bracket_ok)
    candidate.reason = "accepted" if candidate.accepted else "gates_failed"
    return candidate, proposal


def evaluate_phase2_inequality(
    *,
    transform,
    parent_result: Any,
    rho_parent: np.ndarray,
    parent_downforce: float,
    move_limit: float,
    ladder: tuple[float, ...],
    v_max: float,
    objective_noise_threshold: float,
    downforce_noise_threshold: float,
    bracket_spec: BracketSpec,
    evaluate_values: Callable[[np.ndarray], Any],
    evaluate_trial: Callable[[np.ndarray], tuple[Any, dict]],
    return_rho: bool = False,
    freeze_box_faces: bool = True,
    min_update_inf_norm: float = MIN_CORRECTED_UPDATE_INF_NORM,
    extractability_fraction: float = EXTRACTABILITY_FRACTION,
) -> dict | tuple[dict, np.ndarray | None]:
    """Evaluate the registered ladder under the inequality policy, fail-closed."""
    candidates: list[InequalityCandidate] = []
    accepted_rho = None
    for alpha in ladder:
        candidate, proposal = evaluate_inequality_candidate(
            transform=transform,
            parent_result=parent_result,
            rho_parent=rho_parent,
            parent_downforce=parent_downforce,
            alpha=alpha,
            move_limit=move_limit,
            v_max=v_max,
            objective_noise_threshold=objective_noise_threshold,
            downforce_noise_threshold=downforce_noise_threshold,
            bracket_spec=bracket_spec,
            evaluate_values=evaluate_values,
            evaluate_trial=evaluate_trial,
            freeze_box_faces=freeze_box_faces,
            min_update_inf_norm=min_update_inf_norm,
            extractability_fraction=extractability_fraction,
        )
        candidates.append(candidate)
        print(
            "  [inequality] alpha=%s accepted=%s reason=%s phi=%s imp_J=%s"
            " gates=%s"
            % (
                candidate.alpha,
                candidate.accepted,
                candidate.reason,
                candidate.phi_after,
                (
                    None
                    if candidate.trial_objective is None
                    else float(parent_result.objective) - candidate.trial_objective
                ),
                {key: value for key, value in candidate.gate_detail.items()},
            ),
            flush=True,
        )
        if candidate.accepted:
            accepted_rho = proposal.copy()
            break
    payload: dict[str, Any] = {
        "policy_id": POLICY_ID,
        "ladder": [float(alpha) for alpha in ladder],
        "candidates": [entry.to_jsonable() for entry in candidates],
    }
    if accepted_rho is not None:
        payload.update(
            {
                "accepted_alpha": float(candidates[-1].alpha),
                "all_failed": False,
                "successful": True,
                "corrected_rho_sha256": _array_sha256(accepted_rho),
            }
        )
    else:
        payload.update(
            {
                "accepted_alpha": None,
                "all_failed": True,
                "successful": False,
                "corrected_rho_sha256": None,
                "error": "no inequality-policy alpha satisfied the registered gates; "
                "fail-closed",
            }
        )
    return (payload, accepted_rho) if return_rho else payload


__all__ = [
    "EXTRACTABILITY_FRACTION",
    "MIN_CORRECTED_UPDATE_INF_NORM",
    "OCCUPANCY_THRESHOLDS",
    "POLICY_ID",
    "InequalityCandidate",
    "evaluate_inequality_candidate",
    "evaluate_phase2_inequality",
    "occupancy_metrics",
]
