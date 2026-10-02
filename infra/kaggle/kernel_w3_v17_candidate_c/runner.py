#!/usr/bin/env python3
"""Draft runner copied from W3 v17; operator identity is Candidate C.

The canonical-state label (v16, v17, ...) comes from the attached dataset's
``w3_<label>_criteria.json``; all state identity comes from that criteria file.
"""

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path


LABEL = "v16"  # replaced by the discovered criteria label before any output is written
OUT = Path("/kaggle/working") / f"w3_{LABEL}"
INPUT_ROOT = Path("/kaggle/input")
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
SOURCE_FETCH_DEPTH = 16
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
JULIA_SHA256 = "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"
EXPECTED_DRIVER_VERSION = "580.159.04"
EXPECTED_DRIVER_API_VERSION = "13.3.0"
EXPECTED_CUDA_RUNTIME_VERSION = "12.8.0"


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


def discover_dataset(input_root=INPUT_ROOT):
    input_root = Path(input_root)
    matches = sorted(path for path in input_root.rglob("w3_*_criteria.json")
                     if path.is_file()) if input_root.is_dir() else []
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one registered W3 criteria under {input_root}, found {len(matches)}"
        )
    return matches[0].parent, matches[0]


def set_label(label):
    global LABEL, OUT
    LABEL = label
    OUT = Path("/kaggle/working") / f"w3_{label}"


def read_criteria(input_root=INPUT_ROOT):
    input_root = Path(input_root)
    dataset_dir, criteria_path = discover_dataset(input_root)
    set_label(criteria_path.name[len("w3_"):-len("_criteria.json")])
    OUT.mkdir(parents=True, exist_ok=True)
    top_level_entries = (
        sorted(f"{ 'dir' if path.is_dir() else 'file' }:{path.name}"
               for path in input_root.iterdir())
        if input_root.is_dir() else []
    )
    write_json(OUT / "input_mount_inventory.json", {
        "input_root": str(input_root),
        "input_root_exists": input_root.is_dir(),
        "top_level_entries": top_level_entries,
    })
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not sidecar.is_file():
        raise RuntimeError("registered W3 criteria SHA sidecar missing from the attached private dataset")
    expected = sidecar.read_text().strip()
    if sha256(criteria_path) != expected:
        raise RuntimeError("W3 criteria sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise RuntimeError("W3 criteria are not immutable preregistration")
    if criteria["geometry"].get("state_label", "v16") != LABEL:
        raise RuntimeError("W3 criteria state label does not match the staged criteria file name")
    operator = criteria.get("operator", {})
    if (LABEL != "v17_candidate_c"
            or criteria.get("input_dataset_id") != "ramhachi888/cfd-opt-sdf-v17-candidate-c"
            or operator.get("identity") != "candidate_c_moment_blend+normal_floor_0.25"
            or operator.get("normal_floor") != 0.25
            or operator.get("transition_width_solver") != 1.1444091796875e-4
            or operator.get("simulation_body") !=
                "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid)+moving_ground)"
            or operator.get("force_integration_body") !=
                "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))"):
        raise RuntimeError("W3 Candidate C operator/body composition identity mismatch")
    if not str(criteria.get("input_dataset_id", "")).startswith("ramhachi888/"):
        raise RuntimeError("W3 criteria dataset identity mismatch")
    return criteria, expected, dataset_dir, criteria_path


def verify_dataset_manifest(criteria, criteria_sha, dataset_dir):
    dataset_dir = Path(dataset_dir)
    manifest_path = dataset_dir / f"w3_{LABEL}_dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("dataset_id") != criteria["input_dataset_id"]:
        raise RuntimeError("W3 input dataset manifest id mismatch")
    if manifest.get("criteria_sha256") != criteria_sha:
        raise RuntimeError("W3 input dataset manifest criteria binding mismatch")
    expected_names = {
        "sdf_design_state.npz": criteria["inputs"]["canonical_state_npz"]["sha256"],
        criteria["inputs"]["canonical_phi_fortran_raw"]["path"]: criteria["inputs"]["canonical_phi_fortran_raw"]["sha256"],
        f"w3_{LABEL}_criteria.json": criteria_sha,
        f"w3_{LABEL}_criteria.json.sha256": sha256(dataset_dir / f"w3_{LABEL}_criteria.json.sha256"),
    }
    for name, expected_sha in expected_names.items():
        path = dataset_dir / name
        if not path.is_file() or sha256(path) != expected_sha:
            raise RuntimeError(f"W3 staged dataset file hash mismatch: {name}")
        if manifest.get("files", {}).get(name) != expected_sha:
            raise RuntimeError(f"W3 input dataset manifest file binding mismatch: {name}")
    return manifest_path


def gpu_inventory(criteria):
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    expected = criteria["backend"]
    if len(rows) != expected["gpu_count"]:
        raise RuntimeError("W3 T4 inventory count drift")
    if [row.split(",", 1)[0] for row in rows] != [str(i) for i in range(len(rows))]:
        raise RuntimeError("W3 GPU inventory index drift")
    if any(expected["gpu_name"] not in row for row in rows):
        raise RuntimeError("W3 T4 model drift")
    if any(row.split(", ")[-1] != expected["driver_version"] for row in rows):
        raise RuntimeError("W3 NVIDIA driver drift")
    uuids = [row.split(", ")[2] for row in rows]
    if len(set(uuids)) != len(rows) or any(not value.startswith("GPU-") for value in uuids):
        raise RuntimeError("W3 GPU UUID inventory invalid")
    return rows, uuids[0]


def verify_dataset_state(criteria, dataset_dir):
    import numpy as np

    dataset_dir = Path(dataset_dir)
    entry = criteria["inputs"]["canonical_state_npz"]
    state_path = dataset_dir / entry["path"]
    if sha256(state_path) != entry["sha256"]:
        raise RuntimeError("canonical SDF NPZ hash mismatch")
    expected = criteria["geometry"]
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    if metadata.get("state_sha256") != expected["state_sha256"]:
        raise RuntimeError("canonical SDF state identity mismatch")
    if metadata.get("phi_sha256") != expected["phi_c_order_sha256"]:
        raise RuntimeError("canonical SDF metadata phi identity mismatch")
    if metadata.get("source_sha256") != expected["source_surface_sha256"]:
        raise RuntimeError("canonical SDF source-surface binding mismatch")
    if metadata.get("shape") != expected["point_shape"]:
        raise RuntimeError("canonical SDF shape mismatch")
    if (metadata.get("origin_m") != expected["canonical_sdf_origin_m"]
            or metadata.get("spacing_m") != expected["spacing_m"]):
        raise RuntimeError("canonical SDF lattice identity mismatch")
    if phi.shape != tuple(expected["point_shape"]) or not np.isfinite(phi).all():
        raise RuntimeError("canonical SDF array shape/finiteness mismatch")
    c_order_bytes = np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")
    fortran_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    if sha256_bytes(c_order_bytes) != expected["phi_c_order_sha256"]:
        raise RuntimeError("canonical C-order phi bytes mismatch")
    raw_path = OUT / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    raw_path.write_bytes(fortran_bytes)
    if sha256(raw_path) != expected["phi_fortran_sha256"]:
        raise RuntimeError("canonical Fortran-order phi bytes mismatch")
    if sha256(dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]) != expected["phi_fortran_sha256"]:
        raise RuntimeError("staged canonical Fortran-order phi input mismatch")
    return state_path, raw_path, metadata


def fetch_source(base, criteria):
    source = base / "source"
    command(["git", "init", "-q", str(source)], OUT / "git_init.log")
    command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH),
             SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=600)
    commit = criteria["source_commit"]
    command(["git", "-C", str(source), "checkout", "--detach", commit],
            OUT / "git_checkout.log")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != commit:
        raise RuntimeError("W3 source commit drift")
    for name, entry in criteria["inputs"].items():
        if entry.get("location") == "source_repo":
            path = source / entry["path"]
            if sha256(path) != entry["sha256"]:
                raise RuntimeError(f"W3 registered source hash mismatch: {name}")
    project = source / "julia/CFDSDFWaterLilyT4"
    return source, project


def install_julia(base):
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != JULIA_SHA256:
        raise RuntimeError("Julia binary SHA-256 mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)],
            OUT / "julia_extract.log", timeout=600)
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("verified Julia binary was not extracted")
    return julia


def parse_force_csv(path):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        expected_header = [
            "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
            "drag_solver", "downforce_solver", "pressure_fx_solver",
            "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
            "viscous_fy_solver", "viscous_fz_solver",
        ]
        if reader.fieldnames != expected_header:
            raise RuntimeError("W3 force CSV schema mismatch")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    if not rows or any(not all(math.isfinite(value) for value in row.values()) for row in rows):
        raise RuntimeError("W3 force CSV is empty or non-finite")
    if any(right["t_u_l"] <= left["t_u_l"] or right["step"] <= left["step"]
           for left, right in zip(rows, rows[1:])):
        raise RuntimeError("W3 force CSV steps/times are not strictly increasing")
    return rows


def time_weighted_mean(rows, key):
    numerator = denominator = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        numerator += 0.5 * (left[key] + right[key]) * dt
        denominator += dt
    if denominator <= 0:
        return sum(row[key] for row in rows) / len(rows)
    return numerator / denominator


def clipped_force_window(rows, start, end):
    def interpolate(left, right, t):
        if not left["t_u_l"] <= t <= right["t_u_l"]:
            raise RuntimeError(f"raw force rows do not bracket tU/L={t}")
        if left["t_u_l"] == right["t_u_l"]:
            return dict(left)
        alpha = (t - left["t_u_l"]) / (right["t_u_l"] - left["t_u_l"])
        return {
            key: float(t) if key == "t_u_l" else
            left[key] + alpha * (right[key] - left[key])
            for key in left
        }

    def bracket(t):
        left = next((row for row in reversed(rows) if row["t_u_l"] <= t), None)
        right = next((row for row in rows if row["t_u_l"] >= t), None)
        if left is None or right is None:
            raise RuntimeError(f"raw force rows do not bracket exact endpoint {t}")
        return interpolate(left, right, t)

    return ([bracket(start)]
            + [row for row in rows if start < row["t_u_l"] < end]
            + [bracket(end)])


def recompute_metrics(rows, measurement):
    start, end = measurement["force_window_t_u_l"]
    middle = 0.5 * (start + end)
    raw_window = [row for row in rows if start <= row["t_u_l"] <= end]
    if len(raw_window) < measurement["minimum_window_samples"]:
        raise RuntimeError("W3 registered force-window sample count not met")
    window = clipped_force_window(rows, start, end)
    first = clipped_force_window(rows, start, middle)
    second = clipped_force_window(rows, middle, end)
    drag = time_weighted_mean(window, "drag_solver")
    downforce = time_weighted_mean(window, "downforce_solver")
    first_drag = time_weighted_mean(first, "drag_solver")
    second_drag = time_weighted_mean(second, "drag_solver")
    first_downforce = time_weighted_mean(first, "downforce_solver")
    second_downforce = time_weighted_mean(second, "downforce_solver")
    area_solver = measurement["reference_area_m2"] / measurement["spacing_m"] ** 2
    force_scale_n = (measurement["density_kg_m3"] * measurement["freestream_mps"][0] ** 2
                     * measurement["spacing_m"] ** 2)
    return {
        "window_samples": len(raw_window),
        "window_time_weighted_drag_solver": drag,
        "window_time_weighted_downforce_solver": downforce,
        "diagnostic_first_half_time_weighted_drag_solver": first_drag,
        "diagnostic_second_half_time_weighted_drag_solver": second_drag,
        "diagnostic_first_half_time_weighted_downforce_solver": first_downforce,
        "diagnostic_second_half_time_weighted_downforce_solver": second_downforce,
        "stationarity_relative_half_window_drift_drag": (
            abs(first_drag - second_drag) / max(abs(drag), float.fromhex("0x1.0p-52"))),
        "stationarity_relative_half_window_drift_downforce": (
            abs(first_downforce - second_downforce) / max(abs(downforce), float.fromhex("0x1.0p-52"))),
        "cd_time_weighted": drag / (0.5 * area_solver),
        "drag_time_weighted_n": drag * force_scale_n,
        "downforce_time_weighted_n": downforce * force_scale_n,
    }


def force_components_close(rows, measurement):
    relative = measurement["force_component_relative_tolerance"]
    absolute = measurement["force_component_absolute_tolerance"]
    return bool(rows) and all(
        math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=relative, abs_tol=absolute)
        and math.isclose(row["downforce_solver"], -row["fz_solver"],
                         rel_tol=relative, abs_tol=absolute)
        and all(math.isclose(
            row[f"{axis}_solver"],
            row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
            rel_tol=relative, abs_tol=absolute)
            for axis in ("fx", "fy", "fz"))
        for row in rows
    )


def evaluate_gates(criteria, summary, rows, source_commit, runner_sha, criteria_sha,
                   gpu_rows, smoke, source_prerequisites=True, adapter_contract=None,
                   cuda_visible_devices="0"):
    geometry = criteria["geometry"]
    profile = criteria["profile_adapter"]
    runtime = criteria["backend"]
    measurement = criteria["measurement"]
    finite_csv = bool(rows) and all(math.isfinite(value) for row in rows for value in row.values())
    sample_stride = measurement["sample_every_solver_steps"]
    force_closure = finite_csv and force_components_close(rows, measurement)
    terminal_extra = bool(rows) and rows[-1]["t_u_l"] >= measurement["t_end_t_u_l"] \
        and rows[-1]["step"] % sample_stride != 0
    regular_sampling = finite_csv and all(
        (right["step"] - left["step"] == sample_stride)
        or (terminal_extra and right is rows[-1] and right["t_u_l"] >= measurement["t_end_t_u_l"])
        for left, right in zip(rows, rows[1:])
    ) and all(row["step"] % sample_stride == 0 for row in rows[:-1] if terminal_extra)
    try:
        metrics = recompute_metrics(rows, measurement) if finite_csv else {}
    except RuntimeError:
        metrics = {}
    relative_tolerance = measurement["host_recompute_relative_tolerance"]
    metric_match = bool(metrics) and all(
        math.isclose(summary.get(key, math.nan), value, rel_tol=relative_tolerance,
                     abs_tol=1e-10)
        for key, value in metrics.items()
    )
    uuids = [row.split(", ")[2] for row in gpu_rows]
    gates = {
        "T0_registered_inputs": source_prerequisites,
        "T1_canonical_v16_identity": (
            summary.get("state_sha256") == geometry["state_sha256"]
            and summary.get("source_surface_sha256") == geometry["source_surface_sha256"]
            and summary.get("phi_c_order_sha256") == geometry["phi_c_order_sha256"]
            and summary.get("phi_fortran_sha256") == geometry["phi_fortran_sha256"]
            and summary.get("device_roundtrip_sha256") == geometry["phi_fortran_sha256"]
            and summary.get("dims") == profile["cell_dims"]
            and summary.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
            and summary.get("flow_origin_m") == profile["flow_origin_m"]
            and summary.get("flow_upper_m") == [bounds[1] for bounds in profile["physical_box_m"]]
            and summary.get("spacing_m") == geometry["spacing_m"]
        ),
        "T2_margin_gate": (
            summary.get("phi_margin_gate_m") == geometry["margin_gate_m"]
            and summary.get("phi_margin_m", -math.inf) >= geometry["margin_gate_m"]
            and abs(summary.get("phi_margin_m", math.inf) - geometry["expected_margin_m"])
            <= geometry["margin_tolerance_m"]
        ),
        "T3_profile_adapter_is_explicitly_limited": (
            summary.get("source_profile_equivalent") is False
            and summary.get("physical_profile_qualified") is False
            and adapter_contract is not None
            and adapter_contract.get("source_profile_equivalent") is False
            and adapter_contract.get("physical_profile_qualified") is False
            and summary.get("x_max_boundary") == profile["x_max_boundary"]
            and summary.get("pressure_boundary") == profile["pressure_boundary"]
            and adapter_contract.get("flow_origin_m") == profile["flow_origin_m"]
            and adapter_contract.get("flow_cell_dims") == profile["cell_dims"]
            and adapter_contract.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
            and math.isclose(summary.get("solver_length", math.nan),
                             profile["solver_length"], rel_tol=0, abs_tol=1e-7)
            and math.isclose(summary.get("solver_viscosity", math.nan),
                             profile["solver_viscosity"], rel_tol=0, abs_tol=1e-7)
            and summary.get("reynolds") == profile["reynolds"]
        ),
        "T4_backend_identity": (
            len(gpu_rows) == runtime["gpu_count"]
            and len(set(uuids)) == runtime["gpu_count"]
            and all(runtime["gpu_name"] in row and row.split(", ")[-1] == runtime["driver_version"]
                    for row in gpu_rows)
            and JULIA_SHA256 == runtime["julia_archive_sha256"]
            and summary.get("gpu_uuid") == uuids[0]
            and summary.get("gpu_name") == "Tesla T4"
            and summary.get("julia_version") == runtime["julia_version"]
            and summary.get("julia_threads") == runtime["julia_threads"]
            and summary.get("waterlily_version") == runtime["waterlily_version"]
            and summary.get("cuda_jl_version") == runtime["cuda_jl_version"]
            and bool(summary.get("waterlily_backend"))
            and cuda_visible_devices == runtime["cuda_visible_devices"]
            and all(marker in smoke for marker in (
                "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
                f"GPU_COMPUTE_CAPABILITY {runtime['compute_capability']}",
                f"CUDA_DRIVER_VERSION {EXPECTED_DRIVER_API_VERSION}",
                f"CUDA_RUNTIME_VERSION {EXPECTED_CUDA_RUNTIME_VERSION}",
                f"JULIA_VERSION {runtime['julia_version']}",
                f"CUDA_JL_VERSION {runtime['cuda_jl_version']}",
                f"WATERLILY_VERSION {runtime['waterlily_version']}",
                f"GPU_NAME {runtime['gpu_name']}", "NO_SOLVER_STEP",
            ))
        ),
        "T5_primal_completion": (
            summary.get("t_end_target") == measurement["t_end_t_u_l"]
            and summary.get("t_end_reached", 0) >= measurement["t_end_t_u_l"]
            and summary.get("steps", 0) > 0
        ),
        "T6_finite_fields_and_candidate_forces": (
            summary.get("finite_u") is True and summary.get("finite_p") is True
            and finite_csv and summary.get("force_samples", 0) == len(rows)
            and regular_sampling
            and summary.get("window_samples", 0) >= measurement["minimum_window_samples"]
        ),
        "T7_drag_orientation_and_host_recomputation": (
            math.isfinite(summary.get("window_time_weighted_drag_solver", math.nan))
            and summary.get("window_time_weighted_drag_solver", 0) > 0
            and force_closure
            and metric_match
        ),
        "T8_runtime_and_vram": (
            0 < summary.get("wall_seconds", 0) <= measurement["runtime_limit_s"]
            and 0 < summary.get("peak_vram_bytes", 0) < summary.get("vram_total_bytes", 0)
        ),
        "T9_source_commit_and_runner": (
            source_commit == criteria["source_commit"]
            and runner_sha == criteria["inputs"]["kernel_runner"]["sha256"]
            and len(criteria_sha) == 64
        ),
        "T10_stationarity": (
            bool(metrics)
            and metrics.get("stationarity_relative_half_window_drift_drag", math.inf)
            <= measurement["stationarity"]["relative_half_window_drift_max"]
            and metrics.get("stationarity_relative_half_window_drift_downforce", math.inf)
            <= measurement["stationarity"]["relative_half_window_drift_max"]
        ),
    }
    return gates, metrics


def main():
    criteria, criteria_sha, dataset_dir, criteria_path = read_criteria()
    dataset_manifest_path = verify_dataset_manifest(criteria, criteria_sha, dataset_dir)
    runner_sha = sha256(Path(__file__))
    if runner_sha != criteria["inputs"]["kernel_runner"]["sha256"]:
        raise RuntimeError("W3 Kaggle kernel runner hash mismatch")
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    state_path, raw_phi_path, state_metadata = verify_dataset_state(criteria, dataset_dir)
    write_json(OUT / "input_state_metadata.json", state_metadata)
    (OUT / "input_dataset_manifest.json").write_bytes(dataset_manifest_path.read_bytes())
    with tempfile.TemporaryDirectory(prefix="cfd_w3_") as temp:
        base = Path(temp)
        source, project = fetch_source(base, criteria)
        command(["git", "-C", str(source), "status", "--porcelain"], OUT / "git_status.log")
        if sha256(project / "Project.toml") != criteria["inputs"]["project"]["sha256"]:
            raise RuntimeError("W3 T4 project hash mismatch")
        if sha256(project / "Manifest.toml") != criteria["inputs"]["manifest"]["sha256"]:
            raise RuntimeError("W3 T4 manifest hash mismatch")
        julia = install_julia(base)
        env = os.environ.copy()
        geometry = criteria["geometry"]
        env.update({"JULIA_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "0",
                    "W3_SELECTED_GPU_UUID": selected_uuid,
                    "W3_STATE_LABEL": LABEL,
                    "W3_STATE_SHA256": geometry["state_sha256"],
                    "W3_PHI_C_ORDER_SHA256": geometry["phi_c_order_sha256"],
                    "W3_PHI_FORTRAN_SHA256": geometry["phi_fortran_sha256"],
                    "W3_SOURCE_SURFACE_SHA256": geometry["source_surface_sha256"],
                    "W3_POINT_SHAPE": ",".join(str(v) for v in geometry["point_shape"]),
                    "W3_SDF_SPACING_M": repr(float(geometry["spacing_m"])),
                    "W3_EXPECTED_MARGIN_M": repr(float(geometry["expected_margin_m"]))})
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log",
                env=env, timeout=1800)
        if sha256(project / "Project.toml") != criteria["inputs"]["project"]["sha256"]:
            raise RuntimeError("W3 T4 Project.toml changed during instantiate")
        if sha256(project / "Manifest.toml") != criteria["inputs"]["manifest"]["sha256"]:
            raise RuntimeError("W3 T4 Manifest.toml changed during instantiate")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / "scripts/w0b_t4_smoke.jl")],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        required_smoke = (
            "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true", "GPU_COMPUTE_CAPABILITY 7.5.0",
            f"CUDA_DRIVER_VERSION {EXPECTED_DRIVER_API_VERSION}",
            f"CUDA_RUNTIME_VERSION {EXPECTED_CUDA_RUNTIME_VERSION}",
            "JULIA_VERSION 1.12.6", "CUDA_JL_VERSION 6.3.1",
            "WATERLILY_VERSION 1.8.0", "GPU_NAME Tesla T4", "NO_SOLVER_STEP",
        )
        if any(marker not in smoke for marker in required_smoke):
            raise RuntimeError("W3 registered T4 CUDA smoke mismatch")
        job = source / criteria["inputs"]["job"]["path"]
        command([str(julia), "--startup-file=no", f"--project={project}", str(job),
                 str(raw_phi_path), str(OUT)], OUT / f"w3_{LABEL}.log", env=env, timeout=5400)

    summary_path = OUT / f"{LABEL}.summary.json"
    csv_path = OUT / f"{LABEL}.forces.csv"
    if not summary_path.is_file() or not csv_path.is_file():
        raise RuntimeError("W3 job output files are incomplete")
    summary = json.loads(summary_path.read_text())
    if sha256(csv_path) != summary.get("force_csv_sha256"):
        raise RuntimeError("W3 candidate-force CSV hash mismatch")
    rows = parse_force_csv(csv_path)
    adapter_contract = json.loads((OUT / "w3_adapter_contract.json").read_text())
    gates, metrics = evaluate_gates(
        criteria, summary, rows, criteria["source_commit"], runner_sha,
        criteria_sha, gpu_rows, smoke, adapter_contract=adapter_contract,
        cuda_visible_devices=env["CUDA_VISIBLE_DEVICES"],
    )
    write_json(OUT / "fingerprint.json", {
        "criteria_sha256": criteria_sha,
        "criteria_path": criteria_path.name,
        "dataset_id": criteria["input_dataset_id"],
        "state_npz_sha256": sha256(state_path),
        "runner_sha256": runner_sha,
        "source_commit": criteria["source_commit"],
        "gpu_inventory": gpu_rows,
        "selected_gpu_uuid": selected_uuid,
        "julia_archive_sha256": JULIA_SHA256,
        "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
        "platform": platform.platform(),
        "python": platform.python_version(),
    })
    write_json(OUT / "outcome.json", {
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "dataset_id": criteria["input_dataset_id"],
        "state_npz_sha256": sha256(state_path),
        "selected_gpu_uuid": selected_uuid,
        "summary": summary,
        "host_recomputed_metrics": metrics,
        "gates": gates,
        "stationarity_relative_drift_limit": criteria["measurement"]["stationarity"]["relative_half_window_drift_max"],
        "physical_profile_qualified": False,
        "shape_update_allowed": False,
    })
    if not all(gates.values()):
        raise RuntimeError(f"W3 registered gates failed: {gates}")
    manifest = {
        path.name: sha256(path) for path in sorted(OUT.iterdir())
        if path.is_file() and path.name not in {"sha256.json", "DONE"}
    }
    write_json(OUT / "sha256.json", manifest)
    (OUT / "DONE").write_text(f"Kaggle W3 {LABEL} registered first-primal gates completed; verify retrieved SHA-256 files\n")
    print(f"KAGGLE_W3_{LABEL.upper()}_DONE", json.dumps(gates, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERROR.txt").write_text(traceback.format_exc())
        manifest = {
            path.name: sha256(path) for path in sorted(OUT.iterdir())
            if path.is_file() and path.name not in {"sha256.json", "DONE"}
        }
        write_json(OUT / "sha256.json", manifest)
        raise
