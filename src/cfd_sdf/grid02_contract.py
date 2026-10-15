"""GRID-02 contract (plan v2, docs/grid02_plan_2026_10_15.md): grid cases, placements, fits, resolution, pre-registered classification and decision map.  Pure functions, no I/O.

Thresholds are fixed by the registration and never tuned.  Nothing here is a grid-convergence, gradient or qualification claim.
"""
from __future__ import annotations

import math

RESOLUTION_FLOOR_N = 3e-5  # nominal flow_24 value, unmeasured on the other grids
MIN_DOWNFORCE_GAIN_N = 3e-5  # OPT-01 both-grid rule, strictly greater
REFERENCE_LENGTH_M, DENSITY, FREESTREAM = 0.8, 1.0, 1.0
REYNOLDS = 80.0
CELLS = {"flow_16": 16, "flow_24": 24, "flow_32": 32, "flow_48": 48}
DIMS = {"flow_16": (100, 48, 36), "flow_24": (150, 72, 54), "flow_32": (200, 96, 72), "flow_48": (300, 144, 108)}
DESIGN_SPACING_M = 0.025
# native = the OPT-01 canonical SDF origin; shifted = rigid translation (h/2, h/2, 0) of the body against the flow grid (z unshifted: ride height unchanged).  Literals: -0.8 + 0.0125 is not -0.7875 in floats.
PLACEMENTS = {"native": (-1.0, -0.8, -0.6), "shifted": (-0.9875, -0.7875, -0.6)}
PARENT, REPEAT = "opt01b__parent", "opt01b__parent_repeat"
FORWARD_MM, REVERSE_MM = (0.3125, 0.625, 0.9375, 1.25), (0.625, 1.25)
FORWARD = tuple(f"opt01b__prop__s{s:g}mm" for s in FORWARD_MM)
REVERSE = tuple(f"opt01b__ctrl_reverse__s{s:g}mm" for s in REVERSE_MM)
SEVEN = (PARENT,) + FORWARD + REVERSE
JOB_C, JOB_F32, JOB_G02 = "scripts/waterlily_xfid_candidate_c_job.jl", "scripts/waterlily_lowdim02_flow32_job.jl", "scripts/waterlily_grid02_job.jl"
# kernel -> case, placement, ordered states, job, GRID02_CASE env value (only the new job reads it), per-state timeout (s), kernel timeout (s); aggregate cap = states x per-state timeout.
KERNELS = {
    "s24": {"case": "flow_24", "placement": "shifted", "states": SEVEN, "job": JOB_C, "grid02_case": None, "per_state_timeout_s": 900, "kernel_timeout_s": 10800},
    "s32": {"case": "flow_32", "placement": "shifted", "states": SEVEN, "job": JOB_F32, "grid02_case": None, "per_state_timeout_s": 900, "kernel_timeout_s": 10800},
    "f48a": {"case": "flow_48", "placement": "native", "states": (PARENT,) + FORWARD[:3], "job": JOB_G02, "grid02_case": "flow_48", "per_state_timeout_s": 4500, "kernel_timeout_s": 21600},
    "f48b": {"case": "flow_48", "placement": "native", "states": (REPEAT, FORWARD[3], REVERSE[1]), "job": JOB_G02, "grid02_case": "flow_48", "per_state_timeout_s": 4500, "kernel_timeout_s": 21600},
    "f16": {"case": "flow_16", "placement": "native", "states": SEVEN + (REPEAT,), "job": JOB_G02, "grid02_case": "flow_16", "per_state_timeout_s": 900, "kernel_timeout_s": 10800},
}
ALIGNMENT = ("GRID02_ALIGNMENT_DOMINANT", "GRID02_ALIGNMENT_NEGLIGIBLE", "GRID02_ALIGNMENT_PARTIAL_OR_MIXED")
FINE = ("FINE_CONTINUES_TO_FLOW32", "FINE_REVERSES_TOWARD_FLOW24", "FINE_INTERMEDIATE")
DECISIONS = {
    "dominant": "the dual-grid disagreement is a placement artifact; next = register a placement-robust evaluation (native + shifted average) before any new accept rule; no basis expansion.",
    "negligible_stable": "flow_32 is a stable working map for this response (slope changes < 30% from 32 to 48); next = proposals on flow_32 with a flow_48 finalist confirmation, and a separately registered amendment of the dual-grid rule.",
    "negligible_unstable": "no affordable grid gives a stable sub-5 mm slope; next = larger-step / coarser-design-lattice study (solver-free preparation first).",
    "partial": "a second placement phase study (other x/y phases, and z at a registered ride-height tolerance) before any rule change.",
}


def finite(x, label="value"):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(f"{label} must be a finite number")
    return float(x)


def case_dict(case):
    """The measurement case fields that differ per grid (only the spacing enters the N scale rho U^2 dx^2); dx = 0.8/n, viscosity n/80 (Re 80, L = n, U = 1)."""
    n = CELLS[case]
    dx = REFERENCE_LENGTH_M / n
    return {"case_id": case, "flow_dims": list(DIMS[case]), "flow_spacing_m": dx, "solver_length": float(n), "solver_viscosity": n / REYNOLDS, "solver_time_unit_s": dx}


def force_scale_n(case):
    return DENSITY * FREESTREAM ** 2 * case_dict(case)["flow_spacing_m"] ** 2


def origin_env(placement):
    return ",".join(repr(v) for v in PLACEMENTS[placement])


def aggregate_cap_s(kernel):
    k = KERNELS[kernel]
    return len(k["states"]) * k["per_state_timeout_s"]


def resolution(pair_differences):
    """max(floor, largest |parent-pair difference|); a byte-identical pair measures reproducibility, not noise."""
    return max([RESOLUTION_FLOOR_N] + [abs(finite(d, "pair difference")) for d in pair_differences])


def sign_status(dl, res):
    dl, res = finite(dl, "dL"), finite(res, "resolution")
    return "positive_resolved" if dl > res else "negative_resolved" if dl < -res else "unresolved"


def _lsq(steps, y, powers):
    """Normal-equation least squares y = sum_j c_j s^p_j (tiny systems; Gaussian elimination with partial pivoting)."""
    s, y = [finite(v, "step") for v in steps], [finite(v, "dL") for v in y]
    if len(s) != len(y) or len(set(s)) < len(powers):
        raise ValueError("need matching lists with at least as many distinct steps as coefficients")
    m = len(powers)
    A = [[sum(v ** (p + q) for v in s) for q in powers] + [sum(yy * v ** p for v, yy in zip(s, y))] for p in powers]
    for i in range(m):
        piv = max(range(i, m), key=lambda r: abs(A[r][i]))
        A[i], A[piv] = A[piv], A[i]
        if A[i][i] == 0:
            raise ValueError("singular fit")
        for r in range(i + 1, m):
            f = A[r][i] / A[i][i]
            A[r] = [x - f * z for x, z in zip(A[r], A[i])]
    c = [0.0] * m
    for i in reversed(range(m)):
        c[i] = (A[i][m] - sum(A[i][j] * c[j] for j in range(i + 1, m))) / A[i][i]
    return c, max(abs(yy - sum(ci * v ** p for ci, p in zip(c, powers))) for v, yy in zip(s, y))


def fit_quadratic(steps_mm, dl_n):
    """dL = b s + a s^2 (s in mm, no intercept).  Zero crossing b/|a| and attainable gain b^2/(2|a|) only when a < 0 and b > 0 (a forward gain exists); else None with the reason."""
    (b, a), res = _lsq(steps_mm, dl_n, (1, 2))
    out = {"b_n_per_mm": b, "a_n_per_mm2": a, "max_residual_n": res, "zero_crossing_mm": None, "attainable_gain_n": None}
    if a >= 0:
        out["attainable_reason"] = "unbounded in range"
    elif b <= 0:
        out["attainable_reason"] = "no forward gain (b <= 0)"
    else:
        out["zero_crossing_mm"], out["attainable_gain_n"], out["attainable_reason"] = b / abs(a), b * b / (2 * abs(a)), "a < 0"
    return out


def fit_with_intercept(steps_mm, dl_n):
    """Check fit dL = c + b s + a s^2; needs at least three distinct steps (include the parent point s = 0)."""
    (c, b, a), res = _lsq(steps_mm, dl_n, (0, 1, 2))
    return {"c_n": c, "b_n_per_mm": b, "a_n_per_mm2": a, "max_residual_n": res}


def alignment_classification(b_24n, b_24s, b_32n, b_32s):
    """G = b_32n - b_24n; m24 = (b_24s - b_24n)/G; m32 = (b_32n - b_32s)/G.  G == 0 or any non-finite input: ValueError, never classified."""
    b24n, b24s, b32n, b32s = (finite(v, "slope") for v in (b_24n, b_24s, b_32n, b_32s))
    g = b32n - b24n
    if g == 0 or not math.isfinite(g):
        raise ValueError("gap G = b_32n - b_24n is zero or non-finite")
    m24, m32 = (b24s - b24n) / g, (b32n - b32s) / g
    cls = ALIGNMENT[0] if m24 >= 0.5 and m32 >= 0.5 else ALIGNMENT[1] if abs(m24) <= 0.2 and abs(m32) <= 0.2 else ALIGNMENT[2]
    return {"G": g, "m24": m24, "m32": m32, "classification": cls}


def fine_classification(b_24n, b_32n, b_48n):
    """r = (b_48n - b_24n)/G; r >= 0.5 continues to flow_32, r <= 0.2 reverses toward flow_24, else intermediate; STABLE_32_TO_48 iff |b_48n - b_32n| <= 0.3 |b_32n|."""
    b24, b32, b48 = (finite(v, "slope") for v in (b_24n, b_32n, b_48n))
    g = b32 - b24
    if g == 0 or not math.isfinite(g):
        raise ValueError("gap G = b_32n - b_24n is zero or non-finite")
    r = (b48 - b24) / g
    return {"G": g, "r": r, "classification": FINE[0] if r >= 0.5 else FINE[1] if r <= 0.2 else FINE[2], "stable_32_to_48": abs(b48 - b32) <= 0.3 * abs(b32)}


def decision_text(alignment, fine, stable):
    """The registered decision-map sentence; the map branches on the alignment class and STABLE_32_TO_48 only (fine is validated, reported, and not used)."""
    if alignment not in ALIGNMENT or fine not in FINE or type(stable) is not bool:
        raise ValueError("unknown alignment/fine class or non-boolean stable flag")
    key = {ALIGNMENT[0]: "dominant", ALIGNMENT[2]: "partial"}.get(alignment) or ("negligible_stable" if stable else "negligible_unstable")
    return f"{alignment}: {DECISIONS[key]}"


def both_grid_rule(dl_by_grid, dd_by_grid):
    """Descriptive OPT-01 rule for one step: downforce gain > 3e-5 N and drag change <= 0 on EVERY listed grid (no small-drag margin, no gates, no selection)."""
    if not dl_by_grid or set(dl_by_grid) != set(dd_by_grid):
        raise ValueError("dL and dD must list the same non-empty grids")
    per = {g: {"gain_ok": finite(dl_by_grid[g], "dL") > MIN_DOWNFORCE_GAIN_N, "drag_ok": finite(dd_by_grid[g], "dD") <= 0} for g in dl_by_grid}
    return {"per_grid": per, "pass": all(v["gain_ok"] and v["drag_ok"] for v in per.values())}
