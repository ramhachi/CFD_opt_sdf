"""Phase 2 alpha-ladder policy for the PQ3.3b campaign (preflight v4).

Registered ladder (manifest v3): ``alpha_objective = (1.0, 0.5, 0.25, 0.125,
0.0625)``. The ladder is registered in evidence order and is never changed
after a result is observed; a change requires a new manifest.

Per alpha, in this order:
1. the canonical objective proposal is built from ``parent_result`` -- an
   ``OracleResult`` produced through the registered canonical path
   (``ProblemSpec -> compile_problem -> make_oracle_from_compiled ->
   evaluate_parent``), whose ``objective_gradient`` is the signed pullback of
   the response sensitivity into rho_design space. A raw ``numpy.ndarray`` is
   rejected here.
   proposal: ``rho - alpha * move_limit * sign(dJ/drho)``;
2. the proposal is clipped into the parent's move box;
3. a uniform offset scalar is bisected so that ``V_projection == V_target``
   (residual <= volume tolerance), through the real ``DesignTransform.forward``;
4. mask invariance and the move box are re-verified;
5. a Path B centered FD bracket is evaluated in canonical space;
6. the corrected candidate is evaluated by one real trial primal measuring the
   canonical objective ``J_trial`` and the raw ``downforce_trial``.

Candidate gates (all must hold for the FIRST accepting alpha; the ladder stops
at the first accepted candidate): volume residual <= tolerance, V <= V_max,
d_adj < 0, d_fd < -fd noise floor, sign match, J_trial < J_parent - objective
noise threshold, downforce_trial > downforce_parent + downforce noise
threshold, mask drift 0, move-box violation 0, trial primal converged.
If no alpha passes, the outcome is fail-closed and the campaign is not
startable under this manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np

from cfd_sdf.canonical_objective import canonical_objective_from
from cfd_sdf.path_b_bracket import BracketSpec, evaluate_path_b_bracket
from cfd_sdf.projected_restoration import _restore

ALPHA_LADDER = (1.0, 0.5, 0.25, 0.125, 0.0625)
MASK_DRIFT_TOLERANCE = 1e-12
BOX_TOLERANCE = 1e-12
BISECTION_STEPS = 60


@dataclass
class Phase2Candidate:
    """One alpha's measured candidate; every gate is an explicit verdict."""

    alpha: float
    accepted: bool = False
    reason: str = "not_evaluated"
    kappa_volume: float | None = None
    phi_after: float | None = None
    volume_residual: float | None = None
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
        _ = self.gate_detail
        detail = {key: bool(value) for key, value in self.gate_detail.items()}
        payload["gates"] = detail
        return payload


def evaluate_phase2_candidate(
    *,
    transform,
    parent_result: Any,
    rho_parent: np.ndarray,
    parent_downforce: float,
    alpha: float,
    move_limit: float,
    target: float,
    v_max: float,
    volume_tolerance: float,
    objective_noise_threshold: float,
    downforce_noise_threshold: float,
    bracket_spec: BracketSpec,
    evaluate_values: Callable[[np.ndarray], Any],
    evaluate_trial: Callable[[np.ndarray], tuple[Any, dict]],
) -> tuple[Phase2Candidate, np.ndarray]:
    """Steps 1-6 for a single alpha; returns the candidate and its rho_prime."""
    parent_objective, gradient = canonical_objective_from(parent_result)
    candidate = Phase2Candidate(alpha=float(alpha))
    values = np.asarray(rho_parent, dtype=np.float64)
    move_limit = float(move_limit)
    box_low = np.clip(values - move_limit, 0.0, 1.0)
    box_high = np.clip(values + move_limit, 0.0, 1.0)
    active = np.asarray(transform.active, dtype=bool)

    # 1-2: canonical-objective proposal clipped inside the parent's move box
    proposal = np.clip(
        values - alpha * move_limit * np.sign(gradient), box_low, box_high
    )

    # 3: uniform offset bisected onto the projected-volume target
    def phi_at(kappa_volume: float) -> float:
        stepped = np.clip(proposal + kappa_volume * move_limit, box_low, box_high)
        stepped = _restore(stepped, values, active)
        state = transform.forward(stepped)
        projected = np.asarray(state.rho_projected, dtype=np.float64)
        return float(projected[active].mean())

    phi_low = phi_at(-1.0)
    phi_high = phi_at(1.0)
    if phi_low > target + volume_tolerance or phi_high < target - volume_tolerance:
        candidate.reason = "volume_correction_out_of_range"
        candidate.gate_detail = {"volume_correction_bracketed": False}
        return candidate, values
    low_k, high_k, kappa_volume = -1.0, 1.0, None
    for _ in range(BISECTION_STEPS):
        mid = 0.5 * (low_k + high_k)
        phi_mid = phi_at(mid)
        if phi_mid < target:
            low_k = mid
        else:
            high_k = mid
            kappa_volume = mid
    phi_final = phi_at(float(kappa_volume))
    corrected = np.clip(
        proposal + float(kappa_volume) * move_limit, box_low, box_high
    )
    corrected = _restore(corrected, values, active)
    candidate.kappa_volume = float(kappa_volume)
    candidate.phi_after = float(phi_final)
    candidate.volume_residual = abs(float(phi_final) - float(target))
    drift = 0.0
    inactive = ~active
    if inactive.any():
        drift = float(np.max(np.abs(corrected[inactive] - values[inactive])))
    candidate.mask_drift_max = drift
    violation = np.maximum(corrected - box_high, box_low - corrected)
    candidate.move_box_violation_max = float(max(0.0, np.max(violation)))

    # 5: Path B centered bracket along the corrected proposal (canonical space)
    outcome = evaluate_path_b_bracket(
        spec=bracket_spec,
        parent_rho=values,
        parent_gradient=gradient,
        proposal_delta=corrected - values,
        active=active,
        evaluate_values=evaluate_values,
    )
    candidate.bracket = outcome.to_dict()
    candidate.bracket_ok = bool(outcome.ok)

    # 6: real trial primal on the corrected candidate
    trial_result, trial_run = evaluate_trial(corrected)
    candidate.trial_objective = float(trial_result.objective)
    candidate.trial_primal_converged = bool(trial_result.primal_converged)
    candidate.trial_run = trial_run
    trial_downforce_value = extract_downforce_from_run(trial_run)
    candidate.trial_downforce = trial_downforce_value

    volume_ok = bool(candidate.volume_residual <= volume_tolerance)
    vmax_ok = bool(candidate.phi_after <= v_max)
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
        "volume_residual_within_tolerance": volume_ok,
        "projected_volume_within_v_max": vmax_ok,
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
    return candidate, corrected


def evaluate_phase2(
    *,
    transform,
    parent_result: Any,
    rho_parent: np.ndarray,
    parent_downforce: float,
    move_limit: float,
    ladder: tuple[float, ...],
    target: float,
    v_max: float,
    volume_tolerance: float,
    objective_noise_threshold: float,
    downforce_noise_threshold: float,
    bracket_spec: BracketSpec,
    evaluate_values: Callable[[np.ndarray], Any],
    evaluate_trial: Callable[[np.ndarray], tuple[Any, dict]],
) -> dict:
    """Evaluate the registered ladder in registered order, fail-closed."""
    candidates: list[Phase2Candidate] = []
    corrected_rho = np.asarray(rho_parent, dtype=np.float64)
    for alpha in ladder:
        candidate, corrected_rho = evaluate_phase2_candidate(
            transform=transform,
            parent_result=parent_result,
            rho_parent=rho_parent,
            parent_downforce=parent_downforce,
            alpha=alpha,
            move_limit=move_limit,
            target=target,
            v_max=v_max,
            volume_tolerance=volume_tolerance,
            objective_noise_threshold=objective_noise_threshold,
            downforce_noise_threshold=downforce_noise_threshold,
            bracket_spec=bracket_spec,
            evaluate_values=evaluate_values,
            evaluate_trial=evaluate_trial,
        )
        candidates.append(candidate)
        print(
            "  alpha=%s accepted=%s residual=%s reason=%s trial_obj=%s trial_df=%s"
            " gates=%s"
            % (
                candidate.alpha,
                candidate.accepted,
                candidate.volume_residual,
                candidate.reason,
                candidate.trial_objective,
                candidate.trial_downforce,
                {key: value for key, value in candidate.gate_detail.items()},
            ),
            flush=True,
        )
        if candidate.accepted:
            break
    accepted = [entry for entry in candidates if entry.accepted]
    payload: dict[str, Any] = {
        "ladder": [float(a) for a in ladder],
        "candidates": [entry.to_jsonable() for entry in candidates],
    }
    if accepted:
        payload.update(
            {
                "accepted_alpha": float(accepted[0].alpha),
                "all_failed": False,
                "successful": True,
                "corrected_rho_sha256": None,
            }
        )
    else:
        payload.update(
            {
                "accepted_alpha": None,
                "all_failed": True,
                "successful": False,
            }
        )
        raise ValueError(
            "no Phase 2 alpha satisfied the registered candidate gates; "
            "fail-closed: the campaign is not startable under this manifest"
        )
    payload["corrected_rho_sha256"] = _array_sha256(corrected_rho)
    return payload


def _array_sha256(values: np.ndarray) -> str:
    values = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    import hashlib

    return hashlib.sha256(values.tobytes()).hexdigest()


def extract_downforce_from_run(run: dict) -> float | None:
    """Extract the raw downforce coefficient from a run-evidence record."""
    if not isinstance(run, dict):
        return None
    value = run.get("downforce_coefficient")
    if value is None:
        summary = run.get("summary")
        if isinstance(summary, dict):
            value = summary.get("downforce_coefficient")
    return None if value is None else float(value)


__all__ = [
    "ALPHA_LADDER",
    "Phase2Candidate",
    "evaluate_phase2",
    "evaluate_phase2_candidate",
    "extract_downforce_from_run",
]
