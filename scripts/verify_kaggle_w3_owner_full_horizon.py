"""Host-side verification and conservative classification of W3 owner diagnostics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

FORCE_HEADER = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
    "downforce_solver", "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver",
    "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver",
]
COMPONENTS = FORCE_HEADER[2:]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def registered_qualification_flags(criteria: dict[str, Any]) -> dict[str, bool]:
    flags = criteria.get("qualification_flags")
    if flags is None:
        flags = criteria.get("evidence_output", {}).get("qualification_flags")
    if not isinstance(flags, dict):
        raise ValueError("qualification flags are missing from immutable criteria")
    return flags


def read_csv(path: Path) -> list[dict[str, float]]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FORCE_HEADER:
            raise ValueError(f"force CSV schema mismatch: {path}")
        return [{key: float(value) for key, value in row.items()} for row in reader]


def read_numeric_csv(path: Path) -> list[dict[str, float]]:
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV header missing: {path}")
        return [{key: float(value) for key, value in row.items()} for row in reader]


def verify_manifest(folder: Path) -> tuple[dict[str, str], str]:
    manifest_path = folder / "sha256.json"
    manifest = read_json(manifest_path)
    actual = {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and path.name not in {"sha256.json", "DONE", "ERROR.txt"}
    }
    require(actual == set(manifest), "downloaded artifact inventory differs from output SHA manifest")
    for name, expected in manifest.items():
        path = folder / name
        require(path.is_file() and sha256(path) == expected, f"output artifact SHA mismatch: {name}")
    return manifest, sha256(manifest_path)


def clipped_window(rows: list[dict[str, float]], start: float, end: float) -> list[dict[str, float]]:
    if len(rows) < 2:
        raise ValueError("at least two force rows are required")
    rows = sorted(rows, key=lambda row: (row["t_u_l"], row["step"]))

    def endpoint(target: float) -> dict[str, float]:
        left = [row for row in rows if row["t_u_l"] <= target]
        right = [row for row in rows if row["t_u_l"] >= target]
        if not left or not right:
            raise ValueError(f"force rows do not bracket tU/L={target}")
        a, b = left[-1], right[0]
        if a["t_u_l"] == b["t_u_l"]:
            return dict(a)
        ratio = (target - a["t_u_l"]) / (b["t_u_l"] - a["t_u_l"])
        result = {key: a[key] + ratio * (b[key] - a[key]) for key in FORCE_HEADER}
        result["t_u_l"] = target
        return result

    return [endpoint(start)] + [row for row in rows if start < row["t_u_l"] < end] + [endpoint(end)]


def time_weighted_mean(rows: list[dict[str, float]], column: str) -> float:
    if len(rows) < 2:
        raise ValueError("time-weighted force mean needs at least two rows")
    numerator = 0.0
    duration = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        if dt < 0:
            raise ValueError("force times are not monotonic")
        numerator += 0.5 * (left[column] + right[column]) * dt
        duration += dt
    if duration <= 0:
        raise ValueError("force window has zero duration")
    return numerator / duration


def force_integrals(rows: list[dict[str, float]]) -> dict[str, float]:
    window = clipped_window(rows, 80.0, 120.0)
    first = clipped_window(rows, 80.0, 100.0)
    second = clipped_window(rows, 100.0, 120.0)
    drag = time_weighted_mean(window, "drag_solver")
    downforce = time_weighted_mean(window, "downforce_solver")
    first_drag = time_weighted_mean(first, "drag_solver")
    second_drag = time_weighted_mean(second, "drag_solver")
    first_downforce = time_weighted_mean(first, "downforce_solver")
    second_downforce = time_weighted_mean(second, "downforce_solver")
    return {
        "window_time_weighted_drag_solver": drag,
        "window_time_weighted_downforce_solver": downforce,
        "first_half_time_weighted_drag_solver": first_drag,
        "second_half_time_weighted_drag_solver": second_drag,
        "first_half_time_weighted_downforce_solver": first_downforce,
        "second_half_time_weighted_downforce_solver": second_downforce,
        "stationarity_relative_half_window_drift_drag": abs(first_drag - second_drag) / max(abs(drag), 2.220446049250313e-16),
        "stationarity_relative_half_window_drift_downforce": abs(first_downforce - second_downforce) / max(abs(downforce), 2.220446049250313e-16),
    }


def raw_force_rows_finite(rows: list[dict[str, float]]) -> bool:
    return bool(rows) and all(math.isfinite(row[key]) for row in rows for key in FORCE_HEADER[2:])


def validate_kernel_identity(criteria_kernel_id: str, observed_kernel_id: str) -> None:
    if not observed_kernel_id or observed_kernel_id != criteria_kernel_id:
        raise ValueError(
            f"actual Kaggle kernel id {observed_kernel_id!r} differs from immutable criteria id "
            f"{criteria_kernel_id!r}"
        )


def force_closure(rows: list[dict[str, float]], criteria: dict) -> dict[str, Any]:
    atol = criteria["causal_decision_rules"]["force_component_absolute_tolerance"]
    rtol = criteria["causal_decision_rules"]["force_component_relative_tolerance"]
    maximum_residual = 0.0
    checked = 0
    passed = True
    for row in rows:
        if not all(math.isfinite(row[key]) for key in FORCE_HEADER[2:]):
            passed = False
            continue
        for axis in "xyz":
            total = row[f"f{axis}_solver"]
            pressure = row[f"pressure_f{axis}_solver"]
            viscous = row[f"viscous_f{axis}_solver"]
            residual = abs(total - pressure - viscous)
            maximum_residual = max(maximum_residual, residual)
            checked += 1
            passed &= math.isclose(total, pressure + viscous, rel_tol=rtol, abs_tol=atol)
        passed &= math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=rtol, abs_tol=atol)
        passed &= math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=rtol, abs_tol=atol)
    return {"passed": bool(passed and checked == len(rows) * 3),
            "checked_axis_components": checked, "maximum_absolute_residual": maximum_residual}


def exact_zero_history(rows: list[dict[str, float]]) -> bool:
    return bool(rows) and all(math.isfinite(row[key]) and row[key] == 0.0
                               for row in rows for key in FORCE_HEADER[2:])


def strictly_increasing(values: list[float]) -> bool:
    return bool(values) and all(right > left for left, right in zip(values, values[1:]))


def production_fix_gate(retained_control_healthy: bool,
                        natural_replicates: list[dict[str, Any]]) -> bool:
    if not retained_control_healthy or len(natural_replicates) != 2:
        return False
    classes = [item.get("corruption_class") for item in natural_replicates]
    return all(item.get("owner_weakref_cleared") is True
               and item.get("reproducible_corruption_observed") is True
               and item.get("status") == "completed"
               and item.get("progress_t_u_l_reached", 0.0) >= 120.0
               for item in natural_replicates) and classes[0] == classes[1] \
        and classes[0] != "no_post_collection_corruption_observed"


def compare_forces(reference: list[dict[str, float]], candidate: list[dict[str, float]],
                   after_step: int, criteria: dict, *, before_collection: bool = False) -> dict[str, Any]:
    rules = criteria["causal_decision_rules"]
    by_step = {int(row["step"]): row for row in reference}
    comparisons = []
    threshold_abs = rules["force_divergence_absolute_tolerance"]
    threshold_rel = rules["force_divergence_relative_tolerance"]
    max_abs = 0.0
    max_relative = 0.0
    diverged = False
    for row in candidate:
        step = int(row["step"])
        if (step >= after_step if before_collection else step <= after_step) or step not in by_step:
            continue
        other = by_step[step]
        if not all(math.isfinite(row[key]) and math.isfinite(other[key]) for key in COMPONENTS):
            comparisons.append(step)
            diverged = True
            continue
        component_errors = [abs(row[key] - other[key]) for key in COMPONENTS]
        scale = max(1.0, *(abs(other[key]) for key in COMPONENTS))
        local_max = max(component_errors)
        relative = local_max / scale
        max_abs = max(max_abs, local_max)
        max_relative = max(max_relative, relative)
        comparisons.append(step)
        diverged |= local_max > threshold_abs + threshold_rel * scale
    return {"compared_samples": len(comparisons), "common_steps_after_collection": comparisons,
            "maximum_absolute_component_difference": max_abs,
            "maximum_scaled_component_difference": max_relative,
            "diverged_beyond_registered_tolerance": diverged}


def summarize_arm(root: Path, arm_id: str, criteria: dict) -> dict[str, Any]:
    arm_dir = root / "arms" / arm_id
    summary_path = arm_dir / "arm_summary.json"
    result: dict[str, Any] = {"arm_id": arm_id, "status": "missing"}
    if not summary_path.is_file():
        return result
    summary = read_json(summary_path)
    result["status"] = summary.get("status")
    result["summary"] = summary
    result["summary_sha256"] = sha256(summary_path)
    force_path = arm_dir / "v16.forces.csv"
    if not force_path.is_file():
        result["error"] = "force CSV missing"
        return result
    rows = read_csv(force_path)
    result["force_rows"] = len(rows)
    result["force_csv_sha256"] = sha256(force_path)
    result["force_row_count_matches_summary"] = len(rows) == summary.get("force_rows")
    result["force_steps_strictly_increasing"] = strictly_increasing([row["step"] for row in rows])
    result["force_times_strictly_increasing"] = strictly_increasing([row["t_u_l"] for row in rows])
    result["all_raw_force_components_finite"] = raw_force_rows_finite(rows)
    result["force_history_exact_zero"] = exact_zero_history(rows)
    result["component_closure"] = force_closure(rows, criteria)
    result["force_samples_bracket_window"] = bool(rows) and rows[0]["t_u_l"] <= 80 and rows[-1]["t_u_l"] >= 120
    stride = criteria["measurement"]["force_sample_stride_steps"]
    result["force_sampling_steps"] = [int(row["step"]) for row in rows]
    result["force_sampling_regular"] = all(
        int(right["step"] - left["step"]) == stride
        or (right is rows[-1] and right["t_u_l"] >= 120)
        for left, right in zip(rows, rows[1:]))
    result["force_sampling_regular"] &= all(
        int(row["step"]) % stride == 0 or (row is rows[-1] and row["t_u_l"] >= 120.0)
        for row in rows)
    window_rows = [row for row in rows if 80.0 <= row["t_u_l"] <= 120.0]
    result["registered_window_sample_count"] = len(window_rows)
    result["minimum_registered_window_sample_count_met"] = (
        len(window_rows) >= criteria["measurement"]["minimum_window_samples"])
    if result["all_raw_force_components_finite"]:
        try:
            result["host_force_integrals"] = force_integrals(rows)
        except (ValueError, ZeroDivisionError) as error:
            result["host_force_integrals_error"] = str(error)
    else:
        result["host_force_integrals_error"] = "raw force rows include nonfinite values; window integration is undefined"
    progress_path = arm_dir / "progress.csv"
    progress = read_numeric_csv(progress_path) if progress_path.is_file() else []
    result["progress_rows"] = len(progress)
    progress_steps = [int(row["step"]) for row in progress]
    result["progress_steps_contiguous"] = progress_steps == list(range(1, len(progress_steps) + 1))
    result["progress_rows_match_summary"] = len(progress) == summary.get("solver_steps")
    step_limit = criteria["measurement"].get("max_solver_steps_safety_limit")
    result["solver_step_safety_limit_met"] = (
        step_limit is None or not progress_steps or max(progress_steps) <= step_limit
    )
    transitions = [int(row["step"]) for previous, row in zip(progress, progress[1:])
                   if previous["owner_weakref_alive"] == 1.0 and row["owner_weakref_alive"] == 0.0]
    if progress and progress[0]["owner_weakref_alive"] == 0.0 and summary.get("owner_alive_at_setup_return") is True:
        transitions.insert(0, int(progress[0]["step"]))
    if summary.get("owner_alive_at_setup_return") is False:
        transitions.insert(0, 0)
    for event in summary.get("forced_gc_events", []):
        if event.get("weakref_before") is True and event.get("weakref_after") is False:
            transitions.insert(0, int(event.get("after_warmup_step", 1)))
    result["host_first_owner_collection_step"] = transitions[0] if transitions else None
    result["owner_weakref_cleared"] = bool(progress) and any(row["owner_weakref_alive"] == 0.0 for row in progress)
    result["progress_t_u_l_reached"] = progress[-1]["t_u_l"] if progress else 0.0
    fields_path = arm_dir / "field_diagnostics.csv"
    fields = read_numeric_csv(fields_path) if fields_path.is_file() else []
    result["field_diagnostic_rows"] = len(fields)
    result["field_samples_finite"] = bool(fields) and all(
        row["finite_u"] == 1.0 and row["finite_p"] == 1.0 for row in fields)
    collection_step = result["host_first_owner_collection_step"]
    post_rows = [row for row in rows if collection_step is not None and row["step"] > collection_step]
    result["post_collection_force_rows"] = len(post_rows)
    result["force_history_exact_zero_after_collection"] = exact_zero_history(post_rows)
    result["force_components_nonfinite_after_collection"] = bool(post_rows) and any(
        not math.isfinite(row[key]) for row in post_rows for key in FORCE_HEADER[2:])
    post_fields = [row for row in fields if collection_step is not None and row["step"] >= collection_step]
    result["field_nonfinite_after_collection"] = any(
        row["finite_u"] != 1.0 or row["finite_p"] != 1.0 for row in post_fields)
    result["candidate_probe_rows"] = sum(1 for _ in (arm_dir / "candidate_probes.csv").open()) - 1 \
        if (arm_dir / "candidate_probes.csv").is_file() else 0
    result["cuda_memory_peak_sampled_bytes"] = max(
        (row["cuda_used_memory_bytes"] for row in read_numeric_csv(arm_dir / "cuda_memory.csv")),
        default=0.0) if (arm_dir / "cuda_memory.csv").is_file() else 0.0
    result["v4_zero_force_correspondence"] = (
        result["force_history_exact_zero"] and summary.get("finite_u_at_end") is True
        and summary.get("finite_p_at_end") is True and result["progress_t_u_l_reached"] >= 120.0)
    if result.get("host_force_integrals"):
        scale = criteria["fixture"]["force_scale_n_per_solver_unit"]
        area_solver = criteria["fixture"]["reference_area_m2"] / criteria["fixture"]["spacing_m"] ** 2
        host_metrics = result["host_force_integrals"]
        result["host_physical_metrics"] = {
            "drag_time_weighted_n": host_metrics["window_time_weighted_drag_solver"] * scale,
            "downforce_time_weighted_n": host_metrics["window_time_weighted_downforce_solver"] * scale,
            "cd_time_weighted": host_metrics["window_time_weighted_drag_solver"] / (0.5 * area_solver),
        }
        runner_metrics = summary.get("measurement_metrics", {})
        tolerance = criteria["measurement"]["host_recompute_relative_tolerance"]
        result["runner_host_metric_match"] = all(
            key in runner_metrics and math.isclose(runner_metrics[key], value,
                rel_tol=tolerance, abs_tol=criteria["measurement"]["host_recompute_absolute_tolerance"])
            for key, value in host_metrics.items())
    return result


def classify_arms(arms: dict[str, dict[str, Any]], criteria: dict) -> dict[str, Any]:
    a_natural = arms["A-natural"]
    a_forced = arms["A-forced"]
    b_natural = [arms["B-natural-1"], arms["B-natural-2"]]
    b_forced = [arms["B-forced-1"], arms["B-forced-2"]]
    a_natural_rows = read_csv(Path(criteria["_output_root"]) / "arms/A-natural/v16.forces.csv") \
        if (Path(criteria["_output_root"]) / "arms/A-natural/v16.forces.csv").is_file() else []
    a_forced_rows = read_csv(Path(criteria["_output_root"]) / "arms/A-forced/v16.forces.csv") \
        if (Path(criteria["_output_root"]) / "arms/A-forced/v16.forces.csv").is_file() else []
    a_forced_comparison = compare_forces(a_natural_rows, a_forced_rows, -1, criteria) \
        if a_natural_rows and a_forced_rows else {"diverged_beyond_registered_tolerance": True}
    retained_control_healthy = (
        a_natural.get("status") == "completed" and a_forced.get("status") == "completed"
        and a_natural.get("progress_t_u_l_reached", 0.0) >= 120.0
        and a_forced.get("progress_t_u_l_reached", 0.0) >= 120.0
        and a_natural.get("owner_weakref_cleared") is False
        and a_forced.get("owner_weakref_cleared") is False
        and a_natural.get("field_samples_finite") is True
        and a_forced.get("field_samples_finite") is True
        and a_natural.get("all_raw_force_components_finite") is True
        and a_forced.get("all_raw_force_components_finite") is True
        and a_natural.get("component_closure", {}).get("passed") is True
        and a_forced.get("component_closure", {}).get("passed") is True
        and a_natural.get("force_sampling_regular") is True
        and a_forced.get("force_sampling_regular") is True
        and a_natural.get("force_row_count_matches_summary") is True
        and a_forced.get("force_row_count_matches_summary") is True
        and a_natural.get("force_steps_strictly_increasing") is True
        and a_forced.get("force_steps_strictly_increasing") is True
        and a_natural.get("force_times_strictly_increasing") is True
        and a_forced.get("force_times_strictly_increasing") is True
        and a_natural.get("minimum_registered_window_sample_count_met") is True
        and a_forced.get("minimum_registered_window_sample_count_met") is True
        and a_natural.get("progress_steps_contiguous") is True
        and a_forced.get("progress_steps_contiguous") is True
        and a_natural.get("progress_rows_match_summary") is True
        and a_forced.get("progress_rows_match_summary") is True
        and a_natural.get("runner_host_metric_match") is True
        and a_forced.get("runner_host_metric_match") is True
        and not a_natural.get("force_history_exact_zero", True)
        and not a_forced.get("force_history_exact_zero", True)
        and not a_forced_comparison.get("diverged_beyond_registered_tolerance", True)
    )
    post_collection = []
    for arm_id, item in zip(("B-natural-1", "B-natural-2"), b_natural):
        collection_step = item.get("host_first_owner_collection_step")
        rows = read_csv(Path(criteria["_output_root"]) / f"arms/{arm_id}/v16.forces.csv") \
            if (Path(criteria["_output_root"]) / f"arms/{arm_id}/v16.forces.csv").is_file() else []
        comparison = compare_forces(a_natural_rows, rows,
                                    collection_step if collection_step is not None else math.inf, criteria) \
            if a_natural_rows and rows and collection_step is not None else {"diverged_beyond_registered_tolerance": False}
        pre_collection_rows = [row for row in rows if collection_step is not None and row["step"] < collection_step]
        pre_comparison = compare_forces(a_natural_rows, pre_collection_rows, collection_step or 0,
                                        criteria, before_collection=True) \
            if a_natural_rows and collection_step is not None else {"compared_samples": 0,
                "diverged_beyond_registered_tolerance": False}
        pre_collection_consistent = (
            pre_comparison.get("diverged_beyond_registered_tolerance") is False
            or pre_comparison.get("compared_samples") == 0
        )
        enough_post_samples = item.get("post_collection_force_rows", 0) >= \
            criteria["causal_decision_rules"]["minimum_post_collection_force_samples"]
        post_force_diverged = comparison.get("diverged_beyond_registered_tolerance") is True
        if (item.get("force_history_exact_zero_after_collection") and enough_post_samples
                and post_force_diverged and pre_collection_consistent):
            corruption_class = "post_collection_exact_zero_force_history"
        elif (enough_post_samples and
              (item.get("force_components_nonfinite_after_collection")
               or item.get("field_nonfinite_after_collection")) and pre_collection_consistent):
            corruption_class = "post_collection_nonfinite_force_or_fields"
        elif enough_post_samples and post_force_diverged and pre_collection_consistent:
            corruption_class = "post_collection_force_divergence"
        else:
            corruption_class = "no_post_collection_corruption_observed"
        corrupt = corruption_class != "no_post_collection_corruption_observed"
        post_collection.append({"arm_id": arm_id, "collection_step": collection_step,
                                "status": item.get("status"),
                                "progress_t_u_l_reached": item.get("progress_t_u_l_reached", 0.0),
                                "owner_weakref_cleared": item.get("owner_weakref_cleared") is True,
                                "comparison_to_A_natural": comparison,
                                "pre_collection_comparison_to_A_natural": pre_comparison,
                                "pre_collection_force_consistent_with_A": pre_collection_consistent,
                                "corruption_class": corruption_class,
                                "reproducible_corruption_observed": corrupt})
    both_natural_collected = all(item.get("owner_weakref_cleared") is True for item in b_natural)
    both_natural_corrupt = all(item["reproducible_corruption_observed"] for item in post_collection)
    same_natural_failure_class = (
        all(item.get("v4_zero_force_correspondence") is True for item in b_natural)
        or (post_collection[0]["corruption_class"] == post_collection[1]["corruption_class"]
            and post_collection[0]["reproducible_corruption_observed"]
            and post_collection[1]["reproducible_corruption_observed"])
    )
    strong_v4_mapping = (
        retained_control_healthy and both_natural_collected and both_natural_corrupt
        and all(item.get("v4_zero_force_correspondence") is True for item in b_natural)
    )
    owner_bug_confirmed = production_fix_gate(retained_control_healthy, post_collection)
    if strong_v4_mapping:
        classification = "full_horizon_owner_lifetime_root_cause_strongly_supported_for_v4_zero_force_symptom"
    elif owner_bug_confirmed:
        classification = "owner_lifetime_implementation_bug_confirmed_exact_v4_zero_force_symptom_unresolved"
    elif any(item.get("owner_weakref_cleared") for item in b_forced) and any(
            item.get("all_raw_force_components_finite") is False
            or item.get("force_history_exact_zero") for item in b_forced):
        classification = "forced_gc_sensitivity_only_natural_production_path_not_confirmed"
    elif all(item.get("status") == "completed" for item in b_natural) and not both_natural_collected:
        classification = "ordinary_gc_owner_lifetime_hypothesis_weakened_owner_not_collected_in_natural_horizon"
    else:
        classification = "inconclusive_no_production_fix_authorized"
    return {
        "classification": classification,
        "retained_control_healthy": retained_control_healthy,
        "A_forced_vs_A_natural_force_comparison": a_forced_comparison,
        "both_B_natural_collected": both_natural_collected,
        "both_B_natural_corrupt_after_collection": both_natural_corrupt,
        "same_B_natural_failure_class": same_natural_failure_class,
        "B_natural_post_collection_comparisons": post_collection,
        "strong_v4_zero_force_mapping": strong_v4_mapping,
        "owner_lifetime_bug_confirmed": owner_bug_confirmed,
        "production_fix_gate_met": owner_bug_confirmed,
        "B_forced_support_only": b_forced,
        "qualification": False,
    }


def verify(download: Path, *, criteria_path: Path, criteria_dataset_dir: Path,
           w3_dataset_dir: Path, actual_kernel_id: str, kernel_version: int, status_path: Path,
           log_path: Path, host_verifier_path: Path) -> dict[str, Any]:
    criteria_path = Path(criteria_path)
    criteria_sha = sha256(criteria_path)
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    require(sidecar.read_text().strip() == criteria_sha, "criteria sidecar mismatch")
    criteria = read_json(criteria_path)
    require(criteria.get("immutable") is True and criteria.get("registered_before_computation") is True,
            "full-horizon criteria were not preregistered")
    require(criteria.get("evidence_type") == "diagnostic_only", "criteria evidence class mismatch")
    validate_kernel_identity(criteria["kernel_id"], actual_kernel_id)
    require(kernel_version == criteria.get("kernel_version"), "exact Kaggle kernel version differs from criteria")
    criteria_manifest_path = Path(criteria_dataset_dir) / "w3_owner_full_horizon_dataset_manifest.json"
    criteria_manifest = read_json(criteria_manifest_path)
    require(criteria_manifest.get("dataset_id") == criteria["criteria_dataset_id"], "criteria dataset id mismatch")
    for name, expected in criteria_manifest["files"].items():
        require(sha256(Path(criteria_dataset_dir) / name) == expected, f"criteria dataset file SHA mismatch: {name}")
    type_result_path = Path(criteria_dataset_dir) / "w3_owner_type_probe_result.json"
    type_result_sha = sha256(type_result_path)
    require(type_result_sha == criteria["type_probe_prerequisite"]["result_sha256"], "type probe result SHA mismatch")
    type_result = read_json(type_result_path)
    require(type_result.get("host_verification_passed") is True, "type probe result was not host-verified")
    require(type_result.get("exact_kernel_ref") == "ramhachi888/cfd-opt-sdf-w3-owner-type-probe/2",
            "type probe version mismatch")
    identity = type_result["runtime_type_identity"]
    require(identity.get("cuda_device_memory_is_parameter") is True
            and identity.get("cuda_device_memory_is_module_binding") is True,
            "CUDA/CUDACore owner memory type identity was not established")
    w3_manifest_path = Path(w3_dataset_dir) / "w3_v16_dataset_manifest.json"
    require(sha256(w3_manifest_path) == criteria["w3_input"]["dataset_manifest_sha256"],
            "W3 input manifest SHA mismatch")
    w3_manifest = read_json(w3_manifest_path)
    require(w3_manifest.get("dataset_id") == criteria["w3_input"]["dataset_id"], "W3 dataset id mismatch")
    for name, expected in w3_manifest["files"].items():
        require(sha256(Path(w3_dataset_dir) / name) == expected, f"W3 input file SHA mismatch: {name}")

    download = Path(download)
    folder = download / "w3_owner_full_horizon" if (download / "w3_owner_full_horizon").is_dir() else download
    manifest, output_manifest_sha = verify_manifest(folder)
    status_text = Path(status_path).read_text()
    status_name = "COMPLETE" if "COMPLETE" in status_text.upper() else "ERROR" if "ERROR" in status_text.upper() else "OTHER"
    log_path = Path(log_path)
    require(log_path.is_file(), "exact-version Kaggle log missing")
    log_sha = sha256(log_path)
    fingerprint_path = folder / "fingerprint.json"
    execution_path = folder / "execution.json"
    if status_name != "COMPLETE":
        return {
            "evidence_type": "diagnostic_only",
            "diagnostic_id": criteria["criteria_id"],
            "criteria_path": str(criteria_path), "criteria_sha256": criteria_sha,
            "criteria_dataset_manifest_sha256": sha256(criteria_manifest_path),
            "type_probe_prerequisite": {
                "exact_kernel_ref": type_result["exact_kernel_ref"],
                "criteria_sha256": type_result["criteria_sha256"],
                "result_sha256": type_result_sha,
                "runtime_type_identity": identity,
            },
            "kernel_id": criteria["kernel_id"], "observed_kernel_id": actual_kernel_id,
            "kernel_version": kernel_version,
            "exact_kernel_ref": f"{actual_kernel_id}/{kernel_version}",
            "terminal_status": status_name,
            "kaggle_status_sha256": sha256(Path(status_path)),
            "kaggle_log_sha256": log_sha,
            "output_manifest_sha256": output_manifest_sha,
            "output_artifacts": manifest,
            "error_txt_sha256": sha256(folder / "ERROR.txt") if (folder / "ERROR.txt").is_file() else None,
            "host_verifier_sha256": sha256(Path(host_verifier_path)),
            "host_artifact_verification_passed": True,
            "host_verification_passed": False,
            "causal_decision": {
                "classification": "incomplete_kaggle_run_no_owner_causal_decision",
                "production_fix_gate_met": False,
                "qualification": False,
            },
            "qualification": False,
            "qualification_flags": registered_qualification_flags(criteria),
            "claim_scope": "exact-version diagnostic artifact provenance only; no owner-lifetime conclusion or solver qualification",
        }
    require(fingerprint_path.is_file() and execution_path.is_file(), "runtime fingerprint or execution record missing")
    require((folder / "DONE").is_file() and not (folder / "ERROR.txt").exists(),
            "completed full-horizon output lacks DONE or includes ERROR.txt")
    fingerprint = read_json(fingerprint_path)
    execution = read_json(execution_path)
    require(execution.get("completed") is True and execution.get("diagnostic_only") is True
            and execution.get("qualification") is False, "execution completion/claim markers mismatch")
    require(fingerprint.get("kernel_id") == criteria["kernel_id"], "kernel id mismatch")
    require(fingerprint.get("criteria", {}).get("criteria_sha256") == criteria_sha, "runtime criteria SHA mismatch")
    require(fingerprint.get("source_commit") == criteria["source_commit"], "source commit mismatch")
    require(fingerprint.get("source_files") == criteria["source_files"], "runtime source hashes mismatch")
    require(fingerprint.get("runner_sha256") == criteria["source_files"]["runner"]["sha256"], "runner SHA mismatch")
    require(fingerprint.get("selected_gpu_uuid"), "selected GPU UUID missing")
    require(fingerprint.get("cuda_visible_devices") == "0", "CUDA_VISIBLE_DEVICES mismatch")
    gpu_rows = fingerprint.get("gpu_inventory", [])
    backend = criteria["backend"]
    require(len(gpu_rows) == backend["gpu_count"], "GPU inventory count mismatch")
    require(all(backend["gpu_name"] in row and backend["driver_version"] in row for row in gpu_rows),
            "T4 model or NVIDIA driver mismatch")
    require(fingerprint.get("owner_type_prerequisite", {}).get("result_sha256") == type_result_sha,
            "runtime owner type result binding mismatch")
    require(execution.get("criteria_sha256") == criteria_sha, "execution criteria SHA mismatch")
    require(execution.get("source_commit") == criteria["source_commit"], "execution source commit mismatch")
    require(execution.get("arms_in_registered_order") == criteria["arm_order"], "arm order mismatch")

    arms = {arm_id: summarize_arm(folder, arm_id, criteria) for arm_id in criteria["arm_order"]}
    criteria_for_classification = dict(criteria)
    criteria_for_classification["_output_root"] = str(folder)
    decision = classify_arms(arms, criteria_for_classification)
    for arm_id, item in arms.items():
        summary = item.get("summary", {})
        if item.get("status") != "completed":
            item["arm_identity_checks_skipped"] = True
            continue
        require(summary.get("canonical_phi_fortran_sha256") == criteria["w3_input"]["phi_fortran_sha256"],
                f"{arm_id} canonical phi SHA mismatch")
        require(summary.get("canonical_phi_c_order_sha256") == criteria["w3_input"]["phi_c_order_sha256"],
                f"{arm_id} C-order phi SHA mismatch")
        require(summary.get("device_roundtrip_sha256") == criteria["w3_input"]["phi_fortran_sha256"],
                f"{arm_id} device round-trip SHA mismatch")
        require(summary.get("owner_array_type") == identity["type"], f"{arm_id} owner type mismatch")
        require(summary.get("runtime_identity", {}).get("cuda_device_memory_is_owner_parameter") is True,
                f"{arm_id} CUDA memory type identity mismatch")
        require(summary.get("runtime_identity", {}).get("cuda_device_memory_is_memory_module_binding") is True,
                f"{arm_id} CUDACore memory binding identity mismatch")
        runtime = summary.get("runtime_identity", {})
        for key in ("julia_version", "julia_threads", "cuda_jl_version",
                    "cuda_driver_api_version", "cuda_runtime_version", "waterlily_version",
                    "waterlily_backend", "gpu_name", "cuda_visible_devices"):
            require(runtime.get(key) == backend[key], f"{arm_id} runtime identity mismatch: {key}")
        require(runtime.get("owner_memory_module") == identity["memory_module"]["module"],
                f"{arm_id} owner memory module identity mismatch")
        require(runtime.get("owner_memory_package_uuid") == identity["memory_module"]["package_uuid"],
                f"{arm_id} owner memory package UUID mismatch")
        require(runtime.get("owner_memory_package_version") == backend["cudacore_version"],
                f"{arm_id} CUDACore version mismatch")
        require(runtime.get("owner_memory_parameter") == identity["memory_parameter"],
                f"{arm_id} owner memory parameter identity mismatch")
        require(runtime.get("gpu_uuid") == fingerprint["selected_gpu_uuid"],
                f"{arm_id} selected GPU UUID mismatch")
        require(summary.get("flow_dims") == criteria["fixture"]["flow_dims"], f"{arm_id} flow dimensions mismatch")
        require(item.get("solver_step_safety_limit_met") is True,
                f"{arm_id} exceeded the registered solver-step safety limit")
        require(summary.get("flow_origin_m") == criteria["fixture"]["flow_origin_m"], f"{arm_id} flow origin mismatch")
        require(summary.get("canonical_sdf_origin_m") == criteria["fixture"]["canonical_sdf_origin_m"],
                f"{arm_id} canonical SDF origin mismatch")
        require(math.isclose(summary.get("canonical_phi_margin_m", math.nan),
                             criteria["fixture"]["canonical_phi_margin_m"], rel_tol=0, abs_tol=1e-6),
                f"{arm_id} canonical SDF margin mismatch")
        point_path = folder / "arms" / arm_id / "candidate_probe_world_points.json"
        probe_points = read_json(point_path)
        expected_points = criteria["fixture"]["candidate_probe_points"]
        require(probe_points.get("names") == [point["name"] for point in expected_points],
                f"{arm_id} probe name identity mismatch")
        require(probe_points.get("world_m") == [point["world_m"] for point in expected_points],
                f"{arm_id} candidate world probe points changed")
        require(probe_points.get("flow_solver") == [point["flow_solver"] for point in expected_points],
                f"{arm_id} flow-origin / solver-coordinate probe mapping mismatch")
        require(probe_points.get("flow_origin_m") == criteria["fixture"]["flow_origin_m"],
                f"{arm_id} flow origin mapping changed")
        require(probe_points.get("canonical_sdf_origin_m") == criteria["fixture"]["canonical_sdf_origin_m"],
                f"{arm_id} canonical SDF origin changed")

    evidence = {
        "evidence_type": "diagnostic_only",
        "diagnostic_id": criteria["criteria_id"],
        "criteria_path": str(criteria_path), "criteria_sha256": criteria_sha,
        "criteria_dataset_id": criteria["criteria_dataset_id"],
        "criteria_dataset_manifest_sha256": sha256(criteria_manifest_path),
        "type_probe_prerequisite": {
            "exact_kernel_ref": type_result["exact_kernel_ref"],
            "criteria_sha256": type_result["criteria_sha256"],
            "result_sha256": type_result_sha,
            "runtime_type_identity": identity,
        },
        "w3_input_dataset_id": criteria["w3_input"]["dataset_id"],
        "w3_input_dataset_manifest_sha256": sha256(w3_manifest_path),
        "kernel_id": criteria["kernel_id"],
        "observed_kernel_id": actual_kernel_id,
        "kernel_version": kernel_version,
        "exact_kernel_ref": f"{actual_kernel_id}/{kernel_version}",
        "terminal_status": status_name,
        "kaggle_status_sha256": sha256(Path(status_path)),
        "kaggle_log_sha256": log_sha,
        "output_manifest_sha256": output_manifest_sha,
        "output_artifacts": manifest,
        "source_commit": criteria["source_commit"],
        "runner_sha256": fingerprint["runner_sha256"],
        "host_verifier_sha256": sha256(Path(host_verifier_path)),
        "host_verifier_sha256_registered": criteria["source_files"]["host_verifier"]["sha256"],
        "host_verifier_sha256_matches_registration": (
            sha256(Path(host_verifier_path)) == criteria["source_files"]["host_verifier"]["sha256"]
        ),
        "observed_backend_identity": {
            "gpu_inventory": gpu_rows,
            "selected_gpu_uuid": fingerprint["selected_gpu_uuid"],
            "cuda_visible_devices": fingerprint["cuda_visible_devices"],
            "julia_archive_sha256": fingerprint["julia_archive_sha256"],
            "cuda_smoke_sha256": fingerprint["cuda_smoke_sha256"],
            "owner_type_identity": identity,
        },
        "arms": arms,
        "causal_decision": decision,
        "host_verification_passed": status_name == "COMPLETE",
        "host_artifact_verification_passed": status_name == "COMPLETE",
        "qualification": False,
        "qualification_flags": registered_qualification_flags(criteria),
        "claim_scope": "owner-lifetime diagnostic only; no W3 primal, OpenFOAM equivalence, physical profile, gradient, reverse mode, topology, optimizer, or shape update qualification",
    }
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", required=True, type=Path)
    parser.add_argument("--criteria-dataset-dir", required=True, type=Path)
    parser.add_argument("--w3-dataset-dir", required=True, type=Path)
    parser.add_argument("--actual-kernel-id", required=True)
    parser.add_argument("--kernel-version", required=True, type=int)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--record-evidence", action="store_true")
    args = parser.parse_args()
    evidence = verify(args.download, criteria_path=args.criteria,
                      criteria_dataset_dir=args.criteria_dataset_dir,
                      w3_dataset_dir=args.w3_dataset_dir,
                      actual_kernel_id=args.actual_kernel_id,
                      kernel_version=args.kernel_version, status_path=args.status,
                      log_path=args.log, host_verifier_path=Path(__file__))
    if args.record_evidence:
        round_number = read_json(args.criteria).get("round", 1)
        output = args.criteria.parent / f"kaggle_w3_owner_full_horizon_result_2026_09_round{round_number}.json"
        sidecar = output.with_suffix(output.suffix + ".sha256")
        require(not output.exists() and not sidecar.exists(), "refusing to overwrite owner diagnostic evidence")
        payload = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output.write_text(payload)
        sidecar.write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
