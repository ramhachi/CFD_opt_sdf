#!/usr/bin/env python3
"""Exact-runtime diagnostic for the W3 CuArray memory type identity."""

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

OUT = Path("/kaggle/working/w3_owner_type_probe")
INPUT_ROOT = Path("/kaggle/input")
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
W3_CRITERIA_PATH = "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def command(args: list[str], log_path: Path, *, env: dict[str, str] | None = None,
            timeout: int = 3600) -> str:
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def unique_input(filename: str) -> tuple[Path, Path]:
    matches = sorted(path for path in INPUT_ROOT.rglob(filename) if path.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {filename}, found {len(matches)}")
    return matches[0].parent, matches[0]


def load_inputs() -> tuple[dict, Path, Path, dict]:
    inventory = {
        "input_root_exists": INPUT_ROOT.is_dir(),
        "top_level_entries": sorted(
            f"{'dir' if path.is_dir() else 'file'}:{path.name}"
            for path in INPUT_ROOT.iterdir()) if INPUT_ROOT.is_dir() else [],
        "criteria_files": sorted(path.name for path in INPUT_ROOT.rglob("w3_owner_type_probe_criteria.json")),
        "w3_criteria_files": sorted(path.name for path in INPUT_ROOT.rglob("w3_v16_criteria.json")),
    }
    write_json(OUT / "input_mount_inventory.json", inventory)
    criteria_dir, criteria_path = unique_input("w3_owner_type_probe_criteria.json")
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    manifest_path = criteria_dir / "w3_owner_type_probe_dataset_manifest.json"
    if not sidecar.is_file() or not manifest_path.is_file():
        raise RuntimeError("type-probe criteria sidecar or dataset manifest missing")
    criteria_sha = sha256(criteria_path)
    if sidecar.read_text().strip() != criteria_sha:
        raise RuntimeError("type-probe criteria sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise RuntimeError("type-probe criteria are not immutable preregistration")
    manifest = json.loads(manifest_path.read_text())
    expected_dataset_files = {
        "w3_owner_type_probe_criteria.json": criteria_sha,
        "w3_owner_type_probe_criteria.json.sha256": sha256(sidecar),
    }
    if manifest.get("dataset_id") != criteria["criteria_dataset_id"] or manifest.get("files") != expected_dataset_files:
        raise RuntimeError("type-probe criteria dataset manifest mismatch")
    if any(sha256(criteria_dir / name) != expected for name, expected in expected_dataset_files.items()):
        raise RuntimeError("type-probe criteria dataset file hash mismatch")

    w3_dir, w3_criteria_path = unique_input("w3_v16_criteria.json")
    w3_criteria = json.loads(w3_criteria_path.read_text())
    w3_sidecar = w3_criteria_path.with_suffix(w3_criteria_path.suffix + ".sha256")
    w3_manifest_path = w3_dir / "w3_v16_dataset_manifest.json"
    if sha256(w3_criteria_path) != criteria["w3_input"]["criteria_sha256"]:
        raise RuntimeError("W3 round-3 criteria SHA mismatch")
    if not w3_sidecar.is_file() or w3_sidecar.read_text().strip() != criteria["w3_input"]["criteria_sha256"]:
        raise RuntimeError("W3 round-3 criteria sidecar mismatch")
    if not w3_manifest_path.is_file() or sha256(w3_manifest_path) != criteria["w3_input"]["dataset_manifest_sha256"]:
        raise RuntimeError("W3 dataset manifest SHA mismatch")
    w3_manifest = json.loads(w3_manifest_path.read_text())
    if w3_manifest.get("dataset_id") != criteria["w3_input"]["dataset_id"]:
        raise RuntimeError("W3 dataset identity mismatch")
    raw_entry = w3_criteria["inputs"]["canonical_phi_fortran_raw"]
    raw_phi = w3_dir / raw_entry["path"]
    if sha256(raw_phi) != criteria["w3_input"]["phi_fortran_sha256"]:
        raise RuntimeError("canonical W3 raw phi SHA mismatch")
    if w3_manifest.get("files", {}).get(raw_entry["path"]) != criteria["w3_input"]["phi_fortran_sha256"]:
        raise RuntimeError("W3 dataset manifest raw phi SHA mismatch")
    result = dict(criteria)
    result["_criteria_sha256"] = criteria_sha
    result["_criteria_sidecar_sha256"] = sha256(sidecar)
    result["_criteria_dataset_manifest_sha256"] = sha256(manifest_path)
    result["_w3_dataset_manifest_sha256"] = sha256(w3_manifest_path)
    result["_w3_criteria_sidecar_sha256"] = sha256(w3_sidecar)
    return result, raw_phi, w3_manifest_path, inventory


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
    criteria, raw_phi, w3_manifest_path, inventory = load_inputs()
    runner_sha = sha256(Path(__file__))
    files = criteria["source_files"]
    if files["runner"]["sha256"] != runner_sha:
        raise RuntimeError("kernel runner SHA differs from preregistration")
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    (OUT / "w3_input_dataset_manifest.json").write_bytes(w3_manifest_path.read_bytes())
    criteria_status = {
        "criteria_sha256": criteria["_criteria_sha256"],
        "criteria_sidecar_sha256": criteria["_criteria_sidecar_sha256"],
        "criteria_dataset_manifest_sha256": criteria["_criteria_dataset_manifest_sha256"],
        "w3_dataset_manifest_sha256": criteria["_w3_dataset_manifest_sha256"],
        "w3_criteria_sidecar_sha256": criteria["_w3_criteria_sidecar_sha256"],
    }
    with tempfile.TemporaryDirectory(prefix="w3_owner_type_probe_") as temporary:
        base = Path(temporary)
        source = base / "source"
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "fetch", "--depth", "32",
                        SOURCE_URL, SOURCE_REF], check=True, timeout=900)
        commit = criteria["source_commit"]
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", commit], check=True)
        actual_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if actual_commit != commit:
            raise RuntimeError("source commit mismatch")
        for entry in files.values():
            path = source / entry["path"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise RuntimeError(f"source file hash mismatch: {entry['path']}")
        project = source / "julia/CFDSDFWaterLilyT4"
        if sha256(project / "Project.toml") != files["project"]["sha256"]:
            raise RuntimeError("Project.toml SHA mismatch")
        if sha256(project / "Manifest.toml") != files["manifest"]["sha256"]:
            raise RuntimeError("Manifest.toml SHA mismatch")
        julia = install_julia(base)
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "0",
                    "W3_TYPE_PROBE_SELECTED_GPU_UUID": selected_uuid})
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        if sha256(project / "Project.toml") != files["project"]["sha256"] or sha256(project / "Manifest.toml") != files["manifest"]["sha256"]:
            raise RuntimeError("Julia instantiate modified pinned project files")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / "scripts/w0b_t4_smoke.jl")],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        required = ("CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
                    "CUDA_DRIVER_VERSION 13.3.0", "CUDA_RUNTIME_VERSION 12.8.0",
                    "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
                    "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4", "NO_SOLVER_STEP")
        if any(marker not in smoke for marker in required):
            raise RuntimeError("registered T4 smoke identity mismatch")
        write_json(OUT / "fingerprint.json", {
            "kernel_id": criteria["kernel_id"], "criteria": criteria_status,
            "criteria_dataset_id": criteria["criteria_dataset_id"],
            "w3_dataset_id": criteria["w3_input"]["dataset_id"],
            "runner_sha256": runner_sha, "source_commit": actual_commit,
            "source_files": files, "gpu_inventory": gpu_rows,
            "selected_gpu_uuid": selected_uuid, "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
            "platform": platform.platform(), "python": platform.python_version(),
            "input_mount_inventory": inventory, "julia_archive_sha256": JULIA_SHA256,
            "cuda_smoke_sha256": sha256(OUT / "julia_smoke.log"),
        })
        job = source / files["probe_job"]["path"]
        command([str(julia), "--startup-file=no", f"--project={project}", str(job),
                 str(raw_phi), str(OUT)], OUT / "type_probe.log", env=env, timeout=1200)
    report = json.loads((OUT / "type_identity.json").read_text())
    if report.get("gpu_roundtrip_sha256") != criteria["w3_input"]["phi_fortran_sha256"]:
        raise RuntimeError("device round-trip hash mismatch")
    (OUT / "nvidia_driver_version.txt").write_text(criteria["backend"]["driver_version"] + "\n")
    write_json(OUT / "execution.json", {
        "completed": True, "solver_steps": 0, "qualification": False,
        "criteria_sha256": criteria_status["criteria_sha256"],
        "source_commit": criteria["source_commit"], "runner_sha256": runner_sha,
        "probe_job_sha256": files["probe_job"]["sha256"],
    })
    manifest = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    write_json(OUT / "sha256.json", manifest)
    (OUT / "DONE").write_text("Type identity diagnostic completed; no primal step was run.\n")
    print("W3_OWNER_TYPE_PROBE_DONE", json.dumps({"solver_steps": 0, "qualification": False}, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        manifest = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                    if path.is_file() and path.name not in {"sha256.json", "DONE"}}
        write_json(OUT / "sha256.json", manifest)
        raise
