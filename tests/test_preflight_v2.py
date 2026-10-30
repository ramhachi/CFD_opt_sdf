"""Tests for the PQ3.3b preflight v2 measurement core."""

import numpy as np
import pytest

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.preflight_v2 import MASK_DRIFT_TOLERANCE, measure_level

SHAPE = (6, 5, 4)
SPACING = 0.05


def _flat(x):
    return np.asarray(x).ravel(order="F")


def _grid() -> dict:
    shape = SHAPE
    active = np.zeros(shape, dtype=bool)
    active[2:4, 1:4, 1:3] = True
    allowed = active.copy()
    forbidden = np.zeros(shape, dtype=bool)
    forbidden[0, 0, 0] = True
    fixed = np.zeros(shape, dtype=bool)
    fixed[5, 4, 3] = True
    joint = active & allowed & ~forbidden & ~fixed
    return {
        "active": _flat(joint),
        "allowed": _flat(allowed),
        "forbidden": _flat(forbidden),
        "fixed": _flat(fixed),
    }


def _transform(masks, b: float, q: float, radius_m: float = 0.1) -> DesignTransform:
    return DesignTransform(
        shape=SHAPE,
        spacing_m=SPACING,
        active_mask=masks["active"],
        filter=ConeFilter(SHAPE, SPACING, masks["active"], radius_m=radius_m),
        projection=TanhProjection(b, 0.5),
        ramp=RampInterpolation(q),
    )


def _gradient(masks) -> np.ndarray:
    grad = np.zeros(masks["active"].shape, dtype=np.float64)
    grad[masks["active"]] = -1.0
    return grad


def _rho(masks, value: float = 0.3) -> np.ndarray:
    rho = np.full(masks["active"].shape, value, dtype=np.float64)
    rho[masks["fixed"]] = 1.0
    return rho


def test_drift_is_always_measured_and_never_none_forbidden_path():
    masks = _grid()
    transform = _transform(masks, b=8.0, q=30.0)
    rho = _rho(masks)
    record = measure_level(
        transform=transform,
        rho=rho,
        gradient=_gradient(masks),
        forbidden_mask=masks["forbidden"],
        fixed_solid_mask=masks["fixed"],
        move_limit=0.02,
        registered_target=0.9,  # unreachable: bracket failure path
        v_max_projected=0.9,
    )
    assert record["bracketed"] is False
    assert record["bracket_error"] is not None
    for register, drift in record["mask_drift_max"].items():
        assert isinstance(drift, float), (register, drift)
        assert not np.isnan(drift)
    assert record["masks_invariant"] is not None
    assert record["masks_invariant"] is True
    assert max(record["mask_drift_max"].values()) <= MASK_DRIFT_TOLERANCE


def test_bracketed_target_runs_propose_and_probe_measures_contract():
    masks = _grid()
    transform = _transform(masks, b=4.0, q=15.0, radius_m=0.05)
    rho = _rho(masks)
    record = measure_level(
        transform=transform,
        rho=rho,
        gradient=_gradient(masks),
        forbidden_mask=masks["forbidden"],
        fixed_solid_mask=masks["fixed"],
        move_limit=0.2,
        registered_target=0.9,  # above frontier -> not bracketed
        v_max_projected=0.9,
    )
    assert record["monotone_nondecreasing"] is True
    assert record["frontier_growth"] > 0.0
    assert record["masks_invariant"] is True
    probe = record["probe"]
    assert probe is not None
    assert "error" not in probe
    assert probe["within_tolerance"] is True
    assert isinstance(probe["mask_drift"]["forbidden"], float)


def test_probe_contract_forbidden_and_fixed_cells_untouched():
    masks = _grid()
    transform = _transform(masks, b=4.0, q=15.0, radius_m=0.05)
    rho = _rho(masks, 0.4)
    rho[masks["forbidden"]] = 0.0
    record = measure_level(
        transform=transform,
        rho=rho,
        gradient=_gradient(masks),
        forbidden_mask=masks["forbidden"],
        fixed_solid_mask=masks["fixed"],
        move_limit=0.2,
        registered_target=0.9,
        v_max_projected=0.9,
    )
    assert record["masks_invariant"] is True
    assert record["mask_drift_max"]["forbidden"] <= MASK_DRIFT_TOLERANCE
    assert record["mask_drift_max"]["fixed_solid"] <= MASK_DRIFT_TOLERANCE


def test_masks_must_not_overlap_joint_active():
    masks = _grid()
    omask = masks["forbidden"].copy()
    omask[masks["active"]] = True  # overlap active region
    transform = _transform(masks, b=4.0, q=15.0)
    with pytest.raises(ValueError, match="must not overlap"):
        measure_level(
            transform=transform,
            rho=np.full(masks["active"].shape, 0.3),
            gradient=_gradient(masks),
            forbidden_mask=omask,
            fixed_solid_mask=masks["fixed"],
            move_limit=0.05,
            registered_target=0.9,
            v_max_projected=0.9,
        )


def test_mask_shape_mismatch_raises():
    masks = _grid()
    transform = _transform(masks, b=4.0, q=15.0)
    with pytest.raises(ValueError, match="shape"):
        measure_level(
            transform=transform,
            rho=np.full(masks["active"].shape, 0.3),
            gradient=_gradient(masks),
            forbidden_mask=np.zeros(3, dtype=bool),
            fixed_solid_mask=masks["fixed"],
            move_limit=0.05,
            registered_target=0.9,
            v_max_projected=0.9,
        )
