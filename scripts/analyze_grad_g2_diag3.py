#!/usr/bin/env python3
"""G2-DIAG3 host analyzer: integrity of the kernel output, then the stage A (tangent-only continuation) and stage B (held-out long horizon)
classification (run once).  Mechanical rules fixed in the pre-run note.  No bridge table, no FD-08 comparison, no error gate, no GRAD-03 verdict.
Only the finiteness of the long-horizon tangent window means is reported (their values are not interpreted here)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grad_g2_window as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FORK_STEP = 780
END_STEP = 980
N_STEPS = END_STEP - FORK_STEP
SLOPE_FROM = FORK_STEP + N_STEPS // 2
BASELINE_MIN_SLOPE = 0.05
SUPPRESS_SLOPE = 0.005
FLOOR_FACTOR = 2.0
REDUCE_FACTOR = 0.5
MAX_TANGENT_CYCLES = 64
PLATEAU_RUN = 3
LONG_BOX_MAX = 1e3
LONG_GLOBAL_MAX = 1e6
MIN_POINTS = 10
WINDOW = (80.0, 120.0)
PRIMAL_GATE = 1e-3           # Stage B: Dual window-mean primal vs the G2 plain Float32 history (the registered G2 harness gate)
SUMMARY_AGREEMENT = 1e-9     # host recomputation vs the kernel summary
TAUS = (1e-4, 1e-5, 1e-6, 1e-7)
COUNTS = (1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64)
STAGES_U = ("pre_scale", "predict_bdim", "predict_bc", "predict_exitbc", "project1_gradient", "project1_bc", "correct_bdim", "correct_scale",
            "correct_bc", "project2_gradient", "project2_bc")
CS_COLUMNS = ("u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits")
VCS_COLUMNS = ("u_val_xor", "u_val_sum", "p_val_xor", "p_val_sum", "dt_val_bits")
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
TERMINAL = {"TANGENT_ONLY_CAUSAL_SUPPORT", "TANGENT_ONLY_NO_SUPPORT", "DIAG3_NOT_REPRODUCED"}
G2_PLAIN_HISTORY = ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08/kernel_attempt1/plain.history.csv"


def tau_name(t: float) -> str:
    return f"1e-{round(-math.log10(t))}"


ARMS = ([("A0_baseline", "none", 0.0, 0)] + [(f"A1_tau_{tau_name(t)}", "refine_threshold", t, 0) for t in TAUS] +
        [(f"A1_n{n:02d}", "refine_count", 0.0, n) for n in COUNTS] + [(f"D_tau_{tau_name(t)}", "dual_stop", t, 0) for t in TAUS] + [("F32_forced_dual_32", "forced", 0.0, 32)])
ARM_NAMES = [a[0] for a in ARMS]
FAMILY = {"refine_threshold": "threshold", "refine_count": "count", "dual_stop": "dual", "forced": "forced", "none": "baseline"}
THRESHOLD_NAMES = [a[0] for a in ARMS if FAMILY[a[1]] == "threshold"]
COUNT_NAMES = [a[0] for a in ARMS if FAMILY[a[1]] == "count"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def jload(path: Path):
    return json.loads(Path(path).read_text())


def fnum(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def fit_slope(xs, ys) -> float:
    n = len(xs)
    if n < MIN_POINTS:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else float("nan")


def slope_of(rows, column="glob_max_tangent_u", start=SLOPE_FROM) -> float:
    pts = [(int(float(r["step"])), fnum(r[column])) for r in rows if int(float(r["step"])) >= start]
    pts = [(s, math.log10(max(v, 1e-300))) for s, v in pts if math.isfinite(v)]
    return fit_slope([p[0] for p in pts], [p[1] for p in pts])


def classify(s, sb, endpoint, s0, sb0, floor, stopped) -> str:
    if stopped:
        return "diverged"
    if math.isnan(s) or math.isnan(sb):
        return "undetermined"
    if s <= SUPPRESS_SLOPE and sb <= SUPPRESS_SLOPE and endpoint <= FLOOR_FACTOR * floor:
        return "suppresses"
    if s <= REDUCE_FACTOR * s0 and sb <= REDUCE_FACTOR * sb0:
        return "reduces"
    return "no_effect"


def plateau_members(names, ok) -> list[str]:
    members, i = [], 0
    while i < len(names):
        if ok[names[i]]:
            j = i
            while j + 1 < len(names) and ok[names[j + 1]]:
                j += 1
            if j - i + 1 >= PLATEAU_RUN:
                members += names[i:j + 1]
            i = j + 1
        else:
            i += 1
    return members


def select_candidate(names, ok, mean_cycles):
    """Threshold-family plateau member with a looser neighbour that also suppresses, fewest mean tangent cycles, ties -> tighter."""
    cand = [n for n in plateau_members(names, ok) if names.index(n) > 0 and ok[names[names.index(n) - 1]]]
    if not cand:
        return None
    best = cand[0]
    for n in cand[1:]:
        if mean_cycles[n] < mean_cycles[best] or (mean_cycles[n] == mean_cycles[best] and names.index(n) > names.index(best)):
            best = n
    return best


def verify_integrity(out: Path, freeze: dict | None = None) -> dict:
    failures: list[str] = []
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    if not index:
        failures.append("diag_index.json missing")
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    if done and index.get("verdict") not in TERMINAL:
        failures.append("DONE present but verdict is not terminal")
    if index and index.get("status") != "COMPLETE":
        failures.append(f"kernel status is {index.get('status')!r}, not COMPLETE")
    if freeze is not None and "analyzer" in freeze.get("file_hashes", {}) and sha256(Path(__file__)) != freeze["file_hashes"]["analyzer"]:
        failures.append("the analyzer differs from the frozen analyzer")
    if index.get("dryrun") is not False:
        failures.append("dryrun flag is not false")
    if index.get("backend") != "cuda":
        failures.append("backend is not cuda")
    if index.get("qualification_flags") != {k: False for k in FLAGS}:
        failures.append("qualification flags are not all false")
    if (out / "output_manifest.json").is_file():
        for rel, digest in jload(out / "output_manifest.json")["files"].items():
            p = out / rel
            if not p.is_file():
                failures.append(f"manifest file missing: {rel}")
            elif sha256(p) != digest:
                failures.append(f"manifest SHA mismatch: {rel}")
    else:
        failures.append("output_manifest.json missing")
    if freeze is not None:
        if not (out / "run_identity.json").is_file():
            failures.append("run_identity.json missing")
        else:
            identity = jload(out / "run_identity.json")
            if identity.get("source_commit") != freeze["source_commit"]:
                failures.append("kernel source_commit differs from the freeze")
            for rel, digest in freeze["pins"].items():
                if identity.get("verified", {}).get(rel) != digest:
                    failures.append(f"kernel pin not verified: {rel}")
            if identity.get("direction_sha256") != freeze["directions"]["fortran_raw_sha256_d0_only"]:
                failures.append("D0 direction hash differs from the freeze")
            if identity.get("phi_sha256") != freeze["canonical_state"]["phi_fortran_sha256"]:
                failures.append("baseline phi hash differs from the freeze")
        for key in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256", "waterlily_poisson_jl_sha256"):
            if index.get(key) != freeze["runtime_source_hashes"][key]:
                failures.append(f"runtime source hash differs from the freeze: {key}")
        for key, want in (("fork_step", FORK_STEP), ("end_step", END_STEP), ("slope_from_step", SLOPE_FROM)):
            if index.get(key) != want:
                failures.append(f"{key} differs from the registered value")
        if index.get("arms") != ARM_NAMES:
            failures.append("arm inventory differs from the registered one")
    return {"pass": not failures, "failures": failures}


def _median(xs):
    xs = sorted(x for x in xs if math.isfinite(x))
    return xs[len(xs) // 2] if xs else None


def _mean(xs):
    xs = [x for x in xs if math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def stage_a(out: Path, index: dict) -> dict:
    straight_rows = read_csv(out / "straight_checksums.csv") if (out / "straight_checksums.csv").is_file() else []
    straight = {int(r["step"]): r for r in straight_rows}
    floor = fnum(straight[FORK_STEP]["glob_max_tangent_u"]) if FORK_STEP in straight else float("nan")
    results = index.get("arm_results", {})
    rows_by = {a: read_csv(out / f"arm_{a}.steps.csv") for a in ARM_NAMES if (out / f"arm_{a}.steps.csv").is_file() and not results.get(a, {}).get("exception")}
    exceptions = [a for a, r in results.items() if r.get("exception")]

    def identical(rows, columns):
        return bool(rows) and all(int(r["step"]) in straight and all(straight[int(r["step"])][c] == r[c] for c in columns) for r in rows)

    a0 = rows_by.get("A0_baseline", [])
    stopped = lambda a: results.get(a, {}).get("stopped_nonfinite_at_step")  # noqa: E731
    a0_ok = bool(a0) and len(a0) == N_STEPS and not stopped("A0_baseline") and identical(a0, CS_COLUMNS) and math.isfinite(fnum(straight[END_STEP]["glob_max_tangent_u"])) if END_STEP in straight else False
    s0, sb0 = (slope_of(a0), slope_of(a0, "box_project2_bc")) if a0_ok else (float("nan"),) * 2
    arms: dict[str, dict] = {}
    for name, kind, tau, n in ARMS:
        rows = rows_by.get(name)
        if not rows:
            continue
        s, sb = slope_of(rows), slope_of(rows, "box_project2_bc")
        endpoint = fnum(rows[-1]["glob_max_tangent_u"])
        cyc = [fnum(r["cyc1"]) + fnum(r["cyc2"]) for r in rows] if kind in ("refine_threshold", "refine_count") else [fnum(r["iters1"]) + fnum(r["iters2"]) for r in rows]
        entry = {"kind": kind, "slope": s, "box_slope": sb, "endpoint_glob_max_tangent_u": endpoint, "steps": len(rows), "stopped_nonfinite_at_step": stopped(name),
                 "primal_value_identity": identical(rows, VCS_COLUMNS), "mean_tangent_cycles_per_step": _mean(cyc),
                 "class": "baseline" if kind == "none" else classify(s, sb, endpoint, s0, sb0, floor, stopped(name)),
                 "tangent_relative_residual_before_mean": _mean([fnum(r[f"rel_before{k}"]) for r in rows for k in (1, 2)]),
                 "tangent_relative_residual_after_mean": _mean([fnum(r[f"rel_after{k}"]) for r in rows for k in (1, 2)]),
                 "tangent_relative_residual_after_demeaned_mean": _mean([fnum(r[f"rel_after_demeaned{k}"]) for r in rows for k in (1, 2)]),
                 "active_mean_removed_abs_mean": _mean([abs(fnum(r[f"tangent_mean{k}"])) for r in rows for k in (1, 2)]),
                 "fraction_of_projections_at_the_cycle_cap": (_mean([1.0 if fnum(r[f"cyc{k}"]) >= MAX_TANGENT_CYCLES else 0.0 for r in rows for k in (1, 2)]) if kind == "refine_threshold" else None),
                 "median_achieved_rel_after_demeaned": _median([fnum(r[f"rel_after_demeaned{k}"]) for r in rows for k in (1, 2)]),
                 "primal_relative_residual_first_projection_mean_last50": _mean([fnum(r["r1_primal"]) / fnum(r["z1_primal"]) for r in rows[-50:] if fnum(r["z1_primal"]) > 0])}
        arms[name] = entry
    ok = {a: bool(arms.get(a, {}).get("class") == "suppresses" and arms[a]["primal_value_identity"]) for a in ARM_NAMES}
    plateau = {"threshold": plateau_members(THRESHOLD_NAMES, ok), "count": plateau_members(COUNT_NAMES, ok)}
    any_support = bool(plateau["threshold"] or plateau["count"])
    if exceptions or not a0_ok:
        verdict = "DIAG3_INCONCLUSIVE"
    elif math.isnan(s0) or s0 < BASELINE_MIN_SLOPE:
        verdict = "DIAG3_NOT_REPRODUCED"
    elif any_support:
        verdict = "TANGENT_ONLY_CAUSAL_SUPPORT"
    else:
        verdict = "TANGENT_ONLY_NO_SUPPORT"
    mean_cycles = {n: (arms[n]["mean_tangent_cycles_per_step"] if arms.get(n, {}).get("mean_tangent_cycles_per_step") is not None else float("inf")) for n in THRESHOLD_NAMES}
    selected = select_candidate(THRESHOLD_NAMES, ok, mean_cycles) if verdict == "TANGENT_ONLY_CAUSAL_SUPPORT" else None
    # drift of the arms that change the primal (descriptive)
    drift: dict[str, dict] = {}
    if (out / "drift.csv").is_file():
        for r in read_csv(out / "drift.csv"):
            d = drift.setdefault(r["arm"], {"max_rel_l2_u": 0.0, "max_rel_l2_p": 0.0, "max_rel_fx": 0.0, "max_rel_fz": 0.0, "points": 0})
            d["points"] += 1
            d["max_rel_l2_u"] = max(d["max_rel_l2_u"], fnum(r["rel_l2_u"])); d["max_rel_l2_p"] = max(d["max_rel_l2_p"], fnum(r["rel_l2_p"]))
            for key, a, b in (("max_rel_fx", "fx", "fx_straight"), ("max_rel_fz", "fz", "fz_straight")):
                d[key] = max(d[key], abs(fnum(r[a]) - fnum(r[b])) / max(abs(fnum(r[b])), 1e-30))
    return {"floor_glob_max_tangent_u_at_fork": floor, "baseline": {"slope": s0, "box_slope": sb0, "identity_and_complete": a0_ok}, "arms": arms, "exceptions": exceptions,
            "plateau": plateau, "verdict": verdict, "selected_candidate": selected, "primal_drift_vs_straight": drift,
            "missing_arms": [a for a in ARM_NAMES if a not in rows_by]}


def stage_b(out: Path, index: dict) -> dict | None:
    sb = index.get("stage_b")
    if sb is None and not (out / "longrun.steps.csv").is_file():
        return None
    res: dict = {"kernel": sb}
    rows = read_csv(out / "longrun.steps.csv") if (out / "longrun.steps.csv").is_file() else []
    res["steps"] = len(rows)
    res["finite_all_steps"] = bool(rows) and all(fnum(r["nonfinite_primal_u"]) == 0 and fnum(r["nonfinite_tangent_u"]) == 0 for r in rows)
    res["max_box_max_tangent_u"] = max((fnum(r["box_max_tangent_u"]) for r in rows), default=float("nan"))
    res["max_glob_max_tangent_u"] = max((fnum(r["glob_max_tangent_u"]) for r in rows), default=float("nan"))
    res["window_slopes_box_decade_per_step_500_step_windows"] = []
    for start in range(0, len(rows), 500):
        chunk = rows[start:start + 500]
        res["window_slopes_box_decade_per_step_500_step_windows"].append(
            fit_slope([int(float(r["step"])) for r in chunk if fnum(r["box_max_tangent_u"]) > 0], [math.log10(fnum(r["box_max_tangent_u"])) for r in chunk if fnum(r["box_max_tangent_u"]) > 0]) if len(chunk) >= MIN_POINTS else None)
    res["tangent_cycles_mean"] = _mean([fnum(r["cyc1"]) + fnum(r["cyc2"]) for r in rows])
    host_ok, notes = False, []
    if (out / "longrun.history.csv").is_file() and (out / "longrun.summary.json").is_file():
        try:
            hist = W.read_history(out / "longrun.history.csv")
            summary = jload(out / "longrun.summary.json")
            agree = True
            means = {}
            for kernel_name, series in (("fx", "fx"), ("fz", "-fz")):
                for variant, flag in (("dual_time", True), ("frozen_time", False)):
                    v, d = W.window_mean(hist, series, *WINDOW, time_tangent=flag)
                    k = summary[f"window_mean_{kernel_name}_{variant}"]
                    kv, kd = (k["value"], k["tangent"]) if series == "fx" else (-k["value"], -k["tangent"])
                    close = lambda a, b: abs(a - b) <= SUMMARY_AGREEMENT * max(abs(a), abs(b), 1e-12)  # noqa: E731
                    agree &= close(v, kv) and close(d, kd)
                    means[(kernel_name, variant)] = (v, d)
            res["host_recomputation_matches_kernel"] = agree
            res["tangent_window_means_finite"] = all(math.isfinite(d) for _, d in means.values())     # values are NOT interpreted here (no bridge)
            plain = W.read_history(G2_PLAIN_HISTORY)
            diffs = {}
            for kernel_name, series in (("fx", "fx"), ("fz", "-fz")):
                pv = W.window_mean(plain, series, *WINDOW, time_tangent=True)[0]
                dv = means[(kernel_name, "dual_time")][0]
                diffs[kernel_name] = abs(dv - pv) / max(abs(pv), 1e-300)
            res["primal_window_mean_rel_diff_vs_g2_plain"] = diffs
            res["primal_gate_pass"] = max(diffs.values()) <= PRIMAL_GATE
            host_ok = agree and res["primal_gate_pass"] and res["tangent_window_means_finite"]
        except Exception as err:  # noqa: BLE001
            notes.append(f"host recomputation error: {type(err).__name__}: {err}")
    res["host_notes"] = notes
    if sb is None or sb.get("exception"):
        res["verdict"] = "DIAG3_INCONCLUSIVE"       # Stage B was cut or failed: not a scientific outcome
        return res
    completed = bool(sb.get("completed_window")) and not sb.get("stopped_nonfinite_at_step") and not sb.get("sample_failure")
    gates = completed and res["finite_all_steps"] and res["max_box_max_tangent_u"] <= LONG_BOX_MAX and res["max_glob_max_tangent_u"] <= LONG_GLOBAL_MAX and host_ok
    res["verdict"] = "DIAG3_LONG_HORIZON_STABLE" if gates else "DIAG3_LONG_HORIZON_NOT_STABLE"
    return res


def analyze(out: Path) -> dict:
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    report: dict = {"kind": "grad03_g2_diag3_analysis", "verdict_from_kernel": index.get("verdict"), "status": index.get("status"), "no_bridge_value": True,
                    "selected_delta": None, "grad03_verdict": None, "qualification_flags": {k: False for k in FLAGS}}
    a = stage_a(out, index)
    report["stage_a"] = a
    report["verdict"] = a["verdict"] if index.get("status") == "COMPLETE" else "DIAG3_INCONCLUSIVE"
    report["stage_a_verdict"] = a["verdict"]
    report["verdict_matches_kernel"] = report["verdict"] == index.get("verdict")
    kc = index.get("classes", {})
    report["classes_match_kernel"] = all(kc.get(n) == v["class"] for n, v in a["arms"].items()) if kc else None
    report["selection_matches_kernel"] = a["selected_candidate"] == index.get("selected_candidate")
    if a["selected_candidate"] is not None or (out / "longrun.steps.csv").is_file():
        b = stage_b(out, index) or {"verdict": "DIAG3_INCONCLUSIVE", "note": "a Stage B candidate was selected but Stage B left no result (cut by the time limit)"}
        report["stage_b"] = b
        report["stage_b_verdict"] = b["verdict"]
        report["stage_b_matches_kernel"] = (b or {}).get("verdict") == index.get("stage_b_verdict")
    else:
        report["stage_b_verdict"] = "SKIPPED_NO_CANDIDATE"
    proposals = []
    v, bv = report["verdict"], report.get("stage_b_verdict")
    if v == "TANGENT_ONLY_CAUSAL_SUPPORT" and bv == "SKIPPED_NO_CANDIDATE":
        proposals.append("user decision required: the plateau exists only in the fixed-count family, so no threshold candidate was selected and Stage B did not run")
    elif v == "TANGENT_ONLY_CAUSAL_SUPPORT" and bv == "DIAG3_INCONCLUSIVE":
        proposals.append("user decision required: Stage B was cut or failed (instrumentation); a new identity may repair a source bug once")
    elif v == "TANGENT_ONLY_CAUSAL_SUPPORT" and bv == "DIAG3_LONG_HORIZON_STABLE":
        proposals.append("propose a G2 bridge retry as separate, pre-registered work (D0 tangent is stable over the registered horizon with the selected tangent-only rule)")
    elif v == "TANGENT_ONLY_CAUSAL_SUPPORT":
        proposals.append("dig further into the Poisson / linearized-solver semantics (the short-horizon support did not hold over the full horizon)")
    elif v == "TANGENT_ONLY_NO_SUPPORT":
        proposals.append("tangent-only continuation does not remove the growth: dig into the Poisson / linearized solver semantics or re-evaluate the forward long-window path")
    else:
        proposals.append("user decision required (no automatic extension or retry of a scientific outcome)")
    report["next_experiment_proposal"] = proposals
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", required=True, type=Path)
    args = p.parse_args()
    if args.write.exists():
        sys.exit("refusing to overwrite an existing analysis (the diagnostic analyzer runs once)")
    try:
        integrity = verify_integrity(args.out_dir, jload(args.freeze))
    except Exception as err:  # noqa: BLE001
        integrity = {"pass": False, "failures": [f"integrity check error: {type(err).__name__}: {err}"]}
    report = {"integrity": integrity}
    if (args.out_dir / "diag_index.json").is_file():
        try:
            report |= analyze(args.out_dir)
        except Exception as err:  # noqa: BLE001
            report |= {"verdict": "DIAG3_INCONCLUSIVE", "note": f"analysis error: {type(err).__name__}: {err}"}
    else:
        report |= {"verdict": "DIAG3_INCONCLUSIVE", "note": "no diag_index.json"}
    data = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    args.write.write_text(data)
    print(report.get("verdict"), report.get("stage_b_verdict"), "integrity_pass=", integrity["pass"], hashlib.sha256(data.encode()).hexdigest())
    if not integrity["pass"] or "analysis error" in report.get("note", ""):
        sys.exit(3)


if __name__ == "__main__":
    main()
