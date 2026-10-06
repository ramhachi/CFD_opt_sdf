"""Conditional C5 forward envelopes; not a certified LAPACK error theorem.

All envelope algebra uses Decimal on exact binary64 inputs. The operation
counts gamma(8*n+32), gamma(32) and weight gamma(4)/gamma(2) are engineering
backward-error assumptions fixed before evaluation. This helper reuses the
non-independent mathematical reference and claims no verifier independence.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "fd08_numeric_reference_for_bounds", Path(__file__).with_name("analyze_fd08_v2_numeric_contract.py"))
reference = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reference)

D = Decimal


def _u():
    return D(1) / D(2)**53


def _gamma(k):
    ku = D(k) / D(2)**53
    return ku / (1 - ku)


def _absolute(matrix):
    return [[abs(v) for v in row] for row in matrix]


def _transpose(matrix):
    return [list(row) for row in zip(*matrix)]


def _mm(a, b):
    bt = _transpose(b)
    return [[sum(x * y for x, y in zip(row, col)) for col in bt] for row in a]


def _mv(a, b):
    return [sum(x * y for x, y in zip(row, b)) for row in a]


def _add(a, b):
    return [[x + y for x, y in zip(arow, brow)] for arow, brow in zip(a, b)]


def _times(matrix, factor):
    return [[v * factor for v in row] for row in matrix]


def _norm(matrix):
    gram = _mm(_transpose(matrix), matrix)
    largest, _ = reference._decimal_spectrum(gram)
    return largest.sqrt()


def _radius(matrix):
    a, b = matrix[0]
    c, d = matrix[1]
    return ((a + d) + ((a - d)**2 + 4 * b * c).sqrt()) / 2


def _inverse_general(matrix):
    a, b = matrix[0]
    c, d = matrix[1]
    det = a * d - b * c
    if det <= 0:
        raise ValueError("invalid perturbation resolvent")
    return [[d / det, -b / det], [-c / det, a / det]]


def _linear_envelope(x, y, beta, covariance, dx, dy):
    """Entrywise normal-system perturbation with a nonnegative resolvent."""
    n = len(x)
    ax, ay, ac = _absolute(x), [abs(v) for v in y], _absolute(covariance)
    xt, dxt = _transpose(ax), _transpose(dx)
    da = _add(_add(_mm(xt, dx), _mm(dxt, ax)), _mm(dxt, dx))
    u_matrix = _add(ax, dx)
    v_target = [v + error for v, error in zip(ay, dy)]
    da = _add(da, _times(_mm(_transpose(u_matrix), u_matrix), _gamma(n)))
    a = _mm(_transpose(x), x)
    b = _mv(_transpose(x), y)
    # Inversion/solve arithmetic enters before the resolvent radius test.
    db = [u + v + w + _gamma(n) * z
          for u, v, w, z in zip(_mv(xt, dy), _mv(dxt, ay),
                               _mv(dxt, dy), _mv(_transpose(u_matrix), v_target))]
    da = _add(da, _times(_add(_absolute(a), da), _gamma(32)))
    db = [value + _gamma(32) * (abs(rhs) + value) for value, rhs in zip(db, b)]
    e = _mm(ac, da)
    radius = _radius(e)
    if radius >= 1:
        return dict(valid=False, radius=radius, reason="spectral_radius_ge_one")
    resolvent = _inverse_general([[1 - e[0][0], -e[0][1]], [-e[1][0], 1 - e[1][1]]])
    feedback = _mv(da, [abs(v) for v in beta])
    b_beta = _mv(_mm(resolvent, ac), [u + v for u, v in zip(db, feedback)])
    b_cov = _mm(_mm(_mm(resolvent, ac), da), ac)
    return dict(valid=True, radius=radius, beta=b_beta, covariance=b_cov,
                dA=da, db=db, reason=None)


def _prediction_bound(x, beta, b_beta, dx):
    return (sum(abs(v) * b for v, b in zip(x, b_beta))
            + sum(d * abs(b) for d, b in zip(dx, beta))
            + sum(d * error for d, error in zip(dx, b_beta))
            + _gamma(2) * sum((abs(v) + d) * (abs(b) + error)
                              for v, d, b, error in zip(x, dx, beta, b_beta)))


def _sqrt_bound(value, error):
    """Preregistered interval sqrt propagation including final sqrt rounding."""
    if value < 0 or error < 0:
        return None
    low, high = max(D(0), value - error), value + error
    root = value.sqrt()
    return max(high.sqrt() - root, root - low.sqrt()) + (_u()) * high.sqrt()


def _ratio_bound(numerator, denominator, b_num, b_den):
    if b_num is None or b_den is None:
        return None
    d = abs(denominator)
    remaining = d - b_den
    if d == 0 or remaining <= 0:
        return None
    return (b_num / remaining + abs(numerator) * b_den / (d * remaining)
            + (_u()) * (abs(numerator) + b_num) / remaining)


def _difference_ratio_bound(a, b, b_a, b_b):
    if b_a is None or b_b is None:
        return None
    d = abs(b)
    remaining = d - b_b
    if d == 0 or remaining <= 0:
        return None
    t = abs(a - b)
    return ((b_a + b_b) / remaining + t * b_b / (d * remaining)
            + _gamma(3) * (abs(a) + b_a + abs(b) + b_b) / remaining)


def _fit_bound(epsilon, response, fit, p, variant, full_reference):
    result = dict(available=False, beta=None, covariance=None, beta_mm=None, cov_mm=None,
                  beta_native=None, cov_native=None, pilot_s_n=None, weights=None,
                  g_native=None, se_g_native=None, g_n_per_mm=None, g_n_per_m=None,
                  se_g_n_per_mm=None, se_g_n_per_m=None,
                  numeric=dict(valid=False, reason="reference_fit_unavailable",
                               design_cond2=fit["numeric"]["design_cond2"],
                               weighted_design_cond2=fit["numeric"]["weighted_design_cond2"],
                               pilot_radius=None, weighted_radius=None, l_max=None))
    if not fit["available"]:
        return result
    n = len(epsilon)
    scale = reference._scale(variant, full_reference)
    x = reference._design(epsilon, fit["model"], scale)
    pilot_beta = fit["numeric"]["pilot_beta_native"]
    ones = [D(1)] * n
    pilot_cov = reference._inverse(reference._gram(x, ones))
    gamma = _gamma(8 * n + 32)
    xnorm, ynorm = _norm(x), sum(v * v for v in response).sqrt()
    dx = [[gamma * xnorm] * 2 for _ in range(n)]
    dy = [gamma * ynorm] * n
    pilot_bound = _linear_envelope(x, response, pilot_beta, pilot_cov, dx, dy)
    result["numeric"]["pilot_radius"] = pilot_bound["radius"]
    if not pilot_bound["valid"]:
        result["numeric"]["reason"] = "pilot_" + pilot_bound["reason"]
        return result
    b_pilot = [_prediction_bound(row, pilot_beta, pilot_bound["beta"], drow) for row, drow in zip(x, dx)]
    eta, l_values, b_weight = [], [], []
    for value, error, weight in zip(fit["pilot_s_n"], b_pilot, fit["weights"]):
        variance = p["sigma0_n"]**2 + (p["rho"] * value)**2
        # Fixed variance route: sigma0*sigma0 + (rho*pilot)^2, with
        # the rho*pilot product reused. Reciprocal then sqrt is two operations.
        sensitivity = p["rho"]**2 * (2 * abs(value) * error + error**2)
        dv = sensitivity + _gamma(4) * (variance + sensitivity)
        l_value = dv / variance
        l_values.append(l_value)
        if l_value >= 1:
            result["numeric"].update(l_max=max(l_values), reason="weight_variance_relative_error_ge_one")
            return result
        sqrt_amplification = 1 / (1 - l_value).sqrt()
        eta.append((1 + _gamma(2)) * sqrt_amplification - 1)
        b_weight.append(weight * (l_value + _gamma(1)) / (1 - l_value))
    sqrtw = [v.sqrt() for v in fit["weights"]]
    xw = [[w * v for v in row] for row, w in zip(x, sqrtw)]
    yw = [w * v for v, w in zip(response, sqrtw)]
    xwnorm, ywnorm = _norm(xw), sum(v * v for v in yw).sqrt()
    unit_roundoff = _u()
    dxw = [[w * d + e * w * (abs(v) + d)
            + unit_roundoff * w * (1 + e) * (abs(v) + d) + gamma * xwnorm
            for v, d in zip(row, drow)] for row, drow, w, e in zip(x, dx, sqrtw, eta)]
    dyw = [w * d + e * w * (abs(v) + d)
           + unit_roundoff * w * (1 + e) * (abs(v) + d) + gamma * ywnorm
           for v, d, w, e in zip(response, dy, sqrtw, eta)]
    weighted = _linear_envelope(xw, yw, fit["beta_native"], fit["cov_native"], dxw, dyw)
    result["numeric"].update(weighted_radius=weighted["radius"], l_max=max(l_values))
    if not weighted["valid"]:
        result["numeric"]["reason"] = "weighted_" + weighted["reason"]
        return result
    b_beta, b_cov = weighted["beta"], weighted["covariance"]
    mapping = fit["numeric"]["native_to_mm_diagonal"]
    # Conversion has its own forward rounding envelope, in addition to the
    # design-construction perturbation included above. N1 identity is exact.
    conversion_gamma = D(0) if variant == "N1" else _gamma(4)
    beta_mm = [abs(m) * (err + conversion_gamma * (abs(value) + err))
               for m, value, err in zip(mapping, fit["beta_native"], b_beta)]
    covariance_mm = [[abs(mapping[i] * mapping[j]) * (
        b_cov[i][j] + 2 * conversion_gamma * (abs(fit["cov_native"][i][j]) + b_cov[i][j])
        + conversion_gamma**2 * (abs(fit["cov_native"][i][j]) + b_cov[i][j]))
        for j in range(2)] for i in range(2)]
    se_native = _sqrt_bound(fit["cov_native"][0][0], b_cov[0][0])
    se_mm = abs(mapping[0]) * (se_native + conversion_gamma * (abs(fit["se_g_native"]) + se_native))
    # Legacy stored mm slopes/SE may be reconstructed from N/m by /1000.
    # Include the multiply/divide round trip for either comparator operand.
    beta_mm[0] += _gamma(2) * (abs(fit["g_n_per_mm"]) + beta_mm[0])
    se_mm += _gamma(2) * (abs(fit["se_g_n_per_mm"]) + se_mm)
    result.update(available=True, beta=beta_mm, covariance=covariance_mm,
                  beta_mm=beta_mm, cov_mm=covariance_mm, beta_native=b_beta, cov_native=b_cov,
                  pilot_s_n=b_pilot, weights=b_weight, g_native=b_beta[0], se_g_native=se_native,
                  g_n_per_mm=beta_mm[0], g_n_per_m=1000 * (beta_mm[0] + _u() * (abs(fit["g_n_per_mm"]) + beta_mm[0])),
                  se_g_n_per_mm=se_mm, se_g_n_per_m=1000 * (se_mm + _u() * (abs(fit["se_g_n_per_mm"]) + se_mm)))
    design_spectrum = reference._decimal_spectrum(reference._gram(x, ones))
    weighted_spectrum = reference._decimal_spectrum(reference._gram(xw, ones))
    result["numeric"].update(valid=True, reason=None, backward_gamma=gamma,
                             design_gram_spectrum=list(design_spectrum), weighted_gram_spectrum=list(weighted_spectrum),
                             covariance_variance_lower=fit["cov_native"][0][0] - b_cov[0][0],
                             covariance_variance_positivity="positive" if fit["cov_native"][0][0] - b_cov[0][0] > 0 else "ambiguous",
                             pilot_beta_native=pilot_bound["beta"], pilot_cov_native=pilot_bound["covariance"],
                             pilot_dA=pilot_bound["dA"], pilot_db=pilot_bound["db"],
                             weighted_dA=weighted["dA"], weighted_db=weighted["db"],
                             weight_variance_l=l_values, sqrt_weight_relative_error=eta)
    return result


def _holdout_bound(row, bound, p, variant, full_reference):
    result = dict(index=row["index"], s_pred_n=None, sigma_pred_n=None, error_n=None,
                  limit_n=None, threshold_margin_n=None, fit=bound, valid=False)
    if not bound["available"] or row["s_pred_n"] is None:
        return result
    fit = row["fit"]
    x = reference._design([row["epsilon_mm"]], "A", reference._scale(variant, full_reference))[0]
    # Fresh-row construction allowance is separate from training DX.
    gamma = _gamma(8 * fit["n_points"] + 32)
    row_norm = sum(v * v for v in x).sqrt()
    conversion = D(0) if variant == "N1" else _gamma(4)
    dx = [gamma * row_norm + conversion * abs(v) for v in x]
    b_prediction = _prediction_bound(x, fit["beta_native"], bound["beta_native"], dx)
    absx = [abs(v) for v in x]
    covariance_abs = _absolute(fit["cov_native"])
    b_variance_fit = sum(absx[i] * bound["cov_native"][i][j] * absx[j] for i in range(2) for j in range(2))
    b_variance_fit += sum((dx[i] * absx[j] + absx[i] * dx[j] + dx[i] * dx[j])
                          * (covariance_abs[i][j] + bound["cov_native"][i][j])
                          for i in range(2) for j in range(2))
    b_variance_fit += _gamma(5) * sum((absx[i] + dx[i]) * (covariance_abs[i][j] + bound["cov_native"][i][j])
                                    * (absx[j] + dx[j]) for i in range(2) for j in range(2))
    prediction = row["s_pred_n"]
    variance_fit = sum(x[i] * fit["cov_native"][i][j] * x[j] for i in range(2) for j in range(2))
    noise_variance = p["sigma0_n"]**2 + (p["rho"] * prediction)**2
    variance = variance_fit + noise_variance
    sensitivity = p["rho"]**2 * (2 * abs(prediction) * b_prediction + b_prediction**2)
    b_noise = sensitivity + _gamma(4) * (noise_variance + sensitivity)
    unit_roundoff = _u()
    b_variance = (b_variance_fit + b_noise
                  + _gamma(2) * (abs(variance_fit) + b_variance_fit + noise_variance + b_noise))
    b_sigma = _sqrt_bound(variance, b_variance)
    b_error = b_prediction + unit_roundoff * (abs(row["s_obs_n"]) + abs(prediction) + b_prediction)
    b_limit = max(3 * b_sigma + unit_roundoff * 3 * (row["sigma_pred_n"] + b_sigma),
                  p["tol_hold"] * b_prediction + unit_roundoff * p["tol_hold"] * (abs(prediction) + b_prediction))
    b_margin = b_limit + b_error + unit_roundoff * (abs(row["limit_n"]) + abs(row["error_n"]) + b_limit + b_error)
    result.update(s_pred_n=b_prediction, sigma_pred_n=b_sigma, error_n=b_error,
                  limit_n=b_limit, threshold_margin_n=b_margin, valid=True,
                  numeric=dict(predictive_variance_lower=variance - b_variance,
                               predictive_variance_positivity="positive" if variance - b_variance > 0 else "ambiguous",
                               fresh_row_error=dx, predictive_variance_bound=b_variance))
    return result


def bound_series(epsilon, response, params, variant="N1", precision=80, *, presentation_ratios=False, decimal_output=False):
    """Primary-shaped absolute forward-error tree, with invalid envelopes null.

    Bounds compare the corresponding arithmetic variant to the mathematical
    reference. Add two implementations' envelopes for pairwise comparisons.
    They are conditional on the explicitly stated backward-error assumptions.
    """
    with localcontext() as context:
        context.prec = precision
        actual = reference.reference_series(epsilon, response, params, precision=precision,
                                            variant=variant, decimal_output=True)
        eps, y, p = actual["epsilon_mm"], actual["s_n"], actual["params"]
        full_reference = actual["numeric"]["epsilon_ref_mm"]
        gkey = "g_n_per_m" if presentation_ratios else "g_native"
        sekey = "se_g_n_per_m" if presentation_ratios else "se_g_native"
        a = _fit_bound(eps, y, actual["model_a"], p, variant, full_reference)
        b = _fit_bound(eps, y, actual["model_b"], p, variant, full_reference)
        nested = []
        for row in actual["nested"]:
            sa = _fit_bound(eps[:-row["drop"]], y[:-row["drop"]], row["model_a"], p, variant, full_reference)
            sb = _fit_bound(eps[:-row["drop"]], y[:-row["drop"]], row["model_b"], p, variant, full_reference)
            relative = _difference_ratio_bound(row["model_a"][gkey], actual["model_a"][gkey],
                                               sa[gkey], a[gkey]) if row["model_a"]["available"] and actual["model_a"]["available"] else None
            nested.append(dict(drop=row["drop"], model_a=sa, model_b=sb, relative_shift_a=relative,
                               used_for_sign=row["used_for_sign"], used_for_stability=row["used_for_stability"]))
        holdout = []
        for row in actual["holdout"]:
            selected = [j for j in range(len(eps)) if j != row["index"]]
            sub = _fit_bound([eps[j] for j in selected], [y[j] for j in selected], row["fit"], p, variant, full_reference)
            holdout.append(_holdout_bound(row, sub, p, variant, full_reference))
        se_bound = _ratio_bound(actual["model_a"][sekey], actual["model_a"][gkey],
                                a[sekey], a[gkey]) if actual["model_a"]["available"] else None
        # Model difference denominator is g_A, so B is the first operand.
        model_bound = _difference_ratio_bound(actual["model_b"][gkey], actual["model_a"][gkey],
                                              b[gkey], a[gkey]) if actual["model_a"]["available"] and actual["model_b"]["available"] else None
        stability = [row["relative_shift_a"] for row in nested if row["used_for_stability"]]
        maximum = max(stability) if stability and all(v is not None for v in stability) else None
        items = dict(relative_se=dict(value=se_bound, threshold_margin=se_bound),
                     model_difference=dict(value=model_bound, threshold_margin=model_bound),
                     nested_stability=dict(maximum_relative_shift=maximum, threshold_margin=maximum),
                     internal_holdout=dict(minimum_threshold_margin_n=max((row["threshold_margin_n"] for row in holdout), default=D(0))
                                           if all(row["valid"] for row in holdout) else None),
                     magnitude=dict(threshold_n=_u() * p["k_mag"] * p["sigma0_n"]))
        for name, raw_value, tolerance in (("relative_se", actual["items"]["relative_se"]["value"], "tol_se"),
                                           ("model_difference", actual["items"]["model_difference"]["value"], "tol_model"),
                                           ("nested_stability", actual["items"]["nested_stability"]["maximum_relative_shift"], "tol_nested")):
            error = items[name]["threshold_margin"]
            if error is not None:
                items[name]["threshold_margin"] = error + _u() * (abs(p[tolerance]) + abs(raw_value) + error)
        sign_fits = [a, b] + [row[key] for row in nested if row["used_for_sign"] for key in ("model_a", "model_b")]
        items["sign"] = dict(g_n_per_mm=[fit["g_n_per_mm"] for fit in sign_fits])
        all_fits = [a, b] + [row[key] for row in nested for key in ("model_a", "model_b")] + [row["fit"] for row in holdout]
        fit_envelopes_valid = all(fit["available"] for fit in all_fits)
        covariance_positive = all(fit["numeric"].get("covariance_variance_positivity") == "positive" for fit in all_fits)
        predictive_positive = all(row.get("numeric", {}).get("predictive_variance_positivity") == "positive" for row in holdout)
        valid = fit_envelopes_valid and covariance_positive and predictive_positive
        bounds = dict(model_a=a, model_b=b, nested=nested, holdout=holdout, items=items)
        margins = {name: items[name]["threshold_margin"] for name in ("relative_se", "model_difference", "nested_stability")}
        margins.update({f"holdout[{i}]": row["threshold_margin_n"] for i, row in enumerate(holdout)})
        magnitude_threshold = p["k_mag"] * p["sigma0_n"]
        margins.update({f"magnitude[{i}]": _u() * abs(magnitude_threshold) + _u() * (abs(value) + abs(magnitude_threshold) * (1 + _u()))
                        for i, value in enumerate(y)})
        labeled_fits = [("full_A", a), ("full_B", b)]
        labeled_fits += [(f"nested{row['drop']}_{model}", row[f"model_{model}"])
                         for row in nested if row["used_for_sign"] for model in ("a", "b")]
        margins.update({f"sign[{label}]": fit["g_n_per_mm"] for label, fit in labeled_fits})
        diagnostics = dict(variant=variant, valid=valid, precision_decimal_digits=precision, presentation_ratios=presentation_ratios,
                                   operation_envelope="engineering_backward_error_assumption_not_certified_LAPACK_bound",
                                   gamma_k_n="gamma(8*n+32)", weight_arithmetic_gamma="gamma(4),gamma(2)")
        all_labeled = labeled_fits + [(f"holdout{row['index']}", row["fit"]) for row in holdout]
        diagnostics["fits"] = {label: fit["numeric"] for label, fit in all_labeled}
        diagnostics.update(fit_envelopes_valid=fit_envelopes_valid,
                           covariance_variances_positive=covariance_positive,
                           predictive_variances_positive=predictive_positive)
        diagnostics["ratio_bounds_valid"] = all(value is not None for value in (se_bound, model_bound, maximum))
        result = dict(bounds=bounds, diagnostics=diagnostics, margins=margins)
        return result if decimal_output else reference._json(result)
