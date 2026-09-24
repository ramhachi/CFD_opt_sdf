"""Pure tests for the bounded v13 discreteness direction."""

from __future__ import annotations

import numpy as np

from cfd_sdf.design_transform import (
    ConeFilter,
    DesignTransform,
    RampInterpolation,
    TanhProjection,
)
from cfd_sdf.path_b_bracket import BracketSpec
from cfd_sdf.phase2_discreteness_direction import (
    backtrack_transform_candidates,
    evaluate_phase2_discreteness_direction,
    projected_raw_gradient_direction,
    transform_candidate,
    _campaign_record,
)


SHAPE = (6, 5, 4)


class _Result:
    def __init__(self, objective, gradient=None):
        self.objective = float(objective)
        self.objective_gradient = gradient
        self.gradient_space = "rho_design" if gradient is not None else None
        self.adjoint_status = "converged" if gradient is not None else None
        self.primal_converged = True


def _arena():
    mask = np.zeros(SHAPE, dtype=bool)
    mask[1:5, 1:4, 1:3] = True
    active = mask.ravel(order="F")
    transform = DesignTransform(
        shape=SHAPE,
        spacing_m=0.05,
        active_mask=active,
        filter=ConeFilter(SHAPE, 0.05, active, radius_m=0.05),
        projection=TanhProjection(16.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    rho = np.zeros(np.prod(SHAPE), dtype=np.float64)
    ids = np.flatnonzero(active)
    rho[ids] = np.where(np.arange(ids.size) % 2 == 0, 0.42, 0.58)
    rho[ids[0]] = 0.0
    rho[ids[1]] = 1.0
    gradient = np.zeros_like(rho)
    gradient[ids] = np.linspace(-3.0, 2.0, ids.size)
    return transform, rho, gradient, active


def test_raw_gradient_direction_is_a_descent_and_discreteness_tangent():
    transform, rho, gradient, active = _arena()
    result = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )

    assert result.diagnostics["projection_applied"] is True
    assert result.diagnostics["g_objective_dot_direction"] < 0.0
    assert abs(result.diagnostics["g_discreteness_dot_direction"]) < 1e-12
    assert result.diagnostics["direction_inf_norm"] == 1.0
    assert np.all(result.values[~active] == 0.0)
    assert result.values[np.flatnonzero(active)[0]] == 0.0
    assert result.values[np.flatnonzero(active)[1]] == 0.0


def test_transform_candidate_preserves_masks_box_and_records_physical_metrics():
    transform, rho, gradient, active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    candidate = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=0.25,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )

    assert candidate.feasible is True
    assert candidate.metrics["mask_drift_max"] == 0.0
    assert candidate.metrics["move_box_violation_max"] == 0.0
    assert candidate.metrics["corrected_update_inf_norm"] <= 0.0025 + 1e-15
    assert np.all(candidate.rho[~active] == rho[~active])
    assert 0.0 <= candidate.metrics["discreteness_mean_nd_candidate"] <= 1.0


def test_backtracking_stops_at_first_transform_feasible_candidate():
    transform, rho, gradient, _active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    full = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    half = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=0.5,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    assert full.metrics["discreteness_mean_nd_candidate"] > half.metrics[
        "discreteness_mean_nd_candidate"
    ]
    bound = 0.5 * (
        full.metrics["discreteness_mean_nd_candidate"]
        + half.metrics["discreteness_mean_nd_candidate"]
    )

    ledger, selected = backtrack_transform_candidates(
        transform=transform,
        rho=rho,
        direction=direction.values,
        ladder=(1.0, 0.5, 0.25),
        move_limit=0.01,
        discreteness_mean_nd_max=bound,
        v_max=1.0,
    )

    assert [entry.alpha for entry in ledger] == [1.0, 0.5]
    assert ledger[0].feasible is False
    assert ledger[0].gates["projected_discreteness_within_limit"] is False
    assert selected is ledger[1]
    assert selected.feasible is True


def test_invalid_or_zero_projected_direction_fails_closed():
    transform, rho, _gradient, _active = _arena()
    with np.testing.assert_raises(ValueError):
        projected_raw_gradient_direction(
            transform=transform,
            rho=rho,
            objective_gradient=np.zeros_like(rho),
        )


def test_full_evaluator_applies_response_gates_only_to_transform_candidate():
    transform, rho, gradient, _active = _arena()
    parent = _Result(-1.0, gradient)
    calls = {"values": 0, "trial": 0}

    def evaluate_values(candidate):
        calls["values"] += 1
        return _Result(-1.0 + float(np.dot(gradient, candidate - rho)))

    def evaluate_trial(_candidate):
        calls["trial"] += 1
        return _Result(-2.0), {"downforce_coefficient": 2.0}

    payload, accepted = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0, 0.5),
        v_max=1.0,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )

    assert payload["successful"] is True
    assert payload["accepted_alpha"] == 1.0
    assert payload["candidates"][0]["accepted"] is True
    assert payload["candidates"][0]["bracket_ok"] is True
    assert payload["candidates"][0]["gates"]["canonical_objective_improved"] is True
    assert payload["evaluator_calls"]["path_b_evaluator_requests"] == 2
    assert payload["evaluator_calls"]["trial_evaluator_requests"] == 1
    assert payload["evaluator_calls"]["path_b_proven_fresh_solver_runs"] == 0
    assert payload["evaluator_calls"]["trial_proven_fresh_solver_runs"] == 0
    assert payload["evaluator_calls"]["path_b_freshness_unknown"] == 2
    assert payload["evaluator_calls"]["trial_freshness_unknown"] == 1
    assert len(payload["evaluator_calls"]["path_b_requests"]) == 2
    assert accepted is not None
    assert calls == {"values": 2, "trial": 1}


def test_full_evaluator_backtracks_with_no_solver_calls_for_rejected_alpha():
    transform, rho, gradient, _active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    full = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    half = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=0.5,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
    )
    bound = 0.5 * (
        full.metrics["discreteness_mean_nd_candidate"]
        + half.metrics["discreteness_mean_nd_candidate"]
    )
    calls = {"values": 0, "trial": 0}

    def evaluate_values(candidate):
        calls["values"] += 1
        return _Result(-1.0 + float(np.dot(gradient, candidate - rho)))

    def evaluate_trial(_candidate):
        calls["trial"] += 1
        return _Result(-2.0), {"downforce_coefficient": 2.0}

    payload = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=_Result(-1.0, gradient),
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0, 0.5),
        v_max=1.0,
        discreteness_mean_nd_max=bound,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
    )

    assert [record["alpha"] for record in payload["candidates"]] == [1.0, 0.5]
    assert payload["candidates"][0]["reason"] == "discreteness_limit_exceeded"
    assert payload["candidates"][0]["failed_transform_gates"] == [
        "projected_discreteness_within_limit"
    ]
    assert payload["candidates"][0]["trial_run"] is None
    assert payload["candidates"][1]["accepted"] is True
    assert calls == {"values": 2, "trial": 1}


def test_full_evaluator_skips_trial_when_path_b_fails():
    transform, rho, gradient, _active = _arena()
    calls = {"values": 0, "trial": 0}

    def flat_values(_candidate):
        calls["values"] += 1
        return _Result(-1.0)

    def evaluate_trial(_candidate):
        calls["trial"] += 1
        return _Result(-2.0), {"downforce_coefficient": 2.0}

    payload = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=_Result(-1.0, gradient),
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0,),
        v_max=1.0,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=flat_values,
        evaluate_trial=evaluate_trial,
    )

    assert payload["successful"] is False
    assert payload["candidates"][0]["reason"] == "path_b_failed"
    assert calls == {"values": 2, "trial": 0}


def test_response_ladder_continues_to_a_smaller_alpha_after_a_response_failure():
    transform, rho, gradient, _active = _arena()
    parent = _Result(-1.0, gradient)
    trials = {"count": 0}

    def evaluate_values(candidate):
        # a consistently descending bracket about the parent
        return _Result(-1.0 + float(np.dot(gradient, candidate - rho)))

    def evaluate_trial(_candidate):
        trials["count"] += 1
        if trials["count"] == 1:
            # the boldest step overshoots: worse in canonical and raw response
            return _Result(-0.9), {"downforce_coefficient": 0.9}
        return _Result(-2.0), {"downforce_coefficient": 1.5}

    payload, accepted = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0, 0.5),
        v_max=1.0,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )

    assert payload["successful"] is True
    assert payload["accepted_alpha"] == 0.5
    assert payload["candidates"][0]["reason"] == "response_gates_failed"
    assert payload["candidates"][0]["accepted"] is False
    assert payload["candidates"][1]["accepted"] is True
    assert trials["count"] == 2
    assert payload["evaluator_calls"]["trial_evaluator_requests"] == 2
    assert accepted is not None


def test_support_clearance_gate_is_transform_level_and_fail_closed():
    transform, rho, gradient, active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    allowed_all = np.ones_like(active, dtype=bool)
    candidate_ok = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
        support_allowed_cells=allowed_all,
    )
    assert candidate_ok.gates["support_clearance"] is True
    assert candidate_ok.metrics["support_violations"] == 0

    allowed_none = np.zeros_like(active, dtype=bool)
    candidate_bad = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
        support_allowed_cells=allowed_none,
    )
    projected = np.asarray(transform.forward(candidate_bad.rho).rho_projected, dtype=np.float64)
    expected = int(np.count_nonzero(projected > 0.5))
    assert expected > 0
    assert candidate_bad.metrics["support_violations"] == expected
    assert candidate_bad.gates["support_clearance"] is False
    assert candidate_bad.feasible is False


def test_two_tried_alphas_record_per_candidate_requests_and_cumulative_totals():
    transform, rho, gradient, _active = _arena()
    parent = _Result(-1.0, gradient)
    trials = {"count": 0}

    def evaluate_values(candidate):
        return _Result(-1.0 + float(np.dot(gradient, candidate - rho)))

    def evaluate_trial(_candidate):
        trials["count"] += 1
        if trials["count"] == 1:
            return _Result(-0.9), {"downforce_coefficient": 0.9}
        return _Result(-2.0), {"downforce_coefficient": 1.5}

    payload, _accepted = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0, 0.5),
        v_max=1.0,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )

    for record in payload["candidates"]:
        assert record["evaluator_calls"]["path_b_evaluator_requests"] == 2
        assert record["evaluator_calls"]["trial_evaluator_requests"] == 1
        assert len(record["evaluator_calls"]["path_b_requests"]) == 2
        assert [r["request_index"] for r in record["evaluator_calls"]["path_b_requests"]] == [1, 2]
        # per-candidate evidence lists must be independent objects
        assert (
            record["evaluator_calls"]["path_b_requests"]
            is not payload["evaluator_calls"]["path_b_requests"]
        )
        assert (
            payload["candidates"][0]["evaluator_calls"]["path_b_requests"]
            is not payload["candidates"][1]["evaluator_calls"]["path_b_requests"]
        )
    cumulative = payload["evaluator_calls"]
    assert cumulative["path_b_evaluator_requests"] == 4
    assert cumulative["trial_evaluator_requests"] == 2
    assert len(cumulative["path_b_requests"]) == 4
    assert [r["request_index"] for r in cumulative["path_b_requests"]] == [1, 2, 3, 4]


def test_path_b_failure_stops_the_response_ladder_fail_closed():
    transform, rho, gradient, _active = _arena()
    parent = _Result(-1.0, gradient)
    calls = {"values": 0, "trial": 0}

    def flat_values(_candidate):
        calls["values"] += 1
        return _Result(-1.0)

    def evaluate_trial(_candidate):
        calls["trial"] += 1
        return _Result(-2.0), {"downforce_coefficient": 2.0}

    payload = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=0.01,
        ladder=(1.0, 0.5),
        v_max=1.0,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=flat_values,
        evaluate_trial=evaluate_trial,
    )

    records = payload["candidates"]
    assert payload["successful"] is False
    assert records[0]["reason"] == "path_b_failed"
    assert records[0]["bracket_ok"] is False
    assert records[0]["evaluator_calls"]["path_b_evaluator_requests"] == 2
    assert records[0]["evaluator_calls"]["trial_evaluator_requests"] == 0
    # backtracking must not continue past a Path B failure
    assert records[1]["bracket"] is None
    assert records[1].get("evaluator_calls") is None
    assert calls == {"values": 2, "trial": 0}
    assert payload["evaluator_calls"]["path_b_evaluator_requests"] == 2
    assert payload["evaluator_calls"]["trial_evaluator_requests"] == 0


def test_transform_infeasible_alphas_consume_no_solver_calls():
    transform, rho, gradient, _active = _arena()
    parent = _Result(-1.0, gradient)
    values_calls = {"count": 0}
    trial_calls = {"count": 0}

    def evaluate_values(candidate):
        values_calls["count"] += 1
        return _Result(-2.0)

    def evaluate_trial(_candidate):
        trial_calls["count"] += 1
        return _Result(-2.0), {"downforce_coefficient": 1.5}

    payload = evaluate_phase2_discreteness_direction(
        transform=transform,
        parent_result=parent,
        rho_parent=rho,
        parent_downforce=1.0,
        move_limit=1e6,
        ladder=(1.0, 0.5),
        v_max=0.01,
        discreteness_mean_nd_max=1.0,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )
    payload, accepted = payload

    assert payload["successful"] is False
    assert values_calls["count"] == 0
    assert trial_calls is not None
    assert trial_calls["count"] == 0
    assert accepted is None
    for record in payload["candidates"]:
        assert record["bracket_ok"] is False
        assert record["reason"] == "projected_volume_limit_exceeded"
        assert record.get("evaluator_calls") is None
        assert record["trial_run"] is None
        assert record["bracket"] is None


def test_support_clearance_failure_reason_is_recorded():
    transform, rho, gradient, _active = _arena()
    direction = projected_raw_gradient_direction(
        transform=transform,
        rho=rho,
        objective_gradient=gradient,
    )
    allowed_none = np.zeros_like(rho, dtype=bool)
    candidate = transform_candidate(
        transform=transform,
        rho=rho,
        direction=direction.values,
        alpha=1.0,
        move_limit=0.01,
        discreteness_mean_nd_max=1.0,
        v_max=1.0,
        support_allowed_cells=allowed_none,
    )
    record = _campaign_record(candidate)
    assert "support_clearance_violated" in record["reason"]
    assert record["failed_transform_gates"] == ["support_clearance"]
