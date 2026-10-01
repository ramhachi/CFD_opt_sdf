"""Solver-free checks for the FD-08 campaign boundary and verdict.

This module deliberately does not choose an epsilon ladder or estimate a
resolution floor. Those are measured on Candidate C, frozen, and registered
before the 33-run fresh qualification set.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite


FRESH_QUALIFICATION_RUNS = 33
PLATEAU_RELATIVE_LIMIT = 0.05
MINIMUM_PLATEAU_POINTS = 3


def validate_fd08_run_partition(
    calibration_run_ids: Iterable[str], qualification_run_ids: Iterable[str]
) -> None:
    """Require unique, nonempty, disjoint IDs and exactly 33 fresh runs."""
    calibration = tuple(calibration_run_ids)
    qualification = tuple(qualification_run_ids)
    for label, run_ids in (("calibration", calibration), ("qualification", qualification)):
        if not run_ids or any(not isinstance(run_id, str) or not run_id.strip() for run_id in run_ids):
            raise ValueError(f"{label} run IDs must be nonempty strings")
        if len(set(run_ids)) != len(run_ids):
            raise ValueError(f"duplicate {label} run ID")
    overlap = sorted(set(calibration) & set(qualification))
    if overlap:
        raise ValueError(f"calibration runs reused for qualification: {overlap}")
    if len(qualification) != FRESH_QUALIFICATION_RUNS:
        raise ValueError(
            f"qualification requires exactly {FRESH_QUALIFICATION_RUNS} fresh runs; "
            f"got {len(qualification)}"
        )


def evaluate_fd08_response(
    observations: Iterable[Mapping[str, object]], *, resolution_floor_n: float
) -> dict[str, object]:
    """Evaluate one response's separate resolution, 5% plateau, and sign gates.

    Each observation must already contain its signed, centered response
    numerator in N,
    relative plateau deviation, resolved status computed against the
    independently measured absolute floor, and sign. Missing or malformed
    evidence raises instead of being interpreted as a pass.
    """
    if not isfinite(resolution_floor_n) or resolution_floor_n < 0:
        raise ValueError("resolution_floor_n must be finite and nonnegative")
    rows = tuple(observations)
    if len(rows) < MINIMUM_PLATEAU_POINTS:
        raise ValueError(f"at least {MINIMUM_PLATEAU_POINTS} plateau observations are required")
    for row in rows:
        for key in ("response_n", "plateau_relative_deviation", "resolved", "sign"):
            if key not in row:
                raise ValueError(f"observation missing {key}")
        if isinstance(row["response_n"], bool) or isinstance(row["plateau_relative_deviation"], bool):
            raise ValueError("response and plateau deviation must be numeric, not boolean")
        response = float(row["response_n"])
        deviation = float(row["plateau_relative_deviation"])
        if not isfinite(response) or not isfinite(deviation) or deviation < 0:
            raise ValueError("response and plateau deviation must be finite; deviation nonnegative")
        if not isinstance(row["resolved"], bool):
            raise ValueError("resolved must be an explicit boolean from the frozen floor check")
        if abs(response) <= resolution_floor_n and row["resolved"]:
            raise ValueError("response at or below resolution floor cannot be resolved")
        if abs(response) > resolution_floor_n and not row["resolved"]:
            raise ValueError("response above resolution floor cannot be marked unresolved")
        sign = row["sign"]
        if isinstance(sign, bool) or sign not in (-1, 0, 1):
            raise ValueError("sign must be -1, 0, or +1 (not boolean)")
        if sign == 0 and (row["resolved"] or response != 0.0):
            raise ValueError("zero sign is allowed only for an unresolved zero response")
        if sign in (-1, 1) and sign != (1 if response > 0 else -1 if response < 0 else 0):
            raise ValueError("sign must match the signed response numerator")

    resolved = all(bool(row["resolved"]) for row in rows)
    signs = {int(row["sign"]) for row in rows}
    sign_consistent = len(signs) == 1
    deviations = [float(row["plateau_relative_deviation"]) for row in rows]
    plateau_pass = all(value <= PLATEAU_RELATIVE_LIMIT for value in deviations)
    if not resolved:
        verdict = "UNRESOLVED"
    elif plateau_pass and sign_consistent:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {
        "verdict": verdict,
        "resolution_floor_n": resolution_floor_n,
        "all_resolved": resolved,
        "plateau_relative_limit": PLATEAU_RELATIVE_LIMIT,
        "plateau_pass": plateau_pass,
        "sign_consistent": sign_consistent,
    }
