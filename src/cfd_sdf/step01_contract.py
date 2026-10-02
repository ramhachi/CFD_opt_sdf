"""Solver-free contracts for the distinct finite-step STEP-01 oracle."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
from typing import Any

from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.fd08_contract import (
    CALIBRATION_FLOW,
    CANONICAL_PHI_FORTRAN_F32_SHA256,
    CANONICAL_STATE_SHA256,
    WINDOW_TU_L,
)


MIN_STEP_FRACTION = 0.1
MAX_STEP_FRACTION = 0.5
CANONICAL_GRID_SPACING_M = 0.025


def validate_step_fraction(step_fraction_h: float) -> float:
    """Accept only the user-registered STEP-01 range, expressed in h units."""
    step = float(step_fraction_h)
    if not isfinite(step) or not MIN_STEP_FRACTION <= step <= MAX_STEP_FRACTION:
        raise ValueError(
            f"step_fraction_h must be in [{MIN_STEP_FRACTION}, {MAX_STEP_FRACTION}]"
        )
    return step


def validate_step01_preflight(
    repository: Path,
    *,
    backend_identity: str,
    flow_id: str,
    window_tu_l,
    canonical_state_sha256: str,
    canonical_phi_fortran_f32_sha256: str,
    direction_id: str,
    step_fraction_h: float,
    sign: int,
) -> dict[str, Any]:
    """Bind a caller-selected STEP-01 secant to frozen Candidate C/v17 inputs.

    This is a readiness check, not a run registrar. It verifies declared
    bindings only; it does not establish runtime identity or a fresh execution.
    """
    fraction = validate_step_fraction(step_fraction_h)
    if isinstance(sign, bool) or sign not in (-1, 1):
        raise ValueError("STEP-01 sign must be -1 or +1")
    if backend_identity != "Kaggle-T4":
        raise ValueError("STEP-01 formal GPU measurements require the Kaggle-T4 backend identity")
    if flow_id != CALIBRATION_FLOW or tuple(window_tu_l) != WINDOW_TU_L:
        raise ValueError("STEP-01 must use flow_24 and the exact [80, 120] tU/L window")
    if canonical_state_sha256 != CANONICAL_STATE_SHA256:
        raise ValueError("STEP-01 must bind the canonical genesis v17 state identity")
    if canonical_phi_fortran_f32_sha256 != CANONICAL_PHI_FORTRAN_F32_SHA256:
        raise ValueError("STEP-01 must bind the canonical v17 Fortran-order float32 phi bytes")
    if not isinstance(direction_id, str) or not direction_id.strip():
        raise ValueError("STEP-01 requires an explicit caller-supplied direction_id")
    identity = load_candidate_c_identity(repository)
    return {
        "oracle_id": "STEP-01",
        "oracle_type": "finite_step_response_secant",
        "candidate_c_identity": identity,
        "declared_backend_identity": backend_identity,
        "flow_id": flow_id,
        "window_tu_l": list(WINDOW_TU_L),
        "canonical_state_sha256": canonical_state_sha256,
        "canonical_phi_fortran_f32_sha256": canonical_phi_fortran_f32_sha256,
        "direction_id": direction_id,
        "step_fraction_h": fraction,
        "sign": int(sign),
        "signed_step_m": int(sign) * fraction * CANONICAL_GRID_SPACING_M,
        "runtime_identity_verified": False,
        "fresh_solver_execution_verified": False,
        "gradient_qualification": False,
        "criteria_registered": False,
    }


def finite_step_response(*, baseline_n: float, candidate_n: float, step_m: float) -> dict[str, Any]:
    """Return a STEP-01 finite response change in N and secant in N/m.

    This secant is an optimizer-step response oracle and is never a gradient
    qualification result.
    """
    if any(isinstance(value, bool) for value in (baseline_n, candidate_n, step_m)):
        raise ValueError("forces and step_m must be numeric values, not booleans")
    baseline, candidate, step = float(baseline_n), float(candidate_n), float(step_m)
    minimum_m = MIN_STEP_FRACTION * CANONICAL_GRID_SPACING_M
    maximum_m = MAX_STEP_FRACTION * CANONICAL_GRID_SPACING_M
    if (not all(isfinite(value) for value in (baseline, candidate, step))
            or not minimum_m <= abs(step) <= maximum_m):
        raise ValueError(
            f"forces must be finite N values and abs(step_m) must be in [{minimum_m}, {maximum_m}]"
        )
    delta_n = candidate - baseline
    return {
        "oracle_id": "STEP-01",
        "oracle_type": "finite_step_response_secant",
        "delta_response_n": delta_n,
        "finite_secant_n_per_m": delta_n / step,
        "signed_step_m": step,
        "gradient_qualification": False,
    }
