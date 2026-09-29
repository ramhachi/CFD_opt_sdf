#!/usr/bin/env python3
"""Capture the Kaggle T4 CUDA/WaterLily identity and run the registered W0b smoke (no solver step)."""

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

STAGE = "w0b_kaggle"
OUT = Path("/kaggle/working") / STAGE
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/feat/issue-42-w0b-kaggle"
SOURCE_FETCH_DEPTH = 16
# Pinned after the criteria commit exists (the runner is committed after, and rechecked on host).
CRITERIA_COMMIT = "TO_BE_PINNED"
CRITERIA_SHA256 = "TO_BE_PINNED"
CRITERIA_PATH = "docs/evidence/kaggle_w0b_t4_identity_criteria_2026_09.json"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def command(args, log_path, *, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def write_hash_manifest():
    write_json(OUT / "sha256.json", {
        path.name: sha256(path) for path in sorted(OUT.iterdir())
        if path.is_file() and path.name not in {"sha256.json", "DONE"}})


def fetch_source(base):
    source = base / "source"
    command(["git", "init", "-q", str(source)], OUT / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH),
             SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=600)
    command(["git", "-C", str(source), "checkout", "--detach", CRITERIA_COMMIT], OUT / "git_checkout.log")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != CRITERIA_COMMIT:
        raise RuntimeError("criteria commit drift")
    criteria_path = source / CRITERIA_PATH
    if sha256(criteria_path) != CRITERIA_SHA256:
        raise RuntimeError("criteria SHA-256 mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise RuntimeError("criteria are not an immutable preregistration")
    for entry in criteria["source_files"].values():
        if sha256(source / entry["path"]) != entry["sha256"]:
            raise RuntimeError(f"registered source file changed: {entry['path']}")
    return source, criteria


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia binary SHA-256 mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)], OUT / "julia_extract.log", timeout=600)
    return base / "julia-1.12.6/bin/julia"


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    if "TO_BE_PINNED" in (CRITERIA_COMMIT, CRITERIA_SHA256):
        raise RuntimeError("criteria pins were not frozen before submission")
    # Record the allocated GPUs before anything can fail, then stop early on a wrong model.
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if not rows or any("Tesla T4" not in row for row in rows):
        raise RuntimeError(f"allocated GPU is not a Tesla T4: {rows}")
    with tempfile.TemporaryDirectory(prefix="w0b_kaggle_") as temp:
        base = Path(temp)
        source, criteria = fetch_source(base)
        project = source / "julia/CFDSDFWaterLilyT4"
        julia = install_julia(base)
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "0"})
        julia_args = [str(julia), "--startup-file=no", f"--project={project}"]
        command(julia_args + ["-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        command(julia_args + [str(source / "scripts/w0b_t4_smoke.jl")], OUT / "julia_smoke.log", env=env, timeout=1200)
        command(julia_args + ["-e", 'using CUDA; println("GPU_UUID_JULIA GPU-", CUDA.uuid(CUDA.device()))'],
                OUT / "julia_uuid.log", env=env, timeout=600)
        write_json(OUT / "fingerprint.json", {
            "kernel_id": criteria["kernel"]["id"],
            "criteria_commit": CRITERIA_COMMIT,
            "criteria_sha256": CRITERIA_SHA256,
            "runner_sha256": sha256(Path(__file__)),
            "julia_archive_sha256": JULIA_SHA256,
            "project_sha256": sha256(project / "Project.toml"),
            "manifest_sha256": sha256(project / "Manifest.toml"),
            "gpu_csv": rows,
            "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
            "platform": platform.platform(),
            "python": platform.python_version(),
            "started_unix": started,
            "finished_unix": time.time(),
        })
    write_hash_manifest()
    (OUT / "DONE").write_text("W0b-Kaggle identity capture finished; verify retrieved SHA-256 files\n")
    print("KAGGLE_W0B_DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        write_hash_manifest()
        raise
