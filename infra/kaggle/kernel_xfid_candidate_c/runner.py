#!/usr/bin/env python3
"""XFID-C: Candidate C (WaterLily, T4) forces for the seven registered XFID states, flow_24.

Part B of the formal XFID registration. Measurement only: no XFID verdict is computed here.
Helper functions between the BEGIN/END markers are copied verbatim from
infra/kaggle/kernel_w4_v17_candidate_c/runner.py (a test asserts source equality); the rest is new.
Per-state failures are recorded and later states still run (the solver is deterministic).
"""

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

CRITERIA_SHA256 = "39974802c43a55bde53da2afc6e04149ef7fec148d8b678e1f8b92a4523d775b"  # bound at registration; the runner refuses to run otherwise
OUT_ROOT = Path(os.environ.get("XC_OUT_ROOT", "/kaggle/working"))
OUT = OUT_ROOT / "xfid_candidate_c"
INPUT_ROOT = Path(os.environ.get("XC_INPUT", "/kaggle/input"))
SOURCE_URL = os.environ.get("XC_SOURCE_URL", "https://github.com/ramhachi/CFD_opt_sdf.git")
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
SOURCE_FETCH_DEPTH = 400
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
]
STATE = {"stage": "startup"}


def set_stage(stage, **details):
    STATE["stage"] = stage
    STATE.update(details)
    write_json(OUT / "execution_state.json", STATE)


# ---- BEGIN verbatim copy from the W4-C runner ----
def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n")


def command(args, log_path, *, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def install_julia(base, criteria):
    archive = Path(base) / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    expected = criteria["backend"]["julia_archive_sha256"]
    if digest.hexdigest() != expected:
        raise RuntimeError("W4 Julia archive SHA-256 mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)], OUT / "julia_extract.log", timeout=600)
    julia = Path(base) / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("verified W4 Julia binary was not extracted")
    return julia


def zero_level_margin_m(phi, spacing, canonical_label="v16"):
    import numpy as np

    solid = phi < 0.0
    if not solid.any():
        if np.all(phi > 0.0):
            return math.inf
        raise RuntimeError(f"canonical {canonical_label} SDF contains no negative solid nodes")
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing
            for n in phi.shape]
    face_gap = np.minimum(
        np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]),
        gaps[2][None, None, :],
    )
    return float(np.min(face_gap[solid] + phi[solid]))


def parse_force_csv(path):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FORCE_COLUMNS:
            raise RuntimeError("W4 force CSV schema mismatch")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    if not rows or any(not all(math.isfinite(value) for value in row.values()) for row in rows):
        raise RuntimeError("W4 force CSV is empty or contains non-finite values")
    return rows


def time_weighted_mean(rows, key):
    duration = total = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        total += 0.5 * (left[key] + right[key]) * dt
        duration += dt
    if duration <= 0.0:
        raise RuntimeError("W4 force window has no positive physical-time interval")
    return total / duration


def clipped_force_window(rows, start, end):
    def boundary(t):
        right = next((index for index, row in enumerate(rows) if row["t_u_l"] >= t), None)
        if right is None:
            raise RuntimeError("W4 force samples do not reach the registered window endpoint")
        if rows[right]["t_u_l"] == t:
            return dict(rows[right])
        if right == 0:
            raise RuntimeError("W4 force samples do not bracket the registered window start")
        left_row, right_row = rows[right - 1], rows[right]
        alpha = (t - left_row["t_u_l"]) / (right_row["t_u_l"] - left_row["t_u_l"])
        return {key: (float(t) if key == "t_u_l" else left_row[key] + alpha * (right_row[key] - left_row[key]))
                for key in left_row}

    if rows[0]["t_u_l"] > start or rows[-1]["t_u_l"] < end:
        raise RuntimeError("W4 raw force CSV does not bracket [80,120]")
    return [boundary(start),
            *[row for row in rows if start < row["t_u_l"] < end],
            boundary(end)]


def recompute_case_metrics(rows, case, measurement):
    start, end = measurement["force_window_t_u_l"]
    window = [row for row in rows if start <= row["t_u_l"] <= end]
    middle = 0.5 * (start + end)
    first = [row for row in window if row["t_u_l"] < middle]
    second = [row for row in window if row["t_u_l"] >= middle]
    if len(window) < measurement["minimum_force_window_samples"] or not first or not second:
        raise RuntimeError("W4 registered force window is incomplete")
    stride = measurement["force_sample_every_solver_steps"]
    terminal_extra = rows[-1]["step"] % stride != 0
    regular = rows[:-1] if terminal_extra else rows
    if (any(row["step"] % stride for row in regular)
            or any(right["step"] - left["step"] != stride
                   for left, right in zip(regular, regular[1:]))
            or (terminal_extra and not (end <= rows[-1]["t_u_l"]
                                        and 0 < rows[-1]["step"] - rows[-2]["step"] < stride))):
        raise RuntimeError("W4 force samples do not follow the registered stride/terminal rule")
    weighted_window = clipped_force_window(rows, start, end)
    first_weighted_window = clipped_force_window(
        rows, *measurement["stationarity"]["half_windows_t_u_l"][0])
    second_weighted_window = clipped_force_window(
        rows, *measurement["stationarity"]["half_windows_t_u_l"][1])
    columns = ["fx_solver", "fy_solver", "fz_solver", "drag_solver", "downforce_solver",
               "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver",
               "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver"]
    means = {f"window_time_weighted_{key}": time_weighted_mean(weighted_window, key)
             for key in columns}
    means.update({
        "window_samples": len(window),
        "window_mean_drag_solver": sum(row["drag_solver"] for row in window) / len(window),
        "window_mean_downforce_solver": sum(row["downforce_solver"] for row in window) / len(window),
        "diagnostic_first_half_mean_drag_solver": sum(row["drag_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_drag_solver": sum(row["drag_solver"] for row in second) / len(second),
        "diagnostic_first_half_mean_downforce_solver": sum(row["downforce_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_downforce_solver": sum(row["downforce_solver"] for row in second) / len(second),
    })
    for quantity, key in (("drag", "drag_solver"), ("downforce", "downforce_solver")):
        first_mean = time_weighted_mean(first_weighted_window, key)
        second_mean = time_weighted_mean(second_weighted_window, key)
        whole_mean = means[f"window_time_weighted_{key}"]
        means[f"stationarity_first_half_time_weighted_{quantity}_solver"] = first_mean
        means[f"stationarity_second_half_time_weighted_{quantity}_solver"] = second_mean
        means[f"stationarity_relative_half_window_drift_{quantity}"] = (
            abs(first_mean - second_mean) / max(abs(whole_mean), sys.float_info.epsilon))
    scale = (case["density_kg_m3"] * case["freestream_mps"][0] ** 2
             * case["flow_spacing_m"] ** 2)
    means["drag_time_weighted_n"] = means["window_time_weighted_drag_solver"] * scale
    means["downforce_time_weighted_n"] = means["window_time_weighted_downforce_solver"] * scale
    means["pressure_drag_time_weighted_n"] = means["window_time_weighted_pressure_fx_solver"] * scale
    means["viscous_drag_time_weighted_n"] = means["window_time_weighted_viscous_fx_solver"] * scale
    means["pressure_downforce_time_weighted_n"] = -means["window_time_weighted_pressure_fz_solver"] * scale
    means["viscous_downforce_time_weighted_n"] = -means["window_time_weighted_viscous_fz_solver"] * scale
    area_solver = case["reference_area_m2"] / case["flow_spacing_m"] ** 2
    means["cd_time_weighted"] = means["window_time_weighted_drag_solver"] / (
        0.5 * area_solver * case["freestream_mps"][0] ** 2)
    return means


def force_components_close(rows, measurement):
    rel = measurement["force_component_relative_tolerance"]
    absolute = measurement["force_component_absolute_tolerance"]
    return all(
        math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=rel, abs_tol=absolute)
        and math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=rel, abs_tol=absolute)
        and all(math.isclose(row[f"{axis}_solver"],
                             row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
                             rel_tol=rel, abs_tol=absolute)
                for axis in ("fx", "fy", "fz"))
        for row in rows
    )


def close_summary(summary, metrics, tolerance):
    return all(math.isclose(summary.get(key, math.nan), value,
                            rel_tol=tolerance, abs_tol=1e-10)
               for key, value in metrics.items())
# ---- END verbatim copy ----


# ---- new code ----

def literal_false_flags(value):
    keys = {"shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology"}
    return isinstance(value, dict) and set(value) == keys and all(value[key] is False for key in keys)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def discover_dataset():
    matches = sorted(INPUT_ROOT.rglob("xfidc_criteria.json"))
    require(len(matches) == 1, f"expected one attached xfidc_criteria.json, found {len(matches)}")
    return matches[0].parent


def read_criteria(dataset_dir):
    require(CRITERIA_SHA256 != "__CRITERIA_SHA256__", "runner has not been bound to registered criteria")
    path = Path(dataset_dir) / "xfidc_criteria.json"
    sidecar = Path(dataset_dir) / "xfidc_criteria.json.sha256"
    digest = sha256(path)
    require(digest == CRITERIA_SHA256 and sidecar.read_text().strip() == CRITERIA_SHA256, "criteria SHA mismatch")
    criteria = json.loads(path.read_text())
    require(criteria.get("immutable") is True and criteria.get("registered_before_computation") is True,
            "criteria are not an immutable preregistration")
    require(literal_false_flags(criteria.get("qualification_flags")), "qualification flags must be literal false")
    return criteria


def verify_dataset(criteria, dataset_dir):
    dataset_dir = Path(dataset_dir)
    expected = dict(criteria["dataset_files"])
    expected["xfidc_criteria.json"] = CRITERIA_SHA256
    expected["xfidc_criteria.json.sha256"] = sha256(dataset_dir / "xfidc_criteria.json.sha256")
    actual = {p.relative_to(dataset_dir).as_posix() for p in dataset_dir.rglob("*") if p.is_file()}
    require(actual == set(expected), f"attached dataset inventory differs from registration: {sorted(actual ^ set(expected))}")
    for name, digest in expected.items():
        require(sha256(dataset_dir / name) == digest, f"dataset file SHA-256 mismatch: {name}")


def gpu_inventory(criteria):
    """Same checks as the W4-C runner except the host driver version, which is recorded and not gated (user decision)."""
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [[cell.strip() for cell in row] for row in csv.reader(text.splitlines()) if row]
    expected = criteria["backend"]
    require(len(rows) == expected["gpu_count"], "registered T4 inventory count mismatch")
    require([row[0] for row in rows] == [str(i) for i in range(len(rows))], "GPU index inventory mismatch")
    uuids = [row[2] for row in rows]
    require(len(set(uuids)) == len(uuids) and all(u.startswith("GPU-") for u in uuids)
            and all(expected["gpu_name"] in row[1] for row in rows), "registered T4 identity mismatch")
    require(len({row[-1] for row in rows}) == 1, "GPU driver versions disagree across devices")
    return [", ".join(row) for row in rows], uuids[0]


def verify_source(source, criteria):
    for name, entry in criteria["source_inputs"].items():
        path = Path(source) / entry["path"]
        require(path.is_file() and sha256(path) == entry["sha256"], f"registered source input SHA mismatch: {name}")
    project = Path(source) / "julia/CFDSDFWaterLilyT4"
    for name in ("project", "manifest"):
        entry = criteria["source_inputs"][name]
        require(sha256(project / Path(entry["path"]).name) == entry["sha256"], f"Julia {name} SHA mismatch")
    sys.path.insert(0, str(Path(source) / "src"))
    from cfd_sdf.candidate_c_identity import load_candidate_c_identity
    frozen = load_candidate_c_identity(Path(source))
    record = json.loads((Path(source) / frozen["contract_path"]).read_text())
    identity = criteria["operator_identity"]
    require(identity["contract_path"] == frozen["contract_path"] and identity["contract_sha256"] == frozen["contract_sha256"]
            and criteria["operator"] == record["operator"], "criteria do not bind the exact frozen Candidate C identity")
    return project


def verify_state(name, st, criteria, dataset_dir):
    import numpy as np

    npz, raw = Path(dataset_dir) / st["npz_file"], Path(dataset_dir) / st["raw_file"]
    geometry = criteria["geometry"]
    with np.load(npz, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    require(np.isfinite(phi).all() and list(phi.shape) == geometry["point_shape"], f"{name}: phi shape or finiteness mismatch")
    require(metadata.get("state_sha256") == st["state_sha256"], f"{name}: state identity mismatch")
    require(metadata.get("source_sha256") == geometry["source_surface_sha256"], f"{name}: source-surface lineage mismatch")
    require(metadata.get("origin_m") == geometry["canonical_sdf_origin_m"] and metadata.get("spacing_m") == geometry["design_lattice_spacing_m"],
            f"{name}: design-lattice metadata mismatch")
    phi_c = sha256_bytes(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C"))
    phi_f = sha256_bytes(np.asarray(phi, dtype="<f4", order="F").tobytes(order="F"))
    require(phi_c == st["phi_c_order_sha256"] and metadata.get("phi_sha256") == phi_c and phi_f == st["phi_fortran_sha256"],
            f"{name}: phi hash mismatch")
    require(raw.read_bytes() == np.asarray(phi, dtype="<f4", order="F").tobytes(order="F"), f"{name}: raw phi differs from NPZ")
    margin = zero_level_margin_m(phi, geometry["design_lattice_spacing_m"], name)
    require(math.isfinite(margin) and abs(margin - st["phi_expected_margin_m"]) <= geometry["phi_margin_tolerance_m"]
            and margin >= geometry["phi_margin_gate_m"], f"{name}: CPU-side SDF margin failed ({margin})")
    return raw, margin


def state_env(base_env, st, criteria, selected_uuid):
    geometry = criteria["geometry"]
    env = dict(base_env)
    env.update({
        "W4_SELECTED_GPU_UUID": selected_uuid,
        "W4_CANONICAL_STATE_LABEL": "xfid_" + st["name"],
        "W4_STATE_SHA256": st["state_sha256"],
        "W4_STATE_NPZ_SHA256": st["npz_sha256"],
        "W4_PHI_C_ORDER_SHA256": st["phi_c_order_sha256"],
        "W4_PHI_FORTRAN_SHA256": st["phi_fortran_sha256"],
        "W4_SOURCE_SURFACE_SHA256": geometry["source_surface_sha256"],
        "W4_POINT_SHAPE": ",".join(map(str, geometry["point_shape"])),
        "W4_CELL_SHAPE": ",".join(map(str, geometry["cell_shape"])),
        "W4_CANONICAL_ORIGIN_M": ",".join(map(str, geometry["canonical_sdf_origin_m"])),
        "W4_CANONICAL_DESIGN_SPACING_M": str(geometry["design_lattice_spacing_m"]),
        "W4_EXPECTED_MARGIN_M": str(st["phi_expected_margin_m"]),
        "W4_MARGIN_TOLERANCE_M": str(geometry["phi_margin_tolerance_m"]),
        "W4_MARGIN_GATE_M": str(geometry["phi_margin_gate_m"]),
    })
    return env


def evaluate_state(name, st, criteria, outdir, log_text, margin):
    """Host recomputation and registered integrity gates for one state's flow_24 run."""
    measurement, case, backend = criteria["measurement"], criteria["case"], criteria["backend"]
    invoked = [l.split()[-1] for l in log_text.splitlines() if l.startswith("W4_SOLVER_STEP_INVOKED ")]
    returned = [l.split()[-1] for l in log_text.splitlines() if l.startswith("W4_SOLVER_STEP_RETURNED ")]
    summary = json.loads((outdir / "flow_24.summary.json").read_text())
    csv_path = outdir / "flow_24.forces.csv"
    require(sha256(csv_path) == summary.get("force_csv_sha256"), f"{name}: force CSV hash mismatch")
    rows = parse_force_csv(csv_path)
    metrics = recompute_case_metrics(rows, case, measurement)
    tolerance = measurement["host_recompute_relative_tolerance"]
    gates = {
        "solver_step_markers": invoked == ["flow_24"] and returned == ["flow_24"],
        "force_components_consistent": force_components_close(rows, measurement),
        "host_metrics_match_summary": close_summary(summary, metrics, tolerance),
        "finite": all(summary.get(k) is True for k in ("finite_u", "finite_p", "finite_forces")),
        "t_end_reached": summary.get("t_end_reached", 0.0) >= measurement["target_t_u_l"],
        "state_identity": summary.get("state_sha256") == st["state_sha256"] and summary.get("phi_fortran_sha256") == st["phi_fortran_sha256"]
        and summary.get("device_roundtrip_sha256") == st["phi_fortran_sha256"],
        "body_and_backend": summary.get("force_integration_body") == measurement["force_integration_body"]
        and summary.get("waterlily_version") == backend["waterlily_version"] and summary.get("cuda_jl_version") == backend["cuda_jl_version"]
        and summary.get("julia_version") == backend["julia_version"] and summary.get("gpu_name", "").find(backend["gpu_name"]) >= 0,
        "vram": 0 < summary.get("peak_vram_bytes", 0) < summary.get("vram_total_bytes", 0),
    }
    drift = max(metrics["stationarity_relative_half_window_drift_drag"], metrics["stationarity_relative_half_window_drift_downforce"])
    result = {
        "status": "COMPLETED" if all(gates.values()) else "GATE_FAILED",
        "gates": gates,
        "stationarity_drift_max": drift,
        "stationarity_within_registered_limit": drift <= measurement["stationarity"]["relative_half_window_drift_max"],
        "phi_margin_m": margin,
        "forces_n": {k: metrics[k] for k in ("drag_time_weighted_n", "downforce_time_weighted_n", "pressure_drag_time_weighted_n",
                                              "viscous_drag_time_weighted_n", "pressure_downforce_time_weighted_n", "viscous_downforce_time_weighted_n")},
        "cd_time_weighted": metrics["cd_time_weighted"],
        "wall_seconds": summary.get("wall_seconds"), "steps": summary.get("steps"),
        "peak_vram_bytes": summary.get("peak_vram_bytes"),
        "force_csv_sha256": summary.get("force_csv_sha256"),
    }
    write_json(outdir / "state_result.json", result)
    return result


def run_state(st, criteria, dataset_dir, source, project, julia, base_env, selected_uuid, timeout_s):
    name = st["name"]
    outdir = OUT / "states" / name
    outdir.mkdir(parents=True)
    raw, margin = verify_state(name, st, criteria, dataset_dir)
    env = state_env(base_env, st, criteria, selected_uuid)
    job = Path(source) / criteria["source_inputs"]["job"]["path"]
    log = outdir / "job.log"
    command([str(julia), "--startup-file=no", f"--project={project}", str(job), str(raw), str(outdir)], log, env=env, timeout=timeout_s)
    return evaluate_state(name, st, criteria, outdir, log.read_text(errors="replace"), margin)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    set_stage("criteria_discovery")
    dataset_dir = discover_dataset()
    criteria = read_criteria(dataset_dir)
    verify_dataset(criteria, dataset_dir)
    set_stage("dataset_verified")
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    driver = gpu_rows[0].split(", ")[-1]
    runner_sha = sha256(Path(__file__))
    with tempfile.TemporaryDirectory(prefix="cfd_xfidc_") as temp:
        base = Path(temp)
        source = base / "source"
        set_stage("source_fetch")
        command(["git", "init", "-q", str(source)], OUT / "git_init.log")
        command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH), SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=600)
        command(["git", "-C", str(source), "checkout", "--detach", criteria["source_commit"]], OUT / "git_checkout.log")
        actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        require(actual == criteria["source_commit"], "source commit mismatch")
        project = verify_source(source, criteria)
        julia = install_julia(base, criteria)
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": str(criteria["backend"]["julia_threads"]), "CUDA_VISIBLE_DEVICES": criteria["backend"]["cuda_visible_devices"]})
        set_stage("project_instantiate")
        command([str(julia), "--startup-file=no", f"--project={project}", "-e", "using Pkg; Pkg.instantiate()"],
                OUT / "instantiate.log", env=env, timeout=1800)
        for name in ("project", "manifest"):
            entry = criteria["source_inputs"][name]
            require(sha256(project / Path(entry["path"]).name) == entry["sha256"], f"Julia {name} changed during instantiate")
        set_stage("t4_smoke")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}", str(source / criteria["source_inputs"]["kaggle_smoke"]["path"])],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        b = criteria["backend"]
        markers = ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", f"GPU_COMPUTE_CAPABILITY {b['compute_capability']}",
                   f"CUDA_DRIVER_VERSION {b['cuda_driver_api_version']}", f"CUDA_RUNTIME_VERSION {b['cuda_runtime_version']}",
                   f"JULIA_VERSION {b['julia_version']}", f"CUDA_JL_VERSION {b['cuda_jl_version']}",
                   f"WATERLILY_VERSION {b['waterlily_version']}", f"GPU_NAME {b['gpu_name']}", "NO_SOLVER_STEP")
        require(all(m in smoke for m in markers), "registered T4 smoke identity mismatch")
        results = {}
        for st in criteria["state_order"]:
            set_stage("state_" + st["name"])
            try:
                results[st["name"]] = run_state(st, criteria, dataset_dir, source, project, julia, env, selected_uuid, criteria["per_state_timeout_s"])
            except Exception as exc:  # per-state fail-soft: the solver is deterministic, later states still run
                results[st["name"]] = {"status": "STATE_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
            write_json(OUT / "result.json", {"criteria_sha256": CRITERIA_SHA256, "states": results, "partial": True})
        counts = {}
        for r in results.values():
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        write_json(OUT / "result.json", {
            "criteria_sha256": CRITERIA_SHA256, "runner_sha256": runner_sha, "round_id": criteria["round_id"],
            "source_commit": actual, "gpu_inventory": gpu_rows, "host_driver_version_recorded_not_gated": driver,
            "platform": platform.platform(), "python": platform.python_version(), "elapsed_s": time.monotonic() - started,
            "states": results, "status_counts": counts, "all_states_completed": counts == {"COMPLETED": len(criteria["state_order"])},
            "qualification_flags": criteria["qualification_flags"]})
    manifest = {p.relative_to(OUT).as_posix(): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name not in {"sha256.json", "DONE"}}
    write_json(OUT / "sha256.json", manifest)
    (OUT / "DONE").write_text(json.dumps({"status": "FINISHED_STATE_LOOP", "status_counts": counts}, sort_keys=True) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        write_json(OUT / "ERROR.json", {"status": "FAIL", "stage": STATE.get("stage"), "error_type": type(exc).__name__,
                                        "error": str(exc), "traceback": traceback.format_exc()[-4000:]})
        print(f"FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
