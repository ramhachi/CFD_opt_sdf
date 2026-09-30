#!/usr/bin/env python3
"""Run the immutable criteria-bound centered-FD batch on one Kaggle T4."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import traceback
import urllib.request
from pathlib import Path

import numpy as np


STAGE = "sdf_directional_fd_v16"
OUT = Path("/kaggle/working") / STAGE
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
CRITERIA_NAME = "sdf_directional_fd_v16_criteria.json"
MANIFEST_NAME = "sdf_directional_fd_v16_dataset_manifest.json"
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver", "drag_solver",
    "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
    "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver",
]
EXPECTED_DIRECTIONS = ("D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026")
EXPECTED_EPSILONS = (0.0005, 0.001, 0.0025, 0.005, 0.01)
EXPECTED_RUN_ORDER = ["baseline_A"]
for _direction in EXPECTED_DIRECTIONS:
    for _epsilon in EXPECTED_EPSILONS:
        EXPECTED_RUN_ORDER.extend([
            f"{_direction}__eps_{_epsilon:.4f}".replace(".", "p") + "m__plus",
            f"{_direction}__eps_{_epsilon:.4f}".replace(".", "p") + "m__minus",
        ])
        if _direction == "D1_filtered_seed11" and _epsilon == 0.0025:
            EXPECTED_RUN_ORDER.append("baseline_B")
EXPECTED_RUN_ORDER.append("baseline_C")
STATE = {"stage": "startup", "solver_step_invoked": [], "solver_step_returned": []}


def configure_criteria(criteria: dict) -> None:
    """Use registered artifact names and inventories; preserve v16 defaults."""
    global STAGE, OUT, CRITERIA_NAME, MANIFEST_NAME
    global EXPECTED_DIRECTIONS, EXPECTED_EPSILONS, EXPECTED_RUN_ORDER
    artifacts = criteria.get("artifacts", {})
    CRITERIA_NAME = artifacts.get("dataset_criteria_filename", CRITERIA_NAME)
    MANIFEST_NAME = artifacts.get("dataset_manifest_filename", MANIFEST_NAME)
    STAGE = artifacts.get("kernel_output_directory", STAGE)
    OUT = Path("/kaggle/working") / STAGE
    EXPECTED_DIRECTIONS = tuple(criteria["direction_inventory"])
    EXPECTED_EPSILONS = tuple(sorted({float(row["epsilon_m"])
                                      for row in criteria["perturbation_inventory"]}))
    EXPECTED_RUN_ORDER = list(criteria["run_order"])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n")


def set_stage(stage: str, **details) -> None:
    STATE["stage"] = stage
    STATE.update(details)
    write_json(OUT / "execution_state.json", STATE)


def command(args, log_path: Path, *, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def discover_dataset(input_root=Path("/kaggle/input")) -> Path:
    matches = sorted(input_root.rglob("sdf_directional_fd_*_criteria.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one attached FD criteria file, found {len(matches)}")
    return matches[0].parent


def criteria_digest(criteria: dict) -> str:
    value = {key: item for key, item in criteria.items() if key != "criteria_sha256"}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256_bytes(payload)


def read_criteria(dataset_dir: Path):
    matches = sorted(dataset_dir.glob("sdf_directional_fd_*_criteria.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one attached FD criteria file, found {len(matches)}")
    path = matches[0]
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise RuntimeError("FD criteria or its SHA sidecar is missing")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise RuntimeError("FD criteria sidecar SHA mismatch")
    criteria = json.loads(path.read_text())
    if (criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("source_commit") != criteria.get("registered_source_commit")
            or criteria.get("formal_measurement_started") is not False
            or criteria.get("criteria_sha256") != criteria_digest(criteria)):
        raise RuntimeError("FD criteria are not the expected immutable preregistration")
    if (not str(criteria.get("kind", "")).startswith("sdf_directional_fd_")
            or not criteria.get("input_dataset_id")):
        raise RuntimeError("unexpected FD criteria kind or dataset id")
    configure_criteria(criteria)
    return criteria, digest


def registered_dataset_files(criteria):
    return {entry["path"]: entry["sha256"] for entry in criteria["inputs"].values()
            if entry.get("location") == "kaggle_dataset"}


def verify_dataset(criteria, criteria_sha: str, dataset_dir: Path) -> tuple[dict, dict[str, str]]:
    manifest_path = dataset_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RuntimeError("registered FD input dataset manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    expected = registered_dataset_files(criteria)
    expected[CRITERIA_NAME] = criteria_sha
    sidecar_name = CRITERIA_NAME + ".sha256"
    expected[sidecar_name] = sha256(dataset_dir / sidecar_name)
    if (manifest.get("dataset_id") != criteria["input_dataset_id"]
            or manifest.get("criteria_sha256") != criteria_sha
            or manifest.get("source_commit") != criteria["source_commit"]
            or manifest.get("files") != expected):
        raise RuntimeError("FD dataset manifest identity or registered inventory mismatch")
    actual = {path.relative_to(dataset_dir).as_posix() for path in dataset_dir.rglob("*") if path.is_file()}
    actual.discard("dataset-metadata.json")
    allowed = set(expected) | {MANIFEST_NAME}
    if actual != allowed:
        raise RuntimeError(f"FD mounted input inventory mismatch: extra={actual-allowed}, missing={allowed-actual}")
    for name, digest in expected.items():
        path = dataset_dir / name
        if not path.is_file() or sha256(path) != digest:
            raise RuntimeError(f"FD dataset file SHA mismatch: {name}")
    return manifest, {name: sha256(dataset_dir / name) for name in sorted(expected)}


def verify_prerequisites(source: Path, criteria: dict) -> tuple[dict, dict]:
    prereq = criteria["prerequisites"]
    w4_result = None
    for key in ("w3", "w4"):
        info = prereq[key]
        criteria_path = source / info["criteria_path"]
        result_path = source / info["result_path"]
        if sha256(criteria_path) != info["criteria_sha256"] or sha256(result_path) != info["result_sha256"]:
            raise RuntimeError(f"exact {key.upper()} prerequisite SHA mismatch")
        result = json.loads(result_path.read_text())
        observed_backend = result.get("backend_identity", {})
        registered_backend = (observed_backend.get("registered_backend", observed_backend)
                             if key == "w4" else observed_backend)
        if (result.get("verdict") != "PASS" or result.get("host_verification_passed") is not True
                or registered_backend != info["backend_identity"]):
            raise RuntimeError(f"exact {key.upper()} prerequisite is not host-verified PASS")
        if key == "w4":
            w4_result = result
            observation = result.get("backend_identity", {})
            observation_sha = sha256_bytes(json.dumps(
                observation, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
            if (result.get("fd_entry_gate") != info.get("fd_entry_gate")
                    or result.get("extended_domain_fine_grid_required", False) is not info.get("extended_domain_fine_grid_required")
                    or result.get("formal_fd_measurement_started", False) is not info.get("formal_fd_measurement_started")
                    or result.get("selected_gpu_uuid", observation.get("selected_gpu_uuid")) != info["selected_gpu_uuid"]
                    or observation_sha != info["observed_backend_identity_sha256"]):
                raise RuntimeError("W4 FD entry or observed-backend prerequisite does not match registration")
    if prereq["w3"]["backend_identity"] != prereq["w4"]["backend_identity"]:
        raise RuntimeError("W3/W4 prerequisite runtime identities differ")
    if w4_result is None:
        raise RuntimeError("exact W4 prerequisite result was not loaded")
    return prereq["w4"]["backend_identity"], w4_result


def w4_force_metrics(result: dict, flow_id: str) -> dict:
    """Read host-recomputed W4 metrics from either the v16 or v17 result schema."""
    case = result.get("case_measurements", {}).get(flow_id, {})
    metrics = case.get("force_metrics_host_recomputed")
    if metrics is None:
        metrics = result.get("force_metrics", {}).get(flow_id)
        if metrics is None:
            raise RuntimeError(f"W4 host-recomputed force metrics are missing for {flow_id}")
        for total_key, metric_key in (("total_drag_n", "drag_time_weighted_n"),
                                      ("total_downforce_n", "downforce_time_weighted_n")):
            if total_key in case and case[total_key] != metrics.get(metric_key):
                raise RuntimeError(f"W4 case summary and force metrics differ for {flow_id}: {metric_key}")
    return metrics


def verify_source(source: Path, criteria: dict) -> Path:
    for name, entry in criteria["inputs"].items():
        if entry.get("location") == "source_repo":
            path = source / entry["path"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise RuntimeError(f"registered FD source SHA mismatch: {name}")
    return source / criteria["inputs"]["project"]["path"]


def verify_canonical_and_preflight(source: Path, dataset_dir: Path, criteria: dict):
    sys.path.insert(0, str(source / "src"))
    from cfd_sdf.design.sdf_state import SDFDesignState
    from cfd_sdf.gradients.directional_fd import (
        perturbation_case_id,
        perturbed_state, phi_sha256, validate_directions, zero_level_margin_m,
    )

    state_entry = criteria["inputs"]["canonical_state_npz"]
    state = SDFDesignState.load(dataset_dir / state_entry["path"])
    geometry = criteria["geometry"]
    if (state.state_sha256 != geometry["canonical_state_sha256"]
            or list(state.shape) != geometry["point_shape"]
            or list(state.origin_m) != geometry["canonical_sdf_origin_m"]
            or state.spacing_m != geometry["design_spacing_m"]
            or state.narrow_band_width_m != geometry["narrow_band_width_m"]
            or state.source_sha256 != geometry["source_surface_sha256"]):
        raise RuntimeError("canonical NPZ/SDF metadata differs from registered FD criteria")
    canonical_raw = dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    c_sha = phi_sha256(state.phi, order="C")
    f_bytes = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    f_sha = sha256_bytes(f_bytes)
    if (c_sha != geometry["canonical_phi_c_order_sha256"]
            or f_sha != geometry["canonical_phi_fortran_sha256"]
            or canonical_raw.read_bytes() != f_bytes):
        raise RuntimeError("canonical C/F phi identity or raw Fortran data mismatch")
    margin = zero_level_margin_m(state.phi, state.spacing_m)
    if (not math.isfinite(margin)
            or not math.isclose(margin, geometry["canonical_phi_margin_m"], rel_tol=0, abs_tol=1e-6)
            or margin < geometry["margin_gate_m"]):
        raise RuntimeError("canonical CPU-side SDF margin fails its registered identity/gate")
    mask_hashes = {}
    for mask_name, field_name in (("design_mask_sha256", "design_mask"),
                                  ("fixed_solid_mask_sha256", "fixed_solid_mask"),
                                  ("forbidden_mask_sha256", "forbidden_mask"),
                                  ("root_mask_sha256", "root_mask")):
        digest = sha256_bytes(np.ascontiguousarray(getattr(state, field_name), dtype="u1").tobytes())
        if digest != geometry[mask_name]:
            raise RuntimeError(f"canonical {field_name} SHA differs from immutable criteria")
        mask_hashes[field_name] = digest
    dirs = {}
    direction_raw_hashes = {}
    direction_ids = tuple(criteria["direction_inventory"])
    for direction_id in direction_ids:
        record = criteria["direction_inventory"][direction_id]
        raw = (dataset_dir / record["dataset_path"]).read_bytes()
        expected_bytes = int(np.prod(record["shape"])) * np.dtype("<f4").itemsize
        if len(raw) != expected_bytes or sha256_bytes(raw) != record["sha256"]:
            raise RuntimeError(f"registered direction raw input hash/length mismatch: {direction_id}")
        direction = np.frombuffer(raw, dtype="<f4").reshape(record["shape"])
        dirs[direction_id] = direction
        direction_raw_hashes[direction_id] = record["sha256"]
    audit = validate_directions(state, dirs)
    if (tuple(dirs) != direction_ids
            or direction_raw_hashes != criteria["direction_audit"]["direction_sha256"]
            or audit["direction_sha256"] != criteria["direction_audit"]["direction_sha256"]
            or max(abs(value) for value in audit["pairwise_cosine"].values())
                > criteria["directions"]["max_pairwise_abs_cosine"]):
        raise RuntimeError("frozen direction hashes, structure, or nonduplication gate mismatch")
    if len(criteria["perturbation_inventory"]) != 30:
        raise RuntimeError("registered FD perturbation count is not 30")
    details = []
    for entry in criteria["perturbation_inventory"]:
        case_id = perturbation_case_id(entry["direction_id"], entry["epsilon_m"], entry["sign"])
        if case_id != entry["case_id"]:
            raise RuntimeError("registered FD perturbation case id mismatch")
        child, ident = perturbed_state(state, dirs[entry["direction_id"]],
            epsilon_m=entry["epsilon_m"], sign=entry["sign"], margin_gate_m=entry["margin_gate_m"])
        raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
        path = dataset_dir / entry["dataset_path"]
        if (path.read_bytes() != raw or sha256_bytes(raw) != entry["phi_file_sha256"]
                or child.state_sha256 != entry["state_sha256"]
                or ident["phi_c_order_sha256"] != entry["phi_c_order_sha256"]
                or ident["phi_fortran_order_sha256"] != entry["phi_fortran_sha256"]
                or ident["masks_unchanged"] is not True
                or ident["outside_design_phi_identical"] is not True
                or ident["zero_level_margin_m"] < entry["margin_gate_m"]):
            raise RuntimeError(f"perturbation preflight mismatch: {case_id}")
        details.append({"case_id": case_id,
                        "sign_change_node_count": int(np.count_nonzero((child.phi < 0) != (state.phi < 0))),
                        "zero_level_margin_m": ident["zero_level_margin_m"]})
    canonical_identity = {
        "canonical_phi_c_order_sha256": c_sha,
        "canonical_phi_fortran_sha256": f_sha,
        "canonical_margin_m": margin,
        "mask_sha256": mask_hashes,
    }
    return state, dirs, audit, details, canonical_identity


def build_state_identity_payload(state, state_npz_sha256: str, canonical_identity: dict,
                                 direction_audit: dict, perturbation_preflight: list) -> dict:
    required_identity = {
        "canonical_phi_c_order_sha256",
        "canonical_phi_fortran_sha256",
        "canonical_margin_m",
        "mask_sha256",
    }
    required_masks = {"design_mask", "fixed_solid_mask", "forbidden_mask", "root_mask"}
    if (not required_identity.issubset(canonical_identity)
            or set(canonical_identity["mask_sha256"]) != required_masks):
        raise RuntimeError("canonical host-input identity payload is incomplete")
    return {
        **state.to_dict(),
        "state_npz_sha256": state_npz_sha256,
        **canonical_identity,
        "direction_audit": direction_audit,
        "perturbation_preflight": perturbation_preflight,
    }


def host_input_preflight(source: Path, dataset_dir: Path, criteria: dict):
    """Finish all CPU input identity checks and payload assembly before GPU discovery."""
    state, directions, direction_audit, perturbations, canonical_identity = (
        verify_canonical_and_preflight(source, dataset_dir, criteria)
    )
    state_path = dataset_dir / criteria["inputs"]["canonical_state_npz"]["path"]
    state_info = build_state_identity_payload(
        state,
        sha256(state_path),
        canonical_identity,
        direction_audit,
        perturbations,
    )
    json.dumps(state_info, sort_keys=True, allow_nan=False)
    return state, directions, direction_audit, perturbations, state_info


def gpu_inventory(criteria: dict):
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version", "--format=csv,noheader"],
        text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [[cell.strip() for cell in row] for row in csv.reader(text.splitlines()) if row]
    expected = criteria["backend"]
    if len(rows) != expected["gpu_count"] or [row[0] for row in rows] != [str(i) for i in range(len(rows))]:
        raise RuntimeError("registered two-GPU T4 inventory mismatch")
    uuids = [row[2] for row in rows]
    if (len(set(uuids)) != len(uuids) or any(not value.startswith("GPU-") for value in uuids)
            or any(expected["gpu_name"] not in row[1] for row in rows)
            or any(row[-1] != expected["driver_version"] for row in rows)):
        raise RuntimeError("T4 model/driver/UUID identity mismatch")
    return [", ".join(row) for row in rows], uuids[0]


def install_julia(base: Path, expected_sha: str) -> Path:
    archive = base / "julia.tar.gz"
    digest = hashlib.sha256()
    with urllib.request.urlopen(JULIA_URL, timeout=60) as response, archive.open("wb") as handle:
        while block := response.read(1 << 20):
            digest.update(block)
            handle.write(block)
    if digest.hexdigest() != expected_sha:
        raise RuntimeError("registered Julia archive SHA mismatch")
    command(["tar", "-xzf", str(archive), "-C", str(base)], OUT / "julia_extract.log", timeout=600)
    julia = base / "julia-1.12.6/bin/julia"
    if not julia.is_file():
        raise RuntimeError("verified Julia binary missing after extraction")
    return julia


def write_run_queue(base: Path, dataset_dir: Path, criteria: dict) -> Path:
    """Write the registered queue outside OUT so Julia can snapshot it safely."""
    queue_path = Path(base) / "run_queue.tsv"
    with queue_path.open("w") as handle:
        for run_id in criteria["run_order"]:
            if run_id.startswith("baseline_"):
                input_item = criteria["inputs"]["canonical_phi_fortran_raw"]
                state_hash = criteria["geometry"]["canonical_state_sha256"]
                direction_id, eps, sign = "", 0, 0
            else:
                item = next(row for row in criteria["perturbation_inventory"]
                            if row["case_id"] == run_id)
                input_item = {"path": item["dataset_path"], "sha256": item["phi_file_sha256"]}
                state_hash = item["state_sha256"]
                direction_id, eps, sign = item["direction_id"], item["epsilon_m"], item["sign"]
            handle.write("\t".join((run_id, str(Path(dataset_dir) / input_item["path"]),
                input_item["sha256"], state_hash, direction_id, str(eps), str(sign))) + "\n")
    return queue_path


def julia_job_environment(criteria: dict, *, cpu_preflight: bool = False) -> dict[str, str]:
    """Pass frozen canonical, perturbation, and flow identities into the Julia job."""
    geometry, flow = criteria["geometry"], criteria["geometry"]["flow_case"]
    values = {
        "FD_STATE_LABEL": str(geometry.get("state_label", "v16")),
        "FD_STATE_SHA256": geometry["canonical_state_sha256"],
        "FD_PHI_C_ORDER_SHA256": geometry["canonical_phi_c_order_sha256"],
        "FD_PHI_FORTRAN_SHA256": geometry["canonical_phi_fortran_sha256"],
        "FD_SOURCE_SURFACE_SHA256": geometry["source_surface_sha256"],
        "FD_POINT_SHAPE": ",".join(map(str, geometry["point_shape"])),
        "FD_SDF_ORIGIN_M": ",".join(map(str, geometry["canonical_sdf_origin_m"])),
        "FD_SDF_SPACING_M": repr(float(geometry["design_spacing_m"])),
        "FD_EXPECTED_MARGIN_M": repr(float(geometry["canonical_phi_margin_m"])),
        "FD_MARGIN_GATE_M": repr(float(geometry["margin_gate_m"])),
        "FD_FLOW_CASE_ID": flow["case_id"],
        "FD_FLOW_DIMS": ",".join(map(str, flow["flow_dims"])),
        "FD_FLOW_ORIGIN_M": ",".join(map(str, flow["flow_origin_m"])),
        "FD_FLOW_SPACING_M": repr(float(flow["flow_spacing_m"])),
        "FD_SOLVER_LENGTH": repr(float(flow["solver_length"])),
        "FD_SOLVER_VISCOSITY": repr(float(flow["solver_viscosity"])),
        "FD_SOLVER_TIME_UNIT_S": repr(float(flow["solver_time_unit_s"])),
        "FD_DIRECTION_IDS": ",".join(criteria["direction_inventory"]),
        "FD_EPSILONS_M": ",".join(repr(float(value)) for value in sorted({
            row["epsilon_m"] for row in criteria["perturbation_inventory"]})),
        "FD_T_END": repr(float(criteria["measurement"]["target_t_u_l"])),
        "FD_BURN_IN": repr(float(criteria["measurement"]["force_window_t_u_l"][0])),
        "FD_SAMPLE_EVERY": str(criteria["measurement"]["force_sample_every_solver_steps"]),
        "FD_WINDOW_START": repr(float(criteria["measurement"]["force_window_t_u_l"][0])),
        "FD_WINDOW_END": repr(float(criteria["measurement"]["force_window_t_u_l"][1])),
        "FD_STATIONARITY_SPLIT": repr(float(criteria["measurement"]["stationarity_half_windows_t_u_l"][0][1])),
        "FD_CPU_PRESTEP": "1" if cpu_preflight else "0",
    }
    return values


def parse_force_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FORCE_COLUMNS:
            raise RuntimeError(f"FD force CSV schema mismatch: {path.name}")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    if not rows or not all(math.isfinite(value) for row in rows for value in row.values()):
        raise RuntimeError(f"FD force CSV is empty/nonfinite: {path.name}")
    if not all(right["step"] > left["step"] and right["t_u_l"] > left["t_u_l"]
               for left, right in zip(rows, rows[1:])):
        raise RuntimeError(f"FD raw sample order invalid: {path.name}")
    return rows


def force_rows_contract(rows, measurement):
    stride = measurement["force_sample_every_solver_steps"]
    terminal_extra = int(rows[-1]["step"]) % stride != 0
    regular = rows[:-1] if terminal_extra else rows
    if (not all(int(row["step"]) % stride == 0 for row in regular)
            or not all(int(right["step"] - left["step"]) == stride for left, right in zip(regular, regular[1:]))
            or (terminal_extra and not (rows[-1]["t_u_l"] >= measurement["target_t_u_l"]
                and 0 < rows[-1]["step"] - rows[-2]["step"] < stride))):
        raise RuntimeError("force sample stride/terminal sample differs from preregistration")
    start, end = measurement["force_window_t_u_l"]
    raw_window_samples = sum(start <= row["t_u_l"] <= end for row in rows)
    if raw_window_samples < measurement["minimum_window_samples"]:
        raise RuntimeError("registered force window has too few raw samples")


def interpolate_boundary(rows, t):
    right = next((index for index, row in enumerate(rows) if row["t_u_l"] >= t), None)
    if right is None:
        raise RuntimeError("raw force samples do not reach a registered endpoint")
    if rows[right]["t_u_l"] == t:
        return dict(rows[right])
    if right == 0:
        raise RuntimeError("raw force rows do not bracket the registered window start")
    left, after = rows[right - 1], rows[right]
    alpha = (t - left["t_u_l"]) / (after["t_u_l"] - left["t_u_l"])
    return {key: (t if key == "t_u_l" else left[key] + alpha * (after[key] - left[key]))
            for key in left}


def clipped_window(rows, start, end):
    if rows[0]["t_u_l"] > start or rows[-1]["t_u_l"] < end:
        raise RuntimeError("raw force samples do not bracket exact force window")
    return [interpolate_boundary(rows, start),
            *[row for row in rows if start < row["t_u_l"] < end],
            interpolate_boundary(rows, end)]


def time_weighted_mean(rows, key):
    integral = duration = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        integral += 0.5 * (left[key] + right[key]) * dt
        duration += dt
    if duration <= 0:
        raise RuntimeError("exact force window duration is not positive")
    return integral / duration


def recompute_metrics(rows, criteria):
    measurement = criteria["measurement"]
    force = clipped_window(rows, *measurement["force_window_t_u_l"])
    first = clipped_window(rows, *measurement["stationarity_half_windows_t_u_l"][0])
    second = clipped_window(rows, *measurement["stationarity_half_windows_t_u_l"][1])
    out = {f"window_time_weighted_{key}": time_weighted_mean(force, key)
           for key in ["fx_solver", "fy_solver", "fz_solver", "drag_solver", "downforce_solver",
                       "pressure_fx_solver", "pressure_fy_solver", "pressure_fz_solver",
                       "viscous_fx_solver", "viscous_fy_solver", "viscous_fz_solver"]}
    flow = criteria["geometry"]["flow_case"]
    rho, speed, dx = flow["density_kg_m3"], flow["freestream_mps"][0], flow["flow_spacing_m"]
    force_scale = rho * speed**2 * dx**2
    reference_area_solver = flow["reference_area_m2"] / dx**2
    out["drag_time_weighted_n"] = out["window_time_weighted_drag_solver"] * force_scale
    out["downforce_time_weighted_n"] = out["window_time_weighted_downforce_solver"] * force_scale
    out["cd_time_weighted"] = out["window_time_weighted_drag_solver"] / (
        0.5 * reference_area_solver * speed**2)
    for quantity, key in (("drag", "drag_solver"), ("downforce", "downforce_solver")):
        a, b, whole = time_weighted_mean(first, key), time_weighted_mean(second, key), out[f"window_time_weighted_{key}"]
        out[f"stationarity_first_half_time_weighted_{quantity}_solver"] = a
        out[f"stationarity_second_half_time_weighted_{quantity}_solver"] = b
        out[f"stationarity_relative_half_window_drift_{quantity}"] = abs(a-b) / max(abs(whole), sys.float_info.epsilon)
    return out


def force_components_close(rows, measurement):
    rel, absolute = measurement["force_component_relative_tolerance"], measurement["force_component_absolute_tolerance"]
    return all(
        math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=rel, abs_tol=absolute)
        and math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=rel, abs_tol=absolute)
        and all(math.isclose(row[f"{axis}_solver"],
                             row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
                             rel_tol=rel, abs_tol=absolute) for axis in ("fx", "fy", "fz"))
        for row in rows)


def run_summary_contract(summary, criteria):
    geometry = criteria["geometry"]
    flow = geometry["flow_case"]
    run_id = summary.get("run_id")
    expected_margin = geometry["canonical_phi_margin_m"] if run_id in {
        "baseline_A", "baseline_B", "baseline_C"} else next(
            item["zero_level_margin_m"] for item in criteria["perturbation_inventory"]
            if item["case_id"] == run_id)
    close = lambda key, expected: math.isclose(
        float(summary.get(key, math.nan)), float(expected), rel_tol=0.0, abs_tol=1e-12)
    return (
        (geometry.get("state_label", "v16") == "v16" or (
            summary.get("canonical_state_label") == geometry["state_label"]
            and summary.get("canonical_state_sha256") == geometry["canonical_state_sha256"]
            and summary.get("canonical_source_surface_sha256") == geometry["source_surface_sha256"]))
        and math.isclose(float(summary.get("phi_margin_m", math.nan)), expected_margin,
                     rel_tol=0.0, abs_tol=1e-6)
        and close("phi_margin_gate_m", geometry["margin_gate_m"])
        and summary.get("point_shape") == geometry["point_shape"]
        and summary.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
        and summary.get("flow_origin_m") == flow["flow_origin_m"]
        and summary.get("flow_dims") == flow["flow_dims"]
        and close("flow_spacing_m", flow["flow_spacing_m"])
        and close("solver_length", flow["solver_length"])
        and close("solver_viscosity", flow["solver_viscosity"])
        and close("solver_velocity", flow["solver_velocity"])
        and close("solver_time_unit_s", flow["solver_time_unit_s"])
        and close("reynolds", flow["reynolds"])
        and close("density_kg_m3", flow["density_kg_m3"])
        and close("dynamic_viscosity_pa_s", flow["dynamic_viscosity_pa_s"])
        and list(summary.get("freestream_mps", ())) == flow["freestream_mps"]
        and close("reference_length_m", flow["reference_length_m"])
        and close("reference_area_m2", flow["reference_area_m2"])
        and close("canonical_design_spacing_m", geometry["design_spacing_m"])
        and summary.get("candidate_body_mapping") == flow["candidate_body_mapping"]
        and close("sdf_outside_value_m", geometry["outside_value_m"])
        and close("moving_ground_solver_plane", flow["moving_ground_solver_plane"])
        and close("moving_ground_world_plane_m", flow["moving_ground_world_plane_m"])
        and list(summary.get("moving_ground_velocity_mps", ())) == flow["moving_ground_velocity_mps"]
        and summary.get("force_window_t_u_l") == criteria["measurement"]["force_window_t_u_l"]
        and summary.get("stationarity_half_windows_t_u_l") == criteria["measurement"]["stationarity_half_windows_t_u_l"]
        and summary.get("sample_every_solver_steps") == criteria["measurement"]["force_sample_every_solver_steps"]
        and summary.get("physical_box_m") == flow["physical_box_m"]
        and summary.get("native_velocity_boundary") == flow["native_velocity_boundary"]
        and summary.get("side_top_tangential_boundary") == flow["side_top_tangential_boundary"]
        and summary.get("x_plus_boundary") == flow["x_plus_boundary"]
        and summary.get("pressure_boundary") == flow["pressure_boundary"]
        and summary.get("ground_model") == flow["ground_model"]
        and summary.get("force_integration_body") == flow["force_integration_body"]
        and summary.get("force_projection_semantics") == flow["force_projection_semantics"]
        and summary.get("source_profile_equivalent") is flow["source_profile_equivalent"]
        and summary.get("physical_profile_qualified") is flow["physical_profile_qualified"]
    )


def close_summary(summary, metrics, tolerance):
    return all(math.isclose(float(summary.get(key, math.nan)), value,
                            rel_tol=tolerance, abs_tol=1e-10)
               for key, value in metrics.items())


def baseline_noise(values, floor_scale=1e-8):
    data = np.asarray(values, dtype=np.float64)
    median, lo, hi = float(np.median(data)), float(data.min()), float(data.max())
    span = hi - lo
    return {"median": median, "min": lo, "max": hi, "span": span,
            "noise_floor": max(span, floor_scale * max(1.0, abs(median)))}


def classify_response(pairs, baseline_median, noise_floor, *, resolution_factor=20.0,
                      plateau_relative_tolerance=0.05, minimum_resolved_count=3):
    rows = []
    for item in sorted(pairs, key=lambda row: row["epsilon_m"]):
        eps = float(item["epsilon_m"])
        plus, minus = float(item["plus_response"]), float(item["minus_response"])
        signal = abs(plus - minus)
        slope = (plus - minus) / (2.0 * eps)
        even = plus + minus - 2.0 * baseline_median
        rows.append({"epsilon_m": eps, "plus_response_n": plus, "minus_response_n": minus,
            "pair_signal_n": signal, "resolved": signal >= resolution_factor * noise_floor,
            "centered_derivative_n_per_m": slope, "even_nonlinearity_n": even,
            "even_to_odd_ratio": abs(even) / max(signal, noise_floor)})
    resolved = [item for item in rows if item["resolved"]]
    plateau = resolved[:minimum_resolved_count]
    enough = len(plateau) == minimum_resolved_count
    ref = float(np.median([item["centered_derivative_n_per_m"] for item in plateau])) if enough else None
    noise_equivalent = max(noise_floor / item["epsilon_m"] for item in plateau) if enough else None
    deviations = []
    for item in plateau:
        deviation = abs(item["centered_derivative_n_per_m"] - ref) / max(abs(ref), noise_equivalent)
        item["plateau_relative_deviation"] = deviation
        item["directional_noise_equivalent_n_per_m"] = noise_equivalent
        deviations.append(deviation)
    signs = [int(math.copysign(1, item["centered_derivative_n_per_m"]))
             if item["centered_derivative_n_per_m"] else 0 for item in plateau]
    stable = enough and signs[0] != 0 and len(set(signs)) == 1
    passed = enough and stable and all(value <= plateau_relative_tolerance for value in deviations)
    return {"all_epsilon_results": rows, "resolved_epsilon_m": [row["epsilon_m"] for row in resolved],
        "resolved_count": len(resolved), "plateau_epsilon_m": [row["epsilon_m"] for row in plateau],
        "reference_derivative_n_per_m": ref,
        "directional_noise_equivalent_n_per_m": noise_equivalent,
        "plateau_relative_deviations": deviations,
        "plateau_max_relative_deviation": max(deviations) if deviations else None,
        "plateau_signs": signs, "sign_stable": stable, "plateau_pass": passed}


def verify_runner(w4_result, criteria, criteria_sha, manifest, input_hashes, dirs_audit,
                  summaries, rows_by_run, metrics_by_run, gpu_rows, selected_uuid, smoke,
                  actual_commit, runner_sha):
    run_ids = list(criteria["run_order"])
    measurement = criteria["measurement"]
    runtime_rows = {name: summaries[name]["wall_seconds"] for name in run_ids}
    vram_ok = all(0 < summaries[name]["peak_vram_bytes"] <= measurement["peak_vram_limit_bytes"]
                  and 0 < summaries[name]["peak_vram_bytes"] < summaries[name]["vram_total_bytes"]
                  for name in run_ids)
    all_started = STATE.get("solver_step_invoked") == run_ids
    all_returned = STATE.get("solver_step_returned") == run_ids
    all_integrity = True
    all_stationary = True
    for run_id in run_ids:
        summary, rows, metrics = summaries[run_id], rows_by_run[run_id], metrics_by_run[run_id]
        force_rows_contract(rows, measurement)
        all_integrity = all_integrity and summary["finite_u"] and summary["finite_p"] and summary["finite_forces"]
        all_integrity = all_integrity and summary["t_end_reached"] >= measurement["target_t_u_l"]
        raw_window_count = sum(
            measurement["force_window_t_u_l"][0] <= row["t_u_l"] <= measurement["force_window_t_u_l"][1]
            for row in rows)
        all_integrity = all_integrity and summary["window_samples"] == raw_window_count
        all_integrity = all_integrity and raw_window_count >= measurement["minimum_window_samples"]
        all_integrity = all_integrity and run_summary_contract(summary, criteria)
        all_integrity = all_integrity and force_components_close(rows, measurement)
        all_integrity = all_integrity and close_summary(summary, metrics, measurement["host_recompute_relative_tolerance"])
        all_stationary = all_stationary and all(
            metrics[f"stationarity_relative_half_window_drift_{quantity}"]
            <= measurement["stationarity_relative_half_window_drift_max"]
            for quantity in ("drag", "downforce"))
    baseline_ids = ("baseline_A", "baseline_B", "baseline_C")
    noise_contract = criteria["noise_and_plateau"]
    baseline = {response: baseline_noise([metrics_by_run[run][f"{response}_time_weighted_n"]
                                          for run in baseline_ids])
                for response in ("drag", "downforce")}
    direction_results = {}
    for direction_id in EXPECTED_DIRECTIONS:
        direction_results[direction_id] = {}
        for response in ("drag", "downforce"):
            pairs = []
            for epsilon in EXPECTED_EPSILONS:
                plus_id = f"{direction_id}__eps_{epsilon:.4f}".replace(".", "p") + "m__plus"
                minus_id = f"{direction_id}__eps_{epsilon:.4f}".replace(".", "p") + "m__minus"
                pairs.append({"epsilon_m": epsilon,
                    "plus_response": metrics_by_run[plus_id][f"{response}_time_weighted_n"],
                    "minus_response": metrics_by_run[minus_id][f"{response}_time_weighted_n"]})
            direction_results[direction_id][response] = classify_response(
                pairs, baseline[response]["median"], baseline[response]["noise_floor"],
                resolution_factor=noise_contract["resolution_factor"],
                plateau_relative_tolerance=noise_contract["plateau_relative_tolerance"],
                minimum_resolved_count=noise_contract["minimum_resolved_epsilon_count"])
    drag_pass = all(direction_results[d]["drag"]["plateau_pass"] for d in EXPECTED_DIRECTIONS)
    downforce_pass = all(direction_results[d]["downforce"]["plateau_pass"] for d in EXPECTED_DIRECTIONS)
    flow_id = criteria["geometry"]["flow_case"]["case_id"]
    w4_case = w4_force_metrics(w4_result, flow_id)
    reference_drag = w4_case["drag_time_weighted_n"]
    reference_down = w4_case["downforce_time_weighted_n"]
    crosscheck_label = f"w4_{flow_id}"
    baseline_crosscheck = {
        f"{crosscheck_label}_drag_n": reference_drag,
        "fd_baseline_median_drag_n": baseline["drag"]["median"],
        "drag_delta_n": baseline["drag"]["median"] - reference_drag,
        f"{crosscheck_label}_downforce_n": reference_down,
        "fd_baseline_median_downforce_n": baseline["downforce"]["median"],
        "downforce_delta_n": baseline["downforce"]["median"] - reference_down,
        "numerical_tolerance_gate_registered": False,
        "drag_sign_consistent": math.copysign(1, baseline["drag"]["median"])
            == math.copysign(1, reference_drag),
    }
    backend = criteria["backend"]
    identity_ok = (len(gpu_rows) == backend["gpu_count"]
        and all(backend["gpu_name"] in row and row.split(", ")[-1] == backend["driver_version"] for row in gpu_rows)
        and selected_uuid.startswith("GPU-")
        and all(s["gpu_uuid"] == selected_uuid and s["cuda_visible_devices"] == "0"
            and s["julia_version"] == backend["julia_version"]
            and s["julia_threads"] == backend["julia_threads"]
            and s["cuda_jl_version"] == backend["cuda_jl_version"]
            and s["cuda_runtime_version"] == backend["cuda_runtime_version"]
            and s["waterlily_version"] == backend["waterlily_version"]
            and s["waterlily_backend"] == backend["waterlily_backend"] for s in summaries.values())
        and all(marker in smoke for marker in (
            "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
            f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
            f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
            f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
            f"JULIA_VERSION {backend['julia_version']}",
            f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
            f"WATERLILY_VERSION {backend['waterlily_version']}",
            f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP")))
    gates = {
        criteria["gates"][0]: (
            criteria["prerequisites"]["w3"]["host_verified"] is True
            and criteria["prerequisites"]["w4"]["host_verified"] is True
            and criteria["prerequisites"]["w4"]["fd_entry_gate"] == "OPEN"
            and criteria["prerequisites"]["w4"]["extended_domain_fine_grid_required"] is False
            and criteria["prerequisites"]["w4"]["formal_fd_measurement_started"] is False),
        "T1_canonical_state_phi_masks_and_margin_identity": (
            manifest["canonical_state_sha256"] == criteria["geometry"]["canonical_state_sha256"]
            and manifest["canonical_phi_c_order_sha256"] == criteria["geometry"]["canonical_phi_c_order_sha256"]
            and manifest["canonical_phi_fortran_sha256"] == criteria["geometry"]["canonical_phi_fortran_sha256"]
            and len(dirs_audit) == 30
            and min(row["zero_level_margin_m"] for row in dirs_audit) >= criteria["geometry"]["margin_gate_m"]),
        "T2_direction_generation_identity_and_nonduplication": (
            set(criteria["direction_inventory"]) == set(EXPECTED_DIRECTIONS)
            and criteria["direction_audit"]["shape"] == criteria["geometry"]["point_shape"]
            and max(abs(value) for value in criteria["direction_audit"]["pairwise_cosine"].values())
                < criteria["directions"]["max_pairwise_abs_cosine"]),
        "T3_all_30_perturbation_identities_and_preflight": len(criteria["perturbation_inventory"]) == 30
            and all(item["masks_unchanged"] and item["outside_design_phi_identical"]
                    and not item["reinitialization_applied"] and not item["smoothing_applied"]
                    and not item["volume_correction_applied"] and not item["clipping_applied"]
                    for item in criteria["perturbation_inventory"]),
        "T4_exact_backend_and_runtime_identity": identity_ok,
        "T5_all_33_fresh_primal_runs_complete_to_tU_L_120": (
            run_ids == EXPECTED_RUN_ORDER and len(summaries) == 33 and all_started and all_returned
            and all(summary["t_end_reached"] >= measurement["target_t_u_l"]
                    for summary in summaries.values())),
        "T6_finite_fields_forces_component_closure_and_projection": all_integrity,
        "T7_host_recomputed_exact_window_responses_match_runner": all(
            close_summary(summaries[run], metrics_by_run[run], measurement["host_recompute_relative_tolerance"])
            for run in run_ids),
        "T8_all_run_stationarity": all_stationary,
        "T9_three_baseline_noise_measurement": (
            all(len([metrics_by_run[x][f"{response}_time_weighted_n"] for x in baseline_ids]) == 3
                for response in ("drag", "downforce")) and baseline_crosscheck["drag_sign_consistent"]),
        "T10_drag_directional_resolution_sign_and_plateau": drag_pass,
        "T11_downforce_directional_resolution_sign_and_plateau": downforce_pass,
        "T12_source_dataset_kernel_runtime_VRAM_and_artifact_integrity": (
            criteria_sha == sha256(OUT / "input_criteria.json")
            and actual_commit == criteria["source_commit"]
            and runner_sha == criteria["inputs"]["kernel_runner"]["sha256"]
            and all(0 < seconds <= measurement["run_wall_time_limit_s"] for seconds in runtime_rows.values())
            and all(0 < summaries[name]["first_step_seconds"] <= measurement["first_step_wall_time_limit_s"]
                    for name in run_ids)
            and sum(runtime_rows.values()) <= measurement["aggregate_solver_wall_time_limit_s"]
            and vram_ok
            and set(input_hashes) == (set(registered_dataset_files(criteria))
                                      | {CRITERIA_NAME, CRITERIA_NAME + ".sha256"})
            and all(len(digest) == 64 for digest in input_hashes.values())),
    }
    output = {
        "criteria_sha256": criteria_sha, "source_commit": actual_commit,
        "dataset_id": criteria["input_dataset_id"],
        "dataset_manifest_sha256": sha256(OUT / "input_dataset_manifest.json"),
        "backend_identity_expected": backend, "selected_gpu_uuid": selected_uuid,
        "gpu_inventory": gpu_rows, "baseline_noise": baseline,
        f"w4_{flow_id}_crosscheck": baseline_crosscheck,
        "run_order": run_ids, "run_count": len(run_ids),
        "raw_run_sha256": {run: summaries[run]["force_csv_sha256"] for run in run_ids},
        "summaries": summaries, "host_recomputed_metrics": metrics_by_run,
        "directional_fd_results": direction_results,
        "gates": gates, "host_runner_gate_all_pass": all(gates.values()),
        "sdf_directional_fd_oracle_qualified": all(gates.values()),
        "sdf_directional_fd_flow16_qualified": (
            criteria["geometry"]["flow_case"]["case_id"] == "flow_16" and all(gates.values())),
        "sdf_directional_fd_flow24_qualified": (
            criteria["geometry"]["flow_case"]["case_id"] == "flow_24" and all(gates.values())),
        "sdf_gradient_field_qualified": False, "gradient_qualified": False,
        "reverse_mode_qualified": False, "physical_profile_equivalence_qualified": False,
        "grid_or_domain_convergence_qualified": False, "absolute_downforce_qualified": False,
        "optimizer_qualified": False, "topology_qualified": False,
        "shape_update_allowed": False,
    }
    return output


def run_main():
    dataset_dir = discover_dataset()
    criteria, criteria_sha = read_criteria(dataset_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    set_stage("criteria_discovery", canonical_state_label=criteria["geometry"].get("state_label", "v16"),
              flow_case=criteria["geometry"]["flow_case"]["case_id"])
    (OUT / "input_criteria.json").write_bytes((dataset_dir / CRITERIA_NAME).read_bytes())
    (OUT / "input_criteria.json.sha256").write_text(criteria_sha + "\n")
    inventory = [{"path": path.relative_to(Path("/kaggle/input")).as_posix(), "is_file": path.is_file(),
                  "size_bytes": path.stat().st_size if path.is_file() else None,
                  "sha256": sha256(path) if path.is_file() else None}
                 for path in sorted(Path("/kaggle/input").rglob("*"))]
    write_json(OUT / "input_mount_inventory.json", inventory)
    dataset_manifest, input_hashes = verify_dataset(criteria, criteria_sha, dataset_dir)
    (OUT / "input_dataset_manifest.json").write_bytes((dataset_dir / MANIFEST_NAME).read_bytes())
    state_info = None
    with tempfile.TemporaryDirectory(prefix="fd_source_") as temp_text:
        base = Path(temp_text)
        source = base / "source"
        set_stage("source_fetch")
        command(["git", "init", "-q", str(source)], OUT / "git_init.log")
        command(["git", "-C", str(source), "fetch", "--depth", "24", SOURCE_URL, SOURCE_REF],
                OUT / "git_fetch.log", timeout=900)
        command(["git", "-C", str(source), "checkout", "--detach", criteria["source_commit"]],
                OUT / "git_checkout.log")
        actual_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        if actual_commit != criteria["source_commit"]:
            raise RuntimeError("exact registered FD source commit mismatch")
        verify_source(source, criteria)
        backend_expected, w4_result = verify_prerequisites(source, criteria)
        set_stage("host_input_preflight")
        (state, dirs, directions_audit, perturbation_preflight,
         state_info) = host_input_preflight(source, dataset_dir, criteria)
        write_json(OUT / "input_state_and_direction_identity.json", state_info)
        gpu_rows, selected_uuid = gpu_inventory(criteria)
        julia = install_julia(base, backend_expected["julia_archive_sha256"])
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": str(backend_expected["julia_threads"]),
                    "CUDA_VISIBLE_DEVICES": backend_expected["cuda_visible_devices"],
                    "FD_SELECTED_GPU_UUID": selected_uuid})
        env.update(julia_job_environment(criteria))
        project = source / "julia/CFDSDFWaterLilyT4"
        set_stage("project_instantiate")
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        for name in ("project", "manifest"):
            entry = criteria["inputs"][name]
            if sha256(project / Path(entry["path"]).name) != entry["sha256"]:
                raise RuntimeError(f"FD Julia {name} changed during Pkg.instantiate")
        set_stage("t4_smoke")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / criteria["inputs"]["kaggle_smoke"]["path"])],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        markers = ("W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
            f"GPU_COMPUTE_CAPABILITY {backend_expected['compute_capability']}",
            f"CUDA_DRIVER_VERSION {backend_expected['cuda_driver_api_version']}",
            f"CUDA_RUNTIME_VERSION {backend_expected['cuda_runtime_version']}",
            f"JULIA_VERSION {backend_expected['julia_version']}",
            f"CUDA_JL_VERSION {backend_expected['cuda_jl_version']}",
            f"WATERLILY_VERSION {backend_expected['waterlily_version']}",
            f"GPU_NAME {backend_expected['gpu_name']}", "NO_SOLVER_STEP")
        if any(marker not in smoke for marker in markers):
            raise RuntimeError("registered T4 no-solver smoke identity mismatch")
        queue_path = write_run_queue(base, dataset_dir, criteria)
        set_stage("julia_job", solver_step_invoked=[], solver_step_returned=[])
        job = source / criteria["inputs"]["julia_job"]["path"]
        command([str(julia), "--startup-file=no", f"--project={project}", str(job),
                 str(dataset_dir), str(queue_path), str(OUT)], OUT / "fd_run.log", env=env,
                timeout=criteria["measurement"]["aggregate_kernel_timeout_s"])
    log_text = (OUT / "fd_run.log").read_text(errors="replace")
    invoked = [line.split()[-1] for line in log_text.splitlines() if line.startswith("FD_SOLVER_STEP_INVOKED ")]
    returned = [line.split()[-1] for line in log_text.splitlines() if line.startswith("FD_SOLVER_STEP_RETURNED ")]
    if invoked != criteria["run_order"] or returned != invoked:
        raise RuntimeError("FD first-step invocation/return markers do not match the exact registered order")
    STATE["solver_step_invoked"], STATE["solver_step_returned"] = invoked, returned
    STATE["solver_started"] = bool(invoked)
    summaries, metrics_by_run, rows_by_run = {}, {}, {}
    for run_id in criteria["run_order"]:
        summary_path = OUT / f"{run_id}.summary.json"
        csv_path = OUT / f"{run_id}.forces.csv"
        if not summary_path.is_file() or not csv_path.is_file():
            raise RuntimeError(f"FD output missing for exact run id {run_id}")
        summary = json.loads(summary_path.read_text())
        if sha256(csv_path) != summary.get("force_csv_sha256"):
            raise RuntimeError(f"FD raw force CSV SHA mismatch for {run_id}")
        rows = parse_force_csv(csv_path)
        force_rows_contract(rows, criteria["measurement"])
        metrics = recompute_metrics(rows, criteria)
        summaries[run_id], rows_by_run[run_id], metrics_by_run[run_id] = summary, rows, metrics
    fingerprint = {"criteria_sha256": criteria_sha, "source_commit": actual_commit,
        "kernel_runner_sha256": sha256(Path(__file__)), "dataset_id": criteria["input_dataset_id"],
        "dataset_manifest_sha256": sha256(dataset_dir / MANIFEST_NAME), "gpu_inventory": gpu_rows,
        "selected_gpu_uuid": selected_uuid, "backend_expected": backend_expected,
        "julia_archive_sha256": backend_expected["julia_archive_sha256"],
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "platform": platform.platform()}
    write_json(OUT / "runtime_fingerprint.json", fingerprint)
    STATE["stage"] = "host_inside_runner_recompute"
    write_json(OUT / "execution_state.json", STATE)
    runner_sha = sha256(Path(__file__))
    outcome = verify_runner(w4_result, criteria, criteria_sha, dataset_manifest, input_hashes,
        perturbation_preflight, summaries, rows_by_run, metrics_by_run, gpu_rows, selected_uuid,
        smoke, actual_commit, runner_sha)
    write_json(OUT / "outcome.json", outcome)
    crosscheck_key = next(key for key in outcome if key.startswith("w4_flow_") and key.endswith("_crosscheck"))
    write_json(OUT / "run_metrics.json", {
        "baseline_noise": outcome["baseline_noise"],
        crosscheck_key: outcome[crosscheck_key],
        "directional_fd_results": outcome["directional_fd_results"],
        "host_recomputed_metrics": metrics_by_run,
    })
    if not all(outcome["gates"].values()):
        raise RuntimeError(f"registered FD gates failed: {outcome['gates']}")
    set_stage("matrix_complete", solver_step_invoked=invoked, solver_step_returned=returned,
              solver_started=True, run_count=len(invoked))
    manifest = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    write_json(OUT / "sha256.json", manifest)
    flow_case = criteria["geometry"]["flow_case"]["case_id"]
    (OUT / "DONE").write_text(f"All registered {flow_case} primals completed; independent host verification required.\n")
    print("SDF_DIRECTIONAL_FD_DONE", json.dumps(outcome["gates"], sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        run_main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        STATE["failure"] = traceback.format_exc()
        STATE["solver_started"] = bool(STATE.get("solver_step_invoked"))
        julia_log = OUT / "fd_run.log"
        if julia_log.is_file():
            lines = julia_log.read_text(errors="replace").splitlines()
            STATE["solver_step_invoked"] = [line.split()[-1] for line in lines if line.startswith("FD_SOLVER_STEP_INVOKED ")]
            STATE["solver_step_returned"] = [line.split()[-1] for line in lines if line.startswith("FD_SOLVER_STEP_RETURNED ")]
            STATE["solver_started"] = bool(STATE["solver_step_invoked"])
        write_json(OUT / "execution_state.json", STATE)
        (OUT / "ERROR.txt").write_text(STATE["failure"])
        write_json(OUT / "sha256.json", {path.name: sha256(path) for path in sorted(OUT.iterdir())
                   if path.is_file() and path.name != "sha256.json"})
        raise
