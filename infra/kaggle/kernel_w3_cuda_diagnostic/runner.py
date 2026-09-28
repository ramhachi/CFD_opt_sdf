#!/usr/bin/env python3
"""Run a private, one-step CPU/T4 diagnostic for the W3 v16 zero-force result."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import tempfile
import traceback
import urllib.request
from pathlib import Path

STAGE = "w3_v16_cuda_diagnostic"
OUT = Path("/kaggle/working") / STAGE
INPUT_ROOT = Path("/kaggle/input")
DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-genesis-state"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic"
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
SOURCE_FETCH_DEPTH = 32
# Pin the reviewed diagnostic source before submitting the private kernel.
DIAGNOSTIC_SOURCE_COMMIT = "885ae7558012da43e6310e2ffb04db4230150f5b"
DIAGNOSTIC_JOB_SHA256 = "4c080a72f48754c758ee999a38b7d7b83737dd01d2fe7573f4b164d7f0e1ce4e"
OWNER_LIFETIME_JOB_SHA256 = "7fa98a26105f1a2938ab85550931a22cb1020bd27d687d6f4dedb99c1b5572ea"
OWNER_LIFETIME_CRITERIA_PATH = "docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round2.json"
W3_CRITERIA_SHA256 = "f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2"
W3_SOURCE_COMMIT = "5e985fa3395a01228c18910d96e09ecbc5497628"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n")


def command(args: list[str], log_path: Path, *, env: dict[str, str] | None = None,
            timeout: int = 3600) -> str:
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def discover_dataset() -> tuple[Path, Path]:
    matches = sorted(path for path in INPUT_ROOT.rglob("w3_v16_criteria.json")
                     if path.is_file()) if INPUT_ROOT.is_dir() else []
    if len(matches) != 1:
        raise RuntimeError(f"expected one W3 criteria input, found {len(matches)}")
    return matches[0].parent, matches[0]


def load_registered_input() -> tuple[dict, str, Path, Path, dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = {
        "input_root": str(INPUT_ROOT),
        "input_root_exists": INPUT_ROOT.is_dir(),
        "top_level_entries": sorted(
            f"{'dir' if path.is_dir() else 'file'}:{path.name}"
            for path in INPUT_ROOT.iterdir()) if INPUT_ROOT.is_dir() else [],
    }
    write_json(OUT / "input_mount_inventory.json", inventory)
    dataset_dir, criteria_path = discover_dataset()
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != W3_CRITERIA_SHA256:
        raise RuntimeError("W3 round-3 criteria sidecar mismatch")
    criteria_sha = sha256(criteria_path)
    if criteria_sha != W3_CRITERIA_SHA256:
        raise RuntimeError("W3 round-3 criteria SHA mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise RuntimeError("attached W3 criteria are not immutable preregistration")
    if criteria.get("source_commit") != W3_SOURCE_COMMIT or criteria.get("input_dataset_id") != DATASET_ID:
        raise RuntimeError("attached W3 criteria identity mismatch")
    manifest_path = dataset_dir / "w3_v16_dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("dataset_id") != DATASET_ID or manifest.get("criteria_sha256") != criteria_sha:
        raise RuntimeError("W3 dataset manifest criteria binding mismatch")
    expected_files = {
        "sdf_design_state.npz": criteria["inputs"]["canonical_state_npz"]["sha256"],
        "canonical_v16_phi_f4_fortran.raw": criteria["inputs"]["canonical_phi_fortran_raw"]["sha256"],
        "w3_v16_criteria.json": criteria_sha,
        "w3_v16_criteria.json.sha256": sha256(sidecar),
    }
    if set(manifest.get("files", {})) != set(expected_files):
        raise RuntimeError("W3 dataset manifest file inventory mismatch")
    for name, expected_sha in expected_files.items():
        path = dataset_dir / name
        if not path.is_file() or sha256(path) != expected_sha:
            raise RuntimeError(f"W3 dataset input hash mismatch: {name}")
        if manifest["files"].get(name) != expected_sha:
            raise RuntimeError(f"W3 dataset manifest hash mismatch: {name}")
    return criteria, criteria_sha, dataset_dir, manifest_path, inventory


def verify_canonical_state(criteria: dict, dataset_dir: Path) -> tuple[Path, dict]:
    import numpy as np

    entry = criteria["inputs"]["canonical_state_npz"]
    state_path = dataset_dir / entry["path"]
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    geometry = criteria["geometry"]
    if phi.shape != tuple(geometry["point_shape"]) or not np.isfinite(phi).all():
        raise RuntimeError("canonical W3 phi shape/finiteness mismatch")
    c_order = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    f_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    f_order = hashlib.sha256(f_bytes).hexdigest()
    raw_path = dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    if c_order != geometry["phi_c_order_sha256"] or f_order != geometry["phi_fortran_sha256"]:
        raise RuntimeError("canonical W3 C/F phi hash mismatch")
    if raw_path.read_bytes() != f_bytes:
        raise RuntimeError("canonical W3 raw phi bytes differ from NPZ")
    if metadata.get("state_sha256") != geometry["state_sha256"]:
        raise RuntimeError("canonical W3 state identity mismatch")
    if metadata.get("source_sha256") != geometry["source_surface_sha256"]:
        raise RuntimeError("canonical W3 source surface identity mismatch")
    if metadata.get("origin_m") != geometry["canonical_sdf_origin_m"] or metadata.get("spacing_m") != geometry["spacing_m"]:
        raise RuntimeError("canonical W3 SDF lattice metadata mismatch")
    return raw_path, metadata


def gpu_inventory(criteria: dict) -> tuple[list[str], str]:
    rows = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True).splitlines()
    rows = [row.strip() for row in rows if row.strip()]
    (OUT / "nvidia_smi.csv").write_text("\n".join(rows) + "\n")
    expected = criteria["backend"]
    if len(rows) != expected["gpu_count"]:
        raise RuntimeError("T4 inventory count mismatch")
    if any(expected["gpu_name"] not in row or expected["driver_version"] not in row for row in rows):
        raise RuntimeError("T4 model or NVIDIA driver mismatch")
    uuids = [row.split(",")[2].strip() for row in rows]
    if len(set(uuids)) != len(rows):
        raise RuntimeError("T4 UUID inventory is not unique")
    return rows, uuids[0]


def fetch_source(base: Path, criteria: dict) -> Path:
    source = base / "source"
    command(["git", "init", "-q", str(source)], OUT / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH),
             SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=900)
    command(["git", "-C", str(source), "checkout", "--detach", DIAGNOSTIC_SOURCE_COMMIT],
            OUT / "git_checkout.log")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != DIAGNOSTIC_SOURCE_COMMIT:
        raise RuntimeError("diagnostic source commit mismatch")
    w3_criteria_files = {
        name: entry for name, entry in criteria["inputs"].items()
        if entry.get("location") == "source_repo"
    }
    for name, entry in w3_criteria_files.items():
        path = source / entry["path"]
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise RuntimeError(f"pinned W3 round-3 source file changed in diagnostic source: {name}")
    project = source / "julia/CFDSDFWaterLilyT4"
    if sha256(project / "Project.toml") != criteria["inputs"]["project"]["sha256"]:
        raise RuntimeError("T4 Project.toml SHA mismatch")
    if sha256(project / "Manifest.toml") != criteria["inputs"]["manifest"]["sha256"]:
        raise RuntimeError("T4 Manifest.toml SHA mismatch")
    diagnostic_job = source / "scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"
    if sha256(diagnostic_job) != DIAGNOSTIC_JOB_SHA256:
        raise RuntimeError("diagnostic Julia job SHA mismatch")
    owner_job = source / "scripts/waterlily_w3_v16_cuda_owner_lifetime_job.jl"
    owner_criteria = source / OWNER_LIFETIME_CRITERIA_PATH
    owner_sidecar = owner_criteria.with_suffix(owner_criteria.suffix + ".sha256")
    if not owner_job.is_file() or sha256(owner_job) != OWNER_LIFETIME_JOB_SHA256:
        raise RuntimeError("owner-lifetime Julia job SHA mismatch")
    if not owner_criteria.is_file() or not owner_sidecar.is_file():
        raise RuntimeError("owner-lifetime criteria or sidecar missing")
    owner_criteria_sha = sha256(owner_criteria)
    if owner_sidecar.read_text().strip() != owner_criteria_sha:
        raise RuntimeError("owner-lifetime criteria sidecar mismatch")
    preregistration = json.loads(owner_criteria.read_text())
    if preregistration.get("immutable") is not True or preregistration.get("registered_before_computation") is not True:
        raise RuntimeError("owner-lifetime criteria are not immutable preregistration")
    if preregistration.get("inputs", {}).get("owner_lifetime_job", {}).get("sha256") != OWNER_LIFETIME_JOB_SHA256:
        raise RuntimeError("owner-lifetime criteria/job binding mismatch")
    if preregistration.get("inputs", {}).get("w3_criteria_sha256") != W3_CRITERIA_SHA256:
        raise RuntimeError("owner-lifetime criteria/W3 round-3 binding mismatch")
    return source


def classify_owner_arm(arm_id: str, returncode: int, report: dict,
                      last_stage: str | None) -> dict:
    ownership = report.get("ownership", {})
    collected = ownership.get("owner_collected_during_forced_gc") is True
    post_gc_stages = {
        "fixed_probes_after_gc_started", "fixed_probes_after_gc_completed",
        "full_grid_geometry_started", "full_grid_geometry_completed",
        "measure_after_gc_started", "measure_after_gc_completed",
        "primal_step_1_started", "primal_step_1_completed",
        "primal_step_2_started", "primal_step_2_completed", "arm_completed",
    }
    hazard = arm_id.startswith("B") and collected and last_stage in post_gc_stages
    completed = returncode == 0 and report.get("status") == "completed"
    expected = hazard and (returncode != 0 or report.get("status") == "operation_error")
    return {
        "owner_collected_during_forced_gc": collected,
        "expected_lifetime_hazard": expected,
        "julia_caught_operation_error": report.get("status") == "operation_error",
        "process_level_error": returncode != 0,
        "acceptable": completed or expected,
        "classification": "expected_unrooted_post_gc_hazard" if expected
            else "completed" if completed else "unexpected_arm_failure",
    }


def run_owner_lifetime_arms(julia: Path, project: Path, source: Path,
                            raw_phi_path: Path, env: dict[str, str],
                            runner_sha: str, criteria_sha: str,
                            criteria_sidecar_sha: str) -> dict:
    job = source / "scripts/waterlily_w3_v16_cuda_owner_lifetime_job.jl"
    arm_rows = []
    unexpected = []
    for arm_id in ("A", "C", "B1", "B2"):
        log_path = OUT / f"owner_lifetime_{arm_id}.log"
        arm_env = env | {
            "W3_OWNER_ARM_ID": arm_id,
            "W3_OWNER_CRITERIA_SHA256": criteria_sha,
            "W3_OWNER_CRITERIA_SIDECAR_SHA256": criteria_sidecar_sha,
            "W3_OWNER_JOB_SHA256": OWNER_LIFETIME_JOB_SHA256,
        }
        args = [str(julia), "--startup-file=no", f"--project={project}",
                str(job), str(raw_phi_path), str(OUT), arm_id]
        print("RUN OWNER ARM", arm_id, flush=True)
        with log_path.open("w") as handle:
            completed = subprocess.run(args, env=arm_env, stdout=handle,
                                       stderr=subprocess.STDOUT, timeout=1800,
                                       check=False)
        report_path = OUT / f"w3_v16_cuda_owner_lifetime_{arm_id}.json"
        progress_path = OUT / f"w3_v16_cuda_owner_progress_{arm_id}.json"
        report = json.loads(report_path.read_text()) if report_path.is_file() else {}
        progress = json.loads(progress_path.read_text()) if progress_path.is_file() else {}
        last_stage = report.get("last_stage", progress.get("last_stage"))
        classification = classify_owner_arm(
            arm_id, completed.returncode, report or progress, last_stage)
        acceptable = classification["acceptable"]
        if not acceptable:
            unexpected.append(arm_id)
        row = {
            "arm_id": arm_id,
            "process_returncode": completed.returncode,
            "report_path": report_path.name if report_path.is_file() else None,
            "report_sha256": sha256(report_path) if report_path.is_file() else None,
            "progress_path": progress_path.name if progress_path.is_file() else None,
            "progress_sha256": sha256(progress_path) if progress_path.is_file() else None,
            "log_path": log_path.name,
            "log_sha256": sha256(log_path),
            "last_stage": last_stage,
            **classification,
        }
        write_json(OUT / f"owner_lifetime_{arm_id}_runner.json", row)
        arm_rows.append(row)
    execution = {
        "evidence_type": "diagnostic_only",
        "criteria_path": OWNER_LIFETIME_CRITERIA_PATH,
        "criteria_sha256": criteria_sha,
        "criteria_sidecar_sha256": criteria_sidecar_sha,
        "source_commit": DIAGNOSTIC_SOURCE_COMMIT,
        "julia_job_sha256": OWNER_LIFETIME_JOB_SHA256,
        "runner_sha256": runner_sha,
        "arm_order": ["A", "C", "B1", "B2"],
        "arms": arm_rows,
        "unexpected_arm_failures": unexpected,
        "status": "captured" if not unexpected else "arm_failure",
        "qualification_evidence": False,
    }
    write_json(OUT / "owner_lifetime_execution.json", execution)
    if unexpected:
        raise RuntimeError(f"unexpected owner-lifetime arm failure(s): {unexpected}")
    return execution


def install_julia(base: Path) -> Path:
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia archive SHA mismatch")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(base)], check=True)
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("pinned Julia executable missing")
    return julia


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    criteria, criteria_sha, dataset_dir, manifest_path, input_inventory = load_registered_input()
    raw_phi_path, state_metadata = verify_canonical_state(criteria, dataset_dir)
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    runner_sha = sha256(Path(__file__))
    if DIAGNOSTIC_SOURCE_COMMIT == "TO_BE_PINNED" or DIAGNOSTIC_JOB_SHA256 == "TO_BE_PINNED":
        raise RuntimeError("diagnostic identity pins were not frozen before submission")
    (OUT / "input_dataset_manifest.json").write_bytes(manifest_path.read_bytes())
    write_json(OUT / "input_state_metadata.json", state_metadata)
    sidecar_path = dataset_dir / "w3_v16_criteria.json.sha256"
    dataset_manifest_sha = sha256(manifest_path)
    sidecar_sha = sha256(sidecar_path)
    with tempfile.TemporaryDirectory(prefix="w3_cuda_diagnostic_") as temp:
        base = Path(temp)
        source = fetch_source(base, criteria)
        julia = install_julia(base)
        owner_criteria_path = source / OWNER_LIFETIME_CRITERIA_PATH
        owner_criteria_sha = sha256(owner_criteria_path)
        owner_criteria_sidecar_sha = sha256(
            owner_criteria_path.with_suffix(owner_criteria_path.suffix + ".sha256"))
        env = os.environ.copy()
        env.update({
            "JULIA_NUM_THREADS": "1",
            "CUDA_VISIBLE_DEVICES": "0",
            "W3_DIAGNOSTIC_SELECTED_GPU_UUID": selected_uuid,
            "W3_DIAGNOSTIC_W3_SOURCE_COMMIT": W3_SOURCE_COMMIT,
            "W3_DIAGNOSTIC_SOURCE_COMMIT": DIAGNOSTIC_SOURCE_COMMIT,
            "W3_DIAGNOSTIC_JOB_SHA256": DIAGNOSTIC_JOB_SHA256,
            "W3_DIAGNOSTIC_W3_JOB_SHA256": criteria["inputs"]["job"]["sha256"],
            "W3_DIAGNOSTIC_PROJECT_SHA256": criteria["inputs"]["project"]["sha256"],
            "W3_DIAGNOSTIC_MANIFEST_SHA256": criteria["inputs"]["manifest"]["sha256"],
            "W3_DIAGNOSTIC_JULIA_SHA256": JULIA_SHA256,
            "W3_DIAGNOSTIC_RUNNER_SHA256": runner_sha,
            "W3_DIAGNOSTIC_CRITERIA_SHA256": criteria_sha,
            "W3_DIAGNOSTIC_CRITERIA_SIDECAR_SHA256": sidecar_sha,
            "W3_DIAGNOSTIC_DATASET_ID": DATASET_ID,
            "W3_DIAGNOSTIC_DATASET_MANIFEST_SHA256": dataset_manifest_sha,
            "W3_DIAGNOSTIC_STATE_SHA256": criteria["geometry"]["state_sha256"],
            "W3_DIAGNOSTIC_SOURCE_SURFACE_SHA256": criteria["geometry"]["source_surface_sha256"],
            "W3_DIAGNOSTIC_DESIGN_DOMAIN_SHA256": criteria["geometry"]["design_domain_sha256"],
            "W3_OWNER_CRITERIA_SHA256": owner_criteria_sha,
            "W3_OWNER_CRITERIA_SIDECAR_SHA256": owner_criteria_sidecar_sha,
            "W3_OWNER_JOB_SHA256": OWNER_LIFETIME_JOB_SHA256,
        })
        project = source / "julia/CFDSDFWaterLilyT4"
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        if sha256(project / "Project.toml") != criteria["inputs"]["project"]["sha256"]:
            raise RuntimeError("T4 Project.toml changed during instantiate")
        if sha256(project / "Manifest.toml") != criteria["inputs"]["manifest"]["sha256"]:
            raise RuntimeError("T4 Manifest.toml changed during instantiate")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / "scripts/w0b_t4_smoke.jl")],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        required = (
            "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
            "CUDA_DRIVER_VERSION 13.3.0", "CUDA_RUNTIME_VERSION 12.8.0",
            "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
            "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4", "NO_SOLVER_STEP",
        )
        if any(marker not in smoke for marker in required):
            raise RuntimeError("registered CUDA smoke identity mismatch")
        # Preserve backend and immutable-input identity even when the Julia
        # diagnostic itself errors before producing its report.
        write_json(OUT / "fingerprint.json", {
            "kernel_id": KERNEL_ID,
            "criteria_sha256": criteria_sha,
            "criteria_sidecar_sha256": sidecar_sha,
            "dataset_id": DATASET_ID,
            "dataset_manifest_sha256": dataset_manifest_sha,
            "runner_sha256": runner_sha,
            "source_commit": DIAGNOSTIC_SOURCE_COMMIT,
            "diagnostic_job_sha256": DIAGNOSTIC_JOB_SHA256,
            "w3_source_commit": W3_SOURCE_COMMIT,
            "w3_source_job_sha256": criteria["inputs"]["job"]["sha256"],
            "project_sha256": criteria["inputs"]["project"]["sha256"],
            "manifest_sha256": criteria["inputs"]["manifest"]["sha256"],
            "julia_archive_sha256": JULIA_SHA256,
            "state_sha256": criteria["geometry"]["state_sha256"],
            "source_surface_sha256": criteria["geometry"]["source_surface_sha256"],
            "design_domain_sha256": criteria["geometry"]["design_domain_sha256"],
            "gpu_inventory": gpu_rows,
            "selected_gpu_uuid": selected_uuid,
            "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
            "platform": platform.platform(),
            "python": platform.python_version(),
            "input_mount_inventory": input_inventory,
            "cuda_smoke_sha256": sha256(OUT / "julia_smoke.log"),
            "owner_lifetime_criteria_sha256": owner_criteria_sha,
            "owner_lifetime_criteria_sidecar_sha256": owner_criteria_sidecar_sha,
            "owner_lifetime_source_commit": DIAGNOSTIC_SOURCE_COMMIT,
            "owner_lifetime_job_sha256": OWNER_LIFETIME_JOB_SHA256,
        })
        job = source / "scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"
        command([str(julia), "--startup-file=no", f"--project={project}", str(job),
                 str(raw_phi_path), str(OUT)], OUT / "w3_cuda_diagnostic.log", env=env, timeout=5400)
    report_path = OUT / "w3_v16_cuda_diagnostic.json"
    lattice_path = OUT / "v16_flow_lattice.csv"
    if not report_path.is_file() or not lattice_path.is_file():
        raise RuntimeError("Julia diagnostic outputs are incomplete")
    report = json.loads(report_path.read_text())
    expected_identity = {
        "criteria_sha256": criteria_sha,
        "w3_source_commit": W3_SOURCE_COMMIT,
        "diagnostic_source_commit": DIAGNOSTIC_SOURCE_COMMIT,
        "diagnostic_job_sha256": DIAGNOSTIC_JOB_SHA256,
        "source_w3_job_sha256": criteria["inputs"]["job"]["sha256"],
        "project_sha256": criteria["inputs"]["project"]["sha256"],
        "manifest_sha256": criteria["inputs"]["manifest"]["sha256"],
        "julia_archive_sha256": JULIA_SHA256,
        "runner_sha256": runner_sha,
        "criteria_sidecar_sha256": sidecar_sha,
        "dataset_id": DATASET_ID,
        "dataset_manifest_sha256": dataset_manifest_sha,
    }
    if any(report["source_identity"].get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError("Julia diagnostic output source identity differs from runner inputs")
    if report["input_identity"].get("canonical_state_sha256") != criteria["geometry"]["state_sha256"]:
        raise RuntimeError("Julia diagnostic output canonical state identity mismatch")
    report["runtime_identity"]["observed_gpu_inventory"] = gpu_rows
    report["runtime_identity"]["selected_gpu_uuid"] = selected_uuid
    report["runtime_identity"]["nvidia_driver_version"] = gpu_rows[0].split(",")[-1].strip()
    write_json(OUT / "runtime_identity.json", report["runtime_identity"])
    run_owner_lifetime_arms(julia, project, source, raw_phi_path, env, runner_sha,
                            owner_criteria_sha, owner_criteria_sidecar_sha)
    manifest = {
        path.name: sha256(path) for path in sorted(OUT.iterdir())
        if path.is_file() and path.name not in {"sha256.json", "DONE"}
    }
    write_json(OUT / "sha256.json", manifest)
    (OUT / "DONE").write_text(
        "Diagnostic computation finished; this marker does not indicate qualification.\n")
    print("W3_V16_CUDA_DIAGNOSTIC_DONE", json.dumps({
        "qualification_evidence": False,
        "csv_sha256": sha256(lattice_path),
        "report_sha256": sha256(report_path),
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        manifest = {
            path.name: sha256(path) for path in sorted(OUT.iterdir())
            if path.is_file() and path.name not in {"sha256.json", "DONE"}
        }
        write_json(OUT / "sha256.json", manifest)
        raise
