"""Summarize the fixed FD-07 CPU matrix descriptively, without a qualification gate."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

FORCE_SCALE_N = 1.0 / 900.0  # rho=1, U=1, flow spacing=0.8/24 m.
FORCES = {"drag": "drag_solver", "downforce": "downforce_solver"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def window_mean(times, values, start=2.0, end=3.0) -> float:
    """Integrate the piecewise linear history after clipping to exact endpoints."""
    times, values = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
    if (times.ndim != 1 or times.shape != values.shape or times.size < 2
            or not np.isfinite(times).all() or not np.isfinite(values).all()
            or not np.all(times > 0) or not np.all(np.diff(times) > 0)):
        raise ValueError("history requires finite, positive, strictly increasing times and finite values")
    if not np.isfinite([start, end]).all() or end <= start:
        raise ValueError("analysis window must have finite ordered endpoints")
    if times[0] > start or times[-1] < end:
        raise ValueError("history does not bracket both analysis-window endpoints")
    clipped_t = np.r_[start, times[(times > start) & (times < end)], end]
    clipped_v = np.interp(clipped_t, times, values)
    return float(np.sum(np.diff(clipped_t) * (clipped_v[:-1] + clipped_v[1:]) / 2) / (end - start))


def summarize(outdir: Path) -> dict:
    target = outdir / "summary.json"
    if target.exists():
        raise FileExistsError(f"diagnostic summary already exists: {target}")
    plan_path = outdir / "plan.json"
    plan = json.loads(plan_path.read_text())
    start, end = plan["solver"]["analysis_window_u_l"]
    hashes = {"plan.json": sha(plan_path)}
    for name in ("runtime.txt", "noise_f8_fortran.raw", "initial_fields_and_realized_noise.csv"):
        hashes[name] = sha(outdir / name)
    lattices = {}
    for lattice in plan["lattice_order"]:
        raw = outdir / lattice / "phi.raw"
        hashes[f"{lattice}/phi.raw"] = sha(raw)
        if hashes[f"{lattice}/phi.raw"] != plan["lattices"][lattice]["raw_sha256"]:
            raise ValueError(f"prepared phi hash differs from preregistration: {lattice}")
        runs = {}
        for run_id in plan["run_order"]:
            path = outdir / lattice / f"{run_id}.csv"
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            times = [float(row["t_u_l"]) for row in rows]
            means = {name: FORCE_SCALE_N * window_mean(times, [float(row[col]) for row in rows], start, end)
                     for name, col in FORCES.items()}
            runs[run_id] = {"window_mean_n": means, "sample_count": len(rows),
                            "sampled_time_bounds_u_l": [min(times), max(times)]}
            hashes[f"{lattice}/{run_id}.csv"] = sha(path)
        baseline = runs["baseline"]["window_mean_n"]
        for run in runs.values():
            run["delta_from_baseline_n"] = {name: run["window_mean_n"][name] - baseline[name] for name in FORCES}
        pairs = {}
        for scale in ("1e-8", "1e-7"):
            plus, minus = [runs[f"noise_seed1@{sign}{scale}"]["window_mean_n"] for sign in ("+", "-")]
            pairs[scale] = {name: {"odd_n": (plus[name] - minus[name]) / 2,
                                  "even_n": (plus[name] + minus[name]) / 2 - baseline[name]} for name in FORCES}
        ratios = {name: {part: (pairs["1e-7"][name][part] / pairs["1e-8"][name][part]
                               if pairs["1e-8"][name][part] != 0 else None)
                        for part in ("odd_n", "even_n")} for name in FORCES}
        lattices[lattice] = {"runs": runs, "noise_pairs": pairs, "signed_ratio_1e_minus7_over_1e_minus8": ratios}
    summary = {"kind": "fd07_lattice_phase_cpu_diagnostic_summary", "evidence_class": "diagnostic_only",
               "window_u_l": [start, end], "integration": "piecewise linear exact-window trapezoid",
               "force_scale_n_per_solver_force": FORCE_SCALE_N, "input_sha256": hashes,
               "analysis_script_sha256": sha(Path(__file__)), "lattices": lattices,
               "ratio_note": "descriptive signed ratios for a 10x amplitude change; null means zero denominator; no pass/fail threshold",
               "limitations": plan["limitations"],
               "flags": {"shape_update_allowed": False, "sdf_gradient_qualified": False, "canonical_registered": False}}
    payload = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    # Exclusive creation preserves prior summaries, including simultaneous invocations.
    with target.open("x") as handle:
        handle.write(payload)
    return summary


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve()
    result = summarize(directory)
    print(json.dumps({"summary_sha256": sha(directory / "summary.json"), "lattices": result["lattices"]}, indent=2))
