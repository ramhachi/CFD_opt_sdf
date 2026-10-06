"""Solver-free tests; no registered evidence or FD-08 implementation imports."""

import json

import numpy as np
import pytest

from cfd_sdf.fd08_v2_gate import (
    classify_result, evaluate_series, fit_model, load_params, n_per_mm_to_n_per_m,
)


def test_linear_series_units_and_all_six_items():
    epsilon = np.geomspace(0.5, 5, 6)
    result = evaluate_series(epsilon, -0.17 * epsilon / 1000)
    assert result["verdict"] == "PASS"
    assert len(result["items"]) == 6
    assert all(item["passed"] is True for item in result["items"].values())
    assert result["model_a"]["g_n_per_m"] == pytest.approx(-0.17)
    assert result["q_n_per_m"] == pytest.approx([-0.17] * 6)
    assert n_per_mm_to_n_per_m(-0.00017) == pytest.approx(-0.17)
    json.dumps(result, sort_keys=True, allow_nan=False)


@pytest.mark.parametrize("model,power", [("A", 3), ("B", 2)])
def test_wls_uses_one_subset_pilot_and_nominal_covariance(model, power):
    epsilon = np.array([0.5, 1, 2, 3, 5.0])
    response = np.array([-0.00008, -0.00016, -0.00038, -0.00064, -0.0012])
    params = load_params()
    design = np.column_stack((epsilon, epsilon**power))
    pilot_beta = np.linalg.solve(design.T @ design, design.T @ response)
    pilot = design @ pilot_beta
    weights = 1 / (params["sigma0_n"]**2 + (params["rho"] * pilot)**2)
    covariance = np.linalg.inv(design.T @ (weights[:, None] * design))
    beta = covariance @ (design.T @ (weights * response))
    result = fit_model(epsilon, response, model, params)
    np.testing.assert_allclose(result["pilot_s_n"], pilot, rtol=1e-12)
    np.testing.assert_allclose(result["weights"], weights, rtol=1e-12)
    np.testing.assert_allclose(result["beta"], beta, rtol=1e-12)
    np.testing.assert_allclose(result["covariance"], covariance, rtol=1e-12)
    assert result["se_g_n_per_mm"] == pytest.approx(np.sqrt(covariance[0, 0]))


def test_nested_and_holdout_recompute_pilots_and_predictive_variance():
    epsilon = np.geomspace(0.3, 5, 8)
    response = (-0.104 - 0.00104 * epsilon**2) * epsilon / 1000
    response[3] += 2e-6
    params = load_params()
    result = evaluate_series(epsilon, response, params)
    assert [row["drop"] for row in result["nested"]] == [1, 2, 3]
    assert [row["used_for_stability"] for row in result["nested"]] == [True, True, False]
    assert all(row["used_for_sign"] for row in result["nested"])
    for row in result["nested"]:
        subset_fit = fit_model(epsilon[:-row["drop"]], response[:-row["drop"]], "A", params)
        assert row["model_a"] == subset_fit
    assert len(result["holdout"]) == 6
    for row in result["holdout"]:
        selected = np.arange(len(epsilon)) != row["index"]
        subset_fit = fit_model(epsilon[selected], response[selected], "A", params)
        assert row["fit"] == subset_fit
        x = np.array([row["epsilon_mm"], row["epsilon_mm"]**3])
        prediction = x @ subset_fit["beta"]
        sigma = np.sqrt(params["sigma0_n"]**2 + (params["rho"] * prediction)**2 + x @ subset_fit["covariance"] @ x)
        assert row["s_pred_n"] == pytest.approx(prediction)
        assert row["sigma_pred_n"] == pytest.approx(sigma)
        assert row["limit_n"] == pytest.approx(max(3 * sigma, params["tol_hold"] * abs(prediction)))


def test_magnitude_only_is_unresolved_but_other_failure_wins():
    epsilon = np.geomspace(0.5, 5, 6)
    response = -0.17 * epsilon / 1000
    params = {**load_params(), "k_mag": 500}
    unresolved = evaluate_series(epsilon, response, params)
    assert unresolved["verdict"] == "UNRESOLVED"
    assert unresolved["items"]["magnitude"]["point_count"] == 0
    failed = evaluate_series(epsilon, response, {**params, "tol_se": 0})
    assert failed["verdict"] == "FAIL"
    assert failed["items"]["relative_se"]["passed"] is False


def test_short_or_uncomputable_input_is_unresolved_and_json_finite():
    for epsilon, response in (([], []), ([1.0], [0.0]), ([1, 2, 3], [0.0] * 3)):
        result = evaluate_series(epsilon, response)
        assert result["verdict"] == "UNRESOLVED"
        json.dumps(result, sort_keys=True, allow_nan=False)
    result = evaluate_series([1, 2, 3, 4], [0.0] * 4)
    assert result["verdict"] == "FAIL"  # zero cannot establish a common nonzero sign
    assert result["model_a"]["weights"] == pytest.approx([1 / load_params()["sigma0_n"]**2] * 4)


def test_rethreshold_equals_refit_and_cannot_change_noise_or_subsets():
    epsilon = np.geomspace(0.5, 5, 6)
    response = (-0.104 - 0.00104 * epsilon**2) * epsilon / 1000
    result = evaluate_series(epsilon, response)
    for tolerance in (0.05, 0.10, 0.15, 0.20):
        params = {**load_params(), **dict.fromkeys(("tol_se", "tol_nested", "tol_model", "tol_hold"), tolerance)}
        assert classify_result(result, params) == evaluate_series(epsilon, response, params)["verdict"]
    with pytest.raises(ValueError, match="without refitting"):
        classify_result(result, {**load_params(), "rho": 0.1})


@pytest.mark.parametrize("epsilon,response", [([2, 1], [0, 0]), ([1, 1], [0, 0]), ([0, 1], [0, 0]), ([1], [1, 2]), ([float("nan")], [0]), ([[1]], [[0]])])
def test_rejects_invalid_arrays(epsilon, response):
    with pytest.raises(ValueError):
        evaluate_series(epsilon, response)


@pytest.mark.parametrize("key,value", [("sigma0_n", 0), ("rho", -1), ("tol_se", float("nan")), ("nested_drop", 2.0), ("nested_drop", True)])
def test_rejects_invalid_parameters(key, value):
    with pytest.raises(ValueError):
        evaluate_series([1, 2, 3, 4], [1, 2, 3, 4], {**load_params(), key: value})
