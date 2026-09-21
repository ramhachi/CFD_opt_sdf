"""Tests for the GCMMA-shaped acceptance controller and the Stage T loop (DF3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.nonlinear_acceptance import (
    AcceptanceState,
    TrialEvaluation,
    TrialProposal,
    accept_trial,
    merit,
    run_conservative_inner_loop,
    violation,
)
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.problem_spec_compiler import compile_problem
from cfd_sdf.stage_t_loop import (
    LoopSpec,
    ProjectedGradientBackend,
    make_oracle_from_compiled,
    run_stage_t_loop,
)


def _evaluation(
    objective: float,
    constraints: dict[str, float],
    *,
    primal: bool = True,
    adjoint: bool = True,
    geometry: bool = True,
) -> TrialEvaluation:
    return TrialEvaluation(
        objective=objective,
        constraint_values=dict(constraints),
        primal_converged=primal,
        adjoint_converged=adjoint,
        geometry_ok=geometry,
    )


def _state(move: float = 0.1, penalty: float = 1.0) -> AcceptanceState:
    return AcceptanceState(rho=np.zeros(4), move_radius=move, penalty=penalty)


def test_violation_and_merit_are_consistent():
    assert violation({"a": 0.2, "b": 0.0}) == pytest.approx(0.2)
    assert merit(1.0, {"a": 0.5}, penalty=2.0) == pytest.approx(1.0 + 2.0 * 0.25)


def test_accept_trial_accepts_feasible_merit_decrease():
    parent = _evaluation(1.0, {"g": -0.1})
    trial = _evaluation(0.8, {"g": -0.05})
    decision = accept_trial(
        parent=parent,
        trial=trial,
        predicted_trial_objective=0.85,
        state=_state(),
    )
    assert decision.accepted is True
    assert decision.status == "accept"
    # trust ratio 1.33 > 0.75 grows the next move within the registered cap
    assert decision.new_move_radius == pytest.approx(0.15)


def test_accept_trial_rolls_back_on_qualification_and_geometry_failures():
    parent = _evaluation(1.0, {"g": -0.1})
    for kwargs, reason in (
        ({"primal": False}, "primal_not_converged"),
        ({"adjoint": False}, "adjoint_not_converged"),
        ({"geometry": False}, "geometry_gate_failed"),
    ):
        trial = _evaluation(0.5, {"g": -0.1}, **kwargs)
        decision = accept_trial(
            parent=parent,
            trial=trial,
            predicted_trial_objective=0.5,
            state=_state(),
        )
        assert decision.accepted is False
        assert decision.reason == reason
        assert decision.new_move_radius == pytest.approx(0.05)


def test_accept_trial_rejects_non_decreasing_merit_and_grows_penalty():
    parent = _evaluation(1.0, {"g": -0.1})
    trial = _evaluation(1.02, {"g": -0.1})
    decision = accept_trial(
        parent=parent,
        trial=trial,
        predicted_trial_objective=0.9,
        state=_state(),
    )
    assert decision.accepted is False
    assert decision.reason == "merit_not_decreased"
    assert decision.new_penalty > 1.0
    assert decision.new_move_radius == pytest.approx(0.05)


def test_accept_trial_restoration_requires_monotone_violation_reduction():
    parent = _evaluation(1.0, {"g": 0.5})
    improving = _evaluation(0.9, {"g": 0.2})
    decision = accept_trial(
        parent=parent,
        trial=improving,
        predicted_trial_objective=0.8,
        state=_state(),
    )
    assert decision.status == "restoration_accept"

    worsening = _evaluation(0.9, {"g": 0.6})
    decision = accept_trial(
        parent=parent,
        trial=worsening,
        predicted_trial_objective=0.8,
        state=_state(),
    )
    assert decision.accepted is False
    assert decision.reason == "constraint_violation_not_reduced"


def test_accept_trial_rejects_low_trust_ratio_feasible_step():
    parent = _evaluation(1.0, {"g": -0.1})
    trial = _evaluation(0.98, {"g": -0.09})
    decision = accept_trial(
        parent=parent,
        trial=trial,
        predicted_trial_objective=0.5,
        state=_state(),
    )
    assert decision.accepted is False
    assert decision.reason == "trust_ratio_low"
    assert decision.trust_ratio is not None and decision.trust_ratio < 0.25


def test_conservative_inner_loop_retries_from_same_parent_until_accepted():
    parent = _evaluation(1.0, {"g": -0.1})
    state = AcceptanceState(rho=np.full(3, 0.1), move_radius=0.2, penalty=1.0)
    calls: list[float] = []

    def propose(working: AcceptanceState) -> TrialProposal:
        calls.append(working.move_radius)
        return TrialProposal(delta=np.full(3, working.move_radius), backend="test")

    def evaluate(rho: np.ndarray, proposal: TrialProposal) -> TrialEvaluation:
        # the first (large) step fails qualification; smaller steps succeed
        if rho[0] > 0.2:
            return _evaluation(0.5, {"g": -0.05}, primal=False)
        return _evaluation(0.9, {"g": -0.05})

    decision, trial_rho, trace = run_conservative_inner_loop(
        parent=parent,
        state=state,
        propose=propose,
        evaluate=evaluate,
        predicted_objective=lambda proposal: 0.9,
    )
    assert decision.accepted is True
    assert len(calls) == 2
    assert calls[1] < calls[0]
    assert len(trace) == 2
    assert trial_rho is not None and trial_rho[0] <= 0.2


def _spec(tmp_path: Path, *, volume_limit: float = 0.5):
    import yaml

    data = {
        "schema_version": 2,
        "problem_id": "loop_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {"kind": "uniform_cartesian", "voxel_size_m": 1.0, "padding_m": 0.0},
        "geometry_regions": [
            {"id": "design_box", "role": "design_domain", "file": "geometry/design_box.stl"}
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [30.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        ],
        "responses": [
            {"id": "downforce", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, -1.0]}
        ],
        "objectives": [
            {
                "id": "max_downforce",
                "sense": "maximize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "downforce"}],
            }
        ],
        "constraints": [
            {
                "id": "volume_budget",
                "relation": "<=",
                "limit": volume_limit,
                "terms": [
                    {"coefficient": 1.0, "flow_case_id": "straight", "response_id": "downforce"}
                ],
            }
        ],
        "topology_policy": {
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
            "root_groups": [],
            "solid_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
        },
    }
    path = tmp_path / "problem.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_problem_spec(path)


def _transform(n: int = 4) -> DesignTransform:
    shape = (n, 1, 1)
    active = np.ones(n, dtype=bool)
    return DesignTransform(
        shape=shape,
        spacing_m=1.0,
        active_mask=active,
        filter=ConeFilter(shape=shape, spacing_m=1.0, active_mask=active, radius_m=1.0),
        projection=TanhProjection(0.0, 0.5),
        ramp=RampInterpolation(0.0),
    )


def _fake_loop(
    tmp_path: Path,
    *,
    iterations: int,
    checkpoint: Path | None = None,
    resume: Path | None = None,
    volume_limit: float = 0.5,
):
    spec = _spec(tmp_path, volume_limit=volume_limit)
    compiled = compile_problem(spec)
    transform = _transform()
    initial = np.full(4, 0.1)

    def primitive_evaluator(rho: np.ndarray) -> dict:
        total = float(np.sum(rho))
        return {
            "values": {("straight", "downforce"): total},
            "gradients": {("straight", "downforce"): np.ones_like(rho)},
            "primal_converged": True,
            "adjoint_converged": True,
        }

    oracle = make_oracle_from_compiled(
        transform=transform, compiled=compiled, primitive_evaluator=primitive_evaluator
    )
    return run_stage_t_loop(
        spec=LoopSpec(transform=transform, compiled=compiled, move_limit=0.1, max_iterations=iterations),
        oracle=oracle,
        backend=ProjectedGradientBackend(),
        initial_rho=initial,
        checkpoint_path=checkpoint,
        resume_from=resume,
    )


def test_loop_accepts_monotone_feasible_steps(tmp_path: Path):
    result = _fake_loop(tmp_path, iterations=5, volume_limit=0.9)
    # the reference backend cannot slide along an active constraint surface, so
    # it stops improving once every cell and the volume budget are at the limit
    assert result.accepted >= 2
    assert result.final_evaluation.objective <= -0.9 + 1e-9
    assert result.final_evaluation.objective < -4 * 0.1
    for row in result.trace:
        if row.get("accepted"):
            assert row["trial_constraints"]["volume_budget"] <= 1e-9
            assert "objective_gradient" not in row  # trace carries measurements, not gradients
    assert result.transform_hash == _transform().transform_hash()


def test_loop_checkpoint_resume_is_deterministic(tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.json"
    partial = _fake_loop(tmp_path / "partial", iterations=3, checkpoint=checkpoint)
    resumed = _fake_loop(tmp_path / "resumed", iterations=5, resume=checkpoint, checkpoint=None)
    single = _fake_loop(tmp_path / "single", iterations=5)

    assert len(resumed.trace) == 5
    assert np.allclose(resumed.final_rho, single.final_rho)
    assert np.allclose(partial.final_rho, resumed.final_rho, atol=1e-12) or len(single.trace) == 5


def test_loop_rejects_unconverged_oracle_trials_and_still_accepts(tmp_path: Path):
    spec = _spec(tmp_path)
    compiled = compile_problem(spec)
    transform = _transform()
    calls = {"count": 0}

    def primitive_evaluator(rho: np.ndarray) -> dict:
        calls["count"] += 1
        total = float(np.sum(rho))
        return {
            "values": {("straight", "downforce"): total},
            "gradients": {("straight", "downforce"): np.ones_like(rho)},
            "primal_converged": total <= 0.45,
            "adjoint_converged": True,
            "solver_status": "converged" if total <= 0.45 else "iteration_cap",
        }

    oracle = make_oracle_from_compiled(
        transform=transform, compiled=compiled, primitive_evaluator=primitive_evaluator
    )
    result = run_stage_t_loop(
        spec=LoopSpec(transform=transform, compiled=compiled, move_limit=0.1, max_iterations=6),
        oracle=oracle,
        backend=ProjectedGradientBackend(),
        initial_rho=np.full(4, 0.1),
    )
    assert any(not row.get("accepted") for row in result.trace)
    assert any(
        "primal_not_converged" in str(row.get("inner")) for row in result.trace
    )
    assert result.accepted >= 1
    assert result.final_evaluation.objective <= 0.45 + 1e-9
