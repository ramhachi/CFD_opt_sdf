"""Arithmetic-contract checks; synthetic inputs only, no solver artifacts."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "fd08_numeric_contract", Path(__file__).resolve().parents[1] / "scripts/analyze_fd08_v2_numeric_contract.py")
numeric = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(numeric)

PARAMS = dict(sigma0_n=3e-6, rho=0.05, tol_se=0.1, tol_nested=0.15,
              nested_drop=2, tol_model=0.15, tol_hold=0.15, k_mag=5)


def _series():
    epsilon = np.geomspace(0.3, 5, 8)
    response = (-0.104 - 0.00104 * epsilon**2) * epsilon / 1000
    response[3] += 2e-6
    return epsilon, response


@pytest.mark.parametrize("variant", ["N1", "N2", "N3"])
def test_exact_polynomial_and_canonical_unit_conversion(variant):
    epsilon = np.array([0.5, 1, 1.5, 2, 3, 5.0])
    response = -0.000104 * epsilon - 0.00000104 * epsilon**3
    result = numeric.evaluate_variant(epsilon, response, PARAMS, variant)
    a = result["model_a"]
    np.testing.assert_allclose(a["beta_mm"], [-0.000104, -0.00000104], rtol=1e-10)
    assert a["beta"] == a["beta_mm"]
    assert a["covariance"] == a["cov_mm"]
    assert a["g_n_per_m"] == pytest.approx(-0.104, rel=1e-10)
    assert a["se_g_n_per_m"] == a["se_g_n_per_mm"] * 1000
    assert result["verdict"] == "PASS"
    assert all(row["error_n"] < 1e-16 for row in result["holdout"])
    json.dumps(result, allow_nan=False)


def test_variants_agree_on_covariance_and_nonzero_diagnostics_without_verdict_change():
    epsilon, response = _series()
    reference = numeric.reference_series(epsilon, response, PARAMS)
    for variant in ("N1", "N2", "N3"):
        result = numeric.evaluate_variant(epsilon, response, PARAMS, variant)
        assert result["verdict"] == reference["verdict"]
        assert {key: v["passed"] for key, v in result["items"].items()} == {
            key: v["passed"] for key, v in reference["items"].items()}
        for model in ("model_a", "model_b"):
            np.testing.assert_allclose(result[model]["beta"], reference[model]["beta"], rtol=1e-10)
            np.testing.assert_allclose(result[model]["covariance"], reference[model]["covariance"], rtol=1e-10)
            np.testing.assert_allclose(result[model]["weights"], reference[model]["weights"], rtol=1e-10)
        for item in ("relative_se", "model_difference"):
            assert result["items"][item]["value"] == pytest.approx(reference["items"][item]["value"], rel=1e-10)
        for actual, expected in zip(result["nested"], reference["nested"]):
            assert actual["relative_shift_a"] == pytest.approx(expected["relative_shift_a"], rel=1e-9, abs=1e-14)
        for actual, expected in zip(result["holdout"], reference["holdout"]):
            for key in ("s_pred_n", "sigma_pred_n", "error_n", "limit_n"):
                assert actual[key] == pytest.approx(expected[key], rel=1e-10, abs=1e-18)


@pytest.mark.parametrize("variant", ["N1", "N2", "N3"])
def test_subset_pilots_and_n3_reference_remain_fixed_to_full_ladder(variant):
    epsilon, response = _series()
    result = numeric.evaluate_variant(epsilon, response, PARAMS, variant)
    reference = float(max(epsilon))
    for row in result["nested"]:
        expected = numeric.fit_variant(epsilon[:-row["drop"]], response[:-row["drop"]], "A",
                                       PARAMS, variant, epsilon_ref_mm=reference)
        assert row["model_a"] == expected
        assert expected["numeric"]["epsilon_ref_mm"] == reference
    for row in result["holdout"]:
        selected = np.arange(len(epsilon)) != row["index"]
        expected = numeric.fit_variant(epsilon[selected], response[selected], "A", PARAMS,
                                       variant, epsilon_ref_mm=reference)
        assert row["fit"] == expected
        assert expected["pilot_s_n"] != [result["model_a"]["pilot_s_n"][i] for i in np.flatnonzero(selected)]
        mapping = np.asarray(expected["numeric"]["native_to_mm_diagonal"])
        np.testing.assert_allclose(expected["beta_mm"], mapping * expected["beta_native"], rtol=1e-14)
        np.testing.assert_allclose(expected["cov_mm"], mapping[:, None] * expected["cov_native"] * mapping[None, :], rtol=1e-14)


@pytest.mark.parametrize("variant", ["N1", "N2", "N3"])
def test_condition_and_norm_diagnostics_use_native_matrix(variant):
    epsilon, response = _series()
    result = numeric.evaluate_variant(epsilon, response, PARAMS, variant)
    for name, power in (("model_a", 3), ("model_b", 2)):
        fit = result[name]
        scale = {"N1": 1, "N2": 1000, "N3": max(epsilon)}[variant]
        native_epsilon = epsilon / scale
        x = np.column_stack((native_epsilon, native_epsilon**power))
        xw = x * np.sqrt(np.asarray(fit["weights"])[:, None])
        covariance = np.linalg.inv(x.T @ (np.asarray(fit["weights"])[:, None] * x))
        np.testing.assert_allclose(fit["cov_native"], covariance, rtol=1e-12)
        assert fit["numeric"]["design_cond2"] == pytest.approx(np.linalg.cond(x))
        assert fit["numeric"]["weighted_design_cond2"] == pytest.approx(np.linalg.cond(xw))
        assert fit["numeric"]["design_norm2"] == pytest.approx(np.linalg.norm(x, 2))
        assert fit["numeric"]["covariance_max_eigenvalue"] == pytest.approx(np.linalg.eigvalsh(covariance)[-1])


def test_decimal_reference_converges_and_is_unit_invariant():
    epsilon, response = _series()
    base = numeric.reference_series(epsilon, response, PARAMS, precision=80)
    for precision, variant in ((120, "N1"), (80, "N2"), (80, "N3")):
        reference = numeric.reference_series(epsilon, response, PARAMS, precision=precision, variant=variant)
        assert reference["verdict"] == base["verdict"]
        for model in ("model_a", "model_b"):
            np.testing.assert_allclose(reference[model]["beta_mm"], base[model]["beta_mm"], rtol=1e-14)
            np.testing.assert_allclose(reference[model]["cov_mm"], base[model]["cov_mm"], rtol=1e-14)
        assert reference["numeric"]["input_conversion"] == "exact_binary64"
        json.dumps(reference, allow_nan=False)


def test_magnitude_only_unresolved_and_other_failure_precedes_magnitude():
    epsilon = np.geomspace(0.5, 5, 6)
    response = -0.17 * epsilon / 1000
    for evaluate in (numeric.evaluate_variant, numeric.reference_series):
        assert evaluate(epsilon, response, {**PARAMS, "k_mag": 500})["verdict"] == "UNRESOLVED"
        assert evaluate(epsilon, response, {**PARAMS, "k_mag": 500, "tol_se": 0})["verdict"] == "FAIL"


@pytest.mark.parametrize("evaluate", [numeric.evaluate_variant, numeric.reference_series])
def test_short_zero_and_invalid_input_are_handled(evaluate):
    for epsilon, response in (([], []), ([1], [0]), ([1, 2, 3], [0, 0, 0])):
        result = evaluate(epsilon, response, PARAMS)
        assert result["verdict"] == "UNRESOLVED"
        json.dumps(result, allow_nan=False)
    assert evaluate([1, 2, 3, 4], [0] * 4, PARAMS)["verdict"] == "FAIL"
    with pytest.raises(ValueError):
        evaluate([2, 1], [1, 1], PARAMS)
    with pytest.raises(ValueError):
        evaluate([1, 2], [1, 1], {**PARAMS, "sigma0_n": 0})
    with pytest.raises(ValueError):
        evaluate([1, 2], [1, 1], {**PARAMS, "nested_drop": True})


def test_reference_can_preserve_decimal_for_forward_error_subtraction():
    epsilon, response = _series()
    result = numeric.reference_series(epsilon, response, PARAMS, decimal_output=True)
    assert isinstance(result["model_a"]["g_n_per_mm"], Decimal)
    assert isinstance(result["model_a"]["covariance"][0][0], Decimal)
    assert isinstance(result["nested"][0]["relative_shift_a"], Decimal)
    assert isinstance(result["holdout"][0]["sigma_pred_n"], Decimal)
    assert result["epsilon_mm"][0] == Decimal.from_float(float(epsilon[0]))
    assert result["model_a"]["g_n_per_mm"] != Decimal.from_float(float(result["model_a"]["g_n_per_mm"]))


def test_decimal_reference_80_120_digit_convergence_of_raw_metrics():
    from decimal import localcontext

    epsilon, response = _series()
    low = numeric.reference_series(epsilon, response, PARAMS, precision=80, decimal_output=True)
    high = numeric.reference_series(epsilon, response, PARAMS, precision=120, decimal_output=True)

    def leaves(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key != "numeric":
                    yield from leaves(item)
        elif isinstance(value, list):
            for item in value:
                yield from leaves(item)
        elif isinstance(value, Decimal):
            yield value

    assert low["verdict"] == high["verdict"]
    with localcontext() as context:
        context.prec = 120
        for a, b in zip(leaves(low), leaves(high)):
            assert abs(a - b) <= Decimal("1e-70") * max(Decimal(1), abs(b))


_FORWARD_SPEC = importlib.util.spec_from_file_location(
    "fd08_forward_error", Path(__file__).resolve().parents[1] / "scripts/fd08_v2_forward_error.py")
forward = importlib.util.module_from_spec(_FORWARD_SPEC)
_FORWARD_SPEC.loader.exec_module(forward)


@pytest.mark.parametrize("variant", ["N1", "N2", "N3"])
def test_conditional_forward_envelopes_cover_synthetic_arithmetic(variant):
    from decimal import localcontext

    epsilon, response = _series()
    result = numeric.evaluate_variant(epsilon, response, PARAMS, variant)
    reference = numeric.reference_series(epsilon, response, PARAMS, variant=variant, decimal_output=True)
    envelope = forward.bound_series(epsilon, response, PARAMS, variant=variant, decimal_output=True)
    assert envelope["diagnostics"]["valid"] is True
    with localcontext() as context:
        context.prec = 120
        for model in ("model_a", "model_b"):
            for field in ("beta", "covariance", "pilot_s_n", "weights"):
                actual = np.asarray(result[model][field]).ravel()
                exact = np.asarray(reference[model][field], dtype=object).ravel()
                bound = np.asarray(envelope["bounds"][model][field], dtype=object).ravel()
                for a, r, b in zip(actual, exact, bound):
                    assert abs(Decimal.from_float(float(a)) - r) <= b
        for name in ("relative_se", "model_difference"):
            error = abs(Decimal.from_float(result["items"][name]["value"]) - reference["items"][name]["value"])
            assert error <= envelope["bounds"]["items"][name]["value"]
        for index, row in enumerate(result["holdout"]):
            for field in ("s_pred_n", "sigma_pred_n", "error_n", "limit_n"):
                assert abs(Decimal.from_float(row[field]) - reference["holdout"][index][field]) <= envelope["bounds"]["holdout"][index][field]


def test_bound_raw_decimals_converge_80_120_and_display_path_adds_rounding():
    from decimal import localcontext

    epsilon, response = _series()
    low = forward.bound_series(epsilon, response, PARAMS, precision=80, decimal_output=True)
    high = forward.bound_series(epsilon, response, PARAMS, precision=120, decimal_output=True)
    displayed = forward.bound_series(epsilon, response, PARAMS, presentation_ratios=True, decimal_output=True)

    def leaves(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from leaves(item)
        elif isinstance(value, list):
            for item in value:
                yield from leaves(item)
        elif isinstance(value, Decimal):
            yield value

    with localcontext() as context:
        context.prec = 120
        for a, b in zip(leaves(low), leaves(high)):
            assert abs(a - b) <= Decimal("1e-60") * max(abs(b), Decimal("1e-30"))
    assert low["diagnostics"]["valid"] == high["diagnostics"]["valid"]
    assert displayed["bounds"]["items"]["model_difference"]["value"] >= low["bounds"]["items"]["model_difference"]["value"]
    assert set(low["margins"]) >= {"relative_se", "nested_stability", "model_difference", "holdout[0]", "magnitude[0]", "sign[full_A]"}


def test_forward_invalid_perturbation_radius_and_zero_ratio_are_unavailable():
    d = Decimal
    invalid = forward._linear_envelope([[d(1), d(0)], [d(0), d(1)]], [d(1), d(1)],
                                      [d(1), d(1)], [[d(1), d(0)], [d(0), d(1)]],
                                      [[d(2), d(2)], [d(2), d(2)]], [d(2), d(2)])
    assert invalid["valid"] is False
    assert invalid["radius"] >= 1
    assert forward._difference_ratio_bound(d(0), d(0), d(0), d(0)) is None
    zero = forward.bound_series([0.5, 1, 1.5, 2, 3, 5], [0] * 6, PARAMS)
    assert zero["diagnostics"]["ratio_bounds_valid"] is False
    assert zero["bounds"]["items"]["model_difference"]["value"] is None
