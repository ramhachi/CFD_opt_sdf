import numpy as np
import pytest

from cfd_sdf.lbm_reference import (
    LBMConfig, one_step, taylor_green_initial_state,
)


def _metal():
    mx = pytest.importorskip("mlx.core")
    if not mx.metal.is_available():
        pytest.skip("Metal device required")
    return mx


def test_metal_periodic_step_matches_cpu_on_rectangular_grid():
    mx = _metal()
    from cfd_sdf.lbm_metal import MetalStepper
    config = LBMConfig(nx=24, ny=16, steps=10)
    _, _, cpu = taylor_green_initial_state(config)
    gpu = mx.array(cpu, dtype=mx.float32)
    step = MetalStepper(config.viscosity)
    mass = float(cpu.sum())
    for _ in range(config.steps):
        gpu = step(gpu)
        cpu = one_step(cpu, config)
    np.testing.assert_allclose(np.asarray(gpu), cpu, rtol=2e-5, atol=2e-7)
    assert abs(float(np.asarray(gpu).astype(np.float64).sum()) - mass) / mass < 1e-6


def test_metal_non_float32_is_explicitly_rejected():
    mx = _metal()
    from cfd_sdf.lbm_metal import MetalStepper
    step = MetalStepper(0.1)
    with pytest.raises(ValueError, match="float32"):
        step(mx.zeros((9, 4, 4), dtype=mx.int32))


@pytest.mark.parametrize("viscosity", [0.0, 0.5, 0.6, "bad"])
def test_metal_rejects_invalid_bgk_viscosity(viscosity):
    _metal()
    from cfd_sdf.lbm_metal import MetalStepper

    with pytest.raises(ValueError, match="viscosity"):
        MetalStepper(viscosity)
