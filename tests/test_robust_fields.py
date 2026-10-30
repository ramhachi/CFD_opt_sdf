"""Tests for the robust three-field formulation support (DF6)."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.robust_fields import FIELD_NAMES, RobustFieldError, RobustThreeField


def _transform(n: int = 4, *, spacing: float = 1.0, sharpness: float = 8.0, q: float = 30.0) -> DesignTransform:
    shape = (n, n, n)
    active = np.ones(n**3, dtype=bool)
    return DesignTransform(
        shape=shape,
        spacing_m=spacing,
        active_mask=active,
        filter=ConeFilter(shape=shape, spacing_m=spacing, active_mask=active, radius_m=1.5 * spacing),
        projection=TanhProjection(sharpness, 0.5),
        ramp=RampInterpolation(q),
    )


def test_fields_share_filter_and_differ_only_in_projection_threshold():
    transform = _transform()
    robust = RobustThreeField(transform, eta_eroded=0.7, eta_dilated=0.3)
    rng = np.random.default_rng(0)
    rho = rng.uniform(0.2, 0.8, size=transform.active.size)
    fields = robust.fields(rho)
    assert set(fields) == set(FIELD_NAMES)
    filtered = fields["intermediate"].rho_filtered
    assert np.allclose(fields["eroded"].rho_filtered, filtered)
    assert np.allclose(fields["dilated"].rho_filtered, filtered)
    # higher eta is more aggressive: eroded <= intermediate <= dilated on values
    assert np.all(fields["eroded"].rho_projected <= fields["intermediate"].rho_projected + 1e-12)
    assert np.all(fields["intermediate"].rho_projected <= fields["dilated"].rho_projected + 1e-12)


def test_threshold_ordering_and_identity_projection_are_fail_closed():
    with pytest.raises(RobustFieldError, match="thresholds"):
        RobustThreeField(_transform(), eta_eroded=0.4, eta_dilated=0.3)
    identity = _transform(sharpness=0.0)
    with pytest.raises(RobustFieldError, match="non-identity"):
        RobustThreeField(identity)


def test_worst_case_objective_selects_per_sense():
    robust = RobustThreeField(_transform())
    values = {"eroded": 0.4, "intermediate": 0.5, "dilated": 0.6}
    assert robust.worst_case_objective(values, sense="minimize") == 0.6
    assert robust.worst_case_objective(values, sense="maximize") == 0.4
    with pytest.raises(RobustFieldError, match="missing field"):
        robust.worst_case_objective({"eroded": 0.4}, sense="minimize")
    with pytest.raises(RobustFieldError, match="sense"):
        robust.worst_case_objective(values, sense="sideways")


def test_dilated_volume_constraint_uses_the_dilated_field():
    transform = _transform()
    robust = RobustThreeField(transform, eta_eroded=0.7, eta_dilated=0.3)
    rho = np.full(transform.active.size, 0.5)
    fields = robust.fields(rho)
    # the dilated field is at least as large as the intermediate field
    assert robust.volume_fraction(fields["dilated"]) >= robust.volume_fraction(
        fields["intermediate"]
    )
    value = robust.dilated_volume_constraint_value(rho, limit=0.5)
    assert value == pytest.approx(robust.volume_fraction(fields["dilated"]) - 0.5)


def test_backward_matches_finite_difference_for_each_field():
    transform = _transform()
    robust = RobustThreeField(transform, eta_eroded=0.7, eta_dilated=0.3)
    rng = np.random.default_rng(1)
    rho = np.clip(rng.uniform(0.3, 0.7, size=transform.active.size), 0.0, 1.0)
    direction = rng.normal(size=transform.active.size)

    def objective(field_name: str, values: np.ndarray) -> float:
        state = robust.fields(values)[field_name]
        return float(np.sum(state.beta))

    for field_name in FIELD_NAMES:
        step = 1e-6
        fd = (objective(field_name, rho + step * direction) - objective(field_name, rho - step * direction)) / (2 * step)
        gradient = robust.backward(field_name, rho, np.ones_like(rho))
        assert float(np.dot(gradient, direction)) == pytest.approx(fd, rel=1e-4, abs=1e-8)


def test_same_topology_detects_consistent_and_inconsistent_designs():
    transform = _transform(n=6)
    robust = RobustThreeField(transform, eta_eroded=0.7, eta_dilated=0.3)
    rho_solid = np.zeros(transform.active.size)
    cube = np.zeros(transform.shape, dtype=bool)
    cube[1:5, 1:5, 1:5] = True
    rho_solid[cube.ravel(order="F")] = 1.0
    report = robust.same_topology(rho_solid)
    assert report["consistent"] is True
    assert report["components"]["intermediate"] == 1

    rho_island = np.zeros(transform.active.size)
    flat = rho_island.reshape(transform.shape, order="F")
    flat[3, 3, 3] = 1.0
    island_report = robust.same_topology(rho_island)
    assert island_report["consistent"] is False
    assert island_report["components"]["eroded"] == 0
    assert "necessary condition" in island_report["caveat"]


def test_parameter_report_declares_relations_and_cost():
    robust = RobustThreeField(_transform())
    report = robust.parameter_report()
    assert report["volume_constraint_field"] == "dilated"
    assert report["eta_dilated"] < report["eta_intermediate"] < report["eta_eroded"]
    assert "Trillet" in report["analytic_relations"]
    assert "three primal/adjoint" in report["cost"]


def test_robust_fields_are_not_in_the_production_registry():
    robust = RobustThreeField(_transform())
    status = robust.production_status()
    assert status["production_ready"] is False
    assert "PQ6" in status["reason"]
