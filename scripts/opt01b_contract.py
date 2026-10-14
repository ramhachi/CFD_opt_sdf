"""OPT-01 v1.1 Stage B contract: the LOWDIM-04B ladder rule under the OPT-01 verdict names, and the descriptive hindcast.  Pure functions, no I/O.

`evaluate_candidate` and the constants are reused unchanged from the frozen `cfd_sdf.lowdim03_contract`; the geometry verdict passed in is the contract's pre-CFD
gate verdict for the step (a gate-rejected step is evaluated with False and can never be accepted).  Copy-adapted from the frozen lowdim04b_contract (never edited).
"""
from __future__ import annotations

from cfd_sdf.lowdim03_contract import (DRAG_ALLOWANCE_N, GRIDS, MIN_DOWNFORCE_GAIN_N, RESPONSES, SMALL_DRAG_MARGIN_N, evaluate_candidate, finite)  # noqa: F401
import opt01b_states as L

TERMINALS = ("OPT01_V1_ACCEPT", "OPT01_V1_REJECT", "OPT01_V1_INCOMPLETE")


def select_trial(evaluations: dict, steps_mm: dict) -> dict:
    """Largest minimum actual downforce gain over both grids among the accepted positive steps; exact ties use the smaller step.  None accepted: REJECT."""
    expected = {L.candidate_name(s): s for s in L.STEPS_MM}
    if steps_mm != expected or set(evaluations) != set(expected):
        raise ValueError("selection requires exactly the four registered positive candidates")
    accepted = []
    for name, evaluation in evaluations.items():
        if type(evaluation.get("accepted")) is not bool:
            raise ValueError("candidate accepted field is not a boolean")
        gain = finite(evaluation.get("worst_grid_downforce_gain_n"), "worst-grid gain")
        if evaluation["accepted"]:
            if gain <= MIN_DOWNFORCE_GAIN_N:
                raise ValueError("an accepted candidate must exceed the registered downforce threshold")
            accepted.append((-gain, steps_mm[name], name))
    selected = min(accepted)[2] if accepted else None
    return {"verdict": "OPT01_V1_ACCEPT" if selected else "OPT01_V1_REJECT", "selected": selected, "selected_step_mm": steps_mm[selected] if selected else None,
            "selection_objective": "largest minimum actual downforce gain on both grids; exact ties use the smaller step"}


def hindcast(stage_a: dict, states: dict, step_mm: float) -> dict:
    """Descriptive comparison of the actual change at a positive step with the Stage A linear prediction and its diagonal-curvature estimate.

    stage_a: the OPT-01 Stage A analysis (secants with g_sec_n_per_m and even_part_n per grid/response/direction, and the robust basis coefficients in metres for the 1.25 mm step).
    The diagonal estimate (not a registered model, cross terms ignored) is linear + sum_i (w_i/1.25 mm)^2 even_i at the fraction f = step/1.25 mm of the Stage A step.
    No Stage B outcome was predicted before the run; these numbers are reported for hindcast only.
    """
    f = step_mm / 1.25
    w = [x * f for x in stage_a["predictions_at_1p25mm"]["robust_cross_grid"]["normalization"]["basis_coefficients_m"]]
    out = {}
    for grid in GRIDS:
        out[grid] = {}
        for q in RESPONSES:
            sec = stage_a["secants"][grid][q]
            linear = sum(sec[d]["g_sec_n_per_m"] * wi for d, wi in zip(L.BASIS, w))
            quad = sum(sec[d]["even_part_n"] * (wi / 0.00125) ** 2 for d, wi in zip(L.BASIS, w))
            actual = states[grid][L.candidate_name(step_mm)][f"{q}_n"] - states[grid][L.PARENT_NAME][f"{q}_n"]
            out[grid][q] = {"actual_change_n": actual, "stage_a_linear_prediction_n": linear, "stage_a_diagonal_curvature_estimate_n": linear + quad,
                            "actual_over_linear": actual / linear if abs(linear) > 0 else None}
    return out


def pair_parts(states: dict, step_mm: float) -> dict:
    """Odd and even parts of the +step / -step pair relative to the parent (the reverse diagnostics exist at 0.625 and 1.25 mm)."""
    out = {}
    for grid in GRIDS:
        out[grid] = {}
        for q in RESPONSES:
            base = states[grid][L.PARENT_NAME][f"{q}_n"]
            plus = states[grid][L.candidate_name(step_mm)][f"{q}_n"] - base
            minus = states[grid][L.control_name(step_mm)][f"{q}_n"] - base
            out[grid][q] = {"forward_change_n": plus, "reverse_change_n": minus, "odd_part_n": (plus - minus) / 2, "even_part_n": (plus + minus) / 2}
    return out
