#!/usr/bin/env python3
"""Execute the preregistered canonical-state W4 WaterLily sensitivity matrix."""

import csv
import hashlib
import json
import math
import os
import platform
import sys
import subprocess
import tempfile
import traceback
import urllib.request
from pathlib import Path


STAGE = "w4_v17_candidate_c"
OUT_ROOT = Path("/kaggle/working")
OUT = OUT_ROOT / STAGE
SOURCE_URL = "https://github.com/ramhachi/CFD_opt_sdf.git"
SOURCE_REF = "refs/heads/codex/kaggle-batch-migration"
SOURCE_FETCH_DEPTH = 24
JULIA_URL = "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-1.12.6-linux-x86_64.tar.gz"
FORCE_COLUMNS = [
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
]
EXPECTED_CASES = {
    "flow_16": (16, 0.05, [100, 48, 36], 0.2, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "flow_24": (24, 1.0 / 30.0, [150, 72, 54], 0.3, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "flow_32": (32, 0.025, [200, 96, 72], 0.4, [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]),
    "domain_xplus1m_16": (16, 0.05, [120, 48, 36], 0.2, [[-2.5, 3.5], [-1.2, 1.2], [-0.9, 0.9]]),
}
STATE = {"stage": "startup", "solver_step_invoked": [], "solver_step_returned": []}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def literal_false_flags(value):
    keys = {"shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology"}
    return isinstance(value, dict) and set(value) == keys and all(value[key] is False for key in keys)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     allow_nan=False) + "\n")


def set_stage(stage, **details):
    STATE["stage"] = stage
    STATE.update(details)
    write_json(OUT / "execution_state.json", STATE)


def command(args, log_path, *, env=None, timeout=3600):
    print("RUN", " ".join(map(str, args)), flush=True)
    with Path(log_path).open("w") as handle:
        result = subprocess.run(args, env=env, stdout=handle,
                                stderr=subprocess.STDOUT, timeout=timeout,
                                check=False)
    if result.returncode:
        raise RuntimeError(f"command exit {result.returncode}: {Path(log_path).name}")
    return Path(log_path).read_text(errors="replace")


def state_label(criteria):
    return criteria["geometry"].get("state_label", "v16")


def dataset_names(criteria):
    prefix = f"w4_{state_label(criteria)}"
    return {
        "criteria": f"{prefix}_criteria.json",
        "manifest": f"{prefix}_dataset_manifest.json",
        "output": f"{prefix}_sensitivity",
        "log": f"{prefix}.log",
    }


def discover_dataset(input_root=Path("/kaggle/input")):
    matches = sorted(input_root.rglob("w4_*_criteria.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one attached W4 criteria file, found {len(matches)}")
    return matches[0].parent


def read_criteria(dataset_dir):
    matches = sorted(Path(dataset_dir).glob("w4_*_criteria.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one attached W4 criteria file, found {len(matches)}")
    path = matches[0]
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise RuntimeError("registered W4 criteria or SHA sidecar missing")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise RuntimeError("W4 criteria SHA sidecar mismatch")
    criteria = json.loads(path.read_text())
    if (criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"):
        raise RuntimeError("W4 criteria are not an immutable preregistration")
    if criteria.get("source_commit") != criteria.get("registered_source_commit"):
        raise RuntimeError("W4 registered source commit fields disagree")
    label = state_label(criteria)
    if path.name != f"w4_{label}_criteria.json":
        raise RuntimeError("W4 criteria filename does not match its canonical state label")
    allowed_kinds = {
        "v16": {"waterlily_w4_v16_grid_domain_sensitivity_criteria"},
        "v17": {"waterlily_w4_canonical_grid_domain_sensitivity_criteria"},
        "v17_candidate_c": {"waterlily_w4_candidate_c_canonical_grid_domain_sensitivity_criteria"},
    }
    if criteria.get("kind") not in allowed_kinds.get(label, set()):
        raise RuntimeError("unexpected W4 criteria kind/state-label pairing")
    if not criteria.get("input_dataset_id"):
        raise RuntimeError("W4 criteria do not bind a private input dataset")
    if label == "v17_candidate_c":
        if (criteria.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w4-v17-candidate-c"
                or criteria.get("input_dataset_id") != "ramhachi888/cfd-opt-sdf-v17-w4-candidate-c"):
            raise RuntimeError("W4 Candidate C kernel/dataset identity mismatch")
    return criteria, digest


def validate_case_contract(criteria):
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
    if (label not in {"v16", "v17", "v17_candidate_c"}
            or not isinstance(state, dict)
            or geometry.get("state_label", "v16") != state.get("state_label")
            or geometry.get("canonical_state_sha256") != state.get("state_sha256")
            or geometry.get("canonical_state_npz_sha256") != state.get("state_npz_sha256")
            or geometry.get("canonical_phi_c_order_sha256") != state.get("phi_c_order_sha256")
            or geometry.get("canonical_phi_fortran_sha256") != state.get("phi_fortran_sha256")
            or geometry.get("source_surface_sha256") != state.get("source_surface_sha256")
            or geometry.get("point_shape") != state.get("point_shape")
            or geometry.get("cell_shape") != state.get("cell_shape")
            or geometry.get("canonical_sdf_origin_m") != state.get("canonical_sdf_origin_m")
            or geometry.get("design_lattice_spacing_m") != state.get("design_lattice_spacing_m")
            or len(geometry.get("canonical_state_sha256", "")) != 64
            or len(geometry.get("canonical_state_npz_sha256", "")) != 64
            or len(geometry.get("canonical_phi_c_order_sha256", "")) != 64
            or len(geometry.get("canonical_phi_fortran_sha256", "")) != 64
            or len(geometry.get("source_surface_sha256", "")) != 64
            or not isinstance(geometry.get("design_lattice_spacing_m"), (int, float))
            or geometry["design_lattice_spacing_m"] <= 0
            or geometry.get("point_shape") != [value + 1 for value in geometry.get("cell_shape", [])]
            or geometry.get("design_lattice_is_resampled") is not False
            or geometry.get("flow_grid_is_separate_from_design_lattice") is not True
            or geometry.get("baseline_flow_origin_m") != [-2.5, -1.2, -0.9]
            or geometry.get("baseline_physical_box_m") != [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]]
            or geometry.get("reynolds") != 80.0
            or geometry.get("density_kg_m3") != 1.0
            or geometry.get("dynamic_viscosity_pa_s") != 0.01
            or geometry.get("freestream_mps") != [1.0, 0.0, 0.0]
            or geometry.get("reference_length_m") != 0.8
            or geometry.get("reference_area_m2") != 0.64):
        raise RuntimeError("W4 canonical physical/design-grid contract drift")
    if [case.get("case_id") for case in criteria["cases"]] != list(EXPECTED_CASES):
        raise RuntimeError("W4 registered case inventory/order drift")
    for case in criteria["cases"]:
        n, dx, dims, viscosity, box = EXPECTED_CASES[case["case_id"]]
        if (case.get("factor") != ("domain_extent" if case["case_id"].startswith("domain_") else "flow_resolution")
                or case.get("cells_per_reference_length") != n
                or case.get("flow_dims") != dims
                or case.get("physical_box_m") != box
                or not math.isclose(case.get("flow_spacing_m", math.nan), dx, rel_tol=0, abs_tol=1e-12)
                or case.get("solver_length") != float(n)
                or not math.isclose(case.get("solver_time_unit_s", math.nan), dx, rel_tol=0, abs_tol=1e-12)
                or not math.isclose(case.get("solver_viscosity", math.nan), viscosity, rel_tol=0, abs_tol=1e-12)
                or case.get("reynolds") != 80.0
                or case.get("density_kg_m3") != 1.0
                or case.get("dynamic_viscosity_pa_s") != 0.01
                or case.get("freestream_mps") != [1.0, 0.0, 0.0]
                or case.get("reference_length_m") != 0.8
                or case.get("reference_area_m2") != 0.64):
            raise RuntimeError(f"W4 registered case mapping/scale drift: {case.get('case_id')}")
    if (measurement.get("target_t_u_l") != 120.0
            or measurement.get("burn_in_t_u_l") != 80.0
            or measurement.get("force_window_t_u_l") != [80.0, 120.0]
            or measurement.get("force_sample_every_solver_steps") != 8
            or measurement.get("minimum_force_window_samples") < 4
            or measurement.get("per_case_wall_time_limit_s") != 1800.0
            or measurement.get("aggregate_solver_wall_time_limit_s") != 5400.0
            or measurement.get("host_recompute_relative_tolerance") != 1e-9
            or measurement.get("force_component_relative_tolerance") != 1e-6
            or measurement.get("force_component_absolute_tolerance") != 1e-8
            or "exact [80,120] endpoints" not in measurement.get("primary_force_metric", "")
            or "sample the first step at or beyond" not in measurement.get("force_sample_policy", "")):
        raise RuntimeError("W4 measurement-window contract drift")
    stationarity = measurement.get("stationarity", {})
    w3_prereq = criteria.get("prerequisites", {}).get("w3_result_evidence", {})
    if (measurement.get("stationarity_gate") is not True
            or stationarity.get("window_t_u_l") != [80.0, 120.0]
            or stationarity.get("half_windows_t_u_l") != [[80.0, 100.0], [100.0, 120.0]]
            or stationarity.get("relative_half_window_drift_max") != 0.02
            or stationarity.get("quantities") != ["drag", "downforce"]
            or stationarity.get("mean_definition") !=
                "trapezoidal physical-time-weighted means on exact endpoint-clipped intervals"
            or stationarity.get("formula") !=
                "abs(mean_first - mean_second) / max(abs(mean_whole), eps(Float64))"
            or stationarity.get("precedent_criteria_path") != w3_prereq.get("criteria_path")
            or stationarity.get("precedent_criteria_sha256") != w3_prereq.get("criteria_sha256")):
        raise RuntimeError("W4 registered stationarity contract drift")
    comparison = criteria.get("w3_flow16_comparison", {})
    if (criteria.get("prerequisites", {}).get("w3_baseline_reused") is not False
            or criteria["prerequisites"].get("all_four_cases_reexecuted") is not True
            or criteria["prerequisites"].get("w3_flow16_comparison_required") is not True
            or criteria["prerequisites"].get("w3_flow16_numerical_repeatability_gate_registered") is not False
            or comparison.get("numerical_repeatability_gate_registered") is not False
            or comparison.get("required_fields") != [
                "drag_time_weighted_n", "downforce_time_weighted_n", "cd_time_weighted",
                "stationarity_relative_half_window_drift_drag",
                "stationarity_relative_half_window_drift_downforce", "steps", "t_u_l", "force_sign"]
            or "if drag force sign differs, stop matrix interpretation" not in comparison.get("interpretation_rule", "")):
        raise RuntimeError("W4 W3-flow_16 comparison contract drift")
    backend = criteria["backend"]
    if (backend.get("accelerator") != "NvidiaTeslaT4"
            or backend.get("machine_shape") != "NvidiaTeslaT4"
            or backend.get("gpu_name") != "Tesla T4"
            or backend.get("gpu_count") != 2
            or backend.get("cuda_visible_devices") != "0"
            or backend.get("julia_threads") != 1
            or not all(backend.get(key) for key in (
                "driver_version", "cuda_driver_api_version", "cuda_runtime_version",
                "cuda_jl_version", "compute_capability", "julia_version",
                "waterlily_version", "waterlily_backend"))
            or len(backend.get("julia_archive_sha256", "")) != 64):
        raise RuntimeError("W4 backend identity contract is incomplete or not a T4 cohort")
    profile = criteria["profile_semantics"]
    expected_profile = {
        "native_velocity_boundary": "v16_native_far_field_uBC: +x freestream velocity 1 m/s; other normal components zero",
        "side_top_tangential_boundary": "WaterLily native tangential zero-Neumann",
        "x_plus_boundary": "WaterLily convective exit",
        "pressure_boundary": "WaterLily projection pressure; no per-patch freestreamPressure input",
        "ground_model": "moving planar half-space on the expanded flow-domain bottom at world z=-0.9 m, with +x wall velocity 1 m/s",
        "force_integration_body": (criteria.get("operator", {}).get("force_integration_body")
                                   if label == "v17_candidate_c" else
                                   f"canonical {label} candidate GridSDF only; exclude auxiliary moving-ground half-space"),
        "drag_projection": [1.0, 0.0, 0.0],
        "downforce_projection": [0.0, 0.0, -1.0],
        "source_profile_equivalent": False,
        "physical_profile_qualified": False,
    }
    if profile != expected_profile:
        raise RuntimeError("W4 native WaterLily/ground/force semantics drift")
    if any(criteria["evidence_scope"].get(key) is not False for key in (
            "physical_profile_equivalence_qualified", "absolute_downforce_qualified",
            "stationarity_qualified", "grid_or_domain_convergence_qualified",
            "gradient_qualified", "reverse_mode_qualified", "topology_qualified",
            "optimizer_qualified", "shape_update_allowed")):
        raise RuntimeError("W4 criteria improperly promote an out-of-scope claim")


def verify_dataset(criteria, criteria_sha, dataset_dir):
    dataset_dir = Path(dataset_dir)
    names = dataset_names(criteria)
    criteria_path = dataset_dir / names["criteria"]
    sidecar_path = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    manifest_path = dataset_dir / names["manifest"]
    manifest = json.loads(manifest_path.read_text())
    if sha256(criteria_path) != criteria_sha or sidecar_path.read_text().strip() != criteria_sha:
        raise RuntimeError("W4 dataset criteria/sidecar mismatch")
    if manifest.get("dataset_id") != criteria["input_dataset_id"]:
        raise RuntimeError("W4 dataset id mismatch")
    if manifest.get("criteria_sha256") != criteria_sha:
        raise RuntimeError("W4 dataset manifest criteria binding mismatch")
    expected = registered_dataset_files(criteria)
    expected[names["criteria"]] = criteria_sha
    expected[names["criteria"] + ".sha256"] = sha256(sidecar_path)
    if set(manifest.get("files", {})) != set(expected):
        raise RuntimeError("W4 dataset manifest file inventory mismatch")
    actual_names = {path.name for path in dataset_dir.iterdir() if path.is_file()}
    if actual_names != set(expected) | {manifest_path.name}:
        raise RuntimeError("W4 attached dataset contains unregistered files")
    for name, expected_sha in expected.items():
        path = dataset_dir / name
        if not path.is_file() or sha256(path) != expected_sha:
            raise RuntimeError(f"W4 dataset file SHA-256 mismatch: {name}")
        if manifest["files"].get(name) != expected_sha:
            raise RuntimeError(f"W4 dataset manifest hash mismatch: {name}")
    return manifest_path


def registered_dataset_files(criteria):
    return {
        entry["path"]: entry["sha256"]
        for entry in criteria["inputs"].values()
        if entry.get("location") == "kaggle_dataset"
    }


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


def verify_state(criteria, dataset_dir):
    import numpy as np

    geometry = criteria["geometry"]
    entries = criteria["inputs"]
    state_path = Path(dataset_dir) / entries["canonical_state_npz"]["path"]
    raw_path = Path(dataset_dir) / entries["canonical_phi_fortran_raw"]["path"]
    if sha256(state_path) != entries["canonical_state_npz"]["sha256"]:
        raise RuntimeError("canonical W4 state NPZ SHA mismatch")
    if sha256(raw_path) != entries["canonical_phi_fortran_raw"]["sha256"]:
        raise RuntimeError("canonical W4 raw phi SHA mismatch")
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    if not np.isfinite(phi).all() or list(phi.shape) != geometry["point_shape"]:
        raise RuntimeError("canonical W4 phi shape or finiteness mismatch")
    if metadata.get("state_sha256") != geometry["canonical_state_sha256"]:
        raise RuntimeError("canonical W4 state identity mismatch")
    if metadata.get("source_sha256") != geometry["source_surface_sha256"]:
        raise RuntimeError("canonical W4 source-surface lineage mismatch")
    if metadata.get("shape") != geometry["point_shape"]:
        raise RuntimeError("canonical W4 point shape metadata mismatch")
    if (metadata.get("origin_m") != geometry["canonical_sdf_origin_m"]
            or metadata.get("spacing_m") != geometry["design_lattice_spacing_m"]):
        raise RuntimeError("canonical W4 design-lattice metadata mismatch")
    phi_c = sha256_bytes(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C"))
    phi_f = sha256_bytes(np.asarray(phi, dtype="<f4", order="F").tobytes(order="F"))
    if phi_c != geometry["canonical_phi_c_order_sha256"]:
        raise RuntimeError("canonical W4 C-order phi hash mismatch")
    if metadata.get("phi_sha256") != phi_c:
        raise RuntimeError("canonical W4 state metadata C-order phi binding mismatch")
    if phi_f != geometry["canonical_phi_fortran_sha256"]:
        raise RuntimeError("canonical W4 Fortran-order phi hash mismatch")
    if raw_path.read_bytes() != np.asarray(phi, dtype="<f4", order="F").tobytes(order="F"):
        raise RuntimeError("canonical W4 raw phi differs from NPZ Fortran bytes")
    margin = zero_level_margin_m(phi, geometry["design_lattice_spacing_m"],
                                 geometry.get("state_label", "v16"))
    if (not math.isfinite(margin)
            or abs(margin - geometry["phi_expected_margin_m"]) > geometry["phi_margin_tolerance_m"]
            or margin < geometry["phi_margin_gate_m"]):
        raise RuntimeError("canonical W4 CPU-side measured SDF margin failed")
    return state_path, raw_path, metadata, margin


def gpu_inventory(criteria):
    text = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,driver_version",
         "--format=csv,noheader"], text=True)
    (OUT / "nvidia_smi.csv").write_text(text)
    rows = [[cell.strip() for cell in row]
            for row in csv.reader(text.splitlines()) if row]
    expected = criteria["backend"]
    if len(rows) != expected["gpu_count"]:
        raise RuntimeError("W4 registered T4 inventory count mismatch")
    if [row[0] for row in rows] != [str(index) for index in range(len(rows))]:
        raise RuntimeError("W4 GPU index inventory mismatch")
    uuids = [row[2] for row in rows]
    if (len(set(uuids)) != len(uuids) or any(not value.startswith("GPU-") for value in uuids)
            or any(expected["gpu_name"] not in row[1] for row in rows)
            or any(row[-1] != expected["driver_version"] for row in rows)):
        raise RuntimeError("W4 registered T4 identity mismatch")
    return [", ".join(row) for row in rows], uuids[0]


def verify_source(source, criteria):
    for name, entry in criteria["inputs"].items():
        if entry.get("location") == "source_repo":
            path = Path(source) / entry["path"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise RuntimeError(f"registered W4 source input SHA mismatch: {name}")
    project = Path(source) / "julia/CFDSDFWaterLilyT4"
    for name in ("project", "manifest"):
        entry = criteria["inputs"][name]
        if sha256(project / Path(entry["path"]).name) != entry["sha256"]:
            raise RuntimeError(f"registered W4 Julia {name} SHA mismatch")
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    pinned_sources = {entry.get("path"): entry.get("sha256")
                      for entry in criteria["inputs"].values()
                      if entry.get("location") == "source_repo"}
    if (pinned_sources.get(prereq["criteria_path"]) != prereq["criteria_sha256"]
            or pinned_sources.get(prereq["path"]) != prereq["sha256"]):
        raise RuntimeError("W3 prerequisite files are not included in the pinned W4 source inputs")
    w3_criteria_path = Path(source) / prereq["criteria_path"]
    if sha256(w3_criteria_path) != prereq["criteria_sha256"]:
        raise RuntimeError("bound W3 criteria SHA mismatch")
    w3_criteria = json.loads(w3_criteria_path.read_text())
    if (w3_criteria.get("immutable") is not True
            or w3_criteria.get("registered_before_computation") is not True
            or w3_criteria.get("source_commit") != w3_criteria.get("registered_source_commit")
            or w3_criteria.get("geometry", {}).get("state_label") != "v17_candidate_c"
            or w3_criteria.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
            or w3_criteria.get("operator", {}).get("identity") != "candidate_c_moment_blend+normal_floor_0.25"):
        raise RuntimeError("bound W3 criteria are not immutable preregistration")
    result_path = Path(source) / prereq["path"]
    if sha256(result_path) != prereq["sha256"]:
        raise RuntimeError("bound W3 PASS evidence SHA mismatch")
    result = json.loads(result_path.read_text())
    if (prereq.get("host_verified") is not True
            or result.get("verdict") != "PASS"
            or result.get("host_verification_passed") is not True
            or result.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
            or result.get("canonical_state_label") != "v17_candidate_c"
            or not literal_false_flags(result.get("candidate_c_qualification_flags"))
            or result.get("operator_identity_contract_sha256") != criteria.get("operator_identity_record_sha256")
            or result.get("criteria_sha256") != prereq["criteria_sha256"]
            or result.get("kernel_version") != prereq["kernel_version"]
            or result.get("source_commit") != w3_criteria["source_commit"]
            or result.get("backend_identity") != prereq["backend_identity"]
            or prereq["backend_identity"] != criteria["backend"]):
        raise RuntimeError("W4 prerequisite is not the bound host-verified W3 PASS")
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
    if bound_state != expected_state and not (
            expected_state["state_label"] == "v16" and bound_state is None):
        raise RuntimeError("W4 canonical state identity is not derived from its bound W3 criteria")
    geometry = criteria["geometry"]
    if (geometry.get("state_label", "v16") != expected_state["state_label"]
            or geometry.get("canonical_state_sha256") != expected_state["state_sha256"]
            or geometry.get("canonical_state_npz_sha256") != expected_state["state_npz_sha256"]
            or geometry.get("canonical_phi_c_order_sha256") != expected_state["phi_c_order_sha256"]
            or geometry.get("canonical_phi_fortran_sha256") != expected_state["phi_fortran_sha256"]
            or geometry.get("point_shape") != expected_state["point_shape"]
            or geometry.get("cell_shape") != expected_state["cell_shape"]
            or geometry.get("design_lattice_spacing_m") != expected_state["design_lattice_spacing_m"]
            or geometry.get("canonical_sdf_origin_m") != expected_state["canonical_sdf_origin_m"]
            or geometry.get("source_surface_sha256") != expected_state["source_surface_sha256"]):
        raise RuntimeError("W4 state criteria differ from the exact host-verified W3 state")
    return project, result


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


def main():
    global OUT, STAGE
    dataset_dir = discover_dataset()
    criteria, criteria_sha = read_criteria(dataset_dir)
    label = state_label(criteria)
    names = dataset_names(criteria)
    STAGE = names["output"]
    OUT = OUT_ROOT / STAGE
    OUT.mkdir(parents=True, exist_ok=True)
    set_stage("criteria_discovery", canonical_state_label=label)
    validate_case_contract(criteria)
    manifest_path = verify_dataset(criteria, criteria_sha, dataset_dir)
    set_stage("dataset_verified")
    runner_sha = sha256(Path(__file__))
    if runner_sha != criteria["inputs"]["kernel_runner"]["sha256"]:
        raise RuntimeError("W4 Kaggle runner SHA mismatch")
    state_path, raw_phi_path, state_metadata, margin = verify_state(criteria, dataset_dir)
    gpu_rows, selected_uuid = gpu_inventory(criteria)
    write_json(OUT / "input_state_metadata.json", state_metadata)
    (OUT / "input_dataset_manifest.json").write_bytes(manifest_path.read_bytes())
    (OUT / "input_criteria.json").write_bytes((dataset_dir / names["criteria"]).read_bytes())
    (OUT / "input_criteria.json.sha256").write_text(criteria_sha + "\n")
    with tempfile.TemporaryDirectory(prefix="cfd_w4_") as temp:
        base = Path(temp)
        source = base / "source"
        set_stage("source_fetch")
        command(["git", "init", "-q", str(source)], OUT / "git_init.log")
        command(["git", "-C", str(source), "fetch", "--depth", str(SOURCE_FETCH_DEPTH),
                 SOURCE_URL, SOURCE_REF], OUT / "git_fetch.log", timeout=600)
        commit = criteria["source_commit"]
        command(["git", "-C", str(source), "checkout", "--detach", commit], OUT / "git_checkout.log")
        actual_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                                text=True).strip()
        if actual_commit != commit:
            raise RuntimeError("W4 source commit mismatch")
        project, w3_result = verify_source(source, criteria)
        sys.path.insert(0, str(source / "src"))
        from cfd_sdf.candidate_c_identity import load_candidate_c_identity
        frozen = load_candidate_c_identity(source)
        identity_record = json.loads((source / frozen["contract_path"]).read_text())
        record_entry = criteria["inputs"]["operator_identity_record"]
        sidecar_entry = criteria["inputs"]["operator_identity_sha256"]
        if (record_entry["path"] != frozen["contract_path"]
                or record_entry["sha256"] != frozen["contract_sha256"]
                or criteria["operator"] != identity_record["operator"]
                or not literal_false_flags(criteria.get("qualification_flags"))
                or sidecar_entry["path"] != frozen["contract_path"] + ".sha256"
                or sha256(source / sidecar_entry["path"]) != sidecar_entry["sha256"]):
            raise RuntimeError("W4 criteria do not bind the exact frozen Candidate C identity")
        julia = install_julia(base, criteria)
        env = os.environ.copy()
        env.update({"JULIA_NUM_THREADS": str(criteria["backend"]["julia_threads"]),
                    "CUDA_VISIBLE_DEVICES": criteria["backend"]["cuda_visible_devices"],
                    "W4_SELECTED_GPU_UUID": selected_uuid,
                    "W4_CANONICAL_STATE_LABEL": label,
                    "W4_STATE_SHA256": criteria["geometry"]["canonical_state_sha256"],
                    "W4_STATE_NPZ_SHA256": criteria["geometry"]["canonical_state_npz_sha256"],
                    "W4_PHI_C_ORDER_SHA256": criteria["geometry"]["canonical_phi_c_order_sha256"],
                    "W4_PHI_FORTRAN_SHA256": criteria["geometry"]["canonical_phi_fortran_sha256"],
                    "W4_SOURCE_SURFACE_SHA256": criteria["geometry"]["source_surface_sha256"],
                    "W4_POINT_SHAPE": ",".join(map(str, criteria["geometry"]["point_shape"])),
                    "W4_CELL_SHAPE": ",".join(map(str, criteria["geometry"]["cell_shape"])),
                    "W4_CANONICAL_ORIGIN_M": ",".join(map(str, criteria["geometry"]["canonical_sdf_origin_m"])),
                    "W4_CANONICAL_DESIGN_SPACING_M": str(criteria["geometry"]["design_lattice_spacing_m"]),
                    "W4_EXPECTED_MARGIN_M": str(criteria["geometry"]["phi_expected_margin_m"]),
                    "W4_MARGIN_TOLERANCE_M": str(criteria["geometry"]["phi_margin_tolerance_m"]),
                    "W4_MARGIN_GATE_M": str(criteria["geometry"]["phi_margin_gate_m"])})
        set_stage("project_instantiate")
        command([str(julia), "--startup-file=no", f"--project={project}", "-e",
                 "using Pkg; Pkg.instantiate()"], OUT / "instantiate.log", env=env, timeout=1800)
        for name in ("project", "manifest"):
            entry = criteria["inputs"][name]
            if sha256(project / Path(entry["path"]).name) != entry["sha256"]:
                raise RuntimeError(f"W4 Julia {name} changed during instantiate")
        set_stage("t4_smoke")
        smoke = command([str(julia), "--startup-file=no", f"--project={project}",
                         str(source / criteria["inputs"]["kaggle_smoke"]["path"])],
                        OUT / "julia_smoke.log", env=env, timeout=1200)
        backend = criteria["backend"]
        smoke_markers = (
            "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
            f"GPU_COMPUTE_CAPABILITY {backend['compute_capability']}",
            f"CUDA_DRIVER_VERSION {backend['cuda_driver_api_version']}",
            f"CUDA_RUNTIME_VERSION {backend['cuda_runtime_version']}",
            f"JULIA_VERSION {backend['julia_version']}",
            f"CUDA_JL_VERSION {backend['cuda_jl_version']}",
            f"WATERLILY_VERSION {backend['waterlily_version']}",
            f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP",
        )
        if any(marker not in smoke for marker in smoke_markers):
            raise RuntimeError("W4 preregistered T4 smoke identity mismatch")
        set_stage("julia_job", solver_step_invoked=[], solver_step_returned=[])
        job = source / criteria["inputs"]["job"]["path"]
        command([str(julia), "--startup-file=no", f"--project={project}", str(job),
                 str(raw_phi_path), str(OUT)], OUT / names["log"], env=env,
                timeout=criteria["measurement"]["aggregate_solver_wall_time_limit_s"] + 900)

    log_path = OUT / names["log"]
    log_text = log_path.read_text(errors="replace")
    invoked = [line.split()[-1] for line in log_text.splitlines()
               if line.startswith("W4_SOLVER_STEP_INVOKED ")]
    returned = [line.split()[-1] for line in log_text.splitlines()
                if line.startswith("W4_SOLVER_STEP_RETURNED ")]
    if invoked != [case["case_id"] for case in criteria["cases"]] or returned != invoked:
        raise RuntimeError("W4 solver-step progress markers do not cover the registered matrix")
    STATE["solver_step_invoked"] = invoked
    STATE["solver_step_returned"] = returned

    summaries, metrics_by_case, rows_by_case = {}, {}, {}
    for case in criteria["cases"]:
        case_id = case["case_id"]
        summary_path = OUT / f"{case_id}.summary.json"
        csv_path = OUT / f"{case_id}.forces.csv"
        if not summary_path.is_file() or not csv_path.is_file():
            raise RuntimeError(f"W4 output missing for {case_id}")
        summary = json.loads(summary_path.read_text())
        if sha256(csv_path) != summary.get("force_csv_sha256"):
            raise RuntimeError(f"W4 candidate-force CSV hash mismatch for {case_id}")
        rows = parse_force_csv(csv_path)
        metrics = recompute_case_metrics(rows, case, criteria["measurement"])
        summaries[case_id] = summary
        rows_by_case[case_id] = rows
        metrics_by_case[case_id] = metrics
    response = response_analysis(metrics_by_case)
    baseline_comparison = w3_flow16_comparison(
        w3_result, metrics_by_case["flow_16"], summaries["flow_16"], label)
    gates = evaluate_gates(criteria, summaries, metrics_by_case, rows_by_case, margin,
                           gpu_rows, smoke, actual_commit, runner_sha, criteria_sha)
    write_json(OUT / "fingerprint.json", {
        "criteria_sha256": criteria_sha,
        "dataset_id": criteria["input_dataset_id"],
        "source_commit": actual_commit,
        "runner_sha256": runner_sha,
        "source_input_sha256": {name: entry["sha256"] for name, entry in criteria["inputs"].items()
                                 if entry.get("location") == "source_repo"},
        "dataset_manifest_sha256": sha256(manifest_path),
        "state_npz_sha256": sha256(state_path),
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
        "gpu_inventory": gpu_rows,
        "selected_gpu_uuid": selected_uuid,
        "julia_archive_sha256": backend["julia_archive_sha256"],
        "platform": platform.platform(),
        "python": platform.python_version(),
    })
    write_json(OUT / "outcome.json", {
        "criteria_sha256": criteria_sha,
        "dataset_id": criteria["input_dataset_id"],
        "source_commit": actual_commit,
        "w3_result_evidence_sha256": criteria["prerequisites"]["w3_result_evidence"]["sha256"],
        "summaries": summaries,
        "host_recomputed_metrics": metrics_by_case,
        "response_analysis": response,
        "w3_flow16_comparison": baseline_comparison,
        "matrix_interpretation_allowed": baseline_comparison["force_sign_consistent"],
        "gates": gates,
        "matrix_execution_complete": all(gates.values()),
        "kind": f"kaggle_w4_{label}_sensitivity_execution",
        "canonical_state_label": label,
        "claim_scope": criteria["evidence_scope"].get("claim_scope"),
        "w4_sensitivity_matrix_passed": all(gates.values()),
        "fd05_execution_authorized": False,
        "physical_profile_equivalence_qualified": False,
        "absolute_downforce_qualified": False,
        "stationarity_qualified": False,
        "grid_or_domain_convergence_qualified": False,
        "gradient_qualified": False,
        "reverse_mode_qualified": False,
        "topology_qualified": False,
        "optimizer_qualified": False,
        "shape_update_allowed": False,
        "candidate_c_qualification_flags": {
            "shape_update_allowed": False,
            "fd_oracle": False,
            "field_gradient": False,
            "reverse": False,
            "optimizer": False,
            "topology": False,
        },
        "operator_identity": criteria.get("operator") if label == "v17_candidate_c" else None,
    })
    if not all(gates.values()):
        raise RuntimeError(f"W4 registered integrity gates failed: {gates}")
    set_stage("matrix_complete", solver_step_invoked=invoked, solver_step_returned=returned)
    manifest = {path.name: sha256(path) for path in sorted(OUT.iterdir())
                if path.is_file() and path.name not in {"sha256.json", "DONE"}}
    write_json(OUT / "sha256.json", manifest)
    (OUT / "DONE").write_text("W4 matrix execution complete; independent host verification required.\n")
    print(f"KAGGLE_W4_{label.upper()}_MATRIX_DONE", json.dumps(gates, sort_keys=True), flush=True)


def relative_delta(a, b):
    return None if a == b == 0 else abs(a - b) / max(abs(a), abs(b))


def response_analysis(metrics_by_case):
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
            left = metrics_by_case[left_case][quantity]
            right = metrics_by_case[right_case][quantity]
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
        resolution_a = metrics_by_case["flow_24"][quantity]
        resolution_b = metrics_by_case["flow_32"][quantity]
        domain_a = metrics_by_case["flow_16"][quantity]
        domain_b = metrics_by_case["domain_xplus1m_16"][quantity]
        resolution_delta = abs(resolution_a - resolution_b)
        domain_delta = abs(domain_a - domain_b)
        result[quantity] = {
            "flow16_to_flow24_delta_abs_n": detailed[quantity]["flow16_to_flow24"]["absolute_delta_n"],
            "flow16_to_flow24_delta_relative_percent": detailed[quantity]["flow16_to_flow24"]["relative_delta_percent"],
            "resolution_delta_abs_n": resolution_delta,
            "resolution_delta_relative": relative_delta(resolution_a, resolution_b),
            "resolution_delta_relative_percent": detailed[quantity]["flow24_to_flow32"]["relative_delta_percent"],
            "domain_delta_abs_n": domain_delta,
            "domain_delta_relative": relative_delta(domain_a, domain_b),
            "domain_delta_relative_percent": detailed[quantity]["flow16_to_extended_domain16"]["relative_delta_percent"],
            "extended_domain_fine_grid_required": domain_delta >= resolution_delta,
        }
    result["any_force_component_requires_extended_domain_fine_grid"] = any(
        result[key]["extended_domain_fine_grid_required"]
        for key in ("drag_time_weighted_n", "downforce_time_weighted_n")
    )
    return result


def w3_flow16_comparison(w3_result, metrics, summary, canonical_label="v16"):
    previous = w3_result["raw_measurements"]
    previous_label = "w3_round4" if canonical_label == "v16" else f"w3_{canonical_label}"
    current_label = "w4_flow_16"

    def compare(w3_value, w4_value):
        return {
            previous_label: w3_value,
            current_label: w4_value,
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
        "force_sign": {previous_label: drag_sign_w3, current_label: drag_sign_w4},
        "drag_time_weighted_n": compare(previous["drag_time_weighted_n"], metrics["drag_time_weighted_n"]),
        "downforce_time_weighted_n": compare(previous["downforce_time_weighted_n"], metrics["downforce_time_weighted_n"]),
        "cd_time_weighted": compare(previous["cd_time_weighted"], metrics["cd_time_weighted"]),
        "stationarity_relative_half_window_drift_drag": compare(
            previous["stationarity_relative_half_window_drift_drag"],
            metrics["stationarity_relative_half_window_drift_drag"]),
        "stationarity_relative_half_window_drift_downforce": compare(
            previous["stationarity_relative_half_window_drift_downforce"],
            metrics["stationarity_relative_half_window_drift_downforce"]),
        "steps": {previous_label: previous["steps"], current_label: summary["steps"]},
        "t_u_l": {previous_label: previous["t_end_reached"], current_label: summary["t_end_reached"]},
        "force_projection_semantics": "drag=+Fx; downforce=-Fz",
        "interpretation_rule": f"report all W3 {canonical_label} to W4 flow_16 deltas; if drag force sign differs, stop matrix interpretation and diagnose before FD",
        "interpretation_if_force_sign_differs": "stop matrix interpretation and diagnose before FD",
    }


def evaluate_gates(criteria, summaries, metrics, rows, margin, gpu_rows, smoke,
                   source_commit, runner_sha, criteria_sha):
    case_ids = [case["case_id"] for case in criteria["cases"]]
    expected_ids = ["flow_16", "flow_24", "flow_32", "domain_xplus1m_16"]
    measurement, geometry, backend = criteria["measurement"], criteria["geometry"], criteria["backend"]
    profile = criteria["profile_semantics"]
    label = state_label(criteria)
    source_inputs_ok = all(len(entry.get("sha256", "")) == 64
                           for entry in criteria["inputs"].values())
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    gates = {
        "T0_registered_inputs_and_w3_pass": source_inputs_ok and prereq.get("host_verified") is True,
        "T1_registered_case_matrix_complete": case_ids == expected_ids and set(summaries) == set(case_ids)
            and set(metrics) == set(case_ids) and set(rows) == set(case_ids),
        "T2_canonical_phi_and_margin_identity": all(
            s.get("canonical_state_label", "v16") == label
            and s.get("state_sha256") == geometry["canonical_state_sha256"]
            and s.get("state_npz_sha256") == geometry["canonical_state_npz_sha256"]
            and s.get("source_surface_sha256") == geometry["source_surface_sha256"]
            and s.get("phi_c_order_sha256") == geometry["canonical_phi_c_order_sha256"]
            and s.get("phi_fortran_sha256") == geometry["canonical_phi_fortran_sha256"]
            and s.get("canonical_design_point_shape", geometry["point_shape"]) == geometry["point_shape"]
            and s.get("canonical_design_cell_shape", geometry["cell_shape"]) == geometry["cell_shape"]
            and s.get("device_roundtrip_sha256") == geometry["canonical_phi_fortran_sha256"]
            and math.isclose(s.get("phi_margin_m", math.nan), margin,
                             rel_tol=0, abs_tol=geometry["phi_margin_tolerance_m"])
            and s.get("phi_margin_gate_m") == geometry["phi_margin_gate_m"]
            for s in summaries.values()) and margin >= geometry["phi_margin_gate_m"],
        "T3_case_mapping_and_reynolds": all(
            s.get("case_id") == case["case_id"]
            and s.get("flow_dims") == case["flow_dims"]
            and s.get("flow_origin_m") == geometry["baseline_flow_origin_m"]
            and s.get("canonical_sdf_origin_m") == geometry["canonical_sdf_origin_m"]
            and s.get("canonical_state_label", "v16") == label
            and s.get("canonical_design_point_shape", geometry["point_shape"]) == geometry["point_shape"]
            and s.get("canonical_design_cell_shape", geometry["cell_shape"]) == geometry["cell_shape"]
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
            for case in criteria["cases"] for s in [summaries.get(case["case_id"], {})]),
        "T4_native_profile_limitation_preserved": all(
            s.get("source_profile_equivalent") is False
            and s.get("physical_profile_qualified") is False
            and s.get("native_velocity_boundary") == profile["native_velocity_boundary"]
            and s.get("side_top_tangential_boundary") == profile["side_top_tangential_boundary"]
            and s.get("x_max_boundary") == profile["x_plus_boundary"]
            and s.get("pressure_boundary") == profile["pressure_boundary"]
            and s.get("ground_model") == profile["ground_model"]
            and s.get("force_integration_body") == profile["force_integration_body"]
            and s.get("force_projection_semantics") == "drag=+Fx; downforce=-Fz"
            for s in summaries.values()),
        "T5_T4_Julia_CUDA_WaterLily_identity": (
            len(gpu_rows) == backend["gpu_count"]
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
                f"GPU_NAME {backend['gpu_name']}", "NO_SOLVER_STEP"))),
        "T6_primal_completion_and_force_integrity": all(
            s.get("t_end_target") == measurement["target_t_u_l"]
            and s.get("t_end_reached", 0) >= measurement["target_t_u_l"]
            and s.get("steps", 0) > 0 and s.get("finite_u") is True
            and s.get("finite_p") is True and s.get("finite_forces") is True
            and s.get("force_samples") == len(rows.get(s.get("case_id"), []))
            and force_components_close(rows.get(s.get("case_id"), []), measurement)
            for s in summaries.values()),
        "T7_host_force_recomputation": all(
            close_summary(summaries[case_id], metrics[case_id], measurement["host_recompute_relative_tolerance"])
            for case_id in summaries),
        "T8_runtime_and_vram": all(
            0 < s.get("wall_seconds", 0) <= measurement["per_case_wall_time_limit_s"]
            and 0 < s.get("peak_vram_bytes", 0) < s.get("vram_total_bytes", 0)
            for s in summaries.values())
            and sum(s.get("wall_seconds", 0) for s in summaries.values())
            <= measurement["aggregate_solver_wall_time_limit_s"],
        "T9_exact_source_and_runner_identity": source_commit == criteria["source_commit"]
            and runner_sha == criteria["inputs"]["kernel_runner"]["sha256"]
            and len(criteria_sha) == 64,
        "T10_stationarity": all(
            math.isfinite(metrics[case_id].get(f"stationarity_relative_half_window_drift_{quantity}", math.nan))
            and metrics[case_id][f"stationarity_relative_half_window_drift_{quantity}"]
            <= measurement["stationarity"]["relative_half_window_drift_max"]
            for case_id in expected_ids
            for quantity in measurement["stationarity"]["quantities"]
        ),
    }
    return gates


if __name__ == "__main__":
    try:
        main()
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        log = OUT / f"{STAGE.replace('_sensitivity', '')}.log"
        if log.is_file():
            lines = log.read_text(errors="replace").splitlines()
            STATE["solver_step_invoked"] = [line.split()[-1] for line in lines
                if line.startswith("W4_SOLVER_STEP_INVOKED ")]
            STATE["solver_step_returned"] = [line.split()[-1] for line in lines
                if line.startswith("W4_SOLVER_STEP_RETURNED ")]
        STATE["failure"] = traceback.format_exc()
        write_json(OUT / "execution_state.json", STATE)
        (OUT / "ERROR.txt").write_text(STATE["failure"])
        write_json(OUT / "sha256.json", {
            path.name: sha256(path) for path in sorted(OUT.iterdir())
            if path.is_file() and path.name != "sha256.json"
        })
        raise
