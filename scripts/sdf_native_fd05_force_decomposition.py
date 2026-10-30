"""FD-05 (#37) solver-free diagnostic: component and one-sided split of the 33 raw force histories.

Reads the kernel-1 `*.forces.csv` files, converts solver forces to N
(rho U^2 h^2 = 1/900 for flow_24), and reports per run the registered window
(80 <= tU/L <= 120) mean of drag/downforce and their pressure/viscous parts,
the window standard deviation, and the early-time (5 < tU/L < 20) +/- pair
difference.  Diagnostic only; it does not re-judge the registered gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

N_PER_SOLVER = 1.0 / 900.0
WINDOW = (80.0, 120.0)
EARLY = (5.0, 20.0)
KEYS = ("drag_solver", "downforce_solver", "pressure_fx_solver", "viscous_fx_solver",
        "pressure_fz_solver", "viscous_fz_solver")


def load(path: Path) -> np.ndarray:
    return np.genfromtxt(path, delimiter=",", names=True)


def window_mean(a: np.ndarray, key: str, lo: float, hi: float) -> tuple[float, float]:
    w = (a["t_u_l"] >= lo) & (a["t_u_l"] <= hi)
    x = a[key][w] * N_PER_SOLVER
    return float(x.mean()), float(x.std())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel-output", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    runs = sorted(p.name[:-len(".forces.csv")] for p in args.kernel_output.glob("*.forces.csv"))
    data = {r: load(args.kernel_output / f"{r}.forces.csv") for r in runs}
    base = {k: window_mean(data["baseline_A"], k, *WINDOW)[0] for k in KEYS}
    out = {"kind": "sdf_native_fd05_force_decomposition", "evidence_class": "diagnostic_only_solver_free",
           "unit": "N", "window_tUL": WINDOW, "baseline_A_window_mean_N": base, "runs": {}}
    for r in runs:
        rec = {}
        for k in KEYS:
            mean, std = window_mean(data[r], k, *WINDOW)
            rec[k] = {"window_mean_minus_baseline_N": mean - base[k], "window_std_N": std}
        out["runs"][r] = rec
    pairs = {}
    for r in runs:
        if not r.endswith("__plus"):
            continue
        p, m = data[r], data[r[:-len("plus")] + "minus"]
        t = np.linspace(EARLY[0], EARLY[1], 500)
        pairs[r[:-len("__plus")]] = {
            k: {"window_pair_N": out["runs"][r][k]["window_mean_minus_baseline_N"]
                - out["runs"][r[:-len("plus")] + "minus"][k]["window_mean_minus_baseline_N"],
                "early_pair_mean_N": float(np.mean(np.interp(t, p["t_u_l"], p[k]) - np.interp(t, m["t_u_l"], m[k]))
                                           * N_PER_SOLVER)}
            for k in KEYS
        }
    out["pairs_plus_minus"] = pairs
    for name, rec in pairs.items():
        print(name, " ".join(f"{k.split('_solver')[0]}={v['window_pair_N']:+.5f}" for k, v in rec.items()))
    if args.output:
        args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
