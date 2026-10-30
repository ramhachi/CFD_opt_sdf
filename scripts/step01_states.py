"""STEP-01 (#47) state definitions and the numpy perturbation shared by the host registrar and the Kaggle runner.

Pure numpy / hashlib (no cfd_sdf import) so that the runner can import it from a sparse checkout.  The perturbation is exactly the one of
`cfd_sdf.fd08_v2_campaign.construct_state`:  phi_child = float32( float64(phi) + (sign * eps_m) * float64(direction) ),  eps_m = eps_mm / 1000.
Files are little-endian float32, Fortran order, shape (121, 65, 49).  Nothing here is a gradient or a qualification.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

SHAPE = (121, 65, 49)
SPACING_M = 0.025                                       # h
STEP_MM = (2.5, 5.0, 7.5, 10.0, 12.5)                   # 0.1 .. 0.5 h
FRACTIONS_H = (0.1, 0.2, 0.3, 0.4, 0.5)
COMBO_STEP_MM = 7.5                                     # 0.3 h: the largest SDF displacement of a combined direction
SINGLE_DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026", "P1_upstream_lobe")
COMBOS = (("D0_interface_offset", "P1_upstream_lobe"), ("D1_filtered_seed11", "D2_filtered_seed2026"))
KERNELS = {"a": ("D0_interface_offset", "D1_filtered_seed11"), "b": ("D2_filtered_seed2026", "P1_upstream_lobe"), "c": "combos"}
BASELINE_NAME = "step01__baseline"
FD08_BASELINE_CSV_SHA256 = "39370386fd27a7ecd1160a295298798326078a4c5342be07bfb257267a1fbcb3"   # baseline_v17 flow_24.forces.csv: identical bytes in the FD-08 R6 and formal runs


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_f4(path: Path) -> np.ndarray:
    raw = Path(path).read_bytes()
    if len(raw) != int(np.prod(SHAPE)) * 4:
        raise ValueError(f"unexpected byte length: {path}")
    return np.frombuffer(raw, dtype="<f4").reshape(SHAPE, order="F")


def to_raw(array: np.ndarray) -> bytes:
    return np.asarray(array, dtype="<f4").tobytes(order="F")


def perturb(phi: np.ndarray, direction: np.ndarray, step_mm: float, sign: int) -> np.ndarray:
    if sign not in (-1, 1) or not step_mm > 0:
        raise ValueError("sign must be +/-1 and the step positive")
    eps_m = step_mm / 1000.0
    return np.asarray(phi.astype(np.float64) + sign * eps_m * direction.astype(np.float64), dtype="<f4")


def combo_direction(da: np.ndarray, db: np.ndarray) -> tuple[np.ndarray, float]:
    """d_combo = (d_a + d_b) / max|d_a + d_b| (float64 sum and normalisation, then little-endian float32); returns the direction and m = max|d_a + d_b|."""
    total = da.astype(np.float64) + db.astype(np.float64)
    m = float(np.max(np.abs(total)))
    if not m > 0:
        raise ValueError("combined direction is zero")
    out = np.asarray(total / m, dtype="<f4")
    if float(np.max(np.abs(out))) != 1.0:
        raise ValueError("combined direction is not max-norm 1")
    return out, m


def sign_name(sign: int) -> str:
    return "plus" if sign > 0 else "minus"


def single_name(direction: str, step_mm: float, sign: int) -> str:
    return f"step01__{direction}__s{step_mm:g}mm__{sign_name(sign)}"


def combo_name(pair: tuple[str, str], sign: int) -> str:
    return f"step01__combo_{pair[0].split('_')[0]}_{pair[1].split('_')[0]}__s{COMBO_STEP_MM:g}mm__{sign_name(sign)}"


def state_plan(kernel: str) -> list[dict]:
    """The ordered state list of one kernel; the baseline is always first."""
    if kernel not in KERNELS:
        raise ValueError("unknown kernel")
    plan = [{"name": BASELINE_NAME, "kind": "baseline", "directions": [], "step_mm": 0.0, "sign": 0}]
    if kernel == "c":
        for pair in COMBOS:
            for sign in (-1, 1):
                plan.append({"name": combo_name(pair, sign), "kind": "combo", "directions": list(pair), "step_mm": COMBO_STEP_MM, "sign": sign})
    else:
        for direction in KERNELS[kernel]:
            for step in STEP_MM:
                for sign in (-1, 1):
                    plan.append({"name": single_name(direction, step, sign), "kind": "single", "directions": [direction], "step_mm": step, "sign": sign})
    return plan


def all_plans() -> dict[str, list[dict]]:
    return {k: state_plan(k) for k in KERNELS}
