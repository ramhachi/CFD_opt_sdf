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
