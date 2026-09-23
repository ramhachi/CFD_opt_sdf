"""Regression tests: Phase 2 alpha ladder, Path B contract, preflight pass gates."""

from __future__ import annotations

import hashlib
import sys

import numpy as np

sys.path.insert(0, "src")

from cfd_sdf.path_b_bracket import BracketSpec, evaluate_path_b_bracket  # noqa: E402
from cfd_sdf.phase2_policy import ALPHA_LADDER, evaluate_phase2, evaluate_phase2_candidate  # noqa: E402

TARGET = 0.018
V_MAX = 0.07632566813424899
PARENT_OBJECTIVE = -0.5
PARENT_DOWNFORCE = 0.5
NOISE = 1e-6


class _FakeTransform:
    """Slightly non-linear projection stand-in for the volume predicate."""

    def __init__(self, n: int = 8):
        self.active = np.zeros(n, dtype=bool)
        self.active[: n // 2] = True

    def forward(self, values):
        values = np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)
        state = np.clip(values * (1.0 + 0.25 * values), 0.0, 1.0)

        class _State:
            pass

        state_obj = _State()
        state_obj.rho_projected = state
        return state_obj


class _Result:
    """Registered OracleResult stand-in."""

    def __init__(self, objective, downforce=None, gradient=None):
        self.objective = objective
        self.objective_gradient = gradient
        self.gradient_space = "rho_design" if gradient is not None else None
        self.adjoint_status = "converged" if gradient is not None else None
        self.primal_converged = True
        self.primal_artifact = {
            "artifact": {"summary": {"downforce_coefficient": downforce}}
        }


def _bracket_spec():
    return BracketSpec(epsilon=1e-4, noise_floor_abs=NOISE)


def run_ladder(rho, parent_result, trial_objective, trial_downforce, value_of=None, ladder=ALPHA_LADDER, return_rho=True):
    def evaluate_values(rho_array):
        if np.mean(np.asarray(rho_array) - rho) > 0:
            return _Result(-0.600001)
        return _Result(PARENT_OBJECTIVE)

    def evaluate_trial(corrected):
        return _Result(trial_objective, downforce=trial_downforce), {
            "downforce_coefficient": trial_downforce
        }

    return evaluate_phase2(
        transform=_FakeTransform(),
        parent_result=parent_result,
        rho_parent=rho,
        parent_downforce=PARENT_DOWNFORCE,
        move_limit=0.05,
        ladder=ladder,
        target=TARGET,
        v_max=V_MAX,
        volume_tolerance=1e-4,
        objective_noise_threshold=NOISE,
        downforce_noise_threshold=NOISE,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=NOISE),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=return_rho,
    )


def _parent():
    return _Result(PARENT_OBJECTIVE, downforce=PARENT_DOWNFORCE, gradient=np.full(8, -1.0))


def test_alpha_backtracking_picks_a_smaller_feasible_step():
    # a mixed-sign canonical gradient keeps the composite descent direction
    # well-aligned, so the gate order is decided purely by the trial runs:
    # alpha=1.0's trial is worse in canonical space and raw downforce, and
    # the registered ladder must reach the alpha=0.5 candidate
    act = np.array([True, True, True, True, False, False, False, False])
    mean_target = 0.018
    rho = np.array((0.006, 0.014, 0.020, 0.030, 0.0, 0.0, 0.0, 0.0))
    grad = np.array((1.0, -1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0))
    w = -grad

    def j_of(r):
        return float(np.sum(-w * np.asarray(r, dtype=np.float64)))

    parent_objective = j_of(rho)
    parent_downforce = PARENT_DOWNFORCE

    class _FakeForward:
        def __init__(self, values):
            self.rho_projected = values

    class _ArenaTransform:
        def __init__(self):
            self.active = act

        def forward(self, values):
            return _FakeForward(values)

    state = {"trial_calls": 0, "trial_rhos": []}
    trials_by_order = [
        (parent_objective + 0.01, parent_downforce - 0.01),  # alpha=1.0 worse
        (parent_objective - 0.02, parent_downforce + 0.02),  # alpha=0.5 better
    ]

    def evaluate_values(rho_array):
        return _Result(j_of(rho_array))

    def evaluate_trial(corrected):
        state["trial_calls"] += 1
        state["trial_rhos"].append(corrected.copy())
        objective_value, downforce = trials_by_order[state["trial_calls"] - 1]
        return _Result(objective_value, downforce=downforce), {
            "downforce_coefficient": downforce
        }

    parent_result = _Result(
        parent_objective, downforce=parent_downforce, gradient=grad
    )
    result, accepted_rho = evaluate_phase2(
        transform=_ArenaTransform(),
        parent_result=parent_result,
        rho_parent=rho,
        parent_downforce=parent_downforce,
        move_limit=0.01,
        ladder=ALPHA_LADDER,
        target=mean_target,
        v_max=V_MAX,
        volume_tolerance=1e-4,
        objective_noise_threshold=NOISE,
        downforce_noise_threshold=NOISE,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=NOISE),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
        return_rho=True,
    )
    assert result["accepted_alpha"] == 0.5
    assert {candidate["alpha"] for candidate in result["candidates"]} == {1.0, 0.5}
    assert state["trial_calls"] == 2
    assert not np.array_equal(state["trial_rhos"][0], state["trial_rhos"][1])
    np.testing.assert_array_equal(accepted_rho, state["trial_rhos"][1])
    assert result["corrected_rho_sha256"] == hashlib.sha256(
        np.ascontiguousarray(accepted_rho).tobytes()
    ).hexdigest()
    assert result["candidates"][1]["corrected_rho_sha256"] == result["corrected_rho_sha256"]


def test_phase2_downforce_worsening_preserves_all_failed_candidates():
    rho = np.full(8, 0.018)
    parent = _Result(PARENT_OBJECTIVE, downforce=PARENT_DOWNFORCE, gradient=np.full(8, -1.0))
    result, accepted_rho = run_ladder(
        rho,
        parent,
        PARENT_OBJECTIVE + 0.01,  # worse canonical
        PARENT_DOWNFORCE - 0.01,  # worse downforce
    )
    assert result["all_failed"] is True
    assert result["successful"] is False
    assert result["accepted_alpha"] is None
    assert accepted_rho is None
    assert [entry["alpha"] for entry in result["candidates"]] == list(ALPHA_LADDER)
    assert all(not entry["accepted"] for entry in result["candidates"])
    assert all(entry["corrected_rho_sha256"] for entry in result["candidates"])
    assert "not startable" in result["error"]


def test_historical_dict_return_remains_available():
    rho = np.full(8, 0.018)
    parent = _Result(PARENT_OBJECTIVE, downforce=PARENT_DOWNFORCE, gradient=np.full(8, -1.0))
    result = run_ladder(rho, parent, PARENT_OBJECTIVE, PARENT_DOWNFORCE, return_rho=False)
    assert isinstance(result, dict)
    assert result["all_failed"] is True
    assert len(result["candidates"]) == len(ALPHA_LADDER)


def test_freezing_exact_box_faces_restores_centered_path_b_direction():
    rho = np.array([1.0, 0.5, 0.5, 0.5])
    gradient = np.array([0.0, -1.0, -1.0, 1.0])

    class IdentityTransform:
        active = np.ones(4, dtype=bool)

        def forward(self, values):
            return type("State", (), {"rho_projected": values})()

    def objective(values):
        return float(np.dot(gradient, values))

    def evaluate_values(values):
        return _Result(objective(values))

    def evaluate_trial(values):
        downforce = -objective(values)
        return _Result(objective(values), downforce=downforce), {
            "downforce_coefficient": downforce
        }

    common = dict(
        transform=IdentityTransform(),
        parent_result=_Result(objective(rho), downforce=-objective(rho), gradient=gradient),
        rho_parent=rho,
        parent_downforce=-objective(rho),
        alpha=1.0,
        move_limit=0.1,
        target=float(np.mean(rho)),
        v_max=0.9,
        volume_tolerance=1e-8,
        objective_noise_threshold=1e-6,
        downforce_noise_threshold=1e-6,
        bracket_spec=BracketSpec(epsilon=1e-4, noise_floor_abs=1e-6),
        evaluate_values=evaluate_values,
        evaluate_trial=evaluate_trial,
    )
    old, _ = evaluate_phase2_candidate(**common)
    assert old.bracket["reason"] == "bracket_bounds_asymmetric_minus"
    bounded, corrected = evaluate_phase2_candidate(**common, freeze_box_faces=True)
    assert bounded.frozen_box_face_cells == 1
    assert corrected[0] == rho[0]
    assert bounded.bracket["ok"] is True
    assert bounded.accepted is True


def test_volume_only_agreement_does_not_make_the_candidate_pass():
    rho = np.full(8, 0.018)
    parent = _Result(PARENT_OBJECTIVE, downforce=PARENT_DOWNFORCE, gradient=np.full(8, -1.0))
    result, accepted_rho = run_ladder(rho, parent, PARENT_OBJECTIVE, PARENT_DOWNFORCE)
    assert accepted_rho is None
    assert result["successful"] is False
    assert len(result["candidates"]) == len(ALPHA_LADDER)


def test_accepted_alpha_stops_the_ladder_on_a_genuine_improvement():
    rho = np.full(8, 0.018)
    parent = _Result(PARENT_OBJECTIVE, downforce=PARENT_DOWNFORCE, gradient=np.full(8, -1.0))
    result, accepted_rho = run_ladder(
        rho,
        parent,
        PARENT_OBJECTIVE - 0.05,          # trial objective improves
        PARENT_DOWNFORCE + 0.05,          # raw downforce improves
    )
    assert result["successful"] is True
    assert accepted_rho is not None
    assert result["candidates"][0]["alpha"] == 1.0
    gates = result["candidates"][0]["gates"]
    assert gates["canonical_objective_improved"] is True
    assert gates["raw_downforce_improved"] is True
    assert gates["mask_invariance"] is True
    assert gates["volume_residual_within_tolerance"] is True


def test_path_b_sign_mismatch_fails_the_bracket():
    rho = np.array([0.5] * 8)
    gradient = np.array([-1.0] * 8)   # descent gradient for J
    delta = np.array([-0.01] * 8)     # proposal direction: rho increases J

    def eval_values(rho_array):
        if bool(np.all(rho_array > rho)):
            return _Result(-0.4)
        return _Result(-0.6)

    outcome = evaluate_path_b_bracket(
        spec=_bracket_spec(),
        parent_rho=rho,
        parent_gradient=gradient,
        proposal_delta=delta,
        active=np.ones_like(rho, dtype=bool),
        evaluate_values=eval_values,
    )
    assert outcome.ok is False
    assert outcome.reason == "not_a_descent_direction"


def test_path_b_descent_direction_passes_the_registered_bracket():
    rho = np.array([0.5] * 8)
    gradient = np.array([-1.0] * 8)   # canonical descent direction along +rho
    delta = np.array([+0.01] * 8)     # the registered proposal moves +rho

    def eval_values(rho_array):
        if bool(np.all(rho_array > rho)):
            return _Result(-0.6)
        return _Result(-0.4)

    outcome = evaluate_path_b_bracket(
        spec=_bracket_spec(),
        parent_rho=rho,
        parent_gradient=gradient,
        proposal_delta=delta,
        active=np.ones_like(rho, dtype=bool),
        evaluate_values=eval_values,
    )
    assert outcome.ok is True
    assert outcome.reason == "descent_sign_match"
    assert outcome.d_adj < 0.0
    assert outcome.d_fd < -NOISE
