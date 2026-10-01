"""Independently integrate the preregistered FD-07 A/B force histories."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FORCE_COLUMNS = (
    "pressure_fx_solver",
    "pressure_fz_solver",
    "viscous_fx_solver",
    "viscous_fz_solver",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_window_mean(times, values, start: float, end: float) -> float:
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if (times.ndim != 1 or values.shape != times.shape or times.size < 2
            or not np.isfinite(times).all() or not np.isfinite(values).all()
            or not np.all(times > 0) or not np.all(np.diff(times) > 0)):
        raise ValueError("history needs finite, positive, strictly increasing sample times")
    if times[0] > start or times[-1] < end:
        raise ValueError("history does not bracket the exact registered window")
    t = np.r_[start, times[(times > start) & (times < end)], end]
    v = np.interp(t, times, values)
    return float(np.sum(np.diff(t) * (v[:-1] + v[1:]) * 0.5) / (end - start))


def _read_history(path: Path, start: float, end: float, force_scale: float) -> dict:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty force history: {path}")
    times = [float(row["t_u_l"]) for row in rows]
    components = {
        name.removesuffix("_solver"): exact_window_mean(
            times, [float(row[name]) for row in rows], start, end
        ) * force_scale
        for name in FORCE_COLUMNS
    }
    independently_derived = {
        "drag": components["pressure_fx"] + components["viscous_fx"],
        "downforce": -(components["pressure_fz"] + components["viscous_fz"]),
    }
    stored_derived = {
        "drag": exact_window_mean(
            times, [float(row["drag_solver"]) for row in rows], start, end
        ) * force_scale,
        "downforce": exact_window_mean(
            times, [float(row["downforce_solver"]) for row in rows], start, end
        ) * force_scale,
    }
    sample_closure_drag = max(
        abs(float(row["drag_solver"]) - float(row["pressure_fx_solver"])
            - float(row["viscous_fx_solver"])) * force_scale for row in rows
    )
    sample_closure_downforce = max(
        abs(float(row["downforce_solver"]) + float(row["pressure_fz_solver"])
            + float(row["viscous_fz_solver"])) * force_scale for row in rows
    )
    closure = {
        "max_abs_sample_drag_n": sample_closure_drag,
        "max_abs_sample_downforce_n": sample_closure_downforce,
        "window_drag_n": independently_derived["drag"] - stored_derived["drag"],
        "window_downforce_n": independently_derived["downforce"] - stored_derived["downforce"],
    }
    return {
        "window_mean_n": {**components, **independently_derived},
        "stored_total_recomputation_n": stored_derived,
        "force_closure": closure,
        "sample_count": len(rows),
        "sampled_time_bounds_u_l": [min(times), max(times)],
        "history_sha256": sha(path),
    }


def _ratio(numerator: float, denominator: float):
    return numerator / denominator if denominator != 0 else None


def analyze(outdir: Path) -> dict:
    summary_path = outdir / "summary.json"
    if summary_path.exists():
        raise FileExistsError(f"refusing existing analysis result: {summary_path}")
    plan_path = outdir / "plan.json"
    plan = json.loads(plan_path.read_text())
    plan_sha = sha(plan_path)
    expected_plan_sha = (outdir / "plan.sha256").read_text().split()[0]
    if plan_sha != expected_plan_sha:
        raise ValueError("plan differs from its preregistered hash")
    for line in (outdir / "input_files.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        if sha(outdir / relative) != expected:
            raise ValueError(f"raw input hash mismatch: {relative}")
    if sha(outdir / "input_files.sha256") != plan["input_files_manifest_sha256"]:
        raise ValueError("input manifest differs from the preregistration")
    if sha(outdir / "realized_noise.csv") != plan["realized_noise_csv_sha256"]:
        raise ValueError("realized-noise table differs from the preregistration")
    source_manifest_path = outdir / "repository_sources.sha256"
    if sha(source_manifest_path) != plan["source"]["repository_sources_manifest_sha256"]:
        raise ValueError("repository source manifest differs from preregistration")
    source_manifest = {
        relative: expected
        for expected, relative in (
            line.split("  ", 1) for line in source_manifest_path.read_text().splitlines()
        )
    }
    if source_manifest != plan["source"]["repository_source_sha256"]:
        raise ValueError("repository source manifest contents differ from the preregistration")
    for relative, expected in plan["source"]["repository_source_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f"analysis source identity mismatch: {relative}")
    body_path = Path(plan["source"]["waterlily_body_jl"])
    if sha(body_path) != plan["source"]["waterlily_body_jl_sha256"]:
        raise ValueError("pinned WaterLily Body.jl identity changed")

    start, end = plan["solver"]["analysis_window_u_l"]
    force_scale = plan["solver"]["force_conversion_n_per_solver_force"]
    cases = plan["input_cases"]
    arms = ("UPSTREAM", "NO_SIGN_CORRECTION")
    runs: dict[str, dict[str, dict]] = {arm: {} for arm in arms}
    hashes = {
        "plan.json": plan_sha,
        "plan.sha256": sha(outdir / "plan.sha256"),
        "input_files.sha256": sha(outdir / "input_files.sha256"),
        "repository_sources.sha256": sha(source_manifest_path),
        "realized_noise.csv": sha(outdir / "realized_noise.csv"),
        "initialization.csv": sha(outdir / "initialization.csv"),
        "runtime.txt": sha(outdir / "runtime.txt"),
        "preflight.txt": sha(outdir / "preflight.txt"),
        "fixed_face_control.csv": sha(outdir / "fixed_face_control.csv"),
    }
    for case_id, input_case in cases.items():
        for arm in arms:
            history = outdir / arm.lower() / f"{case_id}.csv"
            runs[arm][case_id] = _read_history(history, start, end, force_scale)
            hashes[f"{arm.lower()}/{case_id}.csv"] = runs[arm][case_id]["history_sha256"]
            if input_case["phi_sha256"] != cases[case_id]["phi_sha256"]:
                raise ValueError(f"paired geometry hash mismatch for {case_id}")

    initialization: dict[str, dict] = {arm: {} for arm in arms}
    with (outdir / "initialization.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            arm, case_id = row["arm"], row["case_id"]
            if arm not in arms or case_id not in cases:
                raise ValueError(f"unexpected initialization record: {arm}/{case_id}")
            input_hashes = dict(part.split(":", 1) for part in row["input_hashes"].split(";"))
            if row["phi_sha256"] != cases[case_id]["phi_sha256"]:
                raise ValueError(f"initialization phi hash differs from plan: {arm}/{case_id}")
            initialization[arm][case_id] = {
                "phi_sha256": row["phi_sha256"],
                "mu0_sha256": row["mu0_sha256"],
                "mu1_sha256": row["mu1_sha256"],
                "sigma_sha256": row["sigma_sha256"],
                "flow_velocity_sha256": row["flow_velocity_sha256"],
                "branch_face_count": int(row["branch_face_count"]),
                "sign_flip_face_count": int(row["sign_flip_face_count"]),
                "threshold_branch_changed_faces": int(row["threshold_branch_changed_faces"]),
                "sign_flip_decision_changed_faces": int(row["sign_flip_decision_changed_faces"]),
                "mu0_changed_vs_arm_baseline": int(row["mu0_changed_vs_arm_baseline"]),
                "mu0_max_delta_vs_arm_baseline": float(row["mu0_max_delta_vs_arm_baseline"]),
                "mu0_count_delta_gt_1e-3": int(row["mu0_count_delta_gt_1e-3"]),
                "mu1_changed_vs_arm_baseline": int(row["mu1_changed_vs_arm_baseline"]),
                "mu1_max_delta_vs_arm_baseline": float(row["mu1_max_delta_vs_arm_baseline"]),
                "mu1_count_delta_gt_1e-3": int(row["mu1_count_delta_gt_1e-3"]),
                "ab_mu0_max_delta": float(row["ab_mu0_max_delta"]),
                "ab_mu0_count_gt_1e-3": int(row["ab_mu0_count_gt_1e-3"]),
                "ab_mu1_max_delta": float(row["ab_mu1_max_delta"]),
                "ab_mu1_count_gt_1e-3": int(row["ab_mu1_count_gt_1e-3"]),
                "input_hashes": input_hashes,
            }
    for case_id in cases:
        upstream = initialization["UPSTREAM"][case_id]
        no_sign = initialization["NO_SIGN_CORRECTION"][case_id]
        if upstream["input_hashes"] != no_sign["input_hashes"]:
            raise ValueError(f"raw body-map input hashes differ across arms: {case_id}")
        if upstream["sigma_sha256"] != no_sign["sigma_sha256"]:
            raise ValueError(f"center-distance field differs across arms: {case_id}")
        if upstream["flow_velocity_sha256"] != no_sign["flow_velocity_sha256"]:
            raise ValueError(f"body velocity field differs across arms: {case_id}")
    preflight = (outdir / "preflight.txt").read_text()
    if "native_vs_diagnostic_upstream_exact=true" not in preflight:
        raise ValueError("UPSTREAM self-check did not pass")
    if "moving_ground_native_vs_no_correction_exact=true" not in preflight:
        raise ValueError("moving-ground self-check did not pass")
    if "fixed_face_scalar_control_pass=true" not in preflight:
        raise ValueError("registered FD-07 fixed-face scalar control did not pass")

    fixed_face_control = []
    with (outdir / "fixed_face_control.csv").open(newline="") as stream:
        fixed_face_control = list(csv.DictReader(stream))
    expected_control = plan["fixed_face_control"]
    expected_keys = {
        (map_name, run_id)
        for map_name in expected_control["maps"]
        for run_id in expected_control["runs"]
    }
    by_key = {(row["map"], row["run_id"]): row for row in fixed_face_control}
    if set(by_key) != expected_keys or len(by_key) != len(fixed_face_control):
        raise ValueError("fixed-face control map/run identities differ from preregistration")
    tolerance = expected_control["max_delta_abs_tolerance"]
    for map_name in expected_control["maps"]:
        for run_id in expected_control["runs"]:
            row = by_key[(map_name, run_id)]
            if row["control_pass"].lower() != "true":
                raise ValueError(f"fixed-face control reported failure for {map_name}/{run_id}")
            if int(row["face_count"]) != expected_control["fixed_face_count_per_run"]:
                raise ValueError(f"fixed-face count differs from preregistration for {map_name}/{run_id}")
            if float(row["recorded_mu0_max_abs_error"]) > expected_control["recorded_mu0_rowwise_abs_tolerance"]:
                raise ValueError(f"fixed-face mu0 recomputation differs from recorded values for {map_name}/{run_id}")
            if expected_control["corrected_face_distance_bitwise_equal"] and row["corrected_face_bitwise_equal"].lower() != "true":
                raise ValueError(f"fixed-face corrected distances differ from recorded Float32 values for {map_name}/{run_id}")
            if run_id == "baseline":
                if (int(row["corrected_count_abs_delta_gt_1e-3"]) != 0
                        or int(row["uncorrected_count_abs_delta_gt_1e-3"]) != 0
                        or float(row["corrected_max_abs_delta"]) > tolerance
                        or float(row["uncorrected_max_abs_delta"]) > tolerance):
                    raise ValueError(f"fixed-face baseline is not zero relative to itself for map {map_name}")
                continue
            expected = expected_control["expected_baseline_relative"][map_name][run_id]
            if int(row["corrected_count_abs_delta_gt_1e-3"]) != expected["corrected_count_abs_delta_gt_1e-3"]:
                raise ValueError(f"fixed-face corrected jump count differs for {map_name}/{run_id}")
            if abs(float(row["corrected_max_abs_delta"]) - expected["corrected_max_abs_delta"]) > tolerance:
                raise ValueError(f"fixed-face corrected maximum jump differs for {map_name}/{run_id}")
            if int(row["uncorrected_count_abs_delta_gt_1e-3"]) != expected["uncorrected_count_abs_delta_gt_1e-3"]:
                raise ValueError(f"fixed-face uncorrected jump count differs for {map_name}/{run_id}")
            if abs(float(row["uncorrected_max_abs_delta"]) - expected["uncorrected_max_abs_delta"]) > tolerance:
                raise ValueError(f"fixed-face uncorrected maximum jump differs for {map_name}/{run_id}")

    responses = ("drag", "downforce", "pressure_fx", "pressure_fz", "viscous_fx", "viscous_fz")
    baseline_arm_difference = {
        response: (
            runs["NO_SIGN_CORRECTION"]["baseline"]["window_mean_n"][response]
            - runs["UPSTREAM"]["baseline"]["window_mean_n"][response]
        )
        for response in responses
    }
    pair_results = {arm: {} for arm in arms}
    arm_comparisons = {}
    for seed in plan["perturbations"]["seeds"]:
        for amplitude in plan["perturbations"]["amplitudes_m"]:
            tag = f"{amplitude:.0e}"
            case_plus = f"seed_{seed}_plus_{tag}"
            case_minus = f"seed_{seed}_minus_{tag}"
            key = f"seed_{seed}@{tag}"
            pair_results_per_arm = {}
            for arm in arms:
                baseline = runs[arm]["baseline"]["window_mean_n"]
                plus = runs[arm][case_plus]["window_mean_n"]
                minus = runs[arm][case_minus]["window_mean_n"]
                record = {}
                for response in responses:
                    dplus = plus[response] - baseline[response]
                    dminus = minus[response] - baseline[response]
                    odd = (plus[response] - minus[response]) / 2
                    even = (plus[response] + minus[response]) / 2 - baseline[response]
                    record[response] = {
                        "plus_n": plus[response],
                        "minus_n": minus[response],
                        "baseline_n": baseline[response],
                        "delta_plus_n": dplus,
                        "delta_minus_n": dminus,
                        "abs_delta_plus_n": abs(dplus),
                        "abs_delta_minus_n": abs(dminus),
                        "odd_n": odd,
                        "even_n": even,
                    }
                pair_results_per_arm[arm] = record
                pair_results[arm][key] = record
            ratios = {}
            for response in responses:
                a = pair_results_per_arm["UPSTREAM"][response]
                b = pair_results_per_arm["NO_SIGN_CORRECTION"][response]
                ratios[response] = {
                    "abs_delta_plus_b_over_a": _ratio(b["abs_delta_plus_n"], a["abs_delta_plus_n"]),
                    "abs_delta_minus_b_over_a": _ratio(b["abs_delta_minus_n"], a["abs_delta_minus_n"]),
                    "abs_odd_b_over_a": _ratio(abs(b["odd_n"]), abs(a["odd_n"])),
                    "abs_even_b_over_a": _ratio(abs(b["even_n"]), abs(a["even_n"])),
                }
            arm_comparisons[key] = ratios

    with (outdir / "realized_noise.csv").open(newline="") as stream:
        realized = list(csv.DictReader(stream))
    result = {
        "kind": "fd07_sign_consistency_causal_cpu_diagnostic_summary",
        "evidence_class": "bounded_causal_diagnostic_only",
        "plan_sha256": plan_sha,
        "window_u_l": [start, end],
        "integration": "independent Python piecewise-linear exact-endpoint trapezoid",
        "force_conversion_n_per_solver_force": force_scale,
        "initialization": initialization,
        "fixed_face_control": fixed_face_control,
        "runs": runs,
        "baseline_no_sign_minus_upstream_n": baseline_arm_difference,
        "paired_force_response": pair_results,
        "no_sign_over_upstream_magnitude_ratios": arm_comparisons,
        "realized_noise": realized,
        "raw_input_and_history_sha256": hashes,
        "source_file_sha256": plan["source"]["repository_source_sha256"],
        "interpretation_rule": plan["primary_comparisons_fixed_before_force_inspection"],
        "limitations": plan["limitations"],
        "flags": plan["flags"],
    }
    with summary_path.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


if __name__ == "__main__":
    result = analyze(Path(sys.argv[1]).resolve())
    print(json.dumps({
        "summary_sha256": sha(Path(sys.argv[1]).resolve() / "summary.json"),
        "runs_per_arm": len(result["runs"]["UPSTREAM"]),
        "pair_count_per_arm": len(result["paired_force_response"]["UPSTREAM"]),
    }, indent=2))
