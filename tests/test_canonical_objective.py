"""Regression tests: canonical objective contract + level inheritance rules."""

from __future__ import annotations

import hashlib
import sys

import numpy as np
import pytest

sys.path.insert(0, "src")

from cfd_sdf.canonical_objective import (  # noqa: E402
    canonical_objective_from,
    canonical_sense_sign,
    record_from_parent_result,
)
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.problem_spec_compiler import VolumeBudget, compile_problem  # noqa: E402
from cfd_sdf.preflight_v4_core import inherit_level_start_rho  # noqa: E402

REPO = pytest.importorskip("pathlib").Path(__file__).resolve().parents[1]
SPEC = REPO / "work" / "pq0_2_smoke" / "project_downforce_volume.yaml"


def _compiled():
    return compile_problem(
        load_problem_spec(SPEC),
        volume_budget=VolumeBudget("volume_fraction_max", 0.07632566813424899),
    )


def make_result(objective, gradient=None, space="rho_design", adjoint="converged"):
    from cfd_sdf.stage_t_loop import OracleResult

    return OracleResult(
        objective=objective,
        constraint_values={},
        primal_converged=True,
        objective_gradient=gradient,
        gradient_space=space,
        adjoint_status=adjoint,
    )


def test_maximize_objective_has_negative_sense_sign():
    assert canonical_sense_sign("maximize") == -1
    assert canonical_sense_sign("minimize") == 1


def test_raw_response_gradient_and_canonical_objective_gradient_have_opposite_sign():
    compiled = _compiled()
    raw_grad = np.full(8, 1.5)
    value = compiled.objective_value({("straight", "downforce"): 2.0})
    canonical_grad = compiled.objective_gradient({("straight", "downforce"): raw_grad})
    assert value == -2.0  # J = -downforce for the maximize sense
    assert bool(np.all(canonical_grad == -raw_grad))


def test_raw_numpy_gradient_is_rejected_at_the_oracle_boundary():
    with pytest.raises(TypeError, match="must not be passed"):
        canonical_objective_from(np.ones(4))


def test_values_only_result_is_rejected():
    with pytest.raises(TypeError, match="must not be passed"):
        canonical_objective_from(make_result(-1.0, gradient=None))


def test_wrong_gradient_space_is_rejected():
    with pytest.raises(TypeError, match="rho_design"):
        canonical_objective_from(make_result(-1.0, gradient=np.zeros(2), space="beta"))


def test_record_from_parent_result_hashes_raw_and_canonical_separately():
    gradient = np.full(4, 2.0)
    raw = np.full(4, 3.0)
    result = make_result(-0.5, gradient=gradient)
    record = record_from_parent_result(
        result=result,
        raw_downforce=1.0,
        raw_response_gradient=raw,
        objective_sense="maximize",
        objective_sign=-1,
    )
    assert record.canonical_objective == -0.5
    assert record.objective_sign == -1
    assert record.raw_response_gradient_sha256 != record.canonical_objective_gradient_sha256
    assert record.raw_response_gradient_sha256 == hashlib.sha256(
        np.ascontiguousarray(raw).tobytes()
    ).hexdigest()


def test_strict_level_inheritance_returns_the_same_values():
    parent = np.array([0.1, 0.2, 0.3])
    child = inherit_level_start_rho(parent)
    assert np.array_equal(parent, child)
    assert (
        hashlib.sha256(np.ascontiguousarray(parent).tobytes()).hexdigest()
        == hashlib.sha256(np.ascontiguousarray(child).tobytes()).hexdigest()
    )


def test_simulated_decay_is_absent_from_the_registered_sources():
    for candidate_path in (
        REPO / "scripts" / "pq3_3b_preflight_v4_2026_09.py",
        REPO / "src" / "cfd_sdf" / "preflight_v4_core.py",
        REPO / "src" / "cfd_sdf" / "phase2_policy.py",
    ):
        source = candidate_path.read_text(encoding="utf-8")
        for pattern in (
            'np.clip(accepted_rho - spec["move_limit"]',
            "accepted_rho - move_limit",
            "clip(accepted_rho - ",
        ):
            assert pattern not in source, (candidate_path, pattern)
