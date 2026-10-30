#!/usr/bin/env python3
"""Run the preregistered, diagnostic-only W3 owner-lifetime horizon matrix."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

OUT = Path("/kaggle/working/w3_owner_full_horizon")
INPUT_ROOT = Path("/kaggle/input")
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
ARMS = ("A-natural", "A-forced", "B-natural-1", "B-natural-2", "B-forced-1", "B-forced-2")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def bounded_timeout_seconds(started_at: float, kernel_limit: int,
                            operation_limit: int, *, now: float | None = None) -> int:
    elapsed = (time.monotonic() if now is None else now) - started_at
    remaining = kernel_limit - elapsed
    if remaining < 1:
        raise TimeoutError("registered kernel runtime budget is exhausted")
    return min(operation_limit, int(remaining))


def write_json(path: Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def unique_input(filename: str) -> tuple[Path, Path]:
    matches = sorted(path for path in INPUT_ROOT.rglob(filename) if path.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {filename}, found {len(matches)}")
    return matches[0].parent, matches[0]


def validate_dataset_file(directory: Path, filename: str, expected_sha: str) -> Path:
    path = directory / filename
    if not path.is_file() or sha256(path) != expected_sha:
        raise RuntimeError(f"input hash mismatch: {filename}")
    return path


def load_inputs() -> tuple[dict, Path, Path, dict, dict]:
    inventory = {
        "input_root_exists": INPUT_ROOT.is_dir(),
        "top_level_entries": sorted(
            f"{'dir' if path.is_dir() else 'file'}:{path.name}"
            for path in INPUT_ROOT.iterdir()) if INPUT_ROOT.is_dir() else [],
        "criteria_files": sorted(path.name for path in INPUT_ROOT.rglob("w3_owner_full_horizon_criteria.json")),
        "w3_criteria_files": sorted(path.name for path in INPUT_ROOT.rglob("w3_v16_criteria.json")),
        "type_probe_result_files": sorted(path.name for path in INPUT_ROOT.rglob("w3_owner_type_probe_result.json")),
    }
    write_json(OUT / "input_mount_inventory.json", inventory)
    criteria_dir, criteria_path = unique_input("w3_owner_full_horizon_criteria.json")
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    criteria_manifest_path = criteria_dir / "w3_owner_full_horizon_dataset_manifest.json"
    if not criteria_sidecar.is_file() or not criteria_manifest_path.is_file():
        raise RuntimeError("full-horizon criteria sidecar or dataset manifest missing")
    criteria_sha = sha256(criteria_path)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise RuntimeError("full-horizon criteria sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise RuntimeError("full-horizon criteria are not immutable preregistration")
    if criteria.get("evidence_type") != "diagnostic_only":
        raise RuntimeError("full-horizon criteria evidence class mismatch")
    criteria_manifest = json.loads(criteria_manifest_path.read_text())
    criteria_files = criteria_manifest.get("files", {})
    expected_dataset_files = {
        "w3_owner_full_horizon_criteria.json": criteria_sha,
        "w3_owner_full_horizon_criteria.json.sha256": sha256(criteria_sidecar),
        "w3_owner_type_probe_result.json": criteria["type_probe_prerequisite"]["result_sha256"],
        "w3_owner_type_probe_result.json.sha256": criteria["type_probe_prerequisite"]["result_sidecar_sha256"],
        "w3_owner_type_probe_criteria.json": criteria["type_probe_prerequisite"]["criteria_sha256"],
        "w3_owner_type_probe_criteria.json.sha256": criteria["type_probe_prerequisite"]["criteria_sidecar_sha256"],
    }
    if criteria_manifest.get("dataset_id") != criteria["criteria_dataset_id"] or criteria_files != expected_dataset_files:
        raise RuntimeError("full-horizon criteria dataset manifest mismatch")
    for name, expected in expected_dataset_files.items():
        validate_dataset_file(criteria_dir, name, expected)
    type_result_path = criteria_dir / "w3_owner_type_probe_result.json"
    type_result = json.loads(type_result_path.read_text())
    type_result_sidecar = criteria_dir / "w3_owner_type_probe_result.json.sha256"
    type_criteria_path = criteria_dir / "w3_owner_type_probe_criteria.json"
    type_criteria_sidecar = criteria_dir / "w3_owner_type_probe_criteria.json.sha256"
    type_criteria = json.loads(type_criteria_path.read_text())
    prerequisite = criteria["type_probe_prerequisite"]
    if type_result_sidecar.read_text().strip() != prerequisite["result_sha256"]:
        raise RuntimeError("owner type result sidecar content mismatch")
    if type_criteria_sidecar.read_text().strip() != prerequisite["criteria_sha256"]:
        raise RuntimeError("owner type criteria sidecar content mismatch")
    if type_criteria.get("immutable") is not True or type_criteria.get("registered_before_computation") is not True:
        raise RuntimeError("owner type criteria are not immutable preregistration")
    if type_result.get("host_verification_passed") is not True:
        raise RuntimeError("owner type prerequisite is not host-verified")
    if type_result.get("exact_kernel_ref") != prerequisite["exact_kernel_ref"]:
        raise RuntimeError("owner type prerequisite kernel identity mismatch")
    if type_result.get("criteria_sha256") != prerequisite["criteria_sha256"]:
        raise RuntimeError("owner type prerequisite criteria mismatch")
    if type_criteria.get("criteria_id") != prerequisite["criteria_id"]:
        raise RuntimeError("owner type prerequisite criteria id mismatch")
    owner_type = type_result["runtime_type_identity"]
    if not all(owner_type.get(key) is True for key in (
            "cuda_device_memory_defined", "cuda_device_memory_is_parameter",
            "cuda_device_memory_is_module_binding")):
        raise RuntimeError("owner memory-type identity prerequisite is incomplete")
    if owner_type.get("memory_module", {}).get("package_version") != criteria["backend"]["cudacore_version"]:
        raise RuntimeError("CUDACore version mismatch")

    w3_dir, w3_criteria_path = unique_input("w3_v16_criteria.json")
    w3_sidecar = w3_criteria_path.with_suffix(w3_criteria_path.suffix + ".sha256")
    w3_manifest_path = w3_dir / "w3_v16_dataset_manifest.json"
    w3_manifest = json.loads(w3_manifest_path.read_text())
    if w3_manifest.get("dataset_id") != criteria["w3_input"]["dataset_id"]:
        raise RuntimeError("W3 input dataset id mismatch")
    if sha256(w3_manifest_path) != criteria["w3_input"]["dataset_manifest_sha256"]:
        raise RuntimeError("W3 input dataset manifest SHA mismatch")
    if sha256(w3_criteria_path) != criteria["w3_input"]["criteria_sha256"]:
        raise RuntimeError("W3 criteria SHA mismatch")
    if not w3_sidecar.is_file() or w3_sidecar.read_text().strip() != criteria["w3_input"]["criteria_sha256"]:
        raise RuntimeError("W3 criteria sidecar mismatch")
    w3_criteria = json.loads(w3_criteria_path.read_text())
    raw_rel = w3_criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    raw_phi = validate_dataset_file(w3_dir, raw_rel, criteria["w3_input"]["phi_fortran_sha256"])
    if w3_manifest.get("files", {}).get(raw_rel) != criteria["w3_input"]["phi_fortran_sha256"]:
        raise RuntimeError("W3 canonical raw phi is absent from the registered manifest")
    result = dict(criteria)
    result["_criteria_sha256"] = criteria_sha
    result["_criteria_sidecar_sha256"] = sha256(criteria_sidecar)
    result["_criteria_dataset_manifest_sha256"] = sha256(criteria_manifest_path)
    result["_type_probe_result_sha256"] = sha256(type_result_path)
    result["_type_probe_result_sidecar_sha256"] = sha256(criteria_dir / "w3_owner_type_probe_result.json.sha256")
    result["_type_probe_criteria_sha256"] = sha256(criteria_dir / "w3_owner_type_probe_criteria.json")
    result["_w3_criteria_sidecar_sha256"] = sha256(w3_sidecar)
    result["_w3_dataset_manifest_sha256"] = sha256(w3_manifest_path)
    return result, raw_phi, w3_manifest_path, inventory, type_result


def command(args: list[str], log_path: Path, *, env: dict[str, str] | None = None,
            timeout: int = 3600, check: bool = True) -> subprocess.CompletedProcess:
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, stdout=handle, stderr=subprocess.STDOUT,
                                env=env, timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return result


def gpu_inventory(criteria: dict) -> tuple[list[str], str]:
    rows = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"],
        text=True).splitlines()
    rows = [row.strip() for row in rows if row.strip()]
    expected = criteria["backend"]
    if len(rows) != expected["gpu_count"]:
        raise RuntimeError("T4 inventory count mismatch")
    if any(expected["gpu_name"] not in row or expected["driver_version"] not in row for row in rows):
        raise RuntimeError("T4 model or driver mismatch")
    uuids = [row.split(",")[2].strip() for row in rows]
    if len(set(uuids)) != len(rows):
        raise RuntimeError("GPU UUID inventory is not unique")
    (OUT / "nvidia_smi.csv").write_text("\n".join(rows) + "\n")
    return rows, uuids[0]


def install_julia(base: Path, *, started_at: float, kernel_limit: int) -> Path:
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    initial_timeout = bounded_timeout_seconds(started_at, kernel_limit, 60)
    with urllib.request.urlopen(JULIA_URL, timeout=initial_timeout) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            bounded_timeout_seconds(started_at, kernel_limit, 60)
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia archive SHA mismatch")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(base)], check=True,
                   timeout=bounded_timeout_seconds(started_at, kernel_limit, 600))
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("pinned Julia executable missing")
    return julia


def sha_tree(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256(path)
            for path in sorted(root.rglob("*")) if path.is_file()
            and path.name not in {"sha256.json", "DONE", "ERROR.txt"}}


def main() -> None:
    kernel_started_at = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    criteria, raw_phi, w3_manifest_path, inventory, type_result = load_inputs()
    kernel_limit = criteria["measurement"]["kernel_runtime_limit_s"]
    per_arm_limit = criteria["measurement"]["per_arm_runtime_limit_s"]
    runner_sha = sha256(Path(__file__))
    if criteria["source_files"]["runner"]["sha256"] != runner_sha:
        raise RuntimeError("kernel runner SHA differs from preregistration")
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    (OUT / "w3_input_dataset_manifest.json").write_bytes(w3_manifest_path.read_bytes())
    criteria_status = {
        "criteria_sha256": criteria["_criteria_sha256"],
        "criteria_sidecar_sha256": criteria["_criteria_sidecar_sha256"],
        "criteria_dataset_manifest_sha256": criteria["_criteria_dataset_manifest_sha256"],
        "w3_dataset_manifest_sha256": criteria["_w3_dataset_manifest_sha256"],
        "w3_criteria_sidecar_sha256": criteria["_w3_criteria_sidecar_sha256"],
        "type_probe_result_sha256": criteria["_type_probe_result_sha256"],
        "type_probe_result_sidecar_sha256": criteria["_type_probe_result_sidecar_sha256"],
    }
    arm_runs = []
    try:
        with tempfile.TemporaryDirectory(prefix="w3_owner_full_horizon_") as temporary:
            base = Path(temporary)
            source = base / "source"
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "fetch", "--depth", "64",
                            SOURCE_URL, SOURCE_REF], check=True,
                           timeout=bounded_timeout_seconds(kernel_started_at, kernel_limit, 900))
            commit = criteria["source_commit"]
            subprocess.run(["git", "-C", str(source), "checkout", "--detach", commit], check=True)
            actual_commit = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            if actual_commit != commit:
                raise RuntimeError("source commit mismatch")
            for entry in criteria["source_files"].values():
                path = source / entry["path"]
                if not path.is_file() or sha256(path) != entry["sha256"]:
                    raise RuntimeError(f"source file hash mismatch: {entry['path']}")
            project = source / "julia/CFDSDFWaterLilyT4"
            project_sha = sha256(project / "Project.toml")
            manifest_sha = sha256(project / "Manifest.toml")
            if project_sha != criteria["source_files"]["project"]["sha256"]:
                raise RuntimeError("Project.toml SHA mismatch")
            if manifest_sha != criteria["source_files"]["manifest"]["sha256"]:
                raise RuntimeError("Manifest.toml SHA mismatch")
            julia = install_julia(base, started_at=kernel_started_at, kernel_limit=kernel_limit)
            env = os.environ.copy()
            env.update({"JULIA_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "0",
                        "W3_OWNER_FULL_SELECTED_GPU_UUID": selected_uuid})
            command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                     "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env,
                    timeout=bounded_timeout_seconds(kernel_started_at, kernel_limit, 1800))
            if sha256(project / "Project.toml") != project_sha or sha256(project / "Manifest.toml") != manifest_sha:
                raise RuntimeError("Julia instantiate modified the pinned Project or Manifest")
            smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                             str(source / "scripts/w0b_t4_smoke.jl")],
                            OUT / "julia_smoke.log", env=env,
                            timeout=bounded_timeout_seconds(kernel_started_at, kernel_limit, 1200))
            smoke_text = Path(OUT / "julia_smoke.log").read_text(errors="replace")
            required = ("CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
                        "CUDA_DRIVER_VERSION 13.3.0", "CUDA_RUNTIME_VERSION 12.8.0",
                        "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
                        "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4", "NO_SOLVER_STEP")
            if any(marker not in smoke_text for marker in required):
                raise RuntimeError("registered T4 smoke identity mismatch")
            fingerprint = {
                "kernel_id": criteria["kernel_id"], "criteria": criteria_status,
                "criteria_id": criteria["criteria_id"],
                "criteria_dataset_id": criteria["criteria_dataset_id"],
                "w3_dataset_id": criteria["w3_input"]["dataset_id"],
                "source_commit": actual_commit, "source_files": criteria["source_files"],
                "runner_sha256": runner_sha, "gpu_inventory": gpu_rows,
                "selected_gpu_uuid": selected_uuid, "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
                "platform": platform.platform(), "python": platform.python_version(),
                "input_mount_inventory": inventory, "julia_archive_sha256": JULIA_SHA256,
                "cuda_smoke_sha256": sha256(OUT / "julia_smoke.log"),
                "owner_type_prerequisite": {
                    "exact_kernel_ref": type_result["exact_kernel_ref"],
                    "criteria_sha256": type_result["criteria_sha256"],
                    "result_sha256": criteria["type_probe_prerequisite"]["result_sha256"],
                    "runtime_type_identity": type_result["runtime_type_identity"],
                },
            }
            write_json(OUT / "fingerprint.json", fingerprint)
            job = source / criteria["source_files"]["job"]["path"]
            for arm in ARMS:
                arm_dir = OUT / "arms" / arm
                arm_dir.mkdir(parents=True, exist_ok=False)
                log = arm_dir / "julia_job.log"
                arm_started_at = time.monotonic()
                arm_timeout = bounded_timeout_seconds(kernel_started_at, kernel_limit, per_arm_limit)
                run = command([str(julia), "--startup-file=no", f"--project={project}",
                               str(job), str(raw_phi), str(arm_dir), arm],
                              log, env=env, timeout=arm_timeout, check=False)
                arm_elapsed = time.monotonic() - arm_started_at
                summary_path = arm_dir / "arm_summary.json"
                summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
                arm_runs.append({"arm_id": arm, "return_code": run.returncode,
                                 "summary_sha256": sha256(summary_path) if summary_path.is_file() else None,
                                 "status": summary.get("status") if summary else "missing_summary",
                                 "solver_steps": summary.get("solver_steps") if summary else None,
                                 "runtime_seconds": arm_elapsed,
                                 "registered_timeout_seconds": arm_timeout,
                                 "kernel_elapsed_seconds": time.monotonic() - kernel_started_at})
                write_json(arm_dir / "launch.json", arm_runs[-1])
                print("W3_OWNER_FULL_HORIZON_ARM_FINISHED", json.dumps(arm_runs[-1], sort_keys=True), flush=True)
            if time.monotonic() - kernel_started_at > kernel_limit:
                raise TimeoutError("registered kernel runtime limit was exceeded")
            write_json(OUT / "execution.json", {
                "completed": True, "diagnostic_only": True, "qualification": False,
                "arms_in_registered_order": list(ARMS), "arm_runs": arm_runs,
                "criteria_sha256": criteria_status["criteria_sha256"],
                "source_commit": actual_commit, "runner_sha256": runner_sha,
                "type_probe_result_sha256": criteria_status["type_probe_result_sha256"],
            })
    except Exception:
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        raise
    (OUT / "DONE").write_text("All preregistered arms were launched; diagnostic only; no qualification.\n")
    write_json(OUT / "sha256.json", sha_tree(OUT))
    print("W3_OWNER_FULL_HORIZON_DONE", json.dumps({
        "arms_attempted": len(arm_runs), "qualification": False,
        "criteria_sha256": criteria_status["criteria_sha256"]}, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        if not (OUT / "ERROR.txt").exists():
            (OUT / "ERROR.txt").write_text(traceback.format_exc())
        write_json(OUT / "sha256.json", sha_tree(OUT))
        raise
