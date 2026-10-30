#!/usr/bin/env python3
"""Verify all R6 terminal artifacts before any numerical gate analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fd08_v2_campaign_io import recompute_force_n


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def locate_output(download: Path) -> Path:
    markers = sorted(download.rglob("DONE"))
    if len(markers) != 1:
        raise ValueError(f"expected exactly one terminal marker, found {len(markers)}")
    return markers[0].parent


def verify_output_manifest(output: Path) -> dict:
    manifest_path = output / "sha256.json"
    if not manifest_path.is_file() or not (output / "DONE").is_file():
        raise ValueError("terminal manifest or DONE marker missing")
    manifest = json.loads(manifest_path.read_text())
    expected = set(manifest)
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*")
              if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    if actual != expected:
        raise ValueError(f"terminal output inventory mismatch: {sorted(actual ^ expected)}")
    for name, digest in manifest.items():
        if sha(output / name) != digest:
            raise ValueError(f"terminal output SHA mismatch: {name}")
    return manifest


def verify_registered_dataset(dataset: Path, criteria: dict, criteria_sha: str) -> str:
    """Recheck the complete local input dataset against its immutable manifest."""
    sidecar = dataset / "criteria.json.sha256"
    require(sidecar.is_file() and sidecar.read_text().strip() == criteria_sha,
            "input dataset criteria SHA sidecar mismatch")
    required = dict(criteria.get("dataset_files", {}))
    required.update({
        "criteria.json": criteria_sha,
        "criteria.json.sha256": sha(sidecar),
    })
    manifest_path = dataset / "fd08_v2_dataset_manifest.json"
    require(manifest_path.is_file(), "registered input dataset manifest is missing")
    actual = {path.relative_to(dataset).as_posix() for path in dataset.rglob("*")
              if path.is_file() and path.name != "dataset-metadata.json"}
    expected = set(required) | {"fd08_v2_dataset_manifest.json"}
    require(actual == expected, f"registered dataset inventory mismatch: {sorted(actual ^ expected)}")
    for name, expected_sha in required.items():
        require(sha(dataset / name) == expected_sha, f"registered dataset SHA mismatch: {name}")
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get("criteria_sha256") == criteria_sha,
            "registered dataset manifest criteria SHA mismatch")
    require(manifest.get("files") == {name: sha(dataset / name) for name in sorted(required)},
            "registered dataset manifest file map mismatch")
    return sha(manifest_path)


def verify_registered_state_inventory(output: Path, criteria: dict, result: dict,
                                      done: dict, manifest: dict) -> None:
    rows = criteria["state_inventory"]
    expected_names = {row["name"] for row in rows}
    state_root = output / "states"
    require(state_root.is_dir(), "terminal state directory is missing")
    children = list(state_root.iterdir())
    require(all(path.is_dir() for path in children), "unexpected non-state entry under states/")
    actual_names = {path.name for path in children}
    require(actual_names == expected_names,
            f"terminal state directories mismatch: {sorted(actual_names ^ expected_names)}")
    states = result.get("states")
    require(isinstance(states, dict) and set(states) == expected_names,
            "terminal result state inventory differs from registered inventory")
    require(result.get("state_count") == len(rows)
            and result.get("expected_state_count") == len(rows),
            "terminal result state count mismatch")
    require(done.get("file_count") == len(manifest),
            "DONE file count differs from verified output manifest")
    for name, state in states.items():
        require(state.get("status") == "COMPLETE" and state.get("state_name") == name,
                f"terminal state result identity/status mismatch: {name}")
        require((state_root / name / "state_result.json").is_file(),
                f"terminal state result file missing: {name}")


def verify(args: argparse.Namespace) -> dict:
    criteria_path = args.criteria
    criteria_sha = sha(criteria_path)
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    require(sidecar.is_file() and sidecar.read_text().strip() == criteria_sha,
            "registered R6 criteria SHA-256 sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    round_kind = criteria.get("kind")
    require(round_kind in {"fd08_v2_r6_calibration", "fd08_v2_formal_validation"}
            and criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True
            and criteria.get("status") == "registered_not_run",
            "input is not an immutable unused FD-08 v2 preregistration")
    require(criteria.get("source_commit") and len(criteria["source_commit"]) == 40,
            "criteria source commit is missing")
    source_inputs = criteria.get("source_inputs", {})
    require(bool(source_inputs), "criteria source inventory is missing")
    for name, entry in source_inputs.items():
        source_path = ROOT / entry["path"]
        require(source_path.is_file() and sha(source_path) == entry["sha256"],
                f"registered source input SHA mismatch: {name}")

    output = locate_output(args.download)
    manifest = verify_output_manifest(output)
    result_path = output / "result.json"
    result = json.loads(result_path.read_text())
    done = json.loads((output / "DONE").read_text())
    require(result.get("kind") == round_kind and result.get("status") == "COMPLETE",
            "kernel result is not a complete registered-round terminal")
    require(done.get("status") == "COMPLETE" and done.get("criteria_sha256") == criteria_sha
            and done.get("source_commit") == criteria["source_commit"],
            "DONE marker does not bind the registered R6 criteria/source")
    dataset_manifest_sha = verify_registered_dataset(args.dataset_dir, criteria, criteria_sha)
    verify_registered_state_inventory(output, criteria, result, done, manifest)
    require(result.get("criteria_sha256") == criteria_sha
            and result.get("source_commit") == criteria["source_commit"]
            and result.get("kernel_id") == criteria["kernel_id"]
            and result.get("dataset_id") == criteria["input_dataset_id"],
            "terminal result criteria/source identity mismatch")
    require(result.get("runner_sha256") == criteria["source_inputs"]["kernel_runner"]["sha256"],
            "executed runner SHA differs from registered source")
    require(result.get("dataset_manifest_sha256") == dataset_manifest_sha,
            "terminal result dataset manifest identity mismatch")
    expected_count = int(criteria["expected_state_count"])
    require(expected_count == len(criteria["state_inventory"]),
            "criteria expected state count differs from registered inventory")
    require(not (output / "ERROR.json").exists() and not (output / "partial_result.json").exists(),
            "error or partial-result artifact is present")

    runtime = criteria["runtime"]
    require(len(result.get("gpu_inventory", [])) == runtime["gpu_count"], "T4 GPU inventory incomplete")
    gpu_rows = result["gpu_inventory"]
    require(all(runtime["gpu_name"] in row for row in gpu_rows), "T4 GPU model mismatch")
    require(result.get("host_driver_version_recorded_not_gated"), "host driver version was not recorded")
    smoke = (output / "julia_smoke.log").read_text(errors="replace")
    expected_markers = (
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
        f"GPU_COMPUTE_CAPABILITY {runtime['compute_capability']}",
        f"CUDA_DRIVER_VERSION {runtime['cuda_driver_api_version']}",
        f"CUDA_RUNTIME_VERSION {runtime['cuda_runtime_version']}",
        f"JULIA_VERSION {runtime['julia_version']}",
        f"CUDA_JL_VERSION {runtime['cuda_jl_version']}",
        f"WATERLILY_VERSION {runtime['waterlily_version']}",
        f"GPU_NAME {runtime['gpu_name']}", "NO_SOLVER_STEP",
    )
    require(all(marker in smoke for marker in expected_markers), "runtime smoke identity mismatch")

    # Only now, after the complete manifest, criteria and exact state inventory passed,
    # read solver summaries and force histories on the host.
    verified_states = []
    row_by_name = {row["name"]: row for row in criteria["state_inventory"]}
    measurements = criteria["measurement"]
    total_solver = 0.0
    for name in sorted(row_by_name):
        state_dir = output / "states" / name
        state_result_path = state_dir / "state_result.json"
        summary_path = state_dir / "flow_24.summary.json"
        csv_path = state_dir / "flow_24.forces.csv"
        require(state_result_path.is_file() and summary_path.is_file() and csv_path.is_file()
                and (state_dir / "W4_JOB_DONE").is_file(), f"{name}: terminal state artifacts missing")
        state_result = json.loads(state_result_path.read_text())
        summary = json.loads(summary_path.read_text())
        row = row_by_name[name]
        require(state_result.get("status") == "COMPLETE"
                and state_result.get("state_sha256") == row["state_sha256"]
                and state_result.get("phi_fortran_order_sha256") == row["phi_fortran_order_sha256"],
                f"{name}: state result identity mismatch")
        require(state_result.get("summary_sha256") == sha(summary_path)
                and state_result.get("force_csv_sha256") == sha(csv_path)
                and summary.get("force_csv_sha256") == sha(csv_path),
                f"{name}: raw history/summary hash mismatch")
        require(summary.get("state_sha256") == row["state_sha256"]
                and summary.get("state_npz_sha256") == row["npz_sha256"]
                and summary.get("phi_fortran_sha256") == row["phi_fortran_order_sha256"]
                and summary.get("phi_c_order_sha256") == row["phi_c_order_sha256"]
                and summary.get("device_roundtrip_sha256") == row["phi_fortran_order_sha256"],
                f"{name}: Julia summary state hash mismatch")
        require(all(summary.get(key) is True for key in ("finite_u", "finite_p", "finite_forces")),
                f"{name}: nonfinite terminal state")
        require(summary.get("t_end_reached", 0.0) >= measurements["time_window_t_u_l"][1],
                f"{name}: solver did not reach the end of the registered measurement window")
        for key, expected in (("julia_version", runtime["julia_version"]),
                              ("cuda_jl_version", runtime["cuda_jl_version"]),
                              ("waterlily_version", runtime["waterlily_version"]),
                              ("waterlily_backend", runtime["waterlily_backend"])):
            require(summary.get(key) == expected, f"{name}: runtime field mismatch {key}")
        require(runtime["gpu_name"] in summary.get("gpu_name", ""), f"{name}: runtime GPU name mismatch")
        recomputed = recompute_force_n(csv_path, criteria)
        for quantity in ("drag", "downforce"):
            expected_n = recomputed[f"{quantity}_n"]
            actual_n = summary[f"{quantity}_time_weighted_n"]
            require(math.isclose(expected_n, actual_n, rel_tol=1e-9, abs_tol=1e-10),
                    f"{name}: host raw-history reconstruction differs for {quantity}")
        total_solver += float(summary["wall_seconds"])
        verified_states.append({
            "name": name,
            "state_sha256": row["state_sha256"],
            "summary_sha256": sha(summary_path),
            "force_csv_sha256": sha(csv_path),
            "force_csv_path": csv_path.relative_to(output).as_posix(),
            "host_recomputed_physical_forces": recomputed,
            "solver_wall_seconds": summary["wall_seconds"],
            "t_end_reached": summary["t_end_reached"],
        })
    require(total_solver <= measurements["solver_wall_time_cap_s"], "aggregate solver cap exceeded")
    require(math.isclose(total_solver, result["aggregate_solver_wall_seconds"], rel_tol=1e-12, abs_tol=1e-9),
            "aggregate solver time does not match per-state summaries")
    require(result["elapsed_kernel_seconds"] <= measurements["kernel_execution_allowance_s"],
            "kernel overall execution allowance exceeded")
    verified = {
        "kind": "fd08_v2_r6_host_terminal_verification" if round_kind == "fd08_v2_r6_calibration"
                else "fd08_v2_formal_host_terminal_verification",
        "status": "PASS_TERMINAL_INTEGRITY",
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "verified_source_inputs": {name: entry["sha256"] for name, entry in source_inputs.items()},
        "verifier_source_sha256": sha(Path(__file__)),
        "analyzer_source_sha256": source_inputs[
            "r6_analyzer" if round_kind == "fd08_v2_r6_calibration" else "formal_analyzer"
        ]["sha256"],
        "download_output_manifest_sha256": sha(output / "sha256.json"),
        "download_manifest_file_count": len(manifest),
        "dataset_manifest_sha256": result["dataset_manifest_sha256"],
        "kernel_version": args.kernel_version,
        "state_count": len(verified_states),
        "expected_state_count": expected_count,
        "unexpected_state_count": 0,
        "aggregate_solver_wall_seconds": total_solver,
        "elapsed_kernel_seconds": result["elapsed_kernel_seconds"],
        "gpu_inventory": gpu_rows,
        "host_driver_version_recorded_not_gated": result["host_driver_version_recorded_not_gated"],
        "runtime_smoke_sha256": sha(output / "julia_smoke.log"),
        "states": verified_states,
        "analysis_performed": False,
    }
    if args.evidence:
        if args.evidence.exists():
            raise FileExistsError(f"refusing to overwrite terminal verification evidence: {args.evidence}")
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(verified, sort_keys=True, indent=2, allow_nan=False) + "\n")
        args.evidence.with_suffix(args.evidence.suffix + ".sha256").write_text(sha(args.evidence) + "\n")
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path, default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_criteria.json")
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "work/kaggle_fd08_v2_r6_dataset")
    parser.add_argument("--kernel-version", type=int, required=True)
    parser.add_argument("--evidence", type=Path,
                        default=ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/terminal_verification.json")
    result = verify(parser.parse_args())
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
