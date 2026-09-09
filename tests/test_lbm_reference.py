import json

import numpy as np
import pytest

from cfd_sdf.lbm_reference import (
    LBMConfig,
    equilibrium,
    macroscopic,
    one_step,
    run_taylor_green,
    taylor_green_initial_state,
)


def test_equilibrium_round_trip_recovers_macroscopic_fields() -> None:
    config = LBMConfig(nx=12, ny=8, steps=0, velocity=0.02)
    rho, u, populations = taylor_green_initial_state(config)

    recovered_rho, recovered_u = macroscopic(populations)

    np.testing.assert_allclose(recovered_rho, rho, rtol=1.0e-14, atol=1.0e-14)
    np.testing.assert_allclose(recovered_u, u, rtol=1.0e-14, atol=1.0e-14)
    np.testing.assert_allclose(equilibrium(rho, np.moveaxis(u, 0, -1)), populations)


def test_periodic_bgk_conserves_global_mass_and_momentum() -> None:
    config = LBMConfig(nx=20, ny=12, steps=40, viscosity=0.08, velocity=0.01)
    rho, u, populations = taylor_green_initial_state(config)
    initial_mass = float(np.sum(rho))
    initial_momentum = np.sum(rho[None, ...] * u, axis=(1, 2))

    for _ in range(config.steps):
        populations = one_step(populations, config)

    final_rho, final_u = macroscopic(populations)
    np.testing.assert_allclose(np.sum(final_rho), initial_mass, rtol=1.0e-13, atol=1.0e-13)
    np.testing.assert_allclose(
        np.sum(final_rho[None, ...] * final_u, axis=(1, 2)),
        initial_momentum,
        rtol=1.0e-12,
        atol=1.0e-12,
    )


def test_taylor_green_analytic_decay_error_is_grid_sensitive() -> None:
    # Diffusive lattice scaling keeps the normalized box, Re=U*L/nu, and
    # viscous time nu*t/L^2 fixed while the cell count is refined.
    reports = [
        run_taylor_green(
            LBMConfig(nx=n, ny=n, steps=steps, viscosity=0.1, velocity=velocity)
        )
        for n, steps, velocity in ((16, 25, 0.02), (32, 100, 0.01), (64, 400, 0.005))
    ]
    coarse, medium, fine = reports

    assert coarse["evidence_status"] == "NUMERICAL_REFERENCE_ONLY"
    assert coarse["target_aero_evidence"] == "NOT_AVAILABLE"
    assert coarse["shape_gradient_evidence"] == "NOT_AVAILABLE"
    coarse_error = coarse["analytic_decay"]["relative_rms_error"]
    medium_error = medium["analytic_decay"]["relative_rms_error"]
    fine_error = fine["analytic_decay"]["relative_rms_error"]
    assert fine_error < medium_error < coarse_error
    # The periodic BGK stencil is second-order in this smooth, low-Mach test.
    observed_orders = (
        np.log(coarse_error / medium_error) / np.log(2.0),
        np.log(medium_error / fine_error) / np.log(2.0),
    )
    np.testing.assert_allclose(observed_orders, (2.0, 2.0), atol=0.15)
    assert fine["analytic_decay"]["pass"] is True


def test_run_summary_is_json_safe_and_marks_scope() -> None:
    summary = run_taylor_green(LBMConfig(nx=12, ny=16, steps=3, viscosity=0.1))

    encoded = json.dumps(summary, sort_keys=True)
    assert '"backend": "numpy_cpu"' in encoded
    assert summary["evidence_scope"] == "NOT_TARGET_AERO_OR_SHAPE_GRADIENT_EVIDENCE"
    assert summary["lattice"]["population_shape"] == [9, 16, 12]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"nx": 3},
        {"ny": 3},
        {"steps": -1},
        {"viscosity": 0.0},
        {"viscosity": 0.6},
        {"viscosity": "bad"},
        {"velocity": -0.01},
        {"velocity": 0.1},
    ],
)
def test_invalid_controls_fail_closed(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LBMConfig(**kwargs)


def test_one_step_rejects_wrong_population_shape() -> None:
    config = LBMConfig(nx=32, ny=24)
    with pytest.raises(ValueError, match="shape"):
        one_step(np.zeros((9, config.nx, config.ny)), config)
