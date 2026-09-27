#!/usr/bin/env python3
"""Independently verify a version-specific Kaggle W2-T4b download."""

import argparse
import csv
import json
import math
from pathlib import Path

from verify_kaggle_k0 import ROOT, require, sha256, verify_files


CRITERIA = ROOT / "docs/evidence/kaggle_w2t4b_criteria_2026_09.json"
RUNNER = ROOT / "infra/kaggle/kernel/runner.py"
JOB = ROOT / "scripts/waterlily_w2t4_job.jl"
DEVICE_GRID = ROOT / "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl"


def verify(download):
    criteria = json.loads(CRITERIA.read_text())
    require(sha256(CRITERIA) == CRITERIA.with_suffix(".json.sha256").read_text().strip(),
            "W2-T4b criteria hash mismatch")
    for entry in criteria["inputs"].values():
        if isinstance(entry, dict) and "path" in entry:
            path = ROOT / entry["path"]
            require(sha256(path) == entry["sha256"], f"registered input hash mismatch: {path.name}")
    require(sha256(JOB) == criteria["inputs"]["w2t4_job_sha256"],
            "W2-T4b job source mismatch")
    require(sha256(DEVICE_GRID) == criteria["inputs"]["device_grid_sdf_sha256"],
            "W2-T4b DeviceGridSDF source mismatch")

    folder = download / "w2t4b"
    verified_files = verify_files(folder)
    outcome = json.loads((folder / "outcome.json").read_text())
    summary = json.loads((folder / "gridsdf.summary.json").read_text())
    fingerprint = json.loads((folder / "fingerprint.json").read_text())
    require(outcome["fixture_summary"] == summary, "W2-T4b summary duplication mismatch")
    require(outcome["criteria_sha256"] == sha256(CRITERIA), "W2-T4b criteria binding mismatch")
    require(outcome["source_commit"] == criteria["source_commit"], "W2-T4b source commit mismatch")
    require(fingerprint["source_commit"] == criteria["source_commit"],
            "W2-T4b runner source commit mismatch")
    require(fingerprint["runner_sha256"] == sha256(RUNNER), "W2-T4b runner source mismatch")
    require(outcome["project_sha256"] == criteria["inputs"]["project_sha256"],
            "W2-T4b Project mismatch")
    require(outcome["manifest_sha256"] == criteria["inputs"]["manifest_sha256"],
            "W2-T4b Manifest mismatch")

    rows = outcome["gpu_inventory"]
    require(fingerprint["gpu_csv"] == rows, "W2-T4b GPU inventory binding mismatch")
    require(len(rows) == criteria["backend"]["gpu_count"]
            and all("Tesla T4" in row for row in rows), "W2-T4b T4 inventory mismatch")
    uuids = [row.split(", ")[2] for row in rows]
    selected_uuid = rows[0].split(", ")[2]
    require(len(set(uuids)) == 2 and all(uuid.startswith("GPU-") for uuid in uuids),
            "W2-T4b GPU UUID inventory invalid")
    require(outcome["selected_gpu_uuid"] == selected_uuid,
            "W2-T4b selected GPU UUID does not match the first inventory device")
    require(all(row.split(", ")[-1] == criteria["backend"]["driver_version"] for row in rows),
            "W2-T4b driver cohort mismatch")

    smoke = (folder / "julia_smoke.log").read_text()
    for marker in ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
                   "CUDA_RUNTIME_VERSION 13.3.0", "JULIA_VERSION 1.12.6",
                   "CUDA_JL_VERSION 6.3.1", "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4"):
        require(marker in smoke, f"W2-T4b CUDA smoke missing marker: {marker}")

    csv_path = folder / "gridsdf.forces.csv"
    require(sha256(csv_path) == summary["csv_sha256"], "W2-T4b force CSV hash mismatch")
    with csv_path.open(newline="") as handle:
        rows_csv = list(csv.reader(handle))
    require(bool(rows_csv) and rows_csv[0] == ["step", "t_ud", "drag", "lift", "side",
                                               "pressure_drag", "viscous_drag"],
            "W2-T4b force CSV schema mismatch")
    require(len(rows_csv) - 1 == summary["force_samples"], "W2-T4b force sample count mismatch")
    force_values = [[float(value) for value in row] for row in rows_csv[1:]]
    require(all(len(row) == 7 and all(math.isfinite(value) for value in row)
                for row in force_values), "W2-T4b force CSV contains non-finite values")

    ref = criteria["inputs"]
    threshold = criteria["thresholds"]
    drag = summary["window_mean_drag"]
    gates = {
        "T0_prerequisites": outcome["project_sha256"] == ref["project_sha256"]
                            and outcome["manifest_sha256"] == ref["manifest_sha256"]
                            and all(sha256(ROOT / entry["path"]) == entry["sha256"]
                                    for entry in ref.values()
                                    if isinstance(entry, dict) and "path" in entry),
        "T1_completion": summary["mode"] == "gridsdf" and summary["steps"] > 0
                         and summary["t_end_reached"] >= criteria["fixture"]["time"]["t_end_tu_d"],
        "T2_finiteness": summary["finite_u"] is True and summary["finite_p"] is True,
        "T3_force_finite": summary["finite_forces"] is True and summary["force_samples"] > 0
                           and all(len(row) == 7 and all(math.isfinite(value) for value in row)
                                   for row in force_values),
        "T4_drag_sign": math.isfinite(drag) and drag > 0,
        "T5_stationarity": math.isfinite(drag) and drag != 0
                           and abs(summary["first_half_mean_drag"]
                                   - summary["second_half_mean_drag"]) / abs(drag)
                           <= threshold["stationarity_relative_drift"],
        "T6_cpu_kaggle_agreement": math.isfinite(drag)
                                   and abs(drag - ref["cpu_sampled_window_mean_drag"])
                                   / abs(ref["cpu_sampled_window_mean_drag"])
                                   <= threshold["cpu_kaggle_sampled_relative_drag"],
        "T7_sampled_analytic_agreement": abs(summary["cd"] - ref["t4_analytic_cd"])
                                         / abs(ref["t4_analytic_cd"])
                                         <= threshold["sampled_analytic_relative_cd"],
        "T8_lift_bound": math.isfinite(drag) and drag > 0
                         and abs(summary["window_mean_lift"]) / drag
                         <= threshold["relative_lift_to_drag"],
        "T9_canonical_grid": summary["phi_sha256"] == ref["canonical_phi_sha256"]
                             and summary["device_roundtrip_sha256"] == ref["canonical_phi_sha256"]
                             and summary["phi_margin_m"] >= threshold["phi_margin_min_m"]
                             and abs(summary["phi_margin_m"] - threshold["phi_margin_expected_m"])
                             <= threshold["phi_margin_abs_tolerance_m"],
        "T10_runtime_vram": summary["wall_seconds"] > 0 and summary["ms_per_step"] > 0
                            and 0 < summary["peak_vram_bytes"] < summary["vram_total_bytes"],
        "T11_backend_identity": criteria["backend"]["accelerator"] == "NvidiaTeslaT4"
                                and summary["gpu_name"] == "Tesla T4"
                                and summary["julia_version"] == criteria["backend"]["julia_version"]
                                and summary["cuda_jl_version"] == criteria["backend"]["cuda_jl_version"]
                                and summary["waterlily_version"] == criteria["backend"]["waterlily_version"]
                                and all("Tesla T4" in row and row.split(", ")[-1]
                                        == criteria["backend"]["driver_version"] for row in rows)
                                and selected_uuid.startswith("GPU-")
                                and "GPU_COMPUTE_CAPABILITY 7.5.0" in smoke
                                and "CUDA_RUNTIME_VERSION 13.3.0" in smoke,
        "T12_artifact_retrieval": verified_files > 0,
    }
    remote_gates = {key: value for key, value in gates.items() if key != "T12_artifact_retrieval"}
    require(outcome["gates"] == remote_gates and all(gates.values()), "W2-T4b gate failure")
    return {
        "verified_files": verified_files,
        "steps": summary["steps"],
        "window_mean_drag": drag,
        "cd": summary["cd"],
        "cpu_sampled_relative_drag_difference": abs(drag - ref["cpu_sampled_window_mean_drag"])
                                                / abs(ref["cpu_sampled_window_mean_drag"]),
        "sampled_analytic_relative_cd_difference": abs(summary["cd"] - ref["t4_analytic_cd"])
                                                  / abs(ref["t4_analytic_cd"]),
        "selected_gpu_uuid": selected_uuid,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific kaggle kernels output directory")
    print(json.dumps(verify(parser.parse_args().download), indent=2, sort_keys=True))
