#!/usr/bin/env python3
"""GRID-02 pinned worker (one of five kernels: parent or parent repeat first, then the registered OPT-01 v1 Stage B states for this grid and placement); reuses the amended GRID-01 GPU/runtime protocol.

No historical-baseline byte gate (none exists for these grids/placements): the first state's force CSV SHA is recorded in the index."""
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

KERNEL = "f16"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-grid02-f16"
SOURCE_COMMIT = "054a04df95691f533bd9c06939940c292a51ce4b"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
CASE_ID = "flow_16"
JOB = "scripts/waterlily_grid02_job.jl"
GRID02_JOB = "scripts/waterlily_grid02_job.jl"
EVIDENCE = "docs/evidence/grid02_trend_2026_10_16"
INVENTORY = f"{EVIDENCE}/inventory.json"
BASELINE_RAW = "docs/evidence/opt01b_stage_b_2026_10_15/inputs/parent.phi_f4_fortran.raw"  # the OPT-01 v1 parent (generation 1), Fortran-order Float32, under the OPT-01 Stage B evidence
PROPOSAL_RAW = "docs/evidence/opt01b_stage_b_2026_10_15/inputs/robust_opt01a.dir_f4_fortran.raw"  # the OPT-01 Stage A robust cross-grid direction (max-norm 1)
DIRECTIONS = {"robust_opt01a": PROPOSAL_RAW}
PINS = {'docs/evidence/grid02_trend_2026_10_16/inventory.json': '759587dde80684b4bacadeded4cbca7be450c539e39d8573d088f2de2779c379', 'docs/evidence/opt01b_stage_b_2026_10_15/inputs/parent.phi_f4_fortran.raw': '2f23be7824d31d6c270ada9b3ff2b815601b3435da78e4e7e9089908608bf3d7', 'docs/evidence/opt01b_stage_b_2026_10_15/inputs/robust_opt01a.dir_f4_fortran.raw': '32bb85a00370bcabcb8ecebed3b95482d329a8c56771e6085a2334d8049a4478', 'julia/CFDSDFWaterLily/src': '9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85', 'julia/CFDSDFWaterLilyT4/Manifest.toml': 'c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707', 'julia/CFDSDFWaterLilyT4/Project.toml': 'e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194', 'scripts/grid01_gpu.py': 'bfaed961f3136d14bdeb7e4fccfab807f5fb8c257b45cd3ebb875963104fff38', 'scripts/grid02_case.jl': '2210d56b51c3facba17b735102f5955c4b0068e19a728dba2f84ace68b0bafe1', 'scripts/step01_states.py': 'f3c5ea30cc88c5efe2cbdd8f96ceeb481321ebc0b84228b3287c6ab718b7ca87', 'scripts/waterlily_grid02_job.jl': '4d5a30b04820b5ab2adbe96a129cd0d3d77c3085035a7c3d337154ac6cfcf6ad'}
CONFIG = {'W4_CANONICAL_ORIGIN_M': '-1.0,-0.8,-0.6', 'canonical_origin_m': [-1.0, -0.8, -0.6], 'GRID02_CASE': 'flow_16', 'per_state_timeout_s': 900, 'solver_wall_time_cap_s': 7200, 'kernel_timeout_s': 10800, 'instantiate_timeout_s': 2400, 'gpu_probe_timeout_s': 300, 'reserve_s': 300}  # this kernel's runtime configuration, baked at render time and compared with the inventory's kernel_config
EXPECTED_NAMES = ['opt01b__parent', 'opt01b__prop__s0.3125mm', 'opt01b__prop__s0.625mm', 'opt01b__prop__s0.9375mm', 'opt01b__prop__s1.25mm', 'opt01b__ctrl_reverse__s0.625mm', 'opt01b__ctrl_reverse__s1.25mm', 'opt01b__parent_repeat']
IDENTITY_KEYS = ("state_sha256", "npz_sha256", "phi_fortran_order_sha256", "phi_c_order_sha256", "zero_level_margin_m", "changed_node_count", "maximum_pointwise_change_m")
ORIGINS = ("-1.0,-0.8,-0.6", "-0.9875,-0.7875,-0.6")  # native, shifted (h/2, h/2, 0)
SPARSE = ["julia/", "scripts/", "docs/evidence/opt01b_stage_b_2026_10_15/", "docs/evidence/grid02_trend_2026_10_16/"]
OUT = Path(f"/kaggle/working/grid02_{KERNEL}")
INSTANTIATE_TIMEOUT_S = CONFIG["instantiate_timeout_s"]
PER_STATE_TIMEOUT_S = CONFIG["per_state_timeout_s"]
SOLVER_WALL_TIME_CAP_S = CONFIG["solver_wall_time_cap_s"]  # states x per-state timeout
GPU_PROBE_TIMEOUT_S = CONFIG["gpu_probe_timeout_s"]
KERNEL_TIMEOUT_S = CONFIG["kernel_timeout_s"]  # must equal `kaggle kernels push --timeout`
MARGIN_S = CONFIG["reserve_s"]
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
        lines = [f"{p.relative_to(path)}  {hashlib.sha256(p.read_bytes()).hexdigest()}" for p in sorted(path.rglob("*")) if p.is_file()]
        return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def nvidia_smi():
    return subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)


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
    (source / ".git/info/sparse-checkout").write_text("\n".join("/" + p for p in SPARSE) + "\n")
    fetched = subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", SOURCE_COMMIT])
    if fetched.returncode:
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "origin", SOURCE_COMMIT], check=True)
    subprocess.run(git + ["checkout", "-q", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    if head != SOURCE_COMMIT:
        raise RuntimeError(f"checked-out commit {head} != pinned {SOURCE_COMMIT}")
    return source


def expected_plan(inventory):
    if inventory.get("kind") != "grid02_inventory" or inventory.get("stage_status") != "READY" or inventory.get("blockers"):
        raise ValueError("the inventory is not a READY GRID-02 inventory")
    rows, cfg = inventory.get("states"), inventory.get("kernel_config", {}).get(KERNEL)
    if not isinstance(rows, list) or not isinstance(cfg, dict) or inventory.get("kernels", {}).get(KERNEL) != EXPECTED_NAMES:
        raise ValueError("the inventory is not this kernel's registered state plan")
    if (cfg.get("kernel_id"), cfg.get("case_id"), cfg.get("job")) != (KERNEL_ID, CASE_ID, JOB) or {k: cfg.get(k) for k in CONFIG} != CONFIG:
        raise ValueError("the inventory's kernel configuration differs from the baked one")
    if CONFIG["W4_CANONICAL_ORIGIN_M"] not in ORIGINS or CONFIG["GRID02_CASE"] not in (None, CASE_ID) or (CONFIG["GRID02_CASE"] is None) != (JOB != GRID02_JOB):
        raise ValueError("unregistered placement origin or GRID02_CASE binding")
    if BASELINE_RAW not in PINS or PROPOSAL_RAW not in PINS or INVENTORY not in PINS or JOB not in PINS or inventory["parent"]["raw_path"] != BASELINE_RAW or inventory["proposal"]["file"] != PROPOSAL_RAW:
        raise ValueError("the parent raw, the direction, the inventory or the job is not pinned")
    if PINS[BASELINE_RAW] != inventory["parent"]["phi_fortran_order_sha256"] or PINS[PROPOSAL_RAW] != inventory["proposal"]["sha256_fortran_raw"]:
        raise ValueError("pinned raw hashes differ from the inventory")
    by_name = {r["name"]: r for r in rows}
    if len(by_name) != len(rows) or any(n not in by_name for n in EXPECTED_NAMES):
        raise ValueError("the inventory lacks a registered state")
    plan = [by_name[n] for n in EXPECTED_NAMES]
    if plan[0]["kind"] not in ("parent", "parent_repeat") or any(r["kind"] == "parent" for r in plan[1:]):
        raise ValueError("exactly one parent (or a parent repeat) must come first")
    parent = by_name["opt01b__parent"]
    if any(r["kind"] == "parent_repeat" and any(r[k] != parent[k] for k in IDENTITY_KEYS) for r in plan):
        raise ValueError("a parent repeat differs from the parent identity")
    if parent["phi_fortran_order_sha256"] != inventory["parent"]["phi_fortran_order_sha256"]:
        raise ValueError("the parent row differs from the inventory parent")
    for row in plan:
        if row["kind"] not in ("parent", "parent_repeat") and (row["direction"] != "robust_opt01a" or row["sign"] not in (1, -1) or not row["step_mm"] > 0):
            raise ValueError(f"unregistered state: {row['name']}")
    return plan


def state_env(base_env, inventory, row, gpu_uuid):
    env = dict(base_env)
    env.pop("GRID02_CASE", None)
    env.update(inventory["job_env_common"])
    for key in ("CUDA_DEVICE_ORDER", "CUDA_VISIBLE_DEVICES", "JULIA_NUM_THREADS"):
        if env.get(key) != base_env.get(key):
            raise RuntimeError(f"state environment changes probed device/thread configuration: {key}")
    env.update({
        "W4_SELECTED_GPU_UUID": gpu_uuid,
        "W4_STATE_SHA256": row["state_sha256"],
        "W4_STATE_NPZ_SHA256": row["npz_sha256"],
        "W4_PHI_C_ORDER_SHA256": row["phi_c_order_sha256"],
        "W4_PHI_FORTRAN_SHA256": row["phi_fortran_order_sha256"],
        "W4_EXPECTED_MARGIN_M": str(row["zero_level_margin_m"]),
        "W4_CANONICAL_ORIGIN_M": CONFIG["W4_CANONICAL_ORIGIN_M"],  # native, or shifted (h/2, h/2, 0) for the alignment control: same phi bytes, body translated against the flow grid
    })
    if CONFIG["GRID02_CASE"]:
        env["GRID02_CASE"] = CONFIG["GRID02_CASE"]  # only the new job reads it
    return env


def generate_phi(S, source, row, baseline_phi, directions):
    import numpy as np

    if row["kind"] in ("parent", "parent_repeat"):
        phi = baseline_phi
    else:
        phi = S.perturb(baseline_phi, directions[row["direction"]], row["step_mm"], row["sign"])
    if not np.all(np.isfinite(phi)):
        raise RuntimeError(f"generated phi has non-finite values: {row['name']}")
    raw = S.to_raw(phi)
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError(f"generated GRID-02 (OPT-01 v1 Stage B) phi differs from inventory: {row['name']}")
    if hashlib.sha256(np.asarray(phi, dtype="<f4").tobytes(order="C")).hexdigest() != row["phi_c_order_sha256"]:
        raise RuntimeError(f"generated C-order phi differs from inventory: {row['name']}")
    changed = int(np.count_nonzero(phi != baseline_phi))
    max_change = float(np.max(np.abs(phi.astype(np.float64) - baseline_phi.astype(np.float64))))
    if changed != row["changed_node_count"] or abs(max_change - row["maximum_pointwise_change_m"]) > 1.0e-12:
        raise RuntimeError(f"generated state change metrics differ from inventory: {row['name']}")
    return raw


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=False)
    stage = "gpu_inventory"
    identity = {
        "runner_sha256": sha256(__file__),
        "python_version": sys.version,
        "numpy_version": None,
        "platform": " ".join(os.uname()),
        "kernel": KERNEL,
        "kernel_id": KERNEL_ID,
        "source_commit": SOURCE_COMMIT,
        "pins": PINS,
        "direction_files": {name: PINS[path] for name, path in DIRECTIONS.items()},
        "config": CONFIG,
        "expected_names": EXPECTED_NAMES,
        "case_id": CASE_ID,
        "failure_stage": None,
    }
    index = {"kernel": KERNEL, "kernel_id": KERNEL_ID, "case_id": CASE_ID, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / "grid02_index.json", index)
    failed = False
    try:
        import numpy as np
        identity["numpy_version"] = np.__version__
        gpu = nvidia_smi()
        (OUT / "nvidia_smi.csv").write_text(gpu)
        with tempfile.TemporaryDirectory(prefix="grid02-", dir=OUT.parent) as temp:
            base = Path(temp)
            stage = "source_checkout"
            source = fetch_source(base)
            verified = {}
            for rel, expected in PINS.items():
                path = source / rel
                actual = sha256(path)
                verified[rel] = actual
                if actual != expected:
                    raise RuntimeError(f"pinned file SHA-256 mismatch: {rel}")
            identity["verified"] = verified
            write_json(OUT / "run_identity.json", identity)
            sys.path.insert(0, str(source / "scripts"))
            import step01_states as S
            from grid01_gpu import select_worker_gpu

            selected_gpu = select_worker_gpu(gpu)
            gpu_uuid = selected_gpu["uuid"]
            identity["selected_gpu"] = selected_gpu
            identity["cuda_device_order"] = "PCI_BUS_ID"
            identity["cuda_visible_devices"] = "0"
            write_json(OUT / "run_identity.json", identity)
            inventory = json.loads((source / INVENTORY).read_text())
            plan = expected_plan(inventory)
            by_name = {row["name"]: row for row in plan}
            baseline_phi = S.read_f4(source / BASELINE_RAW)
            if not np.all(np.isfinite(baseline_phi)):
                raise RuntimeError("baseline phi has non-finite values")
            if sha256(source / PROPOSAL_RAW) != inventory["proposal"]["sha256_fortran_raw"]:
                raise RuntimeError("proposal direction hash differs from inventory")
            directions = {"robust_opt01a": S.read_f4(source / PROPOSAL_RAW)}
            if not np.all(np.isfinite(directions["robust_opt01a"])):
                raise RuntimeError("proposal direction has non-finite values")
            julia = install_julia(base)
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "JULIA_NUM_THREADS": "1"})
            project = f"--project={source / PROJECT}"
            stage = "instantiate"
            if run([str(julia), project, "-e", "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env, min(INSTANTIATE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("Pkg.instantiate failed")
            for rel in ("Project.toml", "Manifest.toml"):
                full = f"{PROJECT}/{rel}"
                if sha256(source / full) != PINS[full]:
                    raise RuntimeError(f"{rel} changed during instantiate")
            stage = "observed_cuda_device_probe"
            probe_env = dict(env, GRID01_GPU_PROBE_OUT=str(OUT / "gpu_device_probe.json"))
            if run([str(julia), "--startup-file=no", project, "-e", GPU_PROBE_CODE], OUT / "gpu_device_probe.log", probe_env,
                   min(GPU_PROBE_TIMEOUT_S, remaining(started))):
                raise RuntimeError("independent CUDA device UUID probe failed")
            observed = json.loads((OUT / "gpu_device_probe.json").read_text())
            expected_device = {"logical_device_count": 1, "visible_gpu_names": ["Tesla T4"],
                               "visible_gpu_uuids": [gpu_uuid], "default_device_uuid": gpu_uuid,
                               "cuda_device_order": "PCI_BUS_ID", "cuda_visible_devices": "0"}
            if observed != expected_device:
                raise RuntimeError("observed CUDA singleton/default UUID differs from selected physical GPU")
            solver_elapsed_s = 0.0
            for position, name in enumerate(EXPECTED_NAMES):
                row = by_name[name]
                stage = f"state:{name}"
                outdir = OUT / "states" / name
                outdir.mkdir(parents=True, exist_ok=False)
                raw = generate_phi(S, source, row, baseline_phi, directions)
                phi_path = base / (name + ".phi.f32f")
                phi_path.write_bytes(raw)
                t0 = time.time()
                code = run(
                    [str(julia), "--startup-file=no", project, str(source / JOB), str(phi_path), str(outdir)],
                    outdir / "job.log",
                    state_env(env, inventory, row, gpu_uuid),
                    min(PER_STATE_TIMEOUT_S, remaining(started), SOLVER_WALL_TIME_CAP_S - solver_elapsed_s),
                )
                resolved_phi = phi_path.resolve()
                if resolved_phi.parent != base.resolve() or resolved_phi.name != name + ".phi.f32f":
                    raise RuntimeError("unexpected temporary phi cleanup target")
                resolved_phi.unlink()
                csv = outdir / f"{CASE_ID}.forces.csv"
                entry = {
                    "name": name,
                    "kind": row["kind"],
                    "direction": row["direction"],
                    "step_mm": row["step_mm"],
                    "sign": row["sign"],
                    "exit_code": code,
                    "seconds": time.time() - t0,
                    "forces_csv_sha256": sha256(csv) if csv.is_file() else None,
                    "complete": code == 0 and csv.is_file() and (outdir / "W4_JOB_DONE").is_file() and (outdir / f"{CASE_ID}.summary.json").is_file(),
                }
                solver_elapsed_s += entry["seconds"]
                index["solver_process_wall_seconds_total"] = solver_elapsed_s
                index["states"].append(entry)
                write_json(OUT / "grid02_index.json", index)
                if entry["seconds"] > PER_STATE_TIMEOUT_S or solver_elapsed_s > SOLVER_WALL_TIME_CAP_S:
                    raise RuntimeError("registered per-state or aggregate solver wall-time budget exceeded")
                if not entry["complete"]:
                    raise RuntimeError(f"state did not complete: {name} (exit {code})")
                if position == 0:  # no retained reference exists for this grid/placement: record the parent (or repeat) CSV hash; the analyzer compares the parent pair
                    index["parent_forces_csv_sha256"] = entry["forces_csv_sha256"]
                    write_json(OUT / "grid02_index.json", index)
            if [entry["name"] for entry in index["states"]] != EXPECTED_NAMES:
                raise RuntimeError("completed state sequence differs from the registered plan")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "grid02_index.json", index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "grid02_index.json", index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("all registered GRID-02 states of this kernel completed; host integrity and the response analysis are still required.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
