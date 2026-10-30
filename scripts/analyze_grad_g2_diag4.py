#!/usr/bin/env python3
"""G2-DIAG4 host analyzer: integrity + regression gates re-derived from the saved histories, then the pre-registered classification (run once).

Does the forced-32 Poisson variant (B32fork: exact clone of the original run at step 780, then forced 32 iterations) eliminate the D0 corner tangent
mode over a longer horizon or only delay it?  The classification is made ONLY here.  forced-32 is a different solver candidate: no bridge table, no FD-08
comparison, no delta, no GRAD-03 verdict.  `NO_ONSET_OBSERVED_TO_1500` is not an elimination claim and not an AD fix.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORK_STEP = 780
END_STEP = 1500
REF_LAST_STEP = 980
INTERVALS = ((880, 980), (980, 1100), (1100, 1200), (1200, 1350), (1350, 1500))      # registered reporting intervals
ROLLING = tuple((s, s + 100) for s in range(800, 1401, 25))                          # 100-step windows, stride 25: 800-900, 825-925, ..., 1400-1500
GROWTH_SLOPE = 0.02          # decade/step
GROWTH_R2 = 0.9
MIN_POINTS = 10
BOX_MAX_GATE = 1e3          # instantaneous escape gates
GLOBAL_MAX_GATE = 1e6
DOMINANCE_FACTOR = 100.0    # the mode is localised once the global max tangent is >= 100 x the near-body floor (the floor = the original run's global max at the fork step)
MODE_WINDOW = 25
BOX_ENERGY_FRACTION = 0.90
MODE_OUTSIDE_FRACTION = 0.5   # corner-localised needs the arg-max outside the box in <= this fraction of the evaluated steps
BOX = ((1, 12), (1, 8), (49, 56))                      # 1-based inclusive: i, j, k
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
CS_COLUMNS = ("u_xor", "u_sum", "p_xor", "p_sum", "dt_value_bits", "dt_tangent_bits")
ARMS = ("B0", "B32fork", "B32fresh")
FIRST_STEP = {"B0": 1, "B32fork": FORK_STEP + 1, "B32fresh": 1}
DIAG3_KERNEL = ROOT / "docs/evidence/grad03_g2_diag3_tangent_poisson_2026_10_08/kernel_output"
REF_STRAIGHT = DIAG3_KERNEL / "straight_checksums.csv"
REF_F32 = DIAG3_KERNEL / "arm_F32_forced_dual_32.steps.csv"
TERMINAL = {"DIAG4_RECORDED"}
READING = {("stable", "stable"): "both forced-32 arms show no onset (single run, 1500 steps: consistent with the fixed32 map being stable on its own, not proof)",
           ("stable", "unstable"): "the fixed32 effect may depend on the history", ("unstable", "stable"): "a mode formed before step 780 may not be removable by fixed32",
           ("unstable", "unstable"): "the DIAG2/3 200-step suppression was probably a delay or a transient"}


INTERPRETATION = {
    "FORCED32_NO_ONSET_OBSERVED_TO_1500": (
        "no onset was observed over the 1500-step horizon for B32fork; this is not an elimination claim and not an AD fix: the forced-32 map is a different solver candidate, "
        "and the size of its primal difference to the original is reported only descriptively in the cmp_*.csv summaries",
        "user decision: Path A (fixed32 as a candidate solver semantics: bounded primal / finite-direction transfer study first) or Path B (retain the original semantics: "
        "corner/BDIM/conv_diff linearised-mode decomposition)"),
    "FORCED32_DELAYED_ONSET": (
        "B32fork shows a sustained or magnitude-gated corner-localised tangent growth after step 780: forced-32 delayed but did not remove the onset (not an AD fix)",
        "user decision; the registered expectation is not to extend the horizon further and to consider the internal linearised-mode decomposition (DIAG5); Float64 stays low priority"),
    "FORCED32_DIFFERENT_MODE": (
        "B32fork shows tangent growth that is not corner-localised under the registered mode rule: forced-32 changed the mode (not an AD fix)",
        "user decision; a new localisation of the different mode is required before any further interpretation"),
    "FORCED32_GROWTH_UNLOCALIZED": (
        "B32fork shows tangent growth for which the registered mode rule could not be evaluated (the global tangent never reached the dominance level, or the arm stopped early)",
        "user decision; no corner claim can be made")}


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


def fit(xs, ys):
    """(slope, r2) of the least-squares line, or (nan, nan) when there are too few points."""
    n = len(xs)
    if n < MIN_POINTS:
        return float("nan"), float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return float("nan"), float("nan")
    return sxy / sxx, (sxy * sxy / (sxx * syy) if syy > 0 else 1.0)


def valid(row) -> bool:
    return fnum(row["nonfinite_primal_u"]) == 0 and fnum(row["nonfinite_tangent_u"]) == 0


def series(rows, column, lo, hi):
    pts = [(int(float(r["step"])), fnum(r[column])) for r in rows if lo <= int(float(r["step"])) <= hi and valid(r)]
    pts = [(s, math.log10(max(v, 1e-300))) for s, v in pts if math.isfinite(v)]
    return [p[0] for p in pts], [p[1] for p in pts]


def window_fit(rows, lo, hi) -> dict:
    out = {}
    for name, col in (("global", "glob_max_tangent_u"), ("box", "box_max_tangent_u")):
        xs, ys = series(rows, col, lo, hi)
        complete = len(xs) == hi - lo + 1
        s, r2 = fit(xs, ys)
        out[name] = {"slope": s, "r2": r2, "points": len(xs), "complete": complete}
    out["growth"] = any(out[k]["complete"] and out[k]["slope"] >= GROWTH_SLOPE and out[k]["r2"] >= GROWTH_R2 for k in ("global", "box"))
    return out


def in_box(index: str) -> bool | None:
    if not index:
        return None   # unknown location: callers count it as NOT in the box (conservative)
    parts = [int(x) for x in index.split(";")][:3]
    return all(lo <= v <= hi for v, (lo, hi) in zip(parts, BOX))


def data_defects(rows, first_step) -> list:
    """History defects that must never read as 'no onset': gaps / duplicates / wrong start, or a non-numeric tangent maximum on a row flagged finite."""
    steps = [int(float(r["step"])) for r in rows]
    bad = []
    if first_step is not None and steps and steps[0] != first_step:
        bad.append(f"first step {steps[0]} != {first_step}")
    if any(b - a != 1 for a, b in zip(steps, steps[1:])):
        bad.append("steps are not consecutive")
    if any(valid(r) and not (math.isfinite(fnum(r["glob_max_tangent_u"])) and math.isfinite(fnum(r["box_max_tangent_u"]))) for r in rows):
        bad.append("non-numeric tangent maximum on a row flagged finite")
    return bad


def analyse_arm(rows, floor, first_step=None) -> dict:
    """Pre-registered growth detection and mode localisation for one arm (the same function is applied to the control B0)."""
    res: dict = {"steps": len(rows), "last_step": int(float(rows[-1]["step"])) if rows else None, "data_defects": data_defects(rows, first_step)}
    res["intervals"] = {f"{lo}-{hi}": window_fit(rows, lo, hi) for lo, hi in INTERVALS}
    wins = [(lo, hi, window_fit(rows, lo, hi)) for lo, hi in ROLLING]
    res["rolling_growth_flags"] = {f"{lo}-{hi}": w["growth"] for lo, hi, w in wins}
    pair = next((i for i in range(len(wins) - 1) if wins[i][2]["growth"] and wins[i + 1][2]["growth"]), None)
    persistent_end = wins[pair + 1][1] if pair is not None else None
    breach = next((int(float(r["step"])) for r in rows if valid(r) and (fnum(r["box_max_tangent_u"]) > BOX_MAX_GATE or fnum(r["glob_max_tangent_u"]) > GLOBAL_MAX_GATE)), None)
    nonfinite = next((int(float(r["step"])) for r in rows if not valid(r)), None)
    res["persistent_pair_first_window"] = None if pair is None else f"{wins[pair][0]}-{wins[pair][1]}"
    res["persistent_declared_at_step"] = persistent_end
    res["magnitude_breach_step"] = breach
    res["first_nonfinite_step"] = nonfinite
    events = [x for x in (persistent_end, breach, nonfinite) if x is not None]
    res["growth_event"] = bool(events)
    res["growth_event_step"] = min(events) if events else None
    res["first_step_box_gt_1"] = next((int(float(r["step"])) for r in rows if valid(r) and fnum(r["box_max_tangent_u"]) > 1.0), None)
    res["near_body_floor"] = floor
    # mode localisation, evaluated where the growing mode dominates (global max >= 100 x floor), on the raw tangent field (energy fractions and arg-max location)
    dom = next((i for i, r in enumerate(rows) if valid(r) and fnum(r["glob_max_tangent_u"]) >= DOMINANCE_FACTOR * floor), None) if math.isfinite(floor) else None
    if dom is None:
        res["mode"] = {"evaluated": False, "reason": "the global tangent never reached the dominance level (100 x the near-body floor)"}
    else:
        chunk = [r for r in rows[dom:dom + MODE_WINDOW] if valid(r)]
        fractions = [fnum(r["box_energy_tangent"]) / fnum(r["glob_energy_tangent"]) for r in chunk if fnum(r["glob_energy_tangent"]) > 0]
        outside = [in_box(r["argmax_tangent_u"]) is not True for r in chunk]
        res["mode"] = {"evaluated": True, "first_dominant_step": int(float(rows[dom]["step"])), "steps": len(chunk),
                       "median_box_energy_fraction": statistics.median(fractions) if fractions else None, "fraction_of_steps_with_argmax_outside_box": sum(outside) / len(outside) if outside else None}
        res["mode"]["corner_localised"] = bool(fractions) and res["mode"]["median_box_energy_fraction"] >= BOX_ENERGY_FRACTION and res["mode"]["fraction_of_steps_with_argmax_outside_box"] <= MODE_OUTSIDE_FRACTION
    return res


def classify_arm(a: dict, alive_at_end: bool = None) -> str:
    if a["data_defects"]:
        return "INCOMPLETE_ARM"
    if not a["growth_event"]:
        return "NO_ONSET_OBSERVED_TO_1500" if a["last_step"] == END_STEP else "INCOMPLETE_ARM"
    m = a["mode"]
    if not m["evaluated"]:
        return "GROWTH_UNLOCALIZED"
    return "DELAYED_ONSET" if m["corner_localised"] else "DIFFERENT_MODE"


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
    if index.get("dryrun") is not False or index.get("no_reference") is not False:
        failures.append("dryrun / no_reference flags are not false")
    if index.get("backend") != "cuda":
        failures.append("backend is not cuda")
    if index.get("clone_bit_identical_at_fork") is not True or index.get("independence_checked") is not True:
        failures.append("clone-at-fork / independence checks are not recorded as true")
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
        if sha256(Path(__file__)) != freeze.get("file_hashes", {}).get("analyzer"):
            failures.append("the analyzer differs from (or is missing in) the frozen analyzer")
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
        for key, want in (("fork_step", FORK_STEP), ("end_step", END_STEP), ("forced_iterations", 32), ("reference_last_step", REF_LAST_STEP)):
            if index.get(key) != want:
                failures.append(f"{key} differs from the registered value")
    return {"pass": not failures, "failures": failures}


def regression(out: Path, rows_by: dict) -> dict:
    """Bitwise gates re-derived on the host: B0 == DIAG3 straight (steps 1..980); B32fork == DIAG3 F32 arm (= DIAG2 V1c) (steps 781..980)."""
    def ref(path):
        return {int(r["step"]): tuple(r[c] for c in CS_COLUMNS) for r in read_csv(path)} if Path(path).is_file() else {}
    sref, fref = ref(REF_STRAIGHT), ref(REF_F32)
    def check(rows, reference, lo, hi):
        want = {s for s in range(lo, hi + 1)}
        got = {int(float(r["step"])): tuple(r[c] for c in CS_COLUMNS) for r in rows}
        return {"expected_steps": len(want), "checked": len(want & set(got) & set(reference)), "mismatch_steps": [s for s in sorted(want & set(got) & set(reference)) if got[s] != reference[s]][:20]}
    b0 = check(rows_by.get("B0", []), sref, 1, REF_LAST_STEP)
    fk = check(rows_by.get("B32fork", []), fref, FORK_STEP + 1, REF_LAST_STEP)
    ok = all(c["checked"] == c["expected_steps"] and not c["mismatch_steps"] for c in (b0, fk))
    return {"b0_vs_diag3_straight": b0, "b32fork_vs_diag3_f32": fk, "pass": ok}


def comparison_summary(path: Path) -> dict | None:
    if not Path(path).is_file():
        return None
    rows = read_csv(path)
    if not rows:
        return None
    out: dict = {"steps": len(rows), "first_step": int(float(rows[0]["step"])), "last_step": int(float(rows[-1]["step"]))}
    for col in ("rel_l2_u", "rel_l2_p", "box_rel_l2_u", "drag_rel_diff", "downforce_rel_diff"):
        vals = [abs(fnum(r[col])) for r in rows if math.isfinite(fnum(r[col]))]
        out[col] = {"max": max(vals), "median": statistics.median(vals), "last": vals[-1]} if vals else None
    top = max(rows, key=lambda r: fnum(r["max_abs_du"]))
    out["largest_primal_u_difference"] = {"step": int(float(top["step"])), "value": fnum(top["max_abs_du"]), "index": top["argmax_du"]}
    topp = max(rows, key=lambda r: fnum(r["max_abs_dp"]))
    out["largest_primal_p_difference"] = {"step": int(float(topp["step"])), "value": fnum(topp["max_abs_dp"]), "index": topp["argmax_dp"]}
    return out


def analyze(out: Path) -> dict:
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    report: dict = {"kind": "grad03_g2_diag4_analysis", "verdict_from_kernel": index.get("verdict"), "status": index.get("status"), "no_bridge_value": True,
                    "forced32_is_a_different_solver_candidate": True, "selected_delta": None, "grad03_verdict": None, "qualification_flags": {k: False for k in FLAGS}}
    rows_by = {a: read_csv(out / f"arm_{a}.steps.csv") for a in ARMS if (out / f"arm_{a}.steps.csv").is_file()}
    missing = [a for a in ARMS if not rows_by.get(a)]
    report["missing_arms"] = missing
    report["regression"] = regression(out, rows_by)
    floor = next((fnum(r["glob_max_tangent_u"]) for r in rows_by.get("B0", []) if int(float(r["step"])) == FORK_STEP), float("nan"))   # the ORIGINAL run's near-body scale at the fork step
    arms = {a: analyse_arm(rows_by[a], floor, FIRST_STEP[a]) for a in ARMS if rows_by.get(a)}
    alive = {a: (index.get("result", {}).get(a) or {}).get("alive_at_end") for a in ARMS}
    for a, v in arms.items():
        v["classification"] = classify_arm(v, alive.get(a))
        v["primal_nonfinite_step"] = next((int(float(r["step"])) for r in rows_by[a] if fnum(r["nonfinite_primal_u"]) > 0), None)
    report["arms"] = arms
    report["comparisons"] = {n: comparison_summary(out / f"cmp_{n}.csv") for n in ("B32fork_vs_B0", "B32fresh_vs_B0", "B32fresh_vs_B32fork")}
    control = arms.get("B0")
    control_ok = bool(control and control["growth_event"] and control["mode"]["evaluated"] and control["mode"]["corner_localised"])
    report["control_b0_reproduces_the_corner_mode"] = control_ok
    complete = not missing and report["regression"]["pass"] and control_ok and index.get("status") == "COMPLETE"
    if not complete:
        report["verdict"] = "DIAG4_INCOMPLETE"
        report["why_incomplete"] = {"missing_arms": missing, "regression_pass": report["regression"]["pass"], "control_ok": control_ok, "kernel_status": index.get("status")}
    else:
        report["verdict"] = {"NO_ONSET_OBSERVED_TO_1500": "FORCED32_NO_ONSET_OBSERVED_TO_1500", "DELAYED_ONSET": "FORCED32_DELAYED_ONSET", "DIFFERENT_MODE": "FORCED32_DIFFERENT_MODE",
                             "GROWTH_UNLOCALIZED": "FORCED32_GROWTH_UNLOCALIZED"}.get(arms["B32fork"]["classification"], "DIAG4_INCOMPLETE")
        fresh = arms["B32fresh"]["classification"]
        stable = lambda c: "stable" if c == "NO_ONSET_OBSERVED_TO_1500" else ("not_assessed" if c == "INCOMPLETE_ARM" else "unstable")  # noqa: E731
        report["history_dependence_reading_secondary_only"] = {"fork": arms["B32fork"]["classification"], "fresh": fresh,
                                                              "reading": READING.get((stable(arms["B32fork"]["classification"]), stable(fresh)), "the secondary arm was not assessable; no history-dependence reading")}
        report["interpretation"], report["next_decision"] = INTERPRETATION[report["verdict"]]
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
            report |= {"verdict": "DIAG4_INCOMPLETE", "note": f"analysis error: {type(err).__name__}: {err}"}
    else:
        report |= {"verdict": "DIAG4_INCOMPLETE", "note": "no diag_index.json"}
    if not integrity["pass"]:
        report["verdict_before_integrity"] = report.get("verdict"); report["verdict"] = "DIAG4_INCOMPLETE"
    data = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    with args.write.open("x") as handle:
        handle.write(data)
    print(report.get("verdict"), "integrity_pass=", integrity["pass"], hashlib.sha256(data.encode()).hexdigest())
    if not integrity["pass"] or "analysis error" in report.get("note", ""):
        sys.exit(3)


if __name__ == "__main__":
    main()
