"""Solver-free arithmetic variants and an 80-digit Decimal mathematical reference.

The reference was written with access to the primary implementation: it is not
an independent third evaluator. Inputs are exact conversions of binary64
values; all reference derivation and gate comparisons precede JSON conversion.
No registered solver evidence is loaded and no comparison tolerance lives here.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import math
from typing import Any, Mapping, Sequence

import numpy as np


_PARAM_KEYS = ("sigma0_n", "rho", "tol_se", "tol_nested", "tol_model", "tol_hold", "k_mag")


def _inputs(epsilon_mm, s_n, params):
    epsilon = np.asarray(epsilon_mm, dtype=float)
    response = np.asarray(s_n, dtype=float)
    if epsilon.ndim != 1 or response.ndim != 1 or epsilon.shape != response.shape:
        raise ValueError("epsilon_mm and s_n must be equally sized one-dimensional arrays")
    if not np.all(np.isfinite(epsilon)) or not np.all(np.isfinite(response)):
        raise ValueError("epsilon_mm and s_n must be finite")
    if np.any(epsilon <= 0) or np.any(np.diff(epsilon) <= 0):
        raise ValueError("epsilon_mm must be positive and strictly ascending")
    p = dict(params)
    for key in _PARAM_KEYS:
        value = p.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (key == "sigma0_n" and value == 0):
            raise ValueError(f"{key} must be finite and {'positive' if key == 'sigma0_n' else 'nonnegative'}")
    drop = p.get("nested_drop")
    if isinstance(drop, bool) or not isinstance(drop, int) or drop < 1:
        raise ValueError("nested_drop must be a positive integer")
    return epsilon.tolist(), response.tolist(), p


def _scale(variant, reference):
    if variant == "N1":
        return reference * 0 + 1
    if variant == "N2":
        return reference * 0 + 1000
    if variant == "N3":
        return reference
    raise ValueError("variant must be N1, N2, or N3")


def _design(epsilon, model, scale):
    power = 3 if model == "A" else 2
    return [[e / scale, (e / scale)**power] for e in epsilon]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _gram(design, weights):
    return [[sum(w * x[i] * x[j] for x, w in zip(design, weights)) for j in range(2)] for i in range(2)]


def _inverse(matrix):
    a, b, d = matrix[0][0], matrix[0][1], matrix[1][1]
    determinant = a * d - b * b
    if determinant <= 0:
        raise ValueError("rank deficient design")
    return [[d / determinant, -b / determinant], [-b / determinant, a / determinant]]


def _decimal_spectrum(matrix):
    a, b, d = matrix[0][0], matrix[0][1], matrix[1][1]
    largest = ((a + d) + ((a - d)**2 + 4 * b * b).sqrt()) / 2
    determinant = a * d - b * b
    # det/lambda_max avoids loss of the smaller eigenvalue by subtraction.
    smallest = determinant / largest if largest > 0 else Decimal(0)
    return largest, smallest


def _json(value):
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, np.generic):
        value = value.item()
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _fit(epsilon, response, model, p, variant, reference, decimal=False):
    scale = _scale(variant, reference)
    power = 3 if model == "A" else 2
    mapping = [1 / scale, 1 / scale**power]
    if decimal:
        design = _design(epsilon, model, scale)
    else:
        native_epsilon = np.asarray(epsilon) / scale
        design = np.column_stack((native_epsilon, native_epsilon**power))
    result = dict(model=model, n_points=len(epsilon), dof=len(epsilon) - 2,
                  available=False, beta=None, covariance=None, beta_mm=None, cov_mm=None,
                  beta_native=None, cov_native=None, pilot_s_n=None, weights=None,
                  g_native=None, se_g_native=None, g_n_per_mm=None, g_n_per_m=None,
                  se_g_n_per_mm=None, se_g_n_per_m=None,
                  numeric=dict(variant=variant, epsilon_ref_mm=reference,
                               native_to_mm_diagonal=mapping, pilot_beta_native=None,
                               design_cond2=None, weighted_design_cond2=None,
                               design_norm2=None, weighted_design_norm2=None,
                               response_norm2=None, weighted_response_norm2=None,
                               covariance_norm2=None, covariance_max_eigenvalue=None,
                               pilot_design_cond2=None))
    if len(epsilon) < 2:
        return result
    try:
        if decimal:
            ones = [Decimal(1)] * len(epsilon)
            pilot_cov = _inverse(_gram(design, ones))
            rhs = [sum(x[i] * y for x, y in zip(design, response)) for i in range(2)]
            pilot_beta = [_dot(row, rhs) for row in pilot_cov]
            pilot = [_dot(row, pilot_beta) for row in design]
            weights = [1 / (p["sigma0_n"]**2 + (p["rho"] * y)**2) for y in pilot]
            covariance = _inverse(_gram(design, weights))
            rhs = [sum(w * x[i] * y for x, y, w in zip(design, response, weights)) for i in range(2)]
            beta = [_dot(row, rhs) for row in covariance]
            se = covariance[0][0].sqrt()
            high, low = _decimal_spectrum(_gram(design, ones))
            whigh, wlow = _decimal_spectrum(_gram(design, weights))
            cmax, _ = _decimal_spectrum(covariance)
            diagnostics = dict(design_cond2=(high / low).sqrt(),
                               weighted_design_cond2=(whigh / wlow).sqrt(),
                               design_norm2=high.sqrt(), weighted_design_norm2=whigh.sqrt(),
                               response_norm2=sum(y * y for y in response).sqrt(),
                               weighted_response_norm2=sum(w * y * y for y, w in zip(response, weights)).sqrt(),
                               covariance_norm2=cmax, covariance_max_eigenvalue=cmax)
        else:
            x = np.asarray(design)
            y = np.asarray(response)
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                pilot_beta, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
                if rank < 2:
                    return result
                pilot = x @ pilot_beta
                weights = 1 / (p["sigma0_n"]**2 + (p["rho"] * pilot)**2)
                xw = x * np.sqrt(weights[:, None])
                yw = y * np.sqrt(weights)
                beta, _, rank, _ = np.linalg.lstsq(xw, yw, rcond=None)
                if rank < 2:
                    return result
                covariance = np.linalg.inv(x.T @ (weights[:, None] * x))
                if not all(np.all(np.isfinite(v)) for v in (beta, covariance, pilot, weights)) or covariance[0, 0] < 0:
                    return result
                se = float(np.sqrt(covariance[0, 0]))
                diagnostics = dict(design_cond2=float(np.linalg.cond(x)),
                                   weighted_design_cond2=float(np.linalg.cond(xw)),
                                   design_norm2=float(np.linalg.norm(x, 2)), weighted_design_norm2=float(np.linalg.norm(xw, 2)),
                                   response_norm2=float(np.linalg.norm(y)), weighted_response_norm2=float(np.linalg.norm(yw)),
                                   covariance_norm2=float(np.linalg.norm(covariance, 2)),
                                   covariance_max_eigenvalue=float(np.linalg.eigvalsh(covariance)[-1]))
            pilot_beta, pilot, weights, beta, covariance = (v.tolist() for v in (pilot_beta, pilot, weights, beta, covariance))
        beta_mm = [b * d for b, d in zip(beta, mapping)]
        cov_mm = [[covariance[i][j] * mapping[i] * mapping[j] for j in range(2)] for i in range(2)]
        result.update(available=True, beta=beta_mm, covariance=cov_mm, beta_mm=beta_mm,
                      cov_mm=cov_mm, beta_native=beta, cov_native=covariance,
                      g_native=beta[0], se_g_native=se, pilot_s_n=pilot, weights=weights,
                      g_n_per_mm=beta_mm[0], g_n_per_m=beta_mm[0] * 1000,
                      se_g_n_per_mm=se * mapping[0], se_g_n_per_m=se * mapping[0] * 1000)
        result["numeric"].update(diagnostics, pilot_beta_native=pilot_beta,
                                  pilot_design_cond2=diagnostics["design_cond2"])
    except (ValueError, np.linalg.LinAlgError, FloatingPointError, OverflowError):
        return result
    return result


def _relative(numerator, denominator):
    return abs(numerator) / abs(denominator) if denominator != 0 else None


def _all_available(values):
    return False if False in values else (True if values and all(v is True for v in values) else None)


def _evaluate(epsilon, response, p, variant, reference, decimal=False):
    def fit(e, y, model):
        return _fit(e, y, model, p, variant, reference, decimal)

    n = len(epsilon)
    a, b = fit(epsilon, response, "A"), fit(epsilon, response, "B")
    g_a, g_b = a["g_native"], b["g_native"]
    nested = []
    for drop in range(1, min(max(3, p["nested_drop"]), n - 3) + 1):
        sa, sb = fit(epsilon[:-drop], response[:-drop], "A"), fit(epsilon[:-drop], response[:-drop], "B")
        shift = _relative(sa["g_native"] - g_a, g_a) if sa["available"] and a["available"] else None
        nested.append(dict(drop=drop, n_points=n - drop, model_a=sa, model_b=sb,
                           relative_shift_a=shift, used_for_sign=drop <= 3,
                           used_for_stability=drop <= p["nested_drop"]))
    sign_fits = [a, b] + [row[key] for row in nested if row["used_for_sign"] for key in ("model_a", "model_b")]
    signs = [(g > 0) - (g < 0) for g in (f["g_native"] for f in sign_fits) if g is not None]
    sign_pass = all(v == signs[0] and v != 0 for v in signs) if signs else None
    if len(signs) < len(sign_fits) and sign_pass:
        sign_pass = None
    relative_se = _relative(a["se_g_native"], g_a) if a["available"] else None
    model_difference = _relative(g_a - g_b, g_a) if a["available"] and b["available"] else None
    shifts = [row["relative_shift_a"] for row in nested if row["used_for_stability"]]
    maximum_shift = max(shifts) if shifts and all(v is not None for v in shifts) else None
    holdout = []
    for index in range(1, n - 1):
        selected = [j for j in range(n) if j != index]
        sub = fit([epsilon[j] for j in selected], [response[j] for j in selected], "A")
        row = dict(index=index, epsilon_mm=epsilon[index], s_obs_n=response[index], s_pred_n=None,
                   sigma_pred_n=None, error_n=None, limit_n=None, threshold_margin_n=None, passed=None, fit=sub)
        if sub["available"]:
            x = _design([epsilon[index]], "A", _scale(variant, reference))[0]
            if decimal:
                prediction = _dot(x, sub["beta_native"])
                fit_var = _dot(x, [_dot(crow, x) for crow in sub["cov_native"]])
            else:
                prediction = float(np.asarray(x) @ sub["beta_native"])
                fit_var = float(np.asarray(x) @ sub["cov_native"] @ np.asarray(x))
            variance = p["sigma0_n"]**2 + (p["rho"] * prediction)**2 + fit_var
            if variance >= 0:
                sigma = variance.sqrt() if decimal else math.sqrt(variance)
                error = abs(response[index] - prediction)
                limit = max(3 * sigma, p["tol_hold"] * abs(prediction))
                row.update(s_pred_n=prediction, sigma_pred_n=sigma, error_n=error, limit_n=limit,
                           threshold_margin_n=limit - error, passed=error <= limit)
        holdout.append(row)
    count = sum(abs(y) >= p["k_mag"] * p["sigma0_n"] for y in response)
    items = dict(
        sign=dict(passed=sign_pass, g_n_per_mm=[f["g_n_per_mm"] for f in sign_fits], signs=signs),
        relative_se=dict(passed=relative_se <= p["tol_se"] if relative_se is not None else None, value=relative_se),
        nested_stability=dict(passed=_all_available([v <= p["tol_nested"] if v is not None else None for v in shifts]), maximum_relative_shift=maximum_shift),
        model_difference=dict(passed=model_difference <= p["tol_model"] if model_difference is not None else None, value=model_difference),
        internal_holdout=dict(passed=_all_available([row["passed"] for row in holdout])),
        magnitude=dict(passed=count >= 4, point_count=count, threshold_n=p["k_mag"] * p["sigma0_n"], required_count=4))
    for name, value, tolerance in (("relative_se", relative_se, "tol_se"),
                                   ("nested_stability", maximum_shift, "tol_nested"),
                                   ("model_difference", model_difference, "tol_model")):
        items[name]["threshold_margin"] = p[tolerance] - value if value is not None else None
    margins = [row["threshold_margin_n"] for row in holdout]
    items["internal_holdout"]["minimum_threshold_margin_n"] = min(margins) if margins and all(v is not None for v in margins) else None
    first_five = [item["passed"] for key, item in items.items() if key != "magnitude"]
    verdict = "UNRESOLVED"
    if n >= 4 and n - 2 >= 1:
        if False in first_five:
            verdict = "FAIL"
        elif all(v is True for v in first_five) and items["magnitude"]["passed"]:
            verdict = "PASS"
    return dict(n_points=n, dof=n - 2, params=p, epsilon_mm=epsilon, s_n=response,
                q_n_per_m=[s / e * 1000 for e, s in zip(epsilon, response)],
                model_a=a, model_b=b, nested=nested, holdout=holdout, items=items, verdict=verdict,
                numeric=dict(variant=variant, epsilon_ref_mm=reference,
                             arithmetic="decimal_reference" if decimal else "binary64",
                             dimensionless_diagnostics="native_coefficients_before_presentation_conversion"))


def evaluate_variant(epsilon_mm: Sequence[float], s_n: Sequence[float], params: Mapping[str, Any],
                     variant: str = "N1", precision: int = 80) -> dict[str, Any]:
    """N1 mm, N2 SI, N3 x=epsilon/max(full ladder), one pilot then WLS.

    ``precision`` is accepted for a common caller interface; binary64 precision
    is fixed. beta/covariance and beta_mm/cov_mm always use canonical mm units.
    """
    epsilon, response, p = _inputs(epsilon_mm, s_n, params)
    reference = max(epsilon, default=1.0)
    _scale(variant, reference)
    return _json(_evaluate(epsilon, response, p, variant, reference))


def reference_series(epsilon_mm: Sequence[float], s_n: Sequence[float], params: Mapping[str, Any],
                     precision: int = 80, variant: str = "N1", *, decimal_output: bool = False) -> dict[str, Any]:
    """Decimal OLS/WLS normal systems, inverse and sqrt, exact binary64 input.

    This is a mathematical high-precision reference, not a separate claim of
    implementation independence. Reference decisions use Decimal throughout.
    ``decimal_output=True`` preserves reference values for exact forward-error
    subtraction against binary64 results before the caller serializes JSON.
    """
    if isinstance(precision, bool) or not isinstance(precision, int) or precision < 40:
        raise ValueError("reference precision must be an integer of at least 40 digits")
    epsilon, response, p = _inputs(epsilon_mm, s_n, params)
    epsilon = [Decimal.from_float(e) for e in epsilon]
    response = [Decimal.from_float(s) for s in response]
    p = {key: (Decimal.from_float(float(value)) if key in _PARAM_KEYS else value) for key, value in p.items()}
    reference = max(epsilon, default=Decimal(1))
    _scale(variant, reference)
    with localcontext() as context:
        context.prec = precision
        result = _evaluate(epsilon, response, p, variant, reference, decimal=True)
        result["numeric"].update(precision_decimal_digits=precision, input_conversion="exact_binary64",
                                 independence="not_independent_reference_author_had_primary_access")
        return result if decimal_output else _json(result)


def fit_variant(epsilon_mm, s_n, model, params, variant="N1", epsilon_ref_mm=None):
    """Fit a subset; pass the full-ladder epsilon_ref_mm to retain N3 scaling."""
    if model not in ("A", "B"):
        raise ValueError("model must be A or B")
    epsilon, response, p = _inputs(epsilon_mm, s_n, params)
    reference = max(epsilon, default=1.0) if epsilon_ref_mm is None else float(epsilon_ref_mm)
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("epsilon_ref_mm must be finite and positive")
    _scale(variant, reference)
    return _json(_fit(epsilon, response, model, p, variant, reference))
