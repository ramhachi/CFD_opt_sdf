"""GRID-01 (#26) finite-step secant and solver-free four-dimensional proposals.

The secants are descriptive finite-step measurements.  The proposal solver is
an exhaustive float64 active-set solution of homogeneous convex cone problems;
it does not use a local nonlinear optimizer or make a gradient qualification.
"""
from __future__ import annotations

from itertools import combinations, product
from math import isfinite
from typing import Any

from .lowdim02a_contract import FLOW32_CASE

import numpy as np

BASIS = (
    "D0_interface_offset",
    "D1_filtered_seed11",
    "D2_filtered_seed2026",
    "P1_upstream_lobe",
)
GRIDS = ("flow_24", "flow_32")
RESPONSES = ("downforce", "drag")
STEP_M = 0.0025
PROPOSAL_STEP_M = 0.00125
MIN_RESOLVED_N = 3.0e-5
UNCERTAINTY_N_PER_M = MIN_RESOLVED_N / (2.0 * STEP_M)
MIN_PREDICTED_DOWNFORCE_N = 3.0e-5
KERNEL_TIMEOUT_S = 10800
PER_STATE_TIMEOUT_S = 900
SOLVER_WALL_TIME_CAP_S = 9 * PER_STATE_TIMEOUT_S
GPU_PROBE_TIMEOUT_S = 300
GEOMETRY_GATE_KEYS = frozenset({
    "clearance",
    "masks_and_support_preserved",
    "cell_components_equal_baseline",
    "smoothed_volume_band",
    "eikonal_median_within_limit",
})

# Frozen numerical policy for the finite active-set enumeration.
SOLVER_ID = "float64-exhaustive-orthant-active-set-cone-projection-v1"
FEASIBILITY_ATOL = 1.0e-9
DUAL_ATOL = 1.0e-9
KKT_ATOL = 1.0e-8
OPTIMUM_ATOL = 1.0e-8  # N/m; values at or below this are numerically unresolved.
RANK_ATOL = 1.0e-12


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} is not a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not a number") from exc
    if not isfinite(number):
        raise ValueError(f"{label} is not finite")
    return number


def secant_sample(r0_n: Any, r_plus_n: Any, r_minus_n: Any) -> dict[str, Any]:
    """Return the STEP-01 centered secant and its odd/even finite-step parts."""
    r0 = _finite(r0_n, "r0_n")
    plus = _finite(r_plus_n, "r_plus_n")
    minus = _finite(r_minus_n, "r_minus_n")
    contrast = plus - minus
    even_n = (plus + minus - 2.0 * r0) / 2.0
    resolved = abs(contrast) > MIN_RESOLVED_N
    g = contrast / (2.0 * STEP_M)
    return {
        "r0_n": r0,
        "r_plus_n": plus,
        "r_minus_n": minus,
        "contrast_plus_minus_n": contrast,
        "g_sec_n_per_m": g,
        "even_part_n": even_n,
        "eta_even": abs(2.0 * even_n) / abs(contrast) if contrast != 0.0 else None,
        "resolved": resolved,
        "resolved_sign": (1 if g > 0.0 else -1 if g < 0.0 else 0) if resolved else None,
        "resolution_threshold_n": MIN_RESOLVED_N,
        "resolution_source": "nominal_flow24_floor_not_flow32_noise_measurement",
    }


def component_comparison(flow24: dict[str, Any], flow32: dict[str, Any]) -> dict[str, Any]:
    """Compare two raw secants without assigning signs to unresolved entries."""
    g24 = _finite(flow24["g_sec_n_per_m"], "flow24 g_sec")
    g32 = _finite(flow32["g_sec_n_per_m"], "flow32 g_sec")
    resolved24, resolved32 = flow24["resolved"], flow32["resolved"]
    if not isinstance(resolved24, bool) or not isinstance(resolved32, bool):
        raise ValueError("resolved flags must be booleans")
    if not resolved24 or not resolved32:
        status = "unresolved"
        signs_agree = None
    else:
        signs_agree = (g24 > 0.0) == (g32 > 0.0)
        status = "sign_preserved_resolved" if signs_agree else "sign_flipped_resolved"
    return {
        "flow24_raw_g_sec_n_per_m": g24,
        "flow32_raw_g_sec_n_per_m": g32,
        "flow24_resolved": resolved24,
        "flow32_resolved": resolved32,
        "sign_status": status,
        "resolved_signs_agree": signs_agree,
        "raw_ratio_flow32_over_flow24": g32 / g24 if g24 != 0.0 else None,
        "raw_relative_difference_over_abs_flow24": abs(g32 - g24) / abs(g24) if g24 != 0.0 else None,
        "raw_sign_interpretation_resolved": bool(resolved24 and resolved32),
    }


def cosine_and_norm_ratio(a: Any, b: Any) -> dict[str, Any]:
    left, right = _vector(a, "left vector"), _vector(b, "right vector")
    nl, nr = float(np.linalg.norm(left)), float(np.linalg.norm(right))
    return {
        "cosine": float(np.dot(left, right) / (nl * nr)) if nl > 0.0 and nr > 0.0 else None,
        "flow32_over_flow24_l2_norm": nr / nl if nl > 0.0 else None,
        "flow24_l2_norm": nl,
        "flow32_l2_norm": nr,
        "input_semantics": "raw finite-step secant vectors; component signs remain resolution-scoped",
    }


def _vector(value: Any, label: str) -> np.ndarray:
    out = np.asarray(value, dtype=np.float64)
    if out.shape != (4,) or not np.all(np.isfinite(out)):
        raise ValueError(f"{label} must be a finite four-vector")
    return out


def _constraint_rows(rows: list[tuple[str, np.ndarray]]) -> tuple[list[str], np.ndarray]:
    names: list[str] = []
    normals: list[np.ndarray] = []
    for name, raw in rows:
        row = _vector(raw, f"constraint {name}")
        norm = float(np.linalg.norm(row))
        if norm == 0.0:
            continue
        names.append(name)
        normals.append(row / norm)
    return names, np.stack(normals) if normals else np.zeros((0, 4), dtype=np.float64)


def _projection_certificate(q: np.ndarray, names: list[str], B: np.ndarray) -> dict[str, Any]:
    """Project q onto {c: Bc <= 0} by enumerating independent active sets."""
    valid: list[tuple[float, int, tuple[int, ...], np.ndarray, np.ndarray]] = []
    max_active = min(4, len(names))
    for count in range(max_active + 1):
        for active in combinations(range(len(names)), count):
            if count == 0:
                multipliers = np.zeros(0, dtype=np.float64)
                projected = q.copy()
            else:
                A = B[list(active)]
                if np.linalg.matrix_rank(A, tol=RANK_ATOL) != count:
                    continue
                gram = A @ A.T
                try:
                    multipliers = np.linalg.solve(gram, A @ q)
                except np.linalg.LinAlgError:
                    continue
                if np.any(multipliers < -DUAL_ATOL):
                    continue
                projected = q - A.T @ multipliers
            if len(names) and float(np.max(B @ projected)) > FEASIBILITY_ATOL:
                continue
            if count and float(np.max(np.abs(B[list(active)] @ projected))) > KKT_ATOL:
                continue
            residual = q - (B[list(active)].T @ multipliers if count else 0.0) - projected
            if float(np.linalg.norm(residual, ord=np.inf)) > KKT_ATOL:
                continue
            distance = float(np.linalg.norm(projected - q))
            valid.append((distance, count, active, projected, multipliers))
    if not valid:
        raise ValueError("active-set enumeration found no KKT projection certificate")
    _, _, active, projected, multipliers = min(valid, key=lambda item: (item[0], item[1], item[2]))
    dual_norm = float(np.linalg.norm(projected))
    if dual_norm <= KKT_ATOL:
        # Normalizing roundoff around a zero cone projection can create a unit
        # vector outside the cone, so retain the exact feasible origin.
        projected = np.zeros(4, dtype=np.float64)
        dual_norm = 0.0
    c = projected / dual_norm if dual_norm > 0.0 else np.zeros(4, dtype=np.float64)
    active_names = [names[i] for i in active]
    active_matrix = B[list(active)] if active else np.zeros((0, 4), dtype=np.float64)
    stationarity = q - (active_matrix.T @ multipliers if active else 0.0) - dual_norm * c
    violations = B @ c if len(names) else np.zeros(0, dtype=np.float64)
    return {
        "coefficient_vector": c.tolist(),
        "objective_vector": q.tolist(),
        "constraints": [{"name": n, "normal": row.tolist()} for n, row in zip(names, B)],
        "active_constraints": active_names,
        "multipliers": multipliers.tolist(),
        "dual_norm_upper_bound_n_per_m": dual_norm,
        "branch_objective_n_per_m": float(np.dot(q, c)),
        "max_constraint_violation": max(0.0, float(np.max(violations))) if len(violations) else 0.0,
        "stationarity_residual_inf": float(np.linalg.norm(stationarity, ord=np.inf)),
    }


def _piecewise_branches(
    lift: np.ndarray,
    drag: np.ndarray,
    *,
    robust: bool,
    epsilon: float,
    one_grid: str | None = None,
) -> list[dict[str, Any]]:
    if one_grid is not None:
        grid_index = GRIDS.index(one_grid)
        active_indices = (grid_index,)
    else:
        active_indices = (0, 1)
    orthants = tuple(product((-1.0, 1.0), repeat=4)) if robust else (None,)
    branches = []
    for sigma in orthants:
        for active in active_indices:
            other = 1 - active
            rows: list[tuple[str, np.ndarray]] = []
            if one_grid is None:
                rows.extend((f"drag_{GRIDS[i]}", drag[i]) for i in range(2))
                rows.append((f"min_order_{GRIDS[active]}_le_{GRIDS[other]}", lift[active] - lift[other]))
            else:
                rows.append((f"drag_{one_grid}", drag[active]))
            if robust:
                assert sigma is not None
                sigma_v = np.asarray(sigma, dtype=np.float64)
                rows = [
                    (name, normal + epsilon * sigma_v if name.startswith("drag_") else normal)
                    for name, normal in rows
                ]
                rows.extend((f"orthant_{BASIS[i]}", -sigma_v[i] * np.eye(4)[i]) for i in range(4))
            names, B = _constraint_rows(rows)
            q = lift[active] - epsilon * np.asarray(sigma, dtype=np.float64) if robust else lift[active].copy()
            if one_grid is None:
                branch_id = f"active={GRIDS[active]}"
            else:
                branch_id = f"grid={one_grid}"
            if robust:
                sign_text = "".join("+" if x > 0 else "-" for x in sigma)
                branch_id = f"orthant={sign_text}|{branch_id}"
            branches.append({
                "branch_id": branch_id,
                "objective_vector": q,
                "constraint_names": names,
                "constraint_matrix": B,
                "active_grid_index": active,
                "sigma": sigma,
            })
    return branches


def _family_objective(c: np.ndarray, lift: np.ndarray, epsilon: float, robust: bool, one_grid: str | None) -> float:
    values = lift @ c
    if one_grid is not None:
        value = float(values[GRIDS.index(one_grid)])
        return value - epsilon * float(np.linalg.norm(c, ord=1)) if robust else value
    adjusted = values - epsilon * float(np.linalg.norm(c, ord=1)) if robust else values
    return float(np.min(adjusted))


def solve_cone_family(
    lift: Any,
    drag: Any,
    *,
    robust: bool,
    epsilon: float = UNCERTAINTY_N_PER_M,
    one_grid: str | None = None,
) -> dict[str, Any]:
    """Solve a main or L1-robust problem and provide every branch's KKT proof."""
    L = np.asarray(lift, dtype=np.float64)
    D = np.asarray(drag, dtype=np.float64)
    expected_rows = 1 if one_grid is not None else 2
    if L.shape == (2, 4) and one_grid is not None:
        L = L[[GRIDS.index(one_grid)]]
    if D.shape == (2, 4) and one_grid is not None:
        D = D[[GRIDS.index(one_grid)]]
    if L.shape != (expected_rows, 4) or D.shape != (expected_rows, 4) or not np.all(np.isfinite(L)) or not np.all(np.isfinite(D)):
        raise ValueError("lift and drag inputs must be finite and match the selected grid set")
    eps = _finite(epsilon, "epsilon")
    if eps < 0.0:
        raise ValueError("epsilon must be nonnegative")
    if one_grid is not None and one_grid not in GRIDS:
        raise ValueError(f"unknown grid {one_grid}")
    # Internally index a one-grid problem into the same two-row representation.
    if one_grid is not None:
        lift_full = np.zeros((2, 4), dtype=np.float64)
        drag_full = np.zeros((2, 4), dtype=np.float64)
        idx = GRIDS.index(one_grid)
        lift_full[idx], drag_full[idx] = L[0], D[0]
    else:
        lift_full, drag_full = L, D
    branches = _piecewise_branches(lift_full, drag_full, robust=robust, epsilon=eps, one_grid=one_grid)
    certificates = []
    for branch in branches:
        cert = _projection_certificate(branch["objective_vector"], branch["constraint_names"], branch["constraint_matrix"])
        certificates.append({"branch_id": branch["branch_id"], **cert})
    selected_index = max(range(len(certificates)), key=lambda i: (certificates[i]["dual_norm_upper_bound_n_per_m"], -i))
    selected = certificates[selected_index]
    c = np.asarray(selected["coefficient_vector"], dtype=np.float64)
    objective = _family_objective(c, lift_full, eps, robust, one_grid)
    result = {
        "problem": "single_grid_robust" if robust and one_grid else "single_grid_main" if one_grid else "cross_grid_robust" if robust else "cross_grid_main",
        "robust": robust,
        "grid": one_grid,
        "epsilon_n_per_m": eps if robust else 0.0,
        "t_star_n_per_m": objective,
        "coefficient_vector": c.tolist(),
        "selected_branch_id": selected["branch_id"],
        "branch_certificates": certificates,
        "verification": verify_cone_family(lift_full, drag_full, result=None, robust=robust, epsilon=eps, one_grid=one_grid, generated_certificates=certificates, selected_branch_id=selected["branch_id"], t_star=objective, coefficient_vector=c),
    }
    if not result["verification"]["passed"]:
        raise ValueError("the cone solution failed its independent KKT/optimality verification")
    return result


def verify_cone_family(
    lift: Any,
    drag: Any,
    result: dict[str, Any] | None,
    *,
    robust: bool,
    epsilon: float = UNCERTAINTY_N_PER_M,
    one_grid: str | None = None,
    generated_certificates: list[dict[str, Any]] | None = None,
    selected_branch_id: str | None = None,
    t_star: float | None = None,
    coefficient_vector: Any = None,
) -> dict[str, Any]:
    """Independently check primal, dual, complementarity and all branch bounds."""
    if result is not None:
        generated_certificates = result.get("branch_certificates")
        selected_branch_id = result.get("selected_branch_id")
        t_star = result.get("t_star_n_per_m")
        coefficient_vector = result.get("coefficient_vector")
    L = np.asarray(lift, dtype=np.float64)
    D = np.asarray(drag, dtype=np.float64)
    if one_grid is not None:
        idx = GRIDS.index(one_grid)
        if L.shape == (2, 4):
            L = L[[idx]]
        if D.shape == (2, 4):
            D = D[[idx]]
        lf = np.zeros((2, 4), dtype=np.float64); df = np.zeros((2, 4), dtype=np.float64)
        lf[idx], df[idx] = L[0], D[0]
        L, D = lf, df
    if L.shape != (2, 4) or D.shape != (2, 4) or not np.all(np.isfinite(L)) or not np.all(np.isfinite(D)):
        raise ValueError("verification inputs must be finite 2x4 arrays")
    eps = _finite(epsilon, "epsilon")
    expected = _piecewise_branches(L, D, robust=robust, epsilon=eps, one_grid=one_grid)
    if not isinstance(generated_certificates, list) or len(generated_certificates) != len(expected):
        raise ValueError("missing or extra branch certificates")
    by_id = {c.get("branch_id"): c for c in generated_certificates if isinstance(c, dict)}
    if len(by_id) != len(expected) or set(by_id) != {b["branch_id"] for b in expected}:
        raise ValueError("branch certificate identities are incomplete or duplicated")
    max_primal = max_stationarity = max_complementarity = max_bound_gap = 0.0
    upper_bounds: dict[str, float] = {}
    for branch in expected:
        cert = by_id[branch["branch_id"]]
        q = branch["objective_vector"]
        names, B = branch["constraint_names"], branch["constraint_matrix"]
        recorded_constraints = cert.get("constraints")
        if not isinstance(recorded_constraints, list) or [r.get("name") for r in recorded_constraints] != names:
            raise ValueError(f"{branch['branch_id']}: constraint set mismatch")
        recorded_B = np.asarray([r.get("normal") for r in recorded_constraints], dtype=np.float64).reshape((-1, 4))
        if recorded_B.shape != B.shape or not np.allclose(recorded_B, B, rtol=0.0, atol=1.0e-12):
            raise ValueError(f"{branch['branch_id']}: constraint normals mismatch")
        if not np.allclose(_vector(cert.get("objective_vector"), "certificate objective"), q, rtol=0.0, atol=1.0e-12):
            raise ValueError(f"{branch['branch_id']}: objective vector mismatch")
        c = _vector(cert.get("coefficient_vector"), "certificate coefficients")
        active_names = cert.get("active_constraints")
        multipliers = np.asarray(cert.get("multipliers"), dtype=np.float64)
        if not isinstance(active_names, list) or len(active_names) != len(multipliers) or not np.all(np.isfinite(multipliers)):
            raise ValueError(f"{branch['branch_id']}: invalid active-set multipliers")
        if len(set(active_names)) != len(active_names) or any(name not in names for name in active_names):
            raise ValueError(f"{branch['branch_id']}: unknown or repeated active constraint")
        active_rows = np.stack([B[names.index(name)] for name in active_names]) if active_names else np.zeros((0, 4))
        nu = _finite(cert.get("dual_norm_upper_bound_n_per_m"), "dual norm upper bound")
        if nu < -DUAL_ATOL or np.any(multipliers < -DUAL_ATOL):
            raise ValueError(f"{branch['branch_id']}: negative dual value")
        violation = B @ c if len(names) else np.zeros(0)
        primal_error = max(0.0, float(np.max(violation))) if len(violation) else 0.0
        norm_c = float(np.linalg.norm(c))
        if primal_error > FEASIBILITY_ATOL or norm_c > 1.0 + FEASIBILITY_ATOL:
            raise ValueError(f"{branch['branch_id']}: primal constraints fail")
        stationarity = q - (active_rows.T @ multipliers if len(active_names) else 0.0) - nu * c
        stationarity_error = float(np.linalg.norm(stationarity, ord=np.inf))
        slack = B @ c if len(names) else np.zeros(0)
        active_lambda = {name: float(value) for name, value in zip(active_names, multipliers)}
        comp_linear = max((abs(active_lambda[n] * float(slack[names.index(n)])) for n in active_names), default=0.0)
        comp_ball = abs(nu * (1.0 - norm_c))
        complementarity = max(comp_linear, comp_ball)
        primal_value = float(np.dot(q, c))
        bound_gap = abs(primal_value - nu)
        if stationarity_error > KKT_ATOL or complementarity > KKT_ATOL or bound_gap > KKT_ATOL:
            raise ValueError(f"{branch['branch_id']}: KKT certificate fails")
        if abs(float(cert.get("branch_objective_n_per_m")) - primal_value) > KKT_ATOL:
            raise ValueError(f"{branch['branch_id']}: branch objective mismatch")
        upper_bounds[branch["branch_id"]] = nu
        max_primal = max(max_primal, primal_error, max(0.0, norm_c - 1.0))
        max_stationarity = max(max_stationarity, stationarity_error)
        max_complementarity = max(max_complementarity, complementarity)
        max_bound_gap = max(max_bound_gap, bound_gap)
    if selected_branch_id not in upper_bounds:
        raise ValueError("selected branch is missing")
    max_upper = max(upper_bounds.values())
    if upper_bounds[selected_branch_id] < max_upper - KKT_ATOL:
        raise ValueError("selected branch is not globally optimal over the exhaustive partition")
    selected_cert = by_id[selected_branch_id]
    c_selected = _vector(coefficient_vector, "selected coefficients")
    if not np.allclose(c_selected, selected_cert["coefficient_vector"], rtol=0.0, atol=FEASIBILITY_ATOL):
        raise ValueError("selected coefficients differ from their branch certificate")
    objective = _family_objective(c_selected, L, eps, robust, one_grid)
    if abs(_finite(t_star, "t_star") - objective) > KKT_ATOL or abs(objective - upper_bounds[selected_branch_id]) > KKT_ATOL:
        raise ValueError("reported optimum differs from the verified primal/dual optimum")
    return {
        "passed": True,
        "method": "independent primal-dual KKT verification over every active-grid and sign-orthant branch",
        "branch_count": len(expected),
        "global_upper_bound_n_per_m": max_upper,
        "selected_branch_upper_bound_n_per_m": upper_bounds[selected_branch_id],
        "max_primal_violation": max_primal,
        "max_stationarity_residual_inf": max_stationarity,
        "max_complementarity_residual": max_complementarity,
        "max_primal_dual_gap_n_per_m": max_bound_gap,
        "tolerances": {
            "feasibility_atol": FEASIBILITY_ATOL,
            "dual_atol": DUAL_ATOL,
            "kkt_atol": KKT_ATOL,
            "rank_atol": RANK_ATOL,
        },
    }


def solve_cross_grid_proposals(lift: Any, drag: Any) -> dict[str, Any]:
    """Solve main/robust cross-grid cones and the registered single-grid references."""
    L, D = np.asarray(lift, dtype=np.float64), np.asarray(drag, dtype=np.float64)
    if L.shape != (2, 4) or D.shape != (2, 4) or not np.all(np.isfinite(L)) or not np.all(np.isfinite(D)):
        raise ValueError("cross-grid lift and drag must be finite 2x4 arrays")
    main = solve_cone_family(L, D, robust=False)
    robust = solve_cone_family(L, D, robust=True)
    single = {
        grid: {
            "main": solve_cone_family(L, D, robust=False, one_grid=grid),
            "robust": solve_cone_family(L, D, robust=True, one_grid=grid),
        }
        for grid in GRIDS
    }
    no_drag_norms = {grid: float(np.linalg.norm(L[i])) for i, grid in enumerate(GRIDS)}
    for i, grid in enumerate(GRIDS):
        for label in ("main", "robust"):
            value = single[grid][label]["t_star_n_per_m"]
            single[grid][label]["unconstrained_downforce_norm_n_per_m"] = no_drag_norms[grid]
            single[grid][label]["retention_of_unconstrained_downforce"] = value / no_drag_norms[grid] if no_drag_norms[grid] > 0 else None
    return {
        "solver_id": SOLVER_ID,
        "solver_description": "Exhaustively partition the homogeneous convex problem by the active minimum-lift grid and, for robust L1 terms, all 16 coefficient sign orthants. Each branch is solved by enumerating linearly independent active sets (size <= 4) for Euclidean projection onto a polyhedral cone. Float64 primal-dual KKT certificates prove each branch optimum; the maximum over the exhaustive branches proves the global optimum.",
        "normalization": "coefficient c is constrained by ||c||_2 <= 1; spatial direction v=sum_i c_i d_i is normalized by its actual m=max(abs(v)); a step s uses basis coefficients (s/m)c_i.",
        "robust_uncertainty_epsilon_n_per_m": UNCERTAINTY_N_PER_M,
        "main_cross_grid": main,
        "robust_cross_grid": robust,
        "single_grid_references": single,
        "all_solutions_verified": all(x["verification"]["passed"] for x in (main, robust, *(single[g][k] for g in GRIDS for k in ("main", "robust")))),
    }
