"""Host-side analysis of the X2 grid-phase probe (method fixed in x2_criteria.json).

Usage: analyze_xfid_gridphase_x2.py <result.json> [out.json]. Reports; adopts no floor.
"""

import json
import sys
from pathlib import Path

import numpy as np

RESPONSES = ("drag_n", "downforce_n")


def analyze(result):
    done = {c["id"]: c for c in result["cases"] if c.get("status") == "COMPLETED" and "forces" in c}
    out = {"cases_completed": len(done), "cases_total": len(result["cases"]),
           "not_run_or_failed": {c["id"]: c["status"] for c in result["cases"] if c["id"] not in done}}
    base = [done[k] for k in ("baseline", "baseline_repeat") if k in done]
    out["baseline_repeat_difference_n"] = {r: abs(base[0]["forces"][r]["window_mean"] - base[1]["forces"][r]["window_mean"]) for r in RESPONSES} if len(base) == 2 else None
    out["axes"] = {}
    for axis in "xyz":
        pts = [(0.0, b) for b in base] + [(c["shift_m"] * 1000, c) for c in done.values() if c["axis"] == axis and c["shift_m"] != 0]
        per = {}
        for r in RESPONSES:
            s = np.array([p[0] for p in pts]); y = np.array([p[1]["forces"][r]["window_mean"] for p in pts])
            if len(set(s)) < 4:
                per[r] = "too few distinct shifts"
                continue
            coef = np.polyfit(s, y, 2); res = y - np.polyval(coef, s)
            odd_even = {}
            for m in sorted({abs(v) for v in s if v}):
                if m in s and -m in s:
                    yp, ym = y[s == m][0], y[s == -m][0]
                    odd_even[str(m)] = {"odd_n": (yp - ym) / 2, "even_n": (yp + ym) / 2 - y[s == 0].mean()}
            order = np.argsort(s)
            per[r] = {"slope_n_per_mm": float(coef[1]), "curvature_n_per_mm2": float(coef[0]),
                      "residual_rms_n": float(np.sqrt((res ** 2).mean())), "residual_max_n": float(np.abs(res).max()),
                      "max_consecutive_jump_n": float(np.abs(np.diff(y[order])).max()), "odd_even_by_abs_shift_mm": odd_even}
        out["axes"][axis] = per
    cost = {}
    for st in ("blockMesh", "surfaceFeatureExtract", "snappyHexMesh", "checkMesh", "simpleFoam"):
        rows = [x for c in done.values() for x in c["stages"] if x["stage"] == st]
        if rows:
            peaks = [x["peak_rss_mb_sampled"] for x in rows if x["peak_rss_mb_sampled"] is not None]
            cost[st] = {"wall_s_median": float(np.median([x["wall_s"] for x in rows])), "wall_s_max": float(max(x["wall_s"] for x in rows)),
                        "peak_rss_mb_max": max(peaks) if peaks else None}
    out["cost"] = cost
    out["cells_range"] = [min(c["mesh"]["cells"] for c in done.values()), max(c["mesh"]["cells"] for c in done.values())] if done else None
    return out


if __name__ == "__main__":
    res = analyze(json.loads(Path(sys.argv[1]).read_text()))
    text = json.dumps(res, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text)
    print(text)
