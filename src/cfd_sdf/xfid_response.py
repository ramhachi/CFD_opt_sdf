"""Small, fail-closed arithmetic helpers for the XFID response contract.

This module does not select directions, epsilon values, response floors, or a
formal verdict for an experiment. Those values must be frozen in an immutable
registration after Candidate C's composite operator contract is approved.
"""

from __future__ import annotations

from math import isfinite
from numbers import Real
from typing import Iterable, Literal

XFIDVerdict = Literal["AGREE", "DISAGREE", "UNRESOLVED"]


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def response_deltas(
    baseline_n: float, plus_n: float, minus_n: float
) -> tuple[float, float]:
    """Return ``(R(+eps)-R0, R(-eps)-R0)`` in newtons."""
    baseline = _finite("baseline_n", baseline_n)
    plus = _finite("plus_n", plus_n)
    minus = _finite("minus_n", minus_n)
    return _finite("delta_R_plus", plus - baseline), _finite("delta_R_minus", minus - baseline)


def centered_secant_n_per_unit(plus_n: float, minus_n: float, epsilon: float) -> float:
    """Return the centered secant; its floor is distinct from an N response floor."""
    plus = _finite("plus_n", plus_n)
    minus = _finite("minus_n", minus_n)
    step = _finite("epsilon", epsilon)
    if step <= 0.0:
        raise ValueError("epsilon must be positive")
    return _finite("centered_secant", centered_contrast_n(plus, minus) / step)


def centered_contrast_n(plus_n: float, minus_n: float) -> float:
    """Return ``(R(+eps)-R(-eps))/2`` in N; baseline cancels exactly."""
    plus = _finite("plus_n", plus_n)
    minus = _finite("minus_n", minus_n)
    return _finite("centered_contrast_n", plus / 2.0 - minus / 2.0)


def compare_resolved_delta(
    waterlily_delta_n: float,
    openfoam_delta_n: float,
    waterlily_floor_n: float,
    openfoam_floor_n: float,
) -> XFIDVerdict:
    """Compare one paired response only when each solver resolves its own delta.

    A value exactly on its floor is unresolved. Floors must be positive and
    independently established for this response-difference quantity.
    """
    wl = _finite("waterlily_delta_n", waterlily_delta_n)
    of = _finite("openfoam_delta_n", openfoam_delta_n)
    wl_floor = _finite("waterlily_floor_n", waterlily_floor_n)
    of_floor = _finite("openfoam_floor_n", openfoam_floor_n)
    if wl_floor <= 0.0 or of_floor <= 0.0:
        raise ValueError("resolution floors must be positive")
    if abs(wl) <= wl_floor or abs(of) <= of_floor:
        return "UNRESOLVED"
    return "AGREE" if (wl > 0.0) == (of > 0.0) else "DISAGREE"


def compare_direction(
    waterlily_contrasts_n: tuple[float, float, float],
    openfoam_contrasts_n: tuple[float, float, float],
    waterlily_floors_n: tuple[float, float, float],
    openfoam_floors_n: tuple[float, float, float],
) -> XFIDVerdict:
    """Compare ``(delta_R_plus, delta_R_minus, centered_contrast)`` for one direction.

    Every required contrast is evaluated against its solver-specific floor.
    Any resolved sign disagreement is retained; otherwise an unresolved member
    makes the direction unresolved. The centered floor must come from a
    supported noise model, not the environment replay ceiling.
    """
    groups = (waterlily_contrasts_n, openfoam_contrasts_n, waterlily_floors_n, openfoam_floors_n)
    for values in groups:
        if not isinstance(values, tuple) or len(values) != 3:
            raise ValueError("each direction input must contain three values")
    wl, of, wl_floors, of_floors = groups
    comparisons = [
        compare_resolved_delta(wl[i], of[i], wl_floors[i], of_floors[i])
        for i in range(3)
    ]
    return aggregate_verdicts(comparisons)


def aggregate_verdicts(verdicts: Iterable[XFIDVerdict]) -> XFIDVerdict:
    """Aggregate declared representative comparisons; any resolved disagreement stops."""
    values = tuple(verdicts)
    if not values or any(value not in {"AGREE", "DISAGREE", "UNRESOLVED"} for value in values):
        raise ValueError("at least one valid three-valued verdict is required")
    if "DISAGREE" in values:
        return "DISAGREE"
    if "UNRESOLVED" in values:
        return "UNRESOLVED"
    return "AGREE"
