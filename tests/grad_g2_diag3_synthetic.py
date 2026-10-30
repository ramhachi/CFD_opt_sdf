"""Synthetic G2-DIAG3 kernel outputs (small, analytic) for analyzer tests."""
import csv
import hashlib
import json
from pathlib import Path

from scripts import analyze_grad_g2_diag3 as A
from scripts import grad_g2_window as W
from tests import grad_g2_synthetic as G2S

FLAGS = {k: False for k in A.FLAGS}
PINS = {"julia/CFDSDFWaterLilyT4/Project.toml": "11" * 32, "scripts/x.jl": "22" * 32}
D0 = "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"
PHI = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
FREEZE = {"source_commit": "a" * 40, "pins": PINS, "directions": {"fortran_raw_sha256_d0_only": {"D0_interface_offset": D0}}, "canonical_state": {"phi_fortran_sha256": PHI},
          "runtime_source_hashes": {"waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "waterlily_poisson_jl_sha256": "55" * 32}}
REFINE = [f"{c}{k}" for k in (1, 2) for c in ("cyc", "rel_before", "rel_after", "tangent_mean", "dz_max", "rel_after_demeaned", "rel_before_demeaned")]
HEADER = ["step", "t_u_l", "dt_value", "dt_tangent", "glob_max_tangent_u", "glob_max_primal_u", "nonfinite_primal_u", "nonfinite_tangent_u", *(f"box_{s}" for s in A.STAGES_U),
          "iters1", "iters2", "z1_primal", "z1_tangent", "r1_primal", "r1_tangent", "z2_primal", "z2_tangent", "r2_primal", "r2_tangent", *A.CS_COLUMNS, *A.VCS_COLUMNS, *REFINE]
BASE = 0.1
FLOOR = 21.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cs(step, tweak=0):
    return [step * 2, step * 3, step * 5, step * 7, 11 + tweak, 13]


def vcs(step, tweak=0):
    return [step * 2 + 1, step * 3 + 1, step * 5 + 1, step * 7 + 1, 11 + tweak]


def make_output(root, *, suppress=(), slopes=None, endpoints=None, broken_identity=(), a0_mismatch=False, exception=None, dryrun=False, flags=None, stage_b=None,
                cycles=None, stopped=None, cut_stage_b=False, stage_b_exception=False):
    """`suppress`: arm names whose growth is removed; `broken_identity`: arms whose primal values differ from the straight replay."""
    out = Path(root); out.mkdir(parents=True, exist_ok=True)
    stopped = stopped or {}
    with (out / "straight_checksums.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["step", *A.CS_COLUMNS, *A.VCS_COLUMNS, "glob_max_tangent_u", "box_max_tangent_u"])
        for s in range(0, A.END_STEP + 1):
            w.writerow([s, *cs(s), *vcs(s), FLOOR if s >= A.FORK_STEP else "nan", 0.01 if s >= A.FORK_STEP else "nan"])
    results = {}
    for name, kind, tau, n in A.ARMS:
        last = stopped.get(name, A.END_STEP)
        s_glob = (slopes or {}).get(name, 0.0 if name in suppress else BASE)
        with (out / f"arm_{name}.steps.csv").open("w", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(HEADER)
            for step in range(A.FORK_STEP + 1, last + 1):
                g = FLOOR * 10 ** (s_glob * max(0, step - 800)) if s_glob > 0.02 else FLOOR * (1 + s_glob * (step - 800) / 1000)
                if name in (endpoints or {}) and step == last:
                    g = endpoints[name]
                bx = 0.01 * 10 ** (s_glob * max(0, step - 800))
                nf = 1 if stopped.get(name) == step else 0
                cyc = (cycles or {}).get(name, 6 if kind in ("refine_threshold", "refine_count") else 3)
                tw = 1 if (a0_mismatch and name == "A0_baseline" and step == 900) else 0
                tv = 1 if (name in broken_identity and step == 900) else 0
                row = [step, 0.1 * step, 0.33, 0.05, g, 1.2, 0, nf, *([bx] * len(A.STAGES_U)), 1, 1, 1e-3, 5.0, 1e-6, 0.1, 1e-3, 5.0, 1e-6, 0.1,
                       *cs(step, tw), *vcs(step, tv),
                       *([cyc, 0.02, 1e-5, 1e-9, 5.0, 1e-5, 0.02] * 2)]
                w.writerow(row)
        results[name] = {"name": name, "kind": kind, "steps_run": last - A.FORK_STEP, "stopped_nonfinite_at_step": stopped.get(name)} | ({"exception": exception} if exception and name == "A1_n08" else {})
    with (out / "drift.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["arm", "step", "max_abs_du", "rel_l2_u", "max_abs_dp", "rel_l2_p", "fx", "fz", "fx_straight", "fz_straight"])
        w.writerow(["F32_forced_dual_32", 800, 0.1, 1e-3, 0.2, 2e-3, 101.0, 50.0, 100.0, 50.0])
    ok_all = exception is None
    # recompute classes/identity with the analyzer itself would be circular; the kernel index stores what the Julia job would store
    index = {"tier": "G2-DIAG3", "backend": "cuda", "dryrun": dryrun, "status": "COMPLETE" if ok_all else "INCOMPLETE", "qualification_flags": flags or FLAGS,
             "fork_step": A.FORK_STEP, "end_step": A.END_STEP, "slope_from_step": A.SLOPE_FROM, "arms": A.ARM_NAMES, "arm_results": results,
             "waterlily_flow_jl_sha256": "33" * 32, "waterlily_multilevelpoisson_jl_sha256": "44" * 32, "waterlily_poisson_jl_sha256": "55" * 32}
    a = A.stage_a(out, index)
    index["verdict"], index["stage_a_verdict"] = a["verdict"], a["verdict"]
    index["classes"] = {n: v["class"] for n, v in a["arms"].items()}
    index["selected_candidate"] = a["selected_candidate"]
    if cut_stage_b:     # killed by the time limit while Stage B ran: RUNNING index, selected candidate, no stage_b, no top-level verdict
        index["status"] = "RUNNING_STAGE_B"; index.pop("verdict", None)
    elif stage_b_exception:
        index["stage_b"] = {"exception": "boom"}; index["stage_b_verdict"] = "DIAG3_INCONCLUSIVE"; index["status"] = "INCOMPLETE"; index["verdict"] = "DIAG3_INCONCLUSIVE"
    elif stage_b is not None:
        make_stage_b(out, index, **stage_b)
    else:
        index["stage_b_verdict"] = "SKIPPED_NO_CANDIDATE"
    (out / "diag_index.json").write_text(json.dumps(index))
    (out / "run_identity.json").write_text(json.dumps({"source_commit": FREEZE["source_commit"], "verified": PINS, "direction_sha256": {"D0_interface_offset": D0}, "phi_sha256": PHI,
                                                        "failure_stage": None if ok_all else "diagnostic", "spike_exit_code": 0 if ok_all else 2}))
    terminal = index.get("verdict") in A.TERMINAL and index["status"] == "COMPLETE"
    (out / ("DONE" if terminal and ok_all else "ERROR.txt")).write_text("x\n")
    files = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    (out / "output_manifest.json").write_text(json.dumps({"files": files}))
    return out


def make_stage_b(out, index, *, box_max=0.05, glob_max=30.0, completed=True, nonfinite=False, host_mismatch=False, primal_scale=1.0, sample_failure=False, n_steps=2000):
    with (out / "longrun.steps.csv").open("w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["step", "t_u_l", "glob_max_tangent_u", "glob_max_primal_u", "box_max_tangent_u", "nonfinite_primal_u", "nonfinite_tangent_u", "iters1", "iters2",
                    "cyc1", "rel_before1", "rel_after1", "tangent_mean1", "rel_after_demeaned1", "cyc2", "rel_before2", "rel_after2", "tangent_mean2", "rel_after_demeaned2"])
        for s in range(1, n_steps + 1):
            w.writerow([s, 0.01 * s, glob_max, 1.2, box_max, 0, 0, 1, 1, 5, 0.02, 1e-5, 1e-9, 1e-5, 5, 0.02, 1e-5, 1e-9, 1e-5])
    rows = [dict(r) for r in W.read_history(G2S_PLAIN)]
    for r in rows:
        for c in list(r):
            if c.endswith("_tan") and c != "t_u_l_tan":
                r[c] = 100.0 + 0.01 * r["step"]
            if c == "t_u_l_tan":
                r[c] = 0.5 * r["t_u_l"]
        r["fx"] *= primal_scale
    G2S.write_history(out / "longrun.history.csv", rows)
    summary = G2S.summary_for(rows, "longrun", "Dual")
    if host_mismatch:
        summary["window_mean_fx_dual_time"]["tangent"] *= 1.001
    (out / "longrun.summary.json").write_text(json.dumps(summary))
    index["stage_b"] = {"steps_run": n_steps, "completed_window": completed, "stopped_nonfinite_at_step": 5 if nonfinite else None,
                        "sample_failure": {"step": 8, "message": "x"} if sample_failure else None, "max_box_max_tangent_u": box_max, "max_glob_max_tangent_u": glob_max}
    index["stage_b_verdict"] = "x"


G2S_PLAIN = A.G2_PLAIN_HISTORY
