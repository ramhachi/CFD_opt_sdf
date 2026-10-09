"""LOWDIM-03: actual-primal joint feasibility for one frozen 4D direction.

Reverse states and model agreement are diagnostics, never acceptance gates.
Strict computed drag nonincrease does not establish noise-resolved or physical
nonincrease. No optimizer, gradient or shape-update qualification is changed.
"""
from __future__ import annotations

import math
from typing import Any

GRIDS = ("flow_24", "flow_32")
RESPONSES = ("downforce", "drag")
STEPS_MM = (0.625, 1.25, 2.5)
BASELINE_NAME = "lowdim03__baseline"
MIN_DOWNFORCE_GAIN_N = 3e-5
DRAG_ALLOWANCE_N = 0.0
SMALL_DRAG_MARGIN_N = 3e-5  # nominal diagnostic floor, not measured noise
PREDICTION_DENOMINATOR_FLOOR_N = 0.0
GEOMETRY_GATE_KEYS = frozenset({
    "clearance", "masks_and_support_preserved", "cell_components_equal_baseline",
    "smoothed_volume_band", "eikonal_median_within_limit",
})
QUALIFICATION_FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer",
                       "topology", "shape_update_allowed")
RULES = {"downforce_gain_strictly_greater_than_n": MIN_DOWNFORCE_GAIN_N,
         "drag_change_at_most_n": DRAG_ALLOWANCE_N, "small_drag_margin_n": SMALL_DRAG_MARGIN_N,
         "selection": "max min actual downforce gain over both grids; exact ties choose smaller step",
         "reverse_controls": "diagnostic only; excluded from selection"}


def finite(value: Any, label: str) -> float:
    """Trust-boundary numbers must be JSON numeric values, never booleans."""
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a finite number (not a boolean)")
    return float(value)


def state_name(step_mm: float, sign: int) -> str:
    step = finite(step_mm, "step_mm")
    if step not in STEPS_MM or type(sign) is not int or sign not in (-1, 1):
        raise ValueError("state must have a registered step and an integer +/-1 sign")
    prefix = "prop" if sign == 1 else "ctrl_reverse"
    return f"lowdim03__{prefix}__s{step:g}mm"


def state_plan() -> list[dict[str, Any]]:
    return [{"name": BASELINE_NAME, "kind": "baseline", "step_mm": 0.0, "sign": 0}] + [
        {"name": state_name(step, sign), "kind": "candidate" if sign == 1 else "control",
         "step_mm": step, "sign": sign}
        for sign in (1, -1) for step in STEPS_MM
    ]


def geometry_pass(record: Any) -> bool:
    if not isinstance(record, dict) or not isinstance(record.get("gates"), dict):
        raise ValueError("geometry gate record is missing or malformed")
    gates = record["gates"]
    if set(gates) != GEOMETRY_GATE_KEYS or any(type(v) is not bool for v in gates.values()):
        raise ValueError("geometry gates must be the exact five boolean fields")
    passed = all(gates.values())
    if type(record.get("all_hard_gates_pass")) is not bool or record["all_hard_gates_pass"] != passed:
        raise ValueError("geometry aggregate differs from the five gates")
    return passed


def evaluate_candidate(baselines: dict, responses: dict, hard_gates_pass: bool) -> dict:
    if type(hard_gates_pass) is not bool or set(baselines) != set(GRIDS) or set(responses) != set(GRIDS):
        raise ValueError("candidate needs both grids and a boolean geometry verdict")
    per_grid = {}
    for grid in GRIDS:
        changes = {q: finite(finite(responses[grid][f"{q}_n"], f"{grid} {q}") -
                            finite(baselines[grid][f"{q}_n"], f"{grid} baseline {q}"), f"{grid} {q} change")
                   for q in RESPONSES}
        gain, drag = changes["downforce"], changes["drag"]
        per_grid[grid] = {
            "downforce_change_n": gain, "drag_change_n": drag,
            "downforce_gain_resolved": gain > MIN_DOWNFORCE_GAIN_N,
            "drag_constraint_ok": drag <= DRAG_ALLOWANCE_N,
            "small_computed_drag_margin": abs(drag) <= SMALL_DRAG_MARGIN_N,
        }
    accepted = hard_gates_pass and all(
        v["downforce_gain_resolved"] and v["drag_constraint_ok"] for v in per_grid.values())
    return {"per_grid": per_grid, "hard_geometry_gates_pass": hard_gates_pass,
            "worst_grid_downforce_gain_n": min(v["downforce_change_n"] for v in per_grid.values()),
            "accepted": accepted}


def select_trial(evaluations: dict, steps_mm: dict) -> dict:
    expected = {state_name(step, 1): step for step in STEPS_MM}
    if steps_mm != expected or set(evaluations) != set(expected):
        raise ValueError("selection requires exactly the three registered positive candidates")
    accepted = []
    for name, evaluation in evaluations.items():
        if type(evaluation.get("accepted")) is not bool:
            raise ValueError("candidate accepted field is not a boolean")
        gain = finite(evaluation.get("worst_grid_downforce_gain_n"), "worst-grid gain")
        if evaluation["accepted"]:
            accepted.append((-gain, steps_mm[name], name))
    selected = min(accepted)[2] if accepted else None
    return {"verdict": "LOWDIM03_ACCEPT" if selected else "LOWDIM03_NO_ACCEPT",
            "selected": selected, "selected_step_mm": steps_mm[selected] if selected else None,
            "selection_objective": "largest minimum actual downforce gain on both grids; exact ties use smaller step"}


def predictions(reference: dict, step_mm: float, sign: int = 1) -> dict:
    step = finite(step_mm, "step_mm")
    if step not in STEPS_MM or type(sign) is not int or sign not in (-1, 1):
        raise ValueError("prediction needs a registered step and integer +/-1 sign")
    m = finite(reference["m_max_abs_sum"], "spatial normalization")
    if m <= 0:
        raise ValueError("spatial normalization must be positive")
    out = {}
    for grid in GRIDS:
        row = reference["per_grid"][grid]
        raw = {q: finite(finite(row[f"raw_{q}_slope_n_per_m"], f"{grid} raw {q} slope") * sign * step / 1000 / m,
                         f"{grid} raw {q} prediction")
               for q in RESPONSES}
        # Sensitivity bounds are frozen references for the forward proposal only;
        # reversing a lower/upper bound by negation would invert its semantics.
        out[grid] = {"raw_downforce_prediction_n": raw["downforce"], "raw_drag_prediction_n": raw["drag"]}
        if sign == 1:
            for q, bound in (("downforce", "lower"), ("drag", "upper")):
                slope = finite(row[f"l1_robust_{q}_{bound}_slope_n_per_m"], f"{grid} robust {q} slope")
                out[grid][f"l1_robust_{q}_{bound}_prediction_n"] = finite(slope * step / 1000 / m, f"{grid} {q} bound")
    return out


def model_diagnostics(baselines: dict, plus: dict, minus: dict, reference: dict, step_mm: float) -> dict:
    """Odd/even finite-step behavior and raw linear agreement on each grid."""
    pred = predictions(reference, step_mm)
    out = {}
    for grid in GRIDS:
        row = {"forward_predictions": pred[grid]}
        for q in RESPONSES:
            base = finite(baselines[grid][f"{q}_n"], f"{grid} baseline {q}")
            gain = finite(plus[grid][f"{q}_n"], f"{grid} plus {q}") - base
            reverse = finite(minus[grid][f"{q}_n"], f"{grid} minus {q}") - base
            odd, even = (gain - reverse) / 2, (gain + reverse) / 2
            raw = pred[grid][f"raw_{q}_prediction_n"]
            row[q] = {"forward_change_n": gain, "reverse_change_n": reverse,
                      "odd_part_n": odd, "even_part_n": even,
                      "combined_direction_secant_n_per_m": odd / (step_mm / 1000),
                      "prediction_error_n": gain - raw}
            if q == "downforce":
                row[q]["rho_actual_over_raw_linear"] = gain / raw if raw > PREDICTION_DENOMINATOR_FLOOR_N else None
                row[q]["rho_denominator_usable"] = raw > PREDICTION_DENOMINATOR_FLOOR_N
                row[q]["rho_reason"] = "raw_prediction_positive" if raw > 0 else "raw_prediction_nonpositive"
        out[grid] = row
    return out
