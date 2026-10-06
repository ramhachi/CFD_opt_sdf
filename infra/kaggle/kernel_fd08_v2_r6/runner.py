#!/usr/bin/env python3
"""Private Kaggle runner for setup rehearsal, R6, and formal FD-08 v2 batches."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request


INPUT_ROOT = Path(os.environ.get("FD08_V2_INPUT", "/kaggle/input"))
OUT_ROOT = Path(os.environ.get("FD08_V2_OUT", "/kaggle/working"))
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
    "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
    "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver",
    "viscous_fz_solver",
]
STATE = {"stage": "startup"}
OUT = OUT_ROOT / "fd08_v2_setup_rehearsal"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def set_stage(out: Path, stage: str, **details) -> None:
    STATE.update(stage=stage, **details)
    write_json(out / "execution_state.json", STATE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def command(args, log_path: Path, *, env=None, timeout=3600, check=True) -> str:
    print("RUN", " ".join(map(str, args)), flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    output = log_path.read_text(errors="replace")
    if check and result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {log_path.name}")
    return output


def find_dataset():
    candidates = sorted(INPUT_ROOT.rglob("criteria.json"))
    require(len(candidates) == 1, f"expected one criteria.json input, found {len(candidates)}")
    return candidates[0].parent


def load_criteria(dataset: Path):
    criteria_path = dataset / "criteria.json"
    sidecar = dataset / "criteria.json.sha256"
    require(criteria_path.is_file() and sidecar.is_file(), "criteria and SHA-256 sidecar are required")
    criteria_sha = sha256(criteria_path)
    require(sidecar.read_text().strip() == criteria_sha, "criteria SHA-256 sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    require(criteria.get("immutable") is True, "input criteria are not immutable")
    mode = criteria.get("kind")
    require(mode in {"fd08_v2_setup_rehearsal", "fd08_v2_r6_calibration", "fd08_v2_formal_validation"},
            "unsupported FD-08 v2 input criteria kind")
    if mode != "fd08_v2_setup_rehearsal":
        require(criteria.get("registered_before_computation") is True
                and criteria.get("status") == "registered_not_run",
                "scientific criteria must be preregistered and unused")
        flags = criteria.get("qualification_flags")
        required_flags = {"shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology"}
        require(isinstance(flags, dict) and set(flags) == required_flags
                and all(value is False for value in flags.values()), "qualification flags must be literal false")
    return criteria_path, criteria, criteria_sha


def verify_dataset(dataset: Path, criteria: dict, criteria_sha: str):
    expected = dict(criteria.get("dataset_files", {}))
    expected.update({
        "criteria.json": criteria_sha,
        "criteria.json.sha256": sha256(dataset / "criteria.json.sha256"),
        "fd08_v2_dataset_manifest.json": sha256(dataset / "fd08_v2_dataset_manifest.json"),
    })
    actual = {path.relative_to(dataset).as_posix() for path in dataset.rglob("*") if path.is_file()}
    require(actual == set(expected), f"dataset inventory mismatch: {sorted(actual ^ set(expected))}")
    for name, digest in expected.items():
        require(sha256(dataset / name) == digest, f"dataset file SHA mismatch: {name}")
    manifest = json.loads((dataset / "fd08_v2_dataset_manifest.json").read_text())
    require(manifest.get("criteria_sha256") == criteria_sha, "dataset manifest criteria hash mismatch")
    require(manifest.get("files") == {name: sha256(dataset / name) for name in sorted(expected)
                                      if name != "fd08_v2_dataset_manifest.json"},
            "dataset manifest file map mismatch")
    if criteria.get("kind") == "fd08_v2_r6_calibration":
        setup_path = dataset / "setup_rehearsal_evidence.json"
        setup = json.loads(setup_path.read_text())
        binding = criteria.get("setup_rehearsal", {})
        require(sha256(setup_path) == binding.get("evidence_sha256")
                and setup.get("status") == "PASS_SETUP_ONLY"
                and setup.get("source_commit") == criteria.get("source_commit")
                and setup.get("force_history_present") is False,
                "R6 criteria do not bind the verified setup-only rehearsal")


def verify_source(source: Path, criteria: dict, runner_sha: str):
    for name, entry in criteria["source_inputs"].items():
        path = source / entry["path"]
        require(path.is_file() and sha256(path) == entry["sha256"],
                f"registered source input SHA mismatch: {name}")
    require(runner_sha == criteria["source_inputs"]["kernel_runner"]["sha256"],
            "uploaded runner bytes differ from registered runner source")
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    require(actual == criteria["source_commit"], "source commit differs from immutable criteria")
    return source / "julia/CFDSDFWaterLilyT4"


def fetch_source(base: Path, criteria: dict, out: Path):
    source = base / "source"
    command(["git", "init", "-q", str(source)], out / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", "400", SOURCE_URL, SOURCE_REF],
            out / "git_fetch.log", timeout=600)
    command(["git", "-C", str(source), "checkout", "--detach", criteria["source_commit"]],
            out / "git_checkout.log", timeout=300)
    return source


def install_julia(base: Path, criteria: dict, out: Path):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    expected = criteria["runtime"]["julia_archive_sha256"]
    require(digest.hexdigest() == expected, "Julia archive SHA-256 mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)], out / "julia_extract.log", timeout=600)
    julia = base / "julia-1.12.6/bin/julia"
    require(julia.is_file(), "verified Julia binary not found")
    return julia


def runtime_smoke(julia: Path, project: Path, source: Path, criteria: dict,
                  base_env: dict, out: Path):
    smoke = command(
        [str(julia), "--startup-file=no", f"--project={project}",
         str(source / "scripts/w0b_t4_smoke.jl")],
        out / "julia_smoke.log", env=base_env, timeout=1200,
    )
    backend = criteria["runtime"]
    markers = (
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
        f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
        f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
        f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
        f"JULIA_VERSION {backend['julia_version']}",
        f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
        f"WATERLILY_VERSION {backend['waterlily_version']}",
        f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP",
    )
    require(all(marker in smoke for marker in markers), "runtime smoke did not match registered T4 contract")
    return smoke


def gpu_inventory(criteria, out: Path):
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"],
        text=True,
    )
    (out / "nvidia_smi.csv").write_text(text)
    rows = [[cell.strip() for cell in row] for row in csv.reader(text.splitlines()) if row]
    backend = criteria["runtime"]
    require(len(rows) == backend["gpu_count"], "registered GPU count mismatch")
    require([row[0] for row in rows] == [str(i) for i in range(len(rows))], "GPU index inventory mismatch")
    require(len({row[2] for row in rows}) == len(rows)
            and all(row[2].startswith("GPU-") for row in rows)
            and all(backend["gpu_name"] in row[1] for row in rows), "registered T4 identity mismatch")
    return [", ".join(row) for row in rows], rows[0][2], rows[0][-1]


def margin_m(phi, spacing):
    import numpy as np
    solid = phi < 0.0
    if not solid.any():
        return math.inf if np.all(phi > 0.0) else math.nan
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing for n in phi.shape]
    face_gap = np.minimum(np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]), gaps[2][None, None, :])
    return float(np.min(face_gap[solid] + phi[solid]))


def validate_state_files(dataset: Path, criteria: dict):
    import numpy as np
    canonical = criteria["canonical_state"]
    shape = tuple(canonical["shape"])
    baseline = next(row for row in criteria["state_inventory"] if row["kind"] == "baseline")
    with np.load(dataset / baseline["npz_file"], allow_pickle=False) as archive:
        baseline_phi = np.asarray(archive["phi"], dtype="<f4")
        baseline_masks = {name: np.asarray(archive[name]).copy() for name in
                          ("design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask")}
    require(list(baseline_phi.shape) == list(shape), "baseline state shape mismatch")
    byte_set = set()
    for row in criteria["state_inventory"]:
        raw_path = dataset / row["phi_raw_file"]
        npz_path = dataset / row["npz_file"]
        raw = raw_path.read_bytes()
        require(len(raw) == int(np.prod(shape)) * 4, f"{row['name']}: phi raw byte length mismatch")
        require(sha256_bytes(raw) == row["phi_fortran_order_sha256"], f"{row['name']}: Fortran phi hash mismatch")
        require(raw not in byte_set, f"distinct state phi bytes collide: {row['name']}")
        byte_set.add(raw)
        phi = np.frombuffer(raw, dtype="<f4").reshape(shape, order="F")
        require(np.isfinite(phi).all(), f"{row['name']}: nonfinite phi")
        require(sha256_bytes(np.asarray(phi, dtype="<f4", order="C").tobytes(order="C"))
                == row["phi_c_order_sha256"], f"{row['name']}: C-order phi hash mismatch")
        require(sha256(npz_path) == row["npz_sha256"], f"{row['name']}: state NPZ hash mismatch")
        with np.load(npz_path, allow_pickle=False) as archive:
            npz_phi = np.asarray(archive["phi"], dtype="<f4")
            require(np.array_equal(npz_phi.view("<u4"), phi.view("<u4")),
                    f"{row['name']}: raw phi differs from NPZ phi")
            metadata = json.loads(str(archive["metadata"].item()))
            require(metadata.get("state_sha256") == row["state_sha256"],
                    f"{row['name']}: NPZ state identity mismatch")
            for name, expected in baseline_masks.items():
                require(np.array_equal(np.asarray(archive[name]), expected),
                        f"{row['name']}: mask changed: {name}")
        measured_margin = margin_m(phi, float(canonical["spacing_m"]))
        require(math.isfinite(measured_margin)
                and abs(measured_margin - row["margin_m"]) <= 1e-10
                and measured_margin >= criteria["geometry_reject_gates"]["minimum_zero_level_margin_m"],
                f"{row['name']}: zero-level margin failure")
    require(len(byte_set) == criteria["expected_state_count"], "state byte uniqueness count mismatch")


def state_env(base: dict, row: dict, criteria: dict, gpu_uuid: str):
    env = dict(base)
    canonical = criteria["canonical_state"]
    env.update({
        "W4_SELECTED_GPU_UUID": gpu_uuid,
        "W4_CANONICAL_STATE_LABEL": "v17",
        "W4_STATE_SHA256": row["state_sha256"],
        "W4_STATE_NPZ_SHA256": row["npz_sha256"],
        "W4_PHI_C_ORDER_SHA256": row["phi_c_order_sha256"],
        "W4_PHI_FORTRAN_SHA256": row["phi_fortran_order_sha256"],
        "W4_SOURCE_SURFACE_SHA256": canonical["source_surface_sha256"],
        "W4_POINT_SHAPE": ",".join(map(str, canonical["shape"])),
        "W4_CELL_SHAPE": ",".join(str(int(value) - 1) for value in canonical["shape"]),
        "W4_CANONICAL_ORIGIN_M": ",".join(map(str, canonical["origin_m"])),
        "W4_CANONICAL_DESIGN_SPACING_M": str(canonical["spacing_m"]),
        "W4_EXPECTED_MARGIN_M": str(row["margin_m"]),
        "W4_MARGIN_TOLERANCE_M": "1e-6",
        "W4_MARGIN_GATE_M": "0.15",
    })
    return env


def run_setup_state(row, dataset: Path, source: Path, project: Path, julia: Path,
                    base_env: dict, gpu_uuid: str, criteria: dict, out: Path):
    import numpy as np
    raw = (dataset / row["phi_raw_file"]).read_bytes()
    npz_path = dataset / row["npz_file"]
    phi = np.frombuffer(raw, dtype="<f4").reshape(tuple(criteria["canonical_state"]["shape"]), order="F")
    env = state_env(base_env, row, criteria, gpu_uuid)
    env["W4_PHI_FORTRAN_SHA256"] = row["phi_fortran_order_sha256"]
    env["W4_PHI_C_ORDER_SHA256"] = row["phi_c_order_sha256"]
    env["W4_STATE_SHA256"] = row["state_sha256"]
    log = out / "states" / row["name"] / "setup.log"
    output_json = log.parent / "setup.json"
    command([str(julia), "--startup-file=no", f"--project={project}",
             str(source / "scripts/waterlily_fd08_v2_setup_rehearsal.jl"),
             str(dataset / row["phi_raw_file"]), str(output_json)],
            log, env=env, timeout=criteria["per_state_timeout_s"])
    result = json.loads(output_json.read_text())
    require(result.get("evidence_class") == "setup_only_not_calibration"
            and result.get("state_sha256") == row["state_sha256"]
            and result.get("phi_fortran_sha256") == row["phi_fortran_order_sha256"]
            and result.get("device_roundtrip_sha256") == row["phi_fortran_order_sha256"]
            and result.get("finite_u") is True and result.get("finite_p") is True,
            "setup rehearsal result identity or finite-field check failed")
    text = log.read_text(errors="replace")
    require("FD08_V2_SETUP_DONE " in text, "setup terminal marker absent")
    require(not any(path.suffix == ".csv" for path in log.parent.iterdir()),
            "setup rehearsal unexpectedly emitted force CSV")
    return {"status": "SETUP_ONLY_COMPLETE", "state_name": row["name"],
            "setup": result, "log_sha256": sha256(log),
            "setup_json_sha256": sha256(output_json)}


def run_measurement_state(row, dataset: Path, source: Path, project: Path, julia: Path,
                          base_env: dict, gpu_uuid: str, criteria: dict, out: Path):
    outdir = out / "states" / row["name"]
    outdir.mkdir(parents=True, exist_ok=False)
    env = state_env(base_env, row, criteria, gpu_uuid)
    job = source / "scripts/waterlily_xfid_candidate_c_job.jl"
    log = outdir / "job.log"
    state_started_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state_started_mono = time.monotonic()
    command([str(julia), "--startup-file=no", f"--project={project}", str(job),
             str(dataset / row["phi_raw_file"]), str(outdir)],
            log, env=env, timeout=criteria["measurement"]["per_state_timeout_s"])
    state_elapsed = time.monotonic() - state_started_mono
    state_finished_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary_path = outdir / "flow_24.summary.json"
    csv_path = outdir / "flow_24.forces.csv"
    require(summary_path.is_file() and csv_path.is_file() and (outdir / "W4_JOB_DONE").is_file(),
            f"{row['name']}: expected complete state artifacts missing")
    summary = json.loads(summary_path.read_text())
    require(summary.get("state_sha256") == row["state_sha256"]
            and summary.get("phi_fortran_sha256") == row["phi_fortran_order_sha256"]
            and summary.get("device_roundtrip_sha256") == row["phi_fortran_order_sha256"],
            f"{row['name']}: solver state identity mismatch")
    require(all(summary.get(key) is True for key in ("finite_u", "finite_p", "finite_forces")),
            f"{row['name']}: nonfinite solver output")
    require(summary.get("t_end_reached", 0.0) >= 120.0, f"{row['name']}: did not reach tU/L=120")
    require(summary.get("force_csv_sha256") == sha256(csv_path), f"{row['name']}: force CSV SHA mismatch")
    log_text = log.read_text(errors="replace")
    invoked = [line.split()[-1] for line in log_text.splitlines() if line.startswith("W4_SOLVER_STEP_INVOKED ")]
    returned = [line.split()[-1] for line in log_text.splitlines() if line.startswith("W4_SOLVER_STEP_RETURNED ")]
    require(invoked == ["flow_24"] and returned == ["flow_24"], f"{row['name']}: warmup/solver markers mismatch")
    state_result = {
        "status": "COMPLETE",
        "state_name": row["name"],
        "state_sha256": row["state_sha256"],
        "phi_fortran_order_sha256": row["phi_fortran_order_sha256"],
        "force_csv_sha256": sha256(csv_path),
        "summary_sha256": sha256(summary_path),
        "summary": summary,
        "job_log_sha256": sha256(log),
        "state_started_utc": state_started_utc,
        "state_finished_utc": state_finished_utc,
        "state_elapsed_seconds": state_elapsed,
    }
    write_json(outdir / "state_result.json", state_result)
    return state_result


def main():
    global OUT
    dataset = find_dataset()
    criteria_path, criteria, criteria_sha = load_criteria(dataset)
    mode = criteria["kind"]
    out = OUT_ROOT / criteria.get("artifact_paths", {}).get(
        "output_root", "fd08_v2_setup_rehearsal" if mode == "fd08_v2_setup_rehearsal" else "fd08_v2"
    )
    OUT = out
    out.mkdir(parents=True, exist_ok=False)
    started_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    set_stage(out, "input_integrity")
    verify_dataset(dataset, criteria, criteria_sha)
    if mode != "fd08_v2_setup_rehearsal":
        validate_state_files(dataset, criteria)
    set_stage(out, "gpu_inventory")
    gpu_rows, gpu_uuid, driver = gpu_inventory(criteria, out)
    runner_sha = sha256(Path(__file__))
    with tempfile.TemporaryDirectory(prefix="fd08_v2_") as temp:
        base = Path(temp)
        set_stage(out, "source_fetch")
        source = fetch_source(base, criteria, out)
        project = verify_source(source, criteria, runner_sha)
        julia = install_julia(base, criteria, out)
        env = os.environ.copy()
        env.update({
            "JULIA_NUM_THREADS": str(criteria["runtime"]["julia_threads"]),
            "CUDA_VISIBLE_DEVICES": criteria["runtime"]["cuda_visible_devices"],
        })
        set_stage(out, "project_instantiate")
        command([str(julia), "--startup-file=no", f"--project={project}", "-e", "using Pkg; Pkg.instantiate()"],
                out / "instantiate.log", env=env, timeout=1800)
        for key, filename in (("julia_project", "Project.toml"), ("julia_manifest", "Manifest.toml")):
            bound = criteria["source_inputs"][key]
            require(sha256(project / filename) == bound["sha256"],
                    f"Julia {filename} changed during instantiate")
        set_stage(out, "runtime_smoke")
        smoke_output = runtime_smoke(julia, project, source, criteria, env, out)
        if mode == "fd08_v2_setup_rehearsal":
            rows = criteria["state_inventory"]
            require(len(rows) == 2, "setup rehearsal must contain exactly two signed/baseline states")
            results = [run_setup_state(row, dataset, source, project, julia, env, gpu_uuid, criteria, out)
                       for row in rows]
            result = {
                "kind": mode,
                "evidence_class": "setup_only_not_r6_or_formal_science",
                "criteria_sha256": criteria_sha,
                "source_commit": criteria["source_commit"],
                "kernel_id": criteria["kernel_id"],
                "dataset_id": criteria["input_dataset_id"],
                "runner_sha256": runner_sha,
                "dataset_manifest_sha256": sha256(dataset / "fd08_v2_dataset_manifest.json"),
                "gpu_inventory": gpu_rows,
                "host_driver_version_recorded_not_gated": driver,
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "julia_version": "1.12.6",
                "runtime_smoke_sha256": sha256(out / "julia_smoke.log"),
                "runtime_smoke_markers": {line.split(" ", 1)[0]: line.split(" ", 1)[1]
                                           for line in smoke_output.splitlines()
                                           if line.startswith(("CUDA_", "GPU_", "JULIA_", "WATERLILY_"))},
                "states": results,
                "state_count": len(results),
                "elapsed_s": time.monotonic() - started,
                "started_utc": started_utc,
                "finished_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "SETUP_ONLY_COMPLETE",
                "qualification_flags": {key: False for key in
                    ("shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")},
            }
        else:
            set_stage(out, "state_input_verification")
            results = {}
            solve_started = time.monotonic()
            for index, row in enumerate(criteria["state_inventory"], 1):
                set_stage(out, "state_run", current=row["name"], completed=index - 1,
                          expected=criteria["expected_state_count"])
                result = run_measurement_state(row, dataset, source, project, julia, env, gpu_uuid, criteria, out)
                results[row["name"]] = result
                write_json(out / "partial_result.json", {"criteria_sha256": criteria_sha,
                            "source_commit": criteria["source_commit"], "completed_count": index,
                            "expected_count": criteria["expected_state_count"], "states": results})
            (out / "partial_result.json").unlink(missing_ok=True)
            aggregate_solver = sum(row["summary"]["wall_seconds"] for row in results.values())
            measurement = criteria["measurement"]
            elapsed = time.monotonic() - started
            status = "COMPLETE" if len(results) == criteria["expected_state_count"] else "INCOMPLETE"
            if aggregate_solver > measurement["solver_wall_time_cap_s"]:
                status = "BUDGET_EXCEEDED"
            if elapsed > measurement["kernel_execution_allowance_s"]:
                status = "BUDGET_EXCEEDED"
            result = {
                "kind": mode,
                "criteria_sha256": criteria_sha,
                "source_commit": criteria["source_commit"],
                "kernel_id": criteria["kernel_id"],
                "dataset_id": criteria["input_dataset_id"],
                "runner_sha256": runner_sha,
                "dataset_manifest_sha256": sha256(dataset / "fd08_v2_dataset_manifest.json"),
                "gpu_inventory": gpu_rows,
                "host_driver_version_recorded_not_gated": driver,
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "julia_version": "1.12.6",
                "runtime_smoke_sha256": sha256(out / "julia_smoke.log"),
                "runtime_smoke_markers": {line.split(" ", 1)[0]: line.split(" ", 1)[1]
                                           for line in smoke_output.splitlines()
                                           if line.startswith(("CUDA_", "GPU_", "JULIA_", "WATERLILY_"))},
                "states": results,
                "state_count": len(results),
                "expected_state_count": criteria["expected_state_count"],
                "aggregate_solver_wall_seconds": aggregate_solver,
                "solver_cap_seconds": measurement["solver_wall_time_cap_s"],
                "elapsed_kernel_seconds": elapsed,
                "started_utc": started_utc,
                "finished_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "kernel_allowance_seconds": measurement["kernel_execution_allowance_s"],
                "status": status,
                "qualification_flags": criteria["qualification_flags"],
            }
        write_json(out / "result.json", result)
        if result["status"] not in {"COMPLETE", "SETUP_ONLY_COMPLETE"}:
            raise RuntimeError("batch terminal status is not complete; no DONE marker will be written")
        set_stage(out, "terminal_manifest")
        files = {path.relative_to(out).as_posix(): sha256(path) for path in sorted(out.rglob("*"))
                 if path.is_file() and path.name not in {"sha256.json", "DONE"}}
        write_json(out / "sha256.json", files)
        write_json(out / "DONE", {"status": result["status"], "criteria_sha256": criteria_sha,
                    "source_commit": criteria["source_commit"], "file_count": len(files)})
        print("FD08_V2_TERMINAL ", result["status"], flush=True)


if __name__ == "__main__":
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        write_json(OUT / "ERROR.json", {"status": "FAILED", "stage": STATE.get("stage"),
                    "error_type": type(exc).__name__, "error": str(exc),
                    "traceback": traceback.format_exc()[-6000:]})
        print("FD08_V2_ERROR", type(exc).__name__, str(exc), flush=True)
