#!/usr/bin/env python3
"""Independent FD08v2 evaluator; implemented from spec.md, without helpers.

The sign check uses drops 1..3 irrespective of nested_drop. Stability uses
drops 1..nested_drop; both retain at least three points. Small samples n<4
are UNRESOLVED even when a diagnostic item fails. Undefined relative ratios
are represented by null, never NaN or Infinity. Zero slopes fail the sign
check, since they have no positive/negative sign.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np


DEFAULTS = {
    "sigma0_n": 3e-6,
    "rho": 0.05,
    "tol_se": 0.10,
    "tol_nested": 0.15,
    "nested_drop": 2,
    "tol_model": 0.15,
    "tol_hold": 0.15,
    "k_mag": 5,
}


def to_n_per_m(value):
    """Convert a derivative in N/mm to N/m in one place."""
    return float(value) * 1e3


def design(epsilon_mm, model):
    e = np.asarray(epsilon_mm, dtype=float)
    curvature = e ** 3 if model == "A" else e * np.abs(e)
    return np.column_stack((e, curvature))


def fit(epsilon_mm, response_n, model, params):
    """OLS pilot followed by exactly one nominal-noise WLS fit."""
    x = design(epsilon_mm, model)
    y = np.asarray(response_n, dtype=float)
    pilot_coefficients, _, pilot_rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if pilot_rank != 2:
        return None
    pilot_predictions = x @ pilot_coefficients
    noise_variance = params["sigma0_n"] ** 2 + (params["rho"] * pilot_predictions) ** 2
    weights = 1.0 / noise_variance
    weighted_x = x * np.sqrt(weights)[:, None]
    weighted_y = y * np.sqrt(weights)
    coefficients, _, rank, _ = np.linalg.lstsq(weighted_x, weighted_y, rcond=None)
    if rank != 2:
        return None
    covariance = np.linalg.inv(x.T @ (weights[:, None] * x))
    if not np.all(np.isfinite(covariance)) or covariance[0, 0] < 0:
        return None
    predictions = x @ coefficients
    standard_error = math.sqrt(float(covariance[0, 0]))
    return {
        "model": model,
        "n": len(y),
        "dof": len(y) - 2,
        "coefficients_mm": coefficients.tolist(),
        "g_n_per_m": to_n_per_m(coefficients[0]),
        "se_g_n_per_m": to_n_per_m(standard_error),
        "covariance_mm": covariance.tolist(),
        "pilot_coefficients_mm": pilot_coefficients.tolist(),
        "pilot_predictions_n": pilot_predictions.tolist(),
        "weights_n_inverse_squared": weights.tolist(),
        "predictions_n": predictions.tolist(),
        "residuals_n": (y - predictions).tolist(),
    }


def relative(value, denominator):
    return abs(float(value)) / abs(float(denominator)) if denominator != 0 else None


def item(value, passed, **details):
    return {"value": value, "pass": passed, "calculable": passed is not None, **details}


def evaluate(epsilon_mm, response_n, parameters=None):
    params = dict(DEFAULTS)
    if parameters:
        unknown = set(parameters) - set(params)
        if unknown:
            raise ValueError("Unknown parameters: " + ", ".join(sorted(unknown)))
        params.update(parameters)
    e = np.asarray(epsilon_mm, dtype=float)
    s = np.asarray(response_n, dtype=float)
    if e.ndim != 1 or s.ndim != 1 or len(e) != len(s):
        raise ValueError("epsilon_mm and response_n must be equally sized vectors")
    if not np.all(np.isfinite(e)) or not np.all(np.isfinite(s)):
        raise ValueError("Input values must be finite")
    if len(e) > 1 and not np.all(np.diff(e) > 0):
        raise ValueError("epsilon_mm must be strictly increasing")
    if not all(math.isfinite(float(v)) for v in params.values()):
        raise ValueError("Parameters must be finite")
    if params["sigma0_n"] <= 0 or params["rho"] < 0:
        raise ValueError("sigma0_n must be positive and rho nonnegative")
    for name in ("tol_se", "tol_nested", "tol_model", "tol_hold", "k_mag"):
        if params[name] < 0:
            raise ValueError(name + " must be nonnegative")
    if int(params["nested_drop"]) != params["nested_drop"] or params["nested_drop"] < 0:
        raise ValueError("nested_drop must be a nonnegative integer")
    params["nested_drop"] = int(params["nested_drop"])
    n = len(e)
    full = {model: fit(e, s, model, params) for model in ("A", "B")}
    nested = []
    for drop in range(1, max(3, params["nested_drop"]) + 1):
        if n - drop < 3:
            continue
        fits = {model: fit(e[:-drop], s[:-drop], model, params) for model in ("A", "B")}
        difference = None
        if fits["A"] is not None and full["A"] is not None:
            difference = relative(fits["A"]["g_n_per_m"] - full["A"]["g_n_per_m"], full["A"]["g_n_per_m"])
        nested.append({
            "drop": drop,
            "n": n - drop,
            "used_for_sign": drop <= 3,
            "used_for_stability": drop <= params["nested_drop"],
            "fits": fits,
            "relative_g_A_change": difference,
        })
    sign_fits = [full["A"], full["B"]]
    for subset in nested:
        if subset["used_for_sign"]:
            sign_fits.extend([subset["fits"]["A"], subset["fits"]["B"]])
    slopes = [f["g_n_per_m"] for f in sign_fits if f is not None]
    sign_pass = None
    if slopes:
        sign_pass = bool(all(g > 0 for g in slopes) or all(g < 0 for g in slopes))
        if len(slopes) != len(sign_fits) and sign_pass:
            sign_pass = None
    full_a, full_b = full["A"], full["B"]
    se_ratio = relative(full_a["se_g_n_per_m"], full_a["g_n_per_m"]) if full_a is not None else None
    model_ratio = relative(full_a["g_n_per_m"] - full_b["g_n_per_m"], full_a["g_n_per_m"]) if full_a is not None and full_b is not None else None
    stability = [row["relative_g_A_change"] for row in nested if row["used_for_stability"]]
    stability_max = max(stability) if stability and all(v is not None for v in stability) else None
    if params["nested_drop"] == 0 and full_a is not None:
        stability_max = 0.0
    holdouts = []
    for index in range(1, n - 1):
        mask = np.arange(n) != index
        fitted = fit(e[mask], s[mask], "A", params)
        if fitted is None:
            holdouts.append({"index": index, "epsilon_mm": float(e[index]), "fit": None, "pass": None})
            continue
        row = design([e[index]], "A")[0]
        prediction = float(row @ np.asarray(fitted["coefficients_mm"]))
        propagated_variance = float(row @ np.asarray(fitted["covariance_mm"]) @ row)
        sigma_prediction = math.sqrt(params["sigma0_n"] ** 2 + (params["rho"] * prediction) ** 2 + propagated_variance)
        error = abs(float(s[index]) - prediction)
        tolerance = max(3 * sigma_prediction, params["tol_hold"] * abs(prediction))
        holdouts.append({
            "index": index,
            "epsilon_mm": float(e[index]),
            "observed_n": float(s[index]),
            "prediction_n": prediction,
            "signed_error_n": float(s[index]) - prediction,
            "absolute_error_n": error,
            "propagated_variance_n_squared": propagated_variance,
            "sigma_prediction_n": sigma_prediction,
            "tolerance_n": tolerance,
            "error_over_tolerance": error / tolerance,
            "pass": bool(error <= tolerance),
            "fit": fitted,
        })
    hold_pass = None
    if any(row["pass"] is False for row in holdouts):
        hold_pass = False
    elif holdouts and all(row["pass"] is True for row in holdouts):
        hold_pass = True
    hold_ratios = [row["error_over_tolerance"] for row in holdouts if row["fit"] is not None]
    magnitude_threshold = params["k_mag"] * params["sigma0_n"]
    magnitude_count = int(np.count_nonzero(np.abs(s) >= magnitude_threshold))
    checks = {
        "sign": item(slopes, sign_pass, required_fit_count=len(sign_fits)),
        "relative_se": item(se_ratio, bool(se_ratio <= params["tol_se"]) if se_ratio is not None else None, threshold=params["tol_se"]),
        "nested_stability": item(stability_max, bool(stability_max <= params["tol_nested"]) if stability_max is not None else None, threshold=params["tol_nested"]),
        "model_difference": item(model_ratio, bool(model_ratio <= params["tol_model"]) if model_ratio is not None else None, threshold=params["tol_model"]),
        "holdout": item(max(hold_ratios) if hold_ratios else None, hold_pass, point_count=len(holdouts)),
        "magnitude": item(magnitude_count, bool(magnitude_count >= 4), minimum_count=4, threshold_n=magnitude_threshold),
    }
    ordinary = [checks[key] for key in checks if key != "magnitude"]
    if n < 4 or n - 2 < 1:
        verdict, reason = "UNRESOLVED", "insufficient_sample_count"
    elif any(check["pass"] is False for check in ordinary):
        verdict, reason = "FAIL", "at_least_one_evaluable_non_magnitude_check_failed"
    elif not all(check["pass"] is True for check in ordinary):
        verdict, reason = "UNRESOLVED", "incomplete_computability"
    elif checks["magnitude"]["pass"] is False:
        verdict, reason = "UNRESOLVED", "magnitude_only_failed"
    else:
        verdict, reason = "PASS", "all_six_checks_passed"
    return {"n": n, "dof": n - 2, "params": params, "full_fits": full, "nested": nested,
            "holdouts": holdouts, "items": checks, "verdict": verdict, "verdict_reason": reason}


def rounded(value):
    """Serialize every float with at most 12 significant decimal digits."""
    if isinstance(value, dict):
        return {key: rounded(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(val) for val in value]
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            raise ValueError("Nonfinite output is forbidden")
        return float(format(float(value), ".12g"))
    return value


def evaluate_document(document):
    shared_params = document.get("params", {}) if isinstance(document, dict) else {}
    if isinstance(document, list):
        cases = document
    elif "cases" in document:
        cases = document["cases"]
    elif "fixtures" in document:
        cases = document["fixtures"]
    elif "inputs" in document:
        cases = document["inputs"]
    else:
        cases = [document]
    if isinstance(cases, dict):
        cases = [{"id": key, **val} for key, val in cases.items()]
    results = []
    for index, case in enumerate(cases):
        epsilon = case.get("epsilon_mm", case.get("eps_mm", case.get("epsilons_mm")))
        response = case.get("response_n", case.get("s_n", case.get("S_n")))
        if epsilon is None or response is None:
            raise ValueError("Each case requires epsilon_mm and response_n")
        parameters = {**shared_params, **case.get("params", {})}
        result = evaluate(epsilon, response, parameters)
        results.append({"id": case.get("id", case.get("name", str(index))), **result})
    return {"provenance": "independent_blind_spec_only", "sign_subset_drops": [1, 2, 3],
            "rounding_significant_digits": 12, "results": results}


def self_test():
    assert to_n_per_m(0.001) == 1.0
    assert to_n_per_m(-0.00017) == -0.17
    e = np.geomspace(0.5, 5.0, 6)
    pure_linear = evaluate(e, -0.17 * e / 1000)
    assert pure_linear["verdict"] == "PASS"
    assert abs(pure_linear["full_fits"]["A"]["g_n_per_m"] + 0.17) < 1e-12
    assert [row["drop"] for row in pure_linear["nested"] if row["used_for_sign"]] == [1, 2, 3]
    assert [row["drop"] for row in pure_linear["nested"] if row["used_for_stability"]] == [1, 2]
    exact_a = evaluate(e, (-0.104 - 0.00104 * e ** 2) * e / 1000)
    assert abs(exact_a["full_fits"]["A"]["g_n_per_m"] + 0.104) < 1e-12
    assert len(exact_a["holdouts"]) == 4
    assert all(row["absolute_error_n"] < 1e-15 for row in exact_a["holdouts"])
    assert evaluate(e[:3], -0.17 * e[:3] / 1000)["verdict"] == "UNRESOLVED"
    assert evaluate(e, np.zeros_like(e))["verdict"] == "FAIL"
    assert evaluate(e, -1e-5 * e / 1000)["verdict"] != "PASS"
    json.dumps(rounded(exact_a), sort_keys=True, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON fixture input")
    parser.add_argument("--output", help="JSON result file; otherwise stdout")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("BLIND_SELF_TEST_OK")
    if args.input:
        document = json.loads(Path(args.input).read_text())
        serialized = json.dumps(rounded(evaluate_document(document)), sort_keys=True, allow_nan=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(serialized)
        else:
            print(serialized, end="")
    elif not args.self_test:
        parser.error("provide input or --self-test")


if __name__ == "__main__":
    main()
