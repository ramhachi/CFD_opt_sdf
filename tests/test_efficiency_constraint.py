"""Sign and gradient semantics of the SDF-native objective and constraints."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.canonical_objective import (
    EfficiencyConstraint,
    VolumeConstraint,
    canonical_downforce_objective,
    canonical_downforce_objective_gradient,
)


def test_downforce_objective_is_negated_downforce():
    assert canonical_downforce_objective(0.75) == -0.75
    gradient = canonical_downforce_objective_gradient(np.array([1.0, -2.0]))
    assert np.array_equal(gradient, np.array([-1.0, 2.0]))


def test_efficiency_constraint_value_sign_and_satisfaction():
    constraint = EfficiencyConstraint(r_min=2.0)
    assert constraint.value(c_drag=1.0, c_downforce=1.5) == 0.5
    assert not constraint.satisfied(c_drag=1.0, c_downforce=1.5)
    assert constraint.value(c_drag=1.0, c_downforce=2.0) == 0.0
    assert constraint.satisfied(c_drag=1.0, c_downforce=2.0)
    assert constraint.satisfied(c_drag=1.0, c_downforce=3.0)


def test_efficiency_constraint_gradient_assembly():
    constraint = EfficiencyConstraint(r_min=2.5)
    drag = np.array([1.0, 2.0, 3.0])
    downforce = np.array([0.5, 0.25, 1.0])
    assert np.allclose(constraint.gradient(drag_gradient=drag, downforce_gradient=downforce), 2.5 * drag - downforce)


def test_volume_constraint_normalized_budget():
    constraint = VolumeConstraint(v_max=0.08)
    assert constraint.value(0.08) == 0.0
    assert constraint.satisfied(0.079)
    assert not constraint.satisfied(0.081)
    assert np.allclose(constraint.gradient(np.array([0.08, 0.16])), np.array([1.0, 2.0]))


def test_invalid_limits_fail_closed():
    with pytest.raises(ValueError, match="r_min"):
        EfficiencyConstraint(r_min=0.0)
    with pytest.raises(ValueError, match="v_max"):
        VolumeConstraint(v_max=-1.0)
