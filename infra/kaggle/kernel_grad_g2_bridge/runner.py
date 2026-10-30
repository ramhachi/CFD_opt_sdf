#!/usr/bin/env python3
"""Run the G2 full-window forward-AD bridge measurement on Kaggle T4 (diagnostic; no dataset, no qualification).

Fail-closed: success writes DONE and exits 0; any failure writes ERROR.txt, never DONE, and exits non-zero.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import traceback
import time
import urllib.request
from pathlib import Path

SOURCE_COMMIT = "e44d0f08c07bde902017cc49854ef85b6ac6be64"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCRIPT = "scripts/waterlily_grad_g2_full_window_bridge_2026_10_08.jl"
PINS = {
    "julia/CFDSDFWaterLilyT4/Project.toml": "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194",
    "julia/CFDSDFWaterLilyT4/Manifest.toml": "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707",
    SCRIPT: "1a458c8bbd26a3992665727cda3db730dd0f78cbb344fa13314e98d1463550b3",
}
PHI_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
PHI_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
INPUT_DIR = "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
DIRECTION_INPUTS = (  # fixed order = run order
    ("D0_interface_offset", "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"),
    ("D1_filtered_seed11", "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87"),
    ("D2_filtered_seed2026", "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de"),
    ("P1_upstream_lobe", "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc"),
)
SPARSE = ["julia", "scripts", INPUT_DIR, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs"]
OUT = Path("/kaggle/working/grad_g2_bridge")
INSTANTIATE_TIMEOUT_S = 3600
SCRIPT_TIMEOUT_S = 6000
KERNEL_TIMEOUT_S = 7200   # must equal the `kaggle kernels push --timeout` value
MARGIN_S = 300            # leave time to write ERROR.txt and the manifest before Kaggle kills the kernel


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(args, log_path, env=None, timeout=3600, cwd=None):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as log:
        result = subprocess.run(args, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    for line in Path(log_path).read_text(errors="replace").splitlines()[-60:]:
        print(line, flush=True)
    return result.returncode


def remaining(started):
    left = KERNEL_TIMEOUT_S - MARGIN_S - (time.time() - started)
    if left <= 60:
        raise RuntimeError("kernel time budget exhausted before the next stage")
    return left


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=120) as response, archive.open("wb") as output:
        while block := response.read(1 << 20):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia archive SHA-256 mismatch")
    subprocess.run(["tar", "-xzf", str(archive), "-C", str(base)], check=True)
    return base / "julia-1.12.6/bin/julia"


def fetch_source(base):
    source = base / "source"
    source.mkdir()
    git = ["git", "-C", str(source)]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["remote", "add", "origin", REPO_URL], check=True)
    subprocess.run(git + ["config", "core.sparseCheckout", "true"], check=True)
    (source / ".git/info/sparse-checkout").write_text("\n".join("/" + p + "/" for p in SPARSE) + "\n")
    fetched = subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT]).returncode == 0
    if not fetched:
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError(f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    return source, fetched


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    stage = "gpu_inventory"
    identity = {"source_commit": SOURCE_COMMIT, "pins": PINS, "phi_sha256": PHI_SHA256,
                "direction_sha256": dict(DIRECTION_INPUTS), "failure_stage": None}
    write_json(OUT / "run_identity.json", identity)
    failed = False
    try:
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        if not gpu.strip() or any("Tesla T4" not in row for row in gpu.strip().splitlines()):
            raise RuntimeError("requested T4 worker was not present")
        with tempfile.TemporaryDirectory(prefix="grad-g2-", dir="/kaggle/working") as temp:
            base = Path(temp)
            stage = "source_checkout"
            source, partial = fetch_source(base)
            identity["partial_clone_filter_used"] = partial
            for rel, expected in PINS.items():
                actual = sha256(source / rel)
                identity.setdefault("verified", {})[rel] = actual
                if actual != expected:
                    raise RuntimeError(f"pinned file SHA-256 mismatch: {rel}")
            write_json(OUT / "run_identity.json", identity)
            stage = "julia_installation"
            julia = install_julia(base)
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1", "G2_BACKEND": "cuda"})
            env.pop("G2_DRYRUN_T_END", None)
            project = f"--project={source / PROJECT}"
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(INSTANTIATE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "measurement"
            args = [str(julia), project, str(source / SCRIPT), str(source / PHI_RAW), PHI_SHA256, str(OUT)]
            for name, digest in DIRECTION_INPUTS:
                args += [str(source / INPUT_DIR / f"{name}.dir_f4_fortran.raw"), digest]
            code = run(args, OUT / "measurement.log", env, min(SCRIPT_TIMEOUT_S, remaining(started)))
            identity["spike_exit_code"] = code
            write_json(OUT / "run_identity.json", identity)
            if code != 0:
                raise RuntimeError(f"measurement script exited {code}")
        stage = "completed"
        identity["failure_stage"] = None
        write_json(OUT / "run_identity.json", identity)
    except BaseException:
        failed = True
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("G2 measurement script returned 0; run the host terminal verifier before any analysis.\n")
        files = {p.name: sha256(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
