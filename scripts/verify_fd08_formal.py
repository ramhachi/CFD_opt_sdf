#!/usr/bin/env python3
"""Host-verify the FD-08 formal fresh-33 result from raw force histories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

import numpy as np

from cfd_sdf.fd08_calibration import (
    FORMAL_DIRECTION_IDS,
    aggregate_formal_verdict,
    centered_pair,
    derive_response_floor,
    evaluate_formal_direction_response,
    recompute_force_history,
    select_formal_epsilon_ladder,
    validate_formal_epsilon_ladder,
    verify_output_manifest,
    verify_registered_dataset,
)
from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.fd08_contract import (
    CANONICAL_PHI_FORTRAN_F32_SHA256,
    CANONICAL_STATE_IDENTITY_SHA256,
    CANONICAL_STATE_NPZ_SHA256,
    FRESH_QUALIFICATION_RUNS,
    WINDOW_TU_L,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_immutable(path: Path) -> tuple[dict, str]:
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError("formal criteria and SHA-256 sidecar are required")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError("formal criteria SHA-256 sidecar mismatch")
    return json.loads(path.read_text()), digest


def verify_source_inputs(source_inputs: dict, *, root: Path = ROOT) -> dict[str, str]:
    """Check the complete criteria-bound source inventory against this checkout."""
    if not isinstance(source_inputs, dict) or not source_inputs:
        raise ValueError("criteria source input inventory is missing")
    verified = {}
    root = Path(root).resolve()
    for name, entry in source_inputs.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise ValueError("criteria source input entry is invalid")
        relative = entry.get("path")
        expected = entry.get("sha256")
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts or relative != Path(relative).as_posix()
                or entry.get("location") != "source_repo"
                or not isinstance(expected, str) or len(expected) != 64):
            raise ValueError(f"criteria source input binding is invalid: {name}")
        candidate = root / relative
        path = candidate.resolve()
        if candidate.is_symlink() or root not in path.parents or not path.is_file():
            raise ValueError(f"criteria source input is missing or unsafe: {name}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"criteria source input SHA-256 mismatch: {name}")
        verified[name] = actual
    return verified


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
        os.link(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    try:
        with sidecar.open("x") as handle:
            handle.write(digest + "\n")
    except FileExistsError:
        path.unlink(missing_ok=True)
        raise
    return digest


def verify(criteria_path: Path, runner_result_path: Path, result_root: Path, dataset_dir: Path) -> dict:
    criteria, criteria_sha = load_immutable(criteria_path)
    verified_sources = verify_source_inputs(criteria.get("source_inputs", {}))
    if not {"formal_verifier", "formal_kernel_wrapper", "formal_kernel_base_runner"}.issubset(verified_sources):
        raise ValueError("formal criteria do not bind the host verifier and uploaded kernel sources")
    frozen_identity = load_candidate_c_identity(ROOT)
    if criteria.get("candidate_c_identity") != frozen_identity:
        raise ValueError("formal criteria Candidate C identity differs from the frozen source identity")
    geometry = criteria.get("geometry", {})
    if (geometry.get("canonical_state_npz_sha256") != CANONICAL_STATE_NPZ_SHA256
            or geometry.get("canonical_state_identity_sha256") != CANONICAL_STATE_IDENTITY_SHA256
            or geometry.get("canonical_phi_fortran_sha256") != CANONICAL_PHI_FORTRAN_F32_SHA256):
        raise ValueError("formal criteria canonical v17 state hashes differ from the frozen FD-08 contract")
    dataset_audit = verify_registered_dataset(criteria, criteria_sha, dataset_dir)
    if (criteria.get("kind") != "fd08_candidate_c_formal"
            or criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_run_count") != FRESH_QUALIFICATION_RUNS):
        raise ValueError("criteria are not the immutable FD-08 fresh-33 formal contract")
    expected_flags = {key: False for key in (
        "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
    if criteria.get("qualification_flags") != expected_flags or criteria.get("formal_qualification") is not False:
        raise ValueError("formal criteria must preserve all six qualification flags as literal false")
    if criteria.get("flow_id") != "flow_24" or criteria.get("window_tu_l") != list(WINDOW_TU_L):
        raise ValueError("formal criteria must bind flow_24 and the exact [80,120] tU/L window")
    formal_epsilon = validate_formal_epsilon_ladder(criteria.get("formal_epsilon_ladder_m", []))
    direction_inventory = criteria.get("direction_inventory")
    if not isinstance(direction_inventory, dict) or tuple(direction_inventory) != FORMAL_DIRECTION_IDS:
        raise ValueError("formal criteria direction inventory differs from the frozen D0/D1/D2 order")

    calibration_evidence = criteria.get("calibration_evidence", {})
    calibration_sources = criteria.get("source_inputs", {})
    for label, field, sha_field in (
        ("calibration_criteria", "criteria_path", "criteria_sha256"),
        ("calibration_result", "result_path", "result_sha256"),
    ):
        source = calibration_sources.get(label, {})
        relative_path = calibration_evidence.get(field)
        expected_sha = calibration_evidence.get(sha_field)
        if (not isinstance(relative_path, str) or source.get("path") != relative_path
                or source.get("sha256") != expected_sha):
            raise ValueError(f"formal criteria do not bind the immutable {label} artifact")
        artifact = ROOT / relative_path
        sidecar = artifact.with_suffix(artifact.suffix + ".sha256")
        if (not artifact.is_file() or not sidecar.is_file()
                or sha256(artifact) != expected_sha or sidecar.read_text().strip() != expected_sha):
            raise ValueError(f"registered {label} artifact or its immutable sidecar is unavailable or mismatched")
    calibration_result = json.loads((ROOT / calibration_evidence["result_path"]).read_text())
    calibration_criteria = json.loads((ROOT / calibration_evidence["criteria_path"]).read_text())
    calibration_dataset_path = ROOT / calibration_criteria.get("dataset_staging_path", "")
    calibration_dataset_audit = verify_registered_dataset(
        calibration_criteria, calibration_evidence["criteria_sha256"], calibration_dataset_path,
    )
    if (calibration_dataset_audit != calibration_result.get("registered_dataset_audit")
            or calibration_dataset_audit != calibration_evidence.get("registered_dataset_audit")):
        raise ValueError("calibration input dataset differs from its immutable analysis/registration binding")
    calibration_ids = calibration_result.get("calibration_run_ids", [])
    calibration_states = calibration_criteria.get("state_order", [])
    calibration_raw = calibration_result.get("raw_force_history_inventory", {})
    expected_calibration_ids = [row.get("name") for row in calibration_states]
    if (calibration_result.get("calibration_criteria_sha256") != calibration_evidence.get("criteria_sha256")
            or calibration_result.get("kind") != "fd08_candidate_c_calibration_analysis"
            or calibration_criteria.get("kind") != "fd08_candidate_c_calibration"
            or calibration_ids != expected_calibration_ids
            or set(calibration_raw) != set(calibration_ids)
            or calibration_evidence.get("calibration_run_ids") != calibration_ids
            or calibration_evidence.get("calibration_raw_force_history_sha256") != {
                run_id: item.get("sha256") for run_id, item in calibration_raw.items()
            }):
        raise ValueError("formal epsilon ladder differs from the hash-bound calibration analysis")
    calibration_namespace = calibration_criteria.get("artifact_namespaces", {}).get("calibration_result_root")
    calibration_root = Path(calibration_result.get("result_root_path", "")).resolve()
    calibration_terminal_path = Path(calibration_result.get("runner_result_path", "")).resolve()
    if (not isinstance(calibration_namespace, str)
            or calibration_root != (ROOT / calibration_namespace).resolve()):
        raise ValueError("calibration outputs are outside their hash-bound result namespace")
    calibration_manifest = verify_output_manifest(calibration_root, calibration_terminal_path)
    if (calibration_manifest != calibration_result.get("runner_output_manifest")
            or calibration_evidence.get("runner_output_manifest") != calibration_manifest
            or sha256(calibration_terminal_path) != calibration_result.get("runner_result_sha256")):
        raise ValueError("calibration output manifest or runner terminal changed after preregistration")
    calibration_terminal = json.loads(calibration_terminal_path.read_text())
    calibration_runner_source = calibration_criteria.get("source_inputs", {}).get("kernel_base_runner", {})
    if (calibration_terminal.get("criteria_sha256") != calibration_evidence.get("criteria_sha256")
            or calibration_terminal.get("source_commit") != calibration_criteria.get("source_commit")
            or not isinstance(calibration_runner_source, dict)
            or calibration_terminal.get("runner_sha256") != calibration_runner_source.get("sha256")
            or calibration_terminal.get("all_states_completed") is not True
            or calibration_terminal.get("status_counts") != {"COMPLETED": len(calibration_ids)}
            or set(calibration_terminal.get("states", {})) != set(calibration_ids)):
        raise ValueError("calibration runner terminal is incomplete or not bound to the registered criteria")

    calibration_case = calibration_criteria["case"]
    calibration_force_scale = (
        float(calibration_case["density_kg_m3"])
        * float(calibration_case["freestream_mps"][0]) ** 2
        * float(calibration_case["flow_spacing_m"]) ** 2
    )
    if calibration_result.get("force_scale_n_per_solver_force") != calibration_force_scale:
        raise ValueError("saved calibration force conversion differs from the registered flow_24 scale")
    calibration_state_map = {row["name"]: row for row in calibration_states}
    calibration_force_n: dict[str, dict[str, float]] = {}
    calibration_runtimes = {}
    for run_id in calibration_ids:
        binding = calibration_raw[run_id]
        raw_path = (calibration_root / binding["path"]).resolve()
        if calibration_root not in raw_path.parents:
            raise ValueError(f"unsafe calibration force-history path: {run_id}")
        raw_record = recompute_force_history(
            raw_path, force_scale_n_per_solver_force=calibration_force_scale,
        )
        terminal_state = calibration_terminal["states"][run_id]
        state = calibration_state_map[run_id]
        if (raw_record["sha256"] != binding.get("sha256")
                or raw_record["row_count"] != binding.get("row_count")
                or raw_record["force_n"] != binding.get("host_recomputed_force_n")
                or terminal_state.get("status") != "COMPLETED"
                or not all(terminal_state.get("gates", {}).values())):
            raise ValueError(f"calibration raw history or terminal state failed independent verification: {run_id}")
        summary_path = raw_path.parent / "flow_24.summary.json"
        if not summary_path.is_file():
            raise ValueError(f"calibration state summary is missing: {run_id}")
        summary = json.loads(summary_path.read_text())
        if (summary.get("state_sha256") != state.get("state_sha256")
                or summary.get("phi_fortran_sha256") != state.get("phi_fortran_sha256")
                or summary.get("force_csv_sha256") != raw_record["sha256"]):
            raise ValueError(f"calibration state summary is not bound to its registered input/history: {run_id}")
        runtime = {
            "julia_version": summary.get("julia_version"),
            "waterlily_version": summary.get("waterlily_version"),
            "cuda_jl_version": summary.get("cuda_jl_version"),
            "gpu_name": summary.get("gpu_name"), "gpu_uuid": summary.get("gpu_uuid"),
            "driver_version": calibration_terminal.get("host_driver_version_recorded_not_gated"),
        }
        if any(not isinstance(value, str) or not value for value in runtime.values()):
            raise ValueError(f"calibration runtime identity is incomplete: {run_id}")
        calibration_runtimes[run_id] = runtime
        calibration_force_n[run_id] = raw_record["force_n"]
    if len({json.dumps(value, sort_keys=True) for value in calibration_runtimes.values()}) != 1:
        raise ValueError("calibration runs do not share one observed runtime identity")
    if next(iter(calibration_runtimes.values())) != calibration_result.get("observed_runtime_identity"):
        raise ValueError("calibration runtime differs from the immutable host analysis")

    baseline_ids = [row["name"] for row in calibration_states if row.get("role") == "baseline"]
    expected_baseline_ids = calibration_result.get("baseline_repeat_ids", [])
    if len(baseline_ids) != 5 or expected_baseline_ids != baseline_ids:
        raise ValueError("hash-bound calibration analysis has an invalid five-repeat baseline inventory")
    recalculated_floors = {
        response: derive_response_floor([calibration_force_n[run_id][response] for run_id in baseline_ids])
        for response in ("drag", "downforce")
    }
    if recalculated_floors != calibration_result.get("baseline_resolution_floors"):
        raise ValueError("calibration response floors do not recompute from raw force histories")

    ladder = calibration_criteria.get("calibration_epsilon_ladder_m", [])
    calculated_pair_rows = {
        direction: {response: [] for response in ("drag", "downforce")}
        for direction in FORMAL_DIRECTION_IDS
    }
    calculated_pair_inventory = {
        direction: {response: [] for response in ("drag", "downforce")}
        for direction in FORMAL_DIRECTION_IDS
    }
    for direction in FORMAL_DIRECTION_IDS:
        for epsilon in ladder:
            signed_states = {
                int(row["sign"]): row for row in calibration_states
                if row.get("role") == "perturbation" and row.get("direction_id") == direction
                and float(row.get("epsilon_m")) == float(epsilon)
            }
            if set(signed_states) != {-1, 1}:
                raise ValueError(f"calibration raw inventory lacks a complete signed pair: {direction}/{epsilon}")
            plus, minus = signed_states[1], signed_states[-1]
            for response in ("drag", "downforce"):
                pair = centered_pair(
                    calibration_force_n[plus["name"]][response],
                    calibration_force_n[minus["name"]][response], float(epsilon),
                )
                row = {
                    "epsilon_m": float(epsilon), **pair,
                    "resolved": abs(float(pair["centered_response_n"]))
                    > recalculated_floors[response]["response_floor_n"],
                }
                calculated_pair_rows[direction][response].append(row)
                calculated_pair_inventory[direction][response].append({
                    "plus_run_id": plus["name"], "minus_run_id": minus["name"],
                    "plus_history_sha256": calibration_raw[plus["name"]]["sha256"],
                    "minus_history_sha256": calibration_raw[minus["name"]]["sha256"],
                    **row,
                })
    if calculated_pair_inventory != calibration_result.get("direction_response_pairs"):
        raise ValueError("calibration directional responses do not recompute from raw force histories")
    recalculated_selection = select_formal_epsilon_ladder(
        epsilons_m=ladder,
        pairs=calculated_pair_rows,
        response_floors_n={key: row["response_floor_n"] for key, row in recalculated_floors.items()},
    )
    if (recalculated_selection != calibration_result.get("formal_ladder_selection")
            or recalculated_selection.get("selected_formal_epsilon_ladder_m") != list(formal_epsilon)):
        raise ValueError("formal ladder does not match independent calibration-selection recomputation")

    states = criteria.get("state_order")
    run_ids = [row.get("name") for row in states] if isinstance(states, list) else []
    if len(run_ids) != FRESH_QUALIFICATION_RUNS or len(set(run_ids)) != FRESH_QUALIFICATION_RUNS:
        raise ValueError("formal state inventory must contain exactly 33 unique rows")
    disjoint = criteria.get("calibration_formal_disjointness", {})
    cal_ids = disjoint.get("calibration_run_ids", [])
    if set(run_ids) & set(cal_ids) or disjoint.get("formal_run_ids") != run_ids:
        raise ValueError("calibration and formal run IDs overlap")
    if len([row for row in states if row.get("role") == "baseline"]) != 3:
        raise ValueError("formal set must have exactly three baselines")
    if len([row for row in states if row.get("role") == "perturbation"]) != 30:
        raise ValueError("formal set must have 30 signed perturbations")
    cells = {
        (row.get("direction_id"), float(row.get("epsilon_m", float("nan"))), row.get("sign"))
        for row in states if row.get("role") == "perturbation"
    }
    expected_cells = {
        (direction, epsilon, sign)
        for direction in FORMAL_DIRECTION_IDS for epsilon in formal_epsilon for sign in (-1, 1)
    }
    if cells != expected_cells:
        raise ValueError("formal state inventory is not the complete shared 3 x 5 x 2 design")
    namespaces = criteria.get("artifact_namespaces", {})
    calibration_root = namespaces.get("calibration_result_root")
    formal_root = namespaces.get("formal_result_root")
    if (not isinstance(calibration_root, str) or not isinstance(formal_root, str)
            or calibration_root == formal_root
            or calibration_root.startswith(formal_root.rstrip("/") + "/")
            or formal_root.startswith(calibration_root.rstrip("/") + "/")):
        raise ValueError("calibration and formal output artifact namespaces must be distinct")
    if Path(result_root).resolve() != (ROOT / formal_root).resolve():
        raise ValueError("formal result files are outside their immutable registered namespace")

    terminal_path = Path(runner_result_path)
    manifest_audit = verify_output_manifest(result_root, terminal_path)
    runner_result = json.loads(terminal_path.read_text())
    formal_runner_source = criteria["source_inputs"].get("formal_kernel_base_runner", {})
    actual = runner_result.get("states")
    if (runner_result.get("criteria_sha256") != criteria_sha
            or runner_result.get("source_commit") != criteria.get("source_commit")
            or not isinstance(formal_runner_source, dict)
            or runner_result.get("runner_sha256") != formal_runner_source.get("sha256")
            or runner_result.get("all_states_completed") is not True
            or runner_result.get("status_counts") != {"COMPLETED": FRESH_QUALIFICATION_RUNS}
            or not isinstance(actual, dict) or set(actual) != set(run_ids)):
        raise ValueError("terminal runner result is incomplete or not bound to formal criteria/source")

    expected_runtime = criteria["observed_calibration_runtime_identity"]
    runtime_fields = ("julia_version", "waterlily_version", "cuda_jl_version", "gpu_name", "gpu_uuid")
    output_root = Path(result_root).resolve()
    case = criteria["case"]
    force_scale = float(case["density_kg_m3"]) * float(case["freestream_mps"][0]) ** 2 * float(case["flow_spacing_m"]) ** 2
    state_map = {row["name"]: row for row in states}
    force_n: dict[str, dict[str, float]] = {}
    raw_artifacts: dict[str, dict[str, object]] = {}
    observed_runtimes = {}
    for run_id in run_ids:
        state = state_map[run_id]
        state_result = actual[run_id]
        if state_result.get("status") != "COMPLETED" or not all(state_result.get("gates", {}).values()):
            raise ValueError(f"formal solver state failed a registered gate: {run_id}")
        state_dir = (output_root / "states" / run_id).resolve()
        if output_root not in state_dir.parents:
            raise ValueError(f"unsafe formal state path: {run_id}")
        summary_path = state_dir / "flow_24.summary.json"
        csv_path = state_dir / "flow_24.forces.csv"
        if not summary_path.is_file():
            raise ValueError(f"formal per-state summary is missing: {run_id}")
        summary = json.loads(summary_path.read_text())
        history = recompute_force_history(csv_path, force_scale_n_per_solver_force=force_scale)
        if (history["sha256"] != state_result.get("force_csv_sha256")
                or summary.get("force_csv_sha256") != history["sha256"]
                or summary.get("state_sha256") != state["state_sha256"]
                or summary.get("phi_fortran_sha256") != state["phi_fortran_sha256"]
                or history["window_t_u_l"] != list(WINDOW_TU_L)):
            raise ValueError(f"formal raw force/state integrity mismatch: {run_id}")
        runtime = {
            "julia_version": summary.get("julia_version"),
            "waterlily_version": summary.get("waterlily_version"),
            "cuda_jl_version": summary.get("cuda_jl_version"),
            "gpu_name": summary.get("gpu_name"), "gpu_uuid": summary.get("gpu_uuid"),
            "driver_version": runner_result.get("host_driver_version_recorded_not_gated"),
        }
        for field in runtime_fields:
            if runtime[field] != expected_runtime.get(field):
                raise ValueError(f"formal runtime differs from calibration identity: {field}")
        observed_runtimes[run_id] = runtime
        force_n[run_id] = history["force_n"]
        raw_artifacts[run_id] = {
            "relative_path": csv_path.relative_to(output_root).as_posix(),
            "sha256": history["sha256"], "row_count": history["row_count"],
            "host_recomputed_force_n": history["force_n"],
        }
    if len({json.dumps(value, sort_keys=True) for value in observed_runtimes.values()}) != 1:
        raise ValueError("formal states do not share one observed runtime identity")

    baseline_ids = [row["name"] for row in states if row["role"] == "baseline"]
    baseline = {
        response: float(np.median([force_n[run_id][response] for run_id in baseline_ids]))
        for response in ("drag", "downforce")
    }
    pair_observations = {
        direction: {response: [] for response in ("drag", "downforce")}
        for direction in criteria["direction_inventory"]
    }
    for direction in criteria["direction_inventory"]:
        for epsilon in criteria["formal_epsilon_ladder_m"]:
            signs = {
                int(row["sign"]): row["name"] for row in states
                if row.get("role") == "perturbation" and row.get("direction_id") == direction
                and float(row.get("epsilon_m")) == float(epsilon)
            }
            if set(signs) != {-1, 1}:
                raise ValueError(f"formal signed pair is incomplete: {direction} {epsilon}")
            for response in ("drag", "downforce"):
                pair = centered_pair(force_n[signs[1]][response], force_n[signs[-1]][response], float(epsilon))
                pair_observations[direction][response].append({
                    "epsilon_m": float(epsilon), "response_plus_n": force_n[signs[1]][response],
                    "response_minus_n": force_n[signs[-1]][response], **pair,
                })
    combinations = {
        f"{direction}/{response}": evaluate_formal_direction_response(
            pair_observations[direction][response],
            response_floor_n=float(criteria["response_resolution_floor_n"][response]),
        )
        for direction in criteria["direction_inventory"]
        for response in ("drag", "downforce")
    }
    aggregate = aggregate_formal_verdict(combinations)
    return {
        "kind": "fd08_candidate_c_formal_host_verification",
        "evidence_class": "host_recomputed_formal_directional_fd_verdict",
        "criteria_path": Path(criteria_path).as_posix(), "criteria_sha256": criteria_sha,
        "runner_result_path": terminal_path.as_posix(), "runner_result_sha256": sha256(terminal_path),
        "registered_dataset_audit": dataset_audit,
        "runner_output_manifest": manifest_audit,
        "source_commit": criteria["source_commit"], "formal_run_ids": run_ids,
        "verified_source_input_count": len(verified_sources),
        "formal_verifier_sha256": verified_sources.get("formal_verifier"),
        "calibration_run_ids": cal_ids, "run_id_overlap": [],
        "raw_force_history_inventory": raw_artifacts,
        "force_window_t_u_l": list(WINDOW_TU_L), "force_scale_n_per_solver_force": force_scale,
        "formal_baseline_median_n": baseline,
        "response_resolution_floor_n": criteria["response_resolution_floor_n"],
        "observed_runtime_identity": next(iter(observed_runtimes.values())),
        "direction_response_verdicts": combinations,
        "verdict": aggregate["verdict"], "pass_count": aggregate["pass_count"],
        "fail_count": aggregate["fail_count"], "unresolved_count": aggregate["unresolved_count"],
        "qualification_flags": aggregate["qualification_flags"],
        "fd08_verdict_passed": aggregate["verdict"] == "PASS",
        "formal_qualification": False,
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
    result = verify(args.criteria, args.runner_result, args.result_root, args.dataset)
    digest = _write_once(args.output, result)
    print(json.dumps({"result_path": args.output.as_posix(), "result_sha256": digest,
                      "verdict": result["verdict"], "qualification_flags": result["qualification_flags"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
