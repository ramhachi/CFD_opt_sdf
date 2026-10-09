#!/usr/bin/env python3
"""LOWDIM-02A (#49) Kaggle T4 runner template: the flow_32 baseline, its repeat, the LOWDIM-01 accepted +1.25 mm step, its reverse control and +2.5 mm (descriptive), each with the flow_32 copy of the XFID job.

`scripts/build_lowdim02a_kernel.py` fills the placeholders (source commit, SHA pins) and writes infra/kaggle/kernel_lowdim02a_a/runner.py.
No dataset: the runner regenerates every phi with the numpy function of scripts/step01_states.py (== cfd_sdf construct_state) along the pinned LOWDIM-02A proposal direction, verifies its SHA-256 against
the pinned inventory, and runs `scripts/waterlily_lowdim02_flow32_job.jl <phi> <outdir>` once per state.  The baseline is the first state; its flow_32 force CSV must be
byte identical to the W4 v17 round-2 retained flow_32.forces.csv or the kernel stops (fail closed).  DONE is written only when every state completed.  Observation only; the verdict is the host analyzer's.
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

KERNEL = "PIN_KERNEL"
SOURCE_COMMIT = "PIN_SOURCE_COMMIT"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
JOB = "scripts/waterlily_lowdim02_flow32_job.jl"
STATES_MODULE = "scripts/step01_states.py"
EVIDENCE = "docs/evidence/lowdim02a_flow32_cross_grid_2026_10_09"
LOWDIM01_EVIDENCE = "docs/evidence/lowdim01_four_direction_capability_2026_10_09"
INVENTORY = f"{EVIDENCE}/inventory.json"
SRC_TREE = "julia/CFDSDFWaterLily/src"
PROPOSAL_RAW = f"{LOWDIM01_EVIDENCE}/inputs/proposal_downforce.dir_f4_fortran.raw"
BASELINE_DIR = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs"
BASELINE_RAW = f"{BASELINE_DIR}/cal_baseline_01.phi_f4_fortran.raw"
PINS = {
    f"{PROJECT}/Project.toml": "PIN_T4_PROJECT_SHA",
    f"{PROJECT}/Manifest.toml": "PIN_T4_MANIFEST_SHA",
    JOB: "PIN_JOB_SHA",
    STATES_MODULE: "PIN_STATES_SHA",
    PROPOSAL_RAW: "PIN_PROPOSAL_SHA",
    INVENTORY: "PIN_INVENTORY_SHA",
    SRC_TREE: "PIN_SRC_TREE_SHA",
    BASELINE_RAW: "PIN_BASELINE_RAW_SHA",
}
DIRECTION_FILES = {}                           # the candidates use only the pinned proposal direction (no basis directions are read on the kernel)
FLOW32_BASELINE_CSV_SHA256 = "PIN_FLOW32_BASELINE_CSV_SHA"
SPARSE = ["julia", "scripts", BASELINE_DIR, EVIDENCE, f"{LOWDIM01_EVIDENCE}/inputs"]
OUT = Path(f"/kaggle/working/lowdim02a_{KERNEL}")
INSTANTIATE_TIMEOUT_S = 1800
PER_STATE_TIMEOUT_S = 2400                    # flow_32 took 336 s in W4 v17 round 2; generous margin
KERNEL_TIMEOUT_S = int("PIN_KERNEL_TIMEOUT_S")  # must equal the `kaggle kernels push --timeout` value
MARGIN_S = 300


def sha256(path):
    path = Path(path)
    if path.is_dir():   # a tree hash: SHA-256 over the sorted "relative path  file hash" lines
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def run(args, log_path, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as log:
        result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    for line in Path(log_path).read_text(errors="replace").splitlines()[-30:]:
        print(line, flush=True)
    return result.returncode


def remaining(started):
    left = KERNEL_TIMEOUT_S - MARGIN_S - (time.time() - started)
    if left <= 60:
        raise RuntimeError("kernel time budget exhausted")
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
    if subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT]).returncode != 0:
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError(f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    return source


def state_env(base_env, inventory, row, gpu_uuid):
    env = dict(base_env)
    env.update(inventory["job_env_common"])
    env.update({"W4_SELECTED_GPU_UUID": gpu_uuid, "W4_STATE_SHA256": row["state_sha256"], "W4_STATE_NPZ_SHA256": row["npz_sha256"],
                "W4_PHI_C_ORDER_SHA256": row["phi_c_order_sha256"], "W4_PHI_FORTRAN_SHA256": row["phi_fortran_order_sha256"],
                "W4_EXPECTED_MARGIN_M": str(row["zero_level_margin_m"])})
    return env


def generate_phi(S, source, inventory, row):
    """The perturbed phi bytes of one registered state (the same numpy function as the host registrar), verified against the pinned inventory."""
    import numpy as np
    phi = S.read_f4(source / BASELINE_RAW)
    if row["kind"] in ("baseline", "baseline_repeat"):
        raw = S.to_raw(phi)
    else:
        d = S.read_f4(source / PROPOSAL_RAW)
        raw = S.to_raw(S.perturb(phi, d, row["step_mm"], row["sign"]))
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError(f"generated phi differs from the registered inventory: {row['name']}")
    if row["kind"] not in ("baseline", "baseline_repeat"):
        changed = int(np.count_nonzero(np.frombuffer(raw, dtype="<f4") != np.frombuffer(S.to_raw(phi), dtype="<f4")))
        if changed != row["changed_node_count"]:
            raise RuntimeError(f"changed node count differs from the registered inventory: {row['name']}")
    return raw


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    stage = "gpu_inventory"
    try:
        import numpy
        numpy_version = numpy.__version__
    except ImportError:
        numpy_version = None
    identity = {"runner_sha256": sha256(__file__), "python_version": sys.version, "numpy_version": numpy_version, "platform": " ".join(os.uname()),
                "kernel": KERNEL, "source_commit": SOURCE_COMMIT, "pins": PINS, "direction_files": DIRECTION_FILES, "flow32_baseline_csv_sha256": FLOW32_BASELINE_CSV_SHA256, "failure_stage": None}
    index = {"kernel": KERNEL, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / "lowdim02a_index.json", index)
    failed = False
    try:
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        rows = [r.strip() for r in gpu.strip().splitlines()]
        if not rows or any("Tesla T4" not in r for r in rows):
            raise RuntimeError("requested T4 worker was not present")
        gpu_uuid = rows[0].split(",")[2].strip()
        with tempfile.TemporaryDirectory(prefix="lowdim02a-", dir="/kaggle/working") as temp:
            base = Path(temp)
            stage = "source_checkout"
            source = fetch_source(base)
            for rel, expected in {**PINS, **DIRECTION_FILES}.items():
                actual = sha256(source / rel)
                identity.setdefault("verified", {})[rel] = actual
                if actual != expected:
                    raise RuntimeError(f"pinned file SHA-256 mismatch: {rel}")
            write_json(OUT / "run_identity.json", identity)
            sys.path.insert(0, str(source / "scripts"))
            import step01_states as S
            inventory = json.loads((source / INVENTORY).read_text())
            by_name = {r["name"]: r for r in inventory["states"] if r["kernel"] == KERNEL}
            plan = [{"name": n} for n in inventory["kernels"][KERNEL]]
            if set(by_name) != {p["name"] for p in plan}:
                raise RuntimeError("the state plan differs from the registered inventory")
            if by_name[plan[0]["name"]]["kind"] != "baseline" or sum(r["kind"] == "baseline" for r in by_name.values()) != 1:
                raise RuntimeError("the first registered state must be the single baseline")
            stage = "julia_installation"
            julia = install_julia(base)
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1"})
            project = f"--project={source / PROJECT}"
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(INSTANTIATE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            for item in plan:
                row = by_name[item["name"]]
                stage = f"state:{row['name']}"
                outdir = OUT / "states" / row["name"]
                outdir.mkdir(parents=True, exist_ok=False)
                raw = generate_phi(S, source, inventory, row)
                phi_path = base / (row["name"] + ".phi.f32f")
                phi_path.write_bytes(raw)
                t0 = time.time()
                code = run([str(julia), "--startup-file=no", project, str(source / JOB), str(phi_path), str(outdir)], outdir / "job.log",
                           state_env(env, inventory, row, gpu_uuid), min(PER_STATE_TIMEOUT_S, remaining(started)))
                phi_path.unlink()
                csv = outdir / "flow_32.forces.csv"
                entry = {"name": row["name"], "kind": row["kind"], "exit_code": code, "seconds": time.time() - t0,
                         "forces_csv_sha256": sha256(csv) if csv.is_file() else None, "complete": code == 0 and csv.is_file() and (outdir / "W4_JOB_DONE").is_file()
                         and (outdir / "flow_32.summary.json").is_file()}
                index["states"].append(entry)
                write_json(OUT / "lowdim02a_index.json", index)
                if not entry["complete"]:
                    raise RuntimeError(f"state did not complete: {row['name']} (exit {code})")
                if row["kind"] == "baseline":
                    entry["matches_w4_v17_flow32_baseline"] = entry["forces_csv_sha256"] == FLOW32_BASELINE_CSV_SHA256
                    write_json(OUT / "lowdim02a_index.json", index)
                    if not entry["matches_w4_v17_flow32_baseline"]:
                        raise RuntimeError("the baseline force CSV differs from the W4 v17 round-2 flow_32 baseline: the environment is not the registered one, stopping before any other state")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "lowdim02a_index.json", index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "lowdim02a_index.json", index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("every registered LOWDIM-02A state completed; host verification and the analyzer (which decides accept / reject) are still required.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
