#!/usr/bin/env python3
"""Run the registered FD job on CPU to immediately before its first sim_step!."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_criteria_2026_09.json"
DEFAULT_DATASET = ROOT / "work/kaggle_sdf_directional_fd_v17_flow24_2026_09"
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
DEFAULT_EVIDENCE = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_cpu_prestep_2026_09.json"
RUNNER_PATH = ROOT / "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("fd_cpu_preflight_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the criteria-bound FD runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_run_queue(queue_path: Path, criteria: dict, dataset_dir: Path) -> dict:
    rows = [line.split("\t") for line in queue_path.read_text().splitlines() if line]
    if len(rows) != 33 or any(len(row) != 7 for row in rows):
        raise ValueError("generated Julia run queue does not have the exact 33x7 schema")
    if [row[0] for row in rows] != criteria["run_order"]:
        raise ValueError("generated Julia run queue order differs from immutable criteria")
    for row in rows:
        path = Path(row[1])
        if not path.is_file() or sha256(path) != row[2]:
            raise ValueError(f"Julia queue input file/hash mismatch: {row[0]}")
    return {"path": queue_path.name, "sha256": sha256(queue_path),
        "row_count": len(rows), "first_run": rows[0][0], "last_run": rows[-1][0]}


def run_preflight(criteria_path: Path, dataset_dir: Path, state_path: Path,
                  julia: Path, evidence_path: Path) -> dict:
    criteria_path, dataset_dir, state_path = map(Path, (criteria_path, dataset_dir, state_path))
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not sidecar.is_file() or sidecar.read_text().strip() != sha256(criteria_path):
        raise ValueError("immutable FD-05 criteria/sidecar is missing or mismatched")
    criteria = json.loads(criteria_path.read_text())
    if (criteria.get("criteria_id") != "sdf_directional_fd_v17_flow24_2026_09"
            or criteria.get("immutable") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False):
        raise ValueError("CPU preflight requires the immutable registered v17 flow24 criteria")
    if evidence_path.exists() or evidence_path.with_suffix(evidence_path.suffix + ".sha256").exists():
        raise FileExistsError(f"append-only CPU-prestep evidence target already exists: {evidence_path}")
    branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    tracked_status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    if branch != "codex/kaggle-batch-migration" or commit != criteria["source_commit"] or tracked_status:
        raise ValueError("CPU preflight must use the clean registered source commit worktree")

    runner = load_runner()
    runner.configure_criteria(criteria)
    _, criteria_sha = runner.read_criteria(dataset_dir)
    dataset_manifest, input_hashes = runner.verify_dataset(criteria, criteria_sha, dataset_dir)
    runner.verify_source(ROOT, criteria)
    backend, w4_result = runner.verify_prerequisites(ROOT, criteria)
    state, directions, direction_audit, perturbations, state_identity = runner.host_input_preflight(
        ROOT, dataset_dir, criteria)
    if sha256(state_path) != criteria["inputs"]["canonical_state_npz"]["sha256"]:
        raise ValueError("explicit v17 state path is not the dataset-bound canonical state")

    cpu_project = ROOT / criteria["inputs"]["cpu_project"]["path"]
    cpu_manifest = ROOT / criteria["inputs"]["cpu_manifest"]["path"]
    expected_project_sha = criteria["inputs"]["cpu_project"]["sha256"]
    expected_manifest_sha = criteria["inputs"]["cpu_manifest"]["sha256"]
    if sha256(cpu_project) != expected_project_sha or sha256(cpu_manifest) != expected_manifest_sha:
        raise ValueError("local CPU Julia project or manifest differs from registered source hashes")

    with tempfile.TemporaryDirectory(prefix="fd05_cpu_prestep_") as temp_text:
        temp = Path(temp_text)
        queue_path = runner.write_run_queue(temp, dataset_dir, criteria)
        queue_identity = check_run_queue(queue_path, criteria, dataset_dir)
        output_dir = temp / "job_output"
        environment = os.environ.copy()
        environment.update(runner.julia_job_environment(criteria, cpu_preflight=True))
        environment["JULIA_NUM_THREADS"] = "1"
        environment.pop("CUDA_VISIBLE_DEVICES", None)
        instantiate = subprocess.run([str(julia), "--startup-file=no", f"--project={cpu_project}",
            "-e", "using Pkg; Pkg.instantiate()"], cwd=ROOT, env=environment,
            capture_output=True, text=True, check=False)
        if instantiate.returncode != 0:
            raise RuntimeError("CPU Julia project initialization failed:\n" + instantiate.stdout + instantiate.stderr)
        if sha256(cpu_project) != expected_project_sha or sha256(cpu_manifest) != expected_manifest_sha:
            raise ValueError("CPU Julia instantiate changed the registered project/manifest")
        job = ROOT / criteria["inputs"]["julia_job"]["path"]
        result = subprocess.run([str(julia), "--startup-file=no", f"--project={cpu_project}",
            str(job), str(dataset_dir), str(queue_path), str(output_dir)], cwd=ROOT,
            env=environment, capture_output=True, text=True, check=False)
        log = result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError("registered Julia CPU prestep failed:\n" + log[-16000:])
        required_markers = (
            "FD_PRESTEP_IDENTITY baseline_A",
            f"state={criteria['geometry']['canonical_state_sha256']}",
            f"phi_c={criteria['geometry']['canonical_phi_c_order_sha256']}",
            f"phi_f={criteria['geometry']['canonical_phi_fortran_sha256']}",
            "shape=121,65,49", "spacing_m=0.025", "flow=flow_24",
            "dims=150,72,54", "flow_origin_m=-2.5,-1.2,-0.9",
            "flow_spacing_m=0.03333333333333333",
            "FD_PRESTEP_READY baseline_A", "FD_PRESTEP_COMPLETE runs_validated=33 next=sim_step!",
        )
        missing = [marker for marker in required_markers if marker not in log]
        if missing or "FD_SOLVER_STEP_INVOKED" in log or "FD_SOLVER_STEP_RETURNED" in log:
            raise ValueError(f"CPU prestep boundary/identity mismatch; missing={missing}; log:\n{log[-16000:]}")
        if (not (output_dir / "run_queue.tsv").is_file()
                or (output_dir / "run_queue.tsv").read_bytes() != queue_path.read_bytes()):
            raise ValueError("Julia job did not snapshot the exact registered run queue")
        julia_version = subprocess.check_output([str(julia), "--version"], text=True).strip()
        evidence = {
            "schema_version": 1,
            "kind": "fd05_v17_flow24_local_cpu_prestep",
            "criteria_path": criteria_path.relative_to(ROOT).as_posix(),
            "criteria_sha256": criteria_sha,
            "source_commit": commit,
            "source_branch": branch,
            "dataset_id": criteria["input_dataset_id"],
            "dataset_manifest_sha256": runner.sha256(dataset_dir / criteria["artifacts"]["dataset_manifest_filename"]),
            "dataset_inventory_sha256": input_hashes,
            "state_identity": {"state_sha256": state.state_sha256,
                "state_npz_sha256": sha256(state_path),
                "phi_c_order_sha256": state_identity["canonical_phi_c_order_sha256"],
                "phi_fortran_sha256": state_identity["canonical_phi_fortran_sha256"],
                "point_shape": list(state.shape), "origin_m": list(state.origin_m),
                "spacing_m": state.spacing_m, "source_surface_sha256": state.source_sha256},
            "direction_identity": direction_audit,
            "perturbation_preflight_count": len(perturbations),
            "run_queue": queue_identity,
            "prerequisites": {"w3_result_sha256": criteria["prerequisites"]["w3"]["result_sha256"],
                "w4_result_sha256": criteria["prerequisites"]["w4"]["result_sha256"],
                "w4_case": w4_result["case_measurements"]["flow_24"]["force_metrics_host_recomputed"]},
            "julia_version": julia_version,
            "cpu_project_sha256": sha256(cpu_project),
            "cpu_manifest_sha256": sha256(cpu_manifest),
            "cpu_julia_initialization_stdout": (instantiate.stdout + instantiate.stderr)[-4000:],
            "registered_job_log": log,
            "job_return_code": result.returncode,
            "solver_step_invoked": False,
            "next_operation": "the exact registered job reached immediately before the first sim_step!",
            "prestep_passed": True,
        }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(evidence_path)
    evidence_path.with_suffix(evidence_path.suffix + ".sha256").write_text(digest + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--julia", type=Path, default=Path(shutil.which("julia") or "julia"))
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    result = run_preflight(args.criteria.resolve(), args.dataset.resolve(), args.state.resolve(),
        args.julia.resolve(), args.evidence.resolve())
    print(json.dumps({"prestep_passed": result["prestep_passed"],
        "source_commit": result["source_commit"], "criteria_sha256": result["criteria_sha256"],
        "run_count_checked": result["run_queue"]["row_count"],
        "solver_step_invoked": result["solver_step_invoked"],
        "evidence_path": str(args.evidence.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
