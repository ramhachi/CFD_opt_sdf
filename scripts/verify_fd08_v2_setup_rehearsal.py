#!/usr/bin/env python3
"""Verify the bounded one-step T4 setup rehearsal and prove it is not science."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_fd08_v2_r6 import verify_registered_dataset


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path, default=Path(
        "docs/evidence/fd08_v2_r6_2026_10_06/setup_rehearsal_criteria.json"))
    parser.add_argument("--dataset-dir", type=Path, default=Path("work/kaggle_fd08_v2_setup_dataset"))
    parser.add_argument("--kernel-version", type=int, required=True)
    parser.add_argument("--evidence", type=Path, default=Path(
        "docs/evidence/fd08_v2_r6_2026_10_06/setup_rehearsal_result.json"))
    args = parser.parse_args()
    criteria_sha = sha(args.criteria)
    sidecar = args.criteria.with_suffix(args.criteria.suffix + ".sha256")
    if sidecar.read_text().strip() != criteria_sha:
        raise ValueError("setup criteria sidecar mismatch")
    criteria = json.loads(args.criteria.read_text())
    if criteria.get("kind") != "fd08_v2_setup_rehearsal" or len(criteria["state_inventory"]) != 2:
        raise ValueError("not the frozen two-state setup-only rehearsal")
    for name, entry in criteria["source_inputs"].items():
        source_path = ROOT / entry["path"]
        if not source_path.is_file() or sha(source_path) != entry["sha256"]:
            raise ValueError(f"setup registered source SHA mismatch: {name}")
    dataset_manifest_sha = verify_registered_dataset(args.dataset_dir, criteria, criteria_sha)
    budget_path = args.dataset_dir / "kaggle_budget_preflight.json"
    budget = json.loads(budget_path.read_text())
    if (sha(budget_path) != criteria["budget_feasibility"]["evidence_sha256"]
            or budget.get("phase") != "setup"
            or budget.get("status") != "PASS_CAPABILITY_PREFLIGHT"):
        raise ValueError("setup terminal is not bound to its passing Kaggle budget preflight")
    markers = sorted(args.download.rglob("DONE"))
    if len(markers) != 1:
        raise ValueError("setup output must contain one terminal marker")
    output = markers[0].parent
    manifest_path = output / "sha256.json"
    manifest = json.loads(manifest_path.read_text())
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*")
              if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    if actual != set(manifest):
        raise ValueError("setup output manifest file inventory mismatch")
    for name, expected in manifest.items():
        if sha(output / name) != expected:
            raise ValueError(f"setup output hash mismatch: {name}")
    result = json.loads((output / "result.json").read_text())
    done = json.loads((output / "DONE").read_text())
    if (result.get("kind") != "fd08_v2_setup_rehearsal"
            or result.get("evidence_class") != "setup_only_not_r6_or_formal_science"
            or result.get("status") != "SETUP_ONLY_COMPLETE"
            or result.get("criteria_sha256") != criteria_sha
            or result.get("source_commit") != criteria["source_commit"]
            or result.get("kernel_id") != criteria["kernel_id"]
            or result.get("dataset_id") != criteria["input_dataset_id"]
            or result.get("runner_sha256") != criteria["source_inputs"]["kernel_runner"]["sha256"]
            or result.get("dataset_manifest_sha256") != dataset_manifest_sha
            or done.get("status") != "SETUP_ONLY_COMPLETE"
            or done.get("criteria_sha256") != criteria_sha
            or done.get("source_commit") != criteria["source_commit"]
            or done.get("file_count") != len(manifest)):
        raise ValueError("setup terminal identity/status mismatch")
    if result.get("state_count") != 2 or len(result.get("states", [])) != 2:
        raise ValueError("setup state count mismatch")
    state_root = output / "states"
    expected_names = {row["name"] for row in criteria["state_inventory"]}
    children = list(state_root.iterdir()) if state_root.is_dir() else []
    if (not state_root.is_dir() or not all(path.is_dir() for path in children)
            or {path.name for path in children} != expected_names):
        raise ValueError("setup output contains missing or unexpected state directories")
    if {row.get("state_name") for row in result["states"]} != expected_names:
        raise ValueError("setup result state inventory differs from preregistration")
    runtime = criteria["runtime"]
    gpu_inventory = result.get("gpu_inventory", [])
    if (len(gpu_inventory) != runtime["gpu_count"]
            or any(runtime["gpu_name"] not in row for row in gpu_inventory)):
        raise ValueError("setup T4 GPU inventory mismatch")
    smoke_path = output / "julia_smoke.log"
    if not smoke_path.is_file() or sha(smoke_path) != result.get("runtime_smoke_sha256"):
        raise ValueError("setup runtime smoke log is missing or hash-mismatched")
    smoke = smoke_path.read_text(errors="replace")
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
    if not all(marker in smoke for marker in expected_markers):
        raise ValueError("setup runtime smoke identity mismatch")
    if any(path.name.endswith(".forces.csv") for path in output.rglob("*")):
        raise ValueError("setup-only rehearsal emitted force response data")
    for row, state_result in zip(criteria["state_inventory"], result["states"], strict=True):
        setup = state_result.get("setup", {})
        if (state_result.get("status") != "SETUP_ONLY_COMPLETE"
                or setup.get("evidence_class") != "setup_only_not_calibration"
                or setup.get("state_sha256") != row["state_sha256"]
                or setup.get("phi_fortran_sha256") != row["phi_fortran_order_sha256"]
                or setup.get("device_roundtrip_sha256") != row["phi_fortran_order_sha256"]
                or setup.get("finite_u") is not True or setup.get("finite_p") is not True):
            raise ValueError(f"setup state failed for {row['name']}")
    evidence = {
        "kind": "fd08_v2_setup_rehearsal_verified",
        "status": "PASS_SETUP_ONLY",
        "evidence_class": "not_calibration_or_formal_science",
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "dataset_manifest_sha256": dataset_manifest_sha,
        "budget_preflight_sha256": sha(budget_path),
        "verified_source_inputs": {name: entry["sha256"] for name, entry in criteria["source_inputs"].items()},
        "verifier_source_sha256": sha(Path(__file__)),
        "kernel_version": args.kernel_version,
        "output_manifest_sha256": sha(manifest_path),
        "output_file_count": len(manifest),
        "state_count": 2,
        "force_history_present": False,
        "result_sha256": sha(output / "result.json"),
    }
    if args.evidence.exists():
        raise FileExistsError(f"refusing to overwrite setup evidence: {args.evidence}")
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n")
    args.evidence.with_suffix(args.evidence.suffix + ".sha256").write_text(sha(args.evidence) + "\n")
    print(json.dumps(evidence, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
