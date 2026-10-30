#!/usr/bin/env python3
"""Independently verify one version-specific Kaggle W2b output download."""

import argparse
import csv
import json
import math
from pathlib import Path

from verify_kaggle_k0 import ROOT, require, sha256, verify_files


CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round5.json"
ROUND1_CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round1.json"
ROUND2_CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round2.json"
ROUND3_CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round3.json"
ROUND4_CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round4.json"
ROUND1_DIAGNOSTIC = ROOT / "docs/evidence/kaggle_w2b_version7_fetch_diagnostic_2026_09.json"
ROUND2_DIAGNOSTIC = ROOT / "docs/evidence/kaggle_w2b_version8_runtime_diagnostic_2026_09.json"
ROUND3_DIAGNOSTIC = ROOT / "docs/evidence/kaggle_w2b_version9_partial_failure_diagnostic_2026_09.json"
ROUND4_DIAGNOSTIC = ROOT / "docs/evidence/kaggle_w2b_version10_partial_failure_diagnostic_2026_09.json"
RUNNER = ROOT / "infra/kaggle/kernel_w2b/runner.py"
JOB = ROOT / "scripts/waterlily_w2b_grid_ladder_job.jl"
CASE_IDS = [f"{mode}_{n}" for n in (16, 24, 32) for mode in ("analytic", "gridsdf")]


def relative(a, b):
    require(math.isfinite(a) and math.isfinite(b) and a != 0 and b != 0,
            "response is zero or non-finite")
    return abs(a - b) / max(abs(a), abs(b))


def load_csv(folder, case_id, summary):
    path = folder / f"{case_id}.forces.csv"
    require(sha256(path) == summary["csv_sha256"], f"{case_id}: force CSV hash mismatch")
    with path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    require(bool(rows) and rows[0] == ["step", "t_ud", "drag", "lift", "side",
                                      "pressure_drag", "viscous_drag"],
            f"{case_id}: force CSV schema mismatch")
    require(len(rows) - 1 == summary["force_samples"], f"{case_id}: force sample count mismatch")
    try:
        values = [[float(value) for value in row] for row in rows[1:]]
    except ValueError as exc:
        raise ValueError(f"{case_id}: invalid force CSV value") from exc
    require(all(len(row) == 7 and all(math.isfinite(value) for value in row) for row in values),
            f"{case_id}: non-finite force CSV value")
    require(bool(values), f"{case_id}: force CSV is empty")
    require(all(a[0] < b[0] and a[1] < b[1] for a, b in zip(values, values[1:])),
            f"{case_id}: force CSV steps/times are not strictly increasing")
    return values


def verify_case_metrics(case_id, case, summary, rows):
    """Recompute reported window metrics from the retrieved force history."""
    window = [row for row in rows if 40.0 <= row[1] <= 60.0]
    first_half = [row for row in window if row[1] < 50.0]
    second_half = [row for row in window if row[1] >= 50.0]
    require(bool(first_half) and bool(second_half), f"{case_id}: force window is incomplete")

    def mean(column, samples):
        return math.fsum(row[column] for row in samples) / len(samples)

    def time_weighted(column):
        numerator = math.fsum(
            0.5 * (a[column] + b[column]) * (b[1] - a[1])
            for a, b in zip(window, window[1:])
        )
        duration = math.fsum(b[1] - a[1] for a, b in zip(window, window[1:]))
        require(duration > 0.0, f"{case_id}: force window has no time span")
        return numerator / duration

    def close(key, expected):
        require(math.isfinite(summary[key]) and math.isclose(
            summary[key], expected, rel_tol=1e-10, abs_tol=1e-12
        ), f"{case_id}: {key} does not match force CSV")

    for key, expected in (
        ("window_mean_drag", mean(2, window)),
        ("window_mean_lift", mean(3, window)),
        ("window_mean_side", mean(4, window)),
        ("time_weighted_mean_drag", time_weighted(2)),
        ("time_weighted_mean_lift", time_weighted(3)),
        ("time_weighted_mean_side", time_weighted(4)),
        ("first_half_mean_drag", mean(2, first_half)),
        ("second_half_mean_drag", mean(2, second_half)),
    ):
        close(key, expected)

    area = math.pi * case["solver_radius"] ** 2
    dynamic_pressure = 0.5 * case["u_inf"] ** 2
    close("cd", summary["window_mean_drag"] / (dynamic_pressure * area))
    close("time_weighted_cd", summary["time_weighted_mean_drag"] / (dynamic_pressure * area))
    last = rows[-1]
    require(summary["final_force"] == [last[2], last[3], last[4], last[5], last[6]],
            f"{case_id}: final force does not match force CSV")


def verify(download):
    criteria = json.loads(CRITERIA.read_text())
    require(sha256(CRITERIA) == CRITERIA.with_suffix(CRITERIA.suffix + ".sha256").read_text().strip(),
            "W2b criteria hash mismatch")
    previous = criteria["previous_round"]
    require(previous["criteria_path"] == ROUND4_CRITERIA.relative_to(ROOT).as_posix()
            and previous["criteria_sha256"] == sha256(ROUND4_CRITERIA),
            "W2b previous criteria binding mismatch")
    require(previous["diagnostic_path"] == ROUND4_DIAGNOSTIC.relative_to(ROOT).as_posix()
            and previous["diagnostic_sha256"] == sha256(ROUND4_DIAGNOSTIC)
            and sha256(ROUND4_DIAGNOSTIC)
            == ROUND4_DIAGNOSTIC.with_suffix(ROUND4_DIAGNOSTIC.suffix + ".sha256").read_text().strip(),
            "W2b round-4 diagnostic binding mismatch")
    round1 = json.loads(ROUND1_CRITERIA.read_text())
    round2 = json.loads(ROUND2_CRITERIA.read_text())
    round3 = json.loads(ROUND3_CRITERIA.read_text())
    round4 = json.loads(ROUND4_CRITERIA.read_text())
    round3_diagnostic = json.loads(ROUND3_DIAGNOSTIC.read_text())
    round4_diagnostic = json.loads(ROUND4_DIAGNOSTIC.read_text())
    require(round3_diagnostic["criteria"]["path"] == ROUND3_CRITERIA.relative_to(ROOT).as_posix()
            and round3_diagnostic["criteria"]["sha256"] == sha256(ROUND3_CRITERIA)
            and round3_diagnostic["kernel"]["version"] == 9
            and round3_diagnostic["observed"]["status"] == "KernelWorkerStatus.ERROR"
            and round3_diagnostic["observed"]["completed_case_ids"] == ["analytic_16"]
            and round3_diagnostic["observed"]["job_completion_marker_present"] is False,
            "W2b round-3 partial-failure diagnostic binding mismatch")
    require(round4_diagnostic["criteria"]["path"] == ROUND4_CRITERIA.relative_to(ROOT).as_posix()
            and round4_diagnostic["criteria"]["sha256"] == sha256(ROUND4_CRITERIA)
            and round4_diagnostic["kernel"]["version"] == 10
            and round4_diagnostic["observed"]["status"] == "KernelWorkerStatus.ERROR"
            and round4_diagnostic["observed"]["completed_case_ids"] == ["analytic_16"]
            and round4_diagnostic["observed"]["failed_case_id"] == "gridsdf_16"
            and round4_diagnostic["observed"]["job_completion_marker_present"] is False,
            "W2b round-4 partial-failure diagnostic binding mismatch")
    require(round4["previous_round"]["criteria_path"] == ROUND3_CRITERIA.relative_to(ROOT).as_posix()
            and round4["previous_round"]["criteria_sha256"] == sha256(ROUND3_CRITERIA)
            and round4["previous_round"]["diagnostic_path"] == ROUND3_DIAGNOSTIC.relative_to(ROOT).as_posix()
            and round4["previous_round"]["diagnostic_sha256"] == sha256(ROUND3_DIAGNOSTIC),
            "W2b round-3 to round-4 chain binding mismatch")
    require(round3["previous_round"]["criteria_path"] == ROUND2_CRITERIA.relative_to(ROOT).as_posix()
            and round3["previous_round"]["criteria_sha256"] == sha256(ROUND2_CRITERIA)
            and round3["previous_round"]["diagnostic_path"] == ROUND2_DIAGNOSTIC.relative_to(ROOT).as_posix()
            and round3["previous_round"]["diagnostic_sha256"] == sha256(ROUND2_DIAGNOSTIC),
            "W2b round-2 to round-3 chain binding mismatch")
    require(round2["previous_round"]["criteria_path"] == ROUND1_CRITERIA.relative_to(ROOT).as_posix()
            and round2["previous_round"]["criteria_sha256"] == sha256(ROUND1_CRITERIA)
            and round2["previous_round"]["diagnostic_path"] == ROUND1_DIAGNOSTIC.relative_to(ROOT).as_posix()
            and round2["previous_round"]["diagnostic_sha256"] == sha256(ROUND1_DIAGNOSTIC),
            "W2b round-1 chain binding mismatch")
    require(sha256(ROUND2_CRITERIA)
            == ROUND2_CRITERIA.with_suffix(ROUND2_CRITERIA.suffix + ".sha256").read_text().strip(),
            "W2b round-2 criteria sidecar mismatch")
    require(sha256(ROUND3_CRITERIA)
            == ROUND3_CRITERIA.with_suffix(ROUND3_CRITERIA.suffix + ".sha256").read_text().strip(),
            "W2b round-3 criteria sidecar mismatch")
    require(sha256(ROUND4_CRITERIA)
            == ROUND4_CRITERIA.with_suffix(ROUND4_CRITERIA.suffix + ".sha256").read_text().strip(),
            "W2b round-4 criteria sidecar mismatch")
    require(sha256(ROUND1_CRITERIA)
            == ROUND1_CRITERIA.with_suffix(ROUND1_CRITERIA.suffix + ".sha256").read_text().strip(),
            "W2b round-1 criteria sidecar mismatch")
    require(sha256(ROUND1_DIAGNOSTIC)
            == ROUND1_DIAGNOSTIC.with_suffix(ROUND1_DIAGNOSTIC.suffix + ".sha256").read_text().strip(),
            "W2b round-1 diagnostic sidecar mismatch")
    require(sha256(ROUND2_DIAGNOSTIC)
            == ROUND2_DIAGNOSTIC.with_suffix(ROUND2_DIAGNOSTIC.suffix + ".sha256").read_text().strip(),
            "W2b round-2 diagnostic sidecar mismatch")
    require(sha256(ROUND3_DIAGNOSTIC)
            == ROUND3_DIAGNOSTIC.with_suffix(ROUND3_DIAGNOSTIC.suffix + ".sha256").read_text().strip(),
            "W2b round-3 diagnostic sidecar mismatch")
    round3_inputs_without_job = {key: value for key, value in round3["inputs"].items() if key != "job"}
    round4_inputs_without_job = {key: value for key, value in round4["inputs"].items() if key != "job"}
    round5_inputs_without_job = {key: value for key, value in criteria["inputs"].items() if key != "job"}
    require(criteria["round"] == 5 and criteria["criteria_id"].endswith("round5")
            and criteria["thresholds"] == round1["thresholds"] == round2["thresholds"]
            == round3["thresholds"] == round4["thresholds"]
            and criteria["fixture"] == round1["fixture"] == round2["fixture"]
            == round3["fixture"] == round4["fixture"]
            and round3["inputs"] == round2["inputs"]
            and round4_inputs_without_job == round3_inputs_without_job
            and round5_inputs_without_job == round4_inputs_without_job
            and criteria["inputs"]["job"]["path"] == round4["inputs"]["job"]["path"]
            and criteria["source_commit"] != round4["source_commit"],
            "W2b round-5 contract, source update, or threshold drift")
    runtime_diagnostic = json.loads(ROUND2_DIAGNOSTIC.read_text())
    require(criteria["backend"] == round4["backend"] == round3["backend"]
            and criteria["backend"]["cuda_runtime_version"]
            == runtime_diagnostic["environment"]["cuda_runtime_version"]
            and criteria["backend"]["cuda_driver_api_version"]
            == runtime_diagnostic["environment"]["cuda_driver_api_version"],
            "W2b round-5 CUDA identity does not match registered backend")
    require(sha256(JOB) == criteria["inputs"]["job"]["sha256"], "W2b job source mismatch")
    for entry in criteria["inputs"].values():
        if isinstance(entry, dict) and "path" in entry:
            path = ROOT / entry["path"]
            require(sha256(path) == entry["sha256"], f"registered input hash mismatch: {path}")

    folder = download / "w2b"
    verified_files = verify_files(folder)
    outcome = json.loads((folder / "outcome.json").read_text())
    fingerprint = json.loads((folder / "fingerprint.json").read_text())
    require(outcome["criteria_sha256"] == sha256(CRITERIA), "W2b criteria binding mismatch")
    require(fingerprint["criteria_sha256"] == sha256(CRITERIA), "W2b fingerprint criteria mismatch")
    require(outcome["source_commit"] == criteria["source_commit"], "W2b source commit mismatch")
    require(fingerprint["source_commit"] == criteria["source_commit"], "W2b fingerprint source mismatch")
    require(fingerprint["runner_sha256"] == sha256(RUNNER), "W2b runner source mismatch")
    require(outcome["project_sha256"] == criteria["inputs"]["project"]["sha256"],
            "W2b Project mismatch")
    require(outcome["manifest_sha256"] == criteria["inputs"]["manifest"]["sha256"],
            "W2b Manifest mismatch")
    require(outcome["parameters_sha256"] == sha256(folder / "params.jl"),
            "W2b case-parameter SHA mismatch")

    gpu_rows = outcome["gpu_inventory"]
    require(fingerprint["gpu_csv"] == gpu_rows, "W2b GPU inventory binding mismatch")
    require(len(gpu_rows) == criteria["backend"]["gpu_count"]
            and all("Tesla T4" in row for row in gpu_rows), "W2b T4 inventory mismatch")
    uuids = [row.split(", ")[2] for row in gpu_rows]
    require(len(set(uuids)) == 2 and all(uuid.startswith("GPU-") for uuid in uuids),
            "W2b GPU UUID inventory invalid")
    require(outcome["selected_gpu_uuid"] == uuids[0], "W2b selected UUID mismatch")
    require(all(row.split(", ")[-1] == criteria["backend"]["driver_version"] for row in gpu_rows),
            "W2b driver cohort mismatch")

    smoke = (folder / "julia_smoke.log").read_text()
    for marker in ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
                   f"CUDA_DRIVER_VERSION {criteria['backend']['cuda_driver_api_version']}",
                   f"CUDA_RUNTIME_VERSION {criteria['backend']['cuda_runtime_version']}",
                   "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
                   "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4"):
        require(marker in smoke, f"W2b smoke missing marker: {marker}")

    cases = {item["case_id"]: item for item in criteria["fixture"]["cases"]}
    summaries = outcome["summaries"]
    require(set(summaries) == set(CASE_IDS), "W2b case summary inventory mismatch")
    require(set(outcome["force_csv_finite"]) == set(CASE_IDS), "W2b force CSV gate inventory mismatch")
    force_values = {}
    for case_id in CASE_IDS:
        summary = summaries[case_id]
        case = cases[case_id]
        require(json.loads((folder / f"{case_id}.summary.json").read_text()) == summary,
                f"{case_id}: summary duplication mismatch")
        force_values[case_id] = load_csv(folder, case_id, summary)
        verify_case_metrics(case_id, case, summary, force_values[case_id])
        require(summary["case_id"] == case_id and summary["mode"] == case["mode"],
                f"{case_id}: mode/case mismatch")
        for key in ("cells_per_diameter", "flow_dims", "solver_center", "solver_radius",
                    "reynolds", "viscosity", "world_origin_m", "world_per_solver"):
            expected = case[key]
            actual = summary[key]
            if isinstance(expected, float):
                require(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12),
                        f"{case_id}: {key} mismatch")
            else:
                require(actual == expected, f"{case_id}: {key} mismatch")
        area = math.pi * case["solver_radius"] ** 2
        expected_cd = summary["window_mean_drag"] / (0.5 * case["u_inf"] ** 2 * area)
        expected_tw_cd = summary["time_weighted_mean_drag"] / (0.5 * case["u_inf"] ** 2 * area)
        require(math.isclose(summary["cd"], expected_cd, rel_tol=1e-12, abs_tol=1e-12),
                f"{case_id}: window Cd calculation mismatch")
        require(math.isclose(summary["time_weighted_cd"], expected_tw_cd, rel_tol=1e-12, abs_tol=1e-12),
                f"{case_id}: time-weighted Cd calculation mismatch")
    require(outcome["force_csv_finite"] == {case_id: True for case_id in CASE_IDS},
            "W2b runner force CSV check disagrees with host verification")

    thresholds = criteria["thresholds"]
    summaries_complete = set(summaries) == set(CASE_IDS)
    all_rows_finite = all(outcome["force_csv_finite"].values()) and all(
        summary["finite_forces"] is True and summary["force_samples"] > 0
        for summary in summaries.values()
    )
    stationarity = all(
        abs(s["first_half_mean_drag"] - s["second_half_mean_drag"])
        / abs(s["window_mean_drag"]) <= thresholds["stationarity_relative_drift"]
        for s in summaries.values()
    )
    lift_bound = all(abs(s["window_mean_lift"]) / s["window_mean_drag"]
                     <= thresholds["relative_lift_to_drag"] for s in summaries.values())
    phi_hash = criteria["inputs"]["canonical_phi_sha256"]
    canonical_grid = all(
        (s["phi_sha256"] == phi_hash
         and s["device_roundtrip_sha256"] == phi_hash
         and s["phi_margin_gate_m"] == criteria["fixture"]["geometry"]["sampled_phi_lattice"]["margin_gate_m"]
         and s["phi_margin_m"] >= thresholds["phi_margin_min_m"]
         and abs(s["phi_margin_m"] - thresholds["phi_margin_expected_m"])
         <= thresholds["phi_margin_abs_tolerance_m"])
        if cases[case_id]["mode"] == "gridsdf" else
        s["phi_sha256"] == "" and s["device_roundtrip_sha256"] == ""
        and s["phi_margin_m"] is None and s["phi_margin_gate_m"] is None
        for case_id, s in summaries.items()
    )
    baseline_agreement = (
        relative(summaries["analytic_16"]["window_mean_drag"],
                 criteria["inputs"]["baseline_drag"]["analytic_16"])
        <= thresholds["t4_baseline_relative_drag"]
        and relative(summaries["gridsdf_16"]["window_mean_drag"],
                     criteria["inputs"]["baseline_drag"]["gridsdf_16"])
        <= thresholds["t4_baseline_relative_drag"]
    )
    geometry_agreement = all(
        relative(summaries[f"analytic_{n}"]["time_weighted_cd"],
                 summaries[f"gridsdf_{n}"]["time_weighted_cd"])
        <= thresholds["analytic_gridsdf_time_weighted_relative_cd"]
        for n in (16, 24, 32)
    )
    finest_grid = all(
        relative(summaries[f"{mode}_24"]["time_weighted_cd"],
                 summaries[f"{mode}_32"]["time_weighted_cd"])
        <= thresholds["finest_two_grid_time_weighted_relative_cd"]
        for mode in ("analytic", "gridsdf")
    )
    runtime_vram = all(
        0 < s["wall_seconds"] <= thresholds["case_wall_time_limit_s"]
        and s["ms_per_step"] > 0 and 0 < s["peak_vram_bytes"] < s["vram_total_bytes"]
        for s in summaries.values()
    )
    backend = all(
        s["gpu_name"] == "Tesla T4" and s["julia_version"] == criteria["backend"]["julia_version"]
        and s["cuda_jl_version"] == criteria["backend"]["cuda_jl_version"]
        and s["waterlily_version"] == criteria["backend"]["waterlily_version"]
        and s["julia_threads"] == criteria["fixture"]["domain"]["julia_threads"]
        for s in summaries.values()
    )
    gates = {
        "T0_prerequisites": (outcome["project_sha256"] == criteria["inputs"]["project"]["sha256"]
                             and outcome["manifest_sha256"] == criteria["inputs"]["manifest"]["sha256"]),
        "T1_completion": summaries_complete and all(s["steps"] > 0
                          and s["t_end_target"] == criteria["fixture"]["time"]["t_end_tu_d"]
                          and s["t_end_reached"] >= criteria["fixture"]["time"]["t_end_tu_d"]
                          for s in summaries.values()),
        "T2_finiteness": all(s["finite_u"] is True and s["finite_p"] is True
                             for s in summaries.values()),
        "T3_force_finite": all_rows_finite,
        "T4_drag_sign": all(math.isfinite(s["window_mean_drag"]) and s["window_mean_drag"] > 0
                             for s in summaries.values()),
        "T5_stationarity": stationarity,
        "T6_lift_bound": lift_bound,
        "T7_canonical_grid": canonical_grid,
        "T8_16_baseline_agreement": baseline_agreement,
        "T9_geometry_interpolation_agreement": geometry_agreement,
        "T10_finest_grid_response": finest_grid,
        "T11_runtime_vram": runtime_vram,
        "T12_backend_identity": (backend and len(gpu_rows) == 2
                                 and all("Tesla T4" in row for row in gpu_rows)
                                 and all(row.split(", ")[-1] == criteria["backend"]["driver_version"]
                                         for row in gpu_rows)
                                 and len(set(uuids)) == 2),
        "T13_artifact_retrieval": (folder / "DONE").is_file() and verified_files > 0,
    }
    require(outcome["gates"] == {key: value for key, value in gates.items() if key != "T13_artifact_retrieval"},
            "W2b runner/host gate result mismatch")
    require(all(gates.values()), f"W2b gate failed: {gates}")

    deltas = {
        mode: {
            "cd_16_24_relative": relative(summaries[f"{mode}_16"]["time_weighted_cd"],
                                           summaries[f"{mode}_24"]["time_weighted_cd"]),
            "cd_24_32_relative": relative(summaries[f"{mode}_24"]["time_weighted_cd"],
                                           summaries[f"{mode}_32"]["time_weighted_cd"]),
        }
        for mode in ("analytic", "gridsdf")
    }
    return {"verified_files": verified_files, "gates": gates,
            "grid_deltas": deltas, "selected_gpu_uuid": outcome["selected_gpu_uuid"],
            "case_time_weighted_cd": {key: value["time_weighted_cd"] for key, value in summaries.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific Kaggle output directory")
    print(json.dumps(verify(parser.parse_args().download), indent=2, sort_keys=True))
