"""LOWDIM-02A (#49) Stage A verdict: does the sign of the LOWDIM-01 accepted +1.25 mm step survive on flow_32?

Solver-free arithmetic on caller-supplied N values (host-recomputed with the flow_32 force scale).  Actual primal responses only; not a gradient qualification, not GRID-01 (#26),
not OPT-01 (#30); no flag is touched.
"""

from __future__ import annotations

from math import isfinite

NOMINAL_SIGMA0_N = 3e-6                    # FD-08's nominal T2 noise scale (flow_24; not a measured noise)
MIN_RESOLVED_N = 10.0 * NOMINAL_SIGMA0_N   # 3e-5 N, the LOWDIM-01 resolution
NOISE_FACTOR = 10.0                        # the flow_32 baseline repeat: resolution is at least 10 x |repeat - baseline|
# the registered flow_32 measurement case (WaterLily flow_spacing = reference length / 32); only the spacing enters the N scale (rho * U^2 * dx^2)
FLOW32_CASE = {"case_id": "flow_32", "flow_dims": [200, 96, 72], "flow_spacing_m": 0.025, "solver_length": 32.0, "solver_viscosity": 0.4, "solver_time_unit_s": 0.025}
VERDICTS = ("STAGE_A_PASS", "STAGE_A_SIGN_FLIP", "STAGE_A_UNRESOLVED", "STAGE_A_CONSTRAINT_FAIL", "STAGE_A_INCOMPLETE")


def resolution_n(noise_n: float) -> float:
    return max(MIN_RESOLVED_N, NOISE_FACTOR * abs(noise_n))


def stage_a_verdict(base: dict, repeat: dict, plus: dict, minus: dict, hard_gates_pass: bool) -> dict:
    """base / repeat / plus / minus: {'downforce_n', 'drag_n'} of the flow_32 baseline, its repeat, +1.25 mm along the proposal and -1.25 mm (reverse control).

    PASS: the +1.25 mm downforce gain is resolved and positive, the drag change is within the drag resolution, the reverse control resolvably LOSES downforce (control < -resolution, so the
    response is not a pure even/curvature response) and the geometry gates pass.  SIGN_FLIP: the forward step resolvably loses downforce (gain = odd + even part: the cause is read from the
    reported odd/even parts, not asserted).  UNRESOLVED: |gain| within the resolution.  CONSTRAINT_FAIL: a resolved gain but the drag, control or gate condition fails."""
    vals = [v[k] for v in (base, repeat, plus, minus) for k in ("downforce_n", "drag_n")]
    if not all(isfinite(float(x)) for x in vals):
        raise ValueError("responses must be finite")
    noise_df = abs(repeat["downforce_n"] - base["downforce_n"])
    noise_dr = abs(repeat["drag_n"] - base["drag_n"])
    res_df, res_dr = resolution_n(noise_df), resolution_n(noise_dr)
    gain = plus["downforce_n"] - base["downforce_n"]
    ctrl = minus["downforce_n"] - base["downforce_n"]
    drag = plus["drag_n"] - base["drag_n"]
    drag_ok = drag <= res_dr
    control_worse = ctrl < -res_df
    odd, even = (gain - ctrl) / 2.0, (gain + ctrl) / 2.0
    out = {"downforce_gain_n": gain, "control_downforce_change_n": ctrl, "drag_change_n": drag, "baseline_repeat_downforce_diff_n": noise_df, "baseline_repeat_drag_diff_n": noise_dr,
           "downforce_resolution_n": res_df, "drag_resolution_n": res_dr,
           "resolution_source": "repeat_noise" if NOISE_FACTOR * noise_df > MIN_RESOLVED_N else "nominal_floor", "odd_part_n": odd, "even_part_n": even, "odd_part_resolved_positive": odd > res_df,
           "marginal": res_df < abs(gain) <= 3.0 * res_df, "drag_constraint_ok": drag_ok, "control_resolvably_loses_downforce": control_worse, "hard_geometry_gates_pass": bool(hard_gates_pass)}
    if gain < -res_df:
        out["verdict"] = "STAGE_A_SIGN_FLIP"
    elif abs(gain) <= res_df:
        out["verdict"] = "STAGE_A_UNRESOLVED"
    else:
        out["verdict"] = "STAGE_A_PASS" if (drag_ok and control_worse and hard_gates_pass) else "STAGE_A_CONSTRAINT_FAIL"
    return out
