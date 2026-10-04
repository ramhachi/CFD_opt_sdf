"""Final XFID-01 verdict: WaterLily-C side (recomputed independently from raw force CSVs) + OpenFOAM analysis.

Usage: xfid_final_verdict.py <waterlily_output_dir> <openfoam_analysis.json> [out.json]
The OpenFOAM analysis comes from scripts/analyze_xfid_formal_openfoam.py --unblind, which may only be run after
XFID part B is registered. Rules are those of part A (formal x3_criteria.json); this script adds none.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_xfid_formal_openfoam import DIRECTIONS, verdict  # noqa: E402

FLOW24_SPACING_M = 0.8 / 24
FORCE_SCALE_N = 1.0 * 1.0 ** 2 * FLOW24_SPACING_M ** 2  # rho * U^2 * dx^2 for the flow_24 solver units
WINDOW = (80.0, 120.0)
ABS_FLOOR_N = 1e-8


def window_mean(csv_path, column):
    """Independent trapezoidal mean over the exact [80,120] window with linear endpoint interpolation."""
    with Path(csv_path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    t = np.array([float(r["t_u_l"]) for r in rows])
    y = np.array([float(r[column]) for r in rows])
    assert t[0] <= WINDOW[0] and t[-1] >= WINDOW[1], "force samples do not bracket the window"
    grid = np.concatenate([[WINDOW[0]], t[(t > WINDOW[0]) & (t < WINDOW[1])], [WINDOW[1]]])
    vals = np.interp(grid, t, y)
    return float(np.trapezoid(vals, grid) / (grid[-1] - grid[0]))


def waterlily_forces(out_dir, name):
    path = Path(out_dir) / "states" / name / "flow_24.forces.csv"
    return {"drag_n": window_mean(path, "drag_solver") * FORCE_SCALE_N,
            "downforce_n": window_mean(path, "downforce_solver") * FORCE_SCALE_N}


def waterlily_contrasts(out_dir, result):
    states = result["states"]
    ok = {n: s.get("status") == "COMPLETED" for n, s in states.items()}
    base, rep = waterlily_forces(out_dir, "baseline"), waterlily_forces(out_dir, "baseline_repeat")
    contrasts = {}
    for r in ("drag_n", "downforce_n"):
        floor = max(ABS_FLOOR_N, 3 * abs(base[r] - rep[r]))
        for d in DIRECTIONS:
            if not (ok.get(f"{d}_plus") and ok.get(f"{d}_minus")):
                contrasts[f"{d}:{r}"] = {"S_n": 0.0, "floor_n": float("inf"), "state_failed": True}
                continue
            p, m = waterlily_forces(out_dir, f"{d}_plus")[r], waterlily_forces(out_dir, f"{d}_minus")[r]
            contrasts[f"{d}:{r}"] = {"S_n": (p - m) / 2, "floor_n": floor}
    return contrasts


if __name__ == "__main__":
    out_dir = Path(sys.argv[1])
    result = json.loads((out_dir / "result.json").read_text())
    openfoam = json.loads(Path(sys.argv[2]).read_text())
    wl = waterlily_contrasts(out_dir, result)
    # cross-check against the runner's own host recomputation
    for name, s in result["states"].items():
        if s.get("status") == "COMPLETED":
            mine = waterlily_forces(out_dir, name)
            assert abs(mine["drag_n"] - s["forces_n"]["drag_time_weighted_n"]) < 1e-9 * max(1.0, abs(mine["drag_n"])) + 1e-12, name
    final = {"verdict": verdict(openfoam, wl), "waterlily_contrasts": wl, "openfoam_contrasts": openfoam["contrasts"]}
    text = json.dumps(final, indent=2, sort_keys=True, default=str) + "\n"
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text)
    print(text)
