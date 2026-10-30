#!/usr/bin/env python3
"""Run GRAD-TA1 (tie-averaged forward-AD bridge, QuickTie(1f-5), Dual width 1, full window) on Kaggle T4 (measurement; no dataset, no qualification).

Fail-closed: a run whose script returned 0 (COMPLETE) or 3 (BLOCKED, intact) writes DONE and exits 0; any other failure writes ERROR.txt, never DONE, and exits non-zero.
The host analyzer (scripts/analyze_grad_ta1.py) decides the verdict from the pinned freeze.  Rendered from scripts/grad_ta1_runner_template.py by scripts/build_grad_ta1_kernel.py.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

SOURCE_COMMIT = "28d2c012b4a61cb02384b0a75ba6c5a92ec68b94"
SOURCE_TREE_ID = "692a84db7443f7b74f71b4051e61f1ccf6dc6427"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grad-ta1"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCRIPT = "scripts/waterlily_grad_ta1_2026_10_15.jl"
PHI_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
PHI_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
INPUT_DIR = "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
DIRECTION_INPUTS = (  # fixed order = run order (D0 first: the known blower, the pilot)
    ("D0_interface_offset", "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"),
    ("D1_filtered_seed11", "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87"),
    ("D2_filtered_seed2026", "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de"),
    ("P1_upstream_lobe", "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc"),
)
PINS = {'docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw': 'e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw': 'd0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D1_filtered_seed11.dir_f4_fortran.raw': '96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D2_filtered_seed2026.dir_f4_fortran.raw': '2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/P1_upstream_lobe.dir_f4_fortran.raw': '24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc', 'julia/CFDSDFWaterLily/src': '9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85', 'julia/CFDSDFWaterLilyT4/Manifest.toml': 'c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707', 'julia/CFDSDFWaterLilyT4/Project.toml': 'e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194', 'scripts/quick_tie.jl': '865f31f9b0f359f3d0293405c2b6908cdda017b47e24685dc9d558db61cb96e3', 'scripts/waterlily_grad_ta1_2026_10_15.jl': '3fe08e42054cef3821a01240d5a7d5beb1c781b0939e7f8d974b03527faa1b15'}
SPARSE = ["julia", "scripts", INPUT_DIR, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs"]
OUT = Path("/kaggle/working/grad_ta1")
INSTANTIATE_TIMEOUT_S = 3600
SCRIPT_TIMEOUT_S = 9600
KERNEL_TIMEOUT_S = 10800  # 3 h; must equal the `kaggle kernels push --timeout` value
MARGIN_S = 300            # leave time to write ERROR.txt and the manifest before Kaggle kills the kernel
ACCEPTED_EXIT_CODES = (0, 3)   # 0 COMPLETE, 3 BLOCKED (intact output; the analyzer reports it)
DRYRUN_SWITCHES = ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT")


def sha256(path):
    path = Path(path)
    if path.is_dir():  # a tree hash: SHA-256 over the sorted "relative path  file hash" lines
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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
    tree = subprocess.check_output(git + ["rev-parse", "HEAD^{tree}"], text=True).strip()
    if tree != SOURCE_TREE_ID:
        raise RuntimeError(f"source tree id {tree} != pinned {SOURCE_TREE_ID}")
    return source, fetched


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    stage = "gpu_inventory"
    identity = {"source_commit": SOURCE_COMMIT, "source_tree_id": SOURCE_TREE_ID, "kernel_id": KERNEL_ID, "runner_sha256": sha256(__file__), "pins": PINS,
                "phi_sha256": PHI_SHA256, "direction_sha256": dict(DIRECTION_INPUTS), "failure_stage": None}
    write_json(OUT / "run_identity.json", identity)
    failed = False
    try:
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        if not gpu.strip() or any("Tesla T4" not in row for row in gpu.strip().splitlines()):
            raise RuntimeError("requested T4 worker was not present")
        with tempfile.TemporaryDirectory(prefix="grad-ta1-", dir="/kaggle/working") as temp:
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
            for key in DRYRUN_SWITCHES:
                env.pop(key, None)
            project = f"--project={source / PROJECT}"
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(INSTANTIATE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "measurement"  # the script's first action is the 20-step QuickTie-vs-quick Dual preflight (INCOMPLETE if it fails)
            args = [str(julia), project, str(source / SCRIPT), str(source / PHI_RAW), PHI_SHA256, str(OUT)]
            for name, digest in DIRECTION_INPUTS:
                args += [str(source / INPUT_DIR / f"{name}.dir_f4_fortran.raw"), digest]
            code = run(args, OUT / "measurement.log", env, min(SCRIPT_TIMEOUT_S, remaining(started)))
            identity["spike_exit_code"] = code
            write_json(OUT / "run_identity.json", identity)
            if code not in ACCEPTED_EXIT_CODES:
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
            (OUT / "DONE").write_text("GRAD-TA1 script returned 0 (COMPLETE) or 3 (BLOCKED); run the host analyzer (scripts/analyze_grad_ta1.py) once.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
