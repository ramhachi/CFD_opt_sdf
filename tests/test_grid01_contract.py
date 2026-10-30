from __future__ import annotations

import copy

import numpy as np
import pytest

from cfd_sdf import grid01_contract as C


def test_resolution_boundary_is_strict_and_unresolved_secant_is_retained():
    unresolved = C.secant_sample(0.1, C.MIN_RESOLVED_N, 0.0)
    assert unresolved["resolved"] is False
    assert unresolved["g_sec_n_per_m"] == pytest.approx(C.MIN_RESOLVED_N / (2 * C.STEP_M))
    assert unresolved["resolved_sign"] is None
    resolved = C.secant_sample(0.1, C.MIN_RESOLVED_N * 1.01, 0.0)
    assert resolved["resolved"] is True and resolved["resolved_sign"] == 1


def test_exactly_even_response_does_not_gain_a_secant_sign():
    value = C.secant_sample(0.3, 0.3001, 0.3001)
    assert value["g_sec_n_per_m"] == 0.0
    assert value["resolved"] is False
    assert value["resolved_sign"] is None
    assert value["even_part_n"] == pytest.approx(1.0e-4)
    assert value["eta_even"] is None


def test_comparison_with_either_unresolved_grid_never_reports_sign_agreement():
    result = C.component_comparison(
        {"g_sec_n_per_m": 1.0, "resolved": True},
        {"g_sec_n_per_m": 0.0, "resolved": False},
    )
    assert result["sign_status"] == "unresolved"
    assert result["resolved_signs_agree"] is None
    assert result["raw_sign_interpretation_resolved"] is False
    assert result["raw_ratio_flow32_over_flow24"] == 0.0


def test_main_and_robust_solvers_return_global_kkt_certificates():
    lift = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    drag = np.array([[-1.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0]])
    result = C.solve_cross_grid_proposals(lift, drag)
    main, robust = result["main_cross_grid"], result["robust_cross_grid"]
    assert result["all_solutions_verified"] is True
    assert main["verification"]["branch_count"] == 2
    assert robust["verification"]["branch_count"] == 32
    assert main["t_star_n_per_m"] == pytest.approx(1 / np.sqrt(2))
    assert robust["t_star_n_per_m"] == pytest.approx(1 / np.sqrt(2) - C.UNCERTAINTY_N_PER_M * np.sqrt(2))
    assert main["coefficient_vector"] == pytest.approx([1 / np.sqrt(2), 1 / np.sqrt(2), 0, 0])
    assert all(result["single_grid_references"][grid][mode]["verification"]["passed"] for grid in C.GRIDS for mode in ("main", "robust"))


def test_incompatible_drag_halfspaces_fail_closed_to_the_origin():
    lift = np.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    drag = np.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    result = C.solve_cross_grid_proposals(lift, drag)
    assert result["main_cross_grid"]["t_star_n_per_m"] == pytest.approx(0.0, abs=C.KKT_ATOL)
    assert result["robust_cross_grid"]["t_star_n_per_m"] == pytest.approx(0.0, abs=C.KKT_ATOL)
    assert result["main_cross_grid"]["coefficient_vector"] == [0.0] * 4
    assert result["all_solutions_verified"] is True


def test_mutated_branch_certificate_is_rejected():
    lift = np.array([[1.0, 0.3, 0.0, 0.0], [0.4, 0.9, 0.0, 0.0]])
    drag = np.array([[0.8, 0.0, -0.1, 0.0], [0.7, 0.0, 0.0, -0.1]])
    result = C.solve_cone_family(lift, drag, robust=False)
    altered = copy.deepcopy(result)
    altered["branch_certificates"][0]["coefficient_vector"][0] += 0.1
    with pytest.raises(ValueError, match="primal constraints|selected coefficients|KKT certificate|optimum"):
        C.verify_cone_family(lift, drag, altered, robust=False)


def test_nonfinite_or_wrong_dimension_gradient_is_rejected():
    with pytest.raises(ValueError, match="finite 2x4"):
        C.solve_cross_grid_proposals([[np.nan, 0, 0, 0], [0, 1, 0, 0]], np.zeros((2, 4)))
    with pytest.raises(ValueError, match="finite four-vector"):
        C.cosine_and_norm_ratio([1, 2, 3], [1, 2, 3, 4])


def test_zero_direction_norm_has_no_fabricated_norm_ratio():
    result = C.cosine_and_norm_ratio([0, 0, 0, 0], [1, 0, 0, 0])
    assert result["cosine"] is None
    assert result["flow32_over_flow24_l2_norm"] is None
