#!/usr/bin/env python3
"""Independently verify a version-bound canonical-state W4 sensitivity output."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import subprocess
import traceback
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ROOT / "docs/evidence/kaggle_w4_v16_sensitivity_criteria_2026_09.json"
DATASET_DIR = ROOT / "work/kaggle_w4_v16_dataset"
RUNNER = ROOT / "infra/kaggle/kernel_w4/runner.py"
OUTPUT_NAME = "w4_v16_sensitivity"
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
]
CASE_IDS = ["flow_16", "flow_24", "flow_32", "domain_xplus1m_16"]
EXPECTED_CASES = {
    "flow_16": (16, 0.05, [100, 48, 36], 0.2, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "flow_24": (24, 1.0 / 30.0, [150, 72, 54], 0.3, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "flow_32": (32, 0.025, [200, 96, 72], 0.4, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "domain_xplus1m_16": (16, 0.05, [120, 48, 36], 0.2, [[-2.5, 3.5], [-1.2, 1.2], [-0.9, 0.9]]),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def remote_inventory_sha256(files: dict[str, str]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def state_label(criteria: dict) -> str:
    return criteria["geometry"].get("state_label", "v16")


def dataset_names(criteria: dict) -> dict[str, str]:
    prefix = f"w4_{state_label(criteria)}"
    return {
        "criteria": f"{prefix}_criteria.json",
        "manifest": f"{prefix}_dataset_manifest.json",
        "output": f"{prefix}_sensitivity",
    }


def verify_output_files(folder: Path) -> tuple[int, str]:
    require((folder / "DONE").is_file(), "Kaggle W4 completion marker missing")
    require(not (folder / "ERROR.txt").exists(), "Kaggle W4 ERROR.txt is present")
    manifest_path = folder / "sha256.json"
    manifest = json.loads(manifest_path.read_text())
    names = {item.name for item in folder.iterdir() if item.is_file()}
    require(set(manifest) == names - {"sha256.json", "DONE"},
            "Kaggle W4 output inventory differs from its SHA manifest")
    for name, expected in manifest.items():
        require(Path(name).name == name and sha256(folder / name) == expected,
                f"Kaggle W4 output SHA-256 mismatch: {name}")
    return len(manifest), sha256(manifest_path)


def load_criteria(path: Path) -> tuple[dict, str]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    require(path.is_file() and sidecar.is_file(), "registered W4 criteria or sidecar missing")
    digest = sha256(path)
    require(sidecar.read_text().strip() == digest, "registered W4 criteria SHA mismatch")
    criteria = json.loads(path.read_text())
    require(criteria.get("immutable") is True
            and criteria.get("registered_before_computation") is True
            and criteria.get("status") == "registered_not_run",
            "W4 criteria are not an immutable preregistration")
    label = state_label(criteria)
    require(path.name == f"w4_{label}_criteria.json", "W4 criteria filename/state label mismatch")
    allowed_kinds = {
        "v16": {"waterlily_w4_v16_grid_domain_sensitivity_criteria"},
        "v17": {"waterlily_w4_canonical_grid_domain_sensitivity_criteria"},
    }
    require(criteria.get("kind") in allowed_kinds.get(label, set()),
            "unexpected W4 criteria kind/state-label pairing")
    return criteria, digest


def validate_case_contract(criteria: dict) -> None:
    geometry, measurement = criteria["geometry"], criteria["measurement"]
    label = state_label(criteria)
    state = criteria.get("prerequisites", {}).get("canonical_state_identity")
    if not state and label == "v16":
        state = {
            "state_label": "v16",
            "state_sha256": geometry.get("canonical_state_sha256"),
            "state_npz_sha256": geometry.get("canonical_state_npz_sha256"),
            "phi_c_order_sha256": geometry.get("canonical_phi_c_order_sha256"),
            "phi_fortran_sha256": geometry.get("canonical_phi_fortran_sha256"),
            "point_shape": geometry.get("point_shape"),
            "cell_shape": geometry.get("cell_shape"),
            "design_lattice_spacing_m": geometry.get("design_lattice_spacing_m"),
            "canonical_sdf_origin_m": geometry.get("canonical_sdf_origin_m"),
            "source_surface_sha256": geometry.get("source_surface_sha256"),
        }
    require(label in {"v16", "v17"} and isinstance(state, dict)
            and geometry.get("state_label", "v16") == state.get("state_label")
            and geometry.get("canonical_state_sha256") == state.get("state_sha256")
            and geometry.get("canonical_state_npz_sha256") == state.get("state_npz_sha256")
            and geometry.get("canonical_phi_c_order_sha256") == state.get("phi_c_order_sha256")
            and geometry.get("canonical_phi_fortran_sha256") == state.get("phi_fortran_sha256")
            and geometry.get("point_shape") == state.get("point_shape")
            and geometry.get("cell_shape") == state.get("cell_shape")
            and geometry.get("canonical_sdf_origin_m") == state.get("canonical_sdf_origin_m")
            and geometry.get("design_lattice_spacing_m") == state.get("design_lattice_spacing_m")
            and geometry.get("source_surface_sha256") == state.get("source_surface_sha256")
            and geometry.get("point_shape") == [value + 1 for value in geometry.get("cell_shape", [])]
            and len(geometry.get("canonical_state_sha256", "")) == 64
            and len(geometry.get("canonical_state_npz_sha256", "")) == 64
            and len(geometry.get("canonical_phi_c_order_sha256", "")) == 64
            and len(geometry.get("canonical_phi_fortran_sha256", "")) == 64
            and len(geometry.get("source_surface_sha256", "")) == 64
            and isinstance(geometry.get("design_lattice_spacing_m"), (int, float))
            and geometry["design_lattice_spacing_m"] > 0
            and geometry.get("design_lattice_is_resampled") is False
            and geometry.get("flow_grid_is_separate_from_design_lattice") is True
            and geometry.get("baseline_flow_origin_m") == [-2.5, -1.2, -0.9]
            and geometry.get("baseline_physical_box_m") == [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]
            and geometry.get("reynolds") == 80.0
            and geometry.get("density_kg_m3") == 1.0
            and geometry.get("dynamic_viscosity_pa_s") == 0.01
            and geometry.get("freestream_mps") == [1.0, 0.0, 0.0]
            and geometry.get("reference_length_m") == 0.8
            and geometry.get("reference_area_m2") == 0.64,
            "W4 canonical physical/design-grid contract drift")
    require([case.get("case_id") for case in criteria["cases"]] == CASE_IDS,
            "W4 registered case inventory/order drift")
    for case in criteria["cases"]:
        n, dx, dims, viscosity, box = EXPECTED_CASES[case["case_id"]]
        require(case.get("factor") == ("domain_extent" if case["case_id"].startswith("domain_") else "flow_resolution")
                and case.get("cells_per_reference_length") == n
                and case.get("flow_dims") == dims and case.get("physical_box_m") == box
                and math.isclose(case.get("flow_spacing_m", math.nan), dx, rel_tol=0, abs_tol=1e-12)
                and case.get("solver_length") == float(n)
                and math.isclose(case.get("solver_time_unit_s", math.nan), dx, rel_tol=0, abs_tol=1e-12)
                and math.isclose(case.get("solver_viscosity", math.nan), viscosity, rel_tol=0, abs_tol=1e-12)
                and case.get("reynolds") == 80.0 and case.get("density_kg_m3") == 1.0
                and case.get("dynamic_viscosity_pa_s") == 0.01
                and case.get("freestream_mps") == [1.0, 0.0, 0.0]
                and case.get("reference_length_m") == 0.8
                and case.get("reference_area_m2") == 0.64,
                f"W4 registered case mapping/scale drift: {case.get('case_id')}")
    require(measurement.get("target_t_u_l") == 120.0
            and measurement.get("burn_in_t_u_l") == 80.0
            and measurement.get("force_window_t_u_l") == [80.0, 120.0]
            and measurement.get("force_sample_every_solver_steps") == 8
            and measurement.get("minimum_force_window_samples") >= 4
            and measurement.get("per_case_wall_time_limit_s") == 1800.0
            and measurement.get("aggregate_solver_wall_time_limit_s") == 5400.0
            and measurement.get("host_recompute_relative_tolerance") == 1e-9
            and measurement.get("force_component_relative_tolerance") == 1e-6
            and measurement.get("force_component_absolute_tolerance") == 1e-8
            and "exact [80,120] endpoints" in measurement.get("primary_force_metric", "")
            and "sample the first step at or beyond" in measurement.get("force_sample_policy", ""),
            "W4 measurement-window contract drift")
    stationarity = measurement.get("stationarity", {})
    w3_prereq = criteria.get("prerequisites", {}).get("w3_result_evidence", {})
    require(measurement.get("stationarity_gate") is True
            and stationarity.get("window_t_u_l") == [80.0, 120.0]
            and stationarity.get("half_windows_t_u_l") == [[80.0, 100.0], [100.0, 120.0]]
            and stationarity.get("relative_half_window_drift_max") == 0.02
            and stationarity.get("quantities") == ["drag", "downforce"]
            and stationarity.get("mean_definition") ==
                "trapezoidal physical-time-weighted means on exact endpoint-clipped intervals"
            and stationarity.get("formula") ==
                "abs(mean_first - mean_second) / max(abs(mean_whole), eps(Float64))"
            and stationarity.get("precedent_criteria_path") == w3_prereq.get("criteria_path")
            and stationarity.get("precedent_criteria_sha256") == w3_prereq.get("criteria_sha256"),
            "W4 registered stationarity contract drift")
    comparison = criteria.get("w3_flow16_comparison", {})
    require(criteria.get("prerequisites", {}).get("w3_baseline_reused") is False
            and criteria["prerequisites"].get("all_four_cases_reexecuted") is True
            and criteria["prerequisites"].get("w3_flow16_comparison_required") is True
            and criteria["prerequisites"].get("w3_flow16_numerical_repeatability_gate_registered") is False
            and comparison.get("numerical_repeatability_gate_registered") is False
            and comparison.get("required_fields") == [
                "drag_time_weighted_n", "downforce_time_weighted_n", "cd_time_weighted",
                "stationarity_relative_half_window_drift_drag",
                "stationarity_relative_half_window_drift_downforce", "steps", "t_u_l", "force_sign"]
            and "if drag force sign differs, stop matrix interpretation" in comparison.get("interpretation_rule", ""),
            "W4 W3-flow_16 comparison contract drift")
    backend = criteria["backend"]
    require(backend.get("accelerator") == "NvidiaTeslaT4"
            and backend.get("machine_shape") == "NvidiaTeslaT4"
            and backend.get("gpu_name") == "Tesla T4"
            and backend.get("gpu_count") == 2
            and backend.get("cuda_visible_devices") == "0"
            and backend.get("julia_threads") == 1
            and all(backend.get(key) for key in (
                "driver_version", "cuda_driver_api_version", "cuda_runtime_version",
                "cuda_jl_version", "compute_capability", "julia_version",
                "waterlily_version", "waterlily_backend"))
            and len(backend.get("julia_archive_sha256", "")) == 64,
            "W4 backend identity contract is incomplete or not a T4 cohort")
    require(criteria["profile_semantics"] == {
        "native_velocity_boundary": "v16_native_far_field_uBC: +x freestream velocity 1 m/s; other normal components zero",
        "side_top_tangential_boundary": "WaterLily native tangential zero-Neumann",
        "x_plus_boundary": "WaterLily convective exit",
        "pressure_boundary": "WaterLily projection pressure; no per-patch freestreamPressure input",
        "ground_model": "moving planar half-space on the expanded flow-domain bottom at world z=-0.9 m, with +x wall velocity 1 m/s",
        "force_integration_body": f"canonical {label} candidate GridSDF only; exclude auxiliary moving-ground half-space",
        "drag_projection": [1.0, 0.0, 0.0],
        "downforce_projection": [0.0, 0.0, -1.0],
        "source_profile_equivalent": False,
        "physical_profile_qualified": False,
    }, "W4 native WaterLily/ground/force semantics drift")
    if label == "v17":
        require(criteria.get("kernel_id") == "ramhachi888/cfd-opt-sdf-w4-v17-sensitivity",
                "W4-v17 preregistered kernel id mismatch")
        metadata_path = ROOT / criteria["inputs"]["kernel_metadata"]["path"]
        metadata = json.loads(metadata_path.read_text())
        require(metadata.get("id") == criteria["kernel_id"]
                and metadata.get("is_private") is True
                and criteria["input_dataset_id"] in metadata.get("dataset_sources", []),
                "W4-v17 Kaggle kernel package metadata mismatch")
    require(all(criteria["evidence_scope"].get(key) is False for key in (
        "physical_profile_equivalence_qualified", "absolute_downforce_qualified",
        "stationarity_qualified", "grid_or_domain_convergence_qualified",
        "gradient_qualified", "reverse_mode_qualified", "topology_qualified",
        "optimizer_qualified", "shape_update_allowed")),
        "W4 criteria improperly promote an out-of-scope claim")


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{path}"])


def verify_registered_source(criteria: dict) -> bool:
    require(criteria.get("source_commit") == criteria.get("registered_source_commit"),
            "W4 registered source commit fields disagree")
    for name, entry in criteria["inputs"].items():
        if entry.get("location") != "source_repo":
            continue
        blob = git_blob(criteria["source_commit"], entry["path"])
        require(hashlib.sha256(blob).hexdigest() == entry["sha256"],
                f"registered W4 source input changed in pinned commit: {name}")
        current = ROOT / entry["path"]
        require(current.is_file() and sha256(current) == entry["sha256"],
                f"checked-out W4 source input differs from preregistration: {name}")
    runner_path = ROOT / criteria["inputs"]["kernel_runner"]["path"]
    require(sha256(runner_path) == criteria["inputs"]["kernel_runner"]["sha256"],
            "registered W4 Kaggle runner changed")
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    pinned_sources = {entry.get("path"): entry.get("sha256")
                      for entry in criteria["inputs"].values()
                      if entry.get("location") == "source_repo"}
    require(pinned_sources.get(prereq["criteria_path"]) == prereq["criteria_sha256"]
            and pinned_sources.get(prereq["path"]) == prereq["sha256"],
            "W3 prerequisite files are not included in pinned W4 source inputs")
    w3_criteria_path = ROOT / prereq["criteria_path"]
    require(w3_criteria_path.is_file() and sha256(w3_criteria_path) == prereq["criteria_sha256"],
            "bound W3 criteria SHA mismatch")
    w3_criteria = json.loads(w3_criteria_path.read_text())
    require(w3_criteria.get("immutable") is True
            and w3_criteria.get("registered_before_computation") is True
            and w3_criteria.get("source_commit") == w3_criteria.get("registered_source_commit"),
            "bound W3 criteria are not immutable preregistration")
    result_path = ROOT / prereq["path"]
    require(result_path.is_file() and sha256(result_path) == prereq["sha256"],
            "bound W3 PASS evidence SHA mismatch")
    result = json.loads(result_path.read_text())
    require(result.get("verdict") == "PASS"
            and result.get("host_verification_passed") is True
            and result.get("criteria_sha256") == prereq["criteria_sha256"]
            and result.get("kernel_version") == prereq["kernel_version"]
            and result.get("source_commit") == w3_criteria["source_commit"]
            and result.get("backend_identity") == prereq["backend_identity"]
            and prereq["backend_identity"] == criteria["backend"],
            "W4 prerequisite is not the bound host-verified W3 PASS")
    w3_geometry = w3_criteria.get("geometry", {})
    expected_state = {
        "state_label": w3_geometry.get("state_label", "v16"),
        "state_sha256": w3_geometry.get("state_sha256"),
        "state_npz_sha256": w3_criteria.get("inputs", {}).get("canonical_state_npz", {}).get("sha256"),
        "phi_c_order_sha256": w3_geometry.get("phi_c_order_sha256"),
        "phi_fortran_sha256": w3_geometry.get("phi_fortran_sha256"),
        "point_shape": w3_geometry.get("point_shape"),
        "cell_shape": w3_geometry.get("cell_shape"),
        "design_lattice_spacing_m": w3_geometry.get("spacing_m"),
        "canonical_sdf_origin_m": w3_geometry.get("canonical_sdf_origin_m"),
        "source_surface_sha256": w3_geometry.get("source_surface_sha256"),
    }
    bound_state = criteria["prerequisites"].get("canonical_state_identity")
    require(bound_state == expected_state or (
        expected_state["state_label"] == "v16" and bound_state is None),
            "W4 canonical state identity is not derived from its bound W3 criteria")
    geometry = criteria["geometry"]
    require(geometry.get("state_label", "v16") == expected_state["state_label"]
            and geometry.get("canonical_state_sha256") == expected_state["state_sha256"]
            and geometry.get("canonical_state_npz_sha256") == expected_state["state_npz_sha256"]
            and geometry.get("canonical_phi_c_order_sha256") == expected_state["phi_c_order_sha256"]
            and geometry.get("canonical_phi_fortran_sha256") == expected_state["phi_fortran_sha256"]
            and geometry.get("point_shape") == expected_state["point_shape"]
            and geometry.get("cell_shape") == expected_state["cell_shape"]
            and geometry.get("design_lattice_spacing_m") == expected_state["design_lattice_spacing_m"]
            and geometry.get("canonical_sdf_origin_m") == expected_state["canonical_sdf_origin_m"]
            and geometry.get("source_surface_sha256") == expected_state["source_surface_sha256"],
            "W4 state criteria differ from the exact host-verified W3 state")
    return True


def zero_level_margin_m(phi: np.ndarray, spacing: float) -> float:
    solid = phi < 0.0
    require(bool(solid.any()), "canonical W4 phi has no negative solid nodes")
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing for n in phi.shape]
    face_gap = np.minimum(
        np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]),
        gaps[2][None, None, :],
    )
    return float(np.min(face_gap[solid] + phi[solid]))


def verify_staged_dataset_inventory(criteria: dict, dataset_dir: Path,
                                   expected_files: set[str], manifest_path: Path) -> None:
    metadata_path = dataset_dir / "dataset-metadata.json"
    require(metadata_path.is_file(), "staged W4 Kaggle dataset metadata is missing")
    metadata = json.loads(metadata_path.read_text())
    require(metadata.get("id") == criteria["input_dataset_id"],
            "staged W4 Kaggle dataset metadata id mismatch")
    actual_names = {path.name for path in dataset_dir.iterdir() if path.is_file()}
    allowed_names = expected_files | {manifest_path.name, metadata_path.name}
    require(actual_names == allowed_names,
            "staged W4 dataset contains unregistered files")


def verify_dataset(criteria: dict, criteria_sha: str, dataset_dir: Path) -> tuple[dict, float]:
    dataset_dir = Path(dataset_dir)
    names = dataset_names(criteria)
    criteria_path = dataset_dir / names["criteria"]
    sidecar_path = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    manifest_path = dataset_dir / names["manifest"]
    require(criteria_path.is_file() and sha256(criteria_path) == criteria_sha,
            "staged W4 criteria differs from local preregistration")
    require(sidecar_path.is_file() and sidecar_path.read_text().strip() == criteria_sha,
            "staged W4 criteria sidecar mismatch")
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get("dataset_id") == criteria["input_dataset_id"],
            "staged W4 dataset id mismatch")
    require(manifest.get("criteria_sha256") == criteria_sha,
            "staged W4 manifest criteria binding mismatch")
    expected = registered_dataset_files(criteria)
    expected.update({names["criteria"]: criteria_sha,
                     names["criteria"] + ".sha256": sha256(sidecar_path)})
    require(set(manifest.get("files", {})) == set(expected),
            "staged W4 dataset file inventory mismatch")
    verify_staged_dataset_inventory(criteria, dataset_dir, set(expected), manifest_path)
    for name, digest in expected.items():
        path = dataset_dir / name
        require(path.is_file() and sha256(path) == digest,
                f"staged W4 dataset file SHA mismatch: {name}")
        require(manifest["files"].get(name) == digest,
                f"staged W4 manifest hash mismatch: {name}")

    geometry = criteria["geometry"]
    state_entry = criteria["inputs"]["canonical_state_npz"]
    raw_entry = criteria["inputs"]["canonical_phi_fortran_raw"]
    state_path, raw_path = dataset_dir / state_entry["path"], dataset_dir / raw_entry["path"]
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    require(list(phi.shape) == geometry["point_shape"] and np.isfinite(phi).all(),
            "canonical W4 phi shape/finiteness mismatch")
    require(metadata.get("state_sha256") == geometry["canonical_state_sha256"]
            and metadata.get("source_sha256") == geometry["source_surface_sha256"]
            and metadata.get("shape") == geometry["point_shape"]
            and metadata.get("origin_m") == geometry["canonical_sdf_origin_m"]
            and metadata.get("spacing_m") == geometry["design_lattice_spacing_m"],
            "canonical W4 SDF metadata or lineage mismatch")
    phi_c = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    phi_f_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    phi_f = hashlib.sha256(phi_f_bytes).hexdigest()
    require(phi_c == geometry["canonical_phi_c_order_sha256"],
            "canonical W4 C-order phi hash mismatch")
    require(metadata.get("phi_sha256") == phi_c,
            "canonical W4 state metadata C-order phi binding mismatch")
    require(phi_f == geometry["canonical_phi_fortran_sha256"],
            "canonical W4 Fortran-order phi hash mismatch")
    require(raw_path.read_bytes() == phi_f_bytes, "canonical W4 raw phi/NPZ bytes differ")
    margin = zero_level_margin_m(phi, geometry["design_lattice_spacing_m"])
    require(margin >= geometry["phi_margin_gate_m"]
            and abs(margin - geometry["phi_expected_margin_m"])
            <= geometry["phi_margin_tolerance_m"],
            "canonical W4 CPU-side measured SDF margin mismatch")
    return metadata, margin


def historical_v16_w4_diagnostic(criteria: dict, metrics_by_case: dict,
                                summaries: dict) -> dict:
    """Compare this v17 matrix with the immutable, host-verified W4-v16 round 4."""
    inputs = criteria["inputs"]
    old_criteria_entry = inputs["historical_v16_w4_criteria"]
    old_criteria_sidecar_entry = inputs["historical_v16_w4_criteria_sidecar"]
    old_result_entry = inputs["historical_v16_w4_result"]
    old_result_sidecar_entry = inputs["historical_v16_w4_result_sidecar"]
    old_criteria_path = ROOT / old_criteria_entry["path"]
    old_criteria_sidecar = ROOT / old_criteria_sidecar_entry["path"]
    old_result_path = ROOT / old_result_entry["path"]
    old_result_sidecar = ROOT / old_result_sidecar_entry["path"]
    require(sha256(old_criteria_path) == old_criteria_entry["sha256"]
            and sha256(old_criteria_sidecar) == old_criteria_sidecar_entry["sha256"]
            and sha256(old_result_path) == old_result_entry["sha256"]
            and sha256(old_result_sidecar) == old_result_sidecar_entry["sha256"],
            "historical W4-v16 comparison evidence SHA mismatch")
    old_criteria_sha = sha256(old_criteria_path)
    require(old_criteria_sidecar.read_text().strip() == old_criteria_sha,
            "historical W4-v16 criteria sidecar mismatch")
    old_criteria = json.loads(old_criteria_path.read_text())
    old_result_sha = sha256(old_result_path)
    require(old_result_sidecar.read_text().strip() == old_result_sha,
            "historical W4-v16 result sidecar mismatch")
    old_result = json.loads(old_result_path.read_text())
    require(old_criteria.get("immutable") is True
            and old_criteria.get("registered_before_computation") is True
            and old_criteria.get("criteria_round") == 4
            and old_criteria.get("geometry", {}).get("state_label", "v16") == "v16"
            and old_criteria.get("geometry", {}).get("density_kg_m3") == 1.0
            and old_criteria.get("geometry", {}).get("freestream_mps") == [1.0, 0.0, 0.0]
            and [case.get("case_id") for case in old_criteria.get("cases", [])] == CASE_IDS
            and old_result.get("verdict") == "PASS"
            and old_result.get("host_verification_passed") is True
            and old_result.get("all_T0_T10_passed") is True
            and old_result.get("criteria_sha256") == old_criteria_sha,
            "historical W4-v16 reference is not the exact host-verified round-4 PASS")

    case_comparisons = {}
    quantities = (
        "total_drag_n", "total_downforce_n", "pressure_drag_n", "viscous_drag_n",
        "pressure_downforce_n", "viscous_downforce_n", "cd",
        "stationarity_drag", "stationarity_downforce", "wall_seconds", "peak_vram_bytes",
    )
    for case_id in CASE_IDS:
        old_case = old_result["case_measurements"][case_id]
        old_metrics = old_case["force_metrics_host_recomputed"]
        old_spacing = old_case["geometry"]["flow_spacing_m"]
        old_scale = old_spacing ** 2  # rho=1 kg/m3 and U=1 m/s in both registered matrices.
        old_values = {
            "total_drag_n": old_metrics["drag_time_weighted_n"],
            "total_downforce_n": old_metrics["downforce_time_weighted_n"],
            "pressure_drag_n": old_metrics["window_time_weighted_pressure_fx_solver"] * old_scale,
            "viscous_drag_n": old_metrics["window_time_weighted_viscous_fx_solver"] * old_scale,
            "pressure_downforce_n": -old_metrics["window_time_weighted_pressure_fz_solver"] * old_scale,
            "viscous_downforce_n": -old_metrics["window_time_weighted_viscous_fz_solver"] * old_scale,
            "cd": old_metrics["cd_time_weighted"],
            "stationarity_drag": old_case["stationarity"]["drag"],
            "stationarity_downforce": old_case["stationarity"]["downforce"],
            "wall_seconds": old_case["execution"]["wall_seconds"],
            "peak_vram_bytes": old_case["execution"]["peak_vram_bytes"],
        }
        new = metrics_by_case[case_id]
        current = {
            "total_drag_n": new["drag_time_weighted_n"],
            "total_downforce_n": new["downforce_time_weighted_n"],
            "pressure_drag_n": new["pressure_drag_time_weighted_n"],
            "viscous_drag_n": new["viscous_drag_time_weighted_n"],
            "pressure_downforce_n": new["pressure_downforce_time_weighted_n"],
            "viscous_downforce_n": new["viscous_downforce_time_weighted_n"],
            "cd": new["cd_time_weighted"],
            "stationarity_drag": new["stationarity_relative_half_window_drift_drag"],
            "stationarity_downforce": new["stationarity_relative_half_window_drift_downforce"],
            "wall_seconds": summaries[case_id]["wall_seconds"],
            "peak_vram_bytes": summaries[case_id]["peak_vram_bytes"],
        }
        case_comparisons[case_id] = {}
        for quantity in quantities:
            before, after = old_values[quantity], current[quantity]
            case_comparisons[case_id][quantity] = {
                "w4_v16_round4": before,
                "w4_v17": after,
                "delta_v17_minus_v16": None if after is None else after - before,
                "absolute_delta": None if after is None else abs(after - before),
                "relative_delta_percent": None if after is None or before == after == 0 else
                    (None if after is None else 100.0 * abs(after - before) /
                     max(abs(before), abs(after))),
            }
    return {
        "kind": "w4_v17_vs_v16_round4_cross_state_diagnostic",
        "diagnostic_only": True,
        "qualification_gate": False,
        "relative_delta_definition": (
            "100 * abs(v17 - v16) / max(abs(v16), abs(v17)); null only when both values are zero"),
        "interpretation": "The canonical SDF states differ; this cross-state comparison does not transfer v16 results or qualify physical-force accuracy or grid convergence.",
        "reference_criteria_path": old_criteria_entry["path"],
        "reference_criteria_sha256": old_criteria_sha,
        "reference_result_path": old_result_entry["path"],
        "reference_result_sha256": old_result_sha,
        "cases": case_comparisons,
    }


def registered_dataset_files(criteria: dict) -> dict[str, str]:
    return {
        entry["path"]: entry["sha256"]
        for entry in criteria["inputs"].values()
        if entry.get("location") == "kaggle_dataset"
    }


def read_force_rows(path: Path, measurement: dict) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == FORCE_COLUMNS, "W4 force CSV schema mismatch")
        rows = [{key: float(value) for key, value in row.items()} for row in reader]
    require(bool(rows) and all(math.isfinite(value) for row in rows for value in row.values()),
            "W4 force CSV is empty or contains non-finite values")
    require(all(right["step"] > left["step"] and right["t_u_l"] > left["t_u_l"]
                for left, right in zip(rows, rows[1:])),
            "W4 force CSV step/time order is invalid")
    stride = measurement["force_sample_every_solver_steps"]
    terminal_extra = rows[-1]["step"] % stride != 0
    regular_rows = rows[:-1] if terminal_extra else rows
    require(all(row["step"] % stride == 0 for row in regular_rows)
            and all(right["step"] - left["step"] == stride
                    for left, right in zip(regular_rows, regular_rows[1:]))
            and (not terminal_extra or (rows[-1]["t_u_l"] >= measurement["force_window_t_u_l"][1]
                 and 0 < rows[-1]["step"] - rows[-2]["step"] < stride)),
            "W4 force CSV sampling differs from the registered stride/terminal rule")
    return rows


def _time_weighted_mean(rows: list[dict[str, float]], key: str) -> float:
    integral = duration = 0.0
    for left, right in zip(rows, rows[1:]):
        dt = right["t_u_l"] - left["t_u_l"]
        integral += 0.5 * (left[key] + right[key]) * dt
        duration += dt
    require(duration > 0.0, "W4 force-window duration is not positive")
    return integral / duration


def _clipped_force_window(rows: list[dict[str, float]], start: float, end: float) -> list[dict[str, float]]:
    def boundary(t: float) -> dict[str, float]:
        right = next((index for index, row in enumerate(rows) if row["t_u_l"] >= t), None)
        require(right is not None, "W4 force samples do not reach the registered window endpoint")
        if rows[right]["t_u_l"] == t:
            return dict(rows[right])
        require(right > 0, "W4 force samples do not bracket the registered window start")
        before, after = rows[right - 1], rows[right]
        alpha = (t - before["t_u_l"]) / (after["t_u_l"] - before["t_u_l"])
        return {key: (t if key == "t_u_l" else before[key] + alpha * (after[key] - before[key]))
                for key in before}

    require(rows[0]["t_u_l"] <= start and rows[-1]["t_u_l"] >= end,
            "W4 raw force CSV does not bracket the registered [80,120] window")
    return [boundary(start), *[row for row in rows if start < row["t_u_l"] < end], boundary(end)]


def recompute_case_metrics(rows: list[dict[str, float]], case: dict,
                           measurement: dict) -> dict[str, float]:
    start, end = measurement["force_window_t_u_l"]
    window = [row for row in rows if start <= row["t_u_l"] <= end]
    middle = 0.5 * (start + end)
    first = [row for row in window if row["t_u_l"] < middle]
    second = [row for row in window if row["t_u_l"] >= middle]
    require(len(window) >= measurement["minimum_force_window_samples"] and first and second,
            "W4 registered force window is incomplete")
    weighted_window = _clipped_force_window(rows, start, end)
    first_weighted_window = _clipped_force_window(
        rows, *measurement["stationarity"]["half_windows_t_u_l"][0])
    second_weighted_window = _clipped_force_window(
        rows, *measurement["stationarity"]["half_windows_t_u_l"][1])
    component_columns = ["fx_solver", "fy_solver", "fz_solver", "drag_solver",
                         "downforce_solver", "pressure_fx_solver", "pressure_fy_solver",
                         "pressure_fz_solver", "viscous_fx_solver", "viscous_fy_solver",
                         "viscous_fz_solver"]
    result = {f"window_time_weighted_{key}": _time_weighted_mean(weighted_window, key)
              for key in component_columns}
    result.update({
        "window_samples": len(window),
        "window_mean_drag_solver": sum(row["drag_solver"] for row in window) / len(window),
        "window_mean_downforce_solver": sum(row["downforce_solver"] for row in window) / len(window),
        "diagnostic_first_half_mean_drag_solver": sum(row["drag_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_drag_solver": sum(row["drag_solver"] for row in second) / len(second),
        "diagnostic_first_half_mean_downforce_solver": sum(row["downforce_solver"] for row in first) / len(first),
        "diagnostic_second_half_mean_downforce_solver": sum(row["downforce_solver"] for row in second) / len(second),
    })
    for quantity, key in (("drag", "drag_solver"), ("downforce", "downforce_solver")):
        first_mean = _time_weighted_mean(first_weighted_window, key)
        second_mean = _time_weighted_mean(second_weighted_window, key)
        whole_mean = result[f"window_time_weighted_{key}"]
        result[f"stationarity_first_half_time_weighted_{quantity}_solver"] = first_mean
        result[f"stationarity_second_half_time_weighted_{quantity}_solver"] = second_mean
        result[f"stationarity_relative_half_window_drift_{quantity}"] = (
            abs(first_mean - second_mean) / max(abs(whole_mean), sys.float_info.epsilon))
    scale = case["density_kg_m3"] * case["freestream_mps"][0] ** 2 * case["flow_spacing_m"] ** 2
    result["drag_time_weighted_n"] = result["window_time_weighted_drag_solver"] * scale
    result["downforce_time_weighted_n"] = result["window_time_weighted_downforce_solver"] * scale
    result["pressure_drag_time_weighted_n"] = result["window_time_weighted_pressure_fx_solver"] * scale
    result["viscous_drag_time_weighted_n"] = result["window_time_weighted_viscous_fx_solver"] * scale
    result["pressure_downforce_time_weighted_n"] = -result["window_time_weighted_pressure_fz_solver"] * scale
    result["viscous_downforce_time_weighted_n"] = -result["window_time_weighted_viscous_fz_solver"] * scale
    area_solver = case["reference_area_m2"] / case["flow_spacing_m"] ** 2
    result["cd_time_weighted"] = result["window_time_weighted_drag_solver"] / (
        0.5 * area_solver * case["freestream_mps"][0] ** 2)
    return result


def force_components_close(rows: list[dict[str, float]], measurement: dict) -> bool:
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


def metrics_match(summary: dict, metrics: dict, tolerance: float) -> bool:
    return all(math.isclose(summary.get(key, math.nan), value,
                            rel_tol=tolerance, abs_tol=1e-10)
               for key, value in metrics.items())


def relative_delta(a: float, b: float) -> float | None:
    return None if a == b == 0 else abs(a - b) / max(abs(a), abs(b))


def response_analysis(metrics_by_case: dict) -> dict:
    result = {}
    pairs = {
        "flow16_to_flow24": ("flow_16", "flow_24"),
        "flow24_to_flow32": ("flow_24", "flow_32"),
        "flow16_to_extended_domain16": ("flow_16", "domain_xplus1m_16"),
    }
    quantities = (
        "drag_time_weighted_n", "downforce_time_weighted_n",
        "pressure_drag_time_weighted_n", "viscous_drag_time_weighted_n",
        "pressure_downforce_time_weighted_n", "viscous_downforce_time_weighted_n",
    )
    detailed = {}
    for quantity in quantities:
        detailed[quantity] = {}
        for comparison, (left_case, right_case) in pairs.items():
            left, right = metrics_by_case[left_case][quantity], metrics_by_case[right_case][quantity]
            detailed[quantity][comparison] = {
                "from_case": left_case,
                "to_case": right_case,
                "from_n": left,
                "to_n": right,
                "delta_to_minus_from_n": right - left,
                "absolute_delta_n": abs(right - left),
                "relative_delta_percent": None if left == right == 0 else
                    100.0 * abs(right - left) / max(abs(left), abs(right)),
            }
    result["force_component_deltas"] = detailed
    result["relative_delta_definition"] = (
        "100 * abs(to - from) / max(abs(from), abs(to)); null only when both values are zero")
    for quantity in ("drag_time_weighted_n", "downforce_time_weighted_n"):
        r24, r32 = metrics_by_case["flow_24"][quantity], metrics_by_case["flow_32"][quantity]
        d16, d_ext = metrics_by_case["flow_16"][quantity], metrics_by_case["domain_xplus1m_16"][quantity]
        resolution, domain = abs(r24 - r32), abs(d16 - d_ext)
        result[quantity] = {
            "flow16_to_flow24_delta_abs_n": detailed[quantity]["flow16_to_flow24"]["absolute_delta_n"],
            "flow16_to_flow24_delta_relative_percent": detailed[quantity]["flow16_to_flow24"]["relative_delta_percent"],
            "resolution_delta_abs_n": resolution,
            "resolution_delta_relative": relative_delta(r24, r32),
            "resolution_delta_relative_percent": detailed[quantity]["flow24_to_flow32"]["relative_delta_percent"],
            "domain_delta_abs_n": domain,
            "domain_delta_relative": relative_delta(d16, d_ext),
            "domain_delta_relative_percent": detailed[quantity]["flow16_to_extended_domain16"]["relative_delta_percent"],
            "extended_domain_fine_grid_required": domain >= resolution,
        }
    result["any_force_component_requires_extended_domain_fine_grid"] = any(
        result[key]["extended_domain_fine_grid_required"]
        for key in ("drag_time_weighted_n", "downforce_time_weighted_n")
    )
    return result


def w3_flow16_comparison(w3_result: dict, metrics: dict, summary: dict,
                         canonical_label: str = "v16") -> dict:
    previous = w3_result["raw_measurements"]
    previous_label = "w3_round4" if canonical_label == "v16" else f"w3_{canonical_label}"

    def compare(w3_value: float, w4_value: float) -> dict:
        return {
            previous_label: w3_value,
            "w4_flow_16": w4_value,
            "delta_w4_minus_w3": w4_value - w3_value,
            "absolute_delta": abs(w4_value - w3_value),
            "relative_delta": (None if w3_value == w4_value == 0 else
                               abs(w4_value - w3_value) / max(abs(w3_value), abs(w4_value))),
        }

    drag_sign_w3 = 0 if previous["drag_time_weighted_n"] == 0 else math.copysign(1, previous["drag_time_weighted_n"])
    drag_sign_w4 = 0 if metrics["drag_time_weighted_n"] == 0 else math.copysign(1, metrics["drag_time_weighted_n"])
    return {
        "numerical_repeatability_gate_registered": False,
        "force_sign_consistent": drag_sign_w3 == drag_sign_w4,
        "force_sign": {previous_label: drag_sign_w3, "w4_flow_16": drag_sign_w4},
        "drag_time_weighted_n": compare(previous["drag_time_weighted_n"], metrics["drag_time_weighted_n"]),
        "downforce_time_weighted_n": compare(previous["downforce_time_weighted_n"], metrics["downforce_time_weighted_n"]),
        "cd_time_weighted": compare(previous["cd_time_weighted"], metrics["cd_time_weighted"]),
        "stationarity_relative_half_window_drift_drag": compare(
            previous["stationarity_relative_half_window_drift_drag"],
            metrics["stationarity_relative_half_window_drift_drag"]),
        "stationarity_relative_half_window_drift_downforce": compare(
            previous["stationarity_relative_half_window_drift_downforce"],
            metrics["stationarity_relative_half_window_drift_downforce"]),
        "steps": {previous_label: previous["steps"], "w4_flow_16": summary["steps"]},
        "t_u_l": {previous_label: previous["t_end_reached"], "w4_flow_16": summary["t_end_reached"]},
        "force_projection_semantics": "drag=+Fx; downforce=-Fz",
        "interpretation_rule": f"report all W3 {canonical_label} to W4 flow_16 deltas; if drag force sign differs, stop matrix interpretation and diagnose before FD",
        "interpretation_if_force_sign_differs": "stop matrix interpretation and diagnose before FD",
    }


def recompute_gates(criteria: dict, summaries: dict, metrics: dict, rows: dict,
                    margin: float, gpu_rows: list[str], smoke: str,
                    fingerprint: dict) -> dict:
    geometry, measurement, backend = criteria["geometry"], criteria["measurement"], criteria["backend"]
    profile = criteria["profile_semantics"]
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    label = state_label(criteria)
    cases = {case["case_id"]: case for case in criteria["cases"]}
    gates = {
        "T0_registered_inputs_and_w3_pass": prereq.get("host_verified") is True,
        "T1_registered_case_matrix_complete": list(cases) == CASE_IDS and set(summaries) == set(CASE_IDS)
            and set(metrics) == set(CASE_IDS) and set(rows) == set(CASE_IDS),
        "T2_canonical_phi_and_margin_identity": margin >= geometry["phi_margin_gate_m"]
            and all(s.get("canonical_state_label", "v16") == label
                and s.get("state_sha256") == geometry["canonical_state_sha256"]
                and (label == "v16" or s.get("state_npz_sha256") == geometry["canonical_state_npz_sha256"])
                and s.get("source_surface_sha256") == geometry["source_surface_sha256"]
                and s.get("phi_c_order_sha256") == geometry["canonical_phi_c_order_sha256"]
                and s.get("phi_fortran_sha256") == geometry["canonical_phi_fortran_sha256"]
                and (label == "v16" or s.get("canonical_design_point_shape") == geometry["point_shape"])
                and (label == "v16" or s.get("canonical_design_cell_shape") == geometry["cell_shape"])
                and s.get("device_roundtrip_sha256") == geometry["canonical_phi_fortran_sha256"]
                and s.get("phi_margin_gate_m") == geometry["phi_margin_gate_m"]
                and math.isclose(s.get("phi_margin_m", math.nan), margin, rel_tol=0,
                                 abs_tol=geometry["phi_margin_tolerance_m"])
                for s in summaries.values()),
        "T3_case_mapping_and_reynolds": all(
            s.get("case_id") == cid and s.get("flow_dims") == case["flow_dims"]
            and s.get("flow_origin_m") == geometry["baseline_flow_origin_m"]
            and s.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
            and s.get("canonical_state_label", "v16") == label
            and (label == "v16" or s.get("canonical_design_point_shape") == geometry["point_shape"])
            and (label == "v16" or s.get("canonical_design_cell_shape") == geometry["cell_shape"])
            and s.get("physical_box_max_m") == [axis[1] for axis in case["physical_box_m"]]
            and math.isclose(s.get("flow_spacing_m", math.nan), case["flow_spacing_m"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("solver_length", math.nan), case["solver_length"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("solver_time_unit_s", math.nan), case["solver_time_unit_s"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("solver_viscosity", math.nan), case["solver_viscosity"], rel_tol=0, abs_tol=1e-7)
            and math.isclose(s.get("reynolds", math.nan), geometry["reynolds"], rel_tol=0, abs_tol=1e-10)
            and math.isclose(s.get("density_kg_m3", math.nan), case["density_kg_m3"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("dynamic_viscosity_pa_s", math.nan), case["dynamic_viscosity_pa_s"], rel_tol=0, abs_tol=1e-12)
            and s.get("freestream_mps") == case["freestream_mps"]
            and math.isclose(s.get("reference_length_m", math.nan), case["reference_length_m"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("reference_area_m2", math.nan), case["reference_area_m2"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(s.get("canonical_design_spacing_m", math.nan), geometry["design_lattice_spacing_m"], rel_tol=0, abs_tol=1e-12)
            for cid, case in cases.items() for s in [summaries.get(cid, {})]),
        "T4_native_profile_limitation_preserved": all(
            s.get("source_profile_equivalent") is False and s.get("physical_profile_qualified") is False
            and s.get("native_velocity_boundary") == profile["native_velocity_boundary"]
            and s.get("side_top_tangential_boundary") == profile["side_top_tangential_boundary"]
            and s.get("x_max_boundary") == profile["x_plus_boundary"]
            and s.get("pressure_boundary") == profile["pressure_boundary"]
            and s.get("ground_model") == profile["ground_model"]
            and s.get("force_integration_body") == profile["force_integration_body"]
            and s.get("force_projection_semantics") == "drag=+Fx; downforce=-Fz"
            for s in summaries.values()),
        "T5_T4_Julia_CUDA_WaterLily_identity": len(gpu_rows) == backend["gpu_count"]
            and all(backend["gpu_name"] in row and row.split(", ")[-1] == backend["driver_version"]
                    for row in gpu_rows)
            and all(s.get("gpu_uuid") == gpu_rows[0].split(", ")[2]
                    and s.get("gpu_name") == backend["gpu_name"]
                    and s.get("julia_version") == backend["julia_version"]
                    and s.get("julia_threads") == backend["julia_threads"]
                    and s.get("cuda_jl_version") == backend["cuda_jl_version"]
                    and s.get("waterlily_version") == backend["waterlily_version"]
                    and s.get("waterlily_backend") == backend["waterlily_backend"]
                    for s in summaries.values())
            and all(marker in smoke for marker in (
                "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
                f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
                f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
                f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
                f"JULIA_VERSION {backend['julia_version']}",
                f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
                f"WATERLILY_VERSION {backend['waterlily_version']}",
                f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP")),
        "T6_primal_completion_and_force_integrity": all(
            s.get("t_end_target") == measurement["target_t_u_l"]
            and s.get("t_end_reached", 0) >= measurement["target_t_u_l"]
            and s.get("steps", 0) > 0 and s.get("finite_u") is True
            and s.get("finite_p") is True and s.get("finite_forces") is True
            and s.get("force_samples") == len(rows.get(cid, []))
            and force_components_close(rows.get(cid, []), measurement)
            for cid, s in summaries.items()),
        "T7_host_force_recomputation": all(
            metrics_match(summaries[cid], metrics[cid], measurement["host_recompute_relative_tolerance"])
            for cid in summaries),
        "T8_runtime_and_vram": all(
            0 < s.get("wall_seconds", 0) <= measurement["per_case_wall_time_limit_s"]
            and 0 < s.get("peak_vram_bytes", 0) < s.get("vram_total_bytes", 0)
            for s in summaries.values())
            and sum(s.get("wall_seconds", 0) for s in summaries.values())
            <= measurement["aggregate_solver_wall_time_limit_s"],
        "T9_exact_source_and_runner_identity": fingerprint.get("source_commit") == criteria["source_commit"]
            and fingerprint.get("runner_sha256") == criteria["inputs"]["kernel_runner"]["sha256"]
            and len(fingerprint.get("criteria_sha256", "")) == 64
            and fingerprint.get("w3_result_evidence_sha256") == prereq["sha256"],
        "T10_stationarity": all(
            math.isfinite(metrics[case_id].get(f"stationarity_relative_half_window_drift_{quantity}", math.nan))
            and metrics[case_id][f"stationarity_relative_half_window_drift_{quantity}"]
            <= measurement["stationarity"]["relative_half_window_drift_max"]
            for case_id in CASE_IDS
            for quantity in measurement["stationarity"]["quantities"]
        ),
    }
    return gates


def verify(download: Path, *, criteria_path: Path = CRITERIA,
           dataset_dir: Path = DATASET_DIR, kernel_version: int | None = None,
           kernel_id: str | None = None, dataset_version: int | None = None,
           remote_inventory_path: Path | None = None,
           remote_inventory_sha256: str | None = None,
           terminal_status: str | None = None,
           terminal_log_path: Path | None = None,
           terminal_log_sha256: str | None = None) -> dict:
    criteria, criteria_sha = load_criteria(criteria_path)
    names = dataset_names(criteria)
    label = state_label(criteria)
    validate_case_contract(criteria)
    verify_registered_source(criteria)
    metadata, margin = verify_dataset(criteria, criteria_sha, dataset_dir)
    terminal_log_sha = terminal_log_sha256
    remote_inventory_sha = remote_inventory_sha256
    remote_inventory = None
    if label == "v17":
        require(isinstance(kernel_version, int) and kernel_version >= 1,
                "exact completed Kaggle kernel version is required")
        require(isinstance(kernel_id, str) and kernel_id == criteria.get("kernel_id"),
                "Kaggle kernel id differs from the preregistered kernel")
        require(isinstance(dataset_version, int) and dataset_version >= 1,
                "exact Kaggle dataset version is required")
        require(terminal_status == "KernelWorkerStatus.COMPLETE",
                "the preregistered Kaggle kernel version is not terminal COMPLETE")
        require(terminal_log_path is not None and Path(terminal_log_path).is_file(),
                "terminal Kaggle status response is required")
        terminal_log_path = Path(terminal_log_path)
        terminal_log_sha = sha256(terminal_log_path)
        require(terminal_log_path.read_text(errors="replace").strip() == terminal_status,
                "terminal Kaggle status log does not match COMPLETE status")
        require(remote_inventory_path is not None and Path(remote_inventory_path).is_file(),
                "downloaded remote Kaggle dataset inventory is required")
        remote_inventory = json.loads(Path(remote_inventory_path).read_text())
        require(isinstance(remote_inventory, dict)
                and all(isinstance(name, str) and Path(name).name == name
                        and isinstance(digest, str) and len(digest) == 64
                        for name, digest in remote_inventory.items()),
                "remote Kaggle dataset inventory schema is invalid")
        expected_remote = registered_dataset_files(criteria)
        expected_remote[names["criteria"]] = criteria_sha
        expected_remote[names["criteria"] + ".sha256"] = sha256(
            Path(dataset_dir) / (names["criteria"] + ".sha256"))
        expected_remote[names["manifest"]] = sha256(Path(dataset_dir) / names["manifest"])
        require(remote_inventory == expected_remote,
                "downloaded remote Kaggle dataset files differ from the registered input inventory")
        remote_inventory_sha = remote_inventory_sha256(remote_inventory)
    else:
        expected_kernel_id = criteria.get("kernel_id", "ramhachi888/cfd-opt-sdf-w4-v16-sensitivity")
        require(kernel_id in (None, expected_kernel_id),
                "Kaggle kernel id differs from the historical v16 registration")
        if terminal_log_path is not None:
            terminal_log_sha = sha256(Path(terminal_log_path))
    output_name = names["output"]
    folder = download / output_name if (download / output_name).is_dir() else download
    file_count, output_manifest_sha = verify_output_files(folder)
    outcome = json.loads((folder / "outcome.json").read_text())
    fingerprint = json.loads((folder / "fingerprint.json").read_text())
    require(outcome.get("criteria_sha256") == criteria_sha
            and fingerprint.get("criteria_sha256") == criteria_sha,
            "W4 output is bound to a different criteria file")
    require(outcome.get("source_commit") == criteria["source_commit"]
            and fingerprint.get("source_commit") == criteria["source_commit"],
            "W4 output source commit mismatch")
    runner_path = ROOT / criteria["inputs"]["kernel_runner"]["path"]
    require(fingerprint.get("runner_sha256") == criteria["inputs"]["kernel_runner"]["sha256"]
            and sha256(runner_path) == fingerprint.get("runner_sha256"),
            "W4 output runner identity mismatch")
    require(fingerprint.get("dataset_id") == criteria["input_dataset_id"]
            and outcome.get("dataset_id") == criteria["input_dataset_id"],
            "W4 output dataset identity mismatch")
    expected_source_hashes = {
        name: entry["sha256"] for name, entry in criteria["inputs"].items()
        if entry.get("location") == "source_repo"
    }
    require(fingerprint.get("source_input_sha256") == expected_source_hashes
            and fingerprint.get("julia_archive_sha256") == criteria["backend"]["julia_archive_sha256"],
            "W4 output source-input or Julia archive fingerprint mismatch")
    manifest_path = dataset_dir / names["manifest"]
    require(fingerprint.get("dataset_manifest_sha256") == sha256(manifest_path)
            and (folder / "input_dataset_manifest.json").read_bytes()
            == manifest_path.read_bytes(),
            "W4 run input manifest differs from registered dataset")
    require(fingerprint.get("state_npz_sha256") == criteria["inputs"]["canonical_state_npz"]["sha256"]
            and json.loads((folder / "input_state_metadata.json").read_text()) == metadata,
            "W4 run canonical state identity mismatch")
    require((folder / "input_criteria.json").read_bytes() == criteria_path.read_bytes()
            and (folder / "input_criteria.json.sha256").read_text().strip() == criteria_sha,
            "W4 run criteria copy mismatch")
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    require(fingerprint.get("w3_result_evidence_sha256") == prereq["sha256"]
            and outcome.get("w3_result_evidence_sha256") == prereq["sha256"],
            "W4 output does not bind the preregistered W3 PASS evidence")

    summaries, metrics_by_case, rows_by_case = {}, {}, {}
    measurement = criteria["measurement"]
    for case in criteria["cases"]:
        case_id = case["case_id"]
        summary_path = folder / f"{case_id}.summary.json"
        force_path = folder / f"{case_id}.forces.csv"
        require(summary_path.is_file() and force_path.is_file(),
                f"W4 case files missing: {case_id}")
        summary = json.loads(summary_path.read_text())
        require(sha256(force_path) == summary.get("force_csv_sha256"),
                f"W4 force CSV hash mismatch: {case_id}")
        rows = read_force_rows(force_path, measurement)
        metrics = recompute_case_metrics(rows, case, measurement)
        summaries[case_id], rows_by_case[case_id], metrics_by_case[case_id] = summary, rows, metrics
    require(outcome.get("summaries") == summaries, "W4 outcome/summary copies disagree")
    require(outcome.get("host_recomputed_metrics") == metrics_by_case,
            "W4 runner-reported metrics differ from host recomputation")
    response = response_analysis(metrics_by_case)
    require(outcome.get("response_analysis") == response,
            "W4 runner response analysis differs from host recomputation")
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    w3_result = json.loads((ROOT / prereq["path"]).read_text())
    baseline_comparison = w3_flow16_comparison(
        w3_result, metrics_by_case["flow_16"], summaries["flow_16"], label)
    require(outcome.get("w3_flow16_comparison") == baseline_comparison,
            "W4 runner W3/flow_16 comparison differs from host recomputation")
    require(outcome.get("matrix_interpretation_allowed") is baseline_comparison["force_sign_consistent"],
            "W4 runner baseline interpretation flag differs from host recomputation")

    gpu_rows = [row for row in csv.reader((folder / "nvidia_smi.csv").open(newline="")) if row]
    gpu_rows = [", ".join(cell.strip() for cell in row) for row in gpu_rows]
    require(bool(gpu_rows) and fingerprint.get("gpu_inventory") == gpu_rows
            and fingerprint.get("selected_gpu_uuid") == gpu_rows[0].split(", ")[2],
            "W4 fingerprint GPU inventory/selection mismatch")
    smoke = (folder / "julia_smoke.log").read_text()
    gates = recompute_gates(criteria, summaries, metrics_by_case, rows_by_case,
                            margin, gpu_rows, smoke, fingerprint)
    require(outcome.get("gates") == gates, "W4 runner gates disagree with host recomputation")
    require(all(gates.values()), f"W4 registered integrity gates failed: {gates}")
    require(outcome.get("matrix_execution_complete") is True,
            "W4 outcome does not declare a complete matrix")
    require(outcome.get("w4_sensitivity_matrix_passed") is True,
            "W4 outcome does not declare the registered sensitivity matrix PASS")
    if label == "v17" or "fd05_execution_authorized" in outcome:
        require(outcome.get("fd05_execution_authorized") is False,
                "W4 output must not authorize FD-05 execution")
    for flag in ("physical_profile_equivalence_qualified", "absolute_downforce_qualified",
                 "stationarity_qualified", "grid_or_domain_convergence_qualified",
                 "gradient_qualified", "reverse_mode_qualified", "topology_qualified",
                 "optimizer_qualified", "shape_update_allowed"):
        require(outcome.get(flag) is False, f"W4 improperly promoted {flag}")
    state = json.loads((folder / "execution_state.json").read_text())
    case_ids = [case["case_id"] for case in criteria["cases"]]
    require(state.get("stage") == "matrix_complete"
            and state.get("canonical_state_label") == label
            and state.get("solver_step_invoked") == case_ids
            and state.get("solver_step_returned") == case_ids,
            "W4 solver progress markers do not establish all four case completions")
    if not baseline_comparison["force_sign_consistent"]:
        fd_entry_gate = "BLOCKED: W3 flow_16 drag sign disagreement; diagnose before interpretation"
    elif response["any_force_component_requires_extended_domain_fine_grid"]:
        fd_entry_gate = "BLOCKED: preregister extended-domain fine-grid interaction case"
    else:
        fd_entry_gate = "OPEN"
    case_measurements = {}
    for case_id, summary in summaries.items():
        metrics = metrics_by_case[case_id]
        case_measurements[case_id] = {
            "total_drag_n": metrics["drag_time_weighted_n"],
            "total_downforce_n": metrics["downforce_time_weighted_n"],
            "pressure_drag_n": metrics["pressure_drag_time_weighted_n"],
            "viscous_drag_n": metrics["viscous_drag_time_weighted_n"],
            "pressure_downforce_n": metrics["pressure_downforce_time_weighted_n"],
            "viscous_downforce_n": metrics["viscous_downforce_time_weighted_n"],
            "cd": metrics["cd_time_weighted"],
            "stationarity_drag": metrics["stationarity_relative_half_window_drift_drag"],
            "stationarity_downforce": metrics["stationarity_relative_half_window_drift_downforce"],
            "wall_seconds": summary["wall_seconds"],
            "peak_vram_bytes": summary["peak_vram_bytes"],
            "vram_total_bytes": summary["vram_total_bytes"],
        }
    v16_comparison = (historical_v16_w4_diagnostic(criteria, metrics_by_case, summaries)
                      if label == "v17" else None)
    state_identity = criteria.get("prerequisites", {}).get("canonical_state_identity")
    if state_identity is None and label == "v16":
        geometry = criteria["geometry"]
        state_identity = {
            "state_label": "v16",
            "state_sha256": geometry["canonical_state_sha256"],
            "state_npz_sha256": geometry["canonical_state_npz_sha256"],
            "phi_c_order_sha256": geometry["canonical_phi_c_order_sha256"],
            "phi_fortran_sha256": geometry["canonical_phi_fortran_sha256"],
            "point_shape": geometry["point_shape"],
            "cell_shape": geometry["cell_shape"],
            "design_lattice_spacing_m": geometry["design_lattice_spacing_m"],
            "canonical_sdf_origin_m": geometry["canonical_sdf_origin_m"],
            "source_surface_sha256": geometry["source_surface_sha256"],
        }
    return {
        "kind": f"kaggle_w4_{label}_sensitivity_result",
        "verdict": "PASS",
        "host_verification_passed": True,
        "all_T0_T10_passed": all(gates.values()),
        "canonical_state_label": label,
        "criteria_path": Path(criteria_path).resolve().relative_to(ROOT).as_posix(),
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "registered_source_commit": criteria["registered_source_commit"],
        "state_identity": state_identity,
        "kernel_version": kernel_version,
        "kernel_id": kernel_id,
        "dataset_version": dataset_version,
        "dataset_inventory_sha256": remote_inventory_sha,
        "dataset_inventory_files": remote_inventory,
        "terminal_status": terminal_status,
        "terminal_log_sha256": terminal_log_sha,
        "dataset_id": criteria["input_dataset_id"],
        "selected_gpu_uuid": fingerprint.get("selected_gpu_uuid"),
        "backend_identity": criteria["backend"],
        "verified_files": file_count,
        "output_manifest_sha256": output_manifest_sha,
        "dataset_manifest_sha256": sha256(manifest_path),
        "cpu_measured_sdf_margin_m": margin,
        "force_metrics": metrics_by_case,
        "case_measurements": case_measurements,
        "response_analysis": response,
        "v16_w4_diagnostic_comparison": v16_comparison,
        "w3_flow16_comparison": baseline_comparison,
        "matrix_interpretation_allowed": baseline_comparison["force_sign_consistent"],
        "w4_sensitivity_matrix_passed": True,
        "fd05_execution_authorized": False,
        "fd_entry_gate": fd_entry_gate,
        "gates": gates,
        "qualification_flags": {
            "physical_profile_qualified": False,
            "absolute_downforce_qualified": False,
            "stationarity_qualified": False,
            "grid_or_domain_convergence_qualified": False,
            "sdf_gradient_qualified": False,
            "reverse_mode_qualified": False,
            "optimizer_qualified": False,
            "topology_birth_qualified": False,
            "shape_update_allowed": False,
        },
        "claim_scope": criteria["evidence_scope"]["claim_scope"],
        "evidence_scope": criteria["evidence_scope"],
    }


def fail_closed_diagnostic(args, error: Exception) -> dict:
    criteria_path = Path(args.criteria)
    criteria = {}
    criteria_sha = None
    if criteria_path.is_file():
        criteria_sha = sha256(criteria_path)
        try:
            criteria = json.loads(criteria_path.read_text())
        except (OSError, json.JSONDecodeError):
            criteria = {}
    remote_files = None
    remote_sha = None
    if args.remote_inventory and Path(args.remote_inventory).is_file():
        try:
            remote_files = json.loads(Path(args.remote_inventory).read_text())
            if isinstance(remote_files, dict):
                remote_sha = remote_inventory_sha256(remote_files)
        except (OSError, json.JSONDecodeError):
            remote_files = None
    terminal_log_sha = (sha256(args.terminal_log)
                        if args.terminal_log and Path(args.terminal_log).is_file() else None)
    output_root = Path(args.download)
    output_files = ({str(path.relative_to(output_root)): sha256(path)
                     for path in sorted(output_root.rglob("*")) if path.is_file()}
                    if output_root.is_dir() else {})
    runner_outcome = None
    for outcome_path in output_root.rglob("outcome.json") if output_root.is_dir() else ():
        try:
            runner_outcome = json.loads(outcome_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
        break
    return {
        "kind": "kaggle_w4_v17_host_verification_diagnostic",
        "verdict": "FAIL_CLOSED",
        "host_verification_passed": False,
        "all_T0_T10_passed": False,
        "canonical_state_label": criteria.get("geometry", {}).get("state_label"),
        "criteria_path": (criteria_path.resolve().relative_to(ROOT).as_posix()
                          if criteria_path.is_relative_to(ROOT) else str(criteria_path)),
        "criteria_sha256": criteria_sha,
        "source_commit": criteria.get("source_commit"),
        "kernel_id": args.kernel_id,
        "kernel_version": args.kernel_version,
        "dataset_id": criteria.get("input_dataset_id"),
        "dataset_version": args.dataset_version,
        "dataset_inventory_sha256": remote_sha,
        "dataset_inventory_files": remote_files,
        "terminal_status": args.terminal_status,
        "terminal_log_sha256": terminal_log_sha,
        "downloaded_output_files": output_files,
        "runner_reported_gates_diagnostic_only": (runner_outcome or {}).get("gates"),
        "failure": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
        "gates": {"host_verification_completed": False,
                  "registered_T0_T10_independently_verified": False},
        "fd05_execution_authorized": False,
        "qualification_flags": {
            "physical_profile_qualified": False,
            "absolute_downforce_qualified": False,
            "stationarity_qualified": False,
            "grid_or_domain_convergence_qualified": False,
            "sdf_gradient_qualified": False,
            "reverse_mode_qualified": False,
            "optimizer_qualified": False,
            "topology_birth_qualified": False,
            "shape_update_allowed": False,
        },
        "claim_scope": "No W4 PASS or qualification claim is established by this fail-closed diagnostic.",
    }


def write_append_only_evidence(output: Path, result: dict) -> str:
    output = Path(output)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    require(not output.exists() and not sidecar.exists(),
            "append-only W4 evidence path already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(rendered)
    sidecar.write_text(sha256(output) + "\n")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path, help="version-specific Kaggle output directory")
    parser.add_argument("--criteria", type=Path, default=CRITERIA)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--kernel-version", type=int)
    parser.add_argument("--kernel-id")
    parser.add_argument("--dataset-version", type=int)
    parser.add_argument("--remote-inventory", type=Path)
    parser.add_argument("--remote-inventory-sha256")
    parser.add_argument("--terminal-status")
    parser.add_argument("--terminal-log", type=Path)
    parser.add_argument("--terminal-log-sha256")
    parser.add_argument("--output-evidence", type=Path)
    parser.add_argument("--failure-evidence", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.download, criteria_path=args.criteria,
                        dataset_dir=args.dataset_dir,
                        kernel_version=args.kernel_version,
                        kernel_id=args.kernel_id,
                        dataset_version=args.dataset_version,
                        remote_inventory_path=args.remote_inventory,
                        remote_inventory_sha256=args.remote_inventory_sha256,
                        terminal_status=args.terminal_status,
                        terminal_log_path=args.terminal_log,
                        terminal_log_sha256=args.terminal_log_sha256)
    except Exception as error:
        if not (args.failure_evidence or args.output_evidence):
            raise
        rendered = write_append_only_evidence(
            args.failure_evidence or args.output_evidence,
            fail_closed_diagnostic(args, error))
        print(rendered, end="")
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output_evidence:
        rendered = write_append_only_evidence(args.output_evidence, result)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
