#!/usr/bin/env python3
"""Run a non-qualifying WaterLily/Enzyme reverse-mode diagnostic on Kaggle T4."""

import hashlib
import json
import os
import subprocess
import tempfile
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "julia"
SCRIPT = PROJECT / "reverse_spike.jl"
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        gpu = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
             "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        rows = [row.strip() for row in gpu.splitlines() if row.strip()]
        if not rows or any("Tesla T4" not in row for row in rows):
            raise RuntimeError("requested T4 worker was not present in GPU inventory")
        with tempfile.TemporaryDirectory(prefix="enzyme-reverse-spike-") as temp:
            base = Path(temp)
            julia = install_julia(base)
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = "0"
            env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            env["JULIA_NUM_THREADS"] = "1"
            run([str(julia), f"--project={PROJECT}", "-e", "using Pkg; Pkg.instantiate()"],
                OUT / "instantiate.log", env, 3600)
            run([str(julia), f"--project={PROJECT}", str(SCRIPT)],
                OUT / "reverse_spike.log", env, 7200)
        (OUT / "DONE").write_text(
            "Diagnostic script completed; individual reverse stages are reported in reverse_spike.log.\n")
    except Exception:
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        files = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                 if path.is_file() and path.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)


if __name__ == "__main__":
    main()
