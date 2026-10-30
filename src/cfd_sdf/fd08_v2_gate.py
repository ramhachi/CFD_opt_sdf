"""Unregistered, solver-free FD-08 v2 gate; epsilon in mm, response in N.

The provisional parameters are design options, not approved R6 criteria.
This module deliberately has no coupling to the registered FD-08 code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


def n_per_mm_to_n_per_m(value: float) -> float:
    """Convert a response slope (including q=S/epsilon) to N/m."""
    return float(value) * 1e3


def _validate_params(params: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(params)
    for key in ("sigma0_n", "rho", "tol_se", "tol_nested", "tol_model", "tol_hold", "k_mag"):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a finite number")
        if not np.isfinite(value) or value < 0 or (key == "sigma0_n" and value == 0):
            raise ValueError(f"{key} must be finite and {'positive' if key == 'sigma0_n' else 'nonnegative'}")
    drop = result.get("nested_drop")
    if isinstance(drop, bool) or not isinstance(drop, int) or drop < 1:
        raise ValueError("nested_drop must be a positive integer")
    return result


def load_params(path: str | Path | None = None) -> dict[str, Any]:
    """Read and validate the provisional parameter JSON."""
    source = Path(path) if path is not None else Path(__file__).with_name("fd08_v2_gate_params.json")
    return _validate_params(json.loads(source.read_text(encoding="utf-8")))


def _arrays(epsilon_mm: Sequence[float], s_n: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    epsilon = np.asarray(epsilon_mm, dtype=float)
    response = np.asarray(s_n, dtype=float)
    if epsilon.ndim != 1 or response.ndim != 1 or epsilon.shape != response.shape:
        raise ValueError("epsilon_mm and s_n must be equally sized one-dimensional arrays")
    if not np.all(np.isfinite(epsilon)) or not np.all(np.isfinite(response)):
        raise ValueError("epsilon_mm and s_n must be finite")
    if np.any(epsilon <= 0) or np.any(np.diff(epsilon) <= 0):
        raise ValueError("epsilon_mm must be positive and strictly ascending")
    return epsilon, response


def _design(epsilon: np.ndarray, model: str) -> np.ndarray:
    if model not in ("A", "B"):
        raise ValueError("model must be A or B")
    return np.column_stack((epsilon, epsilon**3 if model == "A" else epsilon * np.abs(epsilon)))


def _fit(epsilon: np.ndarray, response: np.ndarray, model: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """One unweighted pilot and one WLS fit on precisely this point set."""
    result: dict[str, Any] = {
        "model": model, "n_points": len(epsilon), "dof": len(epsilon) - 2,
        "available": False, "beta": None, "covariance": None,
        "pilot_s_n": None, "weights": None, "g_n_per_mm": None,
        "g_n_per_m": None, "se_g_n_per_mm": None, "se_g_n_per_m": None,
    }
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        design = _design(epsilon, model)
        if len(epsilon) < 2 or not np.all(np.isfinite(design)):
            return result
        try:
            pilot_beta, _, rank, _ = np.linalg.lstsq(design, response, rcond=None)
            if rank < 2:
                return result
            pilot = design @ pilot_beta
            weights = 1.0 / (params["sigma0_n"]**2 + (params["rho"] * pilot)**2)
            weighted_design = design * np.sqrt(weights[:, None])
            beta, _, rank, _ = np.linalg.lstsq(weighted_design, response * np.sqrt(weights), rcond=None)
            if rank < 2:
                return result
            covariance = np.linalg.inv(design.T @ (weights[:, None] * design))
            if not all(np.all(np.isfinite(v)) for v in (beta, covariance, pilot, weights)) or covariance[0, 0] < 0:
                return result
            se = float(np.sqrt(covariance[0, 0]))
        except (np.linalg.LinAlgError, ValueError, OverflowError):
            return result
    result.update(
        available=True, beta=beta.tolist(), covariance=covariance.tolist(),
        pilot_s_n=pilot.tolist(), weights=weights.tolist(),
        g_n_per_mm=float(beta[0]), g_n_per_m=n_per_mm_to_n_per_m(beta[0]),
        se_g_n_per_mm=se, se_g_n_per_m=n_per_mm_to_n_per_m(se),
    )
    return result


def fit_model(epsilon_mm: Sequence[float], s_n: Sequence[float], model: str,
              params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return full precision JSON-friendly diagnostics, with unscaled covariance.

    ``beta`` is [g, c] for A (N/mm, N/mm^3) or [g, k] for B
    (N/mm, N/mm^2); only the reported slope and its SE convert to N/m.
    """
    epsilon, response = _arrays(epsilon_mm, s_n)
    return _fit(epsilon, response, model, load_params() if params is None else _validate_params(params))


def _relative(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    value = abs(numerator) / abs(denominator)
    return float(value) if np.isfinite(value) else None


def _decisions(result: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, bool | None]:
    items = result["items"]
    relative_se = items["relative_se"]["value"]
    model_difference = items["model_difference"]["value"]
    shifts = [row["relative_shift_a"] for row in result["nested"] if row["used_for_stability"]]
    nested = False if any(value is not None and value > params["tol_nested"] for value in shifts) else (True if shifts and all(value is not None for value in shifts) else None)
    holds = [row["error_n"] <= max(3 * row["sigma_pred_n"], params["tol_hold"] * abs(row["s_pred_n"])) if row["error_n"] is not None else None for row in result["holdout"]]
    return {
        "sign": items["sign"]["passed"],
        "relative_se": relative_se <= params["tol_se"] if relative_se is not None else None,
        "nested_stability": nested,
        "model_difference": model_difference <= params["tol_model"] if model_difference is not None else None,
        "internal_holdout": False if False in holds else (True if holds and all(value is True for value in holds) else None),
        "magnitude": items["magnitude"]["passed"],
    }


def classify_result(result: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> str:
    """Rethreshold stored raw metrics without refitting for tolerance sensitivity.

    Only the four tolerances may differ; changing the noise model, nested drop,
    or magnitude criterion requires a fresh evaluation.
    """
    parameters = result["params"] if params is None else _validate_params(params)
    for key in ("sigma0_n", "rho", "nested_drop", "k_mag"):
        if parameters[key] != result["params"][key]:
            raise ValueError(f"classify_result cannot change {key} without refitting")
    decisions = _decisions(result, parameters)
    if result["n_points"] < 4 or result["dof"] < 1:
        return "UNRESOLVED"
    first_five = [value for key, value in decisions.items() if key != "magnitude"]
    if False in first_five:
        return "FAIL"
    if all(value is True for value in first_five) and decisions["magnitude"]:
        return "PASS"
    return "UNRESOLVED"


def _finite_json(value: Any) -> Any:
    """Preserve full precision and turn numerical unavailability into JSON null."""
    if isinstance(value, dict):
        return {key: _finite_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite_json(item) for item in value]
    return None if isinstance(value, float) and not np.isfinite(value) else value


def evaluate_series(epsilon_mm: Sequence[float], s_n: Sequence[float],
                    params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate all supplied points; no ladder selection or registered data access.

    ``passed=None`` means an item cannot be computed. Item 1 uses drops 1..3
    as expressly specified; item 3 independently uses ``nested_drop``.
    """
    epsilon, response = _arrays(epsilon_mm, s_n)
    parameters = load_params() if params is None else _validate_params(params)
    n = len(epsilon)
    fit_a = _fit(epsilon, response, "A", parameters)
    fit_b = _fit(epsilon, response, "B", parameters)
    g_a, g_b = fit_a["g_n_per_mm"], fit_b["g_n_per_mm"]
    nested = []
    for drop in range(1, min(max(3, parameters["nested_drop"]), n - 3) + 1):
        sub_a = _fit(epsilon[:-drop], response[:-drop], "A", parameters)
        sub_b = _fit(epsilon[:-drop], response[:-drop], "B", parameters)
        shift = _relative(sub_a["g_n_per_mm"] - g_a, g_a) if sub_a["available"] and fit_a["available"] else None
        nested.append({"drop": drop, "n_points": n - drop, "model_a": sub_a,
                       "model_b": sub_b, "relative_shift_a": shift,
                       "used_for_sign": drop <= 3,
                       "used_for_stability": drop <= parameters["nested_drop"]})

    sign_g = [g_a, g_b] + [row[key]["g_n_per_mm"] for row in nested if row["used_for_sign"] for key in ("model_a", "model_b")]
    signs = [int(np.sign(g)) for g in sign_g if g is not None]
    sign_pass = (all(sign == signs[0] and sign != 0 for sign in signs)
                 if signs else None)
    if len(signs) < len(sign_g) and sign_pass:
        sign_pass = None
    rel_se = _relative(fit_a["se_g_n_per_mm"], g_a) if fit_a["available"] else None
    shifts = [row["relative_shift_a"] for row in nested if row["used_for_stability"]]
    maximum_shift = max(shifts) if shifts and all(v is not None for v in shifts) else None
    model_difference = _relative(g_a - g_b, g_a) if fit_a["available"] and fit_b["available"] else None
    holdout = []
    for index in range(1, n - 1):
        selected = np.arange(n) != index
        sub_fit = _fit(epsilon[selected], response[selected], "A", parameters)
        row = {"index": index, "epsilon_mm": float(epsilon[index]), "s_obs_n": float(response[index]),
               "s_pred_n": None, "sigma_pred_n": None, "error_n": None, "limit_n": None,
               "passed": None, "fit": sub_fit}
        if sub_fit["available"]:
            x = _design(epsilon[index:index + 1], "A")[0]
            prediction = float(x @ np.asarray(sub_fit["beta"]))
            variance = parameters["sigma0_n"]**2 + (parameters["rho"] * prediction)**2 + float(x @ np.asarray(sub_fit["covariance"]) @ x)
            if np.isfinite(variance) and variance >= 0:
                sigma = float(np.sqrt(variance))
                error = float(abs(response[index] - prediction))
                limit = max(3 * sigma, parameters["tol_hold"] * abs(prediction))
                row.update(s_pred_n=prediction, sigma_pred_n=sigma, error_n=error,
                           limit_n=limit, passed=error <= limit)
        holdout.append(row)
    magnitude_count = int(np.count_nonzero(np.abs(response) >= parameters["k_mag"] * parameters["sigma0_n"]))
    items = {
        "sign": {"passed": sign_pass, "g_n_per_mm": sign_g, "signs": signs},
        "relative_se": {"passed": None, "value": rel_se},
        "nested_stability": {"passed": None, "maximum_relative_shift": maximum_shift},
        "model_difference": {"passed": None, "value": model_difference},
        "internal_holdout": {"passed": None},
        "magnitude": {"passed": magnitude_count >= 4, "point_count": magnitude_count,
                      "threshold_n": parameters["k_mag"] * parameters["sigma0_n"], "required_count": 4},
    }
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        q = [n_per_mm_to_n_per_m(s / e) for e, s in zip(epsilon, response)]
    result = {"n_points": n, "dof": n - 2, "params": parameters,
              "epsilon_mm": epsilon.tolist(), "s_n": response.tolist(),
              "q_n_per_m": q,
              "model_a": fit_a, "model_b": fit_b, "nested": nested,
              "holdout": holdout, "items": items}
    for key, passed in _decisions(result, parameters).items():
        items[key]["passed"] = passed
    result["verdict"] = classify_result(result)
    return _finite_json(result)
