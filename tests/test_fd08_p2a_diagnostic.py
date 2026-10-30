from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.diagnose_fd08_r5_posthoc_p2a import (
    decompose_pair,
    fit_q_vs_epsilon_squared,
    loo_diagnostic,
    merge_epsilon_grids,
    odd_even_parts,
    plateau_window_metrics,
    sdf_soft_volume,
)


def test_pair_decomposition_uses_millimetres_for_report_and_metres_for_q() -> None:
    result = decompose_pair(0.004, 0.002, 0.003, 2.0)
    assert result["s_n"] == pytest.approx(0.001)
    assert result["q_n_per_m"] == pytest.approx(0.5)
    assert result["e_n"] == pytest.approx(0.0)


def test_unweighted_q_fit_recovers_registered_quadratic_form() -> None:
    eps_mm = [0.5, 1.5, 5.0, 15.0]
    q = [2.0 + 0.03 * epsilon**2 for epsilon in eps_mm]
    fit = fit_q_vs_epsilon_squared(eps_mm, q)
    assert fit["g_n_per_m"] == pytest.approx(2.0)
    assert fit["c_n_per_m_per_mm_squared"] == pytest.approx(0.03)
    assert fit["residual_rms_n_per_m"] < 1e-12


def test_plateau_uses_median_and_floor_over_smallest_epsilon() -> None:
    rows = [
        {"epsilon_m": epsilon, "q_n_per_m": q}
        for epsilon, q in zip((0.001, 0.002, 0.003, 0.004, 0.005), (10, 10, 12, 10, 10))
    ]
    metrics = plateau_window_metrics(rows, floor_n=0.02)
    assert metrics["q_ref_median_n_per_m"] == 10
    assert metrics["noise_equivalent_n_per_m"] == pytest.approx(20)
    assert metrics["normalizer_n_per_m"] == pytest.approx(20)
    assert metrics["maximum_relative_deviation"] == pytest.approx(0.1)


def test_loo_has_numeric_error_but_no_invented_pass_fail_boundary() -> None:
    three = [
        {"epsilon_mm": eps, "s_n": 100e-6, "q_n_per_m": 4.0 + 0.1 * eps**2}
        for eps in (0.5, 1.5, 5.0)
    ]
    four = three + [{"epsilon_mm": 15.0, "s_n": 120e-6, "q_n_per_m": 4.0 + 0.1 * 15.0**2}]
    unavailable = loo_diagnostic(three, 50.0)
    available = loo_diagnostic(four, 50.0)
    assert unavailable["calculation_status"] == "undeterminable"
    assert available["calculation_status"] == "calculable"
    assert available["status"] == "undeterminable"
    assert available["maximum_absolute_error_micro_n_per_m"] is not None
    assert available["status_reason"].startswith("no registered pass/fail")


def test_sdf_soft_volume_and_odd_even_decomposition() -> None:
    phi = np.asarray([-0.5, 0.0, 0.5], dtype=np.float32)
    h = 1.0
    assert sdf_soft_volume(phi, h) == pytest.approx(1.5)
    parts = odd_even_parts(5.0, 3.0, baseline=4.0, epsilon_m=0.5)
    assert parts["odd_part_m3"] == pytest.approx(1.0)
    assert parts["odd_part_over_epsilon_m2"] == pytest.approx(2.0)
    assert parts["even_part_m3"] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        odd_even_parts(1.0, 0.0, 0.0, epsilon_m=0.0)


def test_epsilon_grid_keeps_exact_r5_values_when_logspace_duplicates_them() -> None:
    r5 = [0.05, 0.15, 0.5, 1.5, 5.0, 15.0, 50.0]
    logspace = [0.049999999999999996, 0.5, 5.0, 50.0]
    unique, overlap = merge_epsilon_grids(r5, logspace)
    assert len(unique) == 7
    assert overlap == [0.05, 0.5, 5.0, 50.0]
    assert all(any(value == registered for value in unique) for registered in r5)
