#!/usr/bin/env python3
"""Independently verify a version-specific Kaggle W3 v16 output download."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09.json"
DATASET_DIR = ROOT / "work/kaggle_w3_v16_dataset"
RUNNER = ROOT / "infra/kaggle/kernel_w3/runner.py"
OUTPUT_NAME = "w3_v16"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_output_files(folder: Path) -> tuple[int, str]:
    require((folder / "DONE").is_file(), "Kaggle W3 completion marker missing")
    require(not (folder / "ERROR.txt").exists(), "Kaggle W3 ERROR.txt is present")
    require((folder / "outcome.json").is_file(), "Kaggle W3 outcome missing")
    manifest_path = folder / "sha256.json"
    manifest = json.loads(manifest_path.read_text())
    names = {item.name for item in folder.iterdir() if item.is_file()}
    require(set(manifest) == names - {"sha256.json", "DONE"},
            "Kaggle W3 output inventory differs from its SHA manifest")
    for name, expected in manifest.items():
        require(Path(name).name == name and sha256(folder / name) == expected,
                f"Kaggle W3 output SHA-256 mismatch: {name}")
    return len(manifest), sha256(manifest_path)


def load_criteria(path: Path) -> tuple[dict, str]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    require(path.is_file() and sidecar.is_file(), "registered W3 criteria or sidecar missing")
    digest = sha256(path)
    require(sidecar.read_text().strip() == digest, "registered W3 criteria SHA mismatch")
    criteria = json.loads(path.read_text())
    require(criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True
            and criteria.get("status") == "registered_not_run",
            "W3 criteria do not describe a preregistered first primal")
    return criteria, digest


def verify_registered_source(criteria: dict) -> bool:
    require(criteria.get("source_commit") == criteria.get("registered_source_commit"),
            "W3 registered source commit fields disagree")
    for name, entry in criteria["inputs"].items():
        if entry.get("location") != "source_repo":
            continue
        path = ROOT / entry["path"]
        require(path.is_file() and sha256(path) == entry["sha256"],
                f"registered W3 source input changed: {name}")
    require(sha256(RUNNER) == criteria["inputs"]["kernel_runner"]["sha256"],
            "registered W3 Kaggle runner changed")
    return True


def verify_dataset(criteria: dict, criteria_sha: str, dataset_dir: Path) -> tuple[dict, float]:
    criteria_file = dataset_dir / "w3_v16_criteria.json"
    criteria_sidecar = criteria_file.with_suffix(criteria_file.suffix + ".sha256")
    require(criteria_file.is_file() and sha256(criteria_file) == criteria_sha,
            "staged W3 criteria differs from local preregistration")
    require(criteria_sidecar.is_file() and criteria_sidecar.read_text().strip() == criteria_sha,
            "staged W3 criteria sidecar differs from local preregistration")
    manifest_path = dataset_dir / "w3_v16_dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get("dataset_id") == criteria["input_dataset_id"],
            "staged W3 dataset id mismatch")
    require(manifest.get("criteria_sha256") == criteria_sha,
            "staged W3 dataset manifest criteria binding mismatch")
    expected_dataset_names = {
        "sdf_design_state.npz", "w3_v16_criteria.json",
        "w3_v16_criteria.json.sha256", "canonical_v16_phi_f4_fortran.raw",
    }
    require(set(manifest.get("files", {})) == expected_dataset_names,
            "staged W3 dataset file inventory mismatch")

    state_path = dataset_dir / criteria["inputs"]["canonical_state_npz"]["path"]
    raw_path = dataset_dir / criteria["inputs"]["canonical_phi_fortran_raw"]["path"]
    require(sha256(state_path) == criteria["inputs"]["canonical_state_npz"]["sha256"],
            "staged canonical v16 NPZ hash mismatch")
    require(sha256(raw_path) == criteria["inputs"]["canonical_phi_fortran_raw"]["sha256"],
            "staged canonical v16 Fortran phi hash mismatch")
    for name, expected in manifest["files"].items():
        path = dataset_dir / name
        require(path.is_file() and sha256(path) == expected,
                f"staged W3 dataset file hash mismatch: {name}")

    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    geometry = criteria["geometry"]
    require(list(phi.shape) == geometry["point_shape"], "canonical v16 phi shape mismatch")
    require(np.isfinite(phi).all(), "canonical v16 phi contains non-finite values")
    require(metadata.get("state_sha256") == geometry["state_sha256"],
            "canonical v16 state metadata hash mismatch")
    require(metadata.get("source_sha256") == geometry["source_surface_sha256"],
            "canonical v16 source-surface lineage mismatch")
    require(metadata.get("shape") == geometry["point_shape"]
            and metadata.get("origin_m") == geometry["origin_m"]
            and metadata.get("spacing_m") == geometry["spacing_m"],
            "canonical v16 world-grid metadata mismatch")
    phi_c = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    phi_f = hashlib.sha256(np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")).hexdigest()
    require(phi_c == geometry["phi_c_order_sha256"], "canonical v16 C-order phi hash mismatch")
    require(phi_f == geometry["phi_fortran_sha256"], "canonical v16 Fortran phi hash mismatch")
    require(raw_path.read_bytes() == np.asarray(phi, dtype="<f4", order="F").tobytes(order="F"),
            "staged raw phi bytes differ from canonical NPZ")

    indices = [np.arange(n, dtype=np.float64) for n in phi.shape]
    spacing = geometry["spacing_m"]
    gaps = [np.minimum(index, n - 1 - index) * spacing for index, n in zip(indices, phi.shape)]
    ix = np.broadcast_to(gaps[0][:, None, None], phi.shape)
    iy = np.broadcast_to(gaps[1][None, :, None], phi.shape)
    iz = np.broadcast_to(gaps[2][None, None, :], phi.shape)
    solid = phi < 0
    require(solid.any(), "canonical v16 phi has no solid samples")
    margin = float(np.min(np.minimum(np.minimum(ix, iy), iz)[solid] + phi[solid]))
    return metadata, margin


def read_force_rows(path: Path, measurement: dict) -> list[dict[str, float]]:
    expected = ["step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
                "drag_solver", "downforce_solver", "pressure_drag_solver",
                "viscous_drag_solver"]
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == expected, "W3 force CSV schema mismatch")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    require(bool(rows), "W3 force CSV is empty")
    require(all(math.isfinite(value) for row in rows for value in row.values()),
            "W3 force CSV contains a non-finite value")
    require(all(right["step"] > left["step"] and right["t_u_l"] > left["t_u_l"]
                for left, right in zip(rows, rows[1:])),
            "W3 force CSV step or time is not strictly increasing")
    stride = measurement["sample_every_solver_steps"]
    require(all(row["step"] % stride == 0 for row in rows),
            "W3 force CSV sample step is off the registered stride")
    require(all(right["step"] - left["step"] == stride for left, right in zip(rows, rows[1:])),
            "W3 force CSV sampling is not regular")
    return rows


def _time_weighted_mean(rows: list[dict[str, float]], key: str) -> float:
    numerator = denominator = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        numerator += 0.5 * (left[key] + right[key]) * dt
        denominator += dt
    return numerator / denominator if denominator > 0 else sum(row[key] for row in rows) / len(rows)


def recompute_metrics(rows: list[dict[str, float]], measurement: dict) -> dict:
    start, end = measurement["burn_in_t_u_l"], measurement["t_end_t_u_l"]
    window = [row for row in rows if start <= row["t_u_l"] <= end]
    middle = 0.5 * (start + end)
    first = [row for row in window if row["t_u_l"] < middle]
    second = [row for row in window if row["t_u_l"] >= middle]
    require(len(window) >= measurement["minimum_window_samples"] and first and second,
            "W3 registered force window is incomplete")
    drag_mean = sum(row["drag_solver"] for row in window) / len(window)
    down_mean = sum(row["downforce_solver"] for row in window) / len(window)
    area_solver = measurement["reference_area_m2"] / measurement["spacing_m"] ** 2
    return {
        "window_samples": len(window),
        "window_mean_drag_solver": drag_mean,
        "window_mean_downforce_solver": down_mean,
        "window_time_weighted_drag_solver": _time_weighted_mean(window, "drag_solver"),
        "window_time_weighted_downforce_solver": _time_weighted_mean(window, "downforce_solver"),
        "diagnostic_first_half_mean_drag_solver": sum(row["drag_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_drag_solver": sum(row["drag_solver"] for row in second) / len(second),
        "diagnostic_first_half_mean_downforce_solver": sum(row["downforce_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_downforce_solver": sum(row["downforce_solver"] for row in second) / len(second),
        "cd_window_mean": drag_mean / (0.5 * area_solver),
        "cd_time_weighted": _time_weighted_mean(window, "drag_solver") / (0.5 * area_solver),
    }


def metrics_match(summary: dict, metrics: dict, measurement: dict) -> bool:
    tolerance = measurement["host_recompute_relative_tolerance"]
    return all(math.isclose(summary.get(key, math.nan), value, rel_tol=tolerance, abs_tol=1e-10)
               for key, value in metrics.items())


def force_components_close(rows: list[dict[str, float]], measurement: dict) -> bool:
    relative = measurement["force_component_relative_tolerance"]
    absolute = measurement["force_component_absolute_tolerance"]
    return all(
        math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=relative, abs_tol=absolute)
        and math.isclose(row["downforce_solver"], -row["fz_solver"],
                         rel_tol=relative, abs_tol=absolute)
        and math.isclose(row["drag_solver"],
                         row["pressure_drag_solver"] + row["viscous_drag_solver"],
                         rel_tol=relative, abs_tol=absolute)
        for row in rows
    )


def observed_backend_identity(criteria: dict, summary: dict,
                             fingerprint: dict, gpu_rows: list[str]) -> dict:
    backend = criteria["backend"]
    return {
        "accelerator": backend["accelerator"],
        "machine_shape": backend["machine_shape"],
        "gpu_count": len(gpu_rows),
        "gpu_name": summary["gpu_name"],
        "driver_version": gpu_rows[0].split(", ")[-1],
        "cuda_visible_devices": fingerprint["cuda_visible_devices"],
        "julia_archive_sha256": fingerprint["julia_archive_sha256"],
        "compute_capability": backend["compute_capability"],
        "cuda_driver_api_version": backend["cuda_driver_api_version"],
        "cuda_runtime_version": backend["cuda_runtime_version"],
        "cuda_jl_version": summary["cuda_jl_version"],
        "julia_version": summary["julia_version"],
        "julia_threads": summary["julia_threads"],
        "waterlily_version": summary["waterlily_version"],
        "waterlily_backend": summary["waterlily_backend"],
    }


def verify(download: Path, *, criteria_path: Path = CRITERIA,
           dataset_dir: Path = DATASET_DIR, kernel_version: int | None = None) -> dict:
    criteria, criteria_sha = load_criteria(criteria_path)
    source_ok = verify_registered_source(criteria)
    metadata, margin = verify_dataset(criteria, criteria_sha, dataset_dir)
    folder = download / OUTPUT_NAME if (download / OUTPUT_NAME).is_dir() else download
    file_count, output_manifest_sha = verify_output_files(folder)
    summary = json.loads((folder / "v16.summary.json").read_text())
    outcome = json.loads((folder / "outcome.json").read_text())
    fingerprint = json.loads((folder / "fingerprint.json").read_text())
    measurement = criteria["measurement"]
    geometry = criteria["geometry"]
    profile = criteria["profile_adapter"]
    backend = criteria["backend"]

    require(outcome.get("summary") == summary, "W3 outcome/summary copies disagree")
    require(outcome.get("criteria_sha256") == criteria_sha,
            "W3 outcome is bound to a different criteria file")
    require(fingerprint.get("criteria_sha256") == criteria_sha,
            "W3 fingerprint is bound to a different criteria file")
    require(fingerprint.get("runner_sha256") == criteria["inputs"]["kernel_runner"]["sha256"]
            and fingerprint.get("runner_sha256") == sha256(RUNNER),
            "W3 runner fingerprint mismatch")
    require(fingerprint.get("julia_archive_sha256") == backend["julia_archive_sha256"],
            "W3 Julia archive fingerprint mismatch")
    require(fingerprint.get("cuda_visible_devices") == backend["cuda_visible_devices"],
            "W3 CUDA visible-device fingerprint mismatch")
    require(outcome.get("source_commit") == criteria["source_commit"]
            and fingerprint.get("source_commit") == criteria["source_commit"],
            "W3 source commit mismatch")
    require((folder / "input_dataset_manifest.json").read_bytes()
            == (dataset_dir / "w3_v16_dataset_manifest.json").read_bytes(),
            "W3 run input dataset manifest differs from staged dataset")
    output_metadata = json.loads((folder / "input_state_metadata.json").read_text())
    require(output_metadata == metadata, "W3 run input state metadata differs from canonical NPZ")
    gpu_rows = [row for row in csv.reader((folder / "nvidia_smi.csv").open(newline=""))
                if row and any(cell.strip() for cell in row)]
    gpu_rows = [", ".join(cell.strip() for cell in row) for row in gpu_rows]
    require(len(gpu_rows) == backend["gpu_count"], "W3 GPU inventory count mismatch")
    gpu_cells = [[cell.strip() for cell in row.split(",")] for row in gpu_rows]
    uuids = [row[2] for row in gpu_cells]
    require(all(backend["gpu_name"] in row[1] for row in gpu_cells)
            and all(row[-1] == backend["driver_version"] for row in gpu_cells)
            and len(set(uuids)) == backend["gpu_count"]
            and all(value.startswith("GPU-") for value in uuids),
            "W3 Kaggle T4 inventory identity mismatch")
    selected_uuid = uuids[0]
    smoke = (folder / "julia_smoke.log").read_text()
    smoke_markers = (
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
        f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
        f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
        f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
        f"JULIA_VERSION {backend['julia_version']}",
        f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
        f"WATERLILY_VERSION {backend['waterlily_version']}",
        f"GPU_NAME {backend['gpu_name']}",
        "NO_SOLVER_STEP",
    )
    smoke_ok = all(marker in smoke for marker in smoke_markers)

    force_path = folder / "v16.forces.csv"
    require(sha256(force_path) == summary.get("force_csv_sha256"),
            "W3 force CSV hash mismatch")
    rows = read_force_rows(force_path, measurement)
    metrics = recompute_metrics(rows, measurement)
    metric_match = metrics_match(summary, metrics, measurement)
    metric_match = metric_match and all(
        math.isclose(outcome.get("host_recomputed_metrics", {}).get(key, math.nan), value,
                     rel_tol=measurement["host_recompute_relative_tolerance"], abs_tol=1e-10)
        for key, value in metrics.items()
    )
    force_components_ok = force_components_close(rows, measurement)

    adapter = json.loads((folder / "w3_adapter_contract.json").read_text())
    gates = {
        "T0_registered_inputs": source_ok and metadata is not None,
        "T1_canonical_v16_identity": (
            summary.get("state_sha256") == geometry["state_sha256"]
            and summary.get("source_surface_sha256") == geometry["source_surface_sha256"]
            and summary.get("phi_c_order_sha256") == geometry["phi_c_order_sha256"]
            and summary.get("phi_fortran_sha256") == geometry["phi_fortran_sha256"]
            and summary.get("device_roundtrip_sha256") == geometry["phi_fortran_sha256"]
            and fingerprint.get("state_npz_sha256") == geometry["state_npz_sha256"]
            and summary.get("dims") == profile["cell_dims"]
            and summary.get("origin_m") == geometry["origin_m"]
            and summary.get("spacing_m") == geometry["spacing_m"]
        ),
        "T2_margin_gate": (
            summary.get("phi_margin_gate_m") == geometry["margin_gate_m"]
            and abs(margin - geometry["expected_margin_m"]) <= geometry["margin_tolerance_m"]
            and abs(summary.get("phi_margin_m", math.inf) - margin) <= geometry["margin_tolerance_m"]
            and margin >= geometry["margin_gate_m"]
        ),
        "T3_profile_adapter_is_explicitly_limited": (
            summary.get("source_profile_equivalent") is False
            and summary.get("physical_profile_qualified") is False
            and adapter.get("source_profile_equivalent") is False
            and adapter.get("physical_profile_qualified") is False
            and summary.get("x_max_boundary") == profile["x_max_boundary"]
            and summary.get("pressure_boundary") == profile["pressure_boundary"]
            and adapter.get("x_max_boundary") == profile["x_max_boundary"]
            and adapter.get("pressure_boundary") == profile["pressure_boundary"]
        ),
        "T4_backend_identity": (
            len(gpu_rows) == backend["gpu_count"] and smoke_ok
            and fingerprint.get("julia_archive_sha256") == backend["julia_archive_sha256"]
            and fingerprint.get("cuda_visible_devices") == backend["cuda_visible_devices"]
            and summary.get("gpu_uuid") == selected_uuid
            and summary.get("gpu_name") == backend["gpu_name"]
            and summary.get("julia_version") == backend["julia_version"]
            and summary.get("julia_threads") == backend["julia_threads"]
            and summary.get("waterlily_version") == backend["waterlily_version"]
            and summary.get("cuda_jl_version") == backend["cuda_jl_version"]
        ),
        "T5_primal_completion": (
            summary.get("t_end_target") == measurement["t_end_t_u_l"]
            and summary.get("t_end_reached", 0) >= measurement["t_end_t_u_l"]
            and summary.get("steps", 0) > 0
        ),
        "T6_finite_fields_and_candidate_forces": (
            summary.get("finite_u") is True and summary.get("finite_p") is True
            and summary.get("force_samples") == len(rows)
            and summary.get("window_samples", 0) >= measurement["minimum_window_samples"]
        ),
        "T7_drag_orientation_and_host_recomputation": (
            summary.get("window_time_weighted_drag_solver", 0) > 0
            and force_components_ok and metric_match
        ),
        "T8_runtime_and_vram": (
            0 < summary.get("wall_seconds", 0) <= measurement["runtime_limit_s"]
            and 0 < summary.get("peak_vram_bytes", 0) < summary.get("vram_total_bytes", 0)
        ),
        "T9_source_commit_and_runner": (
            fingerprint.get("source_commit") == criteria["source_commit"]
            and fingerprint.get("runner_sha256") == criteria["inputs"]["kernel_runner"]["sha256"]
            and len(criteria_sha) == 64
        ),
    }
    require(outcome.get("gates") == gates, "W3 runner gates disagree with host recomputation")
    require(all(gates.values()), f"W3 preregistered gates failed: {gates}")
    require(outcome.get("physical_profile_qualified") is False
            and outcome.get("shape_update_allowed") is False,
            "W3 run incorrectly promoted a qualification/update flag")
    criteria_path = Path(criteria_path).resolve()
    return {
        "verdict": "PASS",
        "host_verification_passed": True,
        "kernel_version": kernel_version,
        "criteria_path": criteria_path.relative_to(ROOT).as_posix(),
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "host_verifier_sha256": sha256(HOST_VERIFIER),
        "selected_gpu_uuid": selected_uuid,
        "backend_identity": observed_backend_identity(
            criteria, summary, fingerprint, gpu_rows),
        "verified_files": file_count,
        "output_manifest_sha256": output_manifest_sha,
        "margin_m": margin,
        "force_metrics": metrics,
        "gates": gates,
        "physical_profile_qualified": False,
        "shape_update_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific kaggle kernels output directory")
    parser.add_argument("--criteria", type=Path, default=CRITERIA)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--kernel-version", type=int)
    args = parser.parse_args()
    print(json.dumps(verify(args.download, criteria_path=args.criteria,
                            dataset_dir=args.dataset_dir,
                            kernel_version=args.kernel_version), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
