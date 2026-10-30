#!/usr/bin/env python3
"""LOWDIM-03 pinned seven-state worker; reuse the amended GRID-01 GPU/runtime protocol."""
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

KERNEL = "a"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-lowdim03-a"
SOURCE_COMMIT = "e5386910d8b77decd748fdbd5efaee002803d86c"
REPO_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
PROJECT = "julia/CFDSDFWaterLilyT4"
CASE_ID = "flow_24"
JOB = "scripts/waterlily_xfid_candidate_c_job.jl"
STATES_MODULE = "scripts/step01_states.py"
EVIDENCE = "docs/evidence/lowdim03_dual_grid_primal_2026_10_10"
INVENTORY = f"{EVIDENCE}/inventory.json"
BASELINE_RAW = "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw"
BASELINE_FORCE_CSV = "docs/evidence/step01_finite_step_secant_2026_10_09/kernel_output/a/states/step01__baseline/flow_24.forces.csv"
PROPOSAL_RAW = f"{EVIDENCE}/inputs/robust_cross_grid.dir_f4_fortran.raw"
DIRECTIONS = {
    "D0_interface_offset": "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw",
    "D1_filtered_seed11": "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D1_filtered_seed11.dir_f4_fortran.raw",
    "D2_filtered_seed2026": "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D2_filtered_seed2026.dir_f4_fortran.raw",
    "P1_upstream_lobe": "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/P1_upstream_lobe.dir_f4_fortran.raw",
}
BASIS = tuple(DIRECTIONS)
PINS = {'docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/cal_baseline_01.phi_f4_fortran.raw': 'e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D0_interface_offset.dir_f4_fortran.raw': 'd0af58bdc2bff55226ff911204ef42d05a6da4a4b52ec4c4521a09141fbf2549', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D1_filtered_seed11.dir_f4_fortran.raw': '96fe6e62c5fcb7ad0108dd64d6fac68cc488ee49deb188be742530f828037a87', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/D2_filtered_seed2026.dir_f4_fortran.raw': '2a22eb09407a14755f495fa07d4df8dee2d4632db41a0b75d1bf744fd3d1d5de', 'docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/P1_upstream_lobe.dir_f4_fortran.raw': '24cc06aeb18e2a5729e560636f13ce78f8f19746268699783e8498921aec5dcc', 'docs/evidence/lowdim03_dual_grid_primal_2026_10_10/inputs/robust_cross_grid.dir_f4_fortran.raw': 'c0f69676929c3eb17b1b623c599bfd97ea286d09810c63848e0d7499437e0bf5', 'docs/evidence/lowdim03_dual_grid_primal_2026_10_10/inventory.json': 'e42cf5e8dd05e58ddc0598b8bdab93b4dba3a6740471c0d2ec701492625f8cd3', 'docs/evidence/step01_finite_step_secant_2026_10_09/kernel_output/a/states/step01__baseline/flow_24.forces.csv': '39370386fd27a7ecd1160a295298798326078a4c5342be07bfb257267a1fbcb3', 'julia/CFDSDFWaterLily/src': '9e2cb6ef8ba35c5e5bbe9db5943cbefd9e93013e7d1b01ce934deda5190d0c85', 'julia/CFDSDFWaterLilyT4/Manifest.toml': 'c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707', 'julia/CFDSDFWaterLilyT4/Project.toml': 'e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194', 'scripts/grid01_gpu.py': 'bfaed961f3136d14bdeb7e4fccfab807f5fb8c257b45cd3ebb875963104fff38', 'scripts/lowdim01_states.py': '456c0110dafb64c2dc4b82e35ba7830aa4b436364802bb6b437f05aa35e82d32', 'scripts/lowdim03_states.py': 'fae904f80a697e0b4c33dcf91631bc83dc666e1c0d62415febc04437634f4d5f', 'scripts/step01_states.py': 'f3c5ea30cc88c5efe2cbdd8f96ceeb481321ebc0b84228b3287c6ab718b7ca87', 'scripts/waterlily_xfid_candidate_c_job.jl': '1d8dbcb63a867c74dc398a38a42cb061748511e9a53f987b1dd702cbb9b08447'}
SPARSE = [
    "julia/",
    "scripts/",
    "docs/evidence/lowdim03_dual_grid_primal_2026_10_10/",
    "docs/evidence/fd08_candidate_c_cpu_rehearsal_2026_10_05_retry1/inputs/",
    "docs/evidence/grad03_gpu_dual_spike_2026_10_08/inputs/",
    BASELINE_FORCE_CSV,
]
OUT = Path(f"/kaggle/working/lowdim03_{KERNEL}")
INSTANTIATE_TIMEOUT_S = 2400
PER_STATE_TIMEOUT_S = 900
SOLVER_WALL_TIME_CAP_S = 6300
GPU_PROBE_TIMEOUT_S = 300
KERNEL_TIMEOUT_S = 10800  # must equal `kaggle kernels push --timeout`
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
EXPECTED_NAMES = ["lowdim03__baseline"] + [
    f"lowdim03__prop__s{s:g}mm" for s in (0.625, 1.25, 2.5)
] + [f"lowdim03__ctrl_reverse__s{s:g}mm" for s in (0.625, 1.25, 2.5)]


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
    import lowdim03_states as L
    rows = inventory.get("states")
    if not isinstance(rows, list) or inventory.get("kernels", {}).get(KERNEL) != EXPECTED_NAMES:
        raise ValueError("the inventory is not the exact seven-state LOWDIM-03 plan")
    if [{k:r.get(k) for k in ("name","kind","step_mm","sign")} for r in rows] != L.plan():
        raise ValueError("state inventory differs from the frozen LOWDIM-03 plan")
    if inventory["grids"][KERNEL]["case_id"] != CASE_ID or inventory["grids"][KERNEL]["job"] != JOB:
        raise ValueError("wrong grid/job binding")
    if inventory["grids"][KERNEL]["baseline_reference"]["forces_csv_path"] != BASELINE_FORCE_CSV or inventory["baseline"]["path"] != BASELINE_RAW:
        raise ValueError("baseline reference paths differ from the pinned runner constants")
    if BASELINE_RAW not in PINS or BASELINE_FORCE_CSV not in PINS or PROPOSAL_RAW not in PINS:
        raise ValueError("a baseline or proposal input is not pinned")
    for row in rows[1:]:
        if row["geometry_gates"]["all_hard_gates_pass"] is not True or not all(v is True for v in row["geometry_gates"]["gates"].values()):
            raise ValueError("preflight geometry gate failed")
    return rows


def state_env(base_env, inventory, row, gpu_uuid):
    env = dict(base_env)
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
    })
    return env


def generate_phi(S, source, row, baseline_phi, directions):
    import numpy as np

    if row["kind"] == "baseline":
        phi = baseline_phi
    else:
        direction = directions["robust_cross_grid"]
        phi = S.perturb(baseline_phi, direction, row["step_mm"], row["sign"])
    if not np.all(np.isfinite(phi)):
        raise RuntimeError(f"generated phi has non-finite values: {row['name']}")
    raw = S.to_raw(phi)
    if S.sha256_bytes(raw) != row["phi_fortran_order_sha256"]:
        raise RuntimeError(f"generated LOWDIM-03 phi differs from inventory: {row['name']}")
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
        "baseline_csv_sha256": PINS[BASELINE_FORCE_CSV],
        "case_id": CASE_ID,
        "failure_stage": None,
    }
    index = {"kernel": KERNEL, "kernel_id": KERNEL_ID, "case_id": CASE_ID, "states": [], "status": "RUNNING"}
    write_json(OUT / "run_identity.json", identity)
    write_json(OUT / "lowdim03_index.json", index)
    failed = False
    try:
        import numpy as np
        identity["numpy_version"] = np.__version__
        gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
        (OUT / "nvidia_smi.csv").write_text(gpu)
        with tempfile.TemporaryDirectory(prefix="lowdim03-", dir="/kaggle/working") as temp:
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
            directions = {}
            for name in BASIS:
                item = inventory["directions"][name]
                path = source / item["path"]
                if sha256(path) != item["sha256_fortran_raw"]:
                    raise RuntimeError(f"direction hash differs from inventory: {name}")
                directions[name] = S.read_f4(path)
                if not np.all(np.isfinite(directions[name])):
                    raise RuntimeError(f"direction has non-finite values: {name}")
            import lowdim01_states
            c = inventory["proposal"]["coefficient_vector"]
            proposal, info = lowdim01_states.coefficient_direction(dict(zip(BASIS, c)), directions)
            if S.to_raw(proposal) != (source / PROPOSAL_RAW).read_bytes() or info["m_max_abs_sum"] != inventory["proposal"]["m_max_abs_sum"]:
                raise RuntimeError("regenerated robust direction differs from the frozen bytes")
            directions = {"robust_cross_grid": proposal}
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
                write_json(OUT / "lowdim03_index.json", index)
                if entry["seconds"] > PER_STATE_TIMEOUT_S or solver_elapsed_s > SOLVER_WALL_TIME_CAP_S:
                    raise RuntimeError("registered per-state or aggregate solver wall-time budget exceeded")
                if not entry["complete"]:
                    raise RuntimeError(f"state did not complete: {name} (exit {code})")
                if position == 0:
                    entry["matches_registered_baseline"] = entry["forces_csv_sha256"] == PINS[BASELINE_FORCE_CSV]
                    write_json(OUT / "lowdim03_index.json", index)
                    if not entry["matches_registered_baseline"]:
                        raise RuntimeError("first-state baseline differs from the registered grid reference; stopping before any perturbed state")
            if [entry["name"] for entry in index["states"]] != EXPECTED_NAMES:
                raise RuntimeError("completed state sequence differs from the registered plan")
        stage = "completed"
        index["status"] = "COMPLETE"
        identity["failure_stage"] = None
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "lowdim03_index.json", index)
    except BaseException:
        failed = True
        index["status"] = "ERROR"
        identity["failure_stage"] = stage
        write_json(OUT / "run_identity.json", identity)
        write_json(OUT / "lowdim03_index.json", index)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        print((OUT / "ERROR.txt").read_text(), flush=True)
    finally:
        if not failed:
            (OUT / "DONE").write_text("all seven registered LOWDIM-03 states completed; joint host integrity and actual response analysis are still required.\n")
        files = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "output_manifest.json"}
        write_json(OUT / "output_manifest.json", {"files": files})
        print("OUTPUT_MANIFEST_SHA256", sha256(OUT / "output_manifest.json"), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
