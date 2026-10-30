"""Host-side analysis of the X3 calibration ensemble (method fixed in x3_criteria.json).

Usage: analyze_xfid_gridphase_x3_calibration.py <result.json> [out.json]. Reports; adopts nothing.
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np

RESPONSES = ("drag_n", "downforce_n")


def analyze(result):
    done = [c for c in result["cases"] if c.get("status") == "COMPLETED" and "forces" in c]
    pairs = {}
    for c in done:  # ids end in <k><p|m>
        pairs.setdefault(c["id"][:-1], {})[c["id"][-1]] = c
    full = {k: v for k, v in pairs.items() if set(v) == {"p", "m"}}
    out = {"cases_completed": len(done), "cases_total": len(result["cases"]), "complete_mirror_pairs": len(full), "responses": {}}
    keys = sorted(full)
    for r in RESPONSES:
        if len(keys) < 4:
            out["responses"][r] = "too few complete mirror pairs"
            continue
        V = np.array([[*np.array(full[k][s]["shift_m"]) * 1000] for k in keys for s in "pm"])
        y = np.array([full[k][s]["forces"][r]["window_mean"] for k in keys for s in "pm"])
        X = np.column_stack([np.ones(len(y)), V])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        res = y - X @ coef
        dof = len(y) - X.shape[1]
        sigma = float(np.sqrt((res ** 2).sum() / dof))
        # balanced splits of mirror pairs into two sets of n/2 pairs
        n = len(keys)
        pm = y.reshape(n, 2)  # per pair: (p, m)
        diffs = []
        for half in itertools.combinations(range(n), n // 2):
            if 0 not in half:  # each split once
                continue
            other = [i for i in range(n) if i not in half]
            diffs.append(pm[list(half)].mean() - pm[other].mean())
        observed = float(np.sqrt(np.mean(np.square(diffs))))
        predicted = sigma * np.sqrt(2.0 / n)
        ratio = observed / predicted
        out["responses"][r] = {
            "ensemble_mean_n": float(y.mean()), "sigma_e_n": sigma, "residual_dof": dof,
            "standard_error_of_mean_n": sigma / np.sqrt(len(y)),
            "linear_translation_n_per_mm": dict(zip("xyz", map(float, coef[1:]))),
            "split_half_rms_observed_n": observed, "split_half_rms_predicted_n": float(predicted),
            "split_half_ratio": float(ratio), "averaging_model_accepted": bool(0.5 <= ratio <= 2.0)}
    return out


if __name__ == "__main__":
    res = analyze(json.loads(Path(sys.argv[1]).read_text()))
    text = json.dumps(res, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text)
    print(text)
