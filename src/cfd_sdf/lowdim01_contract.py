"""LOWDIM-01 (#48) accept / reject contract: the ACTUAL primal responses and the hard geometry gates decide; predicted improvements are reference only.

Solver-free arithmetic on caller-supplied N values.  Not a gradient qualification; no flag is touched.
"""

from __future__ import annotations

from math import isfinite

NOMINAL_SIGMA0_N = 3e-6                       # FD-08's nominal T2 noise scale (not a measured noise)
RESOLVED_FACTOR = 10.0
MIN_DOWNFORCE_GAIN_N = RESOLVED_FACTOR * NOMINAL_SIGMA0_N         # an improvement must be resolved: > 3e-5 N
DRAG_ALLOWANCE_N = RESOLVED_FACTOR * NOMINAL_SIGMA0_N             # drag may not exceed the baseline by more than the resolution


def evaluate_candidate(base_downforce_n: float, base_drag_n: float, downforce_n: float, drag_n: float, hard_gates_pass: bool) -> dict:
    vals = (base_downforce_n, base_drag_n, downforce_n, drag_n)
    if not all(isfinite(float(v)) for v in vals):
        raise ValueError("responses must be finite")
    gain = float(downforce_n) - float(base_downforce_n)
    drag_change = float(drag_n) - float(base_drag_n)
    resolved_gain = gain > MIN_DOWNFORCE_GAIN_N
    drag_ok = drag_change <= DRAG_ALLOWANCE_N
    return {"downforce_change_n": gain, "drag_change_n": drag_change, "downforce_gain_resolved": resolved_gain, "drag_constraint_ok": drag_ok, "hard_geometry_gates_pass": bool(hard_gates_pass),
            "accepted": bool(resolved_gain and drag_ok and hard_gates_pass)}


def select_trial(evaluations: dict[str, dict], steps_mm: dict[str, float]) -> dict:
    """The accepted candidate with the largest actual downforce gain (ties: the smaller step).  None accepted -> bounded No-Go."""
    if not evaluations or set(evaluations) != set(steps_mm):
        raise ValueError("a selection needs at least one evaluated candidate and a step for each")
    accepted = [(-e["downforce_change_n"], steps_mm[name], name) for name, e in evaluations.items() if e["accepted"]]
    if not accepted:
        return {"verdict": "LOWDIM_NO_GO", "selected": None}
    accepted.sort()
    return {"verdict": "LOWDIM_ACCEPT", "selected": accepted[0][2]}
