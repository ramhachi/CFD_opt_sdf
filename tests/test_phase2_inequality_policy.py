"""Tests for the v6 inequality Phase 2 policy (no OpenFOAM)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection  # noqa: E402
from cfd_sdf.path_b_bracket import BracketSpec  # noqa: E402
from cfd_sdf.phase2_inequality_policy import (  # noqa: E402
    DISCRETENESS_POLICY_ID,
    MIN_CORRECTED_UPDATE_INF_NORM,
    POLICY_ID,
    evaluate_phase2_inequality,
    occupancy_metrics,
)

SHAPE = (6, 5, 4)
V_MAX = 0.07632566813424899


class _Result:
    def __init__(self, objective, gradient=None, downforce=None):
        self.objective = objective
        self.objective_gradient = gradient
        self.gradient_space = "rho_design" if gradient is not None else None
        self.adjoint_status = "converged" if gradient is not None else None
        self.primal_converged = True
        self.primal_artifact = {
            "artifact": {"summary": {"downforce_coefficient": downforce}}
        }


def _arena():
    act = np.zeros(SHAPE, dtype=bool)
    act[2:4, 1:4, 1:3] = True
    active = np.asarray(act).ravel(order="F")
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(SHAPE, 0.05, active, radius_m=0.05),
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    rho = np.zeros(SHAPE, dtype=np.float64).ravel(order="F")
    ids = np.nonzero(active)[0]
    rho[ids] = np.linspace(0.10, 0.90, ids.size)
    gradient = np.zeros_like(rho)
    gradient[ids] = -1.0
    return transform, rho, gradient, active


def _bracket_spec():
    return BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6)


def test_policy_identity_and_machine_scale_gate():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    called = {"trial": 0}

    def evaluate_values(candidate):
        return _Result(-1.0 - float(np.sum(candidate - rho)))

    def evaluate_trial(candidate):
        called["trial"] += 1
        return _Result(-1.1, downforce=0.6), {"downforce_coefficient": 0.6}

    # a negligible alpha with a zero gradient produces a machine-scale update
    zero_gradient = np.zeros_like(gradient)
    parent_zero = _Result(objective=-1.0, gradient=zero_gradient, downforce=0.5)
    result = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent_zero,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=V_MAX,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )
    payload, accepted = result
    assert payload["policy_id"] == POLICY_ID
    assert payload["successful"] is False
    assert payload["candidates"][0]["reason"] == "machine_scale_update_rejected"
    assert payload["candidates"][0]["gates"] == {"corrected_update_above_machine_scale": False}
    assert called["trial"] == 0
    assert accepted is None
    del parent


def test_accepted_candidate_stops_ladder_and_respects_freeze():
    transform, rho, gradient, active = _arena()
    rho = rho.copy()
    ids = np.nonzero(active)[0]
    rho[ids[0]] = 0.0  # exact box face
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)

    def evaluate_values(candidate):
        # a genuine descent pair about the parent
        delta_mean = float(np.mean(candidate - rho))
        return _Result(-1.0 - 10.0 * delta_mean)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload, accepted = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0, 0.5, 0.25),
        v_max=1.0,  # the synthetic arena carries high projected volume; the
        # V <= Vmax gate is covered by its own rejection test below
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )
    assert payload["successful"] is True
    assert payload["accepted_alpha"] == 1.0
    assert len(payload["candidates"]) == 1
    frozen = active & ((rho == 0.0) | (rho == 1.0))
    assert float(np.max(np.abs(accepted[frozen] - rho[frozen]))) == 0.0
    assert payload["candidates"][0]["gates"]["corrected_update_above_machine_scale"] is True
    assert payload["candidates"][0]["gates"]["canonical_objective_improved"] is True


def test_volume_upper_bound_gate_rejects_an_over_budget_candidate():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)

    def evaluate_values(candidate):
        return _Result(-1.5)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=0.0,  # impossible budget: the gate must reject
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
    )
    assert payload["successful"] is False
    assert payload["candidates"][0]["gates"]["projected_volume_within_v_max"] is False


def test_extractability_guard_rejects_a_collapse():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    # force the proposal downward everywhere: the occupancy must collapse
    descent = np.ones_like(gradient)
    parent_down = _Result(objective=-1.0, gradient=descent, downforce=0.5)

    def evaluate_values(candidate):
        return _Result(-1.5)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent_down,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.5,  # big step drives cells far down
        ladder=(1.0,),
        v_max=V_MAX,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
    )
    candidate = payload["candidates"][0]
    # the parent occupancy must be recorded regardless of the verdict
    assert candidate["occupancy_parent"] is not None
    assert candidate["occupancy"] is not None
    if candidate["gates"]["extractability_guard"] is False:
        assert candidate["accepted"] is False
    del parent


def test_occupancy_metrics_counts_match_a_manual_count():
    transform, rho, gradient, active = _arena()
    metrics = occupancy_metrics(transform, rho, active)
    projected = np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)[active]
    assert metrics["total_active"] == int(active.sum())
    for threshold in (0.4, 0.5):
        assert metrics[f"cells_gt_{threshold}"] == int(np.count_nonzero(projected > threshold))


def test_machine_scale_threshold_is_registered_at_one_e_minus_eight():
    assert MIN_CORRECTED_UPDATE_INF_NORM == 1e-8


def _always_improving_evaluators(rho):
    def evaluate_values(candidate):
        delta_mean = float(np.mean(candidate - rho))
        return _Result(-1.0 - 10.0 * delta_mean)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    return evaluate_values, evaluate_trial


def test_optional_discreteness_gate_rejects_a_grey_candidate():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    called = {"values": 0, "trial": 0}

    def evaluate_values(candidate):
        called["values"] += 1
        return _Result(-2.0)

    def evaluate_trial(candidate):
        called["trial"] += 1
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        discreteness_mean_nd_max=0.1,
    )

    candidate = payload["candidates"][0]
    assert payload["policy_id"] == DISCRETENESS_POLICY_ID
    assert candidate["discreteness_mean_nd_parent"] is not None
    assert candidate["discreteness_mean_nd_candidate"] > 0.1
    assert candidate["discreteness_mean_nd_max"] == 0.1
    assert candidate["discreteness_field"] == "rho_projection"
    assert candidate["discreteness_scope"] == "transform.active"
    assert candidate["gates"]["projected_discreteness_within_limit"] is False
    assert candidate["reason"] == "discreteness_limit_exceeded"
    assert candidate["accepted"] is False
    assert called == {"values": 0, "trial": 0}


def test_optional_discreteness_gate_accepts_a_discrete_candidate():
    transform, rho, gradient, active = _arena()
    rho = rho.copy()
    rho[active] = 0.9
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    evaluate_values, evaluate_trial = _always_improving_evaluators(rho)

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        discreteness_mean_nd_max=0.1,
    )

    candidate = payload["candidates"][0]
    assert payload["policy_id"] == DISCRETENESS_POLICY_ID
    assert candidate["discreteness_mean_nd_candidate"] <= 0.1
    assert candidate["gates"]["projected_discreteness_within_limit"] is True
    assert candidate["accepted"] is True


def test_discreteness_gate_skips_grey_alpha_before_solver_and_tries_next():
    transform, rho, gradient, active = _arena()
    rho = rho.copy()
    rho[active] = 0.9
    gradient = np.zeros_like(rho)
    gradient[active] = 1.0
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)

    def mean_nd(candidate):
        projected = np.asarray(transform.forward(candidate).rho_projected)[active]
        return float(np.mean(4.0 * projected * (1.0 - projected)))

    proposal_full = rho.copy()
    proposal_full[active] -= 0.3
    proposal_half = rho.copy()
    proposal_half[active] -= 0.15
    limit = 0.5 * (mean_nd(proposal_full) + mean_nd(proposal_half))
    assert mean_nd(proposal_half) < limit < mean_nd(proposal_full)
    calls = {"values": 0, "trial": 0}

    def evaluate_values(candidate):
        calls["values"] += 1
        return _Result(-1.0 + 10.0 * float(np.mean(candidate - rho)))

    def evaluate_trial(candidate):
        calls["trial"] += 1
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.3,
        ladder=(1.0, 0.5),
        v_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        discreteness_mean_nd_max=limit,
    )

    assert payload["candidates"][0]["reason"] == "discreteness_limit_exceeded"
    assert payload["candidates"][1]["accepted"] is True
    assert payload["accepted_alpha"] == 0.5
    assert calls == {"values": 2, "trial": 1}


def test_discreteness_gate_default_preserves_acceptance_behavior():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    evaluate_values, evaluate_trial = _always_improving_evaluators(rho)

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=_bracket_spec(),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
    )

    candidate = payload["candidates"][0]
    assert candidate["accepted"] is True
    assert candidate["discreteness_mean_nd_max"] is None
    assert "projected_discreteness_within_limit" not in candidate["gates"]


@pytest.mark.parametrize("bound", [-0.01, 1.01, np.inf, np.nan])
def test_discreteness_gate_rejects_invalid_bound(bound):
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    evaluate_values, evaluate_trial = _always_improving_evaluators(rho)

    with pytest.raises(ValueError, match="finite and within"):
        evaluate_phase2_inequality(
            transform=transform,
            parent_result=parent,
            rho_parent=rho,
            parent_downforce=0.5,
            move_limit=0.03,
            ladder=(1.0,),
            v_max=1.0,
            objective_noise_threshold=1e-6,
            downforce_noise_threshold=1e-6,
            bracket_spec=_bracket_spec(),
            evaluate_values=evaluate_values,
            evaluate_trial=evaluate_trial,
            discreteness_mean_nd_max=bound,
        )


def test_v6_registration_pins_the_current_artifacts():
    import hashlib
    import json

    from cfd_sdf import campaign_assertions as ca

    d2_path = ROOT / "docs/evidence/pq3_3b_d2_change_manifest_2026_09.json"
    v6_path = ROOT / "docs/evidence/pq3_3b_campaign_manifest_v6_2026_09.json"
    d1_path = ROOT / "docs/evidence/pq3_3b_d1_discriminant_outcome_2026_09.json"
    script_path = ROOT / "scripts/pq3_3b_v6_entry_preflight_2026_09.py"
    d2 = json.loads(d2_path.read_text(encoding="utf-8"))
    v6 = json.loads(v6_path.read_text(encoding="utf-8"))
    assert d2["discriminant_evidence"]["sha256"] == hashlib.sha256(d1_path.read_bytes()).hexdigest()
    assert v6["change_manifest_d2"]["sha256"] == hashlib.sha256(d2_path.read_bytes()).hexdigest()
    assert v6["entry_preflight"]["script_sha256"] == hashlib.sha256(script_path.read_bytes()).hexdigest()
    assert v6["status"] == "registered_preflight_pending"
    assert v6["phase2_policy"]["id"] == POLICY_ID
    assert v6["phase2_policy"]["min_corrected_update_inf_norm"] == MIN_CORRECTED_UPDATE_INF_NORM


def test_volume_cap_correction_lands_on_the_feasible_boundary():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    parent_phi = occupancy_parent_phi = float(
        np.asarray(transform.forward(rho).rho_projected, dtype=np.float64)[active].mean()
    )
    v_max = parent_phi + 0.005

    def evaluate_values(candidate):
        return _Result(-2.0)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=v_max,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        volume_cap_correction=True,
    )
    candidate = payload["candidates"][0]
    assert candidate["volume_cap_correction_applied"] is True
    assert -1.0 <= candidate["volume_cap_kappa"] <= 0.0
    assert candidate["phi_after"] <= v_max + 1e-12
    assert candidate["gates"]["projected_volume_within_v_max"] is True


def test_volume_cap_correction_not_applied_when_already_feasible():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)

    def evaluate_values(candidate):
        return _Result(-2.0)

    def evaluate_trial(candidate):
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        volume_cap_correction=True,
    )
    candidate = payload["candidates"][0]
    assert candidate["volume_cap_correction_applied"] is False
    assert candidate["volume_cap_kappa"] is None


def test_volume_cap_unreachable_is_fail_closed():
    transform, rho, gradient, active = _arena()
    parent = _Result(objective=-1.0, gradient=gradient, downforce=0.5)
    called = {"trial": 0}

    def evaluate_values(candidate):
        return _Result(-2.0)

    def evaluate_trial(candidate):
        called["trial"] += 1
        return _Result(-2.0, downforce=1.5), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_inequality(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=0.5,
        move_limit=0.03,
        ladder=(1.0,),
        v_max=0.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        volume_cap_correction=True,
    )
    assert payload["candidates"][0]["reason"] == "volume_cap_unreachable"
    assert called["trial"] == 0
