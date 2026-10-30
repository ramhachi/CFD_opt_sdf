#!/usr/bin/env python3
"""G2-DIAG1 host analyzer: integrity of the kernel output, then the diagnostic localization report (run once).

Everything here is descriptive/mechanical: the verdict, the failure identity, the growth classification, the case (A-E) and the
H1-H6 statuses are derived with the rules fixed in the pre-run note (constants below are those rules).  No bridge value, no
error gate, no GRAD-03 verdict is computed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G2_FAIL_STEP = 1200
G2_FAIL_TIME_REPR = "16.409412384033203"
ITMX = 32                         # WaterLily MultiLevelPoisson default (unchanged)
PRE_FAILURE_STEPS = 100
SUDDEN_JUMP_DECADES = 1.0         # one-step rise of log10(max|tangent u|) above this = "sudden"
EXP_MIN_SLOPE = 0.01              # decades per step
EXP_MIN_R2 = 0.95
MONOTONE_FRACTION = 0.9
FLOAT32_NEAR_LIMIT_LOG10 = 30.0   # Float32 max is 3.4e38 (log10 = 38.5)
FLOAT32_FAR_LOG10 = 20.0
H2_SUPPORT_DECADES = 3.0
H2_WEAK_DECADES = 1.0
GEOMETRY_FIELDS = {"mu0", "mu1", "V", "D1", "iD1"}
FLAGS = ("fd_oracle", "field_gradient", "reverse", "optimizer", "topology", "shape_update_allowed")
TERMINAL = {"DIAG_LOCALIZED", "DIAG_NOT_REPRODUCED"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def jload(path: Path):
    return json.loads(Path(path).read_text())


def fnum(x: str) -> float:
    try:
        return float(x)
    except ValueError:
        return float("nan")


def log10(x: float) -> float:
    return math.log10(max(x, 1e-300))


# ---- integrity -----------------------------------------------------------------------------------------------------------
def verify_integrity(out: Path, freeze: dict | None = None, *, require_snapshots: bool = False) -> dict:
    """Host-side terminal verification of the downloaded kernel output (must PASS before the analysis is trusted)."""
    failures: list[str] = []
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    if not index:
        failures.append("diag_index.json missing")
    done, error = (out / "DONE").is_file(), (out / "ERROR.txt").is_file()
    if done == error:
        failures.append(f"exactly one of DONE/ERROR.txt must exist (done={done}, error={error})")
    if done and index.get("verdict") not in TERMINAL:
        failures.append("DONE present but verdict is not a terminal DIAG verdict")
    if error and index.get("verdict") in TERMINAL and index.get("status") == "COMPLETE":
        failures.append("ERROR.txt present although the script reported COMPLETE")
    if index.get("dryrun") is not False:
        failures.append("dryrun flag is not false")
    if index.get("backend") != "cuda":
        failures.append("backend is not cuda")
    if index.get("qualification_flags") != {k: False for k in FLAGS}:
        failures.append("qualification flags are not all false")
    manifest_path = out / "output_manifest.json"
    if manifest_path.is_file():
        files = jload(manifest_path)["files"]
        for rel, digest in files.items():
            p = out / rel
            if not p.is_file():
                if require_snapshots or not rel.startswith("snapshots/"):
                    failures.append(f"manifest file missing: {rel}")
            elif sha256(p) != digest:
                failures.append(f"manifest SHA mismatch: {rel}")
    else:
        failures.append("output_manifest.json missing")
    identity_path = out / "run_identity.json"
    if identity_path.is_file() and freeze is not None:
        identity = jload(identity_path)
        if identity.get("source_commit") != freeze["source_commit"]:
            failures.append("kernel source_commit differs from the freeze")
        for rel, digest in freeze["pins"].items():
            if identity.get("verified", {}).get(rel) != digest:
                failures.append(f"kernel pin not verified: {rel}")
        if identity.get("direction_sha256") != freeze["directions"]["fortran_raw_sha256_d0_only"]:
            failures.append("D0 direction hash differs from the freeze")
        if identity.get("phi_sha256") != freeze["canonical_state"]["phi_fortran_sha256"]:
            failures.append("baseline phi hash differs from the freeze")
    elif freeze is not None:
        failures.append("run_identity.json missing")
    if freeze is not None:
        for key in ("waterlily_flow_jl_sha256", "waterlily_multilevelpoisson_jl_sha256"):
            if index.get(key) != freeze["runtime_source_hashes"][key]:
                failures.append(f"runtime source hash differs from the freeze: {key}")
    snap_path = out / "snapshot_index.json"
    if snap_path.is_file():
        for rel, meta in jload(snap_path).items():
            p = out / "snapshots" / rel
            if p.is_file() and sha256(p) != meta["sha256"]:
                failures.append(f"snapshot SHA mismatch: {rel}")
            elif not p.is_file() and require_snapshots:
                failures.append(f"snapshot missing: {rel}")
    return {"pass": not failures, "failures": failures}


# ---- ledgers -------------------------------------------------------------------------------------------------------------
def load_ledger(out: Path):
    rows = []
    for r in read_csv(out / "stage_ledger.csv"):
        rows.append({"step": int(r["step"]), "idx": int(r["stage_idx"]), "stage": r["stage"], "field": r["field"], "np": int(r["nonfinite_primal"]),
                     "nt": int(r["nonfinite_tangent"]), "mp": fnum(r["maxabs_primal"]), "mt": fnum(r["maxabs_tangent"]),
                     "rp": fnum(r["rms_primal"]), "rt": fnum(r["rms_tangent"]), "ap": r["argmax_primal"], "at": r["argmax_tangent"]})
    return rows


def rederive_first_bad(rows):
    for r in rows:
        if r["np"] > 0 or r["nt"] > 0:
            return r
    return None


def last_finite_and_first_bad_stage(rows, bad):
    """(last fully finite (step, idx, stage), first non-finite (step, idx, stage)) in execution order."""
    order, finite = [], {}
    for r in rows:
        key = (r["step"], r["idx"], r["stage"])
        if key not in finite:
            order.append(key); finite[key] = True
        if r["np"] > 0 or r["nt"] > 0:
            finite[key] = False
    first_bad = (bad["step"], bad["idx"], bad["stage"])
    pos = order.index(first_bad)
    return (order[pos - 1] if pos else None), first_bad


def series(rows, stage, field):
    return [r for r in rows if r["stage"] == stage and r["field"] == field]


def growth(rows, fail_step):
    """Growth of max|tangent| / rms tangent of the end-of-step velocity u (stage project2_bc) up to the failure step."""
    s = [r for r in series(rows, "project2_bc", "u") if r["step"] < fail_step]
    out, prev = [], None
    for r in s:
        lg = log10(r["mt"])
        out.append({"step": r["step"], "maxabs_tangent": r["mt"], "rms_tangent": r["rt"], "log10_maxabs_tangent": lg,
                    "ratio_to_previous": (r["mt"] / prev) if prev else None, "maxabs_primal": r["mp"]})
        prev = r["mt"] if r["mt"] > 0 else prev
    return out


def _fit(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0, 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx if sxx else 0.0
    r2 = (sxy * sxy / (sxx * syy)) if sxx and syy else 0.0
    return slope, r2


def growth_pattern(curve):
    tail = curve[-PRE_FAILURE_STEPS:]
    if len(tail) < 3:
        return {"pattern": "insufficient_history", "points": len(tail)}
    lg = [p["log10_maxabs_tangent"] for p in tail]
    steps = [p["step"] for p in tail]
    jumps = [b - a for a, b in zip(lg, lg[1:])]
    slope, r2 = _fit(steps, lg)
    monotone = sum(1 for j in jumps if j >= 0) / len(jumps)
    out = {"points": len(tail), "max_one_step_rise_decades": max(jumps), "linear_fit_slope_decades_per_step": slope, "linear_fit_r2": r2,
           "nondecreasing_fraction": monotone, "log10_maxabs_tangent_last": lg[-1],
           "maxabs_over_rms_tangent_last": (tail[-1]["maxabs_tangent"] / tail[-1]["rms_tangent"]) if tail[-1]["rms_tangent"] else None}
    if out["max_one_step_rise_decades"] > SUDDEN_JUMP_DECADES:
        out["pattern"] = "sudden_jump"
    elif slope > EXP_MIN_SLOPE and r2 >= EXP_MIN_R2:
        out["pattern"] = "roughly_exponential"
    elif monotone >= MONOTONE_FRACTION and slope > 0:
        out["pattern"] = "slow_monotonic"
    else:
        out["pattern"] = "other"
    return out


def plain_consistency(out: Path, plain_history: Path | None) -> dict | None:
    """Informational: primal of the Dual reference run vs the immutable G2 attempt-1 plain Float32 history on common sampled steps."""
    if plain_history is None or not Path(plain_history).is_file() or not (out / "reference_forces.csv").is_file():
        return None
    plain = {int(float(r["step"])): r for r in read_csv(plain_history)}
    ref = {int(float(r["step"])): r for r in read_csv(out / "reference_forces.csv")}
    common = sorted(set(plain) & set(ref))
    if not common:
        return None
    worst = {}
    for col in ("t_u_l", "fx", "fy", "fz"):
        diffs = [(abs(float(ref[s][col]) - float(plain[s][col])) / max(abs(float(plain[s][col])), 1e-30), s) for s in common]
        worst[col] = {"max_relative_difference": max(diffs)[0], "at_step": max(diffs)[1]}
    return {"common_steps": len(common), "first_common_step": common[0], "last_common_step": common[-1], "worst": worst,
            "note": "informational; no gate (Dual and plain primal differ at Float32 round-off and chaotic growth)"}


# ---- the analysis --------------------------------------------------------------------------------------------------------
def analyze(out: Path, plain_history: Path | None = None) -> dict:
    index = jload(out / "diag_index.json") if (out / "diag_index.json").is_file() else {}
    selfc = jload(out / "selfcheck.json") if (out / "selfcheck.json").is_file() else {}
    report: dict = {"kind": "grad03_g2_diag1_analysis", "verdict_from_kernel": index.get("verdict"), "status": index.get("status"),
                    "no_bridge_value": True, "selected_delta": None, "grad03_verdict": None, "qualification_flags": {k: False for k in FLAGS}}
    ref = index.get("reference") or {}
    ref_fail = ref.get("fail")
    # ---- non-interference / determinism, re-derived from the checksum files
    def checksums(name):
        path = out / name
        return {int(r["step"]): tuple(r[k] for k in r if k != "step") for r in read_csv(path)} if path.is_file() else {}
    a, b = checksums("reference_checksums.csv"), checksums("instrumented_checksums.csv")
    common = sorted(set(a) & set(b))
    mism = [s for s in common if a[s] != b[s]]
    selfcheck_ok = bool(common) and not mism and len(common) >= 3 and not selfc.get("sha256_mismatch_steps")
    report["self_check"] = {"compared_steps": len(common), "mismatch_steps": mism[:20], "pass_rederived": selfcheck_ok, "pass_kernel": selfc.get("pass")}
    reproduced = bool(ref_fail) and ref_fail["step"] == G2_FAIL_STEP and f"t={G2_FAIL_TIME_REPR})" in ref_fail["message"]
    report["g2_reproduction"] = {"reference_fail": ref_fail, "reproduced_step_and_time": reproduced, "plain_consistency": plain_consistency(out, plain_history)}
    rows = load_ledger(out)
    bad_row = rederive_first_bad(rows)
    kernel_bad = jload(out / "first_bad.json") if (out / "first_bad.json").is_file() else None
    report["first_bad_rederived"] = None if bad_row is None else {k: bad_row[k] for k in ("step", "idx", "stage", "field", "np", "nt")}
    consistent = (bad_row is None) == (kernel_bad is None) and (kernel_bad is None or (bad_row["step"], bad_row["stage"], bad_row["field"]) ==
                                                                  (kernel_bad["step"], kernel_bad["stage"], kernel_bad["field"]))
    report["first_bad_consistent_with_kernel"] = consistent
    # verdict (same rule as the Julia script)
    exception = (index.get("instrumented") or {}).get("exception") or ref.get("exception")
    if not index or index.get("status") in (None, "RUNNING"):
        verdict = "DIAG_INCOMPLETE"       # the kernel did not finish (e.g. killed by the time limit); ledgers are analysed below as partial evidence
    elif exception:
        verdict = "DIAG_INCOMPLETE"
    elif not selfcheck_ok:
        verdict = "DIAG_INCOMPLETE"
    elif bad_row is None and ref_fail is None:
        verdict = "DIAG_NOT_REPRODUCED"
    elif bad_row is not None and ref_fail is not None and reproduced and bad_row["step"] <= G2_FAIL_STEP and consistent:
        verdict = "DIAG_LOCALIZED"
    else:
        verdict = "DIAG_INCOMPLETE"
    report["verdict"] = verdict
    report["verdict_matches_kernel"] = verdict == index.get("verdict")
    if bad_row is None and verdict == "DIAG_INCOMPLETE":
        report["note"] = "no non-finite value in the partial ledger and the run is incomplete"
        return report
    if bad_row is None:
        report["note"] = "no non-finite value was observed up to the horizon; the horizon is not extended automatically"
        report["horizon"] = {"steps_run": (index.get("instrumented") or {}).get("steps_run"), "t_end_u_l": (index.get("instrumented") or {}).get("t_end_u_l")}
        report["next_decision"] = "user decision required (no automatic extension)"
        return report
    # ---- failure identity
    last_ok, first_bad_stage = last_finite_and_first_bad_stage(rows, bad_row)
    fb = kernel_bad or {}
    loc = jload(out / "localization.json") if (out / "localization.json").is_file() else {}
    report["failure_identity"] = {
        "first_bad_step": bad_row["step"], "first_bad_time_step_start_u_l": fb.get("time_step_start_u_l"), "first_bad_stage": bad_row["stage"],
        "stage_index": bad_row["idx"], "first_bad_field": bad_row["field"],
        "first_bad_component": "both" if bad_row["np"] and bad_row["nt"] else "primal" if bad_row["np"] else "tangent",
        "first_bad_index": fb.get("first_bad_index"), "last_finite_value": {"maxabs_primal_same_field": fb.get("last_finite_maxabs_primal_same_field"),
        "maxabs_tangent_same_field": fb.get("last_finite_maxabs_tangent_same_field")},
        "first_nonfinite_value": {"primal": fb.get("first_nonfinite_primal"), "tangent": fb.get("first_nonfinite_tangent"),
                                  "primal_repr": fb.get("first_nonfinite_primal_repr"), "tangent_repr": fb.get("first_nonfinite_tangent_repr")},
        "first_bad_element_class": fb.get("first_bad_element_class"), "last_fully_finite_stage": last_ok, "first_nonfinite_stage": first_bad_stage,
        "location": loc.get("first_bad_cell")}
    fail_step = bad_row["step"]
    # ---- growth / primal health
    curve = growth(rows, fail_step)
    report["growth"] = {"pre_failure_curve": curve[-PRE_FAILURE_STEPS:], "pattern": growth_pattern(curve),
                        "selected_steps": [p for p in curve if p["step"] in (1, 2, 5, 10, 25, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1050, 1100, 1150, 1175, 1190, fail_step - 1)]}
    first_primal = next((r for r in rows if r["np"] > 0), None)
    report["primal_health"] = {"first_primal_nonfinite": None if first_primal is None else {k: first_primal[k] for k in ("step", "stage", "field")},
                               "u_maxabs_primal_last_steps": [{"step": p["step"], "maxabs_primal": p["maxabs_primal"]} for p in curve[-10:]]}
    # ---- Poisson
    pois = [{"step": int(r["step"]), "stage": r["stage"], "iters": int(r["iters"]), "r2_value": fnum(r["r2_value"]), "r2_tangent": fnum(r["r2_tangent"])}
            for r in read_csv(out / "poisson_ledger.csv")]
    tail = [p for p in pois if fail_step - PRE_FAILURE_STEPS <= p["step"] <= fail_step]
    last20 = [p for p in pois if fail_step - 20 <= p["step"] < fail_step]
    p_tan = [{"step": r["step"], "stage": r["stage"], "field": r["field"], "maxabs_tangent": r["mt"], "maxabs_primal": r["mp"]}
             for r in rows if r["stage"] in ("project1_solve", "project2_solve", "project1_rhs", "project2_rhs") and fail_step - PRE_FAILURE_STEPS <= r["step"] <= fail_step
             and r["field"] in ("x", "r", "z")]
    cap_fraction = (sum(1 for p in last20 if p["iters"] >= ITMX) / len(last20)) if last20 else None
    report["poisson"] = {"itmx": ITMX, "iterations_and_r2_pre_failure": tail, "pressure_residual_rhs_trajectory": p_tan, "iteration_cap_fraction_last20_steps": cap_fraction}
    # ---- geometry
    geo = jload(out / "geometry_static_audit.json") if (out / "geometry_static_audit.json").is_file() else {}
    report["geometry"] = {k: {kk: v[kk] for kk in ("nonfinite_primal", "nonfinite_tangent", "min_primal", "max_primal", "min_tangent", "max_tangent")}
                          for k, v in geo.items() if k != "derived"} | {"derived": geo.get("derived")}
    geo_nonfinite = sum(v["nonfinite_primal"] + v["nonfinite_tangent"] for k, v in geo.items() if k != "derived")
    # ---- forces
    force_rows = read_csv(out / "force_ledger.csv")
    header = list(force_rows[0].keys()) if force_rows else []
    ground_ok = (index.get("instrumented") or {}).get("ground_decomposition") == "available"
    cols = [c for c in header[1:] if ground_ok or not c.startswith("ground")]
    first_force_bad = None
    for r in force_rows:
        bad = next((c for c in cols if not math.isfinite(fnum(r[c]))), None)
        if bad:
            first_force_bad = {"step": int(float(r["step"])), "column": bad}
            break
    tan_cols = [c for c in cols if c.endswith("_tan")]
    last_ok_row = next((r for r in reversed(force_rows) if int(float(r["step"])) < fail_step), None)
    report["force"] = {"first_nonfinite_force_column": first_force_bad,
                       "max_abs_tangent_by_column_last_finite_step": None if last_ok_row is None else
                       {c: abs(fnum(last_ok_row[c])) for c in tan_cols if math.isfinite(fnum(last_ok_row[c]))},
                       "ground_decomposition": (index.get("instrumented") or {}).get("ground_decomposition")}
    # ---- case and hypotheses
    pattern = report["growth"]["pattern"].get("pattern")
    log10_last = report["growth"]["pattern"].get("log10_maxabs_tangent_last")
    stage, field, comp = bad_row["stage"], bad_row["field"], report["failure_identity"]["first_bad_component"]
    ecls = fb.get("first_bad_element_class") or ("B_" if comp == "tangent" else "C_")
    tangent_only = ecls.startswith("B")      # the first non-finite element has a finite primal
    primal_first = ecls.startswith(("C", "D"))
    state_bad_in_step = any((r["np"] or r["nt"]) for r in rows if r["step"] == fail_step and not r["stage"].startswith("force_"))
    if stage.startswith("force_") and not state_bad_in_step:
        case = "E"
    elif geo_nonfinite > 0 or (stage == "measure" and field in GEOMETRY_FIELDS | {f"L{i}" for i in range(2, 12)}):
        case = "D"
    elif primal_first:
        case = "F"
    elif tangent_only and pattern in ("roughly_exponential", "slow_monotonic") and (log10_last or -99) >= FLOAT32_NEAR_LIMIT_LOG10:
        case = "A"
    elif tangent_only and stage in ("project1_solve", "project2_solve"):
        case = "C"
    elif tangent_only and pattern == "sudden_jump":
        case = "B"
    else:
        case = "unclassified"
    report["case"] = case
    report["next_experiment_proposal"] = {
        "A": "Float64 Dual precision discriminator is strongly justified",
        "B": "local diagnostic of the offending stage/operation first",
        "C": "new pre-registered Poisson tolerance/iteration sensitivity diagnostic is a candidate",
        "D": "investigate Candidate C derivative semantics first",
        "E": "diagnose/repair the force derivative path locally",
        "F": "the primal went non-finite first (plain G2 was finite): investigate the offending stage's primal arithmetic locally",
        "unclassified": "no mechanical proposal; report to the user"}[case]
    loc_cell = (loc.get("first_bad_cell") or {})
    in_band = loc_cell.get("in_band_abs_d_lt_3")
    growth_decades = None
    if len(curve) > 100:
        at100 = next((p for p in curve if p["step"] >= 100), None)
        if at100:
            growth_decades = log10_last - at100["log10_maxabs_tangent"] if log10_last is not None else None
    h: dict[str, str] = {}
    h["H1"] = ("supports" if case == "A" else "weakly_supports" if tangent_only and (log10_last or -99) >= FLOAT32_NEAR_LIMIT_LOG10 else
               "refutes" if log10_last is not None and log10_last < FLOAT32_FAR_LOG10 else "unresolved")
    h["H2"] = ("supports" if pattern == "roughly_exponential" and (growth_decades or 0) >= H2_SUPPORT_DECADES else
               "weakly_supports" if pattern in ("roughly_exponential", "slow_monotonic") and (growth_decades or 0) >= H2_WEAK_DECADES else
               "refutes" if growth_decades is not None and growth_decades < H2_WEAK_DECADES else "unresolved")
    h["H3"] = ("supports" if case == "D" else "weakly_supports" if in_band is True and tangent_only and geo_nonfinite == 0 else
               "refutes" if in_band is False and geo_nonfinite == 0 else "unresolved")
    h["H4"] = ("supports" if case == "C" else "weakly_supports" if cap_fraction is not None and cap_fraction >= 0.5 and "project" in stage else
               "refutes" if cap_fraction is not None and cap_fraction == 0.0 else "unresolved")
    h["H5"] = "supports" if case == "E" else "refutes" if state_bad_in_step else "unresolved"
    h["H6"] = ("supports" if not selfcheck_ok or (ref_fail is None) != (bad_row is None) or (ref_fail is not None and not reproduced) else
               "refutes" if reproduced and selfcheck_ok else "unresolved")
    report["hypotheses"] = h | {"note": "H1-H6 fixed before the run; any additional hypothesis must be labelled post-hoc"}
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", required=True, type=Path, help="downloaded kernel output directory")
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--write", required=True, type=Path, help="analysis JSON (written once; refuses to overwrite)")
    p.add_argument("--require-snapshots", action="store_true")
    p.add_argument("--g2-plain-history", type=Path, default=ROOT / "docs/evidence/grad03_g2_full_window_forward_bridge_2026_10_08/kernel_attempt1/plain.history.csv")
    args = p.parse_args()
    if args.write.exists():
        sys.exit("refusing to overwrite an existing analysis (the diagnostic analyzer runs once)")
    freeze = jload(args.freeze)
    integrity = verify_integrity(args.out_dir, freeze, require_snapshots=args.require_snapshots)
    report = {"integrity": integrity}
    if (args.out_dir / "stage_ledger.csv").is_file():
        try:
            report |= analyze(args.out_dir, args.g2_plain_history)
        except Exception as err:   # a malformed/partial output must still leave a stub report
            report |= {"verdict": "DIAG_INCOMPLETE", "note": f"analysis error: {type(err).__name__}: {err}"}
    else:
        report |= {"verdict": "DIAG_INCOMPLETE", "note": "no ledger"}
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.write.write_text(data)
    print(report.get("verdict"), "integrity_pass=", integrity["pass"], hashlib.sha256(data.encode()).hexdigest())
    if not integrity["pass"]:
        sys.exit(3)


if __name__ == "__main__":
    main()
