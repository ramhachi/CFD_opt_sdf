#!/usr/bin/env python3
"""Diagnostic-only host recomputation of a directional-FD kernel output from its raw force CSVs, in N.

Applies the registered window (exact, endpoint-interpolated, time-weighted trapezoid), centered slopes and the
registered noise/resolution/plateau rule from the criteria, then compares with the runner's outcome.json.  It does
not replace strict host verification and never changes a gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def window_mean(a, column, lo, hi):
    t, x = a["t_u_l"], a[column]
    xs = np.concatenate([[np.interp(lo, t, x)], x[(t > lo) & (t < hi)], [np.interp(hi, t, x)]])
    ts = np.concatenate([[lo], t[(t > lo) & (t < hi)], [hi]])
    return float(np.trapezoid(xs, ts) / (hi - lo))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--criteria", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True, help="kernel output directory (*.forces.csv, outcome.json)")
    ap.add_argument("--result", type=Path, required=True)
    args = ap.parse_args()
    if args.result.exists():
        raise SystemExit("append-only evidence target already exists")
    crit = json.loads(args.criteria.read_text())
    outdir = args.output_dir
    flow = crit["geometry"]["flow_case"]
    scale = flow["density_kg_m3"] * flow["freestream_mps"][0] ** 2 * flow["flow_spacing_m"] ** 2
    lo, hi = crit["measurement"]["force_window_t_u_l"]
    npp = crit["noise_and_plateau"]

    def response(run_id):
        a = np.genfromtxt(outdir / f"{run_id}.forces.csv", delimiter=",", names=True)
        return {"drag": window_mean(a, "drag_solver", lo, hi) * scale,
                "downforce": window_mean(a, "downforce_solver", lo, hi) * scale,
                "pressure_drag": window_mean(a, "pressure_fx_solver", lo, hi) * scale,
                "viscous_drag": window_mean(a, "viscous_fx_solver", lo, hi) * scale}

    base = [response(f"baseline_{x}") for x in "ABC"]
    noise, med = {}, {}
    for r in ("drag", "downforce"):
        v = [b[r] for b in base]
        med[r] = float(np.median(v))
        noise[r] = max(max(v) - min(v), 1e-8 * max(1.0, abs(med[r])))
    results = {}
    for d in crit["direction_inventory"]:
        results[d] = {}
        for r in ("drag", "downforce"):
            rows = []
            for eps in crit["perturbation"]["epsilon_ladder_m"]:
                ids = {s: [p["case_id"] for p in crit["perturbation_inventory"]
                           if p["direction_id"] == d and p["epsilon_m"] == eps and p["sign"] == s][0] for s in (1, -1)}
                plus, minus = response(ids[1])[r], response(ids[-1])[r]
                pair = plus - minus
                rows.append({"epsilon_m": eps, "plus_n": plus, "minus_n": minus, "pair_signal_n": pair,
                             "centered_derivative_n_per_m": pair / (2 * eps),
                             "resolved": abs(pair) >= npp["resolution_factor"] * noise[r]})
            chosen = [x for x in rows if x["resolved"]][:3]
            ref = float(np.median([x["centered_derivative_n_per_m"] for x in chosen])) if chosen else float("nan")
            dne = noise[r] / min(x["epsilon_m"] for x in chosen) if chosen else float("nan")
            devs = [abs(x["centered_derivative_n_per_m"] - ref) / max(abs(ref), dne) for x in chosen]
            signs = {int(np.sign(x["centered_derivative_n_per_m"])) for x in chosen}
            results[d][r] = {"rows": rows, "reference_derivative_n_per_m": ref, "plateau_deviations": devs,
                             "plateau_max_relative_deviation": max(devs) if devs else None,
                             "resolved_count": sum(x["resolved"] for x in rows),
                             "plateau_pass": bool(len(chosen) >= npp["minimum_resolved_epsilon_count"] and len(signs) == 1
                                                  and max(devs) <= npp["plateau_relative_tolerance"])}
    outcome = json.loads((outdir / "outcome.json").read_text())
    agree = True
    for d, rr in results.items():
        for r, v in rr.items():
            run = outcome["directional_fd_results"][d][r]
            agree &= (run["plateau_pass"] is v["plateau_pass"]
                      and abs(run["plateau_max_relative_deviation"] - v["plateau_max_relative_deviation"]) < 1e-6
                      and abs(run["reference_derivative_n_per_m"] - v["reference_derivative_n_per_m"]) < 1e-6)
    manifest = json.loads((outdir / "sha256.json").read_text())
    files = manifest.get("files", manifest)
    bad = [k for k, h in files.items() if isinstance(h, str) and (outdir / k).is_file()
           and hashlib.sha256((outdir / k).read_bytes()).hexdigest() != h]
    summaries = [json.loads(p.read_text()) for p in sorted(outdir.glob("*.summary.json"))]
    evidence = {
        "schema_version": 1, "kind": "fd_directional_host_recomputation_from_raw", "evidence_class": "diagnostic_only",
        "criteria_id": crit["criteria_id"], "criteria_sha256": crit["criteria_sha256"],
        "unit": "N", "force_scale_n_per_solver": scale,
        "baseline_repeats_n": base, "baseline_median_n": med, "baseline_noise_floor_n": noise,
        "directional_results_n": results,
        "matches_runner_outcome": bool(agree),
        "output_manifest_entries": len(files), "output_manifest_hash_mismatches": bad,
        "run_summaries": len(summaries),
        "all_summaries_normal_floor": sorted({s.get("normal_floor") for s in summaries}),
        "all_plateau_pass": all(v["plateau_pass"] for rr in results.values() for v in rr.values()),
        "note": "Does not replace strict host verification; no gate or threshold is changed.",
    }
    args.result.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    args.result.with_suffix(args.result.suffix + ".sha256").write_text(
        hashlib.sha256(args.result.read_bytes()).hexdigest() + "\n")
    print(json.dumps({k: evidence[k] for k in ("matches_runner_outcome", "output_manifest_hash_mismatches",
          "all_summaries_normal_floor", "all_plateau_pass", "baseline_median_n")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
