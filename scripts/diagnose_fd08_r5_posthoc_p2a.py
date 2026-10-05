#!/usr/bin/env python3
"""Describe immutable FD-08 R5 calibration data without changing its gates."""

from __future__ import annotations

import argparse
import io
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np

EXPECTED_CRITERIA_SHA256 = "928292ca1911875a564e74ffbe64b7d3d4790d9e49b81272ed39dedd9ebdce6c"
EXPECTED_ANALYSIS_SHA256 = "dc769d6f2b5a2d6dfa45c6a5aeddfde726dd75f6e44ac564b128effecce3fb8b"
EXPECTED_MANIFEST_SHA256 = "1b04c3c2243459d2889dc16aa0f3c02c2ff6a5555a64406bb8177b9ee0b8600e"
EXPECTED_SOURCE_COMMIT = "95bd9cbf8e67f0c718e346f7edca3f343ed1091f"
INTEGRATION_COMMIT = "8e736c1f01a617fe5a29eb7945ea1f1042bf45d1"
EVIDENCE_RELATIVE = Path("docs/evidence/fd08_candidate_c_calibration_2026_10_04_r5")
OUTPUT_RELATIVE = EVIDENCE_RELATIVE / "post_hoc_p2a"
SHAPE = (121, 65, 49)
DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
RESPONSES = ("drag", "downforce")
EPSILON_M = (5e-5, 1.5e-4, 5e-4, 1.5e-3, 5e-3, 1.5e-2, 5e-2)
REGRESSION_INTERVALS_MM = ((0.5, 5.0), (0.5, 15.0), (1.5, 15.0))
SIGNAL_THRESHOLDS_MICRO_N = (10.0, 30.0, 50.0)
PRIMARY_SIGNAL_THRESHOLD_MICRO_N = 50.0
NOISE_SCENARIOS_MICRO_N = (2.0, 3.0, 4.0)
PLATEAU_WINDOWS = ((0, 5), (1, 6), (2, 7))
PLATEAU_FIGURE = "plateau_windows.png"
FUNCTIONAL_FIGURES = tuple(f"sdf_functionals_{name}.png" for name in ("D0", "D1", "D2"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"refusing to replace a different historical artifact: {path}")
        return
    path.write_bytes(data)


def decompose_pair(
    response_plus_n: float,
    response_minus_n: float,
    baseline_mean_n: float,
    epsilon_mm: float,
) -> dict[str, float]:
    """Apply the fixed R5 pair decomposition; q uses epsilon converted to metres."""
    plus = float(response_plus_n)
    minus = float(response_minus_n)
    baseline = float(baseline_mean_n)
    epsilon = float(epsilon_mm)
    if not all(math.isfinite(value) for value in (plus, minus, baseline, epsilon)) or epsilon <= 0.0:
        raise ValueError("pair responses and positive epsilon must be finite")
    signal = (plus - minus) / 2.0
    even_residual = (plus + minus) / 2.0 - baseline
    return {"s_n": signal, "q_n_per_m": signal / (epsilon * 1e-3), "e_n": even_residual}


def fit_q_vs_epsilon_squared(epsilon_mm: Sequence[float], q_n_per_m: Sequence[float]) -> dict[str, Any]:
    """Fit q = g + c epsilon_mm^2 with unweighted least squares."""
    if len(epsilon_mm) != len(q_n_per_m) or len(q_n_per_m) < 2:
        raise ValueError("at least two aligned epsilon/q points are required")
    x = np.asarray(epsilon_mm, dtype=np.float64) ** 2
    y = np.asarray(q_n_per_m, dtype=np.float64)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("fit inputs must be finite")
    design = np.column_stack((np.ones_like(x), x))
    g, c = np.linalg.lstsq(design, y, rcond=None)[0]
    residuals = y - (g + c * x)
    rms = math.sqrt(math.fsum(float(r * r) for r in residuals) / len(residuals))
    g_float = float(g)
    return {
        "point_count": len(y),
        "g_n_per_m": g_float,
        "c_n_per_m_per_mm_squared": float(c),
        "residual_rms_n_per_m": rms,
        "residual_rms_percent_of_abs_g": 100.0 * rms / abs(g_float) if g_float else None,
        "residuals_n_per_m": [float(value) for value in residuals],
        "fit_status": "calculable",
    }


def plateau_window_metrics(rows: Sequence[Mapping[str, float]], floor_n: float) -> dict[str, Any]:
    """Match fd08_calibration._plateau_metrics' median/floor normalization."""
    if len(rows) != 5 or not math.isfinite(float(floor_n)) or floor_n <= 0.0:
        raise ValueError("plateau metric requires five rows and a positive finite response floor")
    slopes = [float(row["q_n_per_m"]) for row in rows]
    epsilons_m = [float(row["epsilon_m"]) for row in rows]
    if any(not math.isfinite(value) for value in slopes + epsilons_m) or min(epsilons_m) <= 0.0:
        raise ValueError("plateau inputs must be finite and epsilon positive")
    q_ref = float(median(slopes))
    noise_equivalent = float(floor_n) / min(epsilons_m)
    normalizer = max(abs(q_ref), noise_equivalent)
    deviations = [abs(value - q_ref) / normalizer for value in slopes]
    return {
        "q_ref_median_n_per_m": q_ref,
        "noise_equivalent_n_per_m": noise_equivalent,
        "normalizer_n_per_m": normalizer,
        "relative_deviations": deviations,
        "maximum_relative_deviation": max(deviations),
        "maximum_relative_deviation_percent": 100.0 * max(deviations),
    }


def loo_diagnostic(rows: Sequence[Mapping[str, float]], threshold_micro_n: float) -> dict[str, Any]:
    """Return numeric leave-one-out errors and a fail-closed three-valued status."""
    threshold_n = float(threshold_micro_n) * 1e-6
    selected = [row for row in rows if abs(float(row["s_n"])) >= threshold_n]
    errors: list[dict[str, Any]] = []
    if len(selected) >= 4:
        for index, held in enumerate(selected):
            train = selected[:index] + selected[index + 1 :]
            fit = fit_q_vs_epsilon_squared(
                [float(row["epsilon_mm"]) for row in train],
                [float(row["q_n_per_m"]) for row in train],
            )
            predicted = fit["g_n_per_m"] + fit["c_n_per_m_per_mm_squared"] * float(held["epsilon_mm"]) ** 2
            observed = float(held["q_n_per_m"])
            absolute = abs(observed - predicted)
            errors.append({
                "held_out_epsilon_mm": float(held["epsilon_mm"]),
                "q_observed_n_per_m": observed,
                "q_predicted_n_per_m": predicted,
                "absolute_error_n_per_m": absolute,
                "absolute_error_micro_n_per_m": absolute * 1e6,
                "relative_error_percent": (100.0 * absolute / abs(observed)) if abs(observed) >= 1e-9 else None,
                "relative_error_status": "calculable" if abs(observed) >= 1e-9 else "undeterminable",
            })
    enough_points = len(selected) >= 4
    return {
        "signal_threshold_micro_n": float(threshold_micro_n),
        "selected_point_count": len(selected),
        "selected_epsilon_mm": [float(row["epsilon_mm"]) for row in selected],
        "calculation_status": "calculable" if enough_points else "undeterminable",
        "status": "undeterminable",
        "status_reason": (
            "no registered pass/fail boundary is specified for numeric LOO errors"
            if enough_points else "fewer than four points satisfy the specified |S| threshold"
        ),
        "maximum_absolute_error_micro_n_per_m": max(
            (row["absolute_error_micro_n_per_m"] for row in errors), default=None,
        ),
        "maximum_relative_error_percent_among_defined": max(
            (row["relative_error_percent"] for row in errors if row["relative_error_percent"] is not None),
            default=None,
        ),
        "point_errors": errors,
    }


def sdf_soft_volume(phi: np.ndarray, cell_width_m: float) -> float:
    """Compute the specified SDF soft-volume proxy with an accurate sum."""
    h = float(cell_width_m)
    if h <= 0.0 or not math.isfinite(h):
        raise ValueError("cell width must be positive and finite")
    values = np.clip(0.5 - np.asarray(phi, dtype=np.float64) / h, 0.0, 1.0)
    return math.fsum(float(value) for value in values.ravel(order="C")) * h**3


def odd_even_parts(plus: float, minus: float, baseline: float, epsilon_m: float) -> dict[str, float]:
    if epsilon_m <= 0.0 or not all(math.isfinite(float(x)) for x in (plus, minus, baseline, epsilon_m)):
        raise ValueError("functional values and positive epsilon must be finite")
    odd = (float(plus) - float(minus)) / 2.0
    return {
        "odd_part_m3": odd,
        "odd_part_over_epsilon_m2": odd / float(epsilon_m),
        "even_part_m3": (float(plus) + float(minus)) / 2.0 - float(baseline),
    }


def merge_epsilon_grids(r5_mm: Sequence[float], logspace_mm: Sequence[float]) -> tuple[list[float], list[float]]:
    """Deduplicate the diagnostic grid while retaining exact registered R5 values."""
    keyed = {format(float(value), ".15g"): float(value) for value in logspace_mm}
    log_keys = set(keyed)
    for value in r5_mm:
        keyed[format(float(value), ".15g")] = float(value)
    overlap = sorted(float(value) for value in r5_mm if format(float(value), ".15g") in log_keys)
    return sorted(keyed.values()), overlap


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _verify_inputs(
    repo: Path, dataset_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    sys.path.insert(0, str(repo / "src"))
    from cfd_sdf.fd08_calibration import verify_registered_dataset

    evidence = repo / EVIDENCE_RELATIVE
    criteria_path = evidence / "xfidc_criteria.json"
    analysis_path = evidence / "calibration_analysis.json"
    runner_root = evidence / "result" / "fd08_calibration"
    runner_result_path = runner_root / "result.json"
    criteria_sha = sha256(criteria_path)
    analysis_sha = sha256(analysis_path)
    if criteria_sha != EXPECTED_CRITERIA_SHA256 or analysis_sha != EXPECTED_ANALYSIS_SHA256:
        raise ValueError("immutable R5 criteria or analysis SHA-256 mismatch")
    criteria = _load_json(criteria_path)
    analysis = _load_json(analysis_path)
    if (criteria.get("source_commit") != EXPECTED_SOURCE_COMMIT
            or len(criteria.get("state_order", [])) != 47
            or len(criteria.get("dataset_files", {})) != 89):
        raise ValueError("R5 criteria does not match the fixed source and inventory")
    if (analysis.get("calibration_criteria_sha256") != criteria_sha
            or analysis.get("source_commit") != EXPECTED_SOURCE_COMMIT
            or analysis.get("calibration_verdict") != "FAIL"
            or analysis.get("formal_phase_allowed") is not False
            or analysis.get("formal_qualification") is not False
            or any(value is not False for value in analysis.get("qualification_flags", {}).values())):
        raise ValueError("R5 analysis no longer records the fixed FAIL / false qualification state")
    dataset_audit = verify_registered_dataset(criteria, criteria_sha, dataset_root)
    if (dataset_audit.get("verified_file_count") != 89
            or dataset_audit.get("inventory_sha256") != analysis["registered_dataset_audit"]["inventory_sha256"]):
        raise ValueError("downloaded R5 dataset differs from its registered inventory")
    manifest_path = runner_root / "sha256.json"
    if sha256(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("R5 force output manifest SHA-256 mismatch")
    runner_manifest = _load_json(manifest_path)
    runner_inventory_sha = hashlib.sha256(
        "\n".join(f"{name}  {runner_manifest[name]}" for name in sorted(runner_manifest)).encode()
    ).hexdigest()
    if runner_inventory_sha != analysis["runner_output_manifest"]["inventory_sha256"]:
        raise ValueError("R5 manifest entry inventory differs from the existing host analysis")
    expected_force_paths = {
        f"states/{row['run_id']}/flow_24.forces.csv" for row in criteria["state_order"]
    }
    if len(expected_force_paths) != 47 or not expected_force_paths.issubset(runner_manifest):
        raise ValueError("R5 manifest does not bind all 47 registered force histories")
    actual_manifested_files = {
        path.relative_to(runner_root).as_posix()
        for path in runner_root.rglob("*")
        if path.is_file() and path.name not in {"sha256.json", "DONE"}
    }
    missing_manifest_files = sorted(set(runner_manifest) - actual_manifested_files)
    extra_runner_files = sorted(actual_manifested_files - set(runner_manifest))
    if extra_runner_files:
        raise ValueError(f"R5 runner output has unmanifested files: {extra_runner_files}")
    done_path = runner_root / "DONE"
    done = _load_json(done_path)
    expected_done_sha = analysis["runner_output_manifest"].get("terminal_marker_sha256")
    if (done.get("status") != "FINISHED_STATE_LOOP"
            or (expected_done_sha and sha256(done_path) != expected_done_sha)):
        raise ValueError("R5 runner DONE marker differs from the existing host analysis")
    if runner_result_path.relative_to(runner_root).as_posix() not in runner_manifest:
        raise ValueError("R5 runner result is not bound by its manifest")
    state_ids = {row["run_id"] for row in criteria["state_order"]}
    if len(state_ids) != 47 or state_ids != set(analysis["calibration_run_ids"]):
        raise ValueError("criteria and analysis do not identify the same 47 calibration states")
    if tuple(float(value) for value in criteria["calibration_epsilon_ladder_m"]) != EPSILON_M:
        raise ValueError("R5 epsilon ladder differs from this descriptive diagnostic contract")
    return criteria, analysis, {
        "criteria_sha256": criteria_sha,
        "analysis_sha256": analysis_sha,
        "criteria_path": criteria_path.relative_to(repo).as_posix(),
        "analysis_path": analysis_path.relative_to(repo).as_posix(),
        "source_commit": EXPECTED_SOURCE_COMMIT,
        "dataset_root": dataset_root.as_posix(),
        "dataset_verified_file_count": dataset_audit["verified_file_count"],
        "dataset_inventory_sha256": dataset_audit["inventory_sha256"],
        "runner_manifest_sha256": sha256(manifest_path),
        "runner_inventory_sha256": runner_inventory_sha,
        "runner_manifest_entry_count": len(runner_manifest),
        "runner_manifest_missing_files": missing_manifest_files,
        "runner_manifest_extra_files": extra_runner_files,
        "runner_full_inventory_verified": not missing_manifest_files,
        "runner_force_history_count_bound_by_manifest": len(expected_force_paths),
        "runner_root": runner_root.relative_to(repo).as_posix(),
    }, runner_manifest


def _read_force_means(
    repo: Path, criteria: Mapping[str, Any], analysis: Mapping[str, Any],
    runner_root_relative: str, runner_manifest: Mapping[str, str],
) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    sys.path.insert(0, str(repo / "src"))
    from cfd_sdf.fd08_calibration import recompute_force_history

    runner_root = repo / runner_root_relative
    force_by_run: dict[str, dict[str, float]] = {}
    force_hash_by_run: dict[str, str] = {}
    for state in criteria["state_order"]:
        run_id = state["run_id"]
        state_dir = runner_root / "states" / run_id
        csv_path = state_dir / "flow_24.forces.csv"
        state_result_path = state_dir / "state_result.json"
        if not state_result_path.exists():
            raise ValueError(f"missing terminal state record: {run_id}")
        state_result = _load_json(state_result_path)
        raw = recompute_force_history(
            csv_path,
            force_scale_n_per_solver_force=float(analysis["force_scale_n_per_solver_force"]),
            window_t_u_l=(80.0, 120.0),
        )
        prior = analysis["raw_force_history_inventory"].get(run_id)
        relative_force_path = f"states/{run_id}/flow_24.forces.csv"
        relative_state_path = f"states/{run_id}/state_result.json"
        if (not prior or raw["sha256"] != prior["sha256"]
                or raw["sha256"] != runner_manifest.get(relative_force_path)
                or sha256(state_result_path) != runner_manifest.get(relative_state_path)
                or raw["sha256"] != state_result.get("force_csv_sha256")
                or state_result.get("status") != "COMPLETED"):
            raise ValueError(f"force history or terminal record mismatch: {run_id}")
        if state_result.get("phi_fortran_sha256") not in (None, state.get("phi_fortran_sha256")):
            raise ValueError(f"registered perturbed phi hash mismatch: {run_id}")
        for response in RESPONSES:
            prior_n = float(prior["host_recomputed_force_n"][response])
            if not math.isclose(raw["force_n"][response], prior_n, rel_tol=2e-14, abs_tol=1e-15):
                raise ValueError(f"host recomputed force differs from existing analysis: {run_id}/{response}")
        force_by_run[run_id] = dict(raw["force_n"])
        force_hash_by_run[run_id] = raw["sha256"]
    return force_by_run, force_hash_by_run


def _build_force_tables(
    criteria: Mapping[str, Any], analysis: Mapping[str, Any],
    force: Mapping[str, Mapping[str, float]], force_hashes: Mapping[str, str],
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, float]]:
    baseline_ids = [row["run_id"] for row in criteria["state_order"] if row["role"] == "baseline"]
    if len(baseline_ids) != 5 or set(baseline_ids) != set(analysis["baseline_repeat_ids"]):
        raise ValueError("R0 requires the five registered identical-input repeats")
    r0 = {
        response: math.fsum(float(force[run_id][response]) for run_id in baseline_ids) / 5.0
        for response in RESPONSES
    }
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for direction in DIRECTIONS:
        output[direction] = {}
        for response in RESPONSES:
            input_rows = analysis["direction_response_pairs"][direction][response]
            rows: list[dict[str, Any]] = []
            for item in input_rows:
                epsilon_m = float(item["epsilon_m"])
                pair = decompose_pair(
                    force[item["plus_run_id"]][response], force[item["minus_run_id"]][response],
                    r0[response], epsilon_m * 1000.0,
                )
                row = {
                    "epsilon_m": epsilon_m,
                    "epsilon_mm": epsilon_m * 1000.0,
                    "plus_run_id": item["plus_run_id"],
                    "minus_run_id": item["minus_run_id"],
                    "plus_force_csv_sha256": force_hashes[item["plus_run_id"]],
                    "minus_force_csv_sha256": force_hashes[item["minus_run_id"]],
                    "r_plus_n": float(force[item["plus_run_id"]][response]),
                    "r_plus_micro_n": float(force[item["plus_run_id"]][response]) * 1e6,
                    "r_minus_n": float(force[item["minus_run_id"]][response]),
                    "r_minus_micro_n": float(force[item["minus_run_id"]][response]) * 1e6,
                    "r0_n": r0[response],
                    "r0_micro_n": r0[response] * 1e6,
                    "s_n": pair["s_n"],
                    "s_micro_n": pair["s_n"] * 1e6,
                    "q_n_per_m": pair["q_n_per_m"],
                    "q_micro_n_per_m": pair["q_n_per_m"] * 1e6,
                    "e_n": pair["e_n"],
                    "e_micro_n": pair["e_n"] * 1e6,
                    "registered_resolved": bool(item["resolved"]),
                    "registered_centered_response_n": float(item["centered_response_n"]),
                }
                rows.append(row)
            rows.sort(key=lambda row: row["epsilon_m"])
            output[direction][response] = rows
    return output, r0


def _regression_tables(series: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"intervals_mm": [list(pair) for pair in REGRESSION_INTERVALS_MM], "series": {}}
    for direction in DIRECTIONS:
        result["series"][direction] = {}
        for response in RESPONSES:
            rows = series[direction][response]
            fits: dict[str, Any] = {"all_points": [], "signal_filtered": {}}
            interval_rows: list[dict[str, Any]] = []
            for lower, upper in REGRESSION_INTERVALS_MM:
                selected = [row for row in rows if lower <= row["epsilon_mm"] <= upper]
                base = {"epsilon_range_mm": [lower, upper], "epsilon_mm": [row["epsilon_mm"] for row in selected]}
                fit = fit_q_vs_epsilon_squared(
                    [row["epsilon_mm"] for row in selected], [row["q_n_per_m"] for row in selected],
                )
                interval_rows.append({**base, **fit})
            fits["all_points"] = interval_rows
            for threshold in SIGNAL_THRESHOLDS_MICRO_N:
                threshold_key = f"{threshold:g}_micro_n"
                threshold_intervals = []
                for lower, upper in REGRESSION_INTERVALS_MM:
                    selected = [row for row in rows if lower <= row["epsilon_mm"] <= upper
                                and abs(row["s_micro_n"]) >= threshold]
                    record: dict[str, Any] = {
                        "epsilon_range_mm": [lower, upper],
                        "signal_threshold_micro_n": threshold,
                        "epsilon_mm": [row["epsilon_mm"] for row in selected],
                    }
                    if len(selected) >= 2:
                        record.update(fit_q_vs_epsilon_squared(
                            [row["epsilon_mm"] for row in selected],
                            [row["q_n_per_m"] for row in selected],
                        ))
                    else:
                        record.update({
                            "point_count": len(selected), "fit_status": "undeterminable",
                            "reason": "fewer than two signal-selected points",
                            "g_n_per_m": None, "c_n_per_m_per_mm_squared": None,
                            "residual_rms_n_per_m": None, "residual_rms_percent_of_abs_g": None,
                            "residuals_n_per_m": [],
                        })
                    threshold_intervals.append(record)
                fits["signal_filtered"][threshold_key] = threshold_intervals
            spread_groups: dict[str, Any] = {}
            candidates = {"all_points": interval_rows}
            candidates.update({f"signal_filtered_{key}": value for key, value in fits["signal_filtered"].items()})
            for name, values in candidates.items():
                g_values = [row["g_n_per_m"] for row in values]
                valid = all(value is not None for value in g_values)
                if valid:
                    center = float(median(g_values))
                    spread = (max(g_values) - min(g_values)) / abs(center) if center else None
                    spread_groups[name] = {
                        "status": "calculable" if spread is not None else "undeterminable",
                        "g_values_n_per_m": g_values,
                        "median_g_n_per_m": center,
                        "relative_spread": spread,
                    }
                else:
                    spread_groups[name] = {
                        "status": "undeterminable", "g_values_n_per_m": g_values,
                        "median_g_n_per_m": None, "relative_spread": None,
                    }
            result["series"][direction][response] = {
                "fits": fits,
                "g_spread_across_three_intervals": spread_groups,
            }
    return result


def _plateau_tables(series: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "normalization": "max(abs(median(q in 5-point window)), response_floor_n / smallest_epsilon_m)",
        "windows": [], "series": {},
    }
    for start, stop in PLATEAU_WINDOWS:
        result["windows"].append({
            "start_index_zero_based": start,
            "epsilon_mm": [EPSILON_M[index] * 1000.0 for index in range(start, stop)],
        })
    for direction in DIRECTIONS:
        result["series"][direction] = {}
        for response in RESPONSES:
            floor_n = float(analysis["baseline_resolution_floors"][response]["response_floor_n"])
            rows = series[direction][response]
            table = []
            for (start, stop), window in zip(PLATEAU_WINDOWS, result["windows"]):
                selected = rows[start:stop]
                metrics = plateau_window_metrics(selected, floor_n)
                table.append({
                    "window_epsilon_mm": window["epsilon_mm"],
                    "response_floor_n": floor_n,
                    "epsilon_min_m": min(row["epsilon_m"] for row in selected),
                    **metrics,
                })
            result["series"][direction][response] = table
    return result


def _loo_tables(series: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status_values": ["pass", "fail", "undeterminable"],
        "classification_rule": "status is undeterminable because no pass/fail error boundary is specified; numeric errors are descriptive only",
        "intervals_mm": [list(pair) for pair in REGRESSION_INTERVALS_MM],
        "series": {},
    }
    for direction in DIRECTIONS:
        result["series"][direction] = {}
        for response in RESPONSES:
            rows = series[direction][response]
            by_interval = []
            for lower, upper in REGRESSION_INTERVALS_MM:
                interval_rows = [row for row in rows if lower <= row["epsilon_mm"] <= upper]
                by_threshold = []
                for threshold in SIGNAL_THRESHOLDS_MICRO_N:
                    by_threshold.append({
                        "epsilon_range_mm": [lower, upper],
                        **loo_diagnostic(interval_rows, threshold),
                    })
                by_interval.append({"epsilon_range_mm": [lower, upper], "thresholds": by_threshold})
            result["series"][direction][response] = by_interval
    return result


def _noise_tables(series: Mapping[str, Any], plateau: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sigma_scenarios_micro_n": list(NOISE_SCENARIOS_MICRO_N),
        "formula": "scenario q uncertainty = sigma / epsilon_m; sigma is an input assumption, not an observed noise measurement",
        "q_reference": "median q in each of the three registered 5-point plateau windows",
        "series": {},
    }
    for direction in DIRECTIONS:
        result["series"][direction] = {}
        for response in RESPONSES:
            result["series"][direction][response] = []
            for (start, stop), plateau_row in zip(PLATEAU_WINDOWS, plateau["series"][direction][response]):
                window_rows = series[direction][response][start:stop]
                q_ref = float(plateau_row["q_ref_median_n_per_m"])
                for force_row in window_rows:
                    for sigma in NOISE_SCENARIOS_MICRO_N:
                        q_uncertainty = sigma * 1e-6 / force_row["epsilon_m"]
                        result["series"][direction][response].append({
                            "window_epsilon_mm": plateau_row["window_epsilon_mm"],
                            "epsilon_mm": force_row["epsilon_mm"],
                            "sigma_micro_n": sigma,
                            "sigma_over_epsilon_n_per_m": q_uncertainty,
                            "q_ref_n_per_m": q_ref,
                            "uncertainty_percent_of_abs_q_ref": (
                                100.0 * q_uncertainty / abs(q_ref) if q_ref else None
                            ),
                        })
    return result


def _read_array(path: Path, order: str) -> np.ndarray:
    array = np.fromfile(path, dtype="<f4")
    if array.size != math.prod(SHAPE):
        raise ValueError(f"raw Float32 array has unexpected size: {path}")
    return array.reshape(SHAPE, order=order)


def _verify_phi_realization(
    dataset_root: Path, criteria: Mapping[str, Any], base_phi: np.ndarray,
    directions: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    checks = []
    for state in criteria["state_order"]:
        if state["role"] == "baseline":
            continue
        direction_id = state["direction_id"]
        epsilon = float(state["epsilon_m"])
        sign = int(state["sign"])
        expected = np.asarray(
            base_phi.astype(np.float64) + sign * epsilon * directions[direction_id].astype(np.float64),
            dtype=np.float32,
        )
        raw_path = dataset_root / "states" / f"{state['run_id']}.phi_f4_fortran.raw"
        npz_path = dataset_root / "states" / f"{state['run_id']}.npz"
        actual_raw = _read_array(raw_path, "F")
        with np.load(npz_path) as archive:
            actual_npz = np.asarray(archive["phi"])
        if not np.array_equal(expected, actual_raw) or not np.array_equal(expected, actual_npz):
            raise ValueError(f"saved signed Float32 state differs from deterministic realization: {state['run_id']}")
        checks.append({
            "run_id": state["run_id"], "direction_id": direction_id,
            "epsilon_m": epsilon, "sign": sign,
            "changed_node_count": int(np.count_nonzero(expected != base_phi)),
            "raw_matches_expected": True, "npz_matches_expected": True,
        })
    if len(checks) != 42:
        raise ValueError(f"expected 42 saved signed perturbation arrays, found {len(checks)}")
    return {"shape": list(SHAPE), "base_phi_raw_order": "Fortran", "direction_raw_order": "C",
            "signed_state_raw_order": "Fortran", "verified_signed_state_count": len(checks), "states": checks}


def _functional_tables(dataset_root: Path, criteria: Mapping[str, Any]) -> dict[str, Any]:
    base_phi = _read_array(dataset_root / "baseline_v17.phi_f4_fortran.raw", "F")
    with np.load(dataset_root / "baseline_v17.npz") as archive:
        base_npz_phi = np.asarray(archive["phi"])
    if base_phi.dtype != np.float32 or base_npz_phi.dtype != np.float32 or not np.array_equal(base_phi, base_npz_phi):
        raise ValueError("Fortran-order baseline raw phi does not exactly match baseline_v17.npz phi")
    directions: dict[str, np.ndarray] = {}
    for direction_id in DIRECTIONS:
        path = dataset_root / "directions" / f"{direction_id}.f4-c.raw"
        direction = _read_array(path, "C")
        if direction.dtype != np.float32:
            raise ValueError(f"registered direction is not Float32: {direction_id}")
        directions[direction_id] = direction
    state_realization = _verify_phi_realization(dataset_root, criteria, base_phi, directions)

    r5_mm = [value * 1000.0 for value in EPSILON_M]
    log_mm = [float(value) for value in np.logspace(math.log10(0.05), math.log10(50.0), 40)]
    epsilon_mm_values, overlap_r5_mm = merge_epsilon_grids(r5_mm, log_mm)
    epsilon_m_values = [value * 1e-3 for value in epsilon_mm_values]
    spacing_m = {"sdf_25_mm": 0.025, "flow_33_33_mm": 0.03333}
    baseline_f = {key: sdf_soft_volume(base_phi, h) for key, h in spacing_m.items()}
    result: dict[str, Any] = {
        "definition": "sum(clip(0.5 - phi/h, 0, 1) * h^3), phi < 0 denotes solid",
        "cell_width_m": spacing_m,
        "epsilon_r5_mm": r5_mm,
        "epsilon_logspace_requested_count": 40,
        "epsilon_logspace_overlap_with_r5_mm": overlap_r5_mm,
        "epsilon_union_unique_count": len(epsilon_mm_values),
        "epsilon_unique_mm": epsilon_mm_values,
        "baseline_functional_m3": baseline_f,
        "float32_realization_audit": state_realization,
        "zero_isosurface_volume": {
            "computed": False,
            "reason": "a robust trilinear zero-surface closed-mesh volume implementation is outside this bounded diagnostic; both specified soft-volume proxies are computed",
        },
        "directions": {},
    }
    for direction_id, direction in directions.items():
        rows = []
        direction64 = direction.astype(np.float64)
        base64 = base_phi.astype(np.float64)
        for epsilon_mm, epsilon_m in zip(epsilon_mm_values, epsilon_m_values):
            plus = np.asarray(base64 + epsilon_m * direction64, dtype=np.float32)
            minus = np.asarray(base64 - epsilon_m * direction64, dtype=np.float32)
            row: dict[str, Any] = {
                "epsilon_mm": epsilon_mm, "epsilon_m": epsilon_m,
                "is_registered_r5_epsilon": any(math.isclose(epsilon_mm, value, rel_tol=0.0, abs_tol=1e-12) for value in r5_mm),
                "changed_node_count_plus": int(np.count_nonzero(plus != base_phi)),
                "changed_node_count_minus": int(np.count_nonzero(minus != base_phi)),
                "functionals": {},
            }
            for key, h in spacing_m.items():
                f_plus = sdf_soft_volume(plus, h)
                f_minus = sdf_soft_volume(minus, h)
                parts = odd_even_parts(f_plus, f_minus, baseline_f[key], epsilon_m)
                row["functionals"][key] = {
                    "f_plus_m3": f_plus, "f_minus_m3": f_minus, **parts,
                }
            rows.append(row)
        result["directions"][direction_id] = rows
    return result


def _make_figures(
    output: Path,
    series: Mapping[str, Any],
    plateau: Mapping[str, Any],
    functionals: Mapping[str, Any],
) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "Hiragino Sans"
    plt.rcParams["axes.unicode_minus"] = False
    colors = {DIRECTIONS[0]: "#2463a6", DIRECTIONS[1]: "#d17a00", DIRECTIONS[2]: "#18835d"}
    labels = {DIRECTIONS[0]: "D0", DIRECTIONS[1]: "D1", DIRECTIONS[2]: "D2"}
    figures: dict[str, str] = {}

    def save_immutable_figure(figure: Any, path: Path) -> None:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=180, facecolor="white")
        write_immutable(path, buffer.getvalue())

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.3), constrained_layout=True)
    x = np.arange(3, dtype=np.float64)
    width = 0.24
    for response_index, response in enumerate(RESPONSES):
        ax = axes[response_index]
        for direction_index, direction in enumerate(DIRECTIONS):
            values = [100.0 * row["maximum_relative_deviation"]
                      for row in plateau["series"][direction][response]]
            ax.bar(x + (direction_index - 1) * width, values, width=width,
                   color=colors[direction], label=labels[direction])
        ax.set_xticks(x, ["0.05–1.5", "0.15–5", "0.5–15"])
        ax.set_xlabel("5点窓の ε 範囲 [mm]")
        ax.set_ylabel("登録済み正規化による最大偏差 [%]")
        ax.set_title("抗力" if response == "drag" else "ダウンフォース")
        ax.grid(axis="y", alpha=0.25)
    axes[1].legend(title="方向", frameon=False)
    fig.suptitle("R5 登録 5 点窓の記述統計（合否境界なし）")
    path = output / PLATEAU_FIGURE
    save_immutable_figure(fig, path)
    plt.close(fig)
    figures[PLATEAU_FIGURE] = sha256(path)

    for direction in DIRECTIONS:
        rows = functionals["directions"][direction]
        eps_all = [row["epsilon_mm"] for row in rows]
        fig, axes = plt.subplots(3, 2, figsize=(13.0, 11.0), constrained_layout=True)
        for col, response in enumerate(RESPONSES):
            force_rows = series[direction][response]
            axes[0, col].plot(
                [row["epsilon_mm"] for row in force_rows],
                [row["q_n_per_m"] for row in force_rows],
                color=colors[direction], marker="o", linewidth=1.6,
            )
            axes[0, col].set_title("抗力 q(ε)" if response == "drag" else "ダウンフォース q(ε)")
            axes[0, col].set_ylabel("q(ε) [N/m]")
        for row_index, (functional_key, functional_label) in enumerate((
            ("sdf_25_mm", "h = 25 mm"), ("flow_33_33_mm", "h = 33.33 mm"),
        ), start=1):
            odd = [row["functionals"][functional_key]["odd_part_over_epsilon_m2"] for row in rows]
            even = [row["functionals"][functional_key]["even_part_m3"] for row in rows]
            axes[row_index, 0].plot(eps_all, odd, color="#6a4c93", marker=".", linewidth=1.25)
            axes[row_index, 0].set_ylabel("奇数部 / ε [m²]")
            axes[row_index, 0].set_title(f"固体率汎関数の奇数部（{functional_label}）")
            axes[row_index, 1].plot(eps_all, even, color="#bc4749", marker=".", linewidth=1.25)
            axes[row_index, 1].set_ylabel("偶数部 [m³]")
            axes[row_index, 1].set_title(f"固体率汎関数の偶数部（{functional_label}）")
        for ax in axes.flat:
            ax.set_xscale("log")
            ax.set_xlabel("ε [mm]")
            ax.grid(True, which="both", alpha=0.25)
        fig.suptitle(f"{labels[direction]}：SDF連続汎関数とR5の力応答 q(ε)（別パネル・別単位）")
        filename = FUNCTIONAL_FIGURES[DIRECTIONS.index(direction)]
        path = output / filename
        save_immutable_figure(fig, path)
        plt.close(fig)
        figures[filename] = sha256(path)
    return figures


def _summary_a5(
    series: Mapping[str, Any], regression: Mapping[str, Any], plateau: Mapping[str, Any],
    loo: Mapping[str, Any], functionals: Mapping[str, Any],
) -> dict[str, Any]:
    best_windows = []
    ranks = []
    loo_defined = []
    loo_undeterminable = []
    for direction in DIRECTIONS:
        for response in RESPONSES:
            sid = f"{direction}/{response}"
            window_rows = plateau["series"][direction][response]
            best_index = min(range(3), key=lambda index: window_rows[index]["maximum_relative_deviation"])
            best = window_rows[best_index]
            best_windows.append({
                "series": sid, "window_epsilon_mm": best["window_epsilon_mm"],
                "maximum_relative_deviation_percent": best["maximum_relative_deviation_percent"],
            })
            spread = regression["series"][direction][response]["g_spread_across_three_intervals"]["all_points"]
            ranks.append({"series": sid, "relative_g_spread": spread["relative_spread"]})
            for interval in loo["series"][direction][response]:
                for threshold in interval["thresholds"]:
                    record = {
                        "series": sid,
                        "epsilon_range_mm": interval["epsilon_range_mm"],
                        "signal_threshold_micro_n": threshold["signal_threshold_micro_n"],
                        "selected_point_count": threshold["selected_point_count"],
                        "status": threshold["status"],
                    }
                    if threshold["calculation_status"] == "calculable":
                        loo_defined.append(record)
                    else:
                        loo_undeterminable.append(record)
    ranks.sort(key=lambda row: (row["relative_g_spread"] is None,
                                -(row["relative_g_spread"] or 0.0), row["series"]))
    functional_comparison = []
    d0 = functionals["directions"][DIRECTIONS[0]]
    d1 = functionals["directions"][DIRECTIONS[1]]
    for functional_key in ("sdf_25_mm", "flow_33_33_mm"):
        ratios = []
        for left, right in zip(d0, d1):
            numerator = abs(right["functionals"][functional_key]["odd_part_over_epsilon_m2"])
            denominator = abs(left["functionals"][functional_key]["odd_part_over_epsilon_m2"])
            if denominator > 0.0:
                ratios.append(numerator / denominator)
        ratio = float(median(ratios)) if ratios else None
        functional_comparison.append({
            "functional": functional_key,
            "epsilon_sample_count": len(ratios),
            "median_abs_D1_over_abs_D0": ratio,
            "median_orders_D1_below_D0": -math.log10(ratio) if ratio is not None and ratio > 0.0 else None,
        })
    return {
        "best_of_three_registered_windows_by_series": best_windows,
        "g_interval_spread_rank_descending": ranks,
        "loo_calculation_available": loo_defined,
        "loo_undeterminable": loo_undeterminable,
        "median_d1_odd_derivative_relative_to_d0": functional_comparison,
    }


def _note_text(result: Mapping[str, Any], script_sha256: str) -> str:
    integrity = result["input_integrity"]
    summary = result["a5_numeric_summary"]
    lines = [
        "# FD-08 R5 P2a 事後記述診断",
        "",
        "証拠区分: `solver_free_post_hoc_calibration_diagnostic_unregistered`",
        "",
        "## 範囲と状態",
        "",
        "この成果物は、登録済み R5 calibration の保存データに対するソルバー不要の記述診断です。R5 の既存 verdict は **FAIL** のままです。FD-08 / gradient / reverse / optimizer の qualification flags はすべて `false` のままです。gate、criteria、direction、epsilon ladder は変更しておらず、R6 / fresh33 の登録・実行はしていません。原因、達成可能性、gate の適否について結論しません。",
        "",
        "A3 の LOO 指示は、数値誤差を出す一方で pass/fail の誤差境界を定めていません。このため、計算可能なケースも数値を併記したうえで3値 status は `undeterminable` としました。これは精度の判定ではなく、分類規則が未定義であることの記録です。",
        "",
        "## 入力の固定と照合",
        "",
        f"- integration source: `{INTEGRATION_COMMIT}`; R5 source commit: `{integrity['source_commit']}`",
        f"- criteria SHA-256: `{integrity['criteria_sha256']}`",
        f"- 既存 analysis SHA-256: `{integrity['analysis_sha256']}`",
        f"- runner manifest SHA-256: `{integrity['runner_manifest_sha256']}`; runner inventory SHA-256: `{integrity['runner_inventory_sha256']}`",
        f"- dataset: {integrity['dataset_verified_file_count']}/89 files verified; inventory SHA-256 `{integrity['dataset_inventory_sha256']}`",
        f"- force outputs: {integrity['runner_force_history_count_bound_by_manifest']}/47 histories verified against the registered manifest, existing analysis and state records",
        f"- runner directory inventory complete: `{integrity['runner_full_inventory_verified']}`; missing non-input manifest files: `{integrity['runner_manifest_missing_files']}`",
        f"- signed Float32 phi: {result['a4_sdf_continuous_functionals']['float32_realization_audit']['verified_signed_state_count']}/42 saved raw and NPZ arrays exactly match deterministic `float32(base.astype(float64) ± epsilon_m * direction)` realization",
        f"- diagnostic script SHA-256: `{script_sha256}`",
        "",
        "Inputs are read-only. `phi` is interpreted as metres with `phi < 0` denoting solid; baseline raw phi uses Fortran order, direction arrays use C order, and saved signed raw phi uses Fortran order. The three force responses use the existing host recomputation helper, exact clipped `[80,120] tU/L` endpoints and `1/900 N` per solver force unit.",
        "",
        "## 固定した記述定義",
        "",
        "- `R0`: 5 baseline repeat force means combined with `math.fsum / 5`; used only for `E`.",
        "- `S=(R(+ε)-R(-ε))/2`, `q=S/ε` with ε converted from mm to m for `q [N/m]`; `E=(R(+ε)+R(-ε))/2-R0`.",
        "- `q=g+c ε²`: unweighted least squares on the three fixed inclusive intervals `[0.5,5]`, `[0.5,15]`, `[1.5,15] mm`; full points and signal-selected columns are both recorded. Signal selections use 10/30/50 µN; 50 µN is the primary descriptive cut. These were chosen after P1 and the plan tables had exposed S and q, and are not described as preregistered thresholds.",
        "- Plateau windows are the three consecutive five-point windows starting at 0.05, 0.15 and 0.5 mm. Maximum deviation uses the registered normalizer `max(|median(q)|, response_floor / epsilon_min)`; no pass/fail line is added.",
        "- LOO includes points where `|S| >= X µN`; relative error is undefined when `|q_obs| < 1e-9 N/m`. Sigma scenarios `{2,3,4} µN` are assumptions, not measured noise.",
        f"- SDF proxies are `Σ clip(0.5 - phi/h,0,1) h³` for `h=25 mm` and `h=33.33 mm`. Seven R5 epsilon values are combined with 40 logarithmically spaced values from 0.05 to 50 mm; overlapping values `{result['a4_sdf_continuous_functionals']['epsilon_logspace_overlap_with_r5_mm']}` are deduplicated with exact R5 values retained, giving {result['a4_sdf_continuous_functionals']['epsilon_union_unique_count']} unique epsilon values. Trilinear zero-isosurface volume was omitted because a robust closed-mesh implementation is outside this bounded diagnostic; both specified soft-volume proxies are included.",
        "",
        "The soft-volume functionals are SDF grid proxies. They are not the WaterLily fluid-cell cut/mask or its `normal_floor`; smoothness in these proxy curves does not establish absence of cut/mask changes. Functional units are shown in separate plot panels from force `q`.",
        "",
        "## 数値要約（A5）",
        "",
        "### 3窓のうち最大偏差が最小の窓",
        "",
        "| 系列 | 窓 ε [mm] | 最大偏差 [%] |",
        "|---|---:|---:|",
    ]
    for row in summary["best_of_three_registered_windows_by_series"]:
        lines.append(f"| {row['series']} | {row['window_epsilon_mm'][0]:g}–{row['window_epsilon_mm'][-1]:g} | {row['maximum_relative_deviation_percent']:.8g} |")
    lines.extend(["", "### 3区間 g ずれ（大きい順）", "", "| 順位 | 系列 | (max g − min g)/|median g| |", "|---:|---|---:|"])
    for index, row in enumerate(summary["g_interval_spread_rank_descending"], 1):
        value = "undeterminable" if row["relative_g_spread"] is None else f"{row['relative_g_spread']:.8g}"
        lines.append(f"| {index} | {row['series']} | {value} |")
    lines.extend([
        "",
        "LOO の数値・各閾値・各系列・各区間と `status` は JSON の `loo` に全件記録しました。`calculation_status=calculable` は数値を算出できたことだけを表し、3値 `status` は誤差境界がないため `undeterminable` です。",
        "",
        "### D1 / D0 の SDF 奇数部微分中央値比",
        "",
        "| 汎関数 | ε点数 | median(|D1|/|D0|) | D1が小さい桁数 = −log10(比) |",
        "|---|---:|---:|---:|",
    ])
    for row in summary["median_d1_odd_derivative_relative_to_d0"]:
        ratio = "undeterminable" if row["median_abs_D1_over_abs_D0"] is None else f"{row['median_abs_D1_over_abs_D0']:.8g}"
        orders = "undeterminable" if row["median_orders_D1_below_D0"] is None else f"{row['median_orders_D1_below_D0']:.8g}"
        lines.append(f"| {row['functional']} | {row['epsilon_sample_count']} | {ratio} | {orders} |")
    lines.extend([
        "",
        "## 図と完全データ",
        "",
        "- `plateau_windows.png`: 6系列・3窓の最大偏差。",
        "- `sdf_functionals_D0.png` / `D1` / `D2`: 力 `q(ε)` と、各 h の奇数部・偶数部を別パネルで表示。日本語タイトル・軸ラベルを使用。",
        "- `diagnostic_result.json`: A1–A5 の数値、force/dataset/source hashes、各入力との対応を含む完全な機械可読結果。PNG の SHA-256 は参照値として記録し、`SHA256SUMS` は JSON とこの note のみを固定。",
        "",
        "## 変更・停止記録",
        "",
        "作業ブランチは `codex/kaggle-batch-migration` から作成し、integration は `--no-ff` merge しました。これはユーザー指示による運用で、`docs/git_branching_strategy.md` の trunk 運用とは異なる点を明記します。ここで Step A を終え、結果を #46 に報告して停止します。B の gate / FD-08 定義の判断はユーザーに残します。",
        "",
    ])
    return "\n".join(lines)


def run(repo: Path, dataset_root: Path) -> Path:
    repo = repo.resolve()
    dataset_root = dataset_root.resolve()
    criteria, analysis, integrity, runner_manifest = _verify_inputs(repo, dataset_root)
    force, force_hashes = _read_force_means(
        repo, criteria, analysis, integrity["runner_root"], runner_manifest,
    )
    series, r0 = _build_force_tables(criteria, analysis, force, force_hashes)
    regression = _regression_tables(series)
    plateau = _plateau_tables(series, analysis)
    loo = _loo_tables(series)
    noise = _noise_tables(series, plateau)
    functionals = _functional_tables(dataset_root, criteria)

    try:
        current_commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover - only exercised outside a git checkout
        raise ValueError("could not bind diagnostic to the current Git commit") from exc
    if current_commit != INTEGRATION_COMMIT:
        raise ValueError(f"diagnostic must start at registered integration commit {INTEGRATION_COMMIT}; found {current_commit}")

    output = repo / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    figures = _make_figures(output, series, plateau, functionals)
    baseline_failure_ids = json.loads(
        (repo / "docs/evidence/four_track_baseline_2026_10_02/failure_ids.json").read_text(encoding="utf-8")
    )
    baseline_xml = Path("/tmp/fd08_p2a_baseline_20261005.xml")
    actual_failure_ids: list[str] = []
    if baseline_xml.exists():
        import xml.etree.ElementTree as ET

        root = ET.parse(baseline_xml).getroot()
        for testcase in root.iter("testcase"):
            if any(child.tag in {"failure", "error"} for child in testcase):
                actual_failure_ids.append(f"{testcase.attrib['classname'].replace('.', '/')}.py::{testcase.attrib['name']}")
    pinned = set(baseline_failure_ids)
    actual = set(actual_failure_ids)
    if not baseline_xml.exists() or actual != pinned:
        raise ValueError("pre-change full pytest failure IDs do not match the pinned baseline")
    baseline_test_record = {
        "command": ".venv/bin/python -m pytest -q --junitxml=/tmp/fd08_p2a_baseline_20261005.xml (run from clean integration worktree before edits)",
        "pytest_exit_code": 1,
        "failed": len(actual_failure_ids),
        "passed": 1439,
        "skipped": 9,
        "failure_id_count": len(actual_failure_ids),
        "new_failure_ids": [], "resolved_failure_ids": [],
        "junit_xml_path": baseline_xml.as_posix(),
        "junit_xml_sha256": sha256(baseline_xml),
    }
    script_sha = sha256(Path(__file__).resolve())
    result: dict[str, Any] = {
        "schema_version": 1,
        "evidence_class": "solver_free_post_hoc_calibration_diagnostic_unregistered",
        "diagnostic_purpose": "descriptive only; no verdict, causal attribution, or gate suitability decision",
        "status_snapshot": {
            "historical_r5_calibration_verdict": analysis["calibration_verdict"],
            "formal_phase_allowed": analysis["formal_phase_allowed"],
            "qualification_flags": analysis["qualification_flags"],
            "r6_registered": False, "fresh33_registered_or_run": False,
        },
        "input_integrity": integrity,
        "diagnostic_source": {
            "integration_commit": current_commit,
            "script_path": "scripts/diagnose_fd08_r5_posthoc_p2a.py",
            "script_sha256": script_sha,
            "git_strategy_note": "user-directed exp branch from integration and --no-ff merge; differs from repository trunk strategy",
        },
        "software": {
            "python": platform.python_version(), "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "force_definition": {
            "flow_id": analysis["flow_id"],
            "window_t_u_l": [80.0, 120.0],
            "force_scale_n_per_solver_force": float(analysis["force_scale_n_per_solver_force"]),
            "r0_baseline_repeat_ids": [row["run_id"] for row in criteria["state_order"] if row["role"] == "baseline"],
            "r0_mean_n_by_response": r0,
            "r0_method": "math.fsum(five registered identical-input baseline force means) / 5; used only for E",
            "s_q_e_formula": "S=(R(+epsilon)-R(-epsilon))/2; q=S/epsilon_m; E=(R(+epsilon)+R(-epsilon))/2-R0",
        },
        "a1_force_decomposition": series,
        "a2_interval_regressions": regression,
        "a3_registered_plateau_windows": plateau,
        "a3_prime_loo": loo,
        "a3_double_prime_noise_scenarios": noise,
        "a4_sdf_continuous_functionals": functionals,
        "a5_numeric_summary": None,
        "prechange_full_pytest_baseline": baseline_test_record,
        "figures": figures,
    }
    result["a5_numeric_summary"] = _summary_a5(series, regression, plateau, loo, functionals)
    result_path = output / "diagnostic_result.json"
    result_data = json_bytes(result)
    write_immutable(result_path, result_data)
    note_data = _note_text(result, script_sha).encode("utf-8")
    note_path = output / "P2a_diagnostic_note.md"
    write_immutable(note_path, note_data)
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in (
        ("diagnostic_result.json", result_data), ("P2a_diagnostic_note.md", note_data),
    )).encode("ascii")
    write_immutable(output / "SHA256SUMS", sums)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--dataset-root", type=Path,
        default=Path("/Users/sota/.codex/worktrees/issue45-root-certifier-integration/work/fd08_candidate_c_calibration_dataset_r5"),
    )
    args = parser.parse_args()
    print(run(args.repo_root, args.dataset_root))


if __name__ == "__main__":
    main()
