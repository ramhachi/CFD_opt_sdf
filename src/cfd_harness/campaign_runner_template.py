#!/usr/bin/env python3
"""harness v1.1 pinned worker for one kernel of a WaterLily T4 campaign (rendered by scripts/harness.py into infra/kaggle/kernel_<campaign>_<k>/runner.py).

Everything campaign-specific is read from the pinned campaign.json of the pinned source commit (its SHA-256 is in PINS); only the PIN block below differs between a formal and a smoke render.
Behaviour equals the proven GRID-02 runner: GPU inventory, sparse checkout and pin verification, Julia install, Pkg.instantiate, the JSON3-free CUDA probe (Tesla T4 only, physical index 0,
singleton UUID), per-state job with per-state/aggregate/kernel budgets, index + manifest, DONE xor ERROR.  Added: a stage-0 self-test before any Julia work and an optional first-state byte gate.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

HARNESS_VERSION = "harness v1.1"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
SCHEMA_REL = "src/cfd_harness/campaign_schema.py"
# --- PIN BEGIN (the only lines that differ between a formal and a smoke render) ---
PIN_BLOCK
# --- PIN END ---
OUT = Path(os.environ.get("CAMPAIGN_WORK_ROOT", "/kaggle/working")) / OUT_DIR_NAME  # Kaggle default; another GPU backend sets CAMPAIGN_WORK_ROOT
GPU_PROBE_CODE = '''
using CUDA
@assert CUDA.functional()
devs = collect(CUDA.devices())
id(d) = "GPU-" * string(CUDA.uuid(d))
Q = string(Char(34))
q(x) = (s = string(x); @assert !occursin(Q, s) && !occursin(string(Char(92)), s); Q * s * Q)
arr(v) = "[" * join(q.(v), ",") * "]"
kv(k, v) = q(k) * ":" * v
json = "{" * join([
    kv("logical_device_count", string(length(devs))),
    kv("visible_gpu_names", arr([CUDA.name(d) for d in devs])),
    kv("visible_gpu_uuids", arr([id(d) for d in devs])),
    kv("default_device_uuid", q(id(CUDA.device()))),
    kv("cuda_device_order", q(ENV["CUDA_DEVICE_ORDER"])),
    kv("cuda_visible_devices", q(ENV["CUDA_VISIBLE_DEVICES"])),
], ",") * "}"
open(ENV["GRID01_GPU_PROBE_OUT"], "w") do io
    println(io, json)
end
'''


def sha256(path):
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"))
        return hashlib.sha256(("\n".join(f"{p.relative_to(path)}  {sha256(p)}" for p in files) + "\n").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def write_manifest(out):
    files = {str(p.relative_to(out)): sha256(p) for p in sorted(Path(out).rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
    write_json(Path(out) / "output_manifest.json", {"files": files})


def nvidia_smi():
    return subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)


def run(args, log_path, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as log:
        result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    for line in Path(log_path).read_text(errors="replace").splitlines()[-30:]:
        print(line, flush=True)
    return result.returncode


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
    (source / ".git/info/sparse-checkout").write_text("\n".join("/" + p for p in SPARSE) + "\n")
    fetched = subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT])
    if fetched.returncode:
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError(f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    return source


def load_schema(source):
    spec = importlib.util.spec_from_file_location("campaign_schema", source / SCHEMA_REL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_phi(S, row, baseline_phi, directions):
    """Regenerate one state's phi from the pinned baseline and direction raws and verify every identity field of the campaign row (both byte orders)."""
    import numpy as np

    phi = baseline_phi if row["direction"] is None else S.perturb(baseline_phi, directions[row["direction"]], row["step_mm"], row["sign"])
    if not np.all(np.isfinite(phi)):
        raise RuntimeError("generated phi has non-finite values")
    raw = S.to_raw(phi)
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError("generated phi differs from the campaign (Fortran-order SHA)")
    if hashlib.sha256(np.asarray(phi, dtype="<f4").tobytes(order="C")).hexdigest() != row["phi_c_order_sha256"]:
        raise RuntimeError("generated C-order phi differs from the campaign")
    changed = int(np.count_nonzero(phi != baseline_phi))
    max_change = float(np.max(np.abs(phi.astype(np.float64) - baseline_phi.astype(np.float64))))
    if changed != row["changed_node_count"] or abs(max_change - row["maximum_pointwise_change_m"]) > 1.0e-12:
        raise RuntimeError("generated state change metrics differ from the campaign")
    return raw


def schema_dry_write(SC, tmp):
    """Write a synthetic index, force CSV and manifest through the runner's own writers and read them back through the schema's checks."""
    tmp = Path(tmp)
    row = {"kind": "parent", "direction": None, "step_mm": 0.0, "sign": 0}
    index = SC.new_index("selftest", "owner/selftest", "case")
    index["states"].append(SC.index_entry("s0", row, 0, 1.0, "0" * 64, True))
    SC.validate_index(index)
    write_json(tmp / "index.json", index)
    (tmp / "case.forces.csv").write_text(",".join(SC.FORCE_COLUMNS) + "\n")
    write_manifest(tmp)
    SC.check_manifest(tmp, ["index.json", "case.forces.csv"])
    SC.selftest_force_check()


def remaining(started, kernel_timeout_s, margin_s):
    left = kernel_timeout_s - margin_s - (time.time() - started)
    if left <= 60:
        raise RuntimeError("kernel time budget exhausted")
    return left


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=False)
    stage = "gpu_inventory"
    identity = {"runner_sha256": sha256(__file__), "python_version": sys.version, "numpy_version": None, "platform": " ".join(os.uname()), "kernel": KERNEL, "kernel_id": KERNEL_ID,
                "source_commit": SOURCE_COMMIT, "pins": PINS, "direction_files": {}, "config": None, "expected_names": None, "case_id": None, "failure_stage": None,
                "harness_version": HARNESS_VERSION, "campaign_sha256": PINS[CAMPAIGN], "smoke": SMOKE,
                "campaign_work_root": os.environ.get("CAMPAIGN_WORK_ROOT", "/kaggle/working")}
    index = {"kernel": KERNEL, "kernel_id": KERNEL_ID, "case_id": None, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / INDEX_NAME, index)
    failed = False
    try:
        import numpy as np
        identity["numpy_version"] = np.__version__
        gpu = nvidia_smi()
        (OUT / "nvidia_smi.csv").write_text(gpu)
        with tempfile.TemporaryDirectory(prefix="harness-", dir=OUT.parent) as temp:
            base = Path(temp)
            stage = "source_checkout"
            source = fetch_source(base)
            verified = {}
            for rel, expected in PINS.items():
                verified[rel] = sha256(source / rel)
                if verified[rel] != expected:
                    raise RuntimeError(f"pinned file SHA-256 mismatch: {rel}")
            identity["verified"] = verified
            write_json(OUT / "run_identity.json", identity)
            stage = "self_test"
            sys.path.insert(0, str(source / "scripts"))
            SC = load_schema(source)
            import step01_states as S
            from grid01_gpu import select_worker_gpu
            campaign = SC.jload(source / CAMPAIGN)
            SC.validate_campaign(campaign)
            if campaign["harness_version"] != HARNESS_VERSION or SC.HARNESS_VERSION != HARNESS_VERSION:
                raise RuntimeError("harness version differs between the runner, the schema and the campaign")
            kernel = campaign["kernels"][KERNEL]
            if kernel["kernel_id"] + ("-smoke" if SMOKE else "") != KERNEL_ID or SC.out_dir_name(campaign, KERNEL) != OUT_DIR_NAME or SC.index_name(campaign) != INDEX_NAME:
                raise RuntimeError("the baked kernel identity or output names differ from the campaign")
            cfg, case_id, job = kernel["config"], kernel["case"]["case_id"], kernel["job"]
            names = SC.run_names(kernel)[:1] if SMOKE else SC.run_names(kernel)
            runs = {r["state"]: r for r in kernel["runs"]}
            for rel, want in [(campaign["baseline"]["path"], campaign["baseline"]["sha256_fortran_raw"])] + [(d["path"], d["sha256_fortran_raw"]) for d in campaign["directions"].values()]:
                if PINS.get(rel) != want:
                    raise RuntimeError(f"the baseline or a direction raw is not pinned to the campaign hash: {rel}")
            if job not in PINS or CAMPAIGN not in PINS or SCHEMA_REL not in PINS:
                raise RuntimeError("the job, the campaign or the schema is not pinned")
            identity.update(direction_files={n: PINS[d["path"]] for n, d in campaign["directions"].items()}, config=cfg, expected_names=names, case_id=case_id)
            index["case_id"] = case_id
            selected_gpu = select_worker_gpu(gpu)
            gpu_uuid = selected_gpu["uuid"]
            identity.update(selected_gpu=selected_gpu, cuda_device_order="PCI_BUS_ID", cuda_visible_devices="0")
            write_json(OUT / "run_identity.json", identity)
            write_json(OUT / INDEX_NAME, index)
            baseline_phi = S.read_f4(source / campaign["baseline"]["path"])
            directions = {n: S.read_f4(source / d["path"]) for n, d in campaign["directions"].items()}
            if not all(np.all(np.isfinite(a)) for a in [baseline_phi, *directions.values()]):
                raise RuntimeError("baseline or direction phi has non-finite values")
            raws = {n: generate_phi(S, campaign["states"][n], baseline_phi, directions) for n in names}
            with tempfile.TemporaryDirectory(prefix="dry-", dir=base) as dry:
                schema_dry_write(SC, dry)
            self_test = {"harness_version": HARNESS_VERSION, "imports": True, "schema_dry_write": True, "phi_identities_verified": len(raws), "gpu_probe": False}
            julia = install_julia(base)
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1"})
            project = f"--project={source / PROJECT}"
            margin = cfg["reserve_s"]
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(cfg["instantiate_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                if sha256(source / PROJECT / rel) != PINS[f"{PROJECT}/{rel}"]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "observed_cuda_device_probe"
            probe_env = dict(env, GRID01_GPU_PROBE_OUT=str(OUT / "gpu_device_probe.json"))
            if run([str(julia), "--startup-file=no", project, "-e", GPU_PROBE_CODE], OUT / "gpu_device_probe.log", probe_env, min(cfg["gpu_probe_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin))):
                raise RuntimeError("independent CUDA device UUID probe failed")
            observed = json.loads((OUT / "gpu_device_probe.json").read_text())
            expected_device = dict(SC.GPU_EXPECTED, visible_gpu_uuids=[gpu_uuid], default_device_uuid=gpu_uuid)
            if observed != expected_device:
                raise RuntimeError("observed CUDA singleton/default UUID differs from selected physical GPU")
            self_test["gpu_probe"] = True
            write_json(OUT / "self_test.json", self_test)
            solver_elapsed_s = 0.0
            for position, name in enumerate(names):
                row, run_spec = campaign["states"][name], runs[name]
                stage = f"state:{name}"
                outdir = OUT / "states" / name
                outdir.mkdir(parents=True, exist_ok=False)
                phi_path = base / (name + ".phi.f32f")
                phi_path.write_bytes(raws[name])
                t0 = time.time()
                code = run([str(julia), "--startup-file=no", project, str(source / job), str(phi_path), str(outdir)], outdir / "job.log", SC.job_env(campaign, run_spec, row, env, gpu_uuid),
                           min(cfg["per_state_timeout_s"], remaining(started, cfg["kernel_timeout_s"], margin), cfg["solver_wall_time_cap_s"] - solver_elapsed_s))
                resolved_phi = phi_path.resolve()
                if resolved_phi.parent != base.resolve() or resolved_phi.name != name + ".phi.f32f":
                    raise RuntimeError("unexpected temporary phi cleanup target")
                resolved_phi.unlink()
                csv = outdir / SC.forces_name(case_id)
                seconds = time.time() - t0
                complete = code == 0 and csv.is_file() and (outdir / "W4_JOB_DONE").is_file() and (outdir / SC.summary_name(case_id)).is_file()
                entry = SC.index_entry(name, row, code, seconds, sha256(csv) if csv.is_file() else None, complete)
                gate = kernel.get("first_state_csv_sha256") if position == 0 else None
                if gate:
                    entry["matches_retained_parent_reference"] = entry["forces_csv_sha256"] == gate
                solver_elapsed_s += seconds
                index["solver_process_wall_seconds_total"] = solver_elapsed_s
                index["states"].append(entry)
                write_json(OUT / INDEX_NAME, index)
                if seconds > cfg["per_state_timeout_s"] or solver_elapsed_s > cfg["solver_wall_time_cap_s"]:
                    raise RuntimeError("registered per-state or aggregate solver wall-time budget exceeded")
                if not complete:
                    raise RuntimeError(f"state did not complete: {name} (exit {code})")
                if position == 0:
                    index["parent_forces_csv_sha256"] = entry["forces_csv_sha256"]
                    write_json(OUT / INDEX_NAME, index)
                    if gate and not entry["matches_retained_parent_reference"]:
                        raise RuntimeError("first-state force CSV differs from the pinned historical CSV")
            if [entry["name"] for entry in index["states"]] != names:
                raise RuntimeError("completed state sequence differs from the registered plan")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        SC.validate_index(index, terminal=True)
        SC.validate_identity(identity)
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / INDEX_NAME, index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / INDEX_NAME, index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("all registered states of this kernel completed; host integrity (scripts/harness.py verify) and the campaign analysis are still required.\n")
        write_manifest(OUT)
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
