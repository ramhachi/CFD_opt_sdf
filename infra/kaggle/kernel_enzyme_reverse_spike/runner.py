#!/usr/bin/env python3
"""Run a non-qualifying WaterLily/Enzyme reverse-mode diagnostic on Kaggle T4."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import traceback
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_COMMIT = "9b22f719e2f06222dd7f01788154399f0fef441d"
SOURCE_ARCHIVE_URL = (
    "https://codeload.github.com/ramhachi/CFD_opt_sdf/zip/" + SOURCE_COMMIT
)
PROJECT_RELATIVE_PATH = "infra/kaggle/kernel_enzyme_reverse_spike/julia"
REGISTERED_PROJECT_SHA256 = "867d0e3f1846d65322b65c44261d649c43775984d36cbc6bfb43a02285653383"
REGISTERED_MANIFEST_SHA256 = "f30dacad47411641cbf297c4663e12029de2565ab6d875aa05891127289a8b6e"
REGISTERED_SCRIPT_SHA256 = "2d261585eb1dd2b408ab730bde010f741f1b8080dcce2319759d43f4ca3c0c48"
SCRIPT_NAME = "reverse_spike.jl"
OUT = Path("/kaggle/working/enzyme_reverse_spike")
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args, log_path, env, timeout):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as log:
        result = subprocess.run(args, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                check=False)
    lines = Path(log_path).read_text(errors="replace").splitlines()
    print("LOG_TAIL", Path(log_path).name, flush=True)
    for line in lines[-80:]:
        print(line, flush=True)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as output:
        while block := response.read(1 << 20):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia 1.12.6 archive SHA-256 mismatch")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(base)], check=True)
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("verified Julia archive extraction failed")
    return julia


def fetch_pinned_project(base):
    archive = Path(base) / "source.zip"
    digest = hashlib.sha256()
    with urllib.request.urlopen(SOURCE_ARCHIVE_URL, timeout=120) as response, archive.open("wb") as output:
        while block := response.read(1 << 20):
            digest.update(block)
            output.write(block)
    archive_sha = digest.hexdigest()
    project = Path(base) / "source-project"
    suffix = "/" + PROJECT_RELATIVE_PATH + "/"
    with zipfile.ZipFile(archive) as bundle:
        project_entries = [
            name for name in bundle.namelist()
            if name.endswith(suffix + "Project.toml")
        ]
        if len(project_entries) != 1:
            raise RuntimeError(
                f"pinned source archive must contain one scratch Project.toml, found {len(project_entries)}"
            )
        source_prefix = project_entries[0][:-len("Project.toml")]
        for name in bundle.namelist():
            if not name.startswith(source_prefix):
                continue
            relative = name[len(source_prefix):]
            parts = Path(relative).parts
            if not relative or any(part in {".", ".."} for part in parts):
                continue
            target = project.joinpath(*parts)
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    project_sha = sha256(project / "Project.toml")
    manifest_sha = sha256(project / "Manifest.toml")
    script_sha = sha256(project / SCRIPT_NAME)
    if (project_sha != REGISTERED_PROJECT_SHA256
            or manifest_sha != REGISTERED_MANIFEST_SHA256
            or script_sha != REGISTERED_SCRIPT_SHA256):
        raise RuntimeError("pinned scratch Julia project/source SHA-256 mismatch")
    return project, archive_sha, project_sha, manifest_sha, script_sha


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stage = "gpu_inventory"
    project_identity = {
        "project_source_commit": SOURCE_COMMIT,
        "registered_project_sha256": REGISTERED_PROJECT_SHA256,
        "registered_manifest_sha256": REGISTERED_MANIFEST_SHA256,
        "registered_reverse_script_sha256": REGISTERED_SCRIPT_SHA256,
        "source_archive_sha256": None,
        "source_project_sha256": None,
        "source_manifest_sha256": None,
        "source_reverse_script_sha256": None,
        "writable_copy_pre_instantiate_project_sha256": None,
        "writable_copy_pre_instantiate_manifest_sha256": None,
        "writable_copy_post_instantiate_project_sha256": None,
        "writable_copy_post_instantiate_manifest_sha256": None,
        "writable_project_path": None,
        "source_hashes_match_registered_inputs": False,
        "copy_hashes_match_registered_inputs": False,
        "instantiate_completed": False,
        "reverse_script_completed": False,
        "failure_stage": None,
    }
    write_json(OUT / "project_identity.json", project_identity)
    try:
        gpu = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
             "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        rows = [row.strip() for row in gpu.splitlines() if row.strip()]
        if not rows or any("Tesla T4" not in row for row in rows):
            raise RuntimeError("requested T4 worker was not present in GPU inventory")
        with tempfile.TemporaryDirectory(
                prefix="enzyme-reverse-spike-", dir="/kaggle/working") as temp:
            base = Path(temp)
            stage = "pinned_source_archive_fetch"
            source_project, archive_sha, source_project_sha, source_manifest_sha, source_script_sha = fetch_pinned_project(base)
            project_identity.update({
                "source_archive_sha256": archive_sha,
                "source_project_sha256": source_project_sha,
                "source_manifest_sha256": source_manifest_sha,
                "source_reverse_script_sha256": source_script_sha,
                "source_hashes_match_registered_inputs": True,
            })
            write_json(OUT / "project_identity.json", project_identity)
            writable_project = base / "julia-project"
            project_identity["writable_project_path"] = str(writable_project)
            write_json(OUT / "project_identity.json", project_identity)
            stage = "writable_project_copy"
            shutil.copytree(source_project, writable_project)
            copied_project_sha = sha256(writable_project / "Project.toml")
            copied_manifest_sha = sha256(writable_project / "Manifest.toml")
            project_identity.update({
                "writable_copy_pre_instantiate_project_sha256": copied_project_sha,
                "writable_copy_pre_instantiate_manifest_sha256": copied_manifest_sha,
                "copy_hashes_match_registered_inputs": (
                    copied_project_sha == REGISTERED_PROJECT_SHA256
                    and copied_manifest_sha == REGISTERED_MANIFEST_SHA256),
            })
            write_json(OUT / "project_identity.json", project_identity)
            if (copied_project_sha != REGISTERED_PROJECT_SHA256
                    or copied_manifest_sha != REGISTERED_MANIFEST_SHA256):
                raise RuntimeError("writable Project/Manifest copy differs from registered scratch pins")
            stage = "julia_installation"
            julia = install_julia(base)
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = "0"
            env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            env["JULIA_NUM_THREADS"] = "1"
            stage = "dependency_resolution"
            run([str(julia), f"--project={writable_project}", "-e", "using Pkg; Pkg.instantiate()"],
                OUT / "instantiate.log", env, 3600)
            project_identity.update({
                "writable_copy_post_instantiate_project_sha256": sha256(writable_project / "Project.toml"),
                "writable_copy_post_instantiate_manifest_sha256": sha256(writable_project / "Manifest.toml"),
                "instantiate_completed": True,
                "failure_stage": None,
            })
            write_json(OUT / "project_identity.json", project_identity)
            stage = "cuda_and_reverse_diagnostics"
            run([str(julia), f"--project={writable_project}",
                 str(writable_project / SCRIPT_NAME)],
                OUT / "reverse_spike.log", env, 7200)
            project_identity["reverse_script_completed"] = True
            project_identity["failure_stage"] = None
            write_json(OUT / "project_identity.json", project_identity)
        (OUT / "DONE").write_text(
            "Diagnostic script completed; individual reverse stages are reported in reverse_spike.log.\n")
        stage = "completed"
    except Exception:
        if project_identity is not None:
            project_identity["failure_stage"] = stage
            write_json(OUT / "project_identity.json", project_identity)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        files = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                 if path.is_file() and path.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)


if __name__ == "__main__":
    main()
