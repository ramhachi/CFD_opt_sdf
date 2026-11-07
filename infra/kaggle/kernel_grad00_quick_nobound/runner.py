#!/usr/bin/env python3
"""Run GRAD-00 (one convection scheme, Dual width 1, full window, central FD) on Kaggle T4 (measurement; no dataset, no qualification).

Fail-closed: a run whose script returned 0 (COMPLETE) or 3 (BLOCKED, intact) writes DONE and exits 0; any other failure writes ERROR.txt, never DONE, and exits non-zero.
The host analyzer (scripts/analyze_grad00.py) applies exploratory labels from the explicit reference, without registering or qualifying the study.  Rendered from frozen scripts/grad_ta1_runner_template.py by scripts/build_grad00_kernels.py.
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

SOURCE_COMMIT = "da28dba4bf5476c7df3eec800d738f5d08c202aa"
SOURCE_TREE_ID = "092a2a1f9781842d5ed52c9b6163d84a23f25579"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grad00-quick-nobound"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCRIPT = 'scripts/waterlily_grad00_lambda_2026_11.jl'
PHI_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
PHI_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
INPUT_DIR = "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs"
DIRECTION_INPUTS = (  # fixed order = run order (D0 first: the known blower, the pilot)
    ("D0_interface_offset", "d0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549"),
    ("D1_filtered_seed11", "96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87"),
    ("D2_filtered_seed2026", "2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de"),
    ("P1_upstream_lobe", "24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc"),
)
PINS = {'docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw': 'e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431', 'docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_analysis.json': '3da59ac9b1086ed286cb0109cd669dac804f4fb99785986515ce35db1acf0466', 'docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json': '31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be', 'docs/evidence/grad00_lambda_2026_11/reference.json': 'f0f5f77c3ae80d94028970e928f430daf9356d3dae4fd7ce3a720c24f8ade5f7', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw': 'd0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D1_filtered_seed11.dir_f4_fortran.raw': '96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D2_filtered_seed2026.dir_f4_fortran.raw': '2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/P1_upstream_lobe.dir_f4_fortran.raw': '24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc', 'julia/CFDSDFWaterLily/src': '9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85', 'julia/CFDSDFWaterLilyT4/Manifest.toml': 'c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707', 'julia/CFDSDFWaterLilyT4/Project.toml': 'e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194', 'scripts/analyze_grad00.py': 'da28523625ff3899645684b5919dd52f2789013d8568ecf2326bb714875aa474', 'scripts/build_grad00_kernels.py': 'fff40ee0b881bbc4ecf005c033fd4ae902a5d85f6c4b95f0153d024dce2f933f', 'scripts/build_grad_ta1_kernel.py': 'ee79780a0cace1898f5cd1e6a1039697cc9a1ac96cff43f53e96a7fbfd3241d5', 'scripts/build_lowdim04a_kernel.py': 'dd06e1f9d2f7b2debcc39b1bcc504e9a2814d4a5b934ad5a6d1b10e23490c2ea', 'scripts/grad00_reference_from_fd08.py': 'd7a018ffe31e14dbcec01e837e38f6ec429a1235bda597cb85ab5a52ab80c153', 'scripts/grad_g2_window.py': 'f2f3fe5b91cd4f3d0da1fc2c61e0ff97e53e6ae575fca878cacb3bc60add6f7c', 'scripts/grad_ta1_runner_template.py': '90b8455da24a0c4c9a0920962a16ec7f2b757071ff6ee6ec34ea61ac598394dd', 'scripts/quick_nobound.jl': '14158bb32958c9e501c2e92764ab49980a19036acce26630640b9808db2e4698', 'scripts/quick_tie.jl': '865f31f9b0f359f3d0293405c2b6908cdda017b47e24685dc9d558db61cb96e3', 'scripts/vanleer_safe.jl': '2a964c56415c32ad6bf58c739fdcc3ec5cd4c5490b77f73749858ae2b86ab56b', 'scripts/verify_grad_g2_terminal.py': '003b68ae7265fa53754a32da64009ecb3d4eed878be59191d89a3e21c15695e4', 'scripts/waterlily_grad00_lambda_2026_11.jl': 'bba320e88553bfa026afb715572166c936c763be81a537c601fe59300d15cdbe', 'scripts/waterlily_grad_ta1_2026_10_15.jl': '3fe08e42054cef3821a01240d5a7d5beb1c781b0939e7f8d974b03527faa1b15'}
ARM = 'quick_nobound'
REFERENCE = {'path': 'docs/evidence/grad00_lambda_2026_11/reference.json', 'sha256': 'f0f5f77c3ae80d94028970e928f430daf9356d3dae4fd7ce3a720c24f8ade5f7', 'definition': 'epsilon_m = the largest of the three FD-08 v2 formal interior epsilons of the direction (formal_analysis.json comparisons, all PASS); spread_n_per_m = the FD-08 Model A calibration standard error of the gradient se_g_n_per_m (formal_criteria.json calibration_binding.fits), fx from the drag fit, fz from the downforce fit. Fixed before any GRAD-00 run (GRAD-00 spec amendment 1, 2026-11-06).', 'sources': {'docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_analysis.json': '3da59ac9b1086ed286cb0109cd669dac804f4fb99785986515ce35db1acf0466', 'docs/evidence/fd08_v2_formal_2026_10_07_amend3/formal_criteria.json': '31b29cccc9d3fd6912a910b09694a8230f9ee0aa84e6a418161881ffbcf907be'}, 'directions': {'D0_interface_offset': {'epsilon_m': 0.003971641173621408, 'spread_n_per_m': {'fx': 0.003340882961506817, 'fz': 0.02060014270961251}}, 'D1_filtered_seed11': {'epsilon_m': 0.003971641173621408, 'spread_n_per_m': {'fx': 0.0023411868563410834, 'fz': 0.003321700208349783}}, 'D2_filtered_seed2026': {'epsilon_m': 0.003971641173621408, 'spread_n_per_m': {'fx': 0.004788957134019947, 'fz': 0.0029913937716240396}}, 'P1_upstream_lobe': {'epsilon_m': 0.003971641173621408, 'spread_n_per_m': {'fx': 0.005882931182735196, 'fz': 0.010178941059118983}}}}
SPARSE = ["julia", "scripts", INPUT_DIR, "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs"]
OUT = Path("/kaggle/working/grad00_quick_nobound")
INSTANTIATE_TIMEOUT_S = 3600
SCRIPT_TIMEOUT_S = 9600
KERNEL_TIMEOUT_S = 10800  # 3 h; must equal the `kaggle kernels push --timeout` value
MARGIN_S = 300            # leave time to write ERROR.txt and the manifest before Kaggle kills the kernel
ACCEPTED_EXIT_CODES = (0, 3)   # 0 COMPLETE, 3 BLOCKED (intact output; the analyzer reports it)
DRYRUN_SWITCHES = ("G2_DRYRUN_T_END", "TA1_PREFLIGHT_ONLY", "TA1_BLOCK_LIMIT", "GRAD00_PREFLIGHT_ONLY")


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
    patterns = ["/" + p + "/" for p in SPARSE]
    if REFERENCE is not None:
        patterns += ["/" + REFERENCE["path"], *("/" + p for p in REFERENCE["sources"])]
    (source / ".git/info/sparse-checkout").write_text("\n".join(patterns) + "\n")
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


def verify_terminal(code):
    expected_status = {0: "COMPLETE", 3: "BLOCKED"}[code]
    expected_runs = {"plain", *(name + suffix for name, _ in DIRECTION_INPUTS for suffix in ("", "__plus", "__minus"))}
    for filename in ("g2_run_index.json", "grad00_index.json"):
        index = json.loads((OUT / filename).read_text())
        if (index["status"] != expected_status or index["arm"] != ARM or index["real_type"] != "Float32"
                or index["backend"] != "cuda" or index["preflight"]["pass"] is not True):
            raise RuntimeError(f"{filename}: exit status, arm, runtime or preflight mismatch")
        statuses = index["run_status"]
        if set(index["runs"]) != expected_runs or set(statuses) != expected_runs:
            raise RuntimeError(f"{filename}: incomplete 13-run inventory")
        for name, status in statuses.items():
            allowed = ("COMPLETE", "BLOCKED") if name in dict(DIRECTION_INPUTS) else ("COMPLETE",)
            if status not in allowed:
                raise RuntimeError(f"{filename}: invalid run status for {name}")
        if ("BLOCKED" in statuses.values()) != (code == 3):
            raise RuntimeError(f"{filename}: BLOCKED status does not match exit code")


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    stage = "reference_configuration"
    identity = {"source_commit": SOURCE_COMMIT, "source_tree_id": SOURCE_TREE_ID, "kernel_id": KERNEL_ID, "runner_sha256": sha256(__file__), "pins": PINS,
                "phi_sha256": PHI_SHA256, "direction_sha256": dict(DIRECTION_INPUTS), "failure_stage": None, "arm": ARM, "reference": REFERENCE}
    write_json(OUT / "run_identity.json", identity)
    failed = False
    try:
        if REFERENCE is None:
            raise RuntimeError("GRAD-00 FD-08 epsilon/plateau-spread reference is not configured; render again with --reference after its definition is supplied")
        stage = "gpu_inventory"
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        if not gpu.strip() or any("Tesla T4" not in row for row in gpu.strip().splitlines()):
            raise RuntimeError("requested T4 worker was not present")
        with tempfile.TemporaryDirectory(prefix="grad00-", dir="/kaggle/working") as temp:
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
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1", "G2_BACKEND": "cuda", "GRAD00_ARM": ARM, "GRAD00_T": "Float32"})
            for key in DRYRUN_SWITCHES:
                env.pop(key, None)
            project = f"--project={source / PROJECT}"
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(INSTANTIATE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "measurement"  # unchanged 20-step finite-primal/tangent preflight; quick also checks its control bytes
            args = [str(julia), project, str(source / SCRIPT), str(source / PHI_RAW), PHI_SHA256, str(OUT)]
            for name, digest in DIRECTION_INPUTS:
                args += [str(source / INPUT_DIR / f"{name}.dir_f4_fortran.raw"), digest]
            args += [str(REFERENCE["directions"][name]["epsilon_m"]) for name, _ in DIRECTION_INPUTS]
            code = run(args, OUT / "measurement.log", env, min(SCRIPT_TIMEOUT_S, remaining(started)))
            identity["spike_exit_code"] = code
            write_json(OUT / "run_identity.json", identity)
            if code not in ACCEPTED_EXIT_CODES:
                raise RuntimeError(f"measurement script exited {code}")
            stage = "terminal_verification"
            verify_terminal(code)
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
            (OUT / "DONE").write_text("GRAD-00 script returned 0 (COMPLETE) or 3 (BLOCKED); run the host analyzer (scripts/analyze_grad00.py) once.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
