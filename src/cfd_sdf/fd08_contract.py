"""Solver-free checks for the FD-08 campaign boundary and verdict.

This module deliberately does not choose an epsilon ladder or estimate a
resolution floor. Those are measured on Candidate C, frozen, and registered
before the 33-run fresh qualification set.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite

import numpy as np

from cfd_sdf.candidate_c_identity import load_candidate_c_identity

FRESH_QUALIFICATION_RUNS = 33
PLATEAU_RELATIVE_LIMIT = 0.05
MINIMUM_PLATEAU_POINTS = 3
CANONICAL_STATE_SHA256 = "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
CANONICAL_PHI_FORTRAN_F32_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
CALIBRATION_FLOW = "flow_24"
WINDOW_TU_L = (80.0, 120.0)


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


def validate_fd08_design(
    calibration_run_ids: Iterable[str], qualification_runs: Iterable[Mapping[str, object]]
) -> dict[str, object]:
    """Check a caller-supplied calibrated 3 + (3 x 5 x 2) run design.

    This validates the fresh-run inventory only. It does not choose directions,
    epsilon values, a resolution floor, or criteria and writes no registration.
    """
    calibration = tuple(calibration_run_ids)
    runs = tuple(qualification_runs)
    if any(not isinstance(run, Mapping) for run in runs):
        raise ValueError("each qualification run must be a mapping")
    ids = [run.get("run_id") for run in runs]
    validate_fd08_run_partition(calibration, ids)
    if len(runs) != FRESH_QUALIFICATION_RUNS:
        raise ValueError("FD-08 qualification inventory must contain exactly 33 rows")
    baselines = [run for run in runs if run.get("role") == "baseline"]
    perturbations = [run for run in runs if run.get("role") == "perturbation"]
    if len(baselines) != 3 or len(perturbations) != 30:
        raise ValueError("FD-08 requires three baseline runs and 30 signed perturbation runs")
    cells = set()
    directions, epsilons = set(), set()
    for run in perturbations:
        direction = run.get("direction_id")
        epsilon = run.get("epsilon_m")
        sign = run.get("sign")
        if not isinstance(direction, str) or not direction.strip():
            raise ValueError("each perturbation requires a direction_id")
        if isinstance(epsilon, bool) or not isinstance(epsilon, (int, float)) or not isfinite(float(epsilon)) or epsilon <= 0:
            raise ValueError("each perturbation requires a finite positive calibrated epsilon_m")
        if isinstance(sign, bool) or sign not in (-1, 1):
            raise ValueError("each perturbation sign must be -1 or +1")
        cell = (direction, float(epsilon), int(sign))
        if cell in cells:
            raise ValueError("duplicate direction/epsilon/sign cell")
        cells.add(cell)
        directions.add(direction)
        epsilons.add(float(epsilon))
    if len(directions) != 3 or len(epsilons) != 5 or len(cells) != 30:
        raise ValueError("FD-08 requires a complete 3-direction x 5-epsilon x 2-sign map")
    if any(not isinstance(run.get("run_id"), str) or not run["run_id"].strip() for run in baselines):
        raise ValueError("baseline run IDs must be nonempty strings")
    return {
        "calibration_run_count": len(calibration),
        "qualification_run_count": len(runs),
        "baseline_run_count": len(baselines),
        "direction_count": len(directions),
        "epsilon_count": len(epsilons),
        "signed_perturbation_count": len(perturbations),
        "fresh_solver_execution_verified": False,
        "formal_qualification": False,
        "criteria_registered": False,
    }


def validate_fd08_binding(
    repository,
    *,
    calibration_backend: str,
    qualification_backend: str,
    flow_id: str,
    window_tu_l: Iterable[float],
    canonical_state_sha256: str,
    canonical_phi_fortran_f32_sha256: str,
) -> dict[str, object]:
    """Bind calibration and future qualification to the frozen C/v17 window."""
    if (not isinstance(calibration_backend, str) or not isinstance(qualification_backend, str)
            or calibration_backend != "Kaggle-T4" or qualification_backend != "Kaggle-T4"):
        raise ValueError("FD-08 calibration and formal runs require the Kaggle-T4 backend identity")
    if flow_id != CALIBRATION_FLOW or tuple(window_tu_l) != WINDOW_TU_L:
        raise ValueError("FD-08 must use flow_24 and the exact [80, 120] tU/L window")
    if canonical_state_sha256 != CANONICAL_STATE_SHA256:
        raise ValueError("FD-08 must bind the canonical genesis v17 state identity")
    if canonical_phi_fortran_f32_sha256 != CANONICAL_PHI_FORTRAN_F32_SHA256:
        raise ValueError("FD-08 must bind the canonical v17 Fortran-order float32 phi bytes")
    identity = load_candidate_c_identity(repository)
    return {
        "candidate_c_identity": identity,
        "declared_backend_identity": qualification_backend,
        "flow_id": flow_id,
        "window_tu_l": list(WINDOW_TU_L),
        "canonical_state_sha256": canonical_state_sha256,
        "canonical_phi_fortran_f32_sha256": canonical_phi_fortran_f32_sha256,
        "runtime_identity_verified": False,
        "formal_qualification": False,
        "criteria_registered": False,
    }


def audit_float32_perturbation(
    canonical_phi, direction, *, epsilon_m: float, sign: int, actual_phi
) -> dict[str, object]:
    """Verify requested perturbation against its actual stored Float32 state."""
    if isinstance(epsilon_m, bool) or not isfinite(float(epsilon_m)) or epsilon_m <= 0:
        raise ValueError("epsilon_m must be finite and positive")
    if isinstance(sign, bool) or sign not in (-1, 1):
        raise ValueError("sign must be -1 or +1")
    base = np.asarray(canonical_phi)
    vector = np.asarray(direction, dtype=np.float64)
    observed = np.asarray(actual_phi)
    if base.dtype != np.dtype(np.float32) or observed.dtype != np.dtype(np.float32):
        raise ValueError("canonical and actual phi must be stored as Float32")
    if base.shape != vector.shape or base.shape != observed.shape:
        raise ValueError("canonical phi, direction and actual phi must have identical shapes")
    if not np.isfinite(base).all() or not np.isfinite(vector).all() or not np.isfinite(observed).all():
        raise ValueError("perturbation arrays must be finite")
    expected = np.asarray(base.astype(np.float64) + int(sign) * float(epsilon_m) * vector, dtype=np.float32)
    if not np.array_equal(observed, expected):
        raise ValueError("actual Float32 phi does not match requested signed perturbation")
    delta = observed.astype(np.float64) - base.astype(np.float64)
    changed = int(np.count_nonzero(observed != base))
    if changed == 0:
        raise ValueError("requested perturbation rounded away in Float32 phi storage")
    return {
        "changed_node_count": changed,
        "max_abs_delta_m": float(np.max(np.abs(delta))),
        "l2_delta_m": float(np.linalg.norm(delta.ravel())),
        "requested_epsilon_m": float(epsilon_m),
        "sign": int(sign),
        "actual_phi_dtype": "float32",
    }


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
    if (isinstance(resolution_floor_n, bool) or not isinstance(resolution_floor_n, (int, float))
            or not isfinite(float(resolution_floor_n)) or resolution_floor_n <= 0):
        raise ValueError("resolution_floor_n must be an independently measured positive finite value")
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
