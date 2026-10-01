#!/usr/bin/env python3
"""Run the registered FD job on CPU to immediately before its first sim_step!."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_normalfloor_criteria_2026_09.json"
DEFAULT_DATASET = ROOT / "work/kaggle_sdf_directional_fd_v17_nfloor_remote_v1_2026_09"
DEFAULT_OUTPUT = ROOT / "work/infra01_preflight/normalfloor_local_preview"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_runner(runner_path: Path):
    spec = importlib.util.spec_from_file_location("fd_cpu_preflight_runner", runner_path)
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


def check_metadata(metadata: dict, dataset_id: str) -> dict:
    kernel_id = metadata.get("id", "")
    title = metadata.get("title", "")
    if not isinstance(title, str):
        raise ValueError("Kaggle kernel slug or dataset binding is invalid")
    owner, separator, slug = kernel_id.partition("/")
    title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if (not separator or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", owner)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 40
            or slug != title_slug or metadata.get("dataset_sources") != [dataset_id]):
        raise ValueError("Kaggle kernel slug or dataset binding is invalid")
    return {"kernel_id": kernel_id, "slug_length": len(slug),
        "dataset_sources": metadata["dataset_sources"]}


def check_queue_output_separation(queue_path: Path, output_dir: Path) -> None:
    if Path(queue_path).resolve() == (Path(output_dir) / "run_queue.tsv").resolve():
        raise ValueError("incoming run queue must not be the Julia output snapshot")


def check_summary_schema(runner_path: Path, job_path: Path) -> dict:
    tree = ast.parse(runner_path.read_text())
    runner_keys = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "run_summary_contract", "close_summary", "verify_runner"}:
            for item in ast.walk(node):
                if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute):
                    if (isinstance(item.func.value, ast.Name) and item.func.value.id == "summary"
                            and item.func.attr == "get" and item.args and isinstance(item.args[0], ast.Constant)):
                        runner_keys.add(item.args[0].value)
                elif (isinstance(item, ast.Subscript) and isinstance(item.value, ast.Name)
                        and item.value.id == "summary" and isinstance(item.slice, ast.Constant)):
                    runner_keys.add(item.slice.value)
    job_text = job_path.read_text()
    start = job_text.index("summary = (")
    end = job_text.index("\n        )", start)
    job_keys = set(re.findall(r"\b([A-Za-z_]\w*)\s*=", job_text[start:end]))
    missing = sorted(runner_keys - job_keys)
    if missing:
        raise ValueError(f"Python verifier expects summary fields absent from Julia job: {missing}")
    return {"python_required_keys": sorted(runner_keys), "julia_keys": sorted(job_keys),
        "missing_from_julia": missing}


def run_preflight(criteria_path: Path, dataset_dir: Path, source_root: Path,
                  julia: Path, output_dir: Path, preview_current_source: bool = False,
                  state_path: Path | None = None) -> dict:
    criteria_path, dataset_dir, source_root, output_dir = map(
        Path, (criteria_path, dataset_dir, source_root, output_dir))
    output_dir = output_dir.resolve()
    evidence_path = output_dir / "preflight_evidence.json"
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not sidecar.is_file() or sidecar.read_text().strip() != sha256(criteria_path):
        raise ValueError("immutable FD criteria/sidecar is missing or mismatched")
    criteria = json.loads(criteria_path.read_text())
    if (not str(criteria.get("criteria_id", "")).startswith("sdf_directional_fd_v17_flow24")
            or criteria.get("immutable") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False):
        raise ValueError("CPU preflight requires the immutable registered v17 flow24 criteria")
    if output_dir.exists():
        raise FileExistsError(f"append-only CPU-prestep output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    branch = subprocess.check_output(["git", "-C", str(source_root), "branch", "--show-current"], text=True).strip()
    commit = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    worktree_status = subprocess.check_output(
        ["git", "-C", str(source_root), "status", "--porcelain"], text=True).strip()
    if not preview_current_source and (
            branch != "codex/kaggle-batch-migration" or commit != criteria["source_commit"] or worktree_status):
        raise ValueError("formal CPU preflight requires the clean registered integration source commit")

    runner = load_runner(source_root / criteria["inputs"]["kernel_runner"]["path"])
    runner.configure_criteria(criteria)
    _, criteria_sha = runner.read_criteria(dataset_dir)
    dataset_manifest, input_hashes = runner.verify_dataset(criteria, criteria_sha, dataset_dir)
    source_mismatches = []
    for name, item in criteria["inputs"].items():
        if item.get("location") != "source_repo":
            continue
        path = source_root / item["path"]
        observed = sha256(path) if path.is_file() else None
        if observed != item["sha256"]:
            source_mismatches.append({"name": name, "path": item["path"],
                "expected_sha256": item["sha256"], "observed_sha256": observed})
    if source_mismatches and not preview_current_source:
        raise RuntimeError(f"registered FD source SHA mismatches: {source_mismatches}")
    backend, w4_result = runner.verify_prerequisites(source_root, criteria)
    metadata_path = source_root / criteria["inputs"]["kernel_metadata"]["path"]
    metadata_identity = check_metadata(json.loads(metadata_path.read_text()), criteria["input_dataset_id"])
    summary_schema = check_summary_schema(
        source_root / criteria["inputs"]["kernel_runner"]["path"],
        source_root / criteria["inputs"]["julia_job"]["path"])
    state, directions, direction_audit, perturbations, state_identity = runner.host_input_preflight(
        source_root, dataset_dir, criteria)
    state_path = state_path or (dataset_dir / criteria["inputs"]["canonical_state_npz"]["path"])
    if sha256(state_path) != criteria["inputs"]["canonical_state_npz"]["sha256"]:
        raise ValueError("explicit v17 state path is not the dataset-bound canonical state")

    cpu_project = source_root / criteria["inputs"]["cpu_project"]["path"]
    cpu_manifest = source_root / criteria["inputs"]["cpu_manifest"]["path"]
    expected_project_sha = criteria["inputs"]["cpu_project"]["sha256"]
    expected_manifest_sha = criteria["inputs"]["cpu_manifest"]["sha256"]
    if sha256(cpu_project) != expected_project_sha or sha256(cpu_manifest) != expected_manifest_sha:
        raise ValueError("local CPU Julia project or manifest differs from registered source hashes")

    scratch_project = output_dir / "scratch_julia_project"
    shutil.copytree(cpu_project.parent, scratch_project)
    output_job = output_dir / "job_output"
    with tempfile.TemporaryDirectory(prefix="fd17_cpu_prestep_queue_") as temp_text:
        temp = Path(temp_text)
        queue_path = runner.write_run_queue(temp, dataset_dir, criteria)
        queue_identity = check_run_queue(queue_path, criteria, dataset_dir)
        incoming_queue = output_dir / "incoming_run_queue.tsv"
        shutil.copyfile(queue_path, incoming_queue)
        check_queue_output_separation(queue_path, output_job)
        environment = os.environ.copy()
        environment.update(runner.julia_job_environment(criteria, cpu_preflight=True))
        environment["JULIA_NUM_THREADS"] = "1"
        environment.pop("CUDA_VISIBLE_DEVICES", None)
        instantiate = subprocess.run([str(julia), "--startup-file=no", f"--project={scratch_project}",
            "-e", "using Pkg; Pkg.instantiate()"], cwd=source_root, env=environment,
            capture_output=True, text=True, check=False)
        (output_dir / "julia_instantiate.log").write_text(instantiate.stdout + instantiate.stderr)
        if instantiate.returncode != 0:
            raise RuntimeError("CPU Julia project initialization failed:\n" + instantiate.stdout + instantiate.stderr)
        if sha256(cpu_project) != expected_project_sha or sha256(cpu_manifest) != expected_manifest_sha:
            raise ValueError("CPU Julia instantiate changed the registered project/manifest")
        job = source_root / criteria["inputs"]["julia_job"]["path"]
        result = subprocess.run([str(julia), "--startup-file=no", f"--project={scratch_project}",
            str(job), str(dataset_dir), str(queue_path), str(output_job)], cwd=source_root,
            env=environment, capture_output=True, text=True, check=False)
        log = result.stdout + result.stderr
        (output_dir / "julia_job.log").write_text(log)
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
        if "normal_floor" in criteria["geometry"]:
            required_markers += (f"normal_floor={float(criteria['geometry']['normal_floor'])}",)
        missing = [marker for marker in required_markers if marker not in log]
        if missing or "FD_SOLVER_STEP_INVOKED" in log or "FD_SOLVER_STEP_RETURNED" in log:
            raise ValueError(f"CPU prestep boundary/identity mismatch; missing={missing}; log:\n{log[-16000:]}")
        if (not (output_job / "run_queue.tsv").is_file()
                or (output_job / "run_queue.tsv").read_bytes() != queue_path.read_bytes()):
            raise ValueError("Julia job did not snapshot the exact registered run queue")
        julia_version = subprocess.check_output([str(julia), "--version"], text=True).strip()
        evidence = {
            "schema_version": 1,
            "kind": f"{criteria['criteria_id']}_local_cpu_prestep",
            "evidence_class": "local_preview_not_formal_registration" if preview_current_source else "formal_preflight",
            "preview_only": preview_current_source,
            "criteria_path": str(criteria_path),
            "criteria_sha256": criteria_sha,
            "source_commit": commit,
            "source_branch": branch,
            "source_worktree_status": worktree_status,
            "source_inputs_match_registered_sha": not source_mismatches,
            "source_input_sha_mismatches": source_mismatches,
            "registered_preflight_script_sha256": criteria["inputs"].get("cpu_preflight", {}).get("sha256"),
            "current_preflight_script_sha256": sha256(source_root / "scripts/preflight_kaggle_sdf_directional_fd_v16_cpu.py"),
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
            "kernel_metadata_identity": metadata_identity,
            "summary_schema_compatibility": summary_schema,
            "run_queue": queue_identity,
            "prerequisites": {"w3_result_sha256": criteria["prerequisites"]["w3"]["result_sha256"],
                "w4_result_sha256": criteria["prerequisites"]["w4"]["result_sha256"],
                "w4_case": runner.w4_force_metrics(
                    w4_result, criteria["geometry"]["flow_case"]["case_id"])},
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
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(evidence_path)
    evidence_path.with_suffix(evidence_path.suffix + ".sha256").write_text(digest + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--julia", type=Path, default=Path(shutil.which("julia") or "julia"))
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preview-current-source", action="store_true")
    args = parser.parse_args()
    result = run_preflight(args.criteria.resolve(), args.dataset.resolve(), args.source_root.resolve(),
        args.julia.resolve(), args.output_dir.resolve(), args.preview_current_source,
        args.state.resolve() if args.state else None)
    print(json.dumps({"prestep_passed": result["prestep_passed"],
        "source_commit": result["source_commit"], "criteria_sha256": result["criteria_sha256"],
        "run_count_checked": result["run_queue"]["row_count"],
        "solver_step_invoked": result["solver_step_invoked"],
        "evidence_class": result["evidence_class"],
        "evidence_path": str(args.output_dir.resolve() / "preflight_evidence.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
