"""Solver-free contracts for the distinct finite-step STEP-01 oracle."""

from __future__ import annotations

from math import isfinite


MIN_STEP_FRACTION = 0.1
MAX_STEP_FRACTION = 0.5


def validate_step_fraction(step_fraction_h: float) -> float:
    """Accept only the user-registered STEP-01 range, expressed in h units."""
    step = float(step_fraction_h)
    if not isfinite(step) or not MIN_STEP_FRACTION <= step <= MAX_STEP_FRACTION:
        raise ValueError(
            f"step_fraction_h must be in [{MIN_STEP_FRACTION}, {MAX_STEP_FRACTION}]"
        )
    return step


def finite_step_response(*, baseline_n: float, candidate_n: float, step_m: float) -> dict[str, float]:
    """Return a finite response change in N and its finite secant in N/m."""
    baseline, candidate, step = float(baseline_n), float(candidate_n), float(step_m)
    if not all(isfinite(value) for value in (baseline, candidate, step)) or step <= 0:
        raise ValueError("forces must be finite N values and step_m must be positive")
    delta_n = candidate - baseline
    return {"delta_response_n": delta_n, "finite_secant_n_per_m": delta_n / step}


# ---- STEP-01 analysis quantities (pure arithmetic on caller-supplied N / m values; no solver, no gradient claim) ---------------------------------------------
NOMINAL_SIGMA0_N = 3e-6          # the nominal T2 noise scale of FD-08 (not a measured noise)
RESOLVED_FACTOR = 10.0           # a response change is "resolved" when |dR| > RESOLVED_FACTOR * sigma0
AGREEMENT_TOLERANCES = (0.30, 0.50)


def centered_secant(r_plus_n: float, r_minus_n: float, step_m: float) -> float:
    """g_sec(s) = [R(+s) - R(-s)] / (2 s), N/m: the primary STEP-01 quantity (its even part cancels)."""
    values = (float(r_plus_n), float(r_minus_n), float(step_m))
    if not all(isfinite(v) for v in values) or values[2] <= 0:
        raise ValueError("responses must be finite and step_m positive")
    return (values[0] - values[1]) / (2.0 * values[2])


def even_ratio(r_plus_n: float, r_minus_n: float, r0_n: float) -> float:
    """eta_even(s) = |R(+s) + R(-s) - 2 R(0)| / |R(+s) - R(-s)|: nonlinearity / asymmetry of the response (nan when the odd part vanishes)."""
    values = (float(r_plus_n), float(r_minus_n), float(r0_n))
    if not all(isfinite(v) for v in values):
        raise ValueError("responses must be finite")
    odd = abs(values[0] - values[1])
    return abs(values[0] + values[1] - 2.0 * values[2]) / odd if odd > 0 else float("nan")


def is_resolved(*delta_n: float, sigma0_n: float = NOMINAL_SIGMA0_N, factor: float = RESOLVED_FACTOR) -> bool:
    """True when every given response change exceeds factor * sigma0 in magnitude."""
    return all(isfinite(float(d)) and abs(float(d)) > factor * sigma0_n for d in delta_n)


def sign_stability(g_sec: list[float], g_hat: float | None = None, resolved: list[bool] | None = None) -> dict:
    """Signs of g_sec over the ordered steps: constant?, equal to sign(g_hat)?, and the first step index at which the sign differs from the first resolved one."""
    resolved = resolved if resolved is not None else [True] * len(g_sec)
    if len(resolved) != len(g_sec):
        raise ValueError("resolved must have one entry per step")
    signs = [(0 if not isfinite(g) or g == 0 else (1 if g > 0 else -1)) for g in g_sec]
    ref = next((sg for sg, ok in zip(signs, resolved) if ok and sg != 0), 0)
    first_flip = next((i for i, (sg, ok) in enumerate(zip(signs, resolved)) if ok and sg != 0 and sg != ref), None)
    same_as_hat = None if g_hat is None or not isfinite(g_hat) or g_hat == 0 or ref == 0 else all(
        sg == (1 if g_hat > 0 else -1) for sg, ok in zip(signs, resolved) if ok)
    return {"signs": signs, "reference_sign": ref, "constant_over_resolved_steps": first_flip is None and ref != 0, "first_flip_index": first_flip,
            "same_sign_as_g_hat_over_resolved_steps": same_as_hat, "unresolved_indices": [i for i, ok in enumerate(resolved) if not ok]}


def agreement_radius(steps_mm: list[float], g_sec: list[float], g_hat: float, tolerance: float) -> float | None:
    """Largest step such that, from the smallest step upward without a gap, |g_sec/g_hat - 1| <= tolerance (which implies the sign agrees). A descriptive radius, NOT a
    validity claim: g_hat is the Model-A local slope of FD-08, not the epsilon->0 derivative.  None when even the smallest step disagrees."""
    if not isfinite(g_hat) or g_hat == 0 or tolerance <= 0:
        raise ValueError("g_hat must be finite and nonzero and the tolerance positive")
    radius = None
    for step, g in sorted(zip(steps_mm, g_sec)):
        if isfinite(g) and abs(g / g_hat - 1.0) <= tolerance:
            radius = step
        else:
            break
    return radius


def secant_drift_radius(steps_mm: list[float], g_sec: list[float], tolerance: float) -> dict:
    """Smallest step at which g_sec(s)/g_sec(s_min) - 1 leaves +-tolerance (where the centered secant bends), and the last step still inside."""
    pairs = sorted(zip(steps_mm, g_sec))
    ref = pairs[0][1]
    if not isfinite(ref) or ref == 0 or tolerance <= 0:
        raise ValueError("the reference secant must be finite and nonzero and the tolerance positive")
    last_inside, first_outside = pairs[0][0], None
    for step, g in pairs[1:]:
        if isfinite(g) and abs(g / ref - 1.0) <= tolerance:
            last_inside = step
        else:
            first_outside = step
            break
    return {"reference_step_mm": pairs[0][0], "last_step_within_mm": last_inside, "first_step_outside_mm": first_outside}


def interpolate_signed_response(steps_mm: list[float], delta_n: list[float], query_mm: float) -> dict:
    """dR(s) at a signed step from the grid of signed single-direction responses (the origin dR = 0 is added): PCHIP and linear interpolation, and their difference."""
    import numpy as np
    from scipy.interpolate import PchipInterpolator
    x = np.asarray(list(steps_mm) + [0.0], dtype=float); y = np.asarray(list(delta_n) + [0.0], dtype=float)
    order = np.argsort(x); x, y = x[order], y[order]
    if len(set(x.tolist())) != len(x) or not (x[0] <= query_mm <= x[-1]):
        raise ValueError("steps must be distinct and the query inside the sampled range")
    pchip, linear = float(PchipInterpolator(x, y)(query_mm)), float(np.interp(query_mm, x, y))
    return {"pchip_n": pchip, "linear_n": linear, "interpolation_spread_n": abs(pchip - linear)}


def additivity_defect(delta_combo_n: float, predicted_n: float, spread_n: float = 0.0, sigma0_n: float = NOMINAL_SIGMA0_N, factor: float = RESOLVED_FACTOR) -> dict:
    """Finite-step additivity of a combined direction: dR(d_a + d_b) against dR(d_a) + dR(d_b).  Relative to |dR_combo|.  The defect is flagged only when it exceeds BOTH the
    interpolation spread of the prediction and the measurement resolution (factor * sigma0): a defect below either is not distinguishable from the prediction's uncertainty."""
    values = (float(delta_combo_n), float(predicted_n), float(spread_n))
    if not all(isfinite(v) for v in values) or values[2] < 0:
        raise ValueError("inputs must be finite and the spread nonnegative")
    defect = values[0] - values[1]
    floor = max(values[2], factor * sigma0_n)
    return {"defect_n": defect, "relative_to_combo": abs(defect) / abs(values[0]) if values[0] != 0 else float("nan"), "uncertainty_floor_n": floor,
            "defect_exceeds_interpolation_spread_and_resolution": abs(defect) > floor}
