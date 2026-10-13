"""LOWDIM-04A Stage A analysis contract: centered secants at the parent, the dual-grid cone, the verdict.  Pure functions, no I/O.

Forked from `cfd_sdf.grid01_contract` (frozen, not edited): the secant step is a parameter (1.25 mm here; GRID-01 hard-codes 2.5 mm, which would
silently halve every secant) and so is the L1 sensitivity epsilon.  The certified cone solver `solve_cone_family` is reused unchanged.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

import numpy as np

from cfd_sdf.grid01_contract import GRIDS, OPTIMUM_ATOL, solve_cone_family

BASIS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
RESPONSES = ("downforce", "drag")
STEP_M = 0.00125
MIN_RESOLVED_N = 3.0e-5                        # nominal flow_24-derived floor; about 1 sigma of the retained flow_32 response jitter, not a 3 sigma rule
EPSILON_N_PER_M = MIN_RESOLVED_N / (2.0 * STEP_M)   # 0.012 N/m for the +-1.25 mm contrast
MIN_PREDICTED_DOWNFORCE_N = 3.0e-5
TERMINALS = ("LOCAL_FEASIBLE_CONE_FOUND", "LOCAL_FEASIBLE_CONE_NOT_FOUND", "LOWDIM04A_INCOMPLETE")


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} is not a number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} is not finite")
    return number


def secant_sample(r0_n: Any, r_plus_n: Any, r_minus_n: Any, step_m: float = STEP_M) -> dict[str, Any]:
    """Centered secant [R(+s)-R(-s)]/(2s) with its odd/even finite-step parts and the frozen resolution rule."""
    r0, plus, minus = finite(r0_n, "r0"), finite(r_plus_n, "r_plus"), finite(r_minus_n, "r_minus")
    contrast = plus - minus
    even = (plus + minus - 2.0 * r0) / 2.0
    g = contrast / (2.0 * step_m)
    resolved = abs(contrast) > MIN_RESOLVED_N
    return {"r0_n": r0, "r_plus_n": plus, "r_minus_n": minus, "contrast_plus_minus_n": contrast, "g_sec_n_per_m": g, "even_part_n": even,
            "eta_even": abs(2.0 * even) / abs(contrast) if contrast != 0.0 else None, "resolved": resolved,
            "resolved_sign": (1 if g > 0.0 else -1 if g < 0.0 else 0) if resolved else None, "resolution_threshold_n": MIN_RESOLVED_N,
            "resolution_source": "nominal_floor_not_a_flow32_noise_measurement"}


def cosine_and_norm_ratio(a: Any, b: Any) -> dict[str, Any]:
    left, right = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    nl, nr = float(np.linalg.norm(left)), float(np.linalg.norm(right))
    return {"cosine": float(left @ right / (nl * nr)) if nl > 0 and nr > 0 else None, "norm_ratio_right_over_left": nr / nl if nl > 0 else None, "left_l2": nl, "right_l2": nr}


def solve(lift: Any, drag: Any, epsilon: float = EPSILON_N_PER_M) -> dict[str, Any]:
    """Main and L1-robust cross-grid cones plus the four single-grid references, each with the solver's KKT verification."""
    L, D = np.asarray(lift, dtype=np.float64), np.asarray(drag, dtype=np.float64)
    if L.shape != (2, 4) or D.shape != (2, 4) or not (np.all(np.isfinite(L)) and np.all(np.isfinite(D))):
        raise ValueError("lift and drag must be finite 2x4 arrays")
    out = {"main_cross_grid": solve_cone_family(L, D, robust=False, epsilon=epsilon), "robust_cross_grid": solve_cone_family(L, D, robust=True, epsilon=epsilon),
           "single_grid": {g: {"main": solve_cone_family(L, D, robust=False, epsilon=epsilon, one_grid=g),
                               "robust": solve_cone_family(L, D, robust=True, epsilon=epsilon, one_grid=g)} for g in GRIDS}}
    out["all_solutions_verified"] = all(x["verification"]["passed"] for x in (out["main_cross_grid"], out["robust_cross_grid"], *(out["single_grid"][g][k] for g in GRIDS for k in ("main", "robust"))))
    return out


def normalization(coefficients: Any, directions: dict[str, np.ndarray], step_m: float = STEP_M) -> dict[str, Any]:
    """Spatial max-norm rescale: v = sum c_i d_i (float64), m = max|v|, a step s uses basis coefficients (s/m) c_i."""
    c = np.asarray(coefficients, dtype=np.float64)
    v = sum(ci * directions[n].astype(np.float64) for ci, n in zip(c, BASIS))
    m = float(np.max(np.abs(v)))
    if not m > 0:
        if float(np.linalg.norm(c)) > 0:
            raise ValueError("nonzero coefficients give a zero spatial direction")
        # the cone has no positive direction: a zero solution predicts 0 N, which the verdict reports as NOT_FOUND (never INCOMPLETE)
        return {"m_max_abs_sum": 0.0, "step_scale": 0.0, "basis_coefficients_m": [0.0] * len(c), "max_abs_dphi_m": 0.0, "zero_solution": True}
    return {"m_max_abs_sum": m, "step_scale": step_m / m, "basis_coefficients_m": (c * (step_m / m)).tolist(), "max_abs_dphi_m": step_m}


def predictions(solutions: dict[str, Any], lift: Any, drag: Any, directions: dict[str, np.ndarray], epsilon: float = EPSILON_N_PER_M) -> dict[str, Any]:
    """Raw and L1-robust-lower predicted gains at the 1.25 mm step, in newtons, with m computed from the actual arrays."""
    L, D = np.asarray(lift, dtype=np.float64), np.asarray(drag, dtype=np.float64)
    out = {}
    for family in ("main_cross_grid", "robust_cross_grid"):
        c = np.asarray(solutions[family]["coefficient_vector"], dtype=np.float64)
        norm = normalization(c, directions)
        scale, l1 = norm["step_scale"], float(np.linalg.norm(c, ord=1))
        out[family] = {"normalization": norm, "per_grid": {g: {
            "raw_downforce_prediction_n": float(L[i] @ c) * scale,
            "l1_robust_downforce_lower_prediction_n": (float(L[i] @ c) - epsilon * l1) * scale,
            "raw_drag_prediction_n": float(D[i] @ c) * scale,
            "l1_robust_drag_upper_prediction_n": (float(D[i] @ c) + epsilon * l1) * scale} for i, g in enumerate(GRIDS)}}
    return out


def verdict(solutions: dict[str, Any], preds: dict[str, Any]) -> dict[str, Any]:
    """FOUND only if BOTH the main and the L1-robust problems pass (t* above the numeric tolerance and the predicted 1.25 mm downforce above the floor on both grids)."""
    reasons = []
    if not solutions["all_solutions_verified"]:
        reasons.append("a_cone_solution_failed_its_kkt_verification")
    tested = {}
    for family, field in (("main_cross_grid", "raw_downforce_prediction_n"), ("robust_cross_grid", "l1_robust_downforce_lower_prediction_n")):
        t = float(solutions[family]["t_star_n_per_m"])
        if t <= OPTIMUM_ATOL:
            reasons.append(f"{family}_t_star_not_positive_beyond_numeric_tolerance")
        for g in GRIDS:
            value = preds[family]["per_grid"][g][field]
            tested[f"{family}|{g}"] = value
            if value < MIN_PREDICTED_DOWNFORCE_N:
                reasons.append(f"{family}_{g}_prediction_below_3e-5_N")
    return {"verdict": "LOCAL_FEASIBLE_CONE_NOT_FOUND" if reasons else "LOCAL_FEASIBLE_CONE_FOUND", "reasons": reasons, "predictions_tested_n": tested,
            "main_t_star_n_per_m": float(solutions["main_cross_grid"]["t_star_n_per_m"]), "robust_t_star_n_per_m": float(solutions["robust_cross_grid"]["t_star_n_per_m"]),
            "numeric_positive_threshold_n_per_m": OPTIMUM_ATOL, "minimum_downforce_prediction_n": MIN_PREDICTED_DOWNFORCE_N,
            "semantics": "a statement about the linear model under nominal floors, not a gain forecast and not drag nonincrease"}
