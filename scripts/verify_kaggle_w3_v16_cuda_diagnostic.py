#!/usr/bin/env python3
"""Verify exact output artifacts from the W3 v16 CPU/T4 diagnostic kernel.

This verifies artifact integrity and independently recomputes diagnostic
statistics. It does not evaluate or create any qualification gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CRITERIA_PATH = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09_round3.json"
DIAGNOSTIC_JOB = ROOT / "scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"
OWNER_LIFETIME_JOB = ROOT / "scripts/waterlily_w3_v16_cuda_owner_lifetime_job.jl"
OWNER_LIFETIME_CRITERIA_PATH = ROOT / "docs/evidence/kaggle_w3_v16_cuda_owner_lifetime_criteria_2026_09_round3.json"
DIAGNOSTIC_RUNNER = ROOT / "infra/kaggle/kernel_w3_cuda_diagnostic/runner.py"
STAGE_NAME = "w3_v16_cuda_diagnostic"
EXPECTED_CRITERIA_SHA256 = "f5bf4faab65fa7ed31957323508daf27ce961ee03f0f0ca396558cdda33c20d2"
EXPECTED_W3_SOURCE_COMMIT = "5e985fa3395a01228c18910d96e09ecbc5497628"
EXPECTED_W3_DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-genesis-state"
W2B_CRITERIA_PATH = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round5.json"
W2B_RESULT_PATH = ROOT / "docs/evidence/kaggle_w2b_round5_result_2026_09.json"
EXPECTED_W2B_CRITERIA_SHA256 = "32c1fb8a80658a9ea37713c477c6ededcc0808d5cbb8bbd07d91a2b83ed1eb47"
BODY_NAMES = ("candidate", "ground", "combined")
BACKENDS = ("cpu", "gpu")
MEASURE_COMPONENTS = ("d", "nx", "ny", "nz", "vx", "vy", "vz")
OWNER_ARM_IDS = ("A", "C", "B1", "B2")
OWNER_GEOMETRY_ARRAYS = ("candidate_cpu", "candidate_cuda", "combined_cpu", "combined_cuda")
OWNER_FIELD_ARRAYS = ("u", "p", "sigma", "mu0", "body_velocity")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_append_only_evidence_target(target: Path, sidecar: Path) -> None:
    require(not target.exists() and not sidecar.exists(),
            "append-only diagnostic evidence path already exists")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_criteria() -> tuple[dict, str]:
    sidecar = CRITERIA_PATH.with_suffix(CRITERIA_PATH.suffix + ".sha256")
    require(CRITERIA_PATH.is_file() and sidecar.is_file(), "W3 round-3 criteria or sidecar missing")
    criteria_sha = sha256(CRITERIA_PATH)
    require(criteria_sha == EXPECTED_CRITERIA_SHA256, "W3 round-3 criteria SHA changed")
    require(sidecar.read_text().strip() == criteria_sha, "W3 round-3 criteria sidecar mismatch")
    criteria = json.loads(CRITERIA_PATH.read_text())
    require(criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True,
            "W3 input criteria are not immutable preregistration")
    require(criteria.get("source_commit") == EXPECTED_W3_SOURCE_COMMIT,
            "W3 round-3 source commit mismatch")
    require(criteria.get("input_dataset_id") == EXPECTED_W3_DATASET_ID,
            "W3 input dataset identity mismatch")
    commit = criteria["source_commit"]
    for name, entry in criteria["inputs"].items():
        if entry.get("location") != "source_repo":
            continue
        content = subprocess.check_output(
            ["git", "-C", str(ROOT), "cat-file", "blob", f"{commit}:{entry['path']}"])
        require(hashlib.sha256(content).hexdigest() == entry["sha256"],
                f"pinned W3 source commit content mismatch: {name}")
    return criteria, criteria_sha


def locate_stage(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    if output_dir.name == STAGE_NAME:
        return output_dir
    candidates = [path for path in output_dir.rglob(STAGE_NAME) if path.is_dir()]
    require(len(candidates) == 1, f"expected one {STAGE_NAME} output directory")
    return candidates[0]


def verify_output_files(folder: Path) -> tuple[dict[str, str], str, str]:
    require((folder / "DONE").is_file() != (folder / "ERROR.txt").is_file(),
            "diagnostic output must contain exactly one of DONE or ERROR.txt")
    manifest_path = folder / "sha256.json"
    require(manifest_path.is_file(), "diagnostic output SHA manifest missing")
    manifest = json.loads(manifest_path.read_text())
    require(isinstance(manifest, dict), "diagnostic SHA manifest is not a JSON object")
    files = {path.name for path in folder.iterdir() if path.is_file()}
    unmanifested = files - set(manifest) - {"sha256.json", "DONE", "ERROR.txt"}
    missing = set(manifest) - files
    require(not unmanifested and not missing,
            f"diagnostic output inventory mismatch: unmanifested={sorted(unmanifested)}, missing={sorted(missing)}")
    for name, digest in manifest.items():
        require(Path(name).name == name and sha256(folder / name) == digest,
                f"diagnostic output SHA mismatch: {name}")
    status = "COMPLETED" if (folder / "DONE").is_file() else "ERROR"
    return manifest, sha256(manifest_path), status


def expected_header() -> list[str]:
    header = ["i", "j", "k", "flow_x_solver", "flow_y_solver", "flow_z_solver"]
    for body in BODY_NAMES:
        for backend in BACKENDS:
            header.extend(f"{backend}_{body}_{component}" for component in MEASURE_COMPONENTS)
    header.extend(("cpu_sigma", "gpu_sigma", "cpu_mu0_sum", "gpu_mu0_sum"))
    return header


def read_lattice_csv(path: Path, dims: tuple[int, int, int]) -> dict[str, object]:
    count = math.prod(dims)
    header = expected_header()
    values = np.empty((count, len(header)), dtype=np.float64)
    row_index = -1
    with Path(path).open(newline="") as handle:
        reader = csv.reader(handle)
        require(next(reader, None) == header, "flow-lattice CSV header mismatch")
        for row_index, row in enumerate(reader):
            require(row_index < count, "flow-lattice CSV contains extra rows")
            require(len(row) == len(header), f"flow-lattice CSV row {row_index} width mismatch")
            try:
                values[row_index] = [float(value) for value in row]
            except ValueError as error:
                raise ValueError(f"flow-lattice CSV row {row_index} is not numeric") from error
    require(row_index + 1 == count, f"flow-lattice CSV row count {row_index + 1} != {count}")
    require(np.isfinite(values).all(), "flow-lattice CSV contains non-finite values")
    nx, ny, nz = dims
    i = np.tile(np.arange(1, nx + 1), ny * nz)
    j = np.tile(np.repeat(np.arange(1, ny + 1), nx), nz)
    k = np.repeat(np.arange(1, nz + 1), nx * ny)
    require(np.array_equal(values[:, 0], i)
            and np.array_equal(values[:, 1], j)
            and np.array_equal(values[:, 2], k),
            "flow-lattice CSV storage order/index identity mismatch")
    expected_coordinates = np.column_stack((i - 0.5, j - 0.5, k - 0.5))
    require(np.allclose(values[:, 3:6], expected_coordinates, rtol=0, atol=1e-6),
            "WaterLily.loc flow solver coordinates mismatch")
    result: dict[str, object] = {"raw": values, "header": header, "row_count": count}
    for body_index, body in enumerate(BODY_NAMES):
        cpu_start = 6 + body_index * 14
        gpu_start = cpu_start + 7
        result[f"{body}_cpu"] = values[:, cpu_start:cpu_start + 7]
        result[f"{body}_gpu"] = values[:, gpu_start:gpu_start + 7]
    result["cpu_sigma"] = values[:, -4]
    result["gpu_sigma"] = values[:, -3]
    result["cpu_mu0_sum"] = values[:, -2]
    result["gpu_mu0_sum"] = values[:, -1]
    return result


def matrix_stats(rows: np.ndarray) -> dict[str, int | float | None]:
    distances = rows[:, 0]
    support = np.abs(distances) <= 1.0
    normal_magnitude = np.linalg.norm(rows[:, 1:4], axis=1)
    supported_normals = normal_magnitude[support]
    return {
        "sample_count": int(distances.size),
        "finite_count": int(np.isfinite(distances).sum()),
        "negative_sdf_count": int((distances < 0).sum()),
        "force_support_abs_d_le_1_count": int(support.sum()),
        "bdim_band_abs_d_le_3_count": int((np.abs(distances) <= 3.0).sum()),
        "min_sdf_solver_units": float(distances.min()),
        "max_sdf_solver_units": float(distances.max()),
        "support_nonzero_normal_count": int((supported_normals > 0).sum()),
        "support_normal_magnitude_min": float(supported_normals.min()) if support.any() else None,
        "support_normal_magnitude_max": float(supported_normals.max()) if support.any() else None,
        "support_normal_magnitude_mean": float(supported_normals.mean()) if support.any() else None,
    }


def compare_cpu_cuda(cpu: np.ndarray, gpu: np.ndarray, spacing_m: float) -> dict[str, int | float]:
    normal_delta = np.linalg.norm(cpu[:, 1:4] - gpu[:, 1:4], axis=1)
    velocity_delta = np.linalg.norm(cpu[:, 4:7] - gpu[:, 4:7], axis=1)
    sign_rows = np.abs(cpu[:, 0]) > 1e-5
    sign_mismatch = np.signbit(cpu[sign_rows, 0]) != np.signbit(gpu[sign_rows, 0])
    return {
        "max_abs_distance_error_m": float(np.max(np.abs(cpu[:, 0] - gpu[:, 0])) * spacing_m),
        "max_normal_vector_error": float(normal_delta.max()),
        "max_body_velocity_error_solver_units": float(velocity_delta.max()),
        "sign_mismatch_count_outside_1e-5_solver_unit_zero_band": int(sign_mismatch.sum()),
        "sign_comparison_count": int(sign_rows.sum()),
    }


def host_candidate_reference(phi: np.ndarray, lattice: dict[str, object],
                             geometry: dict, profile: dict) -> dict[str, object]:
    """Independent NumPy trilinear value/gradient reference at the flow lattice."""
    raw = lattice["raw"]
    solver = raw[:, 3:6].astype(np.float32)
    flow_origin = np.asarray(profile["flow_origin_m"], dtype=np.float32)
    spacing32 = np.float32(geometry["spacing_m"])
    world = (flow_origin + spacing32 * solver).astype(np.float32).astype(np.float64)
    origin = np.asarray(geometry["canonical_sdf_origin_m"], dtype=np.float64)
    spacing = float(geometry["spacing_m"])
    shape = np.asarray(phi.shape, dtype=np.int64)
    grid = (world - origin) / spacing
    inside = np.all((grid >= 0) & (grid <= (shape - 1)), axis=1)
    distance_m = np.full(len(world), 3.0, dtype=np.float64)
    gradient = np.zeros((len(world), 3), dtype=np.float64)
    indices = np.flatnonzero(inside)
    q = grid[indices]
    base = np.minimum(np.floor(q).astype(np.int64), shape - 2)
    t = q - base
    i, j, k = base.T
    tx, ty, tz = t.T
    v000 = phi[i, j, k].astype(np.float64)
    v100 = phi[i + 1, j, k].astype(np.float64)
    v010 = phi[i, j + 1, k].astype(np.float64)
    v110 = phi[i + 1, j + 1, k].astype(np.float64)
    v001 = phi[i, j, k + 1].astype(np.float64)
    v101 = phi[i + 1, j, k + 1].astype(np.float64)
    v011 = phi[i, j + 1, k + 1].astype(np.float64)
    v111 = phi[i + 1, j + 1, k + 1].astype(np.float64)
    bot = (1 - tx) * v000 + tx * v100
    top = (1 - tx) * v001 + tx * v101
    bot_hi = (1 - tx) * v010 + tx * v110
    top_hi = (1 - tx) * v011 + tx * v111
    values = (1 - ty) * ((1 - tz) * bot + tz * top) + ty * ((1 - tz) * bot_hi + tz * top_hi)
    gx = ((1 - ty) * (1 - tz) * (v100 - v000)
          + ty * (1 - tz) * (v110 - v010)
          + (1 - ty) * tz * (v101 - v001)
          + ty * tz * (v111 - v011)) / spacing
    gy = ((1 - tz) * ((1 - tx) * (v010 - v000) + tx * (v110 - v100))
          + tz * ((1 - tx) * (v011 - v001) + tx * (v111 - v101))) / spacing
    gz = ((1 - ty) * ((1 - tx) * (v001 - v000) + tx * (v101 - v100))
          + ty * ((1 - tx) * (v011 - v010) + tx * (v111 - v110))) / spacing
    distance_m[indices] = values
    gradient[indices] = np.column_stack((gx, gy, gz))
    distance_solver = (distance_m / spacing32).astype(np.float32)
    norm = np.linalg.norm(gradient, axis=1)
    normals = np.zeros_like(gradient, dtype=np.float32)
    active = (np.abs(distance_solver) <= 1) & (norm > 0) & np.isfinite(norm)
    normals[active] = (gradient[active] / norm[active, None]).astype(np.float32)
    return {
        "distance_solver": distance_solver,
        "normal": normals,
        "host_cpu_max_abs_distance_error_m": float(
            np.max(np.abs(lattice["candidate_cpu"][:, 0] - distance_solver)) * spacing),
        "host_cpu_max_normal_vector_error": float(
            np.linalg.norm(lattice["candidate_cpu"][:, 1:4] - normals, axis=1).max()),
        "host_cuda_max_abs_distance_error_m": float(
            np.max(np.abs(lattice["candidate_gpu"][:, 0] - distance_solver)) * spacing),
        "host_cuda_max_normal_vector_error": float(
            np.linalg.norm(lattice["candidate_gpu"][:, 1:4] - normals, axis=1).max()),
        "outside_design_box_count": int((~inside).sum()),
    }


def verify_geometry_contract(lattice: dict[str, object], criteria: dict,
                             phi: np.ndarray) -> dict[str, object]:
    geometry = criteria["geometry"]
    profile = criteria["profile_adapter"]
    dims = tuple(profile["cell_dims"])
    points = lattice["raw"][:, 3:6]
    z = points[:, 2]
    expected_ground_distance = z.astype(np.float32)
    ground_support = np.abs(expected_ground_distance) <= 1
    expected_ground_normal = np.zeros((len(z), 3), dtype=np.float32)
    expected_ground_normal[ground_support, 2] = 1
    expected_ground_velocity = np.zeros((len(z), 3), dtype=np.float32)
    expected_ground_velocity[ground_support, 0] = 1
    checks = {}
    for backend in BACKENDS:
        rows = lattice[f"ground_{backend}"]
        checks[f"{backend}_ground_distance_max_error"] = float(
            np.max(np.abs(rows[:, 0] - expected_ground_distance)))
        checks[f"{backend}_ground_normal_max_error"] = float(
            np.linalg.norm(rows[:, 1:4] - expected_ground_normal, axis=1).max())
        checks[f"{backend}_ground_velocity_max_error"] = float(
            np.linalg.norm(rows[:, 4:7] - expected_ground_velocity, axis=1).max())
    checks["expected_ground_support_cells"] = int(ground_support.sum())
    checks["cpu_sigma_vs_combined_distance_max_error"] = float(np.max(np.abs(
        lattice["cpu_sigma"] - lattice["combined_cpu"][:, 0])))
    checks["cuda_sigma_vs_combined_distance_max_error"] = float(np.max(np.abs(
        lattice["gpu_sigma"] - lattice["combined_gpu"][:, 0])))
    checks["cpu_cuda_sigma_max_error"] = float(np.max(np.abs(
        lattice["cpu_sigma"] - lattice["gpu_sigma"])))
    checks["cpu_cuda_mu0_sum_max_error"] = float(np.max(np.abs(
        lattice["cpu_mu0_sum"] - lattice["gpu_mu0_sum"])))
    candidate_reference = host_candidate_reference(phi, lattice, geometry, profile)
    checks["candidate_sdf_reference"] = {
        key: value for key, value in candidate_reference.items()
        if not isinstance(value, np.ndarray)
    }
    return checks


def verify_representative_probes(report: dict, criteria: dict,
                                 phi: np.ndarray) -> dict[str, object]:
    profile = criteria["profile_adapter"]
    geometry = criteria["geometry"]
    flow_origin = np.asarray(profile["flow_origin_m"], dtype=np.float32)
    spacing32 = np.float32(geometry["spacing_m"])
    output: dict[str, object] = {}
    body_data = report["v16_probe_results"]
    for body in BODY_NAMES:
        records = body_data[body]["records"]
        require(records and len({record["name"] for record in records}) == len(records),
                f"{body} representative probe names are empty or duplicated")
        for record in records:
            world = np.asarray(record["world_m"], dtype=np.float32)
            expected_solver = ((world - flow_origin) / spacing32).astype(np.float32)
            require(np.allclose(record["solver"], expected_solver, rtol=0, atol=1e-5),
                    f"{body} world-to-flow map mismatch at {record['name']}")
        cpu = np.asarray([record["cpu_measure"] for record in records], dtype=np.float32)
        gpu = np.asarray([record["gpu_measure"] for record in records], dtype=np.float32)
        comparison = compare_cpu_cuda(cpu, gpu, geometry["spacing_m"])
        for key, value in comparison.items():
            reported = body_data[body]["comparison"].get(key)
            if isinstance(value, int):
                require(value == reported, f"{body} probe comparison mismatch: {key}")
            else:
                require(math.isclose(value, reported if reported is not None else math.nan,
                                     rel_tol=2e-6, abs_tol=2e-8),
                        f"{body} probe comparison mismatch: {key}")
        output[f"{body}_cpu_cuda_comparison"] = comparison

    ground_records = body_data["ground"]["records"]
    ground_cpu = np.asarray([record["cpu_measure"] for record in ground_records], dtype=np.float32)
    ground_gpu = np.asarray([record["gpu_measure"] for record in ground_records], dtype=np.float32)
    expected_ground = np.asarray([
        [record["solver"][2], 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        for record in ground_records
    ], dtype=np.float32)
    output["ground_cpu_max_abs_error"] = float(np.max(np.abs(ground_cpu - expected_ground)))
    output["ground_gpu_max_abs_error"] = float(np.max(np.abs(ground_gpu - expected_ground)))

    candidate_records = body_data["candidate"]["records"]
    raw = np.zeros((len(candidate_records), 6), dtype=np.float64)
    raw[:, 3:6] = np.asarray([record["solver"] for record in candidate_records])
    probe_lattice = {
        "raw": raw,
        "candidate_cpu": np.asarray([record["cpu_measure"] for record in candidate_records]),
        "candidate_gpu": np.asarray([record["gpu_measure"] for record in candidate_records]),
    }
    reference = host_candidate_reference(phi, probe_lattice, geometry, profile)
    output["candidate_numpy_reference"] = {
        key: value for key, value in reference.items() if not isinstance(value, np.ndarray)
    }
    center = next(record for record in candidate_records
                  if record["name"] == "registered_world_center")
    output["world_center_probe"] = {
        "world_m": center["world_m"],
        "flow_solver": center["solver"],
        "expected_flow_solver": [50.0, 24.0, 18.0],
    }
    require(np.allclose(center["world_m"], [0.0, 0.0, 0.0], rtol=0, atol=0)
            and np.allclose(center["solver"], [50.0, 24.0, 18.0], rtol=0, atol=1e-5),
            "canonical v16 center no longer maps to expanded flow solver (50,24,18)")
    return output


def verify_force_snapshot(snapshot: dict) -> dict[str, object]:
    pressure = np.asarray(snapshot["waterlily_pressure_force_raw"], dtype=np.float64)
    viscous = np.asarray(snapshot["waterlily_viscous_force_raw"], dtype=np.float64)
    total = np.asarray(snapshot["waterlily_total_force_raw"], dtype=np.float64)
    require(pressure.shape == viscous.shape == total.shape == (3,), "force vector must have 3 components")
    closure = total - pressure - viscous
    require(np.array_equal(total, pressure + viscous), "diagnostic pressure + viscous does not exactly close")
    require(snapshot["registered_drag_plus_fx_from_raw"] == -total[0],
            "diagnostic +x drag projection mismatch")
    require(snapshot["registered_downforce_minus_fz_from_raw"] == total[2],
            "diagnostic -z downforce projection mismatch")
    return {"pressure_plus_viscous_componentwise_residual": closure.tolist(),
            "waterlily_total_force_raw": total.tolist(),
            "repository_drag_plus_fx": -float(total[0]),
            "repository_downforce_minus_fz": float(total[2])}


def checkout_job_identity(folder: Path) -> tuple[str, str] | None:
    checkout_log = folder / "git_checkout.log"
    if not checkout_log.is_file():
        return None
    match = re.search(r"HEAD is now at ([0-9a-f]{7,40})", checkout_log.read_text())
    if not match:
        return None
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{match.group(1)}^{{commit}}"],
        text=True).strip()
    source = subprocess.check_output(
        ["git", "-C", str(ROOT), "show",
         f"{commit}:scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"])
    return commit, hashlib.sha256(source).hexdigest()


def verify_report(report: dict, criteria: dict, criteria_sha: str,
                  dataset_dir: Path, runner_sha: str, fingerprint: dict,
                  runtime_observed: dict,
                  runner_path: Path = DIAGNOSTIC_RUNNER) -> dict[str, object]:
    require(report.get("evidence_type") == "diagnostic_only"
            and report.get("qualification_evidence") is False,
            "CUDA output incorrectly claims qualification")
    flags = report.get("qualification_flags", {})
    require(flags and all(value is False for value in flags.values()),
            "CUDA diagnostic qualification flags must all remain false")
    geometry = criteria["geometry"]
    expected_inputs = {
        "criteria_sha256": criteria_sha,
        "canonical_phi_fortran_sha256": geometry["phi_fortran_sha256"],
        "canonical_phi_c_order_sha256": geometry["phi_c_order_sha256"],
        "canonical_phi_column_major_bytes_sha256": geometry["phi_fortran_sha256"],
        "device_roundtrip_sha256": geometry["phi_fortran_sha256"],
        "canonical_origin_m": geometry["canonical_sdf_origin_m"],
        "point_shape": geometry["point_shape"],
        "spacing_m": geometry["spacing_m"],
        "source_surface_sha256": geometry["source_surface_sha256"],
        "design_domain_sha256": geometry["design_domain_sha256"],
        "flow_origin_m": criteria["profile_adapter"]["flow_origin_m"],
        "flow_dims": criteria["profile_adapter"]["cell_dims"],
        "canonical_state_sha256": geometry["state_sha256"],
    }
    observed = report.get("input_identity", {})
    for key, value in expected_inputs.items():
        actual = observed.get(key)
        if key == "flow_origin_m":
            matches = np.allclose(actual, value, rtol=0, atol=1e-7)
        elif key == "spacing_m":
            matches = math.isclose(actual, value, rel_tol=0, abs_tol=1e-9)
        else:
            matches = actual == value
        require(matches, f"diagnostic input identity mismatch: {key}")
    margin = geometry["expected_margin_m"]
    measured_margin = observed.get("cpu_measured_sdf_margin_m")
    require(isinstance(measured_margin, (int, float))
            and math.isclose(measured_margin, margin, abs_tol=geometry["margin_tolerance_m"], rel_tol=0),
            "diagnostic measured SDF margin does not match registered canonical value")
    identity = report.get("source_identity", {})
    required_source = {
        "criteria_sha256": criteria_sha,
        "w3_source_commit": EXPECTED_W3_SOURCE_COMMIT,
        "source_w3_job_sha256": criteria["inputs"]["job"]["sha256"],
        "project_sha256": criteria["inputs"]["project"]["sha256"],
        "manifest_sha256": criteria["inputs"]["manifest"]["sha256"],
        "julia_archive_sha256": criteria["backend"]["julia_archive_sha256"],
        "runner_sha256": runner_sha,
        "dataset_id": EXPECTED_W3_DATASET_ID,
        "dataset_manifest_sha256": sha256(dataset_dir / "w3_v16_dataset_manifest.json"),
        "criteria_sidecar_sha256": sha256(dataset_dir / "w3_v16_criteria.json.sha256"),
    }
    for key, value in required_source.items():
        require(identity.get(key) == value, f"diagnostic source/input identity mismatch: {key}")
    required_fingerprint = {
        "criteria_sha256": criteria_sha,
        "criteria_sidecar_sha256": required_source["criteria_sidecar_sha256"],
        "dataset_id": EXPECTED_W3_DATASET_ID,
        "dataset_manifest_sha256": required_source["dataset_manifest_sha256"],
        "runner_sha256": runner_sha,
        "source_commit": identity.get("diagnostic_source_commit"),
        "diagnostic_job_sha256": identity.get("diagnostic_job_sha256"),
        "w3_source_commit": EXPECTED_W3_SOURCE_COMMIT,
        "w3_source_job_sha256": criteria["inputs"]["job"]["sha256"],
        "project_sha256": criteria["inputs"]["project"]["sha256"],
        "manifest_sha256": criteria["inputs"]["manifest"]["sha256"],
        "julia_archive_sha256": criteria["backend"]["julia_archive_sha256"],
        "state_sha256": geometry["state_sha256"],
        "source_surface_sha256": geometry["source_surface_sha256"],
        "design_domain_sha256": geometry["design_domain_sha256"],
        "cuda_visible_devices": criteria["backend"]["cuda_visible_devices"],
    }
    for key, value in required_fingerprint.items():
        require(fingerprint.get(key) == value, f"diagnostic fingerprint mismatch: {key}")
    diagnostic_commit = _runner_pin("DIAGNOSTIC_SOURCE_COMMIT", runner_path)
    require(identity.get("diagnostic_source_commit") == diagnostic_commit,
        "diagnostic source commit mismatch")
    source_job = subprocess.check_output(
        ["git", "-C", str(ROOT), "show",
         f"{diagnostic_commit}:scripts/waterlily_w3_v16_cuda_diagnostic_job.jl"])
    require(hashlib.sha256(source_job).hexdigest() == sha256(DIAGNOSTIC_JOB),
            "local diagnostic job differs from the remote-pinned source commit")
    require(identity.get("diagnostic_job_sha256") == sha256(DIAGNOSTIC_JOB),
            "diagnostic Julia job SHA mismatch")
    runtime = report.get("runtime_identity", {})
    backend = criteria["backend"]
    runtime_checks = {
        "julia_version": backend["julia_version"],
        "julia_threads": backend["julia_threads"],
        "waterlily_version": backend["waterlily_version"],
        "cuda_jl_version": backend["cuda_jl_version"],
        "cuda_runtime_version": backend["cuda_runtime_version"],
        "cuda_driver_version": backend["cuda_driver_api_version"],
        "gpu_name": backend["gpu_name"],
        "gpu_count_visible": 1,
        "cuda_visible_devices": backend["cuda_visible_devices"],
    }
    for key, value in runtime_checks.items():
        require(runtime.get(key) == value, f"diagnostic runtime identity mismatch: {key}")
    inventory = fingerprint.get("gpu_inventory", [])
    require(len(inventory) == backend["gpu_count"], "diagnostic must record both T4 GPUs")
    require(runtime_observed.get("selected_gpu_uuid") == inventory[0].split(",")[2].strip(),
            "diagnostic selected GPU UUID mismatch")
    require(runtime.get("gpu_uuid") == runtime_observed.get("selected_gpu_uuid"),
            "Julia selected GPU UUID differs from nvidia-smi index 0")
    require(all(backend["gpu_name"] in row and backend["driver_version"] in row
                for row in inventory), "observed two-T4 inventory/driver mismatch")
    require(runtime_observed.get("nvidia_driver_version") == backend["driver_version"],
            "observed NVIDIA driver version mismatch")
    require(runtime_observed.get("cuda_visible_devices") == backend["cuda_visible_devices"],
            "observed CUDA_VISIBLE_DEVICES mismatch")
    require(runtime_observed.get("observed_gpu_inventory") == inventory,
            "runtime inventory differs from runner fingerprint")
    require(runtime.get("waterlily_backend"), "WaterLily backend identity missing")
    return {"input_identity_verified": True, "source_identity_verified": True,
            "runtime_identity_verified": True, "qualification_claimed": False}


def verify_partial_fingerprint(fingerprint: dict, criteria: dict,
                               criteria_sha: str, dataset_dir: Path,
                               runner_sha: str,
                               checkout_identity: tuple[str, str] | None) -> dict | None:
    if not fingerprint:
        return None
    expected = {
        "criteria_sha256": criteria_sha,
        "criteria_sidecar_sha256": sha256(dataset_dir / "w3_v16_criteria.json.sha256"),
        "dataset_id": EXPECTED_W3_DATASET_ID,
        "dataset_manifest_sha256": sha256(dataset_dir / "w3_v16_dataset_manifest.json"),
        "runner_sha256": runner_sha,
        "w3_source_commit": EXPECTED_W3_SOURCE_COMMIT,
        "w3_source_job_sha256": criteria["inputs"]["job"]["sha256"],
        "project_sha256": criteria["inputs"]["project"]["sha256"],
        "manifest_sha256": criteria["inputs"]["manifest"]["sha256"],
        "julia_archive_sha256": criteria["backend"]["julia_archive_sha256"],
        "state_sha256": criteria["geometry"]["state_sha256"],
        "source_surface_sha256": criteria["geometry"]["source_surface_sha256"],
        "design_domain_sha256": criteria["geometry"]["design_domain_sha256"],
        "cuda_visible_devices": criteria["backend"]["cuda_visible_devices"],
    }
    for key, value in expected.items():
        require(fingerprint.get(key) == value, f"partial diagnostic fingerprint mismatch: {key}")
    require(checkout_identity is not None,
            "partial diagnostic fingerprint requires a source checkout log")
    require(fingerprint.get("source_commit") == checkout_identity[0],
            "partial diagnostic fingerprint/source checkout commit mismatch")
    require(fingerprint.get("diagnostic_job_sha256") == checkout_identity[1],
            "partial diagnostic fingerprint/job checkout hash mismatch")
    inventory = fingerprint.get("gpu_inventory", [])
    require(len(inventory) == criteria["backend"]["gpu_count"],
            "partial diagnostic fingerprint GPU inventory count mismatch")
    require(all(criteria["backend"]["gpu_name"] in line
                and criteria["backend"]["driver_version"] in line
                for line in inventory),
            "partial diagnostic T4 inventory/driver identity mismatch")
    require(fingerprint.get("selected_gpu_uuid") in
            [line.split(",")[2].strip() for line in inventory],
            "partial diagnostic selected GPU is absent from inventory")
    require(bool(fingerprint.get("cuda_smoke_sha256")),
            "partial diagnostic fingerprint is missing CUDA smoke identity")
    return {
        "fingerprint": fingerprint,
        "checkout_diagnostic_source_commit": checkout_identity[0],
        "checkout_diagnostic_job_sha256": checkout_identity[1],
        "verification": "partial source/input/backend fingerprint independently matched",
    }


def verify_dataset(criteria: dict, dataset_dir: Path) -> tuple[np.ndarray, dict[str, object]]:
    dataset_dir = Path(dataset_dir)
    manifest = json.loads((dataset_dir / "w3_v16_dataset_manifest.json").read_text())
    require(manifest.get("dataset_id") == EXPECTED_W3_DATASET_ID,
            "staged dataset ID mismatch")
    require(manifest.get("criteria_sha256") == EXPECTED_CRITERIA_SHA256,
            "staged dataset criteria binding mismatch")
    expected_files = {
        "sdf_design_state.npz": criteria["inputs"]["canonical_state_npz"]["sha256"],
        "canonical_v16_phi_f4_fortran.raw": criteria["inputs"]["canonical_phi_fortran_raw"]["sha256"],
        "w3_v16_criteria.json": EXPECTED_CRITERIA_SHA256,
    }
    sidecar_path = dataset_dir / "w3_v16_criteria.json.sha256"
    require(sidecar_path.is_file()
            and sidecar_path.read_text().strip() == EXPECTED_CRITERIA_SHA256,
            "staged criteria sidecar mismatch")
    expected_files[sidecar_path.name] = sha256(sidecar_path)
    require(set(manifest.get("files", {})) == set(expected_files),
            "staged W3 dataset inventory mismatch")
    require((dataset_dir / "w3_v16_criteria.json").is_file()
            and sha256(dataset_dir / "w3_v16_criteria.json") == EXPECTED_CRITERIA_SHA256,
            "staged W3 criteria mismatch")
    for name, expected in expected_files.items():
        require(manifest["files"].get(name) == expected,
                f"staged dataset manifest binding mismatch: {name}")
    for name, expected in manifest["files"].items():
        path = dataset_dir / name
        require(path.is_file() and sha256(path) == expected,
                f"staged dataset file hash mismatch: {name}")
    with np.load(dataset_dir / "sdf_design_state.npz", allow_pickle=False) as archive:
        phi = np.asarray(archive["phi"], dtype="<f4")
        metadata = json.loads(str(archive["metadata"].item()))
    require(list(phi.shape) == criteria["geometry"]["point_shape"],
            "staged canonical phi shape mismatch")
    geometry = criteria["geometry"]
    require(metadata.get("state_sha256") == geometry["state_sha256"]
            and metadata.get("source_sha256") == geometry["source_surface_sha256"]
            and metadata.get("shape") == geometry["point_shape"]
            and metadata.get("origin_m") == geometry["canonical_sdf_origin_m"]
            and metadata.get("spacing_m") == geometry["spacing_m"],
            "staged canonical state metadata mismatch")
    phi_c = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    phi_f_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    phi_f = hashlib.sha256(phi_f_bytes).hexdigest()
    require(phi_c == geometry["phi_c_order_sha256"]
            and phi_f == geometry["phi_fortran_sha256"],
            "staged canonical C/F phi identity mismatch")
    raw_path = dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    require(raw_path.read_bytes() == phi_f_bytes,
            "staged raw canonical phi differs from NPZ Fortran-order bytes")
    return phi, metadata


def verify_force_snapshots(report: dict) -> dict[str, object]:
    result = {}
    for group, snapshots in (
        ("v16_solver_free", report["v16_solver_free_measurement"]),
        ("v16_one_step", report["v16_one_step_reproducer"]),
        ("w2b_sphere_cpu", {"force": report["w2b_sphere_control"]["cpu_after_one_step"]}),
        ("w2b_sphere_cuda", {"force": report["w2b_sphere_control"]["gpu_after_one_step"]}),
    ):
        for key, value in snapshots.items():
            if "force" in key and isinstance(value, dict) and "waterlily_total_force_raw" in value:
                result[f"{group}_{key}"] = verify_force_snapshot(value)
            elif key in ("cpu_after_one_step", "gpu_after_one_step") and isinstance(value, dict) \
                    and "waterlily_total_force_raw" in value:
                result[f"{group}_{key}"] = verify_force_snapshot(value)
    return result


def _runner_pin(name: str, runner_path: Path = DIAGNOSTIC_RUNNER) -> str:
    match = re.search(rf'^{re.escape(name)} = "([^"]+)"$',
                      runner_path.read_text(), re.MULTILINE)
    require(match is not None, f"diagnostic runner pin missing: {name}")
    return match.group(1)


def load_owner_lifetime_criteria(
        runner_path: Path = DIAGNOSTIC_RUNNER) -> tuple[dict, str, str]:
    sidecar = OWNER_LIFETIME_CRITERIA_PATH.with_suffix(
        OWNER_LIFETIME_CRITERIA_PATH.suffix + ".sha256")
    require(OWNER_LIFETIME_CRITERIA_PATH.is_file() and sidecar.is_file(),
            "owner-lifetime criteria or sidecar missing")
    criteria_sha = sha256(OWNER_LIFETIME_CRITERIA_PATH)
    require(sidecar.read_text().strip() == criteria_sha,
            "owner-lifetime criteria sidecar mismatch")
    criteria = json.loads(OWNER_LIFETIME_CRITERIA_PATH.read_text())
    require(criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True,
            "owner-lifetime criteria are not immutable preregistration")
    source_commit = _runner_pin("DIAGNOSTIC_SOURCE_COMMIT", runner_path)
    expected_job_sha = _runner_pin("OWNER_LIFETIME_JOB_SHA256", runner_path)
    require(criteria["inputs"]["owner_lifetime_job"]["sha256"] == expected_job_sha,
            "owner-lifetime criteria/runner job pin mismatch")
    require(criteria["inputs"]["w3_criteria_sha256"] == EXPECTED_CRITERIA_SHA256,
            "owner-lifetime criteria/W3 round-3 binding mismatch")
    for path, expected in (
        (OWNER_LIFETIME_JOB, expected_job_sha),
        (OWNER_LIFETIME_CRITERIA_PATH, criteria_sha),
    ):
        content = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"{source_commit}:{path.relative_to(ROOT)}"])
        require(hashlib.sha256(content).hexdigest() == expected,
                f"owner-lifetime source commit content mismatch: {path.name}")
        require(content == path.read_bytes(),
                f"local owner-lifetime source differs from pinned commit: {path.name}")
    return criteria, criteria_sha, sha256(sidecar)


def _owner_float_tolerances(criteria: dict, key: str) -> tuple[float, float]:
    values = re.findall(r"(?<![A-Za-z])(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?",
                        criteria["comparison"][key], re.IGNORECASE)
    require(len(values) == 2, f"owner-lifetime tolerance syntax changed: {key}")
    return tuple(float(value) for value in values)


def _owner_close(left: np.ndarray, right: np.ndarray, atol: float,
                 rtol: float) -> bool:
    return left.shape == right.shape and bool(np.all(
        np.abs(left.astype(np.float64) - right.astype(np.float64))
        <= atol + rtol * np.maximum(np.abs(left), np.abs(right))))


def verify_owner_ownership_schema(arm_id: str, ownership: dict) -> dict:
    strategies = {
        "A": "GC.@preserve owner",
        "C": "OwnedV16Diagnostic owns owner,bodies,simulation",
        "B1": "helper returns bodies,simulation,WeakRef only",
        "B2": "helper returns bodies,simulation,WeakRef only",
    }
    require(arm_id in strategies and ownership.get("strategy") == strategies[arm_id]
            and ownership.get("weakref_created") is True,
            f"owner-lifetime ownership strategy schema mismatch: {arm_id}")
    require(ownership.get("strong_owner_reference_escaped_helper")
            is (arm_id in ("A", "C")),
            f"owner-lifetime strong-owner schema mismatch: {arm_id}")
    before = ownership.get("weakref_before_gc")
    after = ownership.get("weakref_after_gc")
    states = ownership.get("weakref_after_each_gc", [])
    require(before in ("alive", "cleared") and after in ("alive", "cleared")
            and all(state in ("alive", "cleared") for state in states),
            f"owner-lifetime WeakRef state schema mismatch: {arm_id}")
    calls = ownership.get("full_gc_calls", 0)
    require(isinstance(calls, int) and 0 <= calls <= 2 and len(states) == calls,
            f"owner-lifetime forced-GC observation schema mismatch: {arm_id}")
    if calls == 2:
        require(ownership.get("cuda_synchronize_before_gc") is True
                and ownership.get("cuda_synchronize_after_gc") is True,
                f"owner-lifetime CUDA synchronization record mismatch: {arm_id}")
        collected = before == "alive" and after == "cleared"
        require(ownership.get("owner_collected_during_forced_gc") is collected,
                f"owner-lifetime owner-collection boolean mismatch: {arm_id}")
        if arm_id in ("A", "C"):
            require(after == "alive" and states == ["alive", "alive"],
                    f"retained owner did not survive full GC: {arm_id}")
    return {
        "strategy": strategies[arm_id],
        "weakref_before_gc": before,
        "weakref_after_each_gc": states,
        "weakref_after_gc": after,
        "owner_collected_during_forced_gc": ownership.get("owner_collected_during_forced_gc"),
        "forced_gc_calls": calls,
    }


def _owner_read_bundle(folder: Path, spec: dict, names: tuple[str, ...],
                       expected_digest: str) -> dict[str, np.ndarray]:
    path = folder / spec["artifact"]
    require(path.is_file() and path.name == spec["artifact"],
            f"owner-lifetime artifact missing: {spec['artifact']}")
    require(sha256(path) == expected_digest == spec["artifact_sha256"],
            f"owner-lifetime artifact SHA mismatch: {path.name}")
    layout = spec.get("layout", {})
    require(set(layout) == set(names), f"owner-lifetime artifact array inventory mismatch: {path.name}")
    raw = path.read_bytes()
    arrays = {}
    ranges = []
    for name in names:
        entry = layout[name]
        shape = tuple(entry["shape"])
        offset = entry["offset_bytes"]
        nbytes = entry["nbytes"]
        require(entry["dtype"] == "<f4" and entry["order"] == "F"
                and nbytes == math.prod(shape) * 4,
                f"owner-lifetime artifact layout mismatch: {name}")
        chunk = raw[offset:offset + nbytes]
        require(len(chunk) == nbytes and sha256_bytes(chunk) == entry["sha256"],
                f"owner-lifetime array SHA mismatch: {name}")
        arrays[name] = np.frombuffer(chunk, dtype="<f4").reshape(shape, order="F").copy()
        ranges.append((offset, offset + nbytes))
    ranges.sort()
    require(ranges and ranges[0][0] == 0 and ranges[-1][1] == len(raw)
            and all(ranges[index][1] == ranges[index + 1][0]
                    for index in range(len(ranges) - 1)),
            f"owner-lifetime artifact has gaps or trailing bytes: {path.name}")
    return arrays


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _owner_rows_stats(rows: np.ndarray) -> dict[str, object]:
    distance = rows[:, 0]
    norms = np.linalg.norm(rows[:, 1:4].astype(np.float64), axis=1)
    support = np.abs(distance) <= 1.0
    return {
        "sample_count": len(distance),
        "finite_value_count": int(np.isfinite(distance).sum()),
        "negative_distance_count": int((distance < 0).sum()),
        "support_abs_d_le_1_count": int(support.sum()),
        "bdim_abs_d_le_3_count": int((np.abs(distance) <= 3.0).sum()),
        "min_distance_solver_units": float(distance.min()),
        "max_distance_solver_units": float(distance.max()),
        "nonzero_normal_count": int((norms > 0).sum()),
        "normal_magnitude_min": float(norms.min()),
        "normal_magnitude_max": float(norms.max()),
        "normal_magnitude_mean": float(norms.mean()),
        "all_values_finite": bool(np.isfinite(rows).all()),
    }


def _verify_owner_force(snapshot: dict) -> dict[str, object]:
    pressure = np.asarray(snapshot["waterlily_pressure_force_raw"], dtype=np.float64)
    viscous = np.asarray(snapshot["waterlily_viscous_force_raw"], dtype=np.float64)
    total = np.asarray(snapshot["waterlily_total_force_raw"], dtype=np.float64)
    require(pressure.shape == viscous.shape == total.shape == (3,),
            "owner-lifetime force components must have three axes")
    require(np.isfinite(np.concatenate((pressure, viscous, total))).all(),
            "owner-lifetime force components are non-finite")
    require(np.array_equal(total, pressure + viscous),
            "owner-lifetime raw force components do not close")
    body_pressure = np.asarray(snapshot["body_pressure_force"], dtype=np.float64)
    body_viscous = np.asarray(snapshot["body_viscous_force"], dtype=np.float64)
    body_total = np.asarray(snapshot["body_total_force"], dtype=np.float64)
    require(np.array_equal(body_pressure, -pressure)
            and np.array_equal(body_viscous, -viscous)
            and np.array_equal(body_total, -total),
            "owner-lifetime force-on-body negation mismatch")
    require(snapshot["registered_drag_plus_fx_body"] == -total[0]
            and snapshot["registered_downforce_minus_fz_body"] == total[2],
            "owner-lifetime drag/downforce projection mismatch")
    return {
        "pressure_plus_viscous_residual": (total - pressure - viscous).tolist(),
        "body_force_negation_verified": True,
        "drag_plus_fx_body": float(-total[0]),
        "downforce_minus_fz_body": float(total[2]),
    }


def _verify_owner_probe_sets(report: dict, criteria: dict,
                             flow_origin: np.ndarray,
                             spacing: float) -> dict[str, int]:
    checked = {}
    expected_names = {
        "candidate_solid_min_phi", "candidate_surface_min_abs_phi",
        "candidate_nearest_positive_phi", "registered_world_center",
        "outside_x_low", "outside_x_high", "outside_y_low", "outside_y_high",
        "outside_z_low", "outside_z_high",
    }
    for phase in ("fixed_probes_before_gc", "fixed_probes_after_gc"):
        rows = report.get(phase)
        if isinstance(rows, dict) and "skipped" in rows:
            checked[phase] = 0
            continue
        require(isinstance(rows, dict) and set(rows) == {"candidate", "combined"},
                f"owner-lifetime {phase} candidate/combined probes missing")
        for body in ("candidate", "combined"):
            records = rows[body]
            require({row["name"] for row in records} == expected_names,
                    f"owner-lifetime {phase}/{body} probe inventory mismatch")
            for row in records:
                world = np.asarray(row["world_m"], dtype=np.float32)
                expected_solver = ((world - flow_origin.astype(np.float32))
                                   / np.float32(spacing)).astype(np.float32)
                require(np.allclose(row["flow_solver"], expected_solver,
                                    rtol=0, atol=1e-5),
                        f"owner-lifetime world/flow map mismatch: {phase}/{body}/{row['name']}")
                for key in ("cpu_measure", "cuda_measure"):
                    measure = np.asarray(row[key], dtype=np.float32)
                    require(measure.shape == (7,) and np.isfinite(measure).all(),
                            f"owner-lifetime probe measure invalid: {phase}/{body}/{row['name']}")
        checked[phase] = sum(len(rows[body]) for body in ("candidate", "combined"))
    return checked


def _verify_owner_arm_artifacts(folder: Path, report: dict, manifest: dict,
                                phi: np.ndarray, lattice: dict,
                                criteria: dict) -> tuple[dict, dict]:
    geometry_spec = report.get("full_grid_geometry")
    field_spec = report.get("simulation_fields_artifact")
    require(isinstance(geometry_spec, dict) and isinstance(field_spec, dict),
            "completed owner-lifetime arm is missing geometry or field artifacts")
    geometry_arrays = _owner_read_bundle(
        folder, geometry_spec, OWNER_GEOMETRY_ARRAYS,
        manifest.get(geometry_spec["artifact"], ""))
    field_arrays = _owner_read_bundle(
        folder, field_spec, OWNER_FIELD_ARRAYS,
        manifest.get(field_spec["artifact"], ""))
    require(all(np.isfinite(array).all() for array in geometry_arrays.values()),
            "owner-lifetime geometry artifact contains non-finite values")
    require(geometry_spec["flow_dims"] == criteria["fixture"]["flow_dims"]
            and geometry_spec["sample_count"] == math.prod(criteria["fixture"]["flow_dims"]),
            "owner-lifetime flow grid identity mismatch")
    geometry_checks = {}
    reported_geometry = geometry_spec["candidate_and_combined"]
    for key, array_name in (("candidate_cpu", "candidate_cpu"),
                            ("candidate_cuda", "candidate_cuda"),
                            ("combined_cpu", "combined_cpu"),
                            ("combined_cuda", "combined_cuda")):
        rows = geometry_arrays[array_name]
        require(rows.shape == (geometry_spec["sample_count"], 7),
                f"owner-lifetime geometry array shape mismatch: {array_name}")
        body, backend = key.split("_")
        stats = _owner_rows_stats(rows)
        for stat_key, value in stats.items():
            reported = reported_geometry[f"{body}_{backend}"][stat_key]
            if isinstance(value, float):
                require(math.isclose(value, float(reported), rel_tol=2e-6, abs_tol=2e-6),
                        f"owner-lifetime host geometry statistic mismatch: {key}/{stat_key}")
            else:
                require(value == reported,
                        f"owner-lifetime host geometry statistic mismatch: {key}/{stat_key}")
        geometry_checks[key] = stats
    lattice_rows = lattice["raw"]
    require(len(lattice_rows) == geometry_spec["sample_count"],
            "owner-lifetime geometry lattice differs from registered base flow lattice")
    cpu_candidate = geometry_arrays["candidate_cpu"]
    cuda_candidate = geometry_arrays["candidate_cuda"]
    normal_error = np.linalg.norm(cpu_candidate[:, 1:4] - cuda_candidate[:, 1:4], axis=1)
    normal_summary = {
        "max_normal_vector_error": float(normal_error.max()),
        "max_distance_error_m": float(
            np.max(np.abs(cpu_candidate[:, 0] - cuda_candidate[:, 0])) * criteria["fixture"]["spacing_m"]),
    }
    require(math.isclose(normal_summary["max_normal_vector_error"],
                         reported_geometry["candidate_cpu_cuda_max_normal_vector_error"],
                         rel_tol=2e-5, abs_tol=2e-5),
            "owner-lifetime host normal-discrepancy recomputation mismatch")
    require(math.isclose(normal_summary["max_distance_error_m"],
                         reported_geometry["candidate_cpu_cuda_max_distance_error_m"],
                         rel_tol=2e-5, abs_tol=2e-7),
            "owner-lifetime host distance-discrepancy recomputation mismatch")
    examples = reported_geometry["candidate_cpu_cuda_normal_error_examples"]
    require(len(examples) == criteria["execution"]["normal_diagnostic_top_n"],
            "owner-lifetime normal discrepancy examples missing")
    flow_origin = np.asarray(criteria["fixture"]["flow_origin_m"], dtype=np.float32)
    spacing32 = np.float32(criteria["fixture"]["spacing_m"])
    for example in examples:
        solver = np.asarray(example["flow_solver"], dtype=np.float32)
        matches = np.flatnonzero(np.all(
            np.isclose(lattice_rows[:, 3:6].astype(np.float32), solver, rtol=0, atol=1e-6), axis=1))
        require(len(matches) == 1, "owner-lifetime normal example is not on the registered flow lattice")
        index = int(matches[0])
        world = (flow_origin + spacing32 * solver).astype(np.float32)
        require(np.allclose(example["world_m"], world, rtol=0, atol=2e-6),
                "owner-lifetime normal example world coordinate mismatch")
        delta = float(normal_error[index])
        require(math.isclose(delta, example["normal_vector_error"], rel_tol=2e-5, abs_tol=2e-5)
                and np.allclose(example["cpu_normal"], cpu_candidate[index, 1:4], rtol=0, atol=2e-6)
                and np.allclose(example["cuda_normal"], cuda_candidate[index, 1:4], rtol=0, atol=2e-6),
                "owner-lifetime normal example does not match binary geometry artifact")
        coord = ((world - np.asarray(criteria["inputs"]["canonical_phi_origin_m"], dtype=np.float32))
                 / spacing32)
        if np.all((coord >= 0) & (coord <= np.asarray(phi.shape, dtype=np.float32) - 1)):
            base = np.minimum(np.floor(coord).astype(int), np.asarray(phi.shape) - 2)
            expected_patch = phi[base[0]:base[0] + 2, base[1]:base[1] + 2,
                                 base[2]:base[2] + 2].tolist()
            require(example["interpolation_cell_1based"] == (base + 1).tolist()
                    and np.allclose(example["local_phi_neighborhood_2x2x2"],
                                    expected_patch, rtol=0, atol=0),
                    "owner-lifetime normal example local phi cell mismatch")
    field_checks = {}
    final_fields = report["simulation_fields"]["after_step2"]
    for name, array in field_arrays.items():
        stats = {
            "shape": list(array.shape),
            "finite_count": int(np.isfinite(array).sum()),
            "nonzero_count": int(np.count_nonzero(array)),
            "max_abs": float(np.max(np.abs(array))),
            "array_sha256": field_spec["layout"][name]["sha256"],
        }
        require(stats["shape"] == final_fields[name]["shape"]
                and stats["finite_count"] == final_fields[name]["finite_count"]
                and stats["nonzero_count"] == final_fields[name]["nonzero_count"]
                and stats["array_sha256"] == final_fields[name]["array_sha256"]
                and math.isclose(stats["max_abs"], final_fields[name]["max_abs"],
                                 rel_tol=2e-6, abs_tol=2e-6),
                f"owner-lifetime host field statistic mismatch: {name}")
        field_checks[name] = stats
    return ({"geometry": geometry_checks, "normal_discrepancy": normal_summary,
             "normal_examples_host_checked": len(examples)},
            {"fields_after_step2": field_checks,
             "geometry_arrays": geometry_arrays,
             "field_arrays": field_arrays})


def _owner_pair_divergences(left: dict, right: dict, criteria: dict) -> set[str]:
    atol_f, rtol_f = _owner_float_tolerances(criteria, "field_per_element_tolerance")
    atol_force, rtol_force = _owner_float_tolerances(criteria, "force_component_tolerance")
    atol_d = criteria["comparison"]["geometry_distance_abs_tolerance_solver_units"]
    atol_nv = criteria["comparison"]["normal_and_velocity_component_abs_tolerance"]
    divergent = set()
    if left.get("geometry_arrays") and right.get("geometry_arrays"):
        for name in ("candidate_cuda", "combined_cuda"):
            a, b = left["geometry_arrays"][name], right["geometry_arrays"][name]
            if (not _owner_close(a[:, 0], b[:, 0], atol_d, 0)
                    or not _owner_close(a[:, 1:4], b[:, 1:4], atol_nv, 0)
                    or not _owner_close(a[:, 4:7], b[:, 4:7], atol_nv, 0)):
                divergent.add("candidate_geometry")
                break
    if left.get("field_arrays") and right.get("field_arrays"):
        if any(not _owner_close(left["field_arrays"][name], right["field_arrays"][name],
                                atol_f, rtol_f) for name in OWNER_FIELD_ARRAYS):
            divergent.add("simulation_fields")
    if left.get("force_history") and right.get("force_history"):
        for phase in ("step0_after_gc", "step1", "step2"):
            if phase not in left["force_history"] or phase not in right["force_history"]:
                divergent.add("force_history")
                break
            for component in ("waterlily_pressure_force_raw", "waterlily_viscous_force_raw",
                              "waterlily_total_force_raw"):
                if not _owner_close(np.asarray(left["force_history"][phase][component]),
                                    np.asarray(right["force_history"][phase][component]),
                                    atol_force, rtol_force):
                    divergent.add("force_history")
                    break
            if "force_history" in divergent:
                break
    return divergent


def verify_owner_lifetime_experiment(folder: Path, manifest: dict,
                                     base_report: dict | None, fingerprint: dict,
                                     runtime_observed: dict, w3_criteria: dict,
                                     w3_criteria_sha: str, dataset_dir: Path,
                                     phi: np.ndarray, lattice: dict | None,
                                     runner_path: Path = DIAGNOSTIC_RUNNER) -> dict:
    criteria, criteria_sha, criteria_sidecar_sha = load_owner_lifetime_criteria(runner_path)
    execution_path = folder / "owner_lifetime_execution.json"
    if not execution_path.is_file():
        return {
            "criteria_path": str(OWNER_LIFETIME_CRITERIA_PATH.relative_to(ROOT)),
            "criteria_sha256": criteria_sha,
            "criteria_sidecar_sha256": criteria_sidecar_sha,
            "source_commit": _runner_pin("DIAGNOSTIC_SOURCE_COMMIT", runner_path),
            "julia_job_sha256": _runner_pin("OWNER_LIFETIME_JOB_SHA256", runner_path),
            "kernel_runner_sha256": sha256(runner_path),
            "host_verifier_sha256": sha256(Path(__file__)),
            "execution_status": "not_reached",
            "arms": {},
            "host_controls_A_C_match": None,
            "host_verification_passed": False,
            "owner_lifetime_hypothesis": "unresolved",
            "divergence_classes_by_unrooted_replicate": {},
            "same_divergence_class_in_both_replicates": [],
            "qualification_flags": criteria["qualification_flags"],
            "claim_scope": criteria["claim_scope"],
        }
    execution = json.loads(execution_path.read_text())
    expected_job_sha = _runner_pin("OWNER_LIFETIME_JOB_SHA256", runner_path)
    expected_source_commit = _runner_pin("DIAGNOSTIC_SOURCE_COMMIT", runner_path)
    runner_sha = sha256(runner_path)
    expected_execution = {
        "criteria_path": str(OWNER_LIFETIME_CRITERIA_PATH.relative_to(ROOT)),
        "criteria_sha256": criteria_sha,
        "criteria_sidecar_sha256": criteria_sidecar_sha,
        "source_commit": expected_source_commit,
        "julia_job_sha256": expected_job_sha,
        "runner_sha256": runner_sha,
        "arm_order": list(OWNER_ARM_IDS),
        "qualification_evidence": False,
    }
    for key, expected in expected_execution.items():
        require(execution.get(key) == expected,
                f"owner-lifetime execution identity mismatch: {key}")
    require(execution.get("status") in ("captured", "arm_failure"),
            "owner-lifetime execution status is invalid")
    require(fingerprint.get("owner_lifetime_criteria_sha256") == criteria_sha
            and fingerprint.get("owner_lifetime_criteria_sidecar_sha256") == criteria_sidecar_sha
            and fingerprint.get("owner_lifetime_source_commit") == expected_source_commit
            and fingerprint.get("owner_lifetime_job_sha256") == expected_job_sha,
            "owner-lifetime fingerprint identity mismatch")
    rows = execution.get("arms", [])
    require([row.get("arm_id") for row in rows] == list(OWNER_ARM_IDS),
            "owner-lifetime arm order/identity mismatch")
    source_identity = base_report.get("source_identity", {}) if base_report else {}
    require(source_identity.get("runner_sha256") == runner_sha
            and source_identity.get("diagnostic_source_commit") == expected_source_commit,
            "owner-lifetime runner/source differs from the base diagnostic")
    require(w3_criteria_sha == criteria["inputs"]["w3_criteria_sha256"]
            and sha256(dataset_dir / "w3_v16_dataset_manifest.json")
            == criteria["inputs"]["input_dataset_manifest_sha256"],
            "owner-lifetime W3 dataset binding mismatch")
    backend = criteria["fixture"]["backend"]
    require(runtime_observed.get("selected_gpu_uuid") == fingerprint.get("selected_gpu_uuid")
            and runtime_observed.get("cuda_visible_devices") == backend["cuda_visible_devices"]
            and runtime_observed.get("nvidia_driver_version") == backend["driver_version"],
            "owner-lifetime selected GPU/backend fingerprint mismatch")

    arm_data = {}
    arm_host_checks = {}
    accepted_process_outcomes = True
    input_identity = None
    backend_identity = None
    flow_origin = np.asarray(criteria["fixture"]["flow_origin_m"], dtype=np.float32)
    expected_geometry = criteria["inputs"]
    expected_phases = {"fixed_probes_before_gc_started", "fixed_probes_before_gc_completed",
                       "measure_before_gc_started", "measure_before_gc_completed",
                       "full_gc_1_started", "full_gc_1_completed",
                       "full_gc_2_started", "full_gc_2_completed",
                       "fixed_probes_after_gc_started", "fixed_probes_after_gc_completed",
                       "full_grid_geometry_started", "full_grid_geometry_completed",
                       "measure_after_gc_started", "measure_after_gc_completed",
                       "primal_step_1_started", "primal_step_1_completed",
                       "primal_step_2_started", "primal_step_2_completed", "arm_completed"}
    for row in rows:
        arm_id = row["arm_id"]
        report_path = folder / f"w3_v16_cuda_owner_lifetime_{arm_id}.json"
        progress_path = folder / f"w3_v16_cuda_owner_progress_{arm_id}.json"
        runner_record_path = folder / f"owner_lifetime_{arm_id}_runner.json"
        require(runner_record_path.is_file() and row.get("report_path")
                == (report_path.name if report_path.is_file() else None),
                f"owner-lifetime arm runner record/report inventory mismatch: {arm_id}")
        runner_record = json.loads(runner_record_path.read_text())
        require(sha256(runner_record_path) == manifest.get(runner_record_path.name)
                and runner_record == row,
                f"owner-lifetime runner record SHA/content mismatch: {arm_id}")
        require(row.get("log_path") == f"owner_lifetime_{arm_id}.log"
                and row.get("log_path") in manifest
                and row.get("log_sha256") == manifest[row["log_path"]],
                f"owner-lifetime exact arm log hash mismatch: {arm_id}")
        progress = json.loads(progress_path.read_text()) if progress_path.is_file() else {}
        report = json.loads(report_path.read_text()) if report_path.is_file() else progress
        if progress_path.is_file():
            require(row.get("progress_path") == progress_path.name
                    and row.get("progress_sha256") == manifest.get(progress_path.name),
                    f"owner-lifetime progress hash mismatch: {arm_id}")
        if report_path.is_file():
            require(row.get("report_sha256") == manifest.get(report_path.name),
                    f"owner-lifetime report hash mismatch: {arm_id}")
        require(report.get("arm_id") in (None, arm_id),
                f"owner-lifetime report arm identity mismatch: {arm_id}")
        if report.get("input_identity"):
            input_identity = report["input_identity"]
            require(input_identity.get("canonical_phi_fortran_sha256")
                    == expected_geometry["canonical_phi_fortran_sha256"]
                    and input_identity.get("canonical_phi_c_order_sha256")
                    == expected_geometry["canonical_phi_c_order_sha256"]
                    and input_identity.get("gpu_phi_roundtrip_sha256")
                    == expected_geometry["canonical_phi_fortran_sha256"]
                    and input_identity.get("canonical_state_sha256")
                    == expected_geometry["canonical_state_sha256"]
                    and input_identity.get("point_shape") == criteria["inputs"]["canonical_phi_shape"]
                    and input_identity.get("canonical_origin_m") == criteria["inputs"]["canonical_phi_origin_m"]
                    and input_identity.get("flow_dims") == criteria["fixture"]["flow_dims"]
                    and np.allclose(input_identity.get("flow_origin_m"), flow_origin,
                                    rtol=0, atol=1e-6)
                    and math.isclose(input_identity.get("spacing_m"),
                                     criteria["fixture"]["spacing_m"], abs_tol=1e-8),
                    f"owner-lifetime canonical/flow identity mismatch: {arm_id}")
            measured_margin = input_identity.get("cpu_measured_sdf_margin_m")
            require(math.isclose(measured_margin, w3_criteria["geometry"]["expected_margin_m"],
                                 rel_tol=0, abs_tol=1e-6),
                    f"owner-lifetime measured SDF margin mismatch: {arm_id}")
        if report.get("source_identity"):
            identity = report["source_identity"]
            require(identity.get("owner_criteria_sha256") == criteria_sha
                    and identity.get("owner_criteria_sidecar_sha256") == criteria_sidecar_sha
                    and identity.get("owner_job_sha256") == expected_job_sha
                    and identity.get("diagnostic_source_commit") == expected_source_commit
                    and identity.get("diagnostic_job_sha256") == _runner_pin("DIAGNOSTIC_JOB_SHA256", runner_path)
                    and identity.get("source_w3_job_sha256") == w3_criteria["inputs"]["job"]["sha256"]
                    and identity.get("project_sha256") == w3_criteria["inputs"]["project"]["sha256"]
                    and identity.get("manifest_sha256") == w3_criteria["inputs"]["manifest"]["sha256"]
                    and identity.get("julia_archive_sha256") == backend["julia_archive_sha256"]
                    and identity.get("runner_sha256") == runner_sha
                    and identity.get("dataset_id") == EXPECTED_W3_DATASET_ID
                    and identity.get("dataset_manifest_sha256") == expected_geometry["input_dataset_manifest_sha256"],
                    f"owner-lifetime source/input identity mismatch: {arm_id}")
        if report.get("runtime_identity"):
            runtime = report["runtime_identity"]
            for key, value in (
                ("julia_version", backend["julia_version"]),
                ("julia_threads", backend["julia_threads"]),
                ("waterlily_version", backend["waterlily_version"]),
                ("cuda_jl_version", backend["cuda_jl_version"]),
                ("cuda_runtime_version", backend["cuda_runtime_version"]),
                ("cuda_driver_api_version", backend["cuda_driver_api_version"]),
                ("gpu_name", backend["gpu_name"]),
                ("cuda_visible_devices", backend["cuda_visible_devices"]),
                ("visible_gpu_count", 1),
            ):
                require(runtime.get(key) == value,
                        f"owner-lifetime runtime identity mismatch: {arm_id}/{key}")
            require(runtime.get("gpu_uuid") == runtime_observed.get("selected_gpu_uuid"),
                    f"owner-lifetime GPU UUID mismatch: {arm_id}")
            backend_identity = runtime
        ownership = report.get("ownership", {})
        ownership_check = verify_owner_ownership_schema(arm_id, ownership) if ownership else None
        if report.get("runtime_identity") and report.get("qualification_evidence") is not False:
            raise ValueError("owner-lifetime diagnostic incorrectly marks qualification evidence")
        if report.get("qualification_flags"):
            require(all(value is False for value in report["qualification_flags"].values()),
                    f"owner-lifetime qualification flag became true: {arm_id}")
        if report.get("status") == "completed":
            require(report.get("last_stage") == "arm_completed"
                    and report.get("failed_stage") is None,
                    f"owner-lifetime completed arm has failure stage: {arm_id}")
            ownership_states = ownership.get("weakref_after_each_gc", [])
            if arm_id in ("A", "C"):
                require(ownership.get("weakref_after_gc") == "alive"
                        and ownership_states == ["alive", "alive"],
                        f"retained owner did not survive full GC: {arm_id}")
            force_checks = {}
            for phase, snapshot in report["force_history"].items():
                force_checks[phase] = _verify_owner_force(snapshot)
            probe_checks = _verify_owner_probe_sets(
                report, criteria, flow_origin, criteria["fixture"]["spacing_m"])
            geometry_checks, arrays = _verify_owner_arm_artifacts(
                folder, report, manifest, phi, lattice, criteria) if lattice is not None else ({}, {})
            report["_host_force_checks"] = force_checks
            arm_data[arm_id] = {
                "status": "completed",
                "owner_collected_during_forced_gc": ownership.get("owner_collected_during_forced_gc"),
                "report": report,
                "geometry_arrays": arrays.get("geometry_arrays"),
                "field_arrays": arrays.get("field_arrays"),
                "force_history": report.get("force_history"),
            }
            arm_host_checks[arm_id] = {
                "ownership": ownership_check,
                "probe_counts": probe_checks,
                "force_checks": force_checks,
                "geometry": geometry_checks,
            }
        else:
            process_hazard = (arm_id.startswith("B")
                              and row.get("expected_lifetime_hazard") is True
                              and ownership.get("owner_collected_during_forced_gc") is True
                              and row.get("last_stage") in expected_phases)
            if report.get("status") == "operation_error":
                process_hazard = process_hazard and row.get("process_returncode") == 0
                require(report.get("exact_exception"),
                        f"owner-lifetime Julia operation error lacks exception text: {arm_id}")
            else:
                process_hazard = process_hazard and row.get("process_returncode") != 0
            require(process_hazard == (row.get("expected_lifetime_hazard") is True),
                    f"owner-lifetime error classification is inconsistent: {arm_id}")
            acceptable = arm_id.startswith("B") and process_hazard
            if not acceptable:
                accepted_process_outcomes = False
            arm_data[arm_id] = {
                "status": "expected_lifetime_hazard" if process_hazard else "incomplete_or_unexpected",
                "owner_collected_during_forced_gc": ownership.get("owner_collected_during_forced_gc"),
                "report": report,
                "geometry_arrays": None,
                "field_arrays": None,
                "force_history": report.get("force_history"),
            }
            arm_host_checks[arm_id] = {
                "ownership": ownership_check,
                "expected_lifetime_hazard": process_hazard,
                "last_stage": row.get("last_stage"),
                "exact_exception": report.get("exact_exception"),
            }

    controls_ready = all(arm_data.get(name, {}).get("status") == "completed"
                         for name in ("A", "C"))
    controls_match = False
    b_classes = {}
    if controls_ready:
        controls_match = not _owner_pair_divergences(arm_data["A"], arm_data["C"], criteria)
        for arm_id in ("B1", "B2"):
            item = arm_data[arm_id]
            if item["status"] == "completed":
                if not controls_match:
                    b_classes[arm_id] = set()
                else:
                    b_classes[arm_id] = _owner_pair_divergences(arm_data["A"], item, criteria)
                    b_classes[arm_id] |= _owner_pair_divergences(arm_data["C"], item, criteria)
            elif item["status"] == "expected_lifetime_hazard":
                b_classes[arm_id] = {"cuda_lifetime_operation_error"}
            else:
                b_classes[arm_id] = set()
    b_collected = [arm_data.get(name, {}).get("owner_collected_during_forced_gc") is True
                   for name in ("B1", "B2")]
    common_divergence = (b_classes.get("B1", set()) & b_classes.get("B2", set()))
    if controls_ready and controls_match and all(b_collected) and common_divergence:
        classification = "strongly_supported"
    elif controls_ready and controls_match and (
            (all(arm_data.get(name, {}).get("report", {}).get("ownership", {}).get("weakref_after_gc") == "alive"
                 for name in ("B1", "B2")))
            or (all(b_collected) and not any(b_classes.values()))):
        classification = "weakened"
    else:
        classification = "unresolved"
    host_passed = (all(item.get("status") == "completed" for item in arm_data.values()
                       if item.get("status") != "expected_lifetime_hazard")
                   and all(arm_data.get(name, {}).get("status") in
                           ("completed", "expected_lifetime_hazard") for name in OWNER_ARM_IDS)
                   and accepted_process_outcomes)
    return {
        "criteria_path": str(OWNER_LIFETIME_CRITERIA_PATH.relative_to(ROOT)),
        "criteria_sha256": criteria_sha,
        "criteria_sidecar_sha256": criteria_sidecar_sha,
        "source_commit": expected_source_commit,
        "julia_job_sha256": expected_job_sha,
        "kernel_runner_sha256": runner_sha,
        "host_verifier_sha256": sha256(Path(__file__)),
        "execution_status": execution["status"],
        "arms": arm_data,
        "arm_host_checks": arm_host_checks,
        "host_controls_A_C_match": controls_match,
        "host_verification_passed": host_passed,
        "owner_lifetime_hypothesis": classification,
        "divergence_classes_by_unrooted_replicate": {
            key: sorted(value) for key, value in b_classes.items()},
        "same_divergence_class_in_both_replicates": sorted(common_divergence),
        "interpretation": {
            "strongly_supported": "Owner collection was bracketed by forced GC, both B replicates share a post-GC divergence/error class, and A/C controls agree.",
            "weakened": "The registered forced-GC contrast did not reproducibly change geometry, fields, or force, or the B owners remained retained.",
            "unresolved": "Control mismatch, unbracketed collection, incomplete evidence, or non-repeatable B behavior prevents a causal conclusion.",
        }[classification],
        "qualification_flags": criteria["qualification_flags"],
        "claim_scope": criteria["claim_scope"],
    }


def audit_w2b_drag_sign_precedent() -> dict[str, object]:
    criteria_sidecar = W2B_CRITERIA_PATH.with_suffix(W2B_CRITERIA_PATH.suffix + ".sha256")
    result_sidecar = W2B_RESULT_PATH.with_suffix(W2B_RESULT_PATH.suffix + ".sha256")
    criteria_sha = sha256(W2B_CRITERIA_PATH)
    result_sha = sha256(W2B_RESULT_PATH)
    require(criteria_sha == EXPECTED_W2B_CRITERIA_SHA256
            and criteria_sidecar.read_text().strip() == criteria_sha,
            "W2b round-5 sign-precedent criteria hash mismatch")
    require(result_sidecar.read_text().strip() == result_sha,
            "W2b round-5 sign-precedent result sidecar mismatch")
    result = json.loads(W2B_RESULT_PATH.read_text())
    require(result["criteria"]["sha256"] == criteria_sha
            and result["flags"]["waterlily_sampled_sphere_t4_qualified"] is True
            and result["gates"]["T4_drag_sign"] is True,
            "W2b round-5 registered positive-drag gate is not a PASS")
    values = {level: result["measurements"]["case_metrics"][f"gridsdf_{level}"]
              ["time_weighted_mean_drag"] for level in (16, 24, 32)}
    require(all(value > 0 for value in values.values()),
            "W2b round-5 sampled-sphere drag values are not positive")
    return {
        "criteria_path": str(W2B_CRITERIA_PATH.relative_to(ROOT)),
        "criteria_sha256": criteria_sha,
        "result_path": str(W2B_RESULT_PATH.relative_to(ROOT)),
        "result_sha256": result_sha,
        "registered_T4_drag_sign_gate": result["gates"]["T4_drag_sign"],
        "time_weighted_drag_solver_units_by_cells_per_diameter": values,
        "interpretation": "sign-convention precedent only; no v16 target or force-sign diagnosis",
    }


def classify_failure(folder: Path, progress: dict,
                    report: dict | None) -> dict[str, object]:
    last_completed_stage = progress.get("last_completed_stage")
    julia_log_path = folder / "w3_cuda_diagnostic.log"
    julia_log = julia_log_path.read_text(errors="replace") if julia_log_path.is_file() else ""
    error_path = folder / "ERROR.txt"
    wrapper_error = error_path.read_text(errors="replace") if error_path.is_file() else ""
    exception_text = julia_log if julia_log else wrapper_error
    owner_execution_path = folder / "owner_lifetime_execution.json"
    owner_execution = json.loads(owner_execution_path.read_text()) if owner_execution_path.is_file() else {}
    arm_reports = {}
    if owner_execution.get("unexpected_arm_failures"):
        for row in owner_execution.get("arms", []):
            arm_id = row.get("arm_id")
            report_path = folder / row.get("report_path", "")
            if arm_id and report_path.is_file():
                arm_reports[arm_id] = json.loads(report_path.read_text())
        missing_import_arms = {
            arm_id: arm_report for arm_id, arm_report in arm_reports.items()
            if arm_report.get("status") == "operation_error"
            and arm_report.get("last_stage") == "canonical_input_load_started"
            and "UndefVarError" in arm_report.get("exact_exception", "")
            and "v16_physical_profile_bodies" in arm_report.get("exact_exception", "")
        }
        expected_arms = {"A", "C", "B1", "B2"}
        if (set(owner_execution.get("unexpected_arm_failures", [])) == expected_arms
                and set(missing_import_arms) == expected_arms):
            failed_stage = (
                "owner-lifetime Julia import resolution before candidate body construction"
            )
            failure_class = "owner_lifetime_julia_missing_import"
            exception_text = missing_import_arms["A"]["exact_exception"]
        else:
            failed_stage = "owner-lifetime diagnostic arm process or identity"
            failure_class = "owner_lifetime_arm_unexpected_failure"
            exception_text = wrapper_error or exception_text
    elif ("run_owner_lifetime_arms" in wrapper_error
          and "FileNotFoundError" in wrapper_error
          and "julia-1.12.6/bin/julia" in wrapper_error):
        failed_stage = "owner-lifetime arm Julia process launch before A"
        failure_class = "owner_lifetime_runner_workspace_expired"
        exception_text = wrapper_error
    elif "compare_rows" in julia_log and "UndefVarError" in julia_log:
        failed_stage = "representative_probe_cpu_cuda_comparison"
        failure_class = "julia_diagnostic_float_literal_bug"
    elif "v16_representative_probes" in julia_log and "UndefVarError" in julia_log:
        failed_stage = "representative_probe_definitions"
        failure_class = "julia_diagnostic_probe_fixture_bug"
    elif report is not None and last_completed_stage == "diagnostic_report_written":
        failed_stage = last_completed_stage
        failure_class = "runner_output_identity_or_host_aggregation"
    elif last_completed_stage in ("w2b_sphere_control_started", "w2b_sphere_control_completed"):
        failed_stage = last_completed_stage
        failure_class = "w2b_control_cuda_body_or_force"
    elif last_completed_stage == "cuda_one_step_started":
        failed_stage = last_completed_stage
        failure_class = "first_cuda_primal_step"
    elif last_completed_stage == "cpu_one_step_started":
        failed_stage = last_completed_stage
        failure_class = "first_cpu_primal_step"
    elif last_completed_stage in ("cpu_one_step_completed", "cuda_one_step_completed"):
        failed_stage = last_completed_stage
        failure_class = "force_integration_after_first_step"
    elif last_completed_stage == "one_step_reproducer":
        failed_stage = last_completed_stage
        failure_class = "force_integration_or_lattice_artifact_write"
    elif last_completed_stage == "cuda_measure_started":
        failed_stage = last_completed_stage
        failure_class = "WaterLily_combined_body_measure_cuda"
    elif last_completed_stage == "cpu_measure_completed":
        failed_stage = last_completed_stage
        failure_class = "WaterLily_combined_body_measure_cuda"
    elif last_completed_stage == "cuda_simulation_constructed":
        failed_stage = last_completed_stage
        failure_class = "combined_body_solver_free_measurement"
    elif last_completed_stage in ("simulation_construction_started", "cpu_simulation_constructed"):
        failed_stage = last_completed_stage
        failure_class = "simulation_construction_cuda"
    elif last_completed_stage in ("cpu_combined_flow_lattice_completed", "cuda_combined_flow_lattice_completed"):
        failed_stage = last_completed_stage
        failure_class = "full_flow_lattice_composed_body_cuda"
    elif last_completed_stage in ("cpu_ground_flow_lattice_completed", "cuda_ground_flow_lattice_completed"):
        failed_stage = last_completed_stage
        failure_class = "full_flow_lattice_ground_body_cuda"
    elif last_completed_stage in ("cpu_candidate_flow_lattice_completed", "cuda_candidate_flow_lattice_completed"):
        failed_stage = last_completed_stage
        failure_class = "full_flow_lattice_candidate_sdf_cuda"
    elif last_completed_stage == "representative_probe_definitions_started":
        failed_stage = last_completed_stage
        failure_class = "julia_diagnostic_probe_fixture_bug"
    elif last_completed_stage == "representative_probe_definitions_completed":
        failed_stage = "first_representative_waterlily_body_probe"
        failure_class = "representative_waterlily_body_probe_cuda"
    elif last_completed_stage and last_completed_stage.endswith(
            "representative_probe_measurements_completed"):
        failed_stage = last_completed_stage.replace(
            "_representative_probe_measurements_completed",
            "_representative_probe_cpu_cuda_comparison")
        failure_class = "julia_diagnostic_probe_comparison"
    elif last_completed_stage and last_completed_stage.endswith("representative_probes_started"):
        failed_stage = last_completed_stage
        failure_class = "representative_waterlily_body_probe_cuda"
    elif last_completed_stage and last_completed_stage.endswith("representative_probes_completed"):
        failed_stage = "next_representative_body_probe_or_later"
        failure_class = "next_representative_waterlily_body_probe_cuda"
    elif last_completed_stage == "input_and_device_identity":
        failed_stage = "operation_after_input_and_device_identity"
        failure_class = "sdf_device_copy_or_roundtrip"
    elif (folder / "w3_cuda_diagnostic.log").is_file():
        failed_stage = "julia_job_start_or_canonical_input_load"
        failure_class = "julia_job_start_or_canonical_input_load"
    elif (folder / "julia_smoke.log").is_file():
        failed_stage = "cuda_setup_or_julia_smoke"
        failure_class = "cuda_setup_or_julia_smoke"
    elif (folder / "instantiate.log").is_file():
        failed_stage = "julia_runtime_or_package_setup"
        failure_class = "julia_runtime_or_package_setup"
    elif any((folder / name).is_file() for name in ("git_fetch.log", "git_checkout.log")):
        failed_stage = "source_fetch_or_hash_identity"
        failure_class = "source_fetch_or_hash_identity"
    elif (folder / "input_mount_inventory.json").is_file():
        failed_stage = "kaggle_input_discovery_or_dataset_identity"
        failure_class = "kaggle_input_discovery_or_dataset_identity"
    else:
        failed_stage = "kaggle_input_or_runner_bootstrap"
        failure_class = "kaggle_input_or_runner_bootstrap"
    result = {
        "last_completed_stage": last_completed_stage,
        "failed_stage": failed_stage,
        "failure_class": failure_class,
        "solver_started": bool(report and report.get("v16_one_step_reproducer", {}).get("cuda_solver_steps", 0))
        or last_completed_stage in ("cpu_one_step_started", "cpu_one_step_completed",
                     "cuda_one_step_started", "cuda_one_step_completed",
                     "one_step_reproducer", "w2b_sphere_control_started",
                     "w2b_sphere_control_completed", "diagnostic_report_written"),
        "exact_exception": exception_text or None,
    }
    if owner_execution.get("unexpected_arm_failures"):
        arm_rows = owner_execution.get("arms", [])
        result["owner_arm_processes_started"] = bool(arm_rows)
        result["owner_primal_step_reached"] = any(
            str(row.get("last_stage", "")).startswith("primal_step_")
            for row in arm_rows)
        result["owner_arm_exceptions"] = {
            row["arm_id"]: arm_reports.get(row.get("arm_id"), {}).get("exact_exception")
            for row in arm_rows if row.get("arm_id") in arm_reports
        }
        if wrapper_error:
            result["runner_exception"] = wrapper_error
    return result


def build_evidence(output_dir: Path, dataset_dir: Path, *, kernel_version: int,
                   kernel_status: str, kaggle_log: Path,
                   kaggle_status_file: Path,
                   kernel_runner: Path = DIAGNOSTIC_RUNNER) -> dict[str, object]:
    kernel_runner = kernel_runner.resolve()
    criteria, criteria_sha = load_criteria()
    folder = locate_stage(output_dir)
    output_manifest, output_manifest_sha, output_status = verify_output_files(folder)
    phi, metadata = verify_dataset(criteria, dataset_dir)
    report_path = folder / "w3_v16_cuda_diagnostic.json"
    progress_path = folder / "progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.is_file() else {
        "last_completed_stage": "input_or_runtime_setup_before_julia_checkpoint"
    }
    report = json.loads(report_path.read_text()) if report_path.is_file() else None
    runner_sha = sha256(kernel_runner)
    fingerprint_path = folder / "fingerprint.json"
    runtime_path = folder / "runtime_identity.json"
    fingerprint = json.loads(fingerprint_path.read_text()) if fingerprint_path.is_file() else {}
    runtime_observed = json.loads(runtime_path.read_text()) if runtime_path.is_file() else {}
    checkout_identity = checkout_job_identity(folder)
    diagnostic_source_commit = (
        report["source_identity"].get("diagnostic_source_commit") if report else None
    ) or fingerprint.get("source_commit")
    diagnostic_job_sha = (
        report["source_identity"].get("diagnostic_job_sha256") if report else None
    ) or fingerprint.get("diagnostic_job_sha256")
    if checkout_identity is not None:
        checkout_commit, checkout_job_sha = checkout_identity
        require(diagnostic_source_commit in (None, checkout_commit),
                "diagnostic source commit differs from Kaggle checkout log")
        require(diagnostic_job_sha in (None, checkout_job_sha),
                "diagnostic Julia job hash differs from Kaggle checkout source")
        diagnostic_source_commit = checkout_commit
        diagnostic_job_sha = checkout_job_sha
    inventory_path = folder / "nvidia_smi.csv"
    if inventory_path.is_file() and fingerprint:
        require([line.strip() for line in inventory_path.read_text().splitlines() if line.strip()]
                == fingerprint.get("gpu_inventory"),
                "nvidia-smi inventory output differs from fingerprint")
    smoke_path = folder / "julia_smoke.log"
    if fingerprint and smoke_path.is_file():
        require(sha256(smoke_path) == fingerprint.get("cuda_smoke_sha256"),
                "CUDA smoke log differs from partial diagnostic fingerprint")
    source_identity = (verify_report(report, criteria, criteria_sha, dataset_dir,
                                     runner_sha, fingerprint, runtime_observed,
                                     kernel_runner)
                       if report else verify_partial_fingerprint(
                           fingerprint, criteria, criteria_sha, dataset_dir,
                           runner_sha, checkout_identity))
    lattice_summary = None
    numeric_checks = None
    lattice = None
    if report is not None:
        lattice_path = folder / "v16_flow_lattice.csv"
        lattice_sha = sha256(lattice_path)
        require(report["v16_flow_lattice"].get("flow_lattice_csv") == lattice_path.name
                and report["v16_flow_lattice"].get("flow_lattice_csv_sha256") == lattice_sha,
                "Julia flow-lattice CSV identity/hash mismatch")
        lattice = read_lattice_csv(lattice_path,
                                   tuple(criteria["profile_adapter"]["cell_dims"]))
        require(report["v16_flow_lattice"].get("sample_count") == lattice["row_count"],
                "Julia flow-lattice sample count mismatch")
        numeric_checks = verify_geometry_contract(lattice, criteria, phi)
        numeric_checks["representative_probes"] = verify_representative_probes(
            report, criteria, phi)
        expected_stats = report["v16_flow_lattice"]
        for body in BODY_NAMES:
            for backend in BACKENDS:
                observed_stats = matrix_stats(lattice[f"{body}_{backend}"])
                report_backend = "cuda" if backend == "gpu" else "cpu"
                reported_stats = expected_stats[f"{report_backend}_{body}"]
                for key, value in observed_stats.items():
                    reported = reported_stats.get(key)
                    if value is None:
                        require(reported is None,
                                f"Julia/host lattice statistic mismatch: {body}/{backend}/{key}")
                    elif isinstance(value, int):
                        require(value == reported,
                                f"Julia/host lattice statistic mismatch: {body}/{backend}/{key}")
                    else:
                        require(math.isclose(value, reported if reported is not None else math.nan,
                                             rel_tol=2e-6, abs_tol=2e-6),
                                f"Julia/host lattice statistic mismatch: {body}/{backend}/{key}")
                comparison = compare_cpu_cuda(lattice[f"{body}_cpu"],
                                              lattice[f"{body}_gpu"],
                                              criteria["geometry"]["spacing_m"])
                reported_comparison = expected_stats[
                    f"{body}_cpu_cuda_comparison"]
                for key, value in comparison.items():
                    reported = reported_comparison.get(key)
                    if isinstance(value, int):
                        require(value == reported,
                                f"Julia/host CPU-CUDA comparison mismatch: {body}/{key}")
                    else:
                        require(math.isclose(value, reported if reported is not None else math.nan,
                                             rel_tol=2e-6, abs_tol=5e-8),
                                f"Julia/host CPU-CUDA comparison mismatch: {body}/{key}")
        lattice_summary = {
            "row_count": lattice["row_count"],
            "header_sha256": hashlib.sha256(
                (",".join(expected_header()) + "\n").encode()).hexdigest(),
            "csv_sha256": lattice_sha,
            "host_recomputed_stats": {
                f"{body}_{backend}": matrix_stats(lattice[f"{body}_{backend}"])
                for body in BODY_NAMES for backend in BACKENDS
            },
        }
    owner_lifetime = verify_owner_lifetime_experiment(
        folder, output_manifest, report, fingerprint, runtime_observed,
        criteria, criteria_sha, dataset_dir, phi, lattice, kernel_runner)
    require(kernel_version > 0, "Kaggle kernel version must be positive")
    normalized_status = kernel_status.upper()
    require(normalized_status.endswith("COMPLETE") or normalized_status.endswith("ERROR"),
            "Kaggle kernel must be terminal before verification")
    require(Path(kaggle_log).is_file(), "exact-version Kaggle log is required")
    require(Path(kaggle_status_file).is_file(), "exact-version Kaggle status capture is required")
    log_sha = sha256(kaggle_log)
    status_sha = sha256(kaggle_status_file)
    failed_stage = progress.get("last_completed_stage")
    base_complete = output_status == "COMPLETED" and report is not None
    owner_complete = owner_lifetime["host_verification_passed"]
    complete = base_complete and owner_complete
    return {
        "evidence_type": "diagnostic_only",
        "diagnostic_id": "w3_v16_cuda_body_force_minimal_diagnostic_2026_09",
        "created_utc_date": "2026-09-28",
        "kernel_id": "ramhachi888/cfd-opt-sdf-w3-v16-cuda-diagnostic",
        "kernel_version": kernel_version,
        "kaggle_status": kernel_status,
        "output_status": output_status,
        "criteria_path": str(CRITERIA_PATH.relative_to(ROOT)),
        "criteria_sha256": criteria_sha,
        "source_commit": EXPECTED_W3_SOURCE_COMMIT,
        "diagnostic_source_commit": diagnostic_source_commit,
        "diagnostic_job_sha256": diagnostic_job_sha,
        "kernel_runner_sha256": runner_sha,
        "kernel_runner_source_path": str(kernel_runner.relative_to(ROOT))
        if kernel_runner.is_relative_to(ROOT) else str(kernel_runner),
        "julia_job_sha256": diagnostic_job_sha,
        "host_verifier_sha256": sha256(Path(__file__)),
        "input_dataset_id": EXPECTED_W3_DATASET_ID,
        "input_dataset_manifest_sha256": sha256(dataset_dir / "w3_v16_dataset_manifest.json"),
        "input_criteria_sidecar_sha256": sha256(dataset_dir / "w3_v16_criteria.json.sha256"),
        "canonical_state_sha256": metadata.get("state_sha256"),
        "canonical_phi_c_order_sha256": criteria["geometry"]["phi_c_order_sha256"],
        "canonical_phi_fortran_sha256": criteria["geometry"]["phi_fortran_sha256"],
        "exact_kaggle_log_sha256": log_sha,
        "exact_kaggle_status_sha256": status_sha,
        "output_sha256_manifest_sha256": output_manifest_sha,
        "output_artifacts": output_manifest,
        "input_mount_inventory": json.loads((folder / "input_mount_inventory.json").read_text())
        if (folder / "input_mount_inventory.json").is_file() else None,
        "last_completed_stage": failed_stage,
        "solver_steps_v16": (report.get("v16_one_step_reproducer", {}).get("cuda_solver_steps", 0)
                              if report else progress.get("one_step_reproducer", {}).get("cuda_steps", 0)),
        "base_diagnostic_complete": base_complete,
        "owner_lifetime_diagnostic_complete": owner_complete,
        "diagnostic_complete": complete,
        "host_artifact_verification_passed": bool(source_identity and output_manifest),
        "owner_lifetime_host_verification_passed": owner_complete,
        "source_identity_verification": source_identity,
        "partial_source_checkout_verification": {
            "diagnostic_source_commit": checkout_identity[0],
            "diagnostic_job_sha256": checkout_identity[1],
        } if checkout_identity is not None else None,
        "lattice_verification": lattice_summary,
        "independent_numeric_diagnostics": numeric_checks,
        "force_snapshot_verification": verify_force_snapshots(report) if report else None,
        "owner_lifetime_experiment": owner_lifetime,
        "w2b_sign_convention_audit": audit_w2b_drag_sign_precedent(),
        "failure_classification": None if complete else classify_failure(folder, progress, report),
        "qualification_flags": {
            "waterlily_v16_primal_qualified": False,
            "physical_profile_qualified": False,
            "grid_response_qualified": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
            "shape_update_allowed": False,
        },
        "claim_scope": "CPU/T4 CUDA implementation-layer and owner-lifetime diagnosis only; no primal or physical qualification",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dataset-dir", type=Path,
                        default=ROOT / "work/kaggle_w3_v16_dataset_round3")
    parser.add_argument("--kernel-version", required=True, type=int)
    parser.add_argument("--kernel-status", required=True)
    parser.add_argument("--kaggle-log", required=True, type=Path)
    parser.add_argument("--kaggle-status-file", required=True, type=Path)
    parser.add_argument("--kernel-runner", type=Path, default=DIAGNOSTIC_RUNNER,
                        help="exact runner source uploaded for this kernel version")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    evidence = build_evidence(args.output_dir, args.dataset_dir,
                              kernel_version=args.kernel_version,
                              kernel_status=args.kernel_status,
                              kaggle_log=args.kaggle_log,
                              kaggle_status_file=args.kaggle_status_file,
                              kernel_runner=args.kernel_runner)
    target = args.evidence or (ROOT / "docs/evidence" /
        f"kaggle_w3_v16_cuda_diagnostic_version{args.kernel_version}_2026_09.json")
    sidecar = target.with_suffix(target.suffix + ".sha256")
    require_append_only_evidence_target(target, sidecar)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    sidecar.write_text(sha256(target) + "\n")
    print(json.dumps({"evidence": str(target), "sha256": sha256(target),
                      "diagnostic_complete": evidence["diagnostic_complete"],
                      "host_artifact_verification_passed": evidence["host_artifact_verification_passed"],
                      "qualification_flags": evidence["qualification_flags"]}, indent=2))


if __name__ == "__main__":
    main()
