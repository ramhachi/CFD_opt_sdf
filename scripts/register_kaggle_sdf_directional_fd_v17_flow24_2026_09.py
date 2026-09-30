#!/usr/bin/env python3
"""Register the new FD-05 round-1 criteria for canonical v17 on flow_24."""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import register_kaggle_sdf_directional_fd_v16_2026_09 as base


ROOT = base.ROOT
LABEL = "v17"
FLOW_CASE_ID = "flow_24"
CRITERIA_ID = "sdf_directional_fd_v17_flow24_2026_09"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-flow24-directional-fd-oracle"
KERNEL_ID = DATASET_ID + "-kernel"
OUTPUT = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_criteria_2026_09.json"
R5_PATH = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json"
R5_DIAGNOSTIC = ROOT / "docs/evidence/sdf_directional_fd_v16_round5_kernel4_diagnostic_2026_09.json"
V17_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
GENESIS = ROOT / "docs/evidence/sdf_native_genesis_v17_2026_09.json"
W3_CRITERIA = "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json"
W3_RESULT = "docs/evidence/kaggle_w3_v17_primal_result_2026_09.json"
W4_CRITERIA = "docs/evidence/kaggle_w4_v17_sensitivity_criteria_2026_09.json"
W4_RESULT = "docs/evidence/kaggle_w4_v17_sensitivity_result_2026_09.json"
DATASET_CRITERIA_NAME = "sdf_directional_fd_v17_flow24_criteria.json"
DATASET_MANIFEST_NAME = "sdf_directional_fd_v17_flow24_dataset_manifest.json"
OUTPUT_DIRECTORY = "sdf_directional_fd_v17_flow24"
KERNEL_DIR = "infra/kaggle/kernel_sdf_directional_fd_v17_flow24"


def read_registered(path_text: str) -> tuple[dict, str]:
    path = ROOT / path_text
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"required immutable v17 prerequisite or sidecar missing: {path_text}")
    digest = base.sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError(f"v17 prerequisite SHA sidecar mismatch: {path_text}")
    return json.loads(path.read_text()), digest


def v17_prerequisites() -> tuple[dict, dict, dict, dict, str, str, str, str]:
    w3c, w3c_sha = read_registered(W3_CRITERIA)
    w3r, w3r_sha = read_registered(W3_RESULT)
    w4c, w4c_sha = read_registered(W4_CRITERIA)
    w4r, w4r_sha = read_registered(W4_RESULT)
    genesis = json.loads(GENESIS.read_text())
    state = w4c["prerequisites"]["canonical_state_identity"]
    if (w3r.get("verdict") != "PASS" or w3r.get("host_verification_passed") is not True
            or not all(w3r.get("gates", {}).values())
            or w4r.get("verdict") != "PASS" or w4r.get("host_verification_passed") is not True
            or w4r.get("w4_sensitivity_matrix_passed") is not True
            or w4r.get("fd_entry_gate") != "OPEN"
            or w3c["inputs"]["canonical_state_npz"]["sha256"] != genesis["state"]["state_file_sha256"]
            or w4c["geometry"]["canonical_state_sha256"] != genesis["state"]["state_sha256"]
            or state["state_label"] != LABEL or w4r.get("canonical_state_label") != LABEL):
        raise ValueError("W3/W4 v17 prerequisites are not exact host-verified PASS evidence")
    backend = w4r["backend_identity"]
    if backend != w3r["backend_identity"]:
        raise ValueError("W3 and W4 v17 registered backend identities differ")
    flow_case = next((case for case in w4c["cases"] if case["case_id"] == FLOW_CASE_ID), None)
    measurement = w4r.get("force_metrics", {}).get(FLOW_CASE_ID, {})
    case_measurement = w4r.get("case_measurements", {}).get(FLOW_CASE_ID, {})
    if (flow_case is None or flow_case["flow_dims"] != [150, 72, 54]
            or abs(float(flow_case["flow_spacing_m"]) - 1 / 30) > 1e-12
            or flow_case["solver_length"] != 24.0 or flow_case["solver_viscosity"] != 0.3
            or flow_case["physical_box_m"] != w4c["geometry"]["baseline_physical_box_m"]
            or not all(key in measurement for key in ("drag_time_weighted_n", "downforce_time_weighted_n"))
            or case_measurement.get("total_drag_n") != measurement.get("drag_time_weighted_n")
            or case_measurement.get("total_downforce_n") != measurement.get("downforce_time_weighted_n")):
        raise ValueError("W4 v17 flow_24 case or host-recomputed reference is unavailable")
    return w3c, w3r, w4c, w4r, w3c_sha, w3r_sha, w4c_sha, w4r_sha


def assert_r5_unchanged(criteria: dict, r5: dict) -> None:
    """Enforce the R5 fixed contract mechanically, allowing only specified changes."""
    for field in ("measurement", "noise_and_plateau", "responses", "backend"):
        if criteria[field] != r5[field]:
            raise ValueError(f"FD-05 changed an R5-fixed contract block: {field}")
    expected_gates = list(r5["gates"])
    expected_gates[0] = "T0_exact_W3_v17_W4_v17_flow24_prerequisites"
    if criteria["gates"] != expected_gates:
        raise ValueError("FD-05 changed the R5 T0-T12 gate structure or meaning")
    expected_perturbation = copy.deepcopy(r5["perturbation"])
    expected_perturbation["epsilon_relative_to_design_spacing"] = [0.02, 0.04, 0.1, 0.2, 0.4]
    if criteria["perturbation"] != expected_perturbation:
        raise ValueError("FD-05 changed the R5 perturbation contract outside the specified relative-spacing update")
    if criteria["run_order"] != r5["run_order"] or len(criteria["perturbation_inventory"]) != 30:
        raise ValueError("FD-05 changed the R5 run composition/order or perturbation count")
    for field in ("epsilon_ladder_m", "signs", "clipping", "smoothing", "reinitialization",
                  "volume_correction", "total_fresh_primal_runs", "canonical_baseline_fresh_repeats"):
        if criteria["perturbation"][field] != r5["perturbation"][field]:
            raise ValueError(f"FD-05 changed the fixed R5 perturbation item: {field}")


def source_inputs() -> dict:
    paths = {
        "directional_fd_contract": "src/cfd_sdf/gradients/directional_fd.py",
        "criteria_draft": "docs/evidence/sdf_directional_fd_v16_criteria_draft_2026_09.json",
        "criteria_registrar": "scripts/register_kaggle_sdf_directional_fd_v16_2026_09.py",
        "v17_flow24_criteria_registrar": "scripts/register_kaggle_sdf_directional_fd_v17_flow24_2026_09.py",
        "dataset_preparer": "scripts/prepare_kaggle_sdf_directional_fd_v16_dataset_2026_09.py",
        "cpu_preflight": "scripts/preflight_kaggle_sdf_directional_fd_v16_cpu.py",
        "julia_job": "scripts/waterlily_sdf_directional_fd_v16_job.jl",
        "kernel_runner": f"{KERNEL_DIR}/runner.py",
        "shared_kernel_runner": "infra/kaggle/kernel_sdf_directional_fd_v16/runner.py",
        "kernel_metadata": f"{KERNEL_DIR}/kernel-metadata.json",
        "host_verifier": "scripts/verify_kaggle_sdf_directional_fd_v16.py",
        "contract_tests": "tests/test_sdf_directional_fd_contract.py",
        "harness_tests": "tests/test_kaggle_sdf_directional_fd_v16.py",
        "owner_run_type": "julia/CFDSDFWaterLily/src/OwnedV16Run.jl",
        "profile_adapter": "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl",
        "grid_sdf": "julia/CFDSDFWaterLily/src/GridSDFBody.jl",
        "device_grid": "julia/CFDSDFWaterLily/src/DeviceGridSDF.jl",
        "w4_case_module": "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl",
        "project": "julia/CFDSDFWaterLilyT4/Project.toml",
        "manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
        "cpu_project": "julia/CFDSDFWaterLily/Project.toml",
        "cpu_manifest": "julia/CFDSDFWaterLily/Manifest.toml",
        "kaggle_smoke": "scripts/w0b_t4_smoke.jl",
        "w3_criteria": W3_CRITERIA,
        "w3_result": W3_RESULT,
        "w4_criteria": W4_CRITERIA,
        "w4_result": W4_RESULT,
        "r5_criteria": "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round5.json",
        "r5_failure_diagnostic": "docs/evidence/sdf_directional_fd_v16_round5_kernel4_diagnostic_2026_09.json",
        "genesis_evidence": "docs/evidence/sdf_native_genesis_v17_2026_09.json",
    }
    return {name: base.source_entry(path) for name, path in paths.items()}


def build_criteria(source_commit: str) -> dict:
    r5 = json.loads(R5_PATH.read_text())
    r5_sha = base.sha256(R5_PATH)
    r5_diag_sha = base.sha256(R5_DIAGNOSTIC)
    if (R5_PATH.with_suffix(R5_PATH.suffix + ".sha256").read_text().strip() != r5_sha
            or r5_diag_sha != "0b49997661d059a23e4a3cde4952d5cc2a8176468bf3726c42758ff7a65322f8"
            or R5_DIAGNOSTIC.with_suffix(R5_DIAGNOSTIC.suffix + ".sha256").read_text().strip() != r5_diag_sha):
        raise ValueError("preserved R5 criteria/diagnostic identity mismatch")
    (w3c, w3r, w4c, w4r, w3c_sha, w3r_sha, w4c_sha, w4r_sha) = v17_prerequisites()
    genesis = json.loads(GENESIS.read_text())
    if GENESIS.with_suffix(GENESIS.suffix + ".sha256").read_text().strip() != base.sha256(GENESIS):
        raise ValueError("v17 genesis evidence sidecar mismatch")
    state = base.SDFDesignState.load(V17_STATE)
    state_npz_sha = base.sha256(V17_STATE)
    grid = genesis["grid_identity"]
    raw_phi_c_sha = base.phi_sha256(state.phi, order="C")
    raw_phi_f = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    raw_phi_f_sha = base.sha256_bytes(raw_phi_f)
    if (state_npz_sha != genesis["state"]["state_file_sha256"]
            or state.state_sha256 != genesis["state"]["state_sha256"]
            or list(state.shape) != grid["point_shape"]
            or list(state.origin_m) != grid["origin_m"] or state.spacing_m != grid["spacing_m"]
            or raw_phi_c_sha != genesis["state"]["phi_sha256"]
            or raw_phi_f_sha != genesis["state"]["phi_f4_fortran_sha256"]):
        raise ValueError("canonical v17 state does not match genesis evidence")

    geometry = copy.deepcopy(r5["geometry"])
    w4_geometry = w4c["geometry"]
    for key, value in {
        "state_label": LABEL,
        "canonical_state_npz": "sdf_design_state.npz",
        "canonical_state_npz_sha256": state_npz_sha,
        "canonical_state_sha256": state.state_sha256,
        "canonical_phi_c_order_sha256": raw_phi_c_sha,
        "canonical_phi_fortran_sha256": raw_phi_f_sha,
        "canonical_sdf_origin_m": list(state.origin_m),
        "design_spacing_m": state.spacing_m,
        "point_shape": list(state.shape),
        "cell_shape": grid["cell_shape"],
        "source_surface_sha256": state.source_sha256,
        "narrow_band_width_m": state.narrow_band_width_m,
        "canonical_phi_margin_m": base.zero_level_margin_m(state.phi, state.spacing_m),
        "design_mask_sha256": hashlib.sha256(np.ascontiguousarray(state.design_mask, dtype="u1").tobytes()).hexdigest(),
        "fixed_solid_mask_sha256": hashlib.sha256(np.ascontiguousarray(state.fixed_solid_mask, dtype="u1").tobytes()).hexdigest(),
        "forbidden_mask_sha256": hashlib.sha256(np.ascontiguousarray(state.forbidden_mask, dtype="u1").tobytes()).hexdigest(),
        "root_mask_sha256": hashlib.sha256(np.ascontiguousarray(state.root_mask, dtype="u1").tobytes()).hexdigest(),
    }.items():
        geometry[key] = value
    flow = copy.deepcopy(r5["geometry"]["flow_case"])
    flow_spec = next(case for case in w4c["cases"] if case["case_id"] == FLOW_CASE_ID)
    flow_origin = w4c["geometry"]["baseline_flow_origin_m"]
    flow.update({"case_id": FLOW_CASE_ID, "flow_dims": flow_spec["flow_dims"],
        "flow_origin_m": flow_origin, "physical_box_m": flow_spec["physical_box_m"],
        "flow_spacing_m": flow_spec["flow_spacing_m"], "solver_length": flow_spec["solver_length"],
        "solver_velocity": flow_spec["freestream_mps"][0],
        "solver_viscosity": flow_spec["solver_viscosity"],
        "solver_time_unit_s": flow_spec["solver_time_unit_s"],
        "density_kg_m3": flow_spec["density_kg_m3"],
        "dynamic_viscosity_pa_s": flow_spec["dynamic_viscosity_pa_s"],
        "freestream_mps": flow_spec["freestream_mps"],
        "reynolds": flow_spec["reynolds"],
        "reference_length_m": flow_spec["reference_length_m"],
        "reference_area_m2": flow_spec["reference_area_m2"],
        "moving_ground_world_plane_m": flow_origin[2],
        "ground_model": ("moving planar half-space at solver z=0, mapped to world z="
                         f"{flow_origin[2]} m by flow origin, with +x wall velocity 1 m/s"),
        "force_integration_body": f"canonical {LABEL} candidate GridSDF only; exclude auxiliary moving-ground half-space"})
    geometry["flow_case"] = flow
    directions = base.generate_directions(state)
    direction_audit = base.validate_directions(state, directions)
    direction_records, direction_inputs = {}, {}
    for direction_id in base.DIRECTION_IDS:
        raw = np.asarray(directions[direction_id], dtype="<f4", order="C").tobytes(order="C")
        digest = base.sha256_bytes(raw)
        if digest != direction_audit["direction_sha256"][direction_id]:
            raise ValueError(f"v17 direction serialization mismatch: {direction_id}")
        path = f"directions/{direction_id}.f4-c.raw"
        direction_records[direction_id] = {"dataset_path": path, "sha256": digest,
            "shape": list(state.shape), "dtype": "float32_little_endian", "order": "C"}
        direction_inputs[f"direction_{direction_id}"] = {"path": path, "sha256": digest,
            "location": "kaggle_dataset", "shape": list(state.shape),
            "dtype": "float32_little_endian", "order": "C"}
    perturbation_records, perturbation_inputs = [], {}
    for direction_id in base.DIRECTION_IDS:
        for epsilon_m in base.EPSILON_LADDER_M:
            for sign in (1, -1):
                child, identity = base.perturbed_state(state, directions[direction_id],
                    epsilon_m=epsilon_m, sign=sign, margin_gate_m=base.SDF_MARGIN_GATE_M)
                raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
                case_id = base.perturbation_case_id(direction_id, epsilon_m, sign)
                path = f"perturbations/{case_id}.phi-f4-fortran.raw"
                entry = {"case_id": case_id, "direction_id": direction_id,
                    "direction_sha256": direction_records[direction_id]["sha256"],
                    "epsilon_m": epsilon_m, "sign": sign, "parent_state_sha256": state.state_sha256,
                    "state_sha256": child.state_sha256, "dataset_path": path,
                    "phi_file_sha256": base.sha256_bytes(raw),
                    "phi_fortran_sha256": identity["phi_fortran_order_sha256"],
                    "phi_c_order_sha256": identity["phi_c_order_sha256"],
                    "shape": list(child.shape), "origin_m": list(child.origin_m),
                    "spacing_m": child.spacing_m,
                    "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
                    "changed_node_count": identity["changed_node_count"],
                    "zero_level_margin_m": identity["zero_level_margin_m"],
                    "margin_gate_m": base.SDF_MARGIN_GATE_M,
                    "masks_unchanged": identity["masks_unchanged"],
                    "outside_design_phi_identical": identity["outside_design_phi_identical"],
                    "reinitialization_applied": False, "smoothing_applied": False,
                    "volume_correction_applied": False, "clipping_applied": False}
                perturbation_records.append(entry)
                perturbation_inputs[f"perturbation_{case_id}"] = {"path": path,
                    "sha256": base.sha256_bytes(raw), "location": "kaggle_dataset",
                    "shape": list(child.shape), "dtype": "float32_little_endian", "order": "Fortran"}
    if len(perturbation_records) != 30 or min(x["zero_level_margin_m"] for x in perturbation_records) < base.SDF_MARGIN_GATE_M:
        raise ValueError("v17 30-perturbation identity/margin preflight failed")

    metadata_path = ROOT / f"{KERNEL_DIR}/kernel-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("id") != KERNEL_ID or metadata.get("dataset_sources") != [DATASET_ID]:
        raise ValueError("v17 flow24 kernel metadata ID/dataset binding mismatch")
    branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
    if branch != "codex/kaggle-batch-migration":
        raise ValueError(f"FD-05 criteria must be registered on codex/kaggle-batch-migration, got {branch}")
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip():
        raise ValueError("FD-05 criteria require a clean registered source checkout")
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    upstream = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "@{u}"], text=True).strip()
    if source_commit != head or head != upstream:
        raise ValueError("FD-05 source commit must be the clean pushed codex HEAD")

    inputs = source_inputs()
    inputs["canonical_state_npz"] = {"path": "sdf_design_state.npz", "sha256": state_npz_sha,
        "location": "kaggle_dataset"}
    inputs["canonical_phi_fortran_raw"] = {"path": "canonical_v17_phi_f4_fortran.raw",
        "sha256": raw_phi_f_sha, "location": "kaggle_dataset", "dtype": "float32_little_endian",
        "order": "Fortran", "shape": list(state.shape)}
    inputs.update(direction_inputs)
    inputs.update(perturbation_inputs)

    criteria = copy.deepcopy(r5)
    criteria.update({
        "criteria_id": CRITERIA_ID, "criteria_round": 1,
        "criteria_path": OUTPUT.relative_to(ROOT).as_posix(),
        "kind": "sdf_directional_fd_flow24_criteria",
        "status": "registered_not_run", "immutable": True,
        "registered_before_computation": True,
        "registered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "registered_source_commit": source_commit, "source_commit": source_commit,
        "source_tree_commit": source_commit,
        "input_dataset_id": DATASET_ID, "kernel_id": KERNEL_ID,
        "kernel_title": metadata["title"], "dataset_title": "CFD Opt SDF v17 Flow24 Directional FD Oracle Inputs",
        "inputs": inputs,
        "source_input_sha256": {name: entry["sha256"] for name, entry in inputs.items()
                                 if entry.get("location") == "source_repo"},
        "direction_generation_runtime": {"python_version": platform.python_version(),
            "numpy_version": np.__version__},
        "geometry": geometry, "directions": {**copy.deepcopy(r5["directions"]), "shape": list(state.shape)},
        "direction_inventory": direction_records, "direction_audit": direction_audit,
        "perturbation": {**copy.deepcopy(r5["perturbation"]),
            "epsilon_relative_to_design_spacing": [0.02, 0.04, 0.1, 0.2, 0.4]},
        "perturbation_inventory": perturbation_records,
        "run_order": list(base.registered_run_order()),
        "input_dataset_files": {entry["path"]: entry["sha256"] for entry in inputs.values()
                                if entry.get("location") == "kaggle_dataset"},
        "artifacts": {"dataset_criteria_filename": DATASET_CRITERIA_NAME,
            "dataset_manifest_filename": DATASET_MANIFEST_NAME,
            "kernel_output_directory": OUTPUT_DIRECTORY,
            "kernel_log_filename": "fd_run.log"},
        "round_reason": (
            "New FD contract round 1 for canonical v17 on the user-selected W4 flow_24 case. "
            "Absolute R5 epsilon values, signs, run order, measurement windows, gates, and thresholds are preserved; "
            "relative spacing is updated for h=0.025 m."
        ),
        "epsilon_relative_to_design_spacing_rationale": (
            "The absolute R5 ladder is retained for direct comparison; v17 design spacing is 0.025 m, "
            "so the ratios are 0.02, 0.04, 0.1, 0.2, and 0.4."
        ),
        "prerequisites": {
            "w3": {"criteria_path": W3_CRITERIA, "criteria_sha256": w3c_sha,
                "result_path": W3_RESULT, "result_sha256": w3r_sha, "host_verified": True,
                "kernel_version": w3r["kernel_version"], "selected_gpu_uuid": w3r["selected_gpu_uuid"],
                "backend_identity": w3r["backend_identity"]},
            "w4": {"criteria_path": W4_CRITERIA, "criteria_sha256": w4c_sha,
                "result_path": W4_RESULT, "result_sha256": w4r_sha, "host_verified": True,
                "kernel_version": w4r["kernel_version"], "selected_gpu_uuid": w4r["selected_gpu_uuid"],
                "fd_entry_gate": w4r["fd_entry_gate"], "extended_domain_fine_grid_required": False,
                "formal_fd_measurement_started": False,
                "observed_backend_identity_sha256": base.json_hash(w4r["backend_identity"]),
                "backend_identity": w4r["backend_identity"]},
        },
        "backend": w3r["backend_identity"],
        "w4_cross_check": {"case_id": FLOW_CASE_ID,
            "flow24_drag_reference_n": w4r["force_metrics"][FLOW_CASE_ID]["drag_time_weighted_n"],
            "flow24_downforce_reference_n": w4r["force_metrics"][FLOW_CASE_ID]["downforce_time_weighted_n"],
            "numerical_tolerance_gate_registered": False},
        "prior_failed_diagnostic": {"criteria_path": str(R5_PATH.relative_to(ROOT)),
            "criteria_sha256": r5_sha,
            "diagnostic_path": str(R5_DIAGNOSTIC.relative_to(ROOT)),
            "diagnostic_sha256": r5_diag_sha,
            "role": "prior round-5 fail-closed diagnostic; not a retry or a qualification"},
        "claims": {**copy.deepcopy(r5["claims"]),
            "target": "registered WaterLily flow_24 discrete finite-box primal response directional derivative oracle for canonical v17 SDF"},
        "formal_measurement_started": False,
    })
    for i, gate in enumerate(criteria["gates"]):
        if gate.startswith("T0_"):
            criteria["gates"][i] = "T0_exact_W3_v17_W4_v17_flow24_prerequisites"
    assert_r5_unchanged(criteria, r5)
    criteria["criteria_sha256"] = base.json_hash(criteria)
    return criteria


def main() -> int:
    sidecar = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
    if OUTPUT.exists() or sidecar.exists():
        raise SystemExit("FD-05 criteria already exist; immutable preregistration will not be overwritten")
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    criteria = build_criteria(commit)
    OUTPUT.write_text(json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = base.sha256(OUTPUT)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": OUTPUT.relative_to(ROOT).as_posix(),
        "criteria_sha256": digest, "source_commit": commit,
        "direction_count": len(criteria["direction_inventory"]),
        "perturbation_count": len(criteria["perturbation_inventory"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
