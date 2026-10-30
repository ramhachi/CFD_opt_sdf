"""Tests for the module-owned Stage T design transform and its adjoint (DF1)."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.design_transform import (
    BlockFilter,
    ConeFilter,
    DesignTransform,
    DesignTransformError,
    RampInterpolation,
    TanhProjection,
)

SHAPE = (4, 3, 2)
SPACING = 1.0
ACTIVE = np.ones(int(np.prod(SHAPE)), dtype=bool)


def _cone(radius_m: float = 1.0, active: np.ndarray | None = None) -> ConeFilter:
    return ConeFilter(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=ACTIVE if active is None else active,
        radius_m=radius_m,
    )


def _block(width_m: float = 2.0) -> BlockFilter:
    return BlockFilter(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=ACTIVE,
        width_m=width_m,
    )


def _transform(**overrides) -> DesignTransform:
    kwargs = dict(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=ACTIVE,
        filter=_cone(),
        projection=TanhProjection(0.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    kwargs.update(overrides)
    return DesignTransform(**kwargs)


def test_cone_filter_is_adjoint_and_preserves_constants():
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=ACTIVE.size), rng.normal(size=ACTIVE.size)
    F = _cone()
    lhs, rhs = float(np.dot(F.H(x), y)), float(np.dot(x, F.HT(y)))
    assert lhs == pytest.approx(rhs, abs=1e-9 * max(abs(lhs), 1.0))
    assert np.allclose(F.H(ACTIVE.astype(float))[ACTIVE], 1.0)


def test_block_filter_is_symmetric_projection_and_diagnostics_only():
    rng = np.random.default_rng(1)
    x = rng.normal(size=ACTIVE.size)
    F = _block(width_m=2.0)
    assert np.allclose(F.H(x), F.HT(x))
    assert np.allclose(F.H(F.H(x)), F.H(x))
    assert F.production_allowed is False
    transform = _transform(filter=F)
    with pytest.raises(DesignTransformError, match="diagnostics only"):
        transform.production_ready()
    transform.production_ready(allow_diagnostics=True)


def test_projection_and_ramp_match_their_definitions():
    values = np.linspace(0.0, 1.0, 11)
    identity = TanhProjection(0.0, 0.5)
    assert np.allclose(identity.forward(values), values)
    assert np.allclose(identity.derivative(values), 1.0)

    projection = TanhProjection(8.0, 0.5)
    projected = projection.forward(values)
    assert float(projected.min()) >= 0.0 and float(projected.max()) <= 1.0
    assert projected[0] < projected[-1]
    derivative = projection.derivative(values)
    step = 1e-6
    fd = (projection.forward(values + step) - projection.forward(values - step)) / (2 * step)
    assert np.allclose(derivative, fd, rtol=1e-5, atol=1e-6)

    ramp = RampInterpolation(30.0)
    assert np.allclose(ramp.forward(np.array([0.0, 1.0])), np.array([0.0, 1.0]))
    fd_ramp = (ramp.forward(values + step) - ramp.forward(values - step)) / (2 * step)
    assert np.allclose(ramp.derivative(values), fd_ramp, rtol=1e-5, atol=1e-7)


def test_forward_composition_and_volume_fraction_use_projected_field():
    rng = np.random.default_rng(2)
    rho = rng.uniform(0.2, 0.8, size=ACTIVE.size)
    transform = _transform(
        filter=_cone(radius_m=1.0),
        projection=TanhProjection(4.0, 0.5),
        ramp=RampInterpolation(8.0),
    )
    state = transform.forward(rho)
    assert state.rho_filtered.shape == rho.shape
    manual_projected = transform.projection.forward(state.rho_filtered)
    assert np.allclose(state.rho_projected, manual_projected)
    assert np.allclose(state.beta, transform.ramp.forward(state.rho_projected))
    assert transform.projected_volume_fraction(state) == pytest.approx(
        float(np.mean(state.rho_projected[ACTIVE]))
    )


def test_backward_matches_central_difference_directional_derivative():
    rng = np.random.default_rng(3)
    rho = np.clip(rng.uniform(0.2, 0.8, size=ACTIVE.size), 0.0, 1.0)
    direction = rng.normal(size=ACTIVE.size)
    seed = rng.normal(size=ACTIVE.size)
    transform = _transform(
        filter=_cone(radius_m=1.0),
        projection=TanhProjection(6.0, 0.5),
        ramp=RampInterpolation(30.0),
    )

    def objective(values: np.ndarray) -> float:
        return float(np.dot(seed, transform.forward(values).beta))

    step = 1e-6
    fd = (objective(rho + step * direction) - objective(rho - step * direction)) / (2 * step)
    gradient = transform.backward(rho, seed)
    assert float(np.dot(gradient, direction)) == pytest.approx(fd, rel=1e-5, abs=1e-9)


def test_identity_profile_has_identity_chain():
    rho = np.full(ACTIVE.size, 0.3)
    seed = np.ones(ACTIVE.size)
    transform = _transform()
    assert np.allclose(transform.backward(rho, seed), seed * ACTIVE)


def test_transform_hash_is_stable_and_configuration_sensitive():
    first = _transform()
    same = _transform()
    assert first.transform_hash() == same.transform_hash()
    different_projection = _transform(projection=TanhProjection(4.0, 0.5))
    assert different_projection.transform_hash() != first.transform_hash()
    different_ramp = _transform(ramp=RampInterpolation(8.0))
    assert different_ramp.transform_hash() != first.transform_hash()
    different_filter = _transform(filter=_cone(radius_m=2.0))
    assert different_filter.transform_hash() != first.transform_hash()
    description = first.describe()
    assert description["filter"]["kind"] == "cone_density_filter"
    assert description["projection"]["kind"] == "identity"
    assert len(description["active_mask_sha256"]) == 64


def test_fail_closed_declaration_and_input_validation():
    with pytest.raises(DesignTransformError, match="radius"):
        _cone(radius_m=0.0)
    with pytest.raises(DesignTransformError, match="eta"):
        TanhProjection(4.0, 1.0)
    with pytest.raises(DesignTransformError, match="sharpness"):
        TanhProjection(-1.0, 0.5)
    with pytest.raises(DesignTransformError, match="RAMP q"):
        RampInterpolation(-0.5)
    with pytest.raises(DesignTransformError, match="empty"):
        _cone(active=np.zeros(ACTIVE.size, dtype=bool))

    transform = _transform()
    with pytest.raises(DesignTransformError, match=r"\[0, 1\]"):
        transform.forward(np.full(ACTIVE.size, 1.5))
    with pytest.raises(DesignTransformError, match="non-finite"):
        transform.forward(np.full(ACTIVE.size, np.nan))
    with pytest.raises(DesignTransformError, match="shape"):
        transform.forward(np.zeros(3))
    with pytest.raises(DesignTransformError, match="shape"):
        transform.backward(np.zeros(ACTIVE.size), np.zeros(3))
    with pytest.raises(DesignTransformError, match="non-finite"):
        transform.backward(np.zeros(ACTIVE.size), np.full(ACTIVE.size, np.inf))


def test_projected_volume_constraint_value_and_gradient_use_projection():
    from cfd_sdf.problem_spec_compiler import VolumeOccupationConstraint

    rho = np.full(ACTIVE.size, 0.25)
    transform = _transform(
        filter=_cone(radius_m=1.0),
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    constraint = VolumeOccupationConstraint("volume_fraction_max", limit=0.2)
    projected = transform.forward(rho).rho_projected
    expected_value = float(np.mean(projected[ACTIVE])) - 0.2
    assert constraint.value(transform, rho) == pytest.approx(expected_value)

    direction = np.zeros(ACTIVE.size)
    direction[0] = 1.0
    step = 1e-6
    fd = (
        constraint.value(transform, rho + step * direction)
        - constraint.value(transform, rho - step * direction)
    ) / (2 * step)
    gradient = constraint.gradient(transform, rho)
    assert float(np.dot(gradient, direction)) == pytest.approx(fd, rel=1e-4, abs=1e-9)


def test_pullback_spaces_differ_only_by_the_ramp_derivative():
    rng = np.random.default_rng(9)
    rho = np.clip(rng.uniform(0.2, 0.8, size=ACTIVE.size), 0.0, 1.0)
    seed = rng.normal(size=ACTIVE.size)
    identity_ramp = _transform(ramp=RampInterpolation(0.0))
    assert np.allclose(
        identity_ramp.pullback_from_beta(rho, seed),
        identity_ramp.pullback_from_projected(rho, seed),
    )

    ramped = _transform(
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    state = ramped.forward(rho)
    expected_projected = ramped.filter.HT(
        ramped.projection.derivative(state.rho_filtered) * seed
    )
    expected_beta = ramped.filter.HT(
        ramped.projection.derivative(state.rho_filtered)
        * ramped.ramp.derivative(state.rho_projected)
        * seed
    )
    assert np.allclose(ramped.pullback_from_projected(rho, seed), expected_projected)
    assert np.allclose(ramped.pullback_from_beta(rho, seed), expected_beta)
    assert not np.allclose(expected_projected, expected_beta)
