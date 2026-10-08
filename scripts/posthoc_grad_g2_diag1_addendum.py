#!/usr/bin/env python3
"""Post-hoc addendum to G2-DIAG1 (exploratory; outside the registered rules; the DIAG1 freeze/analysis are not modified).

Ledger-based parts are recomputed from the git-tracked gzip ledger; snapshot-based parts need the raw snapshots kept outside git
(``--raw-dir``, default the kernel output download) and are skipped when they are absent."""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / "docs/evidence/grad03_g2_diag1_d0_nonfinite_2026_10_08"
SHAPE = (152, 74, 56, 3)
BOX = {"i_lt": 12, "j_lt": 8, "k_ge": 48}      # 0-based slices: i<12, j<8, k>=48
STAGE_U = ("pre_scale", "predict_bdim", "predict_bc", "predict_exitbc", "project1_gradient", "project1_bc", "correct_bdim", "correct_scale", "correct_bc",
           "project2_gradient", "project2_bc")


def ledger_rows():
    text = gzip.decompress((E / "kernel_output/stage_ledger.csv.gz").read_bytes()).decode()
    return csv.DictReader(io.StringIO(text))


def ledger_part() -> dict:
    gains, rel, solve, iters = {}, {}, {}, {}
    for r in ledger_rows():
        s, st, f = int(r["step"]), r["stage"], r["field"]
        if s == 871 and f in ("u", "u0") and st in STAGE_U:
            gains[st] = float(r["maxabs_tangent"])
        if st in ("project1_rhs", "project1_solve") and f in ("z", "r"):
            solve[(s, st, f)] = (float(r["maxabs_primal"]), float(r["maxabs_tangent"]))
    seq, prev = [], None
    for st in STAGE_U:
        if st in gains:
            seq.append({"stage": st, "max_abs_tangent_u": gains[st], "ratio_to_previous_u_stage": None if prev is None else gains[st] / prev})
            prev = gains[st]
    for s in (100, 300, 400, 500, 700, 800, 845, 849, 850, 870, 900, 1000, 1190):
        z, rr = solve[(s, "project1_rhs", "z")], solve[(s, "project1_solve", "r")]
        rel[s] = {"primal_relative_residual": rr[0] / z[0], "tangent_relative_residual": rr[1] / z[1]}
    pois = list(csv.DictReader((E / "kernel_output/poisson_ledger.csv").open()))
    for r in pois:
        if r["stage"] == "project1_solve":
            iters[int(r["step"])] = (int(r["iters"]), float(r["dt_value"]), float(r["dt_tangent"]))
    first_one = next(s for s in sorted(iters) if all(iters[t][0] == 1 for t in range(s, 1197) if t in iters))
    return {"u_stage_chain_step_871": seq, "net_gain_step_871_start_to_end": gains["project2_bc"] / gains["pre_scale"],
            "poisson_relative_residual": rel, "poisson_iterations_one_from_step": first_one,
            "dt_tangent": {s: iters[s][2] for s in (100, 300, 500, 700, 800, 815, 850, 860, 900, 1000)}, "dt_value_step_800": iters[800][1]}


def snapshot_part(raw: Path) -> dict | None:
    try:
        import numpy as np
    except ImportError:
        return None
    snaps = raw / "snapshots"
    if not (snaps / "step0900.u.dual_f32_interleaved_value_tangent.raw").is_file():
        return None

    def tangent(step):
        a = np.fromfile(snaps / f"step{step:04d}.u.dual_f32_interleaved_value_tangent.raw", dtype="<f4").reshape(-1, 2)
        return a[:, 1].reshape(SHAPE, order="F").astype(np.float64), a[:, 0].reshape(SHAPE, order="F")

    box = (slice(0, BOX["i_lt"]), slice(0, BOX["j_lt"]), slice(BOX["k_ge"], SHAPE[2]))
    out, box_log = {"box": "i<12, j<8, k>=48 (0-based; ghost layers included)", "max_abs_tangent_u": {}, "energy": {}}, {}
    for step in (2, 100, 500, 900, 1000, 1100):
        t = np.abs(tangent(step)[0]).max(axis=3)
        inside, outside = float(t[box].max()), t.copy()
        outside[box] = 0
        box_log[step] = inside
        out["max_abs_tangent_u"][step] = {"in_box": inside, "outside_box": float(outside.max())}
    ii, jj, kk = np.meshgrid(*(np.arange(n) for n in SHAPE[:3]), indexing="ij")
    dist = np.minimum.reduce([ii, SHAPE[0] - 1 - ii, jj, SHAPE[1] - 1 - jj, kk, SHAPE[2] - 1 - kk])
    for step in (900, 1100):
        t, v = tangent(step)
        e = np.abs(t).max(axis=3) ** 2
        tot = e.sum()
        I = np.unravel_index(int(np.argmax(e)), e.shape)
        line = t[max(I[0] - 4, 0):I[0] + 5, I[1], I[2], 0] / np.sqrt(e.max())
        out["energy"][step] = {"fraction_in_box": float(e[box].sum() / tot), "fraction_by_distance_to_nearest_outer_face_cells": {
            f"[{lo},{hi})": float(e[(dist >= lo) & (dist < hi)].sum() / tot) for lo, hi in ((0, 3), (3, 8), (8, 16), (16, 40))},
            "argmax_cell_0based": [int(x) for x in I[:3]], "x_line_through_argmax_normalised": [round(float(x), 3) for x in line],
            "primal_u_at_argmax": [float(x) for x in v[I[0], I[1], I[2], :]]}
    s900_1000 = (math.log10(box_log[1000]) - math.log10(box_log[900])) / 100
    out["growth_rate_box_decade_per_step_900_to_1000"] = s900_1000
    out["extrapolated_onset_step_from_500_level"] = 900 - (math.log10(box_log[900]) - math.log10(box_log[500])) / s900_1000
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=Path("/Users/sota/kg_diag1/out1/grad_g2_diag1"))
    p.add_argument("--write", type=Path, default=E / "posthoc_addendum.json")
    args = p.parse_args()
    if args.write.exists():
        raise SystemExit("refusing to overwrite")
    report = {"kind": "grad03_g2_diag1_posthoc_addendum", "status": "post-hoc exploratory; not part of the registered DIAG1 rules", "ledger": ledger_part(),
              "snapshots": snapshot_part(args.raw_dir), "h4_correction": "DIAG1's mechanical H4 'refutes' used 'itmx reached' as a proxy; the stop test uses the primal residual only, so it says nothing about tangent convergence"}
    args.write.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
