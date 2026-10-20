#!/usr/bin/env python3
"""GRIDRES-01 pinned worker: first the instrumented OPT-01 parent on each retained grid (PARENT_RERUNS: flow_24, flow_32; plan Amendment 2 H2, each must reproduce its retained Stage B force CSV byte for byte or the
kernel stops), then the five states (parent, +0.3125/+0.625/+1.25 mm and the -1.25 mm reverse diagnostic along the OPT-01 Stage A robust direction) on one finer grid; every run records the passive Poisson probe (H1).
Reuses the amended GRID-01 GPU/runtime protocol (copy-adapted from the frozen OPT-01 Stage B worker)."""
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
KERNEL_ID = "PIN_KERNEL_ID"
SOURCE_COMMIT = "PIN_SOURCE_COMMIT"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
CASE_ID = "PIN_CASE_ID"
JOB = "PIN_JOB"
CELLS = "PIN_CELLS"
PARENT_RERUNS = "PIN_PARENT_RERUNS"  # retained grids whose parent is rerun first, instrumented
STATES_MODULE = "scripts/step01_states.py"
EVIDENCE = "docs/evidence/gridres01_2026_10_20"
OPT01B_EVIDENCE = "docs/evidence/opt01b_stage_b_2026_10_15"  # the parent and direction raw files live here (the same bytes as OPT-01 Stage B)
INVENTORY = f"{EVIDENCE}/inventory.json"
BASELINE_RAW = f"{OPT01B_EVIDENCE}/inputs/parent.phi_f4_fortran.raw"  # the OPT-01 v1 parent (generation 1), Fortran-order Float32
PROPOSAL_RAW = f"{OPT01B_EVIDENCE}/inputs/robust_opt01a.dir_f4_fortran.raw"  # the OPT-01 Stage A robust cross-grid direction (max-norm 1)
DIRECTIONS = {"robust_opt01a": PROPOSAL_RAW}
PINS = PIN_PINS
SPARSE = [
    "julia/",
    "scripts/",
    f"{EVIDENCE}/",
    f"{OPT01B_EVIDENCE}/inputs/",
]
OUT = Path(f"/kaggle/working/gridres01_{KERNEL}")
INSTANTIATE_TIMEOUT_S = 2400
PER_STATE_TIMEOUT_S = "PIN_PER_STATE_TIMEOUT_S"
SOLVER_WALL_TIME_CAP_S = "PIN_SOLVER_WALL_TIME_CAP_S"  # aggregate over the parent reruns and the five states
GPU_PROBE_TIMEOUT_S = 300
KERNEL_TIMEOUT_S = "PIN_KERNEL_TIMEOUT_S"  # must equal `kaggle kernels push --timeout`
MARGIN_S = 300
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
EXPECTED_NAMES = ["opt01b__parent"] + [f"opt01b__prop__s{s:g}mm" for s in (0.3125, 0.625, 1.25)] + ["opt01b__ctrl_reverse__s1.25mm"]


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
    import gridres01_states as L
    if inventory.get("stage_status") != "READY" or inventory.get("blockers"):
        raise ValueError("the inventory is blocked before CFD")
    rows = inventory.get("states")
    if not isinstance(rows, list) or inventory.get("kernels", {}).get(CASE_ID) != EXPECTED_NAMES or EXPECTED_NAMES != list(L.NAMES):
        raise ValueError("the inventory is not the exact five-state GRIDRES-01 plan")
    if [{k: r.get(k) for k in ("name", "kind", "direction", "step_mm", "sign")} for r in rows] != L.plan():
        raise ValueError("state inventory differs from the frozen GRIDRES-01 plan")
    grid = inventory["grids"][CASE_ID]
    if grid["case_id"] != CASE_ID or grid["job"] != JOB or grid["cells"] != CELLS or L.GRIDS[CASE_ID]["cells"] != CELLS:
        raise ValueError("wrong grid/job binding")
    reruns = grid["parent_reruns"]
    if [r["case_id"] for r in reruns] != PARENT_RERUNS or list(L.GRIDS[CASE_ID]["parent_reruns"]) != PARENT_RERUNS or any(r["cells"] != L.RERUN_CELLS[r["case_id"]] for r in reruns):
        raise ValueError("parent reruns differ from the registered plan")
    caps = {"per_state_timeout_s": PER_STATE_TIMEOUT_S, "solver_wall_time_cap_s": SOLVER_WALL_TIME_CAP_S, "kernel_timeout_s": KERNEL_TIMEOUT_S}
    if grid["limits"] != caps or {k: L.GRIDS[CASE_ID][k] for k in caps} != caps:
        raise ValueError("registered caps differ from the pinned runner constants")
    if inventory["parent"]["raw_path"] != BASELINE_RAW or inventory["proposal"]["file"] != PROPOSAL_RAW:
        raise ValueError("parent or direction paths differ from the pinned runner constants")
    if BASELINE_RAW not in PINS or PROPOSAL_RAW not in PINS or PINS[BASELINE_RAW] != inventory["parent"]["phi_fortran_order_sha256"]:
        raise ValueError("the parent raw or the proposal direction is not pinned")
    return rows


def state_env(base_env, inventory, row, gpu_uuid, cells):
    env = dict(base_env)
    env.update(inventory["job_env_common"])
    env["GRIDRES01_CELLS"] = str(cells)
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
    })
    return env


def generate_phi(S, source, row, baseline_phi, directions):
    import numpy as np

    if row["kind"] == "parent":
        phi = baseline_phi
    else:
        phi = S.perturb(baseline_phi, directions[row["direction"]], row["step_mm"], row["sign"])
    if not np.all(np.isfinite(phi)):
        raise RuntimeError(f"generated phi has non-finite values: {row['name']}")
    raw = S.to_raw(phi)
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError(f"generated GRIDRES-01 phi differs from inventory: {row['name']}")
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
        "case_id": CASE_ID,
        "failure_stage": None,
    }
    index = {"kernel": KERNEL, "kernel_id": KERNEL_ID, "case_id": CASE_ID, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / "gridres01_index.json", index)
    failed = False
    try:
        import numpy as np
        identity["numpy_version"] = np.__version__
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        with tempfile.TemporaryDirectory(prefix="gridres01-", dir="/kaggle/working") as temp:
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
            parent_row = by_name[EXPECTED_NAMES[0]]
            # (case id, cells, state row, output dir, retained hash or None): the instrumented parent reruns first, so that an instrumentation that is not passive is detected before the flow_40 states
            runs = [(r["case_id"], r["cells"], parent_row, OUT / "parent_reruns" / r["case_id"], r["retained_forces_csv_sha256"]) for r in inventory["grids"][CASE_ID]["parent_reruns"]]
            runs += [(CASE_ID, CELLS, by_name[name], OUT / "states" / name, None) for name in EXPECTED_NAMES]
            index["parent_reruns"] = []
            for run_case, run_cells, row, outdir, retained_sha in runs:
                name = row["name"]
                stage = f"state:{run_case}:{name}"
                outdir.mkdir(parents=True, exist_ok=False)
                raw = generate_phi(S, source, row, baseline_phi, directions)
                phi_path = base / (run_case + "." + name + ".phi.f32f")
                phi_path.write_bytes(raw)
                t0 = time.time()
                code = run(
                    [str(julia), "--startup-file=no", project, str(source / JOB), str(phi_path), str(outdir)],
                    outdir / "job.log",
                    state_env(env, inventory, row, gpu_uuid, run_cells),
                    min(PER_STATE_TIMEOUT_S, remaining(started), SOLVER_WALL_TIME_CAP_S - solver_elapsed_s),
                )
                resolved_phi = phi_path.resolve()
                if resolved_phi.parent != base.resolve() or resolved_phi.name != run_case + "." + name + ".phi.f32f":
                    raise RuntimeError("unexpected temporary phi cleanup target")
                resolved_phi.unlink()
                csv = outdir / f"{run_case}.forces.csv"
                poisson = outdir / f"{run_case}.poisson.csv"
                entry = {
                    "name": name,
                    "kind": row["kind"],
                    "direction": row["direction"],
                    "step_mm": row["step_mm"],
                    "sign": row["sign"],
                    "exit_code": code,
                    "seconds": time.time() - t0,
                    "forces_csv_sha256": sha256(csv) if csv.is_file() else None,
                    "poisson_csv_sha256": sha256(poisson) if poisson.is_file() else None,
                    "complete": code == 0 and csv.is_file() and poisson.is_file() and (outdir / "W4_JOB_DONE").is_file() and (outdir / f"{run_case}.summary.json").is_file(),
                }
                solver_elapsed_s += entry["seconds"]
                index["solver_process_wall_seconds_total"] = solver_elapsed_s
                if retained_sha is not None:
                    entry.update({"case_id": run_case, "retained_forces_csv_sha256": retained_sha, "byte_identical_to_retained": entry["forces_csv_sha256"] == retained_sha})
                    index["parent_reruns"].append(entry)
                else:
                    index["states"].append(entry)
                write_json(OUT / "gridres01_index.json", index)
                if entry["seconds"] > PER_STATE_TIMEOUT_S or solver_elapsed_s > SOLVER_WALL_TIME_CAP_S:
                    raise RuntimeError("registered per-state or aggregate solver wall-time budget exceeded")
                if not entry["complete"]:
                    raise RuntimeError(f"state did not complete: {run_case} {name} (exit {code})")
                if retained_sha is not None and not entry["byte_identical_to_retained"]:
                    raise RuntimeError(f"instrumented {run_case} parent differs from the retained Stage B force CSV: the instrumentation is not passive (or the run is not reproducible); stopped before flow_40")
            if [entry["case_id"] for entry in index["parent_reruns"]] != PARENT_RERUNS:
                raise RuntimeError("completed parent reruns differ from the registered plan")
            if [entry["name"] for entry in index["states"]] != EXPECTED_NAMES:
                raise RuntimeError("completed state sequence differs from the registered plan")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "gridres01_index.json", index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "gridres01_index.json", index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("all registered GRIDRES-01 runs (instrumented parent reruns and the five states) completed; joint host integrity and actual response analysis are still required.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
