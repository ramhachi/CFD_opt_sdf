#!/usr/bin/env python3
"""G2-DIAG2 host analyzer: integrity of the kernel output, then the counterfactual classification (run once).

Mechanical rules fixed in the pre-run note.  No bridge value, no error gate, no GRAD-03 verdict.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

FORK_STEP = 780
END_STEP = 980
SLOPE_FROM = FORK_STEP + 100          # slope window [FORK+100, END]
BASELINE_MIN_SLOPE = 0.05             # decade/step
SUPPRESS_SLOPE = 0.01
REDUCE_FACTOR = 0.5
MIN_POINTS = 10
GAIN_WINDOW = 50                      # last steps used for the descriptive per-stage gain table
STAGES_U = ("pre_scale", "predict_bdim", "predict_bc", "predict_exitbc", "project1_gradient", "project1_bc", "correct_bdim", "correct_scale",
            "correct_bc", "project2_gradient", "project2_bc")
VARIANTS = ("V0_baseline", "V1a_poisson_n4", "V1b_poisson_n16", "V1c_poisson_n32", "V2_dt_tangent_frozen", "V3_kill_corner_box", "V4a_kill_slab_xmin",
            "V4b_kill_slab_ymin", "V4c_kill_slab_zmax", "V4d_kill_slabs_all", "V5_kill_ghost_layers", "V6_kill_exit_slab")
HYPOTHESES = {"H11": ("V1a_poisson_n4", "V1b_poisson_n16", "V1c_poisson_n32"), "H12": ("V2_dt_tangent_frozen",), "H8": ("V3_kill_corner_box", "V4d_kill_slabs_all"),
              "H7": ("V6_kill_exit_slab",), "H13": ("V5_kill_ghost_layers",)}
FACES = {"x-min": "V4a_kill_slab_xmin", "y-min": "V4b_kill_slab_ymin", "z-max": "V4c_kill_slab_zmax"}
CS_COLUMNS = ("u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits")
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
TERMINAL = {"DIAG2_LOCALIZED", "DIAG2_NOT_REPRODUCED"}


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
    pts = [(int(r["step"]), fnum(r[column])) for r in rows if int(r["step"]) >= start]
    pts = [(s, math.log10(max(v, 1e-300))) for s, v in pts if math.isfinite(v)]
    return fit_slope([p[0] for p in pts], [p[1] for p in pts])


def classify(slope: float, box_slope: float, s0: float, box_s0: float, stopped) -> str:
    """Both the global max and the corner-box max must meet a threshold: the global max sits on the near-body floor (~21) until the
    corner mode exceeds it, so a slowed mode could otherwise look suppressed."""
    if stopped:
        return "diverged"
    if math.isnan(slope) or math.isnan(box_slope):
        return "undetermined"
    if slope <= SUPPRESS_SLOPE and box_slope <= SUPPRESS_SLOPE:
        return "suppresses"
    if slope <= REDUCE_FACTOR * s0 and box_slope <= REDUCE_FACTOR * box_s0:
        return "reduces"
    return "no_effect"


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
        for key in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256"):
            if index.get(key) != freeze["runtime_source_hashes"][key]:
                failures.append(f"runtime source hash differs from the freeze: {key}")
        for key, want in (("fork_step", FORK_STEP), ("end_step", END_STEP), ("slope_from_step", SLOPE_FROM)):
            if index.get(key) != want:
                failures.append(f"{key} differs from the registered value")
    return {"pass": not failures, "failures": failures}


def stage_gains(rows):
    """Descriptive: mean ratio of the corner-box max |tangent u| between successive u stages over the last steps."""
    tail = rows[-GAIN_WINDOW:]
    out = {}
    for prev, cur in zip(STAGES_U, STAGES_U[1:]):
        ratios = [fnum(r[f"box_{cur}"]) / fnum(r[f"box_{prev}"]) for r in tail if fnum(r[f"box_{prev}"]) > 0]
        ratios = [x for x in ratios if math.isfinite(x)]
        out[f"{prev}->{cur}"] = sum(ratios) / len(ratios) if ratios else None
    return out


def analyze(out: Path) -> dict:
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    straight = {int(r["step"]): tuple(r[c] for c in CS_COLUMNS) for r in read_csv(out / "straight_checksums.csv")} if (out / "straight_checksums.csv").is_file() else {}
    report: dict = {"kind": "grad03_g2_diag2_analysis", "verdict_from_kernel": index.get("verdict"), "status": index.get("status"), "no_bridge_value": True,
                    "selected_delta": None, "grad03_verdict": None, "qualification_flags": {k: False for k in FLAGS}, "variants": {}}
    rows_by = {v: read_csv(out / f"variant_{v}.steps.csv") for v in VARIANTS if (out / f"variant_{v}.steps.csv").is_file()}
    results = index.get("variant_results", {})
    exceptions = [v for v, r in results.items() if r.get("exception")]
    # V0 gate: bitwise equal to the straight replay
    v0 = rows_by.get("V0_baseline", [])
    complete_v0 = len(v0) == END_STEP - FORK_STEP and not results.get("V0_baseline", {}).get("stopped_nonfinite_at_step")
    gate = bool(v0) and complete_v0 and all(straight.get(int(r["step"])) == tuple(r[c] for c in CS_COLUMNS) for r in v0)
    s0 = slope_of(v0) if v0 else float("nan")
    box_s0 = slope_of(v0, "box_project2_bc") if v0 else float("nan")
    report["v0"] = {"bitwise_equal_to_straight": gate, "complete_run": complete_v0, "slope_decade_per_step": s0, "box_slope_decade_per_step": box_s0, "steps": len(v0)}
    for name, rows in rows_by.items():
        stopped = results.get(name, {}).get("stopped_nonfinite_at_step")
        s, sb = slope_of(rows), slope_of(rows, "box_project2_bc")
        report["variants"][name] = {"slope_decade_per_step": s, "box_slope_decade_per_step": sb,
                                    "class": "baseline" if name == "V0_baseline" else classify(s, sb, s0, box_s0, stopped), "steps": len(rows),
                                    "stopped_nonfinite_at_step": stopped, "final_glob_max_tangent_u": fnum(rows[-1]["glob_max_tangent_u"]) if rows else None,
                                    "final_glob_max_primal_u": fnum(rows[-1]["glob_max_primal_u"]) if rows else None,
                                    "iterations_last_step": [fnum(rows[-1]["iters1"]), fnum(rows[-1]["iters2"])] if rows else None,
                                    "tangent_relative_residual_first_projection_mean_last50": _mean([fnum(r["r1_tangent"]) / fnum(r["z1_tangent"]) for r in rows[-GAIN_WINDOW:] if fnum(r["z1_tangent"]) > 0]),
                                    "primal_relative_residual_first_projection_mean_last50": _mean([fnum(r["r1_primal"]) / fnum(r["z1_primal"]) for r in rows[-GAIN_WINDOW:] if fnum(r["z1_primal"]) > 0]),
                                    "stage_gain_box_mean_last50": stage_gains(rows) if rows else None}
    missing = [v for v in VARIANTS if v not in rows_by]
    if exceptions or missing or not gate:
        verdict = "DIAG2_INCOMPLETE"
    elif math.isnan(s0) or s0 < BASELINE_MIN_SLOPE:
        verdict = "DIAG2_NOT_REPRODUCED"
    else:
        verdict = "DIAG2_LOCALIZED"
    kernel_classes = index.get("classes", {})
    report.update({"verdict": verdict, "verdict_matches_kernel": verdict == index.get("verdict"), "missing_variants": missing, "variant_exceptions": exceptions,
                   "classes_match_kernel": all(kernel_classes.get(n) == v["class"] for n, v in report["variants"].items()) if kernel_classes else None})
    if verdict != "DIAG2_LOCALIZED":
        report["next_decision"] = "user decision required (no automatic extension or retry of a scientific outcome)"
        return report
    status = {}
    for h, names in HYPOTHESES.items():
        classes = [report["variants"][n]["class"] for n in names]
        status[h] = ("supports" if "suppresses" in classes else "weakly_supports" if "reduces" in classes else
                     "refutes" if all(c == "no_effect" for c in classes) else "unresolved")
    report["hypotheses"] = status | {"note": "interventions are counterfactual perturbations; 'supports' means the growth disappears when the mechanism is removed, not a proof of cause"}
    report["faces_that_suppress"] = [face for face, n in FACES.items() if report["variants"][n]["class"] == "suppresses"]
    proposals = []
    if status["H11"] in ("supports", "weakly_supports"):
        proposals.append("pre-register a tangent-aware Poisson stopping rule (iterate until the primal and the tangent residual have converged) and re-check the long window")
    if status["H12"] in ("supports", "weakly_supports"):
        proposals.append("investigate the treatment of the dt tangent (CFL max selection)")
    if any(status[h] in ("supports", "weakly_supports") for h in ("H8", "H7", "H13")):
        proposals.append("local diagnostic of the boundary tangent path (second wave: split conv_diff!/BDIM, boundary closures)")
    if not proposals:
        proposals.append("second wave: split conv_diff! (convection / diffusion / boundary) and BDIM; no first-wave variant removed the growth")
    report["next_experiment_proposal"] = proposals
    return report


def _mean(xs):
    xs = [x for x in xs if math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


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
    except Exception as err:   # e.g. a truncated diag_index.json after a kill
        integrity = {"pass": False, "failures": [f"integrity check error: {type(err).__name__}: {err}"]}
    report = {"integrity": integrity}
    if (args.out_dir / "diag_index.json").is_file():
        try:
            report |= analyze(args.out_dir)
        except Exception as err:   # a malformed/partial output must still leave a stub report
            report |= {"verdict": "DIAG2_INCOMPLETE", "note": f"analysis error: {type(err).__name__}: {err}"}
    else:
        report |= {"verdict": "DIAG2_INCOMPLETE", "note": "no diag_index.json"}
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.write.write_text(data)
    print(report.get("verdict"), "integrity_pass=", integrity["pass"], hashlib.sha256(data.encode()).hexdigest())
    if not integrity["pass"] or "analysis error" in report.get("note", ""):
        sys.exit(3)


if __name__ == "__main__":
    main()
