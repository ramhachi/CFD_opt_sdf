#!/usr/bin/env python3
"""Recompute FD-08 calibration responses from hash-verified raw force histories."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import tempfile

from cfd_sdf.fd08_calibration import (
    CALIBRATION_BASELINE_REPEATS,
    centered_pair,
    derive_response_floor,
    recompute_force_history,
    select_formal_epsilon_ladder,
    verify_output_manifest,
    verify_registered_dataset,
)
from cfd_sdf.fd08_contract import CALIBRATION_FLOW, WINDOW_TU_L


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_immutable_json(path: Path) -> tuple[dict, str]:
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"immutable JSON and SHA-256 sidecar are required: {path}")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError(f"SHA-256 sidecar mismatch: {path}")
    return json.loads(path.read_text()), digest


def _write_once(path: Path, value: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(f"refusing to overwrite append-only evidence: {path}")
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise FileExistsError(f"refusing to overwrite append-only evidence: {path}") from exc
        digest = hashlib.sha256(payload).hexdigest()
        sidecar_fd, sidecar_temp_name = tempfile.mkstemp(prefix=f".{sidecar.name}.", dir=sidecar.parent)
        try:
            with os.fdopen(sidecar_fd, "w") as handle:
                handle.write(digest + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(sidecar_temp_name, sidecar)
            except FileExistsError as exc:
                path.unlink(missing_ok=True)
                raise FileExistsError(f"refusing to overwrite append-only evidence: {sidecar}") from exc
        finally:
            Path(sidecar_temp_name).unlink(missing_ok=True)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return digest


def analyze(criteria_path: Path, runner_result_path: Path, result_root: Path, dataset_dir: Path) -> dict:
    criteria, criteria_sha = load_immutable_json(criteria_path)
    expected_root = criteria.get("artifact_namespaces", {}).get("calibration_result_root")
    if not isinstance(expected_root, str) or Path(result_root).resolve() != (ROOT / expected_root).resolve():
        raise ValueError("calibration artifacts must be saved in the preregistered result namespace")
    dataset_audit = verify_registered_dataset(criteria, criteria_sha, dataset_dir)
    manifest_audit = verify_output_manifest(result_root, runner_result_path)
    if (criteria.get("kind") != "fd08_candidate_c_calibration"
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"):
        raise ValueError("input must be immutable preregistered FD-08 calibration criteria")
    if criteria.get("flow_id") != CALIBRATION_FLOW or criteria.get("window_tu_l") != list(WINDOW_TU_L):
        raise ValueError("calibration criteria must bind flow_24 and exact [80,120] tU/L")
    states = criteria.get("state_order")
    if not isinstance(states, list) or not states:
        raise ValueError("calibration state_order inventory is missing")
    expected_ids = [item.get("name") for item in states]
    if (any(not isinstance(run_id, str) or not run_id for run_id in expected_ids)
            or len(set(expected_ids)) != len(expected_ids)):
        raise ValueError("calibration state IDs must be unique nonempty strings")

    run_result = json.loads(Path(runner_result_path).read_text())
    runner_source = criteria.get("source_inputs", {}).get("kernel_base_runner", {})
    if (run_result.get("criteria_sha256") != criteria_sha
            or run_result.get("all_states_completed") is not True
            or run_result.get("source_commit") != criteria.get("source_commit")
            or not isinstance(runner_source, dict)
            or run_result.get("runner_sha256") != runner_source.get("sha256")):
        raise ValueError("runner terminal does not bind the exact complete calibration criteria/source")
    state_results = run_result.get("states")
    if not isinstance(state_results, dict) or set(state_results) != set(expected_ids):
        raise ValueError("runner terminal state inventory is incomplete or contains extras")
    if run_result.get("status_counts") != {"COMPLETED": len(states)}:
        raise ValueError("runner terminal contains failed or incomplete calibration states")

    state_by_id = {item["name"]: item for item in states}
    histories: dict[str, dict] = {}
    raw_bindings: dict[str, dict] = {}
    runtime_by_state: dict[str, dict] = {}
    root = Path(result_root).resolve()
    case = criteria["case"]
    force_scale = (float(case["density_kg_m3"]) * float(case["freestream_mps"][0]) ** 2
                   * float(case["flow_spacing_m"]) ** 2)
    for run_id in expected_ids:
        run = state_results[run_id]
        if run.get("status") != "COMPLETED" or not all(run.get("gates", {}).values()):
            raise ValueError(f"calibration run failed its registered state gates: {run_id}")
        state_dir = (root / "states" / run_id).resolve()
        if root not in state_dir.parents:
            raise ValueError(f"unsafe calibration state path: {run_id}")
        csv_path = state_dir / "flow_24.forces.csv"
        summary_path = state_dir / "flow_24.summary.json"
        if not summary_path.is_file():
            raise ValueError(f"per-state summary is missing: {run_id}")
        summary = json.loads(summary_path.read_text())
        raw_record = recompute_force_history(csv_path, force_scale_n_per_solver_force=force_scale)
        if raw_record["sha256"] != run.get("force_csv_sha256"):
            raise ValueError(f"runner/result raw-history SHA mismatch: {run_id}")
        if (raw_record["window_t_u_l"] != list(WINDOW_TU_L)
                or summary.get("force_csv_sha256") != raw_record["sha256"]
                or summary.get("state_sha256") != state_by_id[run_id]["state_sha256"]
                or summary.get("phi_fortran_sha256") != state_by_id[run_id]["phi_fortran_sha256"]):
            raise ValueError(f"raw force history or state binding mismatch: {run_id}")
        runtime = {
            "julia_version": summary.get("julia_version"),
            "waterlily_version": summary.get("waterlily_version"),
            "cuda_jl_version": summary.get("cuda_jl_version"),
            "gpu_name": summary.get("gpu_name"),
            "gpu_uuid": summary.get("gpu_uuid"),
            "driver_version": run_result.get("host_driver_version_recorded_not_gated"),
        }
        if any(not isinstance(value, str) or not value for value in runtime.values()):
            raise ValueError(f"actual runtime identity is incomplete: {run_id}")
        runtime_by_state[run_id] = runtime
        histories[run_id] = raw_record["force_n"]
        raw_bindings[run_id] = {
            "path": csv_path.relative_to(root).as_posix(),
            "sha256": raw_record["sha256"], "row_count": raw_record["row_count"],
            "host_recomputed_force_n": raw_record["force_n"],
        }
    if len({json.dumps(item, sort_keys=True) for item in runtime_by_state.values()}) != 1:
        raise ValueError("calibration state runs do not share one observed runtime identity")

    baseline_ids = [run_id for run_id in expected_ids if state_by_id[run_id].get("role") == "baseline"]
    perturbation_ids = [run_id for run_id in expected_ids if state_by_id[run_id].get("role") == "perturbation"]
    if len(baseline_ids) != CALIBRATION_BASELINE_REPEATS or len(baseline_ids) + len(perturbation_ids) != len(states):
        raise ValueError("calibration inventory must contain the fixed five baselines and perturbations only")
    floors = {
        response: derive_response_floor([histories[run_id][response] for run_id in baseline_ids])
        for response in ("drag", "downforce")
    }
    epsilons = tuple(float(value) for value in criteria["calibration_epsilon_ladder_m"])
    directions = tuple(criteria["direction_inventory"])
    expected_pairs = {(direction, epsilon, sign) for direction in directions
                      for epsilon in epsilons for sign in (-1, 1)}
    observed_pairs = set()
    pair_rows: dict[str, dict[str, list[dict]]] = {
        direction: {response: [] for response in ("drag", "downforce")}
        for direction in directions
    }
    pair_raw: dict[str, dict[str, list[dict]]] = {
        direction: {response: [] for response in ("drag", "downforce")}
        for direction in directions
    }
    for run_id in perturbation_ids:
        item = state_by_id[run_id]
        key = (item.get("direction_id"), float(item.get("epsilon_m", math.nan)), item.get("sign"))
        if key not in expected_pairs or key in observed_pairs:
            raise ValueError(f"unexpected or duplicated calibration direction/epsilon/sign: {run_id}")
        observed_pairs.add(key)
    if observed_pairs != expected_pairs:
        raise ValueError("calibration direction/epsilon/sign inventory is incomplete")

    for direction in directions:
        for epsilon in epsilons:
            signed_ids = {
                int(item["sign"]): item["name"] for item in states
                if item.get("role") == "perturbation" and item.get("direction_id") == direction
                and float(item["epsilon_m"]) == epsilon
            }
            if set(signed_ids) != {-1, 1}:
                raise ValueError(f"incomplete signed calibration pair: {direction}, {epsilon}")
            for response in ("drag", "downforce"):
                plus_id, minus_id = signed_ids[1], signed_ids[-1]
                pair = centered_pair(histories[plus_id][response], histories[minus_id][response], epsilon)
                row = {"epsilon_m": epsilon, **pair,
                       "resolved": abs(float(pair["centered_response_n"])) > floors[response]["response_floor_n"]}
                pair_rows[direction][response].append(row)
                pair_raw[direction][response].append({
                    "plus_run_id": plus_id, "minus_run_id": minus_id,
                    "plus_history_sha256": raw_bindings[plus_id]["sha256"],
                    "minus_history_sha256": raw_bindings[minus_id]["sha256"],
                    **row,
                })

    selection = select_formal_epsilon_ladder(
        epsilons_m=epsilons, pairs=pair_rows,
        response_floors_n={k: float(v["response_floor_n"]) for k, v in floors.items()},
    )
    return {
        "kind": "fd08_candidate_c_calibration_analysis",
        "evidence_class": "host_recomputed_micro_response_calibration_only",
        "calibration_criteria_path": Path(criteria_path).as_posix(),
        "calibration_criteria_sha256": criteria_sha,
        "runner_result_path": Path(runner_result_path).as_posix(),
        "runner_result_sha256": sha256(Path(runner_result_path)),
        "result_root_path": Path(result_root).resolve().as_posix(),
        "registered_dataset_audit": dataset_audit,
        "runner_output_manifest": manifest_audit,
        "source_commit": criteria["source_commit"],
        "observed_runtime_identity": next(iter(runtime_by_state.values())),
        "flow_id": CALIBRATION_FLOW, "window_t_u_l": list(WINDOW_TU_L),
        "force_scale_n_per_solver_force": force_scale,
        "raw_force_history_inventory": raw_bindings,
        "calibration_run_ids": expected_ids,
        "calibration_run_count": len(expected_ids),
        "baseline_repeat_ids": baseline_ids,
        "baseline_resolution_floors": floors,
        "direction_response_pairs": pair_raw,
        "formal_ladder_selection": selection,
        "fresh_solver_execution_verified": True,
        "formal_qualification": False,
        "criteria_registered": False,
        "qualification_flags": criteria["qualification_flags"],
        "analysis_host": {"platform": platform.platform(), "python": platform.python_version()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--criteria", type=Path, required=True)
    parser.add_argument("--runner-result", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.criteria, args.runner_result, args.result_root, args.dataset)
    digest = _write_once(args.output, result)
    print(json.dumps({"result_path": args.output.as_posix(), "result_sha256": digest,
                      "formal_ladder_selection": result["formal_ladder_selection"],
                      "formal_qualification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
