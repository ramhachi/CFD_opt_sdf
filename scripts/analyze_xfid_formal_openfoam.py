"""OpenFOAM side of the formal XFID analysis (rules fixed in x3_criteria.json, formal mode).

BLIND HOLD: refuses to run on real data unless --unblind is given; that flag may only be used after the
WaterLily-C side is registered as XFID part B. Usage: analyze_xfid_formal_openfoam.py <result.json> --unblind [out.json]
"""

import json
import sys
from pathlib import Path

import numpy as np

DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
RESPONSES = {"drag_n": 1.05e-4, "downforce_n": 5.94e-4}  # calibration sigma_e (X3 calibration), N
K_SE = 3.0
N_CAL_POOL = 8.0  # S standard error from the calibration prior: sigma_e / 8 for 32-phase means


def parse_id(case_id):
    body = case_id[len("frm_"):]
    state, tail = body.rsplit("_", 1)
    return state, tail[:-1], tail[-1]


def analyze(result):
    done = [c for c in result["cases"] if c.get("status") == "COMPLETED" and "forces" in c]
    table = {}
    for c in done:
        state, k, sign = parse_id(c["id"])
        table.setdefault(state, {})[(k, sign)] = c
    out = {"cases_completed": len(done), "cases_total": len(result["cases"]), "contrasts": {}}
    for r, sigma_cal in RESPONSES.items():
        states = [f"{d}_{s}" for d in DIRECTIONS for s in ("minus", "plus")]
        common = sorted(set.intersection(*(set(table.get(s, {})) for s in states))) if all(s in table for s in states) else []
        n = len(common)
        if n < 8:
            out["contrasts"][r] = "too few matched phases"
            continue
        V = np.array([np.array(table[states[0]][key]["shift_m"]) * 1000 for key in common])
        rows, y = [], []
        for si, s in enumerate(states):
            for vi, key in enumerate(common):
                onehot = np.zeros(len(states)); onehot[si] = 1
                rows.append(np.concatenate([onehot, V[vi]]))
                y.append(table[s][key]["forces"][r]["window_mean"])
        X, y = np.array(rows), np.array(y)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        dof = len(y) - X.shape[1]
        s_pooled = float(np.sqrt(((y - X @ coef) ** 2).sum() / dof))
        se = s_pooled * np.sqrt(2.0 / n) / 2
        prior_floor = K_SE * sigma_cal / N_CAL_POOL
        for d in DIRECTIONS:
            mp = np.mean([table[f"{d}_plus"][key]["forces"][r]["window_mean"] for key in common])
            mm = np.mean([table[f"{d}_minus"][key]["forces"][r]["window_mean"] for key in common])
            S = (mp - mm) / 2
            out["contrasts"][f"{d}:{r}"] = {
                "S_n": float(S), "SE_n": float(se), "matched_phases": n, "dof": int(dof), "pooled_residual_std_n": s_pooled,
                "calibration_floor_n": prior_floor, "resolved": bool(abs(S) > K_SE * se and abs(S) > prior_floor),
                "sign": int(np.sign(S))}
    return out


def verdict(openfoam, waterlily):
    """waterlily: {contrast: {"S_n": float, "floor_n": float}}; AGREE / DISAGREE / UNRESOLVED per the registered rule."""
    states = []
    for name, of in openfoam["contrasts"].items():
        wl = waterlily[name]
        wl_res = abs(wl["S_n"]) > wl["floor_n"]
        both = of["resolved"] and wl_res
        states.append("agree" if both and of["sign"] == int(np.sign(wl["S_n"])) else "disagree" if both else "unresolved")
    if "disagree" in states:
        return "DISAGREE"
    return "AGREE" if all(s == "agree" for s in states) and len(states) == 6 else "UNRESOLVED"


if __name__ == "__main__":
    if "--unblind" not in sys.argv:
        sys.exit("BLIND HOLD: pass --unblind only after XFID part B (WaterLily-C side) is registered")
    args = [a for a in sys.argv[1:] if a != "--unblind"]
    res = analyze(json.loads(Path(args[0]).read_text()))
    text = json.dumps(res, indent=2, sort_keys=True) + "\n"
    if len(args) > 1:
        Path(args[1]).write_text(text)
    print(text)
