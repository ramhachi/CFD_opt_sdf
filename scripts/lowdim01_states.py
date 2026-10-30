"""LOWDIM-01 (#48) state definitions: the coefficient gradient bound from STEP-01, the proposal direction, and the line-search candidates.

Pure numpy; shared by the host registrar and the Kaggle runner.  The perturbation of every candidate is exactly STEP-01's (`step01_states.perturb`).
Nothing here is a gradient qualification: the coefficient gradient is a centered finite difference at +-2.5 mm used ONLY to propose a direction.
"""
from __future__ import annotations

import numpy as np

import step01_states as S

BASIS = S.SINGLE_DIRECTIONS                       # D0_interface_offset, D1_filtered_seed11, D2_filtered_seed2026, P1_upstream_lobe
CANDIDATE_STEP_MM = (1.25, 2.5, 5.0, 7.5)         # max |delta phi| of the candidate along the unit proposal direction
CONTROL_STEP_MM = (1.25, 2.5)                     # CONTROLS: the same steps along the REVERSED proposal direction (never accepted, never selected; they show whether the first-order sign carries information)
FD_STEP_MM = 2.5                                  # the centered finite-difference step of the coefficient gradient (bound from STEP-01)
BASELINE_NAME = "lowdim01__baseline"
PROPOSAL_FILE = "proposal_downforce.dir_f4_fortran.raw"


def candidate_name(step_mm: float) -> str:
    return f"lowdim01__prop__s{step_mm:g}mm"


def control_name(step_mm: float) -> str:
    return f"lowdim01__ctrl_reverse__s{step_mm:g}mm"


def plan() -> list[dict]:
    items = [{"name": BASELINE_NAME, "kind": "baseline", "step_mm": 0.0, "sign": 0}]
    items += [{"name": candidate_name(s), "kind": "candidate", "step_mm": s, "sign": 1} for s in CANDIDATE_STEP_MM]
    items += [{"name": control_name(s), "kind": "control", "step_mm": s, "sign": -1} for s in CONTROL_STEP_MM]
    return items


def coefficient_direction(g: dict[str, float], dirs: dict[str, np.ndarray]) -> tuple[np.ndarray, dict]:
    """Unit proposal direction of maximising the response whose coefficient gradient is `g` (N/m per unit-max-norm basis direction): c = g / ||g||_2 (Euclidean in coefficient
    space), v = sum_i c_i d_i (float64), d_prop = v / max|v| (little-endian float32, max-norm 1).  Returns the direction and the coefficients actually applied per unit step:
    the step s (max |delta phi|) puts the coefficient c_i / m * s on d_i."""
    vec = np.array([g[n] for n in BASIS], dtype=np.float64)
    norm = float(np.linalg.norm(vec))
    if not norm > 0:
        raise ValueError("zero coefficient gradient")
    c = vec / norm
    v = sum(ci * dirs[n].astype(np.float64) for ci, n in zip(c, BASIS))
    m = float(np.max(np.abs(v)))
    out = np.asarray(v / m, dtype="<f4")
    if float(np.max(np.abs(out))) != 1.0:
        raise ValueError("proposal direction is not max-norm 1")
    return out, {"coefficient_unit_vector": {n: float(ci) for n, ci in zip(BASIS, c)}, "m_max_abs_sum": m, "gradient_norm_n_per_m": norm,
                 "per_unit_step_basis_coefficients": {n: float(ci / m) for n, ci in zip(BASIS, c)}}
