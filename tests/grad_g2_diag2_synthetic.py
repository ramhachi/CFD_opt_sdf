"""Synthetic G2-DIAG2 kernel outputs (small, analytic) for analyzer tests."""
import csv
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag2 as A

FLAGS = {k: False for k in A.FLAGS}
PINS = {"julia/CFDSDFWaterLilyT4/Project.toml": "11" * 32, "scripts/x.jl": "22" * 32}
D0 = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
PHI = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
FREEZE = {"source_commit": "a" * 40, "pins": PINS, "directions": {"fortran_raw_sha256_d0_only": {"D0_interface_offset": D0}},
          "canonical_state": {"phi_fortran_sha256": PHI},
          "runtime_source_hashes": {"waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32}}
STEP_HEADER = ["step", "t_u_l", "dt_value", "dt_tangent", "glob_max_tangent_u", "glob_max_primal_u", "nonfinite_primal_u", "nonfinite_tangent_u",
               *(f"box_{s}" for s in A.STAGES_U), "iters1", "iters2", "z1_primal", "z1_tangent", "r1_primal", "r1_tangent", "z2_primal", "z2_tangent",
               "r2_primal", "r2_tangent", *A.CS_COLUMNS]
BASE = 0.09


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cs(step, tweak=0):
    return [step * 2, step * 3, step * 5, step * 7, 11 + tweak, 13]


def make_output(root, slopes=None, *, boxslopes=None, stopped=None, v0_mismatch=False, exception=None, dryrun=False, flags=None, drop=None, forks=(780, 980)):
    out = Path(root)
    out.mkdir(parents=True, exist_ok=True)
    slopes = {v: BASE for v in A.VARIANTS} | (slopes or {})
    stopped = stopped or {}
    with (out / "straight_checksums.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["step", *A.CS_COLUMNS, "glob_max_tangent_u", "box_max_tangent_u"])
        for s in range(0, forks[1] + 1):
            w.writerow([s, *cs(s), 1.0, 1.0])
    results = {}
    for v in A.VARIANTS:
        if v == drop:
            continue
        last = stopped.get(v, forks[1])
        with (out / f"variant_{v}.steps.csv").open("w", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(STEP_HEADER)
            for s in range(forks[0] + 1, last + 1):
                g = 10 ** (1.3 + slopes[v] * max(0, s - 800))
                bx = 10 ** (-2 + (boxslopes or {}).get(v, slopes[v]) * max(0, s - 780))
                tweak = 1 if (v == "V0_baseline" and v0_mismatch and s == 900) else 0
                nf = 1 if stopped.get(v) == s else 0
                row = [s, 0.1 * s, 0.33, 0.05, g, 1.2, 0, nf, *([bx] * len(A.STAGES_U)), 1, 1, 1e-3, 5.0, 1e-6, 0.1, 1e-3, 5.0, 1e-6, 0.1, *cs(s, tweak)]
                w.writerow(row)
        results[v] = {"name": v, "steps_run": last - forks[0], "stopped_nonfinite_at_step": stopped.get(v)} | ({"exception": exception} if exception and v == "V3_kill_corner_box" else {})
    ok = exception is None
    s0 = slopes["V0_baseline"]
    verdict = "DIAG2_LOCALIZED" if ok and s0 >= A.BASELINE_MIN_SLOPE else "DIAG2_NOT_REPRODUCED" if ok else "DIAG2_INCOMPLETE"
    index = {"tier": "G2-DIAG2", "backend": "cuda", "dryrun": dryrun, "status": "COMPLETE" if ok else "INCOMPLETE", "verdict": verdict, "fork_step": forks[0],
             "end_step": forks[1], "slope_from_step": forks[0] + 100, "qualification_flags": flags or FLAGS, "variant_results": results,
             "waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32}
    (out / "diag_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"source_commit": FREEZE["source_commit"], "verified": PINS, "direction_sha256": {"D0_interface_offset": D0},
                                                        "phi_sha256": PHI, "failure_stage": None if ok else "diagnostic"}))
    (out / ("DONE" if ok else "ERROR.txt")).write_text("x\n")
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    return out
